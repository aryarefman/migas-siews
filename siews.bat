@echo off
:: SIEWS+ launcher for Windows
:: Docker Desktop on Windows does NOT support USB webcam device passthrough.
:: Use an IP camera with RTSP URL instead, or use WSL2 with usbipd-win.

echo [SIEWS] Windows detected
echo        Docker Desktop does not support USB webcam passthrough natively.
echo        Options:
echo          1. Use IP camera: set CAMERA_SOURCE=rtsp://... in backend\.env
echo          2. Use usbipd-win to forward USB webcam to WSL2, then run siews.sh from WSL2
echo.

docker compose -f docker-compose.yml %*
