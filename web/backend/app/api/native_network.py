from typing import Literal
from uuid import uuid4
import time

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, StrictInt
from ..errors import ConflictError, InputValidationError
from ..services.windows_capture import capabilities
from .deps import require_auth
from .sdn import check_origin

router = APIRouter(
    prefix="/native-network",
    tags=["Windows network"],
    dependencies=[Depends(require_auth), Depends(check_origin)],
)


def service(request: Request):
    return request.app.state.native_network


class Change(BaseModel):
    topology: Literal["single", "linear", "star", "tree", "custom"] = "single"
    subnet: str = "10.0.0.0/24"
    hosts: int = Field(3, ge=0, le=32)
    switches: int = Field(2, ge=1, le=8)
    node: str = ""
    peer: str = ""
    client: str | None = None


class Traffic(BaseModel):
    source: str
    dest: str
    scenario: str
    samples: int = Field(1, ge=1, le=500)
    rate: int = Field(1, ge=1, le=20)
    duration: int = Field(10, ge=1, le=120)
    offset: int = Field(0, ge=0, le=1000000)
    partition: Literal["test", "active_train"] = "test"
    label: Literal[0, 1] = 1
    dataset: str | None = None


class Capture(BaseModel):
    port: int | None = Field(None, ge=1, le=65535)
    client: str | None = None
    interface: str
    duration: int = Field(10, ge=1, le=120)


@router.get("")
def snapshot(s=Depends(service)):
    return s.snapshot()


@router.post("/topology/{op}")
def change(
    op: Literal[
        "create",
        "start",
        "stop",
        "delete",
        "host",
        "switch",
        "remove",
        "connect",
        "disconnect",
        "map",
    ],
    p: Change,
    s=Depends(service),
):
    return s.change(op, p)


@router.post("/traffic")
def traffic(p: Traffic, s=Depends(service)):
    return s.submit(p.model_dump())


@router.post("/jobs/{jid}/stop")
def stop(jid: str, s=Depends(service)):
    job = s.app.jobs.get(jid)
    if job.job_type not in ("native_traffic", "windows_capture"):
        raise ConflictError("This is not a network job.")
    return {"status": s.app.job_manager.cancel(jid).status}


@router.get("/capture")
def capture_status(s=Depends(service)):
    with s.db() as db:
        jobs = s.jobs(db, "windows-capture")
        for job in jobs:
            job["flows"] = [
                dict(r)
                for r in db.execute(
                    "SELECT src,dst,protocol,packets,bytes FROM capture_flow WHERE job=? ORDER BY bytes DESC",
                    (job["id"],),
                )
            ]
            job["protocols"] = [dict(row) for row in db.execute(
                """SELECT protocol,sum(packets) packets,sum(bytes) bytes FROM capture_flow
                   WHERE job=? GROUP BY protocol ORDER BY packets DESC""", (job["id"],))]
        return {**capabilities(), "jobs": jobs}


@router.post("/capture")
def begin_capture(p: Capture, s=Depends(service)):
    if p.client:
        s.app.clients.get(p.client)
    cap = capabilities()
    if p.interface not in {i["id"] for i in cap["interfaces"]}:
        raise InputValidationError(cap["reason"] or "Select an available interface.")
    job = s.app.job_manager.submit(
        "windows_capture", dedupe_key="windows_capture", payload=p.model_dump()
    )
    with s.db() as db:
        db.execute(
            "INSERT INTO native_job VALUES(?,?,?,?)",
            (job.id, "windows-capture", "capture", time.time()),
        )
    return {"job": job.id}


@router.get("/events/{fid}/trace")
def learning_trace(fid: str, s=Depends(service)):
    import json

    with s.db() as db:
        frame = db.execute("SELECT * FROM native_frame WHERE id=?", (fid,)).fetchone()
        if not frame:
            raise ConflictError("Unknown virtual event.")
        event = db.execute(
            "SELECT id,client,organization,label,evidence,status,run,version FROM auto_event WHERE id=?",
            (frame["event"],),
        ).fetchone()
        run = (
            db.execute("SELECT * FROM auto_run WHERE id=?", (event["run"],)).fetchone()
            if event and event["run"]
            else None
        )
        result = dict(
            frame=fid,
            security=dict(event) if event else None,
            run=None,
            contributions=[],
            acks=[],
        )
        if run:
            result["run"] = {
                k: run[k]
                for k in (
                    "id",
                    "job",
                    "experiment",
                    "parent",
                    "candidate",
                    "detail",
                    "state",
                )
            }
            result["run"]["validation"] = (
                json.loads(run["validation"]) if run["validation"] else None
            )
            if run["job"]:
                job=s.app.jobs.get(run["job"])
                result["job_record"]=dict(id=job.id,status=job.status,progress=job.progress,message=job.error or job.message,started=job.started_at,finished=job.finished_at)
            result["contributions"] = [
                dict(r)
                for r in db.execute(
                    "SELECT id,client,count,organization,round_number,state,digest,duration,base FROM central_update WHERE version=?",
                    (run["candidate"],),
                )
            ]
            result["acks"] = [
                dict(r)
                for r in db.execute(
                    "SELECT client,ts,version,digest FROM auto_ack WHERE run=?",
                    (run["id"],),
                )
            ]
        return result


@router.post("/events/{fid}/compare")
def compare_sample(fid: str, baseline: str, candidate: str, s=Depends(service)):
    import json
    from ..services.version_evaluation import artifact, THRESHOLD
    from ..domain.federated.keras_backend import KerasGRUBackend
    from ..domain.federated.client import weight_digest

    central = s.app.central
    with s.db() as db:
        event = db.execute(
            """SELECT e.* FROM auto_event e JOIN native_frame f ON e.id=f.event
                             WHERE f.id=? AND e.origin='dataset evaluation' AND e.run IS NULL""",
            (fid,),
        ).fetchone()
    if not event:
        raise ConflictError("Select an independent held-out dataset replay.")
    owner = central.row(
        "SELECT model FROM central_version WHERE version=?", (event["version"],)
    )["model"]
    ds, raw, prep = central.reference(owner)
    idx = event["row_index"]
    if (
        event["source"] != ds.sha256
        or idx not in prep.split.test
        or raw.rows[idx] != json.loads(event["features"])
    ):
        raise ConflictError("Replay does not match the fixed holdout.")
    result = []
    for version in (baseline, candidate):
        v = central.row(
            "SELECT * FROM central_version WHERE model=? AND version=?",
            (owner, version),
        )
        side = artifact(central, json.loads(v["artifact"]), "preprocessing")
        if (
            side["prepared"]["split"] != prep.split.as_dict()
            or side["prepared"]["scaler"] != prep.scaler.as_dict()
            or side["feature_names"] != raw.feature_names
        ):
            raise ConflictError("Version preprocessing differs from the reference.")
        weights = central.weights(version)
        if weight_digest(weights) != v["digest"]:
            raise ConflictError("Weight digest mismatch.")
        prob = float(
            KerasGRUBackend().predict(
                weights, [prep.test_rows[list(prep.split.test).index(idx)]]
            )[0]
        )
        result.append(
            dict(
                version=version,
                weight_hash=v["digest"],
                probability=prob,
                prediction=int(prob > THRESHOLD),
                truth=event["truth"],
                csv_row=idx + 2,
            )
        )
    with s.db() as db:
        db.execute(
            "INSERT INTO native_comparison VALUES(?,?,?,?,?,?)",
            (uuid4().hex, fid, baseline, candidate, time.time(), json.dumps(result)),
        )
    return result


class Review(BaseModel):
    label: StrictInt = Field(ge=0, le=1)
    evidence: str = Field(min_length=1, max_length=500)


@router.get("/samples/{engine}/{scope}")
def samples(engine: Literal["simulation", "capture"], scope: str, s=Depends(service)):
    with s.db() as db:
        return [
            dict(r)
            for r in db.execute(
                """SELECT s.id,s.ts,s.client,s.outcome,s.reason,s.event,s.host,s.engine,s.version,CASE WHEN s.event IS NULL THEN s.label ELSE e.label END label
         FROM native_sample s LEFT JOIN auto_event e ON e.id=s.event WHERE s.engine=? AND s.scope=? ORDER BY s.ts DESC LIMIT 200""",
                (engine, scope),
            )
        ]


@router.post("/samples/{sid}/review")
def review(sid: str, p: Review, s=Depends(service)):
    from ..services.native_samples import review

    return review(s.app, sid, p.label, p.evidence)


@router.post("/publish/{engine}/{scope}")
async def publish(
    engine: Literal["simulation", "capture"], scope: str, s=Depends(service)
):
    from ..services.native_samples import publish

    return await publish(s.app, engine, scope)


@router.get("/guide/{mid}")
def guide(mid: str, s=Depends(service)):
    from ..services.native_demo import checkpoints

    return checkpoints(s.app, mid)


@router.post("/events/{fid}/inspect")
def inspect_event(fid: str, s=Depends(service)):
    trace = learning_trace(fid, s)
    with s.db() as db:
        db.execute(
            "INSERT OR REPLACE INTO native_inspection VALUES(?,?)", (fid, time.time())
        )
    return trace

@router.get("/sample/{sid}")
def sample_details(sid: str, s=Depends(service)):
    import json
    from ..services.native_samples import schema

    with s.db() as db:
        row = db.execute(
            """SELECT s.*, e.prediction, e.probability, e.status,
                      CASE WHEN s.event IS NULL THEN s.label ELSE e.label END AS verified
               FROM native_sample s LEFT JOIN auto_event e ON e.id=s.event
               WHERE s.id=?""",
            (sid,),
        ).fetchone()
    if not row:
        raise ConflictError("Unknown observation window.")

    engine = row["engine"]
    units = ["bytes", "switches" if engine == "simulation" else "IP protocol number", "seconds", "seconds"] * 12
    data = dict(row)
    data.update(
        schema_id=engine + ".window.v1",
        preprocessing="raw ordered observations v1",
        features=[
            dict(name=name, value=value, unit=unit)
            for name, value, unit in zip(schema(engine), json.loads(row["features"]), units, strict=True)
        ],
    )
    if row["verified"] in (0, 1) and row["prediction"] in (0, 1):
        outcomes = (("True negative", "False positive"), ("False negative", "True positive"))
        data["outcome"] = outcomes[row["verified"]][row["prediction"]]
    return data
