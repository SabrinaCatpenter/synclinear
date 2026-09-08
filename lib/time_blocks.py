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
