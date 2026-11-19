"""Dataset metadata, upload validation, and revalidation endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status

from ..enums import DatasetType
from ..schemas import (
    DatasetListResponse,
    DatasetResponse,
    DatasetValidationReport,
)
from ..services.dataset_service import DatasetService
from .deps import get_datasets, require_auth

router = APIRouter(
    prefix="/datasets",
    tags=["datasets"],
    dependencies=[Depends(require_auth)],
)


@router.post("", response_model=DatasetResponse, status_code=status.HTTP_201_CREATED)
async def upload_dataset(
    request: Request,
    file: Annotated[UploadFile, File()],
    dataset_type: Annotated[DatasetType, Form()],
    name: Annotated[str | None, Form()] = None,
    label_column: Annotated[str | None, Form()] = None,
    service: DatasetService = Depends(get_datasets),
) -> DatasetResponse:
    record = await service.save_upload(
        file,
        dataset_type=dataset_type,
        name=name,
        label_column=label_column,
    )
    return DatasetResponse.model_validate(record)


@router.post("/validate", response_model=DatasetValidationReport)
async def validate_dataset_upload(
    file: Annotated[UploadFile, File()],
    label_column: Annotated[str | None, Form()] = None,
    service: DatasetService = Depends(get_datasets),
) -> DatasetValidationReport:
    report = await service.validate_upload(file, label_column=label_column)
    return DatasetValidationReport(**report.as_dict())


@router.get("", response_model=DatasetListResponse)
def list_datasets(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    service: DatasetService = Depends(get_datasets),
) -> DatasetListResponse:
    rows, total = service.list(limit=limit, offset=offset)
    return DatasetListResponse(
        items=[DatasetResponse.model_validate(row) for row in rows],
        total=total,
    )


@router.get("/{dataset_id}", response_model=DatasetResponse)
def get_dataset(
    dataset_id: str,
    service: DatasetService = Depends(get_datasets),
) -> DatasetResponse:
    return DatasetResponse.model_validate(service.get(dataset_id))


@router.post("/{dataset_id}/validate", response_model=DatasetValidationReport)
def revalidate_dataset(
    dataset_id: str,
    service: DatasetService = Depends(get_datasets),
) -> DatasetValidationReport:
    _, report = service.revalidate(dataset_id)
    return DatasetValidationReport(**report.as_dict())
