# Decision: install Paseo plugins at sandbox startup, pinned, from the personal kit

**Status:** accepted (2026-11-07)

## Context

The author uses Paseo plugins in the Paseo web UI that the separate `paseo` kit runs
in the sandbox. A new sandbox starts with the daemon's `pluginsEnabled` switch unset
(treated as off) and no plugins configured, so each plugin had to be installed by hand
every time. [0001](0001-ship-the-first-mate-skill-as-a-snapshot-kit.md) and
[0002](0002-personal-kit-and-vendored-pocock-skills.md) kept this kit to files only: no
commands and no egress. A plugin install cannot be a file drop. The daemon owns its
plugin directory and config, and `paseo plugin install` needs a running daemon.

## Decision

1. **One startup command, in the background.** It runs
   `~/paseo-plugins-install.sh` (a dropped file, mode 0755) detached, with the same
   `user: "1000"` and `background: true` shape the paseo kit uses. The script waits up
   to 600 seconds for the daemon (the paseo kit npm-installs the CLI first, which can be
   slow behind a proxy), takes a run lock so two copies never install at once, then
   installs, retrying each plugin up to three times because the paseo kit can restart
   the daemon while it pins the worktree root. It always exits 0 and logs to
   `~/.local/state/paseo/paseo-plugins.log`, so it cannot fail a sandbox create. This is
   the kit's first `commands` block.

2. **The kit turns the global switch on.** If `pluginsEnabled` is not true, the script
   runs `paseo daemon config set pluginsEnabled true` under the paseo kit's
   `config.json` lock directory, then `paseo reload`. Plugins are trusted, unsandboxed
   code: server code can reach the sandbox's files, processes, credentials and network,
   and client code runs inside the app. The author gave explicit consent to enabling the
   switch in every sandbox that uses this kit (2026-11-07). The blast radius is the
   sandbox, which is already the security boundary.

3. **Pin every plugin to a full commit or exact version; do not install by registry
   id.** `paseo plugin install xzthemeofsss/quote-notes` asks `plugins.paseo.sh` what to
   install and takes the answer of the day. The script instead uses
   `git:owner/repo` with `--ref <40-hex>` (or `npm:pkg@x.y.z`), which resolves nothing
   remotely beyond the repository itself. The pin is the one the registry listed when it
   was reviewed. The guard is in the script itself: `install_plugin` refuses, and logs,
   anything but a git source with a lowercase 40-hex commit or an npm source with an
   exact `x.y.z`. `scripts/verify` section 3d checks the guard is present, that no other
   line calls `paseo plugin install`, and that every call is pinned. This also removes the dependency on `plugins.paseo.sh`,
   which was not reachable from the development sandbox, so the registry route could
   not be tested.

4. **Egress: `github.com`.** For `git clone` of the pinned sources. `caps.network` is
   sandbox-wide, so this also lets every other agent in the sandbox reach github.com. The first plugin is
   a git source. An npm-sourced plugin would need `registry.npmjs.org`, which the paseo
   kit already allows; it would be added to `caps.network` here too rather than relied
   on, in the commit that adds such a plugin.

5. **Idempotent and skip-if-present.** The script skips a plugin whose id is already
   configured, so a second run, a daemon restart that re-runs startup, or a snapshot that
   kept the plugin does not error or re-clone.

6. **No in-place updates.** Plugins install at create time, like provider input. To move
   a pin, change the script and recreate the sandbox.

## What was tested

Against a real Paseo 0.12.0 daemon in an isolated `PASEO_HOME`, with a real `git clone`
of the pinned commit (the registry was not used): starting with `pluginsEnabled` unset, the script
set it, reloaded, installed `quote-notes` from `git:xzthemeofsss/paseo-plugins` at the
pinned SHA, and `paseo plugin ls` reported it `running` at that SHA. A second run
logged "already installed; skipped". With no daemon it logged a clear message after the
wait and exited 0. The guard refused a branch, a short SHA, an uppercase SHA, an npm range
and a bare registry id; a second concurrent run exited at the run lock; a TERM left no
lock behind. Not tested: a real `acq run` with the paseo kit on msb or sbx (no `acq` in
the development sandbox), the paseo kit's newer CLI pins (0.12.0 here), a daemon restart
landing mid-install, and `git clone` behind an HTTPS-inspecting proxy whose CA is not in
the system store.

## Consequences

- The kit now depends on the paseo kit for the plugin step to do anything. Kits cannot
  declare dependencies yet, so this is documented, and the script reports a missing
  daemon instead of failing.
- The kit adds one egress host and one background process that lives for a few seconds
  to a few minutes after sandbox start.
- Updating a plugin is a code-review task: read the diff between pins, then bump.
- `scripts/verify` gains section 3d and also shellchecks the installer.
