# Decision: a `personal` kit that also vendors Matt Pocock's engineering skills

**Status:** accepted (2026-11-04)

## Context

[0001](0001-ship-the-first-mate-skill-as-a-snapshot-kit.md) shipped one skill as
a kit named `first-mate-skill`. The kit is really the author's personal layer on
top of the global kits, and that layer now carries more than one skill. The
author also wants the engineering skills from
[mattpocock/skills](https://github.com/mattpocock/skills) (MIT) in every sandbox.

## Decision

1. **Rename the kit `personal`.** It is the author's last-applied layer, not a
   delivery vehicle for one skill. The directory, `name:`, CI matrix, validator
   and test runner all use the new name. Pin and refer to it by `&dir=personal`.

2. **Ship all 27 of Matt's promoted skills.** The 20 under `skills/engineering/` and
   the 7 under `skills/productivity/`: exactly the list in his Claude Code plugin
   manifest at the pinned commit. The first cut shipped 22, leaving out `handoff`,
   `grill-me`, `teach`, `to-questionnaire` and `wait-what`; that left his router
   `ask-matt` naming five skills that were not installed, so they were added. His
   frozen `misc/` bucket and `in-progress/` bucket are not shipped.

3. **Install his `code-review` as `pocock-code-review`.** The playbook kit also
   ships a skill named `code-review` into the same `~/.agents/skills`, and it does
   a different job: his reviews a diff on a Standards axis and a Spec axis with
   parallel sub-agents; the playbook's is an attribution, PR-creation, security
   and merge checklist. Neither replaces the other. If both kept one name, the
   playbook kit's `ln -sfn` would link inside a real directory and leave a stray
   nested symlink, and the name would resolve to whichever won. The rename is
   applied by the vendoring script to the skill's `name:`, its display name, and
   every reference in the skills that call it (`ask-matt`, `implement`,
   `implement-spec`, `tdd`), so `implement` still closes out with his review, not
   the playbook's. The script pins how many references each file must have, so an
   upstream change fails loudly.

4. **Vendor verbatim copies, regenerate with a script.** `scripts/vendor-pocock-skills`
   reads a pinned upstream commit, writes the files under `files/`, rewrites the
   generated block in `spec.yaml`, and writes `vendor/mattpocock-skills.json`
   (commit, per-file sha256). `--check` fails on drift. Considered and rejected:
   a startup fetch (needs github egress and an integrity check, and adds a way
   for sandbox creation to fail) and hand maintenance (about 70 spec records).
   The only network use is on the host, in the script, never in the guest.

5. **Everything else is untouched.** Apart from the rename in decision 3, files
   are byte-identical to upstream. The upstream `LICENSE` ships beside them at
   `~/.agents/licenses/mattpocock-skills-LICENSE`, because the MIT notice has to
   travel with copies. See decision 7 for credit. Files are declared `0644`, including his two `.sh`
   templates, which are samples the agent copies rather than runs in place.

6. **Link check ignores fenced code.** Two upstream skills (`domain-modeling`,
   `wayfinder`) contain four example markdown links inside code fences (a glossary
   map and a closed-ticket index). The
   repository validator now skips fenced blocks when checking local links, with a
   regression test, so vendored files can stay unmodified.

7. **Credit is shipped, generated, and enforced.** The work is Matt Pocock's, so the
   kit says so where a person or an agent will read it: `README.md` (thanks and a
   credit section), `NOTICE` (full provenance, including the author's own part and
   that AI assisted), `docs/vendored-skills.md` (rules for maintainers, with the table
   of local differences generated from the script so it cannot drift), and a short
   `AGENTS.md`. Both licences install into the sandbox under `~/.agents/licenses/`.
   `scripts/verify` fails if a credit file, a licence, or a licence's spec record is
   missing, or if a licence differs from its pinned hash. The lock file records the
   attribution, the upstream release (`1.3.2`), and the local changes.

8. **Third-party material inside the vendored skills.** Matt's `pr` skill says its
   Summary section is adapted from `show-me` by Dex Horthy of HumanLayer, and its
   `SKILL.md` metadata points at `humanlayer/skills`, which is MIT, Copyright (c) 2026
   HumanLayer. Comparing non-blank lines, 88 of the 93 in the pr skill's "### Summary" section are
   identical to that repository's `show-me` (86 of 93 against the Apache-2.0
   `humanlayer/humanlayer` monorepo's copy), so the MIT notice from `humanlayer/skills` is shipped, pinned by
   sha256 in the script, and credited in `NOTICE`. The `pr` skill's own `CREDITS.md`
   ships unmodified. This is a good-faith reading of what the MIT licence asks for,
   not legal advice.

9. **A moved promotion list stops the run.** The script reads the skill list in
   upstream's plugin manifest at the pinned commit and refuses to continue if it no
   longer equals what the kit ships, so a newly promoted or retired skill is a
   decision, not a silent drift.

## Consequences

- The kit grows from 3 files to 84 `files[]` records: 4 are hand-written (the 3
  `paseo-first-mate` files and the HumanLayer licence) and 80 are generated (79 skill files plus the upstream licence). On msb each
  record is an individual copy into the guest, so sandbox creation is slower than
  before; that cost has not been measured here.
- Updating Matt's skills is `scripts/vendor-pocock-skills --sha <full-sha>`, a
  review of the diff, then `scripts/verify`.
- 16 of the 27 are user-invoked, not model-invoked: `disable-model-invocation` is set
  on `ask-matt`, `grill-me`, `grill-with-docs`, `handoff`, `implement`,
  `implement-spec`, `improve-codebase-architecture`, `retro`,
  `setup-matt-pocock-skills`, `teach`, `to-questionnaire`, `to-spec`, `to-tickets`,
  `triage`, `wait-what` and `wayfinder`, and the same 16 carry
  `allow_implicit_invocation: false` in `agents/openai.yaml` for Codex. Harnesses that
  read neither field will treat them as ordinary skills.
- `handoff` saves its document to the OS temporary directory, which does not outlive
  the sandbox, and `teach` writes lesson state into whatever directory it runs in.
  Both are upstream behaviour, unchanged here.
- The skills that publish to an issue tracker (`to-tickets`, `to-spec`, `triage`,
  `wayfinder`, `implement-spec`) expect a project to have run
  `/setup-matt-pocock-skills` once. Without it they fall back to local markdown or
  ask, as upstream describes.
- Upstream says it does not take skill contributions; changes to these files
  belong in this repository's script, not in the copies.
