# ADDENDUM 01 to 2026-11-21_SEL-041_the_gate_runs_what_a_change_touched_and_the_whole_suite_only_at_declared_points: SEL-042 added a third gate call site and made a passing gate the condition of every merge

**Author:** OODA knowledge source on 3c39bd22 (AD-038-R16)

SEL-042 (task `3c39bd22`, merged; RESULT `cc_tasks/2026-11-21_SEL-042_..._RESULT.md`; rulings in
`docs/design/AD-034_ADDENDUM_11_a_stopped_session_is_never_merged_and_the_round_cannot_refuse_itself.md`) changed the
merge round this task edits. The premises still hold (seldon and hazbrief keep `gate_command`; the filing is on main).
What changes:

1. **Numbering.** AD-034-R25 to R28 are taken by ADDENDUM 11. This task's AD-034 addendum is ADDENDUM 12, and its
   rulings start at **AD-034-R29**. Check `docs/design/` and `docs/decisions/register/` for a newer number before
   writing.

2. **Three call sites, not two (Part C).** AD-034-R26 added a call site: when a branch has no recorded gate evidence,
   `_merge` (`seldon/commands/dispatch_worktree.py`, the `evidence is None` branch, `source: "merge_gate"`) runs
   `dispatch.gate_command` in full itself. The evidence sources, in order, are in `gate_evidence()`: the declared pass
   record, the round's re-gate, a kept branch's regate, and a Stop gate that passed **after running at least one
   check** (`checks_run > 0`). Part C routes this merge gate through the planner too. Otherwise every task with no
   `check:` lines still runs the full suite at merge, and the saving is lost.

3. **Part B must rule how a scoped gate meets R26.** R26 counts a Stop gate as evidence only when it ran at least one
   check. A scoped plan that selects nothing (the documents-only or slides-only change this task was filed for)
   runs zero tests. Without a ruling, that change either runs the full `gate_command` at merge or is blocked
   `ungated`. Decide it in the AD-034 addendum, citing R26 and the fail-safe-defaults basis it gives. Two things to
   state: whether a passing rule-5 gate-run record (tier, reason, selected of total, outcome) for the tip being merged
   is evidence; and whether a plan that selected nothing because every changed path matched a `tests: none` slice
   counts as evidence. That is a declared slice, which is different from a missing check. Add the matching
   `gate_evidence` source and its test to Part C's list. A scoped record that matches no slice still makes the gate
   full under rule 4. It is never evidence on its own.

4. **Part E: one record, not two.** Each merge record now carries `gate_evidence` (`source`: `gate_record`, `regate`,
   `kept_regate`, `stop_gate` or `merge_gate`, with the gate's result). Rule 5's gate-run record should be the record
   that `gate_evidence` points to, or should extend it. Do not build a separate stream beside it. Count escapes from the
   same records.

5. **Part A: read the new evidence.** Since SEL-042 merged, a hazbrief task whose Parts declare no `check:` runs its
   gate twice: once in the session and once as `merge_gate`. Tabulate `merge_gate` runs and their seconds separately
   from Stop-gate and re-gate runs. More data points for seldon's suite: SEL-042's two full runs were 25:40 (3,462
   passed) and 25:51 (3,472 passed), each at `-n 6`. **factory** declares a `dispatch` block with no `gate_command`,
   so under R26 its check-less tasks block `ungated` until the operator adds one, as SEL-042's "For the operator"
   item 1 asks. List it in A's table as "no gate command", not as zero seconds.

6. **Part F, the hazbrief return.** SEL-042's return (HB-217, `084beda4`) told hazbrief it can avoid the double gate
   by giving each Part a `check:` or by declaring `dispatch.gate_record`. Say how the scoped tier changes that advice
   now that item 3 is decided, so the two returns do not contradict each other.

Nothing else in Parts A to F changes. The ADDENDUM-level rule still holds: a project that declares no slices behaves
as today. Today now includes R26's merge gate.
