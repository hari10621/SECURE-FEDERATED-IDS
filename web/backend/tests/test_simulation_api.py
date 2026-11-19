from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

from .helpers import create_experiment, upload_dataset


def _simulation_settings(tmp_path) -> Settings:
    return Settings(
        base_dir=tmp_path,
        data_dir=tmp_path / "var",
        database_url=f"sqlite:///{tmp_path / 'sim.db'}",
        research_repo_dir=tmp_path / "research",
        max_upload_bytes=64 * 1024,
        max_csv_rows=10_000,
        max_csv_columns=128,
        enable_research_execution=False,
        enable_simulation=True,
        enable_predictions=False,
        api_token=None,
        job_workers=1,
    )


def _wait_for_job(client: TestClient, job_id: str, timeout: float = 10.0) -> dict:
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


def test_simulation_disabled_fails_closed(client):
    experiment = _dataset_and_experiment(client)
    status_response = client.get(f"/api/v1/experiments/{experiment['id']}/status")
    assert status_response.status_code == 200
    assert status_response.json()["simulation_available"] is False
    assert "disabled" in status_response.json()["simulation_reason"].lower()

    response = client.post(f"/api/v1/experiments/{experiment['id']}/simulate")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "unavailable"
    assert client.get("/api/v1/jobs").json()["total"] == 0


def test_plaintext_simulation_completes_and_is_labelled(tmp_path):
    settings = _simulation_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        experiment = _dataset_and_experiment(client)

        status_response = client.get(f"/api/v1/experiments/{experiment['id']}/status")
        assert status_response.status_code == 200
        body = status_response.json()
        assert body["simulation_available"] is True
        assert body["execution_available"] is False

        response = client.post(
            f"/api/v1/experiments/{experiment['id']}/simulate",
            json={"rounds": 3, "local_epochs": 1, "learning_rate": 0.1, "seed": 3},
        )
        assert response.status_code == 200, response.text
        job = _wait_for_job(client, response.json()["id"])
        assert job["status"] == "succeeded", job
        assert job["progress"] == 1.0

        detail = client.get(f"/api/v1/experiments/{experiment['id']}").json()
        assert detail["status"] == "succeeded"
        result = detail["result"]
        assert result["mode"] == "plaintext_simulation"
        assert result["encrypted"] is False
        assert result["encryption_claimed"] is False
        assert result["parity"] == "unverified"
        assert result["model"]["research_model"] is False
        assert result["crypto"]["available"] is False
        assert len(result["rounds"]) == 3
        assert "accuracy" in result["final_metrics"]
        assert result["legacy_differences"]


def test_simulation_rejects_invalid_request(tmp_path):
    settings = _simulation_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        experiment = _dataset_and_experiment(client)
        response = client.post(
            f"/api/v1/experiments/{experiment['id']}/simulate",
            json={"rounds": 0},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"


def test_simulation_row_cap_fails_closed(tmp_path):
    settings = _simulation_settings(tmp_path).model_copy(
        update={"simulation_max_rows": 2}
    )
    with TestClient(create_app(settings)) as client:
        experiment = _dataset_and_experiment(client)
        response = client.post(f"/api/v1/experiments/{experiment['id']}/simulate")
        assert response.status_code == 200
        job = _wait_for_job(client, response.json()["id"])
        assert job["status"] == "failed"
        detail = client.get(f"/api/v1/experiments/{experiment['id']}").json()
        assert detail["status"] == "failed"
        assert "simulation failed" in (detail["error"] or "").lower()
