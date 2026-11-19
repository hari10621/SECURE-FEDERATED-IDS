from __future__ import annotations

import time

import pytest

from app.db import Database
from app.errors import ConflictError, JobCancelled, NotFoundError
from app.services.job_manager import JobManager
from app.services.job_service import JobService


def _wait_for(service: JobService, job_id: str, statuses: set[str], timeout: float = 5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = service.get(job_id)
        if job is not None and job.status in statuses:
            return job
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not reach {statuses}")


@pytest.fixture
def job_stack(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'jobs.db'}")
    db.init()
    service = JobService(db)
    manager = JobManager(db, service, {}, 1)
    try:
        yield service, manager
    finally:
        manager.shutdown()
        db.dispose()


def test_job_succeeds_and_records_result(job_stack):
    service, manager = job_stack

    def handler(context, payload):
        context.progress(0.5, "halfway")
        return {"processed": payload["count"]}

    manager.register_handler("demo", handler)
    job = manager.submit("demo", dedupe_key="demo-1", payload={"count": 3})
    completed = _wait_for(service, job.id, {"succeeded"})
    assert completed.progress == 1.0
    assert completed.result == {"processed": 3}
    assert completed.started_at is not None
    assert completed.finished_at is not None


def test_job_failure_is_persisted(job_stack):
    service, manager = job_stack

    def handler(context, payload):
        raise RuntimeError("boom")

    manager.register_handler("failing", handler)
    job = manager.submit("failing", dedupe_key="failing-1", payload={})
    failed = _wait_for(service, job.id, {"failed"})
    assert failed.error is not None
    assert "RuntimeError" in failed.error


def test_duplicate_active_job_is_rejected(job_stack):
    service, manager = job_stack

    def handler(context, payload):
        time.sleep(0.3)
        return {"ok": True}

    manager.register_handler("slow", handler)
    first = manager.submit("slow", dedupe_key="same-key", payload={})
    with pytest.raises(ConflictError) as error:
        manager.submit("slow", dedupe_key="same-key", payload={})
    assert error.value.details["job_id"] == first.id
    _wait_for(service, first.id, {"succeeded"})


def test_cancel_marks_job_cancelled(job_stack):
    service, manager = job_stack

    def handler(context, payload):
        while not context.cancel_requested:
            time.sleep(0.01)
        raise JobCancelled("cancelled by test")

    manager.register_handler("cancelable", handler)
    job = manager.submit("cancelable", dedupe_key="cancel-1", payload={})
    time.sleep(0.1)
    manager.cancel(job.id)
    cancelled = _wait_for(service, job.id, {"cancelled"})
    assert cancelled.finished_at is not None


def test_cancel_unknown_job_is_not_found(job_stack):
    _service, manager = job_stack
    with pytest.raises(NotFoundError):
        manager.cancel("missing")


def test_recover_interrupted_marks_stale_jobs_failed(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'recover.db'}")
    db.init()
    try:
        service = JobService(db)
        job = service.create(
            job_type="research_run",
            dedupe_key="stale-key",
            payload={},
        )
        service.update_status(job.id, status="running", progress=0.1, started=True)
        recovered = service.recover_interrupted()
        assert recovered == 1
        refreshed = service.get(job.id)
        assert refreshed is not None
        assert refreshed.status == "failed"
        assert "restarted" in (refreshed.error or "").lower()
    finally:
        db.dispose()
