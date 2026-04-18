# Design Note: Hard-Threshold Gating for Mechanical QC Checks

**Date:** 2026-04-05
**Status:** Design
**Relates to:** AD-020 (Iterative Content Review Pipeline), AD-016 (Paper QC Severity Tiers), AD-018 (Document Structure Graph)
**Provenance:** Pattern extracted from Anthropic's harness engineering research (Rajasekaran, March 2026). Their evaluator uses per-criterion hard pass/fail thresholds — failure on any one criterion fails the sprint. Adapted here for Seldon's verify/review pipeline.
**note_type:** pattern_proposal

---

## 1. Context

Seldon's current QC pipeline has two enforcement layers:

1. **`seldon verify`**: Runs mechanical checks (content hashes, glossary compliance, cross-reference validity, PQ rules). Reports findings. Does not block state transitions.
2. **AD-020 gates**: Multi-lens review pipeline. Reports findings in a synthesis document. Author decides what to act on.

Both layers follow the "gates report, never edit" principle (AD-020 §1). This principle is correct for judgment-based findings — whether a paragraph is argumentative enough, whether a stress test question reveals a gap, whether cognitive scaffolding is adequate. These require author decision.

But some findings are not judgment calls. They are mechanical violations with no ambiguity:

- PQ-01 violation: sentence exceeds 30 words (the hard ceiling, not the 25-30 word warning)
- Glossary term used but not defined in glossary
- Content hash mismatch (file changed but graph not synced)
- Cross-reference to nonexistent section
- Required property missing on artifact

For these, "report and let the author decide" adds a manual step to something that has exactly one correct resolution: fix it. The question is whether Seldon should enforce this mechanically.

## 2. The Pattern: Tiered Gate Enforcement

Split QC findings into two enforcement tiers:

### Tier A: Hard Gates (Mechanical, Unambiguous)

These block state transitions automatically. If a PaperSection has a PQ-01 violation (>30 words), `draft → review` transition is rejected with the specific finding. The author must fix the violation and re-run verify before the transition succeeds.

**Candidates for hard gating:**

| Check | Rationale |
|-------|-----------|
| PQ-01 violation (>30 words) | Unambiguous mechanical threshold. The 25-30 word warning tier remains advisory. |
| Content hash mismatch | File and graph are out of sync. Proceeding with stale data is always wrong. |
| Cross-reference to nonexistent section | Broken link. No judgment required. |
| Glossary term undefined | Term used without definition. Mechanical check against glossary file. |
| Required property missing on artifact | Schema violation. |

### Tier B: Advisory Gates (Judgment Required)

These report findings but do not block transitions. The author reviews and decides. All AD-020 gates remain in this tier.

**Examples:**

| Check | Rationale |
|-------|-----------|
| PQ-01 warning (25-30 words) | Style preference, not violation. Author may have good reason. |
| PQ-09 staccato (3+ short sentences) | Stylistic — may be intentional for emphasis. |
| AD-020 stress test findings | Requires author judgment on whether to address. |
| Depth check (Bloom) findings | Pedagogical judgment. |
| Cascade checker findings | Cross-section impact requires author evaluation of blast radius. |

## 3. Implementation Options

### Option A: Verify as Transition Guard

Modify `transition_state()` in `core/artifacts.py` to call `seldon verify` on the artifact before allowing certain transitions. If Tier A violations exist, the transition is rejected with the violation list.

**Transitions that would be guarded:**
- `PaperSection: draft → review`
- `PaperSection: review → published`
- `Result: proposed → verified`

**Pros:** Enforcement is structural — can't be bypassed by accident. Fits the state machine model.
**Cons:** Couples the state machine to the verify pipeline. Adds latency to every transition. May be frustrating during rapid iteration.

### Option B: Verify with Exit Code

Modify `seldon verify` to return a non-zero exit code when Tier A violations exist. CC tasks and human workflows check the exit code. State transitions are not mechanically blocked, but the convention is enforced through the mandatory edit cycle (`check_glossary → paper sync → paper build --no-render`).

**Pros:** Simpler implementation. Doesn't change core engine. Enforced by convention + CC task templates.
**Cons:** Convention can be bypassed. A CC agent that doesn't check the exit code proceeds with violations.

### Option C: Verify Flag on Artifact

Add a `verify_clean: bool` property to PaperSection (and other verifiable types). `seldon verify` sets it to `true` when all Tier A checks pass, `false` when any fail. State transitions check the flag.

**Pros:** Decouples verify from transition timing. Verify can run anytime; transition checks a cached result.
**Cons:** Flag can go stale if content changes after verify but before transition. Adds a property that isn't really "documentation" — it's process state.

### Recommendation

**Option A for the long term, Option B as the immediate step.** Option B is implementable now — `seldon verify` already runs all the checks; it just needs to return meaningful exit codes and for CC task templates to enforce the check. Option A is the correct architecture but requires careful design of which transitions get guarded and how to handle the "rapid iteration" case where hard gating is friction rather than safety.

## 4. Edge Cases

1. **Override mechanism**: Even Tier A gates need an escape hatch. Sometimes a 31-word sentence is the right sentence. An `--override` flag on the transition command, with mandatory reason text logged to the event store, preserves both enforcement and author autonomy.

2. **Bulk operations**: Running verify on every artifact during a batch state transition (e.g., marking all sections as `review` after a revision pass) could be slow. Consider a `seldon verify --all` that runs once and caches results, with transitions checking the cache.

3. **Cross-artifact dependencies**: A glossary term violation in Section A might be caused by a term added in Section B that hasn't been synced to the glossary yet. The verify check should distinguish between "term used but not in glossary" (author's problem) and "term in glossary but not synced to graph" (tooling's problem).

## 5. What This Does NOT Change

- **Gates still report, never edit.** Hard gating blocks transitions; it doesn't auto-fix violations. The author still makes the fix.
- **AD-020 gates remain advisory.** Judgment-based findings are never hard-gated. The author decides what to act on.
- **The mandatory edit cycle remains.** `check_glossary → paper sync → paper build --no-render` is still the workflow. Hard gating adds a structural enforcement to what's currently a convention.

## 6. Metrics

After implementation, track:
- How often Tier A gates block transitions (high rate = good enforcement; very high rate = threshold may be wrong)
- How often overrides are used (high rate = threshold is probably wrong; low rate = enforcement is working)
- Time-to-fix for Tier A violations (should be fast since fixes are mechanical)

---

*This design note will be registered as a DesignNote artifact with `informs` edges to AD-020, AD-016, and AD-018.*
