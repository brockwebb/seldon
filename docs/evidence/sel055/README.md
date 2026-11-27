# SEL-055 Part B: what the selected gate would have run, and whether it catches a seeded break

**Task:** `cc_tasks/2026-11-27_SEL-055_the_gate_runs_what_a_change_can_break_and_no_queue_waits_an_hour_for_a_one_line_change.md`
and its ADDENDUM 01. **Rulings:** AD-034 ADDENDUM 13 (R38 to R40). **Date:** 2026-11-27. **Machine load:** 50 to 60
during the baseline, 130 to 160 during the seeds (another project's suite and a squiddy record pass ran beside them).
Every wall time below was taken under that load and is an upper figure, not a quiet one.

Tools (`tools/`, each with its method in its docstring): `merges.py` (the last 20 merged tasks from `dispatch_finished`),
`replay.py` (the planner over each merge's change, `prev_main..tip`, in a read-only shared clone under `/tmp`),
`classify.py` (why a plan went full), `timing.py` (per-file test seconds from a junit XML), `seeds.py` (the seeded breaks,
protocol in its docstring), `real_reads_scan2.py` (tests that join the real repository root to a sliced directory),
`survey_runs.py` (the `gate_run` records on file).

## 1. The baseline: seldon's full gate on this branch before the code (Part A's tree)

`python -m pytest tests/ -q -p no:cacheprovider -n 6 --junitxml`, in a shared clone of the branch at `6240d5d` with
the sibling repositories linked beside it: **2 failed, 3,646 passed, 2 skipped in 2,408 s** (40:08). The two failures
are the two that factory's filing of 2026-11-27 names:

- `tests/test_sel052_held_alarm.py::test_a_merge_blocked_task_rings_notify_with_its_reason_and_age`. Diagnosed and fixed
  on this branch. The module imports the `project` fixture from `test_dispatch_stuck_and_journal.py` without the
  `clean_test_db` mark that module applies. So the pass read a `t1` task that an earlier test on the same xdist worker
  had left `blocked` (`dispatcher: session_failed`), and rang for it first. It reproduces in one process: running
  `tests/test_dispatch_stuck_and_journal.py` first fails it. With the mark on the test, the same order passes 25 of 25.
- `tests/test_dispatch_parallel.py::test_union_merge_of_two_event_appends_is_valid`. The known intermittent
  `main_kept_moving` failure (Issue `88c9f4d8`). Not touched here (ADDENDUM 01 item 3).

The junit gives per-file test seconds: 13,371 test-seconds over 215 files.

## 2. The last 20 merged tasks, planned under today's declarations

The change a merge brought is `prev_main..tip`. `prev_main` is main's reflog entry before
`merge <branch>: Fast-forward`, and `tip` is the merge record's commit. The plan is `GP.plan` with this branch's
planner (no cadence: R38). The declaration is the repository's own as it stands today: seldon's from main, and
hazbrief's from its main (HB-218R's three slices). Estimated seconds are a plan's share of the junit's test-seconds
times the full gate's wall seconds (seldon 2,408 s, this task's baseline; hazbrief 2,677 s, the median of its 9
passing full `gate_run` records). The estimate checks against seldon's two measured scoped gates: 462 s estimated
against 430 s measured, and 735 s against 638 s.

### seldon (full gate 2,408 s)

| task | paths changed | plan | first reason | files | est. s | what the merge actually ran |
|---|---|---|---|---|---|---|
| SEL-033 | 28 | full | unmatched: seldon/cli.py | 182/182 | 2408 | before R26 |
| SEL-034 | 14 | full | unmatched: seldon/commands/dispatch.py | 184/184 | 2408 | before R26 |
| SEL-036 | 122 | full | unmatched: scripts/sel036/bridge.py | 187/187 | 2408 | before R26 |
| SEL-035 | 23 | full | unmatched: seldon/commands/docs.py | 188/188 | 2408 | before R26 |
| SEL-037 | 62 | full | unmatched: scripts/sel036/build_candidates.py | 190/190 | 2408 | before R26 |
| SEL-038 | 21 | full | unmatched: seldon/commands/dispatch.py | 191/191 | 2408 | before R26 |
| SEL-039 | 28 | full | unmatched: seldon.yaml | 192/192 | 2408 | before R26 |
| SEL-040 | 31 | full | unmatched: seldon/commands/cc.py | 194/194 | 2408 | before R26 |
| SEL-042 | 40 | full | unmatched: seldon/commands/cc.py | 197/197 | 2408 | before R26 |
| SEL-046 | 6 | full | unmatched: seldon/commands/dispatch_worktree.py | 198/198 | 2408 | Stop gate checks |
| SEL-045R | 63 | full | gate_config_changed: seldon.yaml | 200/200 | 2408 | Stop gate checks |
| SEL-043 | 53 | full | conftest: tests/conftest.py | 204/204 | 2408 | merge_gate full 4,854 s |
| SEL-044 | 27 | full | unmatched: seldon/commands/go.py | 205/205 | 2408 | merge_gate full 5,788 s |
| SEL-047 | 76 | scoped | scoped: documents, task_records | 26/205 | 462 | gate_run scoped 430 s |
| SEL-048 | 10 | scoped | scoped: documents, task_records | 29/205 | 735 | gate_run scoped 638 s |
| SEL-049 | 29 | full | gate_config_changed: seldon.yaml | 205/205 | 2408 | Stop gate checks |
| SEL-050 | 7 | full | gate_config_changed: seldon.yaml | 205/205 | 2408 | Stop gate checks |
| SEL-052 | 49 | full | unmatched: seldon.yaml | 214/214 | 2408 | Stop gate checks |
| SEL-053 | 4 | full | unmatched: seldon/core/project_new.py | 214/214 | 2408 | Stop gate checks |
| SEL-054 | 23 | full | unmatched: seldon/commands/dispatch.py | 216/216 | 2408 | gate_run full 2,449 s |

18 of 20 change package code, tests or `seldon.yaml`, and plan full. That is by design (R30): `tests/conftest.py`
imports `seldon.cli`. 2 of 20 are scoped, at 19% and 31% of the suite's seconds. Summed, the selected gate would have
cost 44,541 s against 48,160 s for the full gate on every merge (7.5% less). One case is not in the last 20: SEL-051's
RESULT-only branch, still parked. Under the cadence it paid two full merge gates (1,900 s and 3,094 s, both red on
main's own failures). Under R38 it plans `scoped: task_records`, 4 files with this branch's corrected slice.

### hazbrief-mcp (full gate 2,677 s)

| task | paths changed | plan | first reason | files | est. s | recorded gate |
|---|---|---|---|---|---|---|
| HB-213 | 129 | full | conftest: tests/conftest.py | 185/185 | 2677 | before R26 |
| HB-214 | 92 | full | unmatched: docs/ARCHITECTURE.md | 186/186 | 2677 | before R26 |
| HB-215 | 130 | full | unmatched: README.md | 189/189 | 2677 | before R26 |
| HB-216 | 26 | full | unmatched: README.md | 191/191 | 2677 | before R26 |
| HB-219 | 37 | full | unmatched: README.md | 193/193 | 2677 | merge_gate |
| HB-220 | 29 | full | full_path: pyproject.toml | 194/194 | 2677 | merge_gate |
| HB-222 | 75 | full | unmatched: docs/briefs/anfo-fire-i81/brief.html | 196/196 | 2677 | merge_gate |
| HB-225 | 9 | full | unmatched: CLAUDE.md | 196/196 | 2677 | merge_gate |
| HB-223 | 63 | full | conftest: tests/conftest.py | 197/197 | 2677 | merge_gate |
| HB-224 | 7 | full | unmatched: docs/evidence/hb224/README.md | 197/197 | 2677 | merge_gate |
| HB-226 | 27 | full | unmatched: docs/evidence/hb226/README.md | 197/197 | 2677 | merge_gate |
| HB-227 | 76 | full | unmatched: docs/FUTURE_WORK.md | 198/198 | 2677 | merge_gate |
| HB-217 | 6 | full | unmatched: CLAUDE.md | 199/199 | 2677 | merge_gate full 4,004 s |
| HB-228 | 20 | full | unmatched: CLAUDE.md | 200/200 | 2677 | merge_gate full 2,558 s |
| HB-229 | 1 | scoped | scoped: records | 39/200 | 267 | merge_gate full 2,333 s (before slices) |
| HB-218R | 12 | full | gate_config_changed: seldon.yaml | 201/201 | 2677 | merge_gate full 2,174 s |
| HB-230 | 64 | full | unmatched: docs/evidence/hb229/README.md | 201/201 | 2677 | merge_gate full 3,340 s |
| HB-231 | 9 | full | unmatched: graphs/hazbrief-corpus/.env.example | 202/202 | 2677 | Stop gate checks |
| HB-232 | 11 | full | conftest: tests/conftest.py | 203/203 | 2677 | Stop gate checks |
| HB-240 | 9 | full | unmatched: docs/evidence/hb240/filings/seldon.md | 203/203 | 2677 | Stop gate checks |

14 of 20 change code (`src/`, `tests/`, `scripts/`, `static/`, `packs/`, `fixtures/`, or a lock or `seldon.yaml`). One
(HB-229) is scoped. 5 go full only because of paths no slice names: HB-225 (`CLAUDE.md`, `docs/decisions`,
`docs/evidence`, `docs/submission`), and HB-224, HB-226, HB-230 and HB-240 (`docs/evidence/**` alone). More than 60 of
hazbrief's test files read `docs/evidence`, so a blanket slice for it would select a large share of the suite. Listing
each evidence directory's readers is hazbrief's work, as HB-230 found for `docs/`. HB-218R's own slices
were not on main for most of these tasks; the table is what they would have run had they been.

### Lane merges (ADDENDUM 01 item 1)

None. Neither repository declares `dispatch.coordination_lane`, and no merged finish in either last 20 carries `lane`
(factory is the only lane user, and its gate is 11 s). The lane path is covered by
`tests/test_sel055_scheduled_gate.py::test_a_lane_branch_with_no_evidence_merges_on_its_selected_gate_and_the_record_says_so`.

## 3. Seeded breaks: does the selected gate catch them?

The protocol is `tools/seeds.py`'s docstring, written before the first run. A seed is valid only if its named reader
test passes on the unseeded base and fails with the seed. A valid seed therefore breaks a test the full suite runs.
Each seed is then planned against the base. A scoped plan is run: red is CAUGHT, green is a MISS. A full plan is
CAUGHT, because the full suite holds the reader.

### seldon (base: this branch at `322a25f`)

| seed | kind | the break | reader | plan | selected | scoped gate | verdict |
|---|---|---|---|---|---|---|---|
| S1 | task file | one `check:` line removed from QC-001's task file | test_criteria_marked.py | scoped: task_records | 3 files | pass, 137 s, 98 tests | **MISS** |
| S2 | evidence data | SQ-010's `actual` changed in docs/evidence/qc002/cpi_first_reading.yaml | test_qc_chart.py | scoped: documents | 23 files | pass, 942 s, 555 tests | **MISS** |
| S3 | task file header | SEL-004's task file gains `**Exclusive:** yes` | test_dispatch_concurrency.py | scoped: task_records | 3 files | fail, 157 s | CAUGHT |
| S4 | convention doc | the result-units convention stops naming RESULT_NAME_PATTERN | test_result_grammar.py | scoped: documents | 23 files | fail, 896 s | CAUGHT |
| S5 | package code | the planner's `**/` stops matching zero directories | test_sel041_gate_plan.py | full: unmatched seldon/core/gate_plan.py | all | (full) | CAUGHT |

**Two misses: under task rule, this stops the rollout of seldon's slices as main declares them.** Both readers read a
real repository file under a sliced path, and neither is in its slice's list. The lists came from SEL-041's
`real_reads.py`, which did not find either. An independent scan (`tools/real_reads_scan2.py`: a test that joins the
real repository root to a sliced directory) finds exactly these two and no other. This branch adds them
(`seldon.yaml`: `task_records` gains `tests/test_criteria_marked.py`, `documents` gains `tests/test_qc_chart.py`).
S1 and S2 re-run under the corrected declaration:

| seed | declaration | plan | selected | scoped gate | verdict |
|---|---|---|---|---|---|
| S1 | corrected (`task_records` + test_criteria_marked.py) | scoped: task_records | 4 files, reader in | fail, 94 s | CAUGHT |
| S2 | corrected (`documents` + test_qc_chart.py) | scoped: documents | 24 files, reader in | fail, 425 s | CAUGHT |

With the corrected declaration, 5 of 5 seldon seeds are caught (`data/seeds_seldon_fixed.json`).

Until this branch merges, main's slices still miss these two breaks. A merge that changed only QC-001's task file
or the QC-002 evidence file could land red, and the next full gate would record the failure as an escape (R33).
Since R38 that full gate is the scheduled one.

### hazbrief-mcp (base: its main at `1a92c283`, a read-only shared clone)

| seed | kind | the break | reader | plan | selected | verdict |
|---|---|---|---|---|---|---|
| H1 | event store | every `seldon_events.jsonl` line naming the first unheld work's Issue removed | test_hb170_cited_sources_held.py | scoped: records | 39 files | CAUGHT (reader selected) |
| H2 | task addendum | HB-115 ADDENDUM 01 loses the review question the test quotes | test_hb115_serve_review.py | scoped: records | 39 files | CAUGHT (reader selected) |
| H3 | task file | HB-212's task file loses the quotations the benchmark record cites | test_hb212_status_words.py | scoped: records | 39 files | CAUGHT (reader selected) |
| H4 | declared script | scripts/gate_ledger.py's bound defaults to 90% confidence, not 95% | test_gate_ledger.py | scoped: gate_ledger | 8 files | CAUGHT (reader selected) |
| H5 | package code | src/hazbrief/geo.py adds a polygon's holes instead of subtracting them | test_geo.py | full: unmatched src/hazbrief/geo.py | all | CAUGHT (full) |

5 of 5 caught. The seeds go where HB-230's 36 seeds did not: the `records` slice, which RESULT-only and lane-like
branches change. HB-230 had already found that the plan missed nothing on its five scoped seeds.

### Deviations from the protocol

1. **hazbrief's tests ran on HB-230's scratch environment.** The clone has no `uv` environment, so the same pytest
   arguments ran on `/tmp/hb230/root/hazbrief-mcp/.venv/bin/python` (Python 3.11, the same lock), with the clone's
   `src` first on `PYTHONPATH`. hazbrief's own checkout and environment were read, never written.
2. **hazbrief's scoped gates were not run to their end** when the plan selected the seed's reader. One records-slice
   gate (39 files at `-n 3`) progressed about 1% a minute at load 150 and was stopped at 12%; it already showed
   failures. A selection that holds a reader which fails alone with the seed is red, so H1 to H4 are recorded
   CAUGHT by that argument, not by a finished run.
3. **Two hazbrief seeds were void and replaced.** "scripts/gate_ledger.py's first `return` returns None" and
   "geometry.py's ring left unclosed" each left its reader passing. They break no test, so they say nothing about
   selection. Their replacements are in the table. The void rows are kept in `data/seeds_hazbrief_main_first.json`,
   the replacements in `data/seeds_hazbrief_main45.json`.
4. **S2's first edit did not apply.** The ratio is computed, not stored, so the seed changes the stored `actual`.

## 4. The times the coordination lane's `merge_wait_s` waits on (ADDENDUM 01 item 2)

`dispatch.coordination_lane.merge_wait_s` defaults to 14,400 s, with "no measured basis" (SEL-054). The gates a lane
supervisor can wait behind, measured:

| gate | seconds | source |
|---|---|---|
| seldon full, `-n 6` | 2,408 (load 50 to 60); recorded full gates 1,900 to 5,788 | this task's baseline; `gate_run` records since 2026-11-21 |
| seldon scoped (documents, task_records) | 137 to 942 (load 130 to 160); recorded 430 and 638 | the seeds; SEL-047's and SEL-048's records |
| hazbrief full | median 2,677; recorded 2,155 to 4,069 | its 9 passing full `gate_run` records |
| hazbrief scoped (records, 39 files) | est. 267 (10% of the suite's seconds) | HB-229's plan, `timing.py` |
| factory full | 10.7 to 10.9 | SEL-041 Part A |

The longest gate on record is 5,788 s, about 40% of 14,400. Behind an exclusive build, a lane task waits for the
build's session and its merge gate, and the session is not measured here. Nothing here supports a new value, so the
default stands (AD-038-R40 owns it).
