# Decision: render the neutral provider generation into pi's `models.json`

**Status:** accepted (2026-10-26)

## Context

acq is separating provider input from agent configuration. A provider kit
publishes:

- `acq-provider-facts/v1` — protocol, host, base URL, models URL, credential
  **name**;
- `acq-neutral-model-catalog/v1` — model metadata only.

acq validates the bundle host-side, materializes a read-only generation, and
mounts it in the guest at:

```text
$ACQ_PROVIDER_INPUT_ROOT/models/providers/<providerId>/facts.json
$ACQ_PROVIDER_INPUT_ROOT/models/providers/<providerId>/snapshot.json
```

The agent kit is the sole writer of that agent's own config. pi reads custom
providers and models from `~/.pi/agent/models.json` (or
`$PI_CODING_AGENT_DIR/models.json`). Its schema is published at
`https://pi.dev/schemas/models.schema.json`.

## Decision

1. **Read only the host-materialized generation.** The renderer never reads the
   provider kit's guest-writable convenience snapshot. It reads
   `$ACQ_PROVIDER_INPUT_ROOT` (defaulting to `/var/lib/acq/provider-input`), so
   the trust boundary is acq's read-only projection.

2. **A missing provider root means "not ready", not "empty".** If
   `models/providers` does not exist, the renderer returns `not-ready` and
   leaves any existing `models.json` untouched. Erasing a working config because
   acq has not materialized input yet would be a regression, not a cleanup. An
   existing but empty provider directory is authoritative and produces
   `providers: {}`.

3. **Validate fail-closed before writing.** Every input must satisfy:

   - `facts.schemaVersion === "acq-provider-facts/v1"`
   - `snapshot.schemaVersion === "acq-neutral-model-catalog/v1"`
   - `facts.providerId === snapshot.providerId === <directory name>`
   - `providerId` and `keyEnv` use the schemas' full-match patterns
     (`(?![\\s\\S])`, not `$`, so a trailing newline is rejected)
   - `baseUrl` and `modelsUrl` start with lowercase `https://`, are within the
     schema length limit, and have no credentials, port, query, or fragment;
     their hostname equals `facts.host` case-insensitively
   - `apiProtocol` is a protocol this renderer implements
   - model ids, display names, and recommendations obey the schema's
     control-character and length limits
   - model ids are non-empty and unique; `models[]` may legitimately be empty
   - `contextWindow` and `maxOutputTokens` are positive integers
   - costs are finite non-negative numbers
   - no unknown fields appear in facts, catalog, model, or cost objects
   - provider directories and `facts.json`/`snapshot.json` are not symlinks

   Any failure aborts the whole render with a precise message. It never writes a
   partial or plausibly-wrong config.

4. **Map only the bounded neutral vocabulary.** Facts and models map as:

   | Neutral | pi |
   | --- | --- |
   | `providerId` | `providers.<id>` |
   | `baseUrl` | `providers.<id>.baseUrl` |
   | `openai-compatible` | `providers.<id>.api = "openai-completions"` |
   | `keyEnv` | `providers.<id>.apiKey = "$KEY_ENV"` |
   | — | `providers.<id>.authHeader = true` |
   | `models[].id` | `models[].id` |
   | `models[].name` | `models[].name` (fallback: id) |
   | `models[].contextWindow` | `models[].contextWindow` |
   | `models[].maxOutputTokens` | `models[].maxTokens` |
   | `cost.{input,output,cacheRead,cacheWrite}` | same fields, missing → `0` |

   pi's `ModelCost` requires all four cost fields. The neutral schema makes them
   optional, so absent values become `0` rather than failing the provider.

   The credential is a `$NAME` environment reference. acq injects the value at
   runtime; the renderer never sees or writes it.

5. **Support one protocol only.** `openai-compatible` maps to pi's
   `openai-completions` API. Other neutral protocols are rejected until a
   correct adapter is implemented. Listing models under a protocol pi cannot
   speak would produce a list that looks valid and fails at request time.

6. **Map tiered neutral pricing to pi tiers.** A
   `costAbove200kContext` object becomes
   `cost.tiers = [{ inputTokensAbove: 200000, … }]`, preserving upstream
   pricing instead of silently dropping it. Both surfaces trigger on input above
   200,000 tokens; pi applies the highest matching request-wide tier, which is
   the closest supported representation of the neutral context-window tier. If
   the neutral entry has a tier but no base cost, pi's required base fields are
   emitted as `0`.

7. **Write atomically and authoritatively.** The renderer creates the config
   directory, writes a `0600` temporary file in the same directory with `wx`,
   `fsync`s it, renames it over the target, and best-effort `fsync`s the
   directory. `rename` replaces a symlink at the target rather than following
   it. The output is deterministic: providers sorted by id, models in catalog
   order. `models.json` is kit-owned; personal overrides belong in a separate
   surface.

8. **Keep recommendations advisory and validated.** Neutral role
   recommendations are checked for shape and cross-reference integrity, then
   ignored. pi has its own model-selection surfaces, and inventing a default
   model would be a policy decision this kit is not chartered to make.

## Considered alternatives

- **Merge with an existing `models.json`.** Rejected for this first version:
  without ownership metadata, a merge cannot distinguish a stale kit-written
  provider from a user-written one, and the fail-closed choice is to state that
  the file is kit-owned. A future version could add digest ownership metadata,
  as the OpenCode renderer does.
- **Write a pi extension instead of `models.json`.** Rejected: `models.json` is
  the documented, first-class surface for custom providers and models, and it is
  what `pi --list-models` reads.
- **Pass provider config through environment or CLI flags.** Rejected: pi's
  provider catalog is file-based, and a per-invocation flag would not survive
  the user's own later `pi` invocations.
- **Accept all neutral protocols and pass them through.** Rejected: pi's API
  names are not neutral protocol names. Silent pass-through would produce a
  config that pi cannot execute.
- **Ignore `costAbove200kContext`.** Rejected: cost reporting would be wrong for
  providers with tiered pricing.
- **Treat a missing root as an empty provider set.** Rejected: it would erase
  working configuration before acq materializes input.

## Consequences

- `pi --list-models` reflects exactly what the selected provider kit publishes,
  with no provider-specific code in this kit.
- Because pi merges a custom provider into its bundled catalog, a provider id
  that pi already knows (for example `opencode-go`) also exposes pi's bundled
  models for that id. The neutral models are present and same-id metadata is
  replaced; extra ids are pi's own catalog. Avoiding that would require a
  different neutral `providerId`, which is a provider-kit decision.
- A provider with a broken or hostile generation fails loudly and does not
  replace the last good config.
- Personal entries in `models.json` do not survive an authoritative render.
  Users who need them should not apply this kit, or should keep them in another
  pi config surface.
- Adding a protocol or a non-200k pricing tier is a reviewed renderer change,
  not a catalog edit.
- The test suite vendors a snapshot of the live `pi.dev` models schema, so every
  emitted shape (including cost tiers and empty model lists) is schema-validated
  offline.
