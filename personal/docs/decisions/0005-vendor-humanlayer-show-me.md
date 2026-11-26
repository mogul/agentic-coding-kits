---
title: "Vendor HumanLayer's show-me skill"
description: "Ship a pinned, hash-verified visual communication skill in the personal kit"
status: draft
tier: 2
date: "2026-11-26"
last_updated: "2026-11-26"
decision_makers: ["Bret Mogilefsky"]
nist_controls: ["CM-3", "SA-11", "SR-3"]
impact_level: "Moderate"
ato_relevance: "no"
risk_treatment: "mitigate"
---

# Vendor HumanLayer's show-me skill

## Context and problem statement

The personal kit already carries an adapted `show-me` visual-guidance section inside
Matt Pocock's `pr` skill. The user requested the complete skill for use across agent
conversations. A mutable runtime installation would not reproduce the reviewed content
in fresh sandboxes.

## Decision outcome

On 2026-11-26, the user approved shipping the unmodified `show-me` skill from
`humanlayer/skills` at commit `4d69d20f6e9b57b4fcf0d501ccfb1be961f0f329`. The kit
ships `SKILL.md` and its OpenAI invocation policy at `~/.agents/skills/show-me/`.
The existing MIT notice travels with the copy. `vendor/humanlayer-show-me.json` records
the full commit SHA, source path, licence hash, and hashes of every shipped file;
`scripts/verify` fails on missing, extra, or modified files.

## Consequences and limitations

- The skill is user-invoked and does not run implicitly.
- It adds no dependency installation, startup command, network permission, or provider
  configuration.
- The skill can recommend creating an HTML artifact and opening it. The agent must still
  obtain any approvals required by its governing instructions before executing commands.
- The record is AI-authored and remains draft pending human review.

## Verification and rollback

Run `personal/scripts/verify` and `python3 scripts/run-kit-tests.py personal`. Human
review is required before deployment. Roll back through a reviewed revert of this
decision, the payload, lock, spec records, and attribution updates.
