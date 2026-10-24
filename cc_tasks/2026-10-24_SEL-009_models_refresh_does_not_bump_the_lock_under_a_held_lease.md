# SEL-009: `models refresh` does not move the lock while a run holds it, and the pilot is sized to what it detects

**Status:** proposed
**Author:** Desktop session (hazbrief), 2026-10-24
**Repo:** seldon (primary); squiddy reads the lock (MODEL-001, `pin_cli`) and is cited, not changed here.
**Governing:** AD-035 (the model lock; R3, R7 the pinned CLI). SQ-038R and its ADDENDUM-00 in squiddy hold the measurement; cite them, do not duplicate them.
**Model:** primary
**Spend:** est. 0.3M tokens. Basis: a lease check in `models refresh`, a deferral record, tests. Zero model calls.
**Network:** none beyond git push.
**Exclusive:** no
**Parts:** A 0.50, B 0.50.
**Premises:**
- premise: the lock resolved at 00:09Z on 2026-10-24 | check: grep -q 2026-10-24T00:09 /Users/brock/GitHub/seldon/models/models.lock.yaml
- premise: a hazbrief run stopped on the bump | check: grep -q cli_not_piloted /Users/brock/GitHub/hazbrief-mcp/cc_tasks/2026-10-23_HB-24_rerate_every_claim_under_the_operational_rubric_RESULT.md
- premise: the re-pilot's cost is recorded | check: grep -q 4,212,332 /Users/brock/GitHub/hazbrief-mcp/cc_tasks/2026-10-24_HB-25_pilot_on_cli_2_1_310_and_finish_the_rating_topup_RESULT.md

Glob and read every sibling `*SEL-009*ADDENDUM*.md`.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.4M.

## The defect

The daily `models refresh` bumped the CLI from 2.1.309 to 2.1.310 at 00:09Z, forty minutes earlier than the hour the operator had planned around. hazbrief's rating top-up was mid-run under a dispatcher lease. squiddy's `pin_cli` (MODEL-001, correctly) refused the next client build with `cli_not_piloted`, stranding 6,701 claims for 1 h 47 min, and the re-pilot the rule then required cost 4.21M weighted (23 % of the top-up it unblocked) to find that content was within one claim on every unit and the only change was cost, 2x per call from a cache effect (squiddy SQ-034). Two faults on Seldon's side:

1. **The refresh has no notion of a held lease.** A lock bump during a run is a mid-run change of the measured system (AD-035's own reasoning for the pin). The refresh should defer while any project's dispatcher lease is held, or while any run has registered itself against the lock, and record the deferral.
2. **The pilot is one size.** MODEL-001 requires a full re-pilot on any CLI change. The cost regime change was visible after the first document (1,439 against 926 weighted per call); content equivalence was decided on 733 same-text claims where a tenth would give the same verdict. The rule should let a project declare a tiered pilot: a cost band on the first N calls, then a content comparison on a bounded sample, with the full pilot reserved for a tripped band or a declared major change.

## Part A: the refresh defers

1. Test first: `seldon models refresh` with a lease held in any project under `prune.repositories` (or a new `lock.holders` list) writes a `lock_refresh_deferred` record naming the holder and exits 0 without touching the lock; with no lease held it refreshes as now. A `--force` exists and is logged.
2. The scheduled refresh time is read from one place and printed by `seldon models show`, so the operator's "about 00:49Z" is a fact, not a memory.

## Part B: the tiered pilot, as a lock-side declaration

3. Test first: `models.lock.yaml` (or the project's `seldon.yaml` under `models:`) can carry `pilot: {cost_calls: N, content_sample: M, full_on: [major, band_tripped]}`. `seldon models show` prints it. Seldon writes nothing in squiddy; the RESULT states the field's contract so a squiddy task can read it (file that squiddy task as a one-line proposed stub citing this one, in `../squiddy/cc_tasks/`, as hazbrief tasks do).
4. Gate; commit; push.

## Deliverables

Code, tests, the squiddy stub, `cc_tasks/2026-10-24_SEL-009_models_refresh_does_not_bump_the_lock_under_a_held_lease_RESULT.md`.
