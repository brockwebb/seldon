# HOOK-001: the commit gate runs as a git hook, and the three refused register statements are rewritten

**Repo:** seldon (primary). Cross-repo by absolute path for every repo whose `seldon.yaml` exists under `/Users/brock/GitHub`. Each gets its own `feat/HOOK-001` branch. L4: commit, merge, push.
**Date:** 2026-10-09. **Authored by:** a Desktop session in squiddy (OODA on PA-001 and SEL-005).
**Governing:** `/Users/brock/GitHub/seldon/docs/design/AD-036_prior_art_receipts_gate.md` R4 (commit point), with `/Users/brock/GitHub/seldon/docs/design/AD-036_ADDENDUM_01_self_test.md`, and AD-033-R3/R8 (`/Users/brock/GitHub/seldon/docs/design/AD-033_decision_register.md`). Read `/Users/brock/GitHub/seldon/cc_tasks/2026-10-09_PA-001_prior_art_receipts_gate_RESULT.md`. Glob and read every sibling `*HOOK-001*ADDENDUM*.md`.
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Model:** primary
**Spend:** est. 0.6M tokens for this session, plus Part B's statement pass for 3 records (under 20k weighted).
**Network:** none beyond git push.

## Step 0
If this task is `in_progress` in the seldon graph, stop. Otherwise set it `in_progress` immediately, so the standing dispatcher cannot launch a second copy.

## Part A: the commit point of AD-036-R4 is a hook

PA-001 found no pre-commit hook runs. `core.hooksPath` names a removed `Documents/` path. So the "commit gate" is `seldon verify` run by protocol: a prose rule, the failure AD-036 exists to end.

1. **Find the cause.**
   - Establish where `core.hooksPath` is set: global, system or per repo. Read what it named and when it was set, from git history and `seldon prior-art search --internal "hooksPath"` and `"pre-commit hook"`.
   - Record the receipts in the RESULT.
2. **Build the hook.**
   - Add `seldon hooks install`. It sets `core.hooksPath` per repository, never globally, to a tracked `.githooks/` directory.
   - Its `pre-commit` runs the Tier A checks for staged governed files only: Prior art, `ruling_label_unparsed`, and the others Tier A holds.
   - Unstaged state never decides a commit.
   - Measure hook time on a typical commit. Report p95 over 10 commits; the bound is 5 s, with no measured basis.
3. **Clear the broken path.** Remove the dead global or system `core.hooksPath` only if that is where it is set, and record the old value in the RESULT.
4. **Install everywhere.** Run `seldon hooks install` in every repo with a `seldon.yaml`, and in the dispatcher's launch path: a dispatched session commits through the same hook.
5. **Prove it.** A planted design note without prior art is refused by `git commit` itself, with no seldon command typed. `git commit --no-verify` is the only way past. `seldon verify` reports any commit on main since this merge that touched `docs/design/` without a recorded verdict, as `hook_bypassed`.
6. **Tests:**
   - the planted refusal;
   - the bypass detection;
   - the hook is installed by path, not copied (`.githooks/` tracked);
   - removing the hook makes the planted-refusal test fail.

## Part B: three rulings that do not bind

AD-035-R8, AD-036-R4 and AD-036-R7 were refused at the AD-033-R3 deictic check ("this decision", "the note") and stand flagged failed. A failed record is not retrieved, so the commit-gate ruling itself is invisible to registration.

- Re-run AD-033-R8's writer for those three with the referent supplied: the note's title and id in the writer's context. The source text stays verbatim.
- Validate as usual. Land them as amend records.
- If a record still fails, report its text and the check's reason; do not hand-write a statement.

## Report

Write the RESULT, under 30 lines, to `/Users/brock/GitHub/seldon/cc_tasks/2026-10-09_HOOK-001_commit_gate_is_a_hook_not_a_protocol_RESULT.md`. It covers:
- the hooksPath cause, with receipts;
- every repo installed;
- hook p95;
- the planted refusal and the bypass check;
- the three records;
- suites (passed, skipped, xfailed, deselected, failed);
- tokens and model.

Then run `seldon verify` and `seldon cc complete`, merge, and push.
