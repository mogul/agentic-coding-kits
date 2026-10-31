---
title: "Claude Code Kit Troubleshooting"
description: "Diagnose installation, routing, credentials, and host-access problems."
status: draft
tier: 2
last_updated: "2026-10-30"
---

# Troubleshooting

## Installation fails

The guest needs glibc Linux x64/ARM64 and Python 3.12–3.14 with stdlib venv.
The kit seeds pip from a pinned, verified wheel; missing ensurepip is supported.
Missing wheels fail rather than compile remote source. Confirm npm/PyPI egress
and system CA trust; compose the CA kit for enterprise certificates. Never use
`--trusted-host`, disable TLS verification, or bypass a checksum failure.
The install does not use Node or an Anthropic download domain.

## Claude says the kit is not ready

Check that startup installation completed and `~/.local/bin` is on PATH.
Check that `ACQ_PROVIDER_INPUT_ROOT` points to acq's materialized read-only tree,
and the selected provider has `facts.json` and `snapshot.json`. Do not fabricate
an empty tree to suppress an error. If several providers exist, set
`ACQ_CLAUDE_PROVIDER` in the guest through a non-secret kit/environment setting.
Choose model IDs from the snapshot, not Anthropic's public API naming scheme.

Confirm credential **presence**, never print its value. Use acq's approved
secret-injection path and check expiration/authorization. No Anthropic login is
needed. The proxy uses the provider's key, not a Claude subscription token.

## Upstream request fails

The bridge always targets `<baseUrl>/chat/completions`, not `/responses` or
`/v1/messages` at USAi. Unknown model IDs fail locally. A 502 intentionally hides
upstream errors that might contain sensitive details. Check gateway availability,
credential status and acq egress diagnostics. Do not enable verbose proxy logs
or copy model prompts/credentials into an issue.

Only ordinary function tools are supported. Server-side Anthropic tools are
rejected; optional thinking/beta/cache fields do not pass through. Validate
specific model capabilities before enabling richer inputs. The count estimate
is conservative and may make the context look fuller than it actually is.

Claude may warn that a gateway deployment ID is an unrecognized model and use
default context metadata. This is distinct from a routing failure. Do not assume
the native model's context window or feature set from its USAi deployment name.

## TUI or browser is unreachable

Use a real interactive PTY through acq, not a host Claude process or a pipe.
For a browser, apply the separate Paseo kit and select Claude in its UI.
`acq ports <sandbox>` shows the host mapping for guest 6767. The browser must
connect to that host-loopback address, not the microVM's loopback address.
Do not publish the model proxy: it is not a browser UI.

Paseo's wrapper for OpenCode does not replace the `claude` wrapper. If Paseo
cannot discover Claude, inspect the daemon's non-interactive PATH and confirm
`~/.local/bin/claude` is executable. Browser composition requires live validation
on your sandbox-capable host; this repository's unit tests cannot prove it.
