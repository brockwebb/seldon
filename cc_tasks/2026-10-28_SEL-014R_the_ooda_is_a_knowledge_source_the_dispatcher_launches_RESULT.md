# RESULT: SEL-014R, the OODA between chained tasks is a knowledge source the dispatcher launches, and a mechanical refusal is retried under a rule

**Task:** `fe704e5e` (`cc_tasks/2026-10-28_SEL-014R_the_ooda_is_a_knowledge_source_the_dispatcher_launches.md`). No
addendum existed at launch.
**Design:** `docs/design/AD-038_ADDENDUM_07_the_ooda_as_a_knowledge_source.md`, rulings AD-038-R16, R17 and R18,
with register records written by `seldon decision accept` (pending; numbered at merge).
**Branch:** `worktree-cuddly-crunching-starfish`. Not merged, pushed or completed here; the dispatcher does that.

Recall used: seldon:AD-038-R10, seldon:2026-10-26_SEL-010R2_dispatch_waits_for_the_desktop_ooda_between_chained_tasks_RESULT, seldon:AD-033-R2

(AD-038-R10 and the SEL-010R2 RESULT are the c18 design R17 amends, and their tests were amended rather than
replaced. AD-033-R2 is why the three rulings' records went through `seldon decision accept` in the note's commit.)

## Outcome

| Part | Done | Evidence |
|---|---|---|
| A. Design note, prior art re-run in seldon, rulings numbered | yes | `AD-038_ADDENDUM_07`; `seldon prior-art verify` PASS (event `58a7bed7`); R16 to R18 records pending |
| B. The knowledge source | yes | `seldon/core/ooda.py`, `seldon/commands/dispatch_ooda.py`; 31 tests |
| C. The retry at registration | yes | `retry_mechanical_refusal` in `seldon/commands/cc.py`, used by the MCP tool too; 15 tests |
| D. Acceptance | yes, with the deviation below | stand-in replay (2 tests), model replay (3 runs, twice), checkpoint kill test |

## What was built

**A. The note.** It re-runs the prior-art searches in seldon: four library receipts (the library holds the later
literature, not Hearsay-II, Hayes-Roth 1985, Gelernter 1985 or Collins and Loftus 1975, which are cited by DOI with
no web receipt, because the task ran with no network) and six internal ones. The internal ones include AD-032 §6,
which already adopted the blackboard for the message board ("informs; never dispatches"); R16 departs from that on
purpose, since the OODA's output gates a launch. W4 is ruled **advisory** (R17).

**B. The knowledge source (R16).** With `dispatch.ooda.enabled`, every pass (serial and parallel), after the reconcile
and before candidacy, runs the OODA on at most `max_per_pass` completed tasks that have an open successor and no
record, oldest completion first. Because it runs before candidacy under the pass lease, no successor is evaluated
ahead of its predecessor's OODA.

- The brief is composed by the dispatcher: the RESULT, the successor and its addenda, the successor's `check:`
  premises run against HEAD, Recall for the predecessor, and the governing header.
- The session is `claude -p --worktree` on `model_role`, bounded by `ooda_grace_s` (wall clock) and `token_cap`
  through the holder's inspector and reap.
- The session ends on one `OODA-VERDICT:` line. The dispatcher checks it and writes exactly one record:
  - `ooda_ok`;
  - `ooda_amended`: the addendum is copied from the worktree and committed through the hooks **before** the record;
  - `ooda_blocked`: with the question and the answering note;
  - `ooda_expired`: with a reason from a closed set.
- The worktree and branch are then removed, or kept and named if the session committed on them.

**c18 (R17).** c18 holds only while an OODA is due or the latest record is `ooda_blocked`. `ooda_grace_s` releases
and holds nothing; it is the session timeout and is required above 0 when the knowledge source is enabled.
`ooda pending` and `seldon_ooda_pending` list only blocks. A Desktop `ooda record` answers a block.
`docs/conventions/desktop_ooda.md` is rewritten to match.

**C. The retry (R18).** `cc register` and `seldon_cc_register` retry `number_taken` and `premise_false` once. Every
rule that fits is applied in that one retry:

- next number from the allocator, with the title line updated and `git mv` plus a commit when the file is tracked;
- `sh -c` wrapping for a check that uses shell syntax;
- `stale_evidence` marking and narrowing to the nearest existing ancestor, for a `test -e|-f|-d|-s` or `ls` path
  that is absent in a *sibling* repository the task names outside its premises. A path in this project's own
  repository is never narrowed: that is AD-038-R5's false premise, and it still reaches its author (see Tests).

A premise with no rule, any other refusal, and a second refusal are reported as before; the second refusal names
the retry. Each retry writes one `registration_retried` record. No model call is made.

**Config.** seldon enables it: `ooda_grace_s: 1800`, `ooda: {enabled: true, max_per_pass: 1, token_cap: 300000,
model_role: primary}`, with the reasons beside each value. At enable time, one OODA is due in seldon's graph:
a3357104 (SEL-012) → SEL-015.

## D. Acceptance

**Stand-in replay** (`tests/test_sel014r_replay_overnight_chain.py`). The three edges run at the commit that brought
each predecessor's RESULT to main (`4635958a`, `cf8afdc9`, `8bb4d2fb`), each in a detached worktree of a shared
clone. The stand-in model decides only from the brief the dispatcher built. All three records were `ooda_ok` or
`ooda_amended`, with no block and no expiry. In the broken-premise fixture, n0 moves `a/` to `b/` while n1 still
checks `a/`; it ends `ooda_amended`, and the addendum's commit is named in the record.

**Model replay** (`scripts/sel014r_replay_with_the_model.py`, `claude-opus-5-5`, checkpointed per the plan below).
Token counts are input plus cache writes plus output; cache reads are listed separately and not counted.

| Run | Edge | Record | Tokens | Cache read | Wall |
|---|---|---|---|---|---|
| 1 | NUM-001R → DESK-004R | `ooda_ok` | 41,151 | 292,340 | 43.6 s |
| 1 | DESK-004R → DISP-004R | `ooda_ok` | 34,458 | 186,039 | 55.6 s |
| 1 | DISP-004R → RECALL-002R | `ooda_expired` (`addendum_missing`), **a dispatcher defect, fixed** | 45,700 | 663,846 | 91.0 s |
| 2 | NUM-001R → DESK-004R | `ooda_ok` | 42,274 | 248,919 | 54.6 s |
| 2 | DESK-004R → DISP-004R | `ooda_amended` | 38,819 | 286,052 | 88.1 s |
| 2 | DISP-004R → RECALL-002R | `ooda_amended` | 52,450 | 815,869 | 145.4 s |

Totals: run 1 121,309 tokens, run 2 133,543, all OODA runs 254,852. The pilot (unit 1) measured 41,151 tokens and
projected 123,453 for three units, inside the 900,000 ceiling.

**Run 2 is the acceptance:** three records, each `ooda_ok` or `ooda_amended`, and zero human reads. The sessions
oriented on the substance:

- Run 2 unit 1 found on its own that `_commit_registered` had moved into `reconcile.py`, the fact DESK-004R later
  recorded (AD-038 ADDENDUM 06 §1 item 3).
- Run 1 unit 3 wrote an addendum foreseeing that ai-readiness-kg's dirty tree would refuse RECALL-002R's
  cross-repository push. Run 2 unit 3 wrote a similar one.

Evidence is in `docs/evidence/sel014r/`: both checkpoints, both progress logs, and run 1's lost addendum.

**Run 1, unit 3 was a dispatcher defect, and it is fixed.** The CLI cut the session's worktree under the
repository's *main* working tree (the clone), not under the linked edge tree that was `project_dir`. The dispatcher
therefore rejected the path and recorded a real amendment as `addendum_missing`. `cli_worktree_root` now reads the
common git dir, and `test_an_amended_verdict_is_found_when_the_project_is_a_linked_worktree` fails on the old code
with that exact symptom. The replay's key now covers `dispatch_ooda.py`, so run 2 re-ran all three units rather
than reuse stale rows.

### Part D checkpoint plan (written before the first model call, CLAUDE.md section 15)

- **Unit:** one OODA run on one edge, in a detached worktree at the replay commit under `/tmp/sel014r/replay*/`,
  with the sibling repositories linked beside it.
- **Key:** sha256 of (predecessor id, successor id, replay commit, model id, the sha256 of `seldon/core/ooda.py`,
  and, from run 2, of `seldon/commands/dispatch_ooda.py`).
- **Checkpoint:** `docs/evidence/sel014r/replay_with_the_model.jsonl`, one fsynced line per unit. Re-running is the
  resume.
- **Progress:** every 60 s and at each unit boundary, to stdout and `..._progress.txt`.
- **Pilot:** unit 1, with its projection printed; abort above the ceiling.
- **Ceilings:** 300,000 tokens and 1,800 s per run (the holder's reap); 900,000 tokens and 5,400 s in total.
- **Failures:** recorded as rows.
- **Tested:** `tests/test_sel014r_replay_script_checkpoint.py` SIGKILLs a run mid-unit and resumes it. The
  checkpoint then equals an uninterrupted run's, and the completed unit's call is not repeated.

## Deviations, and what to know

1. **"Four records" in Part D are three.** The overnight seldon chain has four tasks and three `precedes` edges
   (bacacc4c → f7a1d2f0 → 2909ce0f → ff3a4189; RECALL-002R has no successor). An OODA fires per edge, so last night
   would have produced three records. The broken-premise fixture is the fourth `ooda_amended`.
2. **The replay's siblings are live.** Each edge's seldon tree is at its historical commit, but squiddy, arnold and
   ai-readiness-kg are today's checkouts. So the two run-2 amendments partly describe ai-readiness-kg as it is on
   2026-10-28 (dirty tree, 4 commits ahead). Served Recall was off in the replay, because a fresh worktree carries no
   governed export; lexical Recall ran.
3. **The OODA session has no Stop gate.** The task says the source "reuses the worktree launch and the stop-gate
   stations". It reuses the launch (`_launch_cmd`, `_run`, `_worktree_env`, the model lock, the inspector and reap).
   It does not reuse the Stop gate, which checks a task's Parts; an OODA has none, and its one gate (a verdict the
   dispatcher can check) runs in the dispatcher.
4. **R18 was amended during the task, after the full suite caught a defect.** As first ruled, the stale-evidence
   rule also applied to "this project". `tests/test_friction001_registration_premises.py::test_a_false_premise_
   refuses_registration_with_its_output` then failed: the retry turned R5's false premise `test -f
   seldon/core/reconcile.py` into a vacuous `test -d .` and registered the task. The rule now applies only to a
   sibling repository that the task names outside its premises. A premise that names `../arnold/x` does not by itself
   name arnold; that path is the claim under test. Commit `5ffdf0c` changes the code, the ruling's text, its
   re-accepted pending record (`00003_547d9467...`) and a negative control. The note re-verified PASS (event
   `6d4b12ed`).
5. **A FAIL verdict on the AD-038 base note was recorded and then dropped.** Running `seldon prior-art verify` on
   `AD-038_the_machine_reconciles_its_own_state.md` fails on the known library drift (Issue dbe38fac: its two library
   receipts name a release that can no longer be rebuilt). Verdicts are newest-wins per note hash, so that FAIL would
   have overridden the base note's PASS of 2026-10-20 and held every AD-038-governed task on c14 after merge. The
   commit was local and unmerged; I removed it (`git reset --hard HEAD~1`, losing only 30 query-log lines of that
   run). The hazard remains for anyone who verifies AD-038's base note. See Open item 1.
6. **Model decisions vary between runs.** The same edge (DESK-004R → DISP-004R) was `ooda_ok` in run 1 and
   `ooda_amended` in run 2. Both let the chain proceed, which is what R17 relies on, but how often the knowledge source
   amends is not yet stable. A future chart of `ooda_*` kinds per run is the measure.

## Tests

- New: `tests/test_sel014r_ooda_knowledge_source.py` (31), `tests/test_sel014r_registration_retry.py` (15),
  `tests/test_sel014r_replay_overnight_chain.py` (2), `tests/test_sel014r_replay_script_checkpoint.py` (1).
- Amended to R17: `tests/test_sel010r2_ooda_gate_and_adopt.py`. Ten c18 tests asserted R10's grace; each now
  asserts R17, keeping its intent, and `test_the_grace_releases_nothing` replaces `..._releases_it_without_a_record`.
- Dispatch, SEL, MCP, NUM, DESK and DISP subset after Part B: 696 passed.
- Full suite (`-n 8`, before the R18 amendment): 3070 passed, 7 skipped, 3 failed.
  - `test_friction001_registration_premises::test_a_false_premise_refuses_registration_with_its_output`: **this
    task's defect**, fixed in `5ffdf0c` (deviation 4). It passes now.
  - `test_dispatch_parallel::test_two_disjoint_non_exclusive_tasks_run_concurrently_and_both_merge`: a timing flake
    under `-n 8`, known since SEL-011. It passes alone (38.7 s).
  - `test_pa002_release_resolve::test_rebuilding_the_served_release_reproduces_the_served_index`: fails on main for
    the library drift (Issue dbe38fac). Not this task's.
- After the amendment, every test that touches registration or premises (27 files plus the SEL-014R files):
  594 passed, 6 skipped, 0 failed. The full suite was not re-run, because the amendment can only make registration
  refuse more; the dispatcher's merge gate re-runs it.

## Open

1. **AD-038's base note cannot pass `prior-art verify` until its library receipts are re-run or the drift is fixed
   (Issue dbe38fac).** Until then, do not verify it. Recipe, when the operator chooses: in the seldon primary checkout,
   in a Claude Code window, run `seldon prior-art search --library "<the query on line 36 of the note>"` and file
   an AD-038 erratum that carries the new receipt. Verdicts are newest-wins (`prior_art.verdicts_from_lines`), so a
   failing re-verify is not harmless. That is a design question for AD-036, not for this task.
2. `dispatch_worktree.name_worktree` (task sessions) checks the CLI's worktree against `project_dir`, as the OODA
   did before the fix. That only matters for a dispatcher run from a linked worktree, which no project does.

## Tokens

This session: SESSION_TOKENS at Part D (from `seldon dispatch part-complete`). OODA sessions: 254,852 (above). The
stand-in tests make no model calls.
