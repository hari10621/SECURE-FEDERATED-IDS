# SecureFed-IDS — Architecture & Design

SecureFed-IDS integrates Federated Machine Learning (FL) with Software-Defined Networking (SDN) to achieve privacy-preserving intrusion detection and mitigation. This document outlines the system architecture, component relationships, and threat boundaries.

---

## 1. High-Level Architecture

The system is organized into four distinct operational layers:

```
+-------------------------------------------------------------------------+
|                         Layer 1: Presentation                           |
|      React 19 + TypeScript + Vite Console (12 Specialized Views)        |
+-------------------------------------------------------------------------+
                                    │  HTTP / REST (Port 8000)
                                    ▼
+-------------------------------------------------------------------------+
|                         Layer 2: Application Core                       |
|   FastAPI REST API · Pydantic Validation · Job Worker · SQLite Storage  |
+-------------------------------------------------------------------------+
                    │                                   │
                    ▼                                   ▼
+-------------------------------------+  +--------------------------------+
|     Layer 3: Federated Learning     |  |       Layer 4: SDN & IPS       |
|  3-Block Keras GRU (256/128/64)     |  |  SDNAdapter (Mock / Ryu / CSV) |
|  Deterministic Harness (Seeded)     |  |  OpenFlow 1.3 Flow Stats Parse |
|  Weight Codec (104 Chunks × 4096)   |  |  48-Feature Extraction Pipeline|
|  Sample & Batch Aggregation         |  |  IPS Engine (3 Mitigation Modes|
|  Replay & Byzantine Security Checks |  |  Safe Flow-Mod Rollback Engine |
+-------------------------------------+  +--------------------------------+
```

---

## 2. Component Breakdown

### Layer 1: Presentation (`web/frontend/`)
- Single-page application built with React 19, Vite, TypeScript, and Tailwind CSS.
- **State Management:** Custom API hooks (`useApi.ts`) communicating with the backend over REST.
- **Vite Proxy:** Routes `/api` requests directly to `http://127.0.0.1:8000` to eliminate CORS overhead during development.
- **Fail-Closed Presentation:** When backend capabilities (such as CKKS or Ryu) are unavailable, UI components render informative disabled banners rather than mock data.

### Layer 2: Application Backend (`web/backend/app/`)
- **Framework:** FastAPI running on Uvicorn.
- **Persistence:** SQLite database (`web/var/securefed.db`) with SQLAlchemy ORM modeling Datasets, Experiments, Clients, and Jobs.
- **Storage Subsystem:** Confined directories under `web/var/`:
  - `uploads/`: Secure streaming CSV upload directory.
  - `datasets/`: Validated dataset artifacts.
  - `models/`: Exported Keras weights and JSON metadata.
  - `runs/`: Execution logs and metric summaries.
- **Job Orchestrator:** In-process asynchronous task manager supporting safe cancellation and automatic recovery of interrupted jobs upon server reboot.

### Layer 3: Federated Learning Engine (`app/domain/federated/`)
- **Local IDS Classifier:** 3-block stacked GRU architecture reproducing Shamir et al. (IEEE Access 2026):
  - Input: `(batch_size, 1, 48)`
  - Block 1: `GRU(256, return_sequences=True)` → `BatchNormalization` → `Dropout(0.3)`
  - Block 2: `GRU(128, return_sequences=True)` → `BatchNormalization` → `Dropout(0.3)`
  - Block 3: `GRU(64, return_sequences=False)` → `BatchNormalization` → `Dropout(0.3)`
  - Output: `Dense(1, activation='sigmoid')` (Threshold = 0.5)
  - Optimizer: Adam (`lr = 1e-4`), Loss: Binary Cross-Entropy.
  - Total Parameters: 422,337 floats.
- **Weight Codec:** Lossless flatten and reshape mapping Keras weight tensors to 1D vectors and 104 chunks of 4,096 elements.
- **Server Aggregation:**
  - `sample` mode: $W^{(t)} = \sum_{i=1}^{N} \frac{n_i}{\sum n_j} W_i^{(t)}$
  - `legacy` mode: Replicates research scripts rounding partial batches up.
- **Security Mechanisms:**
  - Round-bound SHA-256 weight digests.
  - Per-client replay protection nonces.
  - Opt-in 3σ Byzantine size-outlier filtering.

### Layer 4: SDN & IPS Subsystem (`app/services/sdn_adapter.py`)
- **Modular Adapter:**
  - `mock`: In-memory OpenFlow 1.3 switch emulation for development and testing.
  - `ryu`: Native connection to a live Ryu OpenFlow 1.3 controller.
  - `offline`: Replay network traffic from packet capture CSV logs.
- **Feature Extraction:** Maps raw OpenFlow match fields and flow counters to the 48-feature input expected by the GRU IDS.
- **Mitigation Engine:**
  - Generates `MitigationRequest` upon attack detection ($P(\text{attack}) \ge 0.5$ or $0.7$).
  - In `manual_approval` mode, queues requests for operator signoff.
  - In `automatic_blocking` mode, pushes OpenFlow flow modification rules with strict priority limits (max priority 10).
  - Maintains full rollback history and atomic `emergency_stop()` functionality.

---

## 3. Data Flow Diagram

```
[Raw Traffic / Flows] ──► [SDN Controller / Adapter]
                                  │
                                  ▼
                         [48-Feature Extraction]
                                  │
                                  ▼
                         [GRU Model Inference]
                                  │
                   ┌──────────────┴──────────────┐
                   ▼                             ▼
           [Normal Traffic]             [Attack Detected]
           (Forward normally)                    │
                                                 ▼
                                        [Alert Generation]
                                                 │
                                                 ▼
                                        [IPS Mitigation Policy]
                                                 │
                             ┌───────────────────┼───────────────────┐
                             ▼                   ▼                   ▼
                      [Detection Only]   [Manual Approval]   [Automatic Block]
                      (Log alert only)   (Await operator)    (Push Flow-Mod)
                                                                     │
                                                                     ▼
                                                             [Verify Flow Drop]
                                                                     │
                                                                     ▼
                                                             [Rollback on Reset]
```

---

## 4. Threat Model & Security Boundaries

1. **Client Isolation:** Current edge clients operate in-memory on a single machine. In production, edge clients must run on physically isolated hardware nodes communicating over TLS/gRPC.
2. **Untrusted Uploads:** CSV files uploaded to `/api/v1/datasets` are confined to `web/var/uploads/`, validated against an exact 49-column numeric regex, and rejected if illegal characters or traversal tokens are detected.
3. **No Arbitrary Execution:** Research scripts are executed through strict allowlisted argument builders (`research_adapter.py`); arbitrary terminal commands or script paths from the web API are rejected.
4. **Network Safety:** The SDN adapter enforces an allowed-switches whitelist and minimum flow priority constraints to prevent accidental disruption of production networks.
