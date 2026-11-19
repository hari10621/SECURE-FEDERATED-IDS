# SecureFed-IDS Backend

Local-first FastAPI backend for SecureFed-IDS. It provides persisted metadata,
safe CSV validation, experiment/job orchestration, the client-configuration
API, a read-only research adapter (Phase 3), a deterministic plaintext
federated simulation core (Phase 4), and opt-in plaintext Keras GRU training.
Encryption, prediction, SDN mitigation, paper-level parity, and independent
client runtimes remain unavailable until verified implementations exist.

The upstream research repository at `../threshold-fl-ids-sdn` is treated as
read-only. It is never imported into the API process.

## Status

- Backend foundation: implemented and unit-tested.
- Dataset upload/validation: implemented; labels must be binary (`0`/`1`) and
  research-compatible files need exactly 48 numeric features with the label in
  the last column.
- Experiment lifecycle: create/list/detail/status/start/cancel are implemented.
  `start` remains unavailable because no verified CKKS backend is configured.
- Federated core: implemented as a deterministic plaintext simulation with
  stable client IDs, seeded partitioning, sample/legacy weighting, binary
  metrics, and a reference linear harness backend. It is not the research GRU.
- Simulation API: `POST /experiments/{id}/simulate` is opt-in via
  `SECUREFED_ENABLE_SIMULATION` (default `false`) and always labels results
  `mode: plaintext_simulation` and `encrypted: false`.
- GRU training API: `POST /experiments/{id}/train` is opt-in via
  `SECUREFED_ENABLE_TRAINING` (default `false`). It runs the real Keras GRU when
  TensorFlow is installed, writes model/preprocessing/result artifacts, and
  labels results `mode: plaintext_federated_training`, `encrypted: false`.
  Defaults are a one-round, one-epoch smoke run.
- Research adapter: fixed script allowlist, isolated run workspace, fixed Python
  executable, `shell=False`, no API token in the child environment, and
  process-group termination on cancellation.
- Encryption: fail-closed. No fake ciphertext is produced or returned.
- Predictions: fail-closed. No model is loaded and no fake metrics are returned.
- SDN mitigation: fail-closed. No controller is contacted.
- Client runtime: configuration records only; every status reports
  `runtime_connected: false`.
- React frontend: implemented in `web/frontend`; lint (typecheck), 17 tests,
  and production build pass.
- GRU training availability depends on the Python process importing TensorFlow.
  The default Python 3.14 test environment does not have it; an isolated
  Python 3.11 + `tensorflow-cpu==2.13.1` runtime was used for verification.

## Requirements

- Python 3.10 or newer for the backend. The test suite was run on Python 3.14.4
  (WSL2 Ubuntu 26.04).
- Linux is the intended runtime for research jobs. Windows is supported for the
  API and tests, but the original CKKS extension targets CPython 3.8 on Linux
  x86-64 and remains unavailable.
- GRU training is optional. It requires a separate environment with TensorFlow;
  verification used Python 3.11.18 and `tensorflow-cpu==2.13.1`. The default
  backend requirements deliberately do not include TensorFlow.
- The legacy research worker, when it eventually exists, must use a separate
  Python 3.8 / OpenFHE environment. It must not be merged into this backend
  environment.

## Setup

```bash
cd web/backend
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
pytest
```

Windows PowerShell:

```powershell
cd web\backend
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
pytest
```

Run locally on loopback only:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

OpenAPI is available at `http://127.0.0.1:8000/docs`.

Optional GRU training runtime (Python 3.11):

```bash
python3.11 -m venv .venv-tf
source .venv-tf/bin/activate
python -m pip install -r requirements-training.txt
SECUREFED_ENABLE_TRAINING=true uvicorn app.main:app --host 127.0.0.1 --port 8000
```

TensorFlow is intentionally absent from the lightweight API requirements. A
`/train` request returns `503` when the running Python process cannot import it.

## Configuration

All settings are optional environment variables prefixed with `SECUREFED_`.
Defaults keep data under `web/var` and bind to no public interface.

| Variable | Default | Purpose |
|---|---|---|
| `SECUREFED_BASE_DIR` | `web/` | Project directory; writable data must be inside it |
| `SECUREFED_DATA_DIR` | `web/var` | Datasets, run workspaces, models, and SQLite database |
| `SECUREFED_DATABASE_URL` | `sqlite:///web/var/securefed.db` | SQLAlchemy database URL |
| `SECUREFED_MAX_UPLOAD_BYTES` | `536870912` | Maximum upload size |
| `SECUREFED_MAX_CSV_ROWS` | `2000000` | Maximum data rows |
| `SECUREFED_MAX_CSV_COLUMNS` | `256` | Maximum columns |
| `SECUREFED_RESEARCH_REPO_DIR` | `threshold-fl-ids-sdn/` | Read-only research repository |
| `SECUREFED_RESEARCH_PYTHON` | unset | Absolute path to the legacy Python 3.8 interpreter |
| `SECUREFED_CKKS_RUNTIME_DIR` | `web/var/ckks` | Reserved location for the native runtime |
| `SECUREFED_ENABLE_RESEARCH_EXECUTION` | `false` | Master switch; not sufficient by itself |
| `SECUREFED_ENABLE_SIMULATION` | `false` | Enables the plaintext simulation endpoint |
| `SECUREFED_SIMULATION_MAX_ROWS` | `5000` | Row cap for the in-process simulation |
| `SECUREFED_ENABLE_TRAINING` | `false` | Enables the plaintext GRU training endpoint |
| `SECUREFED_TRAINING_MAX_ROWS` | `5000` | Row cap for in-process GRU training |
| `SECUREFED_ENABLE_PREDICTIONS` | `false` | Master switch; not sufficient by itself |
| `SECUREFED_JOB_WORKERS` | `1` | In-process worker threads (1-8) |
| `SECUREFED_API_TOKEN` | unset | Optional shared bearer token for local access |
| `SECUREFED_LOG_LEVEL` | `INFO` | Logging level |

If `SECUREFED_API_TOKEN` is set, send `Authorization: Bearer <token>` to all
resource routes. `/health`, `/version`, `/encryption/status`, and `/sdn/status`
remain unauthenticated so liveness checks do not require a secret.

## Layout

```text
web/backend/
  app/
    main.py                 app factory, lifespan, error envelopes, request IDs
    config.py               environment-backed settings and path validation
    db.py                   SQLite engine/session setup
    models.py               Dataset, Experiment, Client, Job tables
    schemas.py              request/response contracts
    api/                    health, datasets, experiments, clients, jobs, predictions
    domain/
      model.py              GRU description, weight codec, artifact round-trip
      dataset.py            CSV loader, scaler, deterministic legacy/clean split
      metrics.py            binary metrics plus ROC AUC
      federated/            simulated client, server, backends, Keras GRU, round harness
      crypto/               fail-closed crypto interfaces and plaintext status
    services/
      dataset_service.py    streaming upload, CSV validation, revalidation
      experiment_service.py persisted experiment records
      federated_service.py  orchestration and fail-closed availability
      simulation_service.py plaintext simulation over a validated dataset
      training_service.py   plaintext GRU training, final weights, artifacts
      job_service.py        job persistence and duplicate suppression
      job_manager.py        worker pool, progress, cancellation, restart recovery
      research_adapter.py   fixed allowlist and isolated run workspace
      encryption_service.py explicit unavailable backend
      model_service.py      explicit unavailable prediction backend
      sdn_service.py        explicit unavailable mitigation backend
    storage/paths.py        path confinement helpers
  tests/                    API, validation, job, adapter, domain, and simulation tests
```

## Safety invariants

- No arbitrary shell or Python execution. The only executable command is built
  from an allowlisted research script, a configured absolute Python path, and a
  prepared run workspace.
- Uploads are streamed to disk with a size cap; filenames are sanitized; writes
  are confined beneath `web/var`.
- CSV validation checks extension, encoding, row width, numeric features, binary
  labels, and the 48-feature research schema.
- All errors use one JSON envelope:
  `{"error": {"code": "...", "message": "...", "details": ...}}`.
- The API never returns a token, encryption key, or fake encrypted value.
- Encryption, prediction, and mitigation availability is reported explicitly,
  not inferred from the presence of a flag.
- Database, job, and experiment state are persisted in SQLite. A restart marks
  previously active jobs and experiments as failed instead of silently resuming
  them.
- Simulation results always report `mode: plaintext_simulation`,
  `encrypted: false`, `encryption_claimed: false`, and `parity: unverified`.
- GRU training results always report `mode: plaintext_federated_training`,
  `encrypted: false`, `encryption_claimed: false`, and `parity: unverified`.
- A terminal job is never overwritten back to `queued` by late bookkeeping; the
  job attachment update is atomic in SQL.

## Plaintext simulation (Phase 4)

`POST /api/v1/experiments/{id}/simulate` runs the deterministic domain harness
on a validated 48-feature dataset. It is disabled by default and requires
`SECUREFED_ENABLE_SIMULATION=true`.

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

The response is a normal job. When it succeeds, the experiment `result` says:

- `mode: "plaintext_simulation"`, `encrypted: false`;
- `model.name: "reference_linear"`, `model.research_model: false`;
- `parity: "unverified"` with a list of legacy differences;
- per-round participants, scaling factors, digests, and metrics;
- final binary metrics including AUC.

This path is not encrypted federated learning, not the GRU, and not a
reproduction of the paper. The encrypted research path (`/start`) is unchanged
and still returns `503`.

## Plaintext GRU training (user Phase 5)

`POST /api/v1/experiments/{id}/train` runs the real Keras GRU through the
in-process federated harness. It is disabled by default and requires
`SECUREFED_ENABLE_TRAINING=true` **and** a Python runtime that can import
TensorFlow.

The request body is optional. The conservative defaults are one round and one
local epoch so a smoke run does not start a research-sized job accidentally.
Explicitly set `rounds: 15` and `local_epochs: 5` for the legacy loop size.

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
  "require_encryption": false
}
```

On success the experiment result contains:

- `mode: "plaintext_federated_training"`, `encrypted: false`,
  `encryption_claimed: false`, `parity: "unverified"`;
- `model.name: "keras_gru"`, `model.research_model: true`;
- configuration, dataset summary, per-round records, and final metrics;
- `workload.independent_clients: false`;
- `artifact` metadata with relative paths and SHA-256 digests.

Artifacts are written under `web/var/models/<experiment_id>/`:

- `<dataset>_<clients>_model.json` - weights, specs, and metadata;
- `preprocessing.json` - feature names, split, scaler, and source counts;
- `result.json` - the experiment result.

`require_encryption: true` returns `503`; no CKKS training path exists. The
loader cap is `SECUREFED_TRAINING_MAX_ROWS` (default 5000). Exceeding it fails
the job rather than silently truncating the dataset. The Keras backend seeds
TensorFlow globally per local fit; keep `SECUREFED_JOB_WORKERS=1` for
single-job determinism.

This is plaintext, in-process training. It is not encrypted federated learning,
not independent clients, and not a paper-parity claim.

## Research adapter limits

`ResearchAdapter` maps only these original scripts:

| Dataset | 4 clients | 8 clients | 12 clients |
|---|---|---|---|
| InSDN | `InSDN_4.py` | `InSDN_8.py` | `InSDN_12.py` |
| CICIDS2017 | `CICDDoS17_4.py` | unavailable | `CICDDoS17_12.py` |
| CICIDS2019 | `CICDDoD19_4.py` (original spelling) | `CICDDoS19_8.py` | `CICDDoS19_12.py` |

The adapter copies the selected script and dataset into a run directory,
creates `home/` and `tmp/`, writes a manifest, and starts the process with a
minimal environment. It does not make the research code safe against a malicious
repository; the repository is assumed to be trusted and read-only.

Cancellation terminates the research process group and records the cancelled
state. It cannot undo files the legacy script already wrote inside its isolated
run directory.

## Known gaps and limitations

- The native CKKS extension is absent. The original `.so` targets CPython 3.8,
  Linux x86-64, and OpenFHE; no source is present in the repository.
- Therefore `POST /experiments/{id}/start` returns `503 unavailable` even if the
  research execution flag is enabled.
- No datasets or trained models are included. Predictions remain unavailable.
- The research scripts contain legacy quirks: hardcoded dataset paths, fixed
  `_4` model filenames, a missing CICIDS2017 8-client script, and
  Jupyter-only behavior in `shapupdates.py`.
- The shared bearer token is a local gate, not authenticated per-client
  federated sessions. Independent clients, replay protection, and per-client
  credentials belong to later phases.
- Jobs are in-process on one host. This is not a distributed queue.
- No TLS, rate limiting, or multi-user authorization is provided.
- The Phase 4 simulation is plaintext and uses a reference linear model. It is
  not the GRU and makes no legacy metric parity claim.
- GRU training runs the real Keras architecture only when TensorFlow is
  available in the backend's Python process. The default Python 3.14
  environment lacks it, so `/train` returns `503` there.
- GRU training is plaintext, in-process, and currently verified only on
  synthetic data. It is not encrypted federated learning, not independent
  clients, and not a paper-level parity claim.
- The simulation and training load the dataset into memory, so they are capped
  by `SECUREFED_SIMULATION_MAX_ROWS` and `SECUREFED_TRAINING_MAX_ROWS`;
  full-scale runs belong to a legacy/isolated worker.
- Simulation threshold defaults to `num_clients - 1`; GRU training defaults to
  the legacy `num_clients // 2 + 1` unless `threshold` is supplied.

## Tests

From `web/backend`:

```bash
pytest
```

Last runs:

- Python 3.14.4 without TensorFlow: **80 passed, 1 skipped**.
- Isolated Python 3.11.18 + `tensorflow-cpu==2.13.1` with
  `SECUREFED_RUN_TF_TESTS=1`: **79 passed, 2 skipped**. The real Keras API test
  runs here.
- Both runs have one non-blocking Starlette `httpx` deprecation warning.

## Related documents

- `../INTEGRATION_PLAN.md` - phased plan and Phase 3/4 status.
- `../DEPENDENCY_REPORT.md` - legacy environment, CKKS, and dataset audit.
- `API.md` - endpoint reference and examples.
