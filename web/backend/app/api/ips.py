"""IDS inference and read-only mitigation advice."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..schemas import (
    PredictionRequest,
    PredictionStatusResponse,
)
from ..errors import UnavailableError
from ..services.model_service import ModelService
from .deps import get_models, require_auth


router = APIRouter(
    prefix="/ips",
    tags=["ips"],
    dependencies=[Depends(require_auth)],
)


@router.post(
    "/detect",
    response_model=PredictionStatusResponse,
    summary="Run IDS model inference on flow features",
)
def ips_detect(
    payload: PredictionRequest,
    models: ModelService = Depends(get_models),
) -> PredictionStatusResponse:
    """Score submitted flow statistics with the admitted model and fitted scaler."""

    try:
        prediction = models.predict(payload.features)
    except UnavailableError as exc:
        return PredictionStatusResponse(available=False, reason=str(exc))
    models.automatic.manual_detection(prediction)
    probability = prediction["prediction"]
    label = prediction["label"]
    reason = f"prediction={probability:.4f}" + (
        " alert=intrusion_detected" if label else ""
    )
    return PredictionStatusResponse(
        available=True,
        reason=reason,
        model="keras_gru",
        preprocessing="securefed-preprocessing-v1",
    )


@router.post(
    "/mitigate",
    response_model=dict[str, Any],
    summary="Generate IPS mitigation request from detection result",
)
def ips_mitigate(
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "enforced": False,
        "mode": "detection_only",
        "recommendation": "Review the recorded sample, source and model confidence before taking action.",
    }
