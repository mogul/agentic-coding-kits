---
title: Use an invocation-owned Responses bridge
description: Preserve acq provider ownership while supporting Codex
status: draft
tier: 2
date: 2026-10-31
---

# Use an invocation-owned Responses bridge

## Context

The existing provider contract describes Chat Completions, whereas Codex
0.166.0 accepts only Responses. Provider metadata must not select arbitrary
transports or supply credentials to unrelated hosts.

## Options

1. Require a Responses provider: incompatible with the current neutral contract.
2. Add a large translation dependency: more installation/supply-chain burden.
3. Implement a bounded standard-library text/function facade.

## Decision

Prototype option 3. Each invocation owns an authenticated loopback server;
the configured HTTPS endpoint is the only upstream route, with redirects denied.
Native model identifiers survive unchanged. No daemon or provider kit changes.

## Consequences

No extra runtime dependencies, but the supported protocol subset is limited.
Responses are buffered. Full streaming, media, reasoning and server-side state
are not claimed. Human review and real CLI/Paseo validation are release gates.
