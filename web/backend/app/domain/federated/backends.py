"""Training backends for the deterministic federated harness.

``ReferenceLinearBackend`` is a dependency-free logistic-regression double. It
is deliberately not the research GRU; it exists so round orchestration,
weighting, and determinism can be tested without TensorFlow. Results from it
must never be presented as a reproduction of the paper.
"""

from __future__ import annotations

import math
import random
from typing import Protocol, Sequence, runtime_checkable

from ...errors import InputValidationError


def _sigmoid(value: float) -> float:
    if value >= 0.0:
        return 1.0 / (1.0 + math.exp(-value))
    exponent = math.exp(value)
    return exponent / (1.0 + exponent)


@runtime_checkable
class TrainingBackend(Protocol):
    name: str
    research_model: bool

    def parameter_count(self, input_features: int) -> int: ...

    def initial_weights(self, input_features: int) -> list[float]: ...

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
    ) -> list[float]: ...

    def predict(
        self, weights: Sequence[float], rows: Sequence[Sequence[float]]
    ) -> list[float]: ...


class ReferenceLinearBackend(TrainingBackend):
    """Deterministic logistic regression: weight 0 is bias, then one per feature."""

    name = "reference_linear"
    research_model = False

    def parameter_count(self, input_features: int) -> int:
        if input_features <= 0:
            raise InputValidationError("input_features must be positive")
        return input_features + 1

    def initial_weights(self, input_features: int) -> list[float]:
        return [0.0] * self.parameter_count(input_features)

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
        if len(weights) != width + 1:
            raise InputValidationError("weight count does not match feature width")

        current = [float(value) for value in weights]
        indices = list(range(len(rows)))
        for _epoch in range(epochs):
            rng.shuffle(indices)
            for start in range(0, len(indices), batch_size):
                batch = indices[start : start + batch_size]
                if not batch:
                    continue
                gradients = [0.0] * len(current)
                for index in batch:
                    row = rows[index]
                    score = current[0]
                    for position, value in enumerate(row):
                        score += current[position + 1] * float(value)
                    error = _sigmoid(score) - int(labels[index])
                    gradients[0] += error
                    for position, value in enumerate(row):
                        gradients[position + 1] += error * float(value)
                scale = learning_rate / len(batch)
                current = [
                    value - scale * gradient
                    for value, gradient in zip(current, gradients)
                ]
        return current

    def predict(
        self, weights: Sequence[float], rows: Sequence[Sequence[float]]
    ) -> list[float]:
        probabilities: list[float] = []
        for row in rows:
            if len(weights) != len(row) + 1:
                raise InputValidationError("weight count does not match feature width")
            score = float(weights[0])
            for position, value in enumerate(row):
                score += float(weights[position + 1]) * float(value)
            probabilities.append(_sigmoid(score))
        return probabilities
