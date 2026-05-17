#!/bin/bash
# SIEWS+ launcher — auto-detects OS and applies correct Docker Compose config

OS="$(uname -s)"

case "$OS" in
  Linux*)
    # Check which video devices actually exist and build override on-the-fly
    DEVICES=""
    for dev in /dev/video0 /dev/video1 /dev/video2; do
      [ -e "$dev" ] && DEVICES="$DEVICES      - $dev:$dev\n"
    done

    if [ -n "$DEVICES" ]; then
      echo "[SIEWS] Linux detected — mounting video devices:"
      for dev in /dev/video0 /dev/video1 /dev/video2; do
        [ -e "$dev" ] && echo "  $dev"
      done
      docker compose -f docker-compose.yml -f docker-compose.linux.yml "$@"
    else
      echo "[SIEWS] Linux detected — no /dev/video* found, running without camera device mount"
      echo "        Set CAMERA_SOURCE to an RTSP URL in backend/.env for IP camera"
      docker compose -f docker-compose.yml "$@"
    fi
    ;;
  Darwin*)
    echo "[SIEWS] macOS detected — Docker Desktop does not support USB device passthrough"
    echo "        Use RTSP IP camera: set CAMERA_SOURCE=rtsp://... in backend/.env"
    docker compose -f docker-compose.yml "$@"
    ;;
  *)
    echo "[SIEWS] Unknown OS: $OS — running base config"
    docker compose -f docker-compose.yml "$@"
    ;;
esac
