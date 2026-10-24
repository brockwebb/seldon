# AD-038 ADDENDUM 02: a task waits on a task in another project's graph, and a block stores its reason

**Date:** 2026-10-24. **Status:** Accepted. Implemented by SEL-008
(`cc_tasks/2026-10-24_SEL-008_cross_project_waits_on_and_a_stored_block_reason.md`, task `30a4b346`).
**Amends:** the ResearchTask state machine of AD-028 section 6 (as extended by AD-038-R2), which lives in
`seldon/domain/research.yaml` `state_machines.ResearchTask`; AD-029's `precedes` is unchanged and its readiness rule is
extended, not replaced. Three new rulings, numbered from the register.
**Code:** `seldon/core/cross_project.py` (new); `seldon/core/artifacts.py` (`plan_task_transition`,
`set_block_reason`); `seldon/core/precedence.py` (`precedence_view`, `short`); `seldon/core/redrive.py`
(`lift_satisfied_waits`); `seldon/core/dispatch.py` (`evaluate` c17, `first_refusal_reason`, `REFUSAL_REASONS`,
`parse_after`); `seldon/commands/dispatch.py` (`_cross_waits`, `_tasks`, `block_reason`, `_block`);
`seldon/commands/dispatch_worktree.py`; `seldon/commands/task.py` (`wait-on`, `unwait`, `update --reason`, `show`,
`list`); `seldon/commands/cc.py` (`read_after_waits`); `seldon/mcp_server.py` (`seldon_task_update` `reason`,
`seldon_task_wait_on`, `seldon_task_unwait`, `seldon_task_list`); `seldon/commands/session.py`, `seldon/commands/go.py`,
`seldon/core/handoff.py` (the briefing reads the other graphs); `seldon/commands/verify.py`
(`check_blocks_and_waits`).
**Tests:** `tests/test_sel008_cross_project_waits_and_block_reason.py` (38).

## 1. Evidence: hazbrief HB-20, 2026-10-24

hazbrief task HB-20 (`311388f9`, "open the concept and topic layer over the claims") ran on 2026-10-23 and stopped on
a Squiddy defect, filed as squiddy SQ-048 (fixed as SQ-048R, `e597085a`). On 2026-10-24 the hazbrief graph showed
HB-20 `proposed` with one edge, HB-19 precedes it; the dependency on SQ-048 was a paragraph in
`hazbrief-mcp/handoffs/2026-10-24_desktop_build_to_graph_rating.md`. Three gaps, each read from the code:

1. **No cross-project edge.** `precedes` is declared `ResearchTask -> ResearchTask` and `add_chain` resolves both ends
   in the project's own database, so a task in `seldon-squiddy` cannot be named from `seldon-hazbrief-mcp`.
2. **`blocked` was reachable only from `in_progress`** (`proposed: [accepted, rejected, superseded, withdrawn]`,
   `accepted: [in_progress, superseded, withdrawn]`). Marking HB-20 blocked from Desktop took
   `proposed -> accepted -> in_progress -> blocked`, and the middle step recorded `claimed_by: desktop`, a claim
   nobody made.
3. **A block had no stored reason.** `seldon_task_update`'s `note` is echoed and not stored, and `transition_task`
   took no reason for `blocked`. A reasonless block can be lifted only by someone who remembers why it was set.

## 2. Rulings

- **AD-038-R7. `blocked` is reachable from every open state, and every block stores its reason.**
  `proposed -> blocked` and `accepted -> blocked` join `in_progress -> blocked`, so a known dependency is recorded
  when it is known, with no claim. Every move into `blocked` requires a non-empty reason, stored on the task as
  `block_reason` and in the ledger in the same append as the state change; a block with no reason is refused before
  any write. The reason is cleared when the task leaves `blocked` (by `seldon task update`, a redrive, a close walk or
  the dispatcher's regate). Replacing the reason of a task already blocked is not a transition
  (`set_block_reason`: one `artifact_updated` line, `blocked -> blocked` stays outside the machine); it is the
  backfill path for tasks blocked before this ruling. The dispatcher's own blocks store
  `dispatcher: <outcome> (exit <code>; log <path>)`. Surfaces: `seldon task update <id> --state blocked --reason
  <text>`; MCP `seldon_task_update(..., reason=...)`; `seldon task list` prints `[blocked: <reason>]` on the task's
  line; `seldon task show` prints it.
- **AD-038-R8. A task may wait on a task in another project's graph; the edge lives in the waiting ledger only.**
  `seldon task wait-on <task> <project>:<task-prefix>` (MCP `seldon_task_wait_on`), or a `<project>:<ref>` entry in
  the task file's `**After:**` header at registration, records the wait as the task's `waits_on_external` list of
  `<project>:<artifact_id>`, in one event in the waiting project's ledger. The other graph is read and never
  written. `<project>` resolves, first match wins, through the waiting project's `seldon.yaml` `tasks.projects`,
  then `decisions.repositories`, then the side-by-side convention (`../<project>` beside the primary checkout); the
  other project's own `seldon.yaml` names its database. A target that resolves to no ResearchTask is refused before
  any write (SEL-007's rule). A wait is **satisfied only when its target is `completed` or `verified`**: unlike a
  `precedes` predecessor (AD-029 section 3), a superseded, withdrawn or rejected target does not satisfy it, because
  the waiter depends on work landing in another repository and a superseded target means that work moved elsewhere;
  such a wait is a dead end that `seldon verify` names. `seldon go`, `seldon task show`, `seldon task list` and the
  MCP task list print each wait with the target's state as of the call. A surface that does not read the other
  graph counts every cross-project wait as unsatisfied (`precedence_view`): it can under-report what is ready, never
  over-report it. `seldon task unwait` removes one.
- **AD-038-R9. The dispatcher reads both graphs, fails closed, and lifts a declared block by rule.**
  Criterion **c17**: a candidate with an unsatisfied cross-project wait is not eligible (`waits_on_unsatisfied`), and
  one whose other graph cannot be read is not eligible either (`waits_on_unreachable`), each unreadable target logged
  to the pass's stderr. c17 is absent from the criteria vector unless it fails, so every other task's vector, and the
  recorded serial transcript, are unchanged except for the dispatcher block's new reason line. The automatic redrive
  (AD-038-R2) gains one case: a **declared** block (one no `dispatcher:` claim set) on a task with cross-project waits
  is redriven to `accepted` once every wait is satisfied, recording `dispatch_redrive` with `stop_reason:
  waits_on_satisfied` answering the block's own state change. A session the dispatcher halted keeps R2's rule: a
  satisfied wait says nothing about why that session stopped. `seldon verify` gains "Blocks and waits": a wait whose
  target no longer resolves is a failure; a blocked task with no reason, a wait on a dead end, and a wait whose graph
  cannot be read now are warnings, each naming its command.

## 3. Negative control and toil measure (AD-038-R6)

- **Negative control.** `test_c17_holds_a_task_whose_cross_project_wait_is_unsatisfied` asserts c17 is absent for a
  task whose waits are all satisfied; `test_the_cross_waits_read_is_ready_only_on_terminal_success_and_unreachable_is_not_ready`
  asserts a completed target produces no entry; `test_a_dispatcher_halt_is_not_lifted_by_a_satisfied_wait` asserts the
  new redrive case leaves a dispatcher halt alone.
- **Toil measure.** `seldon qc chart`'s `redrives_by_operator` already counts every redrive whose actor is not the
  dispatcher. A block lifted by R9 is a dispatcher redrive; a block lifted by hand is an operator one. The target is
  that waits recorded under R8 are never lifted by hand.

## 4. What this does not change

- `precedes` (AD-029): its declaration, its DAG rule, its satisfied set and its advisory start warning.
- A dispatcher-halted task's redrive (AD-038-R2's own two reasons).
- The other project's ledger, graph and dispatcher: nothing in this addendum writes outside the waiting project.

## 5. Prior art

### External

- library receipt: query "task dependency on a task in another project or repository blocked by external task" | release library_graph_20261017_sq018_02_2026-10-17.json sha256:99984ba3da90146a73ab4e9d8ddf15687551cb2cc2659be90d16e525253ecfb5 | rows lesson:2026-02-22_arXiv_2503_08275#p1:16:2457-2472, lesson:2026-02-22_arXiv_2503_08275#p23:362:1775-1902, lesson:2026-02-22_arXiv_2503_08275#p27:455:3249-3635, lesson:2026-02-22_arXiv_2505_15155#p4:125:2605-2622, lesson:2026-02-22_arXiv_2302_01560#p2:24:122-163, lesson:2026-05-09_arXiv_2604_08224#p5:36:4378-5069, lesson:2026-05-09_arXiv_2604_08224#p16:100:231-686, lesson:2026-05-09_arXiv_2604_08224#p24:159:0-2301, lesson:2026-07-09_arXiv_2603_23420#p14:185:416-742, lesson:2026-02-22_arXiv_2503_01935#p28:510:2165-2412, lesson:2026-02-22_arXiv_2503_01935#p28:509:1751-2163, lesson:2026-02-22_arXiv_2503_01935#p28:508:1504-1749, lesson:2026-02-22_arXiv_2410_13232#p24:457:2152-2632, lesson:2026-02-22_arXiv_2507_21046#p36:414:293-315, lesson:2026-02-22_arXiv_2507_21046#p41:554:4772-5488, lesson:2026-02-22_arXiv_2507_21046#p52:713:200-797, lesson:2026-02-22_arXiv_2505_10468#p11:234:2007-2058, lesson:2026-02-22_arXiv_2505_10468#p18:342:1473-1577, lesson:2026-02-22_arXiv_2505_10468#p10:183:1530-1584, lesson:2026-02-22_arXiv_2404_18021#p6:43:252-307, lesson:2026-02-22_arXiv_2404_18021#p27:217:19-59, lesson:2026-02-22_arXiv_2404_18021#p27:223:726-766, lesson:2026-02-27_arXiv_2510_26493#p16:230:1795-2616, lesson:2026-02-27_arXiv_2510_26493#p14:206:28-785, lesson:2026-02-21_arXiv_2510_09517#p12:123:781-1016, lesson:2026-02-21_arXiv_2510_09517#p12:126:1077-1106, lesson:2026-02-21_arXiv_2510_09517#p12:142:2252-2292, lesson:2026-02-22_10_18653_v1_2024_acl_long_515#p16:285:406-484, lesson:2026-05-09_arXiv_2604_23338#p22:332:2470-2904, lesson:2026-05-09_arXiv_2604_23338#p34:456:434-877, lesson:2026-05-09_arXiv_2604_23338#p9:133:2154-2402, lesson:2026-02-22_arXiv_2505_24876#p23:538:712-1237, lesson:2026-02-22_arXiv_2501_06590#p30:467:1534-1833, lesson:2026-02-22_arXiv_2501_06590#p28:434:2178-2248, lesson:2026-02-22_arXiv_2501_06590#p32:498:114-749, lesson:2026-02-22_arXiv_2503_02077#p15:570:165-278, lesson:2026-02-22_arXiv_2512_07436#p5:207:4455-4560, lesson:2026-02-22_arXiv_2512_07436#p4:104:390-400, lesson:2026-02-22_arXiv_2512_07436#p5:204:4360-4383, lesson:2026-03-17_arXiv_2510_15863#p22:448:910-1067, lesson:2026-02-22_arXiv_2311_05657#p22:367:0-345

  The library's rows are agent-planning papers whose task graphs list prerequisite task ids within one plan
  (`dep: list` of task ids, arXiv ACL 2024 long 515 p. 16); none crosses a repository or a store. The engineering
  sources below are the prior art, and each decided one thing here:

- **Apache Airflow `ExternalTaskSensor`** (Airflow documentation, "Cross-DAG Dependencies"): a task in one DAG waits on
  a task in another, and the scheduler reads the other DAG's task state each poke; until it reads a success state the
  waiting task does not run. *Decided here:* R8's satisfied set is terminal success only, R9's c17 reads the other
  graph each pass, and an unreadable graph is "not yet", never "done".
- **Bazel external repositories** (`@repo//pkg:target` labels, resolved through the workspace's own repository
  declarations): a build names a target in another repository by a qualified label and never writes into it.
  *Decided here:* the `<project>:<id>` qualifier, resolved by the waiting project's configuration, and the
  read-only rule on the other graph.
- **GitHub cross-repository references and Jira "is blocked by" issue links**: the blocking link is stored on the
  waiting item and rendered with the target's live state. *Decided here:* the wait is a property of the waiting task
  in its own ledger, and every read surface prints the target's state as of the call.
- **Amazon SQS dead-letter-queue redrive** (already adopted by AD-038-R2): *decided here:* a satisfied wait answers a
  declared block by the same redrive, not by a new task.

### Internal

- internal receipt: query "SQ-048" | repo seldon@20f9c8e50aca22896b8f8421036d6b2b6ecc6ed7 | hits none
- internal receipt: query "SQ-048" | repo squiddy@a93a0d4426f14df0d4ebc70ffda25cf680a38773 | hits docs/design/2026-10-24_DN-050_sq022_slots_filled_gate_as_sampling_plan_hazbrief_filings_triaged.md:206, handoffs/2026-10-24_sq10_dn050_rulings_r219_r231_five_tasks_queued_sq038r_running.md:89, handoffs/2026-10-24_sq10_dn050_rulings_r219_r231_five_tasks_queued_sq038r_running.md:15, handoffs/2026-10-24_sq9_sq019_chain_landed_hazbrief_unblocked_machine_defects_filed_rev001.md:100, handoffs/2026-10-24_sq10_dn050_rulings_r219_r231_five_tasks_queued_sq038r_running.md:19, docs/design/2026-10-24_DN-050_sq022_slots_filled_gate_as_sampling_plan_hazbrief_filings_triaged.md:192
- internal receipt: query "cross-project dependency" | repo seldon@20f9c8e50aca22896b8f8421036d6b2b6ecc6ed7 | hits docs/decisions/REGISTER.md:9
- internal receipt: query "block reason" | repo ai-readiness-kg@e2f0e56f297be4c4ae0f4d12203495512674a120 | hits docs/design/2026-09-15_DN-006_standing_dispatcher_ADDENDUM_04.md:95, docs/design/2026-09-15_DN-006_standing_dispatcher_ADDENDUM_02.md:110, docs/design_decisions.md:335, docs/research/2026-10-02_commerce_guidance_two_pipelines.md:81, docs/design/2026-09-15_DN-006_standing_dispatcher_ADDENDUM_01.md:69, docs/design_decisions.md:820

squiddy's DN-050 section 4 triages hazbrief's filings to squiddy (SQ-039 to SQ-050) with a "depends on" column in a
markdown table: the cross-project dependency this addendum puts in the graph, kept today as prose. Seldon's register
hit for "cross-project dependency" is AD-011's paper references (unrelated): no Seldon ruling names a dependency between
projects' graphs. ai-readiness-kg DN-006 ADDENDUM_04 (line 95) made its dispatcher print "the reason with its
evidence" (`blocked_evidence`) for a refused candidate: the same principle as R7 applied to the dispatcher's
refusals, which R7 extends to the task's own state.
