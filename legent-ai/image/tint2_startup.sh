#!/bin/bash
set -euo pipefail

export DISPLAY=:${DISPLAY_NUM:-1}

if pgrep -fa "tint2( |$)" >/dev/null; then
  echo "tint2 already running"
  exit 0
fi

echo "Starting tint2 panel"
# Try default config; continue even if it fails
(tint2 -c /home/computeruse/.config/tint2/tint2rc || tint2) &
sleep 1
