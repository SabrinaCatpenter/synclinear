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
