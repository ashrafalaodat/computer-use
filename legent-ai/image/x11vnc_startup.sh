#!/bin/bash
set -euo pipefail

export DISPLAY=:${DISPLAY_NUM:-1}

if pgrep -fa "x11vnc -display ${DISPLAY}" >/dev/null; then
  echo "x11vnc already running"
  exit 0
fi

echo "Starting x11vnc on ${DISPLAY} port 5900"
x11vnc -display ${DISPLAY} -forever -shared -wait 50 -rfbport 5900 -nopw &
sleep 1
