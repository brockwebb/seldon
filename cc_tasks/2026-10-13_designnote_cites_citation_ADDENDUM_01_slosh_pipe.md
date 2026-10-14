# Addendum 01 to `cc_tasks/2026-09-28_designnote_cites_citation.md`: second motivating case (slosh-pipe), and a second refused edge

**Date:** 2026-10-13
**Filed from:** slosh-pipe, task 8962cfdb (`cc_tasks/2026-10-13_register_notes_and_registry.md`, steps 4 and 5), branch `build/register`.
**Issues opened there:** 1fa6d45b (`designnote_cites_schema_gap`), 1ed73d2e (`parameter_registry_derived_from_schema_gap`).
**Status of the parent proposal:** still pending. As of seldon 6517ef7, `relationship_types.cites.from_types` in `seldon/domain/research.yaml` is still `[PaperSection, Figure, Document, Section, Ruling]`, and the parent file is untracked in this repository.

This file is written as a separate addendum, not an edit to the parent, because the filing task permits one new file in this directory and nothing else.

## 1. DesignNote as a `cites` source: a second project hits the same refusal

slosh-pipe registered two lab notes as DesignNotes and their 22 citekeys as Citations, all 22 verified (Crossref, doi.org landing page, or page fetch; method, date and by recorded on each). Every `seldon link create <note> cites <citation>` is refused:

```
Error: 'DesignNote' cannot originate a 'cites' relationship. Valid from_types: ['PaperSection', 'Figure', 'Document', 'Section', 'Ruling']
```

The parent proposal's change (add `DesignNote` and `ArchitecturalDecision` to `cites.from_types`) covers this case with no further schema change.

One observation for the implementer: the task that filed this assigns the CiTO intent `uses_data_from` (CiTO `cito:usesDataFrom`) to data sources. The `cito_type` description in `research.yaml` lists six values and not this one. The value is not enforced (`validate_relationship_properties` checks names, not values), so the edges below can be written as they stand; whether the description should name `uses_data_from` is the implementer's call.

Intended edges from slosh-pipe, all `-[cites]-> Citation`. Create them once the schema allows it:

| from (DesignNote) | citation | cito_type |
|---|---|---|
| design_decisions_session_2026_10_13 4d7f3d79 | alemiardakani2012shallow 421cc760 | uses_method_in |
| design_decisions_session_2026_10_13 4d7f3d79 | baritello2020neuromuscular 1718d748 | cites_for_information |
| design_decisions_session_2026_10_13 4d7f3d79 | behm2010canadian 6a142576 | cites_for_information |
| design_decisions_session_2026_10_13 4d7f3d79 | behm2012effectiveness 02e6137e | cites_for_information |
| design_decisions_session_2026_10_13 4d7f3d79 | firefighternation2008use 80f03bb4 | cites_for_information |
| design_decisions_session_2026_10_13 4d7f3d79 | glass2023effect 2bccfc32 | cites_for_information |
| design_decisions_session_2026_10_13 4d7f3d79 | herman2017salib 9a91cae3 | uses_method_in |
| design_decisions_session_2026_10_13 4d7f3d79 | lim2020measuring 38ece829 | uses_data_from |
| design_decisions_session_2026_10_13 4d7f3d79 | mazza2008control d749cfc5 | uses_data_from |
| design_decisions_session_2026_10_13 4d7f3d79 | nagy2023controlling a673773e | uses_method_in |
| design_decisions_session_2026_10_13 4d7f3d79 | nairn2017motion 4c414556 | cites_for_information |
| design_decisions_session_2026_10_13 4d7f3d79 | nrc1997aviation 8b883748 | uses_data_from |
| design_decisions_session_2026_10_13 4d7f3d79 | peterka2002sensorimotor bdfa4f1d | cites_for_information |
| design_decisions_session_2026_10_13 4d7f3d79 | peterka2018implementation 53102999 | uses_method_in |
| design_decisions_session_2026_10_13 4d7f3d79 | saltelli2010variance 3d894128 | uses_method_in |
| design_decisions_session_2026_10_13 4d7f3d79 | schreiber2019multimodal 066e835e | uses_data_from |
| design_decisions_session_2026_10_13 4d7f3d79 | sobol2001global 9dd03aa7 | uses_method_in |
| design_decisions_session_2026_10_13 4d7f3d79 | wang2019effects 144199ac | cites_for_information |
| rigidity_assumption_check_2026_10_13 315b8cba | charlotte2022pvc40 f24abdec | uses_data_from |
| rigidity_assumption_check_2026_10_13 315b8cba | lemmon2026thermophysical e768ce8a | uses_data_from |
| rigidity_assumption_check_2026_10_13 315b8cba | openlab2017ansur2 e1a9e2eb | uses_data_from |
| rigidity_assumption_check_2026_10_13 315b8cba | unibell2016cellclass 323644ec | uses_data_from |

## 2. A second refused edge: a config registry `derived_from` the notes that justify it

slosh-pipe registered `configs/parameters.yaml` (the parameter registry: every model number, with unit, role, provenance per entry and a status; `pending` blocks production) as DataFile `parameter_registry` 427bead8. The task asks for `parameter_registry -[derived_from]-> <note>` for each of the two notes whose decisions and computations justify its entries. Refused:

```
Error: 'DataFile' cannot originate a 'derived_from' relationship. Valid from_types: ['Result']
```

`derived_from` is `[Result] -> [LabNotebookEntry, Citation, Result]`. Neither DataFile nor Document may originate it, and DesignNote may not receive it. `computed_from` (DataFile -> DataFile) and `depends_on` (Document -> Document) do not reach a DesignNote either; `mentions` (Document -> DesignNote) is lexical and asserts no derivation.

Proposed change, for the implementer to weigh against the closed edge set of AD-030 section 4: add `DataFile` and `Document` to `derived_from.from_types`, and `DesignNote` to `derived_from.to_types`. Same discipline as the parent: failing test first in `tests/test_relationship_types.py`, one-line schema changes with a comment naming this addendum, full suite green.

Intended edges:

| from | rel | to |
|---|---|---|
| parameter_registry 427bead8 (DataFile) | derived_from | design_decisions_session_2026_10_13 4d7f3d79 |
| parameter_registry 427bead8 (DataFile) | derived_from | rigidity_assumption_check_2026_10_13 315b8cba |

## What NOT to do

- Do not widen `cites.to_types` or touch any relationship type other than `cites` and `derived_from`.
- Do not create the slosh-pipe edges from this repository; slosh-pipe creates them once the schema lands (its Issues 1fa6d45b and 1ed73d2e close on that).
