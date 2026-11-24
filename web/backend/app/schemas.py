"""Pydantic request/response contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import ClientStatus, DatasetType, ExperimentStatus, JobStatus, ValidationStatus


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    database: str
    encryption: str
    timestamp: datetime


class VersionResponse(BaseModel):
    name: str
    version: str
    api_version: str
    environment: str
    python_version: str


class DatasetValidationReport(BaseModel):
    valid: bool
    rows: int
    columns: int
    feature_count: int
    label_column: str
    label_column_index: int
    label_counts: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    research_compatible: bool


class DatasetResponse(ORMModel):
    id: str
    name: str
    dataset_type: DatasetType
    original_filename: str
    sha256: str
    size_bytes: int
    rows: int
    columns: int
    feature_count: int
    label_column: str
    label_column_index: int
    label_counts: dict[str, int]
    validation_status: ValidationStatus
    validation_errors: list[str]
    warnings: list[str]
    research_compatible: bool
    created_at: datetime


class DatasetListResponse(BaseModel):
    items: list[DatasetResponse]
    total: int


class ExperimentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    dataset_id: str = Field(min_length=1, max_length=64)
    client_count: int
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be empty")
        return value

    @field_validator("client_count")
    @classmethod
    def _allowed_clients(cls, value: int) -> int:
        if value not in {2, 3, 4, 8, 12}:
            raise ValueError("client_count must be one of 2, 3, 4, 8, 12")
        return value


class ExperimentResponse(ORMModel):
    id: str
    name: str
    dataset_id: str
    client_count: int
    status: ExperimentStatus
    config: dict[str, Any]
    result: dict[str, Any] | None
    error: str | None
    job_id: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class ExperimentListResponse(BaseModel):
    items: list[ExperimentResponse]
    total: int


class JobResponse(ORMModel):
    id: str
    job_type: str
    status: JobStatus
    progress: float
    message: str | None
    result: dict[str, Any] | None
    error: str | None
    cancel_requested: bool
    experiment_id: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class JobListResponse(BaseModel):
    items: list[JobResponse]
    total: int


class SimulationRequest(BaseModel):
    """Plaintext simulation settings. This never requests encryption."""

    mode: Literal["legacy", "clean"] = "clean"
    rounds: int = Field(default=5, ge=1, le=100)
    local_epochs: int = Field(default=2, ge=1, le=50)
    batch_size: int = Field(default=32, ge=1, le=4096)
    learning_rate: float = Field(default=0.05, gt=0.0, le=10.0)
    weighting: Literal["sample", "legacy"] = "sample"
    seed: int = Field(default=42, ge=0, le=2**31 - 1)
    test_size: float = Field(default=0.3, gt=0.0, lt=1.0)
    byzantine_check: bool = False


class TrainingRequest(BaseModel):
    """GRU federated training settings.

    Paper-specified defaults: 15 rounds, 512 batch size, 5 local epochs.
    Defaults are deliberately a one-round, one-epoch smoke run. Set the legacy
    15 rounds / 512 batch size / 5 local epochs explicitly for a research-sized run.

    Mode options:
    - ``legacy``: legacy simulated clients (default, for backward compatibility)
    - ``clean``: clean mode — split first, scaler fit on train only
    - ``centralized``: centralized baseline — pool all data, train as one model
    """

    mode: Literal["legacy", "clean", "centralized"] = "legacy"
    rounds: int = Field(default=1, ge=1, le=100)
    local_epochs: int = Field(default=1, ge=1, le=50)
    batch_size: int = Field(default=512, ge=1, le=4096)
    learning_rate: float = Field(default=0.0001, gt=0.0, le=10.0)
    weighting: Literal["sample", "legacy"] = "legacy"
    seed: int = Field(default=42, ge=0, le=2**31 - 1)
    test_size: float = Field(default=0.3, gt=0.0, lt=1.0)
    byzantine_check: bool = False
    byzantine_threshold: int = Field(default=2, ge=1, le=12)
    threshold: int | None = Field(default=None, ge=1, le=12)
    require_encryption: bool = False
    max_rows: int | None = Field(default=None, ge=1)


class PaperSuiteRequest(BaseModel):
    """Automated paper comparison suite settings.

    Defaults match the paper: 15 rounds, 5 local epochs, 512 batch size.
    """

    dataset_id: str = Field(min_length=1)
    rounds: int = Field(default=15, ge=1, le=100)
    local_epochs: int = Field(default=5, ge=1, le=50)
    batch_size: int = Field(default=512, ge=1, le=4096)
    learning_rate: float = Field(default=0.0001, gt=0.0, le=10.0)
    seed: int = Field(default=42, ge=0, le=2**31 - 1)
    test_size: float = Field(default=0.3, gt=0.0, lt=1.0)
    max_rows: int | None = Field(default=None, ge=1)
    client_counts: list[int] = Field(default_factory=lambda: [4, 8, 12])
    include_centralized: bool = True
    include_he: bool = True

    @field_validator("client_counts")
    @classmethod
    def _validate_client_counts(cls, value: list[int]) -> list[int]:
        allowed = {2, 3, 4, 8, 12}
        if not value:
            raise ValueError("client_counts must not be empty")
        invalid = [count for count in value if count not in allowed]
        if invalid:
            raise ValueError(
                f"client_counts must be drawn from {sorted(allowed)}; got {invalid}"
            )
        return value


class ExperimentStatusResponse(BaseModel):
    id: str
    status: ExperimentStatus
    execution_available: bool
    execution_reason: str
    simulation_available: bool = False
    simulation_reason: str = ""
    training_available: bool = False
    training_reason: str = ""
    job: JobResponse | None = None


class ClientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be empty")
        return value


class ClientUpdate(BaseModel):
    status: ClientStatus | None = None
    config: dict[str, Any] | None = None


class ClientResponse(ORMModel):
    id: str
    name: str
    status: ClientStatus
    config: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ClientListResponse(BaseModel):
    items: list[ClientResponse]
    total: int


class ClientStatusResponse(BaseModel):
    id: str
    status: ClientStatus
    runtime_connected: bool = False
    detail: str


class PredictionStatusResponse(BaseModel):
    available: bool
    reason: str
    model: str | None = None
    preprocessing: str | None = None


class PredictionRequest(BaseModel):
    features: list[float] = Field(min_length=1, max_length=4096)


class EncryptionStatusResponse(BaseModel):
    available: bool
    backend: str
    reason: str
    mode: str = "unavailable"
    encryption_claimed: bool = False
    params: dict[str, Any] = Field(default_factory=dict)
    key_ceremony: str = "disabled"
    secret_key_location: str = "none"


class SDNStatusResponse(BaseModel):
    available: bool
    reason: str = ""
    mode: str | None = None
    switch: dict[str, Any] | None = None


class MitigationRequest(BaseModel):
    """Request body for ``POST /api/v1/ips/mitigate``."""

    flow_id: str = ""
    switch_dp_id: str = ""
    table_id: int = 0
    prediction_probability: float = 0.0
    confidence_threshold: float = 0.5
    reason: str = "IDS prediction"


class MitigationResponse(BaseModel):
    """Response from ``POST /api/v1/ips/mitigate``."""

    request_id: str
    status: str
    applied_rule_id: str | None = None
    verification_result: dict[str, Any] | None = None
    error: str | None = None
    applied_at: float | None = None
    completed_at: float | None = None
    reason: str = ""


class IPSDetectResponse(BaseModel):
    """Response from ``POST /api/v1/ips/detect``."""

    available: bool
    reason: str = ""
    prediction: float | None = None
    label: int | None = None
    alert: dict[str, Any] | None = None
