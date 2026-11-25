"""Opt-in browser tour against an isolated real API, the local dashboard and Mininet."""

import csv
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time

import httpx
import pytest


@pytest.mark.skipif(
    not os.getenv("SECUREFED_BROWSER_TEST"),
    reason="requires Chrome, Playwright, the dashboard and running Mininet lab",
)
def test_central_browser(tmp_path):
    from playwright.sync_api import sync_playwright, expect

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {
        **os.environ,
        "SECUREFED_BASE_DIR": str(tmp_path),
        "SECUREFED_DATA_DIR": str(tmp_path / "var"),
        "SECUREFED_DATABASE_URL": "sqlite:///" + (tmp_path / "app.db").as_posix(),
        "SECUREFED_ENABLE_TRAINING": "true",
        "SECUREFED_ENABLE_PREDICTIONS": "true",
        "SECUREFED_ENABLE_CKKS": "true",
    }
    backend = Path(__file__).resolve().parents[1]
    base = f"http://127.0.0.1:{port}"
    with (tmp_path / "api.log").open("w", encoding="utf8") as log:
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=backend,
            env=env,
            stdout=log,
            stderr=log,
        )
        try:
            for _ in range(120):
                try:
                    if httpx.get(base + "/api/v1/health").is_success:
                        break
                except httpx.ConnectError:
                    pass
                time.sleep(0.25)
            dataset = backend.parents[1] / "datasets" / "insdn_compact_1k.csv"
            data = b"\n".join(dataset.read_bytes().splitlines()[:65])
            upload = httpx.post(
                base + "/api/v1/datasets",
                files={"file": ("tour.csv", data, "text/csv")},
                data={"dataset_type": "insdn", "name": "Browser reference"},
            )
            upload.raise_for_status()
            with sync_playwright() as driver:
                browser = driver.chromium.launch(
                    channel=os.getenv("SECUREFED_BROWSER_CHANNEL", "chrome"),
                    headless=True,
                )
                page = browser.new_page()
                page.set_default_timeout(40000)
                page.add_init_script(
                    "localStorage.setItem('securefed.console.api.v1',"
                    + json.dumps(json.dumps({"baseUrl": base, "token": ""}))
                    + ")"
                )
                page.goto("http://127.0.0.1:5173/central-model")

                def navigate(name):
                    page.get_by_role("navigation", name="Primary").get_by_role(
                        "link", name=name, exact=True
                    ).click()

                def button(text):
                    return page.get_by_role("button", name=text, exact=True)

                page.get_by_label("Model name", exact=True).fill("Browser GRU")
                button("Create V0").click()
                expect(page.get_by_text("V0 initialized.", exact=True)).to_be_visible(
                    timeout=120000
                )
                navigate("Federated Clients")
                for n in (1, 2):
                    page.get_by_label("New client name").fill(f"Browser worker {n}")
                    page.get_by_label("Organization", exact=True).fill(f"Lab {n}")
                    page.get_by_label("SDN host", exact=True).select_option(f"h{n}")
                    button("Save client assignment").click()
                    expect(
                        page.get_by_role("status").filter(has_text="succeeded").first
                    ).to_be_visible(timeout=240000)
                    expect(
                        page.get_by_text(
                            f"Browser worker {n} · Lab {n}", exact=False
                        ).first
                    ).to_be_visible()
                navigate("Federated Training")
                page.get_by_label("Enable automatic retraining").check()
                page.get_by_label("Verified attack threshold").fill("1")
                page.get_by_label("Cooldown (seconds)").fill("0")
                page.get_by_label("Allowed F1 decrease").fill("1")
                page.get_by_label("Deploy after validation").check()
                page.get_by_label("Require CKKS", exact=True).check()
                button("Save policy").click()
                expect(page.get_by_text("Policy saved", exact=True)).to_be_visible()
                for n in (1, 2):
                    page.get_by_role(
                        "checkbox", name=re.compile(f"Browser worker {n}")
                    ).check()
                button("Run selected operation").click()
                expect(
                    page.get_by_role("status").filter(has_text="succeeded").first
                ).to_be_visible(timeout=240000)
                navigate("Central Model")
                button("Deploy validated version").click()
                expect(
                    page.get_by_text(re.compile("Completed deploy for V1"))
                ).to_be_visible(timeout=90000)
                navigate("SDN Network")
                page.get_by_label("Lab host", exact=True).select_option("h1")
                page.get_by_label(
                    "Replay training partition for independent review"
                ).check()
                button("Replay labeled attack").click()
                expect(
                    page.get_by_text(re.compile("Recorded attack row"))
                ).to_be_visible()
                navigate("Security Monitoring")
                page.get_by_role(
                    "button", name=re.compile("Lab 1.*dataset training")
                ).first.click()
                row_text = page.get_by_text(re.compile("Source CSV row")).text_content()
                ordinal = int(re.search(r"row (\d+)", row_text).group(1))
                truth = list(csv.DictReader(data.decode("utf-8-sig").splitlines()))[
                    ordinal - 2
                ]
                assert int(truth.get("Label", truth.get("label"))) == 1
                page.get_by_label("Reviewed label").select_option("1")
                page.get_by_label("Independent label evidence").fill(
                    f"Checked tour.csv row {ordinal}, label 1"
                )
                button("Verify sample").click()
                expect(page.get_by_text("Review saved", exact=True)).to_be_visible()
                navigate("Central Model")
                expect(page.get_by_text(re.compile("Deployed · V2"))).to_be_visible(
                    timeout=420000
                )
                button("Synchronize workers").click()
                expect(
                    page.get_by_text(re.compile("Completed sync for V2"))
                ).to_be_visible(timeout=90000)
                model = httpx.get(base + "/api/v1/central-models").json()[0]
                details = httpx.get(
                    base + "/api/v1/central-models/" + model["id"]
                ).json()
                assert len({v["weight_hash"] for v in details["versions"]}) == 3
                v2, v1, _ = details["versions"]
                assert v2["validation"]["before"] == v1["validation"]["after"]
                assert (
                    len([a for a in details["acks"] if a["version"] == v2["version"]])
                    == 2
                )
                result = httpx.get(
                    base + "/api/v1/experiments/" + v2["experiment"]
                ).json()["result"]
                assert result["encrypted"] and all(
                    u["chunk_count"] > 0 for u in result["rounds"][0]["updates"]
                )
                browser.close()
        finally:
            server.terminate()
            server.wait(timeout=30)
