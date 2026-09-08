---
name: synclinear
description: Sync a git repo's commit history into its Linear project — propose new tickets and Done-transitions for existing ones, always with a review step before writing to Linear. Triggered automatically by a Stop hook reminder naming unsynced commits; can also be invoked directly by Eva.
---

# synclinear

You're reading this because either (a) a Stop-hook reminder told you there
are unsynced commits in the current repo, or (b) Eva asked you to sync
Linear directly.

## What "sync" means here

Every commit since `last_synced_commit` (in `.claude/synclinear.json`)
needs one of three outcomes:

1. **Closes an existing open Linear ticket** — propose marking it Done,
   with the commit hash(es) as evidence in the ticket description.
2. **A real deliverable with no existing ticket** — propose a new ticket,
   already Done, evidenced by the commit(s). Group multiple commits under
   one ticket when they're clearly one deliverable (matches this
   project's existing "[Block A] Outlook adapter" granularity, not one
   ticket per commit).
3. **Not ticket-worthy** — plan-doc-only edits, lint/CI fixes, a "Fix
   Task N plan" correction folded into the same task, a typo fix. No
   ticket. Still advances the sync marker (see below) — never
   re-propose these on the next run.

## The flow

1. Read `.claude/synclinear.json` in the current repo root for
   `linear_team`, `linear_project`, `last_synced_commit`.
2. `git log --oneline <last_synced_commit>..HEAD` (full messages: drop
   `--oneline` and read the real commit bodies, not just subject lines —
   you need the detail to judge ticket-worthiness the way this project's
   own commits were judged when the first 32 tickets were built).
3. `list_issues` (Linear MCP) scoped to `linear_project`, states other
   than Done/Canceled/Duplicate — these are the tickets a commit might
   close.
4. For each commit or commit-cluster, decide outcome 1, 2, or 3 above.
5. Print the full proposal as a plain-text list — **this is the review
   gate. Do not call any Linear MCP write tool before this step and
   Eva's reply.** Format:
   ```
   Proposed Linear sync (N commits, M ticket changes):

   - STU-125 -> Done (evidence: <sha> <subject>)
   - NEW: "[Block C] <title>" -> Done (evidence: <sha> <subject>, <sha> <subject>)
   - (no ticket) <sha> <subject> — <one-line reason it's not ticket-worthy>
   ```
6. Wait for Eva's reply. She may say OK, edit specific lines, or reject
   the whole thing. Only apply what she approved.
7. Apply approved changes via `save_issue` (mark Done + append evidence
   to the description for existing tickets; create + immediately mark
   Done for new ones — same pattern used for the first 32 tickets in
   "[Studio] Project Ironman").
8. Update `.claude/synclinear.json`'s `last_synced_commit` to the new
   `HEAD` (use `config.save_config` from this skill's `lib/config.py` —
   same directory as this file, so import it by adding that `lib/`
   folder to `sys.path` — or write the JSON directly. Either way, this
   MUST happen even for a run where every commit landed in the
   "not ticket-worthy" bucket, so those commits are never re-proposed).

## First-time setup for a new repo

If `.claude/synclinear.json` doesn't exist yet and Eva asks you to set
this up for a repo: ask which Linear team and project it maps to (use
`list_teams` / `list_projects` to show her real options, don't guess),
then `save_config` with `last_synced_commit` set to the repo's current
`HEAD` (so the first real sync only covers commits from this point
forward — do not try to backfill the entire history automatically; that
was a one-off, manually-confirmed exercise the first time, not something
this skill should redo unprompted for a new repo).

## Errors

- Linear MCP tools not available when you reach step 3 → say so plainly,
  stop. Don't guess at ticket state.
- A commit is ambiguous (fits two open tickets, or half-fits one) →
  surface the ambiguity as its own line in the step-5 preview rather than
  picking silently. That's what the review gate is for.
