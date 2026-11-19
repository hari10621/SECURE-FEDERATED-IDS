"""Experiment records. This service does not train or invent metrics."""

from __future__ import annotations

import uuid

from sqlalchemy import case, func, select, update

from ..db import Database
from ..enums import ACTIVE_EXPERIMENT_STATUSES, ExperimentStatus
from ..errors import InputValidationError, NotFoundError
from ..models import Experiment, utcnow
from ..schemas import ExperimentCreate
from .dataset_service import DatasetService


class ExperimentService:
    def __init__(self, db: Database, datasets: DatasetService) -> None:
        self.db = db
        self.datasets = datasets

    def create(self, payload: ExperimentCreate) -> Experiment:
        dataset = self.datasets.get(payload.dataset_id)
        if dataset.validation_status != "valid":
            raise InputValidationError("dataset has not passed validation")
        if not dataset.research_compatible:
            raise InputValidationError(
                "dataset is not compatible with the original research scripts",
                details={
                    "reason": "expected 48 numeric features with the label as the last column",
                    "feature_count": dataset.feature_count,
                    "label_column": dataset.label_column,
                },
            )
        experiment = Experiment(
            id=uuid.uuid4().hex,
            name=payload.name,
            dataset_id=dataset.id,
            client_count=payload.client_count,
            status=ExperimentStatus.CREATED.value,
            config=payload.config,
        )
        with self.db.session() as session:
            session.add(experiment)
        return experiment

    def list(self, *, limit: int = 50, offset: int = 0) -> tuple[list[Experiment], int]:
        with self.db.session() as session:
            total = session.scalar(select(func.count()).select_from(Experiment)) or 0
            rows = list(
                session.scalars(
                    select(Experiment)
                    .order_by(Experiment.created_at.desc())
                    .limit(limit)
                    .offset(offset)
                )
            )
        return rows, total

    def get(self, experiment_id: str) -> Experiment:
        with self.db.session() as session:
            experiment = session.get(Experiment, experiment_id)
            if experiment is None:
                raise NotFoundError(f"experiment not found: {experiment_id}")
            return experiment

    def set_state(
        self,
        experiment_id: str,
        *,
        status: ExperimentStatus,
        job_id: str | None = None,
        started: bool = False,
        finished: bool = False,
        result: dict | None = None,
        error: str | None = None,
    ) -> Experiment:
        with self.db.session() as session:
            experiment = session.get(Experiment, experiment_id)
            if experiment is None:
                raise NotFoundError(f"experiment not found: {experiment_id}")
            experiment.status = status.value
            if job_id is not None:
                experiment.job_id = job_id
            if started and experiment.started_at is None:
                experiment.started_at = utcnow()
            if finished:
                experiment.finished_at = utcnow()
            if result is not None:
                experiment.result = result
            if error is not None:
                experiment.error = error[:2000]
            session.flush()
            session.refresh(experiment)
            return experiment

    def attach_job(self, experiment_id: str, job_id: str) -> Experiment:
        """Attach a job in one transaction without regressing a terminal run."""
        terminal = {
            ExperimentStatus.SUCCEEDED.value,
            ExperimentStatus.FAILED.value,
            ExperimentStatus.CANCELLED.value,
        }
        with self.db.session() as session:
            result = session.execute(
                update(Experiment)
                .where(Experiment.id == experiment_id)
                .values(
                    job_id=job_id,
                    status=case(
                        (
                            Experiment.status.notin_(terminal),
                            ExperimentStatus.QUEUED.value,
                        ),
                        else_=Experiment.status,
                    ),
                )
            )
            if result.rowcount == 0:
                raise NotFoundError(f"experiment not found: {experiment_id}")
            session.expire_all()
            experiment = session.get(Experiment, experiment_id)
            assert experiment is not None
            return experiment

    def recover_interrupted(self) -> int:
        """Mark experiments that cannot survive a process restart as failed."""
        with self.db.session() as session:
            experiments = list(
                session.scalars(
                    select(Experiment).where(
                        Experiment.status.in_(ACTIVE_EXPERIMENT_STATUSES)
                    )
                )
            )
            for experiment in experiments:
                experiment.status = ExperimentStatus.FAILED.value
                experiment.error = "process restarted before the experiment completed"
                experiment.finished_at = utcnow()
            return len(experiments)
