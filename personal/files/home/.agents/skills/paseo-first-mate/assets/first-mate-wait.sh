#!/usr/bin/env bash
# First Mate wait loop: one loop per FIRST_MATE_DIR, owned by one agent.
# Runs first-mate-check.py (same directory) every INTERVAL minutes and returns as soon
# as it reports a change, so waiting costs no model tokens.
#
# Usage:
#   first-mate-wait.sh [INTERVAL_MIN [MAX_MIN]]    start a loop (refuses if one is running)
#                                                  defaults: 15 and 480 (8 hours)
#   first-mate-wait.sh status                      none | mine | other, with owner, pid, start,
#                                                  and the age of the last completed detector run
#   first-mate-wait.sh stop [--force]              stop your loop (--force: another owner's)
#   first-mate-wait.sh take-over INTERVAL MAX      stop any running loop, then start yours
#
# The loop exits on purpose when it finds a change, so restart it after every notification:
# run `status` first in every turn, and start a new loop in that same turn if it says none.
# `status` also warns when the last detector run is older than twice the interval (a stuck
# loop or a failing detector looks quiet otherwise). Pair the loop with an hourly heartbeat
# that runs `status` and restarts the loop (see the skill).
#
# Exit codes of a start:
#   0  change found; the report is printed, then the detector's save is committed
#   3  nothing changed within MAX_MIN (prints one line saying the loop ended at its cap)
#   4  a loop is already running and you own it; nothing started
#   5  a loop is running and another owner holds it; nothing started
#   2  usage or environment error (for example, flock is missing)
# Run a start as a BACKGROUND shell command so the harness notifies on completion.
# Use INTERVAL 5 while work is actively in flight, 15 when it is quiet.
#
# The report is printed BEFORE the detector's two-phase save is committed (--peek, print,
# --commit), so a loop killed in between reports the same change again instead of losing it.
# FIRST_MATE_DIR may be relative; it is resolved to an absolute path. When that directory does
# not exist and this script sits in a directory with that path tail (the skill copies the
# scripts into tmp/), that directory is used, so running from inside tmp/ never makes tmp/tmp.
# FIRST_MATE_PYTHON picks the interpreter (default python3).
#
# Ownership is the PASEO_AGENT_ID of the caller (override with FIRST_MATE_OWNER). The
# lock is an flock(2) on FIRST_MATE_DIR/.wait.lock, so it frees itself when the loop
# dies, including by SIGKILL; there is no pidfile to go stale. Needs flock: util-linux on
# Linux, or `brew install flock` on macOS.
set -uo pipefail

HERE=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PYTHON=${FIRST_MATE_PYTHON:-python3}
resolve_dir() {
  local v=${1#./}
  v=${v%/}
  case $1 in
    /*) printf '%s\n' "$1"; return ;;
  esac
  if [ ! -d "$PWD/$v" ] && [ "${HERE%/"$v"}" != "$HERE" ] && [ "$(dirname "$HERE")" != / ]; then
    printf '%s\n' "$HERE"
  else
    printf '%s\n' "$PWD/$v"
  fi
}
DIR=$(resolve_dir "${FIRST_MATE_DIR:-tmp}")
mkdir -p -- "$DIR" || exit 2
DIR=$(CDPATH='' cd -- "$DIR" && pwd)
export FIRST_MATE_DIR=$DIR
LOCK=$DIR/.wait.lock
INFO=$DIR/.wait.owner
LASTRUN=$DIR/.first-mate-lastrun
SECS_PER_MIN=${FIRST_MATE_MINUTE_SECS:-60}
ME=${FIRST_MATE_OWNER:-${PASEO_AGENT_ID:-local}}
export FIRST_MATE_OWNER=$ME

command -v flock >/dev/null 2>&1 || { echo "first-mate-wait.sh needs flock (util-linux)" >&2; exit 2; }

usage() { sed -n '2,/^set -uo/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//' >&2; }
info_get() { sed -n "s/^$1=//p" "$INFO" 2>/dev/null | head -n 1; }

# True when some process holds the lock. The subshell takes and releases it.
is_running() { if ( exec 8>"$LOCK"; flock -n 8 ); then return 1; else return 0; fi; }

# True when the owner file names a live first-mate-wait.sh process. A loop killed with
# SIGKILL leaves its owner file behind, so the file alone is not proof.
info_valid() {
  local p
  p=$(info_get pid)
  [ -n "$p" ] && ps -p "$p" -o args= 2>/dev/null | grep -q 'first-mate-wait.sh'
}

# The loop takes the lock before it writes the owner file. When the lock is held,
# wait (up to about 5s) for a valid owner file so a caller never acts on a half-started
# loop or on a stale file. Returns 1 if the loop died meanwhile, or never published one.
await_info() {
  local _
  for _ in $(seq 1 50); do
    info_valid && return 0
    is_running || return 1
    sleep 0.1
  done
  return 1
}

# Seconds since the detector last completed a run, or empty when it never has.
lastrun_age() {
  local t
  t=$(head -n 1 "$LASTRUN" 2>/dev/null)
  case $t in ''|*[!0-9]*) return 0 ;; esac
  t=$(( $(date +%s) - t ))
  [ "$t" -lt 0 ] && t=0
  echo "$t"
}

human_age() {
  local s=$1
  if [ "$s" -lt 120 ]; then echo "${s}s"
  elif [ "$s" -lt 7200 ]; then echo "$(( s / 60 ))m"
  else echo "$(( s / 3600 ))h$(( s % 3600 / 60 ))m"
  fi
}

# The first word of the first line is none | mine | other; callers parse that. The last
# detector run follows, with a WARNING line when it is older than twice the interval.
describe() {
  local owner kind age interval line since
  age=$(lastrun_age)
  if ! is_running; then
    echo "none"
    [ -n "$age" ] && echo "last-run=$(human_age "$age") ago (no loop is running: start one)"
    return 0
  fi
  await_info
  if ! is_running; then
    echo "none"
    return 0
  fi
  owner=$(info_get owner)
  interval=$(info_get interval)
  if [ "$owner" = "$ME" ]; then kind=mine; else kind=other; fi
  line="$kind owner=${owner:-unknown} pid=$(info_get pid) started=$(info_get started)"
  line="$line interval=${interval}m max=$(info_get max)m"
  if [ -z "$age" ]; then
    echo "$line last-run=never"
  else
    echo "$line last-run=$(human_age "$age") ago"
    # A loop younger than two intervals has not had time to refresh a stale file yet.
    since=$(info_get epoch)
    since=$(( $(date +%s) - ${since:-0} ))
    if [ -n "$interval" ] && [ "$age" -gt $(( interval * 2 * SECS_PER_MIN )) ] \
      && [ "$since" -gt $(( interval * 2 * SECS_PER_MIN )) ]; then
      echo "WARNING: the last detector run was $(human_age "$age") ago, more than twice the ${interval}m interval;" \
        "the loop may be stuck or the detector failing. Check with first-mate-check.py --show."
    fi
  fi
}

cmd_stop() {
  local force=0 owner pid
  [ "${1:-}" = "--force" ] && force=1
  if ! is_running; then echo "none running"; return 0; fi
  await_info
  is_running || { echo "none running"; return 0; }
  owner=$(info_get owner); pid=$(info_get pid)
  if [ "$owner" != "$ME" ] && [ "$force" -eq 0 ]; then
    echo "refusing: the loop is owned by ${owner:-unknown}; use 'stop --force' or 'take-over'" >&2
    return 5
  fi
  # ps works on Linux and macOS; /proc exists only on Linux.
  if [ -z "$pid" ] || ! ps -p "$pid" -o args= 2>/dev/null | grep -q 'first-mate-wait.sh'; then
    echo "cannot verify that pid '${pid:-none}' is the loop; not killing anything" >&2
    return 2
  fi
  kill "$pid"
  for _ in $(seq 1 50); do
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
  local interval=${1:-15} max=${2:-480} owner out deadline got rc txn _
  case "$interval$max" in *[!0-9]*|'') usage; exit 2 ;; esac
  exec 9>"$LOCK"
  # status and stop probe the lock by briefly taking it, so a failed attempt is not
  # proof that a loop is running. Retry until the owner file names a live loop (then
  # it is real), the lock is free (we win it), or about 5s pass.
  got=0
  for _ in $(seq 1 50); do
    if flock -n 9; then got=1; break; fi
    info_valid && break
    sleep 0.1
  done
  if [ "$got" -eq 0 ]; then
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
  printf 'owner=%s\npid=%s\nstarted=%s\ninterval=%s\nmax=%s\nepoch=%s\n' \
    "$ME" "$$" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$interval" "$max" "$(date +%s)" > "$INFO.new" \
    && mv -f -- "$INFO.new" "$INFO"
  OUTF=$(mktemp "$DIR/.wait.out.XXXXXX") || exit 2
  trap cleanup EXIT
  trap 'exit 143' TERM INT
  deadline=$(( $(date +%s) + max * SECS_PER_MIN ))
  while :; do
    # Children must not inherit the lock fd, or a killed loop would keep the lock.
    # The detector runs in the background and is waited on, so a stop (SIGTERM) is
    # handled at once instead of after the detector's network calls finish.
    # --peek prints and stages the save without consuming anything; the commit below
    # runs only after the report is printed. The txn ties the commit to this peek.
    txn="$$.$(date +%s).$RANDOM"
    FIRST_MATE_TXN=$txn "$PYTHON" "$HERE/first-mate-check.py" --peek >"$OUTF" 2>&1 9>&- &
    DET_PID=$!
    wait "$DET_PID"
    rc=$?
    DET_PID=
    out=$(cat -- "$OUTF")
    if [ "$rc" -ne 0 ] && [ -z "$out" ]; then out="first-mate-check.py exited with status $rc and printed nothing"; fi
    if [ -n "$out" ]; then
      printf '%s\n' "$out"
      if ! FIRST_MATE_TXN=$txn "$PYTHON" "$HERE/first-mate-check.py" --commit 9>&- >/dev/null 2>&1; then
        echo "WARNING: could not save the detector state; the same change will be reported again." >&2
      fi
      exit 0
    fi
    if [ "$(date +%s)" -ge "$deadline" ]; then
      echo "first-mate-wait: loop ended at its ${max}-minute cap with no change; start a new one (status first)."
      exit 3
    fi
    sleep $(( interval * SECS_PER_MIN )) 9>&- &
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
