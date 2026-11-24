"""Experiment create/list/detail/status and start/cancel endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from ..schemas import (
    ExperimentCreate,
    ExperimentListResponse,
    ExperimentResponse,
    ExperimentStatusResponse,
    JobResponse,
    PaperSuiteRequest,
    SimulationRequest,
    TrainingRequest,
)
from ..services.experiment_service import ExperimentService
from ..services.federated_service import FederatedService
from ..services.job_service import JobService
from .deps import get_experiments, get_federated, get_jobs, require_auth

router = APIRouter(
    prefix="/experiments",
    tags=["experiments"],
    dependencies=[Depends(require_auth)],
)


@router.post("", response_model=ExperimentResponse, status_code=201)
def create_experiment(
    payload: ExperimentCreate,
    federated: FederatedService = Depends(get_federated),
) -> ExperimentResponse:
    return ExperimentResponse.model_validate(federated.create_experiment(payload))


@router.get("", response_model=ExperimentListResponse)
def list_experiments(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    service: ExperimentService = Depends(get_experiments),
) -> ExperimentListResponse:
    rows, total = service.list(limit=limit, offset=offset)
    return ExperimentListResponse(
        items=[ExperimentResponse.model_validate(row) for row in rows],
        total=total,
    )


@router.post("/run-paper-suite", response_model=JobResponse, status_code=202)
def run_paper_suite(
    payload: PaperSuiteRequest,
    federated: FederatedService = Depends(get_federated),
) -> JobResponse:
    return JobResponse.model_validate(federated.start_paper_suite(payload))


@router.get("/{experiment_id}", response_model=ExperimentResponse)
def get_experiment(
    experiment_id: str,
    service: ExperimentService = Depends(get_experiments),
) -> ExperimentResponse:
    return ExperimentResponse.model_validate(service.get(experiment_id))


@router.get("/{experiment_id}/status", response_model=ExperimentStatusResponse)
def experiment_status(
    experiment_id: str,
    federated: FederatedService = Depends(get_federated),
) -> ExperimentStatusResponse:
    experiment, job, available, reason = federated.status(experiment_id)
    simulation_available, simulation_reason = federated.simulation_status(experiment)
    training_available, training_reason = federated.training_status(experiment)
    return ExperimentStatusResponse(
        id=experiment.id,
        status=experiment.status,
        execution_available=available,
        execution_reason=reason,
        simulation_available=simulation_available,
        simulation_reason=simulation_reason,
        training_available=training_available,
        training_reason=training_reason,
        job=JobResponse.model_validate(job) if job is not None else None,
    )


@router.post("/{experiment_id}/start", response_model=JobResponse)
def start_experiment(
    experiment_id: str,
    federated: FederatedService = Depends(get_federated),
) -> JobResponse:
    return JobResponse.model_validate(federated.start_experiment(experiment_id))


@router.post("/{experiment_id}/simulate", response_model=JobResponse)
def simulate_experiment(
    experiment_id: str,
    payload: SimulationRequest | None = None,
    federated: FederatedService = Depends(get_federated),
) -> JobResponse:
    request = payload or SimulationRequest()
    return JobResponse.model_validate(federated.start_simulation(experiment_id, request))


@router.post("/{experiment_id}/train", response_model=JobResponse)
def train_experiment(
    experiment_id: str,
    payload: TrainingRequest | None = None,
    federated: FederatedService = Depends(get_federated),
) -> JobResponse:
    request = payload or TrainingRequest()
    return JobResponse.model_validate(federated.start_training(experiment_id, request))


@router.post("/{experiment_id}/cancel", response_model=JobResponse)
def cancel_experiment(
    experiment_id: str,
    federated: FederatedService = Depends(get_federated),
) -> JobResponse:
    return JobResponse.model_validate(federated.cancel_experiment(experiment_id))
