# Stacking Reviewed PRs With gh-stack

The mechanics (commands, flags, troubleshooting) belong to the `github/gh-stack`
project. Read its skill and references first:
`skills/gh-stack/SKILL.md`, `references/commands.md`, `references/stack-design.md`,
and `references/troubleshooting.md`. If the skill does not load from the local
registry, fetch the files with `gh api repos/github/gh-stack/contents/skills/gh-stack/<path>`.
Install the extension with `gh extension install github/gh-stack`.

This page holds only what is specific to First Mate: stacking PRs that already
have reviews. These observations came from gh-stack 0.3.0; recheck them on yours.

## Procedure that worked

1. Work in a scratch clone, not the user's worktrees. Set `rerere.enabled true`
   and `remote.pushDefault origin` in it.
2. Make each branch contain the one below it with plain merges. Never rebase a
   branch that has reviews.
3. `gh stack init --base <default> <bottom> <middle> <top>` adopts the existing
   branches and finds their PRs.
4. `gh stack view --json` should show `needsRebase=false` for each layer.
5. Have a read-only blocker-only reviewer compare each layer's diff with its PR's own
   diff (equal patch IDs).
6. Ask the user before `gh stack submit --auto --remote origin`. It pushes
   atomically with force-with-lease and retargets PR bases.
7. For a later change: fix the owning layer, merge it into the layers above, then
   `gh stack push --remote origin`.

## Caveats

- If CI runs only for PRs into the default branch, layers above the bottom show
  only the title check until they are retargeted. Retargeting is the user's call.
- A stack needs real ancestry. Two PRs on the same base that conflict with each
  other, or that touch separate histories, are not a linear stack.
- Host verification on another platform is easier as one stack-level block run at
  the tip, with per-layer heads as an optional part.
- Do not use `env -u` to strip a token for `gh stack` unless you have verified it
  still authenticates (see Secrets in SKILL.md).
