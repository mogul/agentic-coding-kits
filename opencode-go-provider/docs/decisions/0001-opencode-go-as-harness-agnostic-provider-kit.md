# Decision: publish OpenCode Go as a harness-agnostic provider kit

**Status:** accepted, kit status **Preview** (2026-10-25)

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

Ship `opencode-go-provider` as a standalone `hybrid/v1` mixin kit in its own
repository. It is **harness-agnostic in the provider-input sense**: it names no
harness and writes no harness configuration, and any harness that speaks
OpenAI-compatible chat completions can consume the facts and catalog. It is not
claiming that every OpenAI-compatible client works unmodified: OpenCode Go also
expects a stable `x-opencode-session` header and a non-generic user agent, and
some models require workspace region settings. Those preconditions are documented
in the kit README and `agentContext`.

1. **Facts are protocol-scoped.** `provider-input/facts.json` declares
   `apiProtocol: openai-compatible` and the OpenAI-compatible base URL
   (`https://opencode.ai/inference/go/openai/v1`). The models URL stays on the
   same host (`https://opencode.ai/inference/go/v1/models`), satisfying the
   contract's SSRF cross-check.
2. **The catalog contains only routable models.** The snapshot lists exactly the
   18 entries in the Go docs endpoint table that use
   `/openai/v1/chat/completions` (17 paid models plus Beam Free). Models served
   over Anthropic Messages, Google Generative AI, or OpenAI Responses endpoints
   are omitted, as are undocumented free, stealth/experimental, and legacy ids.
   The normalizer enforces an explicit `OPENAI_COMPATIBLE_MODEL_IDS` allowlist
   shared with the tests and fails on any unknown id, so a raw `/v1/models`
   capture cannot be published by accident. Adding a protocol requires widening
   `apiProtocol` and renderer support; it is not a catalog edit.
3. **No harness configuration.** The kit declares a network allow-list and one
   file drop. It writes no global config and names no harness. Harness kits
   remain the sole writers of their own configuration, which prevents competing
   merges.
4. **No secrets and no `environment:` block.** The credential is referenced by
   name (`OPENCODE_GO_API_KEY`) in facts and in `credentialEnvNames`; no value
   ever enters the spec, catalog, tests, or repository. The spec deliberately
   omits an `environment:` block: an empty `OPENCODE_GO_API_KEY` there could
   shadow the placeholder the backend injects, and the patterns env-ownership
   check is aspirational and not currently enforced.
5. **The snapshot is convenience, not trust.** It is dropped under
   `/home/agent/opencode-go/`, which the agent owns and can rewrite. It therefore
   carries model metadata only — no host, base URL, models URL, or credential
   field — so tampering cannot redirect a credential. Consumers needing
   trustworthy facts read the host-materialized, read-only provider generation.
   Shipping the guest-visible duplicate is deliberate parity with the
   `usai-provider` reference kit.
6. **Pricing is normalized to the schema's capabilities.** Costs are USD per 1M
   tokens. DeepSeek's time-of-day pricing is recorded at the off-peak baseline
   (the schema has no tiering) with the peak prices documented in the README.
   `cacheWrite` is omitted where the service publishes no cache-write price,
   rather than being encoded as zero.
7. **The normalizer is a pure, host-side authoring tool.** `scripts/normalize-catalog.mjs`
   reads one curated endpoint capture and writes one neutral catalog. It makes
   no network calls. acq materializes it with the provider bundle and mounts
   that tree read-only, so the agent can execute it but cannot modify it. It is
   executable, and `npm test` includes a drift gate that fails if the shipped
   snapshot diverges from normalizer output.
8. **Defaults are kit-relative and the entry point is symlink-safe.**
   `--source` defaults to `tests/fixtures/normalize-source.json` and `--out`
   defaults to the shipped snapshot path, resolved from the script's own
   location. Entry-point detection compares real paths, so invoking the script
   through a symlink or Windows junction still runs it instead of silently
   exiting 0.
9. **Kit refs must be SHA-pinned.** Documentation requires
   `#ref=<full-sha>&dir=opencode-go-provider`, never `#ref=main`. Provider input
   is materialized at sandbox create time; `acq kit apply` does not refresh it.
10. **Status is Preview until the consumer binds the credential.** The kit is
    complete and contract-validated, but `acq run`/`create` fails at provider
    validation with `facts.keyEnv must match the host credential binding` until
    the pinned Patterns `provider-credential-bindings.json` adds
    `"opencode-go": "OPENCODE_GO_API_KEY"`. The registry is a trusted
    consumer-side control-plane input and cannot be shipped by the kit.

## Considered alternatives

- **Name it `opencode-go-opencode-provider`.** Rejected: the provider is
  OpenCode Go, a service; the harness is a separate axis. Encoding the harness in
  the provider name would imply a coupling this kit deliberately avoids.
- **Catalog every Go model under `openai-compatible`.** Rejected: it would
  advertise models that fail at runtime and hide a protocol mismatch behind a
  list that looks complete.
- **Derive the catalog from the live `/v1/models` endpoint.** Rejected: that
  endpoint mixes protocols and includes free, stealth, and legacy ids, and it
  carries no pricing or limits. The normalizer accepts only curated captures and
  rejects unknown ids.
- **Fetch the models endpoint from inside the normalizer.** Rejected: it would
  make an authoring tool network-dependent and non-hermetic, and it still could
  not obtain pricing or limits (the endpoint returns ids only).
- **Hand-maintain the neutral snapshot.** Rejected: two sources of truth drift.
  The fixture is the authoring input; the snapshot is generated and drift-gated.
- **Put provider facts in a guest-writable file.** Rejected for the same reason
  the reference kit removed that mechanism: the agent has passwordless sudo, so
  a guest-written path cannot be a trust anchor. Facts live in the bundle and are
  materialized host-side.
- **Use `#ref=main` for convenience.** Rejected: a host could later fetch
  different provider-controlled metadata, defeating the trust boundary.

## Consequences

- A harness that speaks OpenAI-compatible chat completions and honors the
  session/user-agent expectations can consume OpenCode Go with no
  OpenCode-specific knowledge.
- The catalog is honest about coverage: the 18 documented OpenAI-compatible
  entries, matching the declared protocol.
- Updating models is a fixture edit plus a regeneration and test run; adding an
  id that is not in the allowlist fails until it is deliberately reviewed.
- DeepSeek cost accounting in a consumer is off-peak by default; peak accounting
  is the consumer's responsibility. The recommended primary also needs the
  workspace Regions setting to include Global.
- Until the acq credential binding lands, the kit is Preview and create-time
  materialization fails with the documented message. No `acq kit apply` call can
  work around it; the sandbox must be recreated after the change.
