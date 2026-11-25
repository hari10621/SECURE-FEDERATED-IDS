from typing import Literal
import json
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from pydantic import BaseModel, ConfigDict, Field
from ..enums import ClientStatus
from ..errors import ConflictError, InputValidationError
from ..models import Client, Job, Experiment
from ..services import version_evaluation
from .deps import require_auth
from .sdn import check_origin

router = APIRouter(
    prefix="/central-models",
    tags=["central models"],
    dependencies=[Depends(require_auth), Depends(check_origin)],
)


def service(request: Request):
    return request.app.state.central


class CreateModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=90)
    dataset: str
    architecture: Literal["GRU-256-128-64"] = "GRU-256-128-64"
    algorithm: Literal["FedAvg"] = "FedAvg"
    method: Literal["random", "import", "restore"] = "random"
    source: str | None = None
    weights: dict | None = None
    preprocessing: dict | None = None
    learning_rate: float = Field(default=0.0001, gt=0, le=1)
    batch_size: int = Field(default=512, ge=1, le=4096)
    seed: int = Field(default=42, ge=0, le=2**31 - 1)
    test_size: float = Field(default=0.3, gt=0, lt=1)
    shards: int = Field(default=2, ge=2, le=12)


class Member(BaseModel):
    name: str = Field(default="", max_length=120)
    client: str | None = None
    organization: str = Field(max_length=120)
    dataset: str
    host: str | None = None
    epochs: int = Field(default=1, ge=1, le=50)
    train: bool = False


class Round(BaseModel):
    base: str
    clients: list[str] = Field(min_length=1, max_length=12)
    action: Literal["stored", "fresh", "local"]
    encrypted: bool = False


@router.post("")
def create(p: CreateModel, s=Depends(service)):
    return s.create(p)


@router.get("")
def models(s=Depends(service)):
    with s.db() as db:
        return [
            dict(r)
            for r in db.execute(
                "SELECT id,name,reference,head,ts FROM central_model ORDER BY ts DESC"
            )
        ]


@router.get("/{mid}")
def detail(mid: str, s=Depends(service)):
    m = s.model(mid)
    with s.db() as db:
        versions = []
        for v in db.execute(
            "SELECT * FROM central_version WHERE model=? ORDER BY number DESC", (mid,)
        ):
            a = json.loads(v["artifact"])
            versions.append(
                dict(
                    version=v["version"],
                    number=v["number"],
                    rounds=v["rounds"],
                    parent=v["parent"],
                    state=v["state"],
                    weight_hash=v["digest"],
                    sha256=a.get("weights_sha256"),
                    ts=v["ts"],
                    experiment=v["experiment"],
                    validation=json.loads(v["metrics"]) if v["metrics"] else None,
                )
            )
        updates = [
            dict(r)
            for r in db.execute(
                """SELECT u.id,u.client,u.organization,u.base,u.count,u.duration,u.digest,
                          u.local_hash,u.state,u.version,u.ts,u.base_hash,u.round_number,
                          c.benign,c.attack
                   FROM central_update u LEFT JOIN central_update_classes c ON c.id=u.id
                   WHERE u.model=? ORDER BY u.ts DESC""",
                (mid,),
            )
        ]
        members = []
        for r in db.execute(
            "SELECT * FROM central_member WHERE model=? ORDER BY slot", (mid,)
        ):
            with s.app.clients.db.session() as session:
                c = session.get(Client, r["client"])
            job = s.app.jobs.get(r["job"]) if r["job"] else None
            members.append(
                {
                    **dict(r),
                    "organization": c.config.get("organization", "") if c else "",
                    "name": c.name if c else "Deleted client",
                    "pid": s.app.clients.pid(r["client"]),
                    "status": job.status if job else "assigned",
                    "message": job.error or job.message if job else None,
                }
            )
        active = (
            json.loads(s.app.models.active.read_bytes())["version"]
            if s.app.models.active.is_file()
            else None
        )
        deployed = next(
            (v["version"] for v in versions if v["version"] == active), None
        )
        acks = [
            dict(r)
            for r in db.execute(
                "SELECT * FROM auto_ack WHERE version IN (SELECT version FROM central_version WHERE model=?) ORDER BY ts DESC",
                (mid,),
            )
        ]
        runs = []
        for r in db.execute(
            "SELECT * FROM auto_run WHERE parent IN (SELECT version FROM central_version WHERE model=?) ORDER BY ts DESC",
            (mid,),
        ):
            events = [
                dict(e)
                for eid in json.loads(r["events"])
                for e in db.execute(
                    "SELECT e.id,e.client,e.organization,e.label,t.ts AS verified FROM auto_event e LEFT JOIN auto_review_time t ON t.event=e.id WHERE e.id=?",
                    (eid,),
                )
            ]
            job = s.app.jobs.get(r["job"]) if r["job"] else None
            runs.append(
                dict(
                    id=r["id"],
                    state=r["state"],
                    detail=r["detail"],
                    parent=r["parent"],
                    candidate=r["candidate"],
                    job=r["job"],
                    experiment=r["experiment"],
                    events=events,
                    started=job.started_at if job else None,
                    finished=job.finished_at if job else None,
                    validation=json.loads(r["validation"]) if r["validation"] else None,
                )
            )
    with s.app.jobs.db.session() as session:
        durations = {
            experiment: (finished - started).total_seconds()
            for experiment, started, finished in session.execute(
                select(Experiment.id, Experiment.started_at, Experiment.finished_at)
                .where(Experiment.id.in_([v["experiment"] for v in versions if v["experiment"]]))
            ) if started and finished
        }
        for version in versions:
            version["training_seconds"] = durations.get(version["experiment"])
        # An unfinished or failed round may never produce a version artifact.
        pending_rounds = [
            dict(
                job=j.id,
                base=j.payload["base"],
                state=j.status,
                progress=j.progress,
                message=j.error or j.message,
                created=j.created_at,
            )
            for j in session.scalars(
                select(Job)
                .where(
                    Job.job_type == "central_round",
                    Job.payload["model"].as_string() == mid,
                    Job.status.in_(
                        (
                            "queued",
                            "running",
                            "failed",
                            "cancellation_requested",
                            "cancelled",
                        )
                    ),
                )
                .order_by(Job.created_at.desc())
            )
        ]
    return {
        **m,
        "config": json.loads(m["config"]),
        "deployed": deployed,
        "versions": versions,
        "clients": members,
        "contributions": updates,
        "acks": acks,
        "retraining": runs,
        "round_jobs": pending_rounds,
    }


@router.post("/{mid}/members")
def member(mid: str, p: Member, s=Depends(service)):
    with s.lock:
        m = s.model(mid)
        mapping = None
        if p.host:
            lab, host = s.app.sdn.host(p.host)
            mapping = (lab, p.host)
            if host.get("client") and host["client"] != p.client:
                raise ConflictError("This SDN host is already mapped.")
        if not p.client and not p.name.strip():
            raise InputValidationError("Enter a client name.")
        c = (
            s.app.clients.get(p.client)
            if p.client
            else s.app.clients.create(
                name=p.name.strip(), config={"organization": p.organization.strip()}
            )
        )
        try:
            s.app.clients.update(
                c.id,
                status=ClientStatus.ENABLED,
                config={**c.config, "organization": p.organization.strip()},
            )
            s.assign(mid, c.id, p.dataset, p.epochs, mapping)
        except Exception:
            if not p.client:
                with s.db() as db:
                    db.execute("DELETE FROM central_member WHERE client=?", (c.id,))
                s.app.clients.update(c.id, status=ClientStatus.DISABLED, config=None)
                with s.app.clients.db.session() as session:
                    session.delete(c)
            else:
                s.app.clients.update(
                    c.id, status=ClientStatus(c.status), config=c.config
                )
            raise
        result = {"client": c.id}
        if p.train:
            result.update(
                s.queue(
                    mid,
                    dict(
                        action="local", base=m["head"], clients=[c.id], encrypted=False
                    ),
                )
            )
        return result


@router.post("/{mid}/rounds")
def rounds(mid: str, p: Round, s=Depends(service)):
    if p.encrypted and p.action != "fresh":
        raise InputValidationError("Select a fresh round for CKKS aggregation.")
    return s.queue(mid, p.model_dump())


@router.get("/{mid}/evaluations")
def evaluation_history(mid: str, s=Depends(service)):
    return version_evaluation.history(s, mid)


@router.post("/{mid}/versions/{vid}/evaluate-heldout")
def heldout(mid: str, vid: str, s=Depends(service)):
    try:
        return version_evaluation.evaluate(s, mid, vid)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise InputValidationError(f"Cannot evaluate saved artifacts: {exc}") from exc


@router.get("/{mid}/versions/{vid}/integrity")
def integrity(mid: str, vid: str, s=Depends(service)):
    v = s.row("SELECT * FROM central_version WHERE model=? AND version=?", (mid, vid))
    try:
        weights = s.weights(vid)  # loads the file and verifies its SHA-256
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise InputValidationError(f"Cannot verify saved artifact: {exc}") from exc
    return {
        "version": vid,
        "artifact_verified": True,
        "weight_matches": version_evaluation.weight_digest(weights) == v["digest"],
    }


@router.post("/{mid}/versions/{version}/{action}")
def version_action(
    mid: str,
    version: str,
    action: Literal["deploy", "rollback", "sync"],
    s=Depends(service),
):
    v = s.row(
        "SELECT * FROM central_version WHERE model=? AND version=?", (mid, version)
    )
    if v["state"] not in ("validated", "deployed"):
        raise ConflictError("Only validated, trained versions can be deployed.")
    with s.app.models.lock:
        if action == "sync":
            with s.db() as db:
                target = db.execute(
                    "SELECT owner FROM auto_sync_target WHERE version=?", (version,)
                ).fetchone()
            if not target:
                raise ConflictError("Deploy the version before synchronization.")
            s.app.automatic.synchronize(target[0])
        else:
            if action == "rollback" and v["state"] != "deployed":
                raise ConflictError("Rollback requires a previously deployed version.")
            s.app.models.deploy(version)
    return {"version": version, "action": action}
