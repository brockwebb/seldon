# Filing from factory: a premise that is false only because its date has not come holds its task forever

**Kind:** filing
**Filed by:** factory
**Date:** 2026-11-28
**Reporter:** factory OODA-029 (`factory/cc_tasks/2026-11-28_OODA-029_the_coordinators_check_in_found_1_changes_that_need_judgment.md`); seldon AD-038-R27 (`| at: launch`), AD-037-R6 (a) (a false premise blocks with an Issue), AD-038-R42 (project premises refuse with no Issue and resume by themselves).
**Spend:** est. 0.6M tokens. Basis: one station change, one test file, one ruling; no model calls of its own.
**Network:** none

## What the record shows

SEL-061 (`2098b773`) was filed by SEL-060's session, as SEL-060 Part C asked, with the premise
`a week has passed since SEL-060 was filed (2026-12-05 or later) | check: sh -c "test $(date +%Y%m%d) -ge 20261205" | at: launch`.
That is the intended way to wait (AD-038-R27). On 2026-11-28T01:52:39Z station (a) refused it `premise_false` and
filed Issue `0e13405d-9dcb-40ae-988a-7cefd1ebcfc2` ("Correct the premise (or the task) and resolve this Issue; the task
waits while it is open"). From then on c13 (`stations.premise_holds`) refuses it while that Issue is open, without
running the premise again. The dispatcher marked it stuck after 3 passes (2026-11-28T02:07:59Z).

So on 2026-12-05 the premise will be true and SEL-061 will still not launch: nothing resolves the Issue but a person
or a session, and the Issue's text says the premise is wrong, which it is not. A premise that waits for time (or for
anything else that becomes true by itself) is not a factual error.

## What seldon already has

AD-038-R42 (SEL-054): a project's `dispatch.premises` refuse as `project_premise_false` once per episode, with no
Issue, and launches resume on the first pass where the check holds. That is the behaviour a waiting task premise needs.
Prior art for the same split: Airflow's sensors in `mode="reschedule"` (a not-yet-true condition releases the slot and
is poked again next interval; it fails only on its timeout) and a DAG's `start_date`; `at(1)` for a date. Cited by
name; not fetched.

## Part A: a waiting premise re-runs each pass and clears itself

Seldon's to design; this is a suggestion, not an order. A task premise marked `| at: launch` (or a new field such as
`| wait`, if seldon prefers to keep R27's meaning) that is false refuses the launch as a wait, once per episode and with
no Issue, is re-evaluated every pass, and the task launches on the first pass where it holds, as R42's project premises
do. An optional ceiling (a date after which a still-false wait becomes `premise_false` with its Issue) keeps a wait that
will never hold from sitting unseen. Record it as a ruling that amends AD-037-R6 (a) or AD-038-R27, with a test: a task
whose date premise is false today is refused with no Issue, then launches on a pass where the check is true, with no
person or session in between.

## Part B: SEL-061 itself

Once Part A is on main, resolve Issue `0e13405d` with a note naming this filing, so c13 no longer holds SEL-061 and its
premise is evaluated afresh each pass. If Part A is not built by 2026-12-05, resolve the Issue by hand on or after that
date instead; resolving it earlier only makes the next pass file a new one.

What NOT to do: do not edit SEL-061's premise or its date; the wait is correct.
