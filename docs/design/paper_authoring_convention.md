# Seldon Paper Authoring Convention — Design Spec

**Date:** 2026-03-15
**Status:** Design — derived from pragmatics paper patterns that worked
**Context:** Every research project reinvents paper-writing conventions. This spec standardizes them as Seldon infrastructure so projects inherit structure, not invent it.

---

## 1. The Problem

The pragmatics paper (`census-mcp-server/paper/`) developed these patterns through painful trial and error:
- `numbers_registry.md` — manual source of truth for every cited number
- `figure_table_map.yaml` — manual source of truth for every figure
- `WRITING_CONVENTIONS_PAPER.md` — prose standards, terminology rules
- `build.py` — assembly script for quarto
- `sections/01_*.md` through `10_*.md` — chapter files
- `generate_figures.py` / `generate_tables.py` — reproducible figures

These work. But they're ad-hoc files that every new paper recreates from scratch (or worse, doesn't create and suffers the drift consequences).

**The numbers registry IS what Seldon's Result artifacts already do.** The figure map IS what Figure artifacts should do. The writing conventions should be a reusable config. The build pipeline should be standardized.

---

## 2. What Seldon Should Provide

### 2a. Paper Directory Scaffold

A new command: `seldon paper init <paper-name>`

Creates:
```
paper/
├── paper.yaml              # Paper config (title, authors, venue, format)
├── conventions.md          # Writing conventions (copied from template, editable)
├── references.bib          # BibTeX (starts empty)
├── sections/               # Chapter files, assembled in order
│   ├── 00_abstract.md
│   ├── 01_introduction.md
│   ├── 02_background.md
│   └── ...                 # User adds sections as needed
├── figures/                # Generated figure outputs (PDF/PNG)
├── assets/                 # Figure generation scripts and source data
│   ├── generate_figures.py
│   └── style.py            # Plot styling (importable)
├── build.py                # Assembly script → quarto render
└── frontmatter.yml         # Quarto frontmatter config
```

The `conventions.md` is seeded from a template in the Seldon repo (the general-purpose writing conventions from the pragmatics paper, minus the paper-specific overrides). Each project adds its own terminology/framing section at the bottom.

### 2b. Numbers Registry = Seldon Result Artifacts

The `numbers_registry.md` pattern maps directly to what Seldon already has:

| numbers_registry.md | Seldon Equivalent |
|---------------------|-------------------|
| ID (SD-001, S2-010) | Result artifact name |
| Number / Value | Result.value + Result.units |
| Description | Result.description |
| Source File | DataFile artifact (COMPUTED_FROM link) |
| Script | Script artifact (GENERATED_BY link) |
| SRS Req | SRS_Requirement artifact (IMPLEMENTS link) |
| V&V status | Result.state (proposed → verified → published) |
| Status (CERTIFIED/COUNTABLE/PENDING) | Maps to state machine transitions |

**The improvement:** In the pragmatics paper, the numbers registry was a manually maintained markdown table. In Seldon, results are graph nodes with enforced provenance chains. `seldon result check-stale` replaces the manual audit process. `seldon result trace` replaces grepping the registry for source scripts.

A new CLI command should export the Seldon graph's Result artifacts into the old-style numbers registry format for human readability:

```bash
seldon paper numbers-registry > paper/numbers_registry.md
```

This generates a markdown table from the graph — not a source of truth (the graph is), but a human-readable view of it.

### 2c. Figure Map = Seldon Figure Artifacts

The `figure_table_map.yaml` pattern maps to Figure artifacts:

| figure_table_map.yaml | Seldon Equivalent |
|-----------------------|-------------------|
| Figure ID (F1, F2) | Figure artifact name |
| Title / Description | Figure properties |
| Section reference | CITES relationship to PaperSection |
| Generation tool / source | GENERATED_BY → Script |
| Output path | Figure.path property |
| Status | Figure.state (draft → review → published) |
| Registry IDs (numbers in figure) | CONTAINS → Result relationships |
| Caption | Figure.caption property |

A new CLI command exports:

```bash
seldon paper figure-map > paper/figure_map.yaml
```

### 2d. Build Pipeline

The `build.py` pattern is project-specific but follows a standard flow:
1. Read `frontmatter.yml`
2. Read `sections/00_abstract.md` through `N_*.md` in sorted order
3. Concatenate into a `.qmd` file
4. Call `quarto render`

Seldon should provide a template `build.py` that works out of the box for the standard directory structure. Projects customize by adding/removing section files.

### 2e. Citation Artifacts

The `references.bib` stays as-is (BibTeX is the standard). But Seldon should track which citations are actually used vs. just listed:

```bash
seldon artifact create Citation -p "name=schmidt_lipson_2009" -p "bibtex_key=schmidt2009distilling" -p "description=GP symbolic regression, rediscovered physical laws"
```

PaperSections then link to Citations:
```bash
seldon link create --from-name related_work --rel cites --to-name schmidt_lipson_2009
```

This lets `seldon paper citation-check` verify that every citation in `references.bib` is actually referenced by a PaperSection, and every PaperSection's cited sources have entries in the bib file.

---

## 3. What This Changes in the Workflow

**Before (pragmatics paper pattern):**
1. Create paper directory manually
2. Create numbers_registry.md manually, maintain by hand
3. Create figure_table_map.yaml manually, maintain by hand
4. Create writing conventions from memory of last paper
5. Write build.py from scratch
6. Manually audit numbers before submission

**After (Seldon paper convention):**
1. `seldon paper init leibniz-pi-paper`
2. Results are already registered as Seldon artifacts from research phase
3. Figures are tracked as Seldon artifacts with GENERATED_BY links
4. Writing conventions inherited from template, project-specific overrides added
5. Build script provided, sections added as files
6. `seldon result check-stale` and `seldon paper numbers-registry` replace manual audit

The key insight: **the research tracking (Tier 1-2) and the paper writing share the same artifact graph.** Results registered during research become the numbers cited in the paper. The provenance chain from research flows directly into the paper's source-of-truth guarantees.

---

## 4. Implementation Priority

This is Tier 4+ work — build when the leibniz-pi paper needs it, not speculatively.

**Minimum viable version for leibniz-pi (do now):**
- Create the `paper/` directory structure manually following the scaffold above
- Copy `conventions.md` from the pragmatics paper template (strip paper-specific rules)
- Use `seldon result list` and `seldon result trace` to populate the numbers manually
- Write `build.py` for quarto assembly
- Register paper sections in Seldon as PaperSection artifacts (already done in bootstrap)

**Seldon engine features (do later, when pattern is validated):**
- `seldon paper init` command
- `seldon paper numbers-registry` export
- `seldon paper figure-map` export  
- `seldon paper citation-check` audit
- Template conventions.md in Seldon repo

---

## 5. Template: conventions.md

The reusable core from the pragmatics paper, stripped of paper-specific rules:

### General Writing Conventions

**Terminology:**
- "Confabulation" not "hallucination" (per NIST AI 600-1)
- "Novel" is banned. Say what makes it different instead.
- No em dashes. Zero tolerance.

**Formatting:**
- Bold: headings, labels, and almost nothing else
- No bold pseudo-headers in prose
- Italic run-in heads for labeled-list prose (APA Level 4)
- No bullet points in prose sections

**Structure:**
- Lead with the point
- Specificity is kindness. Name the number, the section, the implementation.

**Prose Quality:**
- No throat-clearing ("It is worth noting...")
- No redundant framing
- No hedging stacks (one hedge per claim max)
- No self-congratulation ("remarkably," "notably," "strikingly")
- Sentence length: 35 words max
- Prefer active voice
- One idea per paragraph
- Minimum two sentences per paragraph
- Avoid nominalizations
- Pronoun antecedents must be unambiguous
- Tense consistency (results: past; claims: present)
- First-person: "we" throughout

### Paper-Specific Rules

*[Add project-specific terminology, framing, and vocabulary rules here.]*

---

## 6. Relationship to Other Systems

| System | Role in Paper Authoring |
|--------|------------------------|
| **Seldon** | Artifact tracking (results, figures, citations, sections). Provenance enforcement. Staleness detection. |
| **Quarto** | Rendering engine. Markdown + YAML → PDF/HTML. |
| **BibTeX** | Citation format. Standard, not replaced. |
| **PaperBanana** | Figure generation for conceptual diagrams (if available). |
| **plotnine/matplotlib** | Figure generation for data plots. |

---

*This spec will be validated by building the leibniz-pi paper using this convention. Friction findings feed back into the spec before it becomes a Seldon engine feature.*
