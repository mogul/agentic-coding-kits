## Summary

Add an experimental `claude-code` agent kit that runs Claude inside an acq
microVM using a configured OpenAI-shaped model provider, including USAi.

- Pinned SHA-256-verified Claude native binaries for Linux x64 and ARM64.
- Private authenticated, session-local LiteLLM bridge from Anthropic Messages
  to OpenAI Chat Completions, with hash-locked wheel-only dependencies.
- Unprivileged installation, including pip bootstrap for guests without ensurepip.
- Claude-owned model catalog and explicit canonical-name substitutions; no
  separate Paseo catalog projection or global user-config rewrite.
- Host TUI access and optional browser access through the separate Paseo kit.
- README warning: browser picker lists more choices than the configured
  OpenAI-shaped model provider supports; tracked at getpaseo/paseo#8321.

Also consolidate repository CI into a four-kit matrix plus a Claude Python 3.12
lane, reusing pinned upstream Patterns validators rather than importing the
Patterns skill/index toolchain. Shared checks cover lint/format, ShellCheck,
contracts, local doc links and executable modes, tests, dependency audits,
unsafe-shell patterns, and secrets. CI uses read-only permissions, SHA-pinned
actions and checksum-pinned Gitleaks; no model credentials or VM execution.

## Verification

- Local `make check` passed with the pinned Patterns checkout and verified
  Gitleaks executable; all four kits validated and the provider bundle validated.
- Claude offline suite: 27 passed / 3 explicitly gated live skips.
- Actual relocated Claude live/unit/lifecycle suite: 30 passed, with four
  upstream Pydantic deprecation warnings.
- Actual CLI text, file tool/result continuation and real SDK canonical
  Sonnet 5.5 model switch were exercised through USAi.
- Operator observed ARM64 MSB 0.7.7 installation, provider-root presence,
  browser access, and Sonnet 5/5.5 calls from the acq Quickstart checkout.
- Independent adversarial review performed; reproducibility findings addressed.

GitHub Actions execution and local Python 3.12 execution remain unverified in
this session. Native x64 execution, backend mount enforcement, actual browser
permission/disconnect paths, and enterprise CA-specific validation remain live
gates. Offline x64 CI does not prove the native x64 Claude executable works.
See `claude-code/docs/verification.md` for history and limitations.

## Security and licensing

No credentials are stored in the kit, generated model settings, or CI.
Model routing comes from acq's backend-owned provider input; the proxy never
accepts client-supplied provider routing. Claude child environments have projected
provider credentials stripped, but this is defense in depth, not same-user
process isolation. The kit publishes no model API port and enables no permission
bypass. Optional Paseo browser exposure retains its separate trust boundary.

Kit provenance from the local CC0 Patterns worktree is recorded in `NOTICE`;
distribution uses this repository's MIT license. Claude Code remains proprietary,
and downloaded dependencies retain their own licenses.

## Rollback

Remove the kit reference and recreate the disposable test sandbox without it.
Existing Claude user settings and transcripts are not overwritten. Revert the
repository change to restore the former CI layout if needed.

## AI assistance

Implementation, tests, documentation, and independent reviews were AI-assisted.
The human operator performed the reported macOS/MSB/browser checks. Human review
is required before production use. No compliance or ATO assertion is made.
