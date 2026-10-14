# RESULT: DesignNote and ArchitecturalDecision may originate `cites` edges

**Task:** `cc_tasks/2026-09-28_designnote_cites_citation.md` (dispatch ef334553), including its inline afternoon
addendum (ArchitecturalDecision too). No file matches `2026-09-28_designnote_cites_citation_ADDENDUM*.md`.
`cc_tasks/2026-10-13_designnote_cites_citation_ADDENDUM_01_slosh_pipe.md` was found while cataloging. It is
registered as a separate task, ordered after this one, and was not executed here. Its section 1 (slosh-pipe's
DesignNote `cites` refusal) needs no further change: this one covers it. Its section 2 (`derived_from` widening)
and its `uses_data_from` question stay with that task.
**Date:** 2026-10-14
**Governing ruling:** AD-030-R7.

## What changed

- `seldon/domain/research.yaml`, `relationship_types.cites.from_types`: added `DesignNote` and
  `ArchitecturalDecision`, with a comment naming this task. `to_types` and the CiTO values are unchanged.
- `tests/test_relationship_types.py` (written first and run red: 11 failed). It now has:
  - validator accept cases for both new origins to `Citation`, `Result` and `Passage`;
  - two reject cases (`DesignNote -> DesignNote`, `ArchitecturalDecision -> Script`) showing `to_types` did not widen;
  - a config-surface case pinning the full `cites` endpoint sets;
  - `test_create_link_cites_citation_carries_cito_properties`, run for each new origin, which creates the edge
    through `create_link` with `cito_type="uses_method_in"`, `reason` and `raw_reference` and reads them back from
    Neo4j.

## Verification

- check: `python -m dotenv -f .env run -- python -m pytest tests/ -q`: **2474 passed**, exit 0 (14m07s). The test
  file alone: 60 passed.
- judgment (the cross-repo criterion): regs-comment-pipeline's `seldon.yaml` declares `domain: research`, which
  resolves to this repository's editable-installed `research.yaml`, so it uses the new schema with no copy to
  update. Its real artifacts were looked up read-only in `seldon-regs-comment-pipeline`: DesignNote f7c57569
  (`classification_design_notebook_2026_09_28`) and ArchitecturalDecisions 0c11ee63 (AD-003) and b9fd3e0e (AD-004).
  `validate_relationship(cites, <type>, Citation)` passes for both types. **No edge was written in that graph.** The
  addendum's 26 intended edges and the notebook's 15 belong to regs-comment-pipeline's own tasks. They need
  `rel_properties` (see below), and writing them from here would be one repository authoring another's provenance.

## Still open (observed in the task, not in scope, not filed here)

- `seldon link create` has no edge-property option (`-p KEY=VALUE`). So `cito_type`, `reason` and `raw_reference`
  can still only be written through `create_link(..., rel_properties=...)` from Python.
- There is no CLI or MCP command for a generic artifact state transition.
- `SRS_Requirement` has no path and no edge to the AD or citation it relies on.
