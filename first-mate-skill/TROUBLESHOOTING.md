# Troubleshooting — first-mate-skill kit

## The agent does not list or load `paseo-first-mate`

- **Check the file landed.**

  ```bash
  acq exec <sandbox> -- ls -l /home/agent/.agents/skills/paseo-first-mate
  ```

  Expect `SKILL.md` and `assets/`. If it is missing, the kit was not applied:
  confirm `ACQ_EXTRA_KIT_SOURCES` includes `github.com/mogul/`, the ref is a
  full SHA, and `&dir=first-mate-skill` is present.
- **Start a new session.** Agents usually discover skills at startup.

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
restart it after that. If `paseo` is missing the baseline never settles (see the
previous section), so the loop returns every time. Run the script with `--show`
to see the full current snapshot, and `list` to see what is being watched. State
and watch files live in `FIRST_MATE_DIR` (default `./tmp`), relative to where
you run the script.

## An edit to the skill does not show up in a running sandbox

The kit is applied from a pinned SHA. Push the change, pin the new SHA, and
create a new sandbox. Editing the files inside a running sandbox changes that
sandbox only.
