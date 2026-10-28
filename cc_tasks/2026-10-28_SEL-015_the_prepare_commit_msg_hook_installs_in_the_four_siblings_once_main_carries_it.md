# SEL-015: the prepare-commit-msg hook installs in the four siblings once seldon's main carries it

**Status:** proposed
**Author:** CC session (seldon, SEL-012 worktree `flickering-prancing-stream`), 2026-10-28: the remainder of SEL-012 Part B.
**Repo:** squiddy, arnold, ai-readiness-kg, hazbrief-mcp (the install runs there and commits the hook files); seldon (the RESULT).
**After:** 2026-10-28_SEL-012_the_pass_ledger_hook_lands_and_installs_in_every_governed_repository
**Governing:** HOOK-001 (the commit gate is a tracked hook, `core.hooksPath` relative); AD-038-R15 (the hooks installer commits what it writes); squiddy DN-052 R-237, cited by path, not changed here.
**Model:** primary
**Spend:** est. 0.15M tokens. Basis: four `seldon hooks install` runs and four status reads, each rehearsed in a scratch clone by SEL-012 (`docs/evidence/sel012/rehearse_b_transcript.txt`). Zero model calls.
**Network:** none.
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes (commits hook files in four repositories)
**Parts:** A 1.00.

Read `cc_tasks/2026-10-28_SEL-012_the_pass_ledger_hook_lands_and_installs_in_every_governed_repository_RESULT.md`
before starting.

## The condition

SEL-012 landed `seldon hooks prepare-commit-msg` and installed the third hook in seldon. It could not install it in the
four siblings: their hooks run the installed seldon (the editable install at seldon's primary checkout, which is
main), and until SEL-012 merged, main had no `hooks prepare-commit-msg`. A tracked `prepare-commit-msg` there would
have refused every commit, the dispatcher's record commits included (SQ-096 RESULT, "Not done here", item 2). This
task runs after the merge (`**After:**`). The dispatcher's `ensure_installed` does not install the third hook by
itself: `status` reports it as `sequenced` and does not count it missing.

The two facts this task stands on hold only after SEL-012 merges, so they are not `**Premises:**` (registration
evaluates premises when it runs, which was before the merge). Step 0 checks them at launch instead.

## What to build

**A. Install in the four siblings.**

0. Run `seldon hooks prepare-commit-msg --help` and `git cat-file -e main:.githooks/prepare-commit-msg` in seldon's
   primary checkout. If either fails, SEL-012 has not reached main: install nothing, and say so in the RESULT.

For each of squiddy, arnold, ai-readiness-kg and hazbrief-mcp:

1. Record `seldon hooks status --repo /Users/brock/GitHub/<repo>` (expect `"sequenced": false`).
2. Run `seldon hooks install --repo /Users/brock/GitHub/<repo>`. The installer commits only the paths it writes
   (pathspec-limited), so the unrelated uncommitted files in arnold and hazbrief-mcp stay as they are.
3. Record the status again (expect `"installed": true, "sequenced": true`) and the commits the install made.

What the rehearsal (SEL-012, scratch clones, this code) committed in each:
- squiddy: `.githooks/prepare-commit-msg`.
- arnold: `.gitattributes` (`governed/ledger/events.jsonl merge=union`), then `.githooks/commit-msg` and
  `.githooks/prepare-commit-msg`.
- ai-readiness-kg: `.githooks/commit-msg` (untracked in the primary, seldon's exact text) and
  `.githooks/prepare-commit-msg`.
- hazbrief-mcp: `.gitattributes` (`seldon_events.jsonl`, `state/prior_art_queries.jsonl` merge=union), then
  `.githooks/prepare-commit-msg`.

A difference from this list is a finding for the RESULT, not something to work around.

## Success criteria

- `check: seldon hooks status --repo /Users/brock/GitHub/squiddy` (squiddy's gate is installed)
- `check: seldon hooks status --repo /Users/brock/GitHub/arnold` (arnold's gate is installed)
- `check: seldon hooks status --repo /Users/brock/GitHub/ai-readiness-kg` (ai-readiness-kg's gate is installed)
- `check: seldon hooks status --repo /Users/brock/GitHub/hazbrief-mcp` (hazbrief-mcp's gate is installed)
- `check: git -C /Users/brock/GitHub/squiddy ls-files --error-unmatch .githooks/prepare-commit-msg` (squiddy tracks the third hook)
- `check: git -C /Users/brock/GitHub/arnold ls-files --error-unmatch .githooks/prepare-commit-msg` (arnold tracks the third hook)
- `check: git -C /Users/brock/GitHub/ai-readiness-kg ls-files --error-unmatch .githooks/prepare-commit-msg` (ai-readiness-kg tracks the third hook)
- `check: git -C /Users/brock/GitHub/hazbrief-mcp ls-files --error-unmatch .githooks/prepare-commit-msg` (hazbrief-mcp tracks the third hook)
- `judgment: each primary already carries the operator's unrelated uncommitted files, so a clean-tree command cannot tell the install's changes from theirs; the RESULT compares each tree's porcelain status before and after.` (The install left no uncommitted change of its own in any of the four)

## What NOT to do

- Do not edit any hook file by hand, and do not pass `--no-verify` or `-c core.hooksPath=...`.
- Do not change squiddy's `pass_ledger:` block or kit code.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.2M.

## Deliverables

A; `cc_tasks/2026-10-28_SEL-015_the_prepare_commit_msg_hook_installs_in_the_four_siblings_once_main_carries_it_RESULT.md`.
