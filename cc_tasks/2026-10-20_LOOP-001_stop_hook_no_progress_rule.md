# LOOP-001: the Stop hook ends a session on no progress, not on a count; the register allocates its sequence at merge

**Repo:** seldon. L4: commit and push. Work on your worktree branch; the dispatcher merges on green.
**Date:** 2026-10-20. **Authored by:** a Desktop session in squiddy (SQ8).
**Governing:** AD-034 ADDENDUM 01 (the Stop hook is the completion gate; its block cap of 20 was set with no measured basis and is withdrawn by this task), AD-033 (the decision register), AD-038-R6. Write the two rules as AD-034 ADDENDUM 04 and AD-033 ADDENDUM (next number).
**After:** none
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Model:** primary
**Spend:** est. 0.25M tokens. Basis: one hook change with its tests; one allocation change in the register with its test. The floor is 131K.
**Parts:** A 0.6, B 0.4.
**Network:** none beyond git push.
**Exclusive:** yes
**Premises:**
- premise: the stop gate exists in the stations module | check: `grep -q "stop_gate" seldon/core/stations.py`
- premise: the live probe that showed the loop is on disk | check: `test -f docs/evidence/friction002/stop_gate_live_probe.jsonl`
- premise: the register collision is on record | check: `grep -q "rebase_conflict" logs/seldon_dispatch.log`

Glob and read every sibling `*LOOP-001*ADDENDUM*.md`.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.4M.

## Part A: no-progress rule

The prior art is the vendor's own statement of the loop pattern (code.claude.com/docs/en/workflows, "keep fixing until a check passes ... or two rounds in a row make no progress") and the bounded-retry literature (Reflexion, Shinn et al. 2023: a retry must carry new information or stop). FRICTION-002's live probe recorded the failure mode: a model that could not pass its check re-asserted the same state 13 times until the CLI's cap ended the session.

1. The Stop hook keeps, per session, the output of each `check:` on every block (stdout, stderr, exit code, hashed). A block is a round. When two consecutive rounds produce identical check outputs, the hook records `no_progress` with the two round numbers and lets the session end; the dispatcher then treats the finish as `stop_gate_unpassed` (existing path, never merged). When outputs differ, the session continues, with no count and no cap. The CLI's own cap stays as the backstop and is never the first thing that fires.
2. Remove the block cap FRICTION-002 added (its RESULT names it `stations.stop_hook_block_cap: 20`; find the key by its current name in `seldon.yaml` and the station code) and the code that reads it. The loader refuses the key.
3. Tests, failing on HEAD: two identical rounds end the session with `no_progress`; three rounds whose outputs differ continue; a round that passes ends the session `pass`; the cap key is refused at load.

Acceptance:
- `check: pytest tests/test_loop001_no_progress.py -q`
- `check: ! grep -qi "block_cap" seldon.yaml`

## Part B: register sequence at merge

STD-001R and DISP-001R both took seq 292 on 2026-10-19 because `seldon decision accept` numbers a record when it is written on a branch. Prior art: any append-only log with a single writer assigns positions at the commit point, not at the proposal (Kafka's offset is assigned by the broker on append; a database sequence is drawn inside the transaction that commits).

1. On a branch, `decision accept` writes the record with a provisional id (the record's content hash) and no seq. The dispatcher's merge step, under the pass lease on the primary, assigns the next seq to every unnumbered record in the merge, rewrites REGISTER.md, and records `register_numbered` with the mapping. A record is never numbered twice.
2. Tests, failing on HEAD: two branches each with one unnumbered record merge in sequence and receive consecutive seqs with no conflict; a record already numbered keeps its number.

Acceptance:
- `check: pytest tests/test_loop001_register_seq.py -q`

## Report

RESULT under 12 lines: the no-progress rule as implemented, the removed key, the register allocation, test names, tokens against 0.25M.
