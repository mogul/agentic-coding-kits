---
title: Codex gateway kit
description: Codex CLI over a configured Chat Completions provider
status: draft
tier: 3
---

# Codex gateway kit

**Experimental; not ready for deployment.** Installs OpenAI Codex 0.166.0 on
Linux ARM64 or x64. Consumes acq's configured OpenAI-shaped model provider,
specifically its **Chat Completions** API. Codex requires Responses, so each
invocation owns a private authenticated loopback compatibility bridge.

## Use

```bash
export ACQ_EXTRA_KIT_SOURCES="github.com/mogul/"
acq run codex /path/to/project --kit '<provider-kit>' --kit 'git+https://github.com/mogul/agentic-coding-kits.git#ref=<sha>&dir=codex'
```

Provider facts and credentials must already be materialized by acq. With more
than one provider set `ACQ_CODEX_PROVIDER`; `ACQ_CODEX_MODEL` chooses an exact
model ID. No OpenAI subscription login or second Paseo catalog writer is needed.
Only installation hosts are added by this kit; the provider kit owns inference
network access. Corporate CA trust remains a separate kit.

## Boundaries

- Text and ordinary function tools only. Native web search, images, encrypted
  reasoning, custom tools and server-side Responses state are rejected.
- Upstream responses are buffered, then emitted as SSE. This is not live token
  streaming. Token usage is unknown, not fabricated.
- Catalog metadata is deliberately conservative; matching a deployment name
  does not establish native OpenAI capabilities. The kit supplies a minimal
  generic coding instruction template because Codex requires catalog instructions.
- CLI routing/config overrides are rejected. Permissions are not weakened.
  Terminal suspension/job control (Ctrl-Z, shell `fg`/`bg`) is not supported
  by this wrapper; use interruption or exit instead.
- Codex state persists under `~/.local/state/acq/codex`; routing/catalog files
  are per invocation. No credentials are written to disk. The model credential
  stays in the wrapper process, not the CLI environment.
- A same-UID guest process can inspect process state. Loopback authentication is
  not isolation from another process owned by the same user.

## Verification

Run `python3 scripts/test` for offline tests. Real CLI execution is opt-in; see
[verification](docs/verification.md). Real ARM64 CLI file-tool turns and isolated
Paseo sessions through a synthetic provider were exercised here; live gateway and x64 remain
unverified. See [design](docs/decisions/0001-session-bridge.md).

## License

Kit code follows this repository's MIT license. Codex is a separately downloaded
Apache-2.0 upstream product; this repository does not redistribute its binary.
Official source and release: <https://github.com/openai/codex>.
