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

4. **Egress: `github.com` and `registry.npmjs.org`.** `github.com` is for `git clone` of
   git-sourced plugins and `registry.npmjs.org` for npm-sourced ones. The paseo kit
   already allows the npm registry; this kit lists it too rather than rely on another kit.
   `caps.network` is sandbox-wide, so every other agent in the sandbox also reaches these
   hosts. `scripts/verify` fails if an npm-sourced plugin is listed without the npm host.
   The daemon installs npm plugins with `--ignore-scripts` (checked in its source).

5. **Idempotent and skip-if-present.** The script skips a plugin whose id is already
   configured, so a second run, a daemon restart that re-runs startup, or a snapshot that
   kept the plugin does not error or re-clone.

6. **Plugins with a `build` step are allowed, reviewed by hand.** `beautiful-chat`'s
   manifest runs `npm ci --include=dev` on install, unsandboxed, so its dev dependencies
   (React Native, TypeScript, about 360 packages) are fetched and their lifecycle scripts
   may run. Reviewed at the pinned commit: every lockfile entry resolves from
   `registry.npmjs.org` with an integrity hash, and the only package with an install
   script is `fsevents` (macOS only, skipped on Linux). That is a point-in-time review of a
   lockfile, not a guarantee. The kit cannot see a plugin's `build` list from the installer,
   so `scripts/verify` does not check it; the README tells whoever bumps a pin to read it.

7. **No in-place updates.** Plugins install at create time, like provider input. To move
   a pin, change the script and recreate the sandbox.

## What was tested

Against a real Paseo 0.12.0 daemon in an isolated `PASEO_HOME`, with real `git clone`s and
npm installs (the registry at `plugins.paseo.sh` was not used): starting with `pluginsEnabled`
unset, one run of the script set it, reloaded, and installed all four plugins. `paseo plugin
ls` reported each `running` at its pin: `quote-notes` and `beautiful-chat` at their commits,
`skills` 0.4.0 and `mermaid` 0.5.0 from npm (the lockfiles the daemon wrote carry the same
sha512s recorded in the README). `beautiful-chat`'s `npm ci` build took about 7 seconds. A
second run logged "already installed; skipped" for each. With no daemon it logged a clear
message after the wait and exited 0. The run-time guard refused a branch, a short SHA, an
uppercase SHA, an npm range or tag, a bare registry id, `git:` sources with extra path
segments or `@ref`, and `npm:github:` sources, all before calling `paseo`. A second
concurrent run exited at the run lock, and a TERM left no lock behind.

Not tested: a real `acq run` with the paseo kit on msb or sbx (no `acq` in the development
sandbox), the paseo kit's newer CLI pins (0.12.0 here), a daemon restart landing mid-install,
a build that outlasts the CLI's own install timeout, `git clone` behind an HTTPS-inspecting
proxy whose CA is not in the system store, and how any of the plugins look in a browser.

## Consequences

- The kit now depends on the paseo kit for the plugin step to do anything. Kits cannot
  declare dependencies yet, so this is documented, and the script reports a missing
  daemon instead of failing.
- The kit adds two egress hosts (`github.com`, `registry.npmjs.org`) and one background process that lives for a few seconds
  to a few minutes after sandbox start.
- Updating a plugin is a code-review task: read the diff between pins, then bump.
- `scripts/verify` gains section 3d and also shellchecks the installer.
- `mermaid` and `beautiful-chat` conflict until Beautiful Chat's **Assistant markdown**
  setting is switched off in each browser origin. That setting is client-side
  `localStorage`, so the kit cannot apply it. Documented in the README.
