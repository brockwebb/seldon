# PA-002: a library receipt verifies against the release it names when that release is on disk; a new library release does not invalidate every prior design note

**Repo:** seldon. L4: commit and push. Work on your worktree branch; the dispatcher merges on green (AD-034 ADDENDUM 01).
**Date:** 2026-10-19. **Authored by:** a Desktop session in squiddy (SQ8).
**Governing:** AD-036-R3 (a receipt is re-runnable against the corpus identity it names), AD-036-R5, AD-036 ADDENDUM 05 (the gate holds every task a note governs until the note passes), AD-038-R6. Write the fix as AD-036 ADDENDUM 06. No new ruling: this restores what R3 already says.
**After:** none
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Model:** primary
**Spend:** est. 0.25M tokens. Basis: one resolver change in `seldon/core/prior_art.py`, tests, and a re-verify of the notes that fail today. The floor is 131K (AD-037-R11).
**Parts:** A 0.6, B 0.4.
**Network:** none beyond git push.
**Exclusive:** yes
**Premises:**
- premise: AD-036's receipts name the 2026-09-30 release | check: `grep -rq "library_graph_20260930_m002" docs/design`
- premise: the release the receipts name is still on disk | check: `test -f /Users/brock/GitHub/squiddy/graphs/library/exports/library_graph_20260930_m002_2026-09-30.json`
- premise: the index serves a newer release | check: `test -f /Users/brock/GitHub/squiddy/graphs/library/exports/library_graph_20261017_sq018_02_2026-10-17.json`

Glob and read every sibling `*PA-002*ADDENDUM*.md`.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.35M.

## The defect, measured

On 2026-10-19 `seldon prior-art verify docs/design/AD-036_prior_art_receipts_gate.md` returned FAIL with seven `release_unavailable` findings (verdict 3ab498a4): each library receipt names `library_graph_20260930_m002` or `library_graph_20261012_sq013_01`, both still in `squiddy/graphs/library/exports/`, and the verifier compared them only with the release the index serves now (`library_graph_20261017_sq018_02`, cut by SQ-018R on Friday). Every design note with a library receipt written before Friday fails the same way, so every task any of them governs is held at registration (STD-001 was, 2026-10-19). A release is a corpus identity, which R3 chose so a receipt could be re-run; the verifier threw that identity away.

## Part A: resolve the named release

1. A library receipt names a release file and its sha256. Verification loads that release from the library's `exports/` when the file is present and its digest matches, builds the query against it (the kit's `serve` index can be built per release in a temp dir, or the receipt's rows can be checked for membership in that release's row set: choose the cheaper that honours R5's top-20 membership rule, and say which), and passes or fails on membership as before. Only when the named release is absent from disk does the verifier report `release_unavailable`, and that finding names the path it looked for.
2. The query log records which release each verification ran against.
3. Tests, failing on HEAD: a receipt naming a present older release verifies; one naming an absent release reports `release_unavailable` with the path; the current-release path is unchanged.

Acceptance:
- `check: pytest tests/test_pa002_release_resolve.py -q`

## Part B: re-verify what Friday broke

1. Run `seldon prior-art verify` on every design note in seldon and squiddy that carries a library receipt (list them by grep for `library receipt:`), record the verdicts, and list in the RESULT any note that still fails and why.
2. AD-036 ADDENDUM 06: the resolver rule, the 2026-10-19 evidence, and the list of notes re-verified.

Acceptance:
- `check: seldon prior-art verify docs/design/AD-036_prior_art_receipts_gate.md`
- `check: test -f docs/design/AD-036_ADDENDUM_06_receipts_resolve_the_named_release.md`

## Report

RESULT under 15 lines: the resolver choice, the notes re-verified with verdicts, any still failing, tokens against 0.25M.
