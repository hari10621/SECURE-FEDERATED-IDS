"""Dataset upload, CSV validation, and metadata persistence."""

from __future__ import annotations

import csv
import hashlib
import math
import uuid
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from sqlalchemy import func, select

from ..config import Settings
from ..db import Database
from ..enums import DatasetType, ValidationStatus
from ..errors import InputValidationError, NotFoundError, PayloadTooLargeError
from ..models import Dataset
from ..storage.paths import StoragePaths
from .security_service import SecurityService

EXPECTED_FEATURE_COUNT = 48
MAX_REPORTED_ERRORS = 25


@dataclass
class CsvValidation:
    valid: bool
    rows: int
    columns: int
    feature_count: int
    label_column: str
    label_column_index: int
    label_counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    research_compatible: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "rows": self.rows,
            "columns": self.columns,
            "feature_count": self.feature_count,
            "label_column": self.label_column,
            "label_column_index": self.label_column_index,
            "label_counts": self.label_counts,
            "warnings": self.warnings,
            "errors": self.errors,
            "research_compatible": self.research_compatible,
        }


def validate_csv_file(
    path: Path,
    *,
    label_column: str | None,
    max_rows: int,
    max_columns: int,
) -> CsvValidation:
    errors: list[str] = []
    warnings: list[str] = []

    try:
        handle = path.open("r", encoding="utf-8-sig", newline="")
    except OSError as exc:
        return CsvValidation(
            valid=False,
            rows=0,
            columns=0,
            feature_count=0,
            label_column=label_column or "",
            label_column_index=-1,
            errors=[f"cannot read CSV: {exc.__class__.__name__}"],
        )

    with handle:
        reader = csv.reader(handle)
        try:
            header = [cell.strip() for cell in next(reader)]
        except StopIteration:
            return CsvValidation(
                valid=False,
                rows=0,
                columns=0,
                feature_count=0,
                label_column=label_column or "",
                label_column_index=-1,
                errors=["CSV is empty"],
            )

        if len(header) > max_columns:
            errors.append(f"too many columns: {len(header)} > {max_columns}")
        if len(header) < 2:
            errors.append("CSV must contain at least one feature and one label column")
        if any(not cell for cell in header):
            errors.append("header contains an empty column name")
        if len(set(header)) != len(header):
            errors.append("header contains duplicate column names")

        selected_label = label_column
        if selected_label is None:
            selected_label = header[-1] if header else ""
        if selected_label not in header:
            errors.append(f"label column not found: {selected_label!r}")
            label_index = -1
        else:
            label_index = header.index(selected_label)

        feature_indices = [i for i in range(len(header)) if i != label_index] if label_index >= 0 else []
        feature_count = len(feature_indices)
        if feature_count == 0:
            errors.append("no feature columns remain after selecting the label column")

        if label_index >= 0 and label_index != len(header) - 1:
            warnings.append("research scripts assume the label is the last column")
        if selected_label and selected_label != "Label":
            warnings.append("SHAP feature-name extraction expects a column named 'Label'")
        if feature_count and feature_count != EXPECTED_FEATURE_COUNT:
            warnings.append(
                f"research scripts expect {EXPECTED_FEATURE_COUNT} features; found {feature_count}"
            )

        row_count = 0
        labels: Counter[str] = Counter()
        for line_number, row in enumerate(reader, start=2):
            if not row or all(not cell.strip() for cell in row):
                errors.append(f"line {line_number}: empty row")
                if len(errors) >= MAX_REPORTED_ERRORS:
                    break
                continue
            if len(row) != len(header):
                errors.append(
                    f"line {line_number}: expected {len(header)} columns, found {len(row)}"
                )
                if len(errors) >= MAX_REPORTED_ERRORS:
                    break
                continue
            for index in feature_indices:
                raw = row[index].strip()
                try:
                    value = float(raw)
                except ValueError:
                    errors.append(f"line {line_number}: non-numeric feature {header[index]!r}")
                    break
                if not math.isfinite(value):
                    errors.append(f"line {line_number}: non-finite feature {header[index]!r}")
                    break
            else:
                if label_index >= 0:
                    raw_label = row[label_index].strip()
                    try:
                        label_value = float(raw_label)
                    except ValueError:
                        errors.append(f"line {line_number}: non-numeric label")
                    else:
                        if not math.isfinite(label_value) or label_value not in (0.0, 1.0):
                            errors.append(f"line {line_number}: label must be binary 0 or 1")
                        else:
                            labels[str(int(label_value))] += 1
            row_count += 1
            if row_count > max_rows:
                errors.append(f"row limit exceeded: more than {max_rows} rows")
                break
            if len(errors) >= MAX_REPORTED_ERRORS:
                break

    if row_count == 0 and not errors:
        errors.append("CSV contains no data rows")
    if row_count > 0 and len(labels) != 2 and not errors:
        errors.append("CSV must contain exactly two binary label values (0 and 1)")

    valid = not errors
    return CsvValidation(
        valid=valid,
        rows=row_count,
        columns=len(header),
        feature_count=feature_count,
        label_column=selected_label or "",
        label_column_index=label_index,
        label_counts=dict(sorted(labels.items())),
        warnings=warnings,
        errors=errors,
        research_compatible=valid
        and feature_count == EXPECTED_FEATURE_COUNT
        and label_index == len(header) - 1,
    )


class DatasetService:
    def __init__(
        self,
        db: Database,
        paths: StoragePaths,
        security: SecurityService,
        settings: Settings,
    ) -> None:
        self.db = db
        self.paths = paths
        self.security = security
        self.settings = settings

    async def save_upload(
        self,
        upload: UploadFile,
        *,
        dataset_type: DatasetType,
        name: str | None,
        label_column: str | None,
    ) -> Dataset:
        original = self.security.sanitize_filename(upload.filename)
        if not original.lower().endswith(".csv"):
            raise InputValidationError("only .csv files are accepted")

        label = self.security.sanitize_column_name(label_column)
        dataset_id = uuid.uuid4().hex
        target = self.paths.datasets_dir / f"{dataset_id}.csv"
        if not target.resolve().is_relative_to(self.paths.datasets_dir):
            raise InputValidationError("invalid storage target")

        try:
            size, sha256 = await self._stream_to_path(upload, target)
            report = validate_csv_file(
                target,
                label_column=label,
                max_rows=self.settings.max_csv_rows,
                max_columns=self.settings.max_csv_columns,
            )
            if not report.valid:
                target.unlink(missing_ok=True)
                raise InputValidationError("CSV validation failed", details=report.errors)

            display_name = self.security.sanitize_display_name(
                name or Path(original).stem,
                fallback=f"dataset-{dataset_id[:8]}",
            )
            record = Dataset(
                id=dataset_id,
                name=display_name,
                dataset_type=dataset_type.value,
                original_filename=original,
                stored_relative=target.relative_to(self.paths.data_dir).as_posix(),
                sha256=sha256,
                size_bytes=size,
                rows=report.rows,
                columns=report.columns,
                feature_count=report.feature_count,
                label_column=report.label_column,
                label_column_index=report.label_column_index,
                label_counts=report.label_counts,
                validation_status=ValidationStatus.VALID.value,
                validation_errors=[],
                warnings=report.warnings,
                research_compatible=report.research_compatible,
            )
            with self.db.session() as session:
                session.add(record)
            return record
        except Exception:
            target.unlink(missing_ok=True)
            raise
        finally:
            await upload.close()

    async def validate_upload(
        self,
        upload: UploadFile,
        *,
        label_column: str | None,
    ) -> CsvValidation:
        original = self.security.sanitize_filename(upload.filename)
        if not original.lower().endswith(".csv"):
            raise InputValidationError("only .csv files are accepted")
        label = self.security.sanitize_column_name(label_column)
        temp = self.paths.uploads_dir / f"validate-{uuid.uuid4().hex}.csv"
        try:
            await self._stream_to_path(upload, temp)
            return validate_csv_file(
                temp,
                label_column=label,
                max_rows=self.settings.max_csv_rows,
                max_columns=self.settings.max_csv_columns,
            )
        finally:
            temp.unlink(missing_ok=True)
            await upload.close()

    async def _stream_to_path(self, upload: UploadFile, target: Path) -> tuple[int, str]:
        digest = hashlib.sha256()
        size = 0
        with target.open("wb") as handle:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > self.settings.max_upload_bytes:
                    handle.close()
                    target.unlink(missing_ok=True)
                    raise PayloadTooLargeError(
                        f"upload exceeds {self.settings.max_upload_bytes} bytes"
                    )
                digest.update(chunk)
                handle.write(chunk)
        if size == 0:
            target.unlink(missing_ok=True)
            raise InputValidationError("uploaded file is empty")
        return size, digest.hexdigest()

    def list(self, *, limit: int = 50, offset: int = 0) -> tuple[list[Dataset], int]:
        with self.db.session() as session:
            total = session.scalar(select(func.count()).select_from(Dataset)) or 0
            rows = list(
                session.scalars(
                    select(Dataset)
                    .order_by(Dataset.created_at.desc())
                    .limit(limit)
                    .offset(offset)
                )
            )
        return rows, total

    def get(self, dataset_id: str) -> Dataset:
        with self.db.session() as session:
            record = session.get(Dataset, dataset_id)
            if record is None:
                raise NotFoundError(f"dataset not found: {dataset_id}")
            return record

    def path_for(self, dataset: Dataset) -> Path:
        return self.paths.dataset_path(dataset.stored_relative)

    def revalidate(self, dataset_id: str) -> tuple[Dataset, CsvValidation]:
        record = self.get(dataset_id)
        path = self.path_for(record)
        if not path.is_file():
            with self.db.session() as session:
                stored = session.get(Dataset, dataset_id)
                if stored is not None:
                    stored.validation_status = ValidationStatus.INVALID.value
                    stored.validation_errors = ["stored CSV file is missing"]
            raise NotFoundError("stored dataset file is missing")

        report = validate_csv_file(
            path,
            label_column=record.label_column,
            max_rows=self.settings.max_csv_rows,
            max_columns=self.settings.max_csv_columns,
        )
        with self.db.session() as session:
            stored = session.get(Dataset, dataset_id)
            if stored is None:
                raise NotFoundError(f"dataset not found: {dataset_id}")
            stored.rows = report.rows
            stored.columns = report.columns
            stored.feature_count = report.feature_count
            stored.label_column = report.label_column
            stored.label_column_index = report.label_column_index
            stored.label_counts = report.label_counts
            stored.warnings = report.warnings
            stored.validation_status = (
                ValidationStatus.VALID.value if report.valid else ValidationStatus.INVALID.value
            )
            stored.validation_errors = report.errors
            stored.research_compatible = report.research_compatible
            session.flush()
            session.refresh(stored)
        return stored, report
