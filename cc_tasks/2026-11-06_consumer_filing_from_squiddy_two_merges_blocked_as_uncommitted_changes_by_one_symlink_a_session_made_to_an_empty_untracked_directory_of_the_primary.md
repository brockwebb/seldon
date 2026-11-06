# Consumer filing from squiddy: two consecutive merges were blocked as `uncommitted_changes` by one path, a symlink the session made to an empty, untracked, unignored directory of the primary, so a green gate and a finished Part stayed on a kept branch twice

**Repo:** seldon. **Date:** 2026-11-06. **Authored by:** a Desktop session in squiddy (SQ-13), from squiddy's ledger and dispatch log for SQ-114 (ce92a27d) and SQ-114R (878dfe5a), filed into seldon's queue under AD-036-R12 as a report of what a consumer measured. No candidacy headers, not a dispatcher candidate; it registers when SEL-023 Part A lands, and until then seldon's Desktop registers it. This filing proposes no fix; the seldon thread decides what, if anything, changes. It is the same family as squiddy's filing of 2026-11-04 (a merged worktree's removal discards gitignored outputs the primary does not hold): both come from a consumer whose graph state is gitignored and undeclared to the dispatcher, and whose sessions therefore link it by hand.
**Evidence:** squiddy `seldon_events.jsonl`, the two `dispatch_finished` records with `outcome: merge_blocked` (2026-11-05T15:42Z for ce92a27d; 2026-11-05T22:59:38Z for 878dfe5a) and the two Issues the dispatcher opened (the second is `d0180a19`, `merge_blocked`, high/high, `remediated_by` 878dfe5a); squiddy `logs/squiddy_dispatch.log` lines 17693 and 17889 to 17891; the worktree `.claude/worktrees/compressed-wiggling-hinton` as the dispatcher kept it; squiddy SQ-114R RESULT, header paragraph on the 171 links (`/tmp/sq114r/link.py`, `links.txt`) and SQ-114 RESULT section 4; squiddy `seldon.yaml` (declares no `dispatch.worktree_links`); seldon `seldon/core/dispatch.py` `PARALLEL_DEFAULTS["worktree_links"]` (`[".env"]`).

## What the consumer measured

1. **The record, verbatim from the second block** (`dispatch_finished`, 2026-11-05T22:59:38Z, task 878dfe5a):
   ```
   outcome: merge_blocked
   merge: {reason: uncommitted_changes, files: [graphs/library/evidence/20260923_q002/verb_parity_biblio_neo4j], attempt: 1}
   linked: [.env]
   stop_gate: {passed: true, verdict: pass, runs: 1}
   base: eb1f887a; branch: worktree-compressed-wiggling-hinton
   ```
   The first block (ce92a27d, 15:42Z) names the same single path. The dispatch log line: `MERGE BLOCKED 878dfe5a (uncommitted_changes): graphs/library/evidence/20260923_q002/verb_parity_biblio_neo4j; worktree .claude/worktrees/compressed-wiggling-hinton kept; issue d0180a19`. The Issue's description says the dispatcher resolves nothing (SEL-004 decision 3) and gives the by-hand recipe (resolve, gate, fast-forward, `cc complete`, remove, `lease reap`).

2. **What the path is.** In the primary, `graphs/library/evidence/20260923_q002/verb_parity_biblio_neo4j` is a directory with no entries (created 2026-09-23 by Q-002, `ls -la` size 64). git tracks 28 files under `20260923_q002/` and none under this directory: it is untracked because git does not track empty directories, and it is not ignored (`git check-ignore` returns nothing). In the worktree it is a symlink to the primary's directory, made at 21:53Z on 2026-11-05 by the session's link pass.

3. **Why the session linked it.** Library's built state (the index, texts, caches, evidence outputs) is gitignored and lives only in the primary; squiddy declares no `dispatch.worktree_links`, so the dispatcher links `.env` alone (`linked: [.env]`). SQ-114's session wrote a link script that symlinks every ignored library path from the primary into the worktree (171 links) so the release gate can run; SQ-114R's session re-ran it as SQ-114 left it. The script took an empty untracked directory for ignored state and linked it. git then sees a new untracked symlink in the worktree, and the merge gate reads any untracked path as `uncommitted_changes`.

4. **What it cost.** Both tasks halted at their own stop in Part A, so the block hid nothing green in A. But SQ-114R's Part B (`squiddy rate --pilot-only`, red first, committed `8416e9bf`, `part_complete` recorded) and the operator's allow-list ruling (`graphs/library/conformance.yaml`) passed the stop gate and did not land on main. SQ-114R2 (7f9d193e) starts by merging the kept branch at `2ba738c1` by hand. SQ-114's branch at `0da13f3c` was carried the same way, by SQ-114R's A.1. Two tasks, two hand merges, the same one-line cause.

5. **The dispatcher already has a field for this and it was empty.** The `dispatch_finished` record of a merged task carries `merge.linked_by_session: []` and `merge.discarded_ignored: [...]`. A session-made symlink into the primary is what `linked_by_session` is for, but the merge gate counted this one as a change before any such accounting ran.

## What the consumer wants to know back

Two questions, the second being squiddy's to act on once answered. (a) Whether a symlink in the worktree whose target is inside the primary checkout should count as `uncommitted_changes` at the merge gate, or as a session link (`linked_by_session`) the gate ignores and the sweep removes, however the link was made. (b) Whether `dispatch.worktree_links` is the route the seldon thread intends for a consumer whose entire built state is gitignored (library's 171 paths), as the 2026-11-04 filing also asked; if so, squiddy declares the list and its sessions stop writing link scripts, and the one path above never gets linked because it is not ignored.
