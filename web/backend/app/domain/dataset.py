"""Explicit CSV schema, deterministic split, and scaler modes.

Two preprocessing modes exist:

* ``legacy``: fit ``StandardScaler`` on every row, then take the 70/30 split.
  This reproduces the research scripts and therefore leaks test statistics into
  training. It is retained only for comparison and must be labelled.
* ``clean``: split first, then fit the scaler on the training partition only.

The split and scaler are deterministic pure-Python ports. They use a documented
seed but are not byte-identical to NumPy/scikit-learn; parity must be measured
in the legacy environment rather than assumed.
"""

from __future__ import annotations

import csv
import math
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Sequence

from ..errors import InputValidationError

PREPROCESS_MODES = ("legacy", "clean")
DEFAULT_TEST_SIZE = 0.3
DEFAULT_SPLIT_SEED = 42


@dataclass(frozen=True)
class LoadedDataset:
    feature_names: list[str]
    rows: list[list[float]]
    labels: list[int]

    @property
    def feature_count(self) -> int:
        return len(self.feature_names)

    def as_dict(self) -> dict[str, Any]:
        return {
            "feature_names": list(self.feature_names),
            "feature_count": self.feature_count,
            "rows": len(self.rows),
            "label_counts": _label_counts(self.labels),
        }


@dataclass(frozen=True)
class ScalerStats:
    means: list[float]
    scales: list[float]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SplitIndices:
    train: list[int]
    test: list[int]

    def as_dict(self) -> dict[str, Any]:
        return {"train": list(self.train), "test": list(self.test)}


@dataclass(frozen=True)
class PreprocessedDataset:
    mode: str
    feature_names: list[str]
    train_rows: list[list[float]]
    test_rows: list[list[float]]
    train_labels: list[int]
    test_labels: list[int]
    split: SplitIndices
    scaler: ScalerStats
    seed: int
    test_size: float
    differences: list[str] = field(default_factory=list)

    @property
    def feature_count(self) -> int:
        return len(self.feature_names)

    def summary(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "feature_count": self.feature_count,
            "train_rows": len(self.train_rows),
            "test_rows": len(self.test_rows),
            "train_label_counts": _label_counts(self.train_labels),
            "test_label_counts": _label_counts(self.test_labels),
            "seed": self.seed,
            "test_size": self.test_size,
            "split": self.split.as_dict(),
            "scaler": self.scaler.as_dict(),
            "differences": list(self.differences),
        }


def _label_counts(labels: Sequence[int]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for label in labels:
        key = str(int(label))
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def load_csv_dataset(
    path: Path,
    *,
    label_column: str | None = None,
    max_rows: int | None = None,
) -> LoadedDataset:
    """Load a numeric CSV whose label is the last column by default."""
    try:
        handle = path.open("r", encoding="utf-8-sig", newline="")
    except OSError as exc:
        raise InputValidationError("dataset file is unreadable") from exc

    with handle:
        reader = csv.reader(handle)
        try:
            header = [cell.strip() for cell in next(reader)]
        except StopIteration as exc:
            raise InputValidationError("CSV is empty") from exc
        if len(header) < 2:
            raise InputValidationError("CSV must contain at least one feature and one label column")
        if any(not name for name in header):
            raise InputValidationError("CSV header contains an empty column name")
        if len(set(header)) != len(header):
            raise InputValidationError("CSV header contains duplicate column names")

        selected_label = label_column or header[-1]
        if selected_label not in header:
            raise InputValidationError(f"label column not found: {selected_label!r}")
        label_index = header.index(selected_label)
        feature_indices = [index for index in range(len(header)) if index != label_index]
        feature_names = [header[index] for index in feature_indices]

        rows: list[list[float]] = []
        labels: list[int] = []
        for line_number, row in enumerate(reader, start=2):
            if not row or all(not cell.strip() for cell in row):
                raise InputValidationError(f"line {line_number}: empty row")
            if len(row) != len(header):
                raise InputValidationError(
                    f"line {line_number}: expected {len(header)} columns, found {len(row)}"
                )
            features: list[float] = []
            for index in feature_indices:
                raw = row[index].strip()
                try:
                    value = float(raw)
                except ValueError as exc:
                    raise InputValidationError(
                        f"line {line_number}: non-numeric feature {header[index]!r}"
                    ) from exc
                if not math.isfinite(value):
                    raise InputValidationError(
                        f"line {line_number}: non-finite feature {header[index]!r}"
                    )
                features.append(value)
            try:
                label_value = float(row[label_index].strip())
            except ValueError as exc:
                raise InputValidationError(f"line {line_number}: non-numeric label") from exc
            if not math.isfinite(label_value) or label_value not in (0.0, 1.0):
                raise InputValidationError(f"line {line_number}: label must be binary 0 or 1")
            rows.append(features)
            labels.append(int(label_value))
            if max_rows is not None and len(rows) > max_rows:
                raise InputValidationError(f"row limit exceeded: more than {max_rows} rows")

    if not rows:
        raise InputValidationError("CSV contains no data rows")
    return LoadedDataset(feature_names=feature_names, rows=rows, labels=labels)


def fit_scaler(rows: Sequence[Sequence[float]]) -> ScalerStats:
    if not rows:
        raise InputValidationError("cannot fit a scaler on zero rows")
    width = len(rows[0])
    if width == 0:
        raise InputValidationError("cannot fit a scaler on zero features")
    for row in rows:
        if len(row) != width:
            raise InputValidationError("inconsistent feature widths")
    count = len(rows)
    means = [0.0] * width
    for row in rows:
        for index, value in enumerate(row):
            means[index] += float(value)
    means = [value / count for value in means]
    variances = [0.0] * width
    for row in rows:
        for index, value in enumerate(row):
            delta = float(value) - means[index]
            variances[index] += delta * delta
    # StandardScaler uses the population variance (ddof=0).
    variances = [value / count for value in variances]
    scales = [math.sqrt(value) if value > 0.0 else 1.0 for value in variances]
    return ScalerStats(means=means, scales=scales)


def apply_scaler(rows: Sequence[Sequence[float]], stats: ScalerStats) -> list[list[float]]:
    width = len(stats.means)
    scaled: list[list[float]] = []
    for row in rows:
        if len(row) != width:
            raise InputValidationError("row width does not match scaler")
        scaled.append(
            [
                (float(value) - stats.means[index]) / stats.scales[index]
                for index, value in enumerate(row)
            ]
        )
    return scaled


def split_indices(
    labels: Sequence[int],
    *,
    test_size: float = DEFAULT_TEST_SIZE,
    seed: int = DEFAULT_SPLIT_SEED,
    stratify: bool = True,
) -> SplitIndices:
    """Deterministic 70/30 split; not byte-identical to scikit-learn."""
    if not 0.0 < test_size < 1.0:
        raise InputValidationError("test_size must be between 0 and 1")
    total = len(labels)
    if total < 2:
        raise InputValidationError("at least two rows are required for a split")

    train: list[int] = []
    test: list[int] = []
    if not stratify:
        indices = list(range(total))
        random.Random(seed).shuffle(indices)
        test_count = max(1, min(total - 1, int(round(total * test_size))))
        test = sorted(indices[:test_count])
        train = sorted(indices[test_count:])
        return SplitIndices(train=train, test=test)

    classes = sorted({int(label) for label in labels})
    for position, cls in enumerate(classes):
        members = [index for index, label in enumerate(labels) if int(label) == cls]
        rng = random.Random((seed << 8) ^ (position * 0x9E3779B1) ^ cls)
        rng.shuffle(members)
        if len(members) < 2:
            train.extend(members)
            continue
        count = int(round(len(members) * test_size))
        count = max(1, min(len(members) - 1, count))
        test.extend(members[:count])
        train.extend(members[count:])

    if not test:
        moved = train.pop()
        test.append(moved)
    if not train:
        moved = test.pop()
        train.append(moved)
    return SplitIndices(train=sorted(train), test=sorted(test))


def preprocess(
    rows: Sequence[Sequence[float]],
    labels: Sequence[int],
    *,
    feature_names: Sequence[str],
    mode: str = "clean",
    test_size: float = DEFAULT_TEST_SIZE,
    seed: int = DEFAULT_SPLIT_SEED,
    stratify: bool = True,
) -> PreprocessedDataset:
    if mode not in PREPROCESS_MODES:
        raise InputValidationError(f"mode must be one of {', '.join(PREPROCESS_MODES)}")
    if len(rows) != len(labels):
        raise InputValidationError("feature and label row counts differ")
    if not rows:
        raise InputValidationError("dataset is empty")
    width = len(rows[0])
    if len(feature_names) != width:
        raise InputValidationError("feature name count does not match row width")
    for row in rows:
        if len(row) != width:
            raise InputValidationError("inconsistent feature widths")

    split = split_indices(labels, test_size=test_size, seed=seed, stratify=stratify)

    if mode == "legacy":
        stats = fit_scaler(rows)
        scaled = apply_scaler(rows, stats)
        differences = [
            "legacy mode fits the scaler on all rows before splitting, so test "
            "statistics leak into training"
        ]
    else:
        train_raw = [rows[index] for index in split.train]
        stats = fit_scaler(train_raw)
        scaled = apply_scaler(rows, stats)
        differences = []

    train_rows = [scaled[index] for index in split.train]
    test_rows = [scaled[index] for index in split.test]
    train_labels = [int(labels[index]) for index in split.train]
    test_labels = [int(labels[index]) for index in split.test]

    return PreprocessedDataset(
        mode=mode,
        feature_names=list(feature_names),
        train_rows=train_rows,
        test_rows=test_rows,
        train_labels=train_labels,
        test_labels=test_labels,
        split=split,
        scaler=stats,
        seed=seed,
        test_size=test_size,
        differences=differences,
    )
