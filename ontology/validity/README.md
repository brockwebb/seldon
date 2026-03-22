# Validity Ontology — Central Definitions

Per AD-017, this directory contains the canonical validity vocabulary shared across all Seldon-tracked projects.

## Files

| File | Purpose |
|------|---------|
| `VALIDITY_VOCABULARY.md` | Consolidated canonical vocabulary with citations — the single source of truth |
| `provenance/SFV_gemini_discovery_notes.md` | Gemini discovery conversation — intellectual provenance of SFV naming and tax framing |
| `provenance/SFV_naming_prompt_original.md` | Original naming exploration prompt sent to other models |
| `provenance/context_validity_li_post_draft_pre_rename.md` | Pre-rename LinkedIn draft using "Context Validity" — shows original framing before SFV was selected |

## Usage

- Future projects reference `VALIDITY_VOCABULARY.md` for canonical definitions
- Every definition includes a citation to its authoritative source
- Project-specific terms stay in their projects until promoted here
- If a term needs to change, update `VALIDITY_VOCABULARY.md` first
- Future: ingestion script will populate Neo4j from this file (per AD-017)

## Related Assets (stay in their home projects)

- `central_library/crosswalks/fcsm_nist/submitted/webb_2026_fcsm_nist_crosswalk.pdf` — published crosswalk paper (Zenodo)
- `ai4stats/docs/sfv/SFV_TERMINOLOGY_BASELINE.md` — original project-level baseline (ai4stats canonical source; this vocabulary supersedes it for cross-project use)
- `ai-demos/leibniz-pi/docs/data_dictionary.md` — example of Seldon-generated project data dictionary
