# Agentic Coding Kits

Provider kits for [`acq`](https://github.com/GSA-TTS/agentic-coding-quickstart),
the sandbox wrapper used by the GSA-TTS
[agentic-coding-quickstart](https://github.com/GSA-TTS/agentic-coding-quickstart)
project. Each kit describes a model provider once, in a harness-neutral form, so
any coding agent that speaks the provider's protocol can consume it.

This repository is separate from
[agentic-coding-patterns](https://github.com/GSA-TTS/agentic-coding-patterns),
which hosts the reference `usai-provider` kit and the schemas these kits are
validated against. The contract is the same; the distribution is public and
provider-focused.

## What a provider kit contains

A kit is a self-contained `hybrid/v1` mixin with three layers:

1. **Facts** (`acq-provider-facts/v1`) — the wire protocol, host, base URL,
   models URL, and the *name* of the credential environment variable. Never the
   credential itself.
2. **Bundle manifest** (`acq-provider-input-bundle/v2`) — kit-relative paths to
   the facts, the host-side normalizer, the vendored snapshot, and the
   host-materialized provider path, plus the declared credential variable names.
3. **Neutral model catalog** (`acq-neutral-model-catalog/v1`) — model ids,
   display names, context windows, output limits, and per-million-token costs.
   Metadata only: no routing or credential fields.

A kit also ships a `spec.yaml` (network allow-list and any guest file drops), a
host-side normalizer for regenerating the catalog, tests, and operator docs.

## Kits

| Kit | Provider | Protocol | Status |
| --- | --- | --- | --- |
| [`opencode-go-provider/`](opencode-go-provider/) | OpenCode Go | `openai-compatible` | Active |

Each kit directory has its own README with provider-specific details and a
TROUBLESHOOTING guide.

## Layout

```text
README.md                     this file
opencode-go-provider/         one complete provider kit
  spec.yaml                   hybrid/v1 mixin definition
  provider-input.json         acq-provider-input-bundle/v2 manifest
  provider-input/facts.json   acq-provider-facts/v1
  scripts/                    host-side authoring tools (never shipped to guests)
  files/                      payloads dropped into the guest
  tests/                      node:test suite and authoring fixtures
  docs/decisions/             design records
```

New kits follow the same directory contract and get a row in the table above.

## Using a kit

Apply a kit by repository ref, with the kit directory as the fragment:

```bash
acq apply --kit git+https://github.com/mogul/agentic-coding-kits.git#opencode-go-provider
```

Kits never contain secrets. Store provider credentials through `acq secret`, for
example:

```bash
acq secret set opencode-go --host opencode.ai
```

The active backend injects the credential under the name declared in the kit's
facts (`OPENCODE_GO_API_KEY` for OpenCode Go).

## Validating a kit

Kits are validated with the host-time contract validator from
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
kit also needs a matching entry in the consumer's
`provider-credential-bindings.json`; that binding is owned by the consumer
repository, not by this one.

## Adding a kit

1. Copy the structure of an existing kit.
2. Fill in facts and the bundle manifest. Keep `providerId`, `keyEnv`, and
   `providerPath` consistent.
3. Curate the catalog to the models reachable over the declared protocol. Do not
   list a model you cannot route.
4. Add a pure, host-side normalizer plus a drift-gated test suite.
5. Document pricing decisions (tiers, peak hours, free models) in the kit README.
6. Run the tests and the contract validator before opening a pull request.

## Security

- No API keys, tokens, or credentials belong in this repository. Facts reference
  credentials by environment-variable name only.
- A vendored snapshot dropped under `/home/agent` is agent-writable and is not a
  trust anchor. It carries metadata only, by design, so it cannot redirect a
  credential or a provider host.
- Report security issues privately rather than in a public issue.
