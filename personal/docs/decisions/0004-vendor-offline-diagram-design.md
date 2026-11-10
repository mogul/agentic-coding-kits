---
title: "Vendor Diagram Design with offline defaults and guarded export"
description: "Pinned design guidance with project-local state and explicit isolated browser approval"
status: draft
tier: 2
date: "2026-11-09"
last_updated: "2026-11-09"
decision_makers: ["Bret Mogilefsky"]
nist_controls: ["AC-6", "CM-3", "SA-11", "SC-7", "SI-10"]
impact_level: "Moderate"
ato_relevance: "no"
risk_treatment: "mitigate"
---

# Vendor Diagram Design with guarded export

## Context and problem statement

The personal kit needs editorial diagrams without mutable acquisition, global
profile writes or default external-font requests. Upstream PNG export opens HTML
in a browser without enforcing preflight or network isolation. User approval alone
does not address those implementation risks.

## Decision drivers

Preserve useful diagram/import/animation guidance, attribution and reproducibility;
keep project scope and offline behavior; require human authorization for browser
execution; fail closed when provisioning/isolation is unavailable.

## Considered options

- Unmodified marketplace installation or mutable skill fetch.
- Static-only guidance with no animation or export.
- Selective pinned vendoring with local policy and an isolated export guard.

## Decision outcome

The user approved the third option on 2026-11-09. This AI-authored record remains
a draft for human review. Source is pinned at
`f2496acbde9f45ccb55c24d4f75210c8a1355df8` (2.6.153); the generator validates Git
blob IDs and records source/output hashes. No upstream dependencies or maintainer
scripts are installed. Fonts are system-only; branding stays in approved project
files; third-party logos and shared home profiles are excluded.

SVG export validates bounded input/output and calls an internal offline transformer.
PNG requires explicit per-export session approval, Linux Bubblewrap, and a separately
provisioned Python Playwright/Chromium runtime. Bubblewrap isolates network, processes,
environment and mounts; only a source snapshot, runtime and temporary output are
available. No unrestricted fallback exists. The current capture is the complete
static motion frame, while human-opened animation remains available.

The initial browser release gate is closed in code. Per-process rlimits are not
an aggregate Chromium memory/process budget, and the current virtual-memory limit
may prevent Chromium startup. Live validation and appropriate aggregate limits
must precede opening the gate; never fix compatibility by disabling its sandbox.

## Consequences and limitations

- The kit adds no startup command or egress host.
- Browser dependencies remain operator-provisioned; no download/install is implicit.
- Non-Linux automated PNG export is unsupported.
- Quality checks are not sanitizers. Conservative guards may reject valid complex
  diagrams; fix the source rather than weaken isolation silently.
- Approval acknowledgement is not authenticated consent. Agent tool permissions
  enforce human approval; agent-writable kit files are not a trust anchor.
- Project path handling assumes trusted concurrent project writers. It is not an
  adversarial filesystem sandbox. Browser input is an immutable copied snapshot.
- Live Chromium capture cannot be claimed until a runtime is provisioned and
  isolation/render tests pass. Missing prerequisites produce BLOCKED.

## Verification and rollback

Run `personal/scripts/verify` and `python3 scripts/run-kit-tests.py personal`.
Tests cover hashes, policy violations, SVG extraction, browser approval denial and
missing-runtime failure. Live Bubblewrap checks must establish no host-network or
sensitive-mount access. Browser smoke tests remain separate from offline tests.
Human review is required before deployment. Roll back this change through a reviewed
revert, preserving the previous kit revision; do not edit active generated files.

## Tracked release gate DG-001

**Status: blocked.** This decision record is the repository-local change-tracking
record for opening the PNG export gate. Owner: human kit maintainer. Trigger:
explicit approval to provision a pinned Playwright/Chromium runtime and finish
the export isolation work. Required change: establish aggregate memory/process
limits compatible with Chromium, then demonstrate real static and animated-source
PNG capture, denied external requests, hidden sensitive mounts, sandbox enabled,
bounded dimensions, failure/timeout cleanup and repeated deterministic output.
Only a reviewed change satisfying those checks may set
`BROWSER_EXPORT_VALIDATED = True`. No browser dependency installation or gate opening
is authorized by the current vendoring approval.

## Verification transcript (2026-11-09, AI-assisted)

| Check | Observed result |
| --- | --- |
| `personal/scripts/verify` | 30 passed, 0 failed; optional `acq` unavailable |
| `python3 scripts/run-kit-tests.py personal` | Same offline gate passed |
| `python3 personal/scripts/test-diagram-design.py` | 19 regression tests passed, including synthetic imports, adversarial XML/CSS cases and warning propagation |
| `python3 personal/scripts/vendor-diagram-design --check --source-dir <reviewed-tree>` | Generated payload matches verified pinned sources and adaptations |
| Ruff check/format on local authoring and export helpers | Passed using existing hash-locked development tools |
| `python -m pytest scripts/tests -q` | 69 passed |
| `python -m pip_audit --strict --require-hashes --disable-pip -r requirements-dev.lock` | No known vulnerabilities reported |
| `git diff --check` | Passed |
| Live Bubblewrap synthetic fixture | Approved input readable; host sentinel/environment hidden; host loopback unreachable; only loopback interface visible |
| Chromium/Playwright capture and aggregate budgets | BLOCKED, not provisioned or validated; release gate closed |
| Live Paseo Emoji/Agent Office installation and UI | NOT RUN |

No browser dependencies, live plugins, provider configuration, startup commands or
egress hosts were added during verification. Existing locked development tools
were installed in an isolated temporary environment with explicit user approval.
