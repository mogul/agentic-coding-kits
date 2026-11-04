# Vendored skills: what is copied, what differs, how to change it

For people and agents who maintain the `personal` kit. Read this before touching
anything under `files/home/.agents/skills/` other than `paseo-first-mate/`.

## The rule

Twenty-seven of the skills in this kit are **Matt Pocock's work**, copied from
[mattpocock/skills](https://github.com/mattpocock/skills). They are generated, not
authored here.

- **Do not hand-edit them.** `scripts/verify` compares every file to a sha256 in
  [`vendor/mattpocock-skills.json`](../vendor/mattpocock-skills.json) and fails on any
  edit, any extra file, and any missing file.
- **To change what is shipped, change the script**, not the copies:
  `scripts/vendor-pocock-skills` decides which skills are copied and which local
  differences are applied, then regenerates the files, the generated block of
  `spec.yaml`, the lock file and the table below.
- **Keep the credit.** [`NOTICE`](../NOTICE) and the two files in
  `files/home/.agents/licenses/` are part of the copy. If you add third-party
  material, add its notice and a `THIRD_PARTY` entry in the script.
- **Upstream is not the place to send local changes.** Its
  [`CONTRIBUTING.md`](https://github.com/mattpocock/skills/blob/main/CONTRIBUTING.md)
  takes bug reports with a real failing session, and no pull requests or new-skill
  proposals from outside. A change that only suits this kit belongs here.

## Credit

| Work | Author | Licence | Where the notice lives |
| --- | --- | --- | --- |
| The 27 skills (`ask-matt`, `tdd`, `triage`, ...) | Matt Pocock | MIT, Copyright (c) 2026 Matt Pocock | `files/home/.agents/licenses/mattpocock-skills-LICENSE` |
| The visuals menu in the `pr` skill, adapted from `show-me` | Dex Horthy, HumanLayer | MIT, Copyright (c) 2026 HumanLayer | `files/home/.agents/licenses/humanlayer-skills-LICENSE` |
| `paseo-first-mate`, and this kit's scripts, tests and docs | Bret Mogilefsky, with AI assistance | MIT, this repository | [`../../LICENSE`](../../LICENSE) |

`NOTICE` has the full provenance, including how closely the `pr` section matches
`show-me`. The `pr` skill also credits Dex Horthy itself, in
its own `CREDITS.md` and in the `metadata.credits` of its `SKILL.md`; both are shipped
unmodified. The licence files are installed into the sandbox next to the skills, at
`~/.agents/licenses/`, so the notices travel with every copy.

Some skills cite ideas by name (Ousterhout's "Design It Twice" in `codebase-design`,
Michael Feathers's "seam", Fowler's code smells in `pocock-code-review`). Those
credits are Matt's and are shipped as written.

## Local differences from upstream

Everything not listed here is **byte-identical in content** to upstream at the pinned
commit, and has the same file mode (upstream's shipped files are all `0644`).
The table is generated from the script; if it looks wrong, fix the script.

<!-- BEGIN generated:local-differences (scripts/vendor-pocock-skills; do not edit) -->
- Upstream: https://github.com/mattpocock/skills at commit `4ae2317ddb22b046e26455e4f9c9b3aaaf62212d`, release `1.3.2` (Copyright (c) 2026 Matt Pocock, MIT).
- Shipped: 27 skills, 80 files (the licence included).

Third-party material inside those skills:
- `pr`: adapted from `show-me` by Dex Horthy (HumanLayer), MIT, Copyright (c) 2026 HumanLayer; notice at `files/home/.agents/licenses/humanlayer-skills-LICENSE`; source https://github.com/humanlayer/skills/tree/4d69d20f6e9b57b4fcf0d501ccfb1be961f0f329/plugins/show-me

| Shipped file | What differs from upstream |
| --- | --- |
| `pocock-code-review/` | upstream skills/engineering/code-review/ is installed under the name pocock-code-review |
| `ask-matt/SKILL.md` | 4 references to code-review rewritten to pocock-code-review |
| `implement-spec/SKILL.md` | 1 reference to code-review rewritten to pocock-code-review |
| `implement/SKILL.md` | 1 reference to code-review rewritten to pocock-code-review |
| `pocock-code-review/SKILL.md` | 1 reference to code-review rewritten to pocock-code-review |
| `tdd/SKILL.md` | 1 reference to code-review rewritten to pocock-code-review |
| `pocock-code-review/agents/openai.yaml` | display_name: "Code Review" -> display_name: "Pocock Code Review" |
<!-- END generated:local-differences -->

Why each one exists:

- **`code-review` is installed as `pocock-code-review`.** The playbook kit
  (`agentic-coding-playbook`) ships a *different* skill named `code-review` into the
  same `~/.agents/skills`. Matt's reviews a diff on a Standards axis and a Spec axis
  with parallel sub-agents; the playbook's is an attribution, PR, security and merge
  checklist. Neither replaces the other. If both kept the name, the playbook kit's
  `ln -sfn` would link inside a real directory and leave a stray nested symlink, and
  the name would resolve to whichever won.
- **The four callers were rewritten with it.** `implement` and `implement-spec`
  call the review skill by name at close-out, `tdd` points at it, and `ask-matt`
  routes to it. Without the rewrite, `implement` would run the playbook's checklist
  instead of Matt's review. The script pins how many references each file must have,
  so an upstream edit that adds or removes one fails loudly instead of leaving a
  caller pointing at the wrong skill.

## Deliberately not different

- **File modes.** Every vendored file is declared `0644`, including the two `.sh`
  templates (`wizard/template.sh`, `diagnosing-bugs/scripts/hitl-loop.template.sh`).
  They are samples the agent copies, not programs it runs in place.
- **Harness-specific files.** The `agents/openai.yaml` files are shipped. They are how
  Codex learns a skill is user-invoked; other harnesses ignore them.
- **Upstream wording.** Skills say "call the Skill tool" and name `/clear`,
  `/compact` and `CLAUDE.md`. That is Matt's phrasing for his own harness. It is not
  translated, so an agent in another harness maps it to its own skill tool.
- **Links to upstream's site** (for example `aihero.dev`) are left as written.

## Things that surprise people

- **16 of the 27 are user-invoked.** They have `disable-model-invocation: true` in
  `SKILL.md` and `allow_implicit_invocation: false` in `agents/openai.yaml`: `ask-matt`,
  `grill-me`, `grill-with-docs`, `handoff`, `implement`, `implement-spec`,
  `improve-codebase-architecture`, `retro`, `setup-matt-pocock-skills`, `teach`,
  `to-questionnaire`, `to-spec`, `to-tickets`, `triage`, `wait-what`, `wayfinder`. The
  model will not load them on its own; the user types the name.
- **`setup-matt-pocock-skills` edits the project.** It writes `docs/agents/*.md` and an
  `## Agent skills` block into the project's `CLAUDE.md` or `AGENTS.md`. Skills that
  publish to an issue tracker (`to-tickets`, `to-spec`, `triage`, `wayfinder`,
  `implement-spec`) expect it to have run once.
- **`handoff` writes to the OS temporary directory**, not the workspace, so the file
  does not outlive the sandbox. **`teach` treats the current directory as a teaching
  workspace** and fills it with `MISSION.md`, `lessons/` and similar files; do not
  start it in a code repository.

## Updating to a newer upstream

1. Read upstream's changes since the pin in `vendor/mattpocock-skills.json`
   (`ref`) and its `CHANGELOG.md`.
2. `scripts/vendor-pocock-skills --sha <full-40-character-commit>`. It fetches the
   archive over HTTPS (the only network use, on the host, never in the sandbox).
3. If it stops with **"upstream's promoted skills changed"**, upstream added or
   dropped a skill in its plugin manifest. Decide for each, then edit `SKILLS` in the
   script. Shipping all of the promoted set is deliberate: `ask-matt` routes to every
   one of them.
4. If it stops with **"expected N references to code-review"**, upstream changed how a
   skill mentions the review skill. Read the diff, then update `TOKEN_COUNTS`.
5. Review `git diff`. These files steer an agent that can run commands, so read the
   change as you would a dependency bump.
6. `scripts/verify`, then recreate the sandbox: a new kit commit is a new ref.

`scripts/vendor-pocock-skills --check` fetches the pinned commit and fails if a shipped
file differs from, or is missing against, a fresh vendoring. `scripts/verify` also
catches extra files and runs offline.

## Adding another renamed skill

If a vendored skill's name collides with another kit's, add it to the rename the way
`code-review` is handled: change `OLD_NAME`/`NEW_NAME` handling in the script to a
mapping, pin the reference counts per file, and record why in an ADR. Check first
with `git ls-tree --name-only <ref> .agents/skills/` in the playbook repository.

## What is not verified

No live sandbox run, on either backend. On msb every `files[]` record is copied
separately; the effect of 84 records on creation time has not been measured.
