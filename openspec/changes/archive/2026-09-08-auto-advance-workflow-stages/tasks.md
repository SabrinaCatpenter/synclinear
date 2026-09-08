## 1. Config schema

- [ ] 1.1 Add `advanced_workflow_gaps: list[str]` as a new required field
  in `lib/config.py`, validated the same way `known_openspec_changes` is
  (required list-of-strings)
- [ ] 1.2 Update `lib/test_config.py` fixtures and add tests for the new
  field (missing → None, wrong type → None, valid → round-trips)
- [ ] 1.3 Patch the deployed Ironman config
  (`C:\Users\Eva Ng\Desktop\ironman\repo\.claude\synclinear.json`) with
  `"advanced_workflow_gaps": []`

## 2. Gap detection functions

- [ ] 2.1 Add a shared helper `_file_timestamp(repo_root, path)` to
  `hooks/check_unsynced.py`: run `git log -1 --format=%ct -- <path>` in
  `repo_root`; if it returns a value, use it; if empty (untracked file),
  fall back to `os.path.getmtime(path)`. This exists specifically to
  avoid the mtime-after-clone bug found during design (verified via a
  real `git clone` round-trip: git does not preserve commit timestamps as
  file mtimes)
- [ ] 2.2 Add `_gap1_paragraph()`: for each entry from
  `openspec_check.list_changes()` with `status != "no-tasks"`, use
  `_file_timestamp()` on every file under `docs/` and check whether any
  is at or after the entry's `lastModified`; if none is, and the
  signature `"<name>:gap1"` isn't already in `advanced_workflow_gaps`,
  build a directive paragraph
- [ ] 2.3 Add `_gap2_paragraph()`: find the newest `_file_timestamp()`
  under `docs/` (excluding `docs/superpowers/plans/`); if it's newer than
  everything currently in `docs/superpowers/plans/` (or that directory
  doesn't exist), and the signature `"docs:gap2"` isn't already recorded,
  build a directive paragraph. (Gap 2 isn't per-OpenSpec-change like
  1/3 — it's a repo-wide docs-vs-plans staleness check, so its signature
  is a fixed literal, not a change name)
- [ ] 2.4 Add `_gap3_paragraph()`: for each entry from `list_changes()`
  with `status == "complete"`, if the signature `"<name>:gap3"` isn't
  already recorded, build a directive paragraph instructing Claude to
  present the work for review and archive once approved
- [ ] 2.5 Wire all three into `main()` alongside the existing three
  signals; each fired gap appends its signature to
  `advanced_workflow_gaps` and the updated config is saved via
  `config.save_config` before the hook exits
- [ ] 2.6 Write tests in `hooks/test_check_unsynced.py` for each gap:
  fires when the condition holds and the signature is new; stays silent
  when the signature is already recorded; stays silent when the
  underlying condition doesn't hold; multiple gaps firing together
  produce separate paragraphs (extend the existing
  `test_git_and_openspec_signals_produce_separate_paragraphs`-style test)
- [ ] 2.7 Write a test for `_file_timestamp()` specifically covering the
  clone-safety property: commit a file with an old `GIT_COMMITTER_DATE`,
  copy the repo to a fresh directory (simulating a clone — mtime becomes
  "now" but git history is preserved via `git log`), and assert
  `_file_timestamp()` returns the old committed time, not the copy's
  fresh mtime. Also test the untracked-file fallback path (new file, no
  commit yet → filesystem mtime is used).

## 3. Documentation

- [ ] 3.1 Add a new SKILL.md section documenting how Claude should
  respond to each gap directive — concretely, what "begin the next
  stage" means per gap (Gap 1 → invoke `superpowers:brainstorming`; Gap 2
  → invoke `superpowers:writing-plans`; Gap 3 → present completed work
  for Eva's review, then `/opsx:archive` once approved), AND the three
  judgment-aware behaviors from design.md's Decision 5:
  - defer briefly rather than derailing unrelated work in progress when a
    directive fires at an awkward moment
  - proactively clear a gap signature from `advanced_workflow_gaps` when
    Eva mentions redoing a stage whose gap already fired
  - before presenting Gap 3's "please review" step, check whether that
    review already happened earlier in the current conversation — skip
    straight to "archive now?" if so
- [ ] 3.2 Update SKILL.md's frontmatter `description` to mention this
  fourth mechanism alongside flows 3a/3b/3c
- [ ] 3.3 Update README.md if these gap directives are user-visible
  behavior worth documenting for colleagues adopting synclinear (confirm
  with Eva before writing — this affects the public tutorial's scope)

## 4. Verification

- [ ] 4.1 Run the full test suite (`lib/test_config.py`,
  `lib/test_git_check.py`, `lib/test_openspec_check.py`,
  `hooks/test_check_unsynced.py`) and confirm all pass, including the
  pre-existing tests for flows 3a/3b/3c (must show zero regressions)
- [ ] 4.2 Manually verify Gap 1/2/3 against a real throwaway OpenSpec
  change (same style as Task 3's manual field verification) rather than
  trusting the design doc's assumptions about `list_changes()`'s shape
  without a final check
