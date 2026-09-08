# Auto-Advance Workflow Stages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three "gap" detections to synclinear's Stop hook — proposal-complete-but-no-design-doc, design-doc-exists-but-no-plan, tasks-complete-but-not-archived — each firing once per signature as a directive Claude acts on immediately, not a review-gated proposal.

**Architecture:** A new `_file_timestamp()` helper (git-log-first, filesystem-mtime fallback for untracked files) backs three new pure detection functions in `hooks/check_unsynced.py`, composed into `main()` alongside the existing three signals. `lib/config.py` gains one new required field; `lib/openspec_check.py` is unchanged (fully reused). Unlike flows 3a/3b/3c, the hook itself persists fired gap signatures directly — no waiting for Claude to act first — since directives don't have a review-gate step to hang persistence off of.

**Tech Stack:** Python 3 stdlib only (`subprocess`, `json`, `os`, `datetime`), `unittest`, real `git` CLI as test fixture (no mocking — matches this project's established style).

## Global Constraints

- Every new detection function degrades to `None`/no-op on any failure (missing git, missing file, bad JSON) — the Stop hook must never crash a session (verbatim from all three prior tasks' Global Constraints).
- Each of the three gaps fires independently and gets its own paragraph in `additionalContext` — never merged with each other or with the existing 3a/3b/3c paragraphs (same "never merge findings" rule as the rest of the hook).
- Gap directives are phrased as instructions to act immediately ("begin X now"), distinct from flows 3a/3b/3c's "here's a proposal, read SKILL.md" phrasing — this is a deliberate, confirmed design choice (see docs/workflow-stage-advancement/design.md's "Directive phrasing" section), not an oversight to fix.
- `_file_timestamp()` MUST prefer `git log -1 --format=%ct -- <path>` (a file's real last-commit time) over filesystem mtime, falling back to mtime only when the file is untracked (no git log result) — this exists specifically to survive `git clone`, which resets every file's mtime to the moment of cloning regardless of its real commit history (verified empirically during design with a real clone round-trip).
- The hook itself (not a later Claude turn) persists newly-fired gap signatures into `advanced_workflow_gaps` via `config.save_config` before it exits — unlike 3a/3b/3c, where the equivalent config field is updated later by Claude after Eva's review. Directives have no review-gate step to hang that update off of, so the hook does it directly.
- No changes to flows 3a/3b/3c's existing detection logic, output, or review-gated behavior — this plan is purely additive.
- Every MLAI colleague's Studio-team project must work identically — no Ironman-specific paths, names, or assumptions anywhere in this code.

---

### Task 1: Extend `lib/config.py`'s schema with `advanced_workflow_gaps`

**Files:**
- Modify: `C:\Users\Eva Ng\.claude\skills\synclinear\lib\config.py`
- Test: `C:\Users\Eva Ng\.claude\skills\synclinear\lib\test_config.py`
- Modify (deployed config, not test): `C:\Users\Eva Ng\Desktop\ironman\repo\.claude\synclinear.json`

**Interfaces:**
- Consumes: nothing new — same `load_config(repo_root) -> dict | None`, `save_config(repo_root, config) -> None` signatures.
- Produces: `load_config` now additionally requires `advanced_workflow_gaps` (`list[str]`, may be empty). A config missing it, or with the wrong type, is invalid (`None`) — same pattern as `known_openspec_changes`. Task 3's gap-detection code reads/writes this field directly off the dict `load_config` returns.

The current file (already read this session) has:
```python
_REQUIRED_STRING_KEYS = (
    "linear_team",
    "linear_project",
    "timetable_path",
    "last_synced_commit",
    "last_artifact_check_at",
)
_REQUIRED_LIST_OF_STRING_KEYS = ("known_openspec_changes",)
```

- [ ] **Step 1: Write the failing tests**

Add these two test methods to `TestLoadConfig` in `lib/test_config.py` (keep every existing test method unchanged):

```python
    def test_valid_config_with_advanced_workflow_gaps_returns_dict(self):
        with tempfile.TemporaryDirectory() as repo_root:
            claude_dir = os.path.join(repo_root, ".claude")
            os.makedirs(claude_dir)
            with open(os.path.join(claude_dir, "synclinear.json"), "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "linear_team": "Studio",
                        "linear_project": "[Studio] Project Ironman",
                        "timetable_path": "C:/timetable.txt",
                        "last_synced_commit": "de1c2c8",
                        "known_openspec_changes": [],
                        "last_artifact_check_at": "2026-09-08T00:00:00Z",
                        "advanced_workflow_gaps": ["add-widget:gap1"],
                    },
                    f,
                )

            config = load_config(repo_root)

            self.assertEqual(config["advanced_workflow_gaps"], ["add-widget:gap1"])

    def test_missing_advanced_workflow_gaps_returns_none(self):
        with tempfile.TemporaryDirectory() as repo_root:
            claude_dir = os.path.join(repo_root, ".claude")
            os.makedirs(claude_dir)
            with open(os.path.join(claude_dir, "synclinear.json"), "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "linear_team": "Studio",
                        "linear_project": "[Studio] Project Ironman",
                        "timetable_path": "C:/timetable.txt",
                        "last_synced_commit": "de1c2c8",
                        "known_openspec_changes": [],
                        "last_artifact_check_at": "2026-09-08T00:00:00Z",
                    },
                    f,
                )

            self.assertIsNone(load_config(repo_root))
```

Also update the existing tests' fixtures so they stay valid input once Step 3 makes the new key required — add `"advanced_workflow_gaps": []` to the `json.dump(...)` dict in `test_valid_config_returns_dict` and `test_valid_config_with_new_v2_keys_returns_dict`, to the `config` dict in `TestSaveConfig.test_round_trip`, and to the `save_config(...)` call's dict in `test_creates_claude_dir_if_missing`.

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `cd "C:\Users\Eva Ng\.claude\skills\synclinear\lib" && python -m pytest test_config.py -v`
Expected: `test_missing_advanced_workflow_gaps_returns_none` FAILS (today's `load_config` doesn't require this key, so it currently returns a dict instead of `None`). `test_valid_config_with_advanced_workflow_gaps_returns_dict` passes already (extra keys are ignored today) — that's fine, it becomes a real regression guard once Step 3 lands.

- [ ] **Step 3: Update `load_config`'s validation**

In `lib/config.py`, change:
```python
_REQUIRED_LIST_OF_STRING_KEYS = ("known_openspec_changes",)
```
to:
```python
_REQUIRED_LIST_OF_STRING_KEYS = ("known_openspec_changes", "advanced_workflow_gaps")
```
No other changes needed — the existing loop `for key in _REQUIRED_LIST_OF_STRING_KEYS: ...` already validates every key in this tuple the same way.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "C:\Users\Eva Ng\.claude\skills\synclinear\lib" && python -m pytest test_config.py -v`
Expected: PASS, all tests (existing nine plus the two new ones = 11).

- [ ] **Step 5: Patch the real deployed Ironman config**

Read `C:\Users\Eva Ng\Desktop\ironman\repo\.claude\synclinear.json`, then write it back with `"advanced_workflow_gaps": []` added (empty — no gaps have fired yet under this mechanism).

- [ ] **Step 6: No commit yet**

This repo (`~/.claude/skills/synclinear`) IS a real git repository (confirmed this session — unlike `~/.claude` itself, which has no `.git`). Commit at the end of each task as usual:

```bash
cd "C:\Users\Eva Ng\.claude\skills\synclinear"
git add lib/config.py lib/test_config.py
git commit -m "feat: add advanced_workflow_gaps to config schema"
```

(The deployed Ironman config edit in Step 5 is per-machine bookkeeping in a different repo — no commit needed for it.)

---

### Task 2: `_file_timestamp()` — clone-safe timestamp lookup

**Files:**
- Modify: `C:\Users\Eva Ng\.claude\skills\synclinear\hooks\check_unsynced.py`
- Test: `C:\Users\Eva Ng\.claude\skills\synclinear\hooks\test_check_unsynced.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `_file_timestamp(repo_root: str, path: str) -> float | None` — a module-level helper in `check_unsynced.py` that Task 3's three gap functions all call. Returns a Unix timestamp (float) for the file's real last-commit time if it's tracked and committed in git, falling back to `os.path.getmtime(path)` if `git log` finds no history for it (untracked/uncommitted), or `None` if the file doesn't exist at all.

- [ ] **Step 1: Write the failing tests**

Add this new test class to `hooks/test_check_unsynced.py` (near the top-level helpers, after the existing `_run_git`/`_init_repo_with_commit` functions — keep everything else in the file unchanged):

```python
import time


class TestFileTimestamp(unittest.TestCase):
    def test_none_when_file_does_not_exist(self):
        with tempfile.TemporaryDirectory() as repo_root:
            result = _file_timestamp(repo_root, os.path.join(repo_root, "nope.txt"))
            self.assertIsNone(result)

    def test_uses_git_commit_time_not_filesystem_mtime_after_simulated_clone(self):
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
        with tempfile.TemporaryDirectory() as repo_root:
            _run_git(["git", "init"], repo_root)
            file_path = os.path.join(repo_root, "untracked.md")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("brand new, never committed")

            result = _file_timestamp(repo_root, file_path)

            self.assertIsNotNone(result)
            self.assertAlmostEqual(result, os.path.getmtime(file_path), delta=2)
```

Add `import time` and `import subprocess` at the top of `hooks/test_check_unsynced.py` if not already present (`subprocess` is already imported for `_run_git`; `time` is new).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "C:\Users\Eva Ng\.claude\skills\synclinear\hooks" && python -m pytest test_check_unsynced.py::TestFileTimestamp -v`
Expected: FAIL with `NameError: name '_file_timestamp' is not defined` (or an import error, depending on how the test references it — either way, the function doesn't exist yet).

- [ ] **Step 3: Write the implementation**

Add this function to `hooks/check_unsynced.py`, near the top alongside the other module-level helpers (after `_read_cwd_from_stdin`, before `_propose_without_ticket_paragraph`):

```python
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
```

Add `import subprocess` to `check_unsynced.py`'s imports (it isn't there yet — the file currently only calls into `git_check`/`openspec_check` for subprocess work, this is the first direct `subprocess.run` call in `check_unsynced.py` itself).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "C:\Users\Eva Ng\.claude\skills\synclinear\hooks" && python -m pytest test_check_unsynced.py::TestFileTimestamp -v`
Expected: PASS, all three tests.

- [ ] **Step 5: Run the full existing suite to confirm no regressions**

Run: `cd "C:\Users\Eva Ng\.claude\skills\synclinear\hooks" && python -m pytest test_check_unsynced.py -v`
Expected: all previously-passing tests (9 from v2) still PASS, plus the 3 new ones = 12.

- [ ] **Step 6: Commit**

```bash
cd "C:\Users\Eva Ng\.claude\skills\synclinear"
git add hooks/check_unsynced.py hooks/test_check_unsynced.py
git commit -m "feat: add clone-safe _file_timestamp helper"
```

---

### Task 3: Three gap-detection functions, wired into `main()`

**Files:**
- Modify: `C:\Users\Eva Ng\.claude\skills\synclinear\hooks\check_unsynced.py`
- Test: `C:\Users\Eva Ng\.claude\skills\synclinear\hooks\test_check_unsynced.py`

**Interfaces:**
- Consumes: `_file_timestamp(repo_root, path) -> float | None` (Task 2), `openspec_check.list_changes(repo_root) -> list[dict] | None` (unchanged, existing), `config["advanced_workflow_gaps"]: list[str]` (Task 1).
- Produces: three new functions —
  - `_gap1_paragraph(repo_root: str, config: dict) -> tuple[str, list[str]] | None`
  - `_gap2_paragraph(repo_root: str, config: dict) -> tuple[str, list[str]] | None`
  - `_gap3_paragraph(repo_root: str, config: dict) -> tuple[str, list[str]] | None`

  Each returns `None` if nothing fires, or a `(paragraph_text, new_signatures)` tuple — `new_signatures` is the list of gap-signature strings this call determined should be added to `advanced_workflow_gaps` (not yet persisted; `main()` collects and saves them). This differs from `_propose_without_ticket_paragraph`/`_artifact_reminder_paragraph`'s `str | None` return, because those two rely on Claude updating config later after Eva's review — gap directives have no review step to hang that update off of, so the hook persists the signature itself, and needs the caller to actually call `save_config`.

- [ ] **Step 1: Write the failing tests**

Add this to `hooks/test_check_unsynced.py`, as a new test class after `TestCheckUnsyncedHookOpenSpecSignal`:

```python
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
            docs_dir = os.path.join(repo_root, "docs", "add-widget")
            os.makedirs(docs_dir)
            design_path = os.path.join(docs_dir, "design.md")
            with open(design_path, "w", encoding="utf-8") as f:
                f.write("# Add Widget Design\n")
            _run_git(["git", "add", "docs"], repo_root)
            _run_git(["git", "commit", "-m", "design doc"], repo_root)
            save_config(repo_root, _base_config(head))

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
            save_config(repo_root, _base_config(head, advanced_workflow_gaps=["add-widget:gap1"]))

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
            save_config(repo_root, _base_config(head))

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
            save_config(repo_root, _base_config(head, advanced_workflow_gaps=["add-widget:gap3"]))

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
            save_config(repo_root, _base_config(head))

            output = _run_hook(repo_root)

            parsed = json.loads(output)
            context = parsed["hookSpecificOutput"]["additionalContext"]
            paragraphs = [p for p in context.split("\n\n") if p.strip()]
            # commits paragraph + gap3 paragraph (proposal never got past
            # "no-tasks" so gap1 doesn't apply here; no docs/ so gap2 doesn't either)
            self.assertEqual(len(paragraphs), 2)
            self.assertTrue(any("second commit" in p for p in paragraphs))
            self.assertTrue(any("add-widget" in p and "review" in p.lower() for p in paragraphs))
```

Add `from config import load_config` is already imported; also need `save_config` imported in the test file for these new tests — check the existing `from config import save_config` import at the top of `hooks/test_check_unsynced.py` and add `load_config` to that same import line if it's not already there (`from config import load_config, save_config`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "C:\Users\Eva Ng\.claude\skills\synclinear\hooks" && python -m pytest test_check_unsynced.py::TestWorkflowStageGaps -v`
Expected: FAIL — none of `_gap1_paragraph`/`_gap2_paragraph`/`_gap3_paragraph` exist yet, and `main()` doesn't wire them in, so directive text and persisted signatures are both absent.

- [ ] **Step 3: Write the implementation**

Add these three functions to `hooks/check_unsynced.py`, after `_artifact_reminder_paragraph` and before `_commits_paragraph`:

```python
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
        last_modified = entry.get("lastModified")
        if not name or not status or status == "no-tasks" or not last_modified:
            continue
        signature = f"{name}:gap1"
        if signature in known:
            continue
        try:
            change_ts = datetime.datetime.fromisoformat(
                last_modified.replace("Z", "+00:00")
            ).timestamp()
        except ValueError:
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
```

Now update `main()` to wire all three in and persist their signatures. Replace the current `main()` body:

```python
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
```

Add `from config import load_config, save_config` (add `save_config` to the existing import) and `import subprocess` at the top of `check_unsynced.py` if not already present from Task 2.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "C:\Users\Eva Ng\.claude\skills\synclinear\hooks" && python -m pytest test_check_unsynced.py -v`
Expected: PASS, all tests — the 12 from Tasks 1-2 plus the new `TestWorkflowStageGaps` class (9 tests) = 21 (skip counts vary by whether `openspec` is on the machine's PATH, same as before).

If `test_multiple_gaps_and_existing_signals_produce_separate_paragraphs` fails on the expected paragraph count, double check whether `_gap1_paragraph` is misfiring for the "add-widget" change in that test (its `tasks.md` has all boxes checked, so `status` should be `"complete"`, not something gap1 would catch — gap1 only fires on non-"no-tasks" AND non-docs-exists, and gap3 is the one that should catch "complete"; if both accidentally fire, re-check gap1's exclusion isn't accidentally missing a "already complete, not a docs gap" condition — though as designed, gap1 and gap3 are not mutually exclusive by construction, a change with status "complete" also satisfies gap1's condition `status != "no-tasks"` if no docs exist yet, so BOTH could legitimately fire simultaneously; if that happens in this specific test, add a docs/ file for "add-widget" in the test setup to suppress gap1, since the test's intent is to isolate gap3 + the commits signal only).

- [ ] **Step 5: Commit**

```bash
cd "C:\Users\Eva Ng\.claude\skills\synclinear"
git add hooks/check_unsynced.py hooks/test_check_unsynced.py
git commit -m "feat: add gap1/gap2/gap3 workflow-stage-advancement detection"
```

---

### Task 4: SKILL.md documentation

**Files:**
- Modify: `C:\Users\Eva Ng\.claude\skills\synclinear\SKILL.md`

**Interfaces:**
- Consumes: the three directive paragraph shapes Task 3 emits (identifiable by their content: gap1 mentions "brainstorm/grill stage", gap2 mentions "writing-plans stage", gap3 mentions "review now").
- Produces: nothing machine-readable — prose Claude follows when a gap directive fires. No tests apply; verification is a careful read-through against `docs/workflow-stage-advancement/design.md`'s "Judgment before acting" section (the three grilled-and-revised behaviors) and the specs file's four new Requirements about directive judgment.

- [ ] **Step 1: Update the frontmatter description**

Change line 3 to mention this fourth mechanism:
```
description: Sync a git repo's state into Linear and its time log, AND keep the 7-step dev cycle moving — (3a) unsynced commits into Done tickets + time-log lines, (3b) OpenSpec proposals into new Todo tickets sized from tasks.md, (3c) archived OpenSpec changes into a client-facing artifact reminder, (workflow-stage gaps) directs Claude to begin the next stage of the 7-step cycle when one stalls — always with a review step before writing anything to Linear or a file. Triggered automatically by a Stop hook reminder; can also be invoked directly by Eva.
```

- [ ] **Step 2: Add a new section after Flow 3c, before "First-time setup for a new repo"**

Insert:

```markdown
## Workflow-stage gap directives

Triggered by a Stop-hook reminder naming a "gap" in the 7-step per-change
cycle (explore → propose → brainstorm/grill → writing-plans → TDD →
review → archive) — a proposal complete with no design doc, a design doc
with no plan, or all tasks checked but the change not yet archived.

**These are directives, not proposals — do not wait for Eva's go-ahead
before beginning the next stage.** The 7-step sequence itself is a
standing agreement Eva already made; only the content decisions *inside*
each stage (what the design says, whether review passes) still involve
her directly, through ordinary conversation — unchanged from how those
stages always worked.

That said, act with judgment, not blind literalism:

1. **If the directive fires while Eva is mid-conversation on something
   unrelated** to the change that triggered it, mention the pending gap
   briefly and defer — don't derail what's actually happening to
   immediately switch tasks.
2. **If Eva mentions she's redoing a stage** whose gap signature already
   fired (e.g. rewriting a design doc from scratch), proactively remove
   that signature from `advanced_workflow_gaps` in
   `.claude/synclinear.json` (read the file, edit the JSON, write it
   back, or use `lib/config.py`'s `load_config`/`save_config`) so the gap
   is eligible to fire again once the redo is complete — the mechanism
   otherwise stays silently inert with no sign anything's wrong.
3. **For a "tasks complete" directive specifically**, check first whether
   Eva already reviewed and approved this work earlier in the current
   conversation (before the last task got checked off) — `tasks.md`
   checkboxes are a fact about implementation completeness, not proof of
   review. If review already happened, skip straight to asking whether to
   archive now; don't re-present the work for review a second time.

Concretely, what to do per gap:
- **Proposal complete, no design doc** → invoke `superpowers:brainstorming`
  to begin the brainstorm/grill stage.
- **Design doc exists, no plan** → invoke `superpowers:writing-plans` to
  begin the writing-plans stage.
- **All tasks checked, not archived** → present the completed work for
  Eva's review (unless already done this conversation — see point 3
  above), then run `/opsx:archive` (or ask Claude to archive the change)
  once she approves.
```

- [ ] **Step 3: No commit yet — combine with Task 4's own commit below**

- [ ] **Step 4: Commit**

```bash
cd "C:\Users\Eva Ng\.claude\skills\synclinear"
git add SKILL.md
git commit -m "docs: document workflow-stage gap directives in SKILL.md"
```

---

### Task 5: Full-suite verification

**Files:** none modified — this task only runs and reads existing test output.

**Interfaces:** none — this is a verification-only task.

- [ ] **Step 1: Run every test file in the repo**

```bash
cd "C:\Users\Eva Ng\.claude\skills\synclinear\lib" && python -m pytest test_config.py test_git_check.py test_openspec_check.py -v
cd "C:\Users\Eva Ng\.claude\skills\synclinear\hooks" && python -m pytest test_check_unsynced.py -v
```

Expected: every test passes, zero regressions in the pre-existing flows 3a/3b/3c tests. Record the final counts.

- [ ] **Step 2: Manually verify against a real throwaway OpenSpec change**

In a scratch directory (not this repo), reproduce the same manual verification style used for flows 3b/3c during v2: `git init`, `openspec init --tools claude .`, `openspec new change "manual-check"`, write a `tasks.md` with an unchecked box, run the hook directly (`python check_unsynced.py < payload.json` with a stdin JSON containing `cwd`), confirm Gap 1 fires with the expected text; check the box, re-run, confirm Gap 1 no longer fires (signature already recorded) but Gap 3 now does; create a `docs/` file and a `docs/superpowers/plans/` file in the right order, confirm Gap 2 behaves as expected. This is a final sanity check against real CLI behavior, not just the test suite's assumptions about `list_changes()`'s shape.

- [ ] **Step 3: No commit** (verification produces no file changes)

---

## Post-plan note for whoever executes this

`docs/workflow-stage-advancement/design.md`'s "Related" section links (via
Obsidian wikilinks) to `[[flow-3b-openspec-to-linear]]`,
`[[flow-3c-artifact-reminder]]`, and `[[openspec-check-module]]` — none of
these target notes exist yet (flows 3b/3c and `openspec_check.py` were
built directly as code + SKILL.md prose during v2, without their own
`docs/` notes). This is expected and fine per Obsidian's normal
wikilink-to-nonexistent-note behavior, but if Eva ever wants those
back-filled as their own notes, that's separate scope from this plan —
don't create them unprompted.
