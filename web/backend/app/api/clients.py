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
from ..errors import ConflictError
from ..services.dataset_service import DatasetService
from ..services.model_service import ModelService
from .deps import get_clients, get_datasets, get_models, require_auth

router = APIRouter(
    prefix="/clients",
    tags=["clients"],
    dependencies=[Depends(require_auth)],
)


def view(service, client):
    result = ClientResponse.model_validate(client)
    result.worker_pid = service.pid(client.id)
    result.runtime_connected = result.worker_pid is not None
    return result


@router.post("", response_model=ClientResponse, status_code=201)
def create_client(
    payload: ClientCreate,
    service: ClientService = Depends(get_clients),
) -> ClientResponse:
    return view(service,
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
        items=[view(service, row) for row in rows],
        total=total,
    )


@router.get("/{client_id}", response_model=ClientResponse)
def get_client(
    client_id: str,
    service: ClientService = Depends(get_clients),
) -> ClientResponse:
    return view(service, service.get(client_id))


@router.post("/{client_id}/attack-replay")
def attack_replay(client_id: str, offset: Annotated[int, Query(ge=0)] = 0,
                  service: ClientService = Depends(get_clients),
                  datasets: DatasetService = Depends(get_datasets),
                  models: ModelService = Depends(get_models)):
    return score_client_sample(client_id,offset,service,datasets,models)

def score_client_sample(client_id,offset,service,datasets,models,partition="test",host=None):
    client = service.get(client_id)
    manifest, (_, weights, prep, _) = models.current()
    source = datasets.source_id(prep["dataset_id"], weights["metadata"]["dataset_sha256"])
    sample = datasets.labelled_sample(source, 1, partition, offset, None, models)
    if sample["version"] != manifest["version"]:
        raise ConflictError("Deployment changed. Run the replay again.")
    receipt = service.replay(client.id, sample["features"])
    prediction = models.predict(receipt["features"])
    if prediction["version"] != sample["version"]:
        raise ConflictError("Deployment changed during inference. Run the replay again.")
    mapped_lab = None
    if host is None:
        sdn = models.automatic.app.sdn
        with sdn.db() as db:
            mapped = db.execute("SELECT 1 FROM mapping WHERE client=? LIMIT 1", (client.id,)).fetchone()
        if mapped:
            snapshot = sdn.snapshot()
            host = next((h for h in snapshot["hosts"] if h.get("client") == client.id), None)
            mapped_lab = snapshot.get("lab_id") if host else None
    with models.automatic.db() as db:
        db.execute("BEGIN IMMEDIATE")
        eid=models.automatic.record(db,client=client_id,origin="dataset evaluation" if partition=="test" else "dataset training",
            key=weights["metadata"]["dataset_sha256"]+":"+str(sample["index"]),features=sample["features"],schema=prep["feature_names"],
            result=prediction,source=weights["metadata"]["dataset_sha256"],row_index=sample["index"],truth=sample["actual"],
            host=(host or {}).get("name"),host_ip=(host or {}).get("ip"))
    response = {"event_id":eid,"client_name": client.name, "worker_pid": receipt["pid"], "csv_row": sample["index"] + 2,
            "feature_count": len(receipt["features"]), "actual": sample["actual"], **prediction}
    if mapped_lab:
        sdn.event(mapped_lab,host["name"],client.id,"recorded dataset replay",response)
    return response


@router.post("/{client_id}/enable", response_model=ClientResponse)
def enable_client(
    client_id: str,
    service: ClientService = Depends(get_clients),
) -> ClientResponse:
    client = service.update(client_id, status=ClientStatus.ENABLED, config=None)
    return view(service, client)


@router.post("/{client_id}/disable", response_model=ClientResponse)
def disable_client(
    client_id: str,
    service: ClientService = Depends(get_clients),
) -> ClientResponse:
    client = service.update(client_id, status=ClientStatus.DISABLED, config=None)
    return view(service, client)


@router.get("/{client_id}/status", response_model=ClientStatusResponse)
def client_status(
    client_id: str,
    service: ClientService = Depends(get_clients),
) -> ClientStatusResponse:
    client = service.get(client_id)
    return ClientStatusResponse(
        id=client.id, status=client.status, runtime_connected=bool(service.pid(client.id)),
        detail=f"Worker PID {service.pid(client.id)}" if service.pid(client.id) else "Phase 3 configuration record; worker disconnected.",
    )


@router.delete("/{client_id}", response_model=ClientResponse)
def delete_client(
    client_id: str,
    service: ClientService = Depends(get_clients),
) -> ClientResponse:
    client = service.get(client_id)
    service.update(client_id, status=ClientStatus.DISABLED, config=None)
    with service.db.session() as session:
        session.delete(client)
    return view(service, client)


@router.patch("/{client_id}", response_model=ClientResponse)
def update_client(
    client_id: str,
    payload: ClientUpdate,
    service: ClientService = Depends(get_clients),
) -> ClientResponse:
    return view(service,
        service.update(
            client_id,
            status=payload.status,
            config=payload.config,
        )
    )
