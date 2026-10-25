# Troubleshooting — opencode-go-provider kit

These are failure modes specific to the OpenCode Go provider kit. They assume the
kit has been applied to a sandbox and that a harness kit (for example, an
OpenCode kit) is rendering the selected provider generation.

## `acq run`/`acq create` fails: `facts.keyEnv must match the host credential binding`

**Symptoms:** sandbox creation aborts during provider-input validation, before
the sandbox starts, with exactly:

```text
facts.keyEnv must match the host credential binding
```

**Cause:** this kit is **Preview**. The consumer's pinned
`provider-credential-bindings.json` does not yet map `opencode-go` to
`OPENCODE_GO_API_KEY`. That registry is a trusted consumer-side control-plane
input; the kit cannot add itself to it.

**Fix:** wait for (or land) the acq-side change adding
`"opencode-go": "OPENCODE_GO_API_KEY"`, then retry. Provider input is
materialized only at create time, so an existing sandbox cannot be repaired by
`acq kit apply`; delete and recreate it.

## Authentication fails (HTTP 401/403)

**Symptoms:** requests reach `opencode.ai` but every one is rejected.

**Causes and fixes:**

- **Missing or expired key.** Set or refresh it through acq. For a custom
  endpoint, **both** `--host` and `--env` are required; the mapping is not
  recorded otherwise:

  ```bash
  acq secret set -g opencode-go --host opencode.ai --env OPENCODE_GO_API_KEY
  # or, sandbox-scoped:
  acq secret set <sandbox> opencode-go --host opencode.ai --env OPENCODE_GO_API_KEY
  ```

  `--env` must equal the facts `keyEnv` (`OPENCODE_GO_API_KEY`). A bare
  `acq secret set opencode-go` records no host/env mapping, so no key is
  injected.

- **No Go subscription.** An OpenCode Go key requires an active Go or Go Plus
  plan on the workspace. Confirm the subscription in the
  [OpenCode Console](https://opencode.ai/console), then re-copy the key.
- **Key truncated on copy.** Use the console's copy button rather than selecting
  the key by hand.
- **Wrong workspace type.** Go and Go Plus are for single-member workspaces.
  A workspace with a Go subscription cannot invite members; using a key from a
  multi-member workspace will not behave as expected.

## A model returns 404 / "model not found"

**Symptoms:** the model id is valid on OpenCode Go, but this provider returns
not-found.

**Causes and fixes:**

- **Wrong protocol for the model.** This kit declares `openai-compatible` only
  and catalogs only models served over `/openai/v1/chat/completions`. Grok, GPT,
  Claude, Gemini, Qwen, MiniMax M3, and Muse Spark models are served over
  Anthropic-, Google-, or OpenAI-Responses-shaped endpoints. They are not in this
  catalog. Use a provider kit that declares the matching protocol instead of
  forcing the id into this one.
- **Model removed or renamed upstream.** Regenerate the catalog (below) and
  re-apply the kit. The list of Go models changes as upstream models are added
  and retired.
- **Region restriction.** Some models are limited by region. See the DeepSeek
  section below.

## `deepseek-v4-pro` is refused (the recommended primary)

**Symptoms:** other models work, but the primary `deepseek-v4-pro` (or
`deepseek-v4.1-flash`) returns an authorization or availability error.

**Cause:** OpenCode Go requires the workspace **Settings › Privacy › Regions**
setting to include **Global** for DeepSeek V4.1 Flash and V4 Pro. Workspaces
with only the default Europe/United States regions cannot use them.

**Fix:** have a workspace owner or admin enable **Global** under Regions, then
retry. This is a workspace setting, not something the kit or sandbox can change.
DeepSeek models also have peak/off-peak pricing (the catalog records off-peak);
cost estimates are not an error.

## Requests are throttled or stop mid-month (HTTP 429)

**Symptoms:** requests succeed, then fail with rate-limit or allowance errors.

**Causes and fixes:**

- **Monthly Go allowance exhausted.** Each model has its own monthly dollar
  allowance; 5-hour and weekly windows are fractions of it. Check usage in the
  [console](https://opencode.ai/console). Free models remain available, and
  Extra Usage can fall back to pay-as-you-go credits if enabled.
- **Per-model limits differ.** A cheap model may have a much larger allowance
  than a frontier model. The catalog's `cost` values let a harness estimate
  spend, but the allowance table itself lives upstream.

## Requests hang, time out, or fail TLS

**Symptoms:** no response, connection timeouts, or certificate errors.

**Causes and fixes:**

- **Egress blocked.** Confirm `opencode.ai` is allowed. The kit allow-lists it in
  `caps.network.allow`; check the active backend's policy log and add the host if
  a local policy is stricter than the kit.
- **Proxy or TLS interception.** OpenCode Go is a custom endpoint reached through
  the network allow-list, not a built-in backend service proxy. If the sandbox
  intercepts TLS, install the interception CA through the usual certificate kit;
  do not disable verification.
- **Wrong base URL.** The base URL is
  `https://opencode.ai/inference/go/openai/v1` and chat completions are at
  `/chat/completions` beneath it. The models list is a different path:
  `https://opencode.ai/inference/go/v1/models`.

## Poor routing, prompt-cache misses, or a client warning

**Symptoms:** requests work but latency/caching is worse than expected, or the
service warns about the client.

**Causes and fixes:**

- **No stable session header.** OpenCode Go expects `x-opencode-session` with a
  stable value per conversation, used for routing and prompt caching. Send it
  explicitly from a custom harness; some clients are recognized by a native
  session header, but do not rely on that.
- **Generic user agent.** Identify the client with its own product token (for
  example `my-coding-agent/1.0`), not a generic SDK or HTTP-library name.
- **Non-typical traffic.** The service is intended for coding-agent traffic and
  monitors for abuse that degrades other users.

## The catalog is empty, stale, or contains an unroutable model

**Symptoms:** no models appear; a model was added/removed upstream but the
catalog did not change; or normalization fails with "not in the
OpenAI-compatible allowlist".

**Cause:** the snapshot is vendored. It only changes when the fixture is updated
and the normalizer is re-run. The live `/v1/models` response is **not** a valid
authoring input: it mixes protocols and includes free, stealth, and legacy ids.

**Fix:** from the kit directory, curate `tests/fixtures/normalize-source.json`
against the Go docs endpoint table and pricing, then:

```bash
npm ci
npm run sync:opencode-go-models
npm test
```

Recreate the sandbox so the new snapshot is projected. Do not feed the raw
endpoint response to the normalizer; unknown ids fail by design.

## `npm test` fails on the snapshot drift gate

**Symptom:** `shipped snapshot exactly matches normalizeCatalog(fixture)` fails.

**Cause:** either the fixture changed without regenerating the snapshot, or the
snapshot was hand-edited. The snapshot is a generated artifact.

**Fix:** run `npm run sync:opencode-go-models`, review the diff, and re-run
`npm test`. Do not patch the snapshot directly.

## `acq kit apply` did not pick up a kit change

**Symptom:** you updated facts, the catalog, or the snapshot, ran
`acq kit apply`, and the sandbox still behaves the same.

**Cause:** `acq kit apply` applies the kit spec to an existing sandbox. Provider
input — facts, normalizer, snapshot — is materialized only at sandbox **create**
time. There is no mid-life provider-input refresh.

**Fix:** `acq rm <sandbox>` and recreate it with the same kit refs.

## Kit ref is rejected or resolves to unexpected code

**Symptom:** `acq run` cannot fetch the kit, or you are unsure what code the host
loaded.

**Causes and fixes:**

- **Source not allow-listed.** acq only accepts kits from allow-listed source
  prefixes. Add this repository once:
  `export ACQ_EXTRA_KIT_SOURCES="github.com/mogul/"`.
- **Branch ref instead of a SHA.** Use
  `#ref=<full-sha>&dir=opencode-go-provider`, never `#ref=main`. A branch lets
  the host fetch different provider-controlled code later.
- **Wrong directory.** The kit is in a subdirectory; the `&dir=` fragment is
  required.

## The validator fails on `facts.keyEnv must match the host credential binding`

**Symptom:** running `validate_provider_input_contract.py` directly against this
kit reports only this error.

**Cause:** the consumer's `provider-credential-bindings.json` does not map
`opencode-go` to `OPENCODE_GO_API_KEY`. This is the same missing binding that
blocks create-time materialization.

**Fix:** add the binding in the consumer, or validate with a temporary copy that
includes it. Every other validator check — schemas, declared artifact paths,
symlinks, executable normalizer, host allow-list, URLs, and catalog — passes in
that patched run.

## A hand-edited snapshot has no effect, or seems untrusted

**Symptom:** editing
`/home/agent/opencode-go/model-catalog-snapshot.json` in the guest changes
nothing, or you are unsure whether to trust it.

**Explanation:** that path is agent-owned and guest-writable, so it is a
convenience payload, not a trust anchor. Consumers that need trustworthy provider
facts read the host-materialized, read-only provider generation. The snapshot
carries model metadata only; it cannot redirect credentials or change the
provider host.
