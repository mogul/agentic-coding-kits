---
name: paseo-first-mate
id: paseo-first-mate
version: "1.3.0"
title: "Paseo First Mate"
description: "Coordinate a multi-issue engineering effort through isolated Paseo workspaces, structured GitHub metadata, dependency-aware delivery, change-detecting follow-up, and a durable handoff."
type: skill
status: experimental
owners:
  - "@mogul"
primary_personas:
  - developers
  - agents
requires:
  anchors: []
  skills: []
output:
  format: markdown
  contract:
    required_sections:
      - "Summary"
      - "Critical Path"
      - "Actions"
      - "Verification"
    prohibited_content:
      - "Secrets"
      - "Real PII"
      - "Real CUI"
      - "Internal URLs"
quality_gates:
  readability_max_grade: 10
  citations_required: false
collection: engineering
categories:
  - development
  - documentation
triggers:
  - "first mate"
  - "coordinate agents"
  - "multi-issue epic"
  - "manage several pull requests"
  - "delegate with Paseo"
tags:
  - "paseo"
  - "orchestration"
  - "github"
  - "delivery"
routing:
  task_types:
    - orchestrate
    - plan
    - review
  input_artifacts:
    - pull-request-diff
    - documentation
  output_artifacts:
    - documentation
  aliases:
    - "coordinating agent"
    - "delivery coordinator"
    - "epic coordinator"
  prefer_when:
    - "Work spans several tracked issues, branches, repositories, or dependent pull requests"
    - "The user wants one agent to delegate implementation while continuously managing delivery state"
  avoid_when:
    - "A single agent can complete one bounded change without coordination"
portability:
  opencode: true
  cursor: false
  claude_projects: false
  chatgpt: false
  generic_llm: false
changelog:
  - version: "1.3.0"
    changes: "One coordinator and one wait loop per effort (owner-keyed flock in the wait script with status, stop, and take-over; forks and resumed sessions are non-coordinators; never report a loop as running without a status result from this turn). Detector watches branches and workflows. Fresh-base rule, verified agent claims, and reading finish notices against agent status. Runtime acceptance signal, mutation proof, and post-merge proof. Repository PR standards override the template. Pending Decisions and Held Items handoff section, recorded permission policies, shape-only host reads, drafts for human threads, cleanup on merge, and new troubleshooting rows."
  - version: "1.2.0"
    changes: "Add a change-detecting check and background wait loop (bundled assets) as the token-cheap default, alongside the Paseo heartbeat; add the end-the-turn rule for quiet wake-ups, standing ready-when-green grant, agent self-review and reuse rules, filing rule, host-run script hygiene, reviewer reply guidance, and new troubleshooting rows."
  - version: "1.1.0"
    changes: "Add delivery levels (including user-granted ready-push), adoption procedure, audit-before-implement, private handling of security findings, permission and agent-cap guidance, compact handoff with clearable log, and trims."
  - version: "1.0.0"
    changes: "Initial release."
---

# Paseo First Mate

## Summary

Act as the coordinating agent for a multi-issue engineering effort. Maintain the
critical path, delegate bounded issue ownership into isolated Paseo workspaces,
keep GitHub relationships authoritative, respond to CI and review events, and
preserve enough durable context that another coordinator can resume safely.

The First Mate coordinates delivery. It does not replace code owners, approve
its own work, invent live validation results, or merge changes without explicit
authorization.

## When to Use

- An epic spans several issues or repositories.
- Multiple pull requests have strict merge or release dependencies.
- Implementation should be delegated while one agent manages the overall goal.
- The effort needs periodic CI/review follow-up over a long session.
- Context compaction or coordinator handoff is likely.

## When Not to Use

- Repository or classified-data rules prohibit the required tools.

Single-change and read-only work are covered by `avoid_when` above.

## Prerequisites

- Paseo projects registered for every repository in scope.
- Authenticated GitHub CLI with the minimum required permissions.
- Repository instructions loaded from each target checkout, including its
  one-command verification.
- A durable tracker containing the epic and implementation issues.
- Explicit approval before network, dependency, CI, release, merge, or other
  privileged operations when policy requires it.

## Core Invariants

1. GitHub issue, sub-issue, development branch, PR, review, and check metadata is
   authoritative. PR prose and the handoff are explanatory context, not the
   relationship database.
2. One implementation owner controls one issue or one explicitly combined atomic
   PR. Do not create duplicate agents on the same branch. Never open a
   standalone PR for intentionally folded work.
3. Enforce the user-provided active-agent cap. Review agents count while active.
   Keep one slot free for independent review when the cap allows. The user may
   change the cap; record each change.
4. Same-repository linear dependencies use real Git ancestry and `gh stack`.
   Cross-repository dependencies use draft guards, structured issue metadata,
   and documented merge order. Never create a fictional cross-repository stack.
5. Use focused tests and blocker-only adversarial review before pushing. Let
   required CI run the full suite once. Fix only observed failures. The
   `ready-push` level (see Delivery Levels) is the only exception to waiting for
   CI before a PR is marked ready.
6. Never present mocked, offline, or simulated evidence as live end-to-end proof.
   A green pipeline is not proof that the deployed thing runs: a deploy can
   succeed while the application it created crash-loops. Name the runtime signal
   up front (for example, the process count and a specific startup log line), and
   keep the issue unverified until someone has observed that signal.
7. Label every claim as verified, hypothesis, or unverified. Fix the live
   acceptance criterion before implementation starts.
8. Never archive dirty, unpushed, unrecoverable, or intentionally retained work.
9. Never include token, key, credential, or secret values in prompts, logs, API
   calls, comments, or handoff documents.
10. Hold security-relevant findings (guest-integrity, downgrade, trust-boundary)
    privately and ask the user how to proceed. Do not file them as public issues.
11. Never merge, and never change PR draft/ready state, beyond what the user has
    explicitly granted.
12. One coordinator per effort. A resumed or forked session is a non-coordinator
    until the user says it is the coordinator (see section 1). A non-coordinator
    starts no wait loop and takes no action on the watched PRs and agents.

## Delivery Levels

State the level in every delegation prompt. The user sets it; the coordinator
never raises it.

| Level | Agent may | Typical use |
|-------|-----------|-------------|
| `report-only` | Analyze and report | Audits, investigations |
| `uncommitted` | Edit the worktree; no commit, push, or PR | Work awaiting plan or commit approval |
| `draft-push` | Push and open a draft PR; CI runs | Default for normal work |
| `ready-push` | Push and mark the PR ready immediately, without waiting for CI | Simple or urgent changes, only when the user says so |

Separately, the user may grant a standing **ready-when-green** rule: the
coordinator may mark a draft PR ready for review on its own initiative when all
checks pass and no further commits are expected without external review. It is a
recorded grant, never a default. It never covers merge, release, un-readying, or
a PR whose merge guard depends on other work. Record the rule, date, and scope in
the handoff.

`ready-push` rules:

- It is granted per named PR, never as a default. Record the PR, date, and the
  user's stated reason in the handoff.
- Focused tests and static checks still run before the push. Blocker-only
  adversarial review is the default; the user may waive it for an urgent fix, and
  the waiver is recorded.
- CI still runs after the PR is marked ready. Watch it and report a failure
  promptly; do not stay silent on that PR.
- A PR whose merge guard depends on another PR, release, or pin stays draft
  unless the user explicitly overrides that.
- The grant covers draft to ready only. It never covers merge.

## Procedure

### 1. Adopt or Establish the Role

When resuming an existing effort, or when this session is a fork of another:

1. Read the handoff.
2. Compare the coordinator ID in its Controls with your own `$PASEO_AGENT_ID`.
   If they differ, or none is recorded, you are a non-coordinator: do steps 3
   onward read-only (use `first-mate-check.py --show`, which saves nothing),
   start no loop, and ask the user whether you are taking over. A fork inherits
   the handoff, including its claim that a loop is running; that claim is not
   evidence.
3. Refresh authoritative remote state before reporting anything.
4. Verify that every control the handoff names actually exists on the accessible
   daemon: wait loop (`first-mate-wait.sh status`), schedules, workspaces,
   agents. Record any control that is missing or invisible; do not assume its
   state, resume it, or recreate it without authorization. Reconcile workspaces
   against `paseo workspace ls`; retained-workspace notes may be stale in a fresh
   sandbox.
5. As the confirmed coordinator, ensure one wait loop is running (section 8).
   Record your agent ID as coordinator in the handoff.

### 2. Establish the Mission

Read the epic, all structured sub-issues, relevant open PRs, architecture
decisions, repository instructions, and current code boundaries. Report issues
that are in the epic's narrative scope but missing from its formal child list.
State one measurable milestone rather than treating the entire backlog as one
deliverable.

Create a dependency graph:

```text
contract or prerequisite
        -> producer implementation
        -> consumer implementation
        -> release or pin
        -> live validation
        -> milestone
```

Classify every related issue as one of `critical-path`, `parallel`, `deferred`,
`superseded`, `completed`, or `out-of-scope`. Do not close or supersede an issue
until the replacement relationship and delivered scope are unambiguous.

### 3. Reconcile GitHub Metadata

For every implementation unit, propose these changes and apply them with the
user's approval:

- Make it a real epic sub-issue where supported.
- Create the development branch through the issue relationship.
- Create the PR from that linked branch.
- Verify structured closing references before merge.
- Add retrospective closing references for older issues only when the merged PR
  clearly delivered their acceptance criteria.
- Close superseded issues as not planned and name the replacement in a comment.
- Make sure each PR body mentions any folded work.

Fully qualify tracker references in durable GitHub artifacts:

```text
OWNER/REPOSITORY#NUMBER
```

Do not put tracker references in durable repository docs or code comments. In
user-facing messages, link every PR and issue with a full Markdown link.

### 4. Audit Before Implementing Broad Issues

For a broad or partly-stale issue, delegate a read-only audit pinned to an exact
head first. It returns a table of decision, current authority, remaining change,
and test, plus draft child issues. An audit can correct a wrong premise about
what is already done.

1. Copy the audit report into the coordinator worktree before archiving the
   auditor's workspace.
2. Propose slices ranked by size and risk. Get approval before launching, and
   start with the smallest.
3. Treat security-relevant findings under invariant 10.
4. Label each finding verified, hypothesis, or unverified.

### 5. Allocate Workspaces and Agents

Use one Paseo workspace per issue branch (unless a single atomic PR is better),
in the project configured for its repository.

Models:

- Always pass the model and reasoning level explicitly. The provider default may
  be expensive and the CLI may not expose profiles; confirm what a new agent
  resolved to.
- Use a low-cost model for bounded tests, docs, or small fixes. Use a balanced
  model at medium reasoning for feature work and for the coordinator. Reserve high
  reasoning for architecture, security boundaries, complex rebases, or repeatedly
  blocked work, and delegate that depth rather than raising the coordinator's cost.
- Prefer a different model family for adversarial review.

Reuse and self-review:

- Prefer reusing an existing research or audit agent, via `paseo send`, for the
  implementation that follows. Its workspace already has the user's auto-accept
  setting, so it avoids permission prompts. Keep such a workspace and its idle
  agent while implementation is likely to follow; archive once no follow-up is
  expected or the PR is merged or closed. `paseo send` can exceed two minutes, so
  use a longer timeout or run it in the background.
- Do not launch adversarial reviewers from the coordinator. Tell the implementing
  agent to launch its own read-only reviewer subagent before reporting, so the
  reviewer inherits the workspace's permissions. Coordinator-launched reviewers
  repeatedly blocked on permission prompts.
- An agent can go idle with uncommitted edits after its prompt is approved. Nudge
  it to commit, self-review, and report.
- Identify agents and workspaces you did not create, leave them alone, do not
  count them against the cap, and mention them once.
- **Verify agent claims about the baseline before repeating them.** "Fails on
  main", "pre-existing failure", "CI started", and "no conflicts" are claims about
  state the agent may not be able to see (a stale base, a token that cannot read
  check runs, a tool missing from its sandbox). Reproduce them on a clean base,
  or read the exact-head check results yourself, and label what you could not
  confirm.
- **Read a finish notice against the agent's status and your last prompt.** A
  finished notice can be the end of an earlier turn, not the reply to your latest
  follow-up. If the agent shows as running or idle with no new activity after your
  prompt, say that you cannot tell yet; do not describe a result you have not
  read.

Permissions: auto-accept is usually a per-workspace UI toggle the CLI does not
expose, so ask the user to set it after creating a workspace. A provider "build"
mode may not suppress prompts; check pending permissions and the daemon log.
Never approve a request unless the user instructs it. A standing policy the user
has recorded in the handoff (for example, routine web search for public
questions) counts as an instruction, within its stated scope. Some tools need a
specific response shape; if a plain "allow" fails with a validation error, retry
in the shape the error names and record the working form in the handoff.

Base of a new workspace: `git fetch` first and create the workspace from
`origin/<default branch>` (or the exact head of the PR you depend on), never from
a local branch that may be stale. Record the base SHA, put it in the delegation
prompt, and tell the agent to confirm `git merge-base HEAD origin/<default>`
equals it before its first edit. A stale base shows up later as a conflicting PR
and as false claims such as "this test already fails on main".

Branching from an in-flight PR: branch from its exact head, expect a rebase after
it lands, and do not mark the new work ready first. If an SSH fetch fails
host-key verification, fetch over authenticated HTTPS without altering remotes.
Never bypass the check.

An implementation prompt states: issue, branch, and delivery level; in- and
out-of-scope behavior; base; acceptance criteria including the live criterion;
required focused tests and agent-launched self-review; the draft/ready/merge guard; the PR standard
(push levels only); and "if the result contradicts the premise, report it and
do not fix it."

For a new guard, check, or test, also require a mutation proof: the agent reverts
the fix, shows the test fails, restores it, and says what the test does not cover.
A test that cannot fail gives false assurance, and a test that asserts only that a
string exists is not a behavior test.

Use the completion clause that matches the delivery level:

```text
report-only / uncommitted:
  Do not return a progress-only response. Return only with the finished result and
  evidence, or one exact external blocker and its evidence. Leave changes
  uncommitted and prepare, but do not run, any live validation procedure.

draft-push / ready-push:
  Do not return a progress-only response. Return only after the reviewed commit is
  pushed and fresh CI starts, or with one exact external blocker and its evidence.
```

When an agent repeatedly narrates without execution, preserve its worktree,
archive the stalled session, and replace it in the same workspace with a smaller
prompt. Do not discard or duplicate its work.

### 6. Manage Stacks Truthfully

Use `gh stack` only when branches are in the same repository and actual Git
ancestry represents the dependency.

```text
main <- prerequisite <- dependent <- adoption
```

After changing a lower layer:

1. Preserve uncommitted upper-layer work.
2. Rebase or restack upward.
3. Verify ancestry.
4. Restore upper-layer work.
5. Push with lease protection.

When the base branch moves and the lower PR conflicts, prefer merging the base
into the lower branch (a plain merge, no force-push). The old head stays an
ancestor, so the stack above stays valid; only the upper PR needs a sync. Any
force-push still needs the user's approval.

For cross-repository dependencies:

- Keep the dependent PR draft.
- Put the dependency in a prominent merge guard.
- Mark it ready only after the upstream merge, release, and immutable pin.
- Never use `gh stack` to imply cross-repository ancestry.

### 7. Apply the Focused Delivery Loop

```text
focused implementation tests
        -> static checks
        -> blocker-only adversarial review
        -> push or refresh PR (draft, or ready under ready-push)
        -> required CI full suite
        -> reproduce only observed failures
        -> focused fix and review
        -> push again
```

Do not run the full local suite during every implementation or review cycle.
Run it locally only when CI is unavailable or the change is so cross-cutting
that focused coverage cannot provide useful confidence. State the reason.

Before significant pushes, ask the reviewer to inspect only the changed risk
surface and named prior blockers. Broad reviews that keep inventing unrelated
scope make delivery non-terminating.

Read the target repository's own PR standard first (its contributing guide, agent
instructions, and PR template). Where it conflicts with the template below, the
repository wins: follow its title and body prefixes, closing-keyword rules
(`Refs` versus `Closes`), attribution rules, and required sections, and put
them in every delegation prompt. When the user points at a newer or draft
standard, treat it as the target and bring open PR bodies in line with it.

Without a repository standard, PR bodies use plain language and stay concise:

```markdown
## Summary
## Issues
## Before / After
## Verification
## Merge Guard
## Rollback
## Security Impact
```

Keep Issues to five bullets of `OWNER/REPOSITORY#NUMBER` (including folded work),
report live checks as PASS, FAIL, or BLOCKED, and list every ready-gate in Merge
Guard.

Keep preparatory and dependent PRs draft. Mark ready only when all merge guards
are satisfied and current-head CI/review is green, unless the user has granted
`ready-push` for that PR.

### 8. Follow Up With a Change-Detecting Check

The coordinator needs something to wake it. Two mechanisms are acceptable; use the
one the user prefers and record the choice and any later change in the handoff:

- **Background wait loop (default, cheapest).** A shell loop that runs the check
  on an interval and exits only when something changed. The harness notifies the
  coordinator when it finishes, so waiting costs no model calls. There is at most
  one loop per `FIRST_MATE_DIR`, and it is owned by the agent that started it.
- Prefer the heartbeat if the user plans to fork or resume sessions often. A
  heartbeat is a named schedule, so it is one object that no fork can duplicate,
  at the price of a model call per run.
- **Paseo heartbeat.** A scheduled prompt that runs the check each time. Use
  `paseo heartbeat update <id> --cron ...` to change its cadence (for example,
  hourly while nothing is moving, every 15 minutes once something changes).

Either way, a quiet wake-up must not turn into filler. Empty calls (`true`,
`date > /dev/null`) cost tokens, change nothing, and can run away into hundreds
of calls. Run the check once, then end the turn.

Bundled assets:

- `assets/first-mate-check.py` queries the watched PRs (head, draft state, reviews,
  inline comments, check results, merge state), issues, releases, **branches**
  (each new commit), **workflows** (latest run on a branch: head, status,
  conclusion), other agents, and pending permission prompts in parallel, compares them with a saved
  snapshot, and prints **nothing** when nothing changed. A transient API error
  keeps the previous value and is reported. Manage the watch list with `add`,
  `remove`, `prune`, `repo`, and `list` (for example `add branch kits@main`,
  `add workflow kits:deploy.yml@main`); `--show` prints the snapshot without
  saving, and `--reset` forgets state. State and watch files live in
  `FIRST_MATE_DIR` (default `./tmp`, which must be ignored by git).
- `assets/first-mate-wait.sh INTERVAL_MIN MAX_MIN` runs the check on an interval
  and exits as soon as it reports a change (exit 0, report printed) or at the cap
  (exit 3, nothing printed). It holds an `flock` on `FIRST_MATE_DIR/.wait.lock`
  and records the owner (`$PASEO_AGENT_ID`), pid, and start time. The lock frees
  itself when the process dies, so there is no stale pidfile. Starting while a
  loop is running never starts a second one: exit 4 if you own it, exit 5 if
  another agent does. Other forms:
  - `status` prints `none`, `mine ...`, or `other owner=<id> ...`.
  - `stop` stops your own loop; `stop --force` stops another owner's.
  - `take-over INTERVAL MAX` stops any running loop and starts yours. Use it only
    after the user confirms you are the coordinator.

Procedure:

1. Copy both assets next to each other into the coordinator worktree's ignored
   `tmp/`, register the repositories, and add the watch list. Always watch the
   default branch of every repository in scope, and the deploy or release
   workflows that the effort's milestone depends on. A merge you did not make
   (another session, another person) and a pipeline that stays red after your
   merge are both invisible to a PR-only watch list.
2. For the wait loop, run `first-mate-wait.sh status` first, then start the
   script as a **background** shell command only if it says `none`. For a
   heartbeat, have its prompt run `first-mate-check.py` once.
3. Use a 5-minute interval while work is in flight (an agent running, CI pending,
   or a review or live run awaited) and 15 minutes when quiet. Use a cap of about
   two hours on the wait loop. After handling a notification, ensure a loop is
   running (`status`, then start if `none`); never start one blindly. To change
   the interval, `stop` and start again. Exit code 4 on a start means the loop
   you wanted is already there, so do nothing more.
4. **Quiet wake-up rule:** if the check reports nothing, make no further tool
   calls and end the turn. Whether to say "no change" follows the user's current
   preference; record it in the handoff. Say it only when it is true: the check
   ran and reported nothing, never as a guess.
5. On a change, read the report, act only on concrete changes, update the handoff,
   report meaningful changes or blockers to the user, and start the next wait.
   When a branch report shows a merge, reconcile before anything else: which
   open recommendations, agents, and PRs does it supersede, conflict with, or
   unblock? Another session may have fixed the problem differently.
6. Prune merged and closed items from the watch list.
7. Report a loop as running only from a `status` result obtained this turn,
   never from the handoff or from memory.

The detector saves its snapshot when it reports. Two agents running it against
one `FIRST_MATE_DIR` split the events between them, and one never sees a change
the other consumed. Only the coordinator runs it in saving mode; everyone else
uses `--show`.

The check resolves exact-head state, so stale cached PR check fields cannot
mislead it. It cannot see GitHub notifications or review requests on PRs outside
the watch list. Under `ready-push`, a CI failure is always reported. Quiet
wake-ups never delay a direct answer: respond to the user when asked.

### 9. Maintain the Durable Handoff

Store the handoff in the coordinator worktree, not another repository checkout.
Use a repository-local ignored path such as `tmp/FIRST-MATE-HANDOFF.md`. If
`tmp/` is not ignored, add it to the repository-local `.git/info/exclude` rather
than changing project ignore policy solely for the coordinator.

Template:

```markdown
# First Mate Handoff

Updated: YYYY-MM-DD HH:MM UTC

## Goal
## Operating Rules
## Controls
## Current Coordination State
## Completed Work
## Critical Path
## Parallel Work
## Authoritative PR and Branch Heads
## Issue and Metadata State
## Workspaces and Active Agents
## Verification Evidence
## Live Results
## Merge and Release Order
## Immediate Next Actions
## Workspace Safety
## Fast-Track Grants
## Pending Decisions and Held Items
## Wait Log
```

- **Controls:** coordinator agent ID (`$PASEO_AGENT_ID` of the owner), wait
  mechanism (loop or heartbeat), interval, and cap, schedule status (or "not visible"),
  agent cap, coordinator and delegated models, permission setup per workspace.
- **Current Coordination State:** the first section read after each wake-up. Keep the
  whole file near 200 lines.
- **Wait Log:** short dated entries only. Clear it periodically: fold
  durable facts into the state sections, save a gitignored backup under
  `tmp/archive/`, then empty the log.
- **Standing rules:** record every user process rule with its date: delivery
  grants, ready-when-green, filing rule, self-review rule, agent reuse, and
  standing answers to routine permission prompts (for example, "web search is
  allowed for public questions"). Apply a recorded policy; ask about anything it
  does not cover.
- **Pending Decisions and Held Items:** add this section to the template. For each
  open question, record your recommendation, the options, and the trigger that
  would make it urgent, so the user can ask "what did you think?" and get the
  same answer after a compaction. Held security findings are listed by title only,
  with a pointer to a private note outside the repository; the note's contents
  and any attack detail stay out of the handoff and every public place.
- **Prune stale detail** once superseded: old head SHAs, retention notes for
  workspaces that no longer exist, and debugging narratives.

Update it after every meaningful event before sending the user-facing report.
Do not include secrets, sensitive internal topology, or credentials.

### 10. Retire Workspaces Safely

Archive a workspace only when all conditions are true:

- Worktree is clean, or its valuable artifacts are already copied out and
  byte-compared.
- Required commits are pushed or otherwise durably recoverable.
- No agent is running in it, and no dependent work or PR awaiting feedback is
  retained there.
- Archival is authorized: the coordinator confirms it, or the user has granted
  standing permission. Record any standing permission in the handoff.
- PR checks are green or the workspace is definitively obsolete.

Dirty files, untracked files, staged changes, unpushed commits, unavailable
owners, or named retention are hard stops.

When a PR merges, retire what it owned in one pass: archive its idle agent and
workspace, drop it from the watch list, and delete the local branch only if it
matches the remote branch exactly. Do not touch agents or workspaces you did not
create.

### 11. Close the Loop

After upstream merges:

- Rebase or restack dependent branches.
- Resolve immutable release SHAs.
- Update every dependent pin and assertion.
- Re-run focused host validation.
- Execute real live validation at the defined cadence.
- Record `PASS`, `FAIL`, or `BLOCKED`, with transcript paths.
- File real, actionable, untracked defects immediately, except security findings
  (invariant 10). Do not file an issue for work you are about to finish in an
  existing open PR; file only deferred or out-of-scope work.
- Close delivered issues through structured metadata.
- Update the epic status and handoff.
- Surface work that the merge unblocked.
- **Post-merge proof.** Some changes can only be proven by the first real run
  after merge (a deploy, a release, a scheduled job). State that in the PR and the
  handoff, add the run to the watch list (section 8), and write the pass criterion
  as an observable (for example, "two consecutive runs plan zero changes on X"
  or "the app shows 1/1 and logs its ready line"). Keep the item open until it is
  observed. When it fails, read the failing step's log before reporting, and
  separate "my change did not work" from "my change worked and exposed the next
  failure".

Do not declare the milestone complete until production wiring, downstream
consumers, current-head CI, review, and live evidence agree.

## Working With the User and Reviewers

- **Check existing evidence before asking the user to repeat work.** Search the
  PR, its docs, and results folders. If earlier runs do not cover the new check,
  say exactly what was logged, what it did not cover, and why the new run is
  needed. Results must be tied to the tested revision.
- **Read live systems with shape-only commands.** When you need facts from an
  environment only the user can reach, ask for output that cannot carry secrets:
  names, counts, and key lists, never values and never an environment dump. Give
  one pasteable command that filters to that shape (for example, `jq` selecting
  credential key names), and say what the output can and cannot show.
- **Drafts for human threads.** Before posting on a reviewer's or user's thread,
  show the draft, give your recommendation and the options (post, change,
  remove), and wait. Post with the repository's attribution prefix, and keep the
  wording neutral about anything held under invariant 10.
- **Name the cause before blaming it.** A root-cause statement cites the log line
  or `file:line` that locates it, and says which resource it concerns. Correct a
  mislabeled cause as soon as you notice it, in the report and in the handoff.
- **Report what the sandbox lacks.** A missing tool (a package manager, a
  validator, a container runtime) is a fact, not a reason to skip a check
  silently. Say which checks did not run, and ask before installing anything.
- **Host-run scripts.** When the user must run something on their machine, give
  one line starting with a `cd` to the right worktree, or a script plus a one-line
  invocation. Scripts must:
  - use `timeout --foreground`; plain `timeout` backgrounds the child's process
    group, and job control freezes it (state `T`) when it touches the terminal;
  - show live output (`tee`) and set non-interactive flags for the tool under test;
  - give resources names valid for the tool (for example, lowercase);
  - have a per-step timeout and an interrupt trap that cleans up;
  - print PASS, FAIL, or BLOCKED with the tested revision.

  State that the script was only syntax-checked if it was not run live.
- **Diagnose a stalled run before blaming the code.** Check process state and the
  last log write time. Separate "my script's fault" from "possible regression".
- **Reviewer feedback.** A `CHANGES_REQUESTED` review stays on the PR until the
  reviewer re-reviews, so a push does not clear it. Reproduce a reported bug
  before fixing it, add a regression test, and confirm the old form fails it.
  Reply on the PR after the push lands, citing commits. Do not invent authority a
  reviewer implies. A proposed decision record has no authority until accepted,
  so statements about it are conditional.
- **Release PRs created by the workflow token may not trigger required checks.**
  Raise it early; the exemption or manual trigger is the user's decision.
- **State only what you have verified.** If you have not looked since the last
  report, say so. Correct a mistaken claim as soon as you notice it.
- **Lead reports with what changed and what needs a decision.** List decisions
  once under "What I need from you".

## Critical Path

Report a compact dependency view. Arrows mean prerequisite to dependent, not Git
ancestry:

```text
completed prerequisite -> active PR -> review or release gate -> dependent PR
        -> live validation -> milestone
```

Status labels: `COMPLETE`, `ACTIVE`, `WAITING`, `BLOCKED`, `FAILED`. When the
user asks for a map, use a mermaid flowchart with an emoji legend (for example
✅ merged, 🟢 approved and green, 🟡 awaiting review, 🔄 in progress, 🔵 not
started, ⛔ blocked, 🔒 needs a user decision, 📝 draft). Solid arrows mean "must
land before"; dotted arrows mean "informs". Link every issue and PR.

## Actions

Name only actions performed or newly actionable state. Avoid repetitive "no
change" reports. Example: "Upstream merged; restacked the dependent PR and
refreshed CI."

## Verification

Before declaring coordination complete, verify:

- All critical-path issues have truthful structured state.
- Every active PR has a current-head CI and review status.
- Draft guards match actual dependencies. Every ready PR either has green
  current-head CI or a recorded `ready-push` grant.
- Same-repository stacks match Git ancestry.
- Cross-repository order is documented without fake stacking.
- Deferred work is tracked.
- Current release pins are immutable and verified.
- Live results are observed, not simulated.
- Required workspaces are retained; safe obsolete workspaces are archived.
- The handoff reflects the final state and its log is cleared.
- Exactly one coordinator is recorded, and `first-mate-wait.sh status` was run
  this turn before any statement about the loop.
- The wait loop or heartbeat is stopped and its state file cleared when coordination ends.

## Troubleshooting

| Problem | Response |
|---------|----------|
| A control named in the handoff (schedule, wait loop) is not visible | Record the gap, do not recreate it silently, and ask the user. |
| New agent resolved to an unexpected or expensive model | Stop and archive it, then relaunch in the same workspace with an explicit model and reasoning level. |
| Agent prompts for permission despite "build" mode | Check pending permissions and the daemon log; ask the user to set the workspace toggle. Do not approve it yourself. |
| SSH fetch fails host-key verification | Fetch needed refs over authenticated HTTPS without changing remotes. |
| Audit contradicts the issue's premise | Update the handoff and issue plan with the corrected scope before delegating. |
| Branches diverge across worktrees | Compare commits and content; replay only missing reviewed commits with lease protection. |
| Dependent PR conflicts after upstream merge | Preserve work, restack on current base, rerun focused checks, and refresh draft CI. |
| Disk cleanup threatens blocked work | Retain dirty or dependency-blocked workspaces and record them in the handoff. |
| Several wait loops, or duplicate wake-ups | Run `first-mate-wait.sh status`. With the lock there is at most one loop; duplicates come from an older copy of the script or a different `FIRST_MATE_DIR`. Stop the extras, and check for a forked session acting as a second coordinator. |
| A forked session inherits "wait loop running" from the handoff | Treat it as unverified. The fork is a non-coordinator: no loop, read-only `--show`, and ask the user before taking over. |
| Start exits 5 (another owner holds the loop) | Do not force it. Ask the user who the coordinator is; use `take-over` only on their word. |
| A quiet turn fills with empty tool calls | Stop. Run the check once and end the turn (section 8). |
| Host-run script stalls with processes in state `T` | Job control froze the child. Use `timeout --foreground` and show live output. |
| Reviewer's change request remains after the fix | Reply with the commits and wait for re-review; a push does not clear it. |
| Release PR has no checks | Workflow-token PRs may not trigger them. Ask the user: exempt or trigger manually. |
| Wait script reports an API error | One transient error is noise (the previous value is kept); repeated errors are a blocker. |
| Coordinator context is compacted | Read the handoff, GitHub metadata, and the active Paseo inventory before acting. |

## Related Patterns

- Repository code-review procedures for final human review and PR quality.
- Paseo product documentation for workspace, agent, and schedule
  operations.
