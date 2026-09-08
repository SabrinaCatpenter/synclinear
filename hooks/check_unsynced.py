"""Claude Code Stop hook. Runs after every turn, in whatever directory
the session is in. Checks TWO independent signals against a repo's
.claude/synclinear.json: (A) unsynced git commits, and (B) OpenSpec
state — a proposed-but-not-yet-ticketed change, and/or an archived
change since the last client-artifact check. Each signal that fires
gets its own paragraph in the reminder text; they are never merged
into one sentence, since a repo can be in any combination of these
states independently. Emits the exact JSON shape Claude Code requires
to inject text into the next turn's context
(hookSpecificOutput.additionalContext) — plain stdout text does
nothing. Any case with nothing to report: print nothing, exit 0. Never
raises — a bug here must not break every Stop event in every project.
"""
from __future__ import annotations

import datetime
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
from config import load_config  # noqa: E402
from git_check import find_repo_root, unsynced_commits  # noqa: E402
from openspec_check import archive_dir_mtime, list_changes  # noqa: E402

# Computed from this script's own location, not hardcoded to any one
# machine's home directory — SKILL.md always lives one level up from
# hooks/, regardless of where this skill folder is installed.
_SKILL_MD_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "SKILL.md")
)


def _read_cwd_from_stdin() -> str:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, ValueError):
        data = {}
    cwd = data.get("cwd")
    if isinstance(cwd, str) and cwd:
        return cwd
    return os.getcwd()


def _propose_without_ticket_paragraph(repo_root: str, config: dict, skill_md_path: str) -> str | None:
    changes = list_changes(repo_root)
    if not changes:
        return None
    known = set(config["known_openspec_changes"])
    ready_unticketed = []
    for entry in changes:
        name = entry.get("name")
        if not name or name in known:
            continue
        # `openspec list --json` (verified against the real CLI, v1.6.0 on
        # Windows — the brief's assumed `entry["artifacts"]` shape does not
        # exist) reports a per-change `status` field that starts at
        # "no-tasks" (no tasks.md written yet) and moves to "in-progress"
        # the moment tasks.md exists at all — even with every checkbox still
        # unchecked — and only reaches "complete" once every checkbox is
        # ticked. Signal 3b fires on "a proposal exists but has no Linear
        # ticket yet," which is the tasks.md-exists moment (propose done),
        # not the implementation-finished moment — so any status other than
        # "no-tasks" counts as propose-ready here.
        status = entry.get("status")
        if status and status != "no-tasks":
            ready_unticketed.append(name)
    if not ready_unticketed:
        return None
    names = ", ".join(ready_unticketed)
    return (
        f"synclinear: OpenSpec change(s) [{names}] in {repo_root} have a "
        f"completed proposal but no Linear ticket yet. Read {skill_md_path} "
        f"(flow 3b) and follow it."
    )


def _artifact_reminder_paragraph(repo_root: str, config: dict, skill_md_path: str) -> str | None:
    mtime = archive_dir_mtime(repo_root)
    if mtime is None:
        return None
    try:
        last_check = datetime.datetime.fromisoformat(config["last_artifact_check_at"])
    except ValueError:
        return None
    archived_at = datetime.datetime.fromtimestamp(mtime, tz=datetime.timezone.utc)
    if last_check.tzinfo is None:
        last_check = last_check.replace(tzinfo=datetime.timezone.utc)
    if archived_at <= last_check:
        return None
    return (
        f"synclinear: {repo_root}'s OpenSpec archive has changed since the "
        f"last artifact check. A client-facing artifact may be due. Read "
        f"{skill_md_path} (flow 3c) and follow it."
    )


def _commits_paragraph(repo_root: str, config: dict, commits: list[str], skill_md_path: str) -> str:
    project = config["linear_project"]
    lines = "\n".join(f"  - {c}" for c in commits)
    return (
        f"synclinear: {len(commits)} new commit(s) in {repo_root} are not yet "
        f"synced to Linear project \"{project}\":\n{lines}\n"
        f"Read {skill_md_path} and follow it."
    )


def build_reminder(paragraphs: list[str]) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": "\n\n".join(paragraphs),
        }
    }


def main() -> None:
    try:
        cwd = _read_cwd_from_stdin()
        repo_root = find_repo_root(cwd)
        if repo_root is None:
            return
        config = load_config(repo_root)
        if config is None:
            return

        paragraphs = []

        commits = unsynced_commits(repo_root, config["last_synced_commit"])
        if commits:
            paragraphs.append(_commits_paragraph(repo_root, config, commits, _SKILL_MD_PATH))

        propose_paragraph = _propose_without_ticket_paragraph(repo_root, config, _SKILL_MD_PATH)
        if propose_paragraph:
            paragraphs.append(propose_paragraph)

        artifact_paragraph = _artifact_reminder_paragraph(repo_root, config, _SKILL_MD_PATH)
        if artifact_paragraph:
            paragraphs.append(artifact_paragraph)

        if not paragraphs:
            return
        print(json.dumps(build_reminder(paragraphs)))
    except Exception:  # noqa: BLE001 — a Stop hook must never crash the session
        return


if __name__ == "__main__":
    main()
