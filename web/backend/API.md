# SecureFed-IDS Backend API

Base path: `/api/v1`. Interactive documentation: `/docs`.

All responses are JSON. Errors always use:

```json
{
  "error": {
    "code": "validation_error",
    "message": "request validation failed",
    "details": []
  }
}
```

Common error codes: `validation_error` (422), `not_found` (404), `conflict` (409),
`unauthorized` (401), `payload_too_large` (413), `unavailable` (503),
`internal_error` (500).

## Authentication

Authentication is disabled when `SECUREFED_API_TOKEN` is unset. When set, send:

```http
Authorization: Bearer <token>
```

Protected routes: datasets, experiments, clients, jobs, and predictions.
Unprotected: `/health`, `/version`, `/encryption/status`, `/sdn/status`.

`/health` and `/version` also return `X-Request-ID`; a caller may supply
`X-Request-ID` (sanitized to letters, digits, `.`, `_`, `-`).

## System

### `GET /health`

```json
{
  "status": "ok",
  "version": "0.1.0",
  "database": "ok",
  "encryption": "unavailable",
  "timestamp": "2026-11-18T18:00:00Z"
}
```

Returns `503` with `status: "degraded"` if SQLite cannot be queried.

### `GET /version`

```json
{
  "name": "SecureFed-IDS API",
  "version": "0.1.0",
  "api_version": "v1",
  "environment": "local",
  "python_version": "3.14.4"
}
```

### `GET /encryption/status`

```json
{
  "available": false,
  "backend": "native_ckks",
  "reason": "Native CKKS backend is not installed or verified. Encrypted aggregation and threshold decryption are disabled."
}
```

### `GET /sdn/status`

```json
{
  "available": false,
  "reason": "SDN/IPS integration is not implemented in Phase 3."
}
```

## Datasets

Datasets are stored under `web/var/datasets`. Uploads are streamed with a size
limit and validated before metadata is persisted. A valid research-compatible
dataset has exactly 48 numeric feature columns and a binary label column; the
label defaults to the last column.

### `POST /datasets`

Multipart form fields:

| Field | Required | Notes |
|---|---|---|
| `file` | yes | `.csv` only |
| `dataset_type` | yes | `insdn`, `cicids2017`, or `cicids2019` |
| `name` | no | Defaults to the sanitized filename |
| `label_column` | no | Defaults to the last column |

```bash
curl -X POST http://127.0.0.1:8000/api/v1/datasets \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@data.csv;type=text/csv" \
  -F "dataset_type=insdn" \
  -F "name=InSDN sample"
```

`201 Created`:

```json
{
  "id": "2b8d...",
  "name": "InSDN sample",
  "dataset_type": "insdn",
  "original_filename": "data.csv",
  "sha256": "…64 hex characters…",
  "size_bytes": 6123,
  "rows": 12,
  "columns": 49,
  "feature_count": 48,
  "label_column": "Label",
  "label_column_index": 48,
  "label_counts": {"0": 6, "1": 6},
  "validation_status": "valid",
  "validation_errors": [],
  "warnings": [],
  "research_compatible": true,
  "created_at": "2026-11-18T18:00:00Z"
}
```

A non-compatible but valid CSV may be stored with
`research_compatible: false`; the warnings explain why. Experiments reject it.

### `POST /datasets/validate`

Validates an upload without persisting metadata or retaining the file.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/datasets/validate \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@data.csv;type=text/csv"
```

Returns a validation report:

```json
{
  "valid": true,
  "rows": 12,
  "columns": 49,
  "feature_count": 48,
  "label_column": "Label",
  "label_column_index": 48,
  "label_counts": {"0": 6, "1": 6},
  "warnings": [],
  "errors": [],
  "research_compatible": true
}
```

Validation problems (bad extension, oversized payload, or parse failure) are
returned as `422`/`413` error envelopes. A parseable CSV with schema or label
problems returns `200` with `valid: false` and populated `errors`, so callers can
inspect the report before uploading. `research_compatible` is true only for a
valid file with 48 features and the label in the last column.

### `GET /datasets?limit=50&offset=0`

```json
{"items": [/* dataset responses */], "total": 1}
```

### `GET /datasets/{dataset_id}`

Returns one dataset or `404`.

### `POST /datasets/{dataset_id}/validate`

Re-parses the stored file and returns a validation report. Does not create a new
record.

## Experiments

### `POST /experiments`

```bash
curl -X POST http://127.0.0.1:8000/api/v1/experiments \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"InSDN 4-client run","dataset_id":"2b8d…","client_count":4}'
```

`client_count` must be `4`, `8`, or `12`. The dataset must be valid and
research-compatible, and the dataset type/client count pair must have an
allowlisted script. A missing variant (for example CICIDS2017 with 8 clients) is
rejected with `422`.

`201 Created` returns an experiment with `status: "created"` and `job_id: null`.

### `GET /experiments?limit=50&offset=0`

Returns `{"items": [...], "total": n}`.

### `GET /experiments/{experiment_id}`

Returns the experiment or `404`.

### `GET /experiments/{experiment_id}/status`

```json
{
  "id": "8f1a…",
  "status": "created",
  "execution_available": false,
  "execution_reason": "Native CKKS backend is not installed or verified. Encrypted aggregation and threshold decryption are disabled.",
  "simulation_available": false,
  "simulation_reason": "Plaintext simulation is disabled by configuration.",
  "training_available": false,
  "training_reason": "GRU training is disabled by configuration.",
  "job": null
}
```

`execution_available` is true only when configuration, script availability, and
the encryption backend all pass. In Phase 3/4 the encryption backend is always
unavailable, so this is false. `simulation_available` is independent: it is
true only when `SECUREFED_ENABLE_SIMULATION` is set and the dataset is a valid
48-feature research-compatible file. `training_available` additionally requires
`SECUREFED_ENABLE_TRAINING=true` and an importable TensorFlow runtime.

### `POST /experiments/{experiment_id}/start`

Returns a job when encrypted execution is available. In Phase 3/4 this returns
`503` with `{"error":{"code":"unavailable",...}}`. No job or fake metrics are
created.

### `POST /experiments/{experiment_id}/simulate`

Runs the opt-in deterministic plaintext simulation and returns a normal job
(`200`). This does not use CKKS, does not run the research scripts, and does not
claim paper parity.

```json
{
  "mode": "clean",
  "rounds": 5,
  "local_epochs": 2,
  "batch_size": 32,
  "learning_rate": 0.05,
  "weighting": "sample",
  "seed": 42,
  "test_size": 0.3,
  "byzantine_check": false
}
```

`mode` is `clean` or `legacy`; `weighting` is `sample` or `legacy`. Poll the
returned job, then read the experiment. Its `result` contains
`mode: "plaintext_simulation"`, `encrypted: false`, `encryption_claimed: false`,
`parity: "unverified"`, `model.research_model: false`, per-round records, and
final metrics. `503` is returned when simulation is disabled; invalid settings
return `422`.

The in-process loader is capped by `SECUREFED_SIMULATION_MAX_ROWS`; exceeding it
fails the job rather than loading an unbounded dataset.

### `POST /experiments/{experiment_id}/train`

Runs opt-in plaintext federated training with the real Keras GRU and returns a
normal job (`200`). Requires `SECUREFED_ENABLE_TRAINING=true` and TensorFlow in
the backend Python process; otherwise returns `503`. The body is optional.

```json
{
  "mode": "legacy",
  "rounds": 1,
  "local_epochs": 1,
  "batch_size": 32,
  "learning_rate": 0.0001,
  "weighting": "legacy",
  "seed": 42,
  "test_size": 0.3,
  "byzantine_check": false,
  "byzantine_threshold": 2,
  "threshold": 3,
  "require_encryption": false,
  "max_rows": 5000
}
```

Defaults are a one-round, one-epoch smoke run. Set `rounds: 15` and
`local_epochs: 5` explicitly for the legacy loop size. The threshold defaults
to `client_count // 2 + 1`.

Poll the job, then read the experiment. Its `result` contains:

- `mode: "plaintext_federated_training"`, `encrypted: false`,
  `encryption_claimed: false`, `parity: "unverified"`;
- `model.name: "keras_gru"`, `model.research_model: true`;
- `config`, `dataset`, per-round records, `final_metrics`, and `workload`;
- `artifact` metadata with relative paths and SHA-256 digests.

Artifacts under `web/var/models/<experiment_id>/` are the weight JSON
(`<dataset>_<clients>_model.json`), `preprocessing.json`, and `result.json`.

`require_encryption: true` returns `503`; no CKKS training path exists. The
in-process loader is capped by `SECUREFED_TRAINING_MAX_ROWS` and the optional
`max_rows` field; exceeding it fails the job. This is not encrypted federated
learning, not independent clients, and not a paper-parity claim.

### `POST /experiments/{experiment_id}/cancel`

Requests cancellation for the experiment's current job. Returns the updated job.
`409` if there is no job or it is already terminal.

## Jobs

### `GET /jobs?experiment_id=...&limit=50`

Returns `{"items": [...], "total": n}`. Jobs include `status`, `progress`
(0.0-1.0), `message`, `result`, `error`, `cancel_requested`, and timestamps.

### `GET /jobs/{job_id}`

Returns one job or `404`.

### `POST /jobs/{job_id}/cancel`

Requests cancellation and returns the persisted job. A queued or running job
moves to `cancellation_requested`, then `cancelled`. Cancelling a terminal job
returns `409`. Unknown jobs return `404`.

Restart recovery marks jobs and experiments that were active at shutdown as
`failed` with a message explaining that the process restarted before completion.

## Clients

These are configuration records only. No client runtime is launched.

### `POST /clients`

```json
{"name": "client-1", "config": {"dataset_type": "insdn"}}
```

`201 Created`; duplicate names return `409`.

### `GET /clients?limit=50&offset=0`

Returns `{"items": [...], "total": n}`.

### `GET /clients/{client_id}`

Returns one client or `404`.

### `PATCH /clients/{client_id}`

```json
{"status": "disabled", "config": {"notes": "local test"}}
```

`status` is one of `configured`, `enabled`, `disabled`.

### `GET /clients/{client_id}/status`

```json
{
  "id": "c41e…",
  "status": "configured",
  "runtime_connected": false,
  "detail": "Configuration only. Independent client runtimes and authenticated client sessions are not implemented in Phase 3."
}
```

## Predictions

### `GET /predictions/status`

```json
{
  "available": false,
  "reason": "No verified model and preprocessing manifest are configured.",
  "model": null,
  "preprocessing": null
}
```

### `POST /predictions`

```json
{"features": [0.1, 0.2, 0.3]}
```

Returns `503 unavailable`. No prediction, probability, or metric is fabricated.
No model file is loaded while the backend is unavailable.

## HTTP status summary

| Status | Meaning |
|---|---|
| `200` | Read/validate/cancel succeeded |
| `201` | Dataset, experiment, or client created |
| `401` | Missing or wrong bearer token when configured |
| `404` | Unknown dataset, experiment, client, or job |
| `409` | Duplicate active job, duplicate client, or finished/no job cancellation |
| `413` | Upload exceeds `SECUREFED_MAX_UPLOAD_BYTES` |
| `422` | Validation failure or unsupported dataset/script combination |
| `503` | Encrypted execution, simulation, GRU training, encryption, prediction, or mitigation unavailable |
