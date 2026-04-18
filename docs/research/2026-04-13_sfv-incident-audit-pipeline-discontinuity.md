# SFV Incident: Audit Pipeline State Discontinuity (T5)

**Date:** 2026-04-13
**Type:** Dogfooding incident — SFV threat observed in SFV paper's own production pipeline
**Threat:** T5 (State Discontinuity)
**Sub-dimensions affected:** Process Reproducibility (PR), State Coherence (SCoh)
**Severity:** High — 11 paper sections drafted without citation enforcement or audit gates

---

## What Happened

The ai-workflow-design book project developed a rigorous 6-gate audit pipeline over four runs (run-001 through run-004), covering 14 chapters and 119 output files. The pipeline included content audits, Bloom depth checks, practitioner stress tests, cascade verification, secondary sweeps, and review synthesis — all producing structured YAML with a run manifest.

When the SFV paper project (brock_projects/sfv-paper) was initialized, none of the pipeline knowledge transferred. The new project's `seldon.yaml` was bare — no `paths`, no `conventions`, no `review` configuration. The `CLAUDE.md` had no citation rules. Agent symlinks weren't set up.

Result: 11 paper sections were drafted in CC sessions that had no awareness of citation conventions, no audit gates to run, and no run manifest to maintain. The "no bare prose citations" rule that was enforced in ai-workflow-design simply didn't exist in the new project. Nobody flagged it because there was nothing to flag against.

## Where the Knowledge Lived (and Died)

| Knowledge | Where it was in ai-workflow-design | Where it was in brock_projects |
|-----------|-----------------------------------|-------------------------------|
| 6-gate sequence | Manually-written per-chapter CC tasks | Nowhere |
| Run manifest format | `audits/run-NNN_YYYY-MM-DD/run_manifest.yaml` (by example, not by spec) | Nowhere |
| Citation conventions | CLAUDE.md §Citation Conventions | Nowhere |
| `seldon.yaml` paths + conventions | seldon.yaml (15 fields) | seldon.yaml (6 fields) |
| Gate calibration per document type | AD-020 design doc (in Seldon repo — technically accessible) | Not referenced |
| Agent symlinks | `.claude/agents/` → Seldon canonical | Not set up |
| Sweep synthesis pattern | `docs/YYYY-MM-DD_sweep_synthesis_runNNN.md` (by example) | Nowhere |

The gate definitions (AD-019, AD-020) and agent definitions (auditor.md, cascade-checker.md) were in the Seldon repo the whole time. The gap wasn't in the *components* — it was in the *orchestration*. Nobody told the new project's CC sessions that these components existed, in what order to run them, or what conventions to follow.

## Why It Wasn't Caught

The failure was silent. There was no error, no warning, no validation gate that said "you're drafting sections without citation conventions configured." The pipeline that would have caught it was the pipeline that was missing.

Seldon's `seldon go` command orients a CC session to a project. But `seldon go` reads `seldon.yaml` and `CLAUDE.md` — if those files are bare, the session starts bare. The system faithfully reproduced the configured state; the configured state was incomplete.

## Impact

- 11 SFV paper sections need retroactive citation audit
- Unknown number of bare prose citations to convert to proper markup
- No structured audit output exists for any section
- Time cost of remediation estimated at 2-3 CC sessions

The irony: this is a T5 incident in the production of a paper that defines T5. The paper's own pipeline suffered the exact threat the paper describes. The system designed to prevent state discontinuity had a state discontinuity in its own deployment process.

## Root Cause

Three layers of the audit/authoring pipeline exist. Only one was codified as portable Seldon infrastructure:

1. **Gate definitions** — codified (AD-019, AD-020, agent .md files)
2. **Pipeline orchestration** — not codified (gate sequence, run manifest format, sweep synthesis pattern, per-chapter CC task generation)
3. **Project conventions** — partially codified (in ai-workflow-design's project-specific files, not in Seldon-portable form)

The pipeline orchestration lived in session memory and in the accumulated CC task files from ai-workflow-design. It was *implicit* knowledge that became *explicit* only through repeated use — and then died at the project boundary because implicit knowledge doesn't transfer.

## Countermeasure

CC task `2026-04-13_ad022_codify_audit_pipeline.md` produces three artifacts:

1. `docs/conventions/audit_pipeline.md` — the missing orchestration layer
2. `docs/templates/seldon_yaml_template.yaml` — rich project config template so new projects aren't born bare
3. `docs/conventions/authoring_conventions.md` — portable authoring rules extracted from ai-workflow-design

A separate CC task (not yet written) will backport the conventions to brock_projects.

## Lessons

**Process knowledge that only exists in session memory is dead knowledge on a long enough timeline.** It doesn't matter how rigorous the process was — if it's not encoded in a form that transfers to a new session, a new project, or a new person, it will be reinvented or (more likely) skipped.

**Validation must be present at initialization, not just at audit time.** The audit pipeline catches problems after drafting. But the *absence* of the pipeline is itself a problem, and nothing catches that. A richer `seldon init` or a project config validator could flag "you have no citation conventions configured" before the first section is drafted.

**Components without orchestration are shelf-ware.** AD-019 and AD-020 are well-designed. The agent definitions work. But design docs that sit in a `docs/design/` directory don't execute themselves. The gap between "the system can do X" and "the system does X by default" is where process failures live.

**The project boundary is the most dangerous session boundary.** Within a project, handoff docs and `seldon briefing` maintain continuity. Across projects, there's no equivalent mechanism. The conventions, pipeline configuration, and accumulated process knowledge reset to whatever's in `seldon.yaml` and `CLAUDE.md` — and if those are bare, the reset is total.

---

*Filed as a research note for potential conference use and as a documented case study for the SFV paper's incident catalog.*
