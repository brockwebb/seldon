# TRIAGE-001: every open proposal in seldon's graph triaged: superseded ones close as history, dead ones withdraw, live ideas are marked future; the status line says what is moving

**Repo:** seldon. L4: commit, merge, push.
**Date:** 2026-10-15. **Authored by:** Desktop session, on the operator's direction of the same day.
**Governing:** AD-030 (task lifecycle; `supersede` and `withdraw` are terminal with reasons; `superseded_by` edges), AD-036 (a closure that cites a RESULT or ruling cites it by id).
**Framework layer served (DN-005 §5 rule 1):** none (machine bookkeeping).
**After:** none
**Model:** primary
**Spend:** est. 1M tokens.
**Parts:** A 0.65, B 0.35.
**Part map:** A is the triage; B is the status line in `seldon go` and `seldon status`.
**Network:** none beyond git push.
**Exclusive:** yes

## Step 0

If this task is `in_progress`, stop. Otherwise set it `in_progress` now.

## The population

Every ResearchTask in seldon's graph in `proposed` or `accepted` other than this one. Today: 12 or more, the oldest from 2026-05-11 (Molly-era intake rubrics), plus Arnold items (Suunto export, a workout detector false positive) that were filed here because the Desktop session was pointed at this project. Some are PA-001 and SEL-003 follow-ons; some are secrets hygiene; some are FUTURE ideas by their own first word.

## The decision rule (apply it; do not ask)

1. **Supersede** when the work is done or the question decided: a completed task's RESULT, an accepted ruling, code at HEAD, or a newer open task that restates it. `seldon task supersede <id> --superseded-by <artifact>`, evidence in the reason.
2. **Withdraw** when the premise is gone: the component is mothballed (Wintermute, Molly) or deleted, the file named is gone, the ruling reversed, or it duplicates a task closed under rule 1. Reason stated.
3. **Wrong repo** (Arnold, ai-readiness-kg, squiddy items filed here): file the task in its repo (`seldon task create --project <abs path>`, description copied, origin cited) and supersede the local one by the new id. No code changes in other repos.
4. **Future** when still valid and unscheduled: rewrite the description to begin `FUTURE (not scheduled; trigger: <condition>):`. No new tasks.
5. **Active**: live, unblocked, a current reason to run. Named in the RESULT with the reason.
6. **Undecidable**: to the RESULT as a question with two readings. Cap three.

## Part B: the status line

`seldon go` (both forms) and `seldon status` print first: `Moving: <n> in progress, <n> proposed with a source file; <n> future ideas; <n> closed this week.` The dispatcher's `candidate(s)` count and its log exclude `FUTURE` tasks. Tests with the fake graph: a FUTURE task is not a candidate and is not counted; the line's numbers match a hand count.

- check: after the pass, zero tasks in `proposed` without a source file or a `FUTURE` prefix, other than those the RESULT names active.
- check: every supersede has its edge; every withdraw its reason; counts quoted.
- check: full seldon suite, detached and polled; quote the counts. `seldon verify`.

## RESULT

Under 45 lines: the table (id, first words, decision, evidence); the active list; the questions; the status line as printed. `seldon cc complete`, merge, push.
