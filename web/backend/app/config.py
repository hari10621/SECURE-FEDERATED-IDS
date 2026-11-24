"""Application configuration.

Configuration is intentionally small and explicit. Values are read from
``SECUREFED_*`` environment variables; secrets are never echoed back by the API.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator

WEB_DIR = Path(__file__).resolve().parents[2]
DEFAULT_RESEARCH_REPO = WEB_DIR.parent / "threshold-fl-ids-sdn"


def _env(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


class Settings(BaseModel):
    """Runtime settings for the backend.

    ``base_dir`` is the project's web directory. All writable application data
    must stay under ``data_dir``, which must stay under ``base_dir``.
    """

    app_name: str = "SecureFed-IDS API"
    version: str = "0.1.0"
    api_version: str = "v1"
    environment: str = "local"
    api_prefix: str = "/api/v1"

    base_dir: Path = Field(default=WEB_DIR)
    data_dir: Path | None = None
    database_url: str | None = None

    max_upload_bytes: int = Field(default=512 * 1024 * 1024, gt=0)
    max_csv_rows: int = Field(default=2_000_000, gt=0)
    max_csv_columns: int = Field(default=256, gt=1)
    simulation_max_rows: int = Field(default=50000, gt=0)
    training_max_rows: int = Field(default=5000, gt=0)

    research_repo_dir: Path = Field(default=DEFAULT_RESEARCH_REPO)
    research_python: str | None = None
    ckks_runtime_dir: Path | None = None
    enable_research_execution: bool = False
    enable_simulation: bool = False
    enable_training: bool = False
    enable_predictions: bool = False
    enable_ckks: bool = False
    ckks_backend: str = "tenseal"

    job_workers: int = Field(default=1, ge=1, le=8)
    api_token: str | None = None
    log_level: str = "INFO"

    @model_validator(mode="after")
    def _resolve_paths(self) -> "Settings":
        base = Path(self.base_dir).expanduser().resolve()
        data = Path(self.data_dir).expanduser().resolve() if self.data_dir else (base / "var").resolve()
        if not data.is_relative_to(base):
            raise ValueError("data_dir must be inside base_dir")
        object.__setattr__(self, "base_dir", base)
        object.__setattr__(self, "data_dir", data)
        object.__setattr__(self, "research_repo_dir", Path(self.research_repo_dir).expanduser().resolve())
        if self.ckks_runtime_dir is not None:
            object.__setattr__(
                self,
                "ckks_runtime_dir",
                Path(self.ckks_runtime_dir).expanduser().resolve(),
            )
        if self.database_url is None:
            db_path = (data / "securefed.db").as_posix()
            object.__setattr__(self, "database_url", f"sqlite:///{db_path}")
        if self.api_token is not None:
            token = self.api_token.strip()
            object.__setattr__(self, "api_token", token or None)
        return self

    @classmethod
    def from_env(cls) -> "Settings":
        values: dict[str, Any] = {}
        mapping = {
            "app_name": "SECUREFED_APP_NAME",
            "environment": "SECUREFED_ENVIRONMENT",
            "base_dir": "SECUREFED_BASE_DIR",
            "data_dir": "SECUREFED_DATA_DIR",
            "database_url": "SECUREFED_DATABASE_URL",
            "max_upload_bytes": "SECUREFED_MAX_UPLOAD_BYTES",
            "max_csv_rows": "SECUREFED_MAX_CSV_ROWS",
            "max_csv_columns": "SECUREFED_MAX_CSV_COLUMNS",
            "simulation_max_rows": "SECUREFED_SIMULATION_MAX_ROWS",
            "training_max_rows": "SECUREFED_TRAINING_MAX_ROWS",
            "research_repo_dir": "SECUREFED_RESEARCH_REPO_DIR",
            "research_python": "SECUREFED_RESEARCH_PYTHON",
            "ckks_runtime_dir": "SECUREFED_CKKS_RUNTIME_DIR",
            "enable_research_execution": "SECUREFED_ENABLE_RESEARCH_EXECUTION",
            "enable_simulation": "SECUREFED_ENABLE_SIMULATION",
            "enable_training": "SECUREFED_ENABLE_TRAINING",
            "enable_predictions": "SECUREFED_ENABLE_PREDICTIONS",
            "enable_ckks": "SECUREFED_ENABLE_CKKS",
            "ckks_backend": "SECUREFED_CKKS_BACKEND",
            "job_workers": "SECUREFED_JOB_WORKERS",
            "api_token": "SECUREFED_API_TOKEN",
            "log_level": "SECUREFED_LOG_LEVEL",
        }
        for field, env_name in mapping.items():
            raw = _env(env_name)
            if raw is not None:
                values[field] = raw
        return cls(**values)
