"""Deterministic federated round harness (plaintext simulation).

This is an in-process simulation of the legacy training loop. It never claims
encryption. The legacy script used the unseeded global ``random`` module and
positional client IDs; this port uses a seeded local RNG and immutable client
IDs, and records the difference explicitly.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable, Sequence

from ...errors import InputValidationError, IntegrityError, UnavailableError
from ..crypto.base import CentralizedCryptoBackend, CryptoBackend, chunk_count
from ..crypto.plaintext import PlaintextSimulationBackend
from ..dataset import PreprocessedDataset
from ..metrics import compute_metrics
from .backends import TrainingBackend
from .client import (
    BroadcastPackage,
    ClientUpdate,
    SimulatedClient,
    ciphertext_digest,
    make_broadcast,
    plaintext_update_size,
    verify_broadcast,
    weight_digest,
)
from .server import FLServer, WEIGHTING_MODES

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[float, str], None]
AbortCheck = Callable[[], bool]
WeightSink = Callable[[list[float]], None]

PAPER_EXPANSION_FACTOR = 16.57
EXPANSION_WARNING_TOLERANCE = 0.5

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
    batch_size: int = 512
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
    """IID round-robin partition used by the paper.

    Every client receives the same number of rows (``len(labels) // num_clients``)
    by interleaving indices, and the remainder is dropped. ``seed`` selects a
    deterministic rotation phase so different seeds still produce different
    (but equally sized) shards.
    """
    if num_clients <= 0:
        raise InputValidationError("num_clients must be positive")
    total = len(labels)
    size = total // num_clients
    if size == 0:
        raise InputValidationError(
            f"not enough rows ({total}) for {num_clients} clients"
        )
    used = size * num_clients
    offset = seed % num_clients
    shards: list[list[int]] = [[] for _ in range(num_clients)]
    for index in range(used):
        shards[(index + offset) % num_clients].append(index)
    return shards


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
        client_factory: type[SimulatedClient] = SimulatedClient,
        client_ids: Sequence[str] | None = None,
        starting_weights: Sequence[float] | None = None,
        measure_baseline: bool = False,
        assigned_shards: list[list[int]] | None = None,
        after_aggregate: Callable[[int, Sequence[float]], None] | None = None,
        mode: str = "plaintext_simulation",
        include_timing: bool = False,
    ) -> None:
        self.backend = backend
        self.config = config
        self.crypto = crypto or PlaintextSimulationBackend()
        self.abort_check = abort_check
        self.progress = progress
        self.final_weights_sink = final_weights_sink
        self.client_ids = list(client_ids) if client_ids is not None else [
            client_id_for(position + 1) for position in range(config.num_clients)
        ]
        if len(self.client_ids) != config.num_clients or len(set(self.client_ids)) != config.num_clients:
            raise InputValidationError("Supply one unique ID per client shard.")
        self.after_aggregate = after_aggregate
        self.starting_weights = starting_weights
        self.measure_baseline = measure_baseline
        self.assigned_shards = assigned_shards
        self.client_factory = client_factory
        self.mode = mode
        self.include_timing = include_timing

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
        if self.assigned_shards is not None:
            shards = self.assigned_shards
        clients = [
            self.client_factory(
                client_id=client_id,
                rows=[dataset.train_rows[index] for index in shard],
                labels=[dataset.train_labels[index] for index in shard],
                seed=derive_client_seed(self.config.seed, client_id),
            )
            for client_id, shard in zip(self.client_ids, shards)
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

        global_weights = list(self.starting_weights) if self.starting_weights is not None else self.backend.initial_weights(feature_count)
        baseline = _evaluate(self.backend, global_weights, dataset.test_rows, dataset.test_labels)[0] if self.measure_baseline else None
        records: list[dict[str, Any]] = []
        last_digest = weight_digest(global_weights)
        final_metrics: dict[str, float | None] | None = None
        evaluation_note: str | None = None

        for round_index in range(self.config.rounds):
            self._check_abort()
            round_start = time.time()
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

            aggregation_start = time.time()
            aggregation = server.aggregate(updates)
            aggregation_time = time.time() - aggregation_start

            record: dict[str, Any] = {
                "round": round_index,
                "global_hash_before": last_digest,
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
            if self.after_aggregate is not None:
                self.after_aggregate(round_index, global_weights)
            last_digest = aggregation.aggregate_digest
            final_metrics, evaluation_note = _evaluate(
                self.backend, global_weights, dataset.test_rows, dataset.test_labels
            )

            update_bytes = [
                plaintext_update_size(update.weights) for update in updates
            ]
            plaintext_avg_bytes = sum(update_bytes) / len(update_bytes)
            round_metrics: dict[str, Any] = {
                "round_index": round_index,
                "accuracy": final_metrics.get("accuracy"),
                "precision": final_metrics.get("precision"),
                "recall": final_metrics.get("recall"),
                "f1_score": final_metrics.get("f1"),
                "loss": final_metrics.get("log_loss"),
                "bytes_transmitted_per_client": round(plaintext_avg_bytes, 2),
                "plaintext_update_size_bytes": round(plaintext_avg_bytes, 2),
                "encrypted_update_size_bytes": 0.0,
                "expansion_ratio": None,
            }
            if self.include_timing:
                round_metrics.update(
                    {
                        "training_time_seconds": round(time.time() - round_start, 4),
                        "encryption_time_seconds": 0.0,
                        "aggregation_time_seconds": round(aggregation_time, 4),
                        "decryption_time_seconds": 0.0,
                    }
                )
            record["metrics"] = round_metrics
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
            "round_metrics": [record["metrics"] for record in records if record["metrics"]],
            "baseline_metrics": baseline,
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
        include_timing: bool = False,
        client_factory=SimulatedClient, client_ids=None, assigned_shards=None, starting_weights=None,
    ) -> None:
        self.client_factory = client_factory
        self.client_ids = client_ids
        self.assigned_shards = assigned_shards
        self.starting_weights = starting_weights
        self.backend = backend
        self.config = config
        self.crypto = crypto
        self.keyring = keyring
        self.abort_check = abort_check
        self.progress = progress
        self.final_weights_sink = final_weights_sink
        self.context_hash = context_hash
        self.mode = "encrypted_federated"
        self.include_timing = include_timing
        self._expansion_warning_logged = False

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
        shards = self.assigned_shards if self.assigned_shards is not None else shards
        identities = self.client_ids or [client_id_for(i+1) for i in range(len(shards))]
        clients = [
            self.client_factory(
                client_id=identity,
                rows=[dataset.train_rows[index] for index in shard],
                labels=[dataset.train_labels[index] for index in shard],
                seed=derive_client_seed(self.config.seed, identity),
            )
            for identity, shard in zip(identities,shards)
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

        global_weights = list(self.starting_weights) if self.starting_weights is not None else self.backend.initial_weights(feature_count)
        baseline = _evaluate(self.backend,global_weights,dataset.test_rows,dataset.test_labels)[0] if self.starting_weights is not None else None
        records: list[dict[str, Any]] = []
        last_digest = ""
        last_broadcast: BroadcastPackage | None = None
        final_metrics: dict[str, float | None] | None = None
        evaluation_note: str | None = None

        for round_index in range(self.config.rounds):
            self._check_abort()
            round_start = time.time()
            self._report(
                round_index / self.config.rounds,
                f"round {round_index + 1}/{self.config.rounds}: encrypting local deltas",
            )
            updates = []
            encryption_seconds = 0.0
            for client in clients:
                self._check_abort()
                token = server.issue_auth_token(client.client_id)
                encrypt_start = time.time()
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
                        broadcast=last_broadcast,
                    )
                )
                encryption_seconds += time.time() - encrypt_start

            aggregation_start = time.time()
            aggregation = server.aggregate_encrypted(updates, self.crypto)
            aggregation_time = time.time() - aggregation_start

            record: dict[str, Any] = {
                "round": round_index,
                "updates": [update.as_dict() for update in updates],
                "scaling_factors": [float(value) for value in aggregation.scaling_factors],
                "aggregate_digest": aggregation.aggregate_digest,
                "global_hash_before": weight_digest(global_weights),
                "chunk_count": len(aggregation.chunks),
                "aggregate_ciphertext_bytes": aggregation.total_ciphertext_bytes,
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

            # Phase 2, lines 9-10: verify the SHA-256 hash of the encrypted
            # global model before the client-side keyring decrypts it.
            broadcast = make_broadcast(round_index, aggregation.chunks)
            try:
                verify_broadcast(broadcast)
            except IntegrityError as exc:
                record["aborted"] = True
                record["reason"] = str(exc)
                record["broadcast_hash"] = broadcast.hash
                record["broadcast_hash_verified"] = False
                records.append(record)
                continue
            record["broadcast_hash"] = broadcast.hash
            record["broadcast_hash_verified"] = True

            self._report(
                (round_index + 0.5) / self.config.rounds,
                f"round {round_index + 1}/{self.config.rounds}: client-side decryption",
            )
            decrypt_start = time.time()
            delta = self.keyring.decrypt_aggregate(list(aggregation.chunks), expected)
            decryption_time = time.time() - decrypt_start
            if len(delta) != expected:
                raise UnavailableError(
                    f"decrypted delta has {len(delta)} values; expected {expected}"
                )
            global_weights = [
                float(global_value) + float(delta_value)
                for global_value, delta_value in zip(global_weights, delta)
            ]
            record["global_hash_after"] = weight_digest(global_weights)
            last_digest = aggregation.aggregate_digest
            last_broadcast = broadcast
            final_metrics, evaluation_note = _evaluate(
                self.backend, global_weights, dataset.test_rows, dataset.test_labels
            )

            total_bytes = sum(len(chunk) for update in updates for chunk in update.chunks)
            encrypted_avg_bytes = total_bytes / len(updates)
            plaintext_avg_bytes = (
                sum(update.plaintext_size_bytes for update in updates) / len(updates)
            )
            expansion_ratio = (
                encrypted_avg_bytes / plaintext_avg_bytes
                if plaintext_avg_bytes
                else None
            )
            if (
                expansion_ratio is not None
                and abs(expansion_ratio - PAPER_EXPANSION_FACTOR)
                / PAPER_EXPANSION_FACTOR
                > EXPANSION_WARNING_TOLERANCE
                and not self._expansion_warning_logged
            ):
                logger.warning(
                    "communication expansion ratio %.4fx differs from the paper's "
                    "%.2fx claim (round %d)",
                    expansion_ratio,
                    PAPER_EXPANSION_FACTOR,
                    round_index,
                )
                self._expansion_warning_logged = True
            round_metrics: dict[str, Any] = {
                "round_index": round_index,
                "accuracy": final_metrics.get("accuracy"),
                "precision": final_metrics.get("precision"),
                "recall": final_metrics.get("recall"),
                "f1_score": final_metrics.get("f1"),
                "loss": final_metrics.get("log_loss"),
                "bytes_transmitted_per_client": round(encrypted_avg_bytes, 2),
                "plaintext_update_size_bytes": round(plaintext_avg_bytes, 2),
                "encrypted_update_size_bytes": round(encrypted_avg_bytes, 2),
                "expansion_ratio": (
                    round(expansion_ratio, 4) if expansion_ratio is not None else None
                ),
            }
            if self.include_timing:
                round_metrics.update(
                    {
                        "training_time_seconds": round(time.time() - round_start, 4),
                        "encryption_time_seconds": round(encryption_seconds, 4),
                        "aggregation_time_seconds": round(aggregation_time, 4),
                        "decryption_time_seconds": round(decryption_time, 4),
                    }
                )
            record["metrics"] = round_metrics
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
            "integrity": {
                "algorithm": "sha256",
                "broadcast_hash_verified": True,
                "last_broadcast_hash": (
                    last_broadcast.hash if last_broadcast is not None else None
                ),
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
            "round_metrics": [record["metrics"] for record in records if record["metrics"]],
            "baseline_metrics":baseline,
            "final_metrics": final_metrics,
            "final_metrics_note": evaluation_note,
            "aggregate_digest": last_digest,
        }
        return result
