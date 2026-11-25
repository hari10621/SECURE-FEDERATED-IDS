"""Local client configuration endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from ..enums import ClientStatus
from ..schemas import (
    ClientCreate,
    ClientListResponse,
    ClientResponse,
    ClientStatusResponse,
    ClientUpdate,
)
from ..services.client_service import ClientService
from .deps import get_clients, require_auth

router = APIRouter(
    prefix="/clients",
    tags=["clients"],
    dependencies=[Depends(require_auth)],
)


@router.post("", response_model=ClientResponse, status_code=201)
def create_client(
    payload: ClientCreate,
    service: ClientService = Depends(get_clients),
) -> ClientResponse:
    return ClientResponse.model_validate(
        service.create(name=payload.name, config=payload.config)
    )


@router.get("", response_model=ClientListResponse)
def list_clients(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    service: ClientService = Depends(get_clients),
) -> ClientListResponse:
    rows, total = service.list(limit=limit, offset=offset)
    return ClientListResponse(
        items=[ClientResponse.model_validate(row) for row in rows],
        total=total,
    )


@router.get("/{client_id}", response_model=ClientResponse)
def get_client(
    client_id: str,
    service: ClientService = Depends(get_clients),
) -> ClientResponse:
    return ClientResponse.model_validate(service.get(client_id))


@router.post("/{client_id}/enable", response_model=ClientResponse)
def enable_client(
    client_id: str,
    service: ClientService = Depends(get_clients),
) -> ClientResponse:
    client = service.update(client_id, status=ClientStatus.ENABLED, config=None)
    return ClientResponse.model_validate(client)


@router.post("/{client_id}/disable", response_model=ClientResponse)
def disable_client(
    client_id: str,
    service: ClientService = Depends(get_clients),
) -> ClientResponse:
    client = service.update(client_id, status=ClientStatus.DISABLED, config=None)
    return ClientResponse.model_validate(client)


@router.get("/{client_id}/status", response_model=ClientStatusResponse)
def client_status(
    client_id: str,
    service: ClientService = Depends(get_clients),
) -> ClientStatusResponse:
    client = service.get(client_id)
    return ClientStatusResponse(
        id=client.id, status=client.status, runtime_connected=False,
        detail="Phase 3 configuration record. Training starts its own local client workers.",
    )


@router.delete("/{client_id}", response_model=ClientResponse)
def delete_client(
    client_id: str,
    service: ClientService = Depends(get_clients),
) -> ClientResponse:
    client = service.get(client_id)
    with service.db.session() as session:
        session.delete(client)
    return ClientResponse.model_validate(client)


@router.patch("/{client_id}", response_model=ClientResponse)
def update_client(
    client_id: str,
    payload: ClientUpdate,
    service: ClientService = Depends(get_clients),
) -> ClientResponse:
    return ClientResponse.model_validate(
        service.update(
            client_id,
            status=payload.status,
            config=payload.config,
        )
    )
