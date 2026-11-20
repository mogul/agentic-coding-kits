# Status Doc

A Markdown file the user keeps open in a tab. The coordinator updates it in
place on every event, so chat messages can stay short. In one long session this
was the largest single improvement to the user's experience.

Location: an ignored path in the coordinator worktree, next to the handoff
(for example `tmp/PR-STATUS.md`). It is a view for the user. GitHub stays
authoritative, and the handoff stays the coordinator's own memory.

## Template

```markdown
# Status (<effort name>)

Updated: YYYY-MM-DD HH:MM UTC · Agents running: N (cap M) · Loop: running, <interval> interval, <cap> cap

## Needs you
| Item | Action | Why |

## In progress (agents)
| PR | Work |

## Waiting on reviewers
| PR | Head | CI | Notes |

## Backlog (not started)
| Item | Note |

## Leaving alone (per you)
Links only.

## Merged / closed this session
Links only.

## Tracking issues filed
One line each, with a link.

## Standing rules
Delivery level, grants, and process rules the user gave, each with its date.
```

Link every PR and issue with a full Markdown link.

## Rules for using it

- Update the doc first, then say one line in chat.
- Rows move between sections as state changes. Remove a row when it stops being
  true (a done action, a merged PR, a duplicate). Stale rows made the user ask
  twice for cleanup.
- Name the head SHA a row is true for. Re-read the PR before writing a state;
  do not write from memory.
- A "Needs you" row is something only the user can do. Your own to-dos go in
  Backlog or in the handoff.

## Chat reports

- One line per PR event, with a link, plus the decision you need. Add only what the
  PR comments and commits do not already say.
- Do not recap a push, a comment, or a review that is already on the PR.
- Do not repost tables. The doc is the table.
- A quiet wake-up says nothing, or one honest line if the user asked for it.
- State a mistake plainly and fix the doc. When asked why something was missed,
  give the root cause with timestamps, not an apology.
