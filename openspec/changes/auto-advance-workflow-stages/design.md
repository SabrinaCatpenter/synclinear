## Context

synclinear's Stop hook (`hooks/check_unsynced.py`) already detects three
independent signals — unsynced commits (3a), a propose-ready OpenSpec
change with no Linear ticket (3b), and an archived change that might need
a client artifact (3c) — each via a pure detection function in
`lib/git_check.py` / `lib/openspec_check.py`, composed in `main()`, with
each finding rendered as its own paragraph in one combined
`additionalContext` string.

This proposal adds a fourth kind of detection to the same hook: gaps
between adjacent stages of the 7-step per-change cycle (explore → propose
→ brainstorm/grill → writing-plans → TDD → review → archive). Verified
this session: `openspec list --json` only lists *active* (non-archived)
changes — once `openspec archive <name>` runs, the change disappears from
`list --json` entirely (confirmed by a real archive round-trip in a
throwaway `openspec init`'d directory). This matters directly for Gap 3
below.

## Goals / Non-Goals

**Goals:**
- Detect three specific stalls in the 7-step cycle using only filesystem
  state (OpenSpec's own change status, plus the presence/absence of
  `docs/` and `docs/superpowers/plans/` files) — no new state machine, no
  explicit "current step" cursor.
- Fire each gap exactly once per change (persisted, like
  `known_openspec_changes`), phrased as a directive Claude acts on next
  turn, not a proposal awaiting approval.
- Stay purely additive to flows 3a/3b/3c — zero behavior change to
  existing signals or their review-gated writes.
- Work identically for any MLAI colleague's Studio-team project — no
  Ironman-specific paths, names, or assumptions.

**Non-Goals:**
- Not tracking "which of the 7 steps are we on" as an explicit state —
  only the three specific transition gaps below are detected.
- Not auto-completing brainstorm, writing-plans, TDD, or review content —
  the directive only tells Claude to *begin* the next stage; everything
  inside that stage that needs Eva's judgment still happens through
  ordinary conversation, same as it always has.
- Not detecting or enforcing the brainstorm⇄grill loop's internal
  back-and-forth — same exclusion DESIGN.md already carries for flow 3c's
  context (no reliable disk footprint for "mid-brainstorm" vs
  "not started").
- Not doing anything about a change with an incomplete proposal (no
  `tasks` artifact yet) — that's still stage 1-2 territory, no gap to
  detect there.

## Decisions

**Decision 1 — Three gaps, not a state machine.**
Considered: an explicit `current_stage` field per change (1 through 7),
updated as Claude progresses. Rejected: half the stages (explore,
brainstorm/grill mid-loop, review) have no reliable disk signal to
transition on, so the cursor would frequently be stale or require manual
correction — worse than not having one. Instead, three independent
boolean checks, each looking at a *pair* of artifacts:

| Gap | Condition | Means |
|---|---|---|
| 1 | OpenSpec change has `status != "no-tasks"` (proposal complete) AND no matching file under `docs/` | brainstorm/grill hasn't produced its design doc |
| 2 | A `docs/` design doc exists AND no matching file under `docs/superpowers/plans/` | writing-plans hasn't run yet |
| 3 | OpenSpec change has `status == "complete"` (all tasks checked) AND it still appears in `list_changes()` (i.e., not yet archived — confirmed archived changes drop out of `list --json` entirely) | review + archive still pending |

Each gap is evaluated independently per active change; a repo can have
zero, one, or several changes each triggering zero or more gaps
simultaneously — same "never merge findings" rule as 3a/3b/3c, each gets
its own paragraph.

**"Matching file under docs/" — how matching works.** Considered exact
filename derivation from the change name (e.g. `add-widget` →
`docs/add-widget*.md`). Rejected as too rigid — DESIGN.md's own docs/
convention allows a design doc to live in a feature folder, a subfolder,
or be organized by a name that doesn't exactly echo the OpenSpec change's
kebab-case name. Instead: Gap 1/2 checks are **conservative** — they only
fire when `docs/` (or `docs/superpowers/plans/`) has had **no new file
created or modified since the OpenSpec change's `lastModified`
timestamp** (from `list_changes()`). This avoids false positives (a
differently-named design doc that genuinely was written still suppresses
the gap) at the cost of occasionally missing a real gap (if Eva names a
file in a way that happens to predate the change's timestamp for
unrelated reasons) — the acceptable direction to err in, since a missed
reminder just means Eva proceeds as she already does today (no
regression), while a false reminder is actively annoying (this is a
directive, not a dismissible suggestion).

**Timestamp source — grilled and revised.** The first draft of this
decision used `os.path.getmtime()` (filesystem mtime) to compare a
`docs/`/`plans/` file's freshness against the change's `lastModified`.
Verified empirically this session (a real `git clone` round-trip in a
throwaway repo): git does **not** preserve original commit timestamps as
file mtimes — every file's mtime becomes the moment of the `clone` or
`checkout`, regardless of when it was actually committed. Since this tool
ships to colleagues who will `git clone` their own project repos, this
bug would fire on effectively every fresh clone, not as an edge case.
**Revised:** use `git log -1 --format=%ct -- <path>` (the file's real last
commit time) instead of filesystem mtime, for any file that's actually
tracked and committed. For a file that exists but isn't tracked/committed
yet (a `git log` on it returns nothing) — the untracked case can't have
been affected by a clone, so filesystem mtime is safe and correct there;
fall back to it only in that case.

**Decision 2 — Directive phrasing, reusing `context_usage_handoff.py`'s
pattern.** Flows 3a/3b/3c's reminder paragraphs are phrased as "here's
what I found, read SKILL.md and follow it" — SKILL.md's own flow text
then walks Claude through a review-gated proposal. Gap directives skip
straight to instructing action: "Gap 1 detected for change `<name>` — the
proposal is complete but no design doc exists. Begin the brainstorm/grill
stage now: invoke `superpowers:brainstorming`, per the 7-step cycle." This
mirrors `context_usage_handoff.py`'s "this is a DIRECTIVE, not a
suggestion" framing (built earlier this session for the same reason: some
things don't need a confirm-before-acting checkpoint).

**Decision 3 — Persistence field shape.** New config field
`advanced_workflow_gaps: list[str]`, each entry a gap signature string
like `"<change-name>:gap1"`. Chosen over three separate lists (one per
gap) to keep `config.py`'s schema additions minimal and mirror
`known_openspec_changes`'s existing "flat list of strings, append-only,
never pruned" pattern (same rationale as that field: a stale entry is
harmless, a pruned-then-reappearing entry risks a false "never seen
before").

**Decision 4 — `lib/openspec_check.py` needs one addition, not a
rewrite.** `list_changes()` already returns everything Gap 1/3 need
(`name`, `status`, `lastModified`). Gap 2 needs the *design doc's own*
last-commit time (to compare against the plan directory), which isn't an
OpenSpec concern at all — that's answered by a small new helper (git-log
lookup with the untracked-file mtime fallback from the timestamp-source
revision above) added directly in `hooks/check_unsynced.py`, not
`openspec_check.py` — it has nothing to do with OpenSpec state.
Net: zero changes to `lib/openspec_check.py` — fully reused as proposed.

**Decision 5 — Directive tone is judgment-aware, not blindly imperative
(grilled and revised).** Three scenarios surfaced during grilling where a
literal "begin the next stage now" directive would misfire:
1. Eva is mid-conversation on something unrelated to the change that
   triggered the gap — barging in with "begin brainstorming now" would be
   a jarring, out-of-context interruption.
2. Eva genuinely wants to redo an already-"advanced" stage (e.g. deleting
   a design doc to rewrite it) — the gap signature is already recorded
   and won't re-fire on its own; nothing currently un-hangs it.
3. Gap 3 fires purely off `tasks.md` checkboxes, which Claude itself sets
   during TDD — that's a different fact from "Eva has actually reviewed
   this." If review already happened earlier in the same conversation
   (Eva said "looks good" right before the last checkbox got checked),
   the directive would still show up next Stop and ask Claude to
   re-present the work for review, which is a pointless repeat.

None of these change the detection logic — they change how SKILL.md
instructs Claude to *act* on a fired directive. Each becomes an explicit
instruction in the new SKILL.md section (see tasks.md 3.1):
judge whether now is a reasonable moment to act on it (if not, mention it
briefly and defer rather than derailing unrelated work in progress); if
Eva mentions redoing a stage, proactively remove the corresponding
signature from `advanced_workflow_gaps`; and before presenting Gap 3's
"please review" step, check whether that review already happened earlier
in the current conversation — if so, skip straight to asking whether to
archive now.

## Risks / Trade-offs

- **[Risk]** A directive that fires while Claude is mid-conversation on
  something unrelated could feel intrusive (unlike 3a/3b/3c, which just
  wait for Eva to ask). **[Mitigation]** Decision 5 — SKILL.md instructs
  Claude to judge the moment before acting on a directive, deferring
  briefly rather than derailing unrelated work.
- **[Risk]** The timestamp-based "matching file" heuristic (Decision 1,
  revised) can miss a real design doc that predates the change's
  `lastModified` for unrelated reasons (e.g. Eva wrote it, then went back
  and edited the proposal). **[Mitigation]** Deliberately erring toward
  under-firing (see Decision 1) — a missed gap costs nothing beyond
  today's status quo; explicitly documented as a known limitation in
  SKILL.md's new section, not silently swallowed.
- **[Risk]** Once a gap signature is recorded as "advanced," it never
  fires again for that change — if Eva genuinely reverts progress (e.g.
  deletes a design doc to redo it), Gap 1 won't re-fire, and this is easy
  to not notice (the mechanism just goes quiet, same as any other missed
  signal). **[Mitigation]** Accepted, same trade-off as
  `known_openspec_changes` — but Decision 5 adds one concrete backstop:
  SKILL.md instructs Claude to proactively clear the relevant signature
  whenever Eva mentions redoing a stage, rather than leaving it as a
  silent dead end she has to notice and ask about herself.
- **[Risk]** Gap 3 fires off `tasks.md` checkbox state, which is a fact
  about implementation completeness, not about whether Eva has actually
  reviewed the work — a naive reading could make it seem like the
  directive is asking Claude to skip straight to archiving without
  review. **[Mitigation]** The directive's content was always "present
  for review, then archive once approved," never "archive directly" — no
  change needed there. Decision 5 adds one refinement: if that review
  already happened earlier in the same conversation, don't re-ask Claude
  to re-present the work — go straight to "review's done, archive now?"

## Migration Plan

No migration — purely additive. Existing repos with `.claude/synclinear.json`
missing the new `advanced_workflow_gaps` field will fail `load_config`
validation the same way they did for v2's two new fields (Task 1's
precedent) — the deployed Ironman config needs the same one-line patch
during implementation, same as before.

## Open Questions

None outstanding — all resolved during explore/brainstorming with Eva
this session.
