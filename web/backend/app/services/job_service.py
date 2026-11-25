"""Job persistence and duplicate suppression."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select

from ..db import Database
from ..enums import ACTIVE_JOB_STATUSES, JobStatus
from ..errors import ConflictError, NotFoundError
from ..models import Job


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create(
        self,
        *,
        job_type: str,
        dedupe_key: str,
        payload: dict,
        experiment_id: str | None = None,
    ) -> Job:
        with self.db.session() as session:
            active = session.scalar(
                select(Job).where(
                    Job.dedupe_key == dedupe_key,
                    Job.status.in_(ACTIVE_JOB_STATUSES),
                )
            )
            if active is not None:
                raise ConflictError(
                    "an identical job is already queued or running",
                    details={"job_id": active.id, "status": active.status},
                )
            job = Job(
                id=uuid.uuid4().hex,
                job_type=job_type,
                dedupe_key=dedupe_key,
                status=JobStatus.QUEUED.value,
                payload=payload,
                experiment_id=experiment_id,
            )
            session.add(job)
            session.flush()
            session.refresh(job)
            return job

    def get(self, job_id: str) -> Job:
        with self.db.session() as session:
            job = session.get(Job, job_id)
            if job is None:
                raise NotFoundError(f"job not found: {job_id}")
            return job

    def list(self, *, experiment_id: str | None = None, limit: int = 50) -> list[Job]:
        with self.db.session() as session:
            statement = select(Job).order_by(Job.created_at.desc()).limit(limit)
            if experiment_id is not None:
                statement = statement.where(Job.experiment_id == experiment_id)
            return list(session.scalars(statement))

    def latest_of_type(self, job_type: str) -> Job | None:
        with self.db.session() as session:
            return session.scalar(select(Job).where(Job.job_type == job_type)
                                  .order_by(Job.created_at.desc()).limit(1))

    def count(self) -> int:
        with self.db.session() as session:
            return session.scalar(select(func.count()).select_from(Job)) or 0

    def update_status(
        self,
        job_id: str,
        *,
        status: str,
        progress: float | None = None,
        message: str | None = None,
        result: dict | None = None,
        error: str | None = None,
        cancel_requested: bool | None = None,
        started: bool = False,
        finished: bool = False,
    ) -> Job:
        with self.db.session() as session:
            job = session.get(Job, job_id)
            if job is None:
                raise NotFoundError(f"job not found: {job_id}")
            terminal = {
                JobStatus.SUCCEEDED.value,
                JobStatus.FAILED.value,
                JobStatus.CANCELLED.value,
            }
            if job.status in terminal and status != job.status:
                return job
            job.status = status
            if progress is not None:
                job.progress = max(0.0, min(1.0, float(progress)))
            if message is not None:
                job.message = message[:500]
            if result is not None:
                job.result = result
            if error is not None:
                job.error = error[:2000]
            if cancel_requested is not None:
                job.cancel_requested = cancel_requested
            if started and job.started_at is None:
                job.started_at = utcnow()
            if finished:
                job.finished_at = utcnow()
            session.flush()
            session.refresh(job)
            return job

    def recover_interrupted(self) -> int:
        """Mark jobs that cannot survive a process restart as failed."""
        with self.db.session() as session:
            jobs = list(
                session.scalars(
                    select(Job).where(Job.status.in_(ACTIVE_JOB_STATUSES))
                )
            )
            for job in jobs:
                job.status = JobStatus.FAILED.value
                job.error = "process restarted before the job completed"
                job.finished_at = utcnow()
            return len(jobs)
