# Agentic Coding Kits

Provider kits for [`acq`](https://github.com/GSA-TTS/agentic-coding-quickstart),
the sandbox wrapper used by the GSA-TTS
[agentic-coding-quickstart](https://github.com/GSA-TTS/agentic-coding-quickstart)
project. Each kit describes a model provider once, in a harness-neutral form, so
a coding agent that speaks the provider's protocol — and honors any client
expectations the service imposes, such as OpenCode Go's session header and
user-agent — can consume it.

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
normalizer for regenerating the catalog, tests, and operator docs.

## Kits

| Kit | Provider | Protocol | Status |
| --- | --- | --- | --- |
| [`opencode-go-provider/`](opencode-go-provider/) | OpenCode Go | `openai-compatible` | **Preview** — blocked on the acq credential-binding addition |

**Preview status.** The OpenCode Go kit's provider facts, catalog, normalizer,
and tests are complete and contract-validated. It cannot yet be materialized by
`acq run`/`acq create` because the pinned Patterns
`provider-credential-bindings.json` does not include
`"opencode-go": "OPENCODE_GO_API_KEY"`. Until that consumer-side change lands,
create-time provider-input validation fails with exactly
`facts.keyEnv must match the host credential binding`. See the kit README's
"Status" section.

The OpenCode Go catalog currently exposes **19 OpenAI-compatible models**: the 18
models in the Go docs endpoint table plus one active free/experimental alias
(`iceman-contributor-free`). Five deprecated aliases are intentionally excluded.

Each kit directory has its own README with provider-specific details and a
TROUBLESHOOTING guide.

## Layout

```text
README.md                     this file
opencode-go-provider/         one complete provider kit
  spec.yaml                   hybrid/v1 mixin definition
  provider-input.json         acq-provider-input-bundle/v2 manifest
  provider-input/facts.json   acq-provider-facts/v1
  scripts/                    authoring tools, host-materialized and read-only
  files/                      payloads dropped into the guest
  tests/                      node:test suites, fixtures, vendored schema
  docs/decisions/             design records
```

New kits follow the same directory contract and get a row in the table above.

## Using a kit

Provider input is materialized **at sandbox create time only**. `acq kit apply`
applies a kit's spec to an existing sandbox; it does not refresh provider input.
Changing a kit therefore requires recreating the sandbox.

The kit lives in a subdirectory and must be pinned to a full commit SHA. Never
use `#ref=main`: a branch ref lets the host fetch different provider-controlled
code at a different time.

```bash
# acq only accepts kits from allow-listed source prefixes.
export ACQ_EXTRA_KIT_SOURCES="github.com/mogul/"

acq run opencode /path/to/project \
  --kit <opencode-agent-kit> \
  --kit "git+https://github.com/mogul/agentic-coding-kits.git#ref=<full-sha>&dir=opencode-go-provider"
```

The same SHA-pinned ref works in `ACQ_EXTRA_KITS`; in acq builds that expose a
dedicated provider-kit channel (`ACQ_PROVIDER_KITS`), use it there with the same
SHA rule.

Kits never contain secrets. Store provider credentials through `acq secret`.
For a custom endpoint, both `--host` and `--env` are required — the mapping is
not recorded otherwise:

```bash
acq secret set -g opencode-go --host opencode.ai --env OPENCODE_GO_API_KEY
# or, sandbox-scoped:
acq secret set <sandbox> opencode-go --host opencode.ai --env OPENCODE_GO_API_KEY
```

`--env` must equal the kit's `facts.keyEnv`. Injection happens only when that
mapping was recorded, and the harness renderer reads the variable by name.

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
repository, not by this one. With a bindings file that includes the provider,
the validator reports `validated 1 bundle(s)`; the repository CI runs that form.

## Adding a kit

1. Copy the structure of an existing kit.
2. Fill in facts and the bundle manifest. Keep `providerId`, `keyEnv`, and
   `providerPath` consistent.
3. Curate the catalog to the models reachable over the declared protocol. Do not
   list a model you cannot route, and do not derive the list from a raw models
   endpoint.
4. Add a pure, host-side normalizer plus a drift-gated test suite.
5. Document pricing decisions (tiers, peak hours, free models) in the kit README.
6. Run the tests and the contract validator before opening a pull request.

## Security

- No API keys, tokens, or credentials belong in this repository. Facts reference
  credentials by environment-variable name only.
- A vendored snapshot dropped under `/home/agent` is agent-writable and is not a
  trust anchor. It carries metadata only, by design, so it cannot redirect a
  credential or a provider host.
- Report vulnerabilities as described in [`SECURITY.md`](SECURITY.md).

## License

MIT — see [`LICENSE`](LICENSE).
