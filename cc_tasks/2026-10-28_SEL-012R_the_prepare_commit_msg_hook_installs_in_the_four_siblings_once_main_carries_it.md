# SEL-012R: the prepare-commit-msg hook installs in the four siblings once seldon's main carries it

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
**Premises:**
- premise: the installed seldon carries the third hook's subcommand | check: seldon hooks prepare-commit-msg --help
- premise: seldon's main tracks the third hook | check: git cat-file -e main:.githooks/prepare-commit-msg

Checks are single commands with no shell.

Read `cc_tasks/2026-10-28_SEL-012_the_pass_ledger_hook_lands_and_installs_in_every_governed_repository_RESULT.md`
before starting.

## The condition

SEL-012 landed `seldon hooks prepare-commit-msg` and installed the third hook in seldon. It could not install it in the
four siblings: their hooks run the installed seldon (the editable install at seldon's primary checkout, which is
main), and until SEL-012 merged, main had no `hooks prepare-commit-msg`. A tracked `prepare-commit-msg` there would
have refused every commit, the dispatcher's record commits included (SQ-096 RESULT, "Not done here", item 2). This
task runs after the merge, so the premise above holds. The dispatcher's `ensure_installed` does not install the third
hook by itself: `status` reports it as `sequenced` and does not count it missing.

## What to build

**A. Install in the four siblings.** For each of squiddy, arnold, ai-readiness-kg and hazbrief-mcp:

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

- `seldon hooks status` reports `installed: true` and `sequenced: true` in all four.
- The work trees of all four have no new uncommitted changes from the install.

## What NOT to do

- Do not edit any hook file by hand, and do not pass `--no-verify` or `-c core.hooksPath=...`.
- Do not change squiddy's `pass_ledger:` block or kit code.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.2M.

## Deliverables

A; `cc_tasks/2026-10-28_SEL-012R_the_prepare_commit_msg_hook_installs_in_the_four_siblings_once_main_carries_it_RESULT.md`.
