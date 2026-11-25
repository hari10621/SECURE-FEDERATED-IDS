# SecureFed-IDS

SecureFed-IDS is a local research console for training a federated intrusion detector on labeled SDN flow records. It implements the plaintext GRU workflow from *A Secure and Privacy-Preserving Federated Learning-Based Intrusion Detection System for SDN Networks Using Homomorphic Encryption*. The Windows demo runs the API, training workers and dashboard on one machine. The coordinator reads the uploaded CSV and distributes training shards, so it has access to the raw data. The bundled CSVs contain generated traffic examples. Performance on the original research datasets requires separate evaluation.

## Import and run the complete project

**To reproduce this working copy on another computer**, copy the project root with its current source files, both launcher scripts, the frontend lockfile and the `datasets/` folder. Local edits and newly created files travel with a filesystem copy. A Git clone contains the version committed and pushed to the remote. For a source-only install, recreate the Python environment and Node dependencies on the destination. To migrate existing jobs, uploads and trained models too, stop the backend before copying the entire `web/var/` directory.

For the published repository, use the following commands. If you already have a copy, open PowerShell in the directory containing this README and skip the clone.

```powershell
git clone https://github.com/hari10621/SECURE-FEDERATED-IDS.git SecureFed-IDS
cd SecureFed-IDS
```

Use Python 3.12 on Windows and a Node.js version supported by the locked Vite package (Node 20.19+ within the 20.x line, or 22.12+). Install from the repository root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r web/backend/requirements-training.txt -r web/backend/requirements-dev.txt
npm.cmd ci --prefix web/frontend
```

Run `.\start_backend.ps1` in the activated terminal. In a second PowerShell window at the repository root, run `.\start_frontend.ps1`. The backend launcher enables GRU training and predictions, disables CKKS, and uses the activated Python environment when available. Otherwise it looks for the project environments in `.venv` and `web/backend/.venv-tf` before using Python on PATH. Both launchers recognize an already-running local service. The frontend launcher starts Vite. Open the [dashboard](http://127.0.0.1:5173/). Check [API health](http://127.0.0.1:8000/api/v1/health) and the [interactive API reference](http://127.0.0.1:8000/docs) independently.

## First run: verify that the model updates

1. On **Overview**, select **Run tutorial**. The backend creates a sensor and a peer, loads `datasets/insdn_compact_1k.csv`, and reserves 300 of its 1,000 flows for evaluation. The two clients each receive 350 training flows.
2. Each client trains locally for one epoch. The server combines their weights. The tutorial scores one held-out synthetic intrusion using that first global model. A probability above 0.5 produces an intrusion alert.
3. Both clients train again from the first aggregate. The dashboard scores the **same flow** with the second aggregate and displays both probabilities, decisions, weight hashes, accuracy and F1. A changed hash establishes that the weights changed. Compare accuracy and F1 on the shared test set to judge whether detection improved.
4. Reopen **Overview** to see the latest saved tutorial job. **Run tutorial again** creates a new pair of clients. The tutorial uses its own model. To make a model available on **Intrusion Detection**, train an experiment as described below.

The replay is offline. Training on labeled shards drives the update. In one verified run, held-out accuracy rose from 75.7% to 93.7% and F1 rose from 0.711 to 0.920. Both rounds missed the individual replayed intrusion. These values describe that run on synthetic data.

## Train and use your own model

1. Open **Datasets**, choose a CSV and validate or upload it. For GRU training, provide **48 numeric feature columns followed by a binary label column**. Use 0 for benign traffic and 1 for intrusion. Keep feature order consistent across training and inference. The included samples have 1,000, 5,000 and 12,000 rows. File details and generation instructions are in the [dataset guide](datasets/README.md).
2. Open **Federated Training**, create an experiment, select the validated dataset and choose **2, 3, 4, 8 or 12 clients**. The experiment starts its own workers. Manually registering clients is optional.
3. Select the quick check (one round and one local epoch) or the paper schedule (15 rounds and five local epochs). Start GRU training. The default clean split fits the scaler on training rows and reserves 30% for testing. The default training row cap is 5,000, even for larger uploads.
4. Review the job status and per-round metrics under **Federated Training**, **Experiment History** or **Performance Evaluation**. The GRU has three recurrent layers with 256, 128 and 64 units, batch normalization, dropout and a sigmoid output. Each worker receives the current global weights. Aggregation weights each client by its sample count by default.
5. After a successful real plaintext GRU experiment with predictions enabled, open **Intrusion Detection**. Enter 48 raw feature values in the original CSV order, omitting the label. The service verifies the saved weights and scaler checksums, applies the scaler and returns the intrusion probability and binary label.

### Execution modes

| Mode | Purpose |
| --- | --- |
| Plaintext federated GRU | Train local client workers, aggregate updates and evaluate each round. This is the primary demo. |
| Reference simulation | Exercise partitioning, aggregation and metrics using a lightweight linear backend. Enable with `SECUREFED_ENABLE_SIMULATION`. |
| Centralized GRU | Select `mode: "centralized"` on a training request to train on pooled training rows as a baseline. |
| Paper comparison suite | Compare a centralized baseline with in-process federated runs at 4, 8 and 12 clients. Defaults are 15 rounds, five local epochs and batch size 512. The suite defaults to plaintext. |
| Optional encryption and legacy research | Separate CKKS implementations and adapters are present for research use. The plaintext demo requires neither TenSEAL nor an external research checkout. |

## Repository map

| Location | Contents |
| --- | --- |
| [datasets](datasets/) | Three bundled synthetic CSVs, their generator and schema guide. Large local CICIDS2017 CSVs under `web/backend/` are ignored by Git. |
| [Backend entry point](web/backend/app/main.py) | FastAPI startup, service registration, job handlers, CORS and route registration. |
| [Backend API](web/backend/app/api/) | Health, clients, datasets, experiments, jobs, metrics, predictions and IPS endpoints. |
| [Domain code](web/backend/app/domain/) | CSV loading, preprocessing, GRU weight serialization and evaluation metrics. [Federated training](web/backend/app/domain/federated/) contains the round loop, process worker and aggregation server. [Crypto](web/backend/app/domain/crypto/) contains optional backends. |
| [Services](web/backend/app/services/) | Dataset validation, client records, experiment orchestration, job management, training, inference, SDN integration and the [client tutorial](web/backend/app/services/client_tutorial.py). |
| [Configuration](web/backend/app/config.py), [database models](web/backend/app/models.py), [schemas](web/backend/app/schemas.py), [storage](web/backend/app/storage/) | Runtime settings, persisted records, request/response contracts and artifact locations. |
| [Research scripts](web/backend/research/) | Dataset-specific historical experiments, figure generation and SHAP analysis. These are separate from the web app entry point. |
| [Frontend](web/frontend/) | React, TypeScript, Vite and Tailwind. [Pages](web/frontend/src/pages/) implement the console screens. [Components](web/frontend/src/components/) include the tutorial and charts. [API client](web/frontend/src/lib/api.ts) connects them to FastAPI. |
| [Backend tests](web/backend/tests/) and [frontend sources](web/frontend/src/) | Pytest API/domain/integration tests and colocated Vitest tests. |
| Root scripts | The two launchers start the app. The `check_*`, `demo_*`, `run_*` and `frontend_*` helpers support diagnostics and development. Some older helpers use machine-specific paths. Use the portable commands below for verification. |

## Dashboard and API

All API paths below are relative to `http://127.0.0.1:8000/api/v1`. The [OpenAPI schema](http://127.0.0.1:8000/openapi.json) lists request fields, response types and all supported operations.

| Dashboard area | API entry points |
| --- | --- |
| Overview and tutorial | `GET /health`, `GET /version`, `POST /jobs/client-tutorial`, `GET /jobs/client-tutorial/latest` |
| Datasets | `POST /datasets/validate`, `POST /datasets` (multipart upload), `GET /datasets`, `POST /datasets/{id}/validate` |
| Federated Clients | `GET` or `POST /clients`, `PATCH /clients/{id}`, `POST /clients/{id}/enable` or `/disable`, `GET /clients/{id}/status` |
| Training, history and performance | `POST /experiments`, `POST /experiments/{id}/train` or `/simulate`, `GET /experiments/{id}`, `GET /experiments/{id}/metrics`, `POST /experiments/run-paper-suite` |
| Job progress and cancellation | `GET /jobs/{id}`, `POST /jobs/{id}/cancel` |
| Intrusion Detection | `GET /predictions/status`, `POST /predictions` with a JSON `features` array |
| SDN Network and IPS | `GET /sdn/status`, `POST /ips/detect`, `POST /ips/mitigate`. The default adapter is a local mock. Live controller operation requires separate verification. |
| Encryption, security and settings | `GET /encryption/status` reports backend availability. Settings controls the browser's API base URL and optional bearer token. |

## Configuration and persisted data

Set environment variables in the backend shell before startup. A direct Uvicorn launch uses the defaults in [config.py](web/backend/app/config.py). The [Windows launcher](start_backend.ps1) explicitly sets training, prediction and CKKS flags for the plaintext demo.

| Setting | Default or effect |
| --- | --- |
| `SECUREFED_BASE_DIR`, `SECUREFED_DATA_DIR` | Default to `web/` and `web/var/`. The data directory must be under the configured base. |
| `SECUREFED_DATABASE_URL` | Defaults to SQLite at `web/var/securefed.db`. It stores client records, dataset metadata, experiments and job results. |
| `SECUREFED_MAX_UPLOAD_BYTES`, `SECUREFED_MAX_CSV_ROWS` | 512 MiB and 2,000,000 rows by default. The separate training cap controls how many rows are used in an experiment. |
| `SECUREFED_TRAINING_MAX_ROWS`, `SECUREFED_SIMULATION_MAX_ROWS` | 5,000 and 50,000 rows respectively. |
| `SECUREFED_JOB_WORKERS` | One background worker by default. |
| `SECUREFED_API_TOKEN` | Optional bearer token for protected API routes. |
| `SECUREFED_ENABLE_RESEARCH_EXECUTION`, `SECUREFED_RESEARCH_REPO_DIR` | Gate and locate the external legacy research checkout. |

Uploaded CSVs are stored in `web/var/datasets/`. Experiment training writes JSON weights, preprocessing and result artifacts beneath `web/var/models/<experiment-id>/<run-id>/`. The active prediction manifest is `web/var/models/manifest.json`. Tutorial results are stored with their job. Copying only the SQLite database omits uploaded data and model artifacts.

## Verify an installation

From the repository root, with the Python environment active:

```powershell
Push-Location web/backend
python -m pytest tests -q
Pop-Location
npm.cmd --prefix web/frontend test
npm.cmd --prefix web/frontend run build
```

To exercise the real TensorFlow upload-to-prediction test explicitly:

```powershell
Push-Location web/backend
$env:SECUREFED_RUN_TF_TESTS = '1'
python -m pytest tests/test_training_api.py::test_real_keras_gru_training_completes -q
Pop-Location
```

| Symptom | What to check |
| --- | --- |
| Dashboard cannot reach the API | Open the health endpoint. Check the backend terminal and the base URL in Settings. |
| Training disabled or TensorFlow unavailable | Activate the environment used to install the training requirements, then start the backend with the supplied launcher. |
| Dataset uploads but cannot train | Check that it has 48 numeric features, a final binary label column and a valid schema report. |
| Predictions unavailable after the tutorial | Train a regular plaintext GRU experiment with predictions enabled. The tutorial keeps its model separate. |
| Tutorial route returns 404 | Restart the backend from the same project copy as the frontend so both serve the tutorial version. |
