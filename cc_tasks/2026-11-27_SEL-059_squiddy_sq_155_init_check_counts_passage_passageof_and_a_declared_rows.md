# SEL-059: squiddy SQ-155: init --check counts Passage, PassageOf and a declared rows file's classes as emitted

**Status:** proposed
**Author:** `seldon cc return`, 2026-11-27, for squiddy SQ-155 (82fa761a), which answered squiddy:fb0f9767 (AD-036-R16).
**Returns:** squiddy:82fa761a-c85f-4b1f-ab08-0d360cb7b870 (SQ-155)
**After:** none
**Spend:** est. 0.01M agent tokens. Basis: one init check; zero model calls.
**Network:** none
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Parts:** A 1.00.

squiddy:fb0f9767 (fb0f9767) was filed into squiddy; squiddy task SQ-155 (82fa761a) answered it. This task is that answer's return, filed by the answering task rather than pasted by hand (AD-036-R16).

## What landed, and where

- The answering task: `squiddy/cc_tasks/2026-11-27_SQ-155_six_open_filings_with_a_known_fix_are_answered.md`.
- Its RESULT: `squiddy/cc_tasks/2026-11-27_SQ-155_six_open_filings_with_a_known_fix_are_answered_RESULT.md`. Read it in full before starting.
- The commit: squiddy@fe580d7c221468a02b64a6d019d0142dc7d2f8bf (on branch worktree-enumerated-fluttering-parnas, which the dispatcher merges to main).

## What seldon does with it

Answers seldon's filing `fb0f9767` (`init --check` reported Passage, PassageOf and the rows-ingested classes as
declared but never emitted).

What changed: `init.check` counts `squiddy passage promote`'s two classes as always buildable, and the classes in
`squiddy/rows.yaml` `writable` as buildable for a spec that declares `rows:`, as SQ-101 counted `WorkDerivedFrom`.
Test: `test_check_counts_passages_and_a_declared_rows_files_classes_as_emitted`, plus its control.

Step, in the seldon repository (shell, from its root):

1. `SQ init graphs/seldon-biblio --check`
   Expected: exit 0, `matches graph.yaml` (measured read-only with this branch's kit: spec sha256 `9a27037c29a5`).

Nothing in seldon changes. factory-kg's same finding is cleared too (in factory's section).

## Part A: apply it

Acceptance:
- `check: test -f cc_tasks/2026-11-27_SEL-059_squiddy_sq_155_init_check_counts_passage_passageof_and_a_declared_rows_RESULT.md` (the RESULT says what was applied, and what was not)
