# Filing from aacps-ai-policy: seldon project new in a dispatched worktree names the register after the worktree and refuses its siblings, and no command writes prior_art or docs.projections

**Kind:** filing
**Filed by:** aacps-ai-policy
**Date:** 2026-11-27
**Reporter:** aacps-ai-policy AP-03 (`cc_tasks/2026-11-27_AP-03_the_project_and_its_graph_are_brought_to_the_factory_spec.md`, task 1cc5fcf6), which answered factory's spec-check filing of 2026-11-26. AP-03's rule was to fix each finding by the tool's own command and to file wherever no command exists. Filed here and not fixed there (factory F-002).

## What was experienced

### 1. In a dispatched worktree, `seldon project new .` writes the worktree's directory name as the register's repository

- Ran, in the dispatched worktree `/Users/brock/GitHub/aacps-ai-policy/.claude/worktrees/cozy-inventing-diffie`: `seldon project new . --graph aacps-policy-dm`.
- Came back: `decisions  changed  seldon.yaml + decisions.repository cozy-inventing-diffie`.
- The cause: `decisions_text` takes `Path(project_dir).resolve().name`. In a dispatched worktree that is the worktree's name, not the project's. `project.slug` in the same file says `aacps-ai-policy`.
- AP-03 corrected the value by hand to `aacps-ai-policy`, with a comment saying why. The correction is committed on the branch, after `project new`'s own commit.

### 2. The same run falsely refuses the environment step, because it looks for siblings beside the worktree

- Came back: `environment  refused  no sibling directory for ['squiddy', 'seldon'] beside .../.claude/worktrees/cozy-inventing-diffie`, exit 1.
- The cause: `missing_siblings` looks beside the worktree. The siblings are beside the primary checkout (`$SELDON_PRIMARY_CHECKOUT`). So every dispatched task that runs `project new` gets a false refusal and a non-zero exit.
- A related problem is already filed: `cc_tasks/2026-11-25_filing_from_factory_a_declared_worktree_link_to_a_tracked_directory_is_skipped_without_a_word.md`. Here it played out like this:
  - aacps declares `corpus/inbox` in `dispatch.worktree_links`, and that directory holds a tracked `.gitkeep`, so the link was not made in this worktree.
  - As a result, `squiddy manifest validate` on the worktree reported 18 held files absent.
  - Validated on the primary checkout instead, the manifest was CLEAN, with 33 of 33 held files hashed.

### 3. No command writes a `prior_art:` block

- SEL-052's RESULT already lists this under "Not done". AP-03 met it again: the factory spec check's CRITICAL `prior_art_block` finding has no command that answers it.
- So AP-03 wrote AD-036 ADDENDUM 03's three lines verbatim, plus the project's own baseline (`docs/design/AD-036_baseline.txt`, listing the three notes on main).

### 4. No command declares `docs.projections`

- The spec check's WARNING `projections_declared` has no command that answers it. `seldon docs generate requirements|rtm` only renders projections that are already declared, and `seldon req add` authors requirements.
- This project has 0 requirements (`seldon req list`). AP-03 did not hand-build a declaration or empty SE documents, so the WARNING stands.
- What would answer it: a `project new` step (or a `seldon docs init`) that declares the standard projections and writes their marked files. No command can supply the requirements themselves; they are the operator's needs.

## What aacps-ai-policy does not know

Whether `project new` is meant to run inside a dispatched worktree at all. The factory's AP-03 task said to use "the `seldon project` ... paths", and every AP-03 session is dispatched into a worktree.
