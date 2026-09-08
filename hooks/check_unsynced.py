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
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
from config import load_config, save_config  # noqa: E402
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


def _file_timestamp(repo_root: str, path: str) -> float | None:
    if not os.path.isfile(path):
        return None
    rel_path = os.path.relpath(path, repo_root)
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ct", "--", rel_path],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.SubprocessError, OSError):
        result = None
    if result is not None and result.returncode == 0 and result.stdout.strip():
        try:
            return float(result.stdout.strip())
        except ValueError:
            pass
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def _first_commit_timestamp(repo_root: str, path: str) -> float | None:
    if not os.path.isfile(path):
        return None
    rel_path = os.path.relpath(path, repo_root)
    try:
        result = subprocess.run(
            ["git", "log", "--follow", "--diff-filter=A", "--format=%ct", "--", rel_path],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.SubprocessError, OSError):
        result = None
    if result is not None and result.returncode == 0 and result.stdout.strip():
        lines = result.stdout.strip().splitlines()
        try:
            # git log 默认从新到旧排列；--diff-filter=A 只保留"被新增"的那些提交，
            # 正常情况下一个文件只会被"新增"一次，取最后一行（最早的一条）保险起见
            return float(lines[-1])
        except ValueError:
            pass
    # 还没提交（untracked）的 tasks.md，退回用文件系统 mtime——这个文件既然还没
    # commit，就不可能是"被 clone 污染 mtime"的那种情况，mtime 是可信的。
    #
    # 已知的边界（不修，只记录）：这个 fallback 只解决了"clone 污染 mtime"这
    # 一种风险，没有解决另一种同源风险——如果 Eva 迟迟不 commit tasks.md、只是
    # 反复本地编辑（比如先写设计文档但 tasks.md 一直没提交，之后又回来改
    # tasks.md），mtime 会跟着每次编辑往后跳，这正是本函数存在的原因（gap1 时
    # 间戳被无关编辑刷新）在"未提交"这半程又重新出现了一次，只是触发窗口从
    # "整个 change 生命周期"收窄到了"tasks.md 首次 commit 之前"。日常 TDD 流
    # 程通常会较快提交 tasks.md，这个窗口很短，所以留作已知限制而非现在修——
    # 但如果之后发现这个场景真的造成困扰，说明这个假设不成立，需要重新考虑。
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def _week_file_name(start_utc: datetime.datetime) -> str:
    local_date = start_utc.astimezone().date()
    # Friday = weekday() 4 (Monday=0..Sunday=6). Days since the most
    # recent Friday (0 if today IS Friday): this pins Mon-Thu to the
    # PRECEDING Friday's week, and Fri-Sun to the week that just started.
    days_since_friday = (local_date.weekday() - 4) % 7
    week_start = local_date - datetime.timedelta(days=days_since_friday)
    week_end = week_start + datetime.timedelta(days=6)
    return f"{week_start.isoformat()}_{week_end.isoformat()}.txt"


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


def _newest_timestamp_under(repo_root: str, dir_path: str, exclude_dir: str | None = None) -> float | None:
    if not os.path.isdir(dir_path):
        return None
    newest = None
    for root, dirs, files in os.walk(dir_path):
        if exclude_dir and os.path.commonpath([root, exclude_dir]) == exclude_dir:
            dirs[:] = []
            continue
        for filename in files:
            ts = _file_timestamp(repo_root, os.path.join(root, filename))
            if ts is not None and (newest is None or ts > newest):
                newest = ts
    return newest


def _gap1_paragraph(repo_root: str, config: dict) -> tuple[str, list[str]] | None:
    changes = list_changes(repo_root)
    if not changes:
        return None
    known = set(config["advanced_workflow_gaps"])
    docs_dir = os.path.join(repo_root, "docs")
    docs_latest = _newest_timestamp_under(repo_root, docs_dir)
    stalled = []
    new_signatures = []
    for entry in changes:
        name = entry.get("name")
        status = entry.get("status")
        if not name or not status or status == "no-tasks":
            continue
        signature = f"{name}:gap1"
        if signature in known:
            continue
        tasks_path = os.path.join(repo_root, "openspec", "changes", name, "tasks.md")
        change_ts = _first_commit_timestamp(repo_root, tasks_path)
        if change_ts is None:
            continue
        if docs_latest is None or docs_latest < change_ts:
            stalled.append(name)
            new_signatures.append(signature)
    if not stalled:
        return None
    names = ", ".join(stalled)
    text = (
        f"synclinear: OpenSpec change(s) [{names}] in {repo_root} have a "
        f"complete proposal but no design doc under docs/ yet. Begin the "
        f"brainstorm/grill stage now: invoke superpowers:brainstorming, "
        f"per the 7-step cycle."
    )
    return text, new_signatures


def _gap2_paragraph(repo_root: str, config: dict) -> tuple[str, list[str]] | None:
    signature = "docs:gap2"
    if signature in set(config["advanced_workflow_gaps"]):
        return None
    docs_dir = os.path.join(repo_root, "docs")
    plans_dir = os.path.join(repo_root, "docs", "superpowers", "plans")
    docs_latest = _newest_timestamp_under(repo_root, docs_dir, exclude_dir=plans_dir)
    if docs_latest is None:
        return None
    plans_latest = _newest_timestamp_under(repo_root, plans_dir)
    if plans_latest is not None and plans_latest >= docs_latest:
        return None
    text = (
        f"synclinear: {repo_root}'s docs/ has a design doc newer than "
        f"anything in docs/superpowers/plans/. Begin the writing-plans "
        f"stage now: invoke superpowers:writing-plans, per the 7-step "
        f"cycle."
    )
    return text, [signature]


def _gap3_paragraph(repo_root: str, config: dict) -> tuple[str, list[str]] | None:
    changes = list_changes(repo_root)
    if not changes:
        return None
    known = set(config["advanced_workflow_gaps"])
    complete = []
    new_signatures = []
    for entry in changes:
        name = entry.get("name")
        status = entry.get("status")
        if not name or status != "complete":
            continue
        signature = f"{name}:gap3"
        if signature in known:
            continue
        complete.append(name)
        new_signatures.append(signature)
    if not complete:
        return None
    names = ", ".join(complete)
    text = (
        f"synclinear: OpenSpec change(s) [{names}] in {repo_root} have "
        f"every task checked off. Present the completed work to Eva for "
        f"review now, and archive the change (openspec archive) once she "
        f"approves — check first whether that review already happened "
        f"earlier in this conversation, and skip straight to asking about "
        f"archiving if so."
    )
    return text, new_signatures


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

        new_signatures = []
        for gap_fn in (_gap1_paragraph, _gap2_paragraph, _gap3_paragraph):
            result = gap_fn(repo_root, config)
            if result:
                text, signatures = result
                paragraphs.append(text)
                new_signatures.extend(signatures)

        if new_signatures:
            config["advanced_workflow_gaps"] = config["advanced_workflow_gaps"] + new_signatures
            save_config(repo_root, config)

        if not paragraphs:
            return
        print(json.dumps(build_reminder(paragraphs)))
    except Exception:  # noqa: BLE001 — a Stop hook must never crash the session
        return


if __name__ == "__main__":
    main()
