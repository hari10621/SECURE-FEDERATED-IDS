from __future__ import annotations

from app.enums import ExperimentStatus

from .helpers import create_experiment, make_csv, upload_dataset


def _create_dataset(client, *, dataset_type="insdn", features=48):
    response = upload_dataset(
        client,
        content=make_csv(features=features),
        dataset_type=dataset_type,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_experiment_lifecycle_and_unavailable_execution(client):
    dataset_id = _create_dataset(client)
    response = create_experiment(client, dataset_id)
    assert response.status_code == 201, response.text
    experiment = response.json()
    assert experiment["status"] == "created"
    assert experiment["job_id"] is None

    listed = client.get("/api/v1/experiments").json()
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == experiment["id"]

    detail = client.get(f"/api/v1/experiments/{experiment['id']}")
    assert detail.status_code == 200
    assert detail.json()["id"] == experiment["id"]

    status_response = client.get(f"/api/v1/experiments/{experiment['id']}/status")
    assert status_response.status_code == 200
    status_body = status_response.json()
    assert status_body["execution_available"] is False
    assert "disabled" in status_body["execution_reason"].lower()
    assert status_body["job"] is None

    start = client.post(f"/api/v1/experiments/{experiment['id']}/start")
    assert start.status_code == 503
    assert start.json()["error"]["code"] == "unavailable"
    assert client.get("/api/v1/jobs").json()["total"] == 0

    cancel = client.post(f"/api/v1/experiments/{experiment['id']}/cancel")
    assert cancel.status_code == 409


def test_experiment_rejects_non_research_dataset(client):
    dataset_id = _create_dataset(client, features=2)
    response = create_experiment(client, dataset_id)
    assert response.status_code == 422


def test_experiment_rejects_missing_script_variant(client):
    dataset_id = _create_dataset(client, dataset_type="cicids2017")
    response = create_experiment(client, dataset_id, client_count=8)
    assert response.status_code == 422
    assert "no allowlisted research script" in response.json()["error"]["message"]


def test_experiment_validation_errors_are_enveloped(client):
    response = client.post(
        "/api/v1/experiments",
        json={"name": "", "dataset_id": "missing", "client_count": 5},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_recover_interrupted_marks_active_experiments_failed(client):
    dataset_id = _create_dataset(client)
    created = create_experiment(client, dataset_id).json()
    service = client.app.state.experiments
    service.set_state(created["id"], status=ExperimentStatus.QUEUED)

    assert service.recover_interrupted() == 1
    detail = client.get(f"/api/v1/experiments/{created['id']}").json()
    assert detail["status"] == "failed"
    assert "restarted" in (detail["error"] or "").lower()
    assert detail["finished_at"] is not None
