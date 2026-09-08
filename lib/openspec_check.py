"""Pure OpenSpec-plumbing: query change list and archive state via the
real `openspec` CLI. No Linear, no config — hooks/check_unsynced.py
composes this with config.py, same pattern as git_check.py. Every
failure (CLI not installed, no openspec/ directory, bad JSON) degrades
to None rather than raising, because the caller is a Stop hook that
must never crash a session over bookkeeping.
"""
from __future__ import annotations

import json
import os
import subprocess


def list_changes(repo_root: str) -> list[dict] | None:
    if not os.path.isdir(os.path.join(repo_root, "openspec")):
        return None
    try:
        result = subprocess.run(
            "openspec list --json",
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=15,
            shell=True,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    changes = parsed.get("changes")
    if not isinstance(changes, list):
        return None
    return changes


def archive_dir_mtime(repo_root: str) -> float | None:
    archive_dir = os.path.join(repo_root, "openspec", "changes", "archive")
    if not os.path.isdir(archive_dir):
        return None
    try:
        return os.path.getmtime(archive_dir)
    except OSError:
        return None
