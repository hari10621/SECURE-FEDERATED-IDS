"""Persistent virtual topology and event forwarding. No network sockets are used."""

from collections import deque
from ipaddress import ip_network
import json
import time
from uuid import uuid4

from ..errors import AppError, ConflictError, InputValidationError
from .automatic import notice
from . import native_samples
from .security_audit import audit

# Logical frame sizes in the simulator, not captured wire measurements.
SCENARIOS = {
    "Normal ICMP": 84,
    "Normal TCP": 120,
    "Normal UDP": 96,
    "Normal HTTP": 512,
    "Port scanning simulation": 64,
    "SYN flood simulation": 64,
    "UDP flood simulation": 128,
    "ICMP flood simulation": 84,
    "Brute-force login simulation": 256,
    "Suspicious traffic simulation": 192,
}
REPLAY = "Labelled dataset replay"
SCHEMA = "securefed.virtual.frame.v1"


def route(graph, source, dest):
    nodes = graph["nodes"]
    if source == dest or any(
        n not in nodes or nodes[n]["kind"] != "host" for n in (source, dest)
    ):
        raise InputValidationError("Choose two distinct virtual hosts.")
    paths = deque([[source]])
    visited = {source}
    while paths:
        path = paths.popleft()
        for a, b in graph["links"]:
            other = b if a == path[-1] else a if b == path[-1] else None
            if other == dest:
                return [*path, dest]
            if other and other not in visited and nodes[other]["kind"] == "switch":
                visited.add(other)
                paths.append([*path, other])
    raise ConflictError("No forwarding path connects these virtual hosts.")


def add_node(graph, kind):
    key = "h" if kind == "host" else "s"
    nodes = graph["nodes"]
    if sum(n["kind"] == kind for n in nodes.values()) >= (32 if kind == "host" else 8):
        raise InputValidationError("Topology size limit reached.")
    graph["sequence"][key] += 1
    number = graph["sequence"][key]
    name = f"{key}{number}"
    node = {"kind": kind, "name": name, "client": None}
    if kind == "host":
        occupied = {n.get("ip") for n in nodes.values()}
        addr = next(
            (
                str(ip)
                for ip in ip_network(graph["subnet"]).hosts()
                if str(ip) not in occupied
            ),
            None,
        )
        if not addr:
            raise InputValidationError("Subnet has no available host addresses.")
        node.update(
            ip=addr,
            mac="02:00:" + ":".join(f"{b:02x}" for b in number.to_bytes(4, "big")),
        )
    nodes[name] = node
    return name


class NativeNetwork:
    def __init__(self, app):
        self.app = app
        self.db = app.sdn.db
        with self.db() as db:
            db.executescript("""
              CREATE TABLE IF NOT EXISTS native_comparison(id TEXT PRIMARY KEY,frame TEXT,baseline TEXT,candidate TEXT,ts REAL,scores TEXT);
              CREATE TABLE IF NOT EXISTS native_inspection(frame TEXT PRIMARY KEY,ts REAL);
              CREATE TABLE IF NOT EXISTS native_dataset(dataset TEXT PRIMARY KEY,engine TEXT,scope TEXT);
              CREATE TABLE IF NOT EXISTS native_dataset_row(dataset TEXT,ordinal INTEGER,sample TEXT,PRIMARY KEY(dataset,ordinal));
              CREATE TABLE IF NOT EXISTS native_sample(id TEXT PRIMARY KEY,engine TEXT,scope TEXT,client TEXT,ts REAL,features TEXT,label INTEGER,evidence TEXT,event TEXT,outcome TEXT,reason TEXT,version TEXT,host TEXT);
              CREATE INDEX IF NOT EXISTS native_sample_scope ON native_sample(scope,ts);
              CREATE TABLE IF NOT EXISTS native_network(id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS native_frame(id TEXT PRIMARY KEY,network TEXT,job TEXT,ts REAL,src TEXT,dst TEXT,
                scenario TEXT,bytes INTEGER,path TEXT,event TEXT,details TEXT);
              CREATE INDEX IF NOT EXISTS native_frame_network ON native_frame(network,ts);
              CREATE TABLE IF NOT EXISTS native_job(id TEXT PRIMARY KEY,network TEXT,engine TEXT,ts REAL);
              CREATE TABLE IF NOT EXISTS capture_flow(job TEXT,src TEXT,dst TEXT,protocol TEXT,packets INTEGER,bytes INTEGER,
                PRIMARY KEY(job,src,dst,protocol));
            """)
        app.job_manager.register_handler("native_traffic", self.traffic)

    def load(self, db):
        row = db.execute("SELECT body FROM native_network WHERE id=1").fetchone()
        if not row:
            raise ConflictError("Create a virtual network first.")
        return json.loads(row[0])

    def change(self, op, p):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if op == "create":
                if db.execute("SELECT 1 FROM native_network").fetchone():
                    raise ConflictError("A virtual network already exists.")
                try:
                    net = ip_network(p.subnet)
                except ValueError as exc:
                    raise InputValidationError("Enter an aligned IPv4 subnet.") from exc
                if net.version != 4:
                    raise InputValidationError("Choose an IPv4 subnet.")
                g = dict(
                    id=uuid4().hex,
                    subnet=str(net),
                    state="stopped",
                    topology=p.topology,
                    nodes={},
                    links=[],
                    sequence={"h": 0, "s": 0},
                )
                switches = [
                    add_node(g, "switch")
                    for _ in range(1 if p.topology == "single" else p.switches)
                ]
                for i, s in enumerate(switches[1:], 1):
                    parent = (
                        (i - 1) // 2
                        if p.topology == "tree"
                        else 0
                        if p.topology == "star"
                        else i - 1
                    )
                    if p.topology != "custom":
                        g["links"].append([switches[parent], s])
                for i in range(p.hosts):
                    h = add_node(g, "host")
                    if p.topology != "custom":
                        g["links"].append([h, switches[i % len(switches)]])
            else:
                g = self.load(db)
                if op in ("start", "stop"):
                    if (op == "start") != (g["state"] == "running"):
                        g["generation"] = g.get("generation",0)+1
                    g["state"] = "running" if op == "start" else "stopped"
                elif op == "delete":
                    if g["state"] == "running":
                        raise ConflictError("Stop the network before deleting it.")
                    db.execute("DELETE FROM native_network")
                    return {"state": "deleted"}
                elif op in ("host", "switch"):
                    add_node(g, op)
                elif op == "remove":
                    if p.node not in g["nodes"]:
                        raise InputValidationError("Unknown node.")
                    del g["nodes"][p.node]
                    g["links"] = [edge for edge in g["links"] if p.node not in edge]
                elif op in ("connect", "disconnect"):
                    if p.node == p.peer or any(
                        n not in g["nodes"] for n in (p.node, p.peer)
                    ):
                        raise InputValidationError(
                            "Choose two different existing nodes."
                        )
                    if all(g["nodes"][n]["kind"] == "host" for n in (p.node, p.peer)):
                        raise InputValidationError("Connect hosts through switches.")
                    pair = {p.node, p.peer}
                    exists = any(set(e) == pair for e in g["links"])
                    if exists == (op == "connect"):
                        raise ConflictError("Link is already in the requested state.")
                    if op == "connect":
                        g["links"].append([p.node, p.peer])
                    else:
                        g["links"] = [e for e in g["links"] if set(e) != pair]
                elif op == "map":
                    node = g["nodes"].get(p.node, {})
                    if node.get("kind") != "host":
                        raise InputValidationError("Select a host.")
                    if p.client:
                        self.app.clients.get(p.client)
                        if any(
                            n["client"] == p.client and n != node
                            for n in g["nodes"].values()
                        ):
                            raise ConflictError(
                                "Worker already mapped in this network."
                            )
                    node["client"] = p.client or None
            if op in ("create", "remove", "connect", "disconnect", "stop"):
                g["forwarding"] = {}
            db.execute(
                "INSERT OR REPLACE INTO native_network VALUES(1,?)", (json.dumps(g),)
            )
            return {"id": g["id"], "state": g["state"]}

    def submit(self, p):
        with self.db() as db:
            g = self.load(db)
            self.check(g, p)
            p = {**p, "network": g["id"], "generation":g.get("generation",0), "client": g["nodes"][p["dest"]]["client"]}
        job = self.app.job_manager.submit(
            "native_traffic", dedupe_key="native:" + g["id"], payload=p
        )
        with self.db() as db:
            db.execute(
                "INSERT INTO native_job VALUES(?,?,?,?)",
                (job.id, g["id"], "simulation", time.time()),
            )
            notice(db, "Simulation queued · " + job.id)
        return {"job": job.id}

    def check(self, g, p):
        if g["state"] != "running" or g["id"] != p.get("network", g["id"]) or p.get("generation",g.get("generation",0))!=g.get("generation",0):
            raise ConflictError("The selected network is no longer running.")
        if p["scenario"] not in (*SCENARIOS, REPLAY):
            raise InputValidationError("Unknown scenario.")
        path = g.get("forwarding", {}).get(p["source"] + "/" + p["dest"]) or route(
            g, p["source"], p["dest"]
        )
        if p["scenario"] == REPLAY and not g["nodes"][p["dest"]]["client"]:
            raise ConflictError("Map a worker to the destination first.")
        return path

    def frame(self, ctx, p, index):
        app = self.app
        with app.models.lock, self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            g = self.load(db)
            path = self.check(g, p)
            src, dst = (g["nodes"][k] for k in (p["source"], p["dest"]))
            cid = dst["client"]
            if cid != p["client"]:
                raise ConflictError(
                    "Destination assignment changed. Start another run."
                )
            fid = uuid4().hex
            eid = None
            details = dict(
                client=cid,
                organization=app.clients.get(cid).config.get("organization", "")
                if cid
                else None,
                source_ip=src["ip"],
                destination_ip=dst["ip"],
                schema=SCHEMA,
                outcome="Incompatible model",
                provenance="Internal virtual frame",
                feature_names=["frame_bytes"],
                units=["bytes"],
                preprocessing="none",
            )
            size = SCENARIOS.get(p["scenario"], 0)
            if p["scenario"] != REPLAY:
                # These attributes exist only on a virtual frame in the event log.
                scenario = p["scenario"]
                if "scanning" in scenario:
                    details["virtual_service_slot"] = index % 16
                if "flood" in scenario:
                    details["virtual_burst"] = index // 4
                if "SYN" in scenario:
                    details["abstract_state"] = "connection request"
                if "login" in scenario:
                    details["virtual_login_attempt"] = index + 1
                if "Suspicious" in scenario:
                    size *= 1 + (index % 3)
                details["protocol"] = next(
                    (v for v in ("ICMP", "UDP", "HTTP") if v in scenario), "TCP"
                )
            if p["scenario"] == REPLAY:
                details.update(
                    schema=None,
                    feature_names=None,
                    units=None,
                    preprocessing=None,
                    provenance="Labelled CSV replay",
                    outcome="Inference failed",
                )
                try:
                    manifest, (_, weights, prep, _) = app.models.current()
                    ver = manifest["version"]
                    ack = native_samples.current_ack(db, cid, ver, app.clients.pid(cid))
                    if not ack:
                        raise ConflictError(
                            "Synchronize the connected destination worker to the deployed model first."
                        )
                    source = app.datasets.source_id(
                        prep["dataset_id"], weights["metadata"]["dataset_sha256"]
                    )
                    if p.get("dataset") and p["dataset"] != source:
                        raise InputValidationError(
                            "Replay requires the deployed model's source CSV."
                        )
                    sample = app.datasets.labelled_sample(
                        source,
                        p["label"],
                        p["partition"],
                        p["offset"] + index,
                        None,
                        app.models,
                    )
                    details.update(
                        version=ver,
                        weight_hash=ack[0],
                        truth=sample["actual"],
                        schema="csv:" + weights["metadata"]["dataset_sha256"],
                        feature_names=prep["feature_names"],
                        preprocessing=manifest.get("preprocessing_sha256"),
                        dataset=source,
                        csv_row=sample["index"] + 2,
                        partition=p["partition"],
                    )
                    started = time.perf_counter()
                    receipt = app.clients.replay(cid, sample["features"])
                    result = app.models.predict(receipt["features"])
                    if result["version"] != ver:
                        raise ConflictError("Deployment changed during replay.")
                    pred = result["label"]
                    truth = sample["actual"]
                    outcome = (
                        ("True negative", "False positive"),
                        ("False negative", "True positive"),
                    )[truth][pred]
                    details.update(
                        duration_ms=(time.perf_counter() - started) * 1000,
                        prediction=pred,
                        probability=result["prediction"],
                        outcome=outcome,
                    )
                    size = len(
                        json.dumps(sample["features"], separators=(",", ":")).encode()
                    )
                    eid = app.automatic.record(
                        db,
                        client=cid,
                        origin="dataset evaluation"
                        if p["partition"] == "test"
                        else "dataset training",
                        key=weights["metadata"]["dataset_sha256"]
                        + ":"
                        + str(sample["index"]),
                        features=sample["features"],
                        schema=prep["feature_names"],
                        result=result,
                        source=weights["metadata"]["dataset_sha256"],
                        row_index=sample["index"],
                        truth=truth,
                        host=dst["name"],
                        host_ip=dst["ip"],
                        src=src["ip"],
                        dst=dst["ip"],
                    )
                except AppError as exc:
                    details["reason"] = str(exc)
            db.execute(
                "INSERT INTO native_frame VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    fid,
                    g["id"],
                    ctx.job_id,
                    time.time(),
                    src["name"],
                    dst["name"],
                    p["scenario"],
                    size,
                    json.dumps(path),
                    eid,
                    json.dumps(details),
                ),
            )
            if cid and p["scenario"] != REPLAY and (index + 1) % 13 == 0:
                rows = db.execute(
                    "SELECT ts,bytes,path FROM native_frame WHERE job=? AND dst=? ORDER BY ts DESC LIMIT 13",
                    (ctx.job_id, dst["name"]),
                ).fetchall()
                if len(rows) == 13:
                    observations = [
                        (r["ts"], r["bytes"], len(json.loads(r["path"])) - 2)
                        for r in reversed(rows)
                    ]
                    sid = native_samples.record(
                        app,
                        db,
                        "simulation",
                        cid,
                        g["id"],
                        native_samples.vector(observations),
                        dst["name"],
                    )
                    sample = db.execute(
                        "SELECT * FROM native_sample WHERE id=?", (sid,)
                    ).fetchone()
                    details.update(
                        sample=sid,
                        schema="simulation.window.v1",
                        feature_names=native_samples.schema("simulation"),
                        units=["bytes", "switches", "seconds", "seconds"] * 12,
                        outcome=sample["outcome"],
                        version=sample["version"],
                        reason=sample["reason"],
                    )
                    if sample["event"]:
                        details.update(json.loads(sample["reason"]))
                    db.execute(
                        "UPDATE native_frame SET details=?,event=? WHERE id=?",
                        (json.dumps(details), sample["event"], fid),
                    )
            if size:
                key = p["source"] + "/" + p["dest"]
                if key not in g.setdefault("forwarding", {}):
                    g["forwarding"][key] = path
                    db.execute(
                        "UPDATE native_network SET body=? WHERE id=1", (json.dumps(g),)
                    )
            if size:
                audit(
                    db,
                    "traffic generated",
                    job=ctx.job_id,
                    client=cid,
                    organization=details["organization"],
                    version=details.get("version"),
                    event=eid or fid,
                )
            if p["scenario"] == REPLAY:
                audit(
                    db,
                    "attack sample submitted"
                    if p["label"]
                    else "benign sample submitted",
                    job=ctx.job_id,
                    client=cid,
                    organization=details["organization"],
                    version=details.get("version"),
                    event=eid or fid,
                )
            return details

    def traffic(self, ctx, p):
        with self.db() as db:
            audit(db, "simulation started", job=ctx.job_id, event=p["network"])
        start = time.monotonic()
        count = 0
        while count < p["samples"] and time.monotonic() - start < p["duration"]:
            ctx.check_cancelled()
            result = self.frame(ctx, p, count)
            if result["outcome"] == "Inference failed":
                raise ConflictError(result["reason"])
            count += 1
            ctx.progress(
                max(
                    count / p["samples"],
                    min(1, (time.monotonic() - start) / p["duration"]),
                ),
                f"Forwarded {count} events",
            )
            if count < p["samples"]:
                ctx.cancel_event.wait(1 / p["rate"])
        return {"events": count}

    def snapshot(self):
        with self.db() as db:
            try:
                g = self.load(db)
            except ConflictError:
                return dict(
                    network=None,
                    scenarios=[*SCENARIOS, REPLAY],
                    events=[],
                    jobs=[],
                    flows=[],
                    packets=0,
                    bytes=0,
                    bps=0,
                    verified=0,
                    retraining=0,
                )
            net = g["id"]
            stats = db.execute(
                "SELECT count(*),coalesce(sum(bytes),0) FROM native_frame WHERE network=? AND bytes>0",
                (net,),
            ).fetchone()
            recent = db.execute(
                "SELECT coalesce(sum(bytes),0) FROM native_frame WHERE network=? AND ts>?",
                (net, time.time() - 5),
            ).fetchone()[0]
            nodes = g["nodes"]
            for node in nodes.values():
                name = node["name"]
                node["neighbors"] = [
                    b if a == name else a for a, b in g["links"] if name in (a, b)
                ]
                node["connected"] = bool(node["neighbors"] and g["state"] == "running")
                node["tx"], node["rx"] = db.execute(
                    "SELECT count(CASE WHEN src=? THEN 1 END),count(CASE WHEN dst=? THEN 1 END) FROM native_frame WHERE network=? AND bytes>0",
                    (name, name, net),
                ).fetchone()
                cid = node["client"]
                if cid:
                    try:
                        node["organization"] = self.app.clients.get(cid).config.get(
                            "organization", ""
                        )
                    except AppError:
                        node["organization"] = None
                    node["worker_pid"] = self.app.clients.pid(cid)
                    ack = db.execute(
                        "SELECT version FROM auto_ack WHERE client=? AND pid=? ORDER BY ts DESC LIMIT 1",
                        (cid, node["worker_pid"]),
                    ).fetchone()
                    node["synced_version"] = ack[0] if ack else None
                    m = db.execute(
                        "SELECT dataset,total,job FROM central_member WHERE client=?",
                        (cid,),
                    ).fetchone()
                    if m:
                        node.update(
                            dataset=m[0],
                            dataset_rows=m[1],
                            training=self.app.jobs.get(m[2]).status
                            if m[2]
                            else "assigned",
                        )
                node["alerts"] = db.execute(
                    "SELECT count(DISTINCT f.event) FROM native_frame f JOIN auto_event e ON e.id=f.event WHERE f.network=? AND f.dst=? AND e.prediction=1",
                    (net, name),
                ).fetchone()[0]
            events = [
                {**dict(r), "details": json.loads(r["details"])}
                for r in db.execute(
                    "SELECT f.*,e.run,e.status,e.label AS reviewed,e.prediction AS scored FROM native_frame f LEFT JOIN auto_event e ON e.id=f.event WHERE network=? ORDER BY f.ts DESC LIMIT 150",
                    (net,),
                )
            ]
            for entry in events:
                if entry["reviewed"] in (0,1) and entry["scored"] in (0,1):
                    entry["details"]["verified_label"]=entry["reviewed"]
                    entry["details"]["outcome"]=(("True negative","False positive"),("False negative","True positive"))[entry["reviewed"]][entry["scored"]]
            verified, jobs = db.execute(
                "SELECT count(DISTINCT CASE WHEN e.label=1 THEN e.id END),count(DISTINCT e.run) FROM native_frame f JOIN auto_event e ON e.id=f.event WHERE network=?",
                (net,),
            ).fetchone()
            flows = []
            link_counts={tuple(sorted(edge)):dict(endpoints=edge,packets=0,bytes=0,up=g["state"]=="running") for edge in g["links"]}
            for r in db.execute(
                "SELECT src,dst,path,count(*) packets,sum(bytes) bytes FROM native_frame WHERE network=? AND bytes>0 GROUP BY src,dst,path",
                (net,),
            ):
                path = json.loads(r["path"])
                for left,right in zip(path,path[1:]):
                    entry=link_counts.get(tuple(sorted((left,right))))
                    if entry:
                        entry["packets"]+=r["packets"]
                        entry["bytes"]+=r["bytes"]
                for i in range(1, len(path) - 1):
                    if path[i] in nodes:
                        nodes[path[i]]["tx"]+=r["packets"]
                        nodes[path[i]]["rx"]+=r["packets"]
                    if path == g.get("forwarding", {}).get(r["src"] + "/" + r["dst"]):
                        flows.append(
                            dict(
                                switch=path[i],
                                destination=path[-1],
                                via=path[i + 1],
                                packets=r["packets"],
                                bytes=r["bytes"],
                                source=r["src"],
                            )
                        )
            return dict(
                network=g,
                link_counters=list(link_counts.values()),
                scenarios=[*SCENARIOS, REPLAY],
                packets=stats[0],
                bytes=stats[1],
                bps=recent * 8 / 5,
                events=events,
                flows=flows,
                verified=verified,
                retraining=jobs,
                jobs=self.jobs(db, net),
            )

    def jobs(self, db, network):
        result = []
        for row in db.execute(
            "SELECT id FROM native_job WHERE network=? ORDER BY ts DESC LIMIT 10",
            (network,),
        ):
            job = self.app.jobs.get(row[0])
            result.append(
                dict(
                    id=job.id,
                    status=job.status,
                    progress=job.progress,
                    message=job.error or job.message,
                )
            )
        return result
