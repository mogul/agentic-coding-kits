# Agentic Coding Kits

Provider kits, agent kits, and skill kits for
[`acq`](https://github.com/GSA-TTS/agentic-coding-quickstart), the sandbox
wrapper used by the GSA-TTS
[agentic-coding-quickstart](https://github.com/GSA-TTS/agentic-coding-quickstart)
project.

- A **provider kit** describes a model provider once, in a harness-neutral form:
  protocol, host, base URL, models URL, credential variable name, and a neutral
  model catalog. It names no coding agent and writes no agent configuration.
- A **skill kit** drops an Agent Skill into the guest's skills root. It installs
  nothing, runs nothing, and needs no network access.
- An **agent kit** installs a coding agent and renders the selected provider
  generation into that agent's own configuration. It owns the agent config and
  nothing else.

The two compose at sandbox creation: a provider that speaks the provider's
protocol can be consumed by any agent kit that implements the neutral → harness
mapping. A skill kit is independent of both and composes with any
of them.

This repository is separate from
[agentic-coding-patterns](https://github.com/GSA-TTS/agentic-coding-patterns),
which hosts the reference `usai-provider` kit and the schemas these kits are
validated against. The contract is the same; the distribution is public and
includes both provider and agent kits.

## What a provider kit contains

A provider kit is a self-contained `hybrid/v1` mixin with three layers:

1. **Facts** (`acq-provider-facts/v1`) — the wire protocol, host, base URL,
   models URL, and the *name* of the credential environment variable. Never the
   credential itself.
2. **Bundle manifest** (`acq-provider-input-bundle/v2`) — kit-relative paths to
   the facts, the host-side normalizer, the vendored snapshot, and the
   host-materialized provider path, plus the declared credential variable names.
3. **Neutral model catalog** (`acq-neutral-model-catalog/v1`) — model ids,
   display names, context windows, output limits, and per-million-token costs.
   Metadata only: no routing or credential fields.

A provider kit also ships a `spec.yaml` (network allow-list and any guest file
drops), a normalizer for regenerating the catalog, tests, and operator docs.

## What an agent kit contains

An agent kit is a `hybrid/v1` mixin that:

1. **Installs the agent CLI** at startup, idempotently and fail-soft (an optional
   CLI must not fail sandbox creation).
2. **Renders provider input** from the read-only generation acq materializes at
   `$ACQ_PROVIDER_INPUT_ROOT/models/providers/<providerId>/` into the agent's
   native configuration. Rendering is fail-closed: a malformed or ambiguous
   generation is refused rather than guessed at.
3. **Publishes no ports** when the agent is a terminal TUI. It declares no
   `agent:` block unless acq knows the agent as a built-in launch target.

## Kits

| Kit | Kind | Provides | Status |
| --- | --- | --- | --- |
| [`opencode-go-provider/`](opencode-go-provider/) | Provider | OpenCode Go (`openai-compatible`) facts and a 19-model neutral catalog | **Preview** — blocked on the acq credential-binding addition |
| [`pi-coding-agent/`](pi-coding-agent/) | Agent | Pinned pi CLI + `~/.pi/agent/models.json` renderer | **Preview** — live verification pending acq PR 611 |
| [`first-mate-skill/`](first-mate-skill/) | Skill | The `paseo-first-mate` Agent Skill and two helper scripts, dropped into `~/.agents/skills` | Offline-verified; no live sandbox run |

**Preview status.**

- The OpenCode Go provider kit's facts, catalog, normalizer, and tests are
  complete and contract-validated. It cannot yet be materialized by `acq
  run`/`acq create` because the pinned Patterns
  `provider-credential-bindings.json` does not include
  `"opencode-go": "OPENCODE_GO_API_KEY"`. Until that consumer-side change lands,
  create-time provider-input validation fails with exactly
  `facts.keyEnv must match the host credential binding`.
- The pi agent kit is complete and its offline suite passes. Its end-to-end path
  depends on an acq build that materializes `$ACQ_PROVIDER_INPUT_ROOT` and
  exposes the `provider-credential` binding (the provider/agent decoupling in
  acq PR 611). On an older acq, pi installs but the render step reports
  `provider input not ready` and leaves `models.json` untouched.

The OpenCode Go catalog currently exposes **19 OpenAI-compatible models**: the 18
models in the Go docs endpoint table plus one active free/experimental alias
(`iceman-contributor-free`). Five deprecated aliases are intentionally excluded.

Each kit directory has its own README with specific details and a
TROUBLESHOOTING guide.

## Layout

```text
README.md                     this file
opencode-go-provider/         provider kit
  spec.yaml                   hybrid/v1 mixin definition
  provider-input.json         acq-provider-input-bundle/v2 manifest
  provider-input/facts.json   acq-provider-facts/v1
  scripts/                    authoring tools, host-materialized and read-only
  files/                      payloads dropped into the guest
  tests/                      node:test suites, fixtures, vendored schema
  docs/decisions/             design records
pi-coding-agent/              agent kit
  spec.yaml                   hybrid/v1 mixin definition (startup install + render)
  files/home/                 installer and provider-input renderer
  scripts/verify              offline gate + optional live acq/msb check
  tests/                      node:test suite, fixtures, vendored schemas
  docs/decisions/             design records
first-mate-skill/             skill kit
  spec.yaml                   hybrid/v1 mixin definition (file drops only)
  files/home/.agents/skills/  the paseo-first-mate skill and its assets
  scripts/verify              offline gate
  docs/decisions/             design records
```

New kits follow the same directory contract and get a row in the table above.

## Using kits

Provider input is materialized **at sandbox create time only**. `acq kit apply`
applies a kit's spec to an existing sandbox; it does not refresh provider input.
Changing a kit therefore requires recreating the sandbox.

Kits live in subdirectories and must be pinned to a full commit SHA. Never use
`#ref=main`: a branch ref lets the host fetch different provider-controlled code
at a different time.

```bash
# acq only accepts kits from allow-listed source prefixes.
export ACQ_EXTRA_KIT_SOURCES="github.com/mogul/"

# Provider kit + an agent kit (here: pi) in one sandbox.
acq --backend msb run opencode /path/to/project \
  --kit "git+https://github.com/mogul/agentic-coding-kits.git#ref=<full-sha>&dir=opencode-go-provider" \
  --kit "git+https://github.com/mogul/agentic-coding-kits.git#ref=<full-sha>&dir=pi-coding-agent"

# pi is an opt-in --kit mixin, not an acq built-in launch target.
acq --backend msb exec <sandbox> -- pi --list-models
```

The `opencode` positional argument names the sandbox's launch target; it does
not imply the agent kit is an OpenCode kit. `pi` is installed by the mixin and
run explicitly.

The same SHA-pinned ref works in `ACQ_EXTRA_KITS`; in acq builds that expose a
dedicated provider-kit channel (`ACQ_PROVIDER_KITS`), use it there with the same
SHA rule.

Kits never contain secrets. Register the provider credential binding by name,
then let acq inject the value at runtime:

```bash
# Custom endpoint: both --host and --env are required; the mapping is not
# recorded otherwise. --env must equal the provider kit's facts.keyEnv.
acq provider-credential set opencode-go OPENCODE_GO_API_KEY --host opencode.ai

# Store the value itself through the existing secret flow:
acq secret set -g opencode-go --host opencode.ai --env OPENCODE_GO_API_KEY
# or, sandbox-scoped:
acq secret set <sandbox> opencode-go --host opencode.ai --env OPENCODE_GO_API_KEY
```

Injection happens only when the binding was recorded, and the harness renderer
reads the variable by name.

## Validating a kit

Provider kits are validated with the host-time contract validator from
`agentic-coding-patterns`:

```bash
python3 scripts/validate_provider_input_contract.py \
  --schema-dir integrations/isolation/schemas \
  --credential-bindings integrations/isolation/schemas/provider-credential-bindings.json \
  --bundle <path-to-kit>/provider-input.json
```

The validator enforces JSON Schema conformance, kit-relative artifact paths, no
symlinked path components, an executable normalizer, host allow-listing, URL/host
agreement, and catalog validity (including recommendation cross-references). A
provider kit also needs a matching entry in the consumer's
`provider-credential-bindings.json`; that binding is owned by the consumer
repository, not by this one. With a bindings file that includes the provider,
the validator reports `validated 1 bundle(s)`; the repository CI runs that form.

Agent kits use `npm test` plus their own `scripts/verify` gate:

```bash
cd pi-coding-agent
npm ci
npm test
scripts/verify            # offline
RUN_ACQ=1 scripts/verify  # live acq/msb
```

## Adding a kit

1. Copy the structure of an existing kit of the same kind.
2. For a provider kit, fill in facts and the bundle manifest. Keep
   `providerId`, `keyEnv`, and `providerPath` consistent.
3. For an agent kit, install a pinned CLI and render only the neutral vocabulary
   into the agent's own config. Fail closed on malformed input and fail soft on
   install availability.
4. Curate the catalog to the models reachable over the declared protocol. Do not
   list a model you cannot route, and do not derive the list from a raw models
   endpoint.
5. Add tests and a drift gate (for provider catalogs) or a renderer suite (for
   agent kits).
6. Document pricing and mapping decisions in the kit README and
   `docs/decisions/`.
7. Run the tests, the contract validator (provider kits), and `scripts/verify`
   before opening a pull request.

## Security

- No API keys, tokens, or credentials belong in this repository. Facts reference
  credentials by environment-variable name only.
- A vendored snapshot dropped under `/home/agent` is agent-writable and is not a
  trust anchor. It carries metadata only, by design, so it cannot redirect a
  credential or a provider host.
- Agent renderers read the host-materialized provider generation, validate it
  fail-closed, and write only the agent's own config.
- Report vulnerabilities as described in [`SECURITY.md`](SECURITY.md).

## License

MIT — see [`LICENSE`](LICENSE).
