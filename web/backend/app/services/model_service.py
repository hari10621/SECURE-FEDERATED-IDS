"""Validate, version and atomically activate local GRU artifacts."""
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from threading import RLock
from uuid import uuid4

from ..config import Settings
from ..domain.dataset import ScalerStats, apply_scaler
from ..domain.federated.keras_backend import KerasGRUBackend
from ..domain.model import ARTIFACT_FORMAT, parameter_specs
from ..errors import AppError, InputValidationError, UnavailableError
from ..storage.paths import StoragePaths

LABELS = {"0": "Benign", "1": "Attack"}


def atomic_json(path, value):
    tmp = path.with_name(uuid4().hex + ".tmp")
    tmp.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


class ModelService:
    def __init__(self, settings: Settings, paths: StoragePaths):
        self.settings = settings
        self.paths = paths
        self.active = paths.models_dir / "manifest.json"
        self.registry = paths.models_dir / "versions"
        self.lock = RLock()
        self.cached = None

    def artifact(self, path, digest):
        data = self.paths.model_path(path).read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise UnavailableError(f"Checksum mismatch for {path}")
        return json.loads(data)

    def _bundle(self, m, force=False):
        try:
            if "preprocessing_sha256" not in m:
                raise UnavailableError("Manifest lacks a verified preprocessing file and SHA-256.")
            weights = self.artifact(m["model_path"], m["sha256"])
            prep = self.artifact(m["preprocessing"], m["preprocessing_sha256"])
            key = (m["sha256"], m["preprocessing_sha256"])
            if not force and self.cached and self.cached[0] == key:
                return self.cached[1]
            meta = weights["metadata"]
            names = prep["feature_names"]
            stats = ScalerStats(**prep["prepared"]["scaler"])
            specs = [{"name": p.name, "shape": list(p.shape)} for p in parameter_specs(48)]
            if (weights["format"] != ARTIFACT_FORMAT or weights["model"] != "keras_gru"
                    or weights["input_features"] != 48 or weights["parameter_specs"] != specs
                    or prep["format"] != "securefed-preprocessing-v1"
                    or names != prep["dataset"]["feature_names"] or len(set(names)) != 48 or len(names) != 48
                    or meta["experiment_id"] != prep["experiment_id"] or meta["dataset_id"] != prep["dataset_id"]
                    or prep.get("labels", LABELS) != LABELS or len(stats.means) != 48 or len(stats.scales) != 48
                    or not all(math.isfinite(x) for x in stats.means + weights["weights"])
                    or not all(math.isfinite(x) and x > 0 for x in stats.scales)):
                raise UnavailableError("Model architecture, feature schema, provenance or scaler is incompatible.")
            backend = KerasGRUBackend()
            model = backend.load_model(weights["weights"], 48, backend.learning_rate)
            if tuple(model.input_shape[1:]) != (1, 48) or model.output_shape[-1] != 1:
                raise UnavailableError("Unexpected GRU input or output shape.")
            bundle = (model, weights, prep, stats)
            self.cached = key, bundle
            return bundle
        except UnavailableError:
            raise
        except (OSError, ValueError, KeyError, TypeError, AppError) as exc:
            raise UnavailableError(f"Invalid model bundle: {exc}") from exc

    def current(self, force=False):
        if not self.settings.enable_predictions:
            raise UnavailableError("Prediction is disabled.")
        with self.lock:
            try:
                manifest = json.loads(self.active.read_bytes())
            except (OSError, ValueError) as exc:
                raise UnavailableError("No readable active manifest. Deploy a validated experiment.") from exc
            return manifest, self._bundle(manifest, force)

    def register(self, result, artifact, trained_at=None):
        version = Path(artifact["directory"]).name
        m = {"central_model":result.get("central_model"),"automatic": bool(result.get("automatic")), "version": version, "experiment_id": result["experiment_id"],
             "trained_at": trained_at or datetime.now(timezone.utc).isoformat(),
             "participants": [u["client_id"] for u in result["rounds"][-1]["updates"]]
                             if isinstance(result["rounds"], list) and result["rounds"] else [],
             "model_path": Path(artifact["weights_file"]).relative_to("models").as_posix(),
             "sha256": artifact["weights_sha256"],
             "preprocessing": Path(artifact["preprocessing_file"]).relative_to("models").as_posix(),
             "preprocessing_sha256": artifact["preprocessing_sha256"]}
        with self.lock:
            self._bundle(m, force=True)
            self.registry.mkdir(exist_ok=True)
            path = self.registry / (version + ".json")
            if path.exists():
                old = json.loads(path.read_bytes())
                if old["sha256"] != m["sha256"] or old["preprocessing_sha256"] != m["preprocessing_sha256"]:
                    raise UnavailableError("Registered version already has different checksums.")
            else:
                atomic_json(path, m)
        return version

    def deploy(self, version):
        if not self.settings.enable_predictions:
            raise UnavailableError("Prediction is disabled.")
        if not re.fullmatch("[a-f0-9]{32}", version):
            raise InputValidationError("Invalid model version")
        with self.lock:
            path = self.registry / (version + ".json")
            if not path.is_file():
                raise UnavailableError("Model version is not registered.")
            candidate = json.loads(path.read_bytes())
            if candidate.get("central_model"):
                with self.automatic.db() as db:
                    v=db.execute("SELECT v.state,v.parent,m.head FROM central_version v JOIN central_model m ON m.id=v.model WHERE v.version=?",(version,)).fetchone()
                    if not v or (v["state"]!="deployed" and (v["state"]!="validated" or v["parent"]!=v["head"])):
                        raise UnavailableError("Central version is unvalidated, stale, or rejected.")
            if candidate.get("automatic") and not self.automatic.deployable(version):
                raise UnavailableError("Automatic candidate has no passing validation gate.")
            self._bundle(candidate, force=True)
            if self.active.is_file():
                archive = self.paths.models_dir / ("manifest-" + hashlib.sha256(self.active.read_bytes()).hexdigest() + ".json")
                if not archive.exists():
                    archive.write_bytes(self.active.read_bytes())
            atomic_json(self.active, candidate)
            if hasattr(self,"automatic"):
                self.automatic.deployment(version)
            return self.status()

    def status(self, force=False):
        try:
            m, (_, weights, prep, _) = self.current(force)
        except UnavailableError as exc:
            return dict(available=False, reason=str(exc), model=None, preprocessing=None)
        return dict(available=True, reason="Model and preprocessing validated.", model=weights["model"],
                    preprocessing=m["preprocessing"], version=m.get("version"), sha256=m["sha256"],
                    source_experiment=prep["experiment_id"], trained_at=m.get("trained_at"),
                    rounds=weights["metadata"]["rounds"], participants=m.get("participants", []),
                    features=prep["feature_names"], feature_count=48, labels=LABELS, dataset_id=prep["dataset_id"])

    def predict(self, features):
        m, (model, _, _, stats) = self.current()
        if len(features) != 48 or not all(math.isfinite(v) for v in features):
            raise InputValidationError("Enter exactly 48 finite raw features in training CSV order.")
        import numpy as np
        x = np.asarray(apply_scaler([features], stats), dtype="float32").reshape(1, 1, 48)
        probability = float(model(x, training=False).numpy()[0, 0])
        label = int(probability > 0.5)
        return dict(available=True, prediction=probability, label=label, class_name=LABELS[str(label)],
                    confidence=probability if label else 1-probability, version=m.get("version"))
