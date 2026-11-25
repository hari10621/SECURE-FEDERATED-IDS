"""Opt-in browser regression using a private backup of an existing central model."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
from urllib.parse import urlsplit

import httpx
import pytest


@pytest.mark.skipif(
    not os.getenv("SECUREFED_COMPARISON_MODEL"),
    reason="requires saved versions, built UI and Chrome",
)
def test_saved_model_comparison(tmp_path):
    from playwright.sync_api import sync_playwright, expect

    web = Path(__file__).resolve().parents[2]
    src = web / "var"
    target = tmp_path / "var"
    target.mkdir()
    for name in ("sdn.sqlite3", "securefed.db"):
        with (
            sqlite3.connect((src / name).as_uri() + "?mode=ro", uri=True) as original,
            sqlite3.connect(target / name) as cloned,
        ):
            original.backup(cloned)
    for directory in ("models", "datasets", "uploads"):
        shutil.copytree(src / directory, target / directory)
    with sqlite3.connect(target / "sdn.sqlite3") as db:
        db.execute(
            "UPDATE auto_policy SET body=json_set(body,'$.enabled',json('false'),'$.auto_deploy',json('false'))"
        )
    with sqlite3.connect(target / "securefed.db") as db:
        db.execute("UPDATE clients SET status='disabled'")

    def fingerprint():
        return {
            p: hashlib.sha256(p.read_bytes()).digest()
            for directory in ("models", "datasets", "uploads")
            for p in (src / directory).rglob("*")
            if p.is_file()
        }

    before = fingerprint()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    api = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        "SECUREFED_DATA_DIR": str(target),
        "SECUREFED_BASE_DIR": str(tmp_path),
        "SECUREFED_DATABASE_URL": "sqlite:///" + (target / "securefed.db").as_posix(),
        "SECUREFED_ENABLE_TRAINING": "false",
    }
    with (tmp_path / "server.log").open("w") as log:
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)],
            cwd=web / "backend",
            env=env,
            stdout=log,
            stderr=log,
        )
        try:
            for _ in range(150):
                try:
                    if httpx.get(api + "/api/v1/health").is_success:
                        break
                except httpx.ConnectError:
                    pass
                time.sleep(0.2)
                assert server.poll() is None, (tmp_path / "server.log").read_text()
            models = api + "/api/v1/central-models"
            model = next(
                m
                for m in httpx.get(models).json()
                if m["name"] == os.environ["SECUREFED_COMPARISON_MODEL"]
            )
            url = models + "/" + model["id"]
            detail = httpx.get(url).json()
            candidate = next(
                v for v in detail["versions"] if v["parent"] and v["validation"]
            )
            parent = next(
                v for v in detail["versions"] if v["version"] == candidate["parent"]
            )
            report = httpx.get(url + "/evaluations").json()
            assert (
                report[parent["version"]]["metrics"]
                == candidate["validation"]["before"]
            ), report
            assert (
                report[candidate["version"]]["metrics"]
                == candidate["validation"]["after"]
            )
            print(
                "Held-out comparison",
                candidate["validation"],
                "class counts",
                report[candidate["version"]].get("classes"),
            )
            with sync_playwright() as driver:
                browser = driver.chromium.launch(channel="chrome", headless=True)
                ctx = browser.new_context(
                    permissions=["clipboard-read", "clipboard-write"]
                )
                page = ctx.new_page()
                page.set_default_timeout(20000)
                page.add_init_script(
                    "localStorage.setItem('securefed.console.api.v1',"
                    + json.dumps(
                        json.dumps({"baseUrl": "http://127.0.0.1:5173", "token": ""})
                    )
                    + ")"
                )

                def static(route):
                    relative = urlsplit(route.request.url).path.lstrip("/")
                    if relative.startswith("api/"):
                        response = route.fetch(
                            url=api
                            + "/"
                            + relative
                            + (
                                "?" + urlsplit(route.request.url).query
                                if urlsplit(route.request.url).query
                                else ""
                            )
                        )
                        route.fulfill(response=response)
                        return
                    asset = web / "frontend/dist" / relative
                    route.fulfill(
                        path=asset
                        if asset.is_file()
                        else web / "frontend/dist/index.html"
                    )

                page.route("http://127.0.0.1:5173/**", static)
                page.goto("http://127.0.0.1:5173/central-model")
                page.get_by_label("Central model", exact=True).select_option(
                    model["id"]
                )
                inspect = page.get_by_label("Inspect version", exact=True)
                compare = page.get_by_label("Compare with", exact=True)
                inspect.select_option(candidate["version"])
                compare.select_option(parent["version"])
                expect(
                    page.get_by_text("Weight hash changed", exact=True)
                ).to_be_visible()
                baseline = candidate["validation"]["before"]["accuracy"] * 100
                after = candidate["validation"]["after"]["accuracy"] * 100
                first = f"V{parent['number']} {baseline:.2f}% → V{candidate['number']} {after:.2f}%"
                expect(page.get_by_text(first, exact=True).first).to_be_visible()
                integrity = page.get_by_role("button", name="Verify artifact").first
                integrity.click()
                expect(
                    page.get_by_text("Artifact checksum verified", exact=False).first
                ).to_be_visible()
                page.get_by_role("button", name="Copy full hash").first.click()
                assert (
                    page.evaluate("navigator.clipboard.readText()")
                    == parent["weight_hash"]
                )
                page.get_by_role("button", name="View full hash").first.click()
                expect(
                    page.get_by_text(parent["weight_hash"], exact=True).first
                ).to_be_visible()
                contributions = [
                    u
                    for u in detail["contributions"]
                    if u["version"] == candidate["version"]
                    and u["state"] == "aggregated"
                ]
                last_round = max(u["round_number"] or 1 for u in contributions)
                current = [
                    u for u in contributions if (u["round_number"] or 1) == last_round
                ]
                expect(
                    page.locator("summary").filter(has_text="at training")
                ).to_have_count(len(current))
                for u in current:
                    name = next(
                        c["name"]
                        for c in detail["clients"]
                        if c["client"] == u["client"]
                    )
                    expect(
                        page.locator("summary").filter(
                            has_text=f"{name} · {u['organization']} at training"
                        )
                    ).to_be_visible()
                for version in (parent, candidate):
                    button = page.get_by_role(
                        "button", name=f"Evaluate V{version['number']} on holdout"
                    )
                    if button.count():
                        with page.expect_response(
                            lambda r: r.url.endswith("/evaluate-heldout"),
                            timeout=120000,
                        ) as receipt:
                            button.click()
                        receipt.value.finished()
                        result = receipt.value.json()
                        assert (
                            sum(result["matrix"].values())
                            == candidate["validation"]["test_rows"]
                        )
                        for metric in (
                            "accuracy",
                            "precision",
                            "recall",
                            "f1",
                            "false_positive_rate",
                        ):
                            assert result["metrics"][metric] == pytest.approx(
                                report[version["version"]]["metrics"][metric]
                            )
                inspect.select_option(parent["version"])
                compare.select_option(candidate["version"])
                reverse = f"V{candidate['number']} {after:.2f}% → V{parent['number']} {baseline:.2f}%"
                expect(page.get_by_text(reverse, exact=True).first).to_be_visible()
                page.set_viewport_size({"width": 390, "height": 840})
                # ResponsiveContainer observes the resize on the next animation frame.
                page.wait_for_function("document.documentElement.scrollWidth <= innerWidth",timeout=5000)
                page.goto("http://127.0.0.1:5173/training")
                field = page.get_by_label("Verified attack threshold", exact=False)
                field.fill("0")
                expect(page.get_by_role("button", name="Save policy")).to_be_disabled()
                field.fill("8")
                page.get_by_role("button", name="Save policy").click()
                expect(page.get_by_text("Policy saved", exact=True)).to_be_visible()
                assert (
                    httpx.get(api + "/api/v1/automation/status").json()["policy"][
                        "minimum"
                    ]
                    == 8
                )
                browser.close()
        finally:
            server.terminate()
            server.wait(timeout=30)
            assert before == fingerprint()
