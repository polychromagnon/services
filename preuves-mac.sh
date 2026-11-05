#!/bin/bash
# Proofs of the SPEC that only Michael's Mac can give. One line per proof or gesture, in the
# SPEC's order: OK, ÉCHEC, GESTE (something to do by hand, described step by step) or, off
# macOS, SAUTÉ. It works in throwaway folders and opens no dialog and no Terminal window.
# Run: bash ~/Developer/scripts/services/preuves-mac.sh, then send back what it prints.
HERE=$(cd "$(dirname "$0")" && pwd)
PY=$(sed -n '1s/^#! *//p' /opt/homebrew/bin/img2pdf 2>/dev/null)
[ -x "$PY" ] || { echo "img2pdf introuvable : lance d'abord maj"; exit 1; }
exec "$PY" -I "$HERE/tests/preuves_mac.py" "$HERE"
