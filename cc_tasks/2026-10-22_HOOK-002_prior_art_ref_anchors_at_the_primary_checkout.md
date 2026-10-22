# HOOK-002: the commit hook resolves `prior_art.ref` at the primary checkout, so a worktree commit is judged instead of refused

**Repo:** seldon. L4: commit and push. Work on your worktree branch; the dispatcher merges on green (AD-034 ADDENDUM 01). Evidence read in `/Users/brock/GitHub/squiddy` (read only).
**Date:** 2026-10-22. **Authored by:** a Desktop session in squiddy (SQ9). **Re-issues:** the graph task "HOOK-001: the commit hook resolves `prior_art.ref` against the worktree" (no file). Renumbered: HOOK-001 is a completed task (2026-10-09, the commit gate is a hook); the open record reused its number (NUM-001).
**Governing:** AD-036 ADDENDUM 06 (`corpus_anchor`: a defining file inside a linked worktree anchors its corpus at the primary checkout), AD-036 ADDENDUM 03 (`prior_art.ref` by reference), AD-034-R8, HOOK-001's RESULT (the gate is a hook, not a protocol). Write the fix as AD-036 ADDENDUM 08. No new ruling: ADDENDUM 06's anchor rule is applied to the one path it missed.
**After:** none
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Model:** primary
**Spend:** est. 0.2M tokens. Basis: PA-002 (one resolver change, tests, re-verify) 0.25M est.; this is one resolution change at one call site, a test, and a grep across four repositories' RESULTs. The floor is 131K (AD-037-R11).
**Parts:** A 0.2, B 0.5, C 0.3.
**Network:** none beyond git push.
**Exclusive:** yes
**Premises:**
- premise: `corpus_anchor` exists and anchors corpus paths at the primary checkout | check: `grep -q 'def corpus_anchor' seldon/core/prior_art.py`
- premise: `settings` resolves the block reference by origin and does not pass `ref` through `corpus_anchor` | check: `sh -c 'grep -q "def settings" seldon/core/prior_art.py && ! grep -q "ref.*corpus_anchor\|corpus_anchor.*ref" seldon/core/prior_art.py'`
- premise: squiddy's prior_art block is a reference to seldon's | check: `grep -q 'ref: ../seldon/seldon.yaml#prior_art' /Users/brock/GitHub/squiddy/seldon.yaml`
- premise: dispatched squiddy sessions have been committing with --no-verify for this reason | check: `grep -q 'no-verify' /Users/brock/GitHub/squiddy/cc_tasks/2026-10-22_SQ-028R_one_text_of_record_per_document_claims_and_receipts_share_it_RESULT.md`

Glob and read every sibling `*HOOK-002*ADDENDUM*.md`.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.24M. If the fix needs more than `seldon/core/prior_art.py`, `seldon/core/hooks.py` and their tests, stop and report what else it reaches.

## The defect, measured

squiddy RESULTs for SQ-019 (2026-10-21), SQ-029R and SQ-028R (2026-10-22, sections 5): from a dispatched worktree `<primary>/.claude/worktrees/<name>`, the pre-commit hook resolves `prior_art.ref: ../seldon/seldon.yaml` relative to the worktree, reaching `.claude/worktrees/seldon`, which does not exist, and refuses the commit before judging any file. AD-036 ADDENDUM 06 fixed exactly this for corpus paths (`corpus_anchor`) and left the `ref` itself on the worktree-relative path. Every dispatched squiddy merge since then has gone in with `--no-verify`: the gate defeated, not satisfied. SQ-028R ran the gate by hand with the ref read from the primary (`docs/evidence/sq028r/commit_gate.py`): 51 files, 0 findings, so the bypassed commits were in fact clean, which is luck and not a control.

## Part A: receipts

`seldon prior-art search`, both arms, logged in the addendum. Named: git worktrees share one object store and one configuration with the primary (`git-worktree(1)`: "linked working trees"), so a repository-level reference belongs to the repository, not the working tree; `corpus_anchor` already states and applies this rule for corpus paths (ADDENDUM 06). One line each.

## Part B: one anchor for every repository-level path

Test first, failing on HEAD: `settings` resolved from inside a fixture worktree equals `settings` resolved from the primary checkout, field for field, including the resolved `ref` target. Then: the `ref` in a `prior_art` block resolves against `corpus_anchor(definer_dir)`, the same function the corpus uses, so there is one place that knows what "this repository" means. `hooks.pre_commit` and `hooks.commit_msg` take the same path; no second resolver. A `ref` that does not resolve at the primary either is still a refusal, with both paths in the message.

## Part C: the measure of how long it was open

`grep -ln -- '--no-verify'` over every `*_RESULT.md` in seldon, squiddy, arnold and ai-readiness-kg since AD-036 ADDENDUM 06's commit date. List each RESULT, its date, and whether its own text says the gate was run by hand first. Then run the fixed hook over the files each of those commits touched (`git show --name-only`) and report findings per commit: the count of what the bypass let through. Zero expected; measured, not assumed.

## Deliverables

Code and tests; `docs/design/AD-036_ADDENDUM_08_ref_anchors_at_the_primary.md`; `cc_tasks/2026-10-22_HOOK-002_prior_art_ref_anchors_at_the_primary_checkout_RESULT.md` with Part C's table and premises wrong.
