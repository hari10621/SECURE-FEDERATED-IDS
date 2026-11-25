import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from .helpers import upload_dataset
from .test_training_api import _training_settings, _wait_for_job


@pytest.mark.skipif(
    not os.environ.get("SECUREFED_RUN_TF_TESTS"), reason="requires real GRU workers"
)
def test_central_v0_v1_and_verified_v2(tmp_path):
    app = create_app(
        _training_settings(tmp_path).model_copy(
            update={
                "enable_predictions": True,
                "max_upload_bytes": 100000,
                "enable_ckks": True,
            }
        )
    )
    with TestClient(app) as c:
        root = "/api/v1"

        def post(url, body=None):
            r = c.post(root + url, json=body)
            assert r.is_success, r.text
            return r.json()

        def get(url):
            r = c.get(root + url)
            r.raise_for_status()
            return r.json()

        def done(job):
            record = _wait_for_job(c, job, 900)
            assert record["status"] == "succeeded", record

        csv = Path(__file__).resolve().parents[3] / "datasets" / "insdn_compact_1k.csv"
        ds = upload_dataset(
            c, content=b"\n".join(csv.read_bytes().splitlines()[:65])
        ).json()["id"]
        policy = {
            "minimum": 1,
            "enabled": True,
            "cooldown": 0,
            "allowed_f1_drop": 1,
            "auto_deploy": True,
        }
        post("/automation/policy", policy)
        model = post("/central-models", {"name": "Central lab", "dataset": ds})
        path = "/central-models/" + model["id"]
        v0 = model["version"]
        assert not get("/predictions/status")["available"]
        assert c.post(root + path + "/versions/" + v0 + "/deploy").status_code == 409
        ids = []
        for i in range(2):
            member = post(
                path + "/members",
                dict(
                    name="Lab " + str(i),
                    organization="Org " + str(i),
                    dataset=ds,
                    train=True,
                ),
            )
            ids.append(member["client"])
            done(member["job"])
        job = post(path + "/rounds", dict(action="stored", clients=ids, base=v0))
        done(job["job"])
        one = get(path)["versions"][0]
        assert one["number"] == 1 and one["state"] == "validated"
        v1 = one["version"]
        post(path + "/versions/" + v1 + "/deploy")
        assert (
            c.post(
                root + path + "/rounds",
                json=dict(action="stored", clients=ids, base=v0),
            ).status_code
            == 409
        )
        if os.getenv("SECUREFED_TEST_CONNECTED_LAB"):
            h = next(h for h in get("/sdn/inventory/hosts")["items"] if h["connected"])
            post("/sdn/hosts/" + h["name"] + "/map/" + ids[0])
            receipt = post("/sdn/hosts/" + h["name"] + "/replay?partition=active_train")
        else:
            receipt = post("/automation/clients/" + ids[0] + "/training-sample")
        assert receipt["actual"] == 1 and receipt["version"] == v1
        eid = receipt["event_id"]
        assert get("/automation/status")["pending"] == 0
        post(
            "/automation/events/" + eid + "/review",
            {
                "label": 1,
                "evidence": "Reviewed source CSV row " + str(receipt["csv_row"]),
            },
        )
        limit = time.monotonic() + 90
        while time.monotonic() < limit:
            runs = get("/automation/status")["runs"]
            if runs and runs[0]["job"]:
                break
            time.sleep(0.2)
        done(runs[0]["job"])
        dashboard = get(path)
        two, one, zero = dashboard["versions"]
        assert (
            two["number"] == 2
            and two["parent"] == v1
            and dashboard["deployed"] == two["version"]
        )
        assert len({v["weight_hash"] for v in (zero, one, two)}) == 3
        assert two["validation"]["before"] == one["validation"]["after"]
        assert (
            len([a for a in dashboard["acks"] if a["version"] == two["version"]]) == 2
        )
        assert len(dashboard["contributions"]) == 4 and all(
            r["duration"] > 0 for r in dashboard["contributions"]
        )
        assert eid in get("/experiments/" + two["experiment"])["result"]["events"]
        post(path + "/versions/" + v1 + "/rollback")
        post(path + "/versions/" + v1 + "/sync")
        assert get(path)["deployed"] == v1
        # Import the saved weight artifact and its original scaler/split.
        artifact = get("/experiments/" + one["experiment"])["result"]["artifact"]
        source = {
            "name": "Imported",
            "dataset": ds,
            "method": "import",
            "weights": json.loads(
                (tmp_path / "var" / artifact["weights_file"]).read_bytes()
            ),
            "preprocessing": json.loads(
                (tmp_path / "var" / artifact["preprocessing_file"]).read_bytes()
            ),
        }
        imported = post("/central-models", source)
        restored = post(
            "/central-models",
            {"name": "Restored", "dataset": ds, "method": "restore", "source": v1},
        )
        for copy in [imported, restored]:
            initial = get("/central-models/" + copy["id"])["versions"][0]
            assert (
                initial["state"] == "initialized"
                and initial["weight_hash"] == one["weight_hash"]
            )
        source["preprocessing"]["feature_names"].reverse()
        assert c.post(root + "/central-models", json=source).status_code == 422
        assert get("/predictions/status")["version"] == v1
