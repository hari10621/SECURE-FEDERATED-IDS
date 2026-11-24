"""Per-round metric logging for federated learning experiments.

Provides an endpoint to retrieve the ``round_metrics`` JSON array that is
written during training.  Each entry contains per-round statistics such as
accuracy, precision, recall, f1-score, loss, and timing information.
"""

from __future__ import annotations

from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, Request

from ..models import Experiment
from ..schemas import ExperimentResponse
from ..db import Database


def get_database(request: Request) -> Database:
    return request.app.state.db


router = APIRouter(
    prefix="/experiments",
    tags=["experiments", "metrics"],
    dependencies=[],
)


@router.get(
    "/{experiment_id}/metrics",
    response_model=dict[str, List[dict[str, Any]]],
    summary="Retrieve per-round metrics for a federated learning experiment",
)
def get_experiment_metrics(
    experiment_id: str,
    db: Database = Depends(get_database),
) -> dict[str, List[dict[str, Any]]]:
    """Return the ``round_metrics`` JSON array stored with the experiment.

    The metrics are written during training (``TrainingService.execute`` and
    ``EncryptedFederatedHarness.run``) and stored in the experiment's ``result``
    JSON field under the key ``"round_metrics"``.

    Returns:
        A dict with a single key ``"round_metrics"`` mapping to a list of per-round
        metric dicts.  If the experiment has not yet been run or no metrics were
        recorded, an empty list is returned.

    Raises:
        404: If no experiment with the given ID exists.
    """
    experiment: Experiment | None = None
    with db.session() as session:
        experiment = session.get(Experiment, experiment_id)
        if experiment is None:
            raise HTTPException(status_code=404, detail="Experiment not found")
        result: dict[str, Any] = experiment.result or {}
        round_metrics: List[dict[str, Any]] = list(
            result.get("round_metrics", []) or []
        )

    return {"round_metrics": round_metrics}