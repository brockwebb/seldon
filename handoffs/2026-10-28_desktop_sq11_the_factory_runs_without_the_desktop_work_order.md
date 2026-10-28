# Handoff into seldon from the squiddy Desktop thread (SQ11), 2026-10-28: the factory runs without the Desktop

**From:** the squiddy Desktop session SQ11 (handoff `squiddy/handoffs/2026-10-27_sq11_dn052_r234_r237_four_tasks_chained_sq088_superseded_dn050_r_tasks_next.md` and this morning's OODA). **To:** the next seldon Desktop session. **Kind:** work order. Nothing here is registered in seldon's graph; the seldon session registers what it takes. Written under DESK-001 and committed with `seldon_commit_governed` so seldon's tree stays clean.

## What happened that produced this

1. Four chained squiddy tasks (SQ-052R → SQ-086R → SQ-089R → SQ-096) ran overnight with the Desktop thread closed and completed. The OODA between chained tasks (SEL-010R2) was never performed; the chain proceeded on grace. `seldon_ooda_pending` reported nothing in the morning. The chain worked; the OODA step as designed did not happen.
2. Three registrations in one morning were refused for mechanical causes a human then fixed by hand: a premise check with `&&` or `$(...)` not wrapped in `sh -c` (runner reports "unexpected operator" or "bad number"); a task number already taken in another repository (`number_taken`, because the Desktop globbed instead of calling `seldon task number`); a premise naming an evidence file the consumer filing claimed but that does not exist. Each is a one-line fix with a rule behind it.
3. Four consumer filings from hazbrief into squiddy were answered by squiddy tasks whose RESULTs ended with "For hazbrief: paste these steps". The return path ran through the operator's clipboard. The Desktop then wrote the return tasks by hand into `hazbrief-mcp/cc_tasks/` (HB-63, HB-64) and `ai-readiness-kg/cc_tasks/` (the re-pin) and registered them there. The dispatcher already crosses repositories when a task needs it (SQ-096 wrote seldon), so the rule is missing, not the capability.
4. SQ-096 (squiddy, DN-052 R-237) found that refusing a forked `kit/ledger/passes.jsonl` on rebase needs a third tracked hook (`prepare-commit-msg`; git's sequencer runs no pre-commit), installed by `seldon hooks install`, and that squiddy's primary checkout has an absolute `core.hooksPath` against HOOK-001. The seldon side of SQ-096 is on its branch; the `pass_ledger:` block in seldon.yaml is ignored until the hook lands and the install runs in each governed repository. Read `squiddy/cc_tasks/2026-10-27_SQ-096_*_RESULT.md` in full before touching it.

## Prior art (searched from squiddy; the query lines are in squiddy's prior-art log, not seldon's, so a seldon design note re-runs them for its own receipts)

- The operator's description ("a message board the OODA agent reads and writes, with access to memory beyond the thread") is the blackboard architecture: Hearsay-II (Erman, Hayes-Roth, Lesser, Reddy 1980, ACM Computing Surveys 12(2)) and Hayes-Roth, "A blackboard architecture for control" (Artificial Intelligence 26, 1985). Knowledge sources fire on the board's state, write back, and a control component chooses the next one; none holds a conversation. Linda tuple spaces (Gelernter 1985) are the coordination form. Seldon's graph plus task files already is the board; the missing piece is a knowledge source that fires on `task_completed` without a human surface.
- "Nearest nodes traversed for relevant context" is spreading activation (Collins and Loftus 1975). Seldon's Recall at registration is already a thin instance; the OODA session needs the same call.
- DeerFlow 2.0 (ByteDance, March 2026, LangGraph): a lead agent decomposes one long task into sub-agents with isolated contexts and termination conditions, parallel, joined by the lead. One goal per run, no governance between runs. The overlap is context isolation and state outside any context window; the difference is that seldon runs many short governed tasks with design judgment between them. Not a template; a point of comparison.
- Internal: SEL-010R2 (the dispatcher waits for the Desktop OODA between chained tasks), SEL-011 (registration refuses what dispatch would refuse, with a reason line), AD-038-R5 (premises checked at registration), AD-038-R13 (`seldon task number`), DESK-001/002.

## The work, in the order it pays

### W1. The OODA is a knowledge source, not a Desktop step

A headless CC session the dispatcher launches on `task_completed` for a task with an open successor. It runs `seldon go --brief`, reads the RESULT and the successor file, runs the successor's premise checks against HEAD, pulls Recall for the predecessor and the governing note, and ends in exactly one of three records:
- `ooda_ok`: nothing in the RESULT changes the successor; chain proceeds.
- `ooda_amended`: the successor gets an ADDENDUM (a path moved, a premise the predecessor made true or false, a number, a check that needs `sh -c`); the addendum is committed through the hooks; chain proceeds.
- `ooda_blocked`: the RESULT raises a question no ruling answers (a part the governing note did not decide, a finding that wants a new rule, a value call). The chain halts and the record names the question and the note that would answer it. This is the only record a Desktop session reads.

Grace expiry stays as the fallback when the OODA session itself fails, and the record says so (`ooda_expired`), so a chain that ran on grace is distinguishable from one that was checked. The criterion for done: last night's chain re-run with the OODA session would have produced four `ooda_ok` or `ooda_amended` records and no human reading.

### W2. The mechanical refusal is retried under a rule, not reported

Registration refusals with a mechanical cause (`number_taken`; a premise check that fails with "unexpected operator" or "bad number"; a premise naming a path that does not exist in a repository the filing names) are retried once by the registering session under a stated rule (next number from `seldon task number`; wrap in `sh -c`; mark the premise `stale_evidence` and register with the check narrowed to what exists) and the retry is logged on the task. Only a second refusal reaches a human. This is the same knowledge source as W1 firing at registration instead of completion; build it as one thing.

### W3. A consumer filing's answer files its own return

Rule: a task that answers a consumer filing (one whose header names a filing from another repository) is not complete until it has written and registered the return task in the consumer's `cc_tasks/`, through `seldon task number` for that repository's prefix, with `After:` the consumer's latest task, and committed it there. `seldon cc complete` refuses otherwise. The RESULT's "for <consumer>: paste" section is retired. HB-63, HB-64 and the ai-readiness-kg re-pin (`cc_tasks/2026-10-28_repin_squiddy_to_b16ebb05_after_sq021s_rebase.md`) are the hand-made instances to pattern on. Note ai-readiness-kg's dispatcher is off by its own DN-006 decision 10; a return task filed there still waits for a hand launch, which is that repository's choice, not seldon's.

### W4. Decide whether the OODA is required or advisory

SEL-010R2 made it a wait; last night it was skipped by grace and nothing was worse for it. Once W1 exists, the choice is between "required, a chain waits for the session" and "advisory, a chain proceeds unless `ooda_blocked`". Rule it, do not leave it to the grace timer. The squiddy Desktop's view, for what it is worth: advisory, because W1's blocked record is the only case that needs a wait and it declares itself.

### W5. The SQ-096 hook (already in flight)

Land the seldon side of squiddy SQ-096: the third tracked hook, `seldon hooks install` picking it up, the `pass_ledger:` block read. Then run the install in each governed repository and fix squiddy's `core.hooksPath` to relative. Until then DN-052 R-237's refusal exists in `kitpass` but not in the hook.

## Not in this handoff

No seldon task is registered by this file. No AD is proposed; W1 to W4 want one design note in seldon (prior-art receipts re-run there), and the seldon Desktop session writes it. squiddy's own queue (SQ-097, SQ-098 and the DN-050 chain it files) is unaffected and running.
