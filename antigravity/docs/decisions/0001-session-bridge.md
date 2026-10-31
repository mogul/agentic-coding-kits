---
title: Use an invocation-owned Gemini bridge
description: Route agy custom models to acq Chat Completions providers
status: draft
tier: 2
date: 2026-10-31
---

# Use an invocation-owned Gemini bridge

## Context and options

agy 1.4.12 rejects modelProvider=openai, but accepts session-only Gemini
settings and customModelsConfig.customModels. Considered native OpenAI routing
(not supported in the live probe), global Google settings (collides with other
agents), and an invocation-owned bridge with a dedicated persistent HOME.

## Decision

Prototype the bridge. Keep exact custom deployment IDs and expose those through
the wrapper's model discovery. Explicitly route internal lightweight housekeeping
to the configured small model. Use standard-library HTTPS with redirects denied.

## Consequences

No runtime dependency install, Google login or global Paseo writer. This loses
global CLI configuration/skill inheritance and requires a limited Gemini mapping.
Media/reasoning/native search are unsupported. Paseo's upstream plugin uses full
access; external workspace isolation and human review remain essential.
