"""Pure OpenSpec-plumbing: query change list and archive state via the
real `openspec` CLI. No Linear, no config — hooks/check_unsynced.py
composes this with config.py, same pattern as git_check.py. Every
failure (CLI not installed, no openspec/ directory, bad JSON) degrades
to None rather than raising, because the caller is a Stop hook that
must never crash a session over bookkeeping.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest

from openspec_check import archive_dir_last_commit_at, list_changes


def _run(cmd: list[str], cwd: str) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, shell=True)


class TestListChanges(unittest.TestCase):
    def test_none_when_no_openspec_directory(self):
        with tempfile.TemporaryDirectory() as repo_root:
            self.assertIsNone(list_changes(repo_root))

    @unittest.skipUnless(shutil.which("openspec"), "openspec CLI not installed")
    def test_empty_list_when_openspec_initialized_but_no_changes(self):
        with tempfile.TemporaryDirectory() as repo_root:
            _run(["openspec", "init", "--tools", "claude", "."], repo_root)

            result = list_changes(repo_root)

            self.assertEqual(result, [])

    @unittest.skipUnless(shutil.which("openspec"), "openspec CLI not installed")
    def test_lists_a_real_change(self):
        with tempfile.TemporaryDirectory() as repo_root:
            _run(["openspec", "init", "--tools", "claude", "."], repo_root)
            _run(["openspec", "new", "change", "add-widget"], repo_root)

            result = list_changes(repo_root)

            self.assertIsInstance(result, list)
            self.assertTrue(any(entry.get("name") == "add-widget" for entry in result))


def _init_git_repo(repo_root: str) -> None:
    _run(["git", "init"], repo_root)
    _run(["git", "config", "user.email", "test@example.com"], repo_root)
    _run(["git", "config", "user.name", "Test"], repo_root)


class TestArchiveDirLastCommitAt(unittest.TestCase):
    def test_none_when_no_archive_directory(self):
        with tempfile.TemporaryDirectory() as repo_root:
            self.assertIsNone(archive_dir_last_commit_at(repo_root))

    def test_none_when_archive_directory_exists_but_is_empty(self):
        # openspec init (or a manual mkdir) creates this directory with
        # nothing archived in it yet — must not be mistaken for a real
        # archive event just because the directory exists.
        with tempfile.TemporaryDirectory() as repo_root:
            archive_dir = os.path.join(repo_root, "openspec", "changes", "archive")
            os.makedirs(archive_dir)

            self.assertIsNone(archive_dir_last_commit_at(repo_root))

    def test_none_when_directory_has_content_but_no_git_history(self):
        # not a git repo at all — no commit history to read a timestamp from
        with tempfile.TemporaryDirectory() as repo_root:
            archive_dir = os.path.join(repo_root, "openspec", "changes", "archive", "add-widget")
            os.makedirs(archive_dir)
            with open(os.path.join(archive_dir, "proposal.md"), "w", encoding="utf-8") as f:
                f.write("# Add widget\n")

            self.assertIsNone(archive_dir_last_commit_at(repo_root))

    def test_returns_commit_timestamp_when_something_is_actually_archived(self):
        with tempfile.TemporaryDirectory() as repo_root:
            _init_git_repo(repo_root)
            archive_dir = os.path.join(repo_root, "openspec", "changes", "archive", "add-widget")
            os.makedirs(archive_dir)
            proposal_path = os.path.join(archive_dir, "proposal.md")
            with open(proposal_path, "w", encoding="utf-8") as f:
                f.write("# Add widget\n")
            _run(["git", "add", "."], repo_root)
            _run(["git", "commit", "-m", "Archive add-widget"], repo_root)

            result = archive_dir_last_commit_at(repo_root)

            self.assertIsNotNone(result)
            import datetime as _dt

            self.assertIsInstance(_dt.datetime.fromisoformat(result), _dt.datetime)

    def test_touching_the_directory_with_no_new_commit_does_not_change_the_result(self):
        # the whole point of using git history instead of mtime: merely
        # touching the directory (e.g. a later `openspec` command
        # traversing it) must not look like a new archive event
        with tempfile.TemporaryDirectory() as repo_root:
            _init_git_repo(repo_root)
            archive_dir = os.path.join(repo_root, "openspec", "changes", "archive", "add-widget")
            os.makedirs(archive_dir)
            proposal_path = os.path.join(archive_dir, "proposal.md")
            with open(proposal_path, "w", encoding="utf-8") as f:
                f.write("# Add widget\n")
            _run(["git", "add", "."], repo_root)
            _run(["git", "commit", "-m", "Archive add-widget"], repo_root)
            first = archive_dir_last_commit_at(repo_root)

            os.utime(archive_dir, None)  # bump the directory's own mtime, no git change

            second = archive_dir_last_commit_at(repo_root)

            self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
