# SecureFed-IDS — Security & Limitations Report

This document transparently defines the security model, operational boundaries, cryptographic constraints, and lab safety protocols of SecureFed-IDS.

---

## 1. Security Architecture & Threat Model

### Cryptographic Boundary & CKKS Status
- **Target Design:** The reference paper specifies a 4-layer architecture with an offline Trusted Authority (TA) generating CKKS keys and distributing public keys and authorization tokens to edge SDN clients. Model weight deltas ($\Delta W_i$) are encrypted using CKKS before leaving the client.
- **Current Status in Web Platform:** **Fail-Closed / Unavailable**.
- **Reason:** Upstream research code relies on a custom compiled Linux CPython 3.8 extension (`true_threshold_ckks.so`) built against OpenFHE. The binary was removed from `HEAD` upstream and cannot run natively on modern Python 3.11/3.12 or Windows without a dedicated containerized toolchain.
- **Safety Guarantee:** SecureFed-IDS **never fabricates ciphertext or simulated encryption**. The backend explicitly raises `CryptoUnavailable` (HTTP 503) and sets `encryption_claimed: false` until a verified cryptographic backend is linked.

### Authentication & Replay Protection
- **Session Tokens:** Edge clients register with the federated server and receive a session token. In plaintext training, authentication is opt-in; in encrypted mode, tokens are strictly enforced.
- **Replay Protection:** To prevent malicious attackers or lagging clients from replaying past model updates, `FLServer` enforces a unique nonce cache bound to `(client_id, round_index)` with a 300-second maximum clock drift window. Replayed packets are immediately rejected.
- **SHA-256 Digest Integrity:** Weight updates include a digest calculated over both serialized floating-point weights and the round index:
  $$H_i = \text{SHA-256}(\text{weights} \mathbin{\Vert} \text{round\_index})$$
  This ensures that an update intercepted in round $t$ cannot be reused in round $t+1$.

### Byzantine Resilience
- **Opt-in Heuristic:** An optional 3-standard-deviation ($3\sigma$) outlier detection check on serialized weight payload sizes is provided (`byzantine_check=True`).
- **Documented Limitation:** As required by academic rigor, **this size heuristic is NOT a cryptographic Byzantine-resilience guarantee**. It flags updates that deviate radically in serialized structure or cardinality, but cannot detect sophisticated model-poisoning or gradient-inversion attacks.

---

## 2. SDN & IPS Lab Safety Constraints

### Safety Constraints for Production Networks
1. **No Real Network Intervention:** Automatic blocking is **strictly disabled by default** and forbidden on production interfaces. All OpenFlow flow modification commands are confined to isolated virtual lab networks (Mininet or local mock switches).
2. **Switch Whitelisting:** The SDN adapter rejects mitigation commands targeting switch DPIDs outside an explicitly approved whitelist (`allowed_switches`).
3. **Least-Privilege Priorities:** Generated OpenFlow flow modification drop rules are clamped to a maximum priority of 10 (`max_rule_priority = 10`), preventing accidental override of essential network control plane rules (ARP, LLDP, BGP).
4. **Emergency Stop & Rollback:** The SDN adapter maintains an atomic rollback ledger. Triggering `emergency_stop()` purges all active mitigation flow rules across all switches within milliseconds.

---

## 3. Known System Limitations

1. **In-Process Edge Simulation:** Clients currently operate as in-memory data shards within the server process rather than distributed edge containers across physical network topologies.
2. **Offline Datasets:** Live network detection currently maps OpenFlow counters to model features via heuristic transformation; continuous real-time packet stream feature extractors (like CICFlowMeter) are not yet integrated into the packet pipeline.
3. **SHAP Computational Overhead:** KernelExplainer SHAP evaluations in the original research scripts consume significant memory and time ($>10$ minutes on 200 samples); in-dashboard explainability is temporarily capped.
