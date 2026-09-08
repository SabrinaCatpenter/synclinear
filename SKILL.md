---
name: synclinear
description: Sync a git repo's state into Linear and its time log, AND keep the 7-step dev cycle moving — (3a) unsynced commits into Done tickets + time-log lines, (3b) OpenSpec proposals into new Todo tickets sized from tasks.md, (3c) archived OpenSpec changes into a client-facing artifact reminder, (workflow-stage gaps) directs Claude to begin the next stage of the 7-step cycle when one stalls — always with a review step before writing anything to Linear or a file, and (auto time-log) automatically records work blocks into weekly files with no review gate, since a timestamp is a fact, not a decision. Triggered automatically by a Stop hook reminder; can also be invoked directly by Eva.
---

# synclinear

You're reading this because either (a) a Stop-hook reminder told you there
are unsynced commits in the current repo, or (b) Eva asked you to sync
directly.

**This skill has two halves that share one review gate and one sync
marker — not two separate mechanisms.** Every sync run proposes BOTH
Linear ticket changes AND a new time-log line together, Eva approves them
together, and one `last_synced_commit` update covers both.

**Status note (added 2026-09-08):** the time-log half's mechanism for
locating Claude Code's own session transcript file is not yet built — see
`DESIGN.md`'s "Open question" section. Until that's resolved, do the
Linear half exactly as below, and for the time-log half, tell Eva plainly
that this part isn't wired up yet rather than guessing at a transcript
path or skipping it silently.

**v2 status note:** flows 3b and 3c (below) are new in v2 and independent
of the time-log gap above — they only touch Linear and the artifacts/
folder, never `timetable_path`.

## What "sync" means here

Every commit since `last_synced_commit` (in `.claude/synclinear.json`)
needs one of three outcomes:

1. **Closes an existing open Linear ticket** — propose marking it Done,
   with the commit hash(es) as evidence in the ticket description. Do NOT
   change its size label — sizing only happens at creation (step 2), so a
   size a human set deliberately is never silently overridden.
2. **A real deliverable with no existing ticket** — propose a new ticket,
   already Done, evidenced by the commit(s), sized from that
   commit-cluster's real measured hours (once the time-log mechanism
   exists — see the status note above) against this table:

   | Label | Real duration |
   |---|---|
   | Extra Small (XS) | ~15 minutes |
   | Small (S) | ~1 hour |
   | Medium (M) | ~2 hours |
   | Large (L) | ~3 hours |
   | Extra Large (XL) | 5+ hours |

   Group multiple commits under one ticket when they're clearly one
   deliverable (matches this project's existing "[Block A] Outlook
   adapter" granularity, not one ticket per commit) — size by their
   combined measured hours.
3. **Not ticket-worthy** — plan-doc-only edits, lint/CI fixes, a "Fix
   Task N plan" correction folded into the same task, a typo fix. No
   ticket. Still advances the sync marker (see below) — never
   re-propose these on the next run.

## Flow 3a: commits → Linear + time log

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
5. Print ONE combined proposal covering Linear AND the time log — **this
   is the review gate. Do not call any Linear MCP write tool, and do not
   touch `timetable_path`, before this step and Eva's reply.** Format:
   ```
   Proposed sync (N commits, M ticket changes[, +H.Hh to the time log]):

   Linear:
   - STU-125 -> Done (evidence: <sha> <subject>)
   - NEW: "[Block C] <title>" -> Done, sized <label> (evidence: <sha> <subject>, <sha> <subject>, ~H.Hh measured)
   - (no ticket) <sha> <subject> — <one-line reason it's not ticket-worthy>

   Time log (appends to <timetable_path>):
   - <date>  <description>  <H.Hh>
   ```
   (Omit the "Time log" section entirely while that mechanism isn't built
   yet — see the status note above — rather than printing a fake or
   placeholder line.)
6. Wait for Eva's reply. She may say OK, edit specific lines, or reject
   the whole thing. Only apply what she approved.
7. Apply approved changes: Linear tickets via `save_issue` (mark Done +
   append evidence to the description for existing tickets; create,
   apply the size label via `addLabels`, and immediately mark Done for
   new ones — same pattern used for the first 32 tickets in "[Studio]
   Project Ironman"); the time-log line by appending it to
   `timetable_path`.
8. Update `.claude/synclinear.json`'s `last_synced_commit` to the new
   `HEAD` (use `config.save_config` from this skill's `lib/config.py` —
   same directory as this file, so import it by adding that `lib/`
   folder to `sys.path` — or write the JSON directly. Either way, this
   MUST happen even for a run where every commit landed in the
   "not ticket-worthy" bucket, so those commits are never re-proposed).
   One update covers both halves — there is no separate time-log marker.

## Flow 3b: OpenSpec proposal → new Linear ticket (Todo)

Triggered by a Stop-hook reminder naming an OpenSpec change whose
proposal (specifically its `tasks` artifact) is complete but isn't yet
in `known_openspec_changes`, or by Eva asking directly after running
`/openspec-propose`.

1. Read `.claude/synclinear.json` for `linear_team`, `linear_project`,
   `known_openspec_changes`.
2. `openspec status --change "<name>" --json` — read the resolved
   `tasks.md` path and read the file. This is a task LIST, not the
   finer-grained TDD plan `writing-plans` produces later — that's fine,
   it's the right granularity for a rough size estimate.
3. **Size the ticket:**
   - Estimate a rough size per task listed in `tasks.md` (XS/S/M/L/XL,
     same table as flow 3a), sum them, map the sum to the nearest
     bucket in that table.
   - **Bump up one bucket** as a deliberate buffer — the real work
     usually takes longer than a propose-stage estimate. XS→S, S→M,
     M→L, L→XL.
   - **If the summed estimate already maps to XL** (the largest label
     this workspace actually has — confirmed via `list_issue_labels`
     on the Studio team; there is no XXL here even though Linear's
     generic point scale goes further), **stay at XL. Do not invent a
     bucket beyond it.**
   - This sized-at-propose value is a planning estimate, same as any
     Linear `estimate` normally is — it is NOT touched again when the
     ticket later moves to Done (step 6 of flow 3a's philosophy: sizing
     only happens once, at creation).
4. Print ONE proposal — **review gate, same rule as flow 3a: no Linear
   write before Eva's reply.**
   ```
   Proposed new ticket from OpenSpec change "<name>":

   - NEW: "<title from proposal.md>" -> Todo, sized <label>
     (from N tasks in tasks.md, bumped from <raw label>)
   ```
5. Wait for Eva's reply. Apply only what she approves.
6. Apply: create the Linear ticket via `save_issue` (Todo state, sized
   via `addLabels`, project = `linear_project`), matching the existing
   "[Studio] Project Ironman" one-ticket-per-change granularity (not
   per implementation task).
7. Add `<name>` to `known_openspec_changes` in `.claude/synclinear.json`
   via `config.save_config` (import `lib/config.py` the same way flow
   3a does) — this MUST happen even if Eva declined the ticket, so an
   explicitly-skipped change is never re-proposed on the next run.

## Flow 3c: archived OpenSpec change → client artifact reminder

Triggered by a Stop-hook reminder noting the OpenSpec archive changed
since `last_artifact_check_at`, or by Eva directly.

This flow is a **nudge, not a content generator** — never draft the
client-facing HTML artifact's content unprompted. An earlier
Mark-facing progress-report artifact was built by drafting content
without enough review and leaked information that shouldn't have gone
to the client; this flow exists specifically to force a real
discussion with Eva before anything client-facing gets written.

1. Tell Eva plainly what changed in the OpenSpec archive since the
   last check (`openspec list --json` with `--archived` or equivalent,
   or read `openspec/changes/archive/` directly for the changed
   entries) — names and dates, not summarized content.
2. Ask Eva whether a client-facing artifact is warranted for this round
   (it's a weekly-cadence, roll-up decision — one artifact often covers
   several archived changes, so "one artifact per archived change" is
   wrong; let Eva decide the boundary).
3. If yes: discuss the content with Eva directly (this is a live
   conversation, not a template fill) and build the artifact using the
   normal artifact-creation process, saved locally to
   `artifacts/YYYY-MM-DD[-vN].html` in the project repo — dated, not
   ticket-numbered, with a `-v2`/`-v3` suffix for same-day revisions.
4. Either way — Eva says yes and an artifact gets built, or Eva says no
   for this round — update `last_artifact_check_at` in
   `.claude/synclinear.json` to now (ISO 8601 UTC) via
   `config.save_config`. This advances regardless of Eva's content
   decision, same as flow 3b's `known_openspec_changes` update: a
   declined round is not re-prompted forever, only re-prompted when the
   archive changes again.

## Workflow-stage gap directives

Triggered by a Stop-hook reminder naming a "gap" in the 7-step per-change
cycle (explore → propose → brainstorm/grill → writing-plans → TDD →
review → archive) — a proposal complete with no design doc, a design doc
with no plan, or all tasks checked but the change not yet archived.

**These are directives, not proposals — do not wait for Eva's go-ahead
before beginning the next stage.** The 7-step sequence itself is a
standing agreement Eva already made; only the content decisions *inside*
each stage (what the design says, whether review passes) still involve
her directly, through ordinary conversation — unchanged from how those
stages always worked.

That said, act with judgment, not blind literalism:

1. **If the directive fires while Eva is mid-conversation on something
   unrelated** to the change that triggered it, mention the pending gap
   briefly and defer — don't derail what's actually happening to
   immediately switch tasks.
2. **If Eva mentions she's redoing a stage** whose gap signature already
   fired (e.g. rewriting a design doc from scratch), proactively remove
   that signature from `advanced_workflow_gaps` in
   `.claude/synclinear.json` (read the file, edit the JSON, write it
   back, or use `lib/config.py`'s `load_config`/`save_config`) so the gap
   is eligible to fire again once the redo is complete — the mechanism
   otherwise stays silently inert with no sign anything's wrong.
3. **For a "tasks complete" directive specifically**, check first whether
   Eva already reviewed and approved this work earlier in the current
   conversation (before the last task got checked off) — `tasks.md`
   checkboxes are a fact about implementation completeness, not proof of
   review. If review already happened, skip straight to asking whether to
   archive now; don't re-present the work for review a second time.

Concretely, what to do per gap:
- **Proposal complete, no design doc** → invoke `superpowers:brainstorming`
  to begin the brainstorm/grill stage.
- **Design doc exists, no plan** → invoke `superpowers:writing-plans` to
  begin the writing-plans stage.
- **All tasks checked, not archived** → present the completed work for
  Eva's review (unless already done this conversation — see point 3
  above), then run `/opsx:archive` (or ask Claude to archive the change)
  once she approves.

## Auto time log (no review gate — read this before "fixing" it)

If a repo's `.claude/synclinear.json` has `timetable_dir` set, every Stop
event automatically computes the current work block (from the session
transcript, 20-minute idle-gap grouping) and writes it to that week's log
file under `timetable_dir` — **with no review step, unconditionally,
every single time.**

**This is deliberate, not an oversight.** Every other mechanism in this
skill (flows 3a/3b/3c, workflow-stage gaps) either waits for Eva's
review before writing, or writes once per signal and never touches it
again. This one writes on literally every Stop event because the data
has no judgment content to review — a work-block timestamp is an
objective fact about when Eva was interacting with Claude, not a
decision like "should this become a Linear ticket." **Do not add a
review/proposal step here to make it "consistent" with the other
flows** — that would contradict the confirmed design (see
`docs/auto-time-log/design.md`).

**Known limitation, not a bug:** the last line of any week file is
auto-maintained and can be overwritten at any time. If Eva hand-edits
that line (e.g. correcting a duration) while it's still the file's last
line, the next Stop event will silently overwrite her edit. Only edit a
line once a newer block has started (it's no longer the file's last
line) — at that point the tool has moved on and won't touch it again.

## First-time setup for a new repo

If `.claude/synclinear.json` doesn't exist yet and Eva asks you to set
this up for a repo: ask which Linear team and project it maps to (use
`list_teams` / `list_projects` to show her real options, don't guess),
ask which file the repo's coding hours should be appended to
(`timetable_path` — don't assume a filename), then `save_config` with
`last_synced_commit` set to the repo's current
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
