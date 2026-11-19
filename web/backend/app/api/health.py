"""Health, version, and component-status endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request, Response
from sqlalchemy import text

from ..schemas import (
    EncryptionStatusResponse,
    HealthResponse,
    SDNStatusResponse,
    VersionResponse,
)
from .deps import get_encryption, get_sdn

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health(request: Request, response: Response) -> HealthResponse:
    database = "ok"
    try:
        with request.app.state.db.session() as session:
            session.execute(text("SELECT 1"))
    except Exception:
        database = "error"
        response.status_code = 503
    encryption = get_encryption(request).status()
    return HealthResponse(
        status="ok" if database == "ok" else "degraded",
        version=request.app.state.settings.version,
        database=database,
        encryption="available" if encryption["available"] else "unavailable",
        timestamp=datetime.now(timezone.utc),
    )


@router.get("/version", response_model=VersionResponse)
def version(request: Request) -> VersionResponse:
    import platform
    import sys

    settings = request.app.state.settings
    return VersionResponse(
        name=settings.app_name,
        version=settings.version,
        api_version=settings.api_version,
        environment=settings.environment,
        python_version=platform.python_version() if sys.version_info else "unknown",
    )


@router.get("/encryption/status", response_model=EncryptionStatusResponse)
def encryption_status(request: Request) -> EncryptionStatusResponse:
    return EncryptionStatusResponse(**get_encryption(request).status())


@router.get("/sdn/status", response_model=SDNStatusResponse)
def sdn_status(request: Request) -> SDNStatusResponse:
    return SDNStatusResponse(**get_sdn(request).status())
