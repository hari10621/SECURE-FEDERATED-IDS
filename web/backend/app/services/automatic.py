"""Persistent event review, automatic training reservations and deployment audit."""

import json
import logging
import math
import secrets
import threading
import time
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from ..domain.federated.client import weight_digest
from ..enums import ExperimentStatus
from ..errors import ConflictError, InputValidationError
from ..schemas import ExperimentCreate, TrainingRequest

log = logging.getLogger(__name__)


from .security_audit import audit

class Policy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    minimum: int = Field(default=3, ge=1, le=1000)
    minimum_new_samples: int = Field(default=1, ge=1, le=1000)
    minimum_clients: int = Field(default=2, ge=2, le=12)
    rounds: int = Field(default=1, ge=1, le=100)
    epochs: int = Field(default=1, ge=1, le=50)
    cooldown: int = Field(default=300, ge=0, le=604800)
    encrypted: bool = False
    auto_deploy: bool = False
    minimum_accuracy_gain: float = Field(default=0, ge=-1, le=1)
    minimum_f1: float = Field(default=0, ge=0, le=1)
    maximum_fpr: float = Field(default=1, ge=0, le=1)
    allowed_f1_drop: float = Field(default=0, ge=0, le=1)

    def accepts(self, before, after, old_hash, new_hash):
        return (
            old_hash != new_hash
            and after["f1"] >= self.minimum_f1
            and after["accuracy"] - before["accuracy"] >= self.minimum_accuracy_gain
            and after["f1"] + self.allowed_f1_drop >= before["f1"]
            and after["false_positive_rate"] <= self.maximum_fpr
        )


def notice(db, message):
    db.execute(
        "INSERT INTO auto_notice(ts,message) VALUES(?,?)", (time.time(), message)
    )


class AutomaticRetraining:
    def __init__(self, app):
        self.app = app
        self.db = app.sdn.db
        self.wake = threading.Event()
        self.stop = threading.Event()
        self.worker = threading.Thread(
            target=self.loop, daemon=True, name="reviewed-event-queue"
        )
        self.migrate()
        app.job_manager.register_handler("automatic_training", self.execute)

    def migrate(self):
        with self.db() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS security_audit(id TEXT PRIMARY KEY,ts REAL,category TEXT,severity TEXT,client TEXT,organization TEXT,version TEXT,job TEXT,event TEXT);
            CREATE INDEX IF NOT EXISTS audit_time ON security_audit(ts);
            CREATE TABLE IF NOT EXISTS auto_migrations(version INTEGER PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS auto_review_time(event TEXT PRIMARY KEY,ts REAL);
            CREATE TABLE IF NOT EXISTS auto_policy(id INTEGER PRIMARY KEY, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS auto_notice(id INTEGER PRIMARY KEY, ts REAL,message TEXT,seen INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS auto_event(
              id TEXT PRIMARY KEY,sample_key TEXT NOT NULL,client TEXT,organization TEXT,host TEXT,host_ip TEXT,
              src TEXT,dst TEXT,ts REAL,origin TEXT,source TEXT,row_index INTEGER,version TEXT,
              prediction INTEGER,probability REAL,label INTEGER,evidence TEXT,truth INTEGER,
              features TEXT,schema TEXT,status TEXT,run TEXT, UNIQUE(sample_key,client,version,origin));
            CREATE INDEX IF NOT EXISTS auto_pending ON auto_event(status,label,sample_key);
            CREATE TABLE IF NOT EXISTS auto_run(id TEXT PRIMARY KEY,ts REAL,state TEXT,policy TEXT,events TEXT,
              clients TEXT,parent TEXT,candidate TEXT,experiment TEXT,job TEXT,detail TEXT,validation TEXT,finished REAL);
            CREATE UNIQUE INDEX IF NOT EXISTS auto_one_active ON auto_run((1)) WHERE state IN ('queued','training','deploying');
            CREATE TABLE IF NOT EXISTS auto_ack(run TEXT,client TEXT,version TEXT,pid INTEGER,digest TEXT,ts REAL,
              PRIMARY KEY(run,client));
            """)
            if not db.execute(
                "SELECT 1 FROM auto_migrations WHERE version=1"
            ).fetchone():
                for row in db.execute(
                    "SELECT rowid,* FROM events ORDER BY rowid"
                ).fetchall():
                    r = json.loads(row["result"])
                    db.execute(
                        """INSERT OR IGNORE INTO auto_event(id,sample_key,client,host,ts,origin,version,prediction,probability,status)
                              VALUES(?,?,?,?,?,?,?,?,?,'historical')""",
                        (
                            uuid4().hex,
                            "legacy:" + str(row["rowid"]),
                            row["client"],
                            row["host"],
                            row["ts"],
                            row["kind"],
                            r.get("version"),
                            r.get("label"),
                            r.get("prediction"),
                        ),
                    )
                db.execute("INSERT INTO auto_migrations VALUES(1)")
            db.execute(
                "CREATE TABLE IF NOT EXISTS auto_sync_target(id INTEGER PRIMARY KEY,version TEXT,owner TEXT,clients TEXT,ts REAL)"
            )
            if not db.execute(
                "SELECT 1 FROM auto_migrations WHERE version=2"
            ).fetchone():
                db.execute(
                    "UPDATE auto_event SET origin='dataset replay' WHERE status='historical' AND origin='recorded dataset replay'"
                )
                db.execute(
                    "UPDATE auto_event SET origin='live traffic' WHERE status='historical' AND origin='live counters'"
                )
                db.execute("INSERT INTO auto_migrations VALUES(2)")
            db.execute(
                "INSERT OR IGNORE INTO auto_policy VALUES(1,?)",
                (Policy().model_dump_json(),),
            )
            for run in db.execute(
                "SELECT * FROM auto_run WHERE state IN ('queued','training','deploying')"
            ).fetchall():
                active = (
                    self.app.models.status().get("version")
                    if run["state"] == "deploying"
                    else None
                )
                deployed = bool(active and active == run["candidate"])
                self.finish(
                    db,
                    run["id"],
                    "deployed" if deployed else "failed",
                    "Recovered after coordinator restart",
                )

    def policy(self, db):
        return Policy.model_validate_json(
            db.execute("SELECT body FROM auto_policy WHERE id=1").fetchone()[0]
        )

    def record(
        self,
        db,
        *,
        client,
        origin,
        key,
        features,
        schema,
        result,
        host=None,
        host_ip=None,
        src=None,
        dst=None,
        source=None,
        row_index=None,
        truth=None,
    ):
        organization = (
            self.app.clients.get(client).config.get("organization", "")
            if client
            else None
        )
        version = (result or {}).get("version", "")
        old = db.execute(
            "SELECT id FROM auto_event WHERE sample_key=? AND client=? AND version=? AND origin=?",
            (key, client, version, origin),
        ).fetchone()
        if old:
            if host:
                db.execute(
                    "UPDATE auto_event SET host=COALESCE(host,?),host_ip=COALESCE(host_ip,?) WHERE id=? AND (host IS NULL OR host=?)",
                    (host, host_ip, old[0], host),
                )
            return old[0]
        eid = uuid4().hex
        prediction = (result or {}).get("label")
        db.execute(
            """INSERT INTO auto_event(id,sample_key,client,organization,host,host_ip,src,dst,ts,origin,source,row_index,
                    version,prediction,probability,truth,features,schema,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                eid,
                key,
                client,
                organization,
                host,
                host_ip,
                src,
                dst,
                time.time(),
                origin,
                source,
                row_index,
                version,
                prediction,
                (result or {}).get("prediction"),
                truth,
                json.dumps(features),
                json.dumps(schema),
                "ineligible"
                if origin == "manual input"
                else "held-out"
                if origin == "dataset evaluation"
                else "unreviewed",
            ),
        )
        if prediction is not None:
            category=("attack missed" if truth==1 and prediction==0 else "false positive" if truth==0 and prediction==1 else "attack detected" if prediction==1 else "sample scored")
            audit(db,category,client=client,organization=organization,version=version,event=eid,severity="warning" if category in ("false positive","attack missed") else "high" if prediction==1 else "info")
        if prediction == 1:
            notice(
                db, f"Intrusion detected · {organization or client} · {origin} · {eid}"
            )
        return eid

    def manual_detection(self, result):
        if result["label"]:
            with self.db() as db:
                self.record(
                    db,
                    client=None,
                    origin="manual input",
                    key=uuid4().hex,
                    features=None,
                    schema=None,
                    result=result,
                )

    def deployment(self, version):
        with self.db() as db:
            audit(db,"model deployed",version=version,event=version)
            notice(db, "Model deployed · " + version)
            r = db.execute(
                "SELECT id,state FROM auto_run WHERE candidate=?", (version,)
            ).fetchone()
            if r and r["state"] == "validated":
                self.finish(
                    db,
                    r["id"],
                    "deployed",
                    "Previously validated candidate deployed manually",
                )
            managed = db.execute(
                "SELECT model,state FROM central_version WHERE version=?", (version,)
            ).fetchone()
            if managed:
                if (
                    managed["state"] == "deployed"
                    and db.execute(
                        "SELECT head FROM central_model WHERE id=?", (managed["model"],)
                    ).fetchone()[0]
                    != version
                ):
                    notice(db, "Central model rollback · " + version)
                db.execute(
                    "UPDATE central_model SET head=? WHERE id=?",
                    (version, managed["model"]),
                )
                db.execute(
                    "UPDATE central_version SET state='deployed' WHERE version=?",
                    (version,),
                )
                db.execute(
                    "UPDATE central_update SET state='stale',body=NULL WHERE model=? AND base<>? AND state='ready'",
                    (managed["model"], version),
                )
            if (
                managed
                or r
                or db.execute("SELECT 1 FROM auto_sync_target WHERE id=1").fetchone()
                or db.execute(
                    "SELECT 1 FROM auto_run WHERE state='deployed' LIMIT 1"
                ).fetchone()
            ):
                manifest = json.loads(self.app.models.active.read_bytes())
                owner = r["id"] if r else "restore:" + version
                clients = manifest.get("participants", [])
                db.execute(
                    "INSERT OR REPLACE INTO auto_sync_target VALUES(1,?,?,?,?)",
                    (version, owner, json.dumps(clients), time.time()),
                )
        self.wake.set()

    def review(self, eid, label, evidence):
        evidence = evidence.strip()
        if not evidence:
            raise InputValidationError("Record the independent source of the label.")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM auto_event WHERE id=?", (eid,)).fetchone()
            if not row or row["status"] not in ("unreviewed", "verified", "held-out"):
                raise ConflictError("This sample cannot be edited.")
            if row["truth"] is not None and row["truth"] != label:
                raise InputValidationError(
                    "Label differs from the independently stored CSV annotation."
                )
            if row["origin"] == "live traffic":
                db.execute(
                    "UPDATE samples SET label=? WHERE id=?", (label, row["source"])
                )
            status = "held-out" if row["origin"] == "dataset evaluation" else "verified"
            if row["label"] == label and row["evidence"] == evidence:
                return
            db.execute(
                "UPDATE auto_event SET label=?, evidence=?, status=? WHERE id=?",
                (label, evidence, status, eid),
            )
            db.execute("INSERT OR REPLACE INTO auto_review_time VALUES(?,?)",(eid,time.time()))
            audit(db,"sample verified",client=row["client"],organization=row["organization"],version=row["version"],event=eid)
            notice(db, f"Sample verified · {eid} · {'Attack' if label else 'Benign'}")
        self.wake.set()

    def finish(self, db, rid, state, detail):
        db.execute(
            "UPDATE auto_run SET state=?,detail=?,finished=? WHERE id=?",
            (state, detail, time.time(), rid),
        )
        db.execute("UPDATE auto_event SET status=? WHERE run=?", (state, rid))
        if state=="failed":
            run=db.execute("SELECT parent,job FROM auto_run WHERE id=?",(rid,)).fetchone()
            audit(db,"retraining failed",version=run["parent"],job=run["job"],event=rid,severity="warning")
        notice(db, f"Automatic retraining {state} · {rid} · {detail}")

    def loop(self):
        while not self.stop.is_set():
            self.wake.wait(3)
            self.wake.clear()
            if self.stop.is_set():
                break
            try:
                self.tick()
                self.reconcile_workers()
            except Exception:
                log.exception("Automatic queue check failed")

    def reconcile_workers(self):
        with self.db() as db:
            target = db.execute("SELECT * FROM auto_sync_target WHERE id=1").fetchone()
            if not target:
                return
            acknowledged = dict(
                db.execute(
                    "SELECT client,pid FROM auto_ack WHERE run=? AND ts>=?",
                    (target["owner"], target["ts"]),
                )
            )
        for cid in json.loads(target["clients"]):
            pid = self.app.clients.pid(cid)
            if pid and acknowledged.get(cid) != pid:
                self.synchronize(target["owner"])
                return

    def tick(self):
        with self.db() as db:
            queued = db.execute(
                "SELECT id,job FROM auto_run WHERE state='queued' AND job IS NOT NULL"
            ).fetchone()
            if queued and self.app.jobs.get(queued["job"]).status in (
                "failed",
                "cancelled",
            ):
                self.finish(
                    db,
                    queued["id"],
                    "failed",
                    "Queued job stopped before training began.",
                )
            pol = self.policy(db)
            if not pol.enabled:
                return
            if not db.execute(
                "SELECT 1 FROM auto_event WHERE status='verified' AND label=1 LIMIT 1"
            ).fetchone():
                return
            if db.execute(
                "SELECT 1 FROM auto_run WHERE state IN ('queued','training','deploying') OR finished>?",
                (time.time() - pol.cooldown,),
            ).fetchone():
                return
        model = self.app.models.status()
        if not model.get("available"):
            return
        manifest, (_, weights, prep, _) = self.app.models.current()
        if manifest["version"] != model["version"]:
            return
        source_sha = weights["metadata"]["dataset_sha256"]
        train_indices = set(prep["prepared"]["split"]["train"])
        rows, _ = self.app.clients.list(limit=10000)
        online = [r.id for r in rows if self.app.clients.pid(r.id)]
        managed = manifest.get("central_model")
        if managed:
            with self.db() as db:
                members = {
                    r[0]
                    for r in db.execute(
                        "SELECT client FROM central_member WHERE model=?", (managed,)
                    )
                }
            online = [cid for cid in online if cid in members]
        if len(online) < pol.minimum_clients:
            return
        held_out = set()
        if managed:
            _, raw, reference = self.app.central.reference(managed)
            held_out = {tuple(raw.rows[idx]) for idx in reference.split.test}
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if self.policy(db) != pol:
                return
            if db.execute(
                "SELECT 1 FROM auto_run WHERE state IN ('queued','training','deploying') OR finished>?",
                (time.time() - pol.cooldown,),
            ).fetchone():
                return
            candidates = db.execute("""SELECT * FROM auto_event e WHERE status='verified' AND label=1
              AND NOT EXISTS(SELECT 1 FROM auto_event used WHERE used.sample_key=e.sample_key AND used.run IS NOT NULL)
              ORDER BY ts,id""").fetchall()
            events = []
            keys = set()
            ids = []
            for e in candidates:
                try:
                    vector = json.loads(e["features"] or "null")
                    schema = json.loads(e["schema"] or "null")
                except (TypeError, ValueError):
                    continue
                if not isinstance(vector,list) or len(vector)!=len(model["features"]) or not all(type(v) in (int,float) and math.isfinite(v) for v in vector):
                    continue
                if tuple(vector) in held_out:
                    continue
                if e["origin"] in ("simulation window","capture window"):
                    engine=e["origin"].split()[0]
                    if not managed or not db.execute(
                        "SELECT 1 FROM native_dataset WHERE dataset=? AND engine=?", (prep["dataset_id"],engine)
                    ).fetchone():
                        continue
                if (
                    e["sample_key"] in keys
                    or e["client"] not in online
                    or schema != model["features"]
                ):
                    continue
                if e["origin"] == "dataset training" and (
                    e["source"] != source_sha or e["row_index"] not in train_indices
                ):
                    continue
                if e["client"] not in ids:
                    if len(ids) == 12:
                        continue
                    ids.append(e["client"])
                events.append(e["id"])
                keys.add(e["sample_key"])
                if len(events) >= max(pol.minimum,pol.minimum_new_samples):
                    break
            if len(events) < max(pol.minimum,pol.minimum_new_samples):
                return
            # Published live datasets retain their original worker ownership.
            owners = db.execute(
                "SELECT owners FROM published WHERE dataset=?", (model["dataset_id"],)
            ).fetchone()
            if owners:
                required = set(json.loads(owners[0]))
                if len(required)<pol.minimum_clients or not required.issubset(online) or not set(ids).issubset(required):
                    return
                ids = sorted(required)
            else:
                count = next(
                    (n for n in (2, 3, 4, 8, 12) if n >= max(len(ids),pol.minimum_clients) and n <= len(online)),
                    None,
                )
                if count is None:
                    return
                ids = (ids + [cid for cid in online if cid not in ids])[:count]
            rid = uuid4().hex
            db.execute(
                "INSERT INTO auto_run(id,ts,state,policy,events,clients,parent) VALUES(?,?,'queued',?,?,?,?)",
                (
                    rid,
                    time.time(),
                    pol.model_dump_json(),
                    json.dumps(events),
                    json.dumps(ids),
                    model["version"],
                ),
            )
            db.executemany(
                "UPDATE auto_event SET run=?,status='queued' WHERE id=?",
                [(rid, e) for e in events],
            )
            for eid in events:
                selected=db.execute("SELECT * FROM auto_event WHERE id=?",(eid,)).fetchone()
                for category in ("sample assigned for training","retraining triggered"):
                    audit(db,category,client=selected["client"],organization=selected["organization"],version=model["version"],event=eid)
            notice(db, f"Retraining queued · {len(events)} verified attacks · {rid}")
        try:
            job = self.app.job_manager.submit(
                "automatic_training", dedupe_key="auto:" + rid, payload={"run": rid}
            )
            with self.db() as db:
                db.execute("UPDATE auto_run SET job=? WHERE id=?", (job.id, rid))
        except Exception as exc:
            with self.db() as db:
                self.finish(db, rid, "failed", str(exc))
            raise

    def deployable(self, version):
        with self.db() as db:
            r = db.execute(
                "SELECT state FROM auto_run WHERE candidate=?", (version,)
            ).fetchone()
            return r is not None and r[0] in ("validated", "deploying", "deployed")

    def execute(self, ctx, payload):
        rid = payload["run"]
        exp = None
        try:
            with self.db() as db:
                r = dict(
                    db.execute("SELECT * FROM auto_run WHERE id=?", (rid,)).fetchone()
                )
                events = [
                    dict(e)
                    for e in db.execute(
                        "SELECT * FROM auto_event WHERE run=? ORDER BY ts", (rid,)
                    )
                ]
                db.execute(
                    "UPDATE auto_run SET state='training',job=? WHERE id=?",
                    (ctx.job_id, rid),
                )
                db.execute(
                    "UPDATE auto_event SET status='training' WHERE run=?", (rid,)
                )
                notice(db, "Training started · " + rid)
            pol = Policy.model_validate_json(r["policy"])
            ids = json.loads(r["clients"])
            m, (_, weights, prep, _) = self.app.models.current()
            if m["version"] != r["parent"]:
                raise ConflictError("The deployed model changed before training.")
            source = self.app.datasets.source_id(
                prep["dataset_id"], weights["metadata"]["dataset_sha256"]
            )
            exp = self.app.experiments.create(
                ExperimentCreate(
                    name="Automatic " + rid[:10],
                    dataset_id=source,
                    client_count=len(ids),
                    config={
                        "trigger": "automatic",
                        "run": rid,
                        "events": json.loads(r["events"]),
                    },
                )
            )
            with self.db() as db:
                db.execute("UPDATE auto_run SET experiment=? WHERE id=?", (exp.id, rid))
            self.app.jobs.attach_experiment(ctx.job_id, exp.id)
            self.app.experiments.set_state(
                exp.id, status=ExperimentStatus.RUNNING, started=True, job_id=ctx.job_id
            )
            if pol.encrypted and not self.app.encryption.is_available():
                raise ConflictError("CKKS unavailable; encrypted run stopped.")
            req = TrainingRequest(
                client_ids=ids,
                rounds=pol.rounds,
                local_epochs=pol.epochs,
                max_rows=sum(
                    len(indices) for indices in prep["prepared"]["split"].values()
                ),
                mode="clean",
                seed=prep["prepared"]["seed"],
                test_size=prep["prepared"]["test_size"],
                require_encryption=pol.encrypted,
                initialize_from_active=True,
                auto_deploy=False,
            )
            for e in events:
                e["features"] = json.loads(e["features"])
                e["schema"] = json.loads(e["schema"])
            if m.get("central_model"):
                result = self.app.central.aggregate(
                    ctx,
                    dict(
                        model=m["central_model"],
                        base=r["parent"],
                        clients=ids,
                        action="fresh",
                        encrypted=pol.encrypted,
                        policy=pol.model_dump(),
                    ),
                    exp,
                    events,
                    pol.rounds,
                    pol.epochs,
                )
            else:
                result = self.app.training.execute(
                    exp, req, ctx, automatic={"parent": r["parent"], "events": events}
                )
            candidate = result["artifact"]["version"]
            before = result["baseline_metrics"]
            after = result["final_metrics"]
            oldhash = weight_digest(weights["weights"])
            registered = json.loads(
                (self.app.models.registry / (candidate + ".json")).read_bytes()
            )
            bundle = self.app.models.artifact(
                registered["model_path"], registered["sha256"]
            )
            newhash = weight_digest(bundle["weights"])
            passed = all(
                not rnd["aborted"] for rnd in result["rounds"]
            ) and pol.accepts(before, after, oldhash, newhash)
            validation = {
                "before": before,
                "after": after,
                "hash_before": oldhash,
                "hash_after": newhash,
                "passed": passed,
                "test_rows": len(prep["prepared"]["split"]["test"]),
                "source_sha256": weights["metadata"]["dataset_sha256"],
            }
            result.update(
                trigger="automatic",
                events=json.loads(r["events"]),
                validation=validation,
            )
            with self.db() as db:
                db.execute(
                    "UPDATE auto_run SET candidate=?,validation=? WHERE id=?",
                    (candidate, json.dumps(validation), rid),
                )
                notice(db, "Aggregation completed · " + candidate)
                notice(
                    db,
                    ("Validation passed · " if passed else "Validation failed · ")
                    + candidate,
                )
            self.app.experiments.set_state(
                exp.id, status=ExperimentStatus.SUCCEEDED, finished=True, result=result
            )
            if not passed or not pol.auto_deploy:
                with self.db() as db:
                    self.finish(
                        db,
                        rid,
                        "validated" if passed else "rejected",
                        "Candidate staged for review"
                        if passed
                        else "Candidate did not meet validation requirements",
                    )
                return validation
            with self.app.models.lock:
                if self.app.models.status().get("version") != r["parent"]:
                    raise ConflictError("Deployment changed during validation.")
                with self.db() as db:
                    latest = self.policy(db)
                    if latest != pol:
                        self.finish(
                            db,
                            rid,
                            "validated",
                            "Policy changed during training; candidate staged",
                        )
                        return validation
                    db.execute(
                        "UPDATE auto_run SET state='deploying' WHERE id=?", (rid,)
                    )
                self.app.models.deploy(candidate)
                with self.db() as db:
                    self.finish(db, rid, "deployed", "Model deployed · " + candidate)
                try:
                    self.synchronize(rid)
                except Exception:
                    log.exception("Deployed model is awaiting worker acknowledgement")
            return validation
        except Exception as exc:
            with self.db() as db:
                if (
                    db.execute(
                        "SELECT state FROM auto_run WHERE id=?", (rid,)
                    ).fetchone()[0]
                    != "deployed"
                ):
                    self.finish(db, rid, "failed", str(exc))
            if exp and self.app.experiments.get(exp.id).status == "running":
                self.app.experiments.set_state(
                    exp.id,
                    status=ExperimentStatus.FAILED,
                    finished=True,
                    error=str(exc),
                )
            raise

    def synchronize(self, rid):
        with self.app.models.lock, self.db() as db:
            target = db.execute(
                "SELECT * FROM auto_sync_target WHERE id=1 AND owner=?", (rid,)
            ).fetchone()
            if not target:
                raise ConflictError(
                    "This version is no longer the synchronization target."
                )
            m, (_, w, _, _) = self.app.models.current()
            if m["version"] != target["version"]:
                raise ConflictError("The synchronization target is no longer deployed.")
            digest = weight_digest(w["weights"])
            for cid in json.loads(target["clients"]):
                pid = self.app.clients.pid(cid)
                if not pid:
                    continue
                if db.execute(
                    "SELECT 1 FROM auto_ack WHERE run=? AND client=? AND pid=? AND ts>=?",
                    (rid, cid, pid, target["ts"]),
                ).fetchone():
                    continue
                with self.app.clients.lock:
                    worker = self.app.clients.workers.get(cid)
                    if not worker:
                        continue
                    token = secrets.token_hex(24)
                    ack = worker.exchange(
                        {
                            "action": "sync",
                            "client": {"client_id": cid},
                            "version": m["version"],
                            "weights": w["weights"],
                            "token": token,
                        }
                    )
                if (
                    ack["digest"],
                    ack["version"],
                    ack["client_id"],
                    ack["pid"],
                    ack["token"],
                ) != (digest, m["version"], cid, pid, token):
                    raise ConflictError("Worker acknowledgement mismatch.")
                db.execute(
                    "INSERT OR REPLACE INTO auto_ack VALUES(?,?,?,?,?,?)",
                    (rid, cid, m["version"], pid, digest, time.time()),
                )
                audit(db,"worker synchronized",client=cid,organization=self.app.clients.get(cid).config.get("organization"),version=m["version"],event=rid)
                notice(db, f"Client synchronized · {cid} · {m['version']}")
                db.commit()
