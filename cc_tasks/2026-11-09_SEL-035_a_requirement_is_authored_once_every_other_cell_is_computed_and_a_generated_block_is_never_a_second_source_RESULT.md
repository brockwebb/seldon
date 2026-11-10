# RESULT: SEL-035, a requirement is authored once, every other cell is computed, a generated block is never a second source, and a test declares what it verifies

**Task:** `cc_tasks/2026-11-09_SEL-035_a_requirement_is_authored_once_every_other_cell_is_computed_and_a_generated_block_is_never_a_second_source.md`
(086d89ff), with its ADDENDUM 01 (seldon-biblio holds the external list). **Branch:** `worktree-gentle-chasing-minsky`
(merged by the dispatcher). **Design note:** `docs/design/AD-013_ADDENDUM_02_authored_once_computed_everywhere_else.md`.

Recall used: seldon:2026-11-09_SEL-033_requirements_and_decisions_live_in_the_graph_and_the_rtm_is_a_projection_RESULT, seldon:issue-83b09573, seldon:issue-1cc32488, seldon:issue-f42b75b2

(SEL-033's RESULT gave the load route, the 21 RTM rows that name a harness or a judgment, and hazbrief's three
projections, which Parts B and F re-measured. The three Issues are the findings this task answers; f42b75b2 stays
open, as the task says.)

## Outcome

All six Parts done. A requirement now keeps only its authored fields; every other projection cell is computed from
the state and the edges at render; a marked table is output only, and a hand-edited block is refused; a test
declares what it verifies with `@pytest.mark.verifies`, and `seldon req trace` keeps the edges. On a scratch copy of
hazbrief-mcp: `seldon req migrate` moved all 226 requirements off their verbatim cells (1,365 table cells compared:
**no word of any row lost**, class (c) empty), and the 19 cells that disagreed with the graph before this task (Part
B) are exactly the 19 the render now corrects. `seldon/core/requirements.py` is **826 lines, 43 KB** (was 1,101,
53 KB); the requirement code as a whole grew, for the reasons in "Size" below.

Two defects were found by Part F's class (c) check and fixed before the return, each with a test (see Part F). One
departure from the task text in each of A and C, recorded in the rulings (see Part A).

## Part A: the rulings

`docs/design/AD-013_ADDENDUM_02_authored_once_computed_everywhere_else.md`. `seldon prior-art verify` **PASS** before
B to F (sha256 9d514e663f92, event `4da76eeeadef42e99bd685f37682a720`) and again after Part F amended R4's text
(sha256 91b134d94eda, event `f2faf8c5243e43a5955615106a284923`), both in the governed ledger. Register records pending
(numbered at merge, AD-033-R12): amendments of **AD-013-R1** and **AD-013-R2**, new **AD-013-R4**, **R5**, **R6**.

- **AD-013-R1 amended:** authored fields are `requirement_id`, `description`, `set_by`, `document`, `section`,
  `verification_method` (test, inspection, analysis, demonstration; default test), `note`. Departure: the task named
  four verbatim columns; `decision_text` (hazbrief HB-144's Decision column) is the fifth of the same kind and is
  removed too; its trace is the `derived_from` edges to register records.
- **AD-013-R4 new:** every other cell is computed (Status = the state's label, from the projection's or the
  project's `state_labels`, then `: ` and the note; Verified-by, Satisfied-by, Derived-from, Decision from edges); a
  column whose source is neither authored nor computed is refused when the projection is read. One refinement,
  from the measurement: hazbrief maps nine status words onto four states, so a note that opens with a status-map
  word naming the current state, delimited (end, `:`, `;`, `,`, `.`, ` (`), is shown without the label (`changed`,
  `partial`, `not met`); when the state moves, the label is prefixed and the stale qualifier shows.
- **AD-013-R2 amended:** import refuses a marked file (naming `req add` / `req update`); generate refuses a file whose
  blocks no longer hash to the stamped revision (Cog `-c`), prints the differing rows and writes nothing;
  `--discard-edits` is the only override.
- **AD-013-R5 new:** `@pytest.mark.verifies(...)` read with `ast`; `verified_by` edges marked `declared_by: marker`;
  `seldon verify` reports the trace's plan and does not write (a check reads, as `check_prior_art` reads verdicts).
- **AD-013-R6 new:** unverified counted by method; a non-test method reaches `verified` on a `verified_by` edge to a
  **Result or Issue**. Departure: the task said "Document, Result or Issue"; Document is left out because the
  domain's endpoint sets are independent and admitting it would admit `Issue -> Document`, which AD-030 section 4's
  closed edge set refuses (the same reason AD-013-R1 left it out of the sources).
- **Prior art:** the Desktop thread's fetched list as web receipts dated 2026-11-09, each with its seldon-biblio id
  (ADDENDUM 01 section 2), the OpenFastTrace guide at its moved URL with the old path named, Requiem cited and not
  adopted (no ruling here makes links suspect). **seldon-biblio was unavailable** (no served release in the primary
  checkout), so no receipt names `graph seldon-biblio` (ADDENDUM 01 section 3, its first case). Squiddy's library
  answered three queries with nothing on the subject but the operator's ANTS repository, again (finding, not padded);
  five internal queries across seven repositories found only AD-013 ADDENDUM 01 itself.

## Part B: the before numbers (scratch: hazbrief-mcp HEAD `63cc7da2` cloned to /tmp, its event log replayed into a scratch database, 7,903 events; the graph matched the live one, 226 nodes)

1. **Cells that disagree with the graph:** 21 before any operation (19 status cells say `satisfied`, `changed` or `met`
   on rows the graph holds at `implemented` for want of a test; 2 verification cells name a test set that differs
   from the edges). `seldon req add VR-025 --status "withdrawn: ..."` added **0** (it writes text and state together).
   A `satisfies` link from HB-142R to S3-2 (what a task close does) added **1** stale cell (RTM Satisfied-by), and
   `seldon docs generate rtm --check` did **not** report it: the render read the text. Rendered stale after both: 21.
2. **A hand-edited block:** VR-002's statement edited inside its marker block; `seldon docs generate requirements`
   **overwrote** it, exit 0, no message (sha256 `43de0882...` back to the committed `6c840843...`).
3. **`seldon/core/requirements.py`:** 1,101 lines, 53 KB.

## Part C: computed cells and the migration

- `seldon/core/requirements.py`: authored fields only; `status_cell`, `cell_value` and `render_counts` compute from
  the state and edges (per-projection `state_labels` and `none_text`); `settings` refuses a non-computable column.
- `seldon/core/req_migrate.py` + `seldon req migrate [--dry-run]`: per requirement still carrying a verbatim cell, the
  cells are placed by `req_load.place_cells` (section 4.1 of the addendum) and the five properties removed, one
  `artifact_updated` event per node through the log; a second run writes nothing.
- The markdown onboarding load moved to `seldon/core/req_load.py` (it is a different responsibility: reading tables);
  `import` places a row's cells by the same function, so an import never stores a verbatim cell either.
- Domain: `SRS_Requirement` loses the five properties and gains `verification_method` and `note`;
  `verified_by` reaches Result and Issue and carries an optional `declared_by`.

## Part D: one direction

`seldon req import` refuses a marked file; `seldon docs generate` refuses a hand-edited one (rows printed, nothing
written) and `--discard-edits` regenerates; `seldon req add` creates and `seldon req update` changes authored fields,
the state (`verified` only with a qualifying edge) and evidence (`--evidence <Result or Issue id>`). A discarded
edit that restores the committed bytes reports "nothing to commit" instead of failing (found by the test). The tests
were written with the code, not before it; the before behaviour they guard was measured in Part B (overwrite).

## Part E: declared coverage

`seldon/core/req_trace.py` + `seldon req trace [--dry-run]`: function, class and method markers; a parametrized test
binds its function; a marker edge whose marker is gone is removed; a requirement a marker names loses its imported
test edges (SEL-033's); an unknown id, a non-literal argument and a file that does not parse are listed, not fatal;
a second run writes nothing. `seldon verify`'s Requirements check counts the unverified by method, names a
`verified` requirement with no qualifying edge, and reports the trace's pending edges and findings without writing.
`seldon project new` registers the marker (`pyproject.toml` `[tool.pytest.ini_options]` markers, or a `pytest.ini`
when there is no pyproject; never a pytest.ini beside a pyproject, which would silently replace its pytest config).

## Part F: the proof on the scratch copy, and the after numbers

Fresh scratch (same HEAD), hazbrief's hand steps scripted (`/tmp/sel035/f_prepare.py`: per-projection
`state_labels` VIEW `{verified: satisfied, accepted: open, rejected: withdrawn}`, RTM `{verified: met, implemented:
evidence in place, rejected: not met (ruled out)}`, RTM `none_text: none`, column sources remapped to `@decision`,
`@satisfied_by`, `@verified_by`, `@status`, VIEW's `Validated by` column dropped from seldon.yaml and from 27 block
`headers`), then the three commands in order:

- `seldon req migrate`: 226 migrated, 4 given a method (T-2, T-4 inspection; G-2, G-3 "judged, not tested" →
  inspection); 162 cells no edge carries kept in the note and listed (64 satisfied-by, 43 validated-by, 36
  verified-by, 19 status). Second run: 0. Survey after: 0 of each verbatim property.
- `seldon req trace`: 116 test files, 0 marked nodes (hazbrief has no markers yet); 0 events.
- `seldon docs generate requirements`, then `rtm`.

**Every cell that differs from hazbrief's committed files** (`/tmp/sel035/f_compare.py`, 231 rows in 3 files' tables,
1,365 cells; the RTM's `Open findings` table rides along unchanged):

| class | cells | what |
|---|---|---|
| (a) identical | 919 | ID, Requirement, Set by, Decision, Criterion everywhere; 113 VIEW Status; 114 VIEW Verified by |
| (a) same words, re-punctuated or reordered | 69 | 46 VIEW and 22 RTM verification cells list the same tests in sorted order; 1 empty satisfied-by `none` → `—` |
| (a) words moved to the note | 358 | VIEW `Validated by` (161: the column is gone; 43 records now in the Status cell's note); RTM Satisfied by (64: the cell is now the `satisfies` sources, the code paths are in the note); RTM Checked by (39: harness, inspection, bare test names, now `none` or `inspection: none` with the words in the note); 93 Status/State cells carrying those moved words, or a separator normalised (`met (HB-34` → `met: (HB-34`) |
| (b) stale or wrong | 19 | exactly Part B's 19: VR-060, VR-094, VR-097, VR-098 (`satisfied` → `implemented: satisfied`), VR-143 (`changed` → `implemented: changed`), and 14 RTM rows `met` → `evidence in place: met ...` (S3-6, I-1, T-2, T-4, G-1a, C6, E-D2, E-D3, E-D5, E-D6, O-D2, O-D3, O-D4, O-D7): each said satisfied/met with no verifying test |
| (c) wording lost | **0** | every word of every old row is in its new row |

Plus the counts sentence, which follows from (b): "161 rows: 117 satisfied, 27 open, 14 changed, 3 withdrawn" →
"**113** satisfied, 27 open, **13** changed, 3 withdrawn" in REQUIREMENTS_TRACE.md and EVALUATION.md.

**Class (c) was not empty on the first pass, and the migration was not done until it was.** Two defects, fixed and
tested: (1) 13 RTM rows whose status was exactly the label (`met`) kept `satisfied by: ...` in the note, and the render
read `satisfied` as a qualifier and dropped `met`; a qualifier must now be delimited, and R4's text says so (the note
and its records were re-made and re-verified). (2) E-D2 to E-D6 and O-D4 named bare test functions with no file; no
edge carries them, yet the cell was dropped as if one did; a test name now counts only after a file token.

**After numbers (Part B again, on the migrated scratch):**
1. Cells that can disagree with the graph: **0** by construction (no verbatim cell remains). The same two operations:
   `seldon req update VR-025 --state rejected --note ...` renders `withdrawn: ...`; the HB-142R `satisfies` link
   renders in S3-2's Satisfied-by, and `docs generate rtm --check` now exits 1 on it (before: silent).
2. A hand-edited block: **refused**, exit 1, the edited row printed, file byte-identical (sha256 `1a89955c...` before
   and after).
3. `seldon/core/requirements.py`: **826 lines, 43 KB**.

hazbrief's live files hash to their SEL-033 stamps (`50d5494b2fb71fe0`, `cae03581f03532dd`, `103d9b4bdcf1770d`), so
its first `docs generate` under this code is not refused.

**The return:** `seldon cc return 086d89ff --to hazbrief-mcp --answers seldon:SEL-032` (this task has no
**Answers:** header; it follows SEL-033's answer to hazbrief's SEL-032) filed hazbrief-mcp **HB-149** (task
`f5473a1e`, `cc_tasks/2026-11-10_HB-149_a_requirement_is_authored_once_every_other_cell_is_computed_a_generate.md`,
registered and committed there) from the `## For hazbrief-mcp` section below. Nothing else was written to
hazbrief's repository or graph; the scratch clone and database (`seldon-sel035-hb`) were dropped.

### Size

`requirements.py` shrank from 1,101 to 826 lines because the markdown load moved to `req_load.py` (512) and the
verbatim-column path is gone. The requirement code as a whole grew from 1,236 lines (`requirements.py` +
`commands/req.py`) to 1,799 (`requirements.py` 826, `req_load.py` 512, `req_trace.py` 174, `req_migrate.py` 91,
`commands/req.py` 196): the trace (R5), the one-time migration (deletable once every consumer has run it), `req
update` with states and evidence, the edited-block refusal, and the cell-placement rules that replaced storing text.

## Issues

- `83b09573` (verbatim columns): disposition fixed, `remediated_by` 086d89ff, `verified_by`
  `TestMigrate::test_migrate_places_every_cell_removes_them_and_is_idempotent`,
  `TestMigrate::test_a_later_satisfies_edge_and_state_move_show_in_the_cells`,
  `TestComputedCells::test_status_is_the_label_then_the_note`, `changes` AD-013.
- `1cc32488` (edit the table and re-import): disposition fixed, `remediated_by` 086d89ff, `verified_by`
  `TestOneDirection::test_a_hand_edited_block_is_refused_with_its_rows_and_survives`,
  `TestOneDirection::test_a_marked_file_refuses_import_and_an_unmarked_one_imports`,
  `TestOneDirection::test_discard_edits_regenerates`, `changes` AD-013. (`--changes seldon:AD-013-R1|R2` was
  refused: those register records are not projected as Decision nodes in seldon's graph; the AD name was used.)
- `f42b75b2` left open: this task's addendum answers its part (a) by carrying fetched sources as web receipts; part
  (b) (the gate passing on receipts no ruling cites) is its own task.

## Tests

- `tests/test_sel035_authored_once.py` (29): computed cells, the qualifier and its delimiter, the placement rules
  one by one (bare test names kept), the migration on SEL-033-shaped nodes and its idempotence, a later edge and state
  shown, the refusal and its rows, `--discard-edits`, a graph move rendered, import refusal, `req update`, the AST
  scan (function, class, method, parametrized, unparsable, non-literal), the trace (replace, idempotent, removed
  marker), verify reading the plan, evidence for a non-test method, the marker in pyproject and pytest.ini.
- Changed to the amended rulings: `tests/test_sel033_requirements.py` (the fixture loses `Validated by`; VR-003's
  computed status; `req add`/`update`; the method-split wording), `tests/test_sel021_review_findings.py` (the
  widened `verified_by` targets; `issue orphans` still counts only a test Script).
- Full suite on the final code (`-n 6`, 27 min): **3365 passed, 3 failed, 7 skipped**. All three are the known
  failures of ADDENDUM 01 section 5, none this task's: `test_pa002_release_resolve::test_rebuilding_the_served_release_reproduces_the_served_index`
  (library index drift), `test_sel024_gate_record::test_fixture_a_regate_whose_gate_outlasts_lock_wait_does_not_refuse_a_concurrent_filing`
  (timing under load), and `test_dispatch_parallel::test_two_disjoint_non_exclusive_tasks_run_concurrently_and_both_merge`
  (flaky; re-run alone: 1 passed). An earlier full run, before Part F's two fixes, had 3364 passed and the first two.

## For hazbrief-mcp

What changed (seldon SEL-035, AD-013 ADDENDUM 02): a requirement is edited in the graph, never in the table.
A requirement keeps only its authored fields (id, statement, set_by, document, section, verification_method, note);
its Status cell is computed from its state's label and its note, and Verified-by, Satisfied-by and Decision from its
edges. A table inside projection markers is output: `seldon req import` refuses your marked files, and
`seldon docs generate` refuses a block edited by hand (it prints the rows and writes nothing; `--discard-edits` drops
the edit). HB-146 step 1's "or edit the table and re-run `seldon req import`" is withdrawn.

**Do this once, in hazbrief-mcp's primary, in order, after SEL-035 is on seldon's main:**

1. `seldon.yaml`, `docs.projections`:
   - `docs/VIEW_REQUIREMENTS.md`: delete the `{header: Validated by, source: validated_by}` column (no edge computes
     it; the migration moves its 43 records into each row's note), and add
     `state_labels: {verified: satisfied, accepted: open, rejected: withdrawn}`.
   - `docs/REQUIREMENTS_TRACE.md`: change the sources `decision_text` → `'@decision'`, `satisfied_by_text` →
     `'@satisfied_by'`, `verified_by_text` → `'@verified_by'`, `status_text` → `'@status'`; add
     `state_labels: {verified: met, implemented: evidence in place, rejected: not met (ruled out)}` and
     `none_text: none`.
   - `docs/submission/EVALUATION.md`: add the VIEW `state_labels` above (its counts block counts VIEW's rows).
   These are the labels SEL-035 proved on a scratch copy; they are your vocabulary's call.
2. Drop `Validated by` from VIEW's 27 block markers (the marker line is outside the rendered block):
   `sed -i '' 's/|Validated by|/|/' docs/VIEW_REQUIREMENTS.md`
3. `seldon req migrate --dry-run`, read its list (162 cells kept in notes), then `seldon req migrate`.
4. `seldon req trace` (0 edges until a test carries a marker).
5. `seldon docs generate requirements`, then `seldon docs generate rtm`; each commits its files.
6. `pyproject.toml` line 124 becomes
   `markers = ["slow: exhaustive eval-harness runs, excluded from the default gate", "verifies(*ids): the requirements this test verifies (AD-013-R5)"]`;
   then a test declares what it verifies with `@pytest.mark.verifies("VR-012")` and `seldon req trace` keeps the
   edge. Marked edges replace a requirement's imported ones.
7. `tests/test_view_requirements.py` and the `docs/evidence/hb134/rtm.md` export are yours to adjust: the
   `Validated by` column is gone, and the counts sentence becomes "113 satisfied, 27 open, 13 changed, 3 withdrawn"
   because five rows the table called satisfied or changed have no verifying test (below).

**From now on:** `seldon req update <id> --note "..." | --state <state> | --method inspection | --evidence <Result or
Issue id>` and `seldon req add <id> --statement "..."`, then `seldon docs generate requirements` and `rtm`.

**What the proof found in your files (about the files, not the graph):**
- 19 rows said satisfied/changed/met with no verifying test and now say so: VR-060, VR-094, VR-097, VR-098, VR-143;
  S3-6, I-1, T-2, T-4, G-1a, C6, E-D2, E-D3, E-D5, E-D6, O-D2, O-D3, O-D4, O-D7. A marker on a test, or for T-2,
  T-4, G-2, G-3 (now method inspection) an Issue or Result recording the inspection (`--evidence`), then
  `seldon req update <id> --state verified`, clears each.
- E-D2 to E-D6 and O-D4 name test functions with no file, so no edge can be formed; a marker on each test does it.
- Nothing else changes in what a reader sees but the moved words (in the Status/State cell) and test order.
