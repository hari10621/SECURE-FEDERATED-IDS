import os
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from ..errors import ConflictError, ForbiddenError
from ..services.sdn_service import FEATURES
from .clients import score_client_sample
from .deps import get_clients, get_datasets, get_models, get_sdn, require_auth


def check_origin(request: Request):
    origin = request.headers.get("origin")
    if (
        request.method == "POST"
        and origin
        and origin
        not in {
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            f"http://127.0.0.1:{int(os.getenv('SECUREFED_UI_PORT','5173'))}",
            "http://127.0.0.1:8000",
            "http://localhost:8000",
        }
    ):
        raise ForbiddenError("Use the local console for lab operations.")


router = APIRouter(
    prefix="/sdn",
    tags=["sdn"],
    dependencies=[Depends(require_auth), Depends(check_origin)],
)


class Network(BaseModel):
    topology: Literal["single", "linear", "tree"] = "linear"
    switches: int = Field(default=2, ge=1, le=8)
    hosts: int = Field(default=5, ge=2, le=32)
    subnet: str = "10.0.0.0/24"
    controller: str = "127.0.0.1"
    port: int = Field(default=16653, ge=1, le=65535)


@router.get("/topology")
def topology(service=Depends(get_sdn)):
    return service.snapshot()


@router.get("/inventory/{kind}")
def inventory(
    kind: Literal["hosts", "switches", "links", "flows", "history", "events"],
    service=Depends(get_sdn),
):
    snapshot = service.snapshot()
    return {
        "state": snapshot["state"],
        "reason": snapshot["reason"],
        "items": snapshot[kind],
    }


@router.post("/lab/create")
def create(spec: Network, service=Depends(get_sdn)):
    return service.call("create", spec.model_dump())


@router.post("/lab/{action}")
def lifecycle(action: Literal["start", "stop", "delete"], service=Depends(get_sdn)):
    return service.call(action)


@router.post("/hosts/{host}/map/{client_id}")
def mapping(
    host: str, client_id: str, clients=Depends(get_clients), service=Depends(get_sdn)
):
    clients.get(client_id)
    service.map(host, client_id)
    return {"client": client_id}


@router.post("/hosts/{host}/ping")
def ping(host: str, service=Depends(get_sdn)):
    lab, _ = service.host(host)
    return service.call("ping", {"host": host, "lab_id": lab})


@router.post("/hosts/{host}/replay")
def replay(
    host: str,
    partition: Literal["test","active_train"]="test",
    offset: Annotated[int, Query(ge=0)] = 0,
    service=Depends(get_sdn),
    clients=Depends(get_clients),
    datasets=Depends(get_datasets),
    models=Depends(get_models),
):
    lab, h = service.host(host)
    if not h["client"]:
        raise ConflictError("Map a federated client first.")
    receipt = score_client_sample(h["client"], offset, clients, datasets, models,partition=partition,host=h)
    service.event(lab, host, h["client"], "recorded dataset replay", receipt)
    return receipt


@router.post("/hosts/{host}/capture")
def capture(
    host: str,
    normal_probe: bool = False,
    service=Depends(get_sdn),
    models=Depends(get_models),
):
    return service.capture(host, models, normal_probe)


@router.get("/hosts/{host}/samples")
def samples(host: str, service=Depends(get_sdn)):
    lab, h = service.host(host)
    import json

    with service.db() as db:
        rows = db.execute(
            "SELECT id,ts,label,features FROM samples WHERE lab=? AND host=? AND client=? ORDER BY ts DESC LIMIT 100",
            (lab, host, h["client"]),
        )
        return [
            {
                "id": r["id"],
                "ts": r["ts"],
                "label": r["label"],
                "features": json.loads(r["features"]),
            }
            for r in rows
        ]


@router.post("/samples/{sample_id}/approve")
def approve(sample_id: str, label: Literal["0", "1"], evidence: Annotated[str, Query(max_length=500)] = "", service=Depends(get_sdn)):
    with service.db() as db:
        event=db.execute("SELECT id FROM auto_event WHERE source=? AND origin='live traffic'",(sample_id,)).fetchone()
    if event and evidence.strip():
        service.automatic.review(event[0],int(label),evidence)
        return {"label":int(label)}
    with service.db() as db:
        if event and db.execute("SELECT label FROM auto_event WHERE id=? AND evidence IS NOT NULL",(event[0],)).fetchone():
            raise ConflictError("Use the independent review control to change a previously verified label.")
        if not db.execute(
            "UPDATE samples SET label=? WHERE id=?", (int(label), sample_id)
        ).rowcount:
            raise ConflictError("Unknown capture.")
    return {"label": int(label)}


@router.post("/dataset")
async def publish(
    service=Depends(get_sdn),
    datasets=Depends(get_datasets),
    clients=Depends(get_clients),
):
    import csv, io, json
    from starlette.datastructures import UploadFile
    from ..enums import DatasetType

    lab = service.snapshot()["lab_id"]
    with service.db() as db:
        rows = list(
            db.execute(
                "SELECT client,features,label FROM samples WHERE lab=? AND label IS NOT NULL ORDER BY ts,id",
                (lab,),
            )
        )
    labels = [r["label"] for r in rows]
    if min(labels.count(0), labels.count(1)) < 2:
        raise ConflictError(
            "Approve at least two independently verified samples of each class to populate both train and test splits."
        )
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(FEATURES + ["Label"])
    writer.writerows(json.loads(r["features"]) + [r["label"]] for r in rows)
    upload = UploadFile(
        filename="sdn-counter-windows.csv", file=io.BytesIO(stream.getvalue().encode())
    )
    dataset = await datasets.save_upload(
        upload,
        dataset_type=DatasetType.INSDN,
        name="SDN reviewed windows",
        label_column="Label",
    )
    with service.db() as db:
        db.execute(
            "INSERT INTO published VALUES (?,?,?)",
            (dataset.id, lab, json.dumps([r["client"] for r in rows])),
        )
    return {"dataset_id": dataset.id, "rows": len(rows)}
