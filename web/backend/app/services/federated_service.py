"""Federated experiment orchestration around the safe research adapter."""

from __future__ import annotations

from typing import Any

from ..db import Database
from ..enums import ACTIVE_EXPERIMENT_STATUSES, DatasetType, ExperimentStatus, JobStatus
from ..errors import ConflictError, InputValidationError, JobCancelled, NotFoundError, UnavailableError
from ..models import Experiment, Job
from ..schemas import (
    ExperimentCreate,
    PaperSuiteRequest,
    SimulationRequest,
    TrainingRequest,
)
from ..config import Settings
from .dataset_service import DatasetService
from .encryption_service import EncryptionService
from .experiment_runner import run_paper_experiments
from .experiment_service import ExperimentService
from .job_manager import JobContext, JobManager
from .job_service import JobService
from .research_adapter import ResearchAdapter
from .simulation_service import SimulationService
from .training_service import TrainingService


class FederatedService:
    def __init__(
        self,
        db: Database,
        settings: Settings,
        datasets: DatasetService,
        experiments: ExperimentService,
        jobs: JobService,
        adapter: ResearchAdapter,
        encryption: EncryptionService,
        simulation: SimulationService,
        training: TrainingService,
        job_manager: JobManager,
    ) -> None:
        self.db = db
        self.settings = settings
        self.datasets = datasets
        self.experiments = experiments
        self.jobs = jobs
        self.adapter = adapter
        self.encryption = encryption
        self.simulation = simulation
        self.training = training
        self.job_manager = job_manager
        self.paper_suite_backend_factory: Any | None = None

    def create_experiment(self, payload: ExperimentCreate) -> Experiment:
        dataset = self.datasets.get(payload.dataset_id)
        dataset_type = DatasetType(dataset.dataset_type)
        reason = self.adapter.target_reason(dataset_type, payload.client_count)
        if reason:
            raise InputValidationError(reason)
        return self.experiments.create(payload)

    def availability(self, experiment: Experiment) -> tuple[bool, str]:
        if not self.settings.enable_research_execution:
            return False, "Research execution is disabled by configuration."
        try:
            dataset_type = DatasetType(
                self.datasets.get(experiment.dataset_id).dataset_type
            )
        except (ValueError, NotFoundError):
            return False, "Dataset type is invalid or missing."
        reason = self.adapter.target_reason(dataset_type, experiment.client_count)
        if reason:
            return False, reason
        encryption = self.encryption.status()
        if not encryption["available"]:
            return False, encryption["reason"]
        return self.adapter.availability(dataset_type, experiment.client_count)

    def start_experiment(self, experiment_id: str) -> Job:
        experiment = self.experiments.get(experiment_id)
        if experiment.status in ACTIVE_EXPERIMENT_STATUSES:
            raise ConflictError("experiment already has an active job")
        available, reason = self.availability(experiment)
        if not available:
            raise UnavailableError(
                reason,
                details={"experiment_id": experiment_id, "encryption": self.encryption.status()},
            )
        job = self.job_manager.submit(
            "research_run",
            dedupe_key=f"experiment:{experiment.id}:run",
            payload={"experiment_id": experiment.id},
            experiment_id=experiment.id,
        )
        self._attach_job(experiment.id, job.id)
        return job

    def _attach_job(self, experiment_id: str, job_id: str) -> None:
        """Attach a job without regressing a run that already finished.

        A fast-failing worker can reach a terminal state before ``submit``
        returns. The service performs the read and write in one transaction.
        """
        self.experiments.attach_job(experiment_id, job_id)

    def cancel_experiment(self, experiment_id: str) -> Job:
        experiment = self.experiments.get(experiment_id)
        if not experiment.job_id:
            raise ConflictError("experiment has no job to cancel")
        job = self.job_manager.cancel(experiment.job_id)
        if job.status in {
            JobStatus.CANCELLATION_REQUESTED.value,
            JobStatus.CANCELLED.value,
        }:
            self.experiments.set_state(
                experiment.id,
                status=ExperimentStatus.CANCELLATION_REQUESTED,
            )
        return job

    def status(self, experiment_id: str) -> tuple[Experiment, Job | None, bool, str]:
        experiment = self.experiments.get(experiment_id)
        job = self.jobs.get(experiment.job_id) if experiment.job_id else None
        available, reason = self.availability(experiment)
        return experiment, job, available, reason

    def simulation_status(self, experiment: Experiment) -> tuple[bool, str]:
        try:
            dataset = self.datasets.get(experiment.dataset_id)
        except NotFoundError:
            return False, "Dataset is missing."
        return self.simulation.availability(experiment, dataset)

    def start_simulation(self, experiment_id: str, payload: SimulationRequest) -> Job:
        experiment = self.experiments.get(experiment_id)
        if experiment.status in ACTIVE_EXPERIMENT_STATUSES:
            raise ConflictError("experiment already has an active job")
        available, reason = self.simulation_status(experiment)
        if not available:
            raise UnavailableError(reason, details={"experiment_id": experiment_id})
        job = self.job_manager.submit(
            "simulation_run",
            dedupe_key=f"experiment:{experiment.id}:simulation",
            payload={"experiment_id": experiment.id, "request": payload.model_dump()},
            experiment_id=experiment.id,
        )
        self._attach_job(experiment.id, job.id)
        return job

    def training_status(
        self,
        experiment: Experiment,
        request: TrainingRequest | None = None,
    ) -> tuple[bool, str]:
        try:
            dataset = self.datasets.get(experiment.dataset_id)
        except NotFoundError:
            return False, "Dataset is missing."
        return self.training.availability(experiment, dataset, request)

    def start_training(
        self, experiment_id: str, payload: TrainingRequest
    ) -> Job:
        experiment = self.experiments.get(experiment_id)
        if experiment.status in ACTIVE_EXPERIMENT_STATUSES:
            raise ConflictError("experiment already has an active job")
        if payload.threshold is not None and payload.threshold > experiment.client_count:
            raise InputValidationError("threshold must be between 1 and client_count")
        available, reason = self.training_status(experiment, payload)
        if not available:
            raise UnavailableError(reason, details={"experiment_id": experiment_id})
        job = self.job_manager.submit(
            "training_run",
            dedupe_key=f"experiment:{experiment.id}:training",
            payload={"experiment_id": experiment.id, "request": payload.model_dump()},
            experiment_id=experiment.id,
        )
        self._attach_job(experiment.id, job.id)
        return job

    def start_paper_suite(self, payload: PaperSuiteRequest) -> Job:
        dataset = self.datasets.get(payload.dataset_id)
        if dataset.validation_status != "valid":
            raise UnavailableError("Dataset has not passed validation.")
        return self.job_manager.submit(
            "paper_suite_run",
            dedupe_key=f"dataset:{dataset.id}:paper-suite",
            payload={"dataset_id": dataset.id, "request": payload.model_dump()},
        )

    def execute_paper_suite_job(
        self, context: JobContext, payload: dict[str, Any]
    ) -> dict[str, Any]:
        request = PaperSuiteRequest.model_validate(payload.get("request") or {})
        dataset = self.datasets.get(request.dataset_id)
        if dataset.validation_status != "valid":
            raise UnavailableError("Dataset has not passed validation.")
        path = self.datasets.path_for(dataset)
        return run_paper_experiments(
            path,
            dataset.dataset_type,
            settings=self.settings,
            rounds=request.rounds,
            local_epochs=request.local_epochs,
            batch_size=request.batch_size,
            learning_rate=request.learning_rate,
            seed=request.seed,
            test_size=request.test_size,
            max_rows=request.max_rows,
            client_counts=request.client_counts,
            include_centralized=request.include_centralized,
            include_he=request.include_he,
            backend_factory=self.paper_suite_backend_factory,
            progress=lambda fraction, message: context.progress(fraction, message),
            cancel_check=lambda: context.cancel_requested,
        )

    def execute_training_job(
        self, context: JobContext, payload: dict[str, Any]
    ) -> dict[str, Any]:
        experiment_id = payload.get("experiment_id")
        if not isinstance(experiment_id, str):
            raise UnavailableError("invalid training job payload")
        request = TrainingRequest.model_validate(payload.get("request") or {})
        experiment = self.experiments.get(experiment_id)
        self.experiments.set_state(
            experiment.id,
            status=ExperimentStatus.RUNNING,
            started=True,
        )
        try:
            result = self.training.execute(experiment, request, context)
            self.experiments.set_state(
                experiment.id,
                status=ExperimentStatus.SUCCEEDED,
                finished=True,
                result=result,
            )
            return result
        except JobCancelled:
            self.experiments.set_state(
                experiment.id,
                status=ExperimentStatus.CANCELLED,
                finished=True,
            )
            raise
        except Exception as exc:
            self.experiments.set_state(
                experiment.id,
                status=ExperimentStatus.FAILED,
                finished=True,
                error=f"training failed: {exc.__class__.__name__}",
            )
            raise

    def execute_simulation_job(
        self, context: JobContext, payload: dict[str, Any]
    ) -> dict[str, Any]:
        experiment_id = payload.get("experiment_id")
        if not isinstance(experiment_id, str):
            raise UnavailableError("invalid simulation job payload")
        request = SimulationRequest.model_validate(payload.get("request") or {})
        experiment = self.experiments.get(experiment_id)
        self.experiments.set_state(
            experiment.id,
            status=ExperimentStatus.RUNNING,
            started=True,
        )
        try:
            result = self.simulation.execute(experiment, request, context)
            self.experiments.set_state(
                experiment.id,
                status=ExperimentStatus.SUCCEEDED,
                finished=True,
                result=result,
            )
            return result
        except JobCancelled:
            self.experiments.set_state(
                experiment.id,
                status=ExperimentStatus.CANCELLED,
                finished=True,
            )
            raise
        except Exception as exc:
            self.experiments.set_state(
                experiment.id,
                status=ExperimentStatus.FAILED,
                finished=True,
                error=f"simulation failed: {exc.__class__.__name__}",
            )
            raise

    def execute_job(self, context: JobContext, payload: dict[str, Any]) -> dict[str, Any]:
        experiment_id = payload.get("experiment_id")
        if not isinstance(experiment_id, str):
            raise UnavailableError("invalid research job payload")
        experiment = self.experiments.get(experiment_id)
        self.experiments.set_state(
            experiment.id,
            status=ExperimentStatus.RUNNING,
            started=True,
        )
        try:
            available, reason = self.availability(experiment)
            if not available:
                raise UnavailableError(reason)
            dataset = self.datasets.get(experiment.dataset_id)
            dataset_path = self.datasets.path_for(dataset)
            context.progress(0.05, "preparing isolated run workspace")
            invocation = self.adapter.prepare_workspace(
                run_id=experiment.id,
                dataset_type=DatasetType(dataset.dataset_type),
                client_count=experiment.client_count,
                dataset_path=dataset_path,
                dataset_sha256=dataset.sha256,
            )
            context.progress(0.10, "starting fixed research worker")
            result = self.adapter.execute(
                invocation,
                cancel_event=context.cancel_event,
            )
            context.check_cancelled()
            self.experiments.set_state(
                experiment.id,
                status=ExperimentStatus.SUCCEEDED,
                finished=True,
                result=result,
            )
            return result
        except JobCancelled:
            self.experiments.set_state(
                experiment.id,
                status=ExperimentStatus.CANCELLED,
                finished=True,
            )
            raise
        except Exception as exc:
            self.experiments.set_state(
                experiment.id,
                status=ExperimentStatus.FAILED,
                finished=True,
                error=f"experiment failed: {exc.__class__.__name__}",
            )
            raise

