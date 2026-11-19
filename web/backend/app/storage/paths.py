"""Path confinement helpers.

Every writable path used by the backend must resolve beneath the configured
data directory. The research repository is read-only and is accessed only
through fixed, allowlisted filenames.
"""

from __future__ import annotations

from pathlib import Path

from ..config import Settings
from ..errors import ForbiddenError


class StoragePaths:
    def __init__(self, settings: Settings) -> None:
        assert settings.data_dir is not None
        self.base_dir = settings.base_dir.resolve()
        self.data_dir = settings.data_dir.resolve()
        self.datasets_dir = (self.data_dir / "datasets").resolve()
        self.uploads_dir = (self.data_dir / "uploads").resolve()
        self.runs_dir = (self.data_dir / "runs").resolve()
        self.models_dir = (self.data_dir / "models").resolve()
        self.ckks_dir = (
            settings.ckks_runtime_dir.resolve()
            if settings.ckks_runtime_dir is not None
            else (self.data_dir / "ckks").resolve()
        )

    def ensure(self) -> None:
        for path in (
            self.data_dir,
            self.datasets_dir,
            self.uploads_dir,
            self.runs_dir,
            self.models_dir,
            self.ckks_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def ensure_within(path: Path, root: Path, *, label: str = "path") -> Path:
        resolved = path.resolve()
        if not resolved.is_relative_to(root.resolve()):
            raise ForbiddenError(f"{label} is outside the approved directory")
        return resolved

    def resolve_data_relative(self, relative: str) -> Path:
        candidate = (self.data_dir / relative).resolve()
        return self.ensure_within(candidate, self.data_dir, label="data path")

    def dataset_path(self, stored_relative: str) -> Path:
        candidate = self.resolve_data_relative(stored_relative)
        return self.ensure_within(candidate, self.datasets_dir, label="dataset path")

    def run_dir(self, run_id: str) -> Path:
        candidate = (self.runs_dir / run_id).resolve()
        return self.ensure_within(candidate, self.runs_dir, label="run directory")

    def model_path(self, relative: str) -> Path:
        candidate = (self.models_dir / relative).resolve()
        return self.ensure_within(candidate, self.models_dir, label="model path")
