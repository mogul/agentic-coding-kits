# Troubleshooting — personal kit

## The agent does not list or load `paseo-first-mate`

- **Check the file landed.**

  ```bash
  acq exec <sandbox> -- ls -l /home/agent/.agents/skills/paseo-first-mate
  ```

  Expect `SKILL.md` and `assets/`. If it is missing, the kit was not applied:
  confirm `ACQ_EXTRA_KIT_SOURCES` includes `github.com/mogul/`, the ref is a
  full SHA, and `&dir=personal` is present.
- **Start a new session.** Agents usually discover skills at startup.

## Agent Office needs a newer Paseo

**Symptom:** `paseo plugin ls` shows five plugins but not `agent-office`, and
`~/.local/state/paseo/paseo-plugins.log` ends with:

```text
Error: Request failed: Plugin "agent-office" requires Paseo >=0.15.2. Your daemon is 0.15.0. ...
paseo-plugins: agent-office FAILED to install from git:gyuha/agent-office after 3 attempts
```

**Cause:** the daemon is older than the plugin allows. This kit never upgrades
Paseo; the paseo kit's pinned CLI version decides what the sandbox gets. The other
plugins are unaffected, and the installer still exits 0.

**Fix, in the running sandbox** (the paseo kit may put its own pin back on the next
sandbox start, so also raise the pin there):

```bash
npm install -g --prefix "$HOME/.npm-global" --cache "$HOME/.npm" --ignore-scripts @getpaseo/cli@0.15.4
paseo --version        # 0.15.2 or later
paseo daemon restart
sh ~/paseo-plugins-install.sh
paseo plugin ls | grep agent-office
```

The client (desktop or web app) must also be 0.15.2 or later.

## `first-mate-wait.sh: Permission denied`

The scripts are declared `0755`. On sbx, every `files/` payload is first
materialized at `0644` and a combined chmod step restores the declared modes;
if that step did not run, run the script as `bash first-mate-wait.sh` or
`chmod +x` the two files.

## `python3`, `gh`, or `paseo`: command not found

The detector needs `python3` and shells out to `gh` and `paseo`. This kit
installs none of them.
Use an image or kit that provides them, and make sure GitHub access is bound
through acq's secret flow. The detector treats a transient API error as "keep
the previous value" and reports it, so a missing `gh` or `paseo` shows up as an
`ERROR` line on every run, which makes the wait loop return immediately each
time. A missing `python3` also makes the wait loop return at once, with the
shell's "command not found" as its output.

## The detector prints nothing and the wait loop never returns

That is the intended quiet path: once a baseline exists, it prints nothing when
nothing changed, and the wait loop exits 3 at its cap. The very first run prints
`BASELINE saved` (even with an empty watch list, because agents and permission
prompts are always collected), so the wait loop returns once at first start;
start it again after that (check `status` first). If `paseo` is missing the baseline never settles (see the
previous section), so the loop returns every time. Run the script with `--show`
to see the full current snapshot, and `list` to see what is being watched. State
and watch files live in `FIRST_MATE_DIR` (default `./tmp`), relative to where
you run the script.

## Several wait loops, or "refusing: a loop is running"

The wait script allows one loop per `FIRST_MATE_DIR`, owned by the agent whose
`PASEO_AGENT_ID` started it. A second start exits 4 (you own it) or 5 (another
agent owns it) and starts nothing.

- `first-mate-wait.sh status` prints `none`, `mine ...`, or `other owner=<id> ...`.
- `first-mate-wait.sh stop` stops your loop. `stop --force` stops another owner's.
- `first-mate-wait.sh take-over INTERVAL MAX` replaces another owner's loop. Use
  it only when the user has said you are the coordinator.
- The lock is an `flock` on `FIRST_MATE_DIR/.wait.lock`, so it frees itself when the
  loop dies. If you still see several loops, they are from an older copy of the
  script or from different `FIRST_MATE_DIR` values (each directory has its own lock).
- A forked or resumed session inherits the handoff's claim that a loop is running.
  That claim is not evidence; run `status`.

## An edit to the skill does not show up in a running sandbox

The kit is applied from a pinned SHA. Push the change, pin the new SHA, and
create a new sandbox. Editing the files inside a running sandbox changes that
sandbox only.

## A Paseo plugin is not installed

- **Read the log.**

  ```bash
  acq exec <sandbox> -- cat /home/agent/.local/state/paseo/paseo-plugins.log
  acq exec <sandbox> -- paseo plugin ls
  ```

- **"daemon not reachable ... (is the paseo kit applied?)".** The installer talks to the
  Paseo daemon that the separate `paseo` kit starts. Apply both kits. If the daemon was
  slow, run `sh ~/paseo-plugins-install.sh` again; it skips what is already installed.
- **"could not lock config.json" or "could not set pluginsEnabled".** The paseo kit holds
  a lock while it writes `config.json`. Run the installer again.
- **"another installer is running".** A run lock at
  `~/.local/state/paseo/paseo-plugins.run.lock` is held, or was left by a killed run.
  If no installer is running, remove that directory and run again. A killed run can
  likewise leave `~/.paseo/.config-json.lock`, which the paseo kit also waits on.
- **A `git clone` fails.** The sandbox must allow `github.com`. This kit's `caps.network`
  lists it; confirm the kit was applied and the egress policy did not drop it. Behind an
  HTTPS-inspecting proxy, git needs the proxy CA in the system store; that path is untested.
- **The plugin installed but the UI does not show it.** Reload the browser tab. Client
  plugins load in the app, not the daemon, and the app checks the plugin's
  `requirements.paseo` range against its own version.
- **It is installed but you want a newer version.** Change the pin in
  `files/home/paseo-plugins-install.sh`, run `scripts/verify`, and recreate the sandbox.
  Plugins are installed at create time and are not updated in place.
