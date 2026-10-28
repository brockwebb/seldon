# RESULT: SEL-014R, the OODA between chained tasks is a knowledge source the dispatcher launches, and a mechanical refusal is retried under a rule

**Task:** `fe704e5e` (`cc_tasks/2026-10-28_SEL-014R_the_ooda_is_a_knowledge_source_the_dispatcher_launches.md`).
**Design:** `docs/design/AD-038_ADDENDUM_07_the_ooda_as_a_knowledge_source.md` (AD-038-R16, R17, R18).

(In progress. The Part D checkpoint plan below was written before the first paid call, per CLAUDE.md section 15.)

## Part D checkpoint plan (written before the first model call)

The acceptance replay with the real model, `scripts/sel014r_replay_with_the_model.py`:

- **Unit:** one OODA run on one `precedes` edge of the overnight chain (NUM-001R → DESK-004R, DESK-004R → DISP-004R,
  DISP-004R → RECALL-002R): three units, each in a detached worktree at the commit that brought the predecessor's
  RESULT to main, under `/tmp/sel014r/replay/`, with the sibling repositories linked beside it.
- **Key:** sha256 of (predecessor id, successor id, replay commit, model id, sha256 of `seldon/core/ooda.py`).
- **Checkpoint:** `docs/evidence/sel014r/replay_with_the_model.jsonl`, one fsynced line per finished unit; re-running
  the same command skips completed keys.
- **Progress:** every 60 s and at each unit boundary, to stdout and `docs/evidence/sel014r/replay_with_the_model_progress.txt`.
- **Pilot:** the first unit; its measured tokens × 3 is printed as the projection; abort (exit 4) above the ceiling.
- **Ceilings:** per run 300,000 tokens (`dispatch.ooda.token_cap`, the task's "0.3M per OODA run") and 1,800 s
  (`ooda_grace_s`), enforced by the holder's reap; total 900,000 tokens and 5,400 s, which stop new units (exit 3).
- **Failures:** a unit that raises is a row with its error; an expired session is an `ooda_expired` row.
- **Tested:** `tests/test_sel014r_replay_script_checkpoint.py` SIGKILLs a run mid-unit and resumes it; the checkpoint
  equals an uninterrupted run's and the completed unit's call is not repeated.
- **Estimate:** not measured before the pilot. A guess: 50,000 to 150,000 tokens per run (input + cache writes +
  output), so 150,000 to 450,000 in total.
