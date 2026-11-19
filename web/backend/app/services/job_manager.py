"""In-process background job orchestration with persisted state.

This is deliberately a small local-first runner. It is not a distributed queue;
it uses one thread pool and records every state transition in SQLite. Restart
recovery marks interrupted jobs and experiments as failed rather than silently
resuming them.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable

from ..db import Database
from ..enums import JobStatus
from ..errors import ConflictError, JobCancelled, NotFoundError
from ..models import Job
from .job_service import JobService

logger = logging.getLogger(__name__)

JobHandler = Callable[["JobContext", dict[str, Any]], dict[str, Any] | None]


@dataclass
class JobContext:
    job_id: str
    cancel_event: threading.Event
    _progress: Callable[[float, str | None], None]

    @property
    def cancel_requested(self) -> bool:
        return self.cancel_event.is_set()

    def check_cancelled(self) -> None:
        if self.cancel_requested:
            raise JobCancelled("job cancellation requested")

    def progress(self, value: float, message: str | None = None) -> None:
        self.check_cancelled()
        self._progress(value, message)

    def set_progress(self, value: float, message: str | None = None) -> None:
        self.progress(value, message)


class JobManager:
    def __init__(
        self,
        db: Database,
        jobs: JobService,
        handlers: dict[str, JobHandler],
        max_workers: int = 1,
    ) -> None:
        self.db = db
        self.jobs = jobs
        self.handlers = handlers
        self._lock = threading.Lock()
        self._events: dict[str, threading.Event] = {}
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="securefed-job",
        )
        self._closed = False

    def submit(
        self,
        job_type: str,
        *,
        dedupe_key: str,
        payload: dict[str, Any],
        experiment_id: str | None = None,
    ) -> Job:
        if job_type not in self.handlers:
            raise ValueError(f"unknown job type: {job_type}")
        with self._lock:
            if self._closed:
                raise RuntimeError("job manager is closed")
            job = self.jobs.create(
                job_type=job_type,
                dedupe_key=dedupe_key,
                payload=payload,
                experiment_id=experiment_id,
            )
            event = threading.Event()
            self._events[job.id] = event
            self._executor.submit(self._run, job.id, job_type, payload, event)
            return job

    def register_handler(self, job_type: str, handler: JobHandler) -> None:
        if not job_type or not callable(handler):
            raise ValueError("job_type and callable handler are required")
        self.handlers[job_type] = handler

    def get(self, job_id: str) -> Job:
        return self.jobs.get(job_id)

    def cancel(self, job_id: str) -> Job:
        job = self.jobs.get(job_id)
        if job.status in {
            JobStatus.SUCCEEDED.value,
            JobStatus.FAILED.value,
            JobStatus.CANCELLED.value,
        }:
            raise ConflictError("job is already finished", details={"status": job.status})
        with self._lock:
            event = self._events.get(job_id)
            if event is not None:
                event.set()
        return self.jobs.update_status(
            job_id,
            status=JobStatus.CANCELLATION_REQUESTED.value,
            cancel_requested=True,
            message="cancellation requested",
        )

    def shutdown(self) -> None:
        with self._lock:
            self._closed = True
            for event in self._events.values():
                event.set()
            self._events.clear()
        self._executor.shutdown(wait=True, cancel_futures=True)

    def _run(
        self,
        job_id: str,
        job_type: str,
        payload: dict[str, Any],
        event: threading.Event,
    ) -> None:
        try:
            job = self.jobs.get(job_id)
            if job.cancel_requested:
                self.jobs.update_status(
                    job_id,
                    status=JobStatus.CANCELLED.value,
                    error="cancelled before execution",
                    finished=True,
                )
                return
            self.jobs.update_status(
                job_id,
                status=JobStatus.RUNNING.value,
                started=True,
                message="running",
            )

            def progress(value: float, message: str | None) -> None:
                self.jobs.update_status(job_id, status=JobStatus.RUNNING.value, progress=value, message=message)

            context = JobContext(job_id=job_id, cancel_event=event, _progress=progress)
            handler = self.handlers[job_type]
            result = handler(context, payload)
            if event.is_set():
                self.jobs.update_status(
                    job_id,
                    status=JobStatus.CANCELLED.value,
                    message="cancelled",
                    finished=True,
                )
            else:
                self.jobs.update_status(
                    job_id,
                    status=JobStatus.SUCCEEDED.value,
                    progress=1.0,
                    message="completed",
                    result=result or {},
                    finished=True,
                )
        except JobCancelled:
            self.jobs.update_status(
                job_id,
                status=JobStatus.CANCELLED.value,
                message="cancelled",
                finished=True,
            )
        except Exception as exc:  # pragma: no cover - exercised by explicit failure tests
            logger.exception("background job failed: %s", job_id)
            self.jobs.update_status(
                job_id,
                status=JobStatus.FAILED.value,
                error=f"job failed: {exc.__class__.__name__}",
                finished=True,
            )
        finally:
            with self._lock:
                self._events.pop(job_id, None)

