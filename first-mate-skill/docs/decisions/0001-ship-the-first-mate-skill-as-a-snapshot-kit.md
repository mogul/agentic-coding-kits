# Decision: ship the First Mate skill as a snapshot kit at its final path

**Status:** accepted (2026-10-29)

## Context

The `paseo-first-mate` skill is a single `SKILL.md` plus two helper scripts
(a change detector and a wait loop). The author wants it available inside every
acq sandbox, as a personal skill, without editing the playbook kit or the image.
acq's extension point for that is an opt-in `hybrid/v1` mixin applied with
`--kit` or `ACQ_EXTRA_KITS`.

The skill is still being developed in a separate working copy.

## Decision

1. **A mixin kit that only drops files.** The spec has `files[]` records and
   nothing else: no `commands`, no `caps.network`, no `agent:`, no ports. The
   skill needs no install step, and the scripts' network use (`gh`, `paseo`)
   belongs to the kits and image that provide those CLIs.

2. **Write the payload at its final path, `~/.agents/skills/paseo-first-mate/`.**
   This is the cross-agent skills root that the supported agents scan. The
   playbook kit instead extracts a tree elsewhere and symlinks entries into
   several roots, with integrity and symlink guards.
   That machinery protects against a tampered tarball; this kit has no
   download, so it has nothing to guard and no reason to add a link step that
   could fail. The playbook kit links its own skill names into the same
   directory; none of them is `paseo-first-mate`, and both write as the agent
   user, so the two do not collide.

3. **A one-time snapshot, not a synced copy.** The files were copied once from
   the author's working copy at skill version 1.2.0, and later edits are applied
   by replacing the files by hand. Considered and rejected for now: a sync
   script that copies from the working copy into the kit. A snapshot keeps this
   repository self-contained and reviewable by SHA, and avoids a script that
   reaches into a path that exists on one machine. If the skill starts changing
   often, add the sync script then.

4. **Declared modes.** `SKILL.md` is `0644`; the two scripts are `0755`. The
   skill tells the agent to copy the scripts into a git-ignored worktree
   directory before use. They stay executable so the copy keeps working
   and so `bash` and direct invocation both work.

5. **Verification is offline.** `scripts/verify` checks the spec against the
   tree, modes, frontmatter, script syntax, and a credential-pattern scan, and
   runs `acq kit validate` when `acq` is present. A live sandbox run would
   mostly exercise acq's file drop, not anything this kit decides.

6. **Two edits to the snapshot.** Relative to the working copy, the skill's
   `owners` is `@mogul` (this repository's owner), and the dangling
   `pattern-router` line in "Related Patterns" is removed because that pattern
   does not exist here.

## Consequences

- The kit adds no egress, no startup work, and no failure modes beyond the file
  drop.
- Updating the skill is a manual replace plus `scripts/verify` plus a new pinned
  SHA.
- The spec's `files[]` list and the `files/` tree must be kept equal by hand;
  `scripts/verify` enforces it, because msb materializes only listed records.

## Update 2026-10-31: skill 1.3.0

The snapshot moved to skill version 1.3.0. `first-mate-wait.sh` now holds an
`flock` keyed on the caller's `PASEO_AGENT_ID`, and `scripts/test-wait-lock`
(run from `scripts/verify`) covers it offline with a stub detector. This changes
the shipped script, not the kit's shape: still files only, no commands, no
egress. The script now also requires `flock` from util-linux on the sandbox image.
