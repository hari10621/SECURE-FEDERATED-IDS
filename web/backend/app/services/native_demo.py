"""Read-only tutorial checkpoints bound to one central model and virtual network."""

import json
import time
from .version_evaluation import history


def checkpoints(app, mid):
    m = app.central.model(mid)
    ds = app.datasets.get(m["reference"])
    with app.sdn.db() as db:
        versions = [
            dict(r)
            for r in db.execute(
                "SELECT * FROM central_version WHERE model=? ORDER BY number", (mid,)
            )
        ]
        members = [
            dict(r)
            for r in db.execute("SELECT * FROM central_member WHERE model=?", (mid,))
        ]
        zero = versions[0]
        one = next(
            (
                r
                for r in versions
                if r["parent"] == zero["version"]
                and r["state"] in ("validated", "deployed")
            ),
            None,
        )
        base = one["version"] if one else ""
        row = db.execute("SELECT body FROM native_network").fetchone()
        g = json.loads(row[0]) if row else {}
        ids = {r["client"] for r in members}
        mapped = {
            n["client"] for n in g.get("nodes", {}).values() if n.get("client") in ids
        }
        updates = [
            dict(r)
            for r in db.execute(
                "SELECT client,version,state FROM central_update WHERE model=? AND base=?",
                (mid, zero["version"]),
            )
        ]
        contributors = {
            u["client"]
            for u in updates
            if u["version"] == base and u["state"] == "aggregated"
        }
        frames = [
            dict(r)
            for r in db.execute(
                """SELECT f.id,f.scenario,f.dst,e.* FROM native_frame f LEFT JOIN auto_event e ON f.event=e.id
          WHERE f.network=? AND (e.version=? OR f.event IS NULL) ORDER BY f.ts DESC""",
                (g.get("id", ""), base),
            )
        ]
        hits = [
            f
            for f in frames
            if f["client"] in ids
            and f["origin"] == "dataset training"
            and f["truth"] == 1
        ]
        reviewed = [f for f in hits if f["label"] == 1 and f["evidence"]]
        run = next(
            (
                db.execute("SELECT * FROM auto_run WHERE id=?", (f["run"],)).fetchone()
                for f in reviewed
                if f["run"]
            ),
            None,
        )
        two = next(
            (
                v
                for v in versions
                if run and v["version"] == run["candidate"] and v["parent"] == base
            ),
            None,
        )

        def synced(version, workers):
            return bool(workers) and workers.issubset(
                {
                    r[0]
                    for r in db.execute(
                        "SELECT client FROM auto_ack WHERE version=?", (version,)
                    )
                }
            )

        v2 = two["version"] if two else ""
        comparison = db.execute(
            "SELECT c.id FROM native_comparison c JOIN native_frame f ON f.id=c.frame JOIN auto_event e ON e.id=f.event WHERE e.truth=1 AND e.origin='dataset evaluation' AND f.network=? AND c.baseline=? AND c.candidate=?",
            (g.get("id", ""), base, v2),
        ).fetchone()
        evidence = history(app.central, mid) if two else {}
        compatible = (
            two
            and evidence.get(base, {}).get("metrics")
            and evidence.get(v2, {}).get("protocol") == evidence[base].get("protocol")
            and evidence[v2]["metrics"]
        )
        inspected = db.execute(
            "SELECT frame FROM native_inspection WHERE ts>=? AND frame IN (SELECT id FROM native_frame WHERE event IN (SELECT id FROM auto_event WHERE run=?))",
            (
                run["finished"] or time.time() if run else time.time(),
                run["id"] if run else "",
            ),
        ).fetchone()
        results = [
            (
                "Select a validated 48-feature dataset",
                "datasets",
                ds.validation_status == "valid" and ds.feature_count == 48,
            ),
            ("Create central model V0", "central-model", zero["number"] == 0),
            ("Assign two clients", "clients", len(ids) >= 2),
            (
                "Assign organizations",
                "clients",
                sum(bool(app.clients.get(i).config.get("organization")) for i in ids)
                >= 2,
            ),
            (
                "Connect both workers",
                "clients",
                sum(bool(app.clients.pid(i)) for i in ids) >= 2,
            ),
            (
                "Assign local datasets",
                "clients",
                sum(bool(r["dataset"] and r["total"]) for r in members) >= 2,
            ),
            (
                "Train local models from V0",
                "clients",
                len({u["client"] for u in updates}) >= 2,
            ),
            ("Aggregate client updates", "training", len(contributors) >= 2),
            ("Create a federated candidate", "central-model", one),
            (
                "Validate and deploy the first candidate",
                "central-model",
                one and one["state"] == "deployed",
            ),
            (
                "Synchronize the first candidate",
                "central-model",
                synced(base, contributors),
            ),
            ("Start the virtual network", "sdn", g.get("state") == "running"),
            ("Map two tutorial workers", "sdn", len(mapped) >= 2),
            (
                "Generate normal virtual traffic",
                "sdn",
                any(f["scenario"].startswith("Normal ") for f in frames),
            ),
            ("Replay a labelled training attack", "sdn", hits),
            (
                "Inspect the scored event",
                "sdn",
                any(
                    db.execute(
                        "SELECT 1 FROM native_inspection WHERE frame=?", (f["id"],)
                    ).fetchone()
                    for f in hits
                ),
            ),
            ("Verify the independent label", "security", reviewed),
            ("Trigger verified retraining", "training", run and run["job"]),
            ("Generate the retrained candidate", "central-model", two),
            ("Check comparable held-out evaluations", "central-model", compatible),
            (
                "Deploy the validated candidate",
                "central-model",
                two and two["state"] == "deployed",
            ),
            (
                "Synchronize participating workers",
                "central-model",
                two and synced(v2, set(json.loads(run["clients"]))),
            ),
            ("Retest one independent held-out attack", "sdn", comparison),
            ("Inspect the linked training history", "sdn", inspected and two),
        ]
    return [
        {"step": i, "label": label, "page": page, "complete": bool(value)}
        for i, (label, page, value) in enumerate(results, 1)
    ]
