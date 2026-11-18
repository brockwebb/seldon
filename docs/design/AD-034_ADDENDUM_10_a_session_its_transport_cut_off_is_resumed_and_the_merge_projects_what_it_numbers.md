# AD-034 ADDENDUM 10: a session its transport cut off is resumed in its kept worktree, and the merge projects the register records it numbers

**Date:** 2026-11-17. **Status:** Accepted. Implemented by SEL-040 Parts A, B and E
(`cc_tasks/2026-11-16_SEL-040_a_session_lost_to_the_network_is_resumed_not_blocked_an_addendum_files_in_one_call_and_a_premise_can_wait_for_launch.md`),
from what hazbrief thread hz-18 reported on 2026-11-16. **Amends:** AD-034's finish (decision 4: a session that did
not merge is blocked) for one class of ending. **Extends:** AD-038-R2 (the dispatcher redrives the stops it caused)
to a stop the transport caused; LOOP-001's numbering at merge (AD-033 ADDENDUM 01) with the projection it lacked.
Four new rulings, AD-034-R21 to R24.
**Code:** `seldon/core/interruption.py` (the classification, the probe, the resume plan and clause);
`seldon/commands/dispatch_worktree.py` (`finish_session`, `interruption_reading`, `resume_for`,
`number_merged_register`, `_project_register`); `seldon/commands/dispatch.py` (`_launch_inplace`, `_launch_cmd`,
`_auto_redrive`); `seldon/core/redrive.py` (`interrupted` and its probe); `seldon/core/stations.py`
(`launch_tokens`).
**Tests:** `tests/test_sel040_interrupted_session_resumed.py`; `tests/test_loop001_register_seq.py`
(`test_the_records_a_merge_numbers_are_projected_into_the_graph`).

## 1. Evidence

1. **HB-189 was blocked for a person by a closed lid.** hazbrief HB-189 ran from 05:55Z on 2026-11-16 and committed
   its work on branch `worktree-federated-sprouting-dream`. Its last model record is at 10:36:44Z; the host's power log
   reads "Entering Sleep state due to 'Clamshell Sleep'" at 10:37:00Z. In the dark-wake windows after, the CLI wrote
   ten `api_retry` records (attempt 10 of `max_retries` 10, `error_status` null) and ended on its own synthetic message
   "API Error: Can't reach the API server ... (ENOTFOUND)", exit 1. The session never reached its Stop hook, so the
   finish read "Parts declared and no stop gate ran" and recorded `stop_gate_unpassed`; no automatic redrive answers
   that. Desktop wrote a resume addendum and redrove the task by hand, and the redriven session started in a new tree.
2. **Reproduced here first.** The tail of HB-189's log, cut with its content elided
   (`tests/fixtures/sel040/hb189_log_tail.jsonl`, `docs/evidence/sel040/cut_fixture.py`), printed by the stub CLI after
   a committed piece of work, gave `assert 'stop_gate_unpassed' == 'interrupted'` on the code before this addendum
   (`docs/evidence/sel040/reproduction.txt`).
3. **HB-186's eleven records reached the graph only by hand.** HB-186 accepted seven rulings and four amendments in its
   worktree, as pending records; its merge numbered them (seq 514 to 524) and committed the register; nothing projected
   them until HB-187's `seldon decision project` the next morning. HB-187 read the gap as the graph having "lost" them;
   it never held them (`docs/evidence/sel040/part_e_findings.md`).

## 2. Prior art

### External

- **Kubernetes Job pod failure policy** (KEP-3329, stable in Kubernetes 1.31; https://www.k8s.dev/resources/keps/3329/).
  A failed pod is classed before it is counted: a pod with the `DisruptionTarget` condition (the node was drained,
  preempted or lost) takes the action `Ignore` and is restarted without counting toward `backoffLimit`; a listed exit
  code takes `FailJob`; everything else counts. The KEP's stated motivation is a single retry counter applied
  "regardless of the root cause of the failures". Adopted: the finish classes a transport failure before it blocks,
  the class is redriven without a person, and the retries are bounded by their own count. Cited by its published
  name; not fetched (this task's Network header is none).
- **Batch schedulers' requeue on node failure.** Slurm requeues a job whose node failed and does not requeue one that
  exited non-zero; the same split as the KEP. Named, not fetched. Whether seldon-biblio or the squiddy library holds
  it is unchecked: the library arm's search (`seldon prior-art search --library`) did not return within two minutes
  from this worktree and was stopped.
- **The CLI's own documented worktree reuse** (code.claude.com/docs/en/worktrees, "Reuse a worktree name"): "If a
  worktree with the name you pass to `--worktree` already exists, Claude Code opens it instead of creating a new one",
  and with `worktree.baseRef: "head"` it "reopens the worktree at its old tip". Adopted as the resume's mechanism.

### Internal

- internal receipt: query "redrive" | repo seldon@040dbc0743ac835c7a239a27e6cad2f75332ba5b | hits docs/design/AD-038_the_machine_reconciles_its_own_state.md:32, docs/design/AD-038_ADDENDUM_02_waits_on_across_graphs_and_a_stored_block_reason.md:76, docs/decisions/register/00287_seldon-ad-038-r2_accept.yaml:1
- internal receipt: query "kept worktree" | repo seldon@040dbc0743ac835c7a239a27e6cad2f75332ba5b | hits docs/design/AD-034_ADDENDUM_02_breaker_does_not_veto_green.md:24, docs/design/AD-038_ADDENDUM_11_a_kept_worktrees_events_reach_mains_log_or_are_discarded_on_record.md:1, docs/design/AD-038_ADDENDUM_11_a_kept_worktrees_events_reach_mains_log_or_are_discarded_on_record.md:3
- internal receipt: query "decision project" | repo seldon@040dbc0743ac835c7a239a27e6cad2f75332ba5b | hits docs/design/seldon_architectural_decisions.md:156, docs/seldon_architectural_decisions_updated.md:156, docs/decisions/REGISTER.md:1

What the internal record already held: AD-038-R2's redrive (a blocked task goes back to `accepted` with its file, id and
history), `seldon dispatch redrive` for a kept worktree, AD-038-R25 (a kept tree's events reach main's log, and a
later merge of the same branch drops its copies), AD-034 ADDENDUM 02's stale-tree sweep (which removes only a tree
whose branch holds nothing beyond main), and SEL-034 (a terminal task stops its session). This addendum adds the class,
the probe, the bound and the reopening; it reuses each of those unchanged.

## 3. Rulings

- **AD-034-R21. Before a block is recorded, the finish classes how the session ended, and a session its transport cut off is `interrupted`, never `stop_gate_unpassed`.**
  The evidence, recorded on the finish as `interruption`: the CLI's own synthetic "API Error" naming a connection
  failure (`dispatch.interruption.transport_patterns`), or its `api_retry` records reaching `max_retries` after the
  last model turn with no client-error status; and, as corroboration, a Sleep in the host's power log
  (`dispatch.interruption.host_sleep_command`) between the last model turn and the end. A killed process with no
  `result` record and no dispatcher stop is `interrupted` only with that Sleep beside it; alone it is ambiguous (an
  operating-system, out-of-memory and operator kill look alike) and is blocked for a person as before, with the
  ambiguity named. Never `interrupted`: a session whose RESULT is committed (the regate answers it, AD-034-R10), a task
  the graph shows terminal, a session a station or the dispatcher stopped, and a session its Stop gate let go
  (`no_progress`, `ceiling`).
- **AD-034-R22. An interrupted task is redriven at most twice; a third interruption blocks it with the reason `interrupted_thrice`, and every interrupted session's tokens count toward the task's ceiling.**
  The count is the task's `interrupted` and `interrupted_thrice` finishes. The tokens a resumed launch carries
  (`dispatch_launched.resume.prior_tokens`) are added wherever the station reads the launch's tokens: the Stop gate's
  ceiling, the dispatcher's hard stop and `part-complete`.
- **AD-034-R23. The dispatcher redrives an interrupted task itself, once the API's host answers a probe, and relaunches it in its kept worktree with the prior session's last commit and the fact of the interruption stated to the new session.**
  The probe is a TCP connect to `dispatch.interruption.probe_host` (no model call); each change in its answer is
  recorded (`interruption_probe`). The relaunch names the kept tree to the CLI (`--worktree <name>`), keeps the
  first launch's `base`, and appends the resume clause to the prompt: when, on what evidence, which resume of two, the
  branch, its last commit and subject, and the tokens already spent. A kept tree the stale sweep removed (its branch
  held nothing) gives a fresh launch.
- **AD-034-R24. The merge step projects the register records it numbers, under the same lease, so the graph holds what main's register holds the moment main holds it.**
  `register_numbered.projected` records what the projection did, or its error; a failed projection is printed and
  left for `seldon decision project`, and never undoes the merge.

## 4. What the dispatcher can and cannot tell apart

A closed lid and a dropped network both reach the CLI as a transport failure, and both are resumed: the host log, when
it can be read, says which it was. A process killed from outside is the case it cannot class from the stream alone,
and it does not guess: it blocks as before and says why. A server-side failure the CLI reports with an HTTP status (a
5xx, 429 or 408) after its retries is counted as the API not answering; a 4xx refusal (authentication, a bad request)
is not, because the API answered.

## 5. What this does not change

`stop_gate_unpassed`, `session_failed` and every other outcome are recorded as before; a finish that reads no
transport evidence carries no `interruption` field, so an ordinary failure's record is unchanged (the serial
transcript fixture still reproduces). The regate of kept work with a committed RESULT (AD-034-R10) is untouched. The
parallel pass (`max_parallel > 1`) runs no automatic redrive today, as before this addendum; both projects that
dispatch run serially.
