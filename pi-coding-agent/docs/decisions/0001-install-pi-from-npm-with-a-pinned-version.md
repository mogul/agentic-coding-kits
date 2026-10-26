# Decision: install pi from npm, pinned, into a per-user prefix

**Status:** accepted (2026-10-26)

## Context

`pi-coding-agent` is an acq **agent kit** (`hybrid/v1` mixin). It must install
the pi CLI into a sandbox at startup without compromising the sandbox if the
registry is unavailable. It must also coexist with a separate provider kit that
owns model-provider egress.

pi is published as `@earendil-works/pi-coding-agent`. Its npm metadata at the
time of authorship reports:

- current stable: `1.4.0`
- `engines.node`: `>=22.19.0`
- `bin.pi`: `dist/bundle/cli.js`

Upstream also publishes `https://pi.dev/install.sh`, a curl-pipe-to-shell
installer.

## Decision

1. **Use the npm registry, not `pi.dev/install.sh`.**
   - The curl installer is mutable remote shell. A kit is distributed by
     SHA-pinned git ref precisely so the code is reviewable and stable.
   - It needs `pi.dev` egress; this kit's allow-list is only
     `registry.npmjs.org`.
   - It performs an interactive Node/npm preflight that cannot work in a
     non-interactive startup step.
   - Its substantive action is the npm install below, which this kit runs
     directly.

2. **Pin `@earendil-works/pi-coding-agent@1.4.0`.** The pin lives in the install
   script, not in `spec.yaml`, so there is exactly one source of truth. Bumping
   it is a reviewed change: check `engines.node` and lifecycle scripts in the
   new release, rerun the tests, and update the README.

3. **Install with `--ignore-scripts`.** pi has no native build step. Removing
   lifecycle hooks removes an unnecessary install-time code-execution surface.
   This does not constrain code pi runs later; it is an install-time control
   only.

4. **Use the per-user prefix `$HOME/.local`.** The guest's default PATH includes
   `~/.local/bin`, so `pi` resolves from a bare `sh -c` with no profile files
   and no PATH manipulation. The install is unprivileged, needs no sudo, and
   survives for the sandbox lifetime. A bare `command -v pi` probe is therefore
   a meaningful check, not something the verifier papers over with a PATH
   injection.

5. **Run at startup, not in an install phase.** There is no native-module build
   that needs a toolchain and could fail during create. A registry outage should
   leave a usable sandbox without an optional CLI, not abort creation. This is
   why the step is fail-soft (`trap` plus explicit `exit 0` paths) and reports
   failures in a log.

6. **Fold the proxy CA into a wrapper.** The sandbox proxy CA arrives as
   `PROXY_CA_CERT_B64`. Node does not read the system store by default, and an
   export inside the startup process cannot reach a user's later `pi`
   invocation. The script:

   - decodes the proxy CA to a temporary file (so malformed base64 cannot leave
     partial bytes in the bundle),
   - appends the first available system CA bundle,
   - exports `NODE_EXTRA_CA_CERTS` for its own npm install,
   - replaces npm's `$HOME/.local/bin/pi` shim once with a wrapper that exports
     the same bundle and `exec`s the real entrypoint.

   The bundle is rebuilt every boot because the proxy CA can rotate. The wrapper
   is static and written once. If the platform materializes npm's bin entry as a
   regular file instead of a symlink, the script moves that file to `pi-real` and
   wraps it too.

7. **No `agent:` block.** acq treats `agent:` as a declaration that the kit
   provides a built-in agent token. pi is not one of acq's built-in agents; this
   kit is an opt-in `--kit` mixin. Declaring an agent block would invite a
   readiness gate that does not apply. Add one only if acq grows a pi-ready
   gate.

8. **No published ports.** pi is a terminal TUI. There is no server to keep
   alive and nothing to publish to the host.

## Considered alternatives

- **`pi.dev/install.sh`** — rejected for mutability, extra egress, and
  interactivity.
- **Install as root into `/usr/local/bin`** — rejected: needs privilege,
  and the default-PATH contract is stronger for a per-user tool.
- **Install into `$HOME/.npm-global`** — rejected: not on the default PATH, so
  every probe needs a PATH injection and a real regression becomes invisible.
- **`npm install -g` without `--prefix`** — rejected: site npm config can point
  at a root-owned or non-PATH prefix; the flag makes destination deterministic.
- **Pin `latest`** — rejected: behavior would drift with every sandbox boot.
- **Skip the CA wrapper** — rejected: in an inspecting environment, `pi` would
  fail TLS on every provider call even though the installer succeeded.
- **Copy the patterns Pi kit's script** — rejected: this repository's kit is
  independent; the logic above is written for this kit, and the provider-input
  renderer is the new work.

## Consequences

- Installing pi requires only `registry.npmjs.org`; provider egress stays the
  provider kit's responsibility.
- A bad registry day yields a sandbox without pi, with a clear log line, rather
  than a failed sandbox.
- `pi` is on the default PATH for the agent user, which makes
  `pi --list-models` the natural acceptance probe.
- The version pin is duplicated in documentation but authoritative in one
  script; tests and `scripts/verify` guard it.
- Wrapping the npm shim means npm's own `bin/pi` is not the raw entrypoint.
  Uninstalling or reinstalling pi via npm may require deleting the wrapper
  first; normal sandbox lifecycle recreates the prefix from scratch.
