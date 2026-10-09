# SEL-005: run the standing dispatcher for seldon and squiddy, so registered tasks launch without a pasted line

**Repo:** seldon (primary), with `/Users/brock/GitHub/squiddy` by absolute path. L4: commit, merge and push in both.
**Date:** 2026-10-09. **Authored by:** a Desktop session in squiddy.
**Governing:**
- `/Users/brock/GitHub/seldon/docs/design/2026-09-15_standing_dispatcher.md`, its section on what a second project must do;
- ai-readiness-kg `docs/design/2026-09-15_DN-006_standing_dispatcher.md`;
- `/Users/brock/GitHub/seldon/docs/design/AD-034_worktree_per_task_dispatch.md`;
- AD-036 section 6.2.

Glob and read every sibling `*SEL-005*ADDENDUM*.md` first.
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Model:** primary
**Spend:** est. 0.8M tokens for this session. Zero harness model calls. The dry-run passes launch nothing.
**Network:** none beyond git push.

## Step 0
- Stop if this task is `in_progress`.
- Run PA-001 first. Do not start this task until PA-001's RESULT is committed: a dispatcher must not launch tasks past a gate that is still being built.

## The condition

- The only standing dispatcher on this machine is `com.brock.airkg-dispatch`, for ai-readiness-kg.
- seldon and squiddy have no `dispatch:` block, so every task there needs a pasted line.
- Desktop said twice on 2026-10-09 that the dispatcher might launch MODEL-001 and MODEL-002. It could not.

## Work

1. Add a `dispatch:` block to `/Users/brock/GitHub/seldon/seldon.yaml` and `/Users/brock/GitHub/squiddy/seldon.yaml`.
   - Fill every required key per the standing dispatcher note, copying ai-readiness-kg's values and their reason comments where they apply.
   - `standing_band_ref` points at squiddy's machine-wide spend configuration (DN-042 R-176), never a copied number.
   - `max_parallel: 1`.
   - `enabled: true` only after step 3 passes.
2. Create the launchd jobs `com.brock.seldon-dispatch` and `com.brock.squiddy-dispatch`, each with its wrapper script, modelled on `ai-readiness-kg/scripts/jobs/`.
   - Track each plist in its repo and install it by symlink.
   - Set `RunAtLoad` false and `AbandonProcessGroup` true (AD-034 premise 5).
   - The launch uses the lock's `primary` model and env block (AD-035-R3).
3. Before enabling, run `seldon dispatch status` and `seldon dispatch once --dry-run` in both repos. Record which open tasks would launch. Any task that would launch which was never meant to run headless is a finding: list it and set its state, do not launch it.
4. Enable, load both jobs, and confirm one live pass of each writes its log and launches nothing unexpected.
5. Add the dispatcher's existence to the session-start output (`seldon go`). Each project shows `dispatch: on|off`, so a Desktop session knows from state, not memory, whether a pasted line is needed. A test covers both values.

## Report

Write the RESULT, under 30 lines, to `/Users/brock/GitHub/seldon/cc_tasks/2026-10-09_SEL-005_standing_dispatcher_for_seldon_and_squiddy_RESULT.md`. It covers:
- the config blocks;
- the plists;
- the dry-run candidate lists;
- the first live pass's log lines;
- the `seldon go` change;
- the suites;
- tokens and model.

Then run `seldon verify` and `seldon cc complete`, merge, and push.
