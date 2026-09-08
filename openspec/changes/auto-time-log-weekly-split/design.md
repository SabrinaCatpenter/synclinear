## Context

Flow 3a has referenced a "matching time-log line" since v1, but the
computation behind it was never built — the SKILL.md status note has
said so from the start. Today, Eva computes hours manually with a
standalone script, `time_tracker.py` (living at
`C:\Users\Eva Ng\Desktop\ironman\time_tracker.py`, outside this repo),
which parses a Claude Code session transcript's `.jsonl` file, extracts
every `timestamp` field, sorts them, and groups them into work blocks
using a 20-minute idle-gap cutoff. She then hand-transcribes the result
into a single growing txt file.

This design reimplements that same algorithm inside synclinear's own
`lib/`, wires it into the Stop hook so it runs automatically, and splits
the output by week (Friday 00:00 local time as the cutoff) instead of
one ever-growing file — confirmed requirements from this session's
explore phase with Eva, not open questions.

## Goals / Non-Goals

**Goals:**
- Automatically compute the current (possibly still-in-progress) work
  block on every Stop event, using the same 20-minute idle-gap algorithm
  as `time_tracker.py`, reimplemented as an importable function (not a
  dependency on the external standalone script, since this tool ships to
  colleagues who won't have that specific file on their machine).
- Write the result directly, with no review gate — this is a deliberate,
  explicit, documented exception to synclinear's "review before writing"
  principle, justified by the nature of the data: a work-block timestamp
  is an objective fact about when Eva was interacting with Claude, not a
  judgment call the way "should this become a Linear ticket" is.
- Split output into weekly files, Friday 00:00 **local** time as the
  boundary (Saturday through Thursday night is one week) — local time,
  not UTC, because the boundary is meant to reflect Eva's actual work
  week, and the transcript's raw timestamps are UTC.
- Upsert semantics: every Stop event re-derives the latest block and
  overwrites the current week file's last line with it, so the file
  always reflects up-to-the-minute progress; only when a real idle gap
  produces a genuinely new block does the previous line become final and
  a new line start.

**Non-Goals:**
- Not touching flow 3a's own commit-to-Linear logic, or its existing
  `timetable_path` field's meaning — that field stays exactly as it is,
  referenced by flow 3a's still-unbuilt time-log mention; this proposal
  adds a parallel, independent mechanism via a new field.
- Not retroactively backfilling historical time logs from old transcripts
  — this only starts logging from whenever a repo opts in going forward,
  same "no automatic backfill" policy as flows 3a/3b already follow.
- Not creating a Linear ticket for this work — synclinear has no
  Linear team/project of its own.
- Not solving multi-session concurrency (two Claude Code sessions in the
  same repo at the same time, both writing to the same week file) — see
  Risks below; out of scope for this design to solve, acceptable given
  Eva's actual usage pattern (one session per repo at a time).

## Decisions

**Decision 1 — Reimplement the block-grouping algorithm inside
`lib/`, don't depend on the external script.** `time_tracker.py`'s core
logic (`load_timestamps`, `group_into_blocks`) is simple and
self-contained — read every `timestamp` field from a `.jsonl` transcript,
sort, group by a `timedelta` idle-gap cutoff. Porting it into
`lib/time_blocks.py` as importable functions (not shelling out to the
external script, which lives outside this repo and won't exist on a
colleague's machine) keeps synclinear dependency-free, consistent with
every other `lib/` module.

**Decision 2 — Upsert via "does the last line's start-time match the
current last block's start-time."** Every Stop event: re-parse the
transcript, get all blocks, take the last one (call it `current_block`,
which may still be open — no way to know a block has truly ended until a
real idle gap appears after it). Read the target week-file's last
existing line, if any, and parse its recorded start-time. If that
start-time equals `current_block`'s start-time, this is the same block
continuing — overwrite that line with `current_block`'s fresh end-time
and duration. If it differs (or the file is empty/doesn't exist), a real
idle gap has occurred since the last write — `current_block` is a
genuinely new block, so append a new line instead of overwriting.
Considered a separate "is this block still open" boolean flag instead of
comparing start-times, but start-time comparison is simpler, needs no
extra persisted state, and is self-correcting (if a write is ever missed
for any reason, the next write's comparison still behaves correctly).

**Decision 3 — Which week a block belongs to is decided by its START
time (grilled and corrected).** A block that happens to straddle the
Friday-00:00 boundary (e.g., starts Thursday 23:50, still going at
Friday 00:10) is filed entirely under the week containing its start —
never split across two files. This avoids a block being fragmented
mid-write, and matches how a human would describe "when did I start this
session" as the anchor for which week it counts toward.

The first draft of this decision justified it by claiming "a block
crossing midnight is short, so the mis-attribution window is small" —
grilled and found wrong: the 20-minute gap cutoff bounds the *gaps
between* timestamps within a block, not the block's total *duration*. A
block that starts Thursday evening and continues, with no single pause
exceeding 20 minutes, straight through a long work session (a late-night
push before a deadline is a realistic case, not a hypothetical) could
run for hours across the boundary, and this design would still file the
entire multi-hour block under the Thursday-starting week. That's an
accepted trade-off, not a small one — splitting the block at the
boundary would require writing two lines into two different files from
one computed block, which meaningfully complicates the upsert logic in
Decision 2 for a case that's genuinely rare. Documented honestly here
instead of behind a false "the window is small" claim: a long block that
crosses the boundary counts entirely toward the week it started in, full
stop, and that can occasionally attribute a chunk of Friday's hours to
the prior week's file.

**Decision 4 — New config field `timetable_dir`, existing
`timetable_path` untouched.** `timetable_path` currently means "a single
file flow 3a's SKILL.md text refers to for its not-yet-built time-log
line." Repurposing it to mean "a directory of weekly files" would
silently break that unrelated flow's documented semantics. `timetable_dir`
is additive: a repo opts into this new capability by setting it; a repo
that only wants flow 3a's existing behavior (once its time-log half is
eventually built) is unaffected.

**Decision 5 — File naming: `<start-date>_<end-date>.txt`, no separate
prefix field (grilled and revised).** The original draft of this design
added a second config field, `timetable_file_prefix`, to let the
filename carry a prefix like `ironman-time-log-`. Grilled: in every
realistic scenario, the directory and the prefix are set together, once,
and never vary independently — nobody configures "same directory,
different prefix" or "different directory, same prefix." A second field
just doubles the setup burden for no real flexibility gained, and the
directory itself already carries the "what is this" context (it's a
directory named for time logs, holding files named for date ranges — the
prefix was redundant with the directory's own name). Dropped
`timetable_file_prefix` entirely; the filename is just
`<week-start>_<week-end>.txt` (e.g. `2026-09-05_2026-09-11.txt`) under
whatever `timetable_dir` points to.

**Decision 6 — Local timezone, computed from the machine running the
hook, not hardcoded.** The transcript's raw timestamps are UTC (ISO 8601
with a `Z` suffix, confirmed from earlier `time_tracker.py` output and
from Stop-hook payload inspection this session). Converting to local
time uses Python's `datetime.now().astimezone().tzinfo` pattern (same
approach `time_tracker.py` itself already uses for its human-readable
block display) — this naturally reflects whatever timezone the machine
running the hook is set to, no separate config field needed.

**Decision 7 (the deliberate exception, stated explicitly so it's never
"fixed" by mistake) — no review gate, no persisted "already written"
marker.** Every other write path in this hook (flows 3a/3b/3c, and the
workflow-stage gaps) either waits for Eva's review-and-approval before
writing, or writes once per fired signature and then never touches that
signature again. This capability does neither: it writes on literally
every Stop event, unconditionally, upserting the same line potentially
dozens of times as a work session continues. This is correct and
intentional — the write is idempotent in effect (it always converges on
"the true current state of the last block"), and the data being written
carries no judgment content that would benefit from a review step.

## Risks / Trade-offs

- **[Risk]** Two Claude Code sessions running concurrently in the same
  repo would both try to upsert the same week file's last line,
  potentially racing or clobbering each other. **[Mitigation]** Accepted
  as out of scope (see Non-Goals) — Eva's actual usage pattern is one
  active session per repo; if this becomes a real problem later, a
  file lock or per-session block tracking would need its own design
  pass, not bolted on here speculatively.
- **[Risk]** A block that's still "open" (no idle gap yet) gets
  overwritten many times per work session — if the hook crashes or is
  killed mid-write, the file could be left in a partially-written state.
  **[Mitigation]** Write via a temp-file-then-rename pattern (write the
  full new file content to a sibling temp file, then `os.replace()` it
  over the target) rather than in-place line editing, so a crash mid-write
  never corrupts the existing file — the old version survives until the
  new one is fully ready.
- **[Risk]** The 20-minute idle-gap heuristic is a heuristic — it can
  merge two genuinely separate work sessions that happen to be within 20
  minutes of each other, or split one continuous session that happened to
  pause slightly longer. **[Mitigation]** Accepted — this is the same
  heuristic `time_tracker.py` already uses today, unchanged in this
  reimplementation; not a new risk introduced by this design.
- **[Risk]** Reading the transcript file on every single Stop event (a
  file that grows throughout a long session) could get slow for a very
  long-running session. **[Mitigation]** Not optimized in this design —
  parsing a `.jsonl` file line-by-line is cheap even at thousands of
  lines; revisit only if this proves to be a real problem in practice.
- **[Risk]** If Eva manually hand-edits a week file's last line (e.g.
  correcting a duration by hand) while that line is still the "open"
  block being upserted, the next Stop event's write will silently
  overwrite her edit — the upsert logic only checks whether the
  start-time matches, and a hand-edit that doesn't change the start-time
  looks identical to "same block continuing" from the algorithm's point
  of view. **[Mitigation]** Not solved mechanically (no way to
  distinguish "the tool wrote this" from "a human wrote this" without
  adding a marker, which is unnecessary complexity for now) — instead,
  documented explicitly as a usage rule in SKILL.md: the last line of any
  week file is auto-maintained and may be overwritten at any time; only
  edit a line once it's no longer the file's last line (i.e., a newer
  block has already started, so the tool has moved on).

## Migration Plan

No migration — purely additive, same as every prior addition to this
hook. A repo that doesn't set `timetable_dir` sees no behavior change at
all (the new capability is entirely opt-in via config presence, same
pattern as flows 3b/3c's OpenSpec-awareness being a no-op in a repo with
no `openspec/` directory).

## Open Questions

None outstanding — all resolved during explore with Eva this session, plus
three design points caught and revised during a self-directed grilling
pass (Decision 3's corrected mis-attribution claim, Decision 5's dropped
`timetable_file_prefix` field, and the new hand-edit-gets-overwritten
risk documented above) — Eva was asleep for this pass and authorized
proceeding without her live review this round.
