"""ML model discovery and prediction boundary.

No trained model or matching preprocessing pipeline is present. Prediction is
therefore unavailable. This module deliberately does not load arbitrary Keras
or pickle artifacts; model admission requires an explicit manifest and checksum
in a later phase.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ..config import Settings
from ..errors import UnavailableError
from ..storage.paths import StoragePaths


class ModelService:
    def __init__(self, settings: Settings, paths: StoragePaths) -> None:
        self.settings = settings
        self.paths = paths

    def status(self) -> dict[str, Any]:
        if not self.settings.enable_predictions:
            return {
                "available": False,
                "reason": "Prediction is disabled until a verified model and preprocessing pipeline exist.",
                "model": None,
                "preprocessing": None,
            }
        manifest_path = self.paths.models_dir / "manifest.json"
        if not manifest_path.is_file():
            return {
                "available": False,
                "reason": "No admitted model manifest is present.",
                "model": None,
                "preprocessing": None,
            }
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {
                "available": False,
                "reason": "Model manifest is unreadable.",
                "model": None,
                "preprocessing": None,
            }
        model_name = manifest.get("model_path")
        expected_hash = manifest.get("sha256")
        preprocessing = manifest.get("preprocessing")
        if not isinstance(model_name, str) or not isinstance(expected_hash, str) or not preprocessing:
            return {
                "available": False,
                "reason": "Model manifest is incomplete.",
                "model": None,
                "preprocessing": None,
            }
        try:
            model_path = self.paths.model_path(model_name)
        except Exception:
            return {
                "available": False,
                "reason": "Model path is outside the approved model directory.",
                "model": None,
                "preprocessing": None,
            }
        if not model_path.is_file():
            return {
                "available": False,
                "reason": "Model artifact is missing.",
                "model": model_name,
                "preprocessing": None,
            }
        digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
        if digest != expected_hash:
            return {
                "available": False,
                "reason": "Model artifact checksum mismatch.",
                "model": model_name,
                "preprocessing": None,
            }
        return {
            "available": False,
            "reason": "Model loading and inference are not implemented in Phase 3.",
            "model": model_name,
            "preprocessing": preprocessing,
        }

    def predict(self, _features: list[float]) -> dict[str, Any]:
        raise UnavailableError("model unavailable; no prediction was produced")
