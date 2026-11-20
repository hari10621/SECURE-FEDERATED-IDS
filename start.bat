@echo off
title SecureFed-IDS Startup

echo ==========================================
echo SecureFed-IDS Startup
echo ==========================================
echo.

:: Check Python and start the Python-based startup script
python start.py %*

if %errorlevel% neq 0 (
    echo.
    Startup completed with warnings.
    echo.
)

echo.
echo ==========================================
echo SecureFed-IDS startup process complete.
echo ==========================================
echo.
echo Backend URL: http://127.0.0.1:8000
echo Frontend URL: http://localhost:5173 (if started)
echo.
echo Separate windows/processes should be running above.
echo.
pause