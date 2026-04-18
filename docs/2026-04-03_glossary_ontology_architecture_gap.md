# Design Note: Glossary ↔ Ontology Architecture Gap

**Date:** 2026-04-03
**Related:** AD-017 (Central Validity Ontology), AD-018 (Document Structure)
**Status:** Open question — needs design decision before implementation

---

## The Gap

AD-017 establishes a master/replica architecture for the shared validity ontology: canonical terms in `seldon-ontology`, read-only replicas in project databases, promotion via explicit CC task. This works well for the 51 validity vocabulary terms.

But projects also maintain glossaries (`paper/glossary.md` or `book/glossary.md`) that contain:

1. **Inherited shared terms** — SFV, T1-T5, CF, TC, SP, SCoh, SC, etc. These are (or should be) projections of the shared ontology.
2. **Project-local terms with cross-project potential** — confidence laundering, confabulation graph, stochastic tax, model transience, config-driven architecture. These originate in one project but describe general patterns.
3. **Truly project-local terms** — FCSM, FedRAMP, Bradley-Terry aggregation. Specific to the book's domain.

Currently, the glossary is a flat markdown file with no connection to the graph. A CC agent can edit it directly without creating artifacts, without linking to ontology terms, and without the verify gate catching anything (because the glossary path was hardcoded wrong — see separate bug fix task).

## What's Missing

**No mechanism to distinguish category 1/2/3 terms in the glossary.** When a CC agent adds "confidence laundering" to the glossary, nothing tells it to also create a graph artifact and link it to shared vocabulary terms. Nothing marks it as a promotion candidate. Nothing prevents another project from defining the same term differently.

**No glossary-as-projection capability.** The glossary for shared terms (category 1) should be generated from the ontology graph, not maintained manually. Manual maintenance of read-only inherited terms in a flat file is exactly the drift vector AD-017 was designed to prevent.

**No `seldon glossary` command group.** There's `seldon ontology` for the shared vocabulary. There's no equivalent for project-level glossary management — adding terms, checking consistency with the ontology, flagging promotion candidates, or generating the glossary file from graph state.

## Options

### Option A: Glossary as Pure Projection

The glossary file is generated entirely from graph state:
- Shared ontology terms → pulled from read-only replica
- Project-local terms → pulled from project graph artifacts (type TBD — GlossaryEntry or LabNotebookEntry)
- `seldon glossary generate` writes the file; direct edits are overwritten on next generate

Pros: Single source of truth (the graph). No drift possible.
Cons: Requires all terms to be graph artifacts before they appear in the glossary. High friction for rapid vocabulary development during early drafting.

### Option B: Glossary as Source with Graph Sync

The glossary file is the source for project-local terms. A sync command parses it and creates/updates graph artifacts:
- `seldon glossary sync` reads glossary.md, creates artifacts for new terms, updates existing ones
- Shared ontology terms in the glossary are validated against the replica (flag inconsistencies)
- Terms marked with a convention (e.g., `[promotion candidate]` in the definition) get flagged

Pros: Low friction — author edits the glossary naturally, sync integrates with graph.
Cons: Two sources of truth during the interval between edit and sync. Parser complexity.

### Option C: Hybrid — Shared Terms Generated, Local Terms Sourced

- Category 1 (shared) terms: generated from ontology replica, read-only section of glossary
- Category 2/3 (local) terms: authored directly in glossary, synced to graph on `seldon glossary sync`
- Glossary file has two sections: `## Inherited Terms` (generated, do not edit) and `## Project Terms` (editable)

Pros: Clean separation. Shared terms can't drift. Local terms have low friction.
Cons: Two-section glossary may be awkward for Quarto/MyST rendering. Merge on generate could be fragile.

### Option D: Do Nothing — Process Discipline Only

Keep the glossary as a flat file. Add documentation to CLAUDE.md saying "when you add a glossary term, also register it as an artifact." Rely on `seldon verify` (once the path bug is fixed) to catch banned synonyms.

Pros: Zero implementation cost.
Cons: Process discipline doesn't survive agent swarms or tired CC sessions. The Ch 4 revision just proved this — the CC agent didn't register the term.

## Recommendation

**Option B for now, with a path toward Option C.**

The immediate priority is getting `seldon verify` to find the glossary (separate bug fix task). After that, a `seldon glossary sync` command that reads the glossary file and creates graph artifacts for unregistered terms would catch the gap that just happened. The shared-terms-as-generated-section (Option C) is the right architecture but needs more design work to handle the rendering pipeline correctly.

**Defer until:** The verify glossary path fix is done and tested. Then revisit with the data from running verify against ai-workflow-design's glossary — how many terms are unregistered? How many should reference shared ontology terms? That data informs whether this is a 5-term manual fix or a 60-term automation need.

---

## Immediate Actions (separate CC tasks already written)

1. Fix `seldon verify` glossary path resolution
2. Register "confidence laundering" and "confabulation graph" as graph artifacts with ontology edges
3. Surface issues in `get_briefing_data()`
