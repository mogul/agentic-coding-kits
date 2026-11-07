#!/bin/sh
# paseo-plugins-install.sh: install the author's Paseo plugins into the sandbox's
# Paseo daemon. Started in the background by the personal kit's startup command.
#
# Needs the separate `paseo` kit (or any image with `paseo` on PATH and a daemon).
# It waits for the daemon, turns the global plugin switch on, then installs each
# plugin listed at the bottom that is not already installed. It never fails the
# sandbox: every problem is logged to $STATE_DIR/paseo-plugins.log and it exits 0.
#
# Sources are pinned on purpose. install_plugin refuses anything but a git source
# with a full 40-hex commit or an npm source with an exact version. A plain
# registry id such as xzthemeofsss/quote-notes would install whatever the registry
# points at on the day the sandbox is created.

set -u

PASEO_HOME_DIR="${PASEO_HOME:-$HOME/.paseo}"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/paseo"
LOG="$STATE_DIR/paseo-plugins.log"
WAIT_SECONDS="${PASEO_PLUGINS_WAIT_SECONDS:-600}"
ATTEMPTS="${PASEO_PLUGINS_ATTEMPTS:-3}"
mkdir -p "$STATE_DIR" 2>/dev/null || true

log() { printf '%s paseo-plugins: %s\n' "$(date -u +%FT%TZ)" "$*" >>"$LOG"; }

PATH="$HOME/.npm-global/bin:$(npm prefix -g 2>/dev/null)/bin:$PATH"
export PATH

# One installer at a time: a second run (manual or a repeated startup) exits.
RUN_LOCK_DIR="$STATE_DIR/paseo-plugins.run.lock"
CONFIG_LOCK_DIR="$PASEO_HOME_DIR/.config-json.lock"
have_run_lock=""
have_config_lock=""
cleanup() {
  [ -n "$have_config_lock" ] && rmdir "$CONFIG_LOCK_DIR" 2>/dev/null
  have_config_lock=""
  [ -n "$have_run_lock" ] && rmdir "$RUN_LOCK_DIR" 2>/dev/null
  have_run_lock=""
}
trap cleanup EXIT
trap 'cleanup; exit 1' HUP INT TERM

if mkdir "$RUN_LOCK_DIR" 2>/dev/null; then
  have_run_lock=yes
else
  log "another installer is running ($RUN_LOCK_DIR exists); this run did nothing"
  exit 0
fi

paseo_ready() { paseo plugin ls --home "$PASEO_HOME_DIR" --json >/dev/null 2>&1; }

deadline=$(( $(date +%s) + WAIT_SECONDS ))
until command -v paseo >/dev/null 2>&1 && paseo_ready; do
  if [ "$(date +%s)" -ge "$deadline" ]; then
    log "daemon not reachable after ${WAIT_SECONDS}s (is the paseo kit applied?); no plugins installed"
    exit 0
  fi
  sleep 3
done

plugins_enabled() {
  paseo daemon config get --home "$PASEO_HOME_DIR" pluginsEnabled --json 2>/dev/null |
    grep -q '"value": *true'
}

# Same coarse lock directory the paseo kit takes around config.json writes.
enable_plugins() {
  lock_deadline=$(( $(date +%s) + 30 ))
  until mkdir "$CONFIG_LOCK_DIR" 2>/dev/null; do
    if [ "$(date +%s)" -ge "$lock_deadline" ]; then
      log "could not lock config.json; plugins left disabled"
      return 1
    fi
    sleep 1
  done
  have_config_lock=yes
  paseo daemon config set --home "$PASEO_HOME_DIR" pluginsEnabled true >>"$LOG" 2>&1
  status=$?
  rmdir "$CONFIG_LOCK_DIR" 2>/dev/null
  have_config_lock=""
  [ "$status" -eq 0 ] || { log "could not set pluginsEnabled"; return 1; }
  paseo reload --home "$PASEO_HOME_DIR" --json >>"$LOG" 2>&1
  plugins_enabled
}

if ! plugins_enabled; then
  enable_plugins || { log "plugins are not enabled; no plugins installed"; exit 0; }
  log "enabled plugins on the daemon"
fi

plugin_listed() {
  paseo plugin ls --home "$PASEO_HOME_DIR" --json 2>/dev/null | grep -qF "\"id\": \"$1\""
}

plugin_status() {
  paseo plugin ls "$1" --home "$PASEO_HOME_DIR" --json 2>/dev/null |
    sed -n 's/.*"status": *"\([a-z]*\)".*/\1/p' | head -n 1
}

# install_plugin ID SOURCE PIN
#   git:owner/repo  PIN is a full 40-hex commit
#   npm:package     PIN is an exact x.y.z version
# Any other shape is refused, so an unpinned install cannot be added by accident.
install_plugin() {
  id="$1"; source="$2"; pin="${3:-}"
  case "$source" in
    git:*)
      case "$pin" in
        *[!0-9a-f]*|"") log "$id REFUSED: git source needs a full lowercase commit SHA, got '$pin'"; return 0 ;;
      esac
      [ "${#pin}" -eq 40 ] || { log "$id REFUSED: commit pin must be 40 hex characters, got '$pin'"; return 0; }
      target="$source"
      ;;
    npm:*)
      case "$pin" in
        [0-9]*.[0-9]*.[0-9]*) : ;;
        *) log "$id REFUSED: npm source needs an exact x.y.z version, got '$pin'"; return 0 ;;
      esac
      case "$pin" in
        *[!0-9.]*|*..*|.*|*.) log "$id REFUSED: npm version must be digits and dots only, got '$pin'"; return 0 ;;
      esac
      target="$source@$pin"
      ;;
    *) log "$id REFUSED: source must be git:owner/repo or npm:package, got '$source'"; return 0 ;;
  esac

  if plugin_listed "$id"; then
    log "$id already installed (status: $(plugin_status "$id")); skipped"
    return 0
  fi

  n=1
  while [ "$n" -le "$ATTEMPTS" ]; do
    # A daemon restart (the paseo kit does one when it pins the worktree root) can
    # land mid-install; wait for it to answer again before each attempt.
    until paseo_ready; do
      [ "$(date +%s)" -ge "$deadline" ] && break
      sleep 3
    done
    case "$source" in
      git:*) paseo plugin install --home "$PASEO_HOME_DIR" --id "$id" --ref "$pin" "$target" >>"$LOG" 2>&1 ;;
      *)     paseo plugin install --home "$PASEO_HOME_DIR" --id "$id" "$target" >>"$LOG" 2>&1 ;;
    esac
    install_status=$?
    if plugin_listed "$id"; then
      log "$id installed from $target${pin:+ ($pin)} on attempt $n (exit $install_status); status: $(plugin_status "$id")"
      return 0
    fi
    log "$id attempt $n of $ATTEMPTS failed (exit $install_status); see lines above"
    n=$((n + 1))
    sleep 5
  done
  log "$id FAILED to install from $target after $ATTEMPTS attempts"
}

# Codex Style Annotations v0.2.2, the commit the Paseo registry lists for
# xzthemeofsss/quote-notes (https://paseo.sh/plugins/xzthemeofsss/quote-notes).
install_plugin quote-notes git:xzthemeofsss/paseo-plugins 5ce92527c99a328b28775c7d745f324f2cc84309

exit 0
