# synclinear Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the synclinear skill per `C:\Users\Eva Ng\.claude\skills\synclinear\DESIGN.md` — a global Claude Code skill that detects unsynced git commits via a Stop hook and, on request inside the conversation, proposes and applies matching Linear ticket updates after Eva's review.

**Architecture:** A Python Stop-hook script checks the current repo (via cwd) for a `.claude/synclinear.json` config and unsynced commits; if any exist, it emits Claude Code's structured hook-output JSON (`hookSpecificOutput.additionalContext`) so the reminder lands in Claude's next-turn context — plain stdout text does NOT do this; it must be that exact JSON shape. Claude then follows `SKILL.md`'s instructions to read the new commits, list open Linear tickets, propose a text preview, and only call the Linear MCP tools after Eva approves.

**Tech Stack:** Python (`python` on PATH — confirmed present this session, `C:\Python314\python.exe` first on PATH), git subprocess calls, `~/.claude/settings.json` Stop hook registration, the already-connected Linear MCP tools (`list_issues`, `save_issue`).

## Global Constraints

- No git repo backs `~/.claude` — nothing in this plan is committed to git; "commit" steps below just mean "the file is saved," skip any `git add`/`git commit` step language from the template.
- Config file: `.claude/synclinear.json` in the **target** repo (e.g. `ironman/repo/.claude/synclinear.json`), gitignored there, containing `linear_team`, `linear_project`, `last_synced_commit` (exact keys, per DESIGN.md).
- The Stop hook must never error or hang on a repo that hasn't opted in — silent no-op (empty output, exit 0) is required behavior, not just a nice-to-have.
- Hook output that should inject context MUST be valid JSON on stdout shaped `{"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": "<text>"}}` — a hook that just prints plain text does nothing.
- Nothing writes to Linear without Eva's explicit approval of a shown text-list preview — this is enforced by SKILL.md's instructions to Claude, not by code (there is no code-level gate on the Linear MCP calls themselves).

---

### Task 1: Config loader

**Files:**
- Create: `C:\Users\Eva Ng\.claude\skills\synclinear\lib\config.py`
- Test: `C:\Users\Eva Ng\.claude\skills\synclinear\lib\test_config.py`

**Interfaces:**
- Produces: `load_config(repo_root: str) -> dict | None` — reads `<repo_root>/.claude/synclinear.json`, returns the parsed dict, or `None` if the file doesn't exist or isn't valid JSON with the three required keys (`linear_team`, `linear_project`, `last_synced_commit`, all strings). Never raises.
- Produces: `save_config(repo_root: str, config: dict) -> None` — writes the dict back as pretty JSON to the same path, creating the `.claude/` directory if needed.

- [ ] **Step 1: Write the failing tests**

```python
# C:\Users\Eva Ng\.claude\skills\synclinear\lib\test_config.py
from __future__ import annotations

import json
import os
import tempfile
import unittest

from config import load_config, save_config


class TestLoadConfig(unittest.TestCase):
    def test_missing_file_returns_none(self):
        with tempfile.TemporaryDirectory() as repo_root:
            self.assertIsNone(load_config(repo_root))

    def test_valid_config_returns_dict(self):
        with tempfile.TemporaryDirectory() as repo_root:
            claude_dir = os.path.join(repo_root, ".claude")
            os.makedirs(claude_dir)
            with open(os.path.join(claude_dir, "synclinear.json"), "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "linear_team": "Studio",
                        "linear_project": "[Studio] Project Ironman",
                        "last_synced_commit": "de1c2c8",
                    },
                    f,
                )

            config = load_config(repo_root)

            self.assertEqual(config["linear_team"], "Studio")
            self.assertEqual(config["linear_project"], "[Studio] Project Ironman")
            self.assertEqual(config["last_synced_commit"], "de1c2c8")

    def test_malformed_json_returns_none(self):
        with tempfile.TemporaryDirectory() as repo_root:
            claude_dir = os.path.join(repo_root, ".claude")
            os.makedirs(claude_dir)
            with open(os.path.join(claude_dir, "synclinear.json"), "w", encoding="utf-8") as f:
                f.write("{not valid json")

            self.assertIsNone(load_config(repo_root))

    def test_missing_required_key_returns_none(self):
        with tempfile.TemporaryDirectory() as repo_root:
            claude_dir = os.path.join(repo_root, ".claude")
            os.makedirs(claude_dir)
            with open(os.path.join(claude_dir, "synclinear.json"), "w", encoding="utf-8") as f:
                json.dump({"linear_team": "Studio"}, f)  # missing linear_project, last_synced_commit

            self.assertIsNone(load_config(repo_root))


class TestSaveConfig(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as repo_root:
            config = {
                "linear_team": "Studio",
                "linear_project": "[Studio] Project Ironman",
                "last_synced_commit": "abc1234",
            }

            save_config(repo_root, config)
            loaded = load_config(repo_root)

            self.assertEqual(loaded, config)

    def test_creates_claude_dir_if_missing(self):
        with tempfile.TemporaryDirectory() as repo_root:
            save_config(
                repo_root,
                {"linear_team": "X", "linear_project": "Y", "last_synced_commit": "z"},
            )

            self.assertTrue(
                os.path.exists(os.path.join(repo_root, ".claude", "synclinear.json"))
            )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python C:\Users\Eva Ng\.claude\skills\synclinear\lib\test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'config'` (the file doesn't exist yet)

- [ ] **Step 3: Write the implementation**

```python
# C:\Users\Eva Ng\.claude\skills\synclinear\lib\config.py
"""Reads/writes .claude/synclinear.json in a target repo — the per-project
sync bookkeeping (which Linear team/project this repo's commits sync into,
and how far the sync has gotten). Never raises: a missing or malformed
config is treated as "not opted in," not an error, since the Stop hook
that calls this must never crash on an unrelated repo.
"""
from __future__ import annotations

import json
import os

_REQUIRED_KEYS = ("linear_team", "linear_project", "last_synced_commit")


def _config_path(repo_root: str) -> str:
    return os.path.join(repo_root, ".claude", "synclinear.json")


def load_config(repo_root: str) -> dict | None:
    path = _config_path(repo_root)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            config = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(config, dict):
        return None
    if not all(isinstance(config.get(key), str) for key in _REQUIRED_KEYS):
        return None
    return config


def save_config(repo_root: str, config: dict) -> None:
    claude_dir = os.path.join(repo_root, ".claude")
    os.makedirs(claude_dir, exist_ok=True)
    with open(_config_path(repo_root), "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python C:\Users\Eva Ng\.claude\skills\synclinear\lib\test_config.py -v`
Expected: `OK` (5 tests pass)

- [ ] **Step 5: Save**

No git commit — `~/.claude` isn't a repo. Just confirm both files are saved at the paths above.

---

### Task 2: Git-plumbing check (unsynced commits)

**Files:**
- Create: `C:\Users\Eva Ng\.claude\skills\synclinear\lib\git_check.py`
- Test: `C:\Users\Eva Ng\.claude\skills\synclinear\lib\test_git_check.py`

**Interfaces:**
- Consumes: nothing from Task 1 (independent module — the hook script in Task 3 wires config.py and git_check.py together).
- Produces: `find_repo_root(start_dir: str) -> str | None` — walks upward from `start_dir` looking for a `.git` directory; returns the absolute path containing it, or `None` if none found before the filesystem root.
- Produces: `unsynced_commits(repo_root: str, last_synced_commit: str) -> list[str]` — runs `git log --oneline <last_synced_commit>..HEAD` in `repo_root`, returns each line as a list element (empty list if none, or if `last_synced_commit` doesn't exist in this repo's history — see step 3 for why that's the same code path as "nothing new" rather than an error).

- [ ] **Step 1: Write the failing tests**

```python
# C:\Users\Eva Ng\.claude\skills\synclinear\lib\test_git_check.py
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest

from git_check import find_repo_root, unsynced_commits


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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python C:\Users\Eva Ng\.claude\skills\synclinear\lib\test_git_check.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'git_check'`

- [ ] **Step 3: Write the implementation**

```python
# C:\Users\Eva Ng\.claude\skills\synclinear\lib\git_check.py
"""Pure git-plumbing: locate a repo root, and list commits newer than a
known SHA. No Linear, no config — Task 3's hook script composes this with
config.py. Every git failure here (unknown SHA, not a repo, git not on
PATH) degrades to "nothing to report" rather than raising, because the
caller is a Stop hook that must never crash a session over bookkeeping.
"""
from __future__ import annotations

import os
import subprocess


def find_repo_root(start_dir: str) -> str | None:
    current = os.path.abspath(start_dir)
    while True:
        if os.path.isdir(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:  # reached filesystem root
            return None
        current = parent


def unsynced_commits(repo_root: str, last_synced_commit: str) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", f"{last_synced_commit}..HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.SubprocessError, OSError):
        return []
    if result.returncode != 0:
        # unknown SHA, detached weirdness, etc. — same as "nothing new"
        return []
    lines = result.stdout.strip().splitlines()
    return [line for line in lines if line]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python C:\Users\Eva Ng\.claude\skills\synclinear\lib\test_git_check.py -v`
Expected: `OK` (6 tests pass)

- [ ] **Step 5: Save**

No git commit needed (see Global Constraints).

---

### Task 3: The Stop hook script

**Files:**
- Create: `C:\Users\Eva Ng\.claude\skills\synclinear\hooks\check_unsynced.py`
- Test: `C:\Users\Eva Ng\.claude\skills\synclinear\hooks\test_check_unsynced.py`

**Interfaces:**
- Consumes: `config.load_config` and `git_check.find_repo_root` / `git_check.unsynced_commits` from Tasks 1-2 (imported via a `sys.path` insert of the `lib/` directory, since this is a standalone script, not an installed package).
- Produces: a `main() -> None` function that prints either nothing (silent no-op) or a single line of JSON shaped `{"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": "<text>"}}` to stdout, then exits 0. Also produces a `build_reminder(repo_root: str, config: dict, commits: list[str]) -> dict` pure function (the actual JSON-shape logic, unit-tested directly; `main()` just wires stdin/argv/cwd to it and is not itself unit-tested beyond the CLI-level tests below).

- [ ] **Step 1: Write the failing tests**

```python
# C:\Users\Eva Ng\.claude\skills\synclinear\hooks\test_check_unsynced.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python C:\Users\Eva Ng\.claude\skills\synclinear\hooks\test_check_unsynced.py -v`
Expected: FAIL — `FileNotFoundError` or non-empty output from a missing script (the file doesn't exist yet, so the subprocess call itself fails)

- [ ] **Step 3: Write the implementation**

```python
# C:\Users\Eva Ng\.claude\skills\synclinear\hooks\check_unsynced.py
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


def build_reminder(repo_root: str, config: dict, commits: list[str]) -> dict:
    project = config["linear_project"]
    lines = "\n".join(f"  - {c}" for c in commits)
    context = (
        f"synclinear: {len(commits)} new commit(s) in {repo_root} are not yet "
        f"synced to Linear project \"{project}\":\n{lines}\n"
        f"Read C:\\Users\\Eva Ng\\.claude\\skills\\synclinear\\SKILL.md and follow it."
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
        print(json.dumps(build_reminder(repo_root, config, commits)))
    except Exception:  # noqa: BLE001 — a Stop hook must never crash the session
        return


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python C:\Users\Eva Ng\.claude\skills\synclinear\hooks\test_check_unsynced.py -v`
Expected: `OK` (4 tests pass)

- [ ] **Step 5: Save**

No git commit needed.

---

### Task 4: Register the Stop hook in settings.json

**Files:**
- Modify: `C:\Users\Eva Ng\.claude\settings.json` (read first — merge, do not replace; if it doesn't exist yet, create it with just this hooks block)

**Interfaces:**
- Consumes: the script path from Task 3 (`C:\Users\Eva Ng\.claude\skills\synclinear\hooks\check_unsynced.py`).
- Produces: nothing further downstream — this is the last task before SKILL.md.

This task follows the `update-config` skill's own verification workflow (dedup check, pipe-test, write, validate, prove it fires) rather than the plan template's TDD steps, since a settings.json hook isn't a unit you write a pytest for — it's an integration you prove works end-to-end.

- [ ] **Step 1: Read the existing settings file**

Run: read `C:\Users\Eva Ng\.claude\settings.json`. If it exists, check for a pre-existing `hooks.Stop` entry — if one already targets `check_unsynced.py`, stop and report (nothing to do); if one exists for something else, note it (this task adds alongside, never replaces the array).

- [ ] **Step 2: Pipe-test the raw command**

Stop hooks don't read meaningful stdin, so:

Run: `echo {} | python "C:\Users\Eva Ng\.claude\skills\synclinear\hooks\check_unsynced.py"`
Expected (from the current directory, which has no `.claude/synclinear.json`): no output, exit code 0.

- [ ] **Step 3: Merge the hook entry into settings.json**

Add (creating the file with this content if it doesn't exist, or merging into the existing `hooks` object if it does):

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python \"C:\\Users\\Eva Ng\\.claude\\skills\\synclinear\\hooks\\check_unsynced.py\"",
            "timeout": 15
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 4: Validate JSON syntax + schema**

Run: `jq -e '.hooks.Stop[] | .hooks[] | select(.type == "command") | .command' "C:\Users\Eva Ng\.claude\settings.json"`
Expected: exit 0, prints the command string. Exit 5 means the merge broke the file's JSON — fix immediately, a broken settings.json silently disables everything else in it too.

- [ ] **Step 5: Note the watcher caveat, don't try to prove live firing**

Per the `update-config` skill: Stop fires outside the current turn, so it can't be proven to fire from inside this same task the way a `PreToolUse`/`PostToolUse` hook can. Tell Eva it's written and validated, and that if it doesn't seem to trigger on her next session, the fix is `/hooks` (reloads config) or a restart — this implementer cannot open `/hooks` itself.

---

### Task 5: SKILL.md — the sync-flow instructions

**Files:**
- Create: `C:\Users\Eva Ng\.claude\skills\synclinear\SKILL.md`

**Interfaces:**
- Consumes: nothing programmatically — this is the file `check_unsynced.py`'s reminder (Task 3) tells Claude to read. Its content IS the deliverable; there's no code to test here, per DESIGN.md's own call that the commit-to-ticket judgment stays LLM-driven, not hard-coded.

This is the one task in this plan that is instructions, not code — write the complete file below verbatim (fill in nothing further; this is the actual content, not a placeholder):

- [ ] **Step 1: Write the file**

```markdown
---
name: synclinear
description: Sync a git repo's commit history into its Linear project — propose new tickets and Done-transitions for existing ones, always with a review step before writing to Linear. Triggered automatically by a Stop hook reminder naming unsynced commits; can also be invoked directly by Eva.
---

# synclinear

You're reading this because either (a) a Stop-hook reminder told you there
are unsynced commits in the current repo, or (b) Eva asked you to sync
Linear directly.

## What "sync" means here

Every commit since `last_synced_commit` (in `.claude/synclinear.json`)
needs one of three outcomes:

1. **Closes an existing open Linear ticket** — propose marking it Done,
   with the commit hash(es) as evidence in the ticket description.
2. **A real deliverable with no existing ticket** — propose a new ticket,
   already Done, evidenced by the commit(s). Group multiple commits under
   one ticket when they're clearly one deliverable (matches this
   project's existing "[Block A] Outlook adapter" granularity, not one
   ticket per commit).
3. **Not ticket-worthy** — plan-doc-only edits, lint/CI fixes, a "Fix
   Task N plan" correction folded into the same task, a typo fix. No
   ticket. Still advances the sync marker (see below) — never
   re-propose these on the next run.

## The flow

1. Read `.claude/synclinear.json` in the current repo root for
   `linear_team`, `linear_project`, `last_synced_commit`.
2. `git log --oneline <last_synced_commit>..HEAD` (full messages: drop
   `--oneline` and read the real commit bodies, not just subject lines —
   you need the detail to judge ticket-worthiness the way this project's
   own commits were judged when the first 32 tickets were built).
3. `list_issues` (Linear MCP) scoped to `linear_project`, states other
   than Done/Canceled/Duplicate — these are the tickets a commit might
   close.
4. For each commit or commit-cluster, decide outcome 1, 2, or 3 above.
5. Print the full proposal as a plain-text list — **this is the review
   gate. Do not call any Linear MCP write tool before this step and
   Eva's reply.** Format:
   ```
   Proposed Linear sync (N commits, M ticket changes):

   - STU-125 -> Done (evidence: <sha> <subject>)
   - NEW: "[Block C] <title>" -> Done (evidence: <sha> <subject>, <sha> <subject>)
   - (no ticket) <sha> <subject> — <one-line reason it's not ticket-worthy>
   ```
6. Wait for Eva's reply. She may say OK, edit specific lines, or reject
   the whole thing. Only apply what she approved.
7. Apply approved changes via `save_issue` (mark Done + append evidence
   to the description for existing tickets; create + immediately mark
   Done for new ones — same pattern used for the first 32 tickets in
   "[Studio] Project Ironman").
8. Update `.claude/synclinear.json`'s `last_synced_commit` to the new
   `HEAD` (use `config.save_config` from
   `C:\Users\Eva Ng\.claude\skills\synclinear\lib\config.py`, or write
   the JSON directly — either way, this MUST happen even for a run where
   every commit landed in the "not ticket-worthy" bucket, so those
   commits are never re-proposed).

## First-time setup for a new repo

If `.claude/synclinear.json` doesn't exist yet and Eva asks you to set
this up for a repo: ask which Linear team and project it maps to (use
`list_teams` / `list_projects` to show her real options, don't guess),
then `save_config` with `last_synced_commit` set to the repo's current
`HEAD` (so the first real sync only covers commits from this point
forward — do not try to backfill the entire history automatically; that
was a one-off, manually-confirmed exercise the first time, not something
this skill should redo unprompted for a new repo).

## Errors

- Linear MCP tools not available when you reach step 3 → say so plainly,
  stop. Don't guess at ticket state.
- A commit is ambiguous (fits two open tickets, or half-fits one) →
  surface the ambiguity as its own line in the step-5 preview rather than
  picking silently. That's what the review gate is for.
```

- [ ] **Step 2: Save**

No test to run — confirm the file exists at the path above and read it back once to check it's not truncated.

---

## Self-Review

**Spec coverage:** DESIGN.md's three components (config file, Stop hook, sync flow) map to Tasks 1-2 (config + git plumbing), 3-4 (hook script + registration), and 5 (SKILL.md) respectively. The design's Testing section ("throwaway test repo") is Task 2/3's approach exactly. The out-of-scope items (time log automation, unattended Linear writes) are not built anywhere in this plan — confirmed no task does either.

**Placeholder scan:** no TBD/TODO left; SKILL.md's content is the actual file content, not a description of what it should contain.

**Type consistency:** `load_config`/`save_config` signatures in Task 1 match their only other use (Task 3's `check_unsynced.py` import, and SKILL.md's step 8 reference) exactly. `find_repo_root`/`unsynced_commits` from Task 2 match Task 3's usage.
