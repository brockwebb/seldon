# AD-036 ADDENDUM 15: the zero-model-calls instrument runs on the outer session, and a rebuilt release the kit's reader refuses is `release_unavailable`

**Date:** 2026-11-24. **Status:** Accepted. Implemented by SEL-043 Part E
(`cc_tasks/2026-11-21_SEL-043_a_consumer_waits_on_a_producer_only_for_what_can_hurt_it_and_a_running_gate_shows_its_progress_and_its_wall_time.md`),
answering squiddy's filings `083863ef` (item 3: R9's instrument is 41 percent of a squiddy suite run) and `9fb2e0b8`
(an older release rebuilds into an index the kit's reader can read; the reader refuses one it cannot by name; the
rebuild reads the corpus checkpoint under arm A's rule). **Extends:** AD-036-R9 (a test never spends unasked; a PATH
shim that records invocations proves zero calls by default) and AD-036-R19 (a superseded release verifies, and one
that cannot be rebuilt is named `release_unavailable`). Three new rulings, AD-036-R28 to R30.
**Code:** `tests/r9_shim.py`, `tests/conftest.py`; `seldon/core/prior_art.py` (`open_rebuilt`, `checkpoint_rows`,
`KIT_RELEASE_ROWS`). **Tests:** `tests/test_no_live_model_calls.py`, `tests/test_sel043_release_rows.py`.
**Evidence:** `docs/evidence/sel043/r9_runs.txt`.

## 1. Evidence

1. **R9's instrument as each project ran it.** seldon's was a nested pytest over six launcher-adjacent test files
   with a recording `claude` first on PATH: 66.7, 71.1 and 95.8 s, 0.39 to 0.40 GB peak resident (children included),
   in three runs alone on 2026-11-24 (`docs/evidence/sel043/r9_runs.txt`, `tools/r9_measure.sh`). squiddy's
   (`tests/test_pa001_zero_model_calls.py`, filing `083863ef`) is 1,278.5 s of a 3,094.6 s run and about 9.8 GB at its
   peak, three times per kit pass; three runs side by side took squiddy's host 25.5 GB into swap.
2. **What the assertion is about.** "No test invokes `claude` by default" is a property of the commit: of the test
   files and the code they reach, not of the order a run takes them in. The outer session of the suite is a larger
   subject on the same commit: every test file, not six.
3. **The reader's refusal reached seldon as a traceback.** Since squiddy SQ-139, `squiddy.index.Index` checks the index
   it is handed when it opens it and raises `IndexSchemaError` (`index_schema_mismatch: ...`, a `RuntimeError`).
   `open_rebuilt` let it through. With SQ-139's new `build_db` default it cannot fire on seldon's own rebuild, but an
   index built elsewhere would surface as a crash where AD-036-R19 asks for a named refusal.
4. **The rows of an older release come from arm A's rule.** `_release_rows` named `iter_rows`' arguments itself and so
   took its default rule, `q003-corpus/1`. squiddy measured on the library's checkpoint (2026-11-13): of 2,261 units
   with rows under both that rule and the rule the releases were cut under, 3 differ; rows under arm A's rule carry no
   `text_sha256`; and a graph whose checkpoint holds no arm A lines (seldon-biblio and hazbrief-corpus declare
   `text_of_record: parsed`) gets `release_unavailable` for every older release. The rule a release was cut under is
   not in its export; the kit alone knows it.

## 2. Prior art

### External

- **Measurement system analysis** (AIAG, *Measurement Systems Analysis*, 4th edition): an instrument is accepted on its
  ability to detect what it is meant to detect, shown with known references, not on its form. Adopted for R28: the
  new instrument is accepted by its positive controls (a planted call fails the session, serially and under xdist) and
  its negative control (a clean session passes), the same evidence R9's nested run carried. Cited by name; not fetched.
- **Feature detection over version checks** (the practice the Python packaging and web-platform communities use:
  test for the attribute, not the version string): adopted for R30's call on the kit, because the kit's version is not
  a contract and its call is. Cited from general practice; not fetched.
- The library arm holds nothing on either (searched 2026-11-24):
- library receipt: query "test instrument measurement system analysis" | graph library | release library_graph_20261110_sq133r_b.r1_2026-11-13.json sha256:c38db2b4106bbc762c984d545e044a60ac0a91923254ba2e4de8cf8a3964d784 | rows lesson:2026-05-09_arXiv_2601_18278#p11:148:0-286, lesson:2026-05-09_arXiv_2601_18278#p7:102:490-4604, lesson:2026-05-09_arXiv_2601_18278#p3:17:4204-5719, lesson:2026-02-22_arXiv_2503_10265#p7:127:1079-1107, lesson:2026-02-22_arXiv_2503_10265#p3:42:604-615, lesson:2026-02-22_arXiv_2503_10265#p3:70:3888-3898, lesson:2026-02-22_arXiv_2410_20285#p27:357:1306-1340, lesson:2026-02-22_arXiv_2406_04046#p31:462:241-380, lesson:2026-02-22_arXiv_2406_04046#p35:522:280-562, lesson:2026-02-22_arXiv_2406_04046#p31:461:60-239, lesson:2026-06-17_10_1007_s41109_025_00749_0#p24:235:686-859, lesson:2026-02-22_arXiv_2503_22678#p4:38:79-120, lesson:2026-02-22_arXiv_2503_22678#p7:76:1658-1728, lesson:2026-02-22_arXiv_2505_15155#p39:802:788-1020, lesson:2026-02-22_arXiv_2505_15155#p5:167:2682-2895, lesson:2026-02-22_arXiv_2505_15155#p31:644:1934-1976, lesson:2026-02-22_arXiv_2405_07960#p32:279:0-377, lesson:2026-02-22_arXiv_2405_07960#p29:243:1489-1614, lesson:2026-02-22_arXiv_2405_07960#p11:67:1821-1849, lesson:2026-05-09_arXiv_2602_22302#p31:512:1942-2549, lesson:2026-05-09_arXiv_2602_22302#p29:487:2282-2710, lesson:2026-05-09_arXiv_2602_22302#p49:770:0-787, lesson:2026-03-15_arXiv_2403_00578#p3:105:365-732, lesson:2026-05-09_arXiv_2506_16697#p3:21:3-133, lesson:2026-05-09_arXiv_2506_16697#p11:136:1235-2412, lesson:2026-05-09_arXiv_2506_16697#p4:30:94-526, lesson:2024-11-04_10_6028_nist_ai_600_1#p53:762:985-1655, lesson:2024-11-04_10_6028_nist_ai_600_1#p28:338:395-583, lesson:2024-11-04_10_6028_nist_ai_600_1#p42:565:183-592, lesson:2026-02-22_arXiv_2508_21767#p13:269:465-803, lesson:2026-02-22_arXiv_2510_22954#p60:707:0-675, lesson:2026-02-22_arXiv_2510_22954#p61:718:0-584, lesson:2026-02-22_arXiv_2507_22606#p20:317:2843-3079, lesson:2026-02-22_arXiv_2507_22606#p18:245:103-307, lesson:2026-02-22_arXiv_2507_22606#p8:85:1237-1611, lesson:2026-07-09_arXiv_2602_06448#p5:122:1875-2325, lesson:2026-02-22_arXiv_2507_06229#p32:594:0-251, lesson:2026-05-09_arXiv_2508_04826#p3:34:4679-5233, lesson:2026-05-09_arXiv_2508_04826#p11:236:117-1140, lesson:2026-05-09_arXiv_2508_04826#p10:230:2330-2442, lesson:2026-02-22_arXiv_2410_05080#p5:77:686-910, lesson:2026-02-22_arXiv_2506_06972#p6:233:1444-1773, lesson:2026-02-22_arXiv_2506_06972#p16:453:46-1058

### Internal

- internal receipt: query "PATH shim that records invocations" | repo seldon@0d980545529e93b51a9a58fa2cd4156acb154496 | hits docs/design/AD-036_prior_art_receipts_gate.md:137, docs/decisions/register/00230_seldon-ad-036-r9_accept.yaml:1, docs/decisions/register/00247_seldon-ad-036-r9_amend.yaml:1, docs/decisions/REGISTER.md:9
- internal receipt: query "release_unavailable" | repo seldon@0d980545529e93b51a9a58fa2cd4156acb154496 | hits docs/design/AD-036_ADDENDUM_06_receipts_resolve_the_named_release.md:113, docs/design/AD-036_ADDENDUM_01_self_test.md:33, docs/design/AD-036_ADDENDUM_06_receipts_resolve_the_named_release.md:3, docs/design/AD-036_ADDENDUM_06_receipts_resolve_the_named_release.md:11, docs/design/AD-036_prior_art_receipts_gate.md:80, docs/design/AD-036_ADDENDUM_07_self_citation_and_the_governing_header.md:9, docs/design/AD-036_ADDENDUM_12_the_library_arm_searches_a_list_of_graphs_and_a_citation_resolves_to_its_work.md:64, docs/decisions/register/00333_seldon-ad-036-r19_accept.yaml:1, docs/decisions/register/00223_seldon-ad-036-r2_accept.yaml:1, docs/decisions/register/00240_seldon-ad-036-r2_amend.yaml:1, docs/design/AD-036_ADDENDUM_11_a_superseded_release_verifies_and_the_ledger_commits_with_its_note.md:70, docs/design/AD-036_ADDENDUM_12_the_library_arm_searches_a_list_of_graphs_and_a_citation_resolves_to_its_work.md:48, docs/design/AD-036_ADDENDUM_13_the_verdict_ledger_merges_by_union_and_a_held_release_is_read_through_squiddys_accessor.md:57, docs/decisions/register/00352_seldon-ad-036-r24_accept.yaml:1, docs/design/AD-036_ADDENDUM_13_the_verdict_ledger_merges_by_union_and_a_held_release_is_read_through_squiddys_accessor.md:18, docs/design/AD-036_ADDENDUM_06_receipts_resolve_the_named_release.md:26, docs/decisions/register/00342_seldon-ad-036-r21_accept.yaml:1, docs/design/AD-036_ADDENDUM_11_a_superseded_release_verifies_and_the_ledger_commits_with_its_note.md:16, docs/decisions/REGISTER.md:9
- internal receipt: query "zero model calls PATH shim recording claude invocations" | repo seldon@0d980545529e93b51a9a58fa2cd4156acb154496 | hits docs/decisions/REGISTER.md:9

AD-036 line 137 is R9 and register record 00247 its statement as amended by PA-001 ("a PATH shim that records
invocations shall prove zero model calls by default"): R28 keeps that statement and changes where the shim runs. The
`release_unavailable` hits are AD-036-R19's refusal and ADDENDUM 06's rebuild, which R29 and R30 extend. The register
(`docs/decisions/REGISTER.md`) is the receipt outside this family.

## 3. Rulings

- **AD-036-R28. R9's recording shim may run on the outer test session itself: the suite's controller puts it first on PATH for the whole session, every worker and subprocess inherits it, and a session in which it recorded a call fails, naming the calls.**
  It is accepted by its controls, which the suite carries: a planted call fails a session with only the shim loaded,
  serially and under xdist; a clean session passes; and the running session checks that `claude` resolves to its
  shim. `LIVE_MODEL_CALLS=1` (R9's opt-in) turns it off. seldon replaces its nested run with it
  (`tests/r9_shim.py`). What a consumer running the instrument may now do: (a) run the shim on its outer session in
  place of a nested run, with the same three controls, which costs no run time and covers every test file; or (b)
  keep a nested run and run it once per commit rather than once per run (once per kit pass in squiddy), since its
  assertion is a property of the commit. Whether a kit pass may share one reading across its runs is squiddy's to rule
  (its R-184); (a) needs no such ruling, because every run is then its own instrument.
- **AD-036-R29. A rebuilt release that the kit's reader refuses when it opens it (`IndexSchemaError`) is `release_unavailable`, naming the release, the commit it was rebuilt from and the reader's message; any other error of the reader is raised as it was.**
  The error class is looked up on the kit by name, so a kit from before SQ-139 still imports.
- **AD-036-R30. seldon reads an older release's rows through the kit's `release_rows(graph, manifest, *, commit)` when the installed kit has it, and otherwise as before; until then the rows come from arm A's rule, a known limit beside AD-036-R19.**
  The call is asked of squiddy: it returns the rows of the release recorded at `commit` under the row rule that
  release was cut under, and refuses as `iter_rows` does (SystemExit naming the unit) when a unit has none. It is
  feature-checked by name (`KIT_RELEASE_ROWS`). The known limit until it exists: for the library, 3 of 2,261 units'
  rows differ from what the releases served and rebuilt rows carry no `text_sha256`; for a `text_of_record: parsed`
  graph, every older release is `release_unavailable`. No row read changes before the kit's call exists.

## 4. What this does not change

1. R9's statement and its opt-in variable. A test that replaces PATH wholesale escapes the shim, as it escaped the
   nested run.
2. Which receipts verify. AD-036-R19's answers for superseded releases are unchanged until R30's call exists.
