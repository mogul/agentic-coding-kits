#!/usr/bin/env bash
# First Mate wait loop: one loop per FIRST_MATE_DIR, owned by one agent.
# Runs first-mate-check.py (same directory) every INTERVAL minutes and returns as soon
# as it reports a change, so waiting costs no model tokens.
#
# Usage:
#   first-mate-wait.sh INTERVAL_MIN MAX_MIN        start a loop (refuses if one is running)
#   first-mate-wait.sh status                      none | mine | other, with owner, pid, start
#   first-mate-wait.sh stop [--force]              stop your loop (--force: another owner's)
#   first-mate-wait.sh take-over INTERVAL MAX      stop any running loop, then start yours
#
# Exit codes of a start:
#   0  change found; the report is printed (state already saved)
#   3  nothing changed within MAX_MIN (prints nothing)
#   4  a loop is already running and you own it; nothing started
#   5  a loop is running and another owner holds it; nothing started
#   2  usage or environment error (for example, flock is missing)
# Run a start as a BACKGROUND shell command so the harness notifies on completion.
# Use INTERVAL 5 while work is actively in flight, 15 when it is quiet.
#
# Ownership is the PASEO_AGENT_ID of the caller (override with FIRST_MATE_OWNER). The
# lock is an flock(2) on FIRST_MATE_DIR/.wait.lock, so it frees itself when the loop
# dies, including by SIGKILL; there is no pidfile to go stale. Needs flock (util-linux).
set -uo pipefail

HERE=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
DIR=${FIRST_MATE_DIR:-tmp}
mkdir -p -- "$DIR" || exit 2
DIR=$(CDPATH='' cd -- "$DIR" && pwd)
export FIRST_MATE_DIR=$DIR
LOCK=$DIR/.wait.lock
INFO=$DIR/.wait.owner
ME=${FIRST_MATE_OWNER:-${PASEO_AGENT_ID:-local}}
export FIRST_MATE_OWNER=$ME

command -v flock >/dev/null 2>&1 || { echo "first-mate-wait.sh needs flock (util-linux)" >&2; exit 2; }

usage() { sed -n '2,/^set -uo/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//' >&2; }
info_get() { sed -n "s/^$1=//p" "$INFO" 2>/dev/null | head -n 1; }

# True when some process holds the lock. The subshell takes and releases it.
is_running() { if ( exec 8>"$LOCK"; flock -n 8 ); then return 1; else return 0; fi; }

describe() {
  if ! is_running; then echo "none"; return 0; fi
  local owner kind
  owner=$(info_get owner)
  if [ "$owner" = "$ME" ]; then kind=mine; else kind=other; fi
  echo "$kind owner=${owner:-unknown} pid=$(info_get pid) started=$(info_get started)" \
    "interval=$(info_get interval)m max=$(info_get max)m"
}

cmd_stop() {
  local force=0 owner pid i
  [ "${1:-}" = "--force" ] && force=1
  if ! is_running; then echo "none running"; return 0; fi
  owner=$(info_get owner); pid=$(info_get pid)
  if [ "$owner" != "$ME" ] && [ "$force" -eq 0 ]; then
    echo "refusing: the loop is owned by ${owner:-unknown}; use 'stop --force' or 'take-over'" >&2
    return 5
  fi
  if [ -z "$pid" ] || ! tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null | grep -q 'first-mate-wait.sh'; then
    echo "cannot verify that pid '${pid:-none}' is the loop; not killing anything" >&2
    return 2
  fi
  kill "$pid"
  for i in $(seq 1 50); do
    if ! is_running; then echo "stopped (was owned by ${owner:-unknown})"; return 0; fi
    sleep 0.1
  done
  echo "the loop did not stop; investigate pid $pid" >&2
  return 2
}

SLEEP_PID=
DET_PID=
OUTF=
cleanup() {
  [ -n "$SLEEP_PID" ] && kill "$SLEEP_PID" 2>/dev/null
  [ -n "$DET_PID" ] && kill "$DET_PID" 2>/dev/null
  [ -n "$OUTF" ] && rm -f -- "$OUTF"
  [ "$(info_get pid)" = "$$" ] && rm -f -- "$INFO"
}

cmd_start() {
  local interval=${1:-15} max=${2:-60} owner out deadline
  case "$interval$max" in *[!0-9]*|'') usage; exit 2 ;; esac
  exec 9>"$LOCK"
  if ! flock -n 9; then
    owner=$(info_get owner)
    if [ "$owner" = "$ME" ]; then
      echo "a loop is already running and you own it ($(describe)); not starting another"
      exit 4
    fi
    echo "refusing: a loop is running and ${owner:-another owner} holds it ($(describe))." \
      "Use 'take-over' only if the user agreed that you are the coordinator." >&2
    exit 5
  fi
  # Write then rename, so status and stop never read a half-written owner file.
  printf 'owner=%s\npid=%s\nstarted=%s\ninterval=%s\nmax=%s\n' \
    "$ME" "$$" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$interval" "$max" > "$INFO.new" \
    && mv -f -- "$INFO.new" "$INFO"
  OUTF=$(mktemp "$DIR/.wait.out.XXXXXX") || exit 2
  trap cleanup EXIT
  trap 'exit 143' TERM INT
  deadline=$(( $(date +%s) + max * 60 ))
  while :; do
    # Children must not inherit the lock fd, or a killed loop would keep the lock.
    # The detector runs in the background and is waited on, so a stop (SIGTERM) is
    # handled at once instead of after the detector's network calls finish.
    python3 "$HERE/first-mate-check.py" >"$OUTF" 2>&1 9>&- &
    DET_PID=$!
    wait "$DET_PID"
    DET_PID=
    out=$(cat -- "$OUTF")
    if [ -n "$out" ]; then
      printf '%s\n' "$out"
      exit 0
    fi
    [ "$(date +%s)" -ge "$deadline" ] && exit 3
    sleep $(( interval * 60 )) 9>&- &
    SLEEP_PID=$!
    wait "$SLEEP_PID"
  done
}

case "${1:-}" in
  status) describe ;;
  stop) shift; cmd_stop "$@" ;;
  take-over) shift; cmd_stop --force || exit $?; cmd_start "$@" ;;
  -h|--help) usage ;;
  ''|[0-9]*) cmd_start "$@" ;;
  *) usage; exit 2 ;;
esac
