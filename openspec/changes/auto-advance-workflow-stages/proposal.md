## Why

synclinear's Stop hook currently detects three things: unsynced git
commits (flow 3a), an OpenSpec proposal ready for a Linear ticket (flow
3b), and an archived OpenSpec change that might need a client artifact
(flow 3c). It has no awareness of the 7-step per-change development
cycle itself (explore → propose → brainstorm/grill → writing-plans → TDD
→ review → archive) — that sequence only exists as background prose in
DESIGN.md, which Claude doesn't read proactively. The result: Eva has to
re-explain the whole workflow by hand at the start of every project,
because nothing actually remembers the sequence or nudges Claude to keep
moving through it.

## What Changes

- Add three new gap checks to the Stop hook, each detecting a stall
  between two adjacent stages of the 7-step cycle:
  - **Gap 1**: an OpenSpec change's proposal is complete (its `tasks`
    artifact exists) but the repo's `docs/` tree has no corresponding
    design doc yet → the brainstorm/grill stage hasn't produced its
    artifact.
  - **Gap 2**: a design doc exists in `docs/`, but
    `docs/superpowers/plans/` has no corresponding implementation plan →
    the writing-plans stage hasn't happened yet.
  - **Gap 3**: an OpenSpec change's `tasks.md` is fully checked off, but
    the change hasn't been archived → review and archive are still
    pending.
- Each gap fires once per change (tracked via a new persisted set in
  config, same pattern as `known_openspec_changes`), not on every Stop
  event.
- **BREAKING (behavioral, not schema):** unlike flows 3a/3b/3c, these new
  gap reminders are phrased as directives for Claude to act on
  immediately next turn, not proposals awaiting Eva's go-ahead. Advancing
  to the next *stage* of an already-agreed-upon workflow doesn't need a
  fresh approval each time; only the content decisions inside that stage
  (what the design says, whether review passes) still involve Eva
  directly, through ordinary conversation — the directive doesn't skip
  that, it just skips a redundant "should I start?" checkpoint in front
  of it.
- No changes to flows 3a/3b/3c's own review-gated behavior — this is
  additive.

## Capabilities

### New Capabilities

- `workflow-stage-advancement`: detects the three gaps above and directs
  Claude to begin the next stage of the 7-step cycle, reusing
  `lib/openspec_check.py` for OpenSpec state and adding filesystem checks
  for `docs/` and `docs/superpowers/plans/`.

### Modified Capabilities

(none — flows 3a/3b/3c's specs, if any existed, are unchanged by this
proposal; config.py's schema gains one new field, but that's an
implementation detail of the new capability, not a change to an existing
capability's requirements)

## Impact

- `lib/config.py`: one new persisted field (a set/list of "gap
  signatures already advanced") analogous to `known_openspec_changes`.
- `hooks/check_unsynced.py`: three new detection functions plumbed into
  `main()` alongside the existing three signals; new paragraphs use
  directive phrasing distinct from flows 3a/3b/3c.
- `SKILL.md`: new sections documenting how Claude should respond to each
  gap directive (what "begin the next stage" concretely means per gap).
- `lib/openspec_check.py`: reused as-is if its existing return shape
  covers what's needed; extended only if a genuine gap in what it exposes
  is found during design.
- No impact on any repo-specific configuration — this must work for any
  MLAI colleague's Studio-team project, not just Ironman.
