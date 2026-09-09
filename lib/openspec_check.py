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


def archive_dir_last_commit_at(repo_root: str) -> str | None:
    """ISO 8601 timestamp (with offset) of the most recent commit that
    touched openspec/changes/archive, or None when there's nothing worth
    reporting: the directory doesn't exist, it's currently empty (nothing
    has actually been archived yet — not worth interrupting Eva over),
    or git has no history for it (no repo, or the archive predates any
    commit).

    Deliberately git-based, not filesystem mtime: a directory's mtime
    changes on operations with no connection to a real archive event —
    `openspec init` creating the (empty) directory, a fresh clone, or
    simply touching the directory — so comparing it against
    last_artifact_check_at produced false positives with no real change
    behind them.
    """
    archive_dir = os.path.join(repo_root, "openspec", "changes", "archive")
    if not os.path.isdir(archive_dir):
        return None
    if not os.listdir(archive_dir):
        return None
    rel_path = os.path.relpath(archive_dir, repo_root)
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%cI", "--", rel_path],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    output = result.stdout.strip()
    return output or None
