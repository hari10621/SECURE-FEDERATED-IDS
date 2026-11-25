"""Named GRU lineages, immutable baselines, worker contributions and validation."""

from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace
import threading
import time
from uuid import uuid4
import zlib

from ..domain.dataset import apply_scaler, load_csv_dataset, preprocess
from ..domain.federated.client import ClientUpdate, ciphertext_digest, weight_digest
from ..domain.federated.keras_backend import KerasGRUBackend
from ..domain.federated.server import FLServer
from ..domain.metrics import compute_metrics, confusion_counts
from ..domain.model import ARTIFACT_FORMAT, parameter_specs
from ..enums import ExperimentStatus
from ..errors import ConflictError, InputValidationError, UnavailableError
from ..schemas import ExperimentCreate, TrainingRequest
from .automatic import Policy, notice
from .security_audit import audit


class CentralModels:
    def __init__(self, app):
        self.app = app
        self.db = app.sdn.db
        self.lock = threading.RLock()
        with self.db() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS central_update_classes(id TEXT PRIMARY KEY,benign INTEGER,attack INTEGER);
            CREATE TABLE IF NOT EXISTS central_model(id TEXT PRIMARY KEY,name TEXT UNIQUE,reference TEXT,config TEXT,head TEXT,ts REAL);
            CREATE TABLE IF NOT EXISTS central_version(version TEXT PRIMARY KEY,model TEXT,number INTEGER,parent TEXT,state TEXT,artifact TEXT,digest TEXT,metrics TEXT,ts REAL,experiment TEXT,UNIQUE(model,number));
            CREATE TABLE IF NOT EXISTS central_member(client TEXT PRIMARY KEY,model TEXT,dataset TEXT,slot INTEGER,epochs INTEGER,benign INTEGER,attack INTEGER,total INTEGER,job TEXT);
            CREATE TABLE IF NOT EXISTS central_update(id TEXT PRIMARY KEY,client TEXT,organization TEXT,model TEXT,base TEXT,dataset TEXT,count INTEGER,duration REAL,digest TEXT,local_hash TEXT,state TEXT,body BLOB,samples BLOB,version TEXT,ts REAL);
            CREATE INDEX IF NOT EXISTS central_ready ON central_update(model,base,client,state);
            INSERT OR IGNORE INTO auto_migrations VALUES(3);
            """)
            db.execute("BEGIN IMMEDIATE")
            if not db.execute(
                "SELECT 1 FROM auto_migrations WHERE version=4"
            ).fetchone():
                db.execute("ALTER TABLE central_update ADD COLUMN base_hash TEXT")
                db.execute("ALTER TABLE central_update ADD COLUMN round_number INTEGER")
                db.execute(
                    "ALTER TABLE central_version ADD COLUMN rounds INTEGER DEFAULT 0"
                )
                db.execute("INSERT INTO auto_migrations VALUES(4)")
            if not db.execute(
                "SELECT 1 FROM auto_migrations WHERE version=5"
            ).fetchone():
                db.execute("ALTER TABLE central_update ADD COLUMN job TEXT")
                db.execute("INSERT INTO auto_migrations VALUES(5)")
            db.execute(
                "UPDATE central_update SET state='interrupted',body=NULL WHERE state='round'"
            )
        app.job_manager.register_handler("central_local", self.local_job)
        app.job_manager.register_handler("central_round", self.round_job)
        # The registry pointer is atomically replaced before SQLite receives its receipt.
        # Reconcile the narrow crash window between those two durable writes.
        if app.models.active.is_file():
            try:
                manifest = json.loads(app.models.active.read_bytes())
            except (OSError, ValueError):
                return
            version = manifest.get("version")
            with self.db() as db:
                target = db.execute(
                    "SELECT version FROM auto_sync_target WHERE id=1"
                ).fetchone()
            if (
                (manifest.get("central_model") or manifest.get("automatic") or target)
                and version
                and (not target or target[0] != version)
            ):
                if app.models.status().get("version") == version:
                    app.automatic.deployment(version)

    def row(self, query, args):
        with self.db() as db:
            row = db.execute(query, args).fetchone()
            if not row:
                raise ConflictError(
                    "Unknown central model, version or assigned client."
                )
            return dict(row)

    def model(self, mid):
        return self.row("SELECT * FROM central_model WHERE id=?", (mid,))

    def checked_base(self, mid, base):
        m = self.model(mid)
        if m["head"] != base:
            raise ConflictError(
                "Stale base version. Refresh and train from the current head."
            )
        return m

    def data(self, dataset_id, max_rows=None):
        ds = self.app.datasets.get(dataset_id)
        path = self.app.datasets.path_for(ds)
        if hashlib.sha256(path.read_bytes()).hexdigest() != ds.sha256:
            raise InputValidationError("Dataset checksum mismatch.")
        data = load_csv_dataset(
            path,
            label_column=ds.label_column,
            max_rows=max_rows or self.app.training.settings.training_max_rows,
        )
        if data.feature_count != 48 or ds.validation_status != "valid":
            raise InputValidationError("Choose a validated 48-feature CSV.")
        return ds, data

    def reference(self, mid):
        m = self.model(mid)
        config = json.loads(m["config"])
        ds, raw = self.data(m["reference"], config.get("reference_rows"))
        prep = preprocess(
            raw.rows,
            raw.labels,
            feature_names=raw.feature_names,
            seed=config["seed"],
            test_size=config["test_size"],
        )
        if set(prep.test_labels) != {0, 1} or set(prep.train_labels) != {0, 1}:
            raise InputValidationError(
                "The reference split must contain both classes in each partition."
            )
        original = self.row(
            "SELECT artifact FROM central_version WHERE model=? AND number=0", (mid,)
        )
        artifact = json.loads(original["artifact"])
        side = self.app.models.artifact(
            Path(artifact["preprocessing_file"]).relative_to("models").as_posix(),
            artifact["preprocessing_sha256"],
        )
        if (
            side["feature_names"] != raw.feature_names
            or side["prepared"]["split"] != prep.split.as_dict()
            or side["prepared"]["scaler"] != prep.scaler.as_dict()
        ):
            raise InputValidationError(
                "The reference preprocessing has changed since V0."
            )
        return ds, raw, prep

    def weights(self, version):
        v = self.row("SELECT * FROM central_version WHERE version=?", (version,))
        a = json.loads(v["artifact"])
        path = Path(a["weights_file"]).relative_to("models").as_posix()
        return self.app.models.artifact(path, a["weights_sha256"])["weights"]

    def create(self, p):
        if not self.app.training.settings.enable_training:
            raise UnavailableError("Enable GRU training before creating a model.")
        mid = uuid4().hex
        ds, raw = self.data(p.dataset)
        prep = preprocess(
            raw.rows,
            raw.labels,
            feature_names=raw.feature_names,
            seed=p.seed,
            test_size=p.test_size,
        )
        if set(prep.test_labels) != {0, 1} or set(prep.train_labels) != {0, 1}:
            raise InputValidationError(
                "Both partitions require benign and attack records."
            )
        backend = KerasGRUBackend(p.learning_rate)
        if p.method == "random":
            weights = backend.initial_weights(48)
        else:
            if p.method == "restore":
                if (
                    not p.source
                    or len(p.source) != 32
                    or any(c not in "0123456789abcdef" for c in p.source)
                ):
                    raise InputValidationError("Select a registered version.")
                registry = self.app.models.registry / (p.source + ".json")
                if not registry.is_file():
                    raise InputValidationError("Unknown registered version.")
                manifest = json.loads(registry.read_bytes())
                artifact = self.app.models.artifact(
                    manifest["model_path"], manifest["sha256"]
                )
                side = self.app.models.artifact(
                    manifest["preprocessing"], manifest["preprocessing_sha256"]
                )
            else:
                artifact = p.weights or {}
                side = p.preprocessing or {}
            specs = [
                {"name": v.name, "shape": list(v.shape)} for v in parameter_specs(48)
            ]
            if (
                artifact.get("format") != ARTIFACT_FORMAT
                or artifact.get("model") != "keras_gru"
                or artifact.get("input_features") != 48
                or artifact.get("parameter_specs") != specs
                or not isinstance(artifact.get("metadata"), dict)
                or not isinstance(side.get("prepared"), dict)
                or side.get("format") != "securefed-preprocessing-v1"
                or artifact["metadata"].get("experiment_id")
                != side.get("experiment_id")
                or artifact.get("metadata", {}).get("dataset_sha256") != ds.sha256
                or side.get("feature_names") != raw.feature_names
                or side.get("prepared", {}).get("scaler") != prep.scaler.as_dict()
                or side.get("prepared", {}).get("split") != prep.split.as_dict()
                or side.get("prepared", {}).get("mode") != "clean"
            ):
                raise InputValidationError(
                    "The imported architecture, source, feature order, clean split and scaler must match."
                )
            weights = artifact.get("weights", [])
            if not isinstance(weights, list) or not all(
                type(v) in (float, int) and math.isfinite(v) for v in weights
            ):
                raise InputValidationError("Invalid weight values.")
            backend.load_model(weights, 48, p.learning_rate)
        conf = p.model_dump(exclude={"weights", "preprocessing", "name", "dataset"})
        conf["reference_rows"] = len(raw.rows)
        with self.lock, self.db() as db:
            if db.execute(
                "SELECT 1 FROM central_model WHERE name=?", (p.name.strip(),)
            ).fetchone():
                raise ConflictError("Model name already exists.")
            result = {
                "model": {"name": "keras_gru"},
                "completed_rounds": 0,
                "local_epochs": 0,
                "training_mode": "initialization",
                "rounds": [],
            }
            artifact = self.app.training._write_artifacts(
                SimpleNamespace(id=mid, client_count=0),
                ds,
                TrainingRequest(seed=p.seed),
                raw,
                prep,
                result,
                weights,
            )
            version = Path(artifact["directory"]).name
            ts = time.time()
            db.execute(
                "INSERT INTO central_model VALUES(?,?,?,?,?,?)",
                (mid, p.name.strip(), ds.id, json.dumps(conf), version, ts),
            )
            db.execute(
                "INSERT INTO central_version(version,model,number,parent,state,artifact,digest,metrics,ts,experiment) VALUES(?,?,0,NULL,'initialized',?,?,NULL,?,NULL)",
                (version, mid, json.dumps(artifact), weight_digest(weights), ts),
            )
            notice(db, "Central model initialized · " + p.name + " · V0 · " + version)
        return {"id": mid, "version": version}

    def local_data(self, m, member, reference, events=()):
        ds, raw, prep = reference
        local_ds, local = (
            (ds, raw) if member["dataset"] == ds.id else self.data(member["dataset"])
        )
        if local.feature_names != raw.feature_names:
            raise InputValidationError(
                "Client feature names or column order differ from the reference."
            )
        banned = {tuple(raw.rows[i]) for i in prep.split.test}
        allowed = (
            prep.split.train if local_ds.sha256 == ds.sha256 else range(len(local.rows))
        )
        shards = (
            json.loads(m["config"])["shards"] if local_ds.sha256 == ds.sha256 else 1
        )
        slot = member["slot"] if shards > 1 else 0
        with self.db() as db:
            publication = db.execute("""SELECT p.owners FROM published p JOIN native_dataset n
                                      ON n.dataset=p.dataset WHERE p.dataset=?""",(local_ds.id,)).fetchone()
        owners=json.loads(publication[0]) if publication else None
        if owners is not None and len(owners)<len(local.rows):
            raise InputValidationError("Published source lacks row ownership records.")
        rows = {}
        for n, i in enumerate(allowed):
            key = tuple(local.rows[i])
            assigned=owners[i]==member["client"] if owners is not None else n % shards == slot
            if not assigned or key in banned:
                continue
            if key in rows and rows[key] != local.labels[i]:
                raise InputValidationError(
                    "Conflicting labels for duplicate client features."
                )
            rows[key] = local.labels[i]
        for e in events:
            key = tuple(e["features"])
            if key in banned or e["schema"] != raw.feature_names:
                raise InputValidationError(
                    "Verified sample conflicts with evaluation isolation or schema."
                )
            if e["origin"] == "dataset training" and (
                e["source"] != ds.sha256
                or e["row_index"] not in prep.split.train
                or raw.rows[e["row_index"]] != e["features"]
                or raw.labels[e["row_index"]] != e["label"]
            ):
                raise InputValidationError("Verified row provenance mismatch.")
            rows.pop(key, None)
            if e["client"] == member["client"]:
                rows[key] = e["label"]
        if not rows:
            raise InputValidationError(
                "No eligible local records remain after holdout exclusion."
            )
        return (
            apply_scaler(list(rows), prep.scaler),
            list(rows.values()),
            [weight_digest(row) for row in rows],
            local_ds.rows,
        )

    def assign(self, mid, cid, dataset, epochs, mapping=None):
        with self.lock:
            m = self.model(mid)
            reference = self.reference(mid)
            if self.app.datasets.get(dataset).sha256 == reference[0].sha256:
                dataset = m["reference"]
            with self.db() as db:
                db.execute("BEGIN IMMEDIATE")
                prev = db.execute(
                    "SELECT * FROM central_member WHERE client=?", (cid,)
                ).fetchone()
                used = {
                    r[0]
                    for r in db.execute(
                        "SELECT slot FROM central_member WHERE model=? AND dataset=? AND client<>?",
                        (mid, dataset, cid),
                    )
                }
                slots = json.loads(m["config"])["shards"]
                slot = (
                    next((i for i in range(slots) if i not in used), None)
                    if dataset == m["reference"]
                    else 0
                )
                if slot is None:
                    raise ConflictError(
                        "All reference shards are assigned. Choose a separate client dataset."
                    )
                member = dict(client=cid, dataset=dataset, slot=slot)
                _, labels, _, total = self.local_data(m, member, reference)
                if mapping:
                    self.app.sdn.bind(db, *mapping, cid)
                db.execute(
                    "INSERT OR REPLACE INTO central_member VALUES(?,?,?,?,?,?,?,?,NULL)",
                    (
                        cid,
                        mid,
                        dataset,
                        slot,
                        epochs,
                        labels.count(0),
                        labels.count(1),
                        total,
                    ),
                )
                if prev:
                    db.execute(
                        "UPDATE central_update SET state='superseded',body=NULL WHERE client=? AND state='ready'",
                        (cid,),
                    )
                notice(db, "Client dataset assigned · " + cid + " · " + mid)

    def queue(self, mid, p):
        if not self.app.training.settings.enable_training:
            raise UnavailableError("Training is disabled.")
        self.checked_base(mid, p["base"])
        ids = p["clients"]
        if len(set(ids)) != len(ids) or not ids:
            raise InputValidationError("Select distinct registered workers.")
        for cid in ids:
            self.row(
                "SELECT * FROM central_member WHERE model=? AND client=?", (mid, cid)
            )
            if not self.app.clients.pid(cid):
                raise ConflictError("A selected worker is disconnected.")
        kind = "central_local" if p["action"] == "local" else "central_round"
        if kind == "central_round" and len(ids) not in (2, 3, 4, 8, 12):
            raise InputValidationError("Choose 2, 3, 4, 8 or 12 workers.")
        job = self.app.job_manager.submit(
            kind,
            dedupe_key=":".join(
                (
                    kind,
                    mid,
                    p["base"],
                    p["action"],
                    str(bool(p.get("encrypted"))),
                    ",".join(sorted(ids)),
                )
            ),
            payload={**p, "model": mid},
        )
        with self.db() as db:
            db.executemany(
                "UPDATE central_member SET job=? WHERE client=?",
                [(job.id, c) for c in ids],
            )
        return {"job": job.id}

    def train_one(
        self,
        m,
        base,
        member,
        reference,
        weights,
        ctx,
        events=(),
        crypto=None,
        epochs=None,
        round_index=0,
        standalone=False,
    ):
        cid = member["client"]
        rows, labels, keys, _ = self.local_data(m, member, reference, events)
        cfg = json.loads(m["config"])
        worker = self.app.clients.participant(
            client_id=cid, rows=rows, labels=labels, seed=cfg["seed"]
        )
        opts = dict(
            round_index=round_index,
            epochs=epochs or member["epochs"],
            learning_rate=cfg["learning_rate"],
            batch_size=cfg["batch_size"],
        )
        with self.db() as db:
            audit(db,"local training started",client=cid,organization=self.app.clients.get(cid).config.get("organization"),version=base,job=ctx.job_id)
            notice(db, "Local training started · " + cid + " · " + base)
        backend = KerasGRUBackend()
        if crypto:
            server, material, public = crypto
            server.register_client(cid, len(rows))
            token = server.issue_auth_token(cid)
            worker.public_context = material.public_context
            update = worker.train_encrypted(
                weights,
                backend,
                public,
                auth_token=token.token,
                timestamp=token.timestamp,
                nonce=token.nonce,
                **opts,
            )
            digest = update.ciphertext_digest
            local_hash = update.local_hash
            body = None
        else:
            update = worker.train(weights, backend, **opts)
            digest = update.digest
            local_hash = weight_digest(update.weights)
            body = (
                zlib.compress(json.dumps(asdict(update)).encode(), 1)
                if standalone
                else None
            )
        duration = update.training_seconds
        if duration is None:
            raise ConflictError(
                "Worker did not report local training time. Restart the backend."
            )
        self.checked_base(m["id"], base)
        uid = uuid4().hex
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if (
                db.execute(
                    "SELECT head FROM central_model WHERE id=?", (m["id"],)
                ).fetchone()[0]
                != base
            ):
                raise ConflictError("Base changed while worker was training.")
            if standalone:
                db.execute(
                    "UPDATE central_update SET state='superseded',body=NULL WHERE client=? AND base=? AND state='ready'",
                    (cid, base),
                )
            db.execute(
                "INSERT INTO central_update VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    uid,
                    cid,
                    self.app.clients.get(cid).config.get("organization", ""),
                    m["id"],
                    base,
                    member["dataset"],
                    len(rows),
                    duration,
                    digest,
                    local_hash,
                    "ready" if standalone else "round",
                    body,
                    zlib.compress(json.dumps(keys).encode()),
                    None,
                    time.time(),
                    weight_digest(weights),
                    round_index + 1,
                    ctx.job_id,
                ),
            )
            db.execute(
                "INSERT INTO central_update_classes VALUES(?,?,?)",
                (uid, labels.count(0), labels.count(1)),
            )
            for category in ("local training completed","client update received"):
                audit(db,category,client=cid,organization=self.app.clients.get(cid).config.get("organization"),version=base,job=ctx.job_id,event=uid)
            notice(db, "Client contribution received · " + cid + " · " + digest)
        return uid, update, keys

    def local_job(self, ctx, p):
        with self.lock:
            m = self.checked_base(p["model"], p["base"])
            ref = self.reference(m["id"])
            w = self.weights(p["base"])
            for i, cid in enumerate(p["clients"]):
                ctx.progress(i / len(p["clients"]), "Training " + cid)
                member = self.row(
                    "SELECT * FROM central_member WHERE model=? AND client=?",
                    (m["id"], cid),
                )
                self.train_one(m, p["base"], member, ref, w, ctx, standalone=True)
        return {"base": p["base"], "clients": p["clients"]}

    def round_job(self, ctx, p):
        m = self.checked_base(p["model"], p["base"])
        exp = self.app.experiments.create(
            ExperimentCreate(
                name=m["name"] + " round",
                dataset_id=m["reference"],
                client_count=len(p["clients"]),
                config={"trigger": "manual", "central_model": m["id"]},
            )
        )
        self.app.jobs.attach_experiment(ctx.job_id, exp.id)
        self.app.experiments.set_state(
            exp.id, status=ExperimentStatus.RUNNING, started=True, job_id=ctx.job_id
        )
        try:
            result = self.aggregate(ctx, p, exp)
            self.app.experiments.set_state(
                exp.id, status=ExperimentStatus.SUCCEEDED, result=result, finished=True
            )
            return {
                "version": result["artifact"]["version"],
                "validation": result["validation"],
            }
        except Exception as exc:
            self.app.experiments.set_state(
                exp.id, status=ExperimentStatus.FAILED, finished=True, error=str(exc)
            )
            raise

    def aggregate(self, ctx, p, exp, events=(), rounds=1, epochs=None):
        try:
            return self._aggregate(ctx, p, exp, events, rounds, epochs)
        except Exception:
            with self.db() as db:
                db.execute(
                    "UPDATE central_update SET state='failed' WHERE job=? AND state='round'",
                    (ctx.job_id,),
                )
                notice(db, "Central aggregation failed · " + ctx.job_id)
            raise

    def _aggregate(self, ctx, p, exp, events, rounds, epochs):
        with self.lock:
            m = self.checked_base(p["model"], p["base"])
            ds, raw, prep = reference = self.reference(m["id"])
            weights = self.weights(p["base"])
            backend = KerasGRUBackend()
            scores = backend.predict(weights, prep.test_rows)
            before = compute_metrics(prep.test_labels, scores)
            matrix_before = dict(
                zip(
                    ("tp", "tn", "fp", "fn"),
                    confusion_counts(prep.test_labels, [int(p > 0.5) for p in scores]),
                )
            )
            initial = weight_digest(weights)
            ids = p["clients"]
            with self.db() as db:
                db.executemany(
                    "UPDATE central_member SET job=? WHERE client=? AND model=?",
                    [(ctx.job_id, cid, m["id"]) for cid in ids],
                )
            records = []
            contributions = []
            if events and not {0, 1}.issubset(
                {
                    label
                    for cid in ids
                    for label in self.local_data(
                        m,
                        self.row(
                            "SELECT * FROM central_member WHERE client=? AND model=?",
                            (cid, m["id"]),
                        ),
                        reference,
                        events,
                    )[1]
                }
            ):
                raise InputValidationError(
                    "Automatic retraining requires representative benign and attack records."
                )
            for n in range(rounds):
                round_started = time.monotonic()
                server = FLServer(
                    num_clients=len(ids),
                    threshold=len(ids),
                    expected_parameter_count=len(weights),
                    weighting="sample",
                )
                crypto = None
                if p["encrypted"]:
                    if p["action"] == "stored":
                        raise ConflictError(
                            "CKKS requires fresh worker updates under a common round key."
                        )
                    material = self.app.encryption.generate_key_material(
                        parties=len(ids), threshold=len(ids)
                    )
                    public = self.app.encryption.server_backend(material)
                    crypto = server, material, public
                updates = []
                seen = set()
                for i, cid in enumerate(ids):
                    ctx.progress(
                        (n + (i + 0.1) / len(ids)) / (rounds + 1),
                        "Collecting contribution from " + cid,
                    )
                    if not self.app.clients.pid(cid):
                        raise ConflictError("Selected worker disconnected.")
                    member = self.row(
                        "SELECT * FROM central_member WHERE model=? AND client=?",
                        (m["id"], cid),
                    )
                    if p["action"] == "stored":
                        saved = self.row(
                            "SELECT * FROM central_update WHERE model=? AND base=? AND client=? AND state='ready' ORDER BY ts DESC LIMIT 1",
                            (m["id"], p["base"], cid),
                        )
                        if saved["base_hash"] != weight_digest(weights):
                            raise ConflictError(
                                "Stored update does not match the selected base weight hash."
                            )
                        if saved["dataset"] != member["dataset"]:
                            raise ConflictError(
                                "Stored update dataset assignment changed."
                            )
                        uid = saved["id"]
                        update = ClientUpdate(
                            **json.loads(zlib.decompress(saved["body"]))
                        )
                        keys = json.loads(zlib.decompress(saved["samples"]))
                        if (
                            update.client_id != cid
                            or len(keys) != update.sample_count
                            or update.sample_count != saved["count"]
                            or update.digest != saved["digest"]
                        ):
                            raise InputValidationError(
                                "Stored contribution metadata mismatch."
                            )
                    else:
                        uid, update, keys = self.train_one(
                            m,
                            p["base"],
                            member,
                            reference,
                            weights,
                            ctx,
                            events,
                            crypto,
                            epochs,
                            n,
                        )
                    if seen.intersection(keys):
                        raise InputValidationError(
                            "Client datasets overlap. Assign distinct training records."
                        )
                    seen.update(keys)
                    contributions.append(uid)
                    updates.append(update)
                    if not crypto:
                        server.register_client(cid, update.sample_count)
                prev = weight_digest(weights)
                if crypto:
                    combined = server.aggregate_encrypted(updates, public)
                    if combined.aborted or combined.validation_errors:
                        raise ConflictError(
                            combined.reason or "Encrypted update validation failed."
                        )
                    if ciphertext_digest(combined.chunks) != combined.aggregate_digest:
                        raise ConflictError("Aggregate ciphertext digest mismatch.")
                    delta = self.app.encryption.client_keyring(
                        material
                    ).decrypt_aggregate(list(combined.chunks), len(weights))
                    weights = [a + b for a, b in zip(weights, delta, strict=True)]
                else:
                    combined = server.aggregate(updates)
                    if combined.aborted:
                        raise ConflictError(combined.reason)
                    weights = list(combined.weights)
                ctx.check_cancelled()
                scores = backend.predict(weights, prep.test_rows)
                after = compute_metrics(prep.test_labels, scores)
                matrix_after = dict(
                    zip(
                        ("tp", "tn", "fp", "fn"),
                        confusion_counts(
                            prep.test_labels, [int(p > 0.5) for p in scores]
                        ),
                    )
                )
                records.append(
                    dict(
                        round=n,
                        aborted=False,
                        updates=[u.as_dict() for u in updates],
                        scaling_factors=list(combined.scaling_factors),
                        aggregate_digest=combined.aggregate_digest,
                        global_hash_before=prev,
                        global_hash_after=weight_digest(weights),
                        metrics={
                            **after,
                            "round_index": n,
                            "f1_score": after["f1"],
                            "training_time_seconds": time.monotonic() - round_started,
                        },
                    )
                )
            with self.db() as db:
                pol = self.app.automatic.policy(db)
            gate = Policy.model_validate(p["policy"]) if "policy" in p else pol
            final_hash = weight_digest(weights)
            passed = gate.accepts(before, after, initial, final_hash)
            validation = dict(
                before=before,
                after=after,
                passed=passed,
                hash_before=initial,
                hash_after=final_hash,
                test_rows=len(prep.test_labels),
                source_sha256=ds.sha256,
                threshold=0.5,
                matrix_before=matrix_before,
                matrix_after=matrix_after,
            )
            result = dict(
                model={"name": "keras_gru"},
                central_model=m["id"],
                experiment_id=exp.id,
                dataset_id=ds.id,
                parent_version=p["base"],
                automatic=bool(events),
                trigger="automatic" if events else "manual",
                events=[e["id"] for e in events],
                encrypted=p["encrypted"],
                training_mode="federated_he" if crypto else "federated_plaintext",
                rounds=records,
                baseline_metrics=before,
                final_metrics=after,
                validation=validation,
            )
            result["round_metrics"] = [r["metrics"] for r in records]
            epoch_counts = {
                cid: epochs
                or self.row("SELECT epochs FROM central_member WHERE client=?", (cid,))[
                    "epochs"
                ]
                for cid in ids
            }
            result["local_epochs_by_client"] = epoch_counts
            result["local_epochs"] = (
                next(iter(epoch_counts.values()))
                if len(set(epoch_counts.values())) == 1
                else None
            )
            req = TrainingRequest(
                rounds=rounds,
                seed=prep.seed,
                test_size=prep.test_size,
                require_encryption=p["encrypted"],
            )
            artifact = self.app.training._write_artifacts(
                exp, ds, req, raw, prep, result, weights
            )
            version = self.app.models.register(result, artifact)
            artifact["version"] = version
            result["artifact"] = artifact
            with self.db() as db:
                db.execute("BEGIN IMMEDIATE")
                if (
                    db.execute(
                        "SELECT head FROM central_model WHERE id=?", (m["id"],)
                    ).fetchone()[0]
                    != p["base"]
                ):
                    raise ConflictError("Base changed during training.")
                number = db.execute(
                    "SELECT max(number)+1 FROM central_version WHERE model=?",
                    (m["id"],),
                ).fetchone()[0]
                db.execute(
                    "INSERT INTO central_version VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        version,
                        m["id"],
                        number,
                        p["base"],
                        "validated" if passed else "rejected",
                        json.dumps(artifact),
                        validation["hash_after"],
                        json.dumps(validation),
                        time.time(),
                        exp.id,
                        rounds,
                    ),
                )
                db.executemany(
                    "UPDATE central_update SET version=?,state='aggregated',body=NULL WHERE id=?",
                    [(version, u) for u in contributions],
                )
                for category in ("aggregation completed","candidate model generated","model validation passed" if passed else "model validation failed"):
                    audit(db,category,version=version,job=ctx.job_id,event=exp.id)
                notice(
                    db, "Aggregation completed · " + m["name"] + " · V" + str(number)
                )
                notice(
                    db,
                    ("Validation passed · " if passed else "Validation failed · ")
                    + version,
                )
            return result
