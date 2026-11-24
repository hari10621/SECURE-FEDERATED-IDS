from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.domain.federated import ReferenceLinearBackend
from app.main import create_app
from app.services.experiment_runner import run_paper_experiments

from .helpers import make_csv, upload_dataset


def _write_csv(path: Path, *, rows: int = 120, features: int = 4) -> Path:
    header = [f"f{index}" for index in range(features)] + ["Label"]
    lines = [",".join(header)]
    for index in range(rows):
        values = [str(((index * (position + 3)) % 19) / 10.0) for position in range(features)]
        values.append(str(index % 2))
        lines.append(",".join(values))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _settings(tmp_path: Path, *, enable_ckks: bool = False) -> Settings:
    return Settings(
        base_dir=tmp_path,
        data_dir=tmp_path / "var",
        database_url=f"sqlite:///{tmp_path / 'runner.db'}",
        research_repo_dir=tmp_path / "research",
        max_upload_bytes=16 * 1024 * 1024,
        max_csv_rows=10_000,
        max_csv_columns=128,
        enable_ckks=enable_ckks,
        training_max_rows=256,
    )


def test_runner_builds_comparison_summary_and_artifacts(tmp_path):
    dataset_path = _write_csv(tmp_path / "toy.csv")
    output = tmp_path / "out"
    summary = run_paper_experiments(
        dataset_path,
        "insdn",
        settings=_settings(tmp_path),
        rounds=1,
        local_epochs=1,
        batch_size=8,
        client_counts=(4,),
        include_he=False,
        backend_factory=ReferenceLinearBackend,
        output_dir=output,
    )

    assert summary["centralized"] is not None
    for key in ("accuracy", "precision", "recall", "f1"):
        assert key in summary["centralized"]
    assert set(summary["fl_plaintext"]) == {"4"}
    for key in ("accuracy", "precision", "recall", "f1"):
        assert key in summary["fl_plaintext"]["4"]

    directory = Path(summary["artifacts"]["centralized"]).parent
    assert (directory / "centralized.json").is_file()
    assert (directory / "fl_plaintext_n4.json").is_file()
    stored = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    assert stored["run_id"] == summary["run_id"]
    assert stored["fl_plaintext"]["4"]["accuracy"] is not None
    assert stored["plaintext_transmission"]["4"]["total_bytes_transmitted"] > 0


def test_runner_records_he_transmission_and_expansion_factor(tmp_path):
    pytest.importorskip("tenseal")
    dataset_path = _write_csv(tmp_path / "toy.csv")
    summary = run_paper_experiments(
        dataset_path,
        "insdn",
        settings=_settings(tmp_path, enable_ckks=True),
        rounds=1,
        local_epochs=1,
        batch_size=8,
        client_counts=(4,),
        include_he=True,
        backend_factory=ReferenceLinearBackend,
        output_dir=tmp_path / "out",
    )

    he = summary["fl_he"]["4"]
    assert he["available"] is True
    assert he["total_bytes_transmitted"] > 0
    assert he["avg_bytes_per_client_per_round"] > 0
    assert he["expansion_factor"] is not None and he["expansion_factor"] > 0
    assert summary["he_transmission"]["paper_claimed_expansion_factor"] == 16.57
    assert summary["he_transmission"]["observed_expansion_factor"]["4"] == he["expansion_factor"]


def _wait_for_job(client: TestClient, job_id: str, timeout: float = 60.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 200, response.text
        job = response.json()
        if job["status"] in {"succeeded", "failed", "cancelled"}:
            return job
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not finish")


def test_run_paper_suite_endpoint_starts_background_job(tmp_path):
    settings = _settings(tmp_path)
    app = create_app(settings)
    with TestClient(app) as client:
        app.state.federated.paper_suite_backend_factory = lambda: ReferenceLinearBackend()
        upload = upload_dataset(
            client,
            content=make_csv(rows=64, features=48),
        )
        assert upload.status_code == 201, upload.text
        dataset_id = upload.json()["id"]

        response = client.post(
            "/api/v1/experiments/run-paper-suite",
            json={
                "dataset_id": dataset_id,
                "rounds": 1,
                "local_epochs": 1,
                "batch_size": 8,
                "client_counts": [4],
                "include_he": False,
            },
        )
        assert response.status_code == 202, response.text
        job = _wait_for_job(client, response.json()["id"])
        assert job["status"] == "succeeded", job
        result = job["result"]
        assert "centralized" in result
        assert "fl_plaintext" in result
        assert "fl_he" in result
        assert result["fl_plaintext"]["4"]["accuracy"] is not None


def test_run_paper_suite_rejects_invalid_client_count(client):
    response = client.post(
        "/api/v1/experiments/run-paper-suite",
        json={"dataset_id": "missing", "client_counts": [5]},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
