"""Binary classification metrics matching the legacy formulas.

Formulas follow scikit-learn's binary definitions, including zero-division
behaviour (an undefined precision/recall is reported as 0.0). ROC AUC is added
for the new backend; it never replaces the legacy CSV schema.
"""

from __future__ import annotations

import math
from typing import Sequence

from ..errors import InputValidationError

LOG_LOSS_EPSILON = 1e-15


def _as_binary(values: Sequence[int | float], *, name: str) -> list[int]:
    result: list[int] = []
    for value in values:
        if value not in (0, 1, 0.0, 1.0):
            raise InputValidationError(f"{name} must contain only binary 0/1 values")
        result.append(int(value))
    if not result:
        raise InputValidationError(f"{name} must not be empty")
    return result


def confusion_counts(
    y_true: Sequence[int | float], y_pred: Sequence[int | float]
) -> tuple[int, int, int, int]:
    truth = _as_binary(y_true, name="y_true")
    prediction = _as_binary(y_pred, name="y_pred")
    if len(truth) != len(prediction):
        raise InputValidationError("y_true and y_pred lengths differ")
    tp = sum(1 for y, p in zip(truth, prediction) if y == 1 and p == 1)
    tn = sum(1 for y, p in zip(truth, prediction) if y == 0 and p == 0)
    fp = sum(1 for y, p in zip(truth, prediction) if y == 0 and p == 1)
    fn = sum(1 for y, p in zip(truth, prediction) if y == 1 and p == 0)
    return tp, tn, fp, fn


def accuracy_score(y_true: Sequence[int | float], y_pred: Sequence[int | float]) -> float:
    tp, tn, fp, fn = confusion_counts(y_true, y_pred)
    return (tp + tn) / (tp + tn + fp + fn)


def precision_score(y_true: Sequence[int | float], y_pred: Sequence[int | float]) -> float:
    tp, _tn, fp, _fn = confusion_counts(y_true, y_pred)
    denominator = tp + fp
    return tp / denominator if denominator else 0.0


def recall_score(y_true: Sequence[int | float], y_pred: Sequence[int | float]) -> float:
    tp, _tn, _fp, fn = confusion_counts(y_true, y_pred)
    denominator = tp + fn
    return tp / denominator if denominator else 0.0


def f1_score(y_true: Sequence[int | float], y_pred: Sequence[int | float]) -> float:
    precision = precision_score(y_true, y_pred)
    recall = recall_score(y_true, y_pred)
    denominator = precision + recall
    return 2.0 * precision * recall / denominator if denominator else 0.0


def balanced_accuracy_score(
    y_true: Sequence[int | float], y_pred: Sequence[int | float]
) -> float:
    tp, tn, fp, fn = confusion_counts(y_true, y_pred)
    positive_recall = tp / (tp + fn) if (tp + fn) else 0.0
    negative_recall = tn / (tn + fp) if (tn + fp) else 0.0
    return (positive_recall + negative_recall) / 2.0


def matthews_corrcoef(
    y_true: Sequence[int | float], y_pred: Sequence[int | float]
) -> float:
    tp, tn, fp, fn = confusion_counts(y_true, y_pred)
    denominator = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    return (tp * tn - fp * fn) / denominator if denominator else 0.0


def cohen_kappa_score(
    y_true: Sequence[int | float], y_pred: Sequence[int | float]
) -> float:
    tp, tn, fp, fn = confusion_counts(y_true, y_pred)
    total = tp + tn + fp + fn
    observed = (tp + tn) / total
    positive_actual = tp + fn
    negative_actual = fp + tn
    positive_predicted = tp + fp
    negative_predicted = fn + tn
    expected = (
        positive_actual * positive_predicted + negative_actual * negative_predicted
    ) / (total * total)
    denominator = 1.0 - expected
    return (observed - expected) / denominator if denominator else 0.0


def log_loss(y_true: Sequence[int | float], probabilities: Sequence[float]) -> float:
    truth = _as_binary(y_true, name="y_true")
    if len(truth) != len(probabilities):
        raise InputValidationError("y_true and probabilities lengths differ")
    total = 0.0
    for label, probability in zip(truth, probabilities):
        value = float(probability)
        if not math.isfinite(value):
            raise InputValidationError("probabilities must be finite")
        clipped = min(1.0 - LOG_LOSS_EPSILON, max(LOG_LOSS_EPSILON, value))
        if label == 1:
            total -= math.log(clipped)
        else:
            total -= math.log(1.0 - clipped)
    return total / len(truth)


def roc_auc_score(y_true: Sequence[int | float], probabilities: Sequence[float]) -> float:
    truth = _as_binary(y_true, name="y_true")
    if len(truth) != len(probabilities):
        raise InputValidationError("y_true and probabilities lengths differ")
    positives = sum(truth)
    negatives = len(truth) - positives
    if positives == 0 or negatives == 0:
        raise InputValidationError("ROC AUC requires both classes to be present")

    pairs = sorted(
        ((float(score), index) for index, score in enumerate(probabilities)),
        key=lambda item: item[0],
    )
    ranks = [0.0] * len(pairs)
    position = 0
    while position < len(pairs):
        end = position
        while end + 1 < len(pairs) and pairs[end + 1][0] == pairs[position][0]:
            end += 1
        average_rank = (position + end) / 2.0 + 1.0
        for inner in range(position, end + 1):
            ranks[pairs[inner][1]] = average_rank
        position = end + 1

    positive_rank_sum = sum(rank for rank, label in zip(ranks, truth) if label == 1)
    return (
        positive_rank_sum - positives * (positives + 1) / 2.0
    ) / (positives * negatives)


def compute_metrics(
    y_true: Sequence[int | float],
    probabilities: Sequence[float],
    *,
    threshold: float = 0.5,
    include_auc: bool = True,
) -> dict[str, float | None]:
    if not 0.0 < threshold < 1.0:
        raise InputValidationError("threshold must be between 0 and 1")
    truth = _as_binary(y_true, name="y_true")
    if len(truth) != len(probabilities):
        raise InputValidationError("y_true and probabilities lengths differ")
    predictions = [1 if float(value) > threshold else 0 for value in probabilities]
    metrics: dict[str, float | None] = {
        "accuracy": accuracy_score(truth, predictions),
        "precision": precision_score(truth, predictions),
        "recall": recall_score(truth, predictions),
        "f1": f1_score(truth, predictions),
        "mcc": matthews_corrcoef(truth, predictions),
        "cohen_kappa": cohen_kappa_score(truth, predictions),
        "log_loss": log_loss(truth, probabilities),
        "g_mean": balanced_accuracy_score(truth, predictions),
    }
    negatives = sum(label == 0 for label in truth)
    metrics["false_positive_rate"] = sum(t == 0 and p == 1 for t,p in zip(truth,predictions)) / negatives if negatives else None
    if include_auc:
        metrics["auc"] = roc_auc_score(truth, probabilities)
    return metrics
