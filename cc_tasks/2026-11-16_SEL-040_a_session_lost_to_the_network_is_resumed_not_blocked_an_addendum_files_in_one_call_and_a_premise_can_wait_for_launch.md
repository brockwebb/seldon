# SEL-040: a session lost to the network is resumed by the dispatcher and not blocked for a person, an addendum files in one call, and a premise about a predecessor is checked at launch

**Status:** proposed
**Author:** Desktop session (seldon, SLD-2), 2026-11-16, from three findings and two observations reported by hazbrief thread hz-18 on 2026-11-16 and relayed by the operator. hazbrief did not file them (it held to "write nothing into other repositories"); this task's section "The condition" is the record of what it reported.
**Repo:** seldon (primary). hazbrief-mcp is read, never written; Part F files its return. L4: commit, merge, push in seldon.
**After:** none
**Governing:** AD-034 (the merge round, blocks and their reasons) and AD-034 ADDENDUM 02; AD-037-R6 (stop conditions by the dispatcher); AD-038: R1 (reconcile), R11 (candidacy headers), R20 (`cc file`: write, commit and register in one call), R24 (an addendum never carries Spend, Network, Framework layer or Exclusive); DISP-era `seldon dispatch redrive`; AD-033 (the decision register and its projection); RECALL-001 (the recall index). Number new rulings under AD-034 and AD-038.
**Model:** primary
**Spend:** est. 0.9M tokens. Basis: five narrow changes in code the dispatcher and filing path already have, each with a reproduction first; two short addenda; one return. Zero model calls.
**Network:** none
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes (edits `seldon/commands/dispatch.py`, `seldon/commands/dispatch_worktree.py`, `seldon/commands/cc.py`, the recall index code)
**Parts:** A 0.10, B 0.35, C 0.15, D 0.15, E 0.15, F 0.10.
**Premises:**
- premise: the dispatcher's worktree code is where the blocks are recorded | check: test -f seldon/commands/dispatch_worktree.py
- premise: hazbrief's log directory for the lost session exists | check: test -d /Users/brock/GitHub/hazbrief-mcp/logs/dispatch

## The condition (as hazbrief reported it, 2026-11-16)

1. **A session killed by a lost connection was blocked for a person.** The laptop lid closed during hazbrief HB-189; the session ended with "API Error ... ENOTFOUND" after ten retries. The dispatcher recorded `stop_gate_unpassed` and left the task blocked. Its worktree (`federated-sprouting-dream`) held 4 h 45 min of committed work. Desktop wrote a resume addendum and redrove it by hand. Evidence: hazbrief-mcp `logs/dispatch/2026-11-15_HB-189_*.log` (tail).
2. **`seldon_cc_file` cannot file an addendum.** It treats `<stem>_ADDENDUM_NN_*.md` as a new task and refuses it for missing Spend and Network headers, which R24 forbids an addendum to carry. Desktop wrote the file through the Filesystem tool and called `seldon_commit_governed` separately, the two-step sequence R20 exists to remove.
3. **A chained task cannot state a premise about its predecessor.** Premises are checked at filing; hazbrief HB-192 was refused for a premise that HB-189's RESULT exists, while HB-189 was still running.
4. **Observed:** hazbrief HB-187's `seldon verify` found 11 decision records (HBD-390, 429, 431, 434, 435 to 441) missing from the graph after HB-186 had reported them projected.
5. **Observed:** the recall index lists hazbrief Issue `0c4232cb` as `seldon:issue-0c4232cb`.

## Prior art (cite in the addenda)

- Kubernetes Job pod failure policy (KEP-3329, stable in 1.31; https://www.k8s.dev/resources/keps/3329/): a failed pod is classed before it is counted. An infrastructure disruption (`DisruptionTarget`) takes the action Ignore, restart without counting toward `backoffLimit`; a listed exit code takes FailJob; everything else counts. The KEP's stated problem is this task's item 1: a single retry counter "regardless of the root cause of the failures".
- The same split in batch schedulers (Slurm requeues a job on node failure and not on a non-zero exit); cite from seldon-biblio or the squiddy library if either holds it, otherwise name it as unfetched.
- Seldon's own: AD-038-R1 (system-written state is the dispatcher's to reconcile), `seldon dispatch redrive` (a kept worktree is resumable), SEL-034 (a terminal task stops its session).

Run `seldon prior-art search` for the internal receipts before the addenda.

## What to build

**A. Rulings.** An AD-034 addendum: the dispatcher classes how a session ended before it records a block. A session that ended without reaching its stop gate, and whose log tail or exit shows the transport failed (name the evidence used: the CLI's connection errors, a killed process with no RESULT, the host's wake time), is `interrupted`, never `stop_gate_unpassed`. An interrupted task is redriven in its kept worktree by a later pass once the API answers, at most twice per task, with the prior session's last commit and the fact of the interruption stated to the new session; a third interruption blocks with the reason `interrupted_thrice`. Tokens already spent count toward the task's cap. An AD-038 addendum for C and D.

**B. Resume.** Reproduce first from hazbrief's HB-189 log tail (a fixture cut from it, no secrets): show the current code records `stop_gate_unpassed`. Then the classification, the bounded redrive and its tests: an interrupted session resumes with no person; a session that ran to its gate and failed it is still blocked as now; a session that produced a RESULT is never redriven. Say what the dispatcher can and cannot tell apart (a closed lid, a dropped network, a killed process), with evidence, and what it does when it cannot tell.

**C. Addenda in one call.** `seldon cc file` (and the MCP tool) recognises a file whose stem is an existing task's stem plus `_ADDENDUM_NN`: it writes and commits it under the filing lock, registers nothing new, requires no candidacy headers, and still refuses the four headers R24 names. Test with a running task's addendum and with an addendum to a task that does not exist (refused).

**D. A premise that waits for launch.** Measure first: which premises does the dispatcher re-check at launch today, if any. Then: a premise line may carry `at: launch`; registration records it without evaluating it, and the dispatcher evaluates it with the others before the session starts (a false one blocks the task with the premise named, as now). A premise that only restates "the task this one is After has completed" is refused at filing with a pointer to the After header, which already carries that meaning.

**E. The two observations, measured before anything is changed.** (1) In a scratch copy of hazbrief-mcp, find why eleven register records were absent from the graph after a task reported them projected: projection run in a worktree and not replayed on main, a merge that numbered pending records after projecting, or something else. Fix the cause if it is seldon's; report it if it is not. (2) Find where the recall index takes an Issue's repository name from and why a hazbrief Issue was listed under seldon; fix and test.

**F. Return.** `seldon cc return --to hazbrief-mcp`, first line stating nothing in it is needed for the 2026-11-20 submission: what happens now when a session is cut off, that an addendum files in one call, the `at: launch` form, and what E found. Add one sentence correcting the reported belief: a consumer thread may file a report of what it experienced into seldon's `cc_tasks` (hazbrief did so on 2026-11-15, `bbfd478f`); that is the route, and it is not writing another project's work.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 1.1M.

## Deliverables

A to F with tests; the two addenda and their rulings; the return; `cc_tasks/2026-11-16_SEL-040_a_session_lost_to_the_network_is_resumed_not_blocked_an_addendum_files_in_one_call_and_a_premise_can_wait_for_launch_RESULT.md`.
