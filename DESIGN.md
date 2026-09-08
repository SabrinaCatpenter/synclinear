# synclinear — Design

> For agentic workers: REQUIRED SUB-SKILL: use superpowers:writing-plans to
> turn this into an implementation plan, then superpowers:subagent-driven-development
> or superpowers:executing-plans to build it.

**Goal:** Keep a project's Linear tickets in sync with its real git commit
history, with minimal manual effort from Eva, without ever writing to
Linear unreviewed.

**Architecture:** A Stop hook (fires every time Claude finishes a turn)
cheaply checks whether the current project has unsynced commits. If so, it
injects a reminder into Claude's context. Claude then reads the new
commits, proposes which existing Linear tickets they complete and which
need a new ticket, shows Eva a plain-text preview, and only writes to
Linear after she approves (or edits) the list.

**Tech stack:** A lightweight shell/Python script (the Stop hook body),
git, the Linear MCP tools already connected in this environment, a small
per-project JSON config file.

## Scope

**In scope:**
- Reusable across any git repo Eva points it at (Ironman first).
- Auto-detects new commits since the last sync point.
- Auto-*proposes* new tickets and Done-transitions for existing tickets.
- Always shows a text-list preview and waits for Eva's go-ahead before
  writing to Linear.
- Judges "big commit" granularity the same way this session did by hand:
  skip commits that are plan-doc-only edits, lint fixes, or trivial
  follow-ups; group a multi-commit deliverable under one ticket.

**Out of scope (explicitly, per Eva's call this session):**
- Time log / invoice generation (`ironman-time-log.txt` and friends) —
  stays a manual, on-demand ask. Not automated by this skill.
- Fully unattended writes to Linear. There is always a human approval
  step before anything changes in Linear.
- Any UI beyond the terminal text-list preview.

## Components

### 1. Per-project config: `.claude/synclinear.json`

Lives in the git repo this skill is pointed at (e.g.
`ironman/repo/.claude/synclinear.json`). Not committed to the project's
own git history by default (it's Eva's personal sync bookkeeping, not
project state) — gitignored.

```json
{
  "linear_team": "Studio",
  "linear_project": "[Studio] Project Ironman",
  "last_synced_commit": "de1c2c8"
}
```

- `linear_team` / `linear_project`: which Linear team/project this repo's
  commits sync into. Resolved once when the skill is first set up for a
  repo (asks Eva, same way this session confirmed workflow states/labels
  before creating tickets).
- `last_synced_commit`: the most recent commit SHA already considered
  (whether it produced a ticket, updated one, or was judged not
  ticket-worthy). Everything after this SHA, in `git log --reverse`
  order, is "new."

### 2. Stop hook: `~/.claude/hooks/synclinear-check.<ext>`

Runs on every Stop event, for every project, cheaply:

1. Find the current working directory's git repo root (if none, exit
   silently — most Stop events aren't in a git repo at all).
2. Look for `.claude/synclinear.json` there. If missing, exit silently
   (this repo hasn't opted in).
3. `git log --oneline <last_synced_commit>..HEAD` — if empty, exit
   silently (nothing new).
4. If non-empty, print a short reminder to stdout naming the repo and how
   many new commits exist. This becomes a system reminder in Claude's
   next turn.

Registered in `~/.claude/settings.json` under the `Stop` hook, matching
the existing pattern this environment already uses for hooks (see the
`update-config` skill for the exact registration mechanics).

### 3. The sync flow (runs inside the live conversation, not the hook)

When Claude sees the reminder:

1. Read the new commits (`git log <last_synced_commit>..HEAD`, full
   messages).
2. List currently-open Linear tickets in the configured project
   (`list_issues`, states other than Done/Canceled).
3. For each new commit (or logical cluster of commits — same judgment
   call as this session's Block A/B ticket-building): decide one of —
   - **Closes an existing ticket** → propose marking it Done, with the
     commit hash(es) as evidence text.
   - **No existing ticket covers it, and it's a real deliverable** →
     propose a new ticket, already Done, evidenced by the commit(s).
   - **Not ticket-worthy** (plan-doc tweak, lint fix, a "Fix Task N plan"
     correction folded into the same task) → no ticket, just advances
     the sync marker.
4. Print the full proposal as a plain-text list — this is the review
   gate Eva asked for. Nothing touches Linear yet.
5. Eva replies OK / edits / rejects individual lines.
6. Apply only the approved changes via the Linear MCP tools
   (`save_issue`), same as done manually this session.
7. Update `last_synced_commit` in the config to the new HEAD.

## Error handling

- Missing/malformed config → hook exits silently, no reminder (fails
  closed, never spams).
- Linear MCP not connected when Claude tries to act on a reminder → say
  so plainly and stop, don't guess.
- A commit that's ambiguous (could match two open tickets, or half-fits)
  → surface the ambiguity in the preview list rather than picking
  silently; this is exactly the kind of judgment call the review gate
  exists for.

## Testing

- Unit-testable: the Stop hook script's "does repo X have unsynced
  commits" logic is pure git plumbing — testable with a throwaway repo
  and a fake `last_synced_commit`.
- The sync-flow's commit-to-ticket judgment isn't unit-testable (it's an
  LLM call), but the review-gate step means a wrong judgment costs
  nothing — Eva catches it before any Linear write happens. Validate this
  manually against Ironman's real history (the 32 tickets already built
  this session are the known-good baseline to compare a first real run
  against).
