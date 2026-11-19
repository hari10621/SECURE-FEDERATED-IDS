from __future__ import annotations


def test_prediction_is_explicitly_unavailable(client):
    status_response = client.get("/api/v1/predictions/status")
    assert status_response.status_code == 200
    body = status_response.json()
    assert body["available"] is False
    assert body["reason"]

    prediction = client.post("/api/v1/predictions", json={"features": [0.1, 0.2]})
    assert prediction.status_code == 503
    assert prediction.json()["error"]["code"] == "unavailable"


def test_encryption_and_sdn_are_fail_closed(client):
    encryption = client.get("/api/v1/encryption/status")
    assert encryption.status_code == 200
    assert encryption.json()["available"] is False
    assert "disabled" in encryption.json()["reason"].lower()

    sdn = client.get("/api/v1/sdn/status")
    assert sdn.status_code == 200
    assert sdn.json()["available"] is False
    assert "Phase 3" in sdn.json()["reason"]


def test_service_level_encryption_never_produces_ciphertext(client):
    encryption = client.app.state.encryption
    try:
        encryption.encrypt([1.0, 2.0])
    except Exception as exc:
        assert "unavailable" in str(exc).lower()
    else:  # pragma: no cover
        raise AssertionError("encryption.encrypt must fail closed")
