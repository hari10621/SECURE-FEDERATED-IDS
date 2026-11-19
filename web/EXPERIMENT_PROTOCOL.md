# SecureFed-IDS Phase 7: Experiment Protocol

**Protocol Date:** 2026-11-19
**Phase:** 7 (end-to-end IDS validation)
**Status:** PROTOCOL — no experiments executed yet

## 1. Purpose

This document defines the experiment protocol for SecureFed-IDS end-to-end validation. **No experiments have been run yet** — this protocol must be approved and populated before any experimentation.

All experiments must follow this protocol to ensure reproducibility, traceability, and comparability. Every result must include the full metadata specified in Section 6.

## 2. High-Level Workflow

The complete federated IDS workflow, from dataset loading through prediction evaluation:

```
Dataset Loading → Preprocessing → Train/Test Split → Client Sharding
       ↓                   ↓                   ↓                   ↓
Local Training → Federated Rounds → Aggregation → Global Model
       ↓                   ↓
Prediction Evaluation → Confusion Matrix → Metrics (Acc, Prec, Rec, F1)
```

## 3. Experiment Configuration

Every experiment must document the following configuration fields:

| Field | Description | Example |
|---|---|---|
| `dataset_name` | Name of dataset as referenced in code | `InSDN`, `CICIDS2017`, `CICIDS2019` |
| `dataset_path` | Full path to CSV file (relative to repo root or absolute) | `../Final_Binary_InSDN_Dataset.csv` |
| `preprocessing_mode` | `clean`, `legacy`, or other defined mode | `clean` |
| `feature_count` | Number of features in the dataset | `48` (expected) |
| `label_column` | Name/index of label column | `last_column` (assumed) |
| `client_count` | Number of participating clients | `4`, `8`, or `12` (allowed values) |
| `rounds` | Number of federated rounds | `1`–`100` |
| `random_seed` | Seed for deterministic runs | integer, e.g., `42` |
| `evaluation_split` | Test split ratio or fixed split | `0.3` (30% test) or fixed indices |
| `model_architecture` | GRU, linear, or other | `reference_linear`, `gru_48f` |
| `model_config` | Architecture hyperparameters | `gru: 256/128/64, BN, Do 0.3, Dense(1, sigmoid), Adam, BCE` |
| `batch_size` | Training batch size | `32` (default) |
| `learning_rate` | Optimizer learning rate | `0.0001` (GRU default) or `0.1` (plaintext default) |
| `local_epochs` | Epochs per client per round | `1` (smoke), `5`, `15` (legacy) |
| `threshold` | Byzantine threshold (if applicable) | `2` (default) |
| `byzantine_check` | Whether Byzantine validation enabled | `True`/`False` |
| `encryption_backend` | `plaintext`, `native_ckks`, `disabled` | `plaintext` (current) |

## 3. Dataset Requirements

### 5.1 Schema Assumptions (from code inspection)

The code assumes:

- A numeric CSV readable by `pandas.read_csv`
- **The last column is the label**; all preceding columns are features
- A binary classification target (no explicit check for exactly two classes)
- **48 features in practice** — inferred from `top48` filenames and historical `104 chunks` line:
  - GRU has ~422,337 parameters for 48 features
  - 104 chunks × 4096 slots = 422,656 (covers the parameter count)
- The SHAP feature-name extraction drops a column literally named `Label`
- If the label is named differently, feature names fall back to `f0..fN`

**No schema validation is implemented in the code.** Any CSV that `pandas.read_csv` can read will be accepted, but results may be meaningless if the schema differs from expectations.

### 5.2 Required Dataset Verification (before experiment)

Before running any experiment, verify:

- [ ] CSV file exists at the specified path
- [ ] `pandas.read_csv` loads without error
- [ ] Last column contains binary labels (0/1 or -1/1)
- [ ] Feature columns contain finite numeric values (no NaN/Inf)
- [ ] Row count is reasonable (not zero, not excessively large without cap)
- [ ] Class distribution is roughly balanced (or documented imbalance)

**If any verification check fails, do not run the experiment** — fix the dataset or document the deviation.

## 4. Federated Workflow Details

### 4.1 Client Sharding

Training indices are partitioned across clients using `partition_training_indices()` with a fixed seed. The function performs a shuffle-then-floor-slice; remainder rows are dropped (not redistributed). This matches the legacy behavior from `InSDN_4.py:234-240`.

### 4.2 Local Training

Each client trains its local model on its shard:

- **Plaintext mode:** `ReferenceLinearBackend` or `KerasGRUBackend` (if TensorFlow available)
- **CKKS mode:** Not available (Phase 6 blocker); would use `TrueThresholdCKKS` if restored
- Global weights are provided; local training uses the provided `learning_rate`, `local_epochs`, `batch_size`
- Training output: trained weights, final loss, local metrics

### 4.3 Federated Round

One round consists of:

1. Global model distribution to all clients
2. Local training on each client's shard
3. Client upload: weights, sample_count, round_index, session_token (opt-in), digest
4. Server validation: shape, finite values, sample_count, replay protection (round_index freshness)
5. Server aggregation (weighted sum with sample_count or legacy batch_count factors)
6. Global model update

### 4.4 Aggregation Weighting

Two modes, matching the legacy code:

- **`sample`:** weights = sample_count / total_sample_count across participating clients
- **`legacy`:** weights = ceil(sample_count / batch_size) * batch_size / sum(effective_counts across clients)

### 4.5 Byzantine Validation (opt-in)

When `byzantine_check=True`:

- Size-based 3σ outlier heuristic on serialized weight sizes
- If `len(flagged) >= byzantine_threshold` (=2 by default), aggregation aborts
- **Documented limitation:** This is NOT a Byzantine-resilience control; it is a cardinality-free outlier detection
- When `byzantine_check=False`: heuristic skipped; aggregation proceeds with all clients

## 5. Evaluation and Metrics

### 5.1 Metrics Computed (when ground truth available)

| Metric | Formula/Definition |
|---|---|
| `accuracy` | (TP + TN) / (TP + TN + FP + FN) |
| `precision` | TP / (TP + FP) |
| `recall` | TP / (TP + FN) |
| `f1_score` | 2 * precision * recall / (precision + recall) |
| `mcc` | Matthews Correlation Coefficient |
| `balanced_accuracy` | (TPR + TNR) / 2 |
| `auc` | Area under ROC curve (if FPR and TPR available) |

### 5.2 Confusion Matrix

Must include:

- `TP` (true positives), `TN` (true negatives)
- `FP` (false positives), `FN` (false negatives)
- Derived from: global model predictions on test split vs. true labels

### 5.3 Reproducibility Requirements

Every experiment must document, at minimum:

- `random_seed` used for data split and any shuffling
- `numpy` random seed state if applicable
- Python version and package versions (ideally from a pinned environment)
- Whether `PYTHONHASHSEED` was set for full reproducibility

## 6. Required Metadata in Every Result

**Every experiment result must include ALL of the following:**

| Field | Description |
|---|---|
| `dataset_name` | e.g., `InSDN` |
| `dataset_path` | Full path that was loaded |
| `preprocessing_mode` | e.g., `clean` |
| `feature_count` | e.g., `48` |
| `label_column` | e.g., `last_column` |
| `client_count` | e.g., `4` |
| `rounds` | e.g., `1` |
| `random_seed` | e.g., `42` |
| `evaluation_split` | e.g., `0.3` or `fixed_indices` |
| `model_architecture` | e.g., `reference_linear` |
| `model_config` | e.g., `{"layers": [...], "activation": "sigmoid"}` |
| `batch_size` | e.g., `32` |
| `learning_rate` | e.g., `0.0001` |
| `local_epochs` | e.g., `1` |
| `threshold` | e.g., `2` |
| `byzantine_check` | e.g., `False` |
| `encryption_backend` | e.g., `plaintext` |
| `results` | See Section 7 for details |
| `timestamp` | ISO format, e.g., `2026-11-19T10:30:00` |

## 7. Experiment Results Structure

Each experiment result must contain the following:

| Field | Description |
|---|---|
| `accuracy` | Floating point, 0–1, or `null` if not computable |
| `precision` | Floating point, 0–1, or `null` |
| `recall` | Floating point, 0–1, or `null` |
| `f1_score` | Floating point, 0–1, or `null` |
| `mcc` | Floating point, -1–1, or `null` |
| `balanced_accuracy` | Floating point, 0–1, or `null` |
| `auc` | Floating point, 0–1, or `null` |
| `confusion_matrix` | dict with `TP`, `TN`, `FP`, `FN`, or `null` |
| `loss` | Final loss value, or `null` |
| `per_client_metrics` | optional dict client_id → {accuracy, loss}, or `null` |
| `rounds_completed` | integer, number of rounds actually completed |
| `final_model_digest` | SHA-256 of serialized model weights, or `null` |
| `notes` | Free text for documenting deviations, errors, or anomalies |

**If a field cannot be computed (e.g., no test data, no CKKS), it must be `null`, not omitted or fabricated.**

## 8. Small vs. Large Experiments

### 8.1 Small Validation Experiments (approve immediately)

- Synthetic data, 4 clients, 1 round, 1 local epoch
- Fixed seed, deterministic output verifiable
- Can be run in <5 minutes
- **Approve:** yes — these test the pipeline mechanics

### 8.2 Large/Time-Consuming Experiments (require explicit approval)

- Real datasets (InSDN/CICIDS2017/CICIDS2019)
- Multiple rounds (>5)
- Grid search over learning rates, epochs, client counts
- CKKS-encrypted rounds (requires Phase 6 approval)
- **Approve:** must request user approval before starting

**Rule of thumb:** If an experiment would take >30 minutes or require data not currently in the repository, ask for approval first.

## 9. Defect Handling

If an experiment fails:

1. **Record the failure** in the `notes` field with full error text
2. **Fix the defect** (code bug, data issue, configuration error)
3. **Rerun the experiment** from the beginning (do not patch mid-run)
4. **Document both attempts** in the `notes` field (first attempt + failure, then rerun)
5. **Do not fabricate results** to match expected outcomes

## 10. Security Mechanisms in Experiments

If running with security mechanisms enabled:

- `byzantine_check` flag must be set explicitly (`True` or `False`)
- `authentication` via session tokens: opt-in; empty/None tokens accepted in plaintext mode
- `replay_protection` via round_index: always active in `validate_update()`
- **Do not claim** that authentication or SHA-256 alone makes aggregation Byzantine-resilient (per Phase 6 documentation)

## 11. Approval Workflow

| Step | Action | Required |
|---|---|---|
| 1 | Review this protocol | All stakeholders |
| 2 | Approve runtime environment | User / approver |
| 3 | Approve dataset acquisition | User / approver (license review) |
| 4 | Approve CKKS restoration (if needed) | User / approver |
| 5 | Start small validation experiments | After steps 1–4 |
| 6 | Escalate to Phase 8 | After successful small experiments |

---

## 12. Protocol Status

| Item | Status |
|---|---|
| Protocol document | ✅ Created (this file) |
| Small experiments run | ❌ None yet (blocked by data/environment) |
| Large experiments run | ❌ None yet |
| IDS_VALIDATION_REPORT.md | ✅ Created (see separate file) |
| EXPERIMENT_RESULTS.md | ❌ None yet (populated after experiments) |
| Phase 8 readiness | ❌ Blocked — await small experiment success + approval |

---

**This protocol must be approved before any experiment execution.** After approval, start with small synthetic validation experiments, populate EXPERIMENT_RESULTS.md, then proceed to larger runs.

---

*Phase 7 protocol — STOP for approval before Phase 8. No results fabricated or copied from papers. All fields in Section 6 must be populated for every result.*