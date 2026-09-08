## Why

synclinear's flow 3a has always mentioned "matching time-log line" as
part of the commit-sync proposal, but the mechanism to actually compute
those hours was never built — SKILL.md's status note has said so since
v1. Time logging today is entirely manual: Eva runs a standalone script
(`time_tracker.py`, living outside this repo, in a specific project
folder) after the fact and hand-edits a single growing txt file. This
proposal closes that gap with a real, automatic mechanism, generalized so
any colleague's project can use it — not tied to Eva's own file layout.

## What Changes

- Add a Stop-hook-driven auto-log capability: every time the hook runs,
  it re-derives the current work block (20-minute idle-gap grouping over
  the session transcript's timestamps, same algorithm as the existing
  standalone `time_tracker.py`, reimplemented inside synclinear's own
  `lib/` so the tool has no external-script dependency) and **writes it
  directly** — no review gate, no proposal-and-wait. This is a deliberate,
  explicit exception to synclinear's "everything is reviewed before
  writing" rule: a work-block timestamp is an objective fact ("Eva was
  interacting with Claude during this window"), not a judgment call like
  "should this become a Linear ticket."
- **BREAKING (behavioral):** flow 3a's mention of appending a time-log
  line to a single `timetable_path` file is superseded for any repo that
  opts into this new mechanism — logging becomes automatic and
  continuous rather than proposed-alongside-commits.
- Time logs split into weekly files instead of one growing file, cut off
  at Friday 00:00 local time (Saturday through Thursday night is one
  week), named `<prefix>-<start-date>_<end-date>.txt`.
- New config field `timetable_dir` (the directory weekly files live in) —
  the existing `timetable_path` field is left alone, since it has
  different semantics (a single file) that flow 3a's SKILL.md text still
  refers to, and changing its meaning would be a silent breaking change
  to that unrelated flow.
- No Linear ticket for this work (synclinear has no Linear
  team/project of its own — it's a public tool project, not an MLAI
  client project).

## Capabilities

### New Capabilities

- `auto-time-log`: Stop-hook-driven, upsert-based weekly time logging —
  computing the current (possibly still-open) work block on every Stop
  event and writing it directly to the current week's log file, without
  a review gate.

### Modified Capabilities

(none — flow 3a's proposal-based time-log mention in SKILL.md is
superseded by this new mechanism for opted-in repos, but flow 3a's own
spec, if formalized later, is out of scope for this change; this
proposal only adds the new capability)

## Impact

- `lib/config.py`: one new field, `timetable_dir` (string path).
- New module `lib/time_blocks.py` (or similar): the 20-minute idle-gap
  block-grouping algorithm, reimplemented from `time_tracker.py`'s logic
  but as an importable function operating on a transcript path, not a
  standalone CLI script.
- `hooks/check_unsynced.py`: gains a new unconditional (non-review-gated)
  write path — this is architecturally different from every other flow
  in this hook (3a/3b/3c and the workflow-stage gaps are all
  review-gated-proposal or fire-once-directive; this one writes on every
  single Stop event without persisting a "already handled" marker, since
  the whole point is continuous upsert).
- `SKILL.md`: needs a new section explaining this exception to the
  review-gate principle, explicitly, so nobody later "fixes" it into a
  proposal-based flow by mistake.
- No impact on any repo-specific configuration — must work for any MLAI
  colleague's project, not just Ironman.
