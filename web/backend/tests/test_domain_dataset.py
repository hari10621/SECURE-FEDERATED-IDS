from __future__ import annotations

import pytest

from app.domain.dataset import (
    apply_scaler,
    fit_scaler,
    load_csv_dataset,
    preprocess,
    split_indices,
)
from app.errors import InputValidationError


def _write_csv(path, *, rows=40, features=3):
    header = [f"f{index}" for index in range(features)] + ["Label"]
    lines = [",".join(header)]
    for index in range(rows):
        values = [str((index + feature * 3) / 10.0) for feature in range(features)]
        values.append(str(index % 2))
        lines.append(",".join(values))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_load_csv_uses_last_column_as_label(tmp_path):
    dataset = load_csv_dataset(_write_csv(tmp_path / "data.csv"))
    assert dataset.feature_count == 3
    assert dataset.feature_names == ["f0", "f1", "f2"]
    assert len(dataset.rows) == 40
    assert set(dataset.labels) == {0, 1}


def test_loader_rejects_non_binary_label(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("f0,f1,Label\n1,2,3\n", encoding="utf-8")
    with pytest.raises(InputValidationError):
        load_csv_dataset(path)


def test_clean_mode_fits_scaler_on_train_only(tmp_path):
    dataset = load_csv_dataset(_write_csv(tmp_path / "data.csv"))
    prepared = preprocess(
        dataset.rows,
        dataset.labels,
        feature_names=dataset.feature_names,
        mode="clean",
    )
    train_rows = [dataset.rows[index] for index in prepared.split.train]
    legacy = preprocess(
        dataset.rows,
        dataset.labels,
        feature_names=dataset.feature_names,
        mode="legacy",
    )
    expected_train_means = fit_scaler(train_rows).means
    expected_all_means = fit_scaler(dataset.rows).means
    assert prepared.scaler.means == pytest.approx(expected_train_means)
    assert legacy.scaler.means == pytest.approx(expected_all_means)
    assert prepared.scaler.means != pytest.approx(expected_all_means)
    assert any("leak" in note for note in legacy.differences)
    assert prepared.differences == []


def test_split_is_deterministic_and_stratified():
    labels = [0, 1] * 25
    first = split_indices(labels, seed=42)
    second = split_indices(labels, seed=42)
    assert first == second
    assert set(first.train).isdisjoint(first.test)
    assert sorted(first.train + first.test) == list(range(len(labels)))
    assert {labels[index] for index in first.test} == {0, 1}
    assert {labels[index] for index in first.train} == {0, 1}


def test_different_seed_changes_assignment():
    labels = [0, 1] * 50
    assert split_indices(labels, seed=1) != split_indices(labels, seed=2)


def test_scaler_handles_zero_variance():
    stats = fit_scaler([[1.0, 2.0], [1.0, 4.0]])
    assert stats.means == [1.0, 3.0]
    assert stats.scales[0] == 1.0
    assert apply_scaler([[1.0, 2.0]], stats) == [[0.0, -1.0]]


def test_invalid_mode_and_width_are_rejected(tmp_path):
    dataset = load_csv_dataset(_write_csv(tmp_path / "data.csv"))
    with pytest.raises(InputValidationError):
        preprocess(
            dataset.rows,
            dataset.labels,
            feature_names=dataset.feature_names,
            mode="unknown",
        )
    with pytest.raises(InputValidationError):
        preprocess(
            dataset.rows,
            dataset.labels,
            feature_names=dataset.feature_names[:2],
            mode="clean",
        )
