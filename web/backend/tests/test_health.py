from __future__ import annotations

def test_health_ok(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["encryption"] == "unavailable"
    assert response.headers["X-Request-ID"]


def test_version(client):
    response = client.get("/api/v1/version")
    assert response.status_code == 200
    body = response.json()
    assert body["api_version"] == "v1"
    assert body["version"] == "0.1.0"


def test_request_id_is_echoed(client):
    response = client.get("/api/v1/health", headers={"X-Request-ID": "abc-123"})
    assert response.headers["X-Request-ID"] == "abc-123"


def test_invalid_csv_is_rejected_with_envelope(client):
    response = client.post(
        "/api/v1/datasets",
        files={"file": ("bad.csv", b"a,b\n1,not-a-label\n", "text/csv")},
        data={"dataset_type": "insdn", "name": "bad"},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert isinstance(body["error"]["details"], list)
