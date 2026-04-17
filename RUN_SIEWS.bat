@echo off
TITLE SIEWS+ 5.0 - Industrial Safety Startup
COLOR 0A

echo ============================================================
echo   SIEWS+ 5.0 - INTEGRATED SAFETY MONITORING SYSTEM
echo ============================================================
echo.

:: 1. Start AI Servant (Python)
echo [1/3] Starting AI DETECTOR (Python Port 8003)...
start "SIEWS+ AI DETECTOR" cmd /k "cd /d %~dp0backend && python ai_service.py"

:: 2. Wait a bit for AI to load models
timeout /t 5 /nobreak > nul

:: 3. Start Master Backend (Golang)
echo [2/3] Starting MASTER BACKEND (Golang Port 8001)...
start "SIEWS+ MASTER BACKEND" cmd /k "cd /d %~dp0backend\golang_polygon && go run main.go"

:: 4. Start Frontend (Next.js)
echo [3/3] Starting DASHBOARD FRONTEND (Next.js Port 3000)...
start "SIEWS+ DASHBOARD" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo ============================================================
echo ALL SERVICES STARTED!
echo Monitoring: http://localhost:3000
echo ============================================================
pause
