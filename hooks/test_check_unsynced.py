from __future__ import annotations

import json
import os
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
                {"linear_team": "Studio", "linear_project": "P", "last_synced_commit": head},
            )

            output = _run_hook(repo_root)

            self.assertEqual(output, "")

    def test_emits_reminder_json_when_new_commits_exist(self):
        with tempfile.TemporaryDirectory() as repo_root:
            head = _init_repo_with_commit(repo_root)
            save_config(
                repo_root,
                {"linear_team": "Studio", "linear_project": "P", "last_synced_commit": head},
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


if __name__ == "__main__":
    unittest.main()
