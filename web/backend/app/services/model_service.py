"""Verified plaintext GRU inference with the scaler fitted during training."""
import hashlib
import json
import math

from ..config import Settings
from ..domain.dataset import ScalerStats, apply_scaler
from ..domain.federated.keras_backend import KerasGRUBackend
from ..domain.model import keras_runtime_status, parameter_count
from ..errors import ForbiddenError, InputValidationError, UnavailableError
from ..storage.paths import StoragePaths


class ModelService:
    def __init__(self, settings: Settings, paths: StoragePaths) -> None:
        self.settings = settings
        self.paths = paths

    def _artifact(self, path: str, checksum: str) -> dict:
        data = self.paths.model_path(path).read_bytes()
        if hashlib.sha256(data).hexdigest() != checksum:
            raise UnavailableError("Model or preprocessing checksum mismatch.")
        return json.loads(data)

    def _load(self):
        if not self.settings.enable_predictions:
            raise UnavailableError("Prediction is disabled.")
        try:
            manifest = json.loads((self.paths.models_dir / "manifest.json").read_bytes())
            model = self._artifact(manifest["model_path"], manifest["sha256"])
            preprocessing = self._artifact(manifest["preprocessing"], manifest["preprocessing_sha256"])
            names = preprocessing["feature_names"]
            width = model["input_features"]
            stats = ScalerStats(**preprocessing["prepared"]["scaler"])
            if (model["model"] != "keras_gru" or width != 48 or len(names) != width
                    or model["metadata"]["experiment_id"] != preprocessing["experiment_id"]
                    or model["metadata"]["dataset_id"] != preprocessing["dataset_id"]
                    or len(model["weights"]) != parameter_count(width)
                    or len(stats.means) != width or len(stats.scales) != width
                    or not all(math.isfinite(x) for x in stats.means + model["weights"])
                    or not all(math.isfinite(x) and x > 0 for x in stats.scales)):
                raise UnavailableError("Model and preprocessing are incompatible.")
        except FileNotFoundError as exc:
            raise UnavailableError("Train a plaintext GRU to create the model and preprocessing artifacts.") from exc
        except (OSError, KeyError, TypeError, ValueError, ForbiddenError) as exc:
            raise UnavailableError("The prediction manifest or its artifacts are invalid.") from exc
        available, reason = keras_runtime_status()
        if not available:
            raise UnavailableError(reason)
        return manifest, model["weights"], stats

    def status(self):
        try:
            manifest, _, _ = self._load()
        except UnavailableError as exc:
            return dict(available=False, reason=str(exc), model=None, preprocessing=None)
        return dict(available=True, reason="Verified GRU and scaler are ready.",
                    model=manifest["model_path"], preprocessing=manifest["preprocessing"])

    def predict(self, features: list[float]) -> dict:
        _, weights, stats = self._load()
        if len(features) != len(stats.means) or not all(math.isfinite(x) for x in features):
            raise InputValidationError("Enter 48 finite flow features in training CSV column order.")
        scaled = apply_scaler([features], stats)
        probability = KerasGRUBackend().predict(weights, scaled)[0]
        return {"available": True, "prediction": probability, "label": int(probability > 0.5)}
