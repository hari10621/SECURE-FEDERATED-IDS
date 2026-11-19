from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def _build_app(tmp_path, token: str):
    settings = Settings(
        base_dir=tmp_path,
        data_dir=tmp_path / "var",
        database_url=f"sqlite:///{tmp_path / 'auth.db'}",
        research_repo_dir=tmp_path / "research",
        api_token=token,
        max_upload_bytes=64 * 1024,
        enable_research_execution=False,
    )
    return create_app(settings)


def test_optional_bearer_token_protects_mutating_and_read_routes(tmp_path):
    app = _build_app(tmp_path, "top-secret-token")
    with TestClient(app) as client:
        assert client.get("/api/v1/health").status_code == 200

        missing = client.get("/api/v1/datasets")
        assert missing.status_code == 401
        assert missing.json()["error"]["code"] == "unauthorized"

        wrong = client.get(
            "/api/v1/datasets",
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert wrong.status_code == 401

        ok = client.get(
            "/api/v1/datasets",
            headers={"Authorization": "Bearer top-secret-token"},
        )
        assert ok.status_code == 200
        assert "top-secret-token" not in ok.text


def test_no_token_configuration_is_local_open(tmp_path):
    app = _build_app(tmp_path, "")
    with TestClient(app) as client:
        assert client.get("/api/v1/datasets").status_code == 200


def test_not_found_uses_error_envelope(client):
    response = client.get("/api/v1/datasets/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"
    assert "does-not-exist" in body["error"]["message"]


def test_validation_error_envelope(client):
    response = client.post(
        "/api/v1/datasets",
        data={"dataset_type": "not-a-real-type"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
