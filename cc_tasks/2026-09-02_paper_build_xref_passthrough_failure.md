# CC Task: Root-cause and fix the pre-existing failure in `test_build_paper_unknown_xref_passthrough`

**Date:** 2026-09-02
**Authored by:** Desktop session
**Immutable once written. Before starting: glob and read all sibling `2026-09-02_paper_build_xref_passthrough_failure_ADDENDUM*.md` files.**

## Context

`cc_tasks/2026-09-02_snapshot_artifacts_verify_RESULT.md` reports the full suite at 694 passed, 1 failed: `tests/test_paper_build.py::test_build_paper_unknown_xref_passthrough`, exit code 1 vs expected 0, reproduced on a clean worktree of `86b039b` — i.e. it predates AD-027. A red suite masks the next regression; it does not stay red.

## Steps

1. Reproduce on `main` HEAD. Record the failing assertion and the build's stderr in the RESULT.
2. Bisect: find the commit that turned this test red (`git bisect` between the last known-green commit and `86b039b`; the AD-022..026 burst `63228b0` and the ontology-replay fix `86b039b` are the likely candidates). Name the commit and the change.
3. Decide, with the reason stated, which is wrong: the test's expectation (an unknown `{{xref:...}}` token should pass through with exit 0) or the build's behavior (exit 1 on an unknown xref). Read `docs/design/` and the AD that introduced the current behavior before deciding; the design record wins over the test if they disagree, and the RESULT says which one was updated and why.
4. Fix the one that is wrong. No other test changes.
5. Full suite via the dotenv form (the RESULT above notes the zsh `source .env` form silently skips DB tests). Report pass/fail counts before and after. Fix the CLAUDE.md test invocation line if it still shows the form that skips DB tests.

## Constraints

Zero model calls. No project databases touched. Do not modify AD-027 code paths.

## Completion

RESULT at `cc_tasks/2026-09-02_paper_build_xref_passthrough_failure_RESULT.md`; `seldon cc complete`; commit and push.
