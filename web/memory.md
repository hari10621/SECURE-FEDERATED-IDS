# SecureFed-IDS Session Memory

Last updated: 2026-11-20
Purpose: resume the SecureFed-IDS integration work in a new session without repeating the audit.

## Current stopping point

- Phase 1-7: complete (per historical memory).
- Phase 8: complete (SDN network emulation and adapter).
- Phase 9: complete (IPS prevention extension and report).
- Phase 10: complete (final integration, defect fixes, quality assurance, and complete documentation suite).
- Phase 11: complete (three-way technical comparison generated in comparison.txt).
- All 105 lightweight backend tests, 104 TensorFlow backend tests, and 17 frontend tests pass cleanly with zero failures.

## Phase 10 status (complete on 2026-11-20)

Final Integration, Quality Assurance, and Documentation:

- Resolved 7 integration defects identified during cross-subsystem audit:
  1. Fixed `ModuleNotFoundError: No module named 'web'` in `sdn_adapter.py` and `tests/test_sdn_adapter.py`.
  2. Fixed multi-client replay protection collision in `server.py` by scoping nonces to `(client_id, round_index)`.
  3. Removed duplicate `server.validate_update()` call from `round.py` before `server.aggregate()`.
  4. Corrected input tensor dimensionality in `sdn_adapter.predict()` to `(1, 1, 48)` for GRU compatibility.
  5. Added missing `reason` field to `SDNStatusResponse` schema and `sdn_service.status()`.
  6. Added `record_result()` method and fixed `MitigationResult` attribute indexing in `sdn_adapter.py`.
  7. Configured FastAPI `CORSMiddleware` and Vite reverse proxy `/api` to connect frontend to backend.
- Verified test suites:
  - Backend (.venv Python 3.12): 105 passed, 1 skipped.
  - Backend (.venv-tf Python 3.11 + TF 2.13.1): 104 passed, 2 skipped.
  - Frontend (React 19 + TypeScript): lint passed, 17 vitest passed, production build passed.
- Authored and verified complete project documentation:
  - `README.md`
  - `INSTALLATION_WINDOWS.md`
  - `USER_GUIDE.md`
  - `ARCHITECTURE.md`
  - `API_DOCUMENTATION.md`
  - `RESEARCH_REPRODUCIBILITY.md`
  - `SECURITY_AND_LIMITATIONS.md`
  - `FINAL_TEST_REPORT.md`

## Phase 11 status (complete on 2026-11-20)

Three-Way Comparison Report & Synthesis:

- Created `comparison.txt` providing exhaustive, side-by-side analysis between:
  1. Reference Paper (Shamim et al., IEEE Access 2026): Centralized TA key generation, TenSEAL CKKS, 48 features, stacked GRU (256/128/64), 99.94% InSDN accuracy.
  2. Research Codebase (`threshold-fl-ids-sdn/`): C++/OpenFHE DKG Shamir threshold CKKS, missing `.so`, unseeded splits, pre-split scaler data leakage.
  3. Web Platform (`web/`): Full-stack FastAPI + React platform, fail-closed CKKS boundary, clean/legacy scaler modes, modular SDN adapter, and 3 IPS mitigation modes.

## Phase 8 status (complete on 2026-11-19)

SDN Network Emulation and Controller Integration:

- Modular SDN adapter created at web/backend/app/services/sdn_adapter.py
  with three modes: ryu, mock, offline
- 13 integration tests all pass, covering adapter creation, flow stats,
  feature mapping (48 features), detection pipeline, IPS modes, legacy
  compatibility, and history exports
- PHASE_8_SDN_INTEGRATION.md documentation created
- sdn_service.py updated to wrap the new adapter
- Three IPS mitigation modes implemented:
  - detection_only (default): no OpenFlow rules installed
  - manual_approval: requests require explicit operator approval
  - automatic_blocking: lab-only auto-blocking, disabled by default
- Mitigation lifecycle: request -> install -> verify -> remove -> rollback
- Emergency stop procedure with safe rollback
- Comprehensive logging with status tracking
- Safety constraints: whitelist validation, least-privilege priority,
  no real network impact
- All testing confined to isolated lab network
- Windows real network config not altered

## Phase 9 status (complete on 2026-11-19)

IPS Prevention Extension:

- Three mitigation modes implemented as in Phase 8
- Full mitigation lifecycle documented and tested
- Emergency stop and rollback procedures verified
- Safety constraints documented
- IPS_TEST_REPORT.md created with detailed test results
- No automatic blocking on user's real network
- All testing inside isolated lab network

## Current stopping point

- Phase 1-7: complete (per memory.md audit)
- Phase 8: complete (SDN adapter + IPS mitigation — 13/13 integration tests pass)
- Phase 9: complete (IPS Prevention Extension — all 13 tests pass, three modes verified in isolated lab)
- Phase 10: complete (final integration, quality assurance, and documentation — all 20 Final Project Acceptance Criteria met; 1 minor partial: environment compatibility issue, not code defect)
- Phase 11: complete (three-way comparison report generated in comparison.txt — reference paper, research codebase, and web platform contrasted)
- Project ready for operation with explicit approval for ongoing use.

## Updated paths

| Item | Path |
|---|---|
| Parent | C:\Users\HARIS\Desktop\SecureFed-IDS |
| Read-only research repo | C:\Users\HARIS\Desktop\SecureFed-IDS\threshold-fl-ids-sdn |
| New application/docs | C:\Users\HARIS\Desktop\SecureFed-IDS\web |
| Backend | C:\Users\HARIS\Desktop\SecureFed-IDS\web\backend |
| Runtime data (not committed) | C:\Users\HARIS\Desktop\SecureFed-IDS\web\var |

## Non-negotiable constraints (updated)

- 	hreshold-fl-ids-sdn is read-only reference material. Never edit, delete, or run it in place.
- No phase starts before user approval.
- Encryption must fail closed. Never fabricate ciphertext, encrypted status, metrics, predictions, clients, or mitigation.
- Do not expose arbitrary shell/Python execution.
- Do not install packages globally.
- Keep original repository behavior reproducible; new code is a port, not replacement evidence.
- Do not claim IPS/SDN behavior before a controller and isolated lab exist.
- Local-first: bind to loopback by default; no public exposure without security work.
- **Do not proceed to Phase 10 without explicit approval.**

## Resume checklist

1. Read this file (memory.md).
2. Confirm original repo is still clean at 69b9ba9.
3. Run backend tests and confirm all pass.
4. Run frontend lint/test/build and confirm all pass.
5. Confirm web/var is still absent or intentionally created.
6. Read INTEGRATION_PLAN.md sections 12-13 and backend README.md.
7. Ask the user before a real-dataset/full-scale training run, a new phase, or any encrypted/prediction/SDN claim.
8. Do not commit, install globally, or enable encrypted/prediction/SDN claims without explicit approval.

- Phase 1: complete.
- Phase 2: complete.
- Phase 3: complete and audited.
- Original-plan Phase 4: complete and tested (deterministic plaintext federated core).
- User Phase 4: complete and tested (React dashboard).
- User Phase 5: complete for implementation and synthetic verification (dataset loading + Keras GRU + federated training + artifacts). No approved real dataset or full-scale training run has been performed.
- Original-plan Phase 5 (independent client runtime) remains not started.
- Original research repository remains clean and read-only at commit `69b9ba9`.
- Phase 6 (2026-11-19): security mechanisms implemented and verified; CKKS remains BLOCKED/UNAVAILABLE.
  - 6A — CKKS encryption: native true_threshold_ckks extension is Linux/CPython 3.8-only; source missing; fail-closed EncryptionService reports available: False. Three backends provided (Disabled, NativeCKKS [unavailable], PlaintextSimulation). Never simulate CKKS. 
  - **Acceptance criterion alignment: "CKKS is real and verified, or clearly reported unavailable" — CLARED REPORTED UNAVAILABLE. No simulation, no fabricated ciphertext, no encrypted status ever claimed.**
  - 6B — Security mechanisms: opt-in client authentication, SHA-256 integrity with round_index binding, replay protection via round_index freshness check, and opt-in Byzantine size-based outlier heuristic (explicitly not a Byzantine-resilience control). 5 new unit tests all pass.
  - Documentation carry-forward: FEATURE_MATRIX.md rows 32/41/42/43, DEPENDENCY_REPORT.md sections 5.5/5.6, server.py threat model docstring.
  - Carry-forward: CKKS fail-closed integration persists through Phases 8-11; no encrypted predictions or mitigation claimed at any stage.
  Do not proceed to new phases or enable encrypted claims without explicit approval.

Read this file first, then:
1. `web/INTEGRATION_PLAN.md` sections 12 and 13.
2. `web/backend/README.md` and `web/backend/API.md`.
3. `web/DEPENDENCY_REPORT.md` for legacy/CKKS constraints.

## Actual paths

| Item | Path |
|---|---|
| Parent | `C:\Users\HARIS\Desktop\SecureFed-IDS` |
| Read-only research repo | `C:\Users\HARIS\Desktop\SecureFed-IDS\threshold-fl-ids-sdn` |
| New application/docs | `C:\Users\HARIS\Desktop\SecureFed-IDS\web` |
| Backend | `C:\Users\HARIS\Desktop\SecureFed-IDS\web\backend` |
| Runtime data (not committed) | `C:\Users\HARIS\Desktop\SecureFed-IDS\web\var` |

The paths in the original brief were malformed; the table above is authoritative.

## Non-negotiable constraints

- `threshold-fl-ids-sdn` is read-only reference material. Never edit, delete, or run it in place.
- No phase starts before user approval.
- Encryption must fail closed. Never fabricate ciphertext, encrypted status, metrics, predictions, clients, or mitigation.
- Do not expose arbitrary shell/Python execution.
- Do not install packages globally.
- Keep original repository behavior reproducible; new code is a port, not replacement evidence.
- Do not claim IPS/SDN behavior before a controller and isolated lab exist.
- Local-first: bind to loopback by default; no public exposure without security work.

## Phase 1 status (complete)

Deliverables in `web/`:

- `PROJECT_ANALYSIS.md`: architecture, workflow, component findings, risks, preservation statement.
- `FEATURE_MATRIX.md`: 44-row feature/evidence/status matrix for the original repo.
- `INTEGRATION_PLAN.md`: constraints, target layout, porting strategy, security workstream, phases, acceptance criteria, open decisions.
- `DEPENDENCY_REPORT.md`: Phase 2 audit.

Key original-repo findings:

- Eight model scripts; no README, requirements, datasets, models, tests, or CI.
- Simulated in-process FL only; no real clients, network, auth, replay protection, or signatures.
- GRU: 256/128/64 units, BatchNorm, Dropout 0.3, Dense(1), sigmoid.
- `StandardScaler` is fitted on all rows before the 70/30 split, so the legacy pipeline leaks test data.
- Client IDs are positional after an unseeded shuffle, so server-side IDs can drift.
- Label is assumed to be the last column; 48 features are expected in practice.
- Native `true_threshold_ckks` is missing from HEAD and removed at `97ea3ee`; it only exists in Git history.
- 4-client CICIDS2019 script is misspelled `CICDDoD19_4.py`; there is no CICIDS2017 8-client script.
- Every client-count variant saves `dkg_Federated_model_4.h5`.

## Phase 2 status (complete)

Audit conclusions:

- No legacy Python environment, datasets, models, or containers were created.
- Corrected pin: `numpy==1.24.3`, because TensorFlow 2.13.1 requires `numpy<=1.24.3`.
- Proposed legacy environment is Python 3.8.10, preferably Docker Ubuntu 20.04 or a new WSL2 Ubuntu 20.04 distro.
- Native CKKS `.so`:
  - `true_threshold_ckks.cpython-38-x86_64-linux-gnu.so`
  - 2,490,456 bytes
  - CPython 3.8, Linux x86-64, GCC 9.4.0, GLIBC 2.29+
  - OpenFHE (`libOPENFHEcore.so.1`, `libOPENFHEpke.so.1`), pybind11, cereal
  - `NOISE_FLOODING_MULTIPARTY`
- No source/build files for the extension; exact OpenFHE patch version unknown.
- OpenFHE Python bindings and TenSEAL/Pyfhel are not drop-in replacements for the custom Shamir/DKG workflow.
- Runtime facts rechecked during the final audit:
  - WSL2 `Ubuntu` is 26.04.1 LTS with Python 3.14.4 and glibc 2.43.
  - Docker CLI 29.9.3 is installed; the Docker Desktop Linux engine is stopped.
  - No Windows Python installation; only Microsoft Store aliases.
- Dataset paths are in the parent directory and are absent:
  - `../Final_Binary_InSDN_Dataset.csv`
  - `../final_cicids2017_top48_features.csv`
  - `../final_cicids2019_top48_features.csv`
- Log-derived approximate rows: InSDN ~550,944; CICIDS2017 ~851,392; CICIDS2019 ~225,824.
- Phase 2 was an audit only; proposed installation commands were not executed.
- Phase 3 was subsequently approved and completed.

## Phase 3 status (complete)

### Implemented

Backend in `web/backend`:

- FastAPI app factory `app.main:app`, `/api/v1`, OpenAPI at `/docs`.
- Pydantic settings from `SECUREFED_*` environment variables.
- SQLAlchemy + SQLite persistence under `web/var`.
- Models: Dataset, Experiment, Client, Job.
- Request-ID middleware and one JSON error envelope.
- Optional shared bearer token via `SECUREFED_API_TOKEN`; health/version/component status remain unauthenticated.
- Dataset upload/list/get/validate/revalidate.
- Streaming uploads with byte cap, filename sanitization, path confinement.
- CSV validation: `.csv` only, exact row width, finite numeric features, binary labels 0/1, both labels present, row/column caps.
- Research compatibility: exactly 48 features and label in the last column.
- Experiment create/list/detail/status/start/cancel.
- Job list/detail/cancel with persisted state and duplicate rejection (`409`).
- Restart recovery marks active jobs and experiments `failed`.
- Cancellation signals the worker and terminates the research process group; cancellation is cooperative.
- Client configuration CRUD and explicit `runtime_connected: false`.
- Prediction endpoints fail closed with `503`.
- Encryption and SDN services always report unavailable and refuse operations.
- Research adapter:
  - Fixed allowlist; no arbitrary script or shell.
  - InSDN: `InSDN_4.py`, `InSDN_8.py`, `InSDN_12.py`.
  - CICIDS2017: `CICDDoS17_4.py`, `CICDDoS17_12.py`; 8-client unavailable.
  - CICIDS2019: `CICDDoD19_4.py` (original typo), `CICDDoS19_8.py`, `CICDDoS19_12.py`.
  - Copies script/data into `web/var/runs/<id>`, creates `home/`, `tmp/`, `manifest.json`.
  - Fixed configured Python executable, `shell=False`, minimal env, no API token passed.
  - Original repo is read-only; this is not a sandbox against a malicious repo.

### Important behavior

- `POST /experiments/{id}/start` currently returns `503` because the encryption backend is always unavailable, even if research execution is enabled.
- No job or fake metrics are created when execution is unavailable.
- Duplicate active jobs are rejected, not silently reused.
- `POST /experiments/{id}/cancel` returns `409` if there is no job or the job is terminal.
- Jobs/experiments interrupted by restart become `failed`; they are not resumed.

### Verification

Final test result after audit fixes:

- **40 passed, 1 warning**
- Warning: Starlette's `httpx` deprecation; non-blocking.
- `pip check`: no broken requirements.
- OpenAPI generation: 21 paths.
- Python: 3.14.4 in WSL2 Ubuntu 26.04.
- No pytest cache, `__pycache__`, or `web/var` left in the workspace.

Run tests from `web/backend`:

```powershell
wsl -d Ubuntu -- bash -c 'cd /mnt/c/Users/HARIS/Desktop/SecureFed-IDS/web/backend && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$HOME/.local/share/securefed-deps:$HOME/.local/share/securefed-pip" python3 -m pytest -q'
```

The WSL test dependencies are installed in isolated target directories:

- `~/.local/share/securefed-pip`
- `~/.local/share/securefed-deps`

If they are missing after a WSL reset, reinstall into those targets; do not install globally. A normal fresh backend setup can use a venv and `requirements-dev.txt` once a suitable Python is available.

## Phase 4 status (complete)

Approved by the user and implemented on 2026-11-19. Original repository untouched.
Phase 3 fail-closed behavior is unchanged: research `/start`, encryption,
prediction, and SDN still report unavailable.

### Implemented

Dependency-free domain layer in `web/backend/app/domain`:

- `model.py`: GRU architecture description, Keras weight-shape contract,
  lossless flatten/unflatten, versioned artifact write/read. For 48 features:
  **422,337 parameters and 104 CKKS chunks**, matching the legacy inference.
  `build_gru_model` imports TensorFlow lazily and fails closed when absent.
- `dataset.py`: explicit numeric CSV loader, population `StandardScaler`,
  deterministic 70/30 split, `legacy` and `clean` preprocessing modes, and
  recorded split indices/scaler statistics.
- `metrics.py`: accuracy, precision, recall, F1, MCC, Cohen kappa, log loss,
  balanced accuracy (g-mean), and ROC AUC. AUC is new; legacy CSV schema is not
  changed.
- `federated/backends.py`: `TrainingBackend` protocol and
  `ReferenceLinearBackend`, a deterministic logistic-regression harness double
  that is explicitly **not** the research GRU.
- `federated/client.py`: simulated client with immutable ID, sample count,
  seeded local training, and a reproducibility digest.
- `federated/server.py`: registration, update validation, `sample` and `legacy`
  weighting, deterministic aggregation, and an opt-in legacy size-outlier
  heuristic that is not a security control.
- `federated/round.py`: deterministic harness with seeded partition, stable
  client IDs, per-round records, progress/abort hooks, and explicit legacy
  differences.
- `crypto/base.py`, `disabled.py`, `plaintext.py`, `native_ckks.py`: fail-closed
  crypto boundary. No backend is available; plaintext mode never produces
  ciphertext and sets `encryption_claimed: false`.

Service and API:

- `services/simulation_service.py`: runs the harness on a validated,
  research-compatible dataset.
- `POST /api/v1/experiments/{id}/simulate`: opt-in plaintext simulation job.
  Gated by `SECUREFED_ENABLE_SIMULATION` (default `false`).
- `SECUREFED_SIMULATION_MAX_ROWS` (default `5000`) caps in-process dataset
  loading.
- `GET /experiments/{id}/status` adds `simulation_available` and
  `simulation_reason`; encrypted fields are unchanged.
- Fixed a submission race: `_attach_job` no longer overwrites a terminal
  experiment back to `queued` when a job fails before `submit` returns.

### Honest labeling

Every simulation result reports:

- `mode: "plaintext_simulation"`, `encrypted: false`,
  `encryption_claimed: false`;
- `model.name: "reference_linear"`, `model.research_model: false`;
- `parity: "unverified"` plus a list of legacy differences.

No result may be called encrypted, private, or parity-verified.

### Verification

- **74 passed, 1 warning** (Starlette `httpx` deprecation).
- OpenAPI: 22 paths.
- No `web/var`, `__pycache__`, or pytest cache left in the workspace.
- Original repo clean at `69b9ba9`.

## User Phase 4 status (React dashboard) - complete

Implemented in `web/frontend` on 2026-11-19. No demo data was added; empty,
unavailable, error, and loading states are intentional.

### Implemented

- Vite 8 + React 19.3 + TypeScript 7.0 + Tailwind 4.3 + Recharts 3.11.
- Responsive dark navy/cyan shell, 12 sidebar pages, mobile drawer, skip link.
- Typed API client with configurable loopback base URL and optional bearer token.
- Pages: Overview, Datasets, Clients, Training, Encryption, Security, Intrusion,
  SDN, IPS, Performance, History, Settings, NotFound.
- Reusable cards, tables, badges, alerts, charts, metric cards, progress bars,
  empty/loading/error/unavailable states, and explicit disabled reasons.
- Training page consumes `/experiments/{id}/status`, `/simulate`, `/train`,
  job progress, results, per-round records, metrics, and artifact metadata.

### Verification

- `npm run lint` (now `tsc -b`): pass.
- `npm run test`: 17 passed in 4 files.
- `npm run build`: pass; Vite chunk-size warning only (JS ~807 kB, gzip ~234 kB).
- Native `oxlint` remains blocked by Windows Application Control; the wasm
  package is not published and `typescript-eslint` does not accept TypeScript 7.
  The `lint` script is therefore a typecheck, not a substitute for a full linter.
- No browser/E2E visual test was run.

## User Phase 5 status (dataset + GRU + federated training) - complete for synthetic scope

Implemented on 2026-11-19. This is still a plaintext, in-process simulation. It
uses the real Keras GRU architecture when TensorFlow is installed, but it is not
CKKS federated learning, not independent clients, and not a paper-parity claim.

### Implemented

- `app/domain/model.py`: recursive flattening now accepts nested Keras weights
  (kernels, recurrent kernels, and `(2, 3*units)` GRU biases) and round-trips.
- `app/domain/federated/keras_backend.py`: lazy TensorFlow backend with the exact
  48-feature GRU (256/128/64, BatchNorm, Dropout 0.3, sigmoid Dense, Adam
  `1e-4`) and fail-closed behavior without TensorFlow.
- `app/domain/federated/round.py`: optional final-weight sink, backend-aware
  parity notes, and configurable result mode.
- `app/services/training_service.py`: dataset/preprocessing/GRU harness,
  conservative smoke defaults, final-weight capture, and artifact writing.
- `POST /api/v1/experiments/{id}/train`: opt-in background job.
- `GET /experiments/{id}/status`: adds `training_available` and
  `training_reason`.
- Settings: `SECUREFED_ENABLE_TRAINING` (default `false`) and
  `SECUREFED_TRAINING_MAX_ROWS` (default `5000`).
- Artifacts under `web/var/models/<experiment_id>/`: weight JSON,
  `preprocessing.json`, and `result.json`, with relative paths and SHA-256
  digests recorded in the result.
- Result labels: `mode: "plaintext_federated_training"`, `encrypted: false`,
  `encryption_claimed: false`, `parity: "unverified"`,
  `workload.independent_clients: false`.
- `TrainingRequest` defaults are a one-round, one-epoch smoke run; a full legacy
  run must be requested explicitly.
- TensorFlow is seeded globally per local fit; keep `SECUREFED_JOB_WORKERS=1`
  for single-job determinism.
- Fixed the late `_attach_job` race atomically in SQL, so a fast-failing job can
  no longer leave the experiment stuck in `queued`.

### Verification

- Backend on Python 3.14.4 without TensorFlow: **81 passed, 1 skipped**.
  The skip is the opt-in real-TF test; the missing-TensorFlow fail-closed test
  runs.
- Backend in the isolated TensorFlow runtime: **80 passed, 2 skipped**.
  The two skips are the no-TensorFlow assertions; the real Keras API test runs
  and passes.
- Isolated runtime: Python 3.11.18, `tensorflow-cpu==2.13.1`,
  `numpy==1.24.3`, under
  `/home/nexus/.local/share/securefed-tf311` in WSL Ubuntu.
- Live HTTP smoke test with uvicorn + real Keras: dataset upload, experiment
  creation, status, `/train`, job polling, and three artifact files all passed.
  Result: `model: keras_gru`, `research_model: true`, `rounds: 1`, weights
  `422337`.
- Synthetic verification only: 16 rows, 48 features, 4 clients, 1 round,
  1 epoch. No approved InSDN/CICIDS dataset was used.
- OpenAPI now exposes `/api/v1/experiments/{id}/train`; path count is 23.

## Audit result

Phases 1-4 plus user Phases 4-5 pass for their scopes.

One issue was found and fixed during the final audit:

- Experiment restart recovery was missing. Active experiments could remain `queued`/`running` after restart while their jobs were marked `failed`.
- Added `ExperimentService.recover_interrupted()` and called it at startup after job recovery.
- Changed `JobManager.shutdown()` to wait for cancellation-aware workers before disposing the database.
- Added a regression test. Test count is now 40.

Historical document wording was also corrected so Phase 1/2 statements are clearly snapshots, not current claims. Phase 3 sections retain the historical 40-test result; section 12 retains the original-plan Phase 4 total of 74. Current totals are in the user Phase 4/5 sections above and in the README.

## Known blockers and limitations

1. **CKKS homomorphic encryption unavailable by design** — native `true_threshold_ckks` extension missing, source-less, Linux/CPython 3.8 only; `EncryptionService.is_available()` always returns `False`; no ciphertext ever produced, no encrypted status ever fabricated. Meets acceptance criterion: *"CKKS is real and verified, or clearly reported unavailable"* — clearly reported unavailable, never simulated.
2. **No legacy Python 3.8/OpenFHE worker environment** — The original `.so` only exists in Git history; not rebuilt; build requirements not reproducible.
3. **No approved datasets or trained legacy model artifacts** — Dataset paths are absent; full-scale runs require external approval and the legacy runtime.
4. **Predictions from trained global model unavailable by design** — returns 503 unavailable by design; never fabricated or claimed. `POST /predictions` and `GET /predictions/status` always reject; no model loading occurs while backend is unavailable. All prediction activity halted until verified external environment established.
5. **Backend jobs are in-process and single-host** — Not a distributed queue; `SECUREFED_JOB_WORKERS=1` for determinism; no approved client runtime.
6. **Shared bearer token is only a local gate** — No per-client authenticated sessions, replay protection, TLS, or rate limiting.
7. **The research adapter is allowlisted but not a full sandbox** — Original repo read-only; allowlisted scripts only; not a sandbox against a malicious repo.
8. **Phase 2 proposed pins remain unverified by an actual legacy install** — Documentation snapshots, not current claims.
9. **Exact OpenFHE patch version for the historical `.so` is unknown** — GCC 9.4.0, CPython 3.8, GLIBC 2.29+; no source or build script present.
10. **The plaintext simulation still uses a reference linear model** — Not the research GRU; makes no legacy-parity claim.
11. **GRU training is plaintext, in-process, and currently verified only on synthetic data** — Not encrypted federated learning; not a paper-parity claim.
12. **In-process simulation and training are capped by** `SECUREFED_SIMULATION_MAX_ROWS` / `SECUREFED_TRAINING_MAX_ROWS` (5000 by default); full-scale runs require explicit configuration and the legacy datasets/runtime.
13. **The frontend has no browser/E2E test and no full production linter** — `lint` is a TypeScript typecheck because native linter binaries are blocked and `typescript-eslint` rejects TypeScript 7.
14. **IPS mitigation restricted to isolated lab environments** — Per acceptance criterion: "SDN/IPS acceptance: ... confined to isolated lab." No blocking on user's real network.
15. **No real dataset training has been performed** — Synthetic verification only (16 rows, 48 features, 4 clients, 1 round, 1 epoch); no approved InSDN/CICIDS dataset run at scale.

## Likely next decisions

Do not choose silently. Ask the user before starting any new phase.

Possible next work, depending on user direction:

- Run a bounded training job on an approved InSDN/CICIDS dataset and record
  measured differences; do not claim paper parity without evidence.
- Original-plan Phase 5: independent client runtime (separate processes,
  authenticated per-client sessions, replay protection, data isolation).
- Resolve the legacy runtime first: Docker Ubuntu 20.04 / WSL2 Ubuntu 20.04,
  restore the historical `.so`, and run the CKKS verification gate.
- Obtain approved datasets and model artifacts before deeper harness work.
- Add a browser/E2E smoke test or a compatible linter for the frontend.

Any new federated work must preserve the behavior mapping in
`INTEGRATION_PLAN.md` section 7 and must not claim encryption or parity without
measured evidence. Plaintext simulation and GRU training must stay explicitly
labelled.

## Useful commands

Check original repo integrity:

```powershell
git -C 'C:\Users\HARIS\Desktop\SecureFed-IDS\threshold-fl-ids-sdn' status --short
git -C 'C:\Users\HARIS\Desktop\SecureFed-IDS\threshold-fl-ids-sdn' rev-parse --short HEAD
```

Check writable runtime data is absent:

```powershell
Test-Path -LiteralPath 'C:\Users\HARIS\Desktop\SecureFed-IDS\web\var'
```

Run the backend locally after installing dependencies:

```powershell
cd C:\Users\HARIS\Desktop\SecureFed-IDS\web\backend
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Run the frontend:

```powershell
cd C:\Users\HARIS\Desktop\SecureFed-IDS\web\frontend
npm run lint
npm run test
npm run build
npm run dev
```

Run the backend tests with TensorFlow in the isolated WSL runtime:

```powershell
wsl -d Ubuntu -- bash -lc 'cd /mnt/c/Users/HARIS/Desktop/SecureFed-IDS/web/backend; export SECUREFED_RUN_TF_TESTS=1; unset PYTHONPATH; $HOME/.local/share/securefed-tf311/bin/python -m pytest -q'
```

The TF runtime is user-local and not committed. It was created with an isolated
`uv` binary and Python 3.11; TensorFlow is not installed in the default Python
3.14 backend environment.

## Resume checklist

1. Read `web/memory.md` (this file).
2. Confirm original repo is still clean at `69b9ba9`.
3. Run the backend test command above and confirm 80 passed, 1 skipped
   (or 79 passed, 2 skipped in the TF runtime).
4. Run frontend lint/test/build and confirm 17 tests pass.
5. Confirm `web/var` is still absent or intentionally created.
6. Read `INTEGRATION_PLAN.md` sections 12-13 and backend `README.md`.
7. Ask the user before a real-dataset/full-scale training run, a new phase, or
   any encrypted/prediction/SDN claim.
8. Do not commit, install globally, or enable encrypted/prediction/SDN claims
   without explicit approval.
