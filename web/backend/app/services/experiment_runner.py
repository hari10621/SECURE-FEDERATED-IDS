"""Automated paper experiment runner.

Runs the paper's comparison matrix in one pass:

* centralized training (upper-bound baseline)
* plaintext federated learning for N in {4, 8, 12}
* CKKS-encrypted federated learning for N in {4, 8, 12}

Every run is persisted to a JSON file and a comparison summary is returned.
For encrypted runs the runner also records the total bytes transmitted and the
average ciphertext bytes per client per round so the paper's claimed 16.57x
communication expansion can be checked against the observed factor.
"""

from __future__ import annotations

import json
import random
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from ..config import Settings
from ..domain.dataset import LoadedDataset, PreprocessedDataset, load_csv_dataset, preprocess
from ..domain.federated.keras_backend import KerasGRUBackend
from ..domain.federated.round import (
    EncryptedFederatedHarness,
    FederatedAborted,
    FederatedConfig,
    FederatedHarness,
)
from ..domain.metrics import compute_metrics
from ..errors import InputValidationError, JobCancelled, UnavailableError
from .encryption_service import EncryptionService
from .preprocessing_service import detect_dataset_type

PAPER_EXPANSION_FACTOR = 16.57
DEFAULT_CLIENT_COUNTS = (4, 8, 12)
METRIC_KEYS = ("accuracy", "precision", "recall", "f1")

ProgressCallback = Callable[[float, str], None]
CancelCheck = Callable[[], bool]


def _check_cancel(cancel_check: CancelCheck | None) -> None:
    if cancel_check is not None and cancel_check():
        raise JobCancelled("paper suite cancellation requested")


def _metric_subset(metrics: dict[str, Any] | None) -> dict[str, Any]:
    metrics = metrics or {}
    return {key: metrics.get(key) for key in METRIC_KEYS}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )


def _transmission_stats(
    round_metrics: Sequence[dict[str, Any]],
    client_count: int,
) -> dict[str, float]:
    per_round = [
        float(metric["bytes_transmitted_per_client"])
        for metric in round_metrics
        if metric and metric.get("bytes_transmitted_per_client") is not None
    ]
    if not per_round:
        return {
            "total_bytes_transmitted": 0.0,
            "avg_bytes_per_client_per_round": 0.0,
        }
    average = sum(per_round) / len(per_round)
    total = sum(value * client_count for value in per_round)
    return {
        "total_bytes_transmitted": round(total, 2),
        "avg_bytes_per_client_per_round": round(average, 2),
    }


@dataclass(frozen=True)
class _RunnerConfig:
    rounds: int
    local_epochs: int
    batch_size: int
    learning_rate: float
    seed: int
    test_size: float
    max_rows: int
    client_counts: tuple[int, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "rounds": self.rounds,
            "local_epochs": self.local_epochs,
            "batch_size": self.batch_size,
            "learning_rate": self.learning_rate,
            "seed": self.seed,
            "test_size": self.test_size,
            "max_rows": self.max_rows,
            "client_counts": list(self.client_counts),
        }


def _load_prepared(
    dataset_path: Path,
    *,
    label_column: str | None,
    max_rows: int,
    test_size: float,
    seed: int,
) -> tuple[LoadedDataset, PreprocessedDataset]:
    loaded = load_csv_dataset(
        dataset_path,
        label_column=label_column,
        max_rows=max_rows,
    )
    prepared = preprocess(
        loaded.rows,
        loaded.labels,
        feature_names=loaded.feature_names,
        mode="clean",
        test_size=test_size,
        seed=seed,
    )
    return loaded, prepared


def _run_centralized(
    backend: Any,
    prepared: PreprocessedDataset,
    config: _RunnerConfig,
) -> dict[str, Any]:
    weights = backend.initial_weights(prepared.feature_count)
    started = time.time()
    weights = backend.train(
        weights,
        prepared.train_rows,
        prepared.train_labels,
        epochs=config.local_epochs,
        batch_size=config.batch_size,
        learning_rate=config.learning_rate,
        rng=random.Random(config.seed),
    )
    training_time = time.time() - started
    probabilities = backend.predict(weights, prepared.test_rows)
    metrics = compute_metrics(prepared.test_labels, probabilities)
    return {
        "mode": "centralized_training",
        "training_mode": "centralized",
        "encrypted": False,
        "model": {
            "name": backend.name,
            "research_model": backend.research_model,
            "parameter_count": backend.parameter_count(prepared.feature_count),
        },
        "final_metrics": metrics,
        "training_time_seconds": round(training_time, 4),
        "config": config.as_dict(),
    }


def _run_plaintext(
    backend: Any,
    prepared: PreprocessedDataset,
    config: _RunnerConfig,
    client_count: int,
    *,
    abort_check: CancelCheck | None = None,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    federated_config = FederatedConfig(
        num_clients=client_count,
        rounds=config.rounds,
        local_epochs=config.local_epochs,
        batch_size=config.batch_size,
        learning_rate=config.learning_rate,
        seed=config.seed,
    )
    harness = FederatedHarness(
        backend,
        federated_config,
        abort_check=abort_check,
        progress=progress,
        mode="plaintext_federated_training",
        include_timing=True,
    )
    try:
        result = harness.run(prepared)
    except FederatedAborted as exc:
        raise JobCancelled(str(exc)) from exc
    result["training_mode"] = "federated_plaintext"
    return result


def _run_encrypted(
    backend: Any,
    prepared: PreprocessedDataset,
    config: _RunnerConfig,
    client_count: int,
    encryption: EncryptionService,
    *,
    abort_check: CancelCheck | None = None,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    federated_config = FederatedConfig(
        num_clients=client_count,
        rounds=config.rounds,
        local_epochs=config.local_epochs,
        batch_size=config.batch_size,
        learning_rate=config.learning_rate,
        seed=config.seed,
        require_encryption=True,
    )
    material = encryption.generate_key_material(
        parties=client_count,
        threshold=max(1, client_count - client_count // 2),
    )
    harness = EncryptedFederatedHarness(
        backend,
        federated_config,
        encryption.server_backend(material),
        encryption.client_keyring(material),
        abort_check=abort_check,
        progress=progress,
        context_hash=material.context_hash,
        include_timing=True,
    )
    try:
        result = harness.run(prepared)
    except FederatedAborted as exc:
        raise JobCancelled(str(exc)) from exc
    result["training_mode"] = "federated_he"
    return result


def _resolve_output_dir(
    settings: Settings,
    output_dir: str | Path | None,
    run_id: str,
) -> Path:
    root = Path(output_dir) if output_dir is not None else (
        Path(settings.data_dir or ".") / "paper_suite"
    )
    directory = (root / run_id).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def run_paper_experiments(
    dataset_path: str | Path,
    dataset_type: str | None = None,
    *,
    settings: Settings | None = None,
    rounds: int = 15,
    local_epochs: int = 5,
    batch_size: int = 512,
    learning_rate: float = 1e-4,
    seed: int = 42,
    test_size: float = 0.3,
    max_rows: int | None = None,
    client_counts: Sequence[int] = DEFAULT_CLIENT_COUNTS,
    include_centralized: bool = True,
    include_he: bool = True,
    backend_factory: Callable[[], Any] | None = None,
    encryption: EncryptionService | None = None,
    progress: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Run the paper's centralized / FL / HE comparison matrix.

    ``dataset_type`` is auto-detected when omitted. Results are written to
    ``output_dir/<run_id>`` and a comparison summary is returned. The summary
    includes ``centralized``, ``fl_plaintext``, and ``fl_he`` entries, plus the
    observed HE communication-expansion factor.
    """
    path = Path(dataset_path)
    if not path.exists():
        raise InputValidationError(f"dataset not found: {path}")
    if rounds <= 0 or local_epochs <= 0 or batch_size <= 0:
        raise InputValidationError("rounds, local_epochs and batch_size must be positive")
    counts = tuple(int(count) for count in client_counts)
    if not counts:
        raise InputValidationError("at least one client count is required")
    for count in counts:
        if count <= 0:
            raise InputValidationError("client counts must be positive")

    settings = settings or Settings.from_env()
    resolved_type = dataset_type or detect_dataset_type(str(path))
    row_cap = int(max_rows) if max_rows is not None else settings.training_max_rows
    config = _RunnerConfig(
        rounds=rounds,
        local_epochs=local_epochs,
        batch_size=batch_size,
        learning_rate=learning_rate,
        seed=seed,
        test_size=test_size,
        max_rows=row_cap,
        client_counts=counts,
    )
    factory = backend_factory or KerasGRUBackend

    run_id = f"paper-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    directory = _resolve_output_dir(settings, output_dir, run_id)

    def report(fraction: float, message: str) -> None:
        if progress is not None:
            progress(max(0.0, min(1.0, fraction)), message)

    def check() -> None:
        _check_cancel(cancel_check)

    report(0.0, "loading and preprocessing dataset")
    loaded, prepared = _load_prepared(
        path,
        label_column=None,
        max_rows=row_cap,
        test_size=test_size,
        seed=seed,
    )
    report(0.05, f"preprocessing complete ({prepared.feature_count} features)")

    he_encryption = encryption
    if include_he and he_encryption is None:
        he_encryption = EncryptionService(settings)
    he_available = bool(include_he and he_encryption is not None and he_encryption.is_available())
    he_reason = ""
    if include_he and not he_available:
        he_reason = (
            "CKKS backend is unavailable; set SECUREFED_ENABLE_CKKS=1 with TenSEAL "
            "installed to run the encrypted suite."
        )

    total_units = (1 if include_centralized else 0) + len(counts) + (len(counts) if he_available else 0)
    total_units = max(1, total_units)
    completed_units = 0
    artifacts: dict[str, str] = {}

    def unit_progress(base: float) -> ProgressCallback:
        return lambda fraction, message: report(
            (base + 0.95 * max(0.0, min(1.0, fraction))) / total_units,
            message,
        )

    summary: dict[str, Any] = {
        "centralized": None,
        "fl_plaintext": {},
        "fl_he": {},
    }
    plaintext_transmission: dict[int, dict[str, float]] = {}
    he_transmission: dict[int, dict[str, float]] = {}

    if include_centralized:
        check()
        report(0.06, "running centralized baseline")
        backend = factory()
        centralized = _run_centralized(backend, prepared, config)
        summary["centralized"] = _metric_subset(centralized["final_metrics"])
        artifact = directory / "centralized.json"
        _write_json(artifact, centralized)
        artifacts["centralized"] = str(artifact)
        completed_units += 1

    for count in counts:
        check()
        base = completed_units
        report((0.05 + (base / total_units) * 0.95), f"plaintext FL N={count}")
        result = _run_plaintext(
            factory(),
            prepared,
            config,
            count,
            abort_check=cancel_check,
            progress=unit_progress(base),
        )
        summary["fl_plaintext"][count] = _metric_subset(result.get("final_metrics"))
        plaintext_transmission[count] = _transmission_stats(
            result.get("round_metrics") or [], count
        )
        artifact = directory / f"fl_plaintext_n{count}.json"
        _write_json(artifact, result)
        artifacts[f"fl_plaintext_n{count}"] = str(artifact)
        completed_units += 1

    for count in counts:
        check()
        if not he_available:
            summary["fl_he"][count] = {
                **_metric_subset(None),
                "available": False,
                "reason": he_reason,
            }
            continue
        base = completed_units
        report((0.05 + (base / total_units) * 0.95), f"encrypted FL N={count}")
        try:
            result = _run_encrypted(
                factory(),
                prepared,
                config,
                count,
                he_encryption,
                abort_check=cancel_check,
                progress=unit_progress(base),
            )
        except UnavailableError as exc:
            summary["fl_he"][count] = {
                **_metric_subset(None),
                "available": False,
                "reason": str(exc),
            }
            continue
        metrics = _metric_subset(result.get("final_metrics"))
        stats = _transmission_stats(result.get("round_metrics") or [], count)
        plaintext_stats = plaintext_transmission.get(count, {})
        plaintext_avg = plaintext_stats.get("avg_bytes_per_client_per_round", 0.0)
        expansion = (
            round(stats["avg_bytes_per_client_per_round"] / plaintext_avg, 4)
            if plaintext_avg
            else None
        )
        summary["fl_he"][count] = {
            **metrics,
            "available": True,
            "total_bytes_transmitted": stats["total_bytes_transmitted"],
            "avg_bytes_per_client_per_round": stats["avg_bytes_per_client_per_round"],
            "plaintext_avg_bytes_per_client_per_round": plaintext_avg,
            "expansion_factor": expansion,
        }
        he_transmission[count] = stats
        artifact = directory / f"fl_he_n{count}.json"
        _write_json(artifact, result)
        artifacts[f"fl_he_n{count}"] = str(artifact)
        completed_units += 1

    observed_expansion = {
        str(count): summary["fl_he"][count].get("expansion_factor")
        for count in counts
        if summary["fl_he"].get(count, {}).get("available")
    }

    payload: dict[str, Any] = {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "path": str(path),
            "dataset_type": resolved_type,
            "loaded": loaded.as_dict(),
            "prepared": prepared.summary(),
        },
        "config": config.as_dict(),
        "centralized": summary["centralized"],
        "fl_plaintext": {str(count): entry for count, entry in summary["fl_plaintext"].items()},
        "fl_he": {str(count): entry for count, entry in summary["fl_he"].items()},
        "plaintext_transmission": {
            str(count): entry for count, entry in plaintext_transmission.items()
        },
        "he_transmission": {
            "runs": {str(count): entry for count, entry in he_transmission.items()},
            "paper_claimed_expansion_factor": PAPER_EXPANSION_FACTOR,
            "observed_expansion_factor": observed_expansion,
            "note": (
                "Expansion compares average CKKS ciphertext bytes per client per "
                "round against the plaintext update bytes for the same client "
                "count. The paper reports 16.57x."
            ),
        },
        "artifacts": artifacts,
        "notes": [
            "Clients are in-process simulations, not independent runtimes.",
            "Preprocessing uses the leakage-free clean split (scaler fit on train only).",
            "Metric parity against the paper is unverified.",
        ],
    }
    if he_reason:
        payload["he_unavailable_reason"] = he_reason

    summary_path = directory / "summary.json"
    payload["artifacts"]["summary"] = str(summary_path)
    _write_json(summary_path, payload)

    report(1.0, "paper suite complete")
    return payload
