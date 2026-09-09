"""Pure git-plumbing: locate a repo root, and list commits newer than a
known SHA. No Linear, no config — Task 3's hook script composes this with
config.py. Every git failure here (unknown SHA, not a repo, git not on
PATH) degrades to "nothing to report" rather than raising, because the
caller is a Stop hook that must never crash a session over bookkeeping.
"""
from __future__ import annotations

import os
import subprocess


def find_repo_root(start_dir: str) -> str | None:
    current = os.path.abspath(start_dir)
    while True:
        if os.path.isdir(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:  # reached filesystem root
            return None
        current = parent


def current_head(repo_root: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
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


def unsynced_commits(repo_root: str, last_synced_commit: str) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", f"{last_synced_commit}..HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.SubprocessError, OSError):
        return []
    if result.returncode != 0:
        # unknown SHA, detached weirdness, etc. — same as "nothing new"
        return []
    lines = result.stdout.strip().splitlines()
    return [line for line in lines if line]
