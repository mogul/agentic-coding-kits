# pi-coding-agent (acq mixin kit, `hybrid/v1`)

> **Status: Preview for the decoupled provider pipeline.** The kit is complete
> and its offline tests pass, but its end-to-end path depends on an acq build
> that materializes `$ACQ_PROVIDER_INPUT_ROOT` and supports the
> `provider-credential` binding (the provider/agent decoupling in
> [GSA-TTS/agentic-coding-quickstart](https://github.com/GSA-TTS/agentic-coding-quickstart)
> PR 611). On an older acq, the kit installs pi but the render step reports
> `provider input not ready` and leaves `models.json` untouched. See
> [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

An [`acq`](https://github.com/GSA-TTS/agentic-coding-quickstart) **agent kit**
for **pi** (`@earendil-works/pi-coding-agent`). It installs the CLI and renders
the provider generation selected alongside it into pi's own configuration, so:

```bash
pi --list-models
```

lists the models published by the provider kit — for example all 19
OpenAI-compatible `opencode-go` models.

This kit is intentionally separate from
[`opencode-go-provider/`](../opencode-go-provider/). The provider kit owns
facts and the neutral catalog; this kit owns pi's config and nothing else.

## What it does

1. **Installs pi** at startup, unprivileged, pinned to `1.4.0`:

   ```bash
   npm install -g --ignore-scripts --prefix "$HOME/.local" \
     @earendil-works/pi-coding-agent@1.4.0
   ```

   `~/.local/bin` is on the guest's default PATH, so `pi` resolves from a bare
   `sh -c` with no profile or PATH injection.

2. **Renders provider input** at startup. It reads the read-only generation at
   `$ACQ_PROVIDER_INPUT_ROOT/models/providers/<providerId>/` and writes
   `~/.pi/agent/models.json` atomically.

3. **Fails closed on provider input, soft on install.** A malformed provider
   generation stops the render step with a precise error. A missing npm
   registry or Node toolchain logs a message and exits 0 — an optional CLI must
   not fail sandbox creation.

No published ports: pi is a TUI, not a web UI. No `agent:` block: pi is an
opt-in `--kit` mixin, not an acq-built-in agent.

## Interface

| Source | Neutral value | pi `models.json` |
| --- | --- | --- |
| `facts.providerId` | provider slug | `providers.<providerId>` key |
| `facts.baseUrl` | `https://…` | `providers.<id>.baseUrl` |
| `facts.apiProtocol` | `openai-compatible` | `providers.<id>.api = "openai-completions"` |
| `facts.keyEnv` | `OPENCODE_GO_API_KEY` | `providers.<id>.apiKey = "$OPENCODE_GO_API_KEY"` |
| — | — | `providers.<id>.authHeader = true` |
| `models[].id` | stable id | `models[].id` |
| `models[].name` | display name | `models[].name` (falls back to the id) |
| `models[].contextWindow` | input tokens | `models[].contextWindow` |
| `models[].maxOutputTokens` | output tokens | `models[].maxTokens` |
| `models[].cost.{input,output,cacheRead,cacheWrite}` | USD/1M | same four fields; missing fields become `0` because pi's `ModelCost` requires all four |
| `models[].costAbove200kContext` | USD/1M above 200k | `models[].cost.tiers = [{ inputTokensAbove: 200000, … }]` |

The neutral field is named for context-window pricing and pi's tier is keyed to
total request input; both are long-input thresholds at 200,000 tokens, and pi's
request-wide tier is the closest supported representation. If a provider
publishes a base `cost` but no tier, pi gets the four base fields only. If it
publishes a tier without a base cost, the base fields are emitted as `0` so
pi's required `ModelCost` shape stays valid.

The emitted document starts with
`"$schema": "https://pi.dev/schemas/models.schema.json"`.

Only `openai-compatible` is accepted. A provider kit that declares another
protocol is a hard failure rather than a provider that silently does not work.

Example output for `opencode-go`:

```json
{
  "$schema": "https://pi.dev/schemas/models.schema.json",
  "providers": {
    "opencode-go": {
      "baseUrl": "https://opencode.ai/inference/go/openai/v1",
      "api": "openai-completions",
      "apiKey": "$OPENCODE_GO_API_KEY",
      "authHeader": true,
      "models": [
        {
          "id": "glm-5.3-flash",
          "name": "GLM-5.3-Flash",
          "contextWindow": 1000000,
          "maxTokens": 131072,
          "cost": { "input": 0.15, "output": 0.5, "cacheRead": 0.03, "cacheWrite": 0 }
        }
      ]
    }
  }
}
```

### Provider IDs already known to pi

pi merges a `models.json` provider into its bundled catalog. If the provider id
matches one pi already knows (as `opencode-go` does), `pi --list-models` shows
the neutral models **plus** pi's bundled models for that id. Same-id entries
from this kit replace the bundled metadata; the rest are pi's own catalog.

That is pi's documented merge behavior, not a renderer bug. The acceptance
contract is that the provider kit's model ids are present; a strict "only these
ids" assertion would require a provider id pi does not already bundle, which
would contradict the neutral `facts.providerId` mapping.

### Authentication affects what `--list-models` shows

pi lists only models whose provider has usable authentication. The renderer
writes `"apiKey": "$OPENCODE_GO_API_KEY"`; with that variable absent from the
process environment, pi reports:

```text
No models available. Use /login to log into a provider via OAuth or API key.
```

Make sure acq injects the provider credential into the exec environment before
concluding the render failed. The config itself does not store the key.


## Install method

**npm registry, not `https://pi.dev/install.sh`.**

- The curl installer is mutable remote shell and needs `pi.dev` egress.
- It runs an interactive Node/npm preflight that is meaningless in a
  non-interactive startup step.
- The underlying install is a single npm package, so this kit runs that command
  directly against the public registry.

The version is **pinned to `1.4.0`**, the reviewed stable release at the time of
authorship. Bump it deliberately, together with this README and the tests, after
reviewing the new release's npm metadata (`engines.node`, lifecycle scripts).
See [`docs/decisions/0001`](docs/decisions/0001-install-pi-from-npm-with-a-pinned-version.md).

`--ignore-scripts` removes install-time lifecycle hooks. pi has no build step,
so nothing is lost. It does not sandbox code that runs when `pi` is invoked.

The install is a no-op when `pi` already resolves **and runs**. It is also
fail-soft: missing Node/npm, an old Node, or a registry failure logs a clear
message and exits 0.

### Idempotency and pre-existing pi

- A blank sandbox installs the pinned version.
- A later boot sees the wrapper, runs `pi --version`, and skips npm.
- If a half-finished install left a file that resolves but does not execute,
  the version probe fails and the next boot reinstalls.
- If a **different** pi is already on `PATH`, the kit honors it and does not
  shadow it with a second install. It logs the path and version. That pi may be
  a different release; remove it if you need the reviewed pin. When it lives
  outside `$HOME/.local/bin`, this kit does not wrap it, so its CA trust is
  whatever that installation provides.

## CA-bundle handling

The install script folds `PROXY_CA_CERT_B64` (the sandbox proxy CA) and the
system trust store into:

```text
~/.local/state/pi-coding-agent/ca-bundle.pem
```

It exports `NODE_EXTRA_CA_CERTS` for the npm install itself, then moves npm's
`~/.local/bin/pi` entrypoint to the sibling `~/.local/bin/pi-real` and writes a
small wrapper at `pi`. The wrapper exports the same bundle and executes
`pi-real`. Keeping the real entrypoint as a sibling means the wrapper embeds no
path at all, so a `HOME` containing spaces, quotes, `$`, backticks, or newlines
cannot break (or inject into) the generated shell.

The bundle is rebuilt every boot; the wrapper is written once. If
`PROXY_CA_CERT_B64` is malformed, the script warns and omits it rather than
shipping a broken bundle.

## Using the kit

Register the provider credential binding once. This records *where* the key
comes from; the key value is injected by acq at runtime and never enters this
repository:

```bash
acq provider-credential set opencode-go OPENCODE_GO_API_KEY --host opencode.ai
```

Then create a sandbox with the provider kit **and** this agent kit. Both refs
must be pinned to the same full commit SHA; use `&dir=` because the kits live in
subdirectories:

```bash
export ACQ_EXTRA_KIT_SOURCES="github.com/mogul/"

acq --backend msb run opencode . \
  --kit "git+https://github.com/mogul/agentic-coding-kits.git#ref=<full-sha>&dir=opencode-go-provider" \
  --kit "git+https://github.com/mogul/agentic-coding-kits.git#ref=<full-sha>&dir=pi-coding-agent"

acq --backend msb exec <sandbox> -- pi --list-models
```

Expected: `pi` on PATH and the 19 `opencode-go` model ids listed, including
`glm-5.3-flash` and `deepseek-v4-pro`. pi also merges its own bundled
`opencode-go` catalog, so the table may include additional built-in ids; the
neutral catalog's entries are present and override same-id metadata. The
provider credential must be injected into the exec environment or pi reports
"No models available" (see [Troubleshooting](TROUBLESHOOTING.md)).

Never use `#ref=main`. A branch ref lets the host fetch different
provider-controlled code at a different time.

## Verifying the kit

```bash
cd pi-coding-agent
npm ci
npm test                         # node:test renderer suite
scripts/verify                   # offline gate
RUN_ACQ=1 scripts/verify         # live acq/msb gate
```

`scripts/verify` runs the offline gate always: spec presence, `sh -n` and
`shellcheck --severity=warning` on the installer, a stub-npm install behavior
suite (idempotency, broken-install recovery, hostile `HOME`, fail-soft registry
failure, CA decode warning), the renderer tests, source-level regression guards,
and `acq kit validate` when available. The renderer suite vendors a snapshot of
the live `pi.dev` models schema so every emitted shape is validated offline.
`RUN_ACQ=1` additionally creates a sandbox with both kits, waits for startup,
checks `command -v pi`, inspects the rendered `models.json`, and asserts that
`pi --list-models` contains provider model ids. On an acq build without the
decoupled provider pipeline it reports a SKIP with that reason rather than a
false failure.

## Security notes

- **No secrets.** The kit references `OPENCODE_GO_API_KEY` by name only. The
  value is injected by acq and never written to `models.json`.
- **Provider input is validated fail-closed.** Schema versions, provider
  identity, directory name, key-name shape, HTTPS URLs, host agreement,
  protocol, length limits, and full-match regex semantics all follow the
  vendored neutral schemas. Symlinked provider directories and input files are
  rejected.
- **Unknown fields are rejected** rather than silently ignored or passed
  through; the neutral schemas set `additionalProperties: false`.
- **`models.json` is kit-owned.** The renderer rewrites it atomically whenever
  an authoritative provider generation exists. A symlink at the target is
  replaced, not followed. Put personal overrides elsewhere, or expect them to
  be replaced on the next start.
- The vendored provider snapshot under `opencode-go-provider/` is agent-owned
  and is not a trust anchor; the renderer reads only the host-materialized
  generation under `$ACQ_PROVIDER_INPUT_ROOT`.

## Naming

The kit is `pi-coding-agent`, matching the npm package, not the bare upstream
shorthand `pi`.

## License

MIT — see the repository [`LICENSE`](../LICENSE).
