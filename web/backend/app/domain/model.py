"""GRU architecture description and weight codec.

The legacy ``build_gru_model`` is reproduced here as an explicit architecture
description, a parameter-count check, and a lossless weight layout. TensorFlow
is imported lazily and never at module import time, so the domain package stays
usable on the lightweight backend environment.

The Keras model is constructed only when TensorFlow is importable. The lightweight
backend environment has no TensorFlow, so its API reports the training runtime as
unavailable instead of pretending a model exists.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from ..errors import InputValidationError, UnavailableError

GRU_UNITS: tuple[int, int, int] = (256, 128, 64)
DROPOUT_RATE = 0.3
DEFAULT_INPUT_FEATURES = 48
DEFAULT_LEARNING_RATE = 0.0001
CKKS_SLOT_COUNT = 4096
ARTIFACT_FORMAT = "securefed-model-v1"


@dataclass(frozen=True)
class ParameterSpec:
    name: str
    shape: tuple[int, ...]

    @property
    def size(self) -> int:
        total = 1
        for dimension in self.shape:
            total *= dimension
        return total


def parameter_specs(input_features: int) -> list[ParameterSpec]:
    """Return Keras ``get_weights()`` shapes in the original layer order.

    Each GRU uses ``reset_after=True`` (the Keras default), so its bias has
    shape ``(2, 3 * units)``. Each BatchNormalization contributes gamma, beta,
    moving mean, and moving variance of length ``units``.
    """
    _require_input_features(input_features)
    specs: list[ParameterSpec] = []
    previous = input_features
    for index, units in enumerate(GRU_UNITS, start=1):
        specs.extend(
            [
                ParameterSpec(f"gru_{index}_kernel", (previous, 3 * units)),
                ParameterSpec(f"gru_{index}_recurrent_kernel", (units, 3 * units)),
                ParameterSpec(f"gru_{index}_bias", (2, 3 * units)),
                ParameterSpec(f"batch_normalization_{index}_gamma", (units,)),
                ParameterSpec(f"batch_normalization_{index}_beta", (units,)),
                ParameterSpec(f"batch_normalization_{index}_moving_mean", (units,)),
                ParameterSpec(f"batch_normalization_{index}_moving_variance", (units,)),
            ]
        )
        previous = units
    specs.extend(
        [
            ParameterSpec("dense_kernel", (previous, 1)),
            ParameterSpec("dense_bias", (1,)),
        ]
    )
    return specs


def parameter_count(input_features: int = DEFAULT_INPUT_FEATURES) -> int:
    return sum(spec.size for spec in parameter_specs(input_features))


def chunk_count(input_features: int = DEFAULT_INPUT_FEATURES, slot_count: int = CKKS_SLOT_COUNT) -> int:
    if slot_count <= 0:
        raise InputValidationError("slot_count must be positive")
    total = parameter_count(input_features)
    return (total + slot_count - 1) // slot_count


def _require_input_features(input_features: int) -> None:
    if not isinstance(input_features, int) or isinstance(input_features, bool):
        raise InputValidationError("input_features must be an integer")
    if input_features <= 0:
        raise InputValidationError("input_features must be positive")


def _flatten_into(value: Any, flat: list[float]) -> None:
    """Recursively flatten lists, tuples, and NumPy arrays/scalars."""
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, (list, tuple)):
        for item in value:
            _flatten_into(item, flat)
        return
    flat.append(float(value))


def flatten_weights(weights: Sequence[Any]) -> list[float]:
    flat: list[float] = []
    for block in weights:
        _flatten_into(block, flat)
    return flat


def unflatten_to_specs(flat: Sequence[float], specs: Sequence[ParameterSpec]) -> list[list[float]]:
    expected = sum(spec.size for spec in specs)
    if len(flat) != expected:
        raise InputValidationError(
            f"weight count mismatch: expected {expected}, found {len(flat)}"
        )
    blocks: list[list[float]] = []
    offset = 0
    for spec in specs:
        size = spec.size
        blocks.append([float(value) for value in flat[offset : offset + size]])
        offset += size
    return blocks


def flatten_gru_weights(weights: Sequence[Any], input_features: int) -> list[float]:
    specs = parameter_specs(input_features)
    expected = sum(spec.size for spec in specs)
    flat = flatten_weights(weights)
    if len(flat) != expected:
        raise InputValidationError(
            f"GRU weight count mismatch for {input_features} features: "
            f"expected {expected}, found {len(flat)}"
        )
    return flat


def unflatten_gru_weights(flat: Sequence[float], input_features: int) -> list[list[float]]:
    return unflatten_to_specs(flat, parameter_specs(input_features))


def model_description(input_features: int = DEFAULT_INPUT_FEATURES) -> dict[str, Any]:
    _require_input_features(input_features)
    return {
        "model": "gru",
        "input_shape": [1, input_features],
        "layers": [
            {"type": "GRU", "units": 256, "return_sequences": True},
            {"type": "BatchNormalization"},
            {"type": "Dropout", "rate": DROPOUT_RATE},
            {"type": "GRU", "units": 128, "return_sequences": True},
            {"type": "BatchNormalization"},
            {"type": "Dropout", "rate": DROPOUT_RATE},
            {"type": "GRU", "units": 64, "return_sequences": False},
            {"type": "BatchNormalization"},
            {"type": "Dropout", "rate": DROPOUT_RATE},
            {"type": "Dense", "units": 1, "activation": "sigmoid"},
        ],
        "optimizer": {"type": "Adam", "learning_rate": DEFAULT_LEARNING_RATE},
        "loss": "binary_crossentropy",
        "metrics": ["accuracy"],
        "parameter_count": parameter_count(input_features),
        "parameter_block_count": chunk_count(input_features),
    }


def artifact_filename(dataset_type: str, client_count: int) -> str:
    safe = "".join(char for char in dataset_type.lower() if char.isalnum() or char in "-_")
    if not safe:
        raise InputValidationError("dataset_type is required")
    if client_count <= 0:
        raise InputValidationError("client_count must be positive")
    return f"{safe}_{client_count}_model.json"


def write_weight_artifact(
    path: Path,
    *,
    flat_weights: Sequence[float],
    specs: Sequence[ParameterSpec],
    model_name: str,
    input_features: int,
    dataset_type: str,
    client_count: int,
    metadata: dict[str, Any] | None = None,
) -> str:
    expected = sum(spec.size for spec in specs)
    if len(flat_weights) != expected:
        raise InputValidationError(
            f"artifact weight count mismatch: expected {expected}, found {len(flat_weights)}"
        )
    payload = {
        "format": ARTIFACT_FORMAT,
        "model": model_name,
        "input_features": input_features,
        "parameter_count": expected,
        "dataset_type": dataset_type,
        "client_count": client_count,
        "parameter_specs": [
            {"name": spec.name, "shape": list(spec.shape)} for spec in specs
        ],
        "weights": [float(value) for value in flat_weights],
        "metadata": metadata or {},
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    path.write_text(encoded, encoding="utf-8")
    return digest


def read_weight_artifact(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InputValidationError("model artifact is unreadable or malformed") from exc
    if not isinstance(payload, dict) or payload.get("format") != ARTIFACT_FORMAT:
        raise InputValidationError("unsupported model artifact format")
    specs = [
        ParameterSpec(str(item["name"]), tuple(int(dim) for dim in item["shape"]))
        for item in payload.get("parameter_specs", [])
    ]
    weights = [float(value) for value in payload.get("weights", [])]
    blocks = unflatten_to_specs(weights, specs)
    payload["parameter_specs_parsed"] = specs
    payload["weights_blocks"] = blocks
    return payload


def keras_available() -> bool:
    available, _ = keras_runtime_status()
    return available


def keras_runtime_status() -> tuple[bool, str]:
    try:
        import tensorflow as tf  # noqa: F401
    except Exception as exc:  # noqa: BLE001 - any import failure means unavailable
        return (
            False,
            "TensorFlow/Keras is not importable in this Python runtime "
            f"({type(exc).__name__}). Install tensorflow-cpu in an isolated "
            "environment before running GRU training.",
        )
    version = getattr(tf, "__version__", "unknown")
    return True, f"TensorFlow {version} is available for GRU training."


def build_gru_model(input_features: int = DEFAULT_INPUT_FEATURES, learning_rate: float = DEFAULT_LEARNING_RATE):
    """Rebuild the legacy Keras model, or fail closed when TensorFlow is absent.

    This is intentionally not executed by the Phase 4 tests; it exists so the
    exact architecture can be imported by a future legacy worker.
    """
    _require_input_features(input_features)
    available, reason = keras_runtime_status()
    if not available:
        raise UnavailableError(reason)
    from tensorflow.keras.layers import GRU, BatchNormalization, Dense, Dropout
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.optimizers import Adam

    model = Sequential(
        [
            GRU(256, return_sequences=True, input_shape=(1, input_features)),
            BatchNormalization(),
            Dropout(DROPOUT_RATE),
            GRU(128, return_sequences=True),
            BatchNormalization(),
            Dropout(DROPOUT_RATE),
            GRU(64, return_sequences=False),
            BatchNormalization(),
            Dropout(DROPOUT_RATE),
            Dense(1, activation="sigmoid"),
        ]
    )
    model.compile(
        optimizer=Adam(learning_rate=learning_rate),
        loss="binary_crossentropy",
        metrics=["accuracy"],
    )
    return model
