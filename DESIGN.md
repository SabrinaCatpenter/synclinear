# synclinear — Design (v2)

> For agentic workers: REQUIRED SUB-SKILL: use superpowers:writing-plans to
> turn this into an implementation plan, then superpowers:subagent-driven-development
> or superpowers:executing-plans to build it.

> **Supersedes v1** (2026-09-08, earlier same day). v1 only covered
> git-commit-to-Linear backfill sync plus a coding-hours time log. This
> version keeps both of those but reframes synclinear as the sync layer
> for Eva's full confirmed development workflow (below), not a
> standalone tool. Sections carried over unchanged from v1 are noted;
> read the whole file, not just the diff, since the surrounding context
> changed even where the text didn't.

## The workflow this exists to support

Established over a long conversation with Eva on 2026-09-08, using
OpenSpec (`@fission-ai/openspec`, already installed) alongside this
project's existing `superpowers` skills. Weekly outer loop: Eva meets
her client (Mark) to confirm requirements, then syncs those requirements
and guardrails with Claude. Inside that week, each discrete piece of
work goes through this cycle, in order, no skipping:

1. `/openspec-explore` — explore the technical approach (pure
   conversation, no artifacts required)
2. `/openspec-propose` — write it into a formal OpenSpec change
   (creates `openspec/changes/<name>/` with `proposal.md`, `design.md`,
   `tasks.md`) — **a matching Linear ticket should exist from here on**,
   client/PM-facing, one ticket per change (not finer)
3. `superpowers:brainstorming` ⇄ `grilling` (mattpocock-skills) loop —
   brainstorm a design, grill it adversarially, refine, grill again,
   until it holds up. Output: a design doc with Mermaid diagrams under
   the project's `docs/` — independent feature = its own folder; a
   feature that's purely a single-parent sub-component = a subfolder;
   any other relationship (multi-parent, graph-shaped) is an Obsidian
   wikilink (`[[...]]`), never folder nesting, because a folder can only
   express one parent and real dependency graphs usually aren't trees.
4. `superpowers:writing-plans` — bite-sized TDD implementation plan,
   `docs/superpowers/plans/`
5. `superpowers:test-driven-development` — write the code
6. Eva reviews. **Pass** → local plan-doc task ticked off AND the Linear
   ticket marked Done, together, live in conversation (not via a later
   hook pass — see "The two signals" below for why). **Fail** → sent
   back for rework, neither side marked done.
6.5. Before archiving: discuss with Eva and produce a client-facing HTML
   report of this round's changes (same pattern as the two Mark-facing
   progress-report artifacts built earlier the same session), saved
   locally to `artifacts/YYYY-MM-DD[-vN].html` in the project repo —
   dated, not per-ticket, since one report usually rolls up several
   changes/tickets on a weekly cadence.
7. `/openspec-archive-change` — archive the change

Running throughout, not tied to one step: the `handoff` skill
(mattpocock-skills), auto-triggered by a PreCompact hook already built
this session (`~/.claude/hooks/precompact_handoff_reminder.py`) — when
context is about to compact, Claude proactively writes a handoff doc
without being asked.

**A hard rule that shaped every decision below:** architecture docs
(`docs/`), Linear tickets, and local plan-doc tasks are three different
things — different audience, different granularity, different level of
abstraction. Nothing in this design collapses them into one artifact or
lets one stand in for another.

## Goal

Keep three things in sync with what's *actually* happened in a project —
Linear tickets, a coding-hours time log, and (new in v2) awareness of
where each OpenSpec change sits in the 7-step cycle above — with minimal
manual effort from Eva, and without ever writing to Linear, a local
file, or the `artifacts/` folder unreviewed. This last part is
non-negotiable and applies to every mechanism this design describes,
including the ones new in v2.

## The two signals (the central design decision of v2)

v1 had one signal: unsynced git commits. v2 needs (at least) two,
because they answer different questions and can each be true
independently of the other:

```
Signal A — git commits              Signal B — OpenSpec state
(unchanged from v1)                 (new in v2)

"Has step 5 (TDD) produced          "Has step 2 (propose) created a
 code that isn't reflected           change that doesn't have a
 in Linear/the time log yet?"        matching Linear ticket yet, or
                                      step 7 (archive) closed one with
                                      no artifacts/ entry for it yet?"

Checked via: git log                Checked via: `openspec list --json`
<last_synced_commit>..HEAD          against a locally-tracked set of
                                     "changes already handled"
```

A change can be proposed with zero commits yet (signal B fires, signal
A doesn't). A commit can land against a change whose ticket already
exists (signal A fires, signal B doesn't, this is the ordinary case).
**These produce separate reminder lines, never merged into one** — Eva
needs to see at a glance which situation she's in, not decode a
combined sentence.

Two things Eva explicitly decided are *not* part of this signal
scheme:

- **Review-approval (step 6)** is handled live, in conversation, the
  moment Eva says something like "approved"/"looks good" — Claude syncs
  the local task and the Linear ticket to Done right then. The Stop
  hook's git-commit check (signal A) is only a *backstop* for this path
  — if a session gets interrupted between Eva's approval and Claude
  applying it, the next Stop-triggered pass catches the gap the normal
  way (matching a commit to an existing ticket). There is no dedicated
  "was this reviewed" flag anywhere; the live moment IS the record.
- **The brainstorm⇄grill loop (step 3)** has no reliable disk footprint
  (it's conversation, plus whatever design doc eventually gets written —
  and that write is step 3's own output, not a sync-worthy event on its
  own). Out of scope for automated detection entirely; Eva and Claude
  self-govern this step in the moment.
- **The artifacts/ reminder** is a *reminder only* — Stop hook signal B
  can say "this change archived and there's no dated report near that
  time yet," but never drafts the report's content itself. Content
  requires Eva's live discussion, same as the two Mark-facing reports
  built earlier the same session (one of which needed a full anonymize-
  and-recredit rework after a real PII incident — this is not a place
  to let anything happen unreviewed).

## Scope

**In scope (v1, unchanged):**
- Reusable across any git repo Eva points it at.
- Auto-detects new commits since the last sync point (signal A).
- Auto-*proposes* new tickets and Done-transitions for existing tickets,
  sized from real measured hours (see "Ticket sizing" below).
- Auto-*proposes* the matching new time-log line from real Claude Code
  session activity (coding hours only).
- Always shows a text-list preview and waits for Eva's go-ahead before
  writing to Linear or the time log.

**In scope (new in v2):**
- Detects OpenSpec changes with no matching Linear ticket yet (signal B,
  half one).
- Detects archived OpenSpec changes with no nearby `artifacts/` entry
  (signal B, half two) — reminder only, never drafts content.
- Live (non-hook) sync of local-task + Linear-ticket to Done at the
  moment Eva approves a review.

**Out of scope (unchanged from v1, still true):**
- Anything in the time log that isn't coding hours (call durations,
  offline research) — stays a manual, on-demand ask.
- Fully unattended writes to Linear, the time log, or `artifacts/`.
- Any UI beyond the terminal text-list preview.
- Drafting `artifacts/` content proactively.
- Detecting or enforcing the brainstorm⇄grill loop.

## Ticket sizing (unchanged from v1)

Linear has no built-in "log actual time spent" field (confirmed via
Linear's own docs, 2026-09-08). What it has is `estimate` — a
pre-work planning field (points, or in this workspace's case the custom
XS/S/M/L/XL labels). The first 32 tickets built manually this session
left sizing off for lack of a real number. Now that the sync flow
computes real measured hours per commit-cluster (the same data feeding
the time-log line), every *newly created* ticket gets sized from that
real time:

| Label | Real duration |
|---|---|
| Extra Small (XS) | ~15 minutes |
| Small (S) | ~1 hour |
| Medium (M) | ~2 hours |
| Large (L) | ~3 hours |
| Extra Large (XL) | 5+ hours |

Existing tickets marked Done (not newly created) are never re-sized —
sizing only applies at creation, so a size a human set deliberately is
never silently overridden.

## Components

### 1. Per-project config: `.claude/synclinear.json`

```json
{
  "linear_team": "Studio",
  "linear_project": "[Studio] Project Ironman",
  "timetable_path": "C:\\Users\\Eva Ng\\Desktop\\ironman\\ironman-time-log.txt",
  "last_synced_commit": "de1c2c8",
  "known_openspec_changes": [],
  "last_artifact_check_at": "2026-09-08T00:00:00Z"
}
```

- `linear_team` / `linear_project` / `timetable_path` — unchanged from
  v1, resolved at first-time setup by asking Eva.
- `last_synced_commit` — unchanged from v1, drives signal A (git) and
  the time-log's block-grouping window.
- `known_openspec_changes` (**new**) — change names (from
  `openspec/changes/<name>/`) that already have a matching Linear
  ticket. `openspec list --json`'s current active changes, minus this
  set, are the "propose happened but no ticket yet" cases signal B
  needs. A change is added here the moment its ticket is created —
  whether that happens live (Eva asks directly) or via a later synclinear
  pass.
- `last_artifact_check_at` (**new**) — an ISO timestamp, not a
  correctness check. Signal B's artifact-reminder half compares
  `openspec/changes/archive/` entries newer than this timestamp against
  `artifacts/`'s file list; if any archived change has no plausible
  same-week `artifacts/*.html`, remind once. The timestamp then advances
  regardless of whether Eva actually wrote the report — its only job is
  "don't nag about the same batch forever," not "verify the report
  exists." (Exact matching between a dated artifact and which
  change(s) it covers is inherently fuzzy — one report can cover several
  changes — so this check stays a nudge, never a hard gate.)

### 2. Stop hook: `~/.claude/skills/synclinear/hooks/check_unsynced.py`

(Same file as v1 — the path didn't change, the logic inside grows two
new checks.) Runs on every Stop event, for every project, cheaply:

1. Find the repo root from `cwd` (given directly in the Stop hook's own
   stdin JSON — see "Resolved: locating state" below). Exit silently if
   none.
2. Look for `.claude/synclinear.json`. Exit silently if missing (this
   repo hasn't opted in).
3. **Signal A** (unchanged): `git log <last_synced_commit>..HEAD` — note
   if non-empty.
4. **Signal B** (new): if an `openspec/` directory exists alongside the
   config, run `openspec list --json` (and, for the archive half,
   inspect `openspec/changes/archive/` directory mtimes against
   `last_artifact_check_at`). Note any active change not in
   `known_openspec_changes`, and any newly-archived change with no
   plausible recent `artifacts/*.html`.
5. If nothing from either signal, exit silently. Otherwise emit the
   Stop-hook JSON shape (`hookSpecificOutput.additionalContext`,
   `hookEventName: "Stop"`) with each finding as its own line, pointing
   at this skill's `SKILL.md` for how to act on each one.

### 3. The sync flows (run inside the live conversation, not the hook)

Three separate flows now, matching the two signals plus the live-review
path:

**3a. Signal A → Linear/time-log sync (unchanged from v1):** read new
commits, list open Linear tickets, decide per commit-cluster (closes an
existing ticket / needs a new sized ticket / not ticket-worthy), compute
real hours for the time-log line, show ONE combined preview, apply only
what Eva approves, advance `last_synced_commit`.

**3b. Signal B, half one → propose-without-ticket:** for each active
change not in `known_openspec_changes`, read its `proposal.md` and
`tasks.md`, propose a new Linear ticket (Todo, sized by estimating each
listed task in `tasks.md`, summing, mapping to the nearest XS/S/M/L/XL
bucket, then bumping up one bucket as buffer — see "Resolved questions"
below), show the proposal, apply if approved, add the change name to
`known_openspec_changes`.

**3c. Signal B, half two → artifact reminder:** name the archived
change(s) with no nearby report, ask if Eva wants to discuss one now.
No content is drafted here — this just opens the conversation, same as
any other client-facing report this session. Advance
`last_artifact_check_at` regardless of her answer.

**Live path (no hook involved):** the moment Eva approves a review in
conversation, Claude ticks the local plan-doc task and marks the Linear
ticket Done in the same turn — this is not gated on any Stop event.

## Resolved: locating session/repo state

v1 left this open. Resolved 2026-09-08 by adding a temporary diagnostic
Stop hook and reading its real output: **Claude Code's Stop hook stdin
JSON includes `transcript_path` and `cwd` directly** — no need to
reverse-engineer the project-folder sanitization scheme. `check_unsynced.py`
should read stdin (it doesn't yet — v1's implementation ignored stdin
entirely, since it didn't need cwd for anything beyond `os.getcwd()`,
which happens to already match `cwd` in every case tested so far; v2's
time-log half is the first thing that actually needs `transcript_path`).
The diagnostic hook has been removed from `~/.claude/settings.json`
after capturing this answer.

## Error handling (unchanged from v1, extended to the new checks)

- Missing/malformed config → hook exits silently (fails closed).
- No `openspec/` directory → signal B is simply not checked for that
  repo; not an error, just "this repo hasn't adopted OpenSpec."
- Linear MCP not connected when Claude tries to act on any reminder →
  say so plainly and stop, don't guess.
- A commit or change that's ambiguous → surface the ambiguity in the
  preview rather than picking silently.

## Resolved questions (were open in the first draft of this section)

1. **Sizing a ticket created at propose time (3b):** propose-time
   tickets ARE sized immediately, not left unsized until Done. Source:
   `/openspec-propose` already generates `tasks.md` as one of its three
   artifacts (per the `openspec-propose` skill read this session), so a
   task list exists at propose time even though `writing-plans`'
   finer-grained TDD plan doesn't yet. Estimate a rough size per task
   listed in `tasks.md`, sum them, map to the nearest XS/S/M/L/XL
   bucket from the "Ticket sizing" table, then **bump up one bucket** as
   a deliberate buffer (Eva's own words: "怕做不完" — pad for the real
   thing usually taking longer than the proposal-stage estimate). **If
   the summed estimate already maps to XL** (the largest label this
   workspace actually has — confirmed via `list_issue_labels` on the
   Studio team, no XXL exists here even though Linear's generic point
   scale goes further), **stay at XL — do not invent a bucket beyond
   it.** This
   sized-at-propose value is a planning estimate like any Linear
   `estimate` normally is; it is NOT touched again at the Done
   transition (Done only applies to tickets created retroactively from
   commits with no propose-time ticket, per "Ticket sizing" above,
   which stays measured-not-guessed for that path).
2. **`known_openspec_changes` cleanup:** never pruned — grows forever.
   Harmless (just a list of change names) and safer than deleting: a
   deleted entry risks a same-named change reappearing later and being
   mistaken for "never ticketed yet."

## Testing (unchanged from v1, extended)

- Signal A's git-plumbing logic: pure, already tested (v1).
- Signal B's OpenSpec-plumbing logic: same shape as signal A — testable
  with a throwaway `openspec/` directory structure and a fake
  `known_openspec_changes` set, no real OpenSpec CLI invocation needed
  for the unit tests (mock or fixture the JSON `openspec list` would
  return).
- The sync flows' judgment calls (ticket-worthy or not, which change a
  commit belongs to) stay LLM-driven and not unit-tested, same rationale
  as v1: the review gate means a wrong judgment costs nothing.
