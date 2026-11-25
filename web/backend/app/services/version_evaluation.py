"""Read-only evaluation provenance for central GRU versions."""

import hashlib
import json
import math
import zlib
from pathlib import Path

from ..domain.federated.keras_backend import KerasGRUBackend
from ..domain.federated.client import weight_digest
from ..domain.metrics import compute_metrics, confusion_counts
from ..errors import AppError, InputValidationError

METRICS = ("accuracy", "precision", "recall", "f1", "false_positive_rate")
# The original central round writer used the compute_metrics default.
THRESHOLD = 0.5


def artifact(service, files, name):
    path = Path(files[name + "_file"]).relative_to("models").as_posix()
    return service.app.models.artifact(path, files[name + "_sha256"])


def protocol(side, dataset_id, checksum, threshold):
    prepared = side["prepared"]
    if side["dataset_id"] != dataset_id or prepared["mode"] != "clean":
        raise ValueError("Incompatible reference dataset or preprocessing mode.")
    inputs = [
        checksum,
        prepared["split"]["test"],
        side["feature_names"],
        prepared["scaler"],
        side["labels"],
        threshold,
    ]
    return hashlib.sha256(
        json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def valid_metrics(values):
    return isinstance(values, dict) and all(
        isinstance(values.get(key), (float, int))
        and math.isfinite(values[key])
        and 0 <= values[key] <= 1
        for key in METRICS
    )


def history(service, mid):
    model = service.model(mid)
    dataset = service.app.datasets.get(model["reference"])
    with service.db() as db:
        versions = [
            dict(r)
            for r in db.execute(
                "SELECT * FROM central_version WHERE model=? ORDER BY number", (mid,)
            )
        ]
    records = {}
    entries = {}
    for v in versions:
        vid = v["version"]
        record = records[vid] = {
            "metrics": None,
            "reason": "No compatible evaluation has been recorded.",
            "protocol": None,
        }
        try:
            files = json.loads(v["artifact"])
            side = artifact(service, files, "preprocessing")
            result = artifact(service, files, "result")
            if not isinstance(result, dict) or not isinstance(
                result.get("validation", {}), dict
            ):
                raise ValueError("Invalid saved evaluation record.")
            gate = result.get("validation", {})
            threshold = gate.get("threshold", THRESHOLD)
            record["protocol"] = protocol(side, dataset.id, dataset.sha256, threshold)
            record["test_rows"] = len(side["prepared"]["split"]["test"])
            record["threshold"] = threshold
            if v["parent"] is None:
                continue
            parent = entries.get(v["parent"])
            if (
                not parent
                or result["parent_version"] != parent["version"]
                or result["central_model"] != mid
                or result["experiment_id"] != v["experiment"]
                or result["dataset_id"] != dataset.id
                or gate["source_sha256"] != dataset.sha256
                or gate["test_rows"] != record["test_rows"]
                or gate["hash_after"] != v["digest"]
                or gate["hash_before"] != parent["digest"]
                or record["protocol"] != records[parent["version"]]["protocol"]
                or not valid_metrics(gate["before"])
                or not valid_metrics(gate["after"])
            ):
                raise ValueError("Version, weight or evaluation provenance differs.")
            record.update(
                metrics=gate["after"],
                source=f"V{v['number']} after training",
                reason=None,
                matrix=gate.get("matrix_after"),
                trigger=result["trigger"],
                participants=list(result["local_epochs_by_client"])
                if isinstance(result.get("local_epochs_by_client"), dict)
                else None,
            )
            base = records[parent["version"]]
            if base["metrics"] is None and parent["parent"] is None:
                base.update(
                    metrics=gate["before"],
                    source=f"V{v['number']} before training (parent V{parent['number']})",
                    reason=None,
                    matrix=gate.get("matrix_before"),
                )
        except (AppError, OSError, ValueError, KeyError, TypeError) as exc:
            record["reason"] = f"Evaluation evidence unavailable: {exc}"
        finally:
            entries[vid] = v
    # Older standalone local jobs retained exact row hashes but no class totals.
    # Recover totals only where every hash has a unique label in the verified CSV.
    sources = {}
    with service.db() as db:
        old = db.execute(
            """SELECT u.* FROM central_update u LEFT JOIN central_update_classes c
          ON c.id=u.id WHERE u.model=? AND u.state='aggregated' AND c.id IS NULL""",
            (mid,),
        ).fetchall()
    for update in old:
        try:
            if (
                not update["job"]
                or service.app.jobs.get(update["job"]).job_type != "central_local"
            ):
                continue
            dataset_id = update["dataset"]
            if dataset_id not in sources:
                _, raw = service.data(dataset_id)
                labels = {}
                for row, label in zip(raw.rows, raw.labels):
                    key = weight_digest(row)
                    labels[key] = label if labels.get(key, label) == label else None
                sources[dataset_id] = labels
            keys = json.loads(zlib.decompress(update["samples"]))
            values = [sources[dataset_id].get(key) for key in keys]
            if len(values) == update["count"] and all(v in (0, 1) for v in values):
                records[update["version"]].setdefault("classes", {})[update["id"]] = (
                    dict(benign=values.count(0), attack=values.count(1))
                )
        except (AppError, OSError, ValueError, KeyError, TypeError, zlib.error):
            continue
    return records


def evaluate(service, mid, vid):
    v = service.row(
        "SELECT * FROM central_version WHERE model=? AND version=?", (mid, vid)
    )
    ds, _, prep = service.reference(mid)
    saved = artifact(service, json.loads(v["artifact"]), "preprocessing")
    check = protocol(saved, ds.id, ds.sha256, THRESHOLD)
    if (
        saved["feature_names"] != prep.feature_names
        or saved["prepared"]["split"] != prep.split.as_dict()
        or saved["prepared"]["scaler"] != prep.scaler.as_dict()
        or saved["labels"] != {"0": "Benign", "1": "Attack"}
    ):
        raise InputValidationError(
            "Saved preprocessing differs from the fixed reference."
        )
    weights = service.weights(vid)
    if weight_digest(weights) != v["digest"]:
        raise InputValidationError("Saved weight digest mismatch.")
    scores = KerasGRUBackend().predict(weights, prep.test_rows)
    counts = confusion_counts(prep.test_labels, [int(p > THRESHOLD) for p in scores])
    return dict(
        metrics=compute_metrics(prep.test_labels, scores, threshold=THRESHOLD),
        matrix=dict(zip(("tp", "tn", "fp", "fn"), counts)),
        protocol=check,
        source="Explicit held-out evaluation",
        threshold=THRESHOLD,
        test_rows=len(scores),
        reason=None,
    )
