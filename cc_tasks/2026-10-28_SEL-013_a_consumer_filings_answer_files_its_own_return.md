# SEL-013: a task that answers a consumer filing files its own return task in the consumer's repository

**Status:** proposed
**Author:** Desktop session (seldon), 2026-10-28, from the squiddy SQ11 work order (`handoffs/2026-10-28_desktop_sq11_the_factory_runs_without_the_desktop_work_order.md`, item W3).
**Repo:** seldon (primary); squiddy and hazbrief-mcp are read by path for the patterns. L4: commit, merge, push in seldon.
**After:** a3357104
**Governing:** AD-036-R12 (a filing into another repository's `cc_tasks/` registers there and the registration commits it); AD-034-R6 (the dispatcher completes a worktree task); AD-038-R13 (`seldon task number`); AD-034-R12 (cross-repo push). Number the new ruling under AD-036.
**Model:** primary
**Spend:** est. 0.4M tokens. Basis: one header grammar (`Answers:`), one refusal in `cc complete`, a return-task writer that reuses the registrar and the allocator, fixtures. Zero model calls.
**Network:** none beyond git push.
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes (edits `seldon cc complete` and the dispatcher's finish step)
**Parts:** A 0.30, B 0.50, C 0.20.
**Premises:**
- premise: the hand-made return tasks exist to pattern on | check: sh -c "ls /Users/brock/GitHub/hazbrief-mcp/cc_tasks/*HB-63* /Users/brock/GitHub/hazbrief-mcp/cc_tasks/*HB-64*"
- premise: the allocator exists | check: grep -rq "def task_number\|task number" seldon/commands
- premise: cc complete is a command | check: grep -rq "def complete" seldon/commands/cc.py

Checks are single commands with no shell.

## The condition

Four consumer filings from hazbrief into squiddy were answered by squiddy tasks whose RESULTs ended with "For hazbrief: paste these steps". The return path ran through the operator's clipboard, then a Desktop wrote HB-63, HB-64 and ai-readiness-kg's `2026-10-28_repin_squiddy_to_b16ebb05_after_sq021s_rebase.md` by hand. The dispatcher already crosses repositories (SQ-096 wrote seldon; AD-034-R12 pushes there). The capability exists; the rule does not.

## What to build

**A. The header.** A task that answers a filing from another repository carries `**Answers:** <repo>:<task number or id>`. `cc register` validates the target exists in that repository's graph (AD-038-R12's static set gains this check).

**B. The refusal and the writer.** `seldon cc complete` on a task with `Answers:` refuses unless a return task exists, registered and committed, in the consumer's `cc_tasks/`: numbered by `seldon task number <PREFIX>` for that repository, `After:` the consumer's latest open task (or `none`), candidacy headers complete, body stating what landed, where, and what the consumer does with it. Provide `seldon cc return <task> --to <repo>` that writes the file from the RESULT's "for <consumer>" section and registers it there (AD-036-R12), so the session has one command; the dispatcher's finish step runs it when the session did not. The "for <consumer>: paste" section of a RESULT is retired; the convention doc says so.

**C. Record.** Note in the RESULT that ai-readiness-kg's dispatcher is off by its own DN-006 decision 10, so a return filed there still waits for a hand launch, which is that repository's choice. Fixture: a task answering a fixture filing, completed, with the return registered in the fixture consumer.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.5M.

## Deliverables

A, B, C with tests; the ruling under AD-036; `cc_tasks/2026-10-28_SEL-013_a_consumer_filings_answer_files_its_own_return_RESULT.md`.
