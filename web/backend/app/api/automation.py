from typing import Annotated, Literal
import json

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, StrictInt

from ..errors import ConflictError
from ..services.automatic import Policy
from .clients import score_client_sample
from .deps import require_auth
from .sdn import check_origin

router = APIRouter(
    prefix="/automation",
    tags=["automatic retraining"],
    dependencies=[Depends(require_auth), Depends(check_origin)],
)


def service(request: Request):
    return request.app.state.automatic


class Review(BaseModel):
    label: StrictInt = Field(ge=0, le=1)
    evidence: str = Field(min_length=1, max_length=500)


class Organization(BaseModel):
    name: str = Field(max_length=120)


@router.post("/clients/{cid}/organization")
def organization(cid: str, p: Organization, s=Depends(service)):
    clients = s.app.clients
    with clients.lock:
        record = clients.get(cid)
        clients.update(
            cid, status=None, config={**record.config, "organization": p.name.strip()}
        )
    return {"organization": p.name.strip()}


@router.post("/clients/{cid}/training-sample")
def training_sample(
    cid: str, offset: Annotated[int, Query(ge=0)] = 0, s=Depends(service)
):
    return score_client_sample(
        cid,
        offset,
        s.app.clients,
        s.app.datasets,
        s.app.models,
        partition="active_train",
    )


@router.post("/policy")
def policy(p: Policy, s=Depends(service)):
    with s.db() as db:
        db.execute("UPDATE auto_policy SET body=? WHERE id=1", (p.model_dump_json(),))
    s.wake.set()
    return p


def run_view(row, db, s):
    run = dict(row)
    for key in ("policy", "events", "clients", "validation"):
        run[key] = json.loads(run[key]) if run[key] else None
    run["acks"] = [
        dict(r) for r in db.execute("SELECT * FROM auto_ack WHERE run=?", (run["id"],))
    ]
    if run["job"]:
        job = s.app.jobs.get(run["job"])
        run.update(progress=job.progress, message=job.message)
    return run


@router.get("/runs/{rid}")
def run_detail(rid: str, s=Depends(service)):
    with s.db() as db:
        row = db.execute("SELECT * FROM auto_run WHERE id=?", (rid,)).fetchone()
        if not row:
            raise ConflictError("Unknown run")
        return run_view(row, db, s)


@router.get("/status")
def status(s=Depends(service)):
    with s.db() as db:
        runs = []
        for row in db.execute("SELECT * FROM auto_run ORDER BY ts DESC LIMIT 50"):
            run = run_view(row, db, s)
            runs.append(run)
        count = db.execute(
            "SELECT count(DISTINCT sample_key) FROM auto_event e WHERE status='verified' AND label=1 AND NOT EXISTS(SELECT 1 FROM auto_event u WHERE u.sample_key=e.sample_key AND u.run IS NOT NULL)"
        ).fetchone()[0]
        return {"policy": s.policy(db), "pending": count, "runs": runs}


@router.get("/events")
def events(
    client: str = "",
    origin: str = "",
    status: str = "",
    organization: str = "",
    offset: Annotated[int, Query(ge=0)] = 0,
    s=Depends(service),
):
    with s.db() as db:
        rows = db.execute(
            """SELECT id,client,organization,host,host_ip,src,dst,ts,origin,version,prediction,probability,
          truth,label,evidence,status,run,row_index FROM auto_event WHERE (?='' OR client=?) AND (?='' OR origin=?)
          AND (?='' OR status=?) AND (?='' OR organization=?) ORDER BY ts DESC LIMIT 100 OFFSET ?""",
            (
                client,
                client,
                origin,
                origin,
                status,
                status,
                organization,
                organization,
                offset,
            ),
        ).fetchall()
        return [event_view(e) for e in rows]


def event_view(row):
    return {
        **dict(row),
        "severity": "unscored"
        if row["prediction"] is None
        else "normal"
        if not row["prediction"]
        else "high"
        if row["probability"] >= 0.9
        else "warning",
    }


@router.get("/events/{eid}")
def event_detail(eid: str, s=Depends(service)):
    with s.db() as db:
        row = db.execute(
            "SELECT id,client,organization,host,host_ip,src,dst,ts,origin,version,prediction,probability,truth,label,evidence,status,run,row_index FROM auto_event WHERE id=?",
            (eid,),
        ).fetchone()
        if not row:
            raise ConflictError("Unknown event")
        return event_view(row)


@router.post("/events/{eid}/review")
def review(eid: str, p: Review, s=Depends(service)):
    s.review(eid, p.label, p.evidence)
    return {"id": eid}


@router.get("/notifications")
def notifications(before: int = 0, s=Depends(service)):
    with s.db() as db:
        return {
            "unread": db.execute(
                "SELECT count(*) FROM auto_notice WHERE seen=0"
            ).fetchone()[0],
            "items": [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM auto_notice WHERE ?=0 OR id<? ORDER BY id DESC LIMIT 50",
                    (before, before),
                )
            ],
        }


@router.post("/notifications/{nid}/read")
def mark(nid: int, s=Depends(service)):
    with s.db() as db:
        db.execute("UPDATE auto_notice SET seen=1 WHERE id=? OR ?=0", (nid, nid))
    return {"ok": True}


@router.post("/runs/{rid}/sync")
def sync(rid: str, s=Depends(service)):
    s.synchronize(rid)
    return {"ok": True}


@router.post("/runs/{rid}/retry")
def retry(rid: str, s=Depends(service)):
    with s.db() as db:
        db.execute("BEGIN IMMEDIATE")
        r = db.execute("SELECT state FROM auto_run WHERE id=?", (rid,)).fetchone()
        if not r or r[0] != "failed":
            raise ConflictError("Only failed reservations can be released for retry.")
        db.execute(
            "UPDATE auto_event SET status='verified',run=NULL WHERE run=?", (rid,)
        )
        db.execute("UPDATE auto_run SET state='retried' WHERE id=?", (rid,))
    s.wake.set()
    return {"ok": True}
