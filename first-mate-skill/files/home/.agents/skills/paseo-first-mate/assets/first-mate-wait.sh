#!/usr/bin/env bash
# First Mate wait loop. Runs first-mate-check.py (same directory) every INTERVAL minutes and
# returns as soon as it reports a change, so waiting costs no model tokens.
#
# Usage: first-mate-wait.sh INTERVAL_MIN MAX_MIN
#   exit 0  -> change found; the change report is printed (state already saved)
#   exit 3  -> nothing changed within MAX_MIN (print nothing)
# Run it as a BACKGROUND shell command so the harness notifies on completion.
# Use INTERVAL 5 while work is actively in flight, 15 when it is quiet.
set -uo pipefail
INTERVAL=${1:-15}
MAX=${2:-60}
HERE=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# State and watch files live in FIRST_MATE_DIR (default ./tmp); see first-mate-check.py.
deadline=$(( $(date +%s) + MAX * 60 ))
while :; do
  out=$(python3 "$HERE/first-mate-check.py" 2>&1)
  if [ -n "$out" ]; then
    printf '%s\n' "$out"
    exit 0
  fi
  [ "$(date +%s)" -ge "$deadline" ] && exit 3
  sleep $(( INTERVAL * 60 ))
done
