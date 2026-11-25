"""Replay a held-out synthetic attack flow against two successive global models."""
from pathlib import Path

from ..config import WEB_DIR
from ..domain.dataset import load_csv_dataset, preprocess
from ..domain.federated.independent_client import ProcessClient
from ..domain.federated.keras_backend import KerasGRUBackend
from ..domain.federated.round import FederatedConfig, FederatedHarness
from ..domain.model import keras_runtime_status
from ..errors import UnavailableError
from .client_service import ClientService
from .job_manager import JobContext


def run_client_tutorial(context: JobContext, clients: ClientService) -> dict:
    available, reason = keras_runtime_status()
    if not available:
        raise UnavailableError(reason)
    context.progress(0.03, "Preparing labeled synthetic flows")
    path = WEB_DIR.parent / "datasets" / "insdn_compact_1k.csv"
    loaded = load_csv_dataset(path)
    data = preprocess(loaded.rows, loaded.labels, feature_names=loaded.feature_names, seed=42)
    probe = data.test_labels.index(1)
    records = [
        clients.create(name=f"Tutorial {role} {context.job_id[:8]}",
                       config={"tutorial_job": context.job_id, "role": role})
        for role in ("sensor", "peer")
    ]
    sensor, peer = records
    backend = KerasGRUBackend()
    scores = []

    def replay(round_index, weights):
        context.progress(0.47 if round_index == 0 else 0.91,
                         f"Scoring the sensor's held-out attack flow after round {round_index + 1}")
        scores.append(backend.predict(weights, [data.test_rows[probe]])[0])

    def progress(fraction, message):
        context.check_cancelled()
        if "local training" in message:
            context.progress(0.12 + fraction * 0.92, message)

    harness = FederatedHarness(
        backend, FederatedConfig(num_clients=2, rounds=2, local_epochs=1,
                                 batch_size=64, learning_rate=0.0001, weighting="sample", seed=42),
        client_ids=[sensor.id, peer.id], client_factory=ProcessClient,
        after_aggregate=replay, progress=progress, abort_check=lambda: context.cancel_requested,
    )
    result = harness.run(data)
    if len(scores) != 2:
        raise UnavailableError("Both rounds must aggregate before comparing models.")
    comparisons = []
    for record, score in zip(result["rounds"], scores):
        update = next(item for item in record["updates"] if item["client_id"] == sensor.id)
        comparisons.append({
            "round": record["round"] + 1, "digest": record["aggregate_digest"],
            "score": score, "label": int(score > 0.5), "accuracy": record["metrics"]["accuracy"],
            "f1": record["metrics"]["f1_score"], "sensor_samples": update["sample_count"],
        })
    return {
        "sensor": {"id": sensor.id, "name": sensor.name}, "peer": {"id": peer.id, "name": peer.name},
        "dataset": path.name, "csv_row": data.split.test[probe] + 2, "true_label": 1,
        "test_rows": len(data.test_rows), "rounds": comparisons,
        "weights_changed": comparisons[0]["digest"] != comparisons[1]["digest"],
    }
