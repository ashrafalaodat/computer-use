#!/bin/bash
set -euo pipefail

# Start Xvfb + panel + WM + VNC + noVNC
dirname=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
export DISPLAY=:${DISPLAY_NUM:-1}
"${dirname}/start_all.sh"
"${dirname}/novnc_startup.sh"

# Ensure screenshots directory exists and is writable (handles named volume mount)
SCREEN_DIR="/app/legent-ai/static/screenshots"
mkdir -p "${SCREEN_DIR}"
chown -R "$(id -u)":"$(id -g)" "${SCREEN_DIR}" || true

# Start backend (watch code and .env for changes)
cd /app/legent-ai
exec python -m uvicorn main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --reload \
  --reload-dir /app \
  --reload-include .env
