# SEL-060: recall is measured, and a session starts with what the record says about the files it will touch

**Status:** proposed
**Author:** the factory coordinator (FCT-7, a Desktop session), 2026-11-27 19:25 EST, on the operator's word of 19:03 EST: building the ability to learn from its own work "will only serve to improve everything else that much more".
**Repo:** seldon. L4: commit on the task branch; the dispatcher merges.
**After:** none
**What is known before this starts (nothing re-measured by Desktop):**
- Recall (RECALL-001, RECALL-002R) hands a session up to eight hits from the history of its repository and its neighbours at registration and launch. SEL-055's RESULT says: "Recall used: none. I opened none of the eight recall hits." CTAI-010's says no recall hits were given. Registration in factory and critical-thinking-ai prints `Recall: not configured (seldon.yaml has no recall: block; RECALL-001)`. The hits printed for today's factory-authored tasks were mostly months-old RESULTs that share words with the task and nothing else.
- factory FAC-41 measured that an answer found by code from the record cut a session's tokens to a fifth and a half on two tasks (29k against 167k; 29k against 61k) and was the only arm that got them right.
- Read RECALL-001's and RECALL-002R's RESULTs and RECALL-001's chart first.
**Governing:** AD-038 (the dispatcher's launch context), the recall design note and its R-records (find them; RECALL-001 names them), AD-036 (prior art). A change is an addendum to the recall note with prior art and a register record, `seldon prior-art verify` passing before code.
**Prior art:** RECALL-001's own evidence, held. From memory and UNVERIFIED unless confirmed and cited: retrieval evaluated by use, not by rank (click-through as implicit relevance, Joachims 2002); the cost of related distractors in a context (factory's checked claims on Cuconasu et al. 2024 are held at `factory/docs/evidence/fac16/claims.md`: read them, they bear on whether eight weak hits are worse than none).
**Spend:** est. 1.6M tokens.
**Network:** none
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes
**Parts:** A 0.3, B 0.45, C 0.25.
**Premises:**
- premise: recall is configured here | check: sh -c "grep -q '^recall:' seldon.yaml"

Glob and read every sibling `*SEL-059*ADDENDUM*.md`. Other repositories are read by path and never written.

## Part A: is recall used

By code, over every dispatched session's log in every registered repository since recall was turned on: which sessions were handed hits, which hits were opened (a read of the hit's path in the log), and whether the RESULT says they were used. One table: hits handed, opened, used, by repository and by hit kind (result, decision, issue). This is the baseline; say plainly what share of handed hits was ever opened.

Acceptance:
- `check: sh -c "git log --oneline main..HEAD -- docs | grep -q ."` passes.

## Part B: hits a session has reason to open

The decision the coordinator has made, to be corrected by Part A's numbers: hits are chosen by what the task will touch and what it cites, before shared words: earlier tasks and Issues that changed the same files or the same decision ids; review findings on those files; a blocked or re-filed task of the same kind in the last thirty days with its reason; then lexical hits only above a threshold Part A supports. Fewer hits when few are strong (none is allowed). Each hit says in one line why it was chosen. `seldon project` writes the `recall:` block for a repository that lacks it, so factory and critical-thinking-ai get it by their own return tasks. Tests.

Acceptance:
- `check: sh -c "git log --oneline main..HEAD -- tests | grep -q ."` passes.

## Part C: measured on replays, and returned

Replay registration for the last thirty dispatched tasks in seldon and in factory under the old and new selection; report how many hits each gives and, for the tasks whose logs exist, whether the files the session later read are among the new hits and were among the old. RESULT `## For the consumer` for factory, critical-thinking-ai, hazbrief-mcp and aacps-ai-policy; `seldon cc return` to each. The same count as Part A is to be re-run in a week; file that as a task with a date in its premise.

Acceptance:
- `check: sh -c "grep -q '^## For the consumer' cc_tasks/2026-11-27_SEL-059_recall_is_measured_and_a_session_starts_with_what_the_record_says_about_the_files_it_will_touch_RESULT.md"` passes.
