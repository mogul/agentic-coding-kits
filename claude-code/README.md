---
title: "Claude Code acq Agent Kit"
description: "Terminal Claude Code in an acq sandbox using an OpenAI-compatible provider."
status: draft
tier: 2
last_updated: "2026-10-30"
---

# Claude Code (acq agent kit)

Run Claude Code **inside** an acq-managed microVM, using USAi's Claude models
through its **OpenAI Chat Completions** endpoint. The terminal runs in the
guest; your host terminal supplies the keyboard and display. No desktop app,
Anthropic login, or graphical display server is needed.

```text
Host terminal → acq guest terminal → claude wrapper → Claude Code
                                          │             │ Messages + SSE
                                          └── private LiteLLM bridge
                                                    │ HTTPS Chat Completions
                                                    └── USAi / another gateway
```

Experimental integration; human review is required before production use.
See [the architecture decision](docs/decisions/0001-session-local-litellm.md).

## Requirements

- A released acq with neutral `hybrid/v1` kit support, terminal access, and
  [authoritative provider-input materialization](https://github.com/GSA-TTS/agentic-coding-patterns/blob/main/integrations/isolation/docs/provider-input-contract.md).
- A **glibc Linux x64 or ARM64** guest with Python **3.12–3.14**, stdlib `venv`,
  system CA certificates, and `~/.local/bin` on the non-interactive PATH.
- A provider kit, such as [`usai-provider`](https://github.com/GSA-TTS/agentic-coding-patterns/tree/main/integrations/isolation/acq-kits/usai-provider), that supplies
  `facts.json`, `snapshot.json`, and provider egress. Credentials are injected
  through acq's backend secret mechanism, never through `spec.yaml`.
- Sufficient disk/memory: the Claude binary is approximately 300 MB, plus the
  Python bridge and its dependencies. No Node runtime is needed by this kit.

The `agent.name` token is **`claude`**, while this directory is `claude-code`.
That matches Claude's executable and the existing harness readiness declaration.
This does not add a new built-in kit mapping to acq itself. Explicitly apply the
kit if your acq release does not map the `claude` token to this directory.

## Apply and reach the TUI from the host

Select the Claude kit and your provider kit through acq's extra-kit mechanism.
For a local checkout (substitute your absolute checkout path):

```bash
acq --backend msb run shell /path/to/workspace --kit /path/to/agentic-coding-kits/claude-code
```

This uses a shell launch target; invoke `claude` inside the attached guest shell.
It avoids assuming this externally distributed kit has an acq built-in mapping.
For a GitHub-distributed kit, authorize `github.com/mogul/` through
`ACQ_EXTRA_KIT_SOURCES` and use a full commit SHA:

```bash
ACQ_EXTRA_KIT_SOURCES="github.com/mogul/" acq --backend msb run shell /path/to/workspace --kit 'git+https://github.com/mogul/agentic-coding-kits.git#ref=<FULL_COMMIT_SHA>&dir=claude-code'
```

This assumes your acq configuration already selects `usai-provider` and injects
its credential. Follow the provider kit's setup instructions. Inspect your
release's `acq run --help` for kit selection if its interface differs. The
startup install is awaited, but the launcher also checks provider readiness at
each invocation: a missing projection fails, it never uses stale global config.

For an existing sandbox, use its acq interactive terminal/exec interface to run
`claude`. Do not run the host's own Claude executable against a forwarded model
port: that would execute tools on the host rather than inside the microVM.

## Provider and model selection

The launcher reads `$ACQ_PROVIDER_INPUT_ROOT/models/providers/<id>`.
One provider is selected automatically; zero or several require an explicit
`ACQ_CLAUDE_PROVIDER`. No backend paths or credential values are hardcoded.

| Non-secret guest variable | Meaning |
|---|---|
| `ACQ_CLAUDE_PROVIDER` | Selected provider directory ID, for example `usai` |
| `ACQ_CLAUDE_MODEL` | Main and Sonnet-alias model ID |
| `ACQ_CLAUDE_SMALL_MODEL` | Haiku-alias model ID |
| `ACQ_CLAUDE_OPUS_MODEL` | Opus-alias model ID; otherwise the main model |

Provider recommendations supply `primary` and `small` when overrides are absent.
A single-model catalog needs no recommendation; otherwise choose a main model.
For example, USAi's snapshot recommends `claude-sonnet-5` and
`claude_4_5_haiku`. An Opus choice can be supplied explicitly. Every choice must
exist in the selected snapshot. `/model` or `--model` can select another model
from that same provider; the proxy rejects unknown IDs. Other OpenAI-shaped
providers work through the same contract, but must support **Chat Completions,
streaming, and function tools**. Model-specific capabilities require testing.

## Browser/port access from outside the VM

For a browser UI, compose this kit with the existing [`paseo`](https://github.com/GSA-TTS/agentic-coding-patterns/tree/main/integrations/isolation/acq-kits/paseo) kit.
Paseo launches the guest's `claude` executable; that is this kit's wrapper, so
each UI-launched session gets the same provider routing. Select Claude as the
agent in Paseo. Use `acq ports <sandbox>` to find the **host-loopback** mapping
for guest **6767**, then open that address in your host browser.

Paseo supplies `publishedPorts` and binds the **guest network interface**, which
MSB's publisher needs; a guest-loopback-only UI would not be reachable via that
publisher. This kit deliberately publishes **no** model-proxy port. Its random
port is authenticated and loopback-only. Port forwarding the proxy provides an
API, not a Claude UI or remote guest tool execution.

The existing Paseo kit is unauthenticated and intended for a trusted single-user
host. Do not expose its port to a LAN or the Internet. Remote-machine browser
access needs an authenticated, approved access layer; it is not provided here.
Claude's cloud Remote Control is not a local browser server and is not enabled.
Browser access and Sonnet 5/5.5 model calls were confirmed by the operator on
MSB 0.7.7 with the tested acq checkout. This does not establish every browser
feature or model is supported; see the verification record.

### Known limitation: the browser lists more models than are available

Paseo 0.13.0 and the examined 0.14.0 source retain native Claude model choices
even when Claude advertises a restricted gateway catalog. **Fewer models are
actually available than the browser picker shows.** Availability is determined
by the **configured OpenAI-shaped model provider**, not by the displayed list.
Only provider model IDs and the kit's explicitly supported equivalent names can
be used; other choices fail rather than silently selecting a different model.
Extended-context variants are not implied supported by a matching base model.

Tracked upstream: [getpaseo/paseo#8321](https://github.com/getpaseo/paseo/issues/8321).
The Claude kit supplies the restricted SDK catalog and verified substitutions;
the Paseo kit remains a browser-access component, not a second catalog projector.

### Claude-owned model catalog

The default Claude picker can show first-party aliases or dated
Anthropic IDs that are absent from USAi. The proxy rejects those IDs; matching
display names are not a routing contract. The wrapper reads the snapshot on each
launch and supplies temporary Claude settings: `availableModels`,
`enforceAvailableModels`, and `modelPicker` with `replaceBuiltInOptions: true`.
The picker contains exact gateway IDs, and Default resolves to the chosen primary
model. This changes the actual Claude SDK `supportedModels()` response, verified
with the pinned CLI, rather than projecting a second catalog into Paseo config.

No global Claude settings or Paseo settings are rewritten. Existing explicit SDK
`--settings` are composed so hooks and permissions survive; only model catalog
fields are owned by this kit. CLI `--model` still selects an exact gateway ID.
An explicit `modelOverrides` map translates a small set of same-version canonical
Claude names, such as `claude-sonnet-5-5` to `claude-sonnet-5.5`, only when the
target exists in the snapshot and the source is not itself a gateway ID. No fuzzy
matching, extended-context suffix stripping, or unrelated-model substitution.
The real SDK model-switch probe confirms the mapped gateway ID on the wire. The proxy
continues enforcing exact snapshot membership independently of Claude settings.

Paseo must refresh its Claude discovery after re-applying this kit; a daemon
restart interrupts guest sessions and should be scheduled by the operator. An
installed Paseo release may still merge a curated fallback catalog; the actual
browser list must be checked, not assumed from SDK discovery alone. Non-Anthropic
IDs in the snapshot are listed too, but their behavior is not implied validated.

## Installation and lifecycle

- Claude Code **2.1.314**: direct npm **platform tarball**, with independent
  SHA-256 pins for x64 and ARM64. Only the regular `package/claude` member is
  extracted after verification; no upstream install script is executed.
- LiteLLM **1.100.4** library, MCP import dependency, FastAPI and Uvicorn:
  an exact, universal, hash-locked wheel-only dependency set. No LiteLLM
  management UI, database, full proxy service, plugins, or callbacks.
- pip **26.2.2** is bootstrapped from a SHA-256-verified universal wheel into a
  `venv --without-pip`. No system pip, ensurepip package, sudo, or remote bootstrap
  script is needed. This works with the lean Ubuntu guest's split Python packaging.
- Startup installs as the **unprivileged agent**, in
  `~/.local/share/acq/claude-code`. The version/lock stamp avoids repeated
  downloads. Failed installation is visible and no readiness stamp is written.
- Every session binds its own ephemeral loopback socket before spawning the
  proxy, waits for server readiness, then starts Claude. Exit terminates only
  that proxy child. No PID files, global process kills, shared port, or daemon.
  SIGTERM/SIGHUP cleanup also terminates the invocation's Claude process group
  and tool descendants; foreground PTY ownership is handed to Claude and restored.
- User `~/.claude` and project settings are not overwritten. Automatic updates
  and nonessential traffic are disabled in the child environment; no permission
  bypass is enabled. User hooks/MCP configuration remain the operator's responsibility.

## Security and compatibility limits

The backend-owned read-only provider mount is the routing trust boundary.
The kit checks versions, identities, HTTPS hosts, duplicate keys/models, and
symlinked provider entries. It does not implement the backend's mount enforcement.
Provider keys exist only in the injected environment and proxy process memory;
the launcher removes the upstream key and `GITHUB_TOKEN` from Claude's child
environment. This is defense in depth, **not isolation from an agent with shell
access or sudo**. Do not treat same-user processes as a credential boundary.

The facade accepts only Messages and token-count requests, with a per-session
random authentication token. Client-supplied API URLs, credentials, callbacks,
and provider choices do not reach LiteLLM. Upstream exception bodies and access
logs are suppressed to avoid logging prompts or keys. Provider egress belongs to
the provider kit; installation egress is limited to npm and PyPI hosts. TLS
verification stays enabled; use the CA kit for enterprise trust, never bypass it.

USAi streaming tool chunks can repeat the same call ID on every argument fragment.
The kit normalizes those translated SSE blocks into one tool call so Claude sees
complete JSON arguments. Distinct IDs remain distinct calls. The live CLI file-read
test covers the resulting tool call and tool-result continuation.

Supported: ordinary text, streaming text, function-tool calls and results.
Not promised: extended thinking, native server tools/search, prompt-cache
semantics, native compaction, PDF/image/audio behavior, or exact token counts.
Anthropic-only optional fields are not forwarded; thinking/beta/tool-search
features are disabled. The token-count route returns a deliberately conservative
UTF-8-byte estimate, **not Anthropic's tokenizer**. Context utilization may be
overestimated. Do not use the result for billing or capacity guarantees.

Claude Code is **proprietary**, governed by Anthropic's terms, not this repo's
MIT license. Its npm installer is deprecated upstream; this kit deliberately
uses the still-published native platform artifacts to avoid executing remote
installer scripts. LiteLLM, FastAPI, Uvicorn, and MCP SDK licenses must be
reviewed with the locked dependency inventory. No upstream skill or prompt body
has been copied; these packages are dependencies, not vendored source.

## Verification

See the [verification record](docs/verification.md) for observed live results,
review findings addressed, and pending microVM/browser validation gates.

```bash
make setup
make validate
make test
.tmp/ci-venv/bin/python claude-code/scripts/verify
```

The shared checks require a pinned Patterns checkout as described in the
repository README. `scripts/verify --acq /absolute/path/to/acq --sandbox <name>`
selects the tested host executable rather than an older Homebrew installation.

`scripts/verify` runs offline checks and returns **3 (unverified)** until required
live checks are confirmed. Supply an existing, configured sandbox via
`--sandbox <name>` to probe the real wrapper's version and a small live Claude
prompt through `acq exec`. It never creates or deletes a VM. Failures return 1;
successful automated probes still return 3 pending manual interactive PTY
validation. See [troubleshooting](TROUBLESHOOTING.md).

To refresh the bridge lock, use `uv pip compile requirements.in --python-version
3.12 --universal --generate-hashes --only-binary :all: --output-file
requirements.lock` from the payload directory. Audit and re-test after every
pin change. Claude hashes must be re-derived from both platform artifacts.

The repository's kit test runner provisions the locked bridge and pytest in an isolated temporary
environment (Python venv/pip, or installed uv), including on clean CI workers.
It makes package-registry requests; it does not add global dependencies.

## Backend parity

SBX and MSB use the same neutral files, awaited unprivileged startup command,
agent declaration, and provider-input root. No backend shortcut or published
port is required for the TUI. Both must supply a PTY for interactive operation
and an authoritative read-only provider tree. MicroVM boot, interactive PTY,
and optional Paseo composition remain live-host verification requirements.
