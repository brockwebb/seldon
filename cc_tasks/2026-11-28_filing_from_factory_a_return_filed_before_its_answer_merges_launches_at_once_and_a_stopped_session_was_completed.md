# Filing from factory: a return filed before its answer merges launches at once, and a session that pulled the andon was merged and completed

**Kind:** filing
**Filed by:** factory
**Status:** proposed
**Date:** 2026-11-28. Written by the factory coordinator, OODA-026 (factory `cc_tasks/2026-11-28_OODA-026_the_coordinators_check_in_found_7_changes_that_need_judgment.md`). This reports what the factory saw. How seldon answers is seldon's to decide.

## What the factory saw

1. **A return was written `**After:** none` while its answering task was still open.** SEL-060 (`4bf74fa6`) ran
   `seldon cc return` from its worktree before it merged. It filed four returns: aacps-ai-policy AP-08 (`55ab8037`),
   factory FAC-66 (`a7d2ec72`), critical-thinking-ai CTAI-021 (`f5cef002`) and hazbrief-mcp HB-244 (`0677488f`). Each
   return's `**After:**` names only the consumer's own latest open task (`seldon/core/returns.py` `OPEN_STATES`, AD-029).
   None of them names `seldon:4bf74fa6`, although each return's step 0 depends on that commit being on seldon main. At
   2026-11-28T01:35Z SEL-060 is still `in_progress`. AP-08 launched at 01:15Z and found `def recall_step` absent.
   HB-244 is `in_progress` now. The coordinator added `seldon task wait-on <task> seldon:4bf74fa6` by hand to FAC-66
   and CTAI-021.
2. **A session that stopped itself was merged and completed.** AP-08's session recorded `session_stop` at
   01:16:57Z with the reason "SEL-060 not merged ... Step 0 of AP-08 says stop. Redrive after the merge." It did not
   run `part-complete`. The dispatcher then recorded `stop_gate` pass (`checks_run: 0`), `dispatch_merge: merged`, and
   `in_progress -> completed` at 01:17:40Z (aacps-ai-policy `seldon_events.jsonl`, events for `55ab8037`). The task's
   only acceptance check was that its RESULT exists, and the RESULT says nothing was applied. The task is now
   `completed`, so `seldon dispatch redrive` refuses it. The factory re-filed it as AP-09, which waits on
   `seldon:4bf74fa6`.

## What the factory wants to know back

- For 1: whether `seldon cc return` can add a cross-project `After:` on the producer's own task while that task is
  not completed, so that no return launches before the change it applies is on the producer's main.
- For 2: whether a `session_stop` recorded by the session should keep its task from merging and completing, whatever
  the stop gate reads. The AP-08 session expected the andon to block the task, and its RESULT says so.

## References

aacps-ai-policy `cc_tasks/2026-11-28_AP-08_recall_is_measured_and_a_session_starts_with_what_the_record_says_abou_RESULT.md`
("Disposition", "Task-file defect"); seldon `seldon/core/returns.py` (`OPEN_STATES`, `render`); seldon
`cc_tasks/2026-11-27_SEL-060_recall_is_measured_and_a_session_starts_with_what_the_record_says_about_the_files_it_will_touch.md`.
