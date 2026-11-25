import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from .helpers import upload_dataset, create_experiment
from .test_training_api import _training_settings, _wait_for_job


@pytest.mark.skipif(
    not os.environ.get("SECUREFED_RUN_TF_TESTS"), reason="real worker integration"
)
def test_review_queue_training_deployment_and_rollback(tmp_path):
    settings = _training_settings(tmp_path).model_copy(
        update={"enable_predictions": True, "max_upload_bytes": 100000}
    )
    app = create_app(settings)
    root = "/api/v1"
    with TestClient(app) as c:

        def post(path, body=None):
            response = c.post(root + path, json=body)
            response.raise_for_status()
            return response.json()

        def get(path):
            response = c.get(root + path)
            response.raise_for_status()
            return response.json()

        csv = Path(__file__).resolve().parents[3] / "datasets" / "insdn_compact_1k.csv"
        dataset = upload_dataset(
            c, content=b"\n".join(csv.read_bytes().splitlines()[:65])
        ).json()["id"]
        ids = [post("/clients", {"name": "Sensor " + str(n)})["id"] for n in (1, 2)]
        for cid in ids:
            post("/clients/" + cid + "/enable")
        exp = create_experiment(c, dataset, client_count=2).json()["id"]
        job = post(f"/experiments/{exp}/train", {"client_ids": ids, "rounds": 1})
        assert _wait_for_job(c, job["id"], 900)["status"] == "succeeded"
        original = get(f"/experiments/{exp}")["result"]["artifact"]["version"]
        post(f"/predictions/versions/{original}/deploy")
        post(
            f"/automation/clients/{ids[0]}/organization", {"name": "Test organization"}
        )
        held = post(f"/clients/{ids[0]}/attack-replay")["event_id"]
        review = lambda eid: post(
            f"/automation/events/{eid}/review",
            {"label": 1, "evidence": "Compared with stored source CSV annotation"},
        )
        review(held)
        assert get("/automation/status")["pending"] == 0
        sample = lambda offset: post(
            f"/automation/clients/{ids[0]}/training-sample?offset={offset}"
        )["event_id"]
        if os.getenv("SECUREFED_TEST_CONNECTED_LAB"):
            hosts = get("/sdn/inventory/hosts")["items"]
            host = next(h for h in hosts if h["connected"])
            path = "/sdn/hosts/" + host["name"]
            post(path + "/map/" + ids[0])
            capture = post(path + "/capture?normal_probe=true")
            assert capture["prediction"] is None
            assert any(
                e["origin"] == "live traffic" and e["host_ip"] == host["ip"]
                for e in get("/automation/events")
            )
            first = post(path + "/replay?partition=active_train")["event_id"]
            event = get("/automation/events/" + first)
            assert (event["host"], event["host_ip"], event["organization"]) == (
                host["name"],
                host["ip"],
                "Test organization",
            )
        else:
            first = sample(0)
        assert sample(0) == first
        for label in (-1, True, 0):
            assert (
                c.post(
                    root + f"/automation/events/{first}/review",
                    json={"label": label, "evidence": "CSV annotation"},
                ).status_code
                == 422
            )
        review(first)
        assert get("/automation/status")["pending"] == 1
        policy = {
            "enabled": True,
            "minimum": 1,
            "cooldown": 0,
            "auto_deploy": True,
            "allowed_f1_drop": 1,
        }
        post(f"/clients/{ids[1]}/disable")
        post("/automation/policy", policy)
        app.state.automatic.tick()
        assert not get("/automation/status")["runs"]
        post(f"/clients/{ids[1]}/enable")

        def wait_run(event):
            limit = time.monotonic() + 360
            while time.monotonic() < limit:
                for run in get("/automation/status")["runs"]:
                    if event in run["events"] and run["job"]:
                        _wait_for_job(c, run["job"], 900)
                        return next(
                            r
                            for r in get("/automation/status")["runs"]
                            if r["id"] == run["id"]
                        )
                time.sleep(0.3)
            pytest.fail("Automatic run did not start")

        run = wait_run(first)
        assert run["state"] == "deployed", run
        assert len(run["acks"]) == 2
        assert run["validation"]["hash_before"] != run["validation"]["hash_after"]
        assert run["validation"]["test_rows"] > 0
        assert get("/predictions/status")["version"] == run["candidate"]
        post("/automation/policy", {**policy, "encrypted": True})
        second = sample(1)
        review(second)
        failed = wait_run(second)
        assert failed["state"] == "failed" and "CKKS" in failed["detail"]
        assert get("/predictions/status")["version"] == run["candidate"]
        from app.services.encryption_service import EncryptionService

        app.state.encryption = EncryptionService(
            settings.model_copy(update={"enable_ckks": True})
        )
        app.state.training.encryption = app.state.encryption
        if app.state.encryption.is_available():
            post(
                "/automation/policy",
                {**policy, "encrypted": True, "minimum_accuracy_gain": 1},
            )
            third = sample(2)
            review(third)
            rejected = wait_run(third)
            assert rejected["state"] == "rejected", rejected
            assert (
                rejected["validation"]["hash_before"]
                != rejected["validation"]["hash_after"]
            )
            assert not rejected["validation"]["passed"]
            result = get("/experiments/" + rejected["experiment"])["result"]
            assert result["training_mode"] == "federated_he"
            assert result["rounds"][0]["aggregate_ciphertext_bytes"] > 0
            assert {u["client_id"] for u in result["rounds"][0]["updates"]} == set(ids)
            assert (
                c.post(
                    root + f"/predictions/versions/{rejected['candidate']}/deploy"
                ).status_code
                >= 400
            )
            assert get("/predictions/status")["version"] == run["candidate"]
        post(f"/predictions/versions/{original}/deploy")
        assert get("/predictions/status")["version"] == original
        assert get("/automation/notifications")["unread"] >= 8
        post("/automation/notifications/0/read")
        assert get("/automation/notifications")["unread"] == 0
