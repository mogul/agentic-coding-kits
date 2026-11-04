# personal (acq mixin kit, `hybrid/v1`)

An [`acq`](https://github.com/GSA-TTS/agentic-coding-quickstart) **skill kit**
that holds the author's personal layer: the skills a coding agent should have in
every sandbox, applied last on top of the global kits.

It is an opt-in `--kit` mixin. It installs no agent, writes no provider
configuration, runs no commands, publishes no ports, and allow-lists no
network hosts.

## What it ships

```text
~/.agents/skills/
  paseo-first-mate/            the author's own skill (version 1.4.0) and two helper scripts
    SKILL.md
    assets/first-mate-check.py   change detector (prints nothing when nothing changed)
    assets/first-mate-wait.sh    background wait loop around the detector; one loop per
                                 FIRST_MATE_DIR, owned by the starting agent (flock)
  <27 skills from mattpocock/skills>   vendored at a pinned commit, see below
~/.agents/licenses/                            MIT notices for the third-party material
  mattpocock-skills-LICENSE                    Matt Pocock (the vendored skills)
  humanlayer-skills-LICENSE                    HumanLayer (show-me, adapted in the pr skill)
```

`~/.agents/skills` is the cross-agent skills root that the supported agents scan,
so no per-agent linking is needed.

The payload is written at its final path by the kit's `files[]` records, which
is why the spec has no `commands`. Nothing can fail at startup beyond the file
drop itself.

## Matt Pocock's skills

These are **[Matt Pocock](https://github.com/mattpocock)'s work**, not mine. Thank you
to him for publishing them under the MIT licence. Verbatim copies of
[mattpocock/skills](https://github.com/mattpocock/skills) (Copyright (c) 2026 Matt
Pocock, pinned in [`vendor/mattpocock-skills.json`](vendor/mattpocock-skills.json)):
the 27 skills his Claude Code plugin promotes, which is every skill in his
`engineering/` and `productivity/` buckets. His `misc/` bucket (frozen upstream) and
`in-progress/` bucket are not included.

- **Engineering (20):** `ask-matt`, `codebase-design`, `diagnosing-bugs`,
  `domain-modeling`, `grill-with-docs`, `implement`, `implement-spec`,
  `improve-codebase-architecture`, `pr`, `prototype`, `research`, `retro`,
  `setup-matt-pocock-skills`, `tdd`, `to-spec`, `to-tickets`, `triage`, `wayfinder`,
  `wizard`, and code review (installed as `pocock-code-review`, below).
- **Productivity (7):** `grill-me`, `grilling`, `handoff`, `teach`,
  `to-questionnaire`, `wait-what`, `writing-for-agents`.

- **Code review is `pocock-code-review`.** The playbook kit ships a different skill
  called `code-review` into the same directory. His reviews a diff on a Standards
  axis and a Spec axis; the playbook's is an attribution, PR, security and merge
  checklist. Both stay available, and every reference inside his skills was
  rewritten so `implement` still ends with his review. This is the only change to
  upstream text. Every difference from upstream is listed in
  [`docs/vendored-skills.md`](docs/vendored-skills.md); the reasoning is in
  [`docs/decisions/0002`](docs/decisions/0002-personal-kit-and-vendored-pocock-skills.md).
- **16 of the 27 are user-invoked** (`ask-matt`, `grill-me`, `grill-with-docs`,
  `handoff`, `implement`, `implement-spec`, `improve-codebase-architecture`, `retro`,
  `setup-matt-pocock-skills`, `teach`, `to-questionnaire`, `to-spec`, `to-tickets`,
  `triage`, `wait-what`, `wayfinder`). Type the skill's name; the model will not
  pick them on its own. The other 11 it may load when a task matches.
- **Run `/setup-matt-pocock-skills` once per project** before the skills that
  publish to an issue tracker (`to-tickets`, `to-spec`, `triage`, `wayfinder`).
- **`handoff` writes to the temporary directory** (`$TMPDIR`, else `/tmp`), not the
  workspace. The file is gone with the sandbox, so copy it out if the next session
  runs somewhere else.
- **`teach` treats the directory it is run in as a teaching workspace** and creates
  `MISSION.md`, `lessons/`, `reference/` and similar files there. Run it in a
  dedicated directory, not a code repository.

Update them with the vendoring script, then review the diff:

```bash
personal/scripts/vendor-pocock-skills --sha <full-40-char-commit>   # move the pin
personal/scripts/vendor-pocock-skills                               # re-vendor the pinned commit
personal/scripts/vendor-pocock-skills --check                       # fail on drift (needs network)
```

The script runs on the host, never in the sandbox. It refuses archive members
that are not regular text files, caps archive and file sizes, and fails if the
number of `code-review` references in any file differs from what it expects.

## Credit and licences

- **Matt Pocock**: the 27 skills above. MIT, Copyright (c) 2026 Matt Pocock.
- **Dex Horthy, HumanLayer**: the `pr` skill's menu of visuals is adapted from
  HumanLayer's `show-me` skill, as that skill's own `CREDITS.md` says. MIT, Copyright (c)
  2026 HumanLayer.
- **Mine**: `paseo-first-mate` and the scripts in this directory, written with AI
  assistance (OpenCode, claude-sonnet-5.5). MIT, this repository.

Both third-party licences are shipped into the sandbox at `~/.agents/licenses/`, and
[`NOTICE`](NOTICE) has the full provenance. [`docs/vendored-skills.md`](docs/vendored-skills.md)
is for anyone maintaining the copies: the rule against hand-editing, the table of local
differences, and how to update. [`AGENTS.md`](AGENTS.md) is the short version for agents.

## Using the kit

Pin the ref to a full commit SHA and select the subdirectory with `&dir=`.
Never use `#ref=main`: a branch ref lets the host fetch different code at a
different time.

```bash
export ACQ_EXTRA_KIT_SOURCES="github.com/mogul/"

acq run opencode /path/to/project \
  --kit "git+https://github.com/mogul/agentic-coding-kits.git#ref=<full-sha>&dir=personal"
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
secret bindings. The wait loop also needs `flock` (util-linux) and keys its lock
on `PASEO_AGENT_ID`. Use `first-mate-wait.sh status` to see whether a loop is
running and who owns it. A missing tool is reported rather than hidden: the
detector prints an `ERROR` line naming the missing CLI, and the shell reports a
missing `python3`. The detector only reads GitHub and Paseo state; its only
writes are the state and watch files, and the directory that holds them,
`FIRST_MATE_DIR` (default `./tmp`, relative to the current directory).

## Updating the First Mate skill

It is a **one-time snapshot** of the author's working copy, not a synced copy;
see [`docs/decisions/0001`](docs/decisions/0001-ship-the-first-mate-skill-as-a-snapshot-kit.md).
To update it:

1. Replace `SKILL.md` and the two `assets/` files under
   `files/home/.agents/skills/paseo-first-mate/`.
2. Keep each file's mode in `spec.yaml` (`0644` for `SKILL.md`, `0755` for the
   scripts).
3. If you add or remove a file, add or remove its `files[]` record above the
   generated block. msb materializes only the listed records.
4. Run `scripts/verify`.
5. Recreate the sandbox. `acq kit apply` re-applies the spec to an existing
   sandbox, but a new kit commit is a new ref, so a fresh `acq run` is the
   reliable path.

## Verifying the kit

```bash
scripts/verify
```

The offline gate checks that the spec and `files/` agree, that the credit files and both
licences are shipped, the declared modes and
the scripts' executable bits, the First Mate skill's frontmatter and asset
references, that both helper scripts parse, that the detector runs against an
empty state directory, that every vendored file still matches the sha256 in its
lock file, that the renamed skill is consistent everywhere, that no
credential-shaped string is shipped, and `acq kit validate` when available.
`shellcheck` runs when installed. There is no live sandbox check: the kit only
drops files, so a live run would exercise acq's file drop rather than this kit.

## Security notes

- **No secrets.** The skills and scripts reference credentials by variable name
  only, in prose. `scripts/verify` scans the payload for token and key shapes.
- **Instructions are executable influence.** A skill steers an agent that can
  run commands and push code. Everything is plain text you can read in this
  directory; review the diff before pinning a new SHA, especially after
  re-vendoring.
- **Agent-writable.** The files land under `/home/agent`, which the agent owns.
  They are a convenience payload, not a trust anchor.

## License

MIT — see the repository [`LICENSE`](../LICENSE). The vendored skills are
Copyright (c) 2026 Matt Pocock, and the `pr` skill's adapted section is Copyright (c)
2026 HumanLayer, both also MIT; the notices ship at
`files/home/.agents/licenses/`. See [`NOTICE`](NOTICE).
