---
title: Antigravity verification
description: Observed native routing and remaining release gates
status: draft
tier: 3
---

# Verification

The official 1.4.12 ARM64 archive matched the versioned Google manifest's
SHA-512. `agy --help` ran. A synthetic HTTP probe observed a request to
`/v1beta/models/test-model:streamGenerateContent` for an exact custom ID,
plus a separate lightweight housekeeping request.

The real CLI subsequently completed a text turn and a file-tool turn against a
synthetic transport. `python3 scripts/verify-native-cli.py antigravity --binary
<pinned-binary>` repeats the exact-ID/function/file/result path without credentials.
The native default headless mode denied a write; explicit full access in the
isolated fixture allowed it. Kit terminal defaults were not weakened.

A separate Paseo 0.12.0 daemon, isolated HOME and ephemeral loopback port
discovered only `exact.test_model` and completed a real Antigravity session
returning `PASEO_KIT_OK` through the staged wrapper and a local HTTPS synthetic
provider. Offline checks and all six repository contracts passed.

Final `make check` passed: lint/format, ShellCheck, all six contracts and all
kit/shared tests, dependency audits and secret scans. The nine Antigravity
tests passed on Python 3.12 and 3.14. Final adversarial review found no blockers
within the experimental text/function scope. The native verifier and isolated
Paseo session were rerun with final code and passed.

Remaining gates: remote GitHub CI, interactive PTY, x64 and live gateway.
These synthetic tests prove wiring, not remote model behavior or quality.
