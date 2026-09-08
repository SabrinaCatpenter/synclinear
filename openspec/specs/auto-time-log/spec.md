# auto-time-log Specification

## Purpose
TBD - created by archiving change auto-time-log-weekly-split. Update Purpose after archive.
## Requirements
### Requirement: Block-grouping algorithm reimplemented in lib/
The system SHALL provide an importable function in `lib/` that parses a
Claude Code session transcript's `.jsonl` file, extracts every
`timestamp` field, sorts them, and groups them into work blocks using a
20-minute idle-gap cutoff — the same algorithm as the standalone
`time_tracker.py` script, reimplemented so synclinear has no dependency
on that external file.

#### Scenario: Continuous activity within the idle gap
- **WHEN** a transcript's timestamps have no gap exceeding 20 minutes
  between consecutive entries
- **THEN** all of them are grouped into a single work block

#### Scenario: A real idle gap splits blocks
- **WHEN** two consecutive timestamps in the transcript are more than 20
  minutes apart
- **THEN** they are placed into two separate blocks

### Requirement: Automatic, unconditional write on every Stop event
The system SHALL, when a repo's config has `timetable_dir` set,
recompute the current work block on every Stop hook invocation and write
it to the appropriate weekly log file, without waiting for review or
approval — this is a deliberate exception to synclinear's review-gate
principle for every other flow.

#### Scenario: Repo has opted in
- **WHEN** `.claude/synclinear.json` has `timetable_dir` set and the Stop
  hook fires
- **THEN** the current block is written to disk before the hook exits,
  with no proposal text printed and no wait for Eva's reply

#### Scenario: Repo has not opted in
- **WHEN** `.claude/synclinear.json` has no `timetable_dir` field (or no
  config at all)
- **THEN** this capability does nothing — same "silent when not
  configured" behavior as every other flow

### Requirement: Upsert semantics based on block start-time comparison
The system SHALL compare the current computed block's start-time against
the target week-file's last existing line's recorded start-time: if they
match, overwrite that line; if they differ (or the file has no lines
yet), append a new line.

#### Scenario: Same block continuing
- **WHEN** the current block's start-time equals the last line's
  recorded start-time
- **THEN** that line is overwritten with the block's updated end-time and
  duration, not duplicated as a new line

#### Scenario: A new block has started
- **WHEN** the current block's start-time differs from the last line's
  recorded start-time (a real idle gap occurred since the last write)
- **THEN** a new line is appended, and the previous line is left
  unchanged (it is now final)

#### Scenario: First write to an empty or nonexistent week file
- **WHEN** the target week file doesn't exist yet, or exists but is empty
- **THEN** the current block is written as the file's first line

### Requirement: Weekly file boundary at Friday 00:00 local time
The system SHALL determine which week a block belongs to using the
block's start-time, converted to the local timezone of the machine
running the hook, with Friday 00:00 as the boundary (Saturday through
Thursday night is one week).

#### Scenario: Block starts before Friday 00:00 local time
- **WHEN** a block's local start-time falls on Thursday or earlier in the
  same week
- **THEN** it is filed under that week's log file

#### Scenario: Block starts at or after Friday 00:00 local time
- **WHEN** a block's local start-time falls at or after Friday 00:00
- **THEN** it is filed under the following week's log file (the new week
  that just started)

### Requirement: Weekly file naming convention
The system SHALL name each weekly log file
`<week-start-date>_<week-end-date>.txt` (ISO date format, e.g.
`2026-09-05_2026-09-11.txt`), located under the repo's configured
`timetable_dir` — no separate filename-prefix field exists; the
directory itself (named however the repo owner likes) carries that
context.

#### Scenario: New week's first write
- **WHEN** a block's week has no existing log file yet
- **THEN** the system creates `<timetable_dir>/<start>_<end>.txt` with
  that block as its first line

### Requirement: New config field, existing timetable_path untouched
The system SHALL add `timetable_dir` as an optional config field (its
absence means this capability is not opted into, same as before this
change existed) — the existing `timetable_path` field's meaning
(referenced by flow 3a's SKILL.md text) SHALL NOT be altered by this
change.

#### Scenario: Repo has timetable_path but not timetable_dir
- **WHEN** a repo's config has the pre-existing `timetable_path` field
  but no `timetable_dir`
- **THEN** flow 3a's existing (unbuilt) time-log reference is unaffected,
  and this new auto-time-log capability does nothing for that repo

### Requirement: Crash-safe writes
The system SHALL write weekly log file updates via a temp-file-then-rename
pattern (write full new content to a sibling temp file, then atomically
replace the target), not in-place line editing, so a crash or kill
mid-write cannot corrupt the existing file.

#### Scenario: Write interrupted mid-operation
- **WHEN** the write process is killed after the temp file is written but
  before the rename completes
- **THEN** the original weekly log file remains intact and unmodified

