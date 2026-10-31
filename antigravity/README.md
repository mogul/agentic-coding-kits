---
title: Antigravity gateway kit
description: Google agy CLI over a configured Chat Completions provider
status: draft
tier: 3
---

# Antigravity gateway kit

**Experimental; not ready for deployment.** Installs Google's `agy` CLI 1.4.12
on Linux ARM64 or x64—not the Antigravity editor launcher. Paseo supports it via
its Antigravity provider plugin. Each invocation translates Gemini requests to
the configured OpenAI-shaped model provider's **Chat Completions** endpoint.

## Use

```bash
export ACQ_EXTRA_KIT_SOURCES="github.com/mogul/"
acq run antigravity /path/to/project --kit '<provider-kit>' --kit 'git+https://github.com/mogul/agentic-coding-kits.git#ref=<sha>&dir=antigravity'
```

Provider facts and credentials must be materialized by acq. With multiple
providers set `ACQ_ANTIGRAVITY_PROVIDER`. `ACQ_ANTIGRAVITY_MODEL` and
`ACQ_ANTIGRAVITY_SMALL_MODEL` select exact configured IDs. The wrapper's
`agy models` reports those IDs for Paseo discovery. No global Paseo configuration
or Google login is written. CA trust is supplied separately.

## Limitations

- The native terminal picker may show more models than the configured
  OpenAI-shaped model provider supports. Choose an exact configured ID;
  unsupported selections fail rather than route to a similarly named model.
- `customModelsConfig` selects exact IDs, but the CLI still speaks Gemini.
  Internal `gemini-3.1-flash-lite-preview` housekeeping requests with no tools
  explicitly route to the configured small/default model. This is separate
  from user model selection.
- Text and ordinary function tools only; media, native Gemini search and
  thinking features are not supported. Upstream responses are buffered.
  agy 1.4.12 always requests automatic thought output for custom models; the
  kit explicitly ignores that automatic envelope in its text/function mode.
  No thought output or reasoning-effort guarantee is provided. Explicit effort
  flags and non-default thinking settings are rejected.
- **Paseo's plugin launches agy with full access and no permission prompts.**
  The kit does not add that flag for terminal use. An acq microVM remains the
  external boundary; do not assume a CLI plan mode is a filesystem sandbox.
- Persistent conversations use `~/.local/state/acq/antigravity` as their HOME.
  Terminal suspension/job control (Ctrl-Z, shell `fg`/`bg`) is not supported
  by the wrapper; use interruption or exit instead.
  This intentionally separates Google credentials and state from other agents,
  but user-global skills/configuration outside that HOME are not inherited.
- No credentials are persisted. The wrapper holds the upstream key; agy gets
  only a random per-invocation loopback token. Same-UID processes are not isolated.

## Verification and license

Run `python3 scripts/test`. See [verification](docs/verification.md) and
[design](docs/decisions/0001-session-bridge.md). Real ARM64 CLI custom-ID file-tool
turns and isolated Paseo sessions passed against a synthetic provider. Live
gateway, interactive PTY and x64 execution remain unverified.

Kit code is MIT. Antigravity is a separately downloaded proprietary Google
product; installation does not grant rights beyond its upstream terms.
Official product: <https://antigravity.google>.
