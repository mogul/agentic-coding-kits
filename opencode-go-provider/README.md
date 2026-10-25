# opencode-go-provider (acq mixin kit, `hybrid/v1`)

A harness-agnostic [`acq`](https://github.com/GSA-TTS/agentic-coding-quickstart)
provider kit for **OpenCode Go**. It publishes provider facts and a neutral model
catalog; it does not configure any particular coding agent.

The kit is intentionally not named `opencode-go-opencode-provider`. "OpenCode"
in the provider name is the *service* (OpenCode Go), not the harness. Any agent
that speaks the OpenAI-compatible protocol can consume this kit's output, and a
separate harness kit remains the sole writer of that harness's configuration.

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
  startup writer.

## Protocol coverage

OpenCode Go routes different models over different wire protocols. This kit
declares `openai-compatible` only, so the catalog contains **only** models served
over `https://opencode.ai/inference/go/openai/v1/chat/completions`:

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

Models that OpenCode Go serves only over the Anthropic Messages
(`gemini-4-argon`, `claude-haiku-5-5`, `minimax-m3`, `qwen3.8-max`,
`qwen3.8-flash`, `qwen3.7-plus`), Google Generative AI (`gemini-4-argon`), or
OpenAI Responses (`grok-4.7`, `gpt-6-luna`, `gpt-5.6-luna`,
`muse-spark-1.2-contributor`, `muse-spark-1.3-contributor`) endpoints are
**deliberately absent**. A catalog entry for a model this provider input cannot
route would be a bug, not extra coverage. Adding them requires widening
`apiProtocol` and teaching the harness renderer a new protocol, not just adding
ids to this file.

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

Recommendations are advisory: `primary` = `deepseek-v4-pro`, `small` =
`glm-5.3-flash`. Downstream kits make the final role selection.

## Using the kit

Once this repository is published, apply the kit by ref:

```bash
acq apply --kit git+https://github.com/mogul/agentic-coding-kits.git#opencode-go-provider
```

Store the API key through acq rather than in a file:

```bash
acq secret set opencode-go --host opencode.ai
```

The active backend injects `OPENCODE_GO_API_KEY` for the selected provider. The
harness renderer references the environment-variable name from provider facts
and never receives a key value. This repository contains no secrets.

## Catalog updates

`tests/fixtures/normalize-source.json` is an offline capture of
`https://opencode.ai/inference/go/v1/models`, restricted to the
OpenAI-compatible models above and annotated with display name, limits, and
pricing from the Go docs. `scripts/normalize-catalog.mjs` reshapes it into
`acq-neutral-model-catalog/v1` with no network access:

```bash
npm run sync:opencode-go-models   # rewrites files/home/opencode-go/model-catalog-snapshot.json
npm test                          # fails if the shipped snapshot has drifted
```

To refresh from upstream: fetch the models endpoint and the docs pricing table,
update the fixture, regenerate the snapshot, run the tests, and review the diff.
Do not hand-edit the snapshot — it is generated.

## Validation

The kit is designed to pass the `acq` provider-input contract validator from
`GSA-TTS/agentic-coding-patterns`:

```bash
python3 scripts/validate_provider_input_contract.py \
  --schema-dir integrations/isolation/schemas \
  --credential-bindings integrations/isolation/schemas/provider-credential-bindings.json \
  --bundle <path-to-this-kit>/provider-input.json
```

`opencode-go` must also be bound in the consumer's
`provider-credential-bindings.json` (`"opencode-go": "OPENCODE_GO_API_KEY"`).
That binding lives in the consumer repository, not here; until it lands, the
validator's credential-binding check is the one expected failure.

## Trust model

The snapshot lands under `/home/agent`, which the agent owns, so it is
guest-writable and is **not** a trust anchor. It carries model metadata only
(id, name, context window, max output tokens, cost) and no host, base URL, models
URL, or credential field, so rewriting it cannot redirect a credential or point
a consumer at another host. A consumer that needs trustworthy provider facts
must read the host-materialized, read-only provider generation, never this file.

## Layout

```text
spec.yaml                                  hybrid/v1 mixin definition
provider-input.json                        acq-provider-input-bundle/v2 manifest
provider-input/facts.json                  acq-provider-facts/v1
scripts/normalize-catalog.mjs              host-side authoring tool (executable)
files/home/opencode-go/                    snapshot payload dropped into the guest
tests/                                     node:test suite + authoring fixture
docs/decisions/                            design records
```
