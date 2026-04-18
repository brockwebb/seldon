# AD-018: Document Structure Graph

**Date:** 2026-03-28
**Status:** Accepted
**Context:** PaperSection is flat — no hierarchy, no parent/child, no structural relationships. Figure exists but has no chapter assignment or numbering. Table doesn't exist as an artifact type at all. Cross-references between sections ("see Figure 3") have no graph representation. When a Result changes, there is no way to determine which Figures, Tables, or Sections are affected without manual grep. This is the DOORS impact analysis pattern missing from Seldon's paper infrastructure.
**Extends:** AD-006 (Result Registry), AD-012 (Paper as Graph Assembly), AD-013 (Documentation as Traceability)
**Prior art:** `2026-03-10_fractal_document_graph.md` (design insight, captured the full vision including Paragraph/Claim decomposition — this AD implements the practical subset)

---

## Decision

Extend Seldon's research domain config with document hierarchy, Table artifacts, figure/table numbering, cross-reference tracking, and blast radius analysis. Scope is deliberately limited to what's needed for paper and book authoring today — Chapter/Section/Subsection hierarchy, Figure and Table registries with provenance and numbering, and cross-reference edges that enable impact analysis.

Paragraph-level and Claim-level decomposition (from the March 10 design note) remains in the parking lot until this simpler structure proves insufficient.

---

## Architecture

### Document Hierarchy

```
Book / Paper (top-level — optional, exists implicitly from seldon.yaml)
  └── Chapter / Section (PaperSection with sequence + depth)
        └── Section / Subsection (PaperSection with parent relationship)
              └── Figures, Tables, Results (appear_in specific sections)
```

PaperSection already exists. It gains:
- `sequence` property — ordering within its parent (1, 2, 3...)
- `depth` property — 0 = chapter/top-level, 1 = section, 2 = subsection
- `parent` relationship — `contains` edge from parent section to child section

This is NOT a new artifact type. It's extending PaperSection with hierarchy. A chapter is a PaperSection at depth 0. A subsection is a PaperSection at depth 2 with a `contains` edge from its parent.

### Table as First-Class Artifact

New artifact type `Table` — parallel to `Figure`:

```yaml
Table:
  properties:
    name:
      required: true
      description: "Table identifier (e.g., 'table_1_comparison')"
    caption:
      required: true
      description: "Table caption text"
    table_number:
      category: documentation
      description: "Assigned number within document (computed from graph position)"
    generating_script:
      category: documentation
      description: "Script that produces this table"
    data_sources:
      category: documentation
      description: "DataFiles that feed this table"
```

State machine same as Figure: proposed → draft → review → published → stale.

### Figure Updates

Figure gains:
- `figure_number` property — computed from graph position (sequence within parent chapter)
- `caption` property (required)

### Numbering Scheme

Figure and Table numbers are derived from document position, not hardcoded:

- **Within a paper (flat structure):** Figure 1, Figure 2, Figure 3... based on sequence of `appears_in` relationships sorted by parent section sequence.
- **Within a book (chapter structure):** Figure 2.1, Figure 2.3... = Chapter.Sequence within chapter. Table 5.1 = first table in Chapter 5.

Renumbering is a graph traversal: query all Figures/Tables, sort by their parent section's sequence and their own sequence within that section, assign numbers. When a new Figure is inserted before an existing one, the query produces new numbers. Cross-references resolve against the graph, so they automatically point to the right artifact regardless of number changes.

**Build-time resolution:** `{{figure:NAME}}` in section prose resolves to the figure's current number at `seldon paper build` time. Same pattern as `{{result:NAME:value}}`. The number is never hardcoded in prose.

### New Relationships

```yaml
# Document hierarchy
contains_section:
  from_types: [PaperSection]
  to_types: [PaperSection]

# Figure/Table placement
appears_in:
  from_types: [Figure, Table]
  to_types: [PaperSection]

# Figure/Table provenance (generated_by already exists for Figure)
generated_by:
  from_types: [Result, Figure, Table]  # add Table to existing
  to_types: [Script]

# Cross-references (sections referencing figures/tables)
references_figure:
  from_types: [PaperSection]
  to_types: [Figure]

references_table:
  from_types: [PaperSection]
  to_types: [Table]

# Table data content
tabulates:
  from_types: [Table]
  to_types: [Result]

# Figure data content (contains already exists)
# contains:
#   from_types: [Figure]
#   to_types: [Result]
```

### Blast Radius / Impact Analysis

When a Result changes (stale):
1. Find all Figures that `contain` this Result → mark stale
2. Find all Tables that `tabulate` this Result → mark stale
3. Find all PaperSections that `cites` this Result → mark stale
4. Find all PaperSections that `references_figure` any stale Figure → flag for review
5. Find all PaperSections that `references_table` any stale Table → flag for review

This is `get_dependents()` in graph.py — the traversal already exists. The missing piece is the edges (which this AD creates) and a reporting command that presents the blast radius in a human-readable way.

**Command:** `seldon paper impact <artifact-name>` — shows the blast radius tree for a given artifact.

### Reference Tokens

Extend the existing `{{result:NAME:value}}` syntax:

- `{{figure:NAME}}` → resolves to "Figure 2.3" (number computed from graph position)
- `{{table:NAME}}` → resolves to "Table 5.1"
- `{{section:NAME}}` → resolves to "Section 3.2" or "Chapter 3"

These resolve at `seldon paper build` time. Prose never contains hardcoded numbers.

---

## What This Enables

| Before | After |
|--------|-------|
| Flat list of PaperSections | Hierarchical: Chapter → Section → Subsection |
| No Table artifact type | Tables tracked with full provenance |
| Figure numbers hardcoded in prose | Numbers computed from graph position |
| Cross-references are plain text | Cross-references are graph edges |
| "Where is Figure 3 mentioned?" = grep | `seldon paper impact fig_convergence` = graph query |
| Insert a figure = manually renumber everything | Insert = re-run numbering query, build resolves references |
| Result changes = hope you find all mentions | Result changes = deterministic blast radius traversal |

---

## Dogfooding Strategy

**Phase 1: SFV paper** — small (12 sections, few figures/tables). Retrofit hierarchy on existing PaperSections. Register any figures/tables. Validate blast radius works.

**Phase 2: ai-workflow-design book** — 10 chapters, will have many figures and tables. Initialize with hierarchy from day one. This is the real test — a book-length document with Chapter.Figure numbering.

---

## What This Does NOT Do

- Does NOT decompose paragraphs into individual claims (parking lot — from March 10 design note)
- Does NOT implement agent context slicing for per-paragraph writing (parking lot)
- Does NOT build a full assembly-from-graph pipeline (existing `seldon paper build` is extended, not replaced)
- Does NOT handle page numbers or physical layout (that's the rendering engine's job — Quarto/Typst)
- Does NOT auto-detect cross-references from prose (manual `seldon link create` or detected during `paper sync` via token patterns)

---

## Related

- `2026-03-10_fractal_document_graph.md` — full vision (this AD is the practical subset)
- AD-006: Result Registry — Results are what Figures/Tables visualize/tabulate
- AD-012: Paper as Graph Assembly — `paper build` will resolve `{{figure:NAME}}` tokens
- Pragmatics paper patterns: `figure_table_map.yaml`, `numbers_registry.md` (manual precursors to this graph-based approach)
