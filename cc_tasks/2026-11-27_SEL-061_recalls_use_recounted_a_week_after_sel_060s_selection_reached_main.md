# SEL-061: recall's use re-counted a week after SEL-060's selection reached main

**Status:** proposed
**Author:** SEL-060's session (cc:4bf74fa6), 2026-11-27, as SEL-060 Part C asks: "The same count as Part A is to be re-run in a week; file that as a task with a date in its premise."
**Repo:** seldon. L4: commit on the task branch; the dispatcher merges.
**After:** cc_tasks/2026-11-27_SEL-060_recall_is_measured_and_a_session_starts_with_what_the_record_says_about_the_files_it_will_touch.md
**Governing:** AD-031 ADDENDUM 01 (AD-031-R4 to R7), `docs/design/AD-031_ADDENDUM_01_recall_is_chosen_by_what_the_task_cites_and_touches_and_its_use_is_counted_from_the_log.md`.
**Spend:** est. 0.3M tokens.
**Network:** none
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** no
**Touches:** docs/evidence/sel061/, seldon.yaml, cc_tasks/*SEL-061*
**Parts:** A 0.6, B 0.4.
**Premises:**
- premise: a week has passed since SEL-060 was filed (2026-12-05 or later) | check: sh -c "test $(date +%Y%m%d) -ge 20261205" | at: launch
- premise: seldon's recall selection is the touch selection | check: sh -c "grep -q 'mode: touch' seldon.yaml"

Read SEL-060's RESULT and `docs/evidence/sel060/part_a.md`, `replay.md` and `replay_sweep.md` first.

## Part A: the same count, on hits sessions were handed under the new selection

Run `seldon qc recall-audit --out docs/evidence/sel061/part_a_tables.md`. Report, beside SEL-060 Part A's baseline
(14.5% of 2,264 handed hits opened; 16.6% used), the open and use rates of hits registered after SEL-060's merge,
by repository and by stage (the `arms` table: `cited`, `files`, `dead_end`, `lexical`). The audit counts every
session since recall was turned on; separate the sessions registered after the merge by their `recall_listed`
records' `why` lines (a hit with a `why` was chosen by the new selection).

Acceptance:
- `check: sh -c "test -f docs/evidence/sel061/part_a_tables.md"` passes.

## Part B: the decisions SEL-060 left to this count

1. **The file-history stage.** If hits with `arms: [files]` were opened less often than SEL-060's uncited RESULT
   (2.2%), set `recall.selection.max_file_hits` to 0 with the number beside it; otherwise leave it and say why.
2. **The same-title predecessor.** SEL-060's replay (`replay.md` section 2) found factory's sessions opening the RESULT
   of the previous task with the same title, which the new selection does not hand. Measure it the same way on the
   week's sessions; build a stage for it only if Part A's counts support it, as an addendum to AD-031 with its
   prior art.
3. Record each change as an amend of the ruling it changes (`seldon decision amend`), or state that none changed.

Acceptance:
- `check: sh -c "grep -q '^Recall used:' cc_tasks/*SEL-061*_RESULT.md"` passes.
