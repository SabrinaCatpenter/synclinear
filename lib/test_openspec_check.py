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

from openspec_check import archive_dir_mtime, list_changes


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


class TestArchiveDirMtime(unittest.TestCase):
    def test_none_when_no_archive_directory(self):
        with tempfile.TemporaryDirectory() as repo_root:
            self.assertIsNone(archive_dir_mtime(repo_root))

    def test_returns_mtime_when_archive_directory_exists(self):
        with tempfile.TemporaryDirectory() as repo_root:
            archive_dir = os.path.join(repo_root, "openspec", "changes", "archive")
            os.makedirs(archive_dir)

            result = archive_dir_mtime(repo_root)

            self.assertIsNotNone(result)
            self.assertEqual(result, os.path.getmtime(archive_dir))


if __name__ == "__main__":
    unittest.main()
