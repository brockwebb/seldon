# RESULT: `derived_from` may originate at a DataFile and target a DesignNote (Addendum 01, slosh-pipe)

**Task:** `cc_tasks/2026-10-13_designnote_cites_citation_ADDENDUM_01_slosh_pipe.md` (seldon task defca7cc). No file
matches `2026-10-13_designnote_cites_citation_ADDENDUM_01_slosh_pipe_ADDENDUM*.md`.
**Date:** 2026-10-14
**Governing:** AD-030 section 4, AD-030-R7.

## Section 1 (DesignNote `cites`)

Already done by the parent (commit 0e6c017, `cc_tasks/2026-09-28_designnote_cites_citation_RESULT.md`):
`cites.from_types` includes `DesignNote`. No further schema change. slosh-pipe's 22 `cites` edges are unblocked.
The `uses_data_from` question: CiTO defines `cito:usesDataFrom` (Shotton 2010, the ontology AD-030-R7 adopts), so the
`cito_type` description in `research.yaml` now names `uses_data_from`. Description only; values remain unenforced.

## Section 2 (`derived_from`), Part A

- `seldon/domain/research.yaml`, `relationship_types.derived_from`: `from_types` `[Result]` -> `[Result, DataFile]`;
  `to_types` gains `DesignNote`. Comment names this addendum.
- `Document` was **not** added as an origin, which departs from the addendum's proposal (it left this open).

**judgment (whether to widen at all, against AD-030 section 4):** widen, narrowly.
- AD-030 section 4's closed edge set governs edges on governed-document nodes (Document, Section, Ruling, Citation,
  Passage). `derived_from` predates AD-030 and is the research domain's provenance edge, the analogue of W3C PROV-O
  `prov:wasDerivedFrom`, whose domain and range are both `prov:Entity` (AD-030 section 6 already cites PROV-O). A
  DataFile and a DesignNote are both entities, so the `[Result]`-only origin was a Seldon restriction, not one PROV
  imposes. Widening it adds no edge type and leaves the governed-node edge set untouched.
- Adding `Document` as an origin would put a new edge on a governed-document node, which section 4 closes. The
  motivating case (`parameter_registry` 427bead8 is a DataFile) does not need it. A governed Document's dependencies
  stay on `depends_on` and `mentions`. A rejection test pins this.

## Tests (written first, run red: 7 failed, 65 passed)

`tests/test_relationship_types.py`:
- accept: `DataFile -> DesignNote`, `DataFile -> Citation`, `Result -> DesignNote`, and the old `Result -> Result`,
  `Result -> Citation`;
- reject: `Document -> DesignNote` and `DesignNote -> DesignNote` (cannot originate), `DataFile -> Script` and
  `DataFile -> Document` (cannot target);
- end to end through `create_link`: `DataFile -> DesignNote` accepted, `DesignNote -> DesignNote` rejected with no
  event and no edge;
- config surface: the full `derived_from` endpoint sets.

## Verification

- check: `python -m dotenv -f .env run -- python -m pytest tests/test_relationship_types.py -q`: **72 passed**.
- check: `python -m dotenv -f .env run -- python -m pytest tests/ -q`: **2486 passed**, exit 0 (14m33s).

## Not done here (per What NOT to do)

No slosh-pipe edge was written from this repository. slosh-pipe creates its 22 `cites` and 2 `derived_from` edges and
closes Issues 1fa6d45b and 1ed73d2e. The `cites` edges need `rel_properties` for `cito_type`, which `seldon link
create` still cannot set from the CLI (open item carried from the parent RESULT).
