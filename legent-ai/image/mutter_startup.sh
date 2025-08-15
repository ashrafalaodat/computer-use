#!/bin/bash
set -euo pipefail

export DISPLAY=:${DISPLAY_NUM:-1}

if pgrep -fa "mutter --replace" >/dev/null; then
  echo "mutter already running"
  exit 0
fi

echo "Starting mutter window manager"
# Use X11 mode explicitly
mutter --replace --sm-disable &
sleep 1
