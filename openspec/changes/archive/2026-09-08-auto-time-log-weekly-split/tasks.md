## 1. Block-grouping algorithm

- [ ] 1.1 Create `lib/time_blocks.py` porting `time_tracker.py`'s
  `load_timestamps()` and `group_into_blocks()` as importable functions
  (not a CLI script) — same 20-minute idle-gap algorithm, no behavior
  changes from the original
- [ ] 1.2 Add `lib/test_time_blocks.py` with tests for both functions
  (continuous activity groups into one block, a real gap splits blocks,
  empty transcript returns no blocks)

## 2. Config schema

- [ ] 2.1 Add `timetable_dir` as a new *optional* field to
  `lib/config.py` (NOT required — its absence means this capability
  isn't opted into; this differs from every prior config field added so
  far, which were all required). No separate prefix field — grilled and
  dropped (see design.md Decision 5): the directory alone carries enough
  context, and directory+prefix never vary independently in practice.
- [ ] 2.2 Add tests to `lib/test_config.py`: config without this field
  still loads successfully (backward compatible with every existing
  repo's config); config with it present loads it correctly

## 3. Weekly file resolution

- [ ] 3.1 Add a function to determine which week-file a given local
  datetime belongs to (Friday 00:00 boundary) and produce its expected
  filename (`<start>_<end>.txt`, no prefix)
- [ ] 3.2 Write tests: a Thursday-night timestamp and a Friday-morning
  timestamp in the same real-world week land in different files; the
  computed start/end dates in the filename are correct ISO dates

## 4. Upsert write logic

- [ ] 4.1 Add a function that reads a week-file's last line (if any),
  parses its recorded start-time, compares to the current block's
  start-time, and either overwrites the last line or appends a new one
  accordingly
- [ ] 4.2 Implement the write itself via temp-file-then-rename
  (`os.replace()`), not in-place editing
- [ ] 4.3 Write tests: upsert overwrites when start-times match; appends
  a new line when they differ; correctly handles an empty/nonexistent
  file as the first-write case; a crash simulated mid-write (kill before
  rename) leaves the original file untouched

## 5. Wire into the Stop hook

- [ ] 5.1 In `hooks/check_unsynced.py`, read `transcript_path` from
  stdin (already available — confirmed this session's stdin-reading
  code already extracts it for other purposes) and, if the repo's config
  has `timetable_dir` set, compute the current block and upsert-write it
  — unconditionally, with no paragraph added to the reminder text (this
  capability writes silently; it does not participate in the
  additionalContext reminder system flows 3a/3b/3c/gaps use)
- [ ] 5.2 Write tests covering: repo without `timetable_dir` — no file
  written, no error; repo with `timetable_dir` — a file appears in the
  right place with the right content after one hook run; two consecutive
  hook runs within the same block upsert (one line, not two); a
  simulated idle gap between two hook runs produces two lines

## 6. Documentation

- [ ] 6.1 Add a new SKILL.md section explaining this capability and its
  deliberate exception to the review-gate principle — explicit enough
  that nobody later "fixes" it into a proposal-based flow by mistake
  (state directly: this is intentional, here's why, do not change it to
  match flows 3a/3b/3c's pattern)
- [ ] 6.2 Update SKILL.md's frontmatter description to mention this
  fifth mechanism
- [ ] 6.3 Update README.md's setup instructions to mention the new
  optional config fields and what opting in looks like (confirm scope
  with Eva before writing, per the existing pattern for README changes)

## 7. Verification

- [ ] 7.1 Run the full test suite across all lib/ and hooks/ test files,
  confirm zero regressions in flows 3a/3b/3c/gaps
- [ ] 7.2 Manually verify against a real throwaway repo with a real
  Claude Code session transcript (not a synthetic one) — confirm the
  computed blocks match what a human would expect, and that the weekly
  file boundary behaves correctly across a real Thursday-to-Friday
  transition if the manual test happens to span one, or simulate it with
  a transcript containing timestamps straddling the boundary
