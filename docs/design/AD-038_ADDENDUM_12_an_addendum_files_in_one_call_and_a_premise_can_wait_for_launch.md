# AD-038 ADDENDUM 12: an addendum files in one call, a premise can wait for launch, and a create reply names its repository

**Date:** 2026-11-17. **Status:** Accepted. Implemented by SEL-040 Parts C, D and E
(`cc_tasks/2026-11-16_SEL-040_a_session_lost_to_the_network_is_resumed_not_blocked_an_addendum_files_in_one_call_and_a_premise_can_wait_for_launch.md`),
from what hazbrief thread hz-18 reported on 2026-11-16. **Extends:** AD-038-R20 (`cc file` writes, commits and
registers in one call) to addenda; AD-038-R5 (registration runs the task's premises) with a deferral; AD-038-R24 (an
addendum never carries Spend, Network, Framework layer or Exclusive), unchanged and still enforced. Four new rulings,
AD-038-R26 to R29.
**Code:** `seldon/core/filing.py` (`file_addendum`, `addendum_base_stem`); `seldon/commands/cc.py` (`cc file`'s reply,
the registration retry's premise stage); `seldon/mcp_server.py` (`seldon_cc_file`, `_written_to`);
`seldon/core/stations.py` (`parse_premises`, `review_premises(stage=)`, `after_restating_premises`,
`premises_registration_refusal`).
**Tests:** `tests/test_sel040_addendum_files_and_launch_premises.py`.

## 1. Evidence

1. **An addendum could not be filed in one call.** hazbrief's Desktop called `seldon_cc_file` with
   `<stem>_ADDENDUM_NN_<slug>.md`; it was treated as a new task and refused for missing Spend and Network headers, which
   AD-038-R24 forbids an addendum to carry. Desktop wrote the file with the Filesystem tool and called
   `seldon_commit_governed` separately: the two-step sequence R20 exists to remove, with its window in which the
   untracked file fails c7 for the queue.
2. **A chained task could not state a premise about its predecessor.** hazbrief HB-192 was refused at registration
   (AD-038-R5) for a premise that HB-189's RESULT exists, while HB-189 was still running. That premise restates the
   After header, which already holds HB-192 until HB-189 completes; a premise about what HB-189 produces has no way to
   be checked when it can be true, which is at launch.
3. **Measured before D was built:** the serial pass re-runs every `check:` premise of the chosen task at launch
   (`dispatch._pass` -> `_premise_review` -> `dispatch_stations.premise_review` -> `stations.review_premises`), so the
   launch already evaluates every premise; only registration needed to defer. The parallel pass runs no premise
   review; neither project that dispatches runs it (`max_parallel: 1` in seldon and hazbrief-mcp).
4. **An Issue written into the wrong graph said nothing.** Issue `0c4232cb`, about hazbrief's night counts, was created
   by a Desktop call with no `project_dir`; `SELDON_DEFAULT_PROJECT` is seldon, so it was written into seldon's graph,
   and the reply ("Created Issue: 0c4232cb...") named no repository. hazbrief's recall lists it, correctly, as
   `seldon:issue-0c4232cb` (`docs/evidence/sel040/part_e_findings.md`).

## 2. Prior art

### External

- **The atomic publish under a lock** that AD-038-R20 adopted (Gray and Reuter, *Transaction Processing*, 1993, ch. 7;
  `flock(2)`): the addendum is published the same way, write and commit under the filing lock, so no pass observes it
  half-written. Cited by name; not fetched.
- **Deferred constraint checking** (SQL-92 `SET CONSTRAINTS ... DEFERRED`: a constraint declared `DEFERRABLE` is checked
  at commit, not at each statement). A premise marked `at: launch` is a deferrable constraint: declared at
  registration, checked at the point it is meant to hold. Cited by name; not fetched.

### Internal

- internal receipt: query "filing lock" | repo seldon@040dbc0743ac835c7a239a27e6cad2f75332ba5b | hits docs/decisions/register/00326_seldon-ad-038-r20_accept.yaml:1, docs/design/AD-034_ADDENDUM_08_the_merge_requires_the_declared_pass_record.md:1, docs/design/AD-038_ADDENDUM_08_hand_dispatch_one_call_filing_and_a_push_on_every_pass.md:3
- internal receipt: query "premise at registration" | repo seldon@040dbc0743ac835c7a239a27e6cad2f75332ba5b | hits handoffs/2026-10-28_desktop_sq11_the_factory_runs_without_the_desktop_work_order.md:32, docs/design/AD-036_ADDENDUM_07_self_citation_and_the_governing_header.md:17, docs/design/AD-038_ADDENDUM_04_registration_runs_the_dispatchers_static_checks.md:82
- internal receipt: query "redrive" | repo seldon@040dbc0743ac835c7a239a27e6cad2f75332ba5b | hits docs/design/AD-038_the_machine_reconciles_its_own_state.md:32, docs/design/AD-038_ADDENDUM_02_waits_on_across_graphs_and_a_stored_block_reason.md:76, docs/decisions/register/00287_seldon-ad-038-r2_accept.yaml:1

## 3. Rulings

- **AD-038-R26. `seldon cc file` and `seldon_cc_file` file an addendum in one call: a name that is an existing task's stem plus `_ADDENDUM_<NN>` is written and committed under the filing lock, and nothing new is registered.**
  The base task's file must exist and be registered (`addendum_without_task` otherwise, and nothing is written); an
  addendum that carries a header AD-038-R24 names is refused before it is written; an existing file is never
  overwritten; an addendum that cannot be committed is removed again. The reply names the base task and the commit.
- **AD-038-R27. A premise line may end `| at: launch`; registration records it unevaluated (`at_launch`), and station (a) evaluates it with the task's other premises before the session starts.**
  A false one refuses the launch with the premise named, as any false premise does (`premise_false` and its Issue). A
  premise with no `at:` is evaluated at registration and at launch, as before; an `at:` value other than `launch` is
  unreadable and refused.
- **AD-038-R28. A premise that only states that a task the After header names has finished is refused at registration (`premise_restates_after`), with a pointer to the After header, which already carries that meaning.**
  Such a premise names the predecessor (its file stem or its number) and its finishing (RESULT, complete, finished,
  merged, done). A premise about what the predecessor produced is kept, and may be marked `at: launch`.
- **AD-038-R29. A tool that creates an artifact names, in its reply, the repository it wrote into, and says so when `SELDON_DEFAULT_PROJECT` chose it because no `project_dir` was given.**
  `seldon_issue_create` and `seldon_task_create` carry the line `project: <name> (<path>)`.

## 4. What this does not change

An addendum still cannot change a candidacy header (AD-038-R11, R24); re-filing with an R suffix is still the way.
The R18 registration retry runs the premises at the registration stage too, so it never evaluates an `at: launch`
premise. Issue `0c4232cb` stays where it was written; moving it would write into another project's graph.
