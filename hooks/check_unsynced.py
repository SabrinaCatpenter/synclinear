"""Claude Code Stop hook. Runs after every turn, in whatever directory
the session is in. Checks: is this a git repo, is there a
.claude/synclinear.json here, and are there commits newer than its
last_synced_commit? If all three, emits the exact JSON shape Claude Code
requires to inject text into the next turn's context
(hookSpecificOutput.additionalContext) — plain stdout text does nothing.
Any other case: print nothing, exit 0. Never raises — a bug here must not
break every Stop event in every project.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
from config import load_config  # noqa: E402
from git_check import find_repo_root, unsynced_commits  # noqa: E402


# Computed from this script's own location, not hardcoded to any one
# machine's home directory — SKILL.md always lives one level up from
# hooks/, regardless of where this skill folder is installed.
_SKILL_MD_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "SKILL.md")
)


def build_reminder(repo_root: str, config: dict, commits: list[str], skill_md_path: str) -> dict:
    project = config["linear_project"]
    lines = "\n".join(f"  - {c}" for c in commits)
    context = (
        f"synclinear: {len(commits)} new commit(s) in {repo_root} are not yet "
        f"synced to Linear project \"{project}\":\n{lines}\n"
        f"Read {skill_md_path} and follow it."
    )
    return {
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": context,
        }
    }


def main() -> None:
    try:
        repo_root = find_repo_root(os.getcwd())
        if repo_root is None:
            return
        config = load_config(repo_root)
        if config is None:
            return
        commits = unsynced_commits(repo_root, config["last_synced_commit"])
        if not commits:
            return
        print(json.dumps(build_reminder(repo_root, config, commits, _SKILL_MD_PATH)))
    except Exception:  # noqa: BLE001 — a Stop hook must never crash the session
        return


if __name__ == "__main__":
    main()
