# Decision: publish OpenCode Go as a harness-agnostic provider kit

**Status:** accepted (2026-10-25)

## Context

`acq` (the sandbox wrapper in
[agentic-coding-quickstart](https://github.com/GSA-TTS/agentic-coding-quickstart))
is separating provider input from harness configuration. A provider kit should
describe a model provider once — protocol, host, base URL, models URL, credential
variable, and model metadata — and every harness kit should be able to consume
that description without the provider kit knowing which harness is installed.

The reference implementation of this contract is `usai-provider` in
[agentic-coding-patterns](https://github.com/GSA-TTS/agentic-coding-patterns),
which pairs `acq-provider-input-bundle/v2`, `acq-provider-facts/v1`, and
`acq-neutral-model-catalog/v1` with a host-side normalizer and a vendored
snapshot. That kit is GSA-specific and lives inside a larger patterns
repository, so it cannot be the distribution point for a public provider.

OpenCode Go is a good second provider: it is publicly documented, it is
OpenAI-compatible, and it exposes a live models endpoint. It also has a wrinkle
that makes the abstraction earn its keep: one service routes different models
over four different wire protocols. A kit that quietly listed every Go model
under `openai-compatible` would produce plausible-looking but broken routing.

## Decision

Ship `opencode-go-provider` as a standalone, harness-agnostic `hybrid/v1` mixin
kit in its own repository.

1. **Facts are protocol-scoped.** `provider-input/facts.json` declares
   `apiProtocol: openai-compatible` and the OpenAI-compatible base URL
   (`https://opencode.ai/inference/go/openai/v1`). The models URL stays on the
   same host (`https://opencode.ai/inference/go/v1/models`), satisfying the
   contract's SSRF cross-check.
2. **The catalog contains only routable models.** The snapshot lists exactly the
   18 model ids served over `/openai/v1/chat/completions`. Models served over
   Anthropic Messages, Google Generative AI, or OpenAI Responses endpoints are
   omitted. Adding them requires widening `apiProtocol` and teaching renderers a
   new protocol; it is not a catalog edit.
3. **No harness configuration.** The kit declares a network allow-list and one
   file drop. It writes no global config and names no harness. Harness kits
   remain the sole writers of their own configuration, which prevents competing
   merges.
4. **No secrets.** The credential is referenced by name
   (`OPENCODE_GO_API_KEY`) in facts and in `credentialEnvNames`; no value ever
   enters the spec, catalog, tests, or repository.
5. **The snapshot is convenience, not trust.** It is dropped under
   `/home/agent/opencode-go/`, which the agent owns and can rewrite. It therefore
   carries model metadata only — no host, base URL, models URL, or credential
   field — so tampering cannot redirect a credential. Consumers needing
   trustworthy facts read the host-materialized, read-only provider generation.
6. **Pricing is normalized to the schema's capabilities.** Costs are USD per 1M
   tokens. DeepSeek's time-of-day pricing is recorded at the off-peak baseline
   (the schema has no tiering) with the peak prices documented in the README.
   `cacheWrite` is omitted where the service publishes no cache-write price,
   rather than being encoded as zero.
7. **The normalizer is a pure, host-side authoring tool.** `scripts/normalize-catalog.mjs`
   reads one annotated endpoint capture and writes one neutral catalog. It makes
   no network calls and ships outside `files/`, so it never enters the guest. It
   is executable, and `npm test` includes a drift gate that fails if the shipped
   snapshot diverges from normalizer output.
8. **Defaults are kit-relative.** `--source` defaults to
   `tests/fixtures/normalize-source.json` and `--out` defaults to the shipped
   snapshot path, resolved from the script's own directory so the tool works
   regardless of the caller's cwd. `npm run sync:opencode-go-models` regenerates
   the snapshot without arguments.

## Considered alternatives

- **Name it `opencode-go-opencode-provider`.** Rejected: the provider is
  OpenCode Go, a service; the harness is a separate axis. Encoding the harness in
  the provider name would imply a coupling this kit deliberately avoids.
- **Catalog every Go model under `openai-compatible`.** Rejected: it would
  advertise models that fail at runtime and hide a protocol mismatch behind a
  list that looks complete.
- **Fetch the models endpoint from inside the normalizer.** Rejected: it would
  make an authoring tool network-dependent and non-hermetic, and it still could
  not obtain pricing or limits (the endpoint returns ids only). Fetching and
  annotating is a separate, reviewable step; the normalizer only reshapes.
- **Hand-maintain the neutral snapshot.** Rejected: two sources of truth drift.
  The fixture is the authoring input; the snapshot is generated and drift-gated.
- **Put provider facts in a guest-writable file.** Rejected for the same reason
  the reference kit removed that mechanism: the agent has passwordless sudo, so
  a guest-written path cannot be a trust anchor. Facts live in the bundle and are
  materialized host-side.

## Consequences

- A harness that speaks OpenAI-compatible chat completions can consume OpenCode
  Go with no OpenCode-specific knowledge.
- The catalog is honest about coverage: 18 of the service's models, matching the
  declared protocol.
- Updating models is a fixture edit plus a regeneration and test run.
- DeepSeek cost accounting in a consumer is off-peak by default; peak accounting
  is the consumer's responsibility.
- The validator's credential-binding check still fails in a consumer that has not
  yet bound `opencode-go` to `OPENCODE_GO_API_KEY`. That binding is owned by the
  consumer repository and is handled by a separate acq change.
