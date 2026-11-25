"""Authenticated read-only controller telemetry and bounded VM lab operations."""

import http.client
import json
import math
import os
import sqlite3
import time
from pathlib import Path
from uuid import uuid4

from ..errors import ConflictError, InputValidationError, UnavailableError

FEATURES = [
    f"interval_{i:02}_{field}_per_second"
    for i in range(1, 13)
    for field in ("tx_packets", "rx_packets", "tx_bytes", "rx_bytes")
]


def reviewed_owners(data_dir, dataset_id):
    path = data_dir / "sdn.sqlite3"
    if not path.is_file():
        return None
    with sqlite3.connect(path) as db:
        row = db.execute(
            "SELECT owners FROM published WHERE dataset=?", (dataset_id,)
        ).fetchone()
    return json.loads(row[0]) if row else None


class SDNService:
    def __init__(self, paths):
        self.file = paths.data_dir / "sdn.sqlite3"
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS mapping(lab TEXT,host TEXT,client TEXT,PRIMARY KEY(lab,host), UNIQUE(lab,client));
                CREATE TABLE IF NOT EXISTS samples(id TEXT PRIMARY KEY,lab TEXT,host TEXT,client TEXT,
                    ts REAL,features TEXT,label INTEGER,prediction TEXT);
                CREATE TABLE IF NOT EXISTS published(dataset TEXT PRIMARY KEY,lab TEXT,owners TEXT);
                CREATE TABLE IF NOT EXISTS events(lab TEXT,host TEXT,client TEXT,ts REAL,kind TEXT,result TEXT);
            """)

    def db(self):
        db = sqlite3.connect(self.file)
        db.row_factory = sqlite3.Row
        return db

    def call(self, action, payload=None):
        token = os.getenv("SECUREFED_LAB_TOKEN")
        if not token:
            raise UnavailableError(
                "Ubuntu lab agent is unconfigured. Set SECUREFED_LAB_TOKEN and open the VM tunnel."
            )
        try:
            timeout = float(os.getenv("SECUREFED_LAB_TIMEOUT", "20"))
            conn = http.client.HTTPConnection(
                "127.0.0.1",
                int(os.getenv("SECUREFED_LAB_PORT", "8765")),
                timeout=timeout,
            )
            try:
                conn.request(
                    "POST",
                    "/" + action,
                    json.dumps(payload or {}),
                    {
                        "Authorization": "Bearer " + token,
                        "Content-Type": "application/json",
                    },
                )
                response = conn.getresponse()
                if response.status == 403:
                    raise UnavailableError("Ubuntu lab authentication failed.")
                data = json.loads(response.read(4_000_000))
                if response.status != 200:
                    raise ConflictError(data.get("error", "Lab operation failed."))
                return data
            finally:
                conn.close()
        except (OSError, ValueError, http.client.HTTPException) as exc:
            raise UnavailableError(
                "Ubuntu lab agent unreachable or invalid response. Check the tunnel, port and timeout."
            ) from exc

    def snapshot(self):
        try:
            data = self.call("snapshot")
            if data.get("protocol") != "securefed-lab-v1":
                raise UnavailableError("Unrecognized lab agent.")
        except (UnavailableError, ConflictError) as exc:
            return dict(
                state="unavailable",
                reason=str(exc),
                running=False,
                config=None,
                lab_id=None,
                switches=[],
                hosts=[],
                links=[],
                flows=[],
                history=[],
                packets=None,
                events=[],
            )
        with self.db() as db:
            rows = db.execute(
                "SELECT host,client FROM mapping WHERE lab=?", (data["lab_id"],)
            )
            mappings = {r["host"]: r["client"] for r in rows}
            events = db.execute(
                "SELECT * FROM events WHERE lab=? ORDER BY ts DESC LIMIT 100",
                (data["lab_id"],),
            )
            data["events"] = [
                {**dict(r), "result": json.loads(r["result"])} for r in events
            ]
            counts = dict(
                db.execute(
                    "SELECT host,count(*) FROM events WHERE lab=? AND json_extract(result,'$.label')=1 GROUP BY host",
                    (data["lab_id"],),
                )
            )
            for h in data["hosts"]:
                cid=mappings.get(h["name"])
                if cid and hasattr(self,"automatic"):
                    with self.automatic.app.clients.db.session() as session:
                        from ..models import Client
                        worker=session.get(Client,cid)
                        h["organization"]=worker.config.get("organization","") if worker else ""
                    latest=db.execute("SELECT status FROM auto_event WHERE client=? AND host=? ORDER BY ts DESC LIMIT 1",(cid,h["name"])).fetchone()
                    h["retraining"]=latest[0] if latest else None
                h.update(
                    client=mappings.get(h["name"]), alerts=counts.get(h["name"], 0)
                )
        return data

    def status(self):
        s = self.snapshot()
        return dict(
            available=s["state"] == "connected",
            state=s["state"],
            reason=s["reason"],
            mode="openflow13",
        )

    def event(self, lab, host, client, kind, result):
        with self.db() as db:
            db.execute(
                "INSERT INTO events VALUES (?,?,?,?,?,?)",
                (lab, host, client, time.time(), kind, json.dumps(result)),
            )

    def host(self, name):
        snap = self.snapshot()
        for host in snap["hosts"]:
            if (
                host["name"] == name
                and host["connected"]
                and snap["state"] == "connected"
            ):
                return snap["lab_id"], host
        raise ConflictError("Choose a connected host on a verified lab controller.")

    def map(self, host, client):
        lab, _ = self.host(host)
        with self.db() as db:
            self.bind(db, lab, host, client, replace=True)

    def bind(self, db, lab, host, client, *, replace=False):
        previous=db.execute("SELECT client FROM mapping WHERE lab=? AND host=?",(lab,host)).fetchone()
        if previous and previous[0]!=client and not replace:
            raise ConflictError("This SDN host is already mapped.")
        try:
            db.execute("INSERT INTO mapping VALUES (?,?,?) ON CONFLICT(lab,host) DO UPDATE SET client=excluded.client",(lab,host,client))
        except sqlite3.IntegrityError as exc:
            raise ConflictError("This client is already mapped to another host.") from exc

    def capture(self, host, models, normal_probe=False):
        lab, h = self.host(host)
        if not h["client"]:
            raise ConflictError("Map a client before collecting its training samples.")
        raw = self.call(
            "capture", {"host": host, "lab_id": lab, "normal_probe": normal_probe}
        )
        features = raw["features"]
        if len(features) != len(FEATURES) or not all(
            type(x) in (float, int) and math.isfinite(x) and x >= 0 for x in features
        ):
            raise UnavailableError(
                "The host returned an incomplete or invalid counter window."
            )
        prediction = None
        status = models.status()
        if status.get("available") and status.get("features") == FEATURES:
            prediction = models.predict(features)
            if prediction["version"] != status["version"]:
                raise ConflictError("Model changed during capture; capture again.")
            self.event(lab, host, h["client"], "live counters", prediction)
        identifier = uuid4().hex
        with self.db() as db:
            db.execute(
                "INSERT INTO samples VALUES(?,?,?,?,?,?,NULL,?)",
                (
                    identifier,
                    lab,
                    host,
                    h["client"],
                    time.time(),
                    json.dumps(features),
                    json.dumps(prediction),
                ),
            )
            flows = raw["observed_flows"]
            sources = {f["source"] for f in flows}
            destinations = {f["destination"] for f in flows}
            self.automatic.record(db,client=h["client"],origin="live traffic",key=identifier,
                features=features,schema=FEATURES,result=prediction,host=host,host_ip=h.get("ip"),
                source=identifier,src=", ".join(sorted(sources)) or None,
                dst=", ".join(sorted(destinations)) or None)
        return dict(
            id=identifier,
            features=features,
            prediction=prediction,
            client=h["client"],
            observed_flows=raw["observed_flows"],
        )
