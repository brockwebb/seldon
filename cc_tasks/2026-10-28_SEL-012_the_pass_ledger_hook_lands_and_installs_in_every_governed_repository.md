# SEL-012: the pass-ledger hook lands on main and installs in every governed repository

**Status:** proposed
**Author:** Desktop session (seldon), 2026-10-28, from the squiddy SQ11 work order (`handoffs/2026-10-28_desktop_sq11_the_factory_runs_without_the_desktop_work_order.md`, item W5).
**Repo:** seldon (primary); squiddy, arnold, ai-readiness-kg, hazbrief-mcp (the install runs there and commits the hook files). L4: commit, merge, push in all five.
**After:** none
**Governing:** HOOK-001 (the commit gate is a tracked hook, `core.hooksPath` relative); AD-038-R15 (the hooks installer commits what it writes); squiddy DN-052 R-237 (a forked `kit/ledger/passes.jsonl` is refused on rebase), cited by path, not changed here.
**Model:** primary
**Spend:** est. 0.4M tokens. Basis: rebase and merge one existing branch (seven files, 425 lines, tests included), one install run per repository, one config fix. Zero model calls.
**Network:** none beyond git push.
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes (edits the hooks installer and runs it in five repositories)
**Parts:** A 0.40, B 0.40, C 0.20.
**Premises:**
- premise: the SQ-096 seldon branch exists and is unmerged | check: git rev-parse --verify feat/sq096-pass-ledger-fork
- premise: the installer exists | check: test -f seldon/commands/hooks.py
- premise: the squiddy SQ-096 RESULT exists to be read | check: sh -c "ls /Users/brock/GitHub/squiddy/cc_tasks/2026-10-27_SQ-096_*_RESULT.md"

Checks are single commands with no shell.

Read `/Users/brock/GitHub/squiddy/cc_tasks/2026-10-27_SQ-096_*_RESULT.md` in full before Part A.

## The condition

squiddy SQ-096 found that refusing a forked `kit/ledger/passes.jsonl` on rebase needs a third tracked hook (`prepare-commit-msg`, because git's sequencer runs no pre-commit), and that squiddy's primary checkout carries an absolute `core.hooksPath` against HOOK-001. The seldon side is one commit on `feat/sq096-pass-ledger-fork` (e2d0fd8: `seldon verify` and the gate refuse a forked ledger; `seldon/core/pass_ledger.py`; 183 lines of tests), unmerged. Until it lands and the install runs in each repository, the `pass_ledger:` block in seldon.yaml is read by nothing and DN-052 R-237 holds in `kitpass` only.

## What to build

**A. Land the branch.** Rebase `feat/sq096-pass-ledger-fork` onto main, resolve against DESK-004R's installer changes (`e60123f`), full suite green, merge. The third hook is tracked under `.githooks/` and `seldon hooks install` installs all three.

**B. Install everywhere.** Run `seldon hooks install` in seldon, squiddy, arnold, ai-readiness-kg and hazbrief-mcp; the installer commits what it writes (AD-038-R15), so each tree is clean after. Set squiddy's `core.hooksPath` to the relative `.githooks` and record the before and after values.

**C. Prove the refusal.** In a scratch clone of squiddy, fork the pass ledger on a rebase and show the hook refuses it with DN-052 R-237's text; record the transcript in the RESULT.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.5M.

## Deliverables

A, B, C; `cc_tasks/2026-10-28_SEL-012_the_pass_ledger_hook_lands_and_installs_in_every_governed_repository_RESULT.md`.
