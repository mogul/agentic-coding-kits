# first-mate-skill (acq mixin kit, `hybrid/v1`)

An [`acq`](https://github.com/GSA-TTS/agentic-coding-quickstart) **skill kit**.
It drops the `paseo-first-mate` Agent Skill into the sandbox so a coding agent
can coordinate a multi-issue engineering effort through isolated Paseo
workspaces and GitHub: delegate work, track dependent pull requests, wait on
changes cheaply, and keep a durable handoff.

It is an opt-in `--kit` mixin. It installs no agent, writes no provider
configuration, runs no commands, publishes no ports, and allow-lists no
network hosts.

## What it ships

```text
~/.agents/skills/paseo-first-mate/
  SKILL.md                    the skill (version 1.2.0 at authorship)
  assets/first-mate-check.py  change detector (prints nothing when nothing changed)
  assets/first-mate-wait.sh   background wait loop around the detector
```

`~/.agents/skills` is the cross-agent skills root that the supported agents scan,
so no per-agent linking is needed.

The payload is written at its final path by the kit's `files[]` records, which
is why the spec has no `commands`. Nothing can fail at startup beyond the file
drop itself.

## Using the kit

Pin the ref to a full commit SHA and select the subdirectory with `&dir=`.
Never use `#ref=main`: a branch ref lets the host fetch different code at a
different time.

```bash
export ACQ_EXTRA_KIT_SOURCES="github.com/mogul/"

acq run opencode /path/to/project \
  --kit "git+https://github.com/mogul/agentic-coding-kits.git#ref=<full-sha>&dir=first-mate-skill"
```

To apply it on every run, put the same ref in `ACQ_EXTRA_KITS`. Extra kits apply
after the built-ins, and acq resolves overlapping file paths last-wins; that
rule is confirmed in the sbx translator and not separately checked on msb.

Then ask the agent to coordinate an effort ("act as first mate for these
issues"). The skill tells it to copy `assets/` into the coordinator worktree's
git-ignored `tmp/` before using the scripts.

## What the helper scripts need

The detector is a Python 3 script and the wait loop is bash. They call the `gh`
and `paseo` CLIs when the agent runs them. This kit installs none of `python3`,
`gh`, or `paseo` and does not allow-list `api.github.com`; kits cannot declare
dependencies yet, so those must come from the sandbox image, its other kits, and
secret bindings. A missing tool is reported rather than hidden: the detector
prints an `ERROR` line naming the missing CLI, and the shell reports a missing
`python3`. The detector only reads GitHub and Paseo state; its only writes are
the state and watch files, and the directory that holds them, `FIRST_MATE_DIR`
(default `./tmp`, relative to the current directory).

## Updating the skill

The skill is a **one-time snapshot** of the author's working copy, not a synced
copy; see [`docs/decisions/0001`](docs/decisions/0001-ship-the-first-mate-skill-as-a-snapshot-kit.md).
To update it:

1. Replace `SKILL.md` and the two `assets/` files under
   `files/home/.agents/skills/paseo-first-mate/`.
2. Keep each file's mode in `spec.yaml` (`0644` for `SKILL.md`, `0755` for the
   scripts).
3. If you add or remove a file, add or remove its `files[]` record. msb
   materializes only the listed records.
4. Run `scripts/verify`.
5. Recreate the sandbox. `acq kit apply` re-applies the spec to an existing
   sandbox, but a new kit commit is a new ref, so a fresh `acq run` is the
   reliable path.

## Verifying the kit

```bash
scripts/verify
```

The offline gate checks that the spec and `files/` agree, the declared modes and
the scripts' executable bits, the skill's frontmatter and asset references, that
both helper scripts parse, that the detector runs against an empty state
directory, that no credential-shaped string is shipped, and `acq kit validate`
when available. `shellcheck` runs when installed. There is no live sandbox
check: the kit only drops files, so a live run would exercise acq's file drop
rather than this kit.

## Security notes

- **No secrets.** The skill and scripts reference credentials by variable name
  only, in prose. `scripts/verify` scans the payload for token and key shapes.
- **Instructions are executable influence.** A skill steers an agent that can
  run commands and push code. The skill is plain text you can read in this
  directory; review it before pinning a new SHA.
- **Agent-writable.** The files land under `/home/agent`, which the agent owns.
  They are a convenience payload, not a trust anchor.

## License

MIT — see the repository [`LICENSE`](../LICENSE).
