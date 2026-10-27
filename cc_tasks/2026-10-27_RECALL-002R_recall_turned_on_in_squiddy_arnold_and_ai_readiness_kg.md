# RECALL-002R: RECALL-001's recall turned on in squiddy, arnold and ai-readiness-kg

**Status:** proposed
**Author:** Desktop session (seldon), 2026-10-27. Re-filing, with candidacy headers, of RECALL-002 (c9a3cb9b), which had no source file.
**Repo:** seldon (primary, where the task is tracked); squiddy, arnold and ai-readiness-kg (each gains a `recall:` block in its seldon.yaml). L4: commit, merge, push in all four.
**After:** 2909ce0f
**Governing:** RECALL-001 (registration recalls the repositories' own history); AD-031-R1 (every registering repository has a governed graph served with Squiddy's search).
**Model:** primary
**Spend:** est. 0.2M tokens. Basis: three config blocks copied by reference from seldon's, one read-only registration check per repository. Zero model calls.
**Network:** none beyond git push.
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes (writes in three other repositories)
**Parts:** A 0.70, B 0.30.
**Premises:**
- premise: seldon carries the recall block to copy | check: grep -q "^recall:" seldon.yaml
- premise: squiddy has a seldon.yaml | check: test -f /Users/brock/GitHub/squiddy/seldon.yaml
- premise: arnold has a seldon.yaml | check: test -f /Users/brock/GitHub/arnold/seldon.yaml
- premise: ai-readiness-kg has a seldon.yaml | check: test -f /Users/brock/GitHub/ai-readiness-kg/seldon.yaml

Checks are single commands with no shell.

## The condition

Found 2026-10-21: `seldon cc register` on squiddy's SQ-019 printed "Recall: not configured (seldon.yaml has no `recall:` block; RECALL-001)". squiddy's, arnold's and ai-readiness-kg's tasks launch with no history of their own RESULTs, Issues or dead ends. The served indexes were rebuilt under `sq028r-index/3` by squiddy SQ-087 (2026-10-24, parity pass in all three), so the arm is live; only the config is missing.

## What to build

**A.** Each repository's seldon.yaml gains the `recall:` block, values and reasons copied by reference to seldon's lines, not as new numbers; `served.graphs` names that repository's governed graph and `decisions.repositories` names siblings as seldon's does. Commit in each repository through its hooks.

**B.** Acceptance: `seldon cc register --dry-run` (or the nearest read-only path) on one existing task file in each repository prints a Recall list or `Recall: none`, never `not configured`. Record the three outputs in the RESULT. DISP-004R (its predecessor) makes the finish step push all four.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.3M.

## Deliverables

A and B; c9a3cb9b superseded in the closing commit; `cc_tasks/2026-10-27_RECALL-002R_recall_turned_on_in_squiddy_arnold_and_ai_readiness_kg_RESULT.md`.
