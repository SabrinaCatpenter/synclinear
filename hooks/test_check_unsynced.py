from __future__ import annotations

import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
from config import save_config  # noqa: E402

_SCRIPT = os.path.join(os.path.dirname(__file__), "check_unsynced.py")


def _run_git(cmd: list[str], cwd: str) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)


def _init_repo_with_commit(repo_root: str) -> str:
    _run_git(["git", "init"], repo_root)
    _run_git(["git", "config", "user.email", "test@example.com"], repo_root)
    _run_git(["git", "config", "user.name", "Test"], repo_root)
    with open(os.path.join(repo_root, "a.txt"), "w", encoding="utf-8") as f:
        f.write("first")
    _run_git(["git", "add", "a.txt"], repo_root)
    _run_git(["git", "commit", "-m", "first commit"], repo_root)
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _run_hook(cwd: str) -> str:
    result = subprocess.run(
        [sys.executable, _SCRIPT],
        cwd=cwd,
        input="{}",
        capture_output=True,
        text=True,
        timeout=15,
    )
    return result.stdout.strip()


class TestCheckUnsyncedHook(unittest.TestCase):
    def test_silent_when_not_a_git_repo(self):
        with tempfile.TemporaryDirectory() as not_a_repo:
            output = _run_hook(not_a_repo)
            self.assertEqual(output, "")

    def test_silent_when_no_config(self):
        with tempfile.TemporaryDirectory() as repo_root:
            _init_repo_with_commit(repo_root)
            output = _run_hook(repo_root)
            self.assertEqual(output, "")

    def test_silent_when_nothing_new(self):
        with tempfile.TemporaryDirectory() as repo_root:
            head = _init_repo_with_commit(repo_root)
            save_config(
                repo_root,
                {
                    "linear_team": "Studio",
                    "linear_project": "P",
                    "timetable_path": "C:/timetable.txt",
                    "last_synced_commit": head,
                    "known_openspec_changes": [],
                    "last_artifact_check_at": "2026-09-08T00:00:00+00:00",
                },
            )

            output = _run_hook(repo_root)

            self.assertEqual(output, "")

    def test_emits_reminder_json_when_new_commits_exist(self):
        with tempfile.TemporaryDirectory() as repo_root:
            head = _init_repo_with_commit(repo_root)
            save_config(
                repo_root,
                {
                    "linear_team": "Studio",
                    "linear_project": "P",
                    "timetable_path": "C:/timetable.txt",
                    "last_synced_commit": head,
                    "known_openspec_changes": [],
                    "last_artifact_check_at": "2026-09-08T00:00:00+00:00",
                },
            )
            with open(os.path.join(repo_root, "b.txt"), "w", encoding="utf-8") as f:
                f.write("second")
            _run_git(["git", "add", "b.txt"], repo_root)
            _run_git(["git", "commit", "-m", "second commit"], repo_root)

            output = _run_hook(repo_root)

            self.assertNotEqual(output, "")
            parsed = json.loads(output)
            self.assertEqual(
                parsed["hookSpecificOutput"]["hookEventName"], "Stop"
            )
            self.assertIn("second commit", parsed["hookSpecificOutput"]["additionalContext"])
            self.assertIn("P", parsed["hookSpecificOutput"]["additionalContext"])


class TestCheckUnsyncedHookOpenSpecSignal(unittest.TestCase):
    @unittest.skipUnless(shutil.which("openspec"), "openspec CLI not installed")
    def test_reminds_about_propose_without_ticket(self):
        with tempfile.TemporaryDirectory() as repo_root:
            head = _init_repo_with_commit(repo_root)
            subprocess.run(
                "openspec init --tools claude .", cwd=repo_root, check=True, capture_output=True, shell=True
            )
            subprocess.run(
                'openspec new change "add-widget"', cwd=repo_root, check=True, capture_output=True, shell=True
            )
            # Manually mark the tasks artifact done the way openspec-propose would,
            # by writing the file its own template expects at the resolved path.
            tasks_dir = os.path.join(repo_root, "openspec", "changes", "add-widget")
            with open(os.path.join(tasks_dir, "tasks.md"), "w", encoding="utf-8") as f:
                f.write("## 1. Implement widget\n- [ ] Build it\n")
            save_config(
                repo_root,
                {
                    "linear_team": "Studio",
                    "linear_project": "P",
                    "timetable_path": "C:/timetable.txt",
                    "last_synced_commit": head,
                    "known_openspec_changes": [],
                    "last_artifact_check_at": "2026-09-08T00:00:00+00:00",
                },
            )

            output = _run_hook(repo_root)

            self.assertNotEqual(output, "")
            parsed = json.loads(output)
            context = parsed["hookSpecificOutput"]["additionalContext"]
            self.assertIn("add-widget", context)

    def test_silent_on_openspec_signal_when_no_openspec_dir(self):
        with tempfile.TemporaryDirectory() as repo_root:
            head = _init_repo_with_commit(repo_root)
            save_config(
                repo_root,
                {
                    "linear_team": "Studio",
                    "linear_project": "P",
                    "timetable_path": "C:/timetable.txt",
                    "last_synced_commit": head,
                    "known_openspec_changes": [],
                    "last_artifact_check_at": "2026-09-08T00:00:00+00:00",
                },
            )

            output = _run_hook(repo_root)

            self.assertEqual(output, "")

    def test_reminds_about_artifact_when_archive_newer_than_last_check(self):
        with tempfile.TemporaryDirectory() as repo_root:
            head = _init_repo_with_commit(repo_root)
            archive_dir = os.path.join(repo_root, "openspec", "changes", "archive")
            os.makedirs(archive_dir)
            save_config(
                repo_root,
                {
                    "linear_team": "Studio",
                    "linear_project": "P",
                    "timetable_path": "C:/timetable.txt",
                    "last_synced_commit": head,
                    "known_openspec_changes": [],
                    "last_artifact_check_at": "2020-01-01T00:00:00+00:00",
                },
            )

            output = _run_hook(repo_root)

            self.assertNotEqual(output, "")
            parsed = json.loads(output)
            context = parsed["hookSpecificOutput"]["additionalContext"]
            self.assertIn("artifact", context.lower())

    def test_silent_on_artifact_signal_when_archive_older_than_last_check(self):
        with tempfile.TemporaryDirectory() as repo_root:
            head = _init_repo_with_commit(repo_root)
            archive_dir = os.path.join(repo_root, "openspec", "changes", "archive")
            os.makedirs(archive_dir)
            future = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)).isoformat()
            save_config(
                repo_root,
                {
                    "linear_team": "Studio",
                    "linear_project": "P",
                    "timetable_path": "C:/timetable.txt",
                    "last_synced_commit": head,
                    "known_openspec_changes": [],
                    "last_artifact_check_at": future,
                },
            )

            output = _run_hook(repo_root)

            self.assertEqual(output, "")

    def test_git_and_openspec_signals_produce_separate_paragraphs(self):
        with tempfile.TemporaryDirectory() as repo_root:
            head = _init_repo_with_commit(repo_root)
            archive_dir = os.path.join(repo_root, "openspec", "changes", "archive")
            os.makedirs(archive_dir)
            save_config(
                repo_root,
                {
                    "linear_team": "Studio",
                    "linear_project": "P",
                    "timetable_path": "C:/timetable.txt",
                    "last_synced_commit": head,
                    "known_openspec_changes": [],
                    "last_artifact_check_at": "2020-01-01T00:00:00+00:00",
                },
            )
            with open(os.path.join(repo_root, "b.txt"), "w", encoding="utf-8") as f:
                f.write("second")
            _run_git(["git", "add", "b.txt"], repo_root)
            _run_git(["git", "commit", "-m", "second commit"], repo_root)

            output = _run_hook(repo_root)

            parsed = json.loads(output)
            context = parsed["hookSpecificOutput"]["additionalContext"]
            paragraphs = [p for p in context.split("\n\n") if p.strip()]
            self.assertEqual(len(paragraphs), 2)
            self.assertTrue(any("second commit" in p for p in paragraphs))
            self.assertTrue(any("artifact" in p.lower() for p in paragraphs))


if __name__ == "__main__":
    unittest.main()
