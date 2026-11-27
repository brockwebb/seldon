# SEL-054: four things the factory needs from the dispatcher are built

**Status:** proposed
**Author:** the factory coordinator (FCT-7, a Desktop session), 2026-11-27 05:50 EST. First of today's two seldon tasks.
**Repo:** seldon. L4: commit on the task branch; the dispatcher merges.
**After:** none
**What is known before this starts (from the filings; nothing re-measured by Desktop).** Read each in full first, and factory's RESULTs for FAC-29, FAC-30, FAC-31 and FAC-35 and its design notes DN-003, DN-004 and DN-005. The filings report; what changes is decided here.
- `cc_tasks/2026-11-27_filing_from_factory_a_coordinator_task_launches_beside_an_exclusive_build_task.md`: the factory's check-in task (OODA) cannot launch while an exclusive build task runs in the same repository; on 2026-11-26 a blocked merge in another repository waited ninety minutes behind one.
- `cc_tasks/2026-11-26_filing_from_factory_a_project_needs_a_premise_the_dispatcher_evaluates_for_every_task_so_a_spent_grant_stops_new_launches.md`: a spent grant should stop new launches project-wide; today only a task that carries the premise is refused.
- `cc_tasks/2026-11-27_filing_from_factory_the_dispatcher_mints_one_hive_identity_per_session_at_launch.md`.
- `cc_tasks/2026-11-27_filing_from_factory_every_limit_the_dispatcher_sets_is_tried_by_a_planted_control.md`: a deny rule in the wrong path syntax matched nothing and said nothing.
**Governing:** AD-038 (the dispatcher) and its R-records on exclusivity, stations and premises; AD-036-R16 and R17; AD-034. Each change that needs a decision none of these holds is an addendum to its governing note with prior art and a register record, `seldon prior-art verify` passing before code.
**Prior art:** from memory and UNVERIFIED unless confirmed and cited: readers-writer locking (a task that writes only outside the working tree's code does not need the writer's lock); admission control at a queue's head; negative testing of access controls (a control is tested by a request it must refuse).
**Spend:** est. 1.7M tokens. Basis: SEL-052 (five filings and two observations) was estimated 1.4M; these four touch the launch path.
**Network:** none
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes
**Parts:** A 0.5, B 0.5.
**Premises:**
- premise: the launch-beside filing is on main | check: test -f cc_tasks/2026-11-27_filing_from_factory_a_coordinator_task_launches_beside_an_exclusive_build_task.md
- premise: the project-premise filing is on main | check: test -f cc_tasks/2026-11-26_filing_from_factory_a_project_needs_a_premise_the_dispatcher_evaluates_for_every_task_so_a_spent_grant_stops_new_launches.md

Glob and read every sibling `*SEL-054*ADDENDUM*.md`. Other repositories are read by path and never written. If the session passes 1.4M with items left, finish the one in hand and list the rest first in the RESULT.

## Part A: the launch path (a coordinator task beside a build; a project-wide premise)

A red test for each, then the change. A task kind that declares it writes nothing a build task can touch may launch beside an exclusive task, under its own band and meter; state exactly what it may write and refuse the rest at merge. A project may declare premises in `seldon.yaml` that the dispatcher evaluates for every candidate at launch, each refusal naming the premise.

Acceptance:
- `check: sh -c "git log --oneline main..HEAD -- tests | grep -q ."` passes.

## Part B: identity and tried limits; the returns

The dispatcher gives each session one identity at launch that a board can verify (the factory's Hive reads it; the mint is seldon's, the board is not). Every limit the dispatcher sets for a session (deny rules, network line, spend ceiling) is tried once by a planted request at launch or in the gate, and a limit that does not refuse its plant fails loudly. RESULT with `## For the consumer` per filing; `seldon cc return` for each filing answered.

Acceptance:
- `check: sh -c "grep -q '^## For the consumer' cc_tasks/2026-11-27_SEL-054_four_things_the_factory_needs_from_the_dispatcher_are_built_RESULT.md"` passes.
