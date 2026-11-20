# SecureFed-IDS — Research Reproducibility & Benchmark Protocol

This document details the exact dataset schemas, feature selection methodology, preprocessing options, and training protocols required to reproduce the experimental results from the reference paper:
> **Reference:** S. M. Shamim et al., *"A Secure and Privacy-Preserving Federated Learning-Based Intrusion Detection System for SDN Networks Using Homomorphic Encryption,"* IEEE Access, May 2026 (`10.1109/ACCESS.2026.3691160`).

---

## 1. Datasets & Feature Selection

The reference paper benchmarks across three network intrusion datasets:
1. **InSDN:** Synthetic SDN network dataset covering DoS, DDoS, Probe, BPS, Web, and U2R attacks.
2. **CICDDoS2017:** High-volume DDoS benchmark containing common attack vectors.
3. **CICDDoS2019:** Modern DDoS traffic benchmark featuring NetBIOS, LDAP, MSSQL, Syn, and UDP floods.

### 48 Chi-Square Selected Features
For each dataset, raw flows containing 80+ network fields were reduced to the **top 48 most discriminative features** using Chi-Square ($\chi^2$) feature selection.
- **CSV Format Requirement:**
  - Column 1 to Column 48: Numeric flow features (floats/integers).
  - Column 49 (Last Column): Binary label (`0` for Normal, `1` for Attack).
- **Target Filenames:**
  - `Final_Binary_InSDN_Dataset.csv`
  - `final_cicids2017_top48_features.csv`
  - `final_cicids2019_top48_features.csv`

---

## 2. Preprocessing & Data Partitioning

### Preprocessing Modes
1. **`clean` Mode (Recommended for Valid Benchmarks):**
   - Applies an initial 70% / 30% train-test split (`test_size=0.3`, fixed `seed=42`).
   - Fits `StandardScaler` ($\mu, \sigma$) **only** on the training partition.
   - Transforms test data using the fitted training scaler parameters, completely eliminating data leakage.
2. **`legacy` Mode (Research Script Reproduction):**
   - Fits `StandardScaler` across the entire dataset before splitting.
   - Replicates the historical behavior in `InSDN_4.py:465-466`.

### Client Sharding
- Training rows are distributed across $N \in \{4, 8, 12\}$ clients using `partition_training_indices()`.
- Indices are shuffled with a deterministic seed, divided into equal floor slices ($S = \lfloor \text{Total} / N \rfloor$), and trailing remainder rows are dropped, matching the original script logic.

---

## 3. GRU Hyperparameters & Model Configuration

- **Input Dimension:** 48 features, formatted as `(batch_size, 1, 48)`.
- **Model Topology:**
  - Layer 1: `GRU(256, return_sequences=True)` + `BatchNormalization()` + `Dropout(0.3)`
  - Layer 2: `GRU(128, return_sequences=True)` + `BatchNormalization()` + `Dropout(0.3)`
  - Layer 3: `GRU(64, return_sequences=False)` + `BatchNormalization()` + `Dropout(0.3)`
  - Dense Output: `Dense(1, activation='sigmoid')`
- **Total Parameters:** 422,337 floating-point values.
- **Optimizer:** Adam with learning rate $\eta = 1 \times 10^{-4}$, $\beta_1 = 0.9$, $\beta_2 = 0.999$, $\epsilon = 1 \times 10^{-7}$.
- **Loss Function:** Binary Cross-Entropy.
- **Federated Rounds:** 15 communication rounds.
- **Local Epochs:** 5 epochs per client per round.
- **Batch Size:** 32 or 512.

---

## 4. Expected Performance Metrics (Paper Benchmarks)

Under true Homomorphic Encryption Federated Learning (HE-FL) with $N=4$ clients:

| Metric | InSDN Dataset | CICDDoS2017 Dataset | CICDDoS2019 Dataset |
| :--- | :---: | :---: | :---: |
| **Accuracy** | **99.94%** | **99.08%** | **99.62%** |
| **Precision** | **99.93%** | **99.05%** | **99.60%** |
| **Recall** | **99.95%** | **99.12%** | **99.65%** |
| **F1-Score** | **99.94%** | **99.08%** | **99.62%** |
| **ROC AUC** | **0.9998** | **0.9982** | **0.9991** |

---

## 5. Step-by-Step Reproduction Procedure

1. **Obtain Data:** Place the 48-feature CSV files into `web/var/datasets/` or upload them via the Web Console.
2. **Execute Full 15-Round GRU Run:**
   ```bash
   cd web/backend
   .venv-tf/bin/python -c '
   from app.domain.dataset import load_csv_dataset, preprocess
   from app.domain.federated.keras_backend import KerasGRUBackend
   from app.domain.federated.round import FederatedHarness, FederatedConfig

   loaded = load_csv_dataset("web/var/datasets/Final_Binary_InSDN_Dataset.csv", label_column=None)
   prepared = preprocess(loaded.rows, loaded.labels, loaded.feature_names, mode="clean", seed=42)

   config = FederatedConfig(num_clients=4, rounds=15, local_epochs=5, batch_size=32, learning_rate=1e-4, seed=42)
   harness = FederatedHarness(KerasGRUBackend(), config)
   result = harness.run(prepared)
   print("Reproduced Metrics:", result["final_metrics"])
   '
   ```
3. **Inspect Output Artifacts:** Weight matrices and evaluation logs will be generated in `web/var/models/`.
