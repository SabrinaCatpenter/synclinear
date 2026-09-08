# Auto Time Log Weekly Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add automatic, unconditional (no review gate) weekly time-log writing to synclinear's Stop hook — every Stop event recomputes the current work block from the session transcript and upserts it into the correct week's log file.

**Architecture:** A new `lib/time_blocks.py` ports `time_tracker.py`'s block-grouping algorithm as importable functions. `hooks/check_unsynced.py` gains: a week-filename resolver (Friday 00:00 local-time boundary), an upsert-writer (temp-file-then-rename), and a stdin-reading refactor (the hook currently only extracts `cwd` from stdin and discards the rest — this needs `transcript_path` too, and stdin can only be read once per process, so the read itself must be restructured, not just added to). `lib/config.py` gains its first-ever *optional* field (every field added so far has been required).

**Tech Stack:** Python 3 stdlib only (`json`, `os`, `datetime`, `subprocess` already present), `unittest`, no new dependencies.

## Global Constraints

- This capability writes **unconditionally, with no review gate** — a deliberate, confirmed exception to every other flow in this hook (verbatim from design.md's Decision 7). Do not add a review/proposal step; that would contradict the confirmed design.
- The write never participates in the `additionalContext` reminder paragraphs flows 3a/3b/3c/gaps use — it's a silent side-effect, not a signal.
- Only opt-in: a repo without `timetable_dir` set in its config sees zero behavior change. `timetable_dir` is the first *optional* config field this project has ever had — every prior field (`linear_team`, `known_openspec_changes`, `advanced_workflow_gaps`, etc.) is required, and the validation logic needs a new code path for "present-but-optional," not just another entry in an existing required-keys tuple.
- Week boundary: Friday 00:00 **local** time (the machine running the hook's local timezone, not UTC, not configurable) — Saturday through Thursday night is one week.
- A block belongs to the week containing its **start** time, never split across two files, even if the block runs past the boundary (confirmed design decision, corrected during grilling from an earlier false "the window is small" justification — see docs/auto-time-log/design.md).
- Filename: `<week-start-date>_<week-end-date>.txt` (ISO dates), no prefix field — `timetable_file_prefix` was proposed then dropped during grilling; do not reintroduce it.
- Writes MUST use temp-file-then-rename (`os.replace()`), never in-place line editing — crash safety requirement from design.md.
- Upsert comparison is by **start-time only** (does the target file's last line's recorded start-time match the current block's start-time) — no separate "is this block open" flag; this needs no extra persisted state per design.md's Decision 2 rationale.
- The 20-minute idle-gap algorithm itself (`load_timestamps`, `group_into_blocks`) must be a faithful port of `C:\Users\Eva Ng\Desktop\ironman\time_tracker.py`'s existing logic — same behavior, no changes to the grouping rule.

---

### Task 1: `lib/config.py` — first optional field, `timetable_dir`

**Files:**
- Modify: `C:\Users\Eva Ng\.claude\skills\synclinear\lib\config.py`
- Test: `C:\Users\Eva Ng\.claude\skills\synclinear\lib\test_config.py`

**Interfaces:**
- Consumes: nothing new — same `load_config(repo_root) -> dict | None`, `save_config(repo_root, config) -> None` signatures.
- Produces: `load_config` now accepts (but does not require) a `timetable_dir` key. If present, it must be a string, or the config is invalid (`None`) — same "malformed = not opted in" philosophy as every other field, just optional instead of required. If absent, `load_config` succeeds exactly as it does today (no behavior change for any existing repo's config). Task 5's `_write_time_log` reads `config.get("timetable_dir")` (using `.get`, not `config["timetable_dir"]`, since it may be absent) to decide whether to do anything at all.

The current file (already read this session) has `_REQUIRED_STRING_KEYS` and `_REQUIRED_LIST_OF_STRING_KEYS` tuples, both validated with `all(...)`/loop checks that fail the whole config if any listed key is missing or wrong-typed. This task adds a third category — optional string keys — validated differently: absence is fine, presence-with-wrong-type is not.

- [ ] **Step 1: Write the failing tests**

Add these test methods to `TestLoadConfig` in `lib/test_config.py` (keep every existing test method unchanged — this is purely additive validation):

```python
    def test_valid_config_with_timetable_dir_returns_dict(self):
        with tempfile.TemporaryDirectory() as repo_root:
            claude_dir = os.path.join(repo_root, ".claude")
            os.makedirs(claude_dir)
            with open(os.path.join(claude_dir, "synclinear.json"), "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "linear_team": "Studio",
                        "linear_project": "[Studio] Project Ironman",
                        "timetable_path": "C:/timetable.txt",
                        "last_synced_commit": "de1c2c8",
                        "known_openspec_changes": [],
                        "last_artifact_check_at": "2026-09-08T00:00:00Z",
                        "advanced_workflow_gaps": [],
                        "timetable_dir": "C:/timelogs",
                    },
                    f,
                )

            config = load_config(repo_root)

            self.assertEqual(config["timetable_dir"], "C:/timelogs")

    def test_valid_config_without_timetable_dir_still_returns_dict(self):
        with tempfile.TemporaryDirectory() as repo_root:
            claude_dir = os.path.join(repo_root, ".claude")
            os.makedirs(claude_dir)
            with open(os.path.join(claude_dir, "synclinear.json"), "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "linear_team": "Studio",
                        "linear_project": "[Studio] Project Ironman",
                        "timetable_path": "C:/timetable.txt",
                        "last_synced_commit": "de1c2c8",
                        "known_openspec_changes": [],
                        "last_artifact_check_at": "2026-09-08T00:00:00Z",
                        "advanced_workflow_gaps": [],
                    },
                    f,
                )

            config = load_config(repo_root)

            self.assertIsNotNone(config)
            self.assertNotIn("timetable_dir", config)

    def test_timetable_dir_wrong_type_returns_none(self):
        with tempfile.TemporaryDirectory() as repo_root:
            claude_dir = os.path.join(repo_root, ".claude")
            os.makedirs(claude_dir)
            with open(os.path.join(claude_dir, "synclinear.json"), "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "linear_team": "Studio",
                        "linear_project": "[Studio] Project Ironman",
                        "timetable_path": "C:/timetable.txt",
                        "last_synced_commit": "de1c2c8",
                        "known_openspec_changes": [],
                        "last_artifact_check_at": "2026-09-08T00:00:00Z",
                        "advanced_workflow_gaps": [],
                        "timetable_dir": 12345,
                    },
                    f,
                )

            self.assertIsNone(load_config(repo_root))
```

- [ ] **Step 2: Run tests to verify the new ones behave as expected pre-fix**

Run: `cd "C:\Users\Eva Ng\.claude\skills\synclinear\lib" && python -m pytest test_config.py -v`
Expected: `test_valid_config_with_timetable_dir_returns_dict` and `test_valid_config_without_timetable_dir_still_returns_dict` already PASS (today's `load_config` ignores unknown extra keys and doesn't require `timetable_dir`, so both scenarios already work by accident) — `test_timetable_dir_wrong_type_returns_none` FAILS, because nothing currently validates this key's type at all, so a wrong-typed value is silently accepted today.

- [ ] **Step 3: Add optional-key validation to `load_config`**

In `lib/config.py`, add a new tuple and validation loop after the existing `_REQUIRED_LIST_OF_STRING_KEYS` block:

```python
_OPTIONAL_STRING_KEYS = ("timetable_dir",)
```

And in `load_config`, after the existing `for key in _REQUIRED_LIST_OF_STRING_KEYS:` loop, add:

```python
    for key in _OPTIONAL_STRING_KEYS:
        value = config.get(key)
        if value is not None and not isinstance(value, str):
            return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "C:\Users\Eva Ng\.claude\skills\synclinear\lib" && python -m pytest test_config.py -v`
Expected: PASS, all tests (existing eleven plus the three new ones = 14).

- [ ] **Step 5: Commit**

```bash
cd "C:\Users\Eva Ng\.claude\skills\synclinear"
git add lib/config.py lib/test_config.py
git commit -m "feat: add optional timetable_dir config field"
```

---

### Task 2: `lib/time_blocks.py` — port the block-grouping algorithm

**Files:**
- Create: `C:\Users\Eva Ng\.claude\skills\synclinear\lib\time_blocks.py`
- Test: `C:\Users\Eva Ng\.claude\skills\synclinear\lib\test_time_blocks.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `load_timestamps(path: str) -> list[datetime]` and `group_into_blocks(times: list[datetime], idle_gap: timedelta) -> list[tuple[datetime, datetime]]` — exact same signatures and behavior as `time_tracker.py`'s functions of the same name (verbatim port, confirmed against the real file this session). Task 5 imports both directly.

- [ ] **Step 1: Write the failing tests**

```python
from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from time_blocks import group_into_blocks, load_timestamps


def _write_transcript(path: str, timestamps: list[str]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for ts in timestamps:
            f.write(json.dumps({"timestamp": ts}) + "\n")


class TestLoadTimestamps(unittest.TestCase):
    def test_extracts_and_sorts_timestamps(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "transcript.jsonl")
            _write_transcript(path, [
                "2026-09-08T10:00:00.000Z",
                "2026-09-08T09:00:00.000Z",
                "2026-09-08T09:30:00.000Z",
            ])

            result = load_timestamps(path)

            self.assertEqual(len(result), 3)
            self.assertEqual(result, sorted(result))
            self.assertEqual(result[0], datetime(2026, 9, 8, 9, 0, 0, tzinfo=timezone.utc))

    def test_skips_lines_without_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "transcript.jsonl")
            with open(path, "w", encoding="utf-8") as f:
                f.write(json.dumps({"role": "user"}) + "\n")
                f.write(json.dumps({"timestamp": "2026-09-08T09:00:00.000Z"}) + "\n")
                f.write("not even valid json\n")

            result = load_timestamps(path)

            self.assertEqual(len(result), 1)

    def test_empty_file_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "transcript.jsonl")
            open(path, "w", encoding="utf-8").close()

            result = load_timestamps(path)

            self.assertEqual(result, [])


class TestGroupIntoBlocks(unittest.TestCase):
    def test_empty_list_returns_no_blocks(self):
        self.assertEqual(group_into_blocks([], timedelta(minutes=20)), [])

    def test_continuous_activity_groups_into_one_block(self):
        base = datetime(2026, 9, 8, 9, 0, tzinfo=timezone.utc)
        times = [base, base + timedelta(minutes=5), base + timedelta(minutes=10)]

        blocks = group_into_blocks(times, timedelta(minutes=20))

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0], (times[0], times[-1]))

    def test_gap_over_threshold_splits_into_two_blocks(self):
        base = datetime(2026, 9, 8, 9, 0, tzinfo=timezone.utc)
        times = [base, base + timedelta(minutes=5), base + timedelta(minutes=30)]

        blocks = group_into_blocks(times, timedelta(minutes=20))

        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0], (times[0], times[1]))
        self.assertEqual(blocks[1], (times[2], times[2]))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "C:\Users\Eva Ng\.claude\skills\synclinear\lib" && python -m pytest test_time_blocks.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'time_blocks'`.

- [ ] **Step 3: Write the implementation**

```python
"""Ports time_tracker.py's (C:\\Users\\Eva Ng\\Desktop\\ironman\\time_tracker.py)
block-grouping algorithm as importable functions — no dependency on that
external, machine-specific script, so this works for any colleague using
synclinear. Same 20-minute idle-gap algorithm, unchanged behavior.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta


def load_timestamps(path: str) -> list[datetime]:
    times = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = rec.get("timestamp")
            if ts:
                times.append(datetime.fromisoformat(ts.replace("Z", "+00:00")))
    times.sort()
    return times


def group_into_blocks(times: list[datetime], idle_gap: timedelta) -> list[tuple[datetime, datetime]]:
    if not times:
        return []
    blocks = []
    start = prev = times[0]
    for t in times[1:]:
        if t - prev > idle_gap:
            blocks.append((start, prev))
            start = t
        prev = t
    blocks.append((start, prev))
    return blocks
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "C:\Users\Eva Ng\.claude\skills\synclinear\lib" && python -m pytest test_time_blocks.py -v`
Expected: PASS, all 6 tests.

- [ ] **Step 5: Commit**

```bash
cd "C:\Users\Eva Ng\.claude\skills\synclinear"
git add lib/time_blocks.py lib/test_time_blocks.py
git commit -m "feat: port time_tracker.py's block-grouping algorithm into lib/"
```

---

### Task 3: Week-file name resolution (Friday 00:00 local boundary)

**Files:**
- Modify: `C:\Users\Eva Ng\.claude\skills\synclinear\hooks\check_unsynced.py`
- Test: `C:\Users\Eva Ng\.claude\skills\synclinear\hooks\test_check_unsynced.py`

**Interfaces:**
- Consumes: nothing from other tasks (pure date arithmetic).
- Produces: `_week_file_name(start_utc: datetime) -> str` — given a block's UTC start time, converts to local time, determines the Friday-00:00-bounded week it falls in, and returns `"<week-start-date>_<week-end-date>.txt"` (ISO dates). Task 5 calls this to build the full write path.

- [ ] **Step 1: Write the failing tests**

Add to `hooks/test_check_unsynced.py`:

```python
class TestWeekFileName(unittest.TestCase):
    def test_friday_itself_starts_its_own_week(self):
        # 2026-09-04 is a Friday (verified: datetime.date(2026, 9, 4).weekday() == 4).
        # Using a UTC timestamp equal to local midday keeps this test away
        # from timezone-boundary flakiness; expected values are computed
        # with the same local-tz-conversion logic the implementation itself
        # uses, kept as an independent formula below (not calling the
        # implementation), so a real regression in the implementation's
        # logic still gets caught rather than the test trivially agreeing
        # with whatever the implementation currently does.
        friday = datetime.datetime(2026, 9, 4, 10, 0, tzinfo=datetime.timezone.utc)
        result = _week_file_name(friday)
        local_tz = datetime.datetime.now().astimezone().tzinfo
        local_friday_date = friday.astimezone(local_tz).date()
        expected_start = local_friday_date
        expected_end = local_friday_date + datetime.timedelta(days=6)
        self.assertEqual(result, f"{expected_start.isoformat()}_{expected_end.isoformat()}.txt")

    def test_thursday_belongs_to_previous_fridays_week(self):
        # A Thursday, one day before the Friday used above.
        thursday = datetime.datetime(2026, 9, 3, 10, 0, tzinfo=datetime.timezone.utc)
        result = _week_file_name(thursday)
        local_tz = datetime.datetime.now().astimezone().tzinfo
        local_thursday_date = thursday.astimezone(local_tz).date()
        days_since_friday = (local_thursday_date.weekday() - 4) % 7
        expected_start = local_thursday_date - datetime.timedelta(days=days_since_friday)
        expected_end = expected_start + datetime.timedelta(days=6)
        self.assertEqual(result, f"{expected_start.isoformat()}_{expected_end.isoformat()}.txt")

    def test_saturday_belongs_to_the_friday_that_just_passed(self):
        saturday = datetime.datetime(2026, 9, 5, 10, 0, tzinfo=datetime.timezone.utc)
        result = _week_file_name(saturday)
        local_tz = datetime.datetime.now().astimezone().tzinfo
        local_saturday_date = saturday.astimezone(local_tz).date()
        days_since_friday = (local_saturday_date.weekday() - 4) % 7
        expected_start = local_saturday_date - datetime.timedelta(days=days_since_friday)
        expected_end = expected_start + datetime.timedelta(days=6)
        self.assertEqual(result, f"{expected_start.isoformat()}_{expected_end.isoformat()}.txt")
```

(Note: these tests deliberately compute their own expected value using the
same formula the implementation will use, rather than a hardcoded date
string — because the *local* timezone the test runs under is unknown in
advance, and hardcoding a UTC-based expectation would be flaky across
machines. Each test's expected-value formula is written independently in
the test itself, not by calling the implementation, so a real regression
in the implementation's logic still gets caught.)

`hooks/test_check_unsynced.py` already does `import datetime` as a full
module import (confirmed this session) — reuse it, don't add a duplicate.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "C:\Users\Eva Ng\.claude\skills\synclinear\hooks" && python -m pytest test_check_unsynced.py::TestWeekFileName -v`
Expected: FAIL with `NameError: name '_week_file_name' is not defined`.

- [ ] **Step 3: Write the implementation**

Add to `hooks/check_unsynced.py`, near the top alongside other module-level helpers:

```python
def _week_file_name(start_utc: datetime.datetime) -> str:
    local_tz = datetime.datetime.now().astimezone().tzinfo
    local_date = start_utc.astimezone(local_tz).date()
    # Friday = weekday() 4 (Monday=0..Sunday=6). Days since the most
    # recent Friday (0 if today IS Friday): this pins Mon-Thu to the
    # PRECEDING Friday's week, and Fri-Sun to the week that just started.
    days_since_friday = (local_date.weekday() - 4) % 7
    week_start = local_date - datetime.timedelta(days=days_since_friday)
    week_end = week_start + datetime.timedelta(days=6)
    return f"{week_start.isoformat()}_{week_end.isoformat()}.txt"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "C:\Users\Eva Ng\.claude\skills\synclinear\hooks" && python -m pytest test_check_unsynced.py::TestWeekFileName -v`
Expected: PASS, all 3 tests.

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `cd "C:\Users\Eva Ng\.claude\skills\synclinear\hooks" && python -m pytest test_check_unsynced.py -v`
Expected: all previously-passing tests still PASS, plus the 3 new ones.

- [ ] **Step 6: Commit**

```bash
cd "C:\Users\Eva Ng\.claude\skills\synclinear"
git add hooks/check_unsynced.py hooks/test_check_unsynced.py
git commit -m "feat: add Friday-00:00-local week-file name resolution"
```

---

### Task 4: Upsert write logic (temp-file-then-rename)

**Files:**
- Modify: `C:\Users\Eva Ng\.claude\skills\synclinear\hooks\check_unsynced.py`
- Test: `C:\Users\Eva Ng\.claude\skills\synclinear\hooks\test_check_unsynced.py`

**Interfaces:**
- Consumes: nothing from other tasks (operates on a plain file path and two local datetimes).
- Produces: `_upsert_block_line(week_file_path: str, start_local: datetime, end_local: datetime) -> None` — writes or overwrites the file's last line to represent this block, via temp-file-then-rename. Task 5 calls this after resolving the week-file path (Task 3) and computing local start/end times.

- [ ] **Step 1: Write the failing tests**

Add to `hooks/test_check_unsynced.py`:

```python
class TestUpsertBlockLine(unittest.TestCase):
    def test_creates_file_with_first_line_when_none_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "week.txt")
            start = datetime.datetime(2026, 9, 8, 9, 0)
            end = datetime.datetime(2026, 9, 8, 9, 30)

            _upsert_block_line(path, start, end)

            with open(path, encoding="utf-8") as f:
                lines = f.read().splitlines()
            self.assertEqual(len(lines), 1)
            self.assertIn("2026-09-08 09:00", lines[0])
            self.assertIn("09:30", lines[0])

    def test_overwrites_last_line_when_same_start_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "week.txt")
            start = datetime.datetime(2026, 9, 8, 9, 0)
            _upsert_block_line(path, start, datetime.datetime(2026, 9, 8, 9, 10))
            _upsert_block_line(path, start, datetime.datetime(2026, 9, 8, 9, 25))

            with open(path, encoding="utf-8") as f:
                lines = f.read().splitlines()

            self.assertEqual(len(lines), 1)
            self.assertIn("09:25", lines[0])
            self.assertNotIn("09:10", lines[0])

    def test_appends_new_line_when_different_start_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "week.txt")
            _upsert_block_line(
                path,
                datetime.datetime(2026, 9, 8, 9, 0),
                datetime.datetime(2026, 9, 8, 9, 30),
            )
            _upsert_block_line(
                path,
                datetime.datetime(2026, 9, 8, 10, 0),
                datetime.datetime(2026, 9, 8, 10, 15),
            )

            with open(path, encoding="utf-8") as f:
                lines = f.read().splitlines()

            self.assertEqual(len(lines), 2)
            self.assertIn("09:00", lines[0])
            self.assertIn("10:00", lines[1])

    def test_no_temp_file_left_behind_after_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "week.txt")
            _upsert_block_line(
                path,
                datetime.datetime(2026, 9, 8, 9, 0),
                datetime.datetime(2026, 9, 8, 9, 30),
            )

            entries = os.listdir(tmp)

            self.assertEqual(entries, ["week.txt"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "C:\Users\Eva Ng\.claude\skills\synclinear\hooks" && python -m pytest test_check_unsynced.py::TestUpsertBlockLine -v`
Expected: FAIL with `NameError: name '_upsert_block_line' is not defined`.

- [ ] **Step 3: Write the implementation**

Add to `hooks/check_unsynced.py`:

```python
def _format_block_line(start_local: datetime.datetime, end_local: datetime.datetime) -> str:
    duration = end_local - start_local
    return f"{start_local:%Y-%m-%d %H:%M} -> {end_local:%H:%M}  ({duration})"


def _parse_block_line_start(line: str) -> str | None:
    parts = line.split(" -> ", 1)
    if len(parts) != 2:
        return None
    return parts[0].strip()


def _upsert_block_line(week_file_path: str, start_local: datetime.datetime, end_local: datetime.datetime) -> None:
    new_line = _format_block_line(start_local, end_local)
    new_start_key = f"{start_local:%Y-%m-%d %H:%M}"

    existing_lines: list[str] = []
    if os.path.isfile(week_file_path):
        with open(week_file_path, encoding="utf-8") as f:
            existing_lines = [line.rstrip("\n") for line in f if line.strip()]

    if existing_lines and _parse_block_line_start(existing_lines[-1]) == new_start_key:
        existing_lines[-1] = new_line
    else:
        existing_lines.append(new_line)

    content = "\n".join(existing_lines) + "\n"
    tmp_path = week_file_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp_path, week_file_path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "C:\Users\Eva Ng\.claude\skills\synclinear\hooks" && python -m pytest test_check_unsynced.py::TestUpsertBlockLine -v`
Expected: PASS, all 4 tests.

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `cd "C:\Users\Eva Ng\.claude\skills\synclinear\hooks" && python -m pytest test_check_unsynced.py -v`
Expected: all previously-passing tests still PASS, plus these 4 new ones.

- [ ] **Step 6: Commit**

```bash
cd "C:\Users\Eva Ng\.claude\skills\synclinear"
git add hooks/check_unsynced.py hooks/test_check_unsynced.py
git commit -m "feat: add crash-safe upsert write for time-log block lines"
```

---

### Task 5: Wire into the Stop hook (stdin refactor + `_write_time_log`)

**Files:**
- Modify: `C:\Users\Eva Ng\.claude\skills\synclinear\hooks\check_unsynced.py`
- Test: `C:\Users\Eva Ng\.claude\skills\synclinear\hooks\test_check_unsynced.py`

**Interfaces:**
- Consumes: `load_timestamps`/`group_into_blocks` (Task 2), `_week_file_name` (Task 3), `_upsert_block_line` (Task 4), `config.get("timetable_dir")` (Task 1).
- Produces: `_write_time_log(repo_root: str, config: dict, transcript_path: str | None) -> None`, wired into `main()`. No return value participates in the `paragraphs` list — this is a silent side-effect, confirmed design.

**Critical implementation note:** `check_unsynced.py`'s current `_read_cwd_from_stdin()` reads `sys.stdin.read()` once and extracts only `cwd`, discarding the rest of the parsed JSON. **stdin can only be read once per process** — a second call to read it would get an empty string, since the stream is already consumed. This task MUST restructure stdin-reading into a single read that produces a dict, from which BOTH `cwd` and `transcript_path` are extracted — not add a second stdin-reading function alongside the first. No existing test calls `_read_cwd_from_stdin` directly (confirmed this session — all existing tests exercise the hook via subprocess through `_run_hook`), so this refactor is safe as long as the observable behavior (cwd extraction, falling back to `os.getcwd()`) doesn't change.

- [ ] **Step 1: Write the failing tests**

Add to `hooks/test_check_unsynced.py`:

```python
class TestAutoTimeLog(unittest.TestCase):
    def _write_transcript(self, path: str, timestamps: list[str]) -> None:
        with open(path, "w", encoding="utf-8") as f:
            for ts in timestamps:
                f.write(json.dumps({"timestamp": ts}) + "\n")

    def test_no_write_when_timetable_dir_not_configured(self):
        with tempfile.TemporaryDirectory() as repo_root:
            head = _init_repo_with_commit(repo_root)
            transcript_path = os.path.join(repo_root, "transcript.jsonl")
            self._write_transcript(transcript_path, ["2026-09-08T09:00:00.000Z"])
            save_config(repo_root, _base_config(head))  # no timetable_dir

            payload = json.dumps({"cwd": repo_root, "transcript_path": transcript_path})
            result = subprocess.run(
                [sys.executable, _SCRIPT], cwd=repo_root, input=payload,
                capture_output=True, text=True, timeout=15,
            )

            self.assertEqual(result.stdout.strip(), "")

    def test_writes_block_when_timetable_dir_configured(self):
        with tempfile.TemporaryDirectory() as repo_root:
            head = _init_repo_with_commit(repo_root)
            transcript_path = os.path.join(repo_root, "transcript.jsonl")
            self._write_transcript(transcript_path, [
                "2026-09-08T09:00:00.000Z",
                "2026-09-08T09:15:00.000Z",
            ])
            timetable_dir = os.path.join(repo_root, "timelogs")
            config = _base_config(head, timetable_dir=timetable_dir)
            save_config(repo_root, config)

            payload = json.dumps({"cwd": repo_root, "transcript_path": transcript_path})
            subprocess.run(
                [sys.executable, _SCRIPT], cwd=repo_root, input=payload,
                capture_output=True, text=True, timeout=15,
            )

            self.assertTrue(os.path.isdir(timetable_dir))
            files = os.listdir(timetable_dir)
            self.assertEqual(len(files), 1)
            with open(os.path.join(timetable_dir, files[0]), encoding="utf-8") as f:
                content = f.read()
            self.assertIn("->", content)

    def test_consecutive_runs_within_same_block_upsert_one_line(self):
        with tempfile.TemporaryDirectory() as repo_root:
            head = _init_repo_with_commit(repo_root)
            transcript_path = os.path.join(repo_root, "transcript.jsonl")
            timetable_dir = os.path.join(repo_root, "timelogs")
            config = _base_config(head, timetable_dir=timetable_dir)
            save_config(repo_root, config)

            self._write_transcript(transcript_path, ["2026-09-08T09:00:00.000Z"])
            payload = json.dumps({"cwd": repo_root, "transcript_path": transcript_path})
            subprocess.run([sys.executable, _SCRIPT], cwd=repo_root, input=payload, capture_output=True, text=True, timeout=15)

            self._write_transcript(transcript_path, [
                "2026-09-08T09:00:00.000Z",
                "2026-09-08T09:10:00.000Z",
            ])
            subprocess.run([sys.executable, _SCRIPT], cwd=repo_root, input=payload, capture_output=True, text=True, timeout=15)

            files = os.listdir(timetable_dir)
            with open(os.path.join(timetable_dir, files[0]), encoding="utf-8") as f:
                lines = f.read().splitlines()
            self.assertEqual(len(lines), 1)
            self.assertIn("09:10", lines[0])

    def test_stop_hook_still_reports_cwd_based_signals_after_refactor(self):
        # Regression guard: the stdin refactor for transcript_path must not
        # break cwd extraction, which every other signal in this hook depends on.
        with tempfile.TemporaryDirectory() as repo_root:
            head = _init_repo_with_commit(repo_root)
            save_config(repo_root, _base_config(head))
            with open(os.path.join(repo_root, "b.txt"), "w", encoding="utf-8") as f:
                f.write("second")
            _run_git(["git", "add", "b.txt"], repo_root)
            _run_git(["git", "commit", "-m", "second commit"], repo_root)

            output = _run_hook(repo_root)

            self.assertNotEqual(output, "")
            self.assertIn("second commit", output)
```

Update `_base_config` (defined earlier in this file, from the previous plan's Task 3) to accept `timetable_dir` as one of its `**overrides` — it already accepts `**overrides` and applies them via `config.update(overrides)`, so no change to `_base_config` itself is needed; these new tests just pass `timetable_dir=...` as a keyword argument, which already works with the existing helper.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "C:\Users\Eva Ng\.claude\skills\synclinear\hooks" && python -m pytest test_check_unsynced.py::TestAutoTimeLog -v`
Expected: FAIL — `_write_time_log` doesn't exist yet and isn't wired into `main()`, so no files get written.

- [ ] **Step 3: Refactor stdin reading and add `_write_time_log`**

Replace the existing `_read_cwd_from_stdin` function in `hooks/check_unsynced.py` with:

```python
def _read_stdin_payload() -> dict:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, ValueError):
        data = {}
    return data if isinstance(data, dict) else {}


def _cwd_from_payload(data: dict) -> str:
    cwd = data.get("cwd")
    if isinstance(cwd, str) and cwd:
        return cwd
    return os.getcwd()
```

Add the new import at the top of the file: `from time_blocks import group_into_blocks, load_timestamps` (added to the existing `sys.path.insert` block that already makes `lib/` importable — no new `sys.path` manipulation needed, just the new import line alongside `from config import ...`).

Add `_write_time_log`:

```python
def _write_time_log(repo_root: str, config: dict, transcript_path: str | None) -> None:
    timetable_dir = config.get("timetable_dir")
    if not timetable_dir or not transcript_path:
        return
    if not os.path.isfile(transcript_path):
        return
    try:
        times = load_timestamps(transcript_path)
        blocks = group_into_blocks(times, datetime.timedelta(minutes=20))
    except OSError:
        return
    if not blocks:
        return
    start_utc, end_utc = blocks[-1]
    local_tz = datetime.datetime.now().astimezone().tzinfo
    start_local = start_utc.astimezone(local_tz)
    end_local = end_utc.astimezone(local_tz)
    week_file = os.path.join(timetable_dir, _week_file_name(start_utc))
    try:
        os.makedirs(timetable_dir, exist_ok=True)
        _upsert_block_line(week_file, start_local, end_local)
    except OSError:
        return
```

Update `main()` — replace:

```python
        cwd = _read_cwd_from_stdin()
        repo_root = find_repo_root(cwd)
        if repo_root is None:
            return
        config = load_config(repo_root)
        if config is None:
            return
```

with:

```python
        stdin_data = _read_stdin_payload()
        cwd = _cwd_from_payload(stdin_data)
        repo_root = find_repo_root(cwd)
        if repo_root is None:
            return
        config = load_config(repo_root)
        if config is None:
            return

        _write_time_log(repo_root, config, stdin_data.get("transcript_path"))
```

(Placed right after `config` is confirmed non-`None`, before the `paragraphs = []` line — this write happens regardless of whether any signal paragraph ends up firing, since it's unconditional and independent of the reminder system.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "C:\Users\Eva Ng\.claude\skills\synclinear\hooks" && python -m pytest test_check_unsynced.py::TestAutoTimeLog -v`
Expected: PASS, all 4 tests.

- [ ] **Step 5: Run the full suite to confirm zero regressions**

Run: `cd "C:\Users\Eva Ng\.claude\skills\synclinear\hooks" && python -m pytest test_check_unsynced.py -v`
Expected: PASS, every test in the file — this is the task most likely to break something subtle (the stdin-reading refactor touches code every other signal depends on), so treat any failure here as blocking, not incidental.

- [ ] **Step 6: Commit**

```bash
cd "C:\Users\Eva Ng\.claude\skills\synclinear"
git add hooks/check_unsynced.py hooks/test_check_unsynced.py
git commit -m "feat: wire auto time-log writing into the Stop hook"
```

---

### Task 6: SKILL.md documentation

**Files:**
- Modify: `C:\Users\Eva Ng\.claude\skills\synclinear\SKILL.md`

**Interfaces:**
- Consumes: nothing machine-readable.
- Produces: a new section explaining this capability's deliberate exception to the review-gate principle, explicit enough that nobody "fixes" it into a proposal-based flow later. No tests apply.

- [ ] **Step 1: Update the frontmatter description**

Add a mention of this fifth mechanism to SKILL.md's `description` field (read the current frontmatter first — it currently lists flows 3a/3b/3c and workflow-stage gaps as four mechanisms; append a fifth clause covering auto time-log, e.g. "...and (auto time-log) automatically records work blocks into weekly files with no review gate, since a timestamp is a fact, not a decision.").

- [ ] **Step 2: Add a new section**

Insert after the existing "Workflow-stage gap directives" section:

```markdown
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
```

- [ ] **Step 3: Commit**

```bash
cd "C:\Users\Eva Ng\.claude\skills\synclinear"
git add SKILL.md
git commit -m "docs: document auto time-log's deliberate no-review-gate design"
```

---

### Task 7: Full-suite verification

**Files:** none modified.

**Interfaces:** none — verification only.

- [ ] **Step 1: Run every test file in the repo**

```bash
cd "C:\Users\Eva Ng\.claude\skills\synclinear\lib" && python -m pytest test_config.py test_git_check.py test_openspec_check.py test_time_blocks.py -v
cd "C:\Users\Eva Ng\.claude\skills\synclinear\hooks" && python -m pytest test_check_unsynced.py -v
```

Expected: every test passes, zero regressions in flows 3a/3b/3c/gaps.

- [ ] **Step 2: Manually verify against a real Claude Code session transcript**

Point the hook at a **real** transcript file (not a synthetic one) — e.g.
this very session's own transcript, if accessible, or any other real
`.jsonl` transcript on the machine — with a scratch repo's config
pointing `timetable_dir` at a throwaway directory. Run the hook directly
and confirm the computed block matches what a human would expect from
skimming the transcript's actual timestamps. Then simulate a
Thursday-to-Friday boundary case by hand-constructing a small transcript
with timestamps straddling a known Friday 00:00 local boundary, and
confirm the file lands where Decision 3 says it should (filed entirely
under the week the block started in).

- [ ] **Step 3: No commit** (verification only)

---

## Post-plan note for whoever executes this

This plan's Task 5 stdin refactor is the highest-risk task in this
plan — it touches the one piece of code every other signal in the hook
(3a/3b/3c, gaps 1/2/3) depends on for locating the repo root. Do not
skip Step 5's full-suite run for that task; treat any regression there
as blocking, not a pre-existing flake.
