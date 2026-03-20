# Paper Foundations Workflow — Design Spec

**Date:** 2026-03-17
**Status:** Active — validated on leibniz-pi paper
**Context:** Derived from editing the leibniz-pi paper after an agent swarm produced structurally valid but terminologically inconsistent prose. The swarm proved the pipeline mechanics; this workflow addresses the content quality problem.

---

## 1. The Problem

Research produces terminology, results, figures, and claims incrementally across sessions. Without continuous constraint maintenance, these drift:

- Terms get renamed mid-project ("entropy fitness" → "log-precision fitness") but old names persist in documents
- Results computed in one session get cited with slightly different values in another
- Figures get regenerated but downstream references aren't updated
- Banned synonyms creep back into prose because no one checks

The paper-writing phase inherits all accumulated drift. Fixing it retroactively is a mountain of whack-a-mole: fix a term in Methods, the old term is still in Results and Discussion.

**Root cause:** These foundational constraints (vocabulary, evidence inventory, term index) were not maintained incrementally during research. They were treated as a one-time prework task rather than a continuous process.

---

## 2. The Solution: Constraint Propagation

Establish a controlled vocabulary and verified evidence inventory early. Maintain them continuously. Every section must conform. Violations are machine-detectable.

This is constraint propagation applied to writing: reduce the degrees of freedom before searching the solution space. The glossary constrains terminology. The evidence map constrains claims. The keyword index reveals distribution. Sections written against these constraints have fewer drift vectors.

---

## 3. Foundation Files

These live in the project's `paper/` directory. They are reference constraints for writing, not graph artifacts (though they can be registered as LabNotebookEntry artifacts for provenance).

### 3.1 Glossary (`paper/glossary.md`)

Controlled vocabulary. Every technical term the paper uses, with:

- **Term name** (bold heading)
- **Definition** (what it means in this paper's context)
- **Usage notes** (how to use it correctly)
- **Banned synonyms** (quoted phrases that must not appear — machine-checkable)

Format:
```markdown
**Wrong-limit attractor**
: A series whose partial sums converge to a finite value near the target
  within the evaluation horizon, but whose true limit differs from the target.
: Do not write: "deceptive series", "false positive", "spurious convergent".
```

**When to update:** Every time a new term is coined, a term is renamed, or a usage inconsistency is discovered. This should happen during research, not only during paper writing.

**Ideal:** Terms are added to the glossary in the same session they are first used in a research note or result description.

### 3.2 Keyword Index (`paper/keyword_index.md`)

Auto-generated concordance showing which glossary terms appear in which sections. Produced by `paper/check_glossary.py`. Not hand-edited.

**What it reveals:**
- Terms appearing in unexpected sections (signal for scope creep)
- Terms missing from sections where they should appear (signal for incomplete coverage)
- Banned synonyms that slipped through

**When to regenerate:** After every edit to any section file. Part of the standard edit cycle.

### 3.3 Evidence Map (`paper/evidence_map.md`)

Human-readable provenance reference. Maps:

- **Results → Claims → Sections**: Which registered results support which claims, and where those claims appear
- **Figures/Tables → Data → Scripts**: What generates each figure, from what data
- **Claims → Evidence**: For each claim the paper makes, what evidence backs it

This is the human-readable expression of what the Seldon graph tracks. It exists because scanning a markdown table is faster than running Cypher queries when you're mid-edit.

**When to update:** When results are registered, figures are created, claims are added or removed from sections, or the argument structure changes.

### 3.4 Conventions (`paper/conventions.md`)

Already specified in `paper_authoring_convention.md`. The paper-specific terminology section at the bottom should cross-reference the glossary. General style rules are stable; paper-specific rules evolve with the project.

### 3.5 Glossary Checker (`paper/check_glossary.py`)

Python script (no LLM tokens needed) that:

1. Parses `glossary.md` for term definitions and banned synonyms
2. Scans all `sections/*.md` files
3. Reports banned synonym violations with file:line:phrase
4. Generates `keyword_index.md` concordance
5. Reports unused glossary terms (defined but never appear — possible dead terms)

Runs as: `python paper/check_glossary.py`

Flags: `--index-only`, `--violations-only`

Exit code 1 if banned synonyms found (can be used as a CI gate or pre-commit hook).

---

## 4. When Foundations Get Built

### Ideal: Incrementally During Research

The foundations should be living documents maintained throughout the research lifecycle, not retroactive cleanup before paper writing.

| Research Phase | Foundation Activity |
|---|---|
| Experiment design | Add key terms to glossary as they're coined |
| Running experiments | Register results in Seldon as they're computed |
| Analyzing results | Update evidence map with claims the results support |
| Literature review | Add terms from related work that we adopt or contrast against |
| Between sessions | ClaudeClaw runs `check_glossary.py` and `seldon paper sync --dry-run`, reports drift |

### Realistic: At Minimum Before Paper Writing

If foundations weren't maintained during research (the common case until the workflow is habitual), they must be established before iterative section editing begins. The cost of retroactive cleanup scales with the amount of drift accumulated.

### Operational Maintenance (ClaudeClaw / Cron)

Daily or per-session automated checks:

```bash
# Daily sync check (ClaudeClaw cron)
cd /path/to/project
python paper/check_glossary.py --violations-only
seldon paper sync --dry-run
seldon docs check --threshold 80
```

Report surfaces: new violations since last check, sections that changed without sync, documentation gaps. Human reviews, decides what to fix.

This is a maintenance mode task — cheap to run, high signal, prevents drift from accumulating silently between active editing sessions.

---

## 5. The Editing Workflow

Once foundations exist, the editing cycle is:

```
edit section → check_glossary → sync → build
```

Concretely:
```bash
# After editing any section file:
python paper/check_glossary.py       # check terms, regenerate index
seldon paper sync                    # reconcile graph with disk
seldon paper build --no-render       # verify structural integrity
```

### Recommended Writing Order

Conclusion first (backwards from reader order, forwards from argument logic):

1. **Conclusion** — what do we claim?
2. **Results** — what evidence supports the claims?
3. **Experimental Design** — how did we produce the evidence?
4. **Methods** — what machinery did we use?
5. **Background** — what context does the reader need?
6. **Introduction** — what question are we answering?
7. **Abstract** — compress everything (revise last)

Each layer constrains the next. The conclusion constrains which results matter. The results constrain which methods need describing. This prevents the common failure of writing Methods that describe everything the project did rather than everything the paper needs.

---

## 6. Belief Revision / Truth Maintenance

The foundations are not write-once. They are subject to continuous revision:

- **Term renamed:** Update glossary definition, add old name to banned synonyms, run check_glossary to find all instances
- **Result invalidated:** Mark stale in Seldon, staleness propagates to citing sections, update evidence map
- **New claim added:** Verify evidence exists in evidence map, add if missing, check that results are registered and verified
- **Section restructured:** Regenerate keyword index, verify term distribution still makes sense

The Seldon graph handles result staleness propagation automatically. The glossary checker handles term consistency. The evidence map requires human judgment — it's the one piece that can't be fully automated because it encodes the argument structure, which is a human decision.

---

## 7. Relationship to Other Specs

| Document | Relationship |
|---|---|
| `paper_authoring_convention.md` | Covers scaffold, build pipeline, result/figure maps, conventions template. This doc covers the continuous maintenance workflow that uses those structures. |
| `AD-012_paper_as_graph_assembly.md` | Paper build pipeline: reference resolution, QC tiers, Quarto assembly. This doc covers the pre-build constraint maintenance. |
| `AD-013_documentation_as_traceability.md` | Documentation properties on artifacts. Glossary/evidence map are the paper-specific expression of this principle. |
| `conops_agent_swarm_workflow.md` | Agent swarm paper writing. This doc addresses the quality problem the swarm revealed: structurally valid but terminologically inconsistent output. Foundations constrain swarm input. |

---

## 8. Implementation Status

| Component | Status | Location |
|---|---|---|
| Glossary format | Implemented | `paper/glossary.md` (per-project) |
| Glossary checker | Implemented | `paper/check_glossary.py` (per-project, should become Seldon template) |
| Keyword index | Implemented | Auto-generated `paper/keyword_index.md` |
| Evidence map | Implemented | `paper/evidence_map.md` (per-project) |
| `seldon paper sync` | Implemented | Seldon CLI command |
| `seldon paper register` | Implemented | Seldon CLI command |
| ClaudeClaw daily checks | Not yet | Future: cron job for automated drift detection |
| `seldon paper init` scaffold with foundations | Not yet | Future: template glossary + check script + evidence map in scaffold |
| Glossary checker as Seldon command | Not yet | Future: `seldon paper glossary check` |

---

*Validated on the leibniz-pi paper (March 2026). The retroactive cost of not maintaining foundations during research was significant. Build these incrementally from the start on the next project.*
