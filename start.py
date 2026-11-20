#!/usr/bin/env python3
"""SecureFed-IDS Startup Script - starts backend and frontend"""

import os
import sys
import subprocess
import time
import signal

def clear():
    """Clear terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')

def print_header():
    print("=" * 60)
    print("SecureFed-IDS Startup Script")
    print("=" * 60)
    print()

def cprint(text, symbol="[OK]"):
    """Print with symbol prefix - handles encoding safely."""
    print(f"  {symbol} {text}")

def check_python():
    """Check Python availability and version."""
    print("Checking Python...")
    try:
        result = subprocess.run(
            [sys.executable, "--version"],
            capture_output=True, text=True, timeout=5
        )
        version_str = result.stdout.strip()
        cprint(f"Python found: {version_str}")
        
        # Extract major version
        major = int(version_str.split()[1].split(".")[0])
        if major >= 3:
            cprint("Python version compatible.", "[OK]")
            return True, major
        else:
            cprint(f"Python version too old: {version_str}. Requires Python 3.8+.", "[X]")
            return False, major
    except Exception as e:
        cprint(f"Python not found or error: {e}", "[X]")
        print("  Please install Python 3.8+ and add to PATH.")
        return False, 0

def check_node():
    """Check Node.js availability."""
    print("Checking Node.js...")
    try:
        result = subprocess.run(
            ["node", "--version"],
            capture_output=True, text=True, timeout=5
        )
        version_str = result.stdout.strip()
        cprint(f"Node.js found: {version_str}", "[OK]")
        return True
    except Exception:
        cprint("Node.js not found.", "[X]")
        print("  Frontend cannot run without Node.js.")
        print("  Install from https://nodejs.org/")
        return False

def check_project_dir():
    """Verify project directory structure."""
    print("Verifying project directory...")
    main_py = os.path.join("web", "backend", "app", "main.py")
    if os.path.exists(main_py):
        cprint("Project directory confirmed.", "[OK]")
        return True
    else:
        cprint("Project files missing.", "[X]")
        print(f"  Expected: {main_py}")
        print(f"  Run from: {os.getcwd()}")
        return False

def install_backend_reqs():
    """Install backend Python requirements."""
    print("Installing backend requirements...")
    backend_reqs = os.path.join("web", "backend", "requirements.txt")
    training_reqs = os.path.join("web", "backend", "requirements-training.txt")
    
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", backend_reqs],
            capture_output=True, timeout=120
        )
        cprint("Backend requirements installed.", "[OK]")
    except Exception as e:
        cprint(f"Backend install issue: {e}", "[X]")
    
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", training_reqs],
            capture_output=True, timeout=120
        )
        cprint("Training requirements installed.", "[OK]")
    except Exception as e:
        cprint(f"Training install issue: {e}", "[X]")

def start_backend():
    """Start the FastAPI backend as a background process."""
    print("Starting Backend...")
    backend_dir = os.path.join("web", "backend")
    env = os.environ.copy()
    env["SECUREFED_SDN_MODE"] = "mock"
    env["SECUREFED_ENABLE_SIMULATION"] = "false"
    env["SECUREFED_ENABLE_TRAINING"] = "false"
    env["SECUREFED_JOB_WORKERS"] = "1"
    env["SECUREFED_BASE_DIR"] = ".."
    env["SECUREFED_DATA_DIR"] = "web/var"
    
    # Activate venv if exists, otherwise use current Python
    venv_python = os.path.join(backend_dir, ".venv", "Scripts", "python.exe")
    python_exe = venv_python if os.path.exists(venv_python) else sys.executable
    
    cmd = [
        python_exe, "-m", "uvicorn", "app.main:app",
        "--host", "127.0.0.1", "--port", "8000"
    ]
    
    cprint("Starting uvicorn in background...", "[OK]")
    
    # Start process - detach it so it survives script exit
    process = subprocess.Popen(
        cmd,
        cwd=backend_dir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
    )
    
    cprint(f"Backend PID: {process.pid}", "[OK]")
    cprint("Backend URL: http://127.0.0.1:8000", "[OK]")
    
    # Don't wait for it - just return the process object
    return process

def check_backend_health(timeout=15):
    """Wait for backend to be ready by polling the status endpoint."""
    import http.client
    print("Waiting for backend to initialize...")
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            conn = http.client.HTTPConnection("127.0.0.1", 8000, timeout=3)
            conn.request("GET", "/api/v1/sdn/status")
            response = conn.getresponse()
            conn.close()
            if response.status == 200:
                cprint("Backend is ready.", "[OK]")
                return True
        except Exception:
            pass
        time.sleep(1)
    
    cprint("Backend did not become ready in time.", "[X]")
    return False

def start_frontend(node_available):
    """Start the React frontend."""
    print("Starting Frontend...")
    frontend_dir = os.path.join("web", "frontend")
    
    # Check/install node_modules
    node_modules = os.path.join(frontend_dir, "node_modules")
    if not os.path.exists(node_modules):
        cprint("Installing node_modules...")
        try:
            result = subprocess.run(
                ["npm", "install"],
                cwd=frontend_dir,
                capture_output=True, text=True, timeout=120
            )
            if result.stdout:
                cprint(f"npm output: {result.stdout[-80:]}", "[INFO]")
        except Exception as e:
            cprint(f"npm install issue: {e}", "[X]")
    
    if node_available:
        try:
            cprint("Starting npm dev server...", "[OK]")
            # Start npm dev server in background
            npm_process = subprocess.Popen(
                ["npm", "run", "dev", "--", "--host"],
                cwd=frontend_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            cprint(f"Frontend PID: {npm_process.pid}", "[OK]")
            cprint("Frontend URL: http://localhost:5173", "[OK]")
        except Exception as e:
            cprint(f"Frontend start issue: {e}", "[X]")
    else:
        cprint("Skipping frontend start - Node.js not available.", "[X]")

def main():
    print_header()
    
    # Checks
    python_ok, python_major = check_python()
    if not python_ok:
        input("Press Enter to exit...")
        sys.exit(1)
    
    node_available = check_node()
    
    if not check_project_dir():
        input("Press Enter to exit...")
        sys.exit(1)
    
    print()
    
    # Install requirements
    install_backend_reqs()
    print()
    
    # Start backend (as background process)
    backend_process = start_backend()
    print()
    
    # Wait for backend to be ready
    if not check_backend_health():
        cprint(" continuing anyway...", "[INFO]")
    
    print()
    
    # Start frontend
    start_frontend(node_available)
    print()
    
    print("=" * 60)
    print("SecureFed-IDS is starting...")
    print("=" * 60)
    print()
    print("Backend URL: http://127.0.0.1:8000")
    print("Frontend URL: http://localhost:5173 (if started)")
    print()
    print("Separate processes running for each component.")
    print("The backend and frontend will continue running in the background.")
    print("Press Ctrl+C to stop this terminal, the processes will continue.")
    print()
    
    # Keep the terminal open - wait for interrupt
    try:
        while True:
            time.sleep(5)
            # Check if backend process is still running
            if backend_process.poll() is not None:
                cprint("Warning: Backend process has ended.", "[WARN]")
                # Don't break - just warn and keep running
    except (KeyboardInterrupt, EOFError):
        pass
    
    # Cleanup: terminate backend process when user exits
    try:
        backend_process.terminate()
        backend_process.wait(timeout=5)
    except:
        pass
    
    sys.exit(0)

if __name__ == "__main__":
    main()