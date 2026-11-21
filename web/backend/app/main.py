"""FastAPI application factory and local-first entry point."""

from __future__ import annotations

import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api import clients, datasets, experiments, health, ips, jobs, predictions
from .config import Settings
from .db import Database
from .errors import AppError
from .logging_config import configure_logging
from .services.client_service import ClientService
from .services.dataset_service import DatasetService
from .services.encryption_service import EncryptionService
from .services.experiment_service import ExperimentService
from .services.federated_service import FederatedService
from .services.job_manager import JobHandler, JobManager
from .services.job_service import JobService
from .services.model_service import ModelService
from .services.research_adapter import ResearchAdapter
from .services.sdn_service import SDNService
from .services.security_service import SecurityService
from .services.simulation_service import SimulationService
from .services.training_service import TrainingService
from .storage.paths import StoragePaths

logger = logging.getLogger(__name__)
_REQUEST_ID_RE = re.compile(r"[^A-Za-z0-9._-]")


def _request_id(value: str | None) -> str:
    candidate = _REQUEST_ID_RE.sub("", (value or "").strip())[:64]
    return candidate or uuid.uuid4().hex


def _error_response(
    status_code: int,
    code: str,
    message: str,
    details: object | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details}},
    )


def create_app(
    settings: Settings | None = None,
    *,
    job_handlers: dict[str, JobHandler] | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description=(
            "Local-first SecureFed-IDS backend foundation. Encryption and prediction "
            "are fail-closed until verified backends exist."
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:4173",
            "http://127.0.0.1:4173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.settings = settings
    app.state.job_handlers = dict(job_handlers or {})

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings.log_level)
        paths = StoragePaths(settings)
        paths.ensure()
        db = Database(settings.database_url or "")
        db.init()
        security = SecurityService(settings)
        jobs_service = JobService(db)
        jobs_service.recover_interrupted()
        encryption = EncryptionService(settings)
        datasets_service = DatasetService(db, paths, security, settings)
        experiments_service = ExperimentService(db, datasets_service)
        experiments_service.recover_interrupted()
        clients_service = ClientService(db)
        models_service = ModelService(settings, paths)
        sdn_service = SDNService()
        adapter = ResearchAdapter(settings, paths, security)
        simulation_service = SimulationService(settings, datasets_service)
        training_service = TrainingService(
            settings, datasets_service, paths, encryption=encryption
        )
        handlers = dict(application.state.job_handlers)
        job_manager = JobManager(db, jobs_service, handlers, settings.job_workers)
        federated = FederatedService(
            db,
            settings,
            datasets_service,
            experiments_service,
            jobs_service,
            adapter,
            encryption,
            simulation_service,
            training_service,
            job_manager,
        )
        if "research_run" not in handlers:
            handlers["research_run"] = lambda context, payload: federated.execute_job(
                context, payload
            )
        if "simulation_run" not in handlers:
            handlers["simulation_run"] = (
                lambda context, payload: federated.execute_simulation_job(context, payload)
            )
        if "training_run" not in handlers:
            handlers["training_run"] = (
                lambda context, payload: federated.execute_training_job(context, payload)
            )

        application.state.paths = paths
        application.state.db = db
        application.state.security = security
        application.state.jobs = jobs_service
        application.state.job_manager = job_manager
        application.state.encryption = encryption
        application.state.datasets = datasets_service
        application.state.experiments = experiments_service
        application.state.clients = clients_service
        application.state.models = models_service
        application.state.sdn = sdn_service
        application.state.adapter = adapter
        application.state.simulation = simulation_service
        application.state.training = training_service
        application.state.federated = federated
        logger.info("SecureFed-IDS backend started in %s mode", settings.environment)
        try:
            yield
        finally:
            job_manager.shutdown()
            db.dispose()
            logger.info("SecureFed-IDS backend stopped")

    app.router.lifespan_context = lifespan
    app.include_router(health.router, prefix=settings.api_prefix)
    app.include_router(ips.router, prefix=settings.api_prefix)
    app.include_router(datasets.router, prefix=settings.api_prefix)
    app.include_router(experiments.router, prefix=settings.api_prefix)
    app.include_router(clients.router, prefix=settings.api_prefix)
    app.include_router(predictions.router, prefix=settings.api_prefix)
    app.include_router(jobs.router, prefix=settings.api_prefix)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = _request_id(request.headers.get("X-Request-ID"))
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "%s %s %s %.1fms request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            request_id,
        )
        return response

    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        return _error_response(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _error_response(
            422,
            "validation_error",
            "request validation failed",
            jsonable_encoder(exc.errors()),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(
        _request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else "HTTP error"
        return _error_response(exc.status_code, "http_error", detail)

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled application error", exc_info=exc)
        return _error_response(500, "internal_error", "internal server error")

    return app


app = create_app()
