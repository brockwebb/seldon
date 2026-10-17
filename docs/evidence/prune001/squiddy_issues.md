# PRUNE-001 Part A: squiddy, open Issues resolved (2026-10-17)

Run record: `docs/evidence/prune001/part_a_run.json` (`seldon prune run`, rules in seldon.yaml `prune:`, code `seldon/core/prune.py`). Before-state: `before_dry_run.json`. Database `seldon-squiddy`.

**Counts.** Open Issues: 56 before the hand pass, 29 after. Proposed tasks 2; FUTURE proposals 0; stale FUTURE (60 days): 0 before, 0 after.

| issue | rule | commit (the reason) | lead |
|---|---|---|---|
| `f694d215` | fixed_marker | `da74a9c4aa6a` | S-008 defect 1, FIXED with its test (tests/test_repodocs.py::test_an_entry_whose_id_yaml_q |
| `0d34b9af` | fixed_marker | `da74a9c4aa6a` | S-008 defect 2, FIXED with its test (tests/test_write_project_export.py::test_cites_layer_ |
| `1f0aacd5` | fixed_marker | `da74a9c4aa6a` | S-008 defect 4, FIXED: two alternate labels differing only in case (Datasamling and datasa |
| `a4841589` | fixed_marker | `da74a9c4aa6a` | S-008 defect 5, FIXED: the vocabulary import re-emitted the decision stubs of a standard t |
| `bb0f933d` | fixed_marker | `aee8cdada7df` | S-009 defect 1, FIXED with its test (tests/test_secrets.py). R-11 says the kit reads crede |
| `9345b935` | fixed_marker | `aee8cdada7df` | S-009 defect 2, FIXED with its test (tests/test_serve_backends.py). The Neo4j writer had n |
| `bee50af2` | fixed_marker | `a2ad022e60c1` | S-015 defect 2, FIXED with its test (tests/test_vocab_terms.py, four tests). squiddy.vocab |
| `51440d07` | fixed_marker | `6e077fa485b4` | H-001 finding 1, FIXED with its tests (tests/test_lessons.py, six tests). The lessons inta |
| `8374b1da` | fixed_marker | `6e077fa485b4` | H-001 finding 2, FIXED with its tests (tests/test_decisions_sources.py, twelve tests). squ |
| `49806b6d` | fixed_marker | `fcc979a51efb` | HV-001 defect 1, FIXED with its test and its control case. squiddy.refs keyed an arXiv id  |
| `ff305bf6` | fixed_marker | `fcc979a51efb` | HV-001 defect 2, FIXED with its test and its control case. The RFC extractor keyed `RFC-00 |
| `77e0f3ce` | fixed_marker | `fcc979a51efb` | HV-001 defect 3, FIXED. squiddy.assess.assess_entry read `provenance_flag` against the gra |
| `daa9a7e5` | fixed_marker | `fcc979a51efb` | HV-001 defect 4, FIXED with six tests. Three defects in the lessons intake, all first visi |
| `4ac56331` | fixed_marker | `fcc979a51efb` | HV-001 finding 7, FIXED. squiddy.acquire.pdf_text_chars let pypdfium2's PdfiumError escape |
| `8af5e609` | fixed_marker | `c502f45f3902` | K-001 defect 1, FIXED with its tests (tests/test_harvest_prune.py, 4). tools.harvest_citat |
| `6b72147b` | fixed_marker | `c502f45f3902` | K-001 defect 2, FIXED with its tests (tests/test_acquire_batch_resume.py, 3). The resume l |
| `f28cedd4` | fixed_marker | `c502f45f3902` | K-001 defect 3, FIXED with its tests (tests/test_ledger_manifest.py, 2, one a mutation tes |
| `07c3321d` | fixed_marker | `c502f45f3902` | K-001 defect 4, FIXED with its test (tests/test_admit_batch.py). The emitter squiddy init  |
| `2d21b823` | fixed_marker | `c502f45f3902` | K-001 defect 5, FIXED in graphs/library/graph.yaml with its reason on the line. Conversati |
| `f262e9ac` | fixed_marker | `c502f45f3902` | K-001 defect 6, FIXED with its tests (tests/test_init.py, 3). squiddy init --check compare |
| `e377d2de` | fixed_marker | `c502f45f3902` | K-001 defect 7, FIXED with its test (tests/test_admit_batch.py). tools.admit_batch reporte |
| `368cc06a` | fixed_marker | `c502f45f3902` | K-001 defect 8, FIXED with its test and its control (tests/test_refs.py, 2). '10.48550/arX |
| `61f7097b` | fixed_marker | `c502f45f3902` | K-001 defect 9, FIXED. tools.verify_library_reinit_diff read the KGX category and predicat |
| `597307a2` | fixed_marker | `c502f45f3902` | K-001 defect 11, FIXED in graphs/library/graph.yaml. engine.serve.text_fields had no entry |
| `09154c9a` | fixed_marker | `8ec15b53eff8` | HV-002 defect 1, FIXED with its test (tests/test_acquire_batch_resume.py). The acquire rec |
| `20304971` | fixed_marker | `8ec15b53eff8` | HV-002 defect 2, FIXED. A source client read a non-JSON HTTP 200 as an EMPTY RESULT. dblp. |
| `3d93d96e` | fixed_marker | `8ec15b53eff8` | HV-002 defect 3, FIXED. My own calibration handed the NORMALIZED identifier to the ground- |

`fixed_marker`: the commit is the branch head when the Issue was filed; an Issue whose own lead says FIXED was filed after its fix.

**Left open by the negation and first-marker guards:** `c0d80b20`, `78abfb1b` (NOT FIXED), `22af256c`, `d91b4604` (MEASURED not fixed), `dc636a65` (NOT FIXED, then a later RESOLVED). `8e888b61` stays open: its CLOSED is a sub-finding about 900 characters in, and its condition (3) is NOT FIXED.
