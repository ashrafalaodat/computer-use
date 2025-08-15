#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)

export DISPLAY_NUM=${DISPLAY_NUM:-1}
export DISPLAY=:${DISPLAY_NUM}
export WIDTH=${WIDTH:-1280}
export HEIGHT=${HEIGHT:-800}

"${SCRIPT_DIR}/xvfb_startup.sh"
"${SCRIPT_DIR}/tint2_startup.sh"
"${SCRIPT_DIR}/mutter_startup.sh"
"${SCRIPT_DIR}/x11vnc_startup.sh"

echo "GUI stack started on ${DISPLAY} at ${WIDTH}x${HEIGHT}"
