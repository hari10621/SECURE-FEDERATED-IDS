"""Shared enums for persisted state and API contracts."""

from __future__ import annotations

from enum import Enum


class DatasetType(str, Enum):
    INSDN = "insdn"
    CICIDS2017 = "cicids2017"
    CICIDS2019 = "cicids2019"


class ValidationStatus(str, Enum):
    VALID = "valid"
    INVALID = "invalid"


class ExperimentStatus(str, Enum):
    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    CANCELLATION_REQUESTED = "cancellation_requested"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ClientStatus(str, Enum):
    CONFIGURED = "configured"
    ENABLED = "enabled"
    DISABLED = "disabled"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    CANCELLATION_REQUESTED = "cancellation_requested"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


ACTIVE_JOB_STATUSES = {
    JobStatus.QUEUED.value,
    JobStatus.RUNNING.value,
    JobStatus.CANCELLATION_REQUESTED.value,
}

ACTIVE_EXPERIMENT_STATUSES = {
    ExperimentStatus.QUEUED.value,
    ExperimentStatus.RUNNING.value,
    ExperimentStatus.CANCELLATION_REQUESTED.value,
}
