from __future__ import annotations

import os
import subprocess
import tempfile
import unittest

from git_check import current_head, find_repo_root, unsynced_commits


def _run(cmd: list[str], cwd: str) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)


def _init_repo(repo_root: str) -> None:
    _run(["git", "init"], repo_root)
    _run(["git", "config", "user.email", "test@example.com"], repo_root)
    _run(["git", "config", "user.name", "Test"], repo_root)


def _commit(repo_root: str, filename: str, message: str) -> str:
    with open(os.path.join(repo_root, filename), "w", encoding="utf-8") as f:
        f.write(message)
    _run(["git", "add", filename], repo_root)
    _run(["git", "commit", "-m", message], repo_root)
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


class TestFindRepoRoot(unittest.TestCase):
    def test_finds_root_from_root_itself(self):
        with tempfile.TemporaryDirectory() as repo_root:
            _init_repo(repo_root)
            found = find_repo_root(repo_root)
            self.assertEqual(os.path.normcase(found), os.path.normcase(repo_root))

    def test_finds_root_from_nested_subdir(self):
        with tempfile.TemporaryDirectory() as repo_root:
            _init_repo(repo_root)
            nested = os.path.join(repo_root, "a", "b", "c")
            os.makedirs(nested)

            found = find_repo_root(nested)

            self.assertEqual(os.path.normcase(found), os.path.normcase(repo_root))

    def test_returns_none_outside_any_repo(self):
        with tempfile.TemporaryDirectory() as not_a_repo:
            self.assertIsNone(find_repo_root(not_a_repo))


class TestUnsyncedCommits(unittest.TestCase):
    def test_empty_when_last_synced_is_head(self):
        with tempfile.TemporaryDirectory() as repo_root:
            _init_repo(repo_root)
            head = _commit(repo_root, "a.txt", "first commit")

            result = unsynced_commits(repo_root, head)

            self.assertEqual(result, [])

    def test_lists_commits_after_last_synced(self):
        with tempfile.TemporaryDirectory() as repo_root:
            _init_repo(repo_root)
            first = _commit(repo_root, "a.txt", "first commit")
            _commit(repo_root, "b.txt", "second commit")
            _commit(repo_root, "c.txt", "third commit")

            result = unsynced_commits(repo_root, first)

            self.assertEqual(len(result), 2)
            self.assertTrue(any("second commit" in line for line in result))
            self.assertTrue(any("third commit" in line for line in result))

    def test_empty_when_last_synced_commit_unknown_to_this_repo(self):
        # e.g. config left over from a rebase/history-rewrite, or a typo —
        # treat as "can't determine, so nothing new" rather than crash
        with tempfile.TemporaryDirectory() as repo_root:
            _init_repo(repo_root)
            _commit(repo_root, "a.txt", "first commit")

            result = unsynced_commits(repo_root, "0" * 40)

            self.assertEqual(result, [])


class TestCurrentHead(unittest.TestCase):
    def test_returns_head_sha(self):
        with tempfile.TemporaryDirectory() as repo_root:
            _init_repo(repo_root)
            head = _commit(repo_root, "a.txt", "first commit")

            self.assertEqual(current_head(repo_root), head)

    def test_none_outside_any_repo(self):
        with tempfile.TemporaryDirectory() as not_a_repo:
            self.assertIsNone(current_head(not_a_repo))


if __name__ == "__main__":
    unittest.main()
