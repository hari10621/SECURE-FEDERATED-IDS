"""Opt-in plaintext federated simulation over an uploaded dataset.

This service is deliberately separate from the encrypted research path. It uses
the deterministic domain harness and a reference linear model, and every result
is labelled ``mode: plaintext_simulation`` with ``encrypted: false``. It never
claims CKKS encryption, legacy GRU parity, or real independent clients.
"""

from __future__ import annotations

from typing import Any

from ..config import Settings
from ..domain.dataset import load_csv_dataset, preprocess
from ..domain.federated.backends import ReferenceLinearBackend
from ..domain.federated.round import (
    FederatedAborted,
    FederatedConfig,
    FederatedHarness,
)
from ..errors import JobCancelled, UnavailableError
from ..models import Dataset, Experiment
from ..schemas import SimulationRequest
from .dataset_service import EXPECTED_FEATURE_COUNT, DatasetService
from .job_manager import JobContext


class SimulationService:
    def __init__(self, settings: Settings, datasets: DatasetService) -> None:
        self.settings = settings
        self.datasets = datasets

    def availability(self, experiment: Experiment, dataset: Dataset) -> tuple[bool, str]:
        if not self.settings.enable_simulation:
            return False, "Plaintext simulation is disabled by configuration."
        if dataset.validation_status != "valid":
            return False, "Dataset has not passed validation."
        if not dataset.research_compatible:
            return False, "Dataset is not compatible with the 48-feature research schema."
        if dataset.feature_count != EXPECTED_FEATURE_COUNT:
            return False, f"Simulation requires exactly {EXPECTED_FEATURE_COUNT} features."
        if experiment.client_count not in {2, 3, 4, 8, 12}:
            return False, "client_count must be one of 2, 3, 4, 8, 12."
        return (
            True,
            "Plaintext simulation is available. No encryption is performed and "
            "results are not a legacy-parity claim.",
        )

    def execute(
        self,
        experiment: Experiment,
        request: SimulationRequest,
        context: JobContext,
    ) -> dict[str, Any]:
        dataset = self.datasets.get(experiment.dataset_id)
        available, reason = self.availability(experiment, dataset)
        if not available:
            raise UnavailableError(reason)

        path = self.datasets.path_for(dataset)
        context.progress(0.05, "loading validated dataset for simulation")
        loaded = load_csv_dataset(
            path,
            label_column=dataset.label_column,
            max_rows=self.settings.simulation_max_rows,
        )
        context.progress(0.15, f"preprocessing ({request.mode} mode)")
        prepared = preprocess(
            loaded.rows,
            loaded.labels,
            feature_names=loaded.feature_names,
            mode=request.mode,
            test_size=request.test_size,
            seed=request.seed,
        )
        context.progress(0.25, "initialising deterministic round harness")

        config = FederatedConfig(
            num_clients=experiment.client_count,
            rounds=request.rounds,
            local_epochs=request.local_epochs,
            batch_size=request.batch_size,
            learning_rate=request.learning_rate,
            weighting=request.weighting,
            byzantine_check=request.byzantine_check,
            seed=request.seed,
        )

        def progress(fraction: float, message: str) -> None:
            context.progress(0.25 + 0.74 * max(0.0, min(1.0, fraction)), message)

        harness = FederatedHarness(
            ReferenceLinearBackend(),
            config,
            abort_check=lambda: context.cancel_requested,
            progress=progress,
        )
        try:
            result = harness.run(prepared)
        except FederatedAborted as exc:
            raise JobCancelled(str(exc)) from exc

        result["experiment_id"] = experiment.id
        result["dataset_id"] = dataset.id
        result["request"] = request.model_dump()
        context.progress(1.0, "plaintext simulation complete")
        return result
