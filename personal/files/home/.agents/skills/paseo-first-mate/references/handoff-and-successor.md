# Coordinator Handoff and Successor

Use this when the context window is filling (tell the user at about 70% and prepare
early), or when the user asks for a new coordinator in the same workspace.

## Write the handoff first

Follow the template in SKILL.md section 9, and put these in it:

- The user's standing rules, verbatim and dated. Rules the user gave mid-session
  were the most valuable content for a successor. Examples: how to report,
  what never to touch, permission policies, delivery level, agent cap.
- Controls: the old coordinator's agent ID, the loop command (with the absolute
  `FIRST_MATE_DIR`), the heartbeat ID, and a sentence saying these are bound to
  the old ID and must be re-established.
- In-flight commitments, held items, and work that is on hold with its
  trigger. Archive the old log under `tmp/archive/` and clear it.
- A standing-policy line for permission prompts, for example: "external
  search-service prompts are denied; fetching public project sites is allowed."

## Launch the successor

Create the new coordinator in the same workspace with a prompt that says: read the
skill, read the handoff, run `first-mate-wait.sh status`, then `take-over`
(the user's request for a handoff is their word for it), create your own
heartbeat, delete the old one, and claim the running agents. `notifyOnFinish=false`
is fine for the successor itself.

## What breaks if you skip a step

- The loop lock is keyed on the owner ID, so `take-over` is required. It needs the
  user's word; their handoff request counts.
- The old heartbeat fires into the old session. A heartbeat belongs to the agent
  that created it, so the successor may not be able to delete it. Say so in the
  handoff, and have the user or the old coordinator delete it before it retires.
- Agents the old coordinator created carry a `paseo.parent-agent-id` label with
  the old ID, so their finish notices go to the old session. The successor can
  try `paseo_update_agent` to change the label (untested whether it takes
  effect), or poll `paseo_get_agent_status` on each wake-up. The old coordinator
  stops acting after the take-over.
- Workspace creation can fail with a git configuration error when a stale local
  branch or worktree of the same name exists. Run `git worktree prune`, delete the
  stale local branch (only if it matches the remote), and retry. A transient
  failure also happened once; a plain retry worked.

## Successor's first turn

1. `first-mate-wait.sh status`; take over if it is not yours.
2. Re-read GitHub state for everything in the handoff; do not trust its claims.
3. Create the heartbeat. Confirm running agents with `paseo_get_agent_status`.
4. Record your agent ID in Controls.
