# opencode-go-provider (acq mixin kit, `hybrid/v1`)

> **Status: Preview.** The facts, catalog, normalizer, and tests are complete and
> contract-validated, but this kit is **not yet usable with `acq run`/`acq create`**.
> Create-time provider-input materialization fails until the pinned Patterns
> release binds the provider in `provider-credential-bindings.json`:
> `"opencode-go": "OPENCODE_GO_API_KEY"`. Until then the exact failure is
> `facts.keyEnv must match the host credential binding`. See
> [Status and create-time materialization](#status-and-create-time-materialization).

A harness-agnostic [`acq`](https://github.com/GSA-TTS/agentic-coding-quickstart)
provider kit for **OpenCode Go**. It publishes provider facts and a neutral model
catalog; it does not configure any particular coding agent.

The kit is intentionally not named `opencode-go-opencode-provider`. "OpenCode"
in the provider name is the *service* (OpenCode Go), not the harness. A harness
that speaks the OpenAI-compatible protocol and honors OpenCode Go's session and
user-agent expectations can consume this kit's output, and a separate harness kit
remains the sole writer of that harness's configuration. See
[Preconditions OpenCode Go imposes](#preconditions-opencode-go-imposes) for the
qualifications behind that claim.

## Interface

`provider-input.json` declares the provider bundle:

| Field | Value |
| --- | --- |
| `providerId` | `opencode-go` |
| `apiProtocol` | `openai-compatible` |
| `host` | `opencode.ai` |
| `baseUrl` | `https://opencode.ai/inference/go/openai/v1` |
| `modelsUrl` | `https://opencode.ai/inference/go/v1/models` |
| `keyEnv` | `OPENCODE_GO_API_KEY` |

`acq` validates the bundle, materializes the provider under the backend-supplied
input root, and exposes a selected generation at
`current/models/providers/opencode-go/`. A harness renderer (for OpenCode, the
OpenCode kit) reads that generation and maps the neutral facts onto its own
configuration vocabulary. The catalog snapshot is model metadata only;
credentials remain acq-managed.

## What it does

- Allow-lists `opencode.ai` through `caps.network.allow`.
- Supplies facts, normalizer, and snapshot paths through `provider-input.json`.
- Drops a neutral catalog snapshot at
  `/home/agent/opencode-go/model-catalog-snapshot.json` (mode `0644`).
- Does **not** install harness-specific files, write global config, or run a
  startup writer. It also declares no `environment:` block; see
  [Deliberate choices](#deliberate-choices-skip-rationale).

## Protocol coverage and the allowlist

OpenCode Go routes different models over different wire protocols. This kit
declares `openai-compatible` only, so the catalog contains exactly the **18
entries in the Go docs endpoint table that use
`https://opencode.ai/inference/go/openai/v1/chat/completions`** (17 paid models
plus Beam Free):

| Model | Model ID |
| --- | --- |
| GLM-5.3-Flash | `glm-5.3-flash` |
| GLM-5.3 | `glm-5.3` |
| GLM-5.2 | `glm-5.2` |
| Kimi K3.1 Pro | `kimi-k3.1-pro` |
| Kimi K3 | `kimi-k3` |
| Kimi K2.7 Code | `kimi-k2.7-code` |
| LongCat-2.0 | `longcat-2.0` |
| DeepSeek V4.1 Flash | `deepseek-v4.1-flash` |
| DeepSeek V4 Pro | `deepseek-v4-pro` |
| MiMo-V2.6-Flash | `mimo-v2.6-flash` |
| MiMo-V2.6-Pro | `mimo-v2.6-pro` |
| MiMo-V2.5 | `mimo-v2.5` |
| MiMo-V2.5-Pro | `mimo-v2.5-pro` |
| MiniMax M3.1 Flash | `minimax-m3.1-flash` |
| Hy4 preview | `hy4-preview` |
| Hy3 | `hy3` |
| Step 5 Preview | `step-5-preview` |
| Beam Free | `beam-free` |

`scripts/normalize-catalog.mjs` exports this list as
`OPENAI_COMPATIBLE_MODEL_IDS`, the single source of truth shared by the
normalizer and the tests. **Never feed a raw `/v1/models` response to the
normalizer.** The live endpoint returned 38 ids on 2026-10-25, mixing protocols,
free variants, stealth/experimental models, and legacy models. Any id outside
the allowlist is a hard failure, so a raw capture cannot silently publish an
unroutable model.

Excluded ids, and why:

- **Other protocols.** `grok-4.7`, `gpt-6-luna`, `gpt-5.6-luna`,
  `muse-spark-1.2-contributor`, and `muse-spark-1.3-contributor` use the OpenAI
  Responses API. `claude-haiku-5-5`, `minimax-m3`, `qwen3.8-max`, `qwen3.8-flash`,
  and `qwen3.7-plus` use the Anthropic Messages API. `gemini-4-argon` uses the
  Google Generative AI API. This kit cannot route them.
- **Free variants.** Ids ending in `-free` (for example `glm-5.3-flash-free`,
  `kimi-k2.5-free`, `longcat-2.5-preview-free`, `minimax-m3.1-flash-free`,
  `step-5-preview-free`) are promotional or limited-region aliases that are not
  in the documented endpoint table. Beam Free is the one free model the docs
  table does list, so it is included.
- **Stealth / experimental.** `space-bunny`, `cat-jam-free`,
  `iceman-contributor-free`, `omen-alpha`, `big-pickle`, and similar stealth
  aliases are unannounced, may appear or disappear without notice, and are not in
  the documented table.
- **Legacy / undocumented.** `glm-5.1`, `kimi-k2.6`, `minimax-m2.5`,
  `minimax-m2.7`, `qwen3.6-plus`, `qwen3.7-max`, and `grok-4.6` are older or
  undocumented ids that the docs no longer list as current Go models.

Adding a protocol requires widening `apiProtocol` and teaching the harness
renderer a new protocol, not appending ids to the catalog.

## Preconditions OpenCode Go imposes

A harness is only compatible if it also does what the service asks of clients:

- **Stable session header.** Send a stable `x-opencode-session` value per
  conversation so OpenCode Go can optimize routing and prompt caching. Some
  clients are recognized by their native session header, but a custom harness
  should send `x-opencode-session` explicitly.
- **Non-generic user agent.** Identify the client with its own product token
  (for example `my-coding-agent/1.0`), not a generic SDK or HTTP-library name.
- **Region settings for the recommended primary.** `deepseek-v4-pro` (and
  `deepseek-v4.1-flash`) requires the workspace **Settings › Privacy › Regions**
  setting to include **Global**. Without it, requests to those models are
  refused. This is a workspace setting, not something the kit can set.
- **Traffic shape.** The service is meant for typical coding-agent traffic;
  abuse or unusual traffic can be blocked.

Without these, an otherwise OpenAI-compatible harness may authenticate but still
behave poorly or be rejected.

## Pricing notes

All `cost` values are **USD per 1M tokens**, the neutral schema's unit.

- **DeepSeek peak/off-peak.** The neutral catalog schema has no time-of-day
  tiering. DeepSeek V4.1 Flash and V4 Pro publish peak and off-peak prices; this
  catalog records the **off-peak** price as the baseline:

  | Model | Off-peak (recorded) | Peak |
  | --- | --- | --- |
  | DeepSeek V4.1 Flash | $0.15 / $0.60 / $0.003 | $0.30 / $1.20 / $0.006 |
  | DeepSeek V4 Pro | $0.66 / $1.98 / $0.022 | $1.32 / $3.96 / $0.044 |

  (input / output / cached read). Peak hours are 01:00–04:00 and 06:00–10:00
  UTC, Monday–Friday; everything else, including weekends, is off-peak. A
  consumer that needs peak accounting must apply it itself.
- **Cache write.** `cacheWrite` is present only where OpenCode Go publishes a
  cache-write price (Kimi K3.1 Pro and Kimi K3). Elsewhere the docs show `-`,
  so the field is omitted rather than encoded as a misleading `0`.
- **Free models.** Beam Free is recorded as explicit `0` input/output/cache-read
  prices, not as a missing `cost`.
- Prices and model availability change upstream. See
  [opencode.ai/docs/go](https://opencode.ai/docs/go) for the current table.

Recommendations are advisory: `primary` = `deepseek-v4-pro` (region permitting —
see the caveat above), `small` = `glm-5.3-flash`. Downstream kits make the final
role selection.

## Status and create-time materialization

Provider input is materialized **only when a sandbox is created**
(`acq run` on a new sandbox, or `acq create`). `acq kit apply NAME KITREF` applies
a kit's spec to an existing sandbox; it does **not** re-materialize provider
input. Changing this kit's facts, catalog, or snapshot therefore requires
deleting and recreating the sandbox:

```bash
acq rm <sandbox>
acq run ...   # recreate with the same kit refs
```

Before create-time materialization can succeed, the consumer's
`provider-credential-bindings.json` must contain:

```json
{ "providers": { "opencode-go": "OPENCODE_GO_API_KEY" } }
```

Until that acq-side change lands, `acq run`/`create` fails during provider-input
validation with exactly:

```text
facts.keyEnv must match the host credential binding
```

The kit cannot supply that registry entry itself: the registry is a trusted
consumer-side control-plane input, deliberately not provider-controlled.

## Using the kit (after the credential binding lands)

The kit lives in a subdirectory of this repository and must be pinned to a
specific commit. **Use a full SHA in `#ref=`; never `#ref=main`.** A branch ref
lets a host fetch different code at a different time, which defeats the trust
boundary around provider-controlled metadata.

```bash
# acq only accepts kits from allow-listed sources. Add this repo's prefix once.
export ACQ_EXTRA_KIT_SOURCES="github.com/mogul/"

acq run opencode /path/to/project \
  --kit <opencode-agent-kit> \
  --kit "git+https://github.com/mogul/agentic-coding-kits.git#ref=<sha>&dir=opencode-go-provider"
```

The same SHA-pinned ref can go in `ACQ_EXTRA_KITS` instead of a `--kit` flag. If
your acq build exposes a dedicated provider-kit channel
(`ACQ_PROVIDER_KITS`), use the identical ref there; the SHA rule is unchanged.
The `--kit` and `ACQ_EXTRA_KITS` forms are verified against current acq.

The two kits are independent selections: this one publishes provider input, and
`<opencode-agent-kit>` writes the harness configuration that consumes it.

## Credentials

Store the API key through acq. For a custom endpoint like OpenCode Go, the
(host, env) mapping is recorded **only when both `--host` and `--env` are
supplied**:

```bash
# Global (once per machine)
acq secret set -g opencode-go --host opencode.ai --env OPENCODE_GO_API_KEY

# Sandbox-scoped
acq secret set <sandbox> opencode-go --host opencode.ai --env OPENCODE_GO_API_KEY
```

`--env` **must** equal the facts `keyEnv` (`OPENCODE_GO_API_KEY`). A bare
`acq secret set opencode-go` records no host mapping and will not inject the key
for this provider. Credential injection only occurs when the host/env mapping
was recorded.

The active backend injects `OPENCODE_GO_API_KEY` for the selected provider; the
harness renderer reads that variable by name and never receives a key value.
This repository contains no secrets.

## Catalog updates

`tests/fixtures/normalize-source.json` is an offline, curated capture of the
OpenAI-compatible models above, annotated with display name, limits, and pricing
from the Go docs. `scripts/normalize-catalog.mjs` reshapes it into
`acq-neutral-model-catalog/v1` with no network access:

```bash
npm ci
npm run sync:opencode-go-models   # rewrites files/home/opencode-go/model-catalog-snapshot.json
npm test                          # fails if the shipped snapshot has drifted
```

To refresh from upstream: fetch the models endpoint and the docs pricing table,
update the fixture, regenerate the snapshot, run the tests, and review the diff.
Do not hand-edit the snapshot — it is generated. Do not feed the raw endpoint
response to the normalizer; curate it first.

## Validation

The kit is designed to pass the `acq` provider-input contract validator from
`GSA-TTS/agentic-coding-patterns`:

```bash
python3 scripts/validate_provider_input_contract.py \
  --schema-dir integrations/isolation/schemas \
  --credential-bindings integrations/isolation/schemas/provider-credential-bindings.json \
  --bundle <path-to-this-kit>/provider-input.json
```

With a bindings file that includes `"opencode-go": "OPENCODE_GO_API_KEY"`, the
validator reports `validated 1 bundle(s)`. With the currently pinned bindings,
the credential check is the only expected failure (and it runs before the URL and
catalog checks, so use a patched bindings file to exercise those). CI in this
repository runs both the tests and the patched-bindings validation.

`tests/schemas/acq-neutral-model-catalog.schema.json` is a verbatim copy of the
pinned Patterns schema, vendored so `npm test` can check catalog conformance
offline. The authoritative check remains the validator run against the pinned
Patterns release, which CI performs.

## Trust model

The snapshot lands under `/home/agent`, which the agent owns, so it is
guest-writable and is **not** a trust anchor. It carries model metadata only
(id, name, context window, max output tokens, cost) and no host, base URL, models
URL, or credential field, so rewriting it cannot redirect a credential or point
a consumer at another host. A consumer that needs trustworthy provider facts
must read the host-materialized, read-only provider generation, never this file.

The normalizer is also materialized with the provider bundle and mounted
read-only. The agent can execute it but cannot modify it in place.

The SHA pin in the kit ref keeps a host from silently accepting different
provider-controlled code later. Credential host-pinning itself is a consumer-side
(acq) concern; this kit can only declare the correct `host`/`keyEnv` facts.

## Deliberate choices (SKIP rationale)

These were flagged during review and are intentionally unchanged:

- **Guest-writable snapshot duplicate.** Shipping
  `files/home/opencode-go/model-catalog-snapshot.json` in addition to the
  host-materialized snapshot is parity with the `usai-provider` reference kit.
  It is a convenience example, never a trust anchor; the trust rules above are
  the contract.
- **No `environment:` block.** An empty `OPENCODE_GO_API_KEY` in `spec.yaml`
  could shadow the injected placeholder. The patterns env-ownership check is
  aspirational and not currently enforced, so the block is deliberately absent.
- **Credential host-pinning is consumer-side.** The kit declares facts; acq owns
  the trusted credential registry. Requiring a SHA ref (above) is the
  provider-side mitigation.

## Layout

```text
spec.yaml                                  hybrid/v1 mixin definition
provider-input.json                        acq-provider-input-bundle/v2 manifest
provider-input/facts.json                  acq-provider-facts/v1
scripts/normalize-catalog.mjs              host-side authoring tool (executable)
files/home/opencode-go/                    snapshot payload dropped into the guest
tests/                                     node:test suites, fixture, vendored schema
docs/decisions/                            design records
```
