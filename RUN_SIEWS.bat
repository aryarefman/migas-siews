@echo off
TITLE SIEWS+ 5.0 - Industrial Safety Startup
COLOR 0A

echo ============================================================
echo   SIEWS+ 5.0 - INTEGRATED SAFETY MONITORING SYSTEM
echo ============================================================
echo.

:: 1. Start Python Backend (FastAPI)
echo [1/2] Starting PYTHON BACKEND (Port 8001)...
start "SIEWS+ PYTHON BACKEND" cmd /k "cd /d %~dp0backend && python main.py"

:: 2. Wait for backend to initialize
timeout /t 8 /nobreak > nul

:: 3. Start Frontend (Next.js)
echo [2/2] Starting DASHBOARD FRONTEND (Port 3000)...
start "SIEWS+ DASHBOARD" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo ============================================================
echo ALL SERVICES STARTED!
echo Backend API:  http://localhost:8001
echo Dashboard:    http://localhost:3000
echo ============================================================
pause
