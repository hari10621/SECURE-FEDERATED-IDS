"""Prediction status and fail-closed prediction endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..schemas import PredictionRequest, PredictionStatusResponse
from ..services.model_service import ModelService
from .deps import get_models, require_auth

router = APIRouter(
    prefix="/predictions",
    tags=["predictions"],
    dependencies=[Depends(require_auth)],
)


@router.get("/status", response_model=PredictionStatusResponse)
def prediction_status(service: ModelService = Depends(get_models)) -> PredictionStatusResponse:
    return PredictionStatusResponse(**service.status())


@router.post("", response_model=None)
def predict(
    payload: PredictionRequest,
    service: ModelService = Depends(get_models),
) -> None:
    # ModelService.predict always fails closed until a verified model and
    # matching preprocessing manifest are admitted.
    service.predict(payload.features)
