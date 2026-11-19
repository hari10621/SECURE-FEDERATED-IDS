from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        base_dir=tmp_path,
        data_dir=tmp_path / "var",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        research_repo_dir=tmp_path / "research",
        max_upload_bytes=64 * 1024,
        max_csv_rows=10_000,
        max_csv_columns=128,
        enable_research_execution=False,
        enable_predictions=False,
        api_token=None,
        job_workers=1,
    )


@pytest.fixture
def app(settings: Settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client
