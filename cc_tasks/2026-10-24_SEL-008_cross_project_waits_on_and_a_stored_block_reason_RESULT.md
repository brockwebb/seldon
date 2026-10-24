# RESULT: SEL-008, a task can wait on a task in another project's graph, and a block stores its reason

**Date:** 2026-10-24
**Session:** interactive Claude Code session (operator-launched, not dispatched), branch `worktree-SEL-008` in
`.claude/worktrees/SEL-008`. Task `30a4b346`. SEL-009 ran beside it in its own worktree; the two merge together.
**Addenda:** `cc_tasks/*SEL-008*ADDENDUM*.md` globbed: no match.
**Model calls:** zero. **Network:** none beyond git push.

## Premises, as checked at start

Both held, exit 0, run from the primary checkout:

- `grep -q SQ-048 /Users/brock/GitHub/hazbrief-mcp/handoffs/2026-10-24_desktop_build_to_graph_rating.md`
- `grep -q 311388f9 /Users/brock/GitHub/hazbrief-mcp/seldon_events.jsonl`

The task's other two claims, confirmed by reading: `seldon/domain/research.yaml` had `blocked` only under
`in_progress`, and `transition_task` took no reason for it (no stored block reason anywhere in the domain config).
`seldon task show` did not print `precedes` edges at all, so "the single `precedes` edge on HB-20 is confirmed by
`seldon task show`" could not have been true; `show` now prints both directions (below).

## Governing decisions

- The ResearchTask state machine is defined in `seldon/domain/research.yaml` `state_machines.ResearchTask`, ruled by
  **AD-028 section 6** (terminal states) and **AD-038-R2** (the redrive edge `blocked -> accepted`). The header's
  AD-030 governs governed documents and the ledger's import path; it does not define the state machine.
- **AD-029** (`precedes`): its DAG rule and satisfied set are unchanged; its readiness computation is extended.
- **AD-034 / AD-038**: the criteria vector (c1 to c16) and the automatic redrive.
- New rulings, in `docs/design/AD-038_ADDENDUM_02_waits_on_across_graphs_and_a_stored_block_reason.md`:
  **AD-038-R7** (blocked from every open state, with a stored reason), **AD-038-R8** (cross-project `waits_on`),
  **AD-038-R9** (the dispatcher reads both, c17, the redrive of a declared block, the verify check).
  `seldon prior-art verify` on it: **PASS** (governed-ledger event `0fb2948762674cfda60a6bdb3bfea7fc`; one library,
  four internal receipts). Pending decision records (`--decided-by cc:30a4b346`), numbered on main at merge:
  `docs/decisions/register/pending/00001_0857fe689370562d_seldon-ad-038-r7_accept.yaml`,
  `00002_297bf77b1aec9720_seldon-ad-038-r8_accept.yaml`, `00003_238518aef9ecd912_seldon-ad-038-r9_accept.yaml`.

**Prior art, and what each source decided** (receipts in the note): Airflow's `ExternalTaskSensor` (a task waits on a
task in another DAG; only success releases it; an unreadable target is "not yet") decided the satisfied set and the
fail-closed rule; Bazel external repositories decided the qualified `<project>:<id>` label resolved by the waiting
side's configuration and the read-only rule on the other store; GitHub cross-repository references and Jira "is
blocked by" links decided that the edge lives on the waiting item and renders the target's live state; SQS
dead-letter redrive (AD-038-R2) decided that a satisfied wait answers a block by redrive. The library arm's rows are
in-plan task dependencies only. Internally, squiddy DN-050 section 4 keeps hazbrief-to-squiddy dependencies as a
markdown "depends on" column, and ai-readiness-kg DN-006 ADDENDUM_04 made its dispatcher print a refusal's reason with
its evidence. No Seldon ruling named a dependency between projects' graphs.

## Part A: `waits_on` across graphs

1. `seldon task wait-on <task> <project>:<task-prefix>` and `seldon task unwait` (CLI); `seldon_task_wait_on` and
   `seldon_task_unwait` (MCP). The wait is the task's `waits_on_external` property, a list of
   `<project>:<artifact_id>`, written by ONE `artifact_updated` event in the waiting project's ledger
   (`seldon/core/cross_project.py` `add_wait`). The other graph is opened from the other project's own `seldon.yaml`
   and only read. `<project>` resolves through `tasks.projects`, then `decisions.repositories`, then `../<project>`
   beside the PRIMARY checkout (`cross_project.project_root`; from a worktree the side-by-side siblings are beside
   the primary, the trap STD-001R hit). Every refusal (grammar, unknown project, unknown or ambiguous prefix, a
   target that is not a ResearchTask) is raised before the write. Re-recording is a no-op.
2. Recordable at registration: a `<project>:<ref>` entry in the task file's `**After:**` header
   (`seldon/core/dispatch.py` `parse_after`, `seldon/commands/cc.py` `read_after_waits`) is resolved in the other
   graph by the same stem-or-prefix rule as a local ref and lands in the created task's one `artifact_created` line.
   An unresolvable one refuses registration with `after_unresolved` and writes nothing.
3. Read surfaces, each with the target's state as of the call (`cross_project.overlay` / `read_targets`):
   - `seldon go` (and `seldon briefing`): a "Waits on other projects" block, `<task> [state] ⇢ squiddy:e597085a
     [completed] <name>`; a waiting task is out of "Next ready" until its targets succeed.
   - `seldon task show`: "Waits on, in other projects (n), as of <UTC>", plus the `precedes` edges in both
     directions and the block reason.
   - `seldon task list`, MCP `seldon_task_list`: the WAITS_ON column carries `project:id8`.
   - `seldon handoff`'s open-task list.
   A surface that does not read the other graph (`precedence_view` alone) counts every cross-project wait as
   unsatisfied, so nothing can be reported ready without the read.

## Part B: `blocked` from any open state, with a reason

3. `seldon/domain/research.yaml`: `proposed: [accepted, blocked, ...]`, `accepted: [in_progress, blocked, ...]`;
   `block_reason` and `waits_on_external` declared as `system` properties. `plan_task_transition`
   (`seldon/core/artifacts.py`): `blocked` requires `block_reason` (refused with "A block needs a reason (AD-038-R7)"
   before any write), a reason is refused on any other target, and leaving `blocked` clears a stored reason in the
   same append. `set_block_reason` replaces the reason of a task already blocked (one line, no transition: the
   backfill path). CLI `seldon task update <id> --state blocked --reason <text>`; MCP `seldon_task_update(...,
   reason=...)`. The dispatcher's own blocks (`seldon/commands/dispatch.py` `_block`, now with a required `reason`,
   and its four callers in `dispatch_worktree.py`) store `dispatcher: <outcome> (exit <code>; log <path>)`.
4. `seldon task list` prints `[blocked: <reason>]` on the task's line (`[blocked: no reason recorded]` for a legacy
   block); the MCP list prints `blocked: <reason>`.

## Part C: the dispatcher reads both

5. **c17** (`seldon/core/dispatch.py` `evaluate`, `cross_waits=`): a candidate with an unsatisfied cross-project wait
   fails c17 (`waits_on_unsatisfied`); one whose other graph cannot be read fails it as `waits_on_unreachable`, and
   each unreadable target is logged to the pass's stderr (`seldon/commands/dispatch.py` `_cross_waits`). The other
   graphs are read once per pass, in `_survey`, `_pass` and both worktree-mode surveys. c17 is absent unless it fails.
   **The automatic redrive** (`seldon/core/redrive.py` `lift_satisfied_waits`, called from `auto_redrive`): a
   declared block (no `dispatcher:` claim) on a task whose cross-project waits are all satisfied goes back to
   `accepted`, recording `dispatch_redrive` with `stop_reason: waits_on_satisfied` answering the block's own state
   change. A dispatcher-halted session is not lifted this way (AD-038-R2's two reasons stay its only automatic ones).
   Satisfied means `completed` or `verified`; the note says why `superseded`/`withdrawn` are not (they are for
   `precedes`).
6. `seldon verify` "Blocks and waits" (`seldon/commands/verify.py` `check_blocks_and_waits`): **fail** on a wait whose
   target no longer resolves; **warn** on a blocked task with no reason (naming the backfill command), on a wait on a
   superseded, withdrawn or rejected target, and on a wait whose graph cannot be read.

## Tests

`tests/test_sel008_cross_project_waits_and_block_reason.py`, 38 tests, written before the code.

- **Red.** Against the unchanged code the file does not import (`seldon.core.cross_project` and
  `check_blocks_and_waits` do not exist). To see each test fail for its own reason, the file was also run on a clean
  checkout of base `20f9c8e` with only those two imports stubbed: **37 failed, 1 passed**. The one that passed,
  `test_registration_refuses_an_unresolvable_cross_project_ref_and_writes_nothing`, passes on base because base
  refuses any `:` in an After ref as unparseable, which is also "nothing written".
- **Green.** 38 passed.
- **The other project** is a second ephemeral test database (`<test db>-xproj`) behind a second `seldon.yaml` found by
  the side-by-side convention; "unreachable" is a third `seldon.yaml` pointing at `bolt://127.0.0.1:1`.

Existing tests changed, each because the contract changed on purpose:

- `tests/test_friction001_redrive.py` `_halt`, `tests/test_task_lifecycle.py` (the transition matrix and the
  dead-end sweep): a move into `blocked` now carries a reason, as every caller must.
- `tests/test_sel007_atomic_multi_event.py`: `test_redrive_writes_its_three_lines_in_one_append` is now
  `test_redrive_writes_its_lines_in_one_append`; a redrive of a block with a reason writes four lines in one append
  (the claim clear, `dispatch_redrive`, the reason clear, the state change).
- `tests/fixtures/dispatch_serial_transcript.txt`, re-recorded with `SELDON_RECORD_SERIAL_TRANSCRIPT=1`; the diff is
  exactly one new `artifact_updated` line (`block_reason: "dispatcher: session_failed (exit 1; log
  logs/dispatch/t2.log)"`) before the dispatcher's block, and the record commit's line count going from 4 to 5.

Related suites run on the branch before the gate (`test_after_header`, `test_dispatch*` named below, `test_precedence*`,
`test_state`, `test_task*`, `test_sel007_atomic_multi_event`, `test_verify`, `test_go`, `test_session_commands`,
`test_handoff`, `test_mcp_tools`, `test_disp001_launch`, `test_disp002_breaker`, `test_disp003_regate`,
`test_dispatch_parallel`, `test_dispatch_serial_transcript`, `test_moving`, `test_prune001`, `test_cadence_pass`,
`test_friction001_redrive`): 468 passed and 8 failed, all 8 the fixtures above; after the changes, the 5 affected files
plus the new one: 125 passed.

**Full-suite gate:** _PLACEHOLDER: filled after the combined SEL-008 + SEL-009 branch's full run._

## Backfill: projects whose ledgers hold a block with no reason, or a wait kept in prose

Not run in another project (the task's rule). Each line is run from that repository's root, in a Claude Code or shell
session there, after this merge is on seldon main (seldon is installed editable, so every project gets the code):

**hazbrief-mcp, HB-20 (`311388f9`)**: blocked, `claimed_by: desktop`, no reason. Its dependency is squiddy SQ-048,
which squiddy fixed as **SQ-048R, task `e597085a`, already `completed`** (squiddy's graph, read 2026-10-24; SQ-048
itself is not a node there). hazbrief runs no dispatcher, so nothing will lift the block by rule. In order:

    1. seldon task wait-on 311388f9 squiddy:e597085a
    2. seldon task update 311388f9 --state blocked --reason "waited on squiddy SQ-048, fixed as SQ-048R (e597085a)"
    3. seldon dispatch redrive 311388f9

Step 3 clears the false `claimed_by: desktop` and returns HB-20 to `accepted`, since its wait is satisfied.

**seldon (this project), `1581c3ec`** (the SI-09 units-fallback removal): blocked by `cc` with its reason only in its
description. Backfilled here after the merge, with the reason its description states (see "After the merge").

**squiddy**, dispatcher blocks recorded before reasons existed:

    seldon task update 00203aed --state blocked --reason "dispatcher: merge_blocked (exit 0; log logs/dispatch/2026-10-22_SQ-021_extraction_pilot_for_the_ai_readiness_graph_then_its_first_new_document.log)"
    seldon task update f8433f8c --state blocked --reason "dispatcher: session_failed (exit 1; log logs/dispatch/2026-10-22_SQ-036_the_burn_survives_the_quota_window_and_an_operator_opens_a_graphs_budget_once.log)"

**ai-readiness-kg**, the same:

    seldon task update 98ed1dd1 --state blocked --reason "dispatcher: finished_not_ok (exit 0; log logs/dispatch/2026-10-15_executive_summary_v4_instrument_page_two.log)"
    seldon task update 9af5f624 --state blocked --reason "dispatcher: session_failed (exit 1; log logs/dispatch/2026-10-21_fcsm_concern_edges_and_sixteen_checks_one_pager.log)"

Each reason is the task's own last `dispatch_finished` record (`outcome`, `exit_code`, `log_path`), read from that
project's ledger with `seldon.core.redrive.answered_stop`. arnold holds no blocked task. Until they are run, each
project's `seldon verify` shows them as "Blocks and waits" warnings, each naming its line.

## After the merge

_Filled after the merge: the numbered decision records, seldon's own backfill, push._

## Not done, and why

- No `waits_on` was written into any other project's ledger (the task's rule); the recipes above are the operator's.
- `seldon task create` takes no `--waits-on`: a task can be waited from `proposed` with `seldon task wait-on`, and
  `cc register` reads the After header, which covers "recordable at registration".
- The advisory start warning (`precedence.transition_warnings`) still names local predecessors only; it has no
  project directory to read another graph from. c17 is the binding check.
