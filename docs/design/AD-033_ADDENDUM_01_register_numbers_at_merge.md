# AD-033 ADDENDUM 01: the register numbers a branch's records when the branch merges

**Date:** 2026-10-20. **Written by:** LOOP-001 Part B (`cc_tasks/2026-10-20_LOOP-001_stop_hook_no_progress_rule.md`).
**Amends:** AD-033-R2 (one write path) for records written on a branch. One new ruling.

## Evidence

On 2026-10-19 STD-001R and DISP-001R both took seq 292. Each branch's `seldon decision accept` appended `00292_...`
after the same tail, and the second merge stopped at `rebase_conflict` (`logs/seldon_dispatch.log`). With parallel
dispatch (AD-034), two branches cut from one main will always both see the same tail.

## Prior art

An append-only log with a single writer assigns positions at the commit point, not at the proposal. Kafka's broker
assigns the offset on append. A database sequence is drawn inside the transaction that commits. The register's
single writer at the commit point is the dispatcher's merge step, which holds the pass lease on the primary checkout.

## The rule

- **AD-033-R12. A record written in a linked git worktree is written under the register's `pending/` directory with a provisional id (the sha256 of its content) and no seq, prev_hash or record_hash; the dispatcher's merge step, after the fast-forward and under the pass lease on the primary checkout, appends every pending record to the chain in written order, renders REGISTER.md, commits both and records `register_numbered` with the mapping from provisional id to seq; a record whose provisional id the chain already holds is never numbered again.**
  A branch's pending records fold after the chain, so they bind the branch's later commands. REGISTER.md renders
  the chain only, so a branch never edits it. Before the fast-forward, the merge verifies the rebased branch's
  register, pending records included. Two branches that create one id are blocked there as `register_invalid`.
  A numbering that fails after the merge is recorded on `register_numbered` with its `error`. `seldon decision
  number` retries it on the primary and refuses in a worktree. A primary checkout on a non-main branch still
  numbers directly, as before. Code: `seldon/core/decisions.py` `Register.append_pending`, `Register.number`,
  `number_register`, `is_linked_worktree`; `seldon/commands/dispatch_worktree.py` `number_merged_register`,
  `_register_findings`; tests `tests/test_loop001_register_seq.py`.

**Transition.** This branch's own records (AD-034-R11, AD-033-R12) are written pending. The supervisor that merges
this branch runs the code from before it, so it does not number them. The first merge after this one numbers them,
or `seldon decision number` on the primary does.
