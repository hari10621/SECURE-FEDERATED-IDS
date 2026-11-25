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


@router.get("/status", response_model=None)
def prediction_status(service: ModelService = Depends(get_models)) -> PredictionStatusResponse:
    return service.status()


@router.post("", response_model=None)
def predict(
    payload: PredictionRequest,
    service: ModelService = Depends(get_models),
) -> dict:
    result=service.predict(payload.features)
    service.automatic.manual_detection(result)
    return result

@router.post("/reload")
def reload_model(service: ModelService = Depends(get_models)):
    return service.status(force=True)


@router.get("/versions")
def versions(service: ModelService = Depends(get_models)):
    return [p.stem for p in sorted(service.registry.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)]


@router.post("/versions/{version}/deploy")
def deploy(version: str, service: ModelService = Depends(get_models)):
    return service.deploy(version)
