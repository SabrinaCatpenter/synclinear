---
name: synclinear
description: Sync a git repo's state into Linear and its time log, AND keep the 7-step dev cycle moving — (3a) unsynced commits into Done tickets + time-log lines, (3b) OpenSpec proposals into new Todo tickets sized from tasks.md, (3c) archived OpenSpec changes into a client-facing artifact reminder, (workflow-stage gaps) directs Claude to begin the next stage of the 7-step cycle when one stalls, (flow 4) drafts a periodic invoice from raw time-log data on a configurable cadence, reviewed before writing — always with a review step before writing anything to Linear or a file, and (auto time-log) automatically records work blocks into weekly files with no review gate, since a timestamp is a fact, not a decision. Triggered automatically by a Stop hook reminder; can also be invoked directly by Eva.
---

# synclinear

You're reading this because either (a) a Stop-hook reminder told you there
are unsynced commits in the current repo, or (b) Eva asked you to sync
directly.

**This skill has two halves that share one review gate and one sync
marker — not two separate mechanisms.** Every sync run proposes BOTH
Linear ticket changes AND a new time-log line together, Eva approves them
together, and one `last_synced_commit` update covers both.

**Status note — superseded 2026-09-09:** the note that used to live here
said the time-log half's transcript-location mechanism wasn't built yet.
That was true through 2026-09-08; the "Auto time log" section below
describes the mechanism that shipped that same day (archived change
`auto-time-log-weekly-split`) and has been live since. This note is kept
only as a record that the gap existed, not as current guidance — don't
tell Eva the time-log half "isn't wired up," it is.

**Never reference a ticket by its bare ID.** Every time a ticket ID
appears — in a printed sync proposal, in a status update to Eva, in a
commit message, anywhere — pair it with the ticket's title (e.g. `STU-161
"Reversible identity merge + merge audit log"`). A bare ID carries no
context for whoever reads it; this isn't specific to Linear or to this
skill, it's a general rule for referencing any opaque identifier when
talking to a person. Added 2026-09-09 after exactly this mistake.

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

**The reminder fires once per HEAD, not on every Stop.** Same fix as
3b/3c's re-nagging (added 2026-09-09): the hook records the current
commit SHA in `announced_commits_head` the moment it fires, so it won't
repeat while Eva is still deciding. It re-fires only once HEAD moves
again (new commits landed) — approving the sync (step 7 below) advances
`last_synced_commit`, which naturally empties the unsynced-commit list
on the next run regardless of this marker.

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
   - STU-125 "<existing ticket's own title>" -> Done (evidence: <sha> <subject>)
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

**The reminder fires once per change, not on every Stop.** The hook
records each newly-surfaced change in `announced_unticketed` the moment
it first fires, so it won't re-nag every turn while Eva is still
deciding — don't mistake "no reminder this turn" for "already handled";
check `known_openspec_changes` and `announced_unticketed` (step 1) to
see what's actually still open.

1. Read `.claude/synclinear.json` for `linear_team`, `linear_project`,
   `known_openspec_changes`, `announced_unticketed`.
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
   explicitly-skipped change is never re-proposed on the next run. Also
   remove `<name>` from `announced_unticketed` if present (it's the
   "still deciding" marker; once `known_openspec_changes` has the final
   answer, the marker's job is done — leaving it doesn't cause a bug,
   but it's dead weight in the config file).

## Flow 3c: archived OpenSpec change → client artifact reminder

Triggered by a Stop-hook reminder noting the OpenSpec archive changed
since `last_artifact_check_at`, or by Eva directly.

**The signal is git-based, not filesystem mtime — and self-skips when
there's nothing archived yet.** Corrected 2026-09-09: comparing the
archive directory's raw mtime against `last_artifact_check_at` produced
false positives (anything that merely touches the directory — `openspec
init` creating it, a clone — bumps mtime with no real archive event
behind it), and an empty archive directory was never short-circuited, so
a false positive kept re-firing every Stop until someone noticed and
manually advanced the timestamp. The hook now reads the most recent
*commit* touching `openspec/changes/archive` (`archive_dir_last_commit_at`
in `lib/openspec_check.py`), and returns nothing at all when that
directory is currently empty — no archived changes yet means no need to
interrupt Eva, ever, until something real lands there.

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

## Flow 4: periodic invoice draft

Triggered by a Stop-hook reminder that a repo's invoice is due, or by
Eva asking directly (she may just show up and start this — the
reminder is a backstop, not the only way in). Opt-in: does nothing
unless both `invoice_cadence_days` (integer, days between invoices) and
`invoice_next_due` (ISO date) are set in `.claude/synclinear.json`.

**What this produces is a draft, not hand-typed content, and not
something the auto-time-log mechanism above does on its own.** The
raw `timetable_dir` week files are source data only — no description, no
subtotals, no billing math. Turning them into an invoice-style document
(the file at `timetable_path` — per-block narrative, weekly subtotals,
meeting notes, $/hr totals, e.g. this project's own
`ironman-time-log.txt`) is real drafting work: deciding what to call a
block of activity, which items group together, what the subtotal is.
That's exactly the kind of judgment call every other flow in this skill
routes through a review gate before writing, so this flow gets one too,
same as the others — Eva reviews the draft before anything is written to
`timetable_path`.

1. Read `.claude/synclinear.json` for `timetable_dir`, `timetable_path`,
   `invoice_cadence_days`, `invoice_next_due`.
2. Determine the period: from the invoice's last covered date (read the
   end of the existing `timetable_path` file, or ask Eva if it's
   ambiguous) through today.
3. Gather the raw material for that period:
   - Every `timetable_dir` week file overlapping the period (the
     mechanical `<start> -> <end> (<duration>)` lines).
   - `git log` across whatever repos are relevant, for commit context —
     what the work blocks actually were.
   - Calendar meetings via the Google Calendar MCP tools, for the same
     period, if connected.
   - Anything Eva dictates directly (WhatsApp call durations in
     particular — there is no automated source for these; call duration
     only ever shows on the device that answered, and no platform data
     captures it, so ask Eva plainly rather than guessing at a duration).
4. Draft entries in the exact style of the existing `timetable_path`
   file (read it first — match its own format, don't impose a generic
   one) covering the new period: per-block descriptions grounded in the
   commit/calendar evidence gathered above, a period subtotal, and
   running total / billing math if the file's existing format includes
   it.
5. Print the draft and wait for Eva's review — **review gate, same rule
   as every other flow: do not write to `timetable_path` before this
   step and Eva's reply.** She may edit specific entries, correct a
   duration, or reject a block entirely.
6. Apply only what she approved: append/update `timetable_path` with the
   final entries. Then advance `invoice_next_due` by `invoice_cadence_days`
   via `config.save_config` — this MUST happen once the draft is applied,
   the same way every other flow's marker advances on completion, so the
   same period is never redrafted next time.

## One-shot reminders (`one_shot_reminders`)

Three more Stop-hook signals, added 2026-09-09, tracked in
`.claude/synclinear.json`'s `one_shot_reminders` list — same one-shot
philosophy as `advanced_workflow_gaps` (fire once, record a signature,
never repeat that exact signature), but for concerns that don't fit the
7-step per-change gap model:

- **`timetable_dir` opt-in nudge.** Fires once, for any repo that has
  `.claude/synclinear.json` at all but no `timetable_dir` key — ask Eva
  once whether she wants the auto time-log mechanism on for this repo
  (see "Auto time log" below), then move on regardless of her answer; if
  she says yes, set `timetable_dir` via `config.save_config` yourself.
  Existed because the auto-time-log capability shipped 2026-09-08 without
  updating "First-time setup" to ask about it, so repos set up before
  that date (or even after it, until this fix) could go indefinitely
  with time tracking silently off and no way to tell "never asked" from
  "asked and declined."
- **SKILL.md staleness nudge.** Fires once per archive event, only for a
  repo whose root has its own `SKILL.md` (i.e., a repo that IS a
  synclinear-style skill, not just a repo that uses one) — if an OpenSpec
  change archived more recently than `SKILL.md` was last committed,
  says so and asks for a quick read-through. It does not inspect content
  or guess which prose is stale; it only flags the timing gap. Existed
  because a "not yet built" status note in this very file sat
  uncorrected for a day after the mechanism it described had already
  shipped and archived — nothing in the sync mechanism itself pointed
  back at its own documentation.
- **Invoice due (flow 4).** Fires once per due date
  (`invoice_due:<date>`), only when a repo has opted in with both
  `invoice_cadence_days` and `invoice_next_due` set — see "Flow 4:
  periodic invoice draft" above for what happens once it fires.

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
(`timetable_path` — don't assume a filename), **and separately ask
whether she wants the auto time-log mechanism turned on for this repo**
(`timetable_dir` — a directory, not a file; if yes, weekly log files get
written there automatically on every Stop event, no review gate, see
"Auto time log" below; if she doesn't mention it or isn't sure, ask
explicitly rather than silently omitting it — omitting it is exactly
what happened for this repo on 2026-09-08 and produced weeks of
silently-missing time data before anyone noticed). **Also ask whether
she wants periodic invoice drafting turned on** (`invoice_cadence_days`
+ `invoice_next_due` — see "Flow 4" above; skip both if she doesn't want
it, same opt-in-by-omission pattern as `timetable_dir`, but ask rather
than assume, for the same reason). Then `save_config` with
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
