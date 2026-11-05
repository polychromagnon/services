#!/bin/bash
# Replays the mutations of SPEC section 5, as an ordinary user: bash tests/mutations.sh [NUMBER ...]
HERE=$(cd "$(dirname "$0")" && pwd)
PY=$(sed -n '1s/^#! *//p' /opt/homebrew/bin/img2pdf 2>/dev/null)
[ -x "$PY" ] || { echo "img2pdf introuvable sous /opt/homebrew/bin"; exit 2; }
exec "$PY" -I "$HERE/mutations.py" "$@"
