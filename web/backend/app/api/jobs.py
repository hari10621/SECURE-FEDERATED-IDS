"""Background job lookup and cancellation endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from ..errors import UnavailableError
from ..schemas import JobListResponse, JobResponse
from ..services.job_manager import JobManager
from ..services.job_service import JobService
from .deps import get_job_manager, get_jobs, require_auth

router = APIRouter(
    prefix="/jobs",
    tags=["jobs"],
    dependencies=[Depends(require_auth)],
)


@router.get("", response_model=JobListResponse)
def list_jobs(
    experiment_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    jobs: JobService = Depends(get_jobs),
) -> JobListResponse:
    rows = jobs.list(experiment_id=experiment_id, limit=limit)
    return JobListResponse(
        items=[JobResponse.model_validate(row) for row in rows],
        total=len(rows),
    )


@router.post("/client-tutorial", response_model=JobResponse, status_code=202)
def start_tutorial(request: Request, manager: JobManager = Depends(get_job_manager)):
    if not request.app.state.settings.enable_training:
        raise UnavailableError("Enable training with start_backend.ps1 to run the tutorial.")
    return manager.submit("client_tutorial", dedupe_key="client_tutorial", payload={})


@router.get("/client-tutorial/latest", response_model=JobResponse | None)
def latest_tutorial(jobs: JobService = Depends(get_jobs)):
    return jobs.latest_of_type("client_tutorial")


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: str, jobs: JobService = Depends(get_jobs)) -> JobResponse:
    return JobResponse.model_validate(jobs.get(job_id))


@router.delete("/{job_id}", response_model=JobResponse)
def delete_job(
    job_id: str,
    jobs: JobService = Depends(get_jobs),
) -> JobResponse:
    job = jobs.get(job_id)
    with jobs.db.session() as session:
        session.delete(job)
        session.flush()
    return JobResponse.model_validate(job)


@router.post("/{job_id}/cancel", response_model=JobResponse)
def cancel_job(job_id: str, manager: JobManager = Depends(get_job_manager)) -> JobResponse:
    return JobResponse.model_validate(manager.cancel(job_id))
