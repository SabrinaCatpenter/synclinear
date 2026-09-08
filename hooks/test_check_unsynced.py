from __future__ import annotations

import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
from config import load_config, save_config  # noqa: E402
from check_unsynced import _week_file_name  # noqa: E402

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


class TestFileTimestamp(unittest.TestCase):
    @staticmethod
    def _get_file_timestamp():
        # Lazy import to avoid module-level side effects
        import check_unsynced  # noqa: E402
        return check_unsynced._file_timestamp

    def test_none_when_file_does_not_exist(self):
        _file_timestamp = self._get_file_timestamp()
        with tempfile.TemporaryDirectory() as repo_root:
            result = _file_timestamp(repo_root, os.path.join(repo_root, "nope.txt"))
            self.assertIsNone(result)

    def test_uses_git_commit_time_not_filesystem_mtime_after_simulated_clone(self):
        _file_timestamp = self._get_file_timestamp()
        with tempfile.TemporaryDirectory() as repo_root:
            _run_git(["git", "init"], repo_root)
            _run_git(["git", "config", "user.email", "test@example.com"], repo_root)
            _run_git(["git", "config", "user.name", "Test"], repo_root)
            file_path = os.path.join(repo_root, "old.md")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("old content")
            _run_git(["git", "add", "old.md"], repo_root)
            old_commit_env = os.environ.copy()
            old_commit_env["GIT_AUTHOR_DATE"] = "2020-01-01T00:00:00"
            old_commit_env["GIT_COMMITTER_DATE"] = "2020-01-01T00:00:00"
            subprocess.run(
                ["git", "commit", "-m", "old commit"],
                cwd=repo_root, env=old_commit_env, check=True, capture_output=True,
            )
            # Simulate what a `git clone` does to mtimes: touch the file to "now",
            # far later than its real 2020 commit — this is the exact bug found
            # during design (verified with a real clone; reproduced here without
            # needing an actual second clone for speed).
            future_time = time.time()
            os.utime(file_path, (future_time, future_time))

            result = _file_timestamp(repo_root, file_path)

            # 2020-01-01T00:00:00 as a Unix timestamp is ~1577836800 (UTC) —
            # allow either side of the exact value depending on local git's
            # timezone interpretation of a naive date string, but it MUST be
            # far below "now", proving git history won this over the touched mtime.
            self.assertLess(result, future_time - 86400 * 300)  # more than ~300 days earlier

    def test_falls_back_to_mtime_for_untracked_file(self):
        _file_timestamp = self._get_file_timestamp()
        with tempfile.TemporaryDirectory() as repo_root:
            _run_git(["git", "init"], repo_root)
            file_path = os.path.join(repo_root, "untracked.md")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("brand new, never committed")

            result = _file_timestamp(repo_root, file_path)

            self.assertIsNotNone(result)
            self.assertAlmostEqual(result, os.path.getmtime(file_path), delta=2)


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
                    "advanced_workflow_gaps": [],
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
                    "advanced_workflow_gaps": [],
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
                    "advanced_workflow_gaps": [],
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
                    "advanced_workflow_gaps": [],
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
                    "advanced_workflow_gaps": [],
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
                    "advanced_workflow_gaps": [],
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
                    "advanced_workflow_gaps": [],
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


def _init_openspec_repo(repo_root: str) -> None:
    subprocess.run(
        "openspec init --tools claude .", cwd=repo_root, check=True, capture_output=True, shell=True,
    )


def _new_openspec_change(repo_root: str, name: str) -> None:
    subprocess.run(
        f'openspec new change "{name}"', cwd=repo_root, check=True, capture_output=True, shell=True,
    )


def _base_config(head: str, **overrides) -> dict:
    config = {
        "linear_team": "Studio",
        "linear_project": "P",
        "timetable_path": "C:/timetable.txt",
        "last_synced_commit": head,
        "known_openspec_changes": [],
        "last_artifact_check_at": "2026-09-08T00:00:00+00:00",
        "advanced_workflow_gaps": [],
    }
    config.update(overrides)
    return config


class TestWorkflowStageGaps(unittest.TestCase):
    @unittest.skipUnless(shutil.which("openspec"), "openspec CLI not installed")
    def test_gap1_fires_when_proposal_complete_and_no_docs(self):
        with tempfile.TemporaryDirectory() as repo_root:
            head = _init_repo_with_commit(repo_root)
            _init_openspec_repo(repo_root)
            _new_openspec_change(repo_root, "add-widget")
            tasks_dir = os.path.join(repo_root, "openspec", "changes", "add-widget")
            with open(os.path.join(tasks_dir, "tasks.md"), "w", encoding="utf-8") as f:
                f.write("## 1. Implement widget\n- [ ] Build it\n")
            save_config(repo_root, _base_config(head))

            output = _run_hook(repo_root)

            self.assertNotEqual(output, "")
            parsed = json.loads(output)
            context = parsed["hookSpecificOutput"]["additionalContext"]
            self.assertIn("add-widget", context)
            self.assertIn("brainstorm", context.lower())
            # the hook must have persisted the signature itself
            self.assertIn("add-widget:gap1", load_config(repo_root)["advanced_workflow_gaps"])

    @unittest.skipUnless(shutil.which("openspec"), "openspec CLI not installed")
    def test_gap1_silent_when_docs_file_is_newer(self):
        with tempfile.TemporaryDirectory() as repo_root:
            head = _init_repo_with_commit(repo_root)
            _init_openspec_repo(repo_root)
            _new_openspec_change(repo_root, "add-widget")
            tasks_dir = os.path.join(repo_root, "openspec", "changes", "add-widget")
            with open(os.path.join(tasks_dir, "tasks.md"), "w", encoding="utf-8") as f:
                f.write("## 1. Implement widget\n- [ ] Build it\n")
            # `openspec list --json`'s lastModified has millisecond
            # precision; the git commit timestamp _file_timestamp reads for
            # the docs file is truncated to whole seconds. Without a gap,
            # both can land in the same integer second, and the change's
            # sub-second component can make it compare as "later" even
            # though the docs commit below happens after it — sleep past
            # the second boundary so the ordering this test asserts is
            # actually exercised.
            time.sleep(1.1)
            docs_dir = os.path.join(repo_root, "docs", "add-widget")
            os.makedirs(docs_dir)
            design_path = os.path.join(docs_dir, "design.md")
            with open(design_path, "w", encoding="utf-8") as f:
                f.write("# Add Widget Design\n")
            _run_git(["git", "add", "docs"], repo_root)
            _run_git(["git", "commit", "-m", "design doc"], repo_root)
            # Isolate gap1 from the pre-existing 3a/3b/3c signals, which
            # would otherwise also fire here and break the assertEqual(output,
            # "") assertion for reasons unrelated to gap1: the design-doc
            # commit above is unsynced (3a), "add-widget" has a completed
            # proposal not yet in known_openspec_changes (3b), and
            # _init_openspec_repo's archive/ dir postdates the fixed
            # 2026-09-08 baseline as real time advances past it (3c).
            new_head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repo_root, check=True,
                capture_output=True, text=True,
            ).stdout.strip()
            future = (
                datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
            ).isoformat()
            save_config(
                repo_root,
                _base_config(
                    new_head,
                    known_openspec_changes=["add-widget"],
                    last_artifact_check_at=future,
                    # the docs/add-widget/design.md file this test writes
                    # also satisfies gap2's condition (docs/ newer than
                    # docs/superpowers/plans/, which doesn't exist here) —
                    # pre-record it as already-known so only gap1 is under
                    # test.
                    advanced_workflow_gaps=["docs:gap2"],
                ),
            )

            output = _run_hook(repo_root)

            self.assertEqual(output, "")

    @unittest.skipUnless(shutil.which("openspec"), "openspec CLI not installed")
    def test_gap1_silent_when_signature_already_recorded(self):
        with tempfile.TemporaryDirectory() as repo_root:
            head = _init_repo_with_commit(repo_root)
            _init_openspec_repo(repo_root)
            _new_openspec_change(repo_root, "add-widget")
            tasks_dir = os.path.join(repo_root, "openspec", "changes", "add-widget")
            with open(os.path.join(tasks_dir, "tasks.md"), "w", encoding="utf-8") as f:
                f.write("## 1. Implement widget\n- [ ] Build it\n")
            # Isolate gap1's already-recorded-signature check from 3b/3c,
            # which would otherwise also fire (see comment in the previous
            # test for why).
            future = (
                datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
            ).isoformat()
            save_config(
                repo_root,
                _base_config(
                    head,
                    advanced_workflow_gaps=["add-widget:gap1"],
                    known_openspec_changes=["add-widget"],
                    last_artifact_check_at=future,
                ),
            )

            output = _run_hook(repo_root)

            self.assertEqual(output, "")

    def test_gap2_fires_when_docs_newer_than_plans(self):
        with tempfile.TemporaryDirectory() as repo_root:
            head = _init_repo_with_commit(repo_root)
            docs_dir = os.path.join(repo_root, "docs")
            os.makedirs(docs_dir)
            with open(os.path.join(docs_dir, "design.md"), "w", encoding="utf-8") as f:
                f.write("# Design\n")
            _run_git(["git", "add", "docs"], repo_root)
            _run_git(["git", "commit", "-m", "design doc"], repo_root)
            save_config(repo_root, _base_config(head))

            output = _run_hook(repo_root)

            self.assertNotEqual(output, "")
            parsed = json.loads(output)
            context = parsed["hookSpecificOutput"]["additionalContext"]
            self.assertIn("plan", context.lower())
            self.assertIn("docs:gap2", load_config(repo_root)["advanced_workflow_gaps"])

    def test_gap2_silent_when_plan_is_newer(self):
        with tempfile.TemporaryDirectory() as repo_root:
            head = _init_repo_with_commit(repo_root)
            docs_dir = os.path.join(repo_root, "docs")
            os.makedirs(docs_dir)
            with open(os.path.join(docs_dir, "design.md"), "w", encoding="utf-8") as f:
                f.write("# Design\n")
            _run_git(["git", "add", "docs"], repo_root)
            _run_git(["git", "commit", "-m", "design doc"], repo_root)
            plans_dir = os.path.join(repo_root, "docs", "superpowers", "plans")
            os.makedirs(plans_dir)
            with open(os.path.join(plans_dir, "plan.md"), "w", encoding="utf-8") as f:
                f.write("# Plan\n")
            _run_git(["git", "add", "docs"], repo_root)
            _run_git(["git", "commit", "-m", "plan doc"], repo_root)
            # Isolate gap2 from the pre-existing 3a commits signal, which
            # would otherwise fire too: the design/plan doc commits above
            # are unsynced relative to the original `head`.
            new_head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repo_root, check=True,
                capture_output=True, text=True,
            ).stdout.strip()
            save_config(repo_root, _base_config(new_head))

            output = _run_hook(repo_root)

            self.assertEqual(output, "")

    def test_gap2_silent_when_no_docs_at_all(self):
        with tempfile.TemporaryDirectory() as repo_root:
            head = _init_repo_with_commit(repo_root)
            save_config(repo_root, _base_config(head))

            output = _run_hook(repo_root)

            self.assertEqual(output, "")

    @unittest.skipUnless(shutil.which("openspec"), "openspec CLI not installed")
    def test_gap3_fires_when_all_tasks_checked(self):
        with tempfile.TemporaryDirectory() as repo_root:
            head = _init_repo_with_commit(repo_root)
            _init_openspec_repo(repo_root)
            _new_openspec_change(repo_root, "add-widget")
            tasks_dir = os.path.join(repo_root, "openspec", "changes", "add-widget")
            with open(os.path.join(tasks_dir, "tasks.md"), "w", encoding="utf-8") as f:
                f.write("## 1. Implement widget\n- [x] Build it\n")
            save_config(repo_root, _base_config(head))

            output = _run_hook(repo_root)

            self.assertNotEqual(output, "")
            parsed = json.loads(output)
            context = parsed["hookSpecificOutput"]["additionalContext"]
            self.assertIn("add-widget", context)
            self.assertIn("review", context.lower())
            self.assertIn("add-widget:gap3", load_config(repo_root)["advanced_workflow_gaps"])

    @unittest.skipUnless(shutil.which("openspec"), "openspec CLI not installed")
    def test_gap3_silent_when_signature_already_recorded(self):
        with tempfile.TemporaryDirectory() as repo_root:
            head = _init_repo_with_commit(repo_root)
            _init_openspec_repo(repo_root)
            _new_openspec_change(repo_root, "add-widget")
            tasks_dir = os.path.join(repo_root, "openspec", "changes", "add-widget")
            with open(os.path.join(tasks_dir, "tasks.md"), "w", encoding="utf-8") as f:
                f.write("## 1. Implement widget\n- [x] Build it\n")
            # Isolate gap3's already-recorded-signature check from 3b/3c
            # (see comment on test_gap1_silent_when_docs_file_is_newer),
            # and from gap1 itself, which would also fire here since a
            # "complete" change with no docs/ satisfies gap1's condition
            # too (status != "no-tasks" and no docs) — record its
            # signature as already-known so only gap3 is under test.
            future = (
                datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
            ).isoformat()
            save_config(
                repo_root,
                _base_config(
                    head,
                    advanced_workflow_gaps=["add-widget:gap3", "add-widget:gap1"],
                    known_openspec_changes=["add-widget"],
                    last_artifact_check_at=future,
                ),
            )

            output = _run_hook(repo_root)

            self.assertEqual(output, "")

    @unittest.skipUnless(shutil.which("openspec"), "openspec CLI not installed")
    def test_multiple_gaps_and_existing_signals_produce_separate_paragraphs(self):
        with tempfile.TemporaryDirectory() as repo_root:
            head = _init_repo_with_commit(repo_root)
            _init_openspec_repo(repo_root)
            _new_openspec_change(repo_root, "add-widget")
            tasks_dir = os.path.join(repo_root, "openspec", "changes", "add-widget")
            with open(os.path.join(tasks_dir, "tasks.md"), "w", encoding="utf-8") as f:
                f.write("## 1. Implement widget\n- [x] Build it\n")
            with open(os.path.join(repo_root, "b.txt"), "w", encoding="utf-8") as f:
                f.write("second")
            _run_git(["git", "add", "b.txt"], repo_root)
            _run_git(["git", "commit", "-m", "second commit"], repo_root)
            # "existing signals": pre-record add-widget:gap1 so this test
            # isolates commits + gap3. Without this, gap1 also fires here —
            # a "complete" change with no docs/ satisfies both gap1
            # (status != "no-tasks", no docs) and gap3 (status == complete)
            # by design, per the task brief; they are not mutually
            # exclusive. Also suppress the unrelated 3b/3c signals (see
            # comment on test_gap1_silent_when_docs_file_is_newer) so only
            # the commits (3a) + gap3 signals remain, matching the 2
            # paragraphs asserted below.
            future = (
                datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
            ).isoformat()
            save_config(
                repo_root,
                _base_config(
                    head,
                    advanced_workflow_gaps=["add-widget:gap1"],
                    known_openspec_changes=["add-widget"],
                    last_artifact_check_at=future,
                ),
            )

            output = _run_hook(repo_root)

            parsed = json.loads(output)
            context = parsed["hookSpecificOutput"]["additionalContext"]
            paragraphs = [p for p in context.split("\n\n") if p.strip()]
            # commits paragraph + gap3 paragraph (add-widget:gap1 is
            # pre-recorded above to suppress gap1's co-firing; no docs/
            # under docs/superpowers/plans/ so gap2 doesn't apply either)
            self.assertEqual(len(paragraphs), 2)
            self.assertTrue(any("second commit" in p for p in paragraphs))
            self.assertTrue(any("add-widget" in p and "review" in p.lower() for p in paragraphs))

    @unittest.skipUnless(shutil.which("openspec"), "openspec CLI not installed")
    def test_gap1_silent_when_docs_written_before_later_tasks_md_edit(self):
        with tempfile.TemporaryDirectory() as repo_root:
            head = _init_repo_with_commit(repo_root)
            _init_openspec_repo(repo_root)
            _new_openspec_change(repo_root, "add-widget")
            tasks_dir = os.path.join(repo_root, "openspec", "changes", "add-widget")
            with open(os.path.join(tasks_dir, "tasks.md"), "w", encoding="utf-8") as f:
                f.write("## 1. Implement widget\n- [ ] Build it\n")
            _run_git(["git", "add", "openspec"], repo_root)
            _run_git(["git", "commit", "-m", "tasks.md created"], repo_root)

            # 写设计文档并 commit —— 这应该让 gap1 判定"docs 已经够新，不用提醒"
            docs_dir = os.path.join(repo_root, "docs", "add-widget")
            os.makedirs(docs_dir)
            with open(os.path.join(docs_dir, "design.md"), "w", encoding="utf-8") as f:
                f.write("# design\n")
            _run_git(["git", "add", "docs"], repo_root)
            _run_git(["git", "commit", "-m", "design doc"], repo_root)

            # 之后再去修改（勾选）tasks.md —— 这是 TDD 阶段的正常操作，不应该让
            # gap1 重新误触发（这正是这次要修的 bug：旧实现用 change 整体的
            # lastModified 做比较，会被这一步的编辑刷新，导致误报）
            with open(os.path.join(tasks_dir, "tasks.md"), "w", encoding="utf-8") as f:
                f.write("## 1. Implement widget\n- [x] Build it\n")
            _run_git(["git", "add", "openspec"], repo_root)
            _run_git(["git", "commit", "-m", "check off task"], repo_root)

            save_config(repo_root, _base_config(head))

            output = _run_hook(repo_root)

            # gap1 不应该出现在输出里（可能 gap3 会触发，因为任务全部勾选完成了，
            # 那是正常的、预期内的，只需要确认 gap1 相关的措辞没有出现）
            if output:
                parsed = json.loads(output)
                context = parsed["hookSpecificOutput"]["additionalContext"]
                self.assertNotIn("brainstorm/grill stage", context)


class TestWeekFileName(unittest.TestCase):
    def test_friday_itself_starts_its_own_week(self):
        # 2026-09-04 is a Friday (verified: datetime.date(2026, 9, 4).weekday() == 4).
        # Using a UTC timestamp equal to local midday keeps this test away
        # from timezone-boundary flakiness; expected values are computed
        # with the same local-tz-conversion logic the implementation itself
        # uses, kept as an independent formula below (not calling the
        # implementation), so a real regression in the implementation's
        # logic still gets caught rather than the test trivially agreeing
        # with whatever the implementation currently does.
        friday = datetime.datetime(2026, 9, 4, 10, 0, tzinfo=datetime.timezone.utc)
        result = _week_file_name(friday)
        local_tz = datetime.datetime.now().astimezone().tzinfo
        local_friday_date = friday.astimezone(local_tz).date()
        expected_start = local_friday_date
        expected_end = local_friday_date + datetime.timedelta(days=6)
        self.assertEqual(result, f"{expected_start.isoformat()}_{expected_end.isoformat()}.txt")

    def test_thursday_belongs_to_previous_fridays_week(self):
        # A Thursday, one day before the Friday used above.
        thursday = datetime.datetime(2026, 9, 3, 10, 0, tzinfo=datetime.timezone.utc)
        result = _week_file_name(thursday)
        local_tz = datetime.datetime.now().astimezone().tzinfo
        local_thursday_date = thursday.astimezone(local_tz).date()
        days_since_friday = (local_thursday_date.weekday() - 4) % 7
        expected_start = local_thursday_date - datetime.timedelta(days=days_since_friday)
        expected_end = expected_start + datetime.timedelta(days=6)
        self.assertEqual(result, f"{expected_start.isoformat()}_{expected_end.isoformat()}.txt")

    def test_saturday_belongs_to_the_friday_that_just_passed(self):
        saturday = datetime.datetime(2026, 9, 5, 10, 0, tzinfo=datetime.timezone.utc)
        result = _week_file_name(saturday)
        local_tz = datetime.datetime.now().astimezone().tzinfo
        local_saturday_date = saturday.astimezone(local_tz).date()
        days_since_friday = (local_saturday_date.weekday() - 4) % 7
        expected_start = local_saturday_date - datetime.timedelta(days=days_since_friday)
        expected_end = expected_start + datetime.timedelta(days=6)
        self.assertEqual(result, f"{expected_start.isoformat()}_{expected_end.isoformat()}.txt")

    def test_does_not_read_call_time_now_at_all(self):
        # Regression test for the DST bug: the old implementation did
        # `datetime.datetime.now().astimezone().tzinfo` to get a fixed UTC
        # offset, then reused that single offset to convert start_utc. On a
        # DST-observing system (e.g. Australia/Sydney, AEST +10 / AEDT +11),
        # if "now" (call time) and start_utc (the timestamp being converted)
        # fall on opposite sides of a DST transition, that fixed offset is
        # wrong by ~1 hour for start_utc, occasionally flipping local_date
        # across a midnight boundary and misfiling the block into the wrong
        # week file.
        #
        # The fix calls start_utc.astimezone() directly (no args), which
        # asks Python to resolve DST correctly for that specific instant,
        # with no dependency on when the function happens to be called. The
        # most direct way to prove that dependency is gone: make
        # datetime.datetime.now() blow up, and confirm _week_file_name still
        # works. If a future change reintroduces a call to now() to compute
        # the local date, this test fails immediately, regardless of what
        # DST data this machine's tz database has.
        class _ExplodingNow(datetime.datetime):
            @classmethod
            def now(cls, tz=None):  # noqa: D102 - test double
                raise AssertionError(
                    "_week_file_name must not call datetime.datetime.now(); "
                    "it should call start_utc.astimezone() directly so each "
                    "timestamp resolves its own DST state."
                )

        start_utc = datetime.datetime(2026, 1, 15, 10, 0, tzinfo=datetime.timezone.utc)
        with mock.patch("check_unsynced.datetime.datetime", _ExplodingNow):
            result = _week_file_name(start_utc)

        # Sanity check: with now() disabled, the function must still
        # produce a correctly-shaped result by resolving start_utc's own
        # local date directly (mirrors the implementation's own logic, not
        # a hardcoded date, so this stays valid regardless of the machine's
        # local timezone).
        expected_local_date = start_utc.astimezone().date()
        days_since_friday = (expected_local_date.weekday() - 4) % 7
        expected_start = expected_local_date - datetime.timedelta(days=days_since_friday)
        expected_end = expected_start + datetime.timedelta(days=6)
        self.assertEqual(result, f"{expected_start.isoformat()}_{expected_end.isoformat()}.txt")


if __name__ == "__main__":
    unittest.main()
