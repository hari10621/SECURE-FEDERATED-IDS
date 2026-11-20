@echo off
title SecureFed-IDS Startup

echo ==========================================
echo SecureFed-IDS Startup Script
echo ==========================================
echo.

:: Check Python
where python >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=*" %A in ('python --version') do set PY_VER=%A
    echo ✅ Python found: %PY_VER%
) else (
    echo ❌ Python not found in PATH.
    echo Please install Python 3.8+ and add to PATH.
    pause
    exit /b
)

:: Check Node.js
where node >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=*" %A in ('node --version') do set NODE_VER=%A
    echo ✅ Node.js found: %NODE_VER%
) else (
    echo ⚠️ Node.js not found.
    echo Frontend cannot run without Node.js.
    echo Install from https://nodejs.org/
)

:: Verify project directory
if exist web\backend\app\main.py (
    echo ✅ Project directory confirmed.
) else (
    echo ❌ Project files missing.
    echo Expected: web\backend\app\main.py
    echo Run from: C:\Users\HARIS\Desktop\SecureFed-IDS
    pause
    exit /b
)

echo.
echo --- Checks complete ---
echo.

:: Start Backend
echo --- Starting Backend ---
cd /d web\backend
set SECUREFED_SDN_MODE=mock
set SECUREFED_ENABLE_SIMULATION=false
set SECUREFED_ENABLE_TRAINING=false

:: Try venv
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
    echo Using virtual environment...
)

:: Start uvicorn in separate window
start "SecureFed-Backend" cmd /c "uvicorn app.main:app --host 127.0.0.1 --port 8000"

:: Brief pause to let backend initialize
timeout /t 3 >nul

echo.
echo --- Starting Frontend ---
cd /d ..\frontend

:: Install deps if needed
if not exist node_modules (
    echo Installing node_modules...
    npm install 2>nul
)

:: Start frontend
start "SecureFed-Frontend" cmd /c "npm run dev -- --host"

echo.
echo ==========================================
echo SecureFed-IDS is starting...
echo ==========================================
echo.
echo Backend URL: http://127.0.0.1:8000
echo Frontend URL: http://localhost:5173 (or as displayed)
echo.
echo Separate windows will open for each component.
echo.
:: Keep this window open - pause at the end
pause