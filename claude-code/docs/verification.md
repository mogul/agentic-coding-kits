---
title: "Claude Code Kit Verification Record"
description: "Observed test results and unverified microVM gates."
status: draft
tier: 2
last_updated: "2026-10-30"
---

# Verification record

AI-assisted implementation and independent adversarial reviews, recorded
2026-10-30. Individual commands and observed output are in the session's tool
history. Human review is required before production use. No commit or push was
performed, and no VM was launched.

## Verification history

### Relocation check

After copying this kit into `mogul/agentic-coding-kits`, the actual runtime
payload was exercised again: 30 live/unit/lifecycle tests passed (four upstream
Pydantic deprecation warnings). Offline execution reports 27 passed and three
explicit live skips. Local kit documentation links resolve. No host-global
Claude/Paseo configuration was changed by the relocation.

### Destination repository transcript

In `mogul/agentic-coding-kits`, `make check` passed with the pinned Patterns
validator checkout and a checksum-verified local Gitleaks executable. This runs
Ruff lint/format, ShellCheck, all four kit contracts, provider input validation,
shared tooling tests, each kit's offline runner, runtime/development dependency
audits, unsafe-shell checks, and secret scanning. Model credentials and VM
creation are not part of that command. The development and Claude-test locks
are universal hash locks; Python lanes select their requested interpreter.

GitHub Actions and local Python 3.12 execution were not observed in this session.
CI provides the Python 3.12 and 3.14 lanes; these are planned CI checks, not a
claim of a completed remote run.

### Historical Patterns repository transcript

The following table records checks run before relocation in the source Patterns
repository. Its Make targets and 745-test count do not describe this repository.

| Check | Command | Result |
|---|---|---|
| Repository validation | `make validate` | PASS; existing advisory warnings remain |
| Kit specs/payload wiring | `make validate-kits` | PASS; 12 kits and 2 templates |
| Provider contracts | `make validate-provider-input-contract` | PASS; 3 bundles |
| Index/catalog | `make generate-check` | PASS; unchanged and current |
| Repository tests | `make test` | PASS; 745 tests |
| Clean isolated kit suites | `make test-kits` | PASS; temporary runner provisions bridge dependencies |
| Live/lifecycle kit suite | `RUN_CLAUDE_LIVE=1 python -m pytest <kit>/tests -q` with explicit test binary and provider root | PASS; 27 tests |
| Python lint/format | `ruff check <kit>`; `ruff format <kit>` | PASS |
| Shell wrapper | `shellcheck <kit>/files/home/.local/bin/claude` | PASS |
| Unsafe-shell scan | `make scan-shell` | PASS; 0 errors/warnings |
| Locked dependency audit | `pip-audit -r <kit>/files/home/claude-code/requirements.lock --disable-pip --no-deps` | PASS; no known vulnerabilities |
| Python compilation | `python -m compileall -q <kit>/files/home/claude-code` | PASS |
| Whitespace | `git diff --check` | PASS |
| Host-side verifier | `python <kit>/scripts/verify` | UNVERIFIED; expected exit 3, 24 offline tests passed / 3 live tests skipped |

The isolated interpreter contains the exact runtime wheel lock plus test tools.
Live credentials stayed in the injected environment; test files contain only
public provider facts, a model snapshot, and synthetic text. Credentials were
not included in prompts, generated configuration, or recorded output.

## Live observations

### Operator microVM validation and model catalog follow-up

The operator's macOS host ran MSB 0.7.7 with the Quickstart checkout at e4feef5.
The older Homebrew acq 4.1.1 lacked provider projection. With the checkout,
the provider validator accepted one USAi bundle, the guest received a generation
root under `/var/lib/acq/provider-input`, and Claude returned `ACQ_OK`.
The pip-wheel bootstrap installed successfully in the actual Python 3.14 guest
without ensurepip. The operator reached Paseo's browser UI and successfully
prompted Sonnet 5. Exact-ID CLI Sonnet 5.5 returned `ACQ_SONNET_55_OK` too.
The native browser model picker exposed incompatible Claude aliases, motivating
the Claude-owned catalog change rather than a second projection into Paseo.

The updated wrapper's real SDK `supportedModels()` probe returned the exact
snapshot IDs and Default resolved to `claude-sonnet-5`; Fable was absent.
It uses temporary Claude settings without rewriting global config. The updated
live/unit/lifecycle suite passed 29 tests, with four upstream deprecation warnings.
The operator's refreshed browser picker remains a required confirmation.

The operator subsequently confirmed Paseo 0.13.0 retains curated native entries
after restart. Its Sonnet 5.5 ID is `claude-sonnet-5-5`, not USAi's dotted ID.
A real Claude SDK recorder probe with `modelOverrides` observed the dotted
gateway ID on a `setModel` request. A second real SDK probe through the actual
kit wrapper and USAi successfully switched using the canonical hyphenated name.
The kit now includes only explicit same-version override pairs when the target
exists in the selected snapshot. Fable and extended-context variants stay unmapped.
This fixes equivalent-name routing, not Paseo's hardcoded picker contents.

- USAi returned `ACQ_OK` through Chat Completions as JSON and Anthropic-shaped SSE.
- Forced function-tool requests returned `tool_use`.
- The actual checksum-verified **ARM64 Claude Code 2.1.314** executable ran
  through the private launcher and returned `ACQ_OK`.
- The real CLI used Read on a synthetic file and returned its marker, proving
  tool arguments and tool-result continuation through the stream normalization.
- Controlling-PTY regressions performed an immediate stdin read. Targeted
  SIGHUP/SIGTERM exited 129/143 and stopped Claude, its real proxy, and a
  synthetic SIGTERM-resistant tool child. Two-provider credentials were stripped.
- Both x64 and ARM64 native archives were downloaded and SHA-256 checked.
  Only ARM64 execution was possible on this host.

LiteLLM emitted four Pydantic deprecation warnings in live tests. USAi deployment
names can trigger Claude's unrecognized-model/context-metadata warning. Neither
warning is hidden as proof of complete upstream compatibility. Parallel tools,
extended thinking, and richer modalities were not validated.

## Review findings addressed

Independent review found clean-CI dependency wiring, stream concurrency lifetime,
hangup cleanup, unrelated credential forwarding, a session-specific interpreter
path, and a terminal-foreground race. Fixes were reviewed again; the final scoped
recheck found no concrete merge blocker. Live CLI testing also found repeated
tool IDs splitting JSON arguments; a regression and actual Read/result round
trip now pass.

## Pending host validation gates

- [x] Real acq MSB ARM64 microVM provisioning/startup installation, operator-observed.
- [ ] Backend provider-root read-only enforcement and startup ordering.
- [ ] Actual interactive permission prompts and host attach/disconnect.
- [ ] x64 guest installation and CLI execution.
- [x] Paseo composition: published host-loopback browser UI and Claude Sonnet 5/5.5 routing, operator-observed.
- [ ] Browser approval prompts and actual backend disconnect behavior.
- [ ] Enterprise CA trust through the actual guest's Python HTTPS client.

Initial validation was blocked by this environment's inability to launch
microVMs. The operator later confirmed ARM64 MSB installation, generation-root
presence, browser access, and Sonnet 5/5.5 routing as recorded above. Read-only
mount enforcement, permission/disconnect behavior on the actual backend, x64
execution, and enterprise CA-specific validation remain unverified. The kit
stays experimental and the verifier preserves exit 3 for incomplete live coverage.

## Rollback and security impact

Rollback: remove the extra kit selection and recreate the disposable sandbox
without it. Existing user Claude settings and transcripts are not overwritten.

Adds installation egress, locked dependencies, proprietary Claude software,
and an authenticated guest-loopback facade. This kit adds no host model API port,
Anthropic login, cloud relay, permission bypass, or production infrastructure
change. Optional Paseo exposure follows that kit's separate security boundary.
This record is evidence, not a compliance assertion.
