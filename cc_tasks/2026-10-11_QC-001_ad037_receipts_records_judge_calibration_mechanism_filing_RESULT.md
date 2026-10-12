# QC-001 RESULT: AD-037's receipts and records, judge calibration, the checker, marked criteria, the notebook filed

**Date:** 2026-10-12. **Task:** 00e22dd9. It was registered, and set in_progress, only after Part A's `seldon prior-art verify` passed. Merge `47afd69` (seldon), plus ai-readiness-kg `06f3fdd8` and squiddy `9875fdd`.

**Part A.** 8 internal queries and 8 library queries (one per S1 to S8 title), run one at a time, 2026-10-12. `prior-art verify` PASS on AD-037 (sha256 7b80f91c34ff). AD-037 committed through the hook in `c283fa8`, now on main. The receipts found: **Internal, real precedent:** AD-032 FC-28/29 (andon, huddle) and FC-33 with its register records; DN-022 and wintermute TEVV A2 (ABBA); the pilot-first rule in squiddy S-008/Q-003 and ai-readiness-kg DN-008; self-preference declared as a risk, never measured, in squiddy S-008/Q-001/Q-003/Q-005, ai-readiness-kg and wintermute. **Internal, nothing:** "first article inspection" and "earned value" are used nowhere (the earned-value hits are lexical). **Library:** S8 is held (arXiv:2410.10934). S1 to S7 are not; their rows are other works (S1 and S3: the LLM-as-a-judge survey 2411.16594).

**Part B.** Records: `seldon:AD-037-R1` to `R10`, accepted, decided_by desktop (register 00251 to 00260). R10's amendment on FC-33: register 00261. The probe task naming AD-037-R1 binds it ("names it"). AD-033-R8 statements: R1 and R6 (the pilot) written and validated, then landed (00262, 00263). The other eight still hold their verbatim source as the statement. Why: the pilot measured 5.9k weighted per record, against about 4k assumed; the governor's projection for the rest, 50.3k, passed the 48k stop line (40k declared plus 20%); so the bulk was refused before any call, and nothing past the pilot was spent; landing them means going over the declared cap, which is the operator's call (touchpoint 1).

**Part C.** `seldon qc calibrate-judge` writes three numbers, each with its n: ABBA flip rate, with a Wilson-95 interval; replicate kappa, with Cohen's (1960) interval, plus a Wilson interval on its raw agreement; self-preference (catch rate on reference plants minus generator-style plants), with Newcombe's (1998) interval. Two refusals: `calibration_incomplete`, and `judge_uncalibrated` in `seldon.models.resolve_judge`. Reports are keyed to the judge's and the generator's lock ids, so a lock bump voids them. The bar (0.70 Wilson lower bound, n of at least 30) is in `models/registry.yaml`. The set seed (`models/calibration/set.yaml`, zero model calls): 10 items. By class: premise_found_wrong 6, implicit_default 1, unparsed_label 1, label_collision 1, unbounded_resource 1. Each item is one real defect with its receipt, in a pre-2022 library abstract with one minimal plant. Generator halves are QC-002's slots. Lesson record `seldon:AD-032-FC-26-L1`, kind `requirement` (AD-033-R3 has no `lesson` kind). Its consumers: `seldon/core/qc.py`, `seldon/commands/qc.py`, `seldon/models.py`, `tests/test_qc_calibrate_judge.py`. Its reason carries DN-022's report and date.

**Part D.** `checker` tiers in the registry: haiku to sonnet, sonnet to opus, opus to fable, and fable to fable obfuscated. `resolve("checker", generator=...)` returns the locked id. Tested for all four families and for a missing generator.

**Part E.** `criterion_unmarked` at `seldon cc register`. Baseline: 68 tasks (`docs/evidence/qc001/criteria_baseline.txt`; QC-001 is left out and passes). SQ-011's 4 criteria are marked.

**Part F.** Both copies hash to `1d526d502a3431684a9aa82da9f714b8197c4f9b0e4a3e7876f09abd679957e4`. The workbench row is FILED, and the workbench copy is kept.

**Part G.** `max_parallel` is 1 in all three dispatch blocks; ai-readiness-kg's is now explicit, where before it held by default. Each has an AD-037-R9 comment. `tests/test_dispatch_parallel_held.py` reads every dispatch block beside seldon. STOP file untouched.

**Suites (seldon):** 2384 passed, 0 skipped, 0 xfailed, 0 deselected, 0 failed. `seldon verify`: all checks passed.

**Premises found wrong:**
1. "S1 to S8 are not in the library graph": S8 is held.
2. HOOK-001's RESULT lists no premises found wrong.
3. The internal arm searched AD-037 itself, uncommitted on disk. A receipt naming the note's own bytes cannot verify once it is inserted, so those self-hits were left out. The arm should exclude the note being written (follow-up).
4. A Wilson interval does not fit kappa.
5. AD-033 has no `lesson` kind.
6. AD-037 could not be committed before Part B: the hook needs its ten records staged with it. Its "**AD-035-R2 and R7.**" citation also read as declaring AD-035-R2, so it was unbolded before the first commit.
7. R9's hold is enforced by the test, not by the dispatcher: SEL-004's tests build parallel configs with no opt-in record.

**Tokens and model:** Claude Opus 5.5. About 0.32M uncached (input plus cache writes plus output) against the 3M estimate, plus 45.2M cache reads, all from this session's transcript; plus the statement pilot's 11.8k weighted (Sonnet, role `register_statement`).

**Erratum, 2026-10-12, after completion.** Part D's schema change (`load_registry` requires `checker:` and `calibration:`) failed squiddy's recorded pass on b36c413: 55 failures per seed. Squiddy's `tests/fixtures/model001/registry.yaml` was a static byte copy of this registry at 3500b54, while its suite imports this checkout. The fix was a re-copy at fe19900 with its pin moved (squiddy 5359789). Arnold, ai-readiness-kg and icsp_notebook copy the live registry when their tests run, so they were not affected. A registry schema change here should search the consumers for static copies before it lands.
