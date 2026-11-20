# SecureFed-IDS — Windows Installation Guide

This guide provides step-by-step instructions for installing and running SecureFed-IDS on Windows 10 and Windows 11. Two deployment methods are supported:
1. **Windows Native:** Runs the lightweight FastAPI backend, React frontend, and mock SDN emulation directly on Windows.
2. **WSL2 (Ubuntu 22.04 LTS):** Recommended for full TensorFlow 2.13.1 GRU training, Mininet, and live Ryu SDN controller integration.

---

## Method 1: Windows Native Setup (Lightweight & Frontend)

### 1. Prerequisites
- **Git for Windows:** Download from [git-scm.com](https://git-scm.com/).
- **Python 3.11 or 3.12:** Download from [python.org](https://www.python.org/). Check **"Add python.exe to PATH"** during installation.
- **Node.js (LTS v18 or v20):** Download from [nodejs.org](https://nodejs.org/).
- **uv (Fast Python Package Installer):** Open PowerShell and run:
  ```powershell
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```

### 2. Clone the Repository
Open PowerShell:
```powershell
cd C:\Users\$env:USERNAME\Desktop
git clone https://github.com/hari10621/SecureFed-IDS.git
cd SecureFed-IDS
```

### 3. Backend Setup
```powershell
cd web\backend

# Create virtual environment with uv
uv venv .venv --python 3.12

# Install backend dependencies
uv pip install --python .venv\Scripts\python.exe -r requirements-dev.txt
uv pip install --python .venv\Scripts\python.exe "numpy>=1.26.0,<3"

# Verify test suite
.venv\Scripts\python.exe -m pytest -q
# Expected: 105 passed, 1 skipped
```

### 4. Frontend Setup
Open a new PowerShell window:
```powershell
cd C:\Users\$env:USERNAME\Desktop\SecureFed-IDS\web\frontend

# Install node dependencies
npm ci

# Verify typecheck and tests
npm run lint
npm run test
npm run build
```

### 5. Starting the Applications
**Terminal 1 (Backend API):**
```powershell
cd C:\Users\$env:USERNAME\Desktop\SecureFed-IDS\web\backend
$env:SECUREFED_ENABLE_SIMULATION="true"
$env:SECUREFED_ENABLE_TRAINING="true"
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**Terminal 2 (Frontend Dashboard):**
```powershell
cd C:\Users\$env:USERNAME\Desktop\SecureFed-IDS\web\frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

Open `http://127.0.0.1:5173` in your browser.

---

## Method 2: WSL2 Setup (Full Research & Training Stack)

WSL2 is recommended if you need to run full GPU/CPU Keras GRU training, Mininet, and Ryu OpenFlow 1.3 controllers.

### 1. Enable WSL2
In Administrator PowerShell:
```powershell
wsl --install -d Ubuntu-22.04
```
Reboot your computer if prompted.

### 2. Configure Environment Inside Ubuntu
Launch Ubuntu and run:
```bash
# Update packages
sudo apt update && sudo apt install -y git curl build-essential python3.11 python3.11-venv python3-pip

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc

# Clone the repository inside Linux filesystem for optimal I/O
cd ~
git clone https://github.com/hari10621/SecureFed-IDS.git
cd SecureFed-IDS/web/backend

# Create Python 3.11 environment with TensorFlow
uv venv .venv-tf --python 3.11
uv pip install --python .venv-tf/bin/python -r requirements-dev.txt -r requirements-training.txt
uv pip install --python .venv-tf/bin/python "typing-extensions>=4.8.0"

# Verify backend with full TensorFlow tests
SECUREFED_RUN_TF_TESTS=1 .venv-tf/bin/python -m pytest -q
# Expected: 104 passed, 2 skipped
```

### 3. Mininet and Ryu Installation (Optional for Live SDN Lab)
```bash
sudo apt install -y mininet openvswitch-switch
pip3 install ryu

# Start Ryu controller
ryu-manager --verbose ryu.app.simple_switch_13 &

# Start Mininet single-switch topology
sudo mn --controller=remote,ip=127.0.0.1,port=6633 --switch=ovsk,protocols=OpenFlow13
```

---

## Common Windows Troubleshooting

### 1. PowerShell Script Execution Policy
If `uv` or activating venv says scripts are disabled:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 2. Port Conflicts
If port 8000 or 5173 is already in use:
```powershell
Get-NetTCPConnection -LocalPort 8000,5173 | Format-Table -Property LocalAddress,LocalPort,OwningProcess
Stop-Process -Id <PID> -Force
```

### 3. Application Control DLL Policy (`_processors_cy.pyd`)
If Windows Defender Application Control blocks compiled SQLAlchemy C extensions, the pure Python fallback operates automatically without affecting database operations.
