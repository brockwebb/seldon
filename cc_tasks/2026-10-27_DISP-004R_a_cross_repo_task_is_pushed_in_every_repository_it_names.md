# DISP-004R: a cross-repo task's commits are pushed in every repository its Repo line names

**Status:** proposed
**Author:** Desktop session (seldon), 2026-10-27. Re-filing, with candidacy headers, of DISP-004 (d091760b), which had no source file.
**Repo:** seldon (primary); squiddy and ai-readiness-kg (first run pushes their outstanding main). L4: commit, merge, push in all three.
**After:** f7a1d2f0
**Governing:** AD-034 (worktree dispatch, the finish step); AD-036-R12 (cross-repo filings). Number new rulings under AD-034.
**Model:** primary
**Spend:** est. 0.4M tokens. Basis: parse the Repo line at launch, a per-repository push in the finish step with a clean-tree refusal, one two-repository fixture. Zero model calls.
**Network:** none beyond git push.
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes (edits the dispatcher's launch and finish steps)
**Parts:** A 0.70, B 0.30.
**Premises:**
- premise: squiddy is a checkout | check: test -d /Users/brock/GitHub/squiddy/.git
- premise: ai-readiness-kg is a checkout | check: test -d /Users/brock/GitHub/ai-readiness-kg/.git

Checks are single commands with no shell.

## The condition

SQ-019 (squiddy, 2026-10-21) committed ai-readiness-kg 04c26099 and its RESULT says "committed and not pushed": the header said L4 push in both repositories, the launch prompt forbade pushing, and squiddy's dispatcher pushes only squiddy. Same for squiddy 805e333 from a seldon task on 2026-10-20. Root cause: the push step reads only its own repository.

## What to build

**A.** The `**Repo:**` line's repositories with L4 push are parsed at launch. The finish step pushes main in each listed repository whose HEAD moved during the session and whose tree is clean, recording `push:` per repository; a dirty tree there refuses that push and alarms. Fixture: a task naming two repositories, a session committing in both, both pushed.

**B.** First run: push ai-readiness-kg main and squiddy main where they are ahead of origin; record each result in the RESULT.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.5M.

## Deliverables

A and B; d091760b superseded in the closing commit; `cc_tasks/2026-10-27_DISP-004R_a_cross_repo_task_is_pushed_in_every_repository_it_names_RESULT.md`.
