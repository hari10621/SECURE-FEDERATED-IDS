"""Deterministic federated round harness (plaintext simulation).

This is an in-process simulation of the legacy training loop. It never claims
encryption. The legacy script used the unseeded global ``random`` module and
positional client IDs; this port uses a seeded local RNG and immutable client
IDs, and records the difference explicitly.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import asdict, dataclass
from typing import Any, Callable, Sequence

from ...errors import InputValidationError, UnavailableError
from ..crypto.base import CentralizedCryptoBackend, CryptoBackend, chunk_count
from ..crypto.plaintext import PlaintextSimulationBackend
from ..dataset import PreprocessedDataset
from ..metrics import compute_metrics
from .backends import TrainingBackend
from .client import (
    ClientUpdate,
    SimulatedClient,
    ciphertext_digest,
    weight_digest,
)
from .server import FLServer, WEIGHTING_MODES

ProgressCallback = Callable[[float, str], None]
AbortCheck = Callable[[], bool]
WeightSink = Callable[[list[float]], None]

LEGACY_DIFFERENCES = (
    "Plaintext simulation only: no CKKS encryption, DKG, or threshold "
    "decryption is performed, so results are not encrypted federated learning.",
    "Client partitioning uses a seeded local RNG; the legacy scripts used the "
    "unseeded global random module.",
    "Client IDs are assigned once at registration instead of positional indices "
    "derived from a shuffled list.",
    "The split and scaler are deterministic pure-Python ports and are not "
    "byte-identical to NumPy/scikit-learn.",
    "Legacy metric parity is unverified without the datasets and the native "
    "CKKS runtime.",
)


class FederatedAborted(Exception):
    """Raised when a caller-supplied abort check stops the harness."""


@dataclass(frozen=True)
class FederatedConfig:
    num_clients: int = 4
    rounds: int = 15
    local_epochs: int = 5
    batch_size: int = 32
    learning_rate: float = 0.0001
    threshold: int | None = None
    byzantine_threshold: int = 2
    weighting: str = "sample"
    byzantine_check: bool = False
    seed: int = 42
    require_encryption: bool = False

    def __post_init__(self) -> None:
        if self.num_clients <= 0:
            raise InputValidationError("num_clients must be positive")
        if self.rounds <= 0:
            raise InputValidationError("rounds must be positive")
        if self.local_epochs <= 0:
            raise InputValidationError("local_epochs must be positive")
        if self.batch_size <= 0:
            raise InputValidationError("batch_size must be positive")
        if self.learning_rate <= 0.0:
            raise InputValidationError("learning_rate must be positive")
        if self.weighting not in WEIGHTING_MODES:
            raise InputValidationError(
                f"weighting must be one of {', '.join(WEIGHTING_MODES)}"
            )
        if self.byzantine_threshold <= 0:
            raise InputValidationError("byzantine_threshold must be positive")
        if self.threshold is not None and not 1 <= self.threshold <= self.num_clients:
            raise InputValidationError("threshold must be between 1 and num_clients")

    @property
    def effective_threshold(self) -> int:
        return self.threshold if self.threshold is not None else max(1, self.num_clients - 1)

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["effective_threshold"] = self.effective_threshold
        return payload


def partition_training_indices(
    labels: Sequence[int],
    *,
    num_clients: int,
    seed: int,
) -> list[list[int]]:
    """Legacy floor partition on a seeded shuffle.

    ``create_clients`` in the research scripts shuffles ``zip(data, labels)``,
    takes ``len // num_clients`` rows per client, and drops the remainder. The
    same shape is kept here, but the shuffle is seeded for reproducibility.
    """
    if num_clients <= 0:
        raise InputValidationError("num_clients must be positive")
    total = len(labels)
    size = total // num_clients
    if size == 0:
        raise InputValidationError(
            f"not enough rows ({total}) for {num_clients} clients"
        )
    indices = list(range(total))
    random.Random(seed).shuffle(indices)
    used = size * num_clients
    return [
        sorted(indices[offset : offset + size])
        for offset in range(0, used, size)
    ]


def client_id_for(position: int) -> str:
    if position < 1:
        raise InputValidationError("client position is 1-based")
    return f"client-{position}"


def derive_client_seed(base_seed: int, client_id: str) -> int:
    digest = hashlib.sha256(f"{base_seed}:{client_id}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _evaluate(
    backend: TrainingBackend,
    weights: Sequence[float],
    rows: Sequence[Sequence[float]],
    labels: Sequence[int],
) -> tuple[dict[str, float | None], str | None]:
    probabilities = backend.predict(weights, rows)
    try:
        return compute_metrics(labels, probabilities), None
    except InputValidationError as exc:
        try:
            metrics = compute_metrics(labels, probabilities, include_auc=False)
        except InputValidationError:
            return {}, str(exc)
        metrics["auc"] = None
        return metrics, str(exc)


class FederatedHarness:
    def __init__(
        self,
        backend: TrainingBackend,
        config: FederatedConfig,
        *,
        crypto: CryptoBackend | None = None,
        abort_check: AbortCheck | None = None,
        progress: ProgressCallback | None = None,
        final_weights_sink: WeightSink | None = None,
        mode: str = "plaintext_simulation",
    ) -> None:
        self.backend = backend
        self.config = config
        self.crypto = crypto or PlaintextSimulationBackend()
        self.abort_check = abort_check
        self.progress = progress
        self.final_weights_sink = final_weights_sink
        self.mode = mode

    def _check_abort(self) -> None:
        if self.abort_check is not None and self.abort_check():
            raise FederatedAborted("federated simulation aborted by caller")

    def _report(self, fraction: float, message: str) -> None:
        if self.progress is not None:
            self.progress(max(0.0, min(1.0, fraction)), message)

    def run(self, dataset: PreprocessedDataset) -> dict[str, Any]:
        status = self.crypto.status()
        if self.config.require_encryption and not status.available:
            raise UnavailableError(
                "encrypted federated execution is unavailable",
                details={"crypto": status.as_dict()},
            )

        feature_count = dataset.feature_count
        if feature_count <= 0:
            raise InputValidationError("dataset has no features")
        if not dataset.train_rows or not dataset.test_rows:
            raise InputValidationError("train and test partitions must both be non-empty")

        self._report(0.0, "partitioning simulated clients")
        shards = partition_training_indices(
            dataset.train_labels,
            num_clients=self.config.num_clients,
            seed=self.config.seed,
        )
        clients = [
            SimulatedClient(
                client_id=client_id_for(position),
                rows=[dataset.train_rows[index] for index in shard],
                labels=[dataset.train_labels[index] for index in shard],
                seed=derive_client_seed(self.config.seed, client_id_for(position)),
            )
            for position, shard in enumerate(shards, start=1)
        ]

        expected = self.backend.parameter_count(feature_count)
        server = FLServer(
            num_clients=self.config.num_clients,
            threshold=self.config.effective_threshold,
            expected_parameter_count=expected,
            weighting=self.config.weighting,
            byzantine_threshold=self.config.byzantine_threshold,
            byzantine_check=self.config.byzantine_check,
            batch_size=self.config.batch_size,
        )
        for client in clients:
            server.register_client(client.client_id, client.sample_count)

        global_weights = self.backend.initial_weights(feature_count)
        records: list[dict[str, Any]] = []
        last_digest = weight_digest(global_weights)
        final_metrics: dict[str, float | None] | None = None
        evaluation_note: str | None = None

        for round_index in range(self.config.rounds):
            self._check_abort()
            updates: list[ClientUpdate] = []
            self._report(
                round_index / self.config.rounds,
                f"round {round_index + 1}/{self.config.rounds}: local training",
            )
            for client in clients:
                self._check_abort()
                update = client.train(
                    global_weights,
                    self.backend,
                    round_index=round_index,
                    epochs=self.config.local_epochs,
                    batch_size=self.config.batch_size,
                    learning_rate=self.config.learning_rate,
                )
                updates.append(update)

            aggregation = server.aggregate(updates)
            record: dict[str, Any] = {
                "round": round_index,
                "updates": [update.as_dict() for update in updates],
                "scaling_factors": [float(value) for value in aggregation.scaling_factors],
                "aggregate_digest": aggregation.aggregate_digest,
                "aborted": aggregation.aborted,
                "reason": aggregation.reason,
                "byzantine_flagged": list(aggregation.byzantine_flagged),
                "metrics": None,
            }
            if aggregation.aborted:
                records.append(record)
                continue

            global_weights = list(aggregation.weights)
            last_digest = aggregation.aggregate_digest
            final_metrics, evaluation_note = _evaluate(
                self.backend, global_weights, dataset.test_rows, dataset.test_labels
            )
            record["metrics"] = final_metrics
            if evaluation_note:
                record["metrics_note"] = evaluation_note
            records.append(record)

        if final_metrics is None:
            final_metrics, evaluation_note = _evaluate(
                self.backend, global_weights, dataset.test_rows, dataset.test_labels
            )

        if self.final_weights_sink is not None:
            self.final_weights_sink(list(global_weights))

        self._report(1.0, "federated run complete")
        differences = list(LEGACY_DIFFERENCES) + list(dataset.differences)
        if self.backend.research_model:
            differences.append(
                "The research GRU runs through the installed TensorFlow/Keras "
                "version; results are not byte-identical across TensorFlow releases."
            )
            parity_note = (
                "No parity claim is made. The Keras GRU ran in this runtime, but "
                "preprocessing parity and CKKS parity remain unverified."
            )
        else:
            differences.append(
                "The reference linear backend is a harness double, not the research GRU."
            )
            parity_note = (
                "No parity claim is made. Reproducing legacy metrics requires the "
                "approved datasets, a TensorFlow GRU runtime, and a verified native "
                "CKKS backend."
            )
        result = {
            "mode": self.mode,
            "encrypted": False,
            "encryption_claimed": False,
            "crypto": status.as_dict(),
            "model": {
                "name": self.backend.name,
                "research_model": self.backend.research_model,
                "parameter_count": expected,
            },
            "parity": "unverified",
            "parity_note": parity_note,
            "legacy_differences": differences,
            "config": self.config.as_dict(),
            "dataset": dataset.summary(),
            "rounds": records,
            "final_metrics": final_metrics,
            "final_metrics_note": evaluation_note,
            "aggregate_digest": last_digest,
        }
        return result


class EncryptedFederatedHarness:
    """TenSEAL CKKS federated harness implementing the paper's update flow.

    ``crypto`` is the server-side backend (public context only). ``keyring`` is
    the client-side backend that also holds the secret context. The server only
    ever receives serialized ciphertext chunks; decryption happens in the
    keyring after the aggregate hash is verified.
    """

    def __init__(
        self,
        backend: TrainingBackend,
        config: FederatedConfig,
        crypto: CentralizedCryptoBackend,
        keyring: CentralizedCryptoBackend,
        *,
        abort_check: AbortCheck | None = None,
        progress: ProgressCallback | None = None,
        final_weights_sink: WeightSink | None = None,
        context_hash: str | None = None,
    ) -> None:
        self.backend = backend
        self.config = config
        self.crypto = crypto
        self.keyring = keyring
        self.abort_check = abort_check
        self.progress = progress
        self.final_weights_sink = final_weights_sink
        self.context_hash = context_hash
        self.mode = "encrypted_federated"

    def _check_abort(self) -> None:
        if self.abort_check is not None and self.abort_check():
            raise FederatedAborted("encrypted federated run aborted by caller")

    def _report(self, fraction: float, message: str) -> None:
        if self.progress is not None:
            self.progress(max(0.0, min(1.0, fraction)), message)

    def run(self, dataset: PreprocessedDataset) -> dict[str, Any]:
        status = self.crypto.status()
        if not status.available:
            raise UnavailableError(
                "encrypted federated execution is unavailable",
                details={"crypto": status.as_dict()},
            )
        feature_count = dataset.feature_count
        if feature_count <= 0:
            raise InputValidationError("dataset has no features")
        if not dataset.train_rows or not dataset.test_rows:
            raise InputValidationError("train and test partitions must both be non-empty")

        self._report(0.0, "partitioning simulated clients")
        shards = partition_training_indices(
            dataset.train_labels,
            num_clients=self.config.num_clients,
            seed=self.config.seed,
        )
        clients = [
            SimulatedClient(
                client_id=client_id_for(position),
                rows=[dataset.train_rows[index] for index in shard],
                labels=[dataset.train_labels[index] for index in shard],
                seed=derive_client_seed(self.config.seed, client_id_for(position)),
            )
            for position, shard in enumerate(shards, start=1)
        ]

        expected = self.backend.parameter_count(feature_count)
        batch_size = int(getattr(self.crypto, "batch_size", 4096))
        chunks_per_update = chunk_count(expected, batch_size)
        max_faults = self.config.num_clients // 2
        threshold = (
            self.config.threshold
            if self.config.threshold is not None
            else max(1, self.config.num_clients - max_faults)
        )
        server = FLServer(
            num_clients=self.config.num_clients,
            threshold=threshold,
            expected_parameter_count=expected,
            weighting=self.config.weighting,
            byzantine_threshold=self.config.byzantine_threshold,
            byzantine_check=False,
            byzantine_max_faults=max_faults,
            batch_size=self.config.batch_size,
        )
        for client in clients:
            server.register_client(client.client_id, client.sample_count)

        global_weights = self.backend.initial_weights(feature_count)
        records: list[dict[str, Any]] = []
        last_digest = ""
        final_metrics: dict[str, float | None] | None = None
        evaluation_note: str | None = None

        for round_index in range(self.config.rounds):
            self._check_abort()
            self._report(
                round_index / self.config.rounds,
                f"round {round_index + 1}/{self.config.rounds}: encrypting local deltas",
            )
            updates = []
            for client in clients:
                self._check_abort()
                token = server.issue_auth_token(client.client_id)
                updates.append(
                    client.train_encrypted(
                        global_weights,
                        self.backend,
                        self.crypto,
                        round_index=round_index,
                        epochs=self.config.local_epochs,
                        batch_size=self.config.batch_size,
                        learning_rate=self.config.learning_rate,
                        auth_token=token.token,
                        timestamp=token.timestamp,
                        nonce=token.nonce,
                    )
                )

            aggregation = server.aggregate_encrypted(updates, self.crypto)
            record: dict[str, Any] = {
                "round": round_index,
                "updates": [update.as_dict() for update in updates],
                "scaling_factors": [float(value) for value in aggregation.scaling_factors],
                "aggregate_digest": aggregation.aggregate_digest,
                "chunk_count": len(aggregation.chunks),
                "aborted": aggregation.aborted,
                "reason": aggregation.reason,
                "byzantine_flagged": list(aggregation.byzantine_flagged),
                "validation_errors": dict(aggregation.validation_errors),
                "metrics": None,
            }
            if aggregation.aborted:
                records.append(record)
                continue

            if ciphertext_digest(aggregation.chunks) != aggregation.aggregate_digest:
                record["aborted"] = True
                record["reason"] = "aggregate ciphertext hash mismatch"
                records.append(record)
                continue

            self._report(
                (round_index + 0.5) / self.config.rounds,
                f"round {round_index + 1}/{self.config.rounds}: client-side decryption",
            )
            delta = self.keyring.decrypt_aggregate(list(aggregation.chunks), expected)
            if len(delta) != expected:
                raise UnavailableError(
                    f"decrypted delta has {len(delta)} values; expected {expected}"
                )
            global_weights = [
                float(global_value) + float(delta_value)
                for global_value, delta_value in zip(global_weights, delta)
            ]
            last_digest = aggregation.aggregate_digest
            final_metrics, evaluation_note = _evaluate(
                self.backend, global_weights, dataset.test_rows, dataset.test_labels
            )
            record["metrics"] = final_metrics
            if evaluation_note:
                record["metrics_note"] = evaluation_note
            records.append(record)

        if final_metrics is None:
            final_metrics, evaluation_note = _evaluate(
                self.backend, global_weights, dataset.test_rows, dataset.test_labels
            )

        if self.final_weights_sink is not None:
            self.final_weights_sink(list(global_weights))

        self._report(1.0, "encrypted federated run complete")
        differences = [
            difference
            for difference in LEGACY_DIFFERENCES
            if not difference.startswith("Plaintext simulation only")
        ] + list(dataset.differences) + [
            "Encrypted updates are CKKS-approximate; deltas are decrypted and "
            "added to the global weights on the client side.",
            "The server-side backend holds only the public context and never "
            "receives plaintext weights in this mode.",
            "The Trusted Authority is simulated in-process; key material is "
            "generated per run and is not persisted.",
        ]
        result = {
            "mode": self.mode,
            "encrypted": True,
            "encryption_claimed": True,
            "crypto": status.as_dict(),
            "crypto_params": (
                self.crypto.params()
                if hasattr(self.crypto, "params")
                else {}
            ),
            "ta_context_hash": self.context_hash,
            "model": {
                "name": self.backend.name,
                "research_model": self.backend.research_model,
                "parameter_count": expected,
            },
            "ciphertext": {
                "batch_size": batch_size,
                "chunks_per_update": chunks_per_update,
            },
            "parity": "unverified",
            "parity_note": (
                "No parity claim is made. CKKS encryption, aggregation, and "
                "decryption ran, but dataset preprocessing parity and paper "
                "metric parity remain unverified."
            ),
            "legacy_differences": differences,
            "config": self.config.as_dict(),
            "dataset": dataset.summary(),
            "rounds": records,
            "final_metrics": final_metrics,
            "final_metrics_note": evaluation_note,
            "aggregate_digest": last_digest,
        }
        return result
