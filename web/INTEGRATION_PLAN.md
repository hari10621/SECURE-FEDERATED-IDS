# SecureFed-IDS — Phase 1 Integration Plan

This plan describes how the research repository would be integrated into the new
application. This is the Phase 1 baseline; implementation status is recorded in
sections 11-13. The original repository remains untouched.

## 1. Non-negotiable constraints

1. `threshold-fl-ids-sdn` is read-only reference material. No edits, no deletions, no
   in-place runs that write result directories.
2. The new application lives in `C:\Users\HARIS\Desktop\SecureFed-IDS\web`.
3. The original experiment must remain reproducible from the original scripts on its
   original platform. New code is a port, not a replacement of the evidence.
4. Encryption must fail closed. If the native CKKS backend is not present and verified,
   the application must report `encryption: unavailable` and must not claim that model
   updates were encrypted.
5. No feature is accepted on the basis of an import, a comment, or a filename.

## 2. Recommended target decisions (need supervisor approval)

| Decision | Recommendation | Reason |
|---|---|---|
| CKKS host | Linux container or WSL2 Ubuntu 20.04 with Python 3.8 | Only environment compatible with the existing `.so` |
| Windows support | Backend runs in the Linux runtime; browser UI on Windows | Avoids pretending a Linux ABI extension runs natively |
| Client realism | Separate processes first, separate containers later | Achievable incrementally; creates a real trust boundary |
| Data | Start with approved InSDN CSV; add CICIDS only with license review | Keeps scope controlled |
| Legacy metrics | Report as "legacy reproduction" and separately report leakage-free results | Preserves parity without misrepresenting quality |
| Encryption fallback | Explicit `unavailable` mode, never a fake ciphertext | Honest behavior when OpenFHE is missing |

If the supervisor rejects a Linux runtime, the alternative is to rebuild the extension
against a Windows OpenFHE build. That is a separate, higher-risk workstream and must not
be assumed to succeed.

## 3. Proposed application layout

```text
web/
  backend/
    app/
      main.py                  # local-first HTTP API
      config.py                # paths, limits, feature flags
      api/
        datasets.py
        runs.py
        models.py
        health.py
      domain/
        dataset.py             # validated dataset metadata
        model.py               # GRU factory, weight (de)serialization
        metrics.py             # shared evaluation
        federated/
          client.py            # local training + update generation
          server.py            # registration, validation, aggregation
          round.py             # deterministic round orchestration
        crypto/
          base.py              # CryptoBackend protocol
          native_ckks.py       # calls true_threshold_ckks, fail closed
          disabled.py          # explicit unavailable backend
        security/
          auth.py              # client session tokens
          replay.py            # round nonce/timestamp checks
          integrity.py         # signatures/MACs (not plain SHA-256 alone)
      storage/
        runs.py                # run manifests, artifacts, atomic writes
      explain/
        shap_service.py        # bounded, optional
    tests/
      unit/
      integration/
      fixtures/
  frontend/
    ...
  docs/
    PROJECT_ANALYSIS.md
    FEATURE_MATRIX.md
    INTEGRATION_PLAN.md
    DEPENDENCY_REPORT.md
  pyproject.toml               # created in a later approved phase
```

No file in this layout is created during Phase 1 except these four documents.

## 4. Porting strategy

### 4.1 Freeze and inventory

- Tag or record the original commit (`69b9ba9`) and the historical notebook commit
  (`53d70d3`) in the run manifest.
- Copy behavior, not files: reimplement the logic in modules with tests against recorded
  reference values.
- Never import the research scripts as a package; they execute at import time and write
  relative output directories.

### 4.2 Dataset adapter

- One loader with an explicit schema: feature columns, label column, expected dtype,
  allowed label values, feature count, checksum.
- Store uploaded data only under the application's data directory after validation.
- Record the exact split indices so evaluation is reproducible without refitting.
- Provide two preprocessing modes:
  - `legacy`: scaler fitted on all rows, 70/30 seed 42, to reproduce the paper.
  - `clean`: scaler fitted on the training partition only.
- Default for new experiments should be `clean`; `legacy` must be visibly labelled.

### 4.3 Model adapter

- `build_gru_model(input_shape, lr)` copied exactly, with a fixed parameter-count check.
- Weight flattening order must match Keras layer order and must round-trip exactly.
- Save architecture + weights in a versioned format; retain `.h5` export for
  compatibility with `Figure Generation.py` and `shapupdates.py`.
- Unique artifact names per dataset and client count. Do not reuse
  `dkg_Federated_model_4.h5` for 8/12 clients.

### 4.4 Federated core

- `FLServer` logic is split into:
  - registration/session handling,
  - update validation,
  - aggregation,
  - round state.
- Replace positional `client_idx` with immutable client IDs assigned at registration.
- Preserve the original weighted-sum semantics as `legacy_weighting` for parity, and add
  `sample_weighting` based on exact sample counts.
- Keep the original size-based Byzantine check behind a flag for comparison, but do not
  present it as a security control.
- Record every round: participants, hashes, ciphertext sizes, timings, aggregate hash,
  decryption parties, metrics.

### 4.5 Crypto adapter

Define a small interface:

```text
CryptoBackend:
  is_available() -> bool
  status() -> {mode, backend, details}
  initialize(parties, threshold, params) -> handle
  encrypt_vector(array) -> chunks
  add(ciphertext, ciphertext) -> ciphertext
  scale(ciphertext, scalar) -> ciphertext
  threshold_decrypt(chunks, party_ids) -> array
```

- `NativeCKKSBackend` imports `true_threshold_ckks` only inside a guarded initializer.
  Import failure, ABI mismatch, missing `libOPENFHE*`, or bad parameters must produce a
  clear `unavailable` status.
- `DisabledBackend` refuses to produce ciphertext. It must not return random bytes,
  base64 placeholders, or plaintext labelled as encrypted.
- A known-answer test must prove:
  - `decrypt(encrypt(x)) ≈ x` within a documented tolerance,
  - `decrypt(Σ w_i · enc(x_i)) ≈ Σ w_i · x_i`,
  - wrong or insufficient parties fail,
  - threshold parties succeed.
- Until those tests pass in the target environment, all UI/API responses must say
  encryption is unavailable and the corresponding experiment must be disabled.

### 4.6 Explainability

- Make SHAP optional and resource-bounded (sample caps, timeouts, process isolation).
- Replace `display()` with explicit table serialization.
- Never write to a drive root; use the run's artifact directory.
- Separate "global feature importance" from "per-client explanation" so privacy claims
  are not implied.

## 5. Security workstream (must precede any non-local exposure)

1. Authenticated client sessions with per-client credentials; tokens must be required on
   every update, not just registration.
2. Update signatures or MACs with keys independent of the payload; plain SHA-256 is
   integrity only.
3. Round binding: nonce, round ID, deadline, and replay cache.
4. Server-side validation of shapes, chunk counts, sizes, and parameter ranges before
   homomorphic operations.
5. File upload validation: extension, MIME, size, row/column limits, numeric parsing,
   path confinement, no symlinks, no arbitrary command execution.
6. Resource limits and rate limiting; no public bind by default.
7. Secrets only through environment/secret storage; never in source, logs, or CSV.
8. Audit log for registration, update acceptance/rejection, aggregation, decryption, model
   promotion, and any future mitigation request.

## 6. Phased delivery (only after approval of Phase 1)

| Phase | Scope | Exit criteria |
|---|---|---|
| 2 | Reproducible environment and skeleton | Pinned env; health endpoint; original data loader/model tests; no encryption claimed |
| 3 | Local backend foundation, safe research adapter, and verified crypto or explicit disabled mode | API tests pass; uploads/jobs/path safety verified; encryption surfaced as unavailable |
| 4 | Federated core with simulated clients | Deterministic round harness; legacy metrics reproduced or differences explained |
| 5 | Independent client runtime | Separate processes, authenticated sessions, replay protection, per-client data isolation |
| 6 | Local UI and run management | Upload validation, run history, metrics, artifact download; local-only bind |
| 7 | Explainability service | Bounded SHAP job, artifact output, no drive-root writes |
| 8 | Hardening and evaluation | Security tests, failure injection, leakage-free benchmark, documentation |
| 9 | IPS extension | SDN controller integration in an isolated lab; explicit prevention audit trail |

Each phase must run its tests and report pass/fail. No phase starts before approval.

## 7. Behavior-preservation mapping

| Original behavior | New location | Preservation rule |
|---|---|---|
| `build_gru_model` | `domain/model.py` | Identical layer order, units, activations, optimizer, loss |
| `load_csv_data` | `domain/dataset.py` | Same last-column convention in `legacy` mode |
| All-row scaler + 70/30 split | `domain/dataset.py` `legacy` mode | Identical seed and order |
| `create_clients` shuffle/floor split | `federated/round.py` `legacy` mode | Same RNG behavior, but stable IDs added |
| Encrypt 4096-slot chunks | `crypto/native_ckks.py` | Same parameters 8192/4096/2/40 |
| Weighted homomorphic sum | `federated/server.py` | Same arithmetic; exact-sample weighting as separate mode |
| Threshold decryption | `crypto/native_ckks.py` | Same party selection semantics; seed recorded |
| Metrics | `domain/metrics.py` | Same formulas; add AUC without changing old CSV schema |
| SHAP | `explain/shap_service.py` | Same explainer type and sample sizes in `legacy` mode |

If exact parity is impossible (for example, different TensorFlow version), the difference
must be measured and documented rather than hidden.

## 8. Acceptance criteria for integration

- Original repository still clean and unmodified.
- A fresh environment can be created from pinned instructions.
- Dataset validation rejects malformed or out-of-schema files.
- The model factory produces the expected parameter count and round-trips weights.
- Crypto tests either pass, or the application reports `unavailable` and disables the
  encrypted path.
- A simulated run reproduces the legacy workflow with documented, measured differences.
- Authentication, replay protection, and update integrity are test-covered.
- No fake encryption, fake clients, fake metrics, or fake prevention actions appear in
  code, logs, UI, or documentation.

## 9. Explicit non-goals for the IDS integration

- Do not expose arbitrary shell/Python execution through the API.
- Do not install packages globally.
- Do not download unknown binaries or disable Windows security.
- Do not claim IPS behavior before a controller and isolated lab exist.
- Do not present simulated clients as real federated participants.

## 10. Open decisions blocking Phase 2

1. Linux runtime choice: WSL2, Docker, or dedicated Linux host.
2. Whether the existing `.so` may be restored from Git history for local use, and under
   what approval.
3. Approved dataset and license.
4. Whether legacy leakage is retained in reported comparisons.
5. Definition of "independent client" for acceptance.
6. Availability of an SDN controller/lab for the later IPS phase.

## 11. Phase 3 implementation status (backend foundation and research adapter)

Status: completed and tested on 2026-11-18. The original repository was not
modified. No dependencies were installed into a global environment.

The Phase 3 prompt expanded the earlier plan to include the local API foundation
and safe research adapter. This section records what exists; it does not change
the Phase 4 gate.

### 11.1 Backend

- Location: `web/backend`.
- Runtime: Python 3.10+; tested with Python 3.14.4 in WSL2 Ubuntu 26.04.
- Framework: FastAPI, Pydantic, SQLAlchemy, SQLite, `python-multipart`.
- Entry point: `app.main:app`; loopback-only example:
  `uvicorn app.main:app --host 127.0.0.1 --port 8000`.
- Writable state: `web/var` (SQLite, uploaded datasets, run workspaces, models,
  reserved CKKS directory). `web/.gitignore` excludes it.
- API prefix: `/api/v1`; OpenAPI at `/docs`.
- Error contract: one JSON envelope for validation, not-found, conflict,
  unauthorized, payload-too-large, unavailable, and internal errors.
- Request IDs: `X-Request-ID` is sanitized/echoed and logged.
- Optional auth: shared `SECUREFED_API_TOKEN` bearer gate. Liveness and component
  status routes remain unauthenticated.

Implemented routes:

| Area | Routes |
|---|---|
| System | `GET /health`, `/version`, `/encryption/status`, `/sdn/status` |
| Datasets | `POST /datasets`, `GET /datasets`, `GET /datasets/{id}`, `POST /datasets/validate`, `POST /datasets/{id}/validate` |
| Experiments | `POST /experiments`, `GET /experiments`, `GET /experiments/{id}`, `GET /experiments/{id}/status`, `POST /experiments/{id}/start`, `POST /experiments/{id}/cancel` |
| Jobs | `GET /jobs`, `GET /jobs/{id}`, `POST /jobs/{id}/cancel` |
| Clients | `POST /clients`, `GET /clients`, `GET /clients/{id}`, `PATCH /clients/{id}`, `GET /clients/{id}/status` |
| Predictions | `GET /predictions/status`, `POST /predictions` |

### 11.2 Dataset validation and path safety

- Streaming upload with a byte cap; sanitized filenames; no user-controlled
  storage paths.
- Writes are confined beneath `web/var`; revalidation uses the stored relative
  path only.
- CSV checks: `.csv` extension, non-empty data, exact row width, finite numeric
  features, binary labels (`0`/`1`), both labels present, row/column caps.
- Research compatibility requires 48 features and the label in the last column.
- Non-compatible files may be retained with `research_compatible: false`, but
  experiments reject them.

### 11.3 Experiment, job, and cancellation behavior

- Experiments persist `created`, `queued`, `running`, `cancellation_requested`,
  `succeeded`, `failed`, or `cancelled`.
- Jobs persist the same lifecycle plus progress, message, result, and error.
- Duplicate active jobs are rejected with `409`, not silently started twice.
- Restart recovery marks previously active jobs and experiments `failed`; it
  does not resume them.
- Cancellation is cooperative: a cancel request is persisted, the worker is
  signaled, and the legacy research process group is terminated. Cancellation
  cannot roll back files already written inside the isolated run directory.
- In Phase 3, `start` remains `503 unavailable` because the encryption backend
  is always unavailable. No job is created and no fake metrics are returned.

### 11.4 Research adapter

- Fixed allowlist only; no arbitrary script, path, or shell execution.
- InSDN: `InSDN_4.py`, `InSDN_8.py`, `InSDN_12.py`.
- CICIDS2017: `CICDDoS17_4.py`, `CICDDoS17_12.py`; 8-client variant is absent.
- CICIDS2019: `CICDDoD19_4.py` (original typo), `CICDDoS19_8.py`,
  `CICDDoS19_12.py`.
- Per-run workspace under `web/var/runs`: copied script, copied dataset under
  the original expected filename, `home/`, `tmp/`, and `manifest.json`.
- Fixed configured Python executable; `shell=False`; minimal environment without
  `SECUREFED_API_TOKEN`; `PYTHONPATH` limited to the run directory and CKKS
  directory.
- Original repository is read-only. The adapter is not a sandbox against a
  malicious repository; repo integrity is an explicit trust assumption.

### 11.5 Explicit fail-closed components

- `EncryptionService` always reports unavailable; there is no fake ciphertext.
- `SDNService` always reports unavailable; no controller is contacted.
- `ModelService` reports unavailable and refuses to load arbitrary Keras/pickle
  artifacts; prediction returns `503`.
- Client records are configuration only; `runtime_connected` is always false.

### 11.6 Tests and remaining gaps

Test command (from `web/backend`):

```bash
pytest
```

Result: 40 passed, 1 warning (Starlette's `httpx` deprecation) on Python 3.14.4.
The warning is non-blocking.

Remaining gaps before Phase 4:

1. No verified CKKS runtime. The original `.so` requires CPython 3.8/Linux and
   OpenFHE; no source is available.
2. No legacy Python 3.8/OpenFHE worker environment has been created.
3. No datasets or trained models are present; predictions stay disabled.
4. Legacy scripts still have hardcoded dataset/model paths and SHAP/Jupyter
   quirks; these must be handled in an isolated worker, not by importing them.
5. The backend is single-host with in-process jobs; it is not a distributed
   queue or authenticated multi-client system.
6. No React frontend, TLS, rate limiting, or per-client credentials yet.

These gaps are intentional. Do not enable or claim encryption, federated
execution, prediction, or SDN mitigation until their tests and runtime evidence
exist.

## 12. Phase 4 implementation status (deterministic federated core)

Status: completed and tested on 2026-11-19. The original repository was not
modified and remains clean at `69b9ba9`. Phase 3 fail-closed behavior is
unchanged: encryption, real research execution, predictions, and SDN mitigation
still report unavailable.

### 12.1 What exists

New dependency-free domain layer in `web/backend/app/domain`:

| Module | Purpose |
|---|---|
| `model.py` | GRU architecture description, Keras weight-shape contract, lossless flatten/unflatten, versioned artifact write/read. For 48 features this yields 422,337 parameters and 104 CKKS chunks, matching the legacy inference in `DEPENDENCY_REPORT.md` §6.1. |
| `dataset.py` | Explicit numeric CSV loader, population `StandardScaler`, deterministic 70/30 split, `legacy` and `clean` preprocessing modes, recorded split indices and scaler statistics. |
| `metrics.py` | Binary accuracy, precision, recall, F1, MCC, Cohen kappa, log loss, balanced accuracy (g-mean), and ROC AUC. AUC is new and does not alter the legacy CSV schema. |
| `federated/backends.py` | `TrainingBackend` protocol plus `ReferenceLinearBackend`, a deterministic logistic-regression harness double. It is not the research GRU. |
| `federated/client.py` | Simulated client with immutable ID, sample count, local training, and a reproducibility digest. |
| `federated/server.py` | Registration, update validation, `sample` and `legacy` weighting, deterministic aggregation, and an opt-in legacy size-outlier heuristic. |
| `federated/round.py` | Deterministic round harness with seeded partitioning, stable client IDs, per-round records, progress/abort hooks, and explicit difference reporting. |
| `crypto/base.py` | `CryptoBackend` protocol and the original CKKS parameter block. |
| `crypto/disabled.py` | Fail-closed backend; every operation raises. |
| `crypto/plaintext.py` | Explicit plaintext simulation status; refuses to produce ciphertext. |
| `crypto/native_ckks.py` | Placeholder that never probes or claims the historical extension. |

Service and API integration:

- `services/simulation_service.py` runs the deterministic harness on an
  uploaded, validated, research-compatible dataset.
- `POST /api/v1/experiments/{id}/simulate` creates a normal background job.
  It is gated by `SECUREFED_ENABLE_SIMULATION` (default `false`).
- `GET /experiments/{id}/status` now also reports `simulation_available` and
  `simulation_reason`; the encrypted research fields are unchanged.
- Row loading for the simulation is capped by
  `SECUREFED_SIMULATION_MAX_ROWS` (default 5,000) to keep the in-process
  harness bounded.
- A fast-failing job can no longer be overwritten back to `queued` after it has
  already reached a terminal state; only the job id is attached in that case.

### 12.2 Preserved and intentionally different behavior

Preserved semantics:

- GRU layer order, units (256/128/64), BatchNorm, Dropout 0.3, Dense(1),
  sigmoid, Adam, binary cross-entropy, and input shape `(1, features)`.
- Label is the last column by default; 48 features are required for the
  research schema.
- Legacy client partition is still shuffle plus a floor split that drops the
  remainder.
- Legacy weighting still computes batch cardinality times batch size, so a
  partial final batch counts as a full one.
- The size-based Byzantine check remains available behind a flag and is not
  presented as a security control.

Documented differences (also emitted in every simulation result):

- The partition shuffle is seeded; the legacy scripts used the unseeded global
  `random` module.
- Client IDs are stable registration IDs, not positional indices derived from
  a shuffled list.
- The split and scaler are deterministic pure-Python ports, not byte-identical
  to NumPy/scikit-learn.
- The harness backend is a reference linear model, not the research GRU.
- No encryption, DKG, or threshold decryption is performed. Results are
  plaintext simulation and are labelled `encrypted: false`.
- Legacy metric parity is unverified; the datasets, TensorFlow 2.13/Python 3.8
  runtime, and verified CKKS backend are still missing.

### 12.3 Verification

From `web/backend` using the isolated WSL dependency targets:

- **74 passed, 1 warning** on Python 3.14.4.
- Warning: Starlette's `httpx` deprecation; non-blocking.
- OpenAPI generation: 22 paths.
- New tests cover the GRU contract, artifact round-trip, loader/scaler/split
  modes, metric formulas, crypto fail-closed behavior, partition determinism,
  weighting modes, aggregation failures, the opt-in Byzantine heuristic,
  harness determinism, abort/encryption gates, and the simulation API.

### 12.4 Deliberate non-claims

- The simulation endpoint is not federated learning with encryption and is not
  a reproduction of the paper.
- The reference linear backend is not the GRU.
- No result may be called encrypted, private, or parity-verified.
- Independent client runtimes, authentication, replay protection, real CKKS,
  predictions, and SDN mitigation remain unavailable.

### 12.5 Remaining blockers before later phases

1. No verified CKKS runtime or legacy Python 3.8/OpenFHE worker.
2. No approved datasets or trained legacy model artifacts.
3. No independent client runtime or authenticated client sessions.
4. No React frontend, TLS, rate limiting, or multi-user authorization.
5. The in-process simulation is single-host and bounded by
   `SECUREFED_SIMULATION_MAX_ROWS`.

## 13. User Phase 4/5 implementation status (dashboard and GRU training)

Status: completed and tested on 2026-11-19. The original repository remains
clean at `69b9ba9`. Section 12 retains the original-plan Phase 4 record; this
section records the user's renumbered delivery.

### 13.1 React dashboard (user Phase 4)

- Located in `web/frontend`; Vite 8, React 19.3, TypeScript 7.0, Tailwind 4.3,
  Recharts 3.11.
- Twelve sidebar pages plus NotFound, responsive shell, explicit
  loading/empty/error/unavailable states, and no demo data.
- Typed API client, loopback base URL, optional bearer token, job polling,
  training/simulation controls, result metrics, per-round records, and artifact
  metadata.
- `npm run lint` is `tsc -b` because native linter binaries are blocked by
  Windows Application Control and `typescript-eslint` rejects TypeScript 7.
- Verification: typecheck pass; 17 tests pass; production build pass with a
  non-blocking ~807 kB chunk warning. No browser/E2E test was run.

### 13.2 Dataset + GRU + federated training (user Phase 5)

- `federated/keras_backend.py`: real Keras GRU, lazily imported; 256/128/64,
  BatchNorm, Dropout 0.3, sigmoid Dense, Adam 1e-4, input `(1, 48)`.
- Nested Keras weights are flattened recursively and round-trip through the
  existing parameter specs (422,337 parameters for 48 features).
- `services/training_service.py` and `POST /experiments/{id}/train` run the
  plaintext round harness, capture final weights, and write:
  - `<dataset>_<clients>_model.json`
  - `preprocessing.json`
  - `result.json`
- Gated by `SECUREFED_ENABLE_TRAINING` (default false) and
  `SECUREFED_TRAINING_MAX_ROWS` (default 5000).
- Conservative defaults: one round, one local epoch. Legacy 15/5 must be
  requested explicitly.
- Results are labelled `plaintext_federated_training`, `encrypted: false`,
  `parity: "unverified"`, `workload.independent_clients: false`.
- Fixed the late job-attachment race with an atomic SQL update.

### 13.3 Verification

- Default Python 3.14 backend: 80 passed, 1 skipped.
- Isolated Python 3.11.18 + TensorFlow 2.13.1: 79 passed, 2 skipped; the real
  Keras API test runs and passes.
- Live uvicorn smoke test: upload, create, status, `/train`, job polling, and
  artifact files passed with `model: keras_gru`, 422,337 weights, 1 round.
- Synthetic 16-row data only; no approved dataset or full-scale run was used.

### 13.4 Deliberate non-claims

- Not encrypted federated learning; no CKKS, DKG, or threshold decryption.
- Not independent clients; clients are in-process simulations.
- Not paper parity; preprocessing, TensorFlow numerics, and datasets differ.
- No predictions, IPS, or SDN mitigation claims.
