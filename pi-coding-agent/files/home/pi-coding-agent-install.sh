#!/bin/sh
# Install @earendil-works/pi-coding-agent for the current user.
#
# Runs as a startup step (user 1000), every sandbox start. It is idempotent and
# never fails the sandbox: an optional CLI must not break `acq create`.
#
# INSTALL METHOD: the npm registry, not pi.dev/install.sh. The curl installer is
# mutable remote shell, needs pi.dev egress, and performs an interactive
# Node/npm preflight that makes no sense in a non-interactive startup step. This
# script runs the same underlying npm install directly.
#
# VERSION PIN: 1.4.0, the reviewed stable release. Bump deliberately, together
# with the README and tests, after reviewing the new release's npm metadata
# (engines.node and lifecycle scripts).
#
# PREFIX: $HOME/.local. `~/.local/bin` is on the guest's default PATH, so a
# plain `sh -c 'command -v pi'` resolves without profile files or PATH hacks.
# It is also unprivileged and survives for the lifetime of the sandbox.
#
# LIFECYCLE SCRIPTS: --ignore-scripts. pi itself has no build step; the flag
# removes an unnecessary install-time code-execution surface. It does not stop
# code that runs when `pi` is later invoked.
#
# CA BUNDLE: the sandbox proxy CA (PROXY_CA_CERT_B64) and the system trust store
# are folded into a per-user bundle. It is exported for the npm install below and
# referenced by the generated `pi` wrapper, so later user invocations trust the
# same inspection chain. The wrapper is static; only the bundle is rebuilt.
#
# PORTABILITY: the sandbox is Linux (msb/sbx). `base64 -d` and `dirname` are
# the Linux coreutils/busybox interfaces this script targets; macOS is not a
# supported host for the startup step.

set -eu

PI_VERSION="1.4.0"
PI_PACKAGE="@earendil-works/pi-coding-agent@${PI_VERSION}"
NPM_PREFIX="${HOME}/.local"
STATE_DIR="${HOME}/.local/state/pi-coding-agent"
CA_BUNDLE="${STATE_DIR}/ca-bundle.pem"
LOG="${STATE_DIR}/install.log"

# Fail soft even on an unexpected `set -e` trip. Any failure below is an
# optional-CLI failure, not a sandbox failure.
on_exit() {
  _rc=$?
  if [ "$_rc" -ne 0 ]; then
    echo "pi-coding-agent: install aborted (exit $_rc); sandbox continues without pi" >&2
  fi
  exit 0
}
trap on_exit EXIT

mkdir -p "$STATE_DIR"
: > "$LOG"

# --- Preflight ---------------------------------------------------------------
# Run this before any npm invocation: under `set -eu`, a command substitution
# that calls a missing npm would abort with an opaque shell error.
if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  echo "pi-coding-agent: node and/or npm not found on PATH; skipping pi install (installing Node is out of scope)" >&2
  exit 0
fi

# pi's declared engines.node is >=22.19.0. npm does not enforce engines by
# default, so check explicitly and fail clearly now instead of at first run.
if ! node -e 'const v = process.versions.node.split(".").map(Number); process.exit(v[0] > 22 || (v[0] === 22 && (v[1] > 19 || (v[1] === 19 && v[2] >= 0))) ? 0 : 1)' 2>/dev/null; then
  echo "pi-coding-agent: pi requires Node.js >=22.19.0, found $(node --version 2>/dev/null); skipping install" >&2
  exit 0
fi

# --- CA bundle ---------------------------------------------------------------
# Built every boot: the proxy CA can rotate. Decode to a temp file first so a
# malformed value cannot leave partial DER/PEM bytes in the bundle.
: > "$CA_BUNDLE"
if [ -n "${PROXY_CA_CERT_B64:-}" ]; then
  _ca_tmp="${STATE_DIR}/ca-bundle.tmp"
  if printf '%s' "$PROXY_CA_CERT_B64" | base64 -d > "$_ca_tmp" 2>/dev/null; then
    cat "$_ca_tmp" >> "$CA_BUNDLE"
  else
    echo "pi-coding-agent: PROXY_CA_CERT_B64 failed to base64-decode; proxy CA not added (see $LOG)" >&2
  fi
  rm -f "$_ca_tmp"
fi
for _store in /etc/ssl/certs/ca-certificates.crt /etc/pki/tls/certs/ca-bundle.crt /etc/ssl/cert.pem; do
  if [ -f "$_store" ]; then
    cat "$_store" >> "$CA_BUNDLE"
    break
  fi
done
if [ -s "$CA_BUNDLE" ]; then
  NODE_EXTRA_CA_CERTS="$CA_BUNDLE"
  export NODE_EXTRA_CA_CERTS
fi

# --- Install (idempotent) ----------------------------------------------------
# `command -v pi` alone is not enough: a half-finished npm install can leave a
# file that resolves but does not run. Only skip when the CLI actually executes.
_pi_existing="$(command -v pi 2>/dev/null || true)"
_pi_existing_version=""
if [ -n "$_pi_existing" ]; then
  _pi_existing_version="$(pi --version 2>/dev/null || true)"
fi
if [ -n "$_pi_existing" ] && [ -n "$_pi_existing_version" ]; then
  # A pre-existing pi from another installation is honored rather than shadowed.
  # It may be a different version; see README "Idempotency and pre-existing pi".
  echo "pi-coding-agent: pi already on PATH ($_pi_existing, version ${_pi_existing_version}); skipping npm install"
else
  if [ -n "$_pi_existing" ]; then
    echo "pi-coding-agent: pi at $_pi_existing does not run; attempting reinstall" >&2
  fi
  mkdir -p "$NPM_PREFIX"
  # `--prefix` on the command line, not only an env var: some images export
  # NPM_CONFIG_PREFIX, and the flag wins over every config source.
  # --no-audit/--no-fund avoid extra registry endpoints; --fetch-retries=0
  # because the next sandbox start retries anyway.
  if npm install -g --ignore-scripts --no-audit --no-fund --prefix "$NPM_PREFIX" \
      --fetch-timeout=30000 --fetch-retries=0 \
      "$PI_PACKAGE" >> "$LOG" 2>&1; then
    echo "pi-coding-agent: installed ${PI_PACKAGE}"
  else
    _rc=$?
    echo "pi-coding-agent: npm install exited ${_rc} (prefix=$NPM_PREFIX); pi unavailable this boot. See $LOG" >&2
    exit 0
  fi
fi

# --- Wrapper -----------------------------------------------------------------
# npm normally creates $NPM_PREFIX/bin/pi as a symlink (some platforms use a
# regular file). Move that entrypoint to the stable sibling `pi-real` and replace
# bin/pi with a wrapper that exports the CA bundle. The wrapper derives its
# directory from $0 at runtime instead of embedding a path in shell text: that
# avoids quoting bugs (and shell injection) when HOME contains spaces, quotes,
# `$`, backticks, or newlines.
_pi_bin="${NPM_PREFIX}/bin/pi"
_pi_real="${NPM_PREFIX}/bin/pi-real"
_wrap=0
if [ -L "$_pi_bin" ]; then
  _wrap=1
elif [ -f "$_pi_bin" ] && ! grep -q 'Generated by pi-coding-agent-install.sh' "$_pi_bin" 2>/dev/null; then
  _wrap=1
fi

if [ "$_wrap" = "1" ]; then
  rm -f "$_pi_real"
  mv "$_pi_bin" "$_pi_real"
  {
    printf '%s\n' \
      '#!/bin/sh' \
      '# Generated by pi-coding-agent-install.sh; do not edit.' \
      '_ca="${HOME}/.local/state/pi-coding-agent/ca-bundle.pem"' \
      'if [ -s "$_ca" ]; then NODE_EXTRA_CA_CERTS="$_ca"; export NODE_EXTRA_CA_CERTS; fi' \
      'case "$0" in' \
      '  */*) _pi_dir=${0%/*} ;;' \
      '  *) _pi_dir=$(dirname "$(command -v "$0")") ;;' \
      'esac' \
      'exec "$_pi_dir/pi-real" "$@"'
  } > "$_pi_bin"
  chmod 0755 "$_pi_bin"
fi

if command -v pi >/dev/null 2>&1 && pi --version >/dev/null 2>&1; then
  echo "pi-coding-agent: pi is installed and runs ($(command -v pi), version $(pi --version 2>/dev/null))"
else
  echo "pi-coding-agent: pi is not runnable after install; see $LOG" >&2
fi

exit 0
