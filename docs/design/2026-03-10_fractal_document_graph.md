# Design Insight: Fractal Document Graph — Paper as Database

**Date:** 2026-03-10
**Source:** Discussion on graph-native research writing
**Extends:** AD-006 (Result Registry), AD-009 (Database as Context), Research Domain Config

---

## The Insight

A research paper is not a collection of flat files. It's a graph of claims backed by evidence. The granularity isn't fixed — it's fractal. Nodes exist at whatever depth provenance requires.

**Old model:** `chapters/02_methods.md` — a flat file. Citations maintained by human discipline. No structural relationship between what's written and what produced it. Change a result, grep for where it might be mentioned, hope you find them all.

**Graph model:** Every structural element of the paper is a node. Relationships enforce what flat files can't.

---

## Document Node Hierarchy

```
Paper
  └── Section (e.g., "Methods", "Results")
        └── Subsection (e.g., "2.1 Data Sources")
              └── Paragraph
                    └── Claim (a specific assertion backed by evidence)
                          └── cites → Result (verified value with provenance)
                          └── cites → Citation (external literature reference)
                          └── references → Figure / Table
```

Not every paragraph needs claim-level decomposition. The graph is as deep as the provenance requires:

- A paragraph stating established background → section-level node, `cites` edges to `Citation` nodes. No deeper decomposition needed.
- A paragraph reporting a specific finding → paragraph contains `Claim` nodes, each with `cites` edges to specific `Result` nodes with full provenance chains.
- A sentence with a critical number → the `Claim` node links to a `Result` that links to a `Script` that links to `DataFile` inputs. Traceable from sentence to raw data.

---

## Node Types (extending research domain config)

| Node Type | Granularity | Key Attributes |
|-----------|-------------|----------------|
| `Paper` | Top-level | title, authors, status (draft/submitted/published), version |
| `Section` | Chapter/major section | title, sequence_number, word_count, status |
| `Subsection` | Numbered subsection | title, sequence_number, parent_section |
| `Paragraph` | Single paragraph | content_hash, sequence_number, status (draft/reviewed/final) |
| `Claim` | An assertion within a paragraph | statement, claim_type (finding/methodology/background), confidence |
| `Figure` | A figure or visualization | caption, figure_type, file_path |
| `Table` | A data table | caption, columns, row_count |
| `Citation` | External literature reference | bibtex_key, APA_string, DOI |

Existing types from AD-006/007 that connect:
- `Result` — a verified quantitative finding with provenance
- `Script` — code that generated a result
- `DataFile` — input data
- `ResearchTask` — tracked work item

## Edge Types (extending research domain config)

| Edge Type | From → To | Meaning |
|-----------|-----------|---------|
| `contains` | Section → Subsection → Paragraph | Structural hierarchy |
| `contains_claim` | Paragraph → Claim | Paragraph makes this assertion |
| `cites_result` | Claim → Result | Claim is backed by this verified result |
| `cites_literature` | Claim → Citation | Claim references this external source |
| `references_figure` | Paragraph → Figure | Paragraph references this figure |
| `references_table` | Paragraph → Table | Paragraph references this table |
| `visualizes` | Figure → Result | Figure visualizes this result |
| `tabulates` | Table → Result[] | Table contains these results |
| `sequenced_after` | Section → Section | Document ordering |

---

## Staleness Propagation — Surgical Precision

When a `Result` changes (re-run produces different value):

1. `Result` status → `stale`
2. Traverse: `Result` ← `cites_result` ← `Claim` ← `contains_claim` ← `Paragraph` ← `contains` ← `Section`
3. Mark each `Claim` as `stale` (the specific assertion is now unsupported)
4. Mark each `Paragraph` containing a stale claim as `needs_review`
5. Mark each `Figure`/`Table` that `visualizes`/`tabulates` the stale result as `needs_update`
6. The `Section` gets a staleness score: N stale claims out of M total claims
7. Everything NOT in the traversal path stays clean

**This is impossible with flat files.** In a flat file, "result changed" means "grep the whole paper and hope." In the graph, it's a deterministic traversal that identifies exactly which sentences are affected.

---

## Agent Context Slices for Writing

A drone assembling a paragraph gets:

```
Context slice for Paragraph 3 of Section 2.1:
- Outline position: Section 2.1 "Data Sources", third paragraph
- Previous paragraph summary: [1 sentence]
- Next paragraph summary: [1 sentence]
- Claims to make:
  - Claim: "The ACS 5-year sample covers N respondents"
    - Result: result-20260310-acs-count (value: 3,548,000, status: verified)
    - Provenance: generated_by script/count_acs_records.py, computed_from data/acs_2024.csv
  - Claim: "Response rates vary by geography"
    - Result: result-20260310-response-rate-range (value: 89.2%-97.1%, status: verified)
    - Citation: (Census Bureau, 2024)
- Style context: [from CLAUDE.md or paper-level style node]
```

That's maybe 500 tokens. The drone writes one paragraph with full provenance awareness. It can't hallucinate a number because the only numbers in its context are verified results from the graph.

---

## Assembly from Graph

The paper assembles from the graph, not from flat files:

```
seldon paper assemble --format latex --output paper.tex
```

1. Query all `Section` nodes, sort by `sequenced_after`
2. For each section, query `Paragraph` nodes, sort by `sequence_number`
3. For each paragraph, render content with inline citations from `cites_literature` edges
4. For each figure/table reference, insert the appropriate float
5. Generate bibliography from all `Citation` nodes in the graph
6. Generate a provenance appendix: every claimed result with its full chain

The assembled document is a **projection** of the graph, not the source of truth. Edit the graph, re-assemble. The paper is always consistent with the graph because it's generated from it.

---

## What This Changes

| Old Pattern | New Pattern |
|-------------|-------------|
| Write chapters as markdown files | Write claims backed by graph-linked results |
| Manually maintain citations | Citations are edges — add a `cites` edge, it appears in the bibliography |
| Grep for stale numbers | Staleness propagates automatically through the graph |
| Copy-paste results into text | Results are retrieved from the graph at assembly time — always current |
| Session handoffs describe "what was written" | Graph state IS what was written — query it |
| Review means reading the whole paper | Review means checking staleness scores per section |

---

## Implementation Priority

This is NOT a near-term build item. The current priority is the SAS conversion proof of concept and Seldon's core engine.

But the research domain config schema (Seldon T0-1) should be designed with this granularity in mind. The node types and edge types above should be representable in the domain config, even if the writing workflow isn't built yet. When the pragmatics paper needs this, the schema should already support it.

---

*The paper is a projection of the graph. The graph is the paper's source of truth. Edit the graph, the paper follows.*
