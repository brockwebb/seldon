# CC Task: Build Global Citation Catalog in Seldon

**Date:** 2026-03-22
**Priority:** Normal — should be done before or alongside the vocabulary build task
**Repo:** `~/Documents/GitHub/seldon/`

---

## Objective

Build a global citation catalog at `seldon/docs/references/references.bib` that serves as the single canonical bibliography across all Seldon-tracked projects. The vocabulary file (`ontology/validity/VALIDITY_VOCABULARY.md`) and all future ontology documents cite from this catalog using BibTeX keys.

The global catalog enables blast radius analysis: if a source is updated (e.g., NIST releases AI RMF 2.0), grep the citation key to find every definition, document, and project that depends on it.

---

## Philosophy

- **One bibliography to rule them all.** Project-specific `.bib` files can continue to exist for their own papers, but the global catalog is the canonical version. If a source appears in multiple projects, it should be here.
- **Extract from existing project bibliographies.** Don't start from zero — pull entries from existing `.bib` files across projects.
- **Add new entries for the validity vocabulary.** Some sources (Shadish/Cook/Campbell, Cronbach/Meehl, Hirstein, Groves) aren't in any existing `.bib` yet.
- **Standard BibTeX format.** Follow the convention already in the Seldon references.bib header: APA 7th edition, keys = `AuthorYearKeyword`, alphabetical order.
- **Every entry must be complete.** Author, title, year, publisher/journal, DOI or URL where available.

---

## Step 1: Extract entries from existing project bibliographies

Read the following files and extract any entries that have cross-project relevance (frameworks, standards, foundational methodology texts). Skip entries that are purely project-specific (e.g., a GP convergence paper only used in the leibniz-pi paper).

| Source | Path |
|--------|------|
| FCSM/NIST crosswalk | `~/Documents/GitHub/central_library/crosswalks/fcsm_nist/references.bib` |
| Seldon (existing, mostly empty) | `~/Documents/GitHub/seldon/docs/references/references.bib` |
| Leibniz-Pi paper | `~/Documents/GitHub/ai-demos/leibniz-pi/paper/references.bib` |
| Census MCP paper | `~/Documents/GitHub/census-mcp-server/paper/references.bib` |

**Extract these categories:**
- Framework documents (NIST, FCSM, OMB)
- Statutes and regulations
- Brock's own published work
- Foundational methodology texts referenced across projects

---

## Step 2: Add new entries for the validity vocabulary

The following sources are needed for the validity vocabulary but may not exist in any current `.bib` file. Add them:

```bibtex
@book{ShadishCookCampbell2002,
  author    = {Shadish, William R. and Cook, Thomas D. and Campbell, Donald T.},
  title     = {Experimental and Quasi-Experimental Designs for Generalized Causal Inference},
  publisher = {Houghton Mifflin},
  year      = {2002},
  address   = {Boston},
  note      = {Canonical reference for construct, internal, external, and statistical conclusion validity}
}

@article{CronbachMeehl1955,
  author  = {Cronbach, Lee J. and Meehl, Paul E.},
  title   = {Construct validity in psychological tests},
  journal = {Psychological Bulletin},
  volume  = {52},
  number  = {4},
  pages   = {281--302},
  year    = {1955},
  doi     = {10.1037/h0040957},
  note    = {Origin of construct validity concept; foundational for reliability vs validity distinction}
}

@book{Hirstein2005,
  author    = {Hirstein, William},
  title     = {Brain Fiction: Self-Deception and the Riddle of Confabulation},
  publisher = {MIT Press},
  year      = {2005},
  address   = {Cambridge, MA},
  note      = {Clinical neuropsychology origin of confabulation term; basis for distinguishing confabulation from hallucination in AI context}
}

@book{Groves2009,
  author    = {Groves, Robert M. and Fowler, Floyd J. and Couper, Mick P. and Lepkowski, James M. and Singer, Eleanor and Tourangeau, Roger},
  title     = {Survey Methodology},
  edition   = {2nd},
  publisher = {Wiley},
  year      = {2009},
  series    = {Wiley Series in Survey Methodology},
  note      = {Canonical reference for Total Survey Error framework}
}

@online{Webb2026ai4stats,
  author = {Webb, Brock},
  title  = {{AI} for Official Statistics},
  year   = {2026},
  url    = {https://brockwebb.github.io/ai4stats/},
  note   = {Chapter 20 introduces State Fidelity Validity (SFV) framework}
}
```

Also verify whether `Webb2026crosswalk` (the Zenodo crosswalk paper) is already captured — it is in the crosswalk `.bib` as `webb2026crosswalk`. Normalize the key to match convention.

---

## Step 3: Write the consolidated global catalog

Write to `~/Documents/GitHub/seldon/docs/references/references.bib`

Preserve the existing header convention:
```
% Seldon — Canonical Bibliography
% Format: APA 7th Edition (BibTeX)
% Add new entries alphabetically by citation key
%
% Convention: citation_key = AuthorYearKeyword
% Example: Webb2026traceability, Asimov1951foundation
%
% PURPOSE: Global citation catalog for all Seldon-tracked projects.
% Vocabulary files and ontology documents cite from this catalog.
% If a source updates (e.g., NIST AI RMF 2.0), grep the key to find blast radius.
```

Organize sections:
```
% ═══════════════════════════════════════════════════════════════
% Framework Documents (NIST, FCSM, OMB)
% ═══════════════════════════════════════════════════════════════

% ═══════════════════════════════════════════════════════════════
% Statutes and Regulations
% ═══════════════════════════════════════════════════════════════

% ═══════════════════════════════════════════════════════════════
% Foundational Methodology (Validity, Survey Methods, Psychometrics)
% ═══════════════════════════════════════════════════════════════

% ═══════════════════════════════════════════════════════════════
% AI/ML Methodology and Governance
% ═══════════════════════════════════════════════════════════════

% ═══════════════════════════════════════════════════════════════
% Webb (Own Published Work)
% ═══════════════════════════════════════════════════════════════
```

---

## Step 4: Create a companion markdown index

Create `~/Documents/GitHub/seldon/docs/references/CITATION_INDEX.md`:

```markdown
# Global Citation Catalog — Index

**File:** `references.bib`
**Per:** AD-017 (Central Validity Ontology)
**Purpose:** Single canonical bibliography for all Seldon-tracked projects.

## Usage

- Vocabulary files cite using BibTeX keys from this catalog (e.g., `[ShadishCookCampbell2002]`)
- Project-specific `.bib` files may continue to exist for their own papers
- If a source is shared across projects, it should be here
- **Blast radius:** To find what depends on a source, grep the citation key across all repos

## Quick Reference

| Key | Short Description | Used By |
|-----|-------------------|---------|
| `fcsm2020` | FCSM 20-04 Data Quality Framework | crosswalk paper, ai4stats, validity vocabulary |
| `nist2023airm` | NIST AI RMF 1.0 | crosswalk paper, ai4stats, validity vocabulary |
| `ShadishCookCampbell2002` | Classical validity types | validity vocabulary |
| `CronbachMeehl1955` | Construct validity / reliability distinction | validity vocabulary |
| `Hirstein2005` | Confabulation (clinical origin) | validity vocabulary, crosswalk paper |
| `Groves2009` | Total Survey Error | validity vocabulary, ai4stats |
| `Webb2026ai4stats` | AI for Official Statistics (SFV chapter) | validity vocabulary |
| `webb2026crosswalk` | FCSM/NIST crosswalk (Zenodo) | crosswalk paper, validity vocabulary |
| [add others as catalog grows] | | |

## Maintenance

When adding a new source:
1. Add the BibTeX entry to `references.bib` in the correct section, alphabetically
2. Add a row to the Quick Reference table above with the key and which projects use it
3. If replacing/updating an existing source, grep the old key across all repos to assess blast radius
```

---

## Step 5: Update the vocabulary CC task dependency

The vocabulary build task (`2026-03-22_migrate_sfv_to_central_ontology.md`) should reference citation keys from this global catalog rather than defining its own inline citation table. The citation keys in the vocabulary task spec remain valid — they just now point to this `.bib` file as the authoritative source.

No need to rewrite the vocabulary task — just ensure CC reads the global catalog when building the vocabulary and uses matching keys.

---

## Step 6: Register and commit

```bash
cd ~/Documents/GitHub/seldon

seldon add artifact \
  --name "Global Citation Catalog" \
  --type Document \
  --path docs/references/references.bib

seldon add artifact \
  --name "Citation Index" \
  --type Document \
  --path docs/references/CITATION_INDEX.md

git add docs/references/
git commit -m "Build global citation catalog for cross-project bibliography (AD-017)

- Consolidated entries from crosswalk, leibniz-pi, census-mcp bibliographies
- Added foundational methodology sources (Shadish/Cook/Campbell, Cronbach/Meehl, Groves, Hirstein)
- Created CITATION_INDEX.md for blast radius tracking
- Vocabulary and ontology documents cite from this catalog"
```

---

## Verification

1. `seldon/docs/references/references.bib` contains entries from all source projects plus new validity sources
2. `seldon/docs/references/CITATION_INDEX.md` exists with quick reference table
3. Every entry has complete metadata (author, title, year, publisher/journal, DOI/URL where available)
4. Entries are organized by section and alphabetical within sections
5. No duplicate keys
6. Artifacts registered with Seldon
7. Committed
