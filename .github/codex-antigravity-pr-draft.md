## Summary

Add independently installable experimental Codex and Google Antigravity (`agy`)
agent kits consuming acq's neutral configured Chat Completions provider input.
No USAi-specific endpoints, model catalogs or credential values are embedded.

- Codex 0.166.0: per-invocation authenticated Responses facade, exact-ID native catalog.
- Antigravity 1.4.12: per-invocation authenticated Gemini facade, custom-model settings.
- Standard-library runtime; no new third-party runtime dependencies.
- Six-kit CI matrix, Python 3.12 coverage and repeatable credential-free real-CLI verifier.
- No changes to existing kits' runtime behavior or Paseo's configuration/catalog.

## Context and plan

Existing provider kits publish Chat Completions-compatible facts/catalogs.
Neither agent's native wire API matches that contract. Keep adaptation in each
agent kit, preserve exact IDs, scope translation to text/function tools and
reject unsupported behavior. Design records live with each kit.

This branch is based on the Claude-kit branch so it reuses its shared validation
and executable-index guard. It must target that branch until the prerequisite
is merged, or be rebased onto main afterward. Do not include unrelated base work
as a new change.

## Verification transcript

- `make check PATTERNS=<pinned-checkout> GITLEAKS=<pinned-binary>`: PASS.
  Includes Ruff, formatting, ShellCheck, all six contracts, all offline suites,
  28 shared tests, dependency audits, unsafe-shell and secret scanning.
- Codex: 14 tests, PASS on Python 3.12 and 3.14.
- Antigravity: 9 tests, PASS on Python 3.12 and 3.14.
- `python3 scripts/verify-native-cli.py codex --binary <pinned-arm64-binary>`: PASS.
- Equivalent Antigravity command: PASS.
  Both execute real CLI file tools and verify exact IDs, tool results and final replies.
- Separate Paseo 0.12.0 daemon, isolated HOME/port and local HTTPS synthetic provider:
  both catalogs contain only `exact.test_model`; both real sessions complete with
  `PASEO_KIT_OK`. Final code rerun PASS. Active user daemon was untouched.
- Independent adversarial reviews: concrete findings fixed and regressions added;
  final review reports no blockers within experimental text/function scope.

These are real CLI/protocol/Paseo tests against synthetic model output, not live
gateway/model-quality verification. Remote CI, native x64 and interactive PTY
remain unverified. Terminal suspension/job control is unsupported.

## Security impact

New installation hosts and private loopback services. No published model ports,
persisted keys, disabled TLS verification or global provider config writes.
Upstream redirects are denied; installer redirects checked before following.
Local auth token is separate from outbound correlation metadata. Tool/field
translation uses a limited allowlist. Same-UID guest processes are not isolated.
Paseo's Antigravity plugin uses full access; the kit's terminal wrapper does not
enable that flag. The synthetic file fixture explicitly opts into it.

## Limitations

Buffered responses, text/function tools only, no media/native search/encrypted
reasoning/server-side Responses state. Antigravity's fixed automatic thought
envelope is explicitly ignored by the text/function policy; effort flags reject.
CLI state uses kit-owned persistent directories; normal user-global config is
not inherited. Generic Codex catalog instructions may affect model performance.

## Rollback

Revert this PR's commits. Remove the two kit references from future sandbox
creation. Existing sandboxes are not modified automatically; do not delete
conversation directories without operator consent.

## AI assistance and review

Implementation and verification were AI-assisted. Human review is required;
this is not production approval or a compliance assertion.
