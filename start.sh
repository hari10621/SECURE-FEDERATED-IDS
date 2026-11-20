#!/bin/bash
# SecureFed-IDS Startup Script
# Checks basic requirements and starts frontend + backend

set -e

echo "========================================="
echo "SecureFed-IDS Startup Script"
echo "========================================="

# ==========================================
# REQUIREMENT CHECKS
# ==========================================

echo ""
echo "--- Checking Requirements ---"

# 1. Check operating system
OS=$(uname -s)
if [ "$OS" = "Darwin" ] || [ "$OS" = "Linux" ]; then
    echo "✅ OS: $OS (supported)"
else
    echo "⚠️  OS: $OS — Windows detected; project runs in mock mode natively"
fi

# 2. Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
PY_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PY_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)
if [ -x "$(command -v python3)" ]; then
    if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 8 ]; then
        echo "✅ Python: $PYTHON_VERSION (supported)"
    else
        echo "⚠️  Python $PYTHON_VERSION — 3.8+ recommended; project may work with limitations"
    fi
else
    echo "❌ Python3 not found — install Python 3.8+ first"
    exit 1
fi

# 3. Check if we're in the project directory
if [ ! -f "web/backend/app/main.py" ]; then
    echo "❌ Not in SecureFed-IDS project directory — missing web/backend/app/main.py"
    echo "   Run this script from: C:\\Users\\HARIS\\Desktop\\SecureFed-IDS"
    exit 1
fi
echo "✅ Project directory confirmed"

# 4. Check Node.js for frontend
if [ -x "$(command -v node)" ]; then
    NODE_VERSION=$(node --version)
    echo "✅ Node.js: $NODE_VERSION available"
    HAS_NPM=$( [ -x "$(command -v npm)" ] && echo "yes" || echo "no" )
    if [ "$HAS_NPM" = "yes" ]; then
        echo "✅ npm available"
    else
        echo "⚠️  npm not found — frontend build/tests may fail"
    fi
else
    echo "⚠️  Node.js not found — frontend will not build; skip frontend setup"
fi

# 5. Check if backend dependencies are installed
if [ -f "web/backend/requirements.txt" ] || [ -f "web/backend/requirements-dev.txt" ]; then
    echo "✅ Backend requirements files found"
    if [ -d "web/backend/.venv" ] || [ -d "web/backend/venv" ]; then
        echo "✅ Backend virtual environment exists"
    else
        echo "⚠️  No backend venv detected — consider: python3 -m venv web/backend/venv && source web/backend/venv/bin/activate && pip install -r web/backend/requirements.txt"
    fi
else
    echo "⚠️  No requirements.txt found in web/backend/"
fi

# 6. Check if frontend dependencies are installed
if [ -d "web/frontend/node_modules" ]; then
    echo "✅ Frontend node_modules exist"
else
    echo "⚠️  Frontend node_modules missing — run: cd web/frontend && npm install"
fi

echo ""
echo "--- All requirement checks complete ---"
echo ""

# ==========================================
# BACKEND STARTUP
# ==========================================

echo ""
echo "--- Starting Backend (FastAPI + Uvicorn) ---"

cd "$(dirname "$0")/web/backend"

# Activate venv if it exists, otherwise use system python
if [ -d "venv" ]; then
    echo "Using existing virtual environment..."
    source venv/bin/activate
elif [ -d ".venv" ]; then
    echo "Using existing virtual environment..."
    source .venv/bin/activate
else
    echo "No virtual environment found — using system python (not recommended for production)"
    # We'll still try to run; pip packages should be installed globally or via venv
fi

# Set default environment variables if not already set
export SECUREFED_SDN_MODE="${SECUREFED_SDN_MODE:-mock}"
export SECUREFED_ENABLE_SIMULATION="${SECUREFED_ENABLE_SIMULATION:-false}"
export SECUREFED_ENABLE_TRAINING="${SECUREFED_ENABLE_TRAINING:-false}"

# Run the backend
echo "Starting uvicorn on 127.0.0.1:8000..."
echo "Access API at: http://127.0.0.1:8000"
echo "Access docs at:  http://127.0.0.1:8000/docs"
echo "Encryption status will report: unavailable (fail-closed by design)"
uvicorn app.main:app --host 127.0.0.1 --port 8000 &

BACKEND_PID=$!

# ==========================================
# FRONTEND STARTUP
# ==========================================

echo ""
echo "--- Starting Frontend (React + Vite) ---"

cd "$(dirname "$0")/web/frontend"

# Check if node_modules exists
if [ -d "node_modules" ]; then
    echo "node_modules found — starting vite dev server..."
    npm run dev -- --host & else
    echo "node_modules missing — installing..."
    npm install 2>&1 | tail -5
    echo "Starting vite dev server after install..."
    npm run dev -- --host &
else
    FRONTEND_PID=$!
fi

# Wait for both processes
echo ""
echo "========================================="
echo "SecureFed-IDS Running"
echo "========================================="
echo "Backend:  http://127.0.0.1:8000 (PID: $BACKEND_PID)"
echo "Frontend: http://localhost:5173 (or shown by vite) (PID: $FRONTEND_PID)"
echo ""
echo "Press Ctrl+C to stop both servers..."
echo ""

# Wait for interrupt
wait $BACKEND_PID $FRONTEND_PID 2>/dev/null

echo ""
echo "Servers stopped."