# SEL-057: seldon project new is right in a dispatched worktree, and commands write the prior-art block and the projections

**Repo:** seldon. L4: commit on the task branch; the dispatcher merges on green.
**Date:** 2026-11-27. **Authored by:** factory OODA-012 (the coordinator's check-in; DN-003, F-044), from aacps-ai-policy AP-03's RESULT.
**After:** 2026-11-27_SEL-056_squiddy_sq_151_the_coarse_tier_for_reference_documents_with_a_cited_pa
**What is known before this starts (from the filing; nothing re-measured by the coordinator).** Read in full first.
- `cc_tasks/2026-11-27_filing_from_aacps_ai_policy_seldon_project_new_in_a_dispatched_worktre.md` (b0966092), four items:
  1. In a dispatched worktree, `seldon project new .` writes the worktree's directory name as `decisions.repository` (`decisions_text` uses `Path(project_dir).resolve().name`; `project.slug` says the real name).
  2. The same run falsely refuses the environment step: `missing_siblings` looks beside the worktree, not beside `$SELDON_PRIMARY_CHECKOUT`, so every dispatched `project new` exits non-zero.
  3. No command writes a `prior_art:` block (also in SEL-052's RESULT "Not done"); factory's spec check reports it CRITICAL wherever it is missing, and AP-03 had to copy AD-036 ADDENDUM 03's lines by hand.
  4. No command declares `docs.projections`; factory's spec check reports `projections_declared` WARNING for every repository that lacks it, and nothing a project can run clears it.
- Related, already filed and not answered here unless it falls out of item 2: `cc_tasks/2026-11-25_filing_from_factory_a_declared_worktree_link_to_a_tracked_directory_is_skipped_without_a_word.md`.
**Governing:** AD-033-R13 (project new declares the decisions block), SEL-019/SEL-020, AD-036 and ADDENDUM 03 (prior art by reference), AD-013-R2 (projections declared in docs.projections), AD-036-R16/R17 (filings and returns). A fix that needs a decision none holds is an addendum with prior art and a register record.
**Prior art:** git's own worktree model (`git rev-parse --git-common-dir` names the main repository from inside a linked worktree; `--show-toplevel` names the worktree); idempotent scaffolding (`cargo init`, `git init` re-run safely).
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Model:** primary for the agent. Zero pipeline model calls.
**Spend:** est. 0.8M agent tokens. Basis: SEL-052 and SEL-053 answered factory filings of this size; four items, two of them new scaffolding steps.
**Parts:** A 0.4, B 0.6.
**Network:** none
**Exclusive:** yes
**Premises:**
- premise: the filing is on main | check: test -f cc_tasks/2026-11-27_filing_from_aacps_ai_policy_seldon_project_new_in_a_dispatched_worktre.md

Glob and read every sibling `*SEL-057*ADDENDUM*.md`. Other repositories are read by path and never written. If the session passes 0.65M with items left, finish the one in hand and list the rest first in the RESULT.

## Part A: project new in a dispatched worktree

A red test for each (a project created in a linked git worktree whose siblings sit beside the main checkout), then the fix: the register's repository is the project's name, not the worktree's; the sibling check looks beside the primary checkout. Re-running `project new` on a project already at spec changes nothing.

Acceptance:
- `check: sh -c "git log --oneline main..HEAD -- seldon tests | grep -q ."` passes.

## Part B: the prior-art block and the projections have a command

A red test, then a command (a `project new` step, or its own subcommand; choose and record which) that writes AD-036 ADDENDUM 03's prior-art reference block and the project's baseline, and one that declares the standard projections in `docs.projections` and writes their marked files without inventing requirements (requirements are the operator's needs). RESULT with `## For the consumer` naming aacps-ai-policy and saying which of its hand-written lines the commands now produce, and `seldon cc return` for the filing.

Acceptance:
- `check: sh -c "grep -q '^## For the consumer' cc_tasks/2026-11-27_SEL-057_seldon_project_new_is_right_in_a_dispatched_worktree_and_commands_write_the_prior_art_block_and_the_projections_RESULT.md"` passes.

## What NOT to do

- Do not write in aacps-ai-policy or any other repository; the return carries the consumer's steps.
- Do not author requirements or needs for any project.
- Do not lift a hold or change a repository's visibility.
