## ADDED Requirements

### Requirement: Gap 1 detection (proposal complete, no design doc)
The system SHALL detect, per active OpenSpec change, when the change's
`tasks` artifact exists (i.e. `status != "no-tasks"` from
`list_changes()`) AND no file under the repo's `docs/` tree has a
last-commit time (via `git log -1 --format=%ct`) at or after that
change's `lastModified` timestamp. For a `docs/` file that isn't tracked
by git yet (no `git log` result), its filesystem mtime is used instead —
an untracked file can't have had its mtime rewritten by a clone/checkout,
so the filesystem timestamp is trustworthy in that specific case only.

#### Scenario: Proposal complete, design doc not yet written
- **WHEN** an OpenSpec change has a non-"no-tasks" status and no file
  under `docs/` has a (git-commit-time-or-untracked-mtime) timestamp at
  or after the change's `lastModified`
- **THEN** the Stop hook emits a directive paragraph naming the change
  and instructing Claude to begin the brainstorm/grill stage next turn

#### Scenario: Design doc already exists
- **WHEN** a file under `docs/` has a git-commit-time (or, if untracked,
  a filesystem mtime) at or after the change's `lastModified`
- **THEN** Gap 1 does not fire for that change

#### Scenario: Repo was freshly cloned
- **WHEN** every file under `docs/` is tracked and committed (so `git
  log` resolves a real historical commit time for each, not the
  clone/checkout moment)
- **THEN** Gap 1's timestamp comparison reflects true history, not the
  moment of the clone — this is the specific failure mode a filesystem-mtime-only
  implementation would have had (verified via a real `git clone`
  round-trip during design)

### Requirement: Gap 2 detection (design doc exists, no implementation plan)
The system SHALL detect, per repo, when at least one file under `docs/`
exists AND no file under `docs/superpowers/plans/` has a last-commit time
(or untracked-file mtime, same fallback rule as Gap 1) at or after that
design doc's own timestamp.

#### Scenario: Design doc written, plan not yet written
- **WHEN** a `docs/` file's timestamp postdates everything currently in
  `docs/superpowers/plans/` (or that directory doesn't exist yet)
- **THEN** the Stop hook emits a directive paragraph instructing Claude
  to begin the writing-plans stage next turn

#### Scenario: Plan already exists
- **WHEN** a file under `docs/superpowers/plans/` has a timestamp at or
  after the relevant design doc's timestamp
- **THEN** Gap 2 does not fire

### Requirement: Gap 3 detection (tasks complete, not archived)
The system SHALL detect, per active OpenSpec change, when
`completedTasks == totalTasks` and `totalTasks > 0` (i.e.
`status == "complete"` from `list_changes()`) — since `openspec list
--json` only returns active (non-archived) changes, any such entry is by
definition not yet archived.

#### Scenario: All tasks checked off, change still active
- **WHEN** `list_changes()` returns an entry with `status == "complete"`
- **THEN** the Stop hook emits a directive paragraph instructing Claude to
  present the completed work to Eva for review, and archive the change
  once she approves

#### Scenario: Change already archived
- **WHEN** a change has been archived via `openspec archive`
- **THEN** it no longer appears in `list_changes()`'s output, so Gap 3
  cannot fire for it

### Requirement: Each gap fires at most once per change
The system SHALL persist a record of which gap signatures (change name +
gap number) have already been directed, in `.claude/synclinear.json`'s
`advanced_workflow_gaps` list, and SHALL NOT re-emit a directive for a
signature already present in that list.

#### Scenario: Gap already directed once
- **WHEN** a gap signature (e.g. `"add-widget:gap1"`) is already present
  in `advanced_workflow_gaps`
- **THEN** the Stop hook does not emit that paragraph again, even if the
  underlying condition (proposal complete, no design doc) still holds

#### Scenario: New gap signature
- **WHEN** a gap fires for a signature not yet in `advanced_workflow_gaps`
- **THEN** the Stop hook emits the directive AND the signature is added
  to `advanced_workflow_gaps` (persisted via `config.save_config`)

### Requirement: Directive phrasing, not proposal phrasing
Gap paragraphs SHALL instruct Claude to begin the next stage immediately,
distinct from flows 3a/3b/3c's "here's a proposal, review before I write
anything" phrasing — because advancing to the next stage of an
already-agreed 7-step cycle is not itself a decision requiring Eva's
prior approval, only the content produced inside that stage is.

#### Scenario: Gap directive text
- **WHEN** any of Gap 1, 2, or 3 fires
- **THEN** the paragraph's wording directs immediate action ("begin X
  now") rather than awaiting a yes/no reply, while any content decisions
  inside that stage (design content, review pass/fail) still happen
  through ordinary conversation with Eva, unchanged from today

### Requirement: Directive judgment before acting
Claude SHALL, upon receiving a gap directive, judge whether the current
moment is reasonable to act on it before doing so: if Eva is clearly
mid-conversation on something unrelated to the change that triggered the
gap, Claude SHALL mention the pending gap briefly and defer rather than
derailing the unrelated work in progress.

#### Scenario: Gap fires during unrelated work
- **WHEN** a gap directive appears on the same turn Eva is deep in
  discussion of something unrelated to the change that triggered it
- **THEN** Claude briefly notes the pending gap and continues the current
  topic, rather than abruptly switching to begin the next stage

### Requirement: Manual signature reset on explicit redo
Claude SHALL, when Eva indicates she is redoing a stage whose gap
signature was already recorded in `advanced_workflow_gaps` (e.g.
mentioning she's rewriting a design doc that Gap 1 already fired for),
proactively remove that signature from the config so the gap can fire
again once the redo is complete.

#### Scenario: Eva redoes a stage
- **WHEN** Eva says she's redoing work whose gap signature is already in
  `advanced_workflow_gaps`
- **THEN** Claude removes that signature via `config.save_config` so the
  gap is eligible to fire again

### Requirement: Gap 3 skips redundant review presentation
Claude SHALL, upon receiving a Gap 3 directive, check whether Eva already
reviewed and approved the completed work earlier in the current
conversation before presenting it for review again; if review already
happened, Claude SHALL skip straight to asking whether to archive now.

#### Scenario: Review already happened this conversation
- **WHEN** Gap 3 fires and Eva approved the work earlier in the same
  conversation (before the last task checkbox was checked)
- **THEN** Claude asks directly whether to archive now, without
  re-presenting the work for review

#### Scenario: Review has not yet happened
- **WHEN** Gap 3 fires and no review occurred yet in the current
  conversation
- **THEN** Claude presents the completed work for Eva's review as
  originally specified

### Requirement: No behavior change to flows 3a/3b/3c
The system SHALL NOT alter the detection logic, output format, or
review-gate behavior of flows 3a, 3b, or 3c.

#### Scenario: Existing flows unaffected
- **WHEN** the Stop hook runs in a repo with unsynced commits and/or a
  propose-ready OpenSpec change and/or an archived change needing an
  artifact check
- **THEN** flows 3a/3b/3c behave identically to their pre-existing
  implementation, each still producing its own separate paragraph
