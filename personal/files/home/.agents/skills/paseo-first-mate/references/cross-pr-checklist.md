# Cross-PR Checklist

Run this when the watch list grows, before a batch of merges, and whenever a
merge lands that you did not make. Each item is a cheap check that caught a real
problem across many open PRs.

| Check | How | Why |
|-------|-----|-----|
| Sequence-number collisions | List the next free number claimed by each open branch for anything numbered: decision records, migrations, numbered test files. A short script over `git ls-tree` of each branch works. | Several branches claimed the same number; the loser renames late and breaks review. |
| Shared generated files | List the PRs that edit the same index, generated doc, or relevance list. | They conflict one by one as each merges. Plan the order early. |
| Conflict counts | Recompute with `git merge-tree --write-tree --name-only <base> <branch>` against the long-lived branch. | Counts in an epic go stale. Edit the epic in place and check its body did not change under you before you overwrite it. |
| Stale PR bodies | Re-read the Verification section of each PR after pushes. Update it as the standing grant allows. | The body outlives the head it described. Never tick a human attestation box. |
| Merge queue bounces | If a PR bounces on a test that looks unrelated or racy, ask for a re-run (your token may not be able to) and investigate only if it repeats. | One bounce is often noise. |
| What a merge unblocked | Search your held and blocked items for the one you just merged (SKILL.md section 11). | Blocked work is forgotten unless something prompts it. |
| Unmerged duplicate work | Compare open PRs for overlapping paths. | Another session may have fixed the same problem differently. |
