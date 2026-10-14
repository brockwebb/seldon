# DISP-c7: the prior-art query log is the calling repo's evidence; seldon's tree stops re-dirtying

**Repo:** seldon. L4: commit, merge, push.
**Date:** 2026-10-14. **Authored by:** Desktop session.
**Resolves:** Issue 7e70aeb0. **Governing:** AD-036 (prior-art receipts are evidence of the repo whose document they support), the dispatcher's c7 clean-tree criterion.
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**After:** none
**Model:** primary
**Spend:** est. 600k tokens.
**Parts:** A 0.15, B 0.45, C 0.20, D 0.20.
**Part map:** A is the rulings; B is steps 1 and 2; C is steps 3 and 4; D is step 5 and the gate.
**Network:** none beyond git push.
**Exclusive:** yes

## Step 0

If this task is `in_progress`, stop. Otherwise set it `in_progress` now.

## Measured premises (verify; report any that is wrong)

- `seldon prior-art search` and `verify` append every query, from any repo on the machine, to `state/prior_art_queries.jsonl` in the seldon checkout, which git tracks. MODEL-003's RESULT confirmed this (dirty-tree section): the operator committed it twice on 2026-10-13 and it was dirty again within hours. Issue 7e70aeb0 records 300+ refused dispatcher passes on c7 for a task that never touched the file.
- `docs/evidence/model001/refresh_*.json` is written by the automatic lock refresh; on 2026-10-12 the refresh wrote evidence without committing it.
- A cross-repo filing into seldon's `cc_tasks/` (the 2026-09-28 DesignNote-cites proposal, its 2026-10-13 slosh-pipe addendum) is left untracked, because nothing registers it.

## Rulings (write as an addendum to AD-036 or the dispatcher's AD, whichever owns c7; bold `-Rn.` lines so the register reads them)

1. The prior-art query log lives in the repo that ran the search (`<repo>/state/prior_art_queries.jsonl`), beside the document the receipt supports. Seldon's own log holds only seldon's searches. Prior art: a test's fixtures and a build's lockfile live with the project that uses them.
2. Automatic writers (lock refresh, the query log) commit what they write, in the repo they write to, with a path-scoped commit through the hooks; an automatic process that leaves a tracked file dirty is a defect.
3. A cross-repo filing into another repo's `cc_tasks/` registers the file there (`seldon cc register --project <that repo>`), which commits it. Writing without registering is refused by the filing helper, if one exists; if none exists, say so and add the rule to the filing instructions in CLAUDE.md.

## Steps

1. Move the log: `seldon prior-art search/verify` resolve the calling repo (the `--project` dir, else cwd's seldon.yaml) and append there. Migrate the existing seldon log: split its lines by `corpora` or `release` provenance where the calling repo is recoverable; lines that are not attributable stay in seldon's log, counted in the RESULT.
2. The verifier reads receipts from the calling repo's log. Prior-art verify on every repo with a `state/prior_art_queries.jsonl` after migration gives the same verdicts as before, per document; quote the before/after table sha256.
3. The lock refresh commits its evidence file in the same run as the lock (one commit), or, when the lock did not change, commits the evidence alone. Test with the fake runner.
4. Fix the defect MODEL-003 found: an internal receipt whose hit path contains spaces is `malformed` to the verifier. Encode or quote the path; add a test with a path containing two spaces.
5. Register the two untracked cross-repo filings in seldon as tasks of their own (`seldon cc register`), state `proposed`; do not run them.

## Gate

- check: full seldon suite, detached and polled; quote passed, skipped, xfailed, deselected, failed.
- check: `git status --porcelain` empty in seldon, ai-readiness-kg, squiddy, arnold and icsp_notebook after one `seldon prior-art search` from each; quote.
- check: `seldon dispatch status` in seldon reports `dirty=False` across three consecutive passes with another repo's prior-art search run between them.
- check: `seldon verify`.

## RESULT

Under 40 lines: migration counts (attributed per repo, unattributable), the verdict table sha256s, the refresh commit behaviour, the two registered task ids, premises found wrong. `seldon cc complete`, merge, push. Close Issue 7e70aeb0 by reference.
