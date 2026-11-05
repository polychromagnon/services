#!/bin/bash
# VM suite of the services actions, in img2pdf's own Python (it carries Pillow and pikepdf).
# Run it as an ordinary user: bash tests/run.sh [MODULE ...]; bash tests/mutations.sh replays
# the mutations. Exit status: 0 when every check is OK.
HERE=$(cd "$(dirname "$0")" && pwd)
PY=$(sed -n '1s/^#! *//p' "${SUITE_PREFIX:-/opt/homebrew}/bin/img2pdf" 2>/dev/null)
[ -x "$PY" ] || { echo "img2pdf introuvable sous ${SUITE_PREFIX:-/opt/homebrew}/bin"; exit 2; }
exec "$PY" -I "$HERE/suite.py" "$@"
