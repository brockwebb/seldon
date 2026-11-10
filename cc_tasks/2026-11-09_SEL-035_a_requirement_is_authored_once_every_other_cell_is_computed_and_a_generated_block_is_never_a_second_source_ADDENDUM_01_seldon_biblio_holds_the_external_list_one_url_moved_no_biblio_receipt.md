# ADDENDUM 01 to 2026-11-09_SEL-035_a_requirement_is_authored_once_every_other_cell_is_computed_and_a_generated_block_is_never_a_second_source: seldon-biblio now holds the external list; one URL moved; no seldon-biblio receipt yet

**Author:** OODA knowledge source on 91998dc1 (AD-038-R16)
**Predecessor:** SEL-036 (`91998dc1`), RESULT `cc_tasks/2026-11-09_SEL-036_seldon_gets_a_bibliographic_graph_every_cited_source_is_a_resolved_work_with_its_metadata_and_text_RESULT.md`
**Governing for this addendum:** AD-036 ADDENDUM 12 (R21, R22, and its section 4).

All four premises still hold. SEL-036 cataloged every source in this task's "Prior art" list into
`graphs/seldon-biblio` and changed how the library arm searches. That changes four things in Part A and one in the
tests. Parts B to F are otherwise unchanged.

## 1. Part A, `### External`: one cited URL has moved

`https://github.com/itsallcode/openfasttrace/blob/main/doc/user_guide.md` returned 404 at HEAD on 2026-11-09
(SEL-036 `evidence/sel036/units.jsonl`; seed `sw_openfasttrace`, field `texts_moved`). The guide is now
`https://github.com/itsallcode/openfasttrace/blob/main/doc/user_guide/user_guide.md`. Cite the new URL. Say on the
receipt that the task file cited the old path, and that the Desktop thread's fetch date of 2026-11-09 still applies
to everything else in the list.

## 2. Part A, `### External`: give each source its catalog id

Each external source is now an entry in seldon-biblio (`graphs/seldon-biblio/intake/seeds.yaml`, block
"AD-013 ADDENDUM 01 section 2 and SEL-035"). Add the entry id beside each URL, so that a later R22 bridge run can
point the addendum's citations at their works without a second reading:

| source in this task | seldon-biblio entry |
|---|---|
| Doorstop (site) | `sw_doorstop` |
| Browning and Adams, Doorstop paper (JSEA 2014) | `browning2014doorstop` (metadata only; its open text is off SEL-036's network allowlist) |
| OpenFastTrace | `sw_openfasttrace` (the held page is the guide's index; the guide's child pages were not fetched) |
| StrictDoc | `sw_strictdoc` |
| sphinx-needs (needtable, dynamic functions) | `sw_sphinx_needs` |
| Cog (`running.html`) | `sw_cog` |
| ISO/IEC/IEEE 15288 / 29148 | `iso15288_2023`, `iso29148_2018` (`access: purchase`, metadata only) |
| INCOSE verification methods | `scukanec2010verification`, `argondigital_verification_methods` |

SEL-036 also added `sw_requiem` (suspect-link fingerprints) under SEL-035. It is the nearest prior art for Doorstop's
`reviewed` fingerprint in this list. Cite it, or say in the addendum why it is not cited. Do not leave it out without
a word.

## 3. Part A, receipts: do not write a `graph seldon-biblio` library receipt

`prior_art.library.graph` in seldon.yaml is now a list: `../squiddy/graphs/library`, then `graphs/seldon-biblio`.
Under R21, `seldon prior-art search --library` prints one receipt for each graph that answered, plus an
"unavailable" line for each graph that could not answer.

The primary checkout has no served release of seldon-biblio. Checked 2026-11-09: no `work/` directory under
`/Users/brock/GitHub/seldon/graphs/seldon-biblio`, because the RESULT's after-merge recipe has not been run. A
dispatched worktree has none either (no `dispatch.worktree_links` for it). Therefore:

- `graph seldon-biblio: unavailable` in this task's search output is expected, and it is not a failure.
- AD-013 ADDENDUM 02 must not carry a receipt that names `graph seldon-biblio` unless that graph's served release is
  present in the primary checkout when the addendum is verified. Under ADDENDUM 12 section 4, such a receipt fails
  `release_unavailable`. A FAIL verdict on the AD-013 family would hold every task that AD-013 governs.
- Receipts from squiddy's library and from the internal arm are written as before. SEL-036 Part F found that squiddy's
  library answers none of this domain's queries, so expect few or no library rows there. Record that as a finding.
  Do not pad it.
- If the release exists in the primary checkout by the time this task runs, seldon-biblio receipts are allowed. Say
  in the RESULT which case held.

## 4. Domain config and the tests that pin it

SEL-036 added `ExternalReference` and `resolves_to` to `seldon/domain/research.yaml` (R22). When Part C removes the
four verbatim properties and adds `verification_method`, keep both additions. Two tests pin the domain's contents:
`tests/test_docs.py::test_artifact_types_has_all_types` and `tests/test_domain.py::test_load_domain_config`. SEL-036
had to update both (`b62476d`). Update them in the same commit as the config change.

## 5. Suite failures already known (do not chase these)

These failures are already known and are not caused by this task:

- `test_pa002_release_resolve::test_rebuilding_the_served_release_reproduces_the_served_index`: library index drift.
  It fails on main.
- `test_sel024_gate_record::test_fixture_a_regate_whose_gate_outlasts_lock_wait...`: fails under load, on main too.
- `test_dispatch_parallel::test_two_disjoint...`: flaky; it passes when run alone.

Any other failure belongs to this task.
