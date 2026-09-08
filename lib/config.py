"""Reads/writes .claude/synclinear.json in a target repo — the per-project
sync bookkeeping (which Linear team/project this repo's commits sync into,
and how far the sync has gotten). Never raises: a missing or malformed
config is treated as "not opted in," not an error, since the Stop hook
that calls this must never crash on an unrelated repo.
"""
from __future__ import annotations

import json
import os

_REQUIRED_STRING_KEYS = (
    "linear_team",
    "linear_project",
    "timetable_path",
    "last_synced_commit",
    "last_artifact_check_at",
)
_REQUIRED_LIST_OF_STRING_KEYS = ("known_openspec_changes", "advanced_workflow_gaps")
_OPTIONAL_STRING_KEYS = ("timetable_dir",)


def _config_path(repo_root: str) -> str:
    return os.path.join(repo_root, ".claude", "synclinear.json")


def load_config(repo_root: str) -> dict | None:
    path = _config_path(repo_root)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            config = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(config, dict):
        return None
    if not all(isinstance(config.get(key), str) for key in _REQUIRED_STRING_KEYS):
        return None
    for key in _REQUIRED_LIST_OF_STRING_KEYS:
        value = config.get(key)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            return None
    for key in _OPTIONAL_STRING_KEYS:
        value = config.get(key)
        if value is not None and not isinstance(value, str):
            return None
    return config


def save_config(repo_root: str, config: dict) -> None:
    claude_dir = os.path.join(repo_root, ".claude")
    os.makedirs(claude_dir, exist_ok=True)
    with open(_config_path(repo_root), "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
