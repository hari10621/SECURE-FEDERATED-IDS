# SecureFed-IDS — Phase 2 Dependency Audit and Reproducibility Check

Status at Phase 2 completion: inspection only. No package was installed, upgraded, or
removed. No virtual environment was created. No container was started, no image was
pulled, no dataset was downloaded, and no research script was executed. The original
repository is still clean at `69b9ba9`.

Phase 3 was subsequently approved and completed; see `INTEGRATION_PLAN.md` section 11 and
`backend/README.md` for the current backend status. This report remains the legacy
environment and CKKS audit.

This report replaces the Phase 1 draft. It re-checks the important Phase 1 conclusions
against the source, the binary metadata, PyPI package metadata, and the local runtime.

## 1. What was checked in Phase 2

| Area | Method | Result |
|---|---|---|
| Phase 1 documents | Read all four documents | Used as starting point, not trusted blindly |
| Direct imports | Searched every `.py` file | Eight package imports plus standard library |
| Dataset paths | Searched `data_path`, `DATA_PATH`, `read_csv` | Three parent-directory CSVs; none present |
| Model paths | Searched `model_path`, `MODEL_PATHS` | Three saved-model paths; none present |
| Package versions | PyPI JSON metadata for candidate pins | Constraints confirmed; one Phase 1 pin corrected |
| Python 3.8 wheels | PyPI file lists | cp38 Windows and manylinux wheels exist for all top-level pins |
| CKKS binary | Re-used read-only metadata from Phase 1 | Linux/CPython 3.8/OpenFHE extension; not executable here |
| Local runtime | Version and path checks | No Windows Python; Docker CLI present but daemon stopped; WSL2 Ubuntu 26.04 has Python 3.14, not 3.8 |
| Git state | `git status`, `git rev-parse` | Clean at `69b9ba9` |
| Installation/execution | Deliberately not performed | Waiting for approval |

### 1.1 Important correction to the Phase 1 draft

The Phase 1 report proposed `numpy==1.24.4`. That is wrong for this stack:
`tensorflow==2.13.1` declares `numpy<=1.24.3,>=1.22`. The proposed pin is now
`numpy==1.24.3`. NumPy 1.24.4 itself supports Python 3.8, but it violates TensorFlow's
declared constraint and must not be used.

### 1.2 Local runtime findings

- **Windows native:** no usable Python. Only Microsoft Store execution aliases exist.
- **Docker:** CLI `29.9.3` is installed, but the Docker Desktop Linux engine is not
  running. No image was inspected or pulled.
- **WSL2:** an `Ubuntu` distribution exists, but it is Ubuntu 26.04 with Python 3.14 and
  glibc 2.43. It does not contain Python 3.8. It is therefore not a drop-in CKKS
  environment.
- **Docker or a new Ubuntu 20.04 environment is the realistic parity path.** Both require
  approval before pulling images or installing packages.

## 2. Confirmed direct dependencies

Imports were verified in the source, not inferred from filenames. The eight model scripts
use the same top-level imports (`InSDN_4.py:9-30`, and equivalents in the other model
scripts). `InSDN_4.py` adds `shap` and `matplotlib` at lines 818-819 and 869.
`shapupdates.py:13-23` adds `scipy.stats.spearmanr`. `Figure Generation.py:7-20` adds
`matplotlib.gridspec`.

| Package | Used by | Purpose | Confirmed constraint | Proposed pin |
|---|---|---|---|---|
| `tensorflow` | all model scripts, `shapupdates.py`, `Figure Generation.py` | GRU training, `.h5` save/load | Requires Python `>=3.8`; caps NumPy at `<=1.24.3`; requires Keras `>=2.13.1,<2.14` | `2.13.1` |
| `numpy` | all scripts | Arrays, weight flattening, metrics | TensorFlow cap `<=1.24.3`; other pins accept NumPy 1.x | `1.24.3` |
| `pandas` | all scripts | CSV loading and tables | Python `>=3.8` for 2.0.3 | `2.0.3` |
| `scikit-learn` | all scripts | Split, scaler, metrics, ROC | Python `>=3.8`; NumPy `<2.0` | `1.3.2` |
| `shap` | InSDN model scripts, `shapupdates.py` | KernelExplainer and GradientExplainer | Python `>=3.8`; pulls `numba` | `0.44.1` |
| `scipy` | `shapupdates.py` | `spearmanr` | Python `>=3.8,<3.12`; NumPy `<1.27` | `1.10.1` |
| `matplotlib` | InSDN scripts, `shapupdates.py`, `Figure Generation.py` | Figures and plots | Python `>=3.8`; NumPy `<2` | `3.7.5` |
| `h5py` | Keras `.h5` artifacts | HDF5 model I/O | TensorFlow dependency; cp38 wheel available | `3.9.0` |
| `true_threshold_ckks` | all eight model scripts | Native threshold CKKS/DKG/Shamir | Not on PyPI; Linux/CPython 3.8 `.so` only | **Unavailable** |

Standard library only: `os`, `time`, `csv`, `hashlib`, `pickle`, `typing`, `random`,
`tempfile`, plus `typing` annotations. No installation is needed for these.

`pickle` is used to measure the in-memory size of a local weights list
(`measure_communication_overhead`), not to deserialize untrusted input.

## 3. Missing dependencies and inputs

### 3.1 Missing Python packages

All third-party packages are missing because no usable Python environment exists. This is
not a statement that they cannot be installed; it is the current machine state.

### 3.2 Missing native dependency

`true_threshold_ckks` is absent from HEAD and is not a PyPI package. It exists only as a
historical Linux shared object. Details are in section 5.

### 3.3 Missing project files

- No `requirements.txt`, `pyproject.toml`, `environment.yml`, lockfile, or hash file.
- No `README` describing setup or dataset acquisition.
- No tests, CI, or import guard.
- No datasets and no trained models.

## 4. Proposed pins and compatibility notes

### 4.1 Proposed top-level requirements

The following is a proposed file, not a file that was created:

```text
# Proposed requirements-legacy-py38.txt
# Python 3.8.10 only. Do not install on a modern Python.
tensorflow==2.13.1
keras==2.13.1
numpy==1.24.3
pandas==2.0.3
scikit-learn==1.3.2
scipy==1.10.1
matplotlib==3.7.5
shap==0.44.1
numba==0.58.1
llvmlite==0.41.1
h5py==3.9.0
protobuf==4.23.4
typing-extensions==4.5.0
```

Notes:

- `keras==2.13.1` is required by TensorFlow 2.13.1. Do not use Keras 3.
- `numba==0.58.1` and `llvmlite==0.41.1` are Python 3.8-compatible pins for SHAP's
  transitive dependency. Newer Numba releases may require a newer Python.
- `protobuf==4.23.4` satisfies TensorFlow 2.13's `<5` and exclusion constraints and
  TensorBoard 2.13's `>=3.19.6` constraint. If the resolver rejects it, record the
  conflict rather than silently changing Python.
- `typing-extensions==4.5.0` satisfies TensorFlow's `<4.6` constraint.
- `h5py==3.9.0` has a cp38 wheel and supports NumPy 1.24.
- `true_threshold_ckks` is deliberately not listed: it is not installable from PyPI and
  must not be fetched from an unknown source.

### 4.2 Important transitive packages

These are not direct imports, but they are part of the resolved environment. A full
hash-locked file cannot be produced without an approved install.

| Package | Why it appears | Note |
|---|---|---|
| `tensorboard==2.13.0` | TensorFlow dependency | Python 3.8 wheel available |
| `tensorflow-estimator==2.13.0` | TensorFlow dependency | Python 3.8 metadata available |
| `tensorflow-io-gcs-filesystem==0.31.0` | TensorFlow dependency | cp38 Windows and manylinux wheels exist |
| `joblib`, `threadpoolctl` | scikit-learn | Pure Python / compiled wheels |
| `tqdm`, `slicer==0.0.7`, `cloudpickle`, `packaging` | SHAP | Do not let `slicer` drift |
| `importlib-metadata` | Numba on Python <3.9 | Resolver should add it |
| `contourpy`, `cycler`, `fonttools`, `kiwisolver`, `pillow`, `pyparsing` | Matplotlib | Several have dropped Python 3.8 in newer releases; a lock/freeze is required |
| `python-dateutil`, `pytz`, `tzdata` | Pandas | Pure Python / data package |
| `google-auth`, `google-auth-oauthlib`, `markdown`, `requests`, `werkzeug`, `tensorboard-data-server` | TensorBoard | Resolver drift risk on Python 3.8 |
| `absl-py`, `astunparse`, `flatbuffers`, `gast`, `google-pasta`, `grpcio`, `libclang`, `opt-einsum`, `six`, `termcolor`, `wrapt` | TensorFlow | Resolver should choose compatible releases |

In 2026, many transitive projects no longer publish Python 3.8-compatible releases. An
unlocked `pip install` can therefore resolve to a newer package that requires Python 3.9
or newer. The mitigation is an approved, frozen, hash-locked environment; do not treat the
top-level pins as a complete lock.

### 4.3 Python and OS compatibility

| Environment | Python | Status for this project |
|---|---|---|
| Windows 11 native, x64 | 3.8.10 | TensorFlow 2.13.1 CPU works. Native GPU support is not available for this TensorFlow line on Windows. `true_threshold_ckks` cannot load. Suitable only for non-crypto import/model tests. |
| WSL2 current `Ubuntu` | 3.14.4 | Not suitable. The existing `.so` is CPython 3.8-only. Adding Python 3.8 to Ubuntu 26.04 is not the parity path. |
| WSL2 Ubuntu 20.04 (new distro) | 3.8.10 | Matches the extension's original toolchain (GCC 9.4, glibc 2.31). Possible, but requires a new distro installation and approval. |
| Docker `ubuntu:20.04` | 3.8.10 | Recommended for parity. Docker CLI exists but the daemon is stopped; pulling the image and running the container require approval. |
| Native Linux host | 3.8.10 | Same compatibility as Docker; requires OpenFHE 1.x shared libraries. |
| Any Python 3.9+ | 3.9+ | Cannot load the existing `.so`. A new stack would require reimplementation, not reproduction. |

The extension requires glibc 2.29 or newer. Ubuntu 20.04's glibc 2.31 satisfies this.
Newer glibc is generally backward compatible, but Python 3.8 and the C++/OpenFHE ABI are
the limiting factors.

## 5. `true_threshold_ckks` audit

### 5.1 What exists

| Property | Finding |
|---|---|
| File | `true_threshold_ckks.cpython-38-x86_64-linux-gnu.so` |
| Git history | Added in `6824e5b`; deleted from HEAD in `97ea3ee` |
| Size | 2,490,456 bytes |
| Format | ELF shared object, Linux x86-64 |
| Python ABI | CPython 3.8 only |
| Compiler | GCC 9.4.0 (Ubuntu 20.04 toolchain) |
| Minimum GLIBC | 2.29 |
| FHE library | OpenFHE (`lbcrypto`), CKKS |
| Linked sonames | `libOPENFHEcore.so.1`, `libOPENFHEpke.so.1`, `libstdc++.so.6`, `libm.so.6`, `libgcc_s.so.1`, `libc.so.6` |
| Binding | pybind11 |
| Serialization | cereal |
| Embedded mode | `NOISE_FLOODING_MULTIPARTY` |
| Exported behavior | DKG lead/join/finalize, EvalMult key phases, Shamir share construction, partial decryption, combine |

No `.cpp`, header, CMake file, pybind11 binding source, or build script is present in the
repository. A web search did not find a public `true_threshold_ckks` source repository.
The associated paper describes a custom C++/pybind11 layer over OpenFHE multiparty CKKS
plus Shamir resharing and Lagrange combination, but the paper text reviewed does not
provide the source artifact. The exact OpenFHE 1.x patch version is not recorded.

### 5.2 Build requirements if it must be rebuilt

A rebuild would need all of the following; this list is a requirement list, not a working
recipe, because the source is absent:

- Linux x86-64, preferably Ubuntu 20.04.
- CPython 3.8 development headers and a matching interpreter.
- GCC/G++ 9.4 or an ABI-compatible toolchain.
- CMake and a C++ build system.
- OpenFHE 1.x built with shared libraries, providing `libOPENFHEcore.so.1` and
  `libOPENFHEpke.so.1`.
- pybind11 and cereal.
- The original binding code and the exact DKG/Shamir implementation.
- A reproducible build manifest recording OpenFHE commit/version, compiler, flags, and
  the resulting SHA-256.

Without the source, the exact build recipe cannot be reconstructed. Do not invent one.

### 5.3 Paths forward and their effect on the research method

| Option | What it means | Effect on method/results | Recommendation |
|---|---|---|---|
| A. Restore the original `.so` from Git history | Use the project's own historical binary in a Linux/Python 3.8 environment with matching OpenFHE libraries | Preserves the intended method if the binary and parameters behave as logged. The binary is still untrusted until tested; the exact OpenFHE version is unknown | Best parity candidate, subject to approval, checksum, and verification |
| B. Rebuild the extension | Recreate the pybind11/OpenFHE wrapper from source | Can preserve the method if the source and OpenFHE version are recovered; high effort and risk | Only if A fails and the author provides source |
| C. OpenFHE Python bindings | Use documented `openfhe-python` APIs | **Not drop-in.** The original uses custom post-DKG Shamir shares and custom partial decryption; OpenFHE's native multiparty decryption is a different protocol. Serialization, ciphertext parameters, timings, and results would change | Requires explicit redesign approval; not a reproduction |
| D. TenSEAL or Pyfhel | Alternative CKKS libraries | CKKS encryption only; no equivalent threshold DKG/Shamir workflow. Method and results change | Not acceptable for parity |
| E. Disabled backend | Fail-closed `encryption: unavailable` mode | No encrypted-FL claims; the rest of the platform can be developed and tested | Safe fallback until CKKS is verified |

Package metadata checked for the alternatives:

- `openfhe` latest `1.6.1.0.24.4` requires Python `>=3.12`.
- `openfhe==1.2.3.1.20.4` declares Python `>=3.8` and its description says it requires
  Ubuntu 20.04. It is a Python wrapper for OpenFHE, not the original custom extension.
- `tenseal==0.3.15` has cp38 Windows and manylinux wheels; `0.3.16` does not publish cp38
  wheels. TenSEAL does not provide the original threshold-DKG/Shamir workflow.
- `pyfhel==3.4.3` declares Python `>=3.7` but publishes source only; it also lacks the
  original threshold workflow.

No alternative was installed or downloaded. None should be treated as a drop-in
replacement.

### 5.4 Verification gate before any encryption claim

1. Load the module in the chosen Linux/Python 3.8 environment.
2. Record `ldd` output and resolved OpenFHE library versions.
3. Encrypt/decrypt a known vector and check tolerance.
4. Verify a homomorphic weighted sum equals the plaintext weighted sum within tolerance.
5. Verify `threshold - 1` parties fail and `threshold` parties succeed.
6. Run the DKG/EvalMult sequence for 4, 8, and 12 parties.
7. Record the environment, hashes, and all outputs.

Until all seven pass, the application must report encryption as unavailable.

## 6. Dataset requirements

No dataset was downloaded. The paths below are exactly what the source expects, relative
to the original repository root. The parent directory is
`C:\Users\HARIS\Desktop\SecureFed-IDS`.

| Dataset | Path used by source | Used by | Present? | Approx. rows (inferred) |
|---|---|---|---|---|
| InSDN | `../Final_Binary_InSDN_Dataset.csv` | `InSDN_4.py:461`, `InSDN_8.py`, `InSDN_12.py`, `shapupdates.py:39`, `Figure Generation.py:29` | No | ~550,944 |
| CICIDS2017 | `../final_cicids2017_top48_features.csv` | `CICDDoS17_4.py:461`, `CICDDoS17_12.py`, `Figure Generation.py:41` | No | ~851,392 |
| CICIDS2019 | `../final_cicids2019_top48_features.csv` | `CICDDoD19_4.py:461`, `CICDDoS19_8.py`, `CICDDoS19_12.py`, `Figure Generation.py:35` | No | ~225,824 |

### 6.1 Schema assumptions

The code has no schema validation. It assumes:

- A numeric CSV readable by `pandas.read_csv`.
- The **last column is the label**; all preceding columns are features
  (`load_csv_data`, `InSDN_4.py:228-232`).
- A binary classification target. There is no check for exactly two classes.
- 48 features in practice. This is inferred from the `top48` filenames, the SHAP warning
  that expects 48 features, and the historical `104 chunks` line: the GRU has about
  422,337 parameters for 48 features, and 104 chunks of 4096 covers that. The code itself
  reads whatever feature count the CSV has.
- The SHAP feature-name extraction drops a column literally named `Label`
  (`InSDN_4.py:825`). If the label is named differently, feature names fall back to
  `f0..fN`. The exact column names of the missing CSVs cannot be verified.

### 6.2 Row-count derivation and caveats

The row counts are derived from the historical 4-client notebook outputs at commit
`53d70d3`, assuming batch size 32 and a 70/30 split. They are approximate and are not a
substitute for the missing files.

- InSDN: 4 clients x 3,013 train steps x 32 = 385,664 train rows; 5,165 test steps x 32 =
  165,280 test rows; total ~550,944. Other notebook cells show 6,694 test steps, which is
  inconsistent and likely stale output from another run.
- CICIDS2017: 4 x 4,656 x 32 = 595,968 train rows; 7,982 x 32 = 255,424 test rows; total
  ~851,392.
- CICIDS2019: 4 x 1,235 x 32 = 158,080 train rows; 2,117 x 32 = 67,744 test rows; total
  ~225,824.

File sizes, exact row counts, class balance, column names, checksums, and licenses are
unknown. Do not download a large dataset without explicit approval and a license review.

### 6.3 Required model artifacts

These are also missing:

- `4_InSDN_dkg_true/dkg_Federated_model_4.h5`
- `8_InSDN_dkg_true/dkg_Federated_model_4.h5`
- `12_InSDN_dkg_true/dkg_Federated_model_4.h5`
- `4_CICDDoS17_dkg_true/dkg_Federated_model_4.h5`
- `4_CICDDoS19_dkg_true/dkg_Federated_model_4.h5`

`Figure Generation.py` expects one model per dataset under those hardcoded directories.
`shapupdates.py` expects the three InSDN models and writes to `\shap_stability_results`,
which is the root of the current drive, not the project directory. It also calls
`display()` at lines 346, 438, 461, and 499, which is a Jupyter-only function.

The repository also has source-coverage gaps: there is no `CICDDoS17_8.py`, and the
4-client CICIDS2019 script is named `CICDDoD19_4.py` (typo). Do not assume every
dataset/client-count combination exists.

## 7. Proposed installation commands (not executed)

Nothing below has been run. Every command requires approval first. Do not install any of
these packages globally.

### 7.1 Windows native (non-CKKS checks only)

Precondition: install Python 3.8.10 x64 from the official Python distribution and verify
its path. This does not make `true_threshold_ckks` usable.

```powershell
# Proposed only. Do not run before approval.
py -3.8 -m venv C:\Users\HARIS\Desktop\SecureFed-IDS\web\.venv-win38
C:\Users\HARIS\Desktop\SecureFed-IDS\web\.venv-win38\Scripts\python.exe -m pip install --upgrade pip==23.3.2 setuptools==68.2.2 wheel==0.41.3
C:\Users\HARIS\Desktop\SecureFed-IDS\web\.venv-win38\Scripts\python.exe -m pip install --only-binary=:all: -r C:\Users\HARIS\Desktop\SecureFed-IDS\web\requirements-legacy-py38.txt
C:\Users\HARIS\Desktop\SecureFed-IDS\web\.venv-win38\Scripts\python.exe -m pip check
C:\Users\HARIS\Desktop\SecureFed-IDS\web\.venv-win38\Scripts\python.exe -m pip freeze
```

`requirements-legacy-py38.txt` is the proposed block in section 4.1. It has not been
created.

### 7.2 Docker Ubuntu 20.04 (recommended parity runtime)

Precondition: start Docker Desktop, approve the image pull, and create a project-local
workspace. This does not install anything on the Windows host.

```powershell
# Proposed only. Do not run before approval.
docker run --rm -it -v "C:\Users\HARIS\Desktop\SecureFed-IDS:/work" -w /work/web ubuntu:20.04 bash
```

Inside the container, after approval:

```bash
apt-get update
apt-get install -y python3.8 python3.8-venv python3-pip build-essential
python3.8 -m venv .venv-linux38
. .venv-linux38/bin/activate
python -m pip install --upgrade pip==23.3.2 setuptools==68.2.2 wheel==0.41.3
python -m pip install --only-binary=:all: -r requirements-legacy-py38.txt
python -m pip check
python -m pip freeze
```

This installs only inside the container. It does not provide OpenFHE libraries or make
the CKKS extension work.

### 7.3 CKKS restoration, after separate approval

Only after the runtime is approved, the binary is checksummed, and the OpenFHE 1.x
libraries are available:

```bash
# Proposed only. Do not run before approval.
git -C /work/threshold-fl-ids-sdn show \
  6824e5b:true_threshold_ckks.cpython-38-x86_64-linux-gnu.so \
  > /work/runtime/true_threshold_ckks.cpython-38-x86_64-linux-gnu.so
sha256sum /work/runtime/true_threshold_ckks.cpython-38-x86_64-linux-gnu.so
ldd /work/runtime/true_threshold_ckks.cpython-38-x86_64-linux-gnu.so
```

Do not run the `.so` until `ldd` resolves `libOPENFHEcore.so.1` and
`libOPENFHEpke.so.1` and the verification gate in section 5.4 has been approved.

### 7.4 What not to run

- Do not run `pip install true_threshold_ckks`; it is not a PyPI package.
- Do not download a `.so`, `.dll`, `.pyd`, wheel, or executable from an unknown source.
- Do not run the model scripts with the real `.so` until the verification gate passes.
- Do not run full training or SHAP jobs without a separate approval.

## 8. Safe minimal checks after installation (not run)

These are proposed checks, not executed. They require approval after the environment
exists.

```powershell
# Lightweight environment check; TensorFlow import is moderately heavy.
python -c "import sys; print(sys.version)"
python -c "import numpy, pandas, sklearn, scipy, matplotlib, h5py; print('core imports ok')"
python -c "import tensorflow as tf; print(tf.__version__)"
python -c "import shap; print(shap.__version__)"
```

For syntax-only checking, compile a copy of the scripts with the bytecode cache redirected
outside the repository. Do not import the scripts, because they execute top-level code and
import `true_threshold_ckks`:

```powershell
# Proposed only; compiles syntax, does not import or run the scripts.
$env:PYTHONPYCACHEPREFIX="$env:TEMP\securefed-pycache"
python -m py_compile "C:\path\to\copy\InSDN_4.py"
```

Do not run `python InSDN_4.py` in the repository root: it would read missing datasets and
write relative result directories into the original repository.

## 9. Risks and unresolved issues

1. **Native CKKS remains the critical blocker.** No end-to-end encrypted run is possible
   on this Windows machine.
2. **The `.so` is untrusted and its source is missing.** Restoring it from Git history is
   better than downloading an unknown binary, but it still requires a checksum, `ldd`
   review, and the seven-step verification gate.
3. **Exact OpenFHE version is unknown.** The sonames identify OpenFHE 1.x, not the patch
   release. A mismatched `libOPENFHEcore.so.1` can fail at load time or produce wrong
   results.
4. **OpenFHE Python is not a drop-in replacement.** The original uses custom Shamir
   shares and custom partial decryption; native OpenFHE multiparty decryption changes the
   protocol, timings, serialization, and potentially results.
5. **Python 3.8 is end-of-life.** TensorFlow 2.13.1 is old. The environment must be
   isolated, network-restricted where possible, and never exposed as a service.
6. **Transitive dependency drift.** An unlocked install in 2026 can select packages that
   no longer support Python 3.8. A frozen, hash-locked environment is required.
7. **NumPy pin correction.** `numpy==1.24.4` is incompatible with TensorFlow 2.13.1;
   use `1.24.3`.
8. **SHAP fragility.** `shap==0.44.1` plus `numba==0.58.1` is the Python 3.8-compatible
   combination, but `shap.plots._waterfall.waterfall_legacy` is a private API and
   `shapupdates.py` depends on `display()`. Both need isolation or replacement in the new
   application.
9. **GPU parity is not reproducible.** Historical logs show CUDA/cuDNN 8.6 and an RTX
   3090, but no driver or CUDA version is recorded. CPU fallback must be labelled as a
   different environment.
10. **Datasets are missing and unlicensed.** Exact schema, row counts, checksums, and
    distribution terms are unknown. The row counts in this report are log-derived
    estimates, not verified file metadata.
11. **Model artifacts are missing.** `Figure Generation.py` and `shapupdates.py` cannot
    run without them. The `_4` suffix is reused for 8- and 12-client runs, so artifact
    names are not trustworthy.
12. **Source coverage is incomplete.** There is no `CICDDoS17_8.py`; the 4-client
    CICIDS2019 file is misspelled `CICDDoD19_4.py`.
13. **No lockfile or hashes.** A reproducible install cannot be claimed until a freeze
    and hashes are recorded.
14. **Docker/WSL state.** Docker CLI is installed but the engine is stopped. The existing
    WSL Ubuntu is 26.04 with Python 3.14, so it is not the parity environment.

## 10. Phase 2 verdict and stop point

- The Python-level dependencies are conventional and appear resolvable on Python 3.8
  with the pins above. They are **not installed yet**.
- The native CKKS extension is still unavailable, Linux-only, CPython 3.8-only, and
  source-less. This blocks any encrypted federated run.
- No dataset, model, or lockfile is present.
- No virtual environment was created, no package was installed, no container was
  started, and no research code was executed.

Approval is needed before any of the following:

1. Choose the runtime: Docker Ubuntu 20.04 (recommended), a new WSL2 Ubuntu 20.04 distro,
   or a dedicated Linux host.
2. Approve creation of a project-local virtual environment and installation of the pins.
3. Approve pulling the Docker image, if Docker is chosen.
4. Approve restoring the historical `.so` from Git history, or choose the disabled CKKS
   backend for now.
5. Approve obtaining datasets and model artifacts, with license review.

Phase 2 ended here pending approval. Phase 3 was subsequently approved and completed; the
legacy CKKS and dataset blockers above are still unresolved.
