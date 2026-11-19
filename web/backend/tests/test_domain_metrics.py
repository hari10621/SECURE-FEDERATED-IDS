from __future__ import annotations

import math

import pytest

from app.domain.metrics import compute_metrics, roc_auc_score
from app.errors import InputValidationError


def test_perfect_predictions():
    metrics = compute_metrics([0, 0, 1, 1], [0.05, 0.2, 0.8, 0.95])
    assert metrics["accuracy"] == 1.0
    assert metrics["precision"] == 1.0
    assert metrics["recall"] == 1.0
    assert metrics["f1"] == 1.0
    assert metrics["mcc"] == 1.0
    assert metrics["cohen_kappa"] == 1.0
    assert metrics["g_mean"] == 1.0
    assert metrics["auc"] == 1.0


def test_known_binary_values():
    metrics = compute_metrics([0, 1, 1, 0], [0.1, 0.8, 0.6, 0.9])
    assert metrics["accuracy"] == pytest.approx(0.75)
    assert metrics["precision"] == pytest.approx(2 / 3)
    assert metrics["recall"] == pytest.approx(1.0)
    assert metrics["f1"] == pytest.approx(0.8)
    assert metrics["mcc"] == pytest.approx(2 / math.sqrt(12))
    assert metrics["cohen_kappa"] == pytest.approx(0.5)
    assert metrics["g_mean"] == pytest.approx(0.75)
    assert metrics["auc"] == pytest.approx(0.5)


def test_log_loss_clips_extreme_probabilities():
    metrics = compute_metrics([1, 0], [1.0, 0.0], include_auc=False)
    assert metrics["log_loss"] == pytest.approx(-math.log(1.0 - 1e-15), abs=1e-12)
    assert "auc" not in metrics


def test_single_class_auc_is_rejected():
    with pytest.raises(InputValidationError):
        roc_auc_score([1, 1, 1], [0.2, 0.3, 0.4])


def test_non_binary_labels_are_rejected():
    with pytest.raises(InputValidationError):
        compute_metrics([0, 2], [0.1, 0.9])
