# SEL-018: a relative path in `dispatch:` resolves against the primary checkout, so `dispatch status` reads from a worktree

**Status:** proposed
**Author:** Desktop session (seldon), 2026-10-30, from hazbrief HB-73's RESULT (Part D) via the hazbrief Desktop thread.
**Repo:** seldon (primary). L4: commit, merge, push in seldon.
**After:** none
**Governing:** AD-034 (worktree dispatch); DN-006 §5 (the standing band is a reference, never a copy); SEL-017 Part B (the worktree's hook resolves) and RECALL-002R (sibling paths resolve from the primary) as the precedents of the same class. No new ruling expected; if one is needed, number it under AD-034.
**Model:** primary
**Spend:** est. 0.15M tokens. Basis: one resolver change, one fixture. Zero model calls.
**Network:** none beyond git push.
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes (edits seldon/core/dispatch.py)
**Parts:** A 0.70, B 0.30.
**Premises:**
- premise: standing_band_ref is joined to project_dir as given | check: grep -q "path = project_dir / rel" seldon/core/dispatch.py
- premise: a primary-checkout resolver already exists | check: grep -q "def primary_checkout" seldon/core/worktree.py

Checks are single commands with no shell.

## The condition

hazbrief HB-73, run headless in a worktree, could not read `seldon dispatch status`: `standing_band_ref: ../squiddy/squiddy/spend.yaml#job_token_cap_default` was joined to the worktree's path, where `../squiddy` does not exist, and the config loader raised "names ../squiddy/squiddy/spend.yaml, which does not exist". The reference is correct from the primary checkout, which is the only place the operator ever wrote it for. Same defect class as the worktree's `core.hooksPath` (SEL-017 B) and `recall.repositories` (RECALL-002R): a path meant relative to the repository resolved relative to wherever the command ran.

## What to build

**A.** Every relative path read from `dispatch:` (`standing_band_ref` first; audit the block for others, `gate_command` working directory included) is joined to `worktree.primary_checkout(project_dir)`, never to `project_dir` as given. An absolute path is left alone. The error text names both the reference and the checkout it was resolved from.

**B.** Fixture: a linked worktree of a fixture repository whose `standing_band_ref` points at `../sibling/spend.yaml`; `dispatch status` from inside the worktree reads the cap. Negative control: the same reference with the sibling absent still fails, naming the primary checkout.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.25M.

## Deliverables

A and B; `cc_tasks/2026-10-30_SEL-018_relative_dispatch_paths_resolve_against_the_primary_checkout_RESULT.md`.
