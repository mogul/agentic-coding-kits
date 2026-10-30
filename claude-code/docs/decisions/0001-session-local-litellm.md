---
title: "Use a session-local LiteLLM bridge for Claude Code"
description: "Bridge Anthropic Messages to OpenAI Chat Completions without publishing a model gateway."
status: draft
tier: 2
date: "2026-10-30"
last_updated: "2026-10-30"
decision_status: proposed
decision_makers: ["Repository maintainers"]
nist_controls: ["AC-6", "SC-7", "SC-8", "SI-10", "SR-3"]
impact_level: "Not assessed"
ato_relevance: "Not assessed"
risk_treatment: mitigate
---

# Use a session-local LiteLLM bridge for Claude Code

## Context and problem statement

Claude Code speaks Anthropic Messages. USAi exposes Claude models through
OpenAI-shaped endpoints, including Chat Completions but not Responses in the
observed test. A microVM has no desktop display. Model calls and coding tools
must stay in the guest while the human interacts from the host.

## Decision drivers

- Reuse existing streaming/tool translation instead of writing a protocol adapter.
- Read provider-neutral inputs and injected credentials, without storing keys.
- Avoid global configuration ownership, shared daemon/port races, and GUI dependencies.
- Pin both supported guest architectures and every bridge dependency.
- Keep user permission prompts and provider egress controls intact.

## Considered options

1. Claude Code Router: purpose-built routing, but its current CLI introduces a
   management UI, database/native dependency, and larger configuration surface.
2. Full LiteLLM proxy: established Claude integration, but more endpoints and
   management/auth/storage features than a single guest session needs.
3. LiteLLM library behind a narrow, session-local facade: reuse translation,
   exposing only authenticated Messages and token-count routes.
4. Write a translator: minimal dependencies, but high maintenance and protocol risk.

## Decision outcome

Propose option 3. Each wrapper invocation pre-binds a random guest-loopback port,
spawns a ready-gated service, runs Claude and terminates only that service on exit.
Force LiteLLM's `use_chat_completions_url_for_anthropic_messages` setting; the
default Responses path fails on the observed USAi endpoint. Do not publish the
proxy. The host uses acq's TUI/PTY connection; the existing Paseo kit provides
optional browser access via its own published UI port.

The observed gateway repeats tool IDs across argument chunks; LiteLLM emits
separate incomplete SSE blocks for them. Normalize consecutive same-ID blocks
into a single call without changing tool names or argument bytes. A regression
fixture and live Claude Read/result continuation validate this adapter.

Pin LiteLLM 1.100.4 with patched filelock 4.2.1. Newer LiteLLM releases currently
cap filelock below 4.0, which conflicts with published filelock advisory fixes.
The chosen locked set was audited without reported vulnerabilities.

Install Claude's native npm platform artifact after SHA-256 verification, without
an upstream install script. Install bridge dependencies as hash-locked wheels in
a dedicated per-user venv. Installation and session routing fail visibly rather
than fallback to Anthropic or an unpinned dependency.

## Consequences

### Distribution and validation ownership

Distribute the kit in `mogul/agentic-coding-kits`, with no runtime dependency on
the Patterns repository layout. Keep the neutral contract's validation code in
its upstream home and use a pinned Patterns checkout from shared repository
tooling. The kit retains its hash-locked runtime, tests, and operator verification;
the destination CI discovers kits and tests them through a common runner rather
than importing the Patterns skill/routing/index pipeline. Provenance is recorded
in `NOTICE`, and downloaded dependencies retain their own licenses.

Positive: no database, no desktop, no proxy administrative API, no stored keys,
no global settings replacement, independent concurrent sessions, both Linux architectures.

Negative: LiteLLM still has a sizable dependency tree; native npm distribution is
deprecated upstream and may disappear. Claude is proprietary and requires human
license/terms review. Ordinary tool use is supported, but Anthropic-specific
thinking/server tools/cache semantics and exact tokenizer behavior are not.
Conservative token counts can overestimate context usage. Browser composition
and actual microVM PTY/lifecycle must be tested on a capable host.

The facade's input boundary accepts only model IDs from the authoritative
snapshot and ordinary request fields. Provider routing never comes from client
bodies. Same-user environment separation does not prevent a shell-capable agent
from recovering credentials; the microVM/backend egress remains the boundary.
Control tags describe design concerns, not a compliance or ATO assertion.

## Links

- [LiteLLM Claude Code integration](https://github.com/BerriAI/litellm/blob/main/cookbook/ai_coding_tool_guides/claude_code_quickstart/guide.md)
- [LiteLLM Messages dispatch implementation](https://github.com/BerriAI/litellm/tree/main/litellm/llms/anthropic/pass_through/messages)
- [Claude Code Router](https://github.com/musistudio/claude-code-router)
- [Claude Code distribution](https://github.com/anthropics/claude-code)
- [Provider contract](https://github.com/GSA-TTS/agentic-coding-patterns/blob/main/integrations/isolation/docs/provider-input-contract.md)
- [Kit README](../../README.md)
