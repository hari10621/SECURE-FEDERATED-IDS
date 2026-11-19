"""Keras GRU backend for the federated harness.

TensorFlow is imported lazily. The module is safe to import on the lightweight
backend runtime, but ``train``, ``predict``, and ``initial_weights`` fail closed
when TensorFlow is absent. The architecture is the research ``InSDN_4/8/12``
model: three GRU blocks with BatchNormalization and Dropout, then a sigmoid
Dense output.
"""

from __future__ import annotations

import random
from typing import Sequence

from ...errors import InputValidationError, UnavailableError
from ..model import (
    DEFAULT_LEARNING_RATE,
    build_gru_model,
    flatten_gru_weights,
    parameter_count,
    parameter_specs,
    unflatten_gru_weights,
)
from .backends import TrainingBackend


class KerasGRUBackend(TrainingBackend):
    name = "keras_gru"
    research_model = True

    def __init__(self, learning_rate: float = DEFAULT_LEARNING_RATE) -> None:
        if learning_rate <= 0.0:
            raise InputValidationError("learning_rate must be positive")
        self.learning_rate = learning_rate

    def parameter_count(self, input_features: int) -> int:
        return parameter_count(input_features)

    def _build(self, input_features: int, learning_rate: float):
        try:
            return build_gru_model(input_features, learning_rate)
        except UnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - report a fail-closed runtime error
            raise UnavailableError(
                "TensorFlow/Keras could not build the GRU model "
                f"({type(exc).__name__})."
            ) from exc

    def _load(self, weights: Sequence[float], input_features: int, learning_rate: float):
        import numpy as np

        model = self._build(input_features, learning_rate)
        specs = parameter_specs(input_features)
        blocks = unflatten_gru_weights(weights, input_features)
        arrays = [
            np.asarray(block, dtype="float32").reshape(spec.shape)
            for block, spec in zip(blocks, specs)
        ]
        try:
            model.set_weights(arrays)
        except ValueError as exc:
            raise InputValidationError(
                "weight shapes do not match the Keras GRU model"
            ) from exc
        return model

    def initial_weights(self, input_features: int) -> list[float]:
        model = self._build(input_features, self.learning_rate)
        return flatten_gru_weights(model.get_weights(), input_features)

    def train(
        self,
        weights: Sequence[float],
        rows: Sequence[Sequence[float]],
        labels: Sequence[int],
        *,
        epochs: int,
        batch_size: int,
        learning_rate: float,
        rng: random.Random,
    ) -> list[float]:
        import numpy as np
        import tensorflow as tf

        if epochs <= 0:
            raise InputValidationError("epochs must be positive")
        if batch_size <= 0:
            raise InputValidationError("batch_size must be positive")
        if learning_rate <= 0.0:
            raise InputValidationError("learning_rate must be positive")
        if len(rows) != len(labels):
            raise InputValidationError("feature and label row counts differ")
        if not rows:
            raise InputValidationError("cannot train on zero rows")
        width = len(rows[0])
        for row in rows:
            if len(row) != width:
                raise InputValidationError("inconsistent feature widths")
        if len(weights) != parameter_count(width):
            raise InputValidationError("weight count does not match feature width")

        seed = rng.randrange(0, 2**31 - 1)
        tf.keras.utils.set_random_seed(seed)
        model = self._load(weights, width, learning_rate)
        features = np.asarray(rows, dtype="float32").reshape(-1, 1, width)
        targets = np.asarray(labels, dtype="float32")
        dataset = (
            tf.data.Dataset.from_tensor_slices((features, targets))
            .shuffle(len(rows), seed=seed, reshuffle_each_iteration=True)
            .batch(batch_size)
        )
        model.fit(dataset, epochs=epochs, verbose=0)
        return flatten_gru_weights(model.get_weights(), width)

    def predict(
        self, weights: Sequence[float], rows: Sequence[Sequence[float]]
    ) -> list[float]:
        import numpy as np

        if not rows:
            return []
        width = len(rows[0])
        for row in rows:
            if len(row) != width:
                raise InputValidationError("inconsistent feature widths")
        if len(weights) != parameter_count(width):
            raise InputValidationError("weight count does not match feature width")
        model = self._load(weights, width, self.learning_rate)
        features = np.asarray(rows, dtype="float32").reshape(-1, 1, width)
        probabilities = model.predict(features, verbose=0)
        return np.asarray(probabilities, dtype="float64").reshape(-1).tolist()
