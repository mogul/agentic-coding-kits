# Delegation Prompt Template

Start every implementation or fix prompt from this list and cut what does not
apply. Each rule below exists because an agent went wrong without it. Pair it
with the completion clause for the delivery level (SKILL.md, section 5).

## Template

```text
Task: <issue or finding, quoted exactly from the review or issue>
Delivery level: <report-only | uncommitted | draft-push | ready-push>
Branch / workspace: <name>. Base: <full SHA>. Push target: <remote branch>.

Before the first edit:
- Confirm `git merge-base HEAD origin/<default>` equals the base SHA, and that
  HEAD equals the remote head you are told to extend. If not, stop and report.

Rules:
- Plain fast-forward push only. Bring in the base branch with a MERGE, never a
  rebase, unless told to. Force-push only when told to, with lease.
- Do not comment on the PR, edit its body, or change draft/ready state. The
  coordinator does that. Do not merge.
- Never print, log, or paste a secret value. Never run bare `env`, `printenv`,
  `export -p`, `set`, `gh auth token`, or an unfiltered `gh auth status`.
- Never delete files or directories you did not create, including shared
  scratch space and other agents' environments. If disk is low, stop and report.
- Reproduce first: show the new test failing on the current code. Then fix.
  Then give a mutation proof: revert the fix, see the test fail, restore it,
  see it pass. Say what the test does not cover.
- Run focused tests only. Run at most one heavy suite at a time. CI runs the rest.
- No external web search or search-service prompts. Fetching public project
  sites (code hosts, package registries) is fine.
- Launch ONE read-only, blocker-only adversarial reviewer subagent over your
  diff before pushing. Loop until it reports no blockers. After you apply its
  suggestions, run it again, or say that you did not.
- Clean up only scratch you created. Name anything you leave behind.
- If the push is rejected for a credential limit (for example, a workflow file
  and a token without that scope), stop. Do not retry. Report the exact error
  and a one-line host command (references/host-commands.md).

Final report (short, no pasted logs): commits (every one, including any made
after you first reported), head SHA, what the tests prove and do not prove,
what you left behind, one exact blocker if any. The coordinator reads the
commits and PR for detail.
```

## Notes for the coordinator

- Quote the reviewer's findings verbatim. A paraphrase drifts.
- Keep one agent per branch. If an agent errors with a transient network error,
  re-prompt it ("restart from the top; the worktree is clean") before replacing it.
- Verify claims yourself: heads, CI state, "no conflicts". Agent reports of
  "CI started" were stale more than once.
- An agent can make a commit after its final report. Compare the remote head with
  the head it reported before you trust either.
- Reasoning level and model follow SKILL.md section 5. Do not copy model names
  from old prompts.
