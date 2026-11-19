"""Small test helpers."""

from __future__ import annotations

from fastapi.testclient import TestClient


def make_csv(
    *,
    rows: int = 12,
    features: int = 48,
    label: str = "Label",
    feature_value: str = "0.5",
    label_values: tuple[str, str] = ("0", "1"),
) -> bytes:
    header = [f"f{i}" for i in range(features)] + [label]
    lines = [",".join(header)]
    for index in range(rows):
        values = [feature_value] * features
        values.append(label_values[index % 2])
        lines.append(",".join(values))
    return ("\n".join(lines) + "\n").encode("utf-8")


def upload_dataset(
    client: TestClient,
    *,
    content: bytes | None = None,
    filename: str = "dataset.csv",
    dataset_type: str = "insdn",
    name: str = "Test dataset",
    label_column: str | None = None,
):
    data = {"dataset_type": dataset_type, "name": name}
    if label_column is not None:
        data["label_column"] = label_column
    return client.post(
        "/api/v1/datasets",
        files={"file": (filename, content if content is not None else make_csv(), "text/csv")},
        data=data,
    )


def create_experiment(
    client: TestClient,
    dataset_id: str,
    *,
    name: str = "Experiment",
    client_count: int = 4,
):
    return client.post(
        "/api/v1/experiments",
        json={"name": name, "dataset_id": dataset_id, "client_count": client_count},
    )
