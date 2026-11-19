from __future__ import annotations


def test_client_crud_and_explicit_runtime_status(client):
    created = client.post(
        "/api/v1/clients",
        json={"name": "client-1", "config": {"dataset_type": "insdn"}},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "configured"

    listed = client.get("/api/v1/clients").json()
    assert listed["total"] == 1

    fetched = client.get(f"/api/v1/clients/{body['id']}")
    assert fetched.status_code == 200

    status_response = client.get(f"/api/v1/clients/{body['id']}/status")
    assert status_response.status_code == 200
    status_body = status_response.json()
    assert status_body["runtime_connected"] is False
    assert "Phase 3" in status_body["detail"]

    updated = client.patch(
        f"/api/v1/clients/{body['id']}",
        json={"status": "disabled"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "disabled"


def test_duplicate_client_name_conflicts(client):
    payload = {"name": "client-1", "config": {}}
    assert client.post("/api/v1/clients", json=payload).status_code == 201
    duplicate = client.post("/api/v1/clients", json=payload)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "conflict"
