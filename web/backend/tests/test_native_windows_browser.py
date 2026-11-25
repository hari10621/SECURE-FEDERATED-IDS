"""Real Windows launchers and browser; all runtime files go to pytest's temporary directory."""

import os
from pathlib import Path
import socket
import subprocess

import pytest


def free_ports():
    with socket.socket() as ui, socket.socket() as api:
        ui.bind(("127.0.0.1", 0))
        api.bind(("127.0.0.1", 0))
        return ui.getsockname()[1], api.getsockname()[1]


@pytest.mark.skipif(
    not os.getenv("SECUREFED_NATIVE_BROWSER"),
    reason="opt-in Windows launcher and Chrome tour",
)
def test_native_windows_browser(tmp_path):
    from playwright.sync_api import sync_playwright, expect

    root = Path(__file__).resolve().parents[3]
    ui, api = free_ports()
    env = {
        **os.environ,
        "SECUREFED_BASE_DIR": str(tmp_path),
        "SECUREFED_DATA_DIR": str(tmp_path / "var"),
        "SECUREFED_DATABASE_URL": "sqlite:///"
        + (tmp_path / "var" / "securefed.db").as_posix(),
        "SECUREFED_API_PORT": str(api),
        "SECUREFED_UI_PORT": str(ui),
    }

    def script(name):
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(root / name),
            ],
            cwd=root,
            env=env,
            check=True,
            timeout=150,
        )

    try:
        script("start_all.ps1")
        with sync_playwright() as driver:
            browser = driver.chromium.launch(channel="chrome")
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{ui}/sdn")
            expect(page.get_by_label("Network engine")).to_have_value(
                "Windows Native Simulation"
            )
            page.get_by_role("button", name="Create network", exact=True).click()
            page.get_by_role("button", name="start", exact=True).click()
            page.get_by_role("button", name="Start simulation", exact=True).click()
            expect(
                page.get_by_role("button", name="Normal ICMP", exact=False)
            ).to_be_visible(timeout=30000)
            page.get_by_label("Network engine").select_option(
                "Windows Live Traffic Capture"
            )
            expect(
                page.get_by_text("Passive interface capture", exact=True)
            ).to_be_visible()
            browser.close()
    finally:
        script("stop_services.ps1")
