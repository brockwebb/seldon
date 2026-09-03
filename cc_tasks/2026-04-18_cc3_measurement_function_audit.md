# CC Task: Measurement-Function Audit

**Date:** 2026-04-18
**Project:** Seldon (`/Users/brock/Documents/GitHub/seldon/`)
**Parent ResearchTask:** `38b0698b` (Evolution Burst 2026-04 Plan Anchor)
**Spec ResearchTask:** `e5af26f8`
**Scope:** Evolution burst 2026-04 — CC3 of 5

---

## Goal

For every currently-installed enhancement, skill, MCP tool, or pipeline gate in the stack, answer three questions honestly:

1. **What outcome does it claim to improve?**
2. **How would we know if it is working?**
3. **Do we currently know if it is working?** — yes / no / no-idea.

Feynman principle applied outward: cannot improve what is not measured, cannot claim value for what cannot be verified. This audit feeds the Phase C kill list — components with no measurement function AND no qualitative evidence of value are kill candidates.

**Diagnostic only. No remediation. No changes to any component.**

---

## Prerequisites

1. CC2 (`2026-04-18_cc2_infrastructure_state_of_play.md`) has completed OR is completing in parallel. This task cross-references CC2's inventory — if CC2 is not done first, note that and proceed with the list in Step 1 below; do not block.
2. Output directory already created by CC2: `/Users/brock/Documents/GitHub/seldon/docs/design/evolution_burst_2026-04/`. If it doesn't exist, `mkdir -p` it.
3. `.env` loaded: `source /Users/brock/Documents/GitHub/seldon/.env`.

---

## Steps

### 1. Build the inventory

The inventory MUST include at minimum:

- **mv2 memory skill** — Rust-based memory skill
- **Seldon ontology master/replica sync** — `seldon ontology ingest` / `seldon ontology sync` (AD-017)
- **AD-019 Agentic Content Audit** — auditor subagent pipeline
- **AD-020 Multi-Lens Review** — cascade-checker, reviewer stress test, gate calibration
- **Seldon MCP tools** — `seldon_go`, `seldon_task_create/update/close/list`, `seldon_issue_create/update`, `seldon_cc_register/complete`, `seldon_query`
- **Claude skills** — every skill in `~/.claude/skills/` and any project-local `skills/` directories
- **Wintermute MCP** — if running per CC2
- **claude-mem** (thedotmack) — if installed per CC2
- **Perplexity-verification external loop** — the citation-fact-check pattern used on SFV
- **Seldon core CLI commands** — `seldon verify`, `seldon paper audit`, `seldon paper sync`, `seldon paper build`, `seldon docs check`

Add any other enhancement/skill/tool discovered in CC2 or encountered in the repo's `cc_tasks/`, `skills/`, or `docs/design/` directories.

For discovery:

```bash
ls -la ~/.claude/skills/ 2>/dev/null
find /Users/brock/Documents/GitHub/seldon/ -type d -name 'skills' -o -name 'agents' 2>/dev/null | head -20
find /Users/brock/Documents/GitHub/seldon/docs/design/ -name 'AD-*' -type f 2>/dev/null | xargs grep -l 'enhancement\|skill\|gate\|audit' 2>/dev/null | head -20
```

Cross-reference against `/Users/brock/Documents/GitHub/seldon/docs/design/evolution_burst_2026-04/cc2_infrastructure_state_2026-04-18.md` once it exists.

### 2. For each inventory item, fill the matrix

Four columns:

| Component | Claimed improvement | Measurement function | Do we know it works? |
|---|---|---|---|

**Column 2 ("Claimed improvement")** — one sentence. What outcome is this component supposed to produce? Source the claim — AD number, README, conventions doc, or "unstated, inferred from use."

**Column 3 ("Measurement function")** — how would we detect working vs not-working? Concrete signals:
- Specific metric (e.g., "citation error rate", "glossary violation count per section")
- Specific observable behavior (e.g., "CC task produces YAML that parses")
- Specific comparison (e.g., "audit-pipeline-on vs audit-pipeline-off error rates")

If no measurement function exists, write: **"NONE — would need to build"** and name what would need to exist.

**Column 4 ("Do we know it works?")** — exactly one of:
- **Yes, measured** — we have numbers
- **Yes, qualitative evidence** — no numbers but clear qualitative signal (e.g., "caught X real issue in SFV audit")
- **No, but should be measurable** — measurement function exists per column 3, we just haven't run it
- **No idea** — no measurement function, no qualitative evidence
- **Known broken** — evidence it isn't working

Short note in the cell explaining the basis for the verdict.

### 3. Identify cross-component measurement dependencies

Some components' measurement depends on other components. Call these out:

- AD-019 auditor quality depends on AD-020 cascade-checker working
- Ontology sync working depends on Seldon verify running
- Etc.

One short subsection: "Measurement dependency chains." Two-level chains at most; don't over-engineer.

### 4. Write the analysis paragraph

One paragraph at the end, naming:

- **Count: components with no measurement function at all** — N of M total
- **Count: components claiming improvements we cannot verify** — N of M
- **Biggest measurement gap** — one specific item where the absence of measurement is most consequential
- **Easiest measurement win** — one component where building the measurement function would be cheap and high-value

These four items feed directly into Phase C's kill list and 75/15/10 roadmap.

### 5. Write the deliverable

**Output path:** `/Users/brock/Documents/GitHub/seldon/docs/design/evolution_burst_2026-04/cc3_measurement_function_audit.md`

Structure:

```markdown
# CC3: Measurement-Function Audit — 2026-04-18

**Date:** 2026-04-18
**Executor:** Claude Code session
**Purpose:** For Phase C evolution burst synthesis. Kill-list input.

## Matrix

| Component | Claimed improvement | Measurement function | Do we know it works? |
|---|---|---|---|
| mv2 memory skill | ... | ... | ... |
| (one row per component)

## Per-component notes

Short section per component with full context: source of the claim, detail on the measurement function, evidence basis for the verdict. Anything that didn't fit in a table cell.

## Measurement dependency chains

(brief — 3–5 chains max)

## Analysis

- Components with no measurement function: N of M
- Components claiming unverifiable improvements: N of M
- Biggest measurement gap: <component> — <why>
- Easiest measurement win: <component> — <why>

## Honest unknowns

Any inventory item where even "do we know it works?" is itself unknown.

## Questions for Brock

Where Brock's context would resolve an ambiguity.
```

### 6. Register deliverable and close

```bash
cd /Users/brock/Documents/GitHub/seldon/
seldon cc complete cc_tasks/2026-04-18_cc3_measurement_function_audit.md
```

Also close the spec ResearchTask:

```bash
# MATCH (a:ResearchTask {artifact_id: 'e5af26f8-19f2-4f75-a129-8996356297e5'})
# SET a.state = 'completed'
# via seldon CLI or cypher
```

Commit:

```bash
git add docs/design/evolution_burst_2026-04/cc3_measurement_function_audit.md
git add cc_tasks/2026-04-18_cc3_measurement_function_audit.md
git commit -m "cc3: measurement-function audit"
```

---

## Success Contract

**Deliverables:**
1. `docs/design/evolution_burst_2026-04/cc3_measurement_function_audit.md` exists, with matrix covering all 10 minimum-required components plus any discovered in CC2 or during inventory discovery.
2. Every row has all four columns filled (no blanks; use "NONE" or "No idea" explicitly).
3. Analysis paragraph includes all four named numerics/verdicts.
4. Graph reflects completion: CC task file marked complete, spec ResearchTask `e5af26f8` transitioned to `completed`.
5. Git commit exists.

**Verification commands:**
```bash
# Deliverable exists
ls -la /Users/brock/Documents/GitHub/seldon/docs/design/evolution_burst_2026-04/cc3_measurement_function_audit.md

# Minimum row count: 10 mandatory + header/separator
grep -c '^|' /Users/brock/Documents/GitHub/seldon/docs/design/evolution_burst_2026-04/cc3_measurement_function_audit.md
# Expect: >= 12

# No empty cells in matrix
grep -E '^\|[^|]*\|[^|]*\|[^|]*\|[[:space:]]*\|[[:space:]]*$' /Users/brock/Documents/GitHub/seldon/docs/design/evolution_burst_2026-04/cc3_measurement_function_audit.md
# Expect: no output (no row ending with empty last column)

# Graph reflects completion
cd /Users/brock/Documents/GitHub/seldon/
seldon verify --quiet && echo OK || echo FAIL
```

**Scope boundaries (DO NOT do these):**
- Do NOT propose measurement functions for components that lack them — that's Phase C's job. Just record that the measurement function is missing.
- Do NOT run any component to test it. This is audit by inspection, documentation review, and cross-reference against existing evidence (SFV audit results, prior handoffs, etc.). Do not invoke `seldon paper audit` or any pipeline fresh for this task.
- Do NOT recommend kill candidates. Your job is to produce the honest verdict per row. The synthesis is Brock's.
- Do NOT expand a single component into multiple rows unless they have genuinely distinct measurement profiles. `seldon paper audit` Tier 1 vs Tier 2 vs Tier 3 CAN be three rows if they have distinct measurement stories; `seldon_task_create` and `seldon_task_update` are ONE row (the MCP tool surface as a whole).
- Do NOT hedge with "partially working" or "sort of measured" — force a choice among the five verdict options. Use the notes cell for nuance.

**Assumptions:**
- CC2 has run OR is running. If neither, the inventory in Step 1 is the floor; note which items could not be verified as actually present.
- Some components ("Perplexity-verification external loop") are workflows rather than installed software. Include them anyway — a workflow has a claimed improvement and can have a measurement function.
- If AD documents reference measurement functions that were never built (spec vs implementation gap), flag in the per-component notes.

---

## What this feeds into

- **Phase C kill list**: rows with "No idea" or "Known broken" are kill candidates if no qualitative evidence supports them.
- **Phase C 75/15/10 roadmap**: "Easiest measurement wins" become candidate high-ROI items (75% bucket). Measurement-function buildouts with long lead time become 15% bucket items.
- **Candidate AD-024 (Observability)**: this matrix IS the initial ObservabilityRegistry. CC4's dashboard implements the metric side; this document is the measurement-function spec side.

If every row says "No idea," we have been shipping vibes. If most rows say "Yes, measured," we have an observability foundation worth building on. The honest result is probably somewhere in between — and knowing where specifically is the point.

---

*End of CC3 task spec.*
