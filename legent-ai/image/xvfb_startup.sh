#!/bin/bash
set -euo pipefail

DISPLAY_NUM=${DISPLAY_NUM:-1}
WIDTH=${WIDTH:-1280}
HEIGHT=${HEIGHT:-800}

if pgrep -fa "Xvfb :${DISPLAY_NUM}\b" >/dev/null; then
  echo "Xvfb already running on :${DISPLAY_NUM}"
  exit 0
fi

echo "Starting Xvfb on :${DISPLAY_NUM} at ${WIDTH}x${HEIGHT}"
Xvfb :${DISPLAY_NUM} -ac -screen 0 ${WIDTH}x${HEIGHT}x24 -dpi 96 -nolisten tcp -nolisten unix &
sleep 1
