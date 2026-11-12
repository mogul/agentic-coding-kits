# personal (acq mixin kit, `hybrid/v1`)

An [`acq`](https://github.com/GSA-TTS/agentic-coding-quickstart) **skill kit**
that holds the author's personal layer: the skills a coding agent should have in
every sandbox, applied last on top of the global kits.

It is an opt-in `--kit` mixin. It installs no agent, writes no provider
configuration, and publishes no ports. It runs one background startup command that
installs Paseo plugins (see [Paseo plugins](#paseo-plugins)), and allow-lists one
network hosts, `github.com` and `registry.npmjs.org`, for that command.

## What it ships

```text
~/.agents/skills/
  paseo-first-mate/            the author's own skill (version 1.4.0) and two helper scripts
    SKILL.md
    assets/first-mate-check.py   change detector (prints nothing when nothing changed)
    assets/first-mate-wait.sh    background wait loop around the detector; one loop per
                                 FIRST_MATE_DIR, owned by the starting agent (flock)
  <27 skills from mattpocock/skills>   vendored at a pinned commit, see below
  diagram-design/              offline editorial diagram guidance and guarded export
~/.agents/licenses/                            MIT notices for the third-party material
  mattpocock-skills-LICENSE                    Matt Pocock (the vendored skills)
  humanlayer-skills-LICENSE                    HumanLayer (show-me, adapted in the pr skill)
  diagram-design-LICENSE                       Cathryn Lavery (Diagram Design)
```

`~/.agents/skills` is the cross-agent skills root that the supported agents scan,
so no per-agent linking is needed.

The skills are written at their final path by the kit's `files[]` records, so they
need no command. The one startup command is the plugin installer below; it is
detached and always exits 0, so nothing it does can fail a sandbox create.

## Paseo plugins

At startup a background script, `~/paseo-plugins-install.sh`, installs the author's
Paseo plugins into the sandbox's Paseo daemon. It needs the separate
[`paseo` kit](https://github.com/GSA-TTS/agentic-coding-patterns/tree/main/integrations/isolation/acq-kits/paseo) applied too: that
kit starts the daemon this script talks to. Without it the script waits up to ten
minutes, logs that the daemon never answered, and installs nothing.

What it does, in order:

1. Takes a run lock (one installer at a time) and waits for `paseo plugin ls` to answer.
2. If the daemon's global `pluginsEnabled` switch is off, sets it with
   `paseo daemon config set` under the paseo kit's `config.json` lock and runs
   `paseo reload`. **Plugins are trusted, unsandboxed code**: a plugin's server code
   can reach the sandbox's files, processes, credentials and network, and its client
   code runs inside the Paseo app. Using this kit is the consent to turn the switch
   on.
3. Installs each listed plugin that is not already installed, from a source pinned to
   a full commit (`git:owner/repo` plus the SHA) or an exact npm version. It does not
   use a bare registry id such as `xzthemeofsss/quote-notes`, which would install
   whatever the registry points at that day. `scripts/verify` fails on an unpinned
   entry. Each install is retried up to three times, waiting for the daemon in between,
   because the paseo kit can restart the daemon while it pins the worktree root.

Log: `~/.local/state/paseo/paseo-plugins.log`. Check the result with `paseo plugin ls`.
Plugins live under the daemon's home, which is not persisted past the sandbox, so
each new sandbox installs them again.

| Plugin | Source | Pin (sha512s are recorded for reviewers; nothing checks them at install) | Notes |
| --- | --- | --- | --- |
| [`quote-notes`](https://paseo.sh/plugins/xzthemeofsss/quote-notes) ("Codex Style Annotations", 0.2.2) by xzthemeofsss | `git:xzthemeofsss/paseo-plugins` | `5ce92527c99a328b28775c7d745f324f2cc84309` | Client plus a one-line settings registration; no server handlers. Needs Paseo 0.11.4 or later. Disable the older `quote` plugin first if you add it. Some labels are in Chinese. |
| [`skills`](https://paseo.sh/plugins/gpambrozio/skills) ("Skills", 0.4.0) by gpambrozio | `npm:@gpambrozio/paseo-skills` | `0.4.0` (sha512 `zMgP2U/vrRsLkKhoQICkN52+YoDy2WkkYymEDmruduKxf4Dq99Ct8Pk3xqJyAzijq2oprMFYLbj/wT6XepBLeA==`) | Lists the skills each agent session can use, renders each `SKILL.md`, and can invoke one. Reads the skill directories under `~/.claude`, `~/.codex` (or `$CODEX_HOME`) and `~/.agents`, and the project-level ones for the agent's working directory; writes nothing; no network or subprocess. Shows this kit's 29 skills in the Paseo UI. Needs Paseo 0.9 or later. |
| [`mermaid`](https://paseo.sh/plugins/dutchakdev/mermaid) (0.5.0) by dutchakdev | `npm:paseo-plugin-mermaid` | `0.5.0` (sha512 `vNVNE1b0z7HJ1093jT1Cz/f3QYXFKg6yTfdqTHeFqaa9Ks437b0nrmQRdY/tWC9XDdXvgjWCCS1v9CsYYsCOhg==`) | Draws `mermaid` code blocks in chat as diagrams (flowcharts and sequence diagrams itself, other types through Paseo's Markdown on 0.13 or later), and opens `.mmd` files as diagrams. Runs only in the app: no server code, network or subprocess. Needs Paseo 0.11 or later. If you install Better Paseo, turn off its "Plugin markdown for replies" setting. |
| [`beautiful-chat`](https://paseo.sh/plugins/aborakati/beautiful-chat) (0.1.0) by ABorakati | `git:ABorakati/beautiful-chat` | `42b61d8301b5400a67821bbbfcf99fa8b681dc37` | Redraws chat timeline items (tool calls, reasoning, checklists, prompts, errors, replies) as typed, syntax-highlighted cards that follow the Paseo theme, with its own settings page and chat find. The code does not gate on provider, so it applies to every agent; only the OMP-specific parts (job and IRC envelopes) are provider specific. Its manifest runs `npm ci --include=dev` during install, so the daemon needs `npm` on its PATH and `registry.npmjs.org`. Its server spawns `xdg-open` for "reveal path", which does nothing useful in a headless sandbox. **Conflicts with `mermaid` by default, see below.** |
| [`emoji`](https://paseo.sh/plugins/yoseptf/emoji) (0.1.0) by YoseptF | `git:YoseptF/paseo-emoji` | `425e37563234d05a3ceaf15040db221625537db9` | Adds Slack-style `:emoji:` autocomplete to the composer using a bundled dictionary. Client-only; no server entry, runtime dependencies, network requests, or build commands. Uses the composer's DOM on desktop/web and intercepts Enter/Tab to accept a suggestion; native mobile is a no-op. Needs Paseo 0.8.0 or later. |
| [`agent-office`](https://paseo.sh/plugins/gyuha/agent-office) (0.2.0) by gyuha | `git:gyuha/agent-office` | `47b99a0d8a619a97af2443dede661e3b9b45b1bc` | Shows agents as characters in an office. Observes agent/workspace metadata and lifecycle events; keeps state in memory and uses embedded image assets. Does not start agents, approve permissions, write files, spawn commands, or call external services. Desktop/web animation; basic text fallback on mobile. Needs Paseo 0.15.2 or later on both daemon and client. Failed polling can leave stale status; use Paseo's agent state for authoritative decisions. Does not require Agent Team. |

**Compatibility and verification:** the full list now requires Paseo **0.15.2 or
later** on both daemon and client for Agent Office. This kit does not upgrade
either runtime. Emoji and Agent Office were source-reviewed at these exact pins.
Live results from a real sandbox:

- On Paseo **0.15.0** (what the paseo kit installed at the time), `quote-notes`,
  `skills`, `mermaid`, `beautiful-chat` and `emoji` all installed and reported
  `running`. `agent-office` was refused by the daemon with
  `requires Paseo >=0.15.2. Your daemon is 0.15.0` and installed nothing; the other
  five were unaffected.
- After upgrading the CLI to 0.15.4 and re-running `~/paseo-plugins-install.sh`,
  `agent-office` installed.

See [Agent Office needs a newer Paseo](TROUBLESHOOTING.md#agent-office-needs-a-newer-paseo).
Emoji and Agent Office UI behavior is still not verified. The earlier four-plugin
installer run on Paseo 0.12.0 does not establish compatibility for these additions.

**Mermaid and Beautiful Chat: switch one setting off, once per browser.** Beautiful Chat's
**Assistant markdown** setting is on by default and takes assistant replies before Mermaid
sees them, so Mermaid blocks show as plain code. In the Paseo app open
**Settings, Plugins, Beautiful Chat** and turn **Assistant markdown** off; Paseo then draws
replies itself and Mermaid draws the diagrams. (Mermaid's own overview calls the
equivalent setting in a different plugin, Better Paseo, "Plugin markdown for replies";
Beautiful Chat's is named **Assistant markdown**.)

Beautiful Chat keeps its settings in the browser's `localStorage` under
`paseo/beautiful-chat/preferences/v1`, not on the daemon, so the kit cannot set this for
you. `localStorage` belongs to the page origin. It carries across sandboxes only if you
reach them through the same origin, such as the hosted app at `app.paseo.sh` or the desktop
app. A daemon-served web UI on a per-sandbox published port is a new origin each time and
needs the toggle again. On a native mobile client `localStorage` may not exist, in which
case the choice is not saved and the conflict returns; that is untested.

To add or change one, edit the `install_plugin` lines at the bottom of
`files/home/paseo-plugins-install.sh`, read the plugin's source, and run
`scripts/verify`. The reasoning is in
[`docs/decisions/0003`](docs/decisions/0003-install-paseo-plugins-at-startup.md).

## Diagram Design

[Diagram Design by Cathryn Lavery](https://github.com/cathrynlavery/diagram-design)
is selectively vendored at `f2496acbde9f45ccb55c24d4f75210c8a1355df8`
(2.6.153), under MIT. It generates editorial HTML/SVG diagrams and imports draw.io,
Mermaid, Excalidraw and PlantUML sources. The local adaptations use system fonts,
manual project-local brand tokens, and no global profiles or remote onboarding.
Logos, galleries, example files and font binaries are not shipped.

Animation remains available using the reviewed template controller. The human can
open the generated HTML manually. SVG export is offline and user-requested through
`scripts/export_diagram.py`; the upstream transformer is internal, not a sanitizer.
The guarded Python export workflow targets Linux and Python 3.12 or later;
Windows/macOS automated export is unsupported. PNG export is **off by default** and requires explicit approval for the specific
input/output in the current session. Only the complete static animation frame is
supported, not intermediate-frame or full-page capture.

The PNG guard requires Linux Bubblewrap and a separately provisioned runtime outside
the project containing `bin/python` (with Playwright) and `chromium/chrome`.
It mounts only the snapshot/runtime/temporary output plus read-only system runtime
libraries, isolates network and process namespaces, clears the environment, and
limits time/output/pixel area. It never installs packages or falls back to an
unrestricted renderer. Browser export remains **BLOCKED** here: Chromium/Playwright
are not provisioned, so no successful live PNG capture is claimed. A hard release
gate additionally refuses browser execution until live capture and aggregate
resource/isolation tests pass; approval/provisioning alone do not enable it.

Maintainers edit `vendor/diagram-design-local/` and regenerate with
`python3 personal/scripts/vendor-diagram-design`; do not edit generated skill files.
`vendor/diagram-design.json` records provenance and hashes. See
[vendoring details](docs/vendored-skills.md#diagram-design) and
[decision 0004](docs/decisions/0004-vendor-offline-diagram-design.md).

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
- **Cathryn Lavery**: Diagram Design, MIT, Copyright (c) 2025 Cathryn Lavery.
  The separate lock and local adaptations are described above.
- **Mine**: `paseo-first-mate` and the scripts in this directory, written with AI
  assistance (OpenCode, claude-sonnet-5.5). MIT, this repository.

All three third-party licences are shipped into the sandbox at `~/.agents/licenses/`, and
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
drops files and starts one plugin installer that needs the separate paseo kit, so a live run would exercise acq and that kit rather than this one. The installer itself is exercised against a real Paseo daemon in an isolated home; see ADR 0003.

## Security notes

- **No secrets.** The skills and scripts reference credentials by variable name
  only, in prose. `scripts/verify` scans the payload for token and key shapes.
- **Instructions are executable influence.** A skill steers an agent that can
  run commands and push code. Everything is plain text you can read in this
  directory; review the diff before pinning a new SHA, especially after
  re-vendoring.
- **`github.com` and `registry.npmjs.org` are open to every agent in the sandbox.**
  `caps.network` is sandbox-wide, not scoped to the installer, so any agent or plugin
  there can also reach them (clones, gists, pushes, package fetches). The paseo kit
  already allows the npm registry.
- **Plugins are code, not text.** A listed plugin runs unsandboxed. Review a plugin's
  source at the exact commit before you add or move its pin, and check what it fetches
  and writes. Some plugins run commands at install: `beautiful-chat` declares
  `build: npm ci --include=dev`, which executes with the daemon's privileges and the sandbox's
  registry access (npm lifecycle scripts of its dependencies included). Read a plugin's `paseo-plugin.json` `build` list as well as its code. The installer reaches only `github.com` and `registry.npmjs.org`
  (and whatever the daemon's own allow-list permits); the egress allow-list is the only network control, and the
  plugin runs inside it.
- **Agent-writable.** The files land under `/home/agent`, which the agent owns.
  They are a convenience payload, not a trust anchor.

## License

MIT — see the repository [`LICENSE`](../LICENSE). The vendored skills are
Copyright (c) 2026 Matt Pocock, and the `pr` skill's adapted section is Copyright (c)
2026 HumanLayer, both also MIT; the notices ship at
`files/home/.agents/licenses/`. See [`NOTICE`](NOTICE).
