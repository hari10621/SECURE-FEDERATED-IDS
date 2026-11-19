from __future__ import annotations

from .helpers import make_csv, upload_dataset


def test_upload_list_get_and_revalidate(client):
    response = upload_dataset(client)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["rows"] == 12
    assert body["columns"] == 49
    assert body["feature_count"] == 48
    assert body["label_column"] == "Label"
    assert body["label_counts"] == {"0": 6, "1": 6}
    assert body["research_compatible"] is True
    assert len(body["sha256"]) == 64

    datasets_dir = client.app.state.paths.datasets_dir
    files = list(datasets_dir.glob("*.csv"))
    assert len(files) == 1

    listed = client.get("/api/v1/datasets").json()
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == body["id"]

    fetched = client.get(f"/api/v1/datasets/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == body["id"]

    validated = client.post(f"/api/v1/datasets/{body['id']}/validate")
    assert validated.status_code == 200
    assert validated.json()["valid"] is True


def test_validate_endpoint_does_not_persist(client):
    response = client.post(
        "/api/v1/datasets/validate",
        files={"file": ("check.csv", make_csv(), "text/csv")},
    )
    assert response.status_code == 200
    assert response.json()["valid"] is True
    assert client.get("/api/v1/datasets").json()["total"] == 0


def test_rejects_wrong_extension(client):
    response = upload_dataset(client, filename="dataset.txt", content=b"a,b\n1,0\n")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert list(client.app.state.paths.datasets_dir.glob("*")) == []


def test_rejects_non_numeric_feature(client):
    content = b"f0,Label\nnot-a-number,0\n"
    response = upload_dataset(client, content=content)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_rejects_non_binary_label(client):
    content = b"f0,Label\n1.0,2\n"
    response = upload_dataset(client, content=content)
    assert response.status_code == 422


def test_rejects_ragged_row(client):
    content = b"f0,f1,Label\n1.0,2.0,0\n1.0,0\n"
    response = upload_dataset(client, content=content)
    assert response.status_code == 422


def test_rejects_missing_label_column(client):
    response = upload_dataset(client, label_column="Missing")
    assert response.status_code == 422


def test_filename_path_traversal_is_sanitized(client):
    response = upload_dataset(client, filename="..\\..\\evil.csv")
    assert response.status_code == 201
    assert response.json()["original_filename"] == "evil.csv"
    assert not (client.app.state.paths.base_dir / "evil.csv").exists()
    assert list(client.app.state.paths.datasets_dir.glob("*.csv"))


def test_rejects_oversized_upload(client):
    too_big = b"a,b\n" + (b"1,0\n" * 100_000)
    response = upload_dataset(client, content=too_big)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


def test_non_research_compatible_dataset_is_flagged(client):
    response = upload_dataset(client, content=make_csv(features=2, rows=4))
    assert response.status_code == 201
    assert response.json()["research_compatible"] is False
    assert response.json()["warnings"]
