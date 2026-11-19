"""API dependency helpers."""

from __future__ import annotations

from typing import Annotated

from fastapi import Header, Request

from ..services.client_service import ClientService
from ..services.dataset_service import DatasetService
from ..services.experiment_service import ExperimentService
from ..services.federated_service import FederatedService
from ..services.job_manager import JobManager
from ..services.job_service import JobService
from ..services.model_service import ModelService
from ..services.security_service import SecurityService
from ..services.sdn_service import SDNService
from ..services.encryption_service import EncryptionService
from ..config import Settings


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_security(request: Request) -> SecurityService:
    return request.app.state.security


def get_datasets(request: Request) -> DatasetService:
    return request.app.state.datasets


def get_experiments(request: Request) -> ExperimentService:
    return request.app.state.experiments


def get_clients(request: Request) -> ClientService:
    return request.app.state.clients


def get_jobs(request: Request) -> JobService:
    return request.app.state.jobs


def get_job_manager(request: Request) -> JobManager:
    return request.app.state.job_manager


def get_federated(request: Request) -> FederatedService:
    return request.app.state.federated


def get_models(request: Request) -> ModelService:
    return request.app.state.models


def get_encryption(request: Request) -> EncryptionService:
    return request.app.state.encryption


def get_sdn(request: Request) -> SDNService:
    return request.app.state.sdn


def require_auth(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    get_security(request).require_token(authorization)
