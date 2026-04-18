# CC Task Template: TEVV Verification Audit

**Template version:** 1.0
**Date:** 2026-04-05
**Relates to:** AD-020, regression audit loop design note
**Proven on:** Ch 9 (run-002, `afbccb41`), Ch 8 (run-002, `5844863d`)

---

## Instructions

Copy this template. Replace all `{{PLACEHOLDER}}` values. The resulting CC task is the specification for a single TEVV verification audit of one chapter.

---

# TEVV Verification Audit — {{CHAPTER_NAME}}

**Date:** {{DATE}}
**Project:** {{PROJECT}} (`{{PROJECT_DIR}}`)
**Baseline run:** `{{BASELINE_RUN_DIR}}`  (e.g., `audits/run-001_2026-04-05`)
**Output run:** `{{OUTPUT_RUN_DIR}}`  (e.g., `audits/run-002_2026-04-06`)
**Chapter file:** `{{CHAPTER_PATH}}`  (e.g., `book/chapter-09.md`)

## Objective

Re-audit `{{CHAPTER_NAME}}` after revision. Compare against the baseline discovery audit to measure resolution of prior findings, detect regressions, and assign a verdict.

## Prerequisites

- Baseline synthesis YAML exists: `{{BASELINE_RUN_DIR}}/{{CHAPTER_SLUG}}_review_synthesis.yaml`
- Chapter has been revised since the baseline audit
- `seldon paper sync` has been run after the revision
- Cross-chapter semantic anchor data is current (`seldon paper context` for all siblings)

## Gate Selection

Run these gates (per calibration analysis recommendations for TEVV verification):

1. **Content audit** — full assertion classification
2. **Practitioner stress test** — same 10 questions as baseline (regenerate if baseline didn't save questions)
3. **Cross-chapter cascade checks** — using semantic anchors from `seldon paper context`
4. **Review synthesis** — cluster findings, assign verdicts
5. **Delta summary** — compare against baseline

Skip unless the revision was structural:
- Bloom depth check
- Secondary sweep (narrative, visual, motivation, clarity)

## Execution Steps

### Step 1: Read baseline data

Read the baseline synthesis YAML in full:
```
{{BASELINE_RUN_DIR}}/{{CHAPTER_SLUG}}_review_synthesis.yaml
```

Read the baseline practitioner stress test YAML:
```
{{BASELINE_RUN_DIR}}/{{CHAPTER_SLUG}}_practitioner_stress_test.yaml
```

**Do not proceed without reading these files.** The delta summary depends on accurate baseline data.

### Step 2: Read revised chapter

Read the full chapter file: `{{CHAPTER_PATH}}`

### Step 3: Gather cross-chapter context

Run `seldon paper context` for each sibling chapter. Compress into a context block containing: `core_argument`, `claims`, `forward_promises`, `terminology_defined`, `open_threads` per sibling.

If semantic anchors are not populated for all siblings, note which chapters lack anchor data in the run manifest.

### Step 4: Run gates

Execute the selected gates in order: content audit → practitioner stress test → cascade checks → synthesis → delta summary.

For each gate, write output to:
```
{{OUTPUT_RUN_DIR}}/{{CHAPTER_SLUG}}_<gate_name>.yaml
```

### Step 5: Write delta summary

**CRITICAL — BASELINE SCORE COPYING RULE:**

Every baseline score in the delta summary must be copied verbatim from the baseline YAML file. Do NOT derive, recall, or estimate baseline scores from memory or from the revised chapter text.

For each score field in the delta summary, include a YAML comment identifying the source:

```yaml
score_comparison:
    practitioner_stress_test:
      # Copied verbatim from {{BASELINE_RUN_DIR}}/{{CHAPTER_SLUG}}_practitioner_stress_test.yaml summary block
      baseline: "X fully / Y partial / Z not"
      current: "..."
      delta: "..."
```

This rule exists because of a confirmed T2 (False State Injection) error in the Ch 9 TEVV verification, where the auditor recalled baseline scores from a contaminated thread instead of reading the file. The wrong baseline produced a false improvement signal.

Write the delta summary to:
```
{{OUTPUT_RUN_DIR}}/{{CHAPTER_SLUG}}_delta_summary.yaml
```

### Step 6: Write run manifest

Write or update the run manifest at `{{OUTPUT_RUN_DIR}}/run_manifest.yaml` with:

```yaml
run_manifest:
  run_id: "{{RUN_ID}}"
  date: "{{DATE}}"
  run_type: "tevv_verification"
  model: "{{MODEL}}"
  pipeline: "AD-020 manual Phase 1"
  baseline_run: "{{BASELINE_RUN_DIR}}"
  chapters_audited:
    - {{CHAPTER_SLUG}}
  gates_run:
    - content_audit
    - practitioner_stress_test
    - cascade_results
    - review_synthesis
    - delta_summary
  cross_chapter_context: "{{CONTEXT_DESCRIPTION}}"
  notes: "{{NOTES}}"
```

### Step 7: Verify and complete

```bash
seldon verify --strict
seldon cc complete {{CC_TASK_FILEPATH}}
```

## Delta Summary Schema

The delta summary must include:

1. **`cluster_resolution`** — For each baseline cluster: resolution status (`resolved`, `partially_resolved`, `still_open`), evidence of resolution, remaining gaps.

2. **`score_comparison`** — For each measurable metric: baseline value (copied verbatim from file), current value, delta, interpretation. Minimum metrics:
   - Practitioner stress test scores
   - Bloom ceiling and floor
   - Citation count and external citation rate
   - Visual element count
   - Reflection prompt count
   - Word count
   - Canonical baseline compliance (if applicable)
   - Cascade check results

3. **`new_findings`** — Issues not present in the baseline audit. These indicate either regressions or areas the original audit missed.

4. **`verdict`** — One of:
   - `improved` — measurable progress on key metrics, majority of HIGH/MEDIUM findings resolved
   - `stable` — no regression, targeted fixes only, structural profile unchanged
   - `regressed` — new issues introduced or prior findings worsened
   - `insufficient` — revision did not address the primary findings

5. **`verdict_rationale`** — 2-3 sentences explaining the verdict. Include the previous and new submission-equivalent assessment (e.g., `revise_before_use → conditionally_ready`).

## Known Pipeline Risks

- **T2 (False State Injection):** The auditor may recall scores from a prior conversation thread instead of reading the baseline file. The verbatim-copy rule with source comments mitigates this.
- **Single-model feedback loop:** Same model family for discovery and verification produces diminishing returns. For critical chapters, consider multi-model verification (Gemini/OpenRouter) as a future extension.
- **Resolution scoring subjectivity:** "Resolved" vs "partially resolved" is a judgment call. When uncertain, default to `partially_resolved` and list what would need to be true for `resolved`.
- **Audit does not consume resolution notes:** The audit re-evaluates the text as-is. If a finding was addressed in a way that doesn't change the chapter text (e.g., the author decided the current text is correct), the delta summary will report it as `still_open`. The author should note such decisions in a separate resolution log or in the CC task itself.

---

*Template version 1.0. Based on patterns proven in Ch 8 and Ch 9 TEVV verification runs (2026-04-05).*
