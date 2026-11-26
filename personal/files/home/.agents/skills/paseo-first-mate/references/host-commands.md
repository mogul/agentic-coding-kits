# Host Commands, Credential Limits, and Verification Tiers

Some work needs something the sandbox cannot do: a push the token may not make,
a run on the user's real machine, a platform you do not have.

## When the token cannot push

Seen with a token that lacks the scope to push `.github/workflows/*`. The same
shape applies to any push a credential refuses.

1. The agent commits locally and makes ONE plain push attempt.
2. If it is rejected, the agent stops. No retries, no workarounds.
3. It reports the exact error and one host command:

   ```text
   cd <worktree path> && git push origin HEAD:<remote branch>
   ```

4. The user runs it on their host.
5. The coordinator then reads the remote head and compares it with the reported
   commit. Agents sometimes commit after reporting, so the pushed head can differ.

The same token may be unable to re-run workflows, read branch protection, or use
some GraphQL fields. Say what you could not check rather than guess. A
reviewer request that fails on a GraphQL scope error works through REST:

```text
gh api -X POST repos/OWNER/REPO/pulls/N/requested_reviewers -f 'reviewers[]=LOGIN'
```

and `gh api repos/OWNER/REPO/pulls/N` returns `.requested_reviewers`. When
requesting a re-review, comment first (no recap of the diff), then request it.

## Files the host must read

The host cannot see the sandbox's temporary directories. Copy anything the user
must read or run (a PR body, a script) into the worktree, and keep it out of Git
with the worktree's `.git/info/exclude` (use `git rev-parse --git-path info/exclude`
for the path). Then refer to it by a worktree-relative path:

```text
cd <worktree path> && gh pr create --repo OWNER/REPO --base main --head BRANCH --title "TITLE" --body-file PR-BODY.md
```

## Writing a command the user pastes

- One line, starting with `cd` to the worktree. The user's shell may be anywhere.
- No `#` comments inside the block. An interactive zsh passes `#` through as an
  argument. Put expectations in prose outside the block.
- Say what a pass and a fail look like, and which revision it tests.
- Applies equally to instructions you give another agent for a host run.

## Copy-paste recipe pitfalls

Found when another agent ran a recipe on a native platform:

- `git clone -c key=value` does not persist the setting. Use `--config`.
- `git checkout` does not rewrite files whose content is identical between
  commits. To force re-materialization: `git rm --cached -r -q . && git reset --hard -q`.
- Global commit signing can break tests that make scratch commits. Disable it per
  process with `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=commit.gpgsign GIT_CONFIG_VALUE_0=false`.
- A tool may exist on the host under a name you assumed absent (for example,
  `python3`). A "missing tool" test needs a PATH-narrowing recipe that was proved
  in the same session.
- Use `timeout --foreground`, show live output, and set a per-step timeout (SKILL.md,
  Working With the User).

## Evidence

- Tie every result to the exact head SHA it tested. Accept a PASS only for that SHA.
  Label an older report "old head, does not carry over".
- `NOT EXERCISED` is a first-class result. Never convert it to PASS.
- Hosted CI is the authority. Local runs are focused checks only. If the sandbox
  cannot run a platform (macOS, Windows), say so on each PR.

## Tiers for risky acceptance

When the real account is the only account, split the verification:

| Tier | Where | What |
|------|-------|------|
| 1 | The user's real account | Read-only, preview, help, dry-run, and cancel paths |
| 2 | An isolated account, VM, or CI runner | Anything destructive |

Record each result under its tier. Do not call a Tier 1 pass proof of a Tier 2
behavior. When no safe local test bed exists, a hosted runner can be one: a workflow
with `workflow_dispatch` and a `ref` input, run on a hosted runner of the target
platform, inside a refusal guard that makes it exit unless it runs in CI.
