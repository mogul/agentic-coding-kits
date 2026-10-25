# Troubleshooting — opencode-go-provider kit

These are failure modes specific to the OpenCode Go provider kit. They assume the
kit has been applied to a sandbox and that a harness kit (for example, an
OpenCode kit) is rendering the selected provider generation.

## Authentication fails (HTTP 401/403)

**Symptoms:** requests reach `opencode.ai` but every one is rejected.

**Causes and fixes:**

- **Missing or expired key.** The kit reads `OPENCODE_GO_API_KEY`; it never stores
  the key. Set or refresh it through acq:
  `acq secret set opencode-go --host opencode.ai`.
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
  and deliberately catalogs only models served over
  `/openai/v1/chat/completions`. Grok, GPT, Claude, Gemini, Qwen, MiniMax M3, and
  Muse Spark models are served over Anthropic-, Google-, or OpenAI-Responses-shaped
  endpoints. They are not in this catalog. Use a provider kit that declares the
  matching protocol instead of forcing the id into this one.
- **Model removed or renamed upstream.** Regenerate the catalog (below) and
  re-apply the kit. The list of Go models changes as upstream models are added
  and retired.
- **Region or privacy restriction.** Some models are limited by region.
  DeepSeek V4.1 Flash and V4 Pro require the workspace's **Regions** privacy
  setting to include **Global**. Muse Spark Contributor models require enabling
  paid endpoints that train on request data. Beam Free is unavailable in several
  regions and is time-limited.
- **Session header missing.** OpenCode Go expects a stable session identifier
  (`x-opencode-session`) for conversations. Harnesses that do not send one may be
  routed poorly or rejected; use a client version with session support.

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

## The catalog is empty or shows stale models

**Symptoms:** no models appear, or a model was added/removed upstream but the
catalog did not change.

**Cause:** the snapshot is vendored. It only changes when the fixture is updated
and the normalizer is re-run.

**Fix:** from the kit directory, update
`tests/fixtures/normalize-source.json` from the live endpoint and the Go pricing
docs, then:

```bash
npm run sync:opencode-go-models
npm test
```

Re-apply or recreate the sandbox so the new snapshot is projected.

## `npm test` fails on the snapshot drift gate

**Symptom:** `shipped snapshot exactly matches normalizeCatalog(fixture)` fails.

**Cause:** either the fixture changed without regenerating the snapshot, or the
snapshot was hand-edited. The snapshot is a generated artifact.

**Fix:** run `npm run sync:opencode-go-models`, review the diff, and re-run
`npm test`. Do not patch the snapshot directly.

## The validator fails on `facts.keyEnv must match the host credential binding`

**Symptom:** running `validate_provider_input_contract.py` against this kit
reports only this error.

**Cause:** the consumer's `provider-credential-bindings.json` does not yet map
`opencode-go` to `OPENCODE_GO_API_KEY`. The binding is owned by the consumer
repository (an acq change), not by this kit.

**Fix:** add `"opencode-go": "OPENCODE_GO_API_KEY"` to that file in the consumer,
or wait for the corresponding acq change. Every other validator check — schemas,
declared artifact paths, symlinks, executable normalizer, host allow-list, URLs,
and catalog — passes independently.

## A hand-edited snapshot has no effect, or seems untrusted

**Symptom:** editing
`/home/agent/opencode-go/model-catalog-snapshot.json` in the guest changes
nothing, or you are unsure whether to trust it.

**Explanation:** that path is agent-owned and guest-writable, so it is a
convenience payload, not a trust anchor. Consumers that need trustworthy provider
facts read the host-materialized, read-only provider generation. The snapshot
carries model metadata only; it cannot redirect credentials or change the
provider host.
