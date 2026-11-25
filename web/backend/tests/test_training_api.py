from __future__ import annotations

import csv
import json
import os
import random
import time
from pathlib import Path
from typing import Sequence

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.domain.model import keras_available, parameter_count, read_weight_artifact
from app.main import create_app

from .helpers import create_experiment, upload_dataset


class _FakeGRUBackend:
    """Harness double with GRU-sized weights; not a TensorFlow model."""

    name = "fake_gru"
    research_model = False

    def parameter_count(self, input_features: int) -> int:
        return parameter_count(input_features)

    def initial_weights(self, input_features: int) -> list[float]:
        return [0.0] * self.parameter_count(input_features)

    def train(
        self,
        weights: Sequence[float],
        rows: Sequence[Sequence[float]],
        labels: Sequence[int],
        *,
        epochs: int,
        batch_size: int,
        learning_rate: float,
        rng: random.Random,
    ) -> list[float]:
        return [float(value) for value in weights]

    def predict(
        self, weights: Sequence[float], rows: Sequence[Sequence[float]]
    ) -> list[float]:
        return [0.5 for _ in rows]


def _training_settings(tmp_path: Path, *, enabled: bool = True) -> Settings:
    return Settings(
        base_dir=tmp_path,
        data_dir=tmp_path / "var",
        database_url=f"sqlite:///{tmp_path / 'training.db'}",
        research_repo_dir=tmp_path / "research",
        max_upload_bytes=64 * 1024,
        max_csv_rows=10_000,
        max_csv_columns=128,
        enable_research_execution=False,
        enable_simulation=False,
        enable_training=enabled,
        enable_predictions=False,
        training_max_rows=64,
        api_token=None,
        job_workers=1,
    )


def _wait_for_job(client: TestClient, job_id: str, timeout: float = 20.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 200, response.text
        job = response.json()
        if job["status"] in {"succeeded", "failed", "cancelled"}:
            return job
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not finish")


def _dataset_and_experiment(client: TestClient):
    upload = upload_dataset(client)
    assert upload.status_code == 201, upload.text
    created = create_experiment(client, upload.json()["id"])
    assert created.status_code == 201, created.text
    return created.json()


def test_training_disabled_fails_closed(client):
    experiment = _dataset_and_experiment(client)
    status_response = client.get(f"/api/v1/experiments/{experiment['id']}/status")
    assert status_response.status_code == 200
    body = status_response.json()
    assert body["training_available"] is False
    assert "disabled" in body["training_reason"].lower()

    response = client.post(f"/api/v1/experiments/{experiment['id']}/train")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "unavailable"
    assert client.get("/api/v1/jobs").json()["total"] == 0


@pytest.mark.skipif(keras_available(), reason="TensorFlow is installed in this runtime")
def test_training_reports_missing_tensorflow(tmp_path):
    settings = _training_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        experiment = _dataset_and_experiment(client)
        status_response = client.get(f"/api/v1/experiments/{experiment['id']}/status")
        body = status_response.json()
        assert body["training_available"] is False
        assert "tensorflow" in body["training_reason"].lower()

        response = client.post(f"/api/v1/experiments/{experiment['id']}/train")
        assert response.status_code == 503
        assert "tensorflow" in response.json()["error"]["message"].lower()
        assert client.get("/api/v1/jobs").json()["total"] == 0


def test_training_completes_with_injected_backend_and_writes_artifacts(tmp_path):
    settings = _training_settings(tmp_path)
    app = create_app(settings)
    with TestClient(app) as client:
        app.state.training.backend_factory = lambda: _FakeGRUBackend()
        experiment = _dataset_and_experiment(client)

        response = client.post(
            f"/api/v1/experiments/{experiment['id']}/train",
            json={
                "mode": "clean",
                "rounds": 2,
                "local_epochs": 1,
                "learning_rate": 0.1,
                "seed": 5,
            },
        )
        assert response.status_code == 200, response.text
        job = _wait_for_job(client, response.json()["id"])
        assert job["status"] == "succeeded", job
        assert job["progress"] == 1.0

        detail = client.get(f"/api/v1/experiments/{experiment['id']}").json()
        assert detail["status"] == "succeeded"
        result = detail["result"]
        assert result["mode"] == "plaintext_federated_training"
        assert result["encrypted"] is False
        assert result["encryption_claimed"] is False
        assert result["parity"] == "unverified"
        assert result["workload"]["independent_clients"] is False
        assert len(result["rounds"]) == 2
        assert "accuracy" in result["final_metrics"]

        artifact = result["artifact"]
        assert artifact["encrypted"] is False
        weights_path = settings.data_dir / artifact["weights_file"]
        result_path = settings.data_dir / artifact["result_file"]
        preprocessing_path = settings.data_dir / artifact["preprocessing_file"]
        assert weights_path.is_file()
        assert result_path.is_file()
        assert preprocessing_path.is_file()
        assert weights_path.name == "insdn_4_model.json"

        stored = read_weight_artifact(weights_path)
        assert stored["input_features"] == 48
        assert stored["client_count"] == 4
        assert stored["parameter_count"] == parameter_count(48)
        assert len(stored["weights"]) == parameter_count(48)
        assert stored["metadata"]["experiment_id"] == experiment["id"]

        sidecar = json.loads(result_path.read_text(encoding="utf-8"))
        assert sidecar["mode"] == "plaintext_federated_training"
        preprocessing = json.loads(preprocessing_path.read_text(encoding="utf-8"))
        assert preprocessing["format"] == "securefed-preprocessing-v1"
        assert preprocessing["prepared"]["mode"] == "clean"


def test_centralized_training_pools_data_and_reports_metrics(tmp_path):
    settings = _training_settings(tmp_path)
    app = create_app(settings)
    with TestClient(app) as client:
        app.state.training.backend_factory = lambda: _FakeGRUBackend()
        experiment = _dataset_and_experiment(client)

        response = client.post(
            f"/api/v1/experiments/{experiment['id']}/train",
            json={
                "mode": "centralized",
                "rounds": 1,
                "local_epochs": 1,
                "batch_size": 512,
                "learning_rate": 0.1,
                "seed": 5,
            },
        )
        assert response.status_code == 200, response.text
        job = _wait_for_job(client, response.json()["id"])
        assert job["status"] == "succeeded", job

        detail = client.get(f"/api/v1/experiments/{experiment['id']}").json()
        assert detail["status"] == "succeeded"
        result = detail["result"]
        assert result["training_mode"] == "centralized"
        assert result["mode"] == "centralized_training"
        assert result["encrypted"] is False
        metrics = result["final_metrics"]
        for key in ("accuracy", "precision", "recall", "f1"):
            assert key in metrics

        artifact = result["artifact"]
        weights_path = settings.data_dir / artifact["weights_file"]
        assert weights_path.is_file()
        stored = read_weight_artifact(weights_path)
        assert len(stored["weights"]) == parameter_count(48)
        assert stored["metadata"]["training_mode"] == "centralized"

        preprocessing_path = settings.data_dir / artifact["preprocessing_file"]
        preprocessing = json.loads(preprocessing_path.read_text(encoding="utf-8"))
        assert preprocessing["prepared"]["mode"] == "clean"


def test_training_exposes_round_metrics_endpoint(tmp_path):
    settings = _training_settings(tmp_path)
    app = create_app(settings)
    with TestClient(app) as client:
        app.state.training.backend_factory = lambda: _FakeGRUBackend()
        experiment = _dataset_and_experiment(client)

        response = client.post(
            f"/api/v1/experiments/{experiment['id']}/train",
            json={
                "mode": "clean",
                "rounds": 2,
                "local_epochs": 1,
                "learning_rate": 0.1,
                "seed": 5,
            },
        )
        assert response.status_code == 200, response.text
        job = _wait_for_job(client, response.json()["id"])
        assert job["status"] == "succeeded", job

        metrics_response = client.get(
            f"/api/v1/experiments/{experiment['id']}/metrics"
        )
        assert metrics_response.status_code == 200, metrics_response.text
        round_metrics = metrics_response.json()["round_metrics"]
        assert len(round_metrics) == 2
        for entry in round_metrics:
            for key in (
                "round_index",
                "accuracy",
                "precision",
                "recall",
                "f1_score",
                "loss",
                "training_time_seconds",
                "aggregation_time_seconds",
                "bytes_transmitted_per_client",
            ):
                assert key in entry


def test_training_row_cap_fails_closed(tmp_path):
    settings = _training_settings(tmp_path).model_copy(
        update={"training_max_rows": 2}
    )
    app = create_app(settings)
    with TestClient(app) as client:
        app.state.training.backend_factory = lambda: _FakeGRUBackend()
        experiment = _dataset_and_experiment(client)
        response = client.post(f"/api/v1/experiments/{experiment['id']}/train")
        assert response.status_code == 200
        job = _wait_for_job(client, response.json()["id"])
        assert job["status"] == "failed"
        detail = client.get(f"/api/v1/experiments/{experiment['id']}").json()
        assert detail["status"] == "failed"
        assert "training failed" in (detail["error"] or "").lower()


def test_training_rejects_threshold_above_client_count(tmp_path):
    settings = _training_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        experiment = _dataset_and_experiment(client)
        response = client.post(
            f"/api/v1/experiments/{experiment['id']}/train",
            json={"threshold": 5},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"
        assert client.get("/api/v1/jobs").json()["total"] == 0


def test_encrypted_training_request_fails_closed(tmp_path):
    settings = _training_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        experiment = _dataset_and_experiment(client)
        response = client.post(
            f"/api/v1/experiments/{experiment['id']}/train",
            json={"require_encryption": True},
        )
        assert response.status_code == 503
        assert "ckks" in response.json()["error"]["message"].lower()
        assert client.get("/api/v1/jobs").json()["total"] == 0


@pytest.mark.skipif(
    not keras_available() or not os.environ.get("SECUREFED_RUN_TF_TESTS"),
    reason="set SECUREFED_RUN_TF_TESTS=1 in a TensorFlow runtime",
)
def test_real_keras_gru_training_completes(tmp_path):
    settings = _training_settings(tmp_path).model_copy(update={"enable_predictions": True, "max_upload_bytes": 2_000_000, "training_max_rows": 1000})
    with TestClient(create_app(settings)) as client:
        dataset = Path(__file__).resolve().parents[3] / "datasets" / "insdn_compact_1k.csv"
        uploaded = upload_dataset(client, content=dataset.read_bytes())
        uploaded.raise_for_status()
        experiment = create_experiment(client, uploaded.json()["id"]).json()
        ids = []
        pids = []
        for i in range(4):
            record = client.post("/api/v1/clients", json={"name": f"worker-{i}"}).json()
            enabled = client.post(f"/api/v1/clients/{record['id']}/enable").json()
            assert enabled["runtime_connected"]
            ids.append(record["id"])
            pids.append(enabled["worker_pid"])
        response = client.post(
            f"/api/v1/experiments/{experiment['id']}/train",
            json={
                "mode": "clean",
                "rounds": 2,
                "client_ids": ids,
                "local_epochs": 1,
                "batch_size": 64,
                "learning_rate": 0.0001,
                "seed": 7,
            },
        )
        assert response.status_code == 200, response.text
        job = _wait_for_job(client, response.json()["id"], timeout=360.0)
        assert job["status"] == "succeeded", job

        detail = client.get(f"/api/v1/experiments/{experiment['id']}").json()
        result = detail["result"]
        assert result["mode"] == "plaintext_federated_training"
        assert result["model"]["name"] == "keras_gru"
        assert result["model"]["research_model"] is True
        assert result["encrypted"] is False
        assert len(result["rounds"]) == 2
        assert all(not record["aborted"] and len(record["updates"]) == 4 for record in result["rounds"])
        assert result["rounds"][0]["aggregate_digest"] != result["rounds"][1]["aggregate_digest"]

        artifact = result["artifact"]
        weights_path = settings.data_dir / artifact["weights_file"]
        stored = read_weight_artifact(weights_path)
        assert stored["parameter_count"] == parameter_count(48)
        assert len(stored["weights"]) == parameter_count(48)
        with dataset.open(newline="") as stream:
            row = next(csv.DictReader(stream))
        features = [float(value) for key, value in row.items() if key != "Label"]
        assert not client.get("/api/v1/predictions/status").json()["available"]
        version = artifact["version"]
        assert client.post(f"/api/v1/predictions/versions/{version}/deploy").json()["version"] == version
        assert client.post("/api/v1/predictions/reload").json()["features"] == list(row)[:-1]
        for record in result["rounds"]:
            assert record["global_hash_before"] != record["aggregate_digest"]
            assert [u["worker_pid"] for u in record["updates"]] == pids
            assert [u["client_id"] for u in record["updates"]] == ids
            assert all(u["local_loss"] >= 0 for u in record["updates"])
        assert result["rounds"][0]["aggregate_digest"] == result["rounds"][1]["global_hash_before"]
        assert client.post("/api/v1/predictions/versions/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/deploy").status_code == 503
        assert client.get("/api/v1/predictions/status").json()["version"] == version
        for label in (0, 1):
            sample = client.get(f"/api/v1/datasets/{uploaded.json()['id']}/sample", params={"label": label}).json()
            assert sample["index"] in result["dataset"]["split"]["test"]
            assert sample["actual"] == label
            assert client.post("/api/v1/predictions", json={"features": sample["features"]}).json()["class_name"] in {"Benign", "Attack"}
        prediction = client.post("/api/v1/predictions", json={"features": features})
        prediction.raise_for_status()
        probability = prediction.json()["prediction"]
        assert 0 <= probability <= 1
        assert prediction.json()["label"] == int(probability > 0.5)
        ips = client.post("/api/v1/ips/detect", json={"features": features})
        ips.raise_for_status()
        assert ips.json()["available"] is True
        assert f"prediction={probability:.4f}" in ips.json()["reason"]
        for invalid in (features[:-1], features + [0], ["1"] * 48):
            assert client.post("/api/v1/predictions", json={"features": invalid}).status_code == 422
        replay = client.post(f"/api/v1/clients/{ids[0]}/attack-replay")
        replay.raise_for_status()
        receipt = replay.json()
        assert receipt["worker_pid"] == pids[0] and receipt["feature_count"] == 48
        assert receipt["actual"] == 1 and receipt["version"] == version
        assert receipt["csv_row"] - 2 in result["dataset"]["split"]["test"]
        assert 0 <= receipt["prediction"] <= 1
        offline = client.post("/api/v1/clients", json={"name": "offline"}).json()
        assert client.post(f"/api/v1/clients/{offline['id']}/attack-replay").status_code == 409
        dataset_id = uploaded.json()["id"]
        warm = create_experiment(client, dataset_id, name="Warm start").json()
        options = {"rounds": 1, "seed": 7, "mode": "clean", "client_ids": ids,
                   "initialize_from_active": True, "local_epochs": 1, "batch_size": 64}
        def assign(row_id):
            client.patch(f"/api/v1/clients/{ids[0]}", json={"config": {
                "assignment_dataset": dataset_id, "training_rows": [row_id]}}).raise_for_status()
        assign(result["dataset"]["split"]["train"][0])
        started = client.post(f"/api/v1/experiments/{warm['id']}/train", json=options)
        started.raise_for_status()
        completed = _wait_for_job(client, started.json()["id"], timeout=360)
        assert completed["status"] == "succeeded", completed
        updated = client.get(f"/api/v1/experiments/{warm['id']}").json()["result"]
        assert updated["parent_version"] == version
        assert updated["rounds"][0]["global_hash_before"] == result["rounds"][-1]["aggregate_digest"]
        candidate = updated["artifact"]["version"]
        assert client.get("/api/v1/predictions/status").json()["version"] == version
        for selected in (candidate, version):
            assert client.post(f"/api/v1/predictions/versions/{selected}/deploy").json()["version"] == selected
        invalid_prep = settings.data_dir / updated["artifact"]["preprocessing_file"]
        invalid_prep.write_bytes(invalid_prep.read_bytes() + b" ")
        assert client.post(f"/api/v1/predictions/versions/{candidate}/deploy").status_code == 503
        assert client.get("/api/v1/predictions/status").json()["version"] == version
        assign(result["dataset"]["split"]["test"][0])
        rejected = create_experiment(client, dataset_id, name="Held-out assignment").json()
        job_id = client.post(f"/api/v1/experiments/{rejected['id']}/train", json=options).json()["id"]
        assert _wait_for_job(client, job_id, timeout=360)["status"] == "failed"
        scaler_path = settings.data_dir / artifact["preprocessing_file"]
        scaler_path.write_bytes(scaler_path.read_bytes() + b" ")
        assert client.post("/api/v1/predictions", json={"features": features}).status_code == 503
