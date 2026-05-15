@echo off
TITLE SIEWS+ 5.0 - Windows Full Stack
COLOR 0A

echo.
echo ============================================================
echo   SIEWS+ 5.0 - Starting All Services (Windows)
echo ============================================================
echo.

:: 1. Start Docker services (inference + frontend) in background
echo [1/3] Starting Docker (Inference + Frontend)...
cd /d %~dp0
docker compose -f docker-compose.windows.yml up -d --build

:: 2. Wait for inference to be healthy
echo [2/3] Waiting for Inference service...
:wait_inference
timeout /t 3 /nobreak > nul
curl -s -o nul -w "%%{http_code}" http://localhost:8002/health | findstr "200" > nul
if errorlevel 1 (
    echo        Still loading...
    goto wait_inference
)
echo        Inference ready!

:: 3. Start Python Backend native (webcam + GPU)
echo [3/3] Starting Backend (native - GPU + Webcam)...
start "SIEWS+ Backend" cmd /k "cd /d %~dp0backend && python main.py"

:: Wait for backend to be ready
:wait_backend
timeout /t 2 /nobreak > nul
curl -s -o nul -w "%%{http_code}" http://localhost:8001/health | findstr "200" > nul
if errorlevel 1 (
    goto wait_backend
)

echo.
echo ============================================================
echo   ALL SERVICES RUNNING!
echo.
echo   Dashboard:    http://localhost:3000
echo   Backend API:  http://localhost:8001  (native GPU + webcam)
echo   Inference:    http://localhost:8002  (Docker)
echo.
echo   To stop: docker compose -f docker-compose.windows.yml down
echo            + close the Backend window
echo ============================================================
echo.
pause
