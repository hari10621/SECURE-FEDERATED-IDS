# SecureFed-IDS — Phase 1 Feature Matrix

Status vocabulary:

- **Implemented / executed** — code exists and a historical run log shows it completing.
- **Implemented / unverified** — code exists but was not run in this phase.
- **Partial** — only part of the feature is present or it is not enforced.
- **Not implemented** — absent from the repository.
- **Blocked** — cannot run because a dependency or input is missing.

"Historical" means evidence comes from the removed notebook
`InSDN_4.ipynb` at commit `53d70d3`, not from the current `.py` files, which were not
executed.

This matrix describes the original research repository as observed in Phase 1. It is not a
current gap list for the new application; the Phase 3 backend is documented in
`backend/README.md` and `backend/API.md`.

| Feature | Source file/function | Evidence | Status | Verification | Remaining work |
|---|---|---|---|---|---|
| GRU binary classifier | `InSDN_4.py:209-222` `build_gru_model`; same in all model scripts | 3 GRU layers 256/128/64, BN + Dropout 0.3, Dense(1, sigmoid), Adam, BCE | Implemented / historically executed | Historical notebook shows 5-epoch training and metrics | Extract to shared model factory; add architecture unit test |
| Input shape and feature handling | `InSDN_4.py:471-472,518` | `(N,1,F)` reshape; `F` read from CSV | Implemented / unverified | No schema validation in source | Add feature-count/schema validation and a 48-feature contract |
| CSV loading | `InSDN_4.py:228-232` `load_csv_data` | Last column is label, all others numeric features | Implemented / unverified | Datasets missing | Add dataset registry, checksums, column validation |
| Scaling | `InSDN_4.py:465-466` | `StandardScaler().fit_transform` on all data | Implemented / historically executed | Fit occurs before split (leakage) | Provide leakage-free mode; preserve legacy mode explicitly |
| Train/test split | `InSDN_4.py:468-469` | 30% test, seed 42, stratified | Implemented / historically executed | Seed recorded in source | Save split indices/artifacts; add run manifest |
| Client sharding | `InSDN_4.py:234-240` `create_clients` | Shuffle then floor-slice; remainder dropped | Implemented / historically executed | In-process only | Replace with real client data partitions; log dropped rows |
| Client independence | none | All clients are in-memory shards in one process | Not implemented | No network or process isolation | Build client runtime/service boundary |
| Client identity | `InSDN_4.py:591,602` | `client_names.index(client)` after `random.shuffle` | Partial / defective | Source inspection; IDs drift after first round | Assign stable IDs independent of list order |
| Local training | `InSDN_4.py:601-612` | Rebuild model, copy global weights, 5 epochs, batch 32 | Implemented / historically executed | Historical logs show epochs/loss | Extract trainer; add determinism controls |
| Global model | `InSDN_4.py:519,688` | Initial Keras model; weights replaced after decryption | Implemented / historically executed | Historical logs | Add versioned model registry and per-round checkpoints |
| Weight flatten/reshape | `InSDN_4.py:418-442` | Concatenate/reshape in layer order; padded tail ignored | Implemented / unverified | 104 chunks consistent with ~422k params | Round-trip unit test for arbitrary architectures |
| CKKS encryption | `InSDN_4.py:141-149,418-427`; `true_threshold_ckks` | `encrypt_to_bytes` per 4096-slot chunk | Blocked | Native `.so` removed; Windows incompatible | Restore/replace native backend; fail closed if absent |
| CKKS decryption | `InSDN_4.py:157-180,430-442` | `partial_decrypt_shamir` + `combine_partial_decryptions` | Blocked | Same | Add known-answer and aggregate-equivalence tests |
| DKG key generation | `InSDN_4.py:86-108` | Lead/join/finalize public key; EvalMult key phases | Blocked | Source comments + historical logs only | Verify API and security model independently |
| Shamir key sharing | `InSDN_4.py:110-133` | Generates all party shares, sums them, registers keys | Blocked | Source inspection shows one-process key material | Move parties into separate trust domains |
| Homomorphic weighted aggregation | `InSDN_4.py:371-412` | Encrypted scalar multiply + add per chunk | Blocked | Requires native CKKS | Test against plaintext weighted sum |
| Aggregation weighting | `InSDN_4.py:247-256,623-628` | Batch-count × 32 / global batch-count × 32 | Implemented / unverified | Factors `0.2500` in historical 4-client log | Use exact sample counts; test unequal shards |
| SHA-256 chunk integrity | `InSDN_4.py:36-41,426` | Hash per ciphertext chunk; server recomputes | Implemented / historically executed | Logs show 104 chunks verified per client | Add authenticated signatures/MACs, not just hashes |
| Aggregate hash verification | `InSDN_4.py:404-412,445-446` | Hash of concatenated aggregate stored and checked | Implemented / historically executed | Logs show "Aggregated hash verified" | Bind hash to round and sender identity |
| Client registration | `InSDN_4.py:321-335` | Token created and stored per client ID | Partial | Token never checked on update | Require token/session authentication |
| Authentication | none | No signatures, mTLS, API auth, or credential verification | Not implemented | Source inspection | Add authenticated client sessions |
| Replay protection | none | No nonce, round binding, or timestamp | Not implemented | Source inspection | Bind updates to round + nonce |
| Byzantine validation | `InSDN_4.py:355-369` | Ciphertext size > 3σ heuristic; aborts or filters | Partial / unverified | Historical run had no malicious clients | Replace with size-independent robust validation |
| Robust aggregation | none | Only weighted sum; no median/trimmed mean/clipping | Not implemented | Source inspection | Add robust aggregation baseline and tests |
| Per-round global metrics | `InSDN_4.py:690-727` | Acc, precision, recall, F1, MCC, kappa, log loss, balanced accuracy | Implemented / historically executed | Historical logs show all rounds | Add AUC and Wilson/CI reporting |
| Per-client metrics | `InSDN_4.py:633-638` | Only loss/accuracy/enc/dec time are real | Partial | Precision/recall/AUC written as `0` | Compute real per-client metrics or remove columns |
| AUC | `Figure Generation.py:97-98` | ROC AUC computed only in figure script | Partial | Requires saved models | Move into evaluation pipeline |
| Centralised baseline | `InSDN_4.py:774-791` | 1 epoch, lr 0.001, batch 512 | Implemented / historically executed | Historical output | Match FL training budget or label as non-comparable |
| Final model artifact | `InSDN_4.py:772` | `dkg_Federated_model_4.h5` for all client counts | Partial / defective | Duplicate filename across variants | Use unique names and a manifest |
| CSV result artifacts | `InSDN_4.py:521-541` | Per-client, per-round, communication, summary CSVs | Implemented / historically executed | Writers present | Add run IDs, schemas, and atomic writes |
| Communication accounting | `InSDN_4.py:283-294,588-589,690-706` | Pickle size × clients × 2; encrypted size; timers | Implemented / unverified | Timers and pickle size vary | Define measurement method; record environment |
| KernelExplainer SHAP | `InSDN_4.py:811-999` | Background 100, samples 200, summary/bar/waterfall/top-15/fidelity | Implemented / historically executed (InSDN) | Notebook logs show SHAP start; plots not inspected | Bound runtime/memory; add tests; remove private API |
| GradientExplainer SHAP | `shapupdates.py:261-317` | Three saved models, balanced samples, Spearman/Jaccard stability | Implemented / unverified | Models absent; uses `display()` | Make notebook-independent; parameterize paths |
| SHAP for CICDDoS variants | CICDDoS scripts | SHAP removed or commented out | Not implemented for those datasets | Source diff | Implement consistently or document why omitted |
| Reproducibility controls | various | Split seed only; unseeded shuffles/party choice; no global TF seed | Partial | Source inspection | Add seeds, lockfile, dataset/version hashes, run manifest |
| Dataset availability | none | Paths point to missing parent CSVs | Blocked | Files absent | Obtain, validate, and document datasets |
| Environment/packaging | none | No requirements, lockfile, tests, CI | Not implemented | Repository listing | Create pinned env and test suite |
| Backend API | none | No HTTP/gRPC service | Not implemented | Repository listing | Build minimal local-first API |
| Frontend | none | No UI | Not implemented | Repository listing | Build after backend contracts |
| Persistent storage | none | Only CSV/H5 files | Not implemented | Source inspection | Add run/artifact storage with access control |
| File-upload hardening | none | No upload path | Not implemented | Repository listing | Validate type/size, confine to project directory |
| IPS / SDN mitigation | none | No controller or OpenFlow code | Not implemented | Repository listing | Separate later phase; isolated lab only |
| Tests | none | No test files or test runner | Not implemented | Repository listing | Add unit/integration tests before features |
| Documentation | none | No README | Not implemented | Repository listing | Write setup/run/security docs |

## Summary counts

- Implemented and historically executed: 12
- Implemented but unverified in this phase: 6
- Partial / defective: 7
- Not implemented: 13
- Blocked: 6

Counts describe the 44 rows in this matrix only; they are not a quality score.
