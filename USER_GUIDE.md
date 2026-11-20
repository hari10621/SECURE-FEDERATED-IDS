# SecureFed-IDS — User Guide

This guide walks you through using the SecureFed-IDS web console and REST API. The console provides 12 dedicated pages for configuring datasets, monitoring federated training, auditing cryptographic and security status, and controlling SDN/IPS mitigation.

---

## 1. Overview Dashboard (`/`)
- **System Health:** Live indicators for API connection, SQLite database integrity, CKKS encryption status, and SDN adapter state.
- **Recent Experiments:** Table of recently created, running, and completed federated experiments with timestamps and outcomes.
- **Capability Summary:** Transparent display of active capabilities (e.g. GRU training, mock SDN) vs. fail-closed capabilities (e.g. native CKKS, independent client containers).

---

## 2. Datasets Management (`/datasets`)
- **Upload CSV:** Drag-and-drop or select a network traffic CSV file.
- **Validation Pipeline:**
  - Enforces schema: exactly 48 numeric feature columns and 1 binary label column (`0` = normal, `1` = attack) at the end.
  - Checks for non-numeric, NaN, or infinite values.
  - Confines file storage to `web/var/uploads/` with sanitized filenames to prevent directory traversal.
- **Preprocessing Configuration:**
  - `clean` (Recommended): Splits dataset into train/test (70/30) first, fitting `StandardScaler` only on the training partition to prevent statistical data leakage.
  - `legacy`: Fits `StandardScaler` across all rows before splitting, exactly replicating historical research scripts.

---

## 3. Federated Clients (`/clients`)
- **Client Registry:** Lists registered client identities participating in federated learning.
- **Supported Topologies:** 4, 8, or 12 clients.
- **Partitioning:** Shards the training dataset across clients using seeded deterministic shuffle-then-floor slicing.
- **Session Tokens:** Displays opt-in authentication tokens and activity timestamps for each client.

---

## 4. Federated Training (`/training`)
- **Experiment Setup:**
  - Select validated dataset.
  - Configure client count (4, 8, 12), communication rounds (e.g., 15), local epochs (e.g., 5), batch size (e.g., 32), and learning rate (e.g., `0.0001`).
  - Choose aggregation weighting: `sample` (proportional to sample size) or `legacy` (cardinality-based batch rounding).
- **Execution Modes:**
  - **Simulation Mode:** Fast deterministic linear benchmark executed via `POST /experiments/{id}/simulate`.
  - **Real GRU Training:** Trains the 3-block Keras GRU (`256 → 128 → 64`) via `POST /experiments/{id}/train`.
- **Live Progress:** Visual progress bars, active round count, and real-time loss and accuracy curves plotted using Recharts.
- **Artifact Export:** Download trained model weights (`securefed-training-v1`), scaler statistics (`securefed-preprocessing-v1`), and full per-round metric logs.

---

## 5. Homomorphic Encryption (`/encryption`)
- **Current Status:** Reports **Fail-Closed / Unavailable**.
- **Cryptographic Specifications:** Displays the target CKKS parameters from the reference paper:
  - Polynomial modulus degree $n = 8192$ (4,096 complex slots).
  - Modulus chain $Q = [60, 40, 40, 60]$, scale $\Delta = 2^{40}$.
  - Weight chunking into 104 chunks for 422,337 GRU parameters.
- **Verification Gate:** Documents the 7-step criteria required before encrypted aggregation can be toggled on.

---

## 6. Security Monitoring (`/security`)
- **Authentication:** Verifies client update credentials against recorded session tokens.
- **Replay Protection:** Rejects duplicate updates for the same client and round index using the `(client_id, round_index)` nonce cache.
- **SHA-256 Digest Integrity:** Verifies update integrity with round-bound hashes ($H_i = \text{SHA-256}(\text{weights} \mathbin{\Vert} \text{round}$).
- **Byzantine Outlier Heuristic:** Opt-in 3σ size deviation filter to detect anomalous or corrupted client updates.

---

## 7. Intrusion Detection (`/intrusion`)
- **Flow Inference:** Feeds 48-feature flow vectors into the trained global model.
- **Classification:** Outputs attack probability (0.0 to 1.0) and binary decision (threshold = 0.5).
- **Alert Feed:** Real-time log of detected attack flows, complete with source/dest IP, protocol, ports, and timestamp.

---

## 8. SDN Network Emulation (`/sdn`)
- **Controller Status:** Displays connection state to OpenFlow 1.3 controller (Ryu) or mock emulation engine.
- **Switch Topology:** Lists active switch Datapath IDs (e.g. `00:00:00:00:00:00:00:01`), port counts, and hardware metadata.
- **Flow Statistics:** Displays live OpenFlow flow tables with packet counts, byte counts, durations, and priorities.

---

## 9. IPS / Prevention (`/ips`)
- **Mitigation Modes:**
  - `detection_only`: Alerts generated; no OpenFlow flow modification rules installed.
  - `manual_approval`: Mitigation requests require explicit human confirmation via the dashboard before rule installation.
  - `automatic_blocking`: Automatically pushes OpenFlow drop rules for detected intrusions (strictly restricted to isolated test labs).
- **Rule Management:** Lists active flow-mod rules, match parameters, and installation timestamps.
- **Rollback & Emergency Stop:** Instant one-click rollback of specific flow entries or global `Emergency Stop` to purge all active blocks.

---

## 10. Performance Evaluation (`/performance`)
- **Metric Comparison:** Side-by-side comparison of accuracy, precision, recall, F1-score, MCC, and AUC across rounds and client counts.
- **Overhead Accounting:** Communication payload sizes and client compute timing.

---

## 11. Experiment History (`/history`)
- **Audit Log:** Comprehensive historical ledger of all simulation, training, and mitigation jobs stored in `web/var/securefed.db`.
- **Export Reports:** Export full experiment results in JSON or CSV format for academic paperwork and presentation.

---

## 12. Settings (`/settings`)
- **Backend Base URL:** Configures local API endpoint (default: `http://127.0.0.1:8000`).
- **Security Tokens:** Configures local `SECUREFED_API_TOKEN` for authenticated administrative sessions.
