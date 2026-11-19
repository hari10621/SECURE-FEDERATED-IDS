"""Opt-in plaintext federated GRU training over an uploaded dataset.

Training is deliberately separate from the encrypted research worker. It uses
the installed TensorFlow/Keras runtime and the deterministic harness, writes a
weight artifact plus preprocessing and result sidecars, and never claims CKKS
encryption, independent clients, or paper-level metric parity.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from ..config import Settings
from ..domain.dataset import LoadedDataset, PreprocessedDataset, load_csv_dataset, preprocess
from ..domain.federated.keras_backend import KerasGRUBackend
from ..domain.federated.round import (
    FederatedAborted,
    FederatedConfig,
    FederatedHarness,
)
from ..domain.model import (
    artifact_filename,
    keras_runtime_status,
    parameter_specs,
    write_weight_artifact,
)
from ..errors import JobCancelled, UnavailableError
from ..models import Dataset, Experiment
from ..schemas import TrainingRequest
from ..storage.paths import StoragePaths
from .dataset_service import EXPECTED_FEATURE_COUNT, DatasetService
from .job_manager import JobContext

ARTIFACT_FORMAT = "securefed-training-v1"
PREPROCESSING_FORMAT = "securefed-preprocessing-v1"


def _write_json(path: Path, payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    path.write_text(encoded, encoding="utf-8")
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class TrainingService:
    def __init__(
        self,
        settings: Settings,
        datasets: DatasetService,
        paths: StoragePaths,
        *,
        backend_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.settings = settings
        self.datasets = datasets
        self.paths = paths
        self.backend_factory = backend_factory or KerasGRUBackend

    def availability(
        self,
        experiment: Experiment,
        dataset: Dataset,
        request: TrainingRequest | None = None,
    ) -> tuple[bool, str]:
        if not self.settings.enable_training:
            return False, "GRU training is disabled by configuration."
        if dataset.validation_status != "valid":
            return False, "Dataset has not passed validation."
        if not dataset.research_compatible:
            return False, "Dataset is not compatible with the 48-feature research schema."
        if dataset.feature_count != EXPECTED_FEATURE_COUNT:
            return False, f"Training requires exactly {EXPECTED_FEATURE_COUNT} features."
        if experiment.client_count not in {4, 8, 12}:
            return False, "client_count must be one of 4, 8, 12."
        if request is not None and request.require_encryption:
            return (
                False,
                "Encrypted GRU training is unavailable: no verified native CKKS "
                "runtime is installed.",
            )
        backend = self.backend_factory()
        if backend.research_model:
            available, reason = keras_runtime_status()
            if not available:
                return False, reason
        return (
            True,
            "Plaintext GRU training is available. No encryption or independent "
            "client isolation is provided, and results are not a parity claim.",
        )

    def execute(
        self,
        experiment: Experiment,
        request: TrainingRequest,
        context: JobContext,
    ) -> dict[str, Any]:
        dataset = self.datasets.get(experiment.dataset_id)
        available, reason = self.availability(experiment, dataset, request)
        if not available:
            raise UnavailableError(reason)

        path = self.datasets.path_for(dataset)
        row_cap = self.settings.training_max_rows
        if request.max_rows is not None:
            row_cap = min(row_cap, request.max_rows)
        context.progress(0.05, "loading validated dataset for GRU training")
        loaded = load_csv_dataset(
            path,
            label_column=dataset.label_column,
            max_rows=row_cap,
        )
        context.progress(0.12, f"preprocessing ({request.mode} mode)")
        prepared = preprocess(
            loaded.rows,
            loaded.labels,
            feature_names=loaded.feature_names,
            mode=request.mode,
            test_size=request.test_size,
            seed=request.seed,
        )

        threshold = (
            request.threshold
            if request.threshold is not None
            else experiment.client_count // 2 + 1
        )
        config = FederatedConfig(
            num_clients=experiment.client_count,
            rounds=request.rounds,
            local_epochs=request.local_epochs,
            batch_size=request.batch_size,
            learning_rate=request.learning_rate,
            threshold=threshold,
            byzantine_threshold=request.byzantine_threshold,
            weighting=request.weighting,
            byzantine_check=request.byzantine_check,
            seed=request.seed,
            require_encryption=request.require_encryption,
        )
        backend = self.backend_factory()
        captured_weights: list[float] = []

        def progress(fraction: float, message: str) -> None:
            context.progress(0.20 + 0.72 * max(0.0, min(1.0, fraction)), message)

        harness = FederatedHarness(
            backend,
            config,
            abort_check=lambda: context.cancel_requested,
            progress=progress,
            final_weights_sink=lambda weights: captured_weights.extend(weights),
            mode="plaintext_federated_training",
        )
        context.progress(0.18, "initialising Keras GRU round harness")
        try:
            result = harness.run(prepared)
        except FederatedAborted as exc:
            raise JobCancelled(str(exc)) from exc

        if not captured_weights:
            raise UnavailableError("training completed without final model weights")

        result["experiment_id"] = experiment.id
        result["dataset_id"] = dataset.id
        result["request"] = request.model_dump()
        result["workload"] = {
            "implementation": "in-process simulated clients",
            "independent_clients": False,
            "encryption": False,
            "row_cap": row_cap,
        }
        result["legacy_differences"] = list(result.get("legacy_differences", [])) + [
            "Training uses in-process simulated clients, not independently "
            "authenticated client runtimes.",
            "Cancellation is checked between clients, not inside a Keras fit call.",
        ]

        context.progress(0.94, "writing model and preprocessing artifacts")
        artifact = self._write_artifacts(
            experiment,
            dataset,
            request,
            loaded,
            prepared,
            result,
            captured_weights,
        )
        result["artifact"] = artifact
        context.progress(1.0, "plaintext GRU training complete")
        return result

    def _write_artifacts(
        self,
        experiment: Experiment,
        dataset: Dataset,
        request: TrainingRequest,
        loaded: LoadedDataset,
        prepared: PreprocessedDataset,
        result: dict[str, Any],
        weights: list[float],
    ) -> dict[str, Any]:
        directory = self.paths.ensure_within(
            self.paths.models_dir / experiment.id,
            self.paths.models_dir,
            label="training directory",
        )
        directory.mkdir(parents=True, exist_ok=True)

        weights_name = artifact_filename(dataset.dataset_type, experiment.client_count)
        weights_path = self.paths.ensure_within(
            directory / weights_name,
            self.paths.models_dir,
            label="weights artifact",
        )
        weights_digest = write_weight_artifact(
            weights_path,
            flat_weights=weights,
            specs=parameter_specs(prepared.feature_count),
            model_name=str(result["model"]["name"]),
            input_features=prepared.feature_count,
            dataset_type=dataset.dataset_type,
            client_count=experiment.client_count,
            metadata={
                "format": ARTIFACT_FORMAT,
                "experiment_id": experiment.id,
                "dataset_id": dataset.id,
                "dataset_sha256": dataset.sha256,
                "mode": "plaintext_federated_training",
                "encrypted": False,
                "parity": "unverified",
                "rounds": request.rounds,
                "local_epochs": request.local_epochs,
                "seed": request.seed,
                "aggregate_digest": result.get("aggregate_digest"),
            },
        )

        preprocessing_path = self.paths.ensure_within(
            directory / "preprocessing.json",
            self.paths.models_dir,
            label="preprocessing artifact",
        )
        preprocessing_digest = _write_json(
            preprocessing_path,
            {
                "format": PREPROCESSING_FORMAT,
                "experiment_id": experiment.id,
                "dataset_id": dataset.id,
                "dataset": loaded.as_dict(),
                "feature_names": list(prepared.feature_names),
                "prepared": prepared.summary(),
            },
        )

        result_path = self.paths.ensure_within(
            directory / "result.json",
            self.paths.models_dir,
            label="result artifact",
        )
        result_digest = _write_json(result_path, result)

        def relative(path: Path) -> str:
            return path.relative_to(self.paths.data_dir).as_posix()

        return {
            "format": ARTIFACT_FORMAT,
            "directory": relative(directory),
            "weights_file": relative(weights_path),
            "weights_sha256": weights_digest,
            "preprocessing_file": relative(preprocessing_path),
            "preprocessing_sha256": preprocessing_digest,
            "result_file": relative(result_path),
            "result_sha256": result_digest,
            "encrypted": False,
            "parity": "unverified",
        }
