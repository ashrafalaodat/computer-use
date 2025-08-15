#!/bin/bash
set -euo pipefail

# Serve noVNC on 0.0.0.0:6080, proxying to x11vnc on :5900 using cloned /opt/noVNC
NOVNC_DIR=${NOVNC_DIR:-/opt/noVNC}
NOVNC_PROXY="${NOVNC_DIR}/utils/novnc_proxy"

if pgrep -fa "novnc_proxy .* 6080" >/dev/null; then
  echo "noVNC already running on 6080"
  exit 0
fi

if [[ ! -x "${NOVNC_PROXY}" ]]; then
  echo "novnc_proxy not found at ${NOVNC_PROXY}" >&2
  exit 1
fi

echo "Starting noVNC on :6080 (serving ${NOVNC_DIR})"
"${NOVNC_PROXY}" --vnc 127.0.0.1:5900 --listen 0.0.0.0:6080 &
sleep 1
