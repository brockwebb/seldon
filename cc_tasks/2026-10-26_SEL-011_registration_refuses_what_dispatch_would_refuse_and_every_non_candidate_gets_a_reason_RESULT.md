# RESULT: SEL-011, registration refuses what dispatch would refuse, and every non-candidate gets a reason line

**Task:** `bd5f26fb`,
`cc_tasks/2026-10-26_SEL-011_registration_refuses_what_dispatch_would_refuse_and_every_non_candidate_gets_a_reason.md`.
No addenda.
**Date:** 2026-10-26. **Branch:** `worktree-calm-prancing-koala`. Commit `a10e0f5` holds Parts A and B, the addendum and
the register record. The closing commit holds this RESULT and the supersession of `9965fbed`.
**Ruling:** AD-038-R12 is new, numbered under AD-038 as the task asked, in
`docs/design/AD-038_ADDENDUM_04_registration_runs_the_dispatchers_static_checks.md`. It is accepted with
`--decided-by cc:bd5f26fb` and is pending under `docs/decisions/register/pending/`; the merge step numbers it on main
(AD-033 ADDENDUM 01).
**Spend:** 181,324 tokens at Part B's boundary (`part_complete`), against an estimate of 0.4M and a stop at 0.5M.
There were no model calls and no network use (no push; the dispatcher merges).

Recall used: seldon:2026-10-15_TRIAGE-001_open_proposals_closed_as_history_RESULT

(TRIAGE-001's RESULT is where the advice Part C corrects was written. The other hits were background: the Parts
gate, `parts_baseline` and the premises-at-registration precedent were read from the code, not from their RESULTs.)

## Part A: one candidacy function, run at registration

- **`seldon.core.dispatch.static_checks(task_file, cfg, project_dir, config)`** is the one function that both
  `evaluate` and `seldon cc register` call (`registration_static_refusal` → `register_task_file`). It checks, in the
  dispatcher's order:

  | Check | Code |
  |---|---|
  | `dispatch.candidacy_headers` present | `no_header:<names>` |
  | Framework-layer value | `framework_layer_names_no_layer` |
  | Spend is `zero` or a token count | `spend_unreadable` (new) |
  | Network grammar | `network_undeclared` |
  | Exclusive/Touches (c10) | `concurrency_undeclared` |
  | Model lock | `model_not_in_lock` / `model_lock_unreadable` |
  | `**Parts:**` under `qc.parts_baseline` | `parts_undeclared` |
  | After grammar | `after_unresolved` |

  `candidacy()` is now a thin wrapper over it, so no second copy of the header logic remains.
- **Registration** refuses before anything is created and names every failure at once
  (`<code>: <grammar>; <code>: <grammar>. File: <path>`). SEL-010 had three wrong headers and learned of them one at
  a time. The old separate model and Parts calls in `register_task_file` are removed; the shared function does both.
  - A project with **no `dispatch:` block** is held only to what registration already checked: Model lock, Parts and
    After.
  - A `dispatch:` block that does not load refuses as `dispatch_config_unreadable`.
  - The block is loaded from a deep copy, so the rest of registration reads `config` exactly as it was written.
- **At the dispatcher,** Spend, Network and Exclusive/Touches stay criteria (c4, c5, c10). A candidate that fails one
  keeps its refusal line and its `dispatch_stuck` streak. Parts and After are new not-a-candidate reasons there.
  - c4 now carries a `message` when Spend does not parse.
  - `first_refusal_reason` returns `spend_unreadable` instead of `above_band`, and `spend_unreadable` is added to
    `REFUSAL_REASONS`.
- **Dispatch-only (live state):** c4's comparison with the band, c2, c6, c7, c11 to c18. Registration does not hold
  Spend against the band, because the band is a live reference that can move.
- **One fix found by the suite:** `load_candidacy_headers` refused its own output (a tuple). A cadence instance
  registers inside a pass with the block the pass already loaded, so loading it again refused every instance (four
  `test_cadence_pass` failures and one `test_dispatch_own_record` failure on the first run). The loader now accepts a
  tuple, and `test_the_dispatch_loader_accepts_its_own_output` covers it.
- **Vocabulary:** the After code is `after_unresolved`, the word registration has used since 2026-09-19. It is now
  defined once in `seldon/core/dispatch.py`, and `cc.AFTER_UNRESOLVED` imports it.
- **The fixed grammar texts** are `LAYER_GRAMMAR` and `SPEND_GRAMMAR`, beside `NETWORK_GRAMMAR`.

**Tests** (`tests/test_sel011_registration_refuses_what_dispatch_would_refuse.py`, 20):
- One parametrized fixture per static check (11 cases). Each runs `register_task_file` with `driver=None` (so nothing
  is created) and asserts that the refusal starts with the code and quotes the grammar. Each also asserts that
  `evaluate` refuses the same file on the same code.
- Plus: a clean file passes both; all failures are named at once; a project with no dispatcher; an unloadable block;
  no mutation of `config`; `spend_unreadable` at dispatch; loader idempotence.

**Live check (read-only):**
- `static_checks` over seldon's open tasks: only `e60b17fe` (SEL-003) has a file, and its reason is unchanged
  (`no_header:Spend,Framework layer served`). No open task's candidacy changed.
- `registration_static_refusal` on squiddy's SQ-088 and SQ-091 (read by path): both are now refused with
  `no_header:Spend,Network,Framework layer served` and the grammar. SQ-091R passes, and so does this task's own file.

## Part B: a reason line for every non-candidate

- **Pass output.** `_refusal_lines` (the text of the pass log, of the parallel pass, and of `seldon go`'s last-pass
  view) now prints one line per non-candidate, `  <id8> not_a_candidate: <reason>  <source file>`, with the grammar
  indented under it. "nothing eligible (N open, 0 candidate(s))" is now followed by N lines.
- **`seldon dispatch status`** prints the same grammar under its existing `NOT A CANDIDATE (<reason>)` line.
- **Log parsing is safe.** The toil measure's parser matches only `dirty_tree:` lines, so it does not count the new
  lines.
- **Tests:**
  - `test_every_non_candidate_gets_a_line_with_its_id_reason_and_file` and
    `test_a_future_task_and_a_task_with_no_file_still_get_a_line`.
  - `tests/test_dispatch_launch.py::test_a_pass_with_nothing_eligible_writes_no_event` now asserts the line in a real
    CLI pass and the grammar in `status`. It still asserts that nothing is written to the log.
- **`9965fbed` is resolved.** It is a ResearchTask with no file, not an Issue. It is superseded by `bd5f26fb` in the
  closing commit. Its other request, writing the Framework-layer grammar into DN-006, falls in ai-readiness-kg, which
  this task does not write. The grammar now exists as `LAYER_GRAMMAR` and is quoted by every refusal; DN-006 can cite
  it.

## Part C: the record

1. **A committed task file's headers can be repaired only by a new file.** The registrar (`static_checks` via
   `register_task_file`) and the dispatcher (`static_checks` via `evaluate`) read the base file only, never an
   addendum (AD-038-R11, restated in R12). An addendum that carries the missing header is ignored by both. The route
   is a new task file, `<id>R`, as SEL-010R2 did.
2. **Correction to TRIAGE-001.** Its RESULT
   (`cc_tasks/2026-10-15_TRIAGE-001_open_proposals_closed_as_history_RESULT.md`, line 29) says SEL-003 (`e60b17fe`)
   "needs those headers and `**Parts:**` added in an addendum before it can launch". That is wrong: an addendum cannot
   supply them. SEL-003 launches only if it is re-filed as a new task file (e.g. `SEL-003R`) carrying Spend, Network,
   Framework layer served and Parts. Its refusal today is still `no_header:Spend,Framework layer served`. TRIAGE-001's
   file is left as written; this is the correction of record.
3. **For SPEC-001: a `check:` line runs without a shell.** `seldon.core.stations.check_argv` splits the command with
   `shlex.split` and execs the argv, so there is no `/bin/sh`. A pipe, `&&`, `||`, `;`, `!`, a redirect or a glob is
   passed as a literal argument, and the check fails or tests the wrong thing. Five squiddy checks failed this way the
   weekend of 2026-10-24. Write such a check as `sh -c "<pipeline>"`, or as a single command. This task's own premises
   follow the rule (`grep -q ...`, one command each).

## Verification

- `python -m dotenv -f .env run -- python -m pytest tests/ -q -n 8` on `a10e0f5`: see the closing line below.
- On the first full run (before the loader fix and the After-code unification) there were 9 failures. Seven were
  fixed as above.
  - `test_pa002_release_resolve::test_rebuilding_the_served_release_reproduces_the_served_index` fails on main too,
    from squiddy library index drift (recorded 2026-10-24). It is not a regression.
  - `test_dispatch_stuck_and_journal::test_a_project_with_no_dispatch_block_is_left_alone` failed only because the
    tree had uncommitted changes under `seldon/` (the version banner printed "uncommitted"). It passes once
    committed.

**Second full run on `a10e0f5`: 2 failed, 2923 passed, 7 skipped in 1065.84s.**

- `test_pa002_release_resolve::test_rebuilding_the_served_release_reproduces_the_served_index` is the known drift
  failure above.
- `test_dispatch_parallel::test_two_disjoint_non_exclusive_tasks_run_concurrently_and_both_merge` failed on wall-clock
  overlap: task a ended at +13.7 s, before task b started at +15.6 s. It ran under 8-way xdist load. Re-run alone,
  `tests/test_dispatch_parallel.py` and `tests/test_dispatch_stuck_and_journal.py` passed (31 passed). Nothing in
  this change touches launch timing. It is a timing flake under load, not a regression.

## Not done / for the next session

- DN-006 (ai-readiness-kg) does not yet cite `LAYER_GRAMMAR` beside its Network grammar. That repository is not
  written from here.
- SEL-003 (`e60b17fe`) still needs a re-file to launch (Part C item 2). Filing it is a Desktop decision about whether
  Phase 1b is still wanted, not something this task can do mechanically.
