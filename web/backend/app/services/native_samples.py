"""Distinct, ordered 12-observation schemas for native simulation and passive capture."""

import csv
import hashlib
import io
import json
import time
from uuid import uuid4

from starlette.datastructures import UploadFile
from ..enums import DatasetType
from ..errors import AppError, ConflictError, InputValidationError

FIELDS = {
    "simulation": (
        "frame_bytes",
        "switch_hops",
        "seconds_since_previous",
        "seconds_since_first",
    ),
    "capture": (
        "frame_bytes",
        "ip_protocol_number",
        "seconds_since_previous",
        "seconds_since_first",
    ),
}


def schema(engine):
    return [
        f"{engine}_v1_{index:02}_{field}"
        for index in range(1, 13)
        for field in FIELDS[engine]
    ]


def vector(observations):
    # 13 observed frames supply 12 measured interarrival intervals.
    start = observations[0][0]
    return [
        value
        for prev, now in zip(observations, observations[1:])
        for value in (now[1], now[2], max(0, now[0] - prev[0]), max(0, now[0] - start))
    ]


def current_ack(db, client, version, pid):
    return db.execute(
        """SELECT a.digest FROM auto_ack a JOIN auto_sync_target t
      ON t.version=a.version AND t.owner=a.run AND a.ts>=t.ts
      WHERE a.client=? AND a.version=? AND a.pid=? ORDER BY a.ts DESC LIMIT 1""",
        (client, version, pid),
    ).fetchone()


def record(app, db, engine, owner, scope, features, host=None):
    sid = uuid4().hex
    names = schema(engine)
    eid = None
    outcome = "Incompatible model"
    model_version = None
    reason = (
        "Train and deploy a model on a reviewed dataset with this observation schema."
    )
    try:
        manifest, (_, weights, prep, _) = app.models.current()
        model_version = manifest["version"]
        registered = db.execute(
            "SELECT 1 FROM native_dataset WHERE dataset=? AND engine=?",
            (prep["dataset_id"], engine),
        ).fetchone()
        if prep["feature_names"] == names and registered:
            receipt = current_ack(db, owner, model_version, app.clients.pid(owner))
            if not receipt:
                raise ConflictError("A synchronized worker is required.")
            start = time.perf_counter()
            delivered = app.clients.replay(owner, features)
            pred = app.models.predict(delivered["features"])
            if pred["version"] != model_version:
                raise ConflictError("Deployment changed.")
            eid = app.automatic.record(
                db,
                client=owner,
                origin=engine + " window",
                key=hashlib.sha256(json.dumps(features).encode()).hexdigest(),
                features=features,
                schema=names,
                result=pred,
                source=sid,
                host=host,
            )
            outcome = "Unknown ground truth"
            reason = json.dumps(
                dict(
                    prediction=pred["label"],
                    probability=pred["prediction"],
                    weight_hash=receipt[0],
                    duration_ms=(time.perf_counter() - start) * 1000,
                )
            )
    except AppError as exc:
        reason = str(exc)
    db.execute(
        "INSERT INTO native_sample VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            sid,
            engine,
            scope,
            owner,
            time.time(),
            json.dumps(features),
            None,
            None,
            eid,
            outcome,
            reason,
            model_version,
            host,
        ),
    )
    return sid


def review(app, sid, label, evidence):
    if not evidence.strip():
        raise InputValidationError("Independent evidence is required.")
    with app.sdn.db() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM native_sample WHERE id=?", (sid,)).fetchone()
        if not row:
            raise ConflictError("Unknown sample.")
        if row["label"] is not None:
            if row["label"] == label and row["evidence"] == evidence:
                return {"id": sid}
            raise ConflictError("This sample already has a recorded review.")
        if row["event"]:
            # The standard reviewer handles eligibility and notification; keep its
            # label and this sample receipt together in one SQLite transaction.
            ev = db.execute(
                "SELECT status FROM auto_event WHERE id=?", (row["event"],)
            ).fetchone()
            if ev["status"] != "unreviewed":
                raise ConflictError("Review this linked event in Security Monitoring.")
            db.execute(
                "UPDATE auto_event SET label=?,evidence=?,status='verified' WHERE id=?",
                (label, evidence, row["event"]),
            )
            db.execute(
                "INSERT OR REPLACE INTO auto_review_time VALUES(?,?)",
                (row["event"], time.time()),
            )
        db.execute(
            "UPDATE native_sample SET label=?,evidence=? WHERE id=?",
            (label, evidence, sid),
        )
        from .automatic import notice

        from .security_audit import audit
        audit(db,"sample verified",client=row["client"],organization=app.clients.get(row["client"]).config.get("organization"),version=row["version"],event=row["event"] or sid)
        notice(db, "Sample verified · " + (row["event"] or sid))
    app.automatic.wake.set()
    return {"id": sid}


async def publish(app, engine, scope):
    with app.sdn.db() as db:
        rows = db.execute(
            """SELECT s.*,CASE WHEN s.event IS NULL THEN s.label ELSE e.label END AS reviewed FROM native_sample s LEFT JOIN auto_event e
          ON s.event=e.id WHERE s.engine=? AND (s.scope=? OR ?='all-reviewed') AND (e.status IS NULL OR e.status != 'excluded') AND (CASE WHEN s.event IS NULL THEN s.label ELSE e.label END) IS NOT NULL ORDER BY s.ts,s.id""",
            (engine, scope,scope),
        ).fetchall()
    # Conflicting duplicate feature vectors cannot be assigned ground truth.
    unique = {}
    for r in rows:
        if r["features"] in unique and unique[r["features"]]["client"]!=r["client"]:
            raise ConflictError("Identical observations have conflicting worker ownership.")
        if (
            r["features"] in unique
            and unique[r["features"]]["reviewed"] != r["reviewed"]
        ):
            raise ConflictError("Conflicting labels for identical observations.")
        unique[r["features"]] = r
    rows = list(unique.values())
    labels = [r["reviewed"] for r in rows]
    if min(labels.count(0), labels.count(1)) < 2:
        raise ConflictError("Review at least two distinct samples from each class.")
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow([*schema(engine), "Label"])
    for r in rows:
        writer.writerow([*json.loads(r["features"]), r["reviewed"]])
    dataset = await app.datasets.save_upload(
        UploadFile(
            filename=engine + "-windows.csv",
            file=io.BytesIO(stream.getvalue().encode()),
        ),
        dataset_type=DatasetType.INSDN,
        name=engine + " reviewed windows",
        label_column="Label",
    )
    with app.sdn.db() as db:
        db.execute(
            "INSERT OR IGNORE INTO native_dataset VALUES(?,?,?)",
            (dataset.id, engine, scope),
        )
        db.execute(
            "INSERT OR IGNORE INTO published VALUES(?,?,?)",
            (dataset.id, scope, json.dumps([r["client"] for r in rows])),
        )
        db.executemany("INSERT OR IGNORE INTO native_dataset_row VALUES(?,?,?)",
                       ((dataset.id,index,r["id"]) for index,r in enumerate(rows)))
    return {"dataset": dataset.id, "rows": len(rows)}
