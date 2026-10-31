---
title: Codex verification
description: Observed checks and remaining release gates
status: draft
tier: 3
---

# Verification

The official 0.166.0 ARM64 archive matched its published SHA-256 and the binary
ran on Linux ARM64. A real `codex exec` using a generated catalog and local
synthetic Chat Completions transport returned `CODEX_PROBE_OK`, exit 0.
This verifies the request path, not live upstream model access.

`python3 scripts/verify-native-cli.py codex --binary <pinned-binary>` passed:
exact custom ID, function call, real file write, tool result and final response.
The offline suite and process-group SIGTERM/SIGHUP tests passed. A separate
Paseo 0.12.0 daemon with an isolated HOME and ephemeral loopback port discovered
only `exact.test_model` and completed a real Codex session returning
`PASEO_KIT_OK` through the staged wrapper and a local HTTPS synthetic provider.

Final `make check` passed: lint/format, ShellCheck, six kit contracts, all kit
tests, 28 shared-tooling tests, dependency audits and secret scans. Codex's
14 tests passed on Python 3.12 and 3.14. Final adversarial review found no
blockers within the experimental text/function scope. The native verifier and
isolated Paseo session were rerun with the final code and passed.

Remaining gates: remote GitHub CI, interactive PTY, native x64 and live gateway.
No real model credential was sent during these probes.
