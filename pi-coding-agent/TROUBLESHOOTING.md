# Troubleshooting — pi-coding-agent kit

These failure modes assume the kit ran as a startup step in an acq sandbox and
that a provider kit (for example `opencode-go-provider`) was applied alongside
it.

## `pi: command not found`

**Symptoms:** `command -v pi` is empty after the sandbox is ready.

**Causes and fixes:**

- **Install failed.** Read the log:

  ```bash
  acq exec <sandbox> -- sh -c 'cat "$HOME/.local/state/pi-coding-agent/install.log"'
  ```

  The install is fail-soft, so a registry outage leaves a running sandbox
  without pi. Re-run the step after connectivity returns:

  ```bash
  acq exec <sandbox> -- sh /home/agent/pi-coding-agent-install.sh
  ```

- **Node missing or too old.** pi declares `engines.node >=22.19.0`. The script
  logs a clear message and exits 0. Installing Node is out of scope for this
  kit; use a base image that carries it.

- **Prefix not on PATH.** The kit installs to `$HOME/.local`. `~/.local/bin` is
  on the default guest PATH. If a custom image removed it, add it before `pi`
  will resolve. Do not "fix" this by pointing at another prefix in one kit; the
  default-PATH contract is what makes a bare `sh -c` probe work.

## `pi --version` is not the pinned `1.4.0`

**Symptoms:** pi runs, but its version differs from the kit's pin.

**Cause:** the kit is idempotent and deliberately honors any `pi` already on
PATH that executes successfully, including one from a base image or a user
install. It logs the path and version and skips the pinned npm install.

**Fix:** remove or rename the pre-existing `pi` (and the `pi-real` sibling if it
belongs to this kit) and re-run the startup step, or recreate the sandbox. If
you see a *different* path from `command -v pi`, the pre-existing binary is
earlier on PATH. A pre-existing pi outside `$HOME/.local/bin` is not wrapped by
this kit, so it does not inherit the kit's CA bundle.

## `pi --list-models` is empty, or has no provider

**Symptoms:** pi runs, but the list is empty or lacks `opencode-go`.

**Causes and fixes:**

- **Provider generation not materialized.** This kit depends on acq's
  provider/agent decoupling (PR 611): `ACQ_PROVIDER_INPUT_ROOT` pointing at
  `models/providers/<providerId>/facts.json` and `snapshot.json`. On an older
  acq the renderer logs:

  ```text
  pi-coding-agent: provider input not ready at …; left …/models.json unchanged
  ```

  Confirm the environment inside the sandbox:

  ```bash
  acq exec <sandbox> -- sh -c 'echo "$ACQ_PROVIDER_INPUT_ROOT"; ls -R "$ACQ_PROVIDER_INPUT_ROOT" 2>/dev/null | head'
  ```

  If it is empty, upgrade acq (or apply the PR 611 build) and recreate the
  sandbox. Provider input is materialized only at create time.

- **Provider kit missing or rejected.** Both kits must be supplied. If
  `opencode-go-provider` was not applied, there is no provider directory to
  render.

- **Startup order.** The render step runs after the install step. If a
  transient error stopped it, re-run:

  ```bash
  acq exec <sandbox> -- node /home/agent/pi-coding-agent-render-models.mjs
  acq exec <sandbox> -- pi --list-models
  ```

- **Wrong controller.** The renderer writes
  `$PI_CODING_AGENT_DIR/models.json` when that variable is set, otherwise
  `$HOME/.pi/agent/models.json`. Inspect the file acq actually reads.

## `pi --list-models` says "No models available"

**Symptoms:** `models.json` clearly contains the provider, but pi prints:

```text
No models available. Use /login to log into a provider via OAuth or API key.
```

**Cause:** pi only lists models whose provider has usable authentication. The
renderer writes `"apiKey": "$OPENCODE_GO_API_KEY"`, which pi resolves from the
process environment. If acq injected no value, the provider is unavailable even
though the config is correct.

**Fix:** confirm the variable is present in the exec session:

```bash
acq exec <sandbox> -- sh -c 'test -n "$OPENCODE_GO_API_KEY" && echo present || echo missing'
```

If it is missing, store/register the credential through acq (see the kit
README), then recreate the sandbox so the backend injects it. Do not paste the
key into `models.json`.

## `pi --list-models` shows models that are not in the neutral catalog

**Symptoms:** the provider kit publishes 19 models, but the list also contains
`claude-…`, `gemini-…`, `gpt-…`, or other `opencode-go` ids.

**Cause:** pi has its own bundled `opencode-go` catalog. `models.json` entries
add to or replace same-id entries on that provider; they do not replace pi's
entire bundled model list. This is documented pi behavior.

**Fix:** none required if the neutral model ids are present. If you need a
provider namespace that pi does not already bundle, the neutral `providerId`
would have to differ, which is a provider-kit change, not an agent-kit toggle.


## The renderer exits non-zero

The render step is deliberately **fail-closed**. It refuses to write a config
it cannot trust. Read the exact message; each maps to one validation:

| Message | Meaning |
| --- | --- |
| `unsupported facts schema` | `facts.json` is not `acq-provider-facts/v1` |
| `unsupported catalog schema` | `snapshot.json` is not `acq-neutral-model-catalog/v1` |
| `does not match directory` | `facts.providerId` differs from the provider directory name |
| `catalog providerId does not match` | facts and catalog disagree |
| `invalid providerId` / `invalid provider directory` | slug violates the neutral schema (lowercase, hyphens, 1–32 chars) |
| `invalid keyEnv` | credential name is not `[A-Z][A-Z0-9_]*` |
| `baseUrl host does not match` / `modelsUrl host does not match` | URL host differs from `facts.host` (SSRF containment) |
| `unsupported apiProtocol` | provider declares something other than `openai-compatible` |
| `duplicate model` | catalog repeats a model id |
| `contains unsupported field` | input carries a field outside the neutral schemas |

Do not work around these by editing `models.json` by hand; fix the provider
generation or the provider kit. A hand-written config will be replaced on the
next authoritative render.

## `models.json` was rewritten and my personal settings disappeared

`~/.pi/agent/models.json` is **kit-owned**. The renderer rewrites it atomically
whenever a provider generation is available, so it is not a good place for
personal additions. Keep personal provider config in a separate pi config
surface, or omit this kit if you intend to manage `models.json` yourself.

The renderer leaves the file untouched when the provider root is absent, so an
unrelated pi install is not clobbered on a host without provider input.

## TLS errors during npm install or model requests

**Symptoms:** certificate verification failures, especially behind a TLS
inspecting proxy.

The install script builds `~/.local/state/pi-coding-agent/ca-bundle.pem` from
`PROXY_CA_CERT_B64` plus the system trust store and wraps `pi` so later
invocations use it. Check:

```bash
acq exec <sandbox> -- sh -c 'echo "len=${#PROXY_CA_CERT_B64}"; wc -c "$HOME/.local/state/pi-coding-agent/ca-bundle.pem"'
acq exec <sandbox> -- sh -c 'head -n1 "$(command -v pi)"; grep -n NODE_EXTRA_CA_CERTS "$(command -v pi)"; ls -l "$(dirname "$(command -v pi)")/pi-real"'
```

- If `PROXY_CA_CERT_B64` is empty, acq/the base image did not supply the proxy
  CA. That is outside this kit.
- If the decode warning appears in the startup output, the value is malformed
  base64. Do not disable TLS verification; fix or re-issue the CA value.
- The `pi` on PATH should be a small shell wrapper mentioning
  `NODE_EXTRA_CA_CERTS` and `pi-real`, not npm's raw JS entrypoint. The wrapper
  derives its directory from `$0` and executes the sibling `pi-real`. If the
  wrapper is missing, or `pi-real` is missing, the wrapper step did not run or
  the install was interrupted; re-run the install script and read the log.

## Requests are rejected with HTTP 401/403

The model appears in `pi --list-models` but the provider rejects requests.

- **Credential not injected.** For a custom endpoint, acq records the binding
  only when both host and env name are supplied:

  ```bash
  acq provider-credential set opencode-go OPENCODE_GO_API_KEY --host opencode.ai
  ```

  `--env` must equal the provider kit's `facts.keyEnv`. A binding without the
  host (or an env mismatch) means no key reaches the sandbox.

- **Key expired or plan inactive.** Refresh it through acq, then recreate the
  sandbox if the backend injected a stale placeholder.

- **Region restriction (OpenCode Go).** `deepseek-v4-pro` and
  `deepseek-v4.1-flash` require the workspace Regions setting to include
  **Global**. This is a workspace setting, not a kit setting.

- **Wrong protocol for the model.** Only models the provider serves over the
  OpenAI-compatible chat-completions endpoint are in a neutral
  `openai-compatible` catalog. See the provider kit's troubleshooting.

## `acq create` fails before the sandbox starts

- **`facts.keyEnv must match the host credential binding`** — the consumer's
  `provider-credential-bindings.json` (or `provider-credential` registry) does
  not map `opencode-go` to `OPENCODE_GO_API_KEY`. Register the binding with the
  command above, or upgrade acq to a build with the decoupled registry, then
  recreate the sandbox.

- **acq lacks provider-input support** — an acq build predating PR 611 has no
  `provider-credential` command and does not set `ACQ_PROVIDER_INPUT_ROOT`.
  This kit will still install pi, but `--list-models` will be empty. Upgrade
  acq and recreate.

Provider input is materialized at create time. `acq kit apply` does not refresh
it; delete and recreate the sandbox.

## Kit ref is rejected or resolves to unexpected code

- **Source not allow-listed.** acq accepts kits only from allow-listed source
  prefixes:

  ```bash
  export ACQ_EXTRA_KIT_SOURCES="github.com/mogul/"
  ```

- **Branch ref instead of a SHA.** Use
  `#ref=<full-sha>&dir=pi-coding-agent`, never `#ref=main`.

- **Wrong directory.** The kit lives in a subdirectory; `&dir=` is required.

## `scripts/verify` skips the live gate

`RUN_ACQ=1` requires an acq with the decoupled provider/agent pipeline. The
script detects the missing `provider-credential` command and reports SKIP rather
than a false failure. The offline gate (spec, syntax, tests, source guards)
still runs and is the authoritative check on an older host.
