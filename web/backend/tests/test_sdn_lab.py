"""SDN API trust boundary, schema and counter collection regressions."""

from app.services.sdn_service import FEATURES


def test_unconfigured_agent_never_reports_mock_connection(client, monkeypatch):
    monkeypatch.delenv("SECUREFED_LAB_TOKEN", raising=False)
    monkeypatch.setenv("SECUREFED_SDN_MODE", "mock")
    status = client.get("/api/v1/sdn/status").json()
    assert status["available"] is False and status["state"] == "unavailable"
    snapshot = client.get("/api/v1/sdn/topology").json()
    assert snapshot["packets"] is None and snapshot["hosts"] == []
    assert client.post("/api/v1/sdn/lab/start").status_code == 503


def test_lab_operations_are_restricted(client):
    assert client.post("/api/v1/sdn/lab/anything").status_code == 422
    assert (
        client.post(
            "/api/v1/sdn/lab/start", headers={"Origin": "https://example.org"}
        ).status_code
        == 403
    )
    assert (
        client.post("/api/v1/sdn/lab/create", json={"hosts": 10000}).status_code == 422
    )
    assert client.post("/api/v1/ips/mitigate", json={}).json()["enforced"] is False


def test_live_window_schema():
    assert len(set(FEATURES)) == 48
    assert FEATURES[0] == "interval_01_tx_packets_per_second"
    assert FEATURES[-1] == "interval_12_rx_bytes_per_second"


def test_reviewed_counter_windows_train_and_score_in_isolated_database(
    tmp_path, monkeypatch
):
    import os
    import pytest
    from fastapi.testclient import TestClient
    from app.domain.model import keras_available
    from app.main import create_app
    from .test_training_api import _training_settings, _wait_for_job
    from .helpers import create_experiment

    if not keras_available() or not os.getenv("SECUREFED_RUN_TF_TESTS"):
        pytest.skip("Requires TensorFlow integration tests")
    settings = _training_settings(tmp_path).model_copy(
        update={"enable_predictions": True}
    )
    app = create_app(settings)
    with TestClient(app) as client:
        service = app.state.sdn
        # Deterministic protocol fixtures, only inside this temporary database.
        rows = [{"name": name, "connected": True} for name in ("h1", "h2")]
        count = 0

        def agent(action, payload=None):
            nonlocal count
            if action == "snapshot":
                return {
                    "protocol": "securefed-lab-v1",
                    "lab_id": "test",
                    "state": "connected",
                    "reason": "test protocol fixture",
                    "hosts": [dict(r) for r in rows],
                }
            assert action == "capture"
            count += 1
            return {
                "features": [float(count + i) for i in range(48)],
                "observed_flows": [],
            }

        monkeypatch.setattr(service, "call", agent)
        ids = []
        for host in ("h1", "h2"):
            worker = client.post("/api/v1/clients", json={"name": host}).json()["id"]
            ids.append(worker)
            client.post(f"/api/v1/clients/{worker}/enable").raise_for_status()
            client.post(f"/api/v1/sdn/hosts/{host}/map/{worker}").raise_for_status()
            for i in range(4):
                sample = client.post(f"/api/v1/sdn/hosts/{host}/capture").json()
                assert sample["prediction"] is None
                client.post(
                    f"/api/v1/sdn/samples/{sample['id']}/approve?label={i % 2}"
                ).raise_for_status()
        dataset = client.post("/api/v1/sdn/dataset").json()
        assert dataset["rows"] == 8
        exp = create_experiment(client, dataset["dataset_id"], client_count=2).json()[
            "id"
        ]
        job = client.post(
            f"/api/v1/experiments/{exp}/train", json={"client_ids": ids, "rounds": 1}
        ).json()
        assert _wait_for_job(client, job["id"], timeout=360)["status"] == "succeeded"
        result = client.get(f"/api/v1/experiments/{exp}").json()["result"]
        version = result["artifact"]["version"]
        client.post(f"/api/v1/predictions/versions/{version}/deploy").raise_for_status()
        capture = client.post("/api/v1/sdn/hosts/h1/capture").json()
        assert capture["prediction"]["version"] == version
        assert 0 <= capture["prediction"]["prediction"] <= 1
        assert (
            client.get("/api/v1/sdn/inventory/events").json()["items"][0]["kind"]
            == "live counters"
        )
