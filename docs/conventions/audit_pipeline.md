# Audit Pipeline — Orchestration Reference

**Type:** Convention document
**Reference:** AD-019 (Agentic Content Audit), AD-020 (Multi-Lens Review Pipeline)
**Scope:** How to run the pipeline, in what order, with what outputs. For design rationale, see the ADs.

---

## 1. Pipeline Overview

The audit pipeline is two ADs run in sequence:

- **AD-019 (Tier 1):** Correctness — claim classification, citation coverage, depth assessment, cross-section impacts
- **AD-020 (Tiers 2–3):** Comprehensiveness — practitioner utility, cognitive depth, narrative/clarity/visual/motivational framing

Both ADs share the same output philosophy: structured YAML findings, not prose reports. Findings are Issues and ResearchTasks in the graph — stateful, queryable, resolvable.

**For `book_chapter` type:** six gates run (see §2). Gate profile varies by document type (see §3).

Each gate produces structured YAML output. No gate edits prose. The author decides what to change.

---

## 2. Gate Sequence

Canonical order for `book_chapter` document type:

```
1. content_audit          → Tier 1 (AD-019): claim classification, citation coverage,
                            depth assessment, cross-section impacts
2. perplexity_queries     → Output artifact of gate 1, not a separate gate.
                            Generated from content_audit citation_gap findings.
3. practitioner_stress_test → Tier 2a (AD-020): can a practitioner answer real questions
                               from this material?
4. bloom_depth_check      → Tier 2b (AD-020): cognitive depth — does reader reach
                             Evaluate/Create?
5. secondary_sweep        → Tier 3 (AD-020): blended lens pass (narrative, clarity,
                             visual gaps, motivational framing)
6. cascade_results        → Cross-section impact verification. Spawns cascade-checker
                             agents per AD-019 §6. Can run in parallel with Tiers 2–3.
7. review_synthesis       → Synthesis engine: clusters findings by topic, orders by
                             convergence, produces actionable items per AD-020 §4
```

**Sequencing rules:**
- Gates 1–5 run sequentially.
- Gate 6 (cascade) can run in parallel with gates 3–5 via agent team (see §7.2).
- Gate 7 (synthesis) runs after all others complete.

---

## 3. Gate Calibration by Document Type

Document type is declared in `seldon.yaml` under `review.document_type` (see `docs/templates/seldon_yaml_template.yaml`).

### 3.1 Gate Profile by Type

| Gate | `academic_paper` | `book_chapter` | `blog_post` | `course_handout` | `policy_brief` |
|------|-----------------|----------------|-------------|-------------------|----------------|
| **Tier 1: Correctness** | Full — citations mandatory for every factual claim | Full | Light — higher common knowledge threshold | Moderate | Light citations, heavy accuracy |
| **Tier 2: Stress Test** | Reviewer 2 persona | Practitioner persona | Interested generalist | Student doing homework | Decision-maker with 10 minutes |
| **Tier 2: Depth Check** | Argument completeness (not Bloom) | Full Bloom — does reader reach Evaluate/Create? | Skip | Bloom is primary — scaffolding IS the point | Skip |
| **Tier 3: Narrative** | Argument arc | Story arc, hook, tension | Dominant concern | Light | Light |
| **Tier 3: Clarity** | Jargon audit | Yes | Yes | Dominant concern | Dominant concern |
| **Tier 3: Visual gaps** | Figures/tables/diagrams | Yes | Moderate | Critical | Light |
| **Tier 3: Motivational framing** | Light | Keller ARCS | Engagement dominant | Relevance to learning objectives | Relevance to decision |

**Skipped gates by type:**
- `blog_post`: skip bloom_depth_check
- `policy_brief`: skip bloom_depth_check

### 3.2 Lighter Profiles for Non-Chapter Content

| Document Pattern | Gates |
|-----------------|-------|
| `foreword` / `introduction` | content_audit_light + secondary_sweep (skip practitioner_stress_test, bloom_depth_check, cascade_results) |
| `reference_appendix` | content_audit_light + secondary_sweep (verify canonical lists match CLAUDE.md and seldon.yaml) |

### 3.3 Stress Test Persona by Document Type

| Document Type | Persona | Example Question |
|---|---|---|
| `academic_paper` | Reviewer 2 at the target venue | "What alternative explanations weren't considered?" |
| `book_chapter` | Working practitioner | "Can I use this to make a design decision tomorrow?" |
| `blog_post` | Interested generalist | "Did I learn something I can explain to someone else?" |
| `course_handout` | Student doing the homework | "Can I complete the exercise with only this handout?" |
| `policy_brief` | Decision-maker with 10 minutes | "Is there enough here to approve or reject the proposal?" |

Enhancement: the practitioner stress test benefits from a fresh model (one that did NOT participate in drafting). Use a different model for this gate if available — the drafting model's blind spots are the chapter's blind spots.

---

## 4. Run Manifest Format

The run manifest is **mandatory** for every audit run. Write it after all gates for a chapter complete. Store at `audits/{run-dir}/run_manifest.yaml`.

```yaml
run_manifest:
  run_id: "run-NNN"
  date: "YYYY-MM-DD"
  run_type: "discovery | tevv_verification | targeted"
  model: "{model used}"
  pipeline: "AD-020"  # or "AD-019 only" for correctness-only pass
  chapters_audited:
    - slug: "{chapter-slug}"
      file: "{relative path from project root}"
      document_type: "{type from AD-020 §7.1}"
      gates_run: [content_audit, practitioner_stress_test, bloom_depth_check, secondary_sweep, cascade_results, review_synthesis]
      gates_skipped: []
      status: "complete | partial | failed"
      verdict: "clean | conditionally_ready | needs_revision"
      output_files:
        - "audits/run-NNN_YYYY-MM-DD/{chapter-slug}_content_audit.yaml"
        - "audits/run-NNN_YYYY-MM-DD/{chapter-slug}_review_synthesis.yaml"
      key_findings:
        - "One-line summary of highest-priority finding"
```

**First run for any project is always `run_type: discovery`.** Subsequent targeted or verification passes use appropriate types.

---

## 5. Output File Naming Convention

All gate output files go in `audits/run-NNN_YYYY-MM-DD/`. Never write to `audits/` root.

Determine the next run ID before starting: `ls -d audits/run-*/`, increment, create the directory:
```bash
mkdir -p audits/run-NNN_YYYY-MM-DD
```

File names within the run directory:

```
{chapter-slug}_content_audit.yaml
{chapter-slug}_perplexity_queries.md
{chapter-slug}_practitioner_stress_test.yaml
{chapter-slug}_bloom_depth_check.yaml
{chapter-slug}_secondary_sweep.yaml
{chapter-slug}_cascade_results.yaml
{chapter-slug}_review_synthesis.yaml
run_manifest.yaml
```

`{chapter-slug}` is the file stem of the audited chapter (e.g., `chapter-03` for `book/chapter-03.md`).

---

## 6. Sweep Synthesis Pattern

After a full-book audit run, findings across all chapters are batched into lettered groups for author triage. Each batch groups related findings across chapters, regardless of which gate produced them.

**Decision gates (DG-N)** are created for findings that require author judgment before CC can act.

Output files:
```
docs/YYYY-MM-DD_sweep_synthesis_runNNN.md
docs/YYYY-MM-DD_author_decisions_runNNN.md
```

The sweep synthesis is a CC task, not a gate — it reads all `{slug}_review_synthesis.yaml` files from a completed run and produces the batched document.

---

## 7. How to Invoke the Pipeline

### 7.1 Single Chapter

Write a CC task that specifies:
- Target file path
- Document type (from §3.1)
- Gate calibration (which gates to run, which to skip)
- Ontology context command: `seldon ontology list --verbose`
- Bibliography path
- Reference to the auditor.md agent definition
- Run directory to create

Use `docs/templates/cc_task_content_audit.md` as the starting template for single-chapter audits.
Use `docs/templates/cc_task_agent_team_audit.md` for agent-team (parallel cascade) pattern.

### 7.2 Full-Book Sweep

Write one CC task per chapter (or per batch of chapters). Each produces its gate outputs in the same run directory. After all chapters complete, write a sweep synthesis CC task that reads all `review_synthesis.yaml` files and produces the batched synthesis.

Cap concurrent cascade teammates at 5.

### 7.3 New Project — First Run

1. Ensure agent symlinks are in place:
   ```bash
   mkdir -p .claude/agents
   ln -s /Users/brock/Documents/GitHub/seldon/.claude/agents/auditor.md .claude/agents/auditor.md
   ln -s /Users/brock/Documents/GitHub/seldon/.claude/agents/cascade-checker.md .claude/agents/cascade-checker.md
   ```
   Copies drift (confirmed: 363-byte divergence within 24 hours). Symlinks only.

2. Ensure `audits/` directory exists at project root.

3. Set `review.document_type` in `seldon.yaml` (see `docs/templates/seldon_yaml_template.yaml`).

4. Run the pipeline on each section/chapter per the gate calibration for the document type.

5. First run is always `run_type: discovery`.

---

## 8. Agent Definitions

| Agent | File | Role |
|-------|------|------|
| `auditor` | `.claude/agents/auditor.md` | Lead — runs all gates, produces YAML findings, spawns cascade checkers |
| `cascade-checker` | `.claude/agents/cascade-checker.md` | Lightweight — verifies one cross-section impact finding in a target chapter |

Both are defined in the Seldon repo and symlinked into project `.claude/agents/`. Projects do not own these definitions — they consume them read-only.

---

*For gate design rationale, claim taxonomy, and synthesis engine architecture, see AD-019 and AD-020 in `docs/design/`.*
