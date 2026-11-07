# ADDENDUM 01 to squiddy's lease filing of 2026-11-06: an 81-minute episode the same afternoon, in which the lease delivered an ordering the waiting task needed and had not declared

**Repo:** seldon. **Date:** 2026-11-06. **Authored by:** the same Desktop session in squiddy (SQ-13). Adds one measurement to the filing; proposes no fix.
**Evidence:** squiddy `seldon_events.jsonl`: `registration_retried` 673d2f02 at 14:47:16Z, `dispatch_refused` 673d2f02 at 14:51:32Z with payload `held: {seldon: {holder: dispatcher:HexagonMBP.local:63675, task: 0d115437-25c2-4b9c-8c09-63674315038f, acquired_at: 2026-11-06T14:23:18Z}}`, `dispatch_launched` 673d2f02 at 16:12:48Z; squiddy `logs/squiddy_dispatch.log` lines 19110 to 19205 (16 `refused: environment_in_flight` fires, the first at 14:51:29Z, the launch on the 16:12:41Z fire); squiddy `cc_tasks/2026-11-06_SQ-124_..._ADDENDUM_01_branch_line_discard_and_the_premise_retry.md` and SQ-124's header and RESULT; no `wait_on` event for 673d2f02 in squiddy's ledger.

## The episode

| waiting | holder | from the log | refused passes | minutes |
|---|---|---|--:|--:|
| squiddy SQ-124 (673d2f02) | seldon SEL-024 (0d115437) | 2026-11-06 14:51:29Z to the launch at 16:12:48Z | 16 | 81.3 |

Measured so far: 533.1 minutes in REV-001's window, under 6 on 2026-11-05, and 81.3 in this episode.

## What this episode adds to the question

SQ-124 is SEL-024's own squiddy half, filed by `seldon cc file`. Its ADDENDUM 01 asks that SEL-024 be confirmed merged before it runs, and its registration premise was weakened to `test -d ../seldon/seldon/core` because `seldon/core/gate_record.py` did not exist yet (`stale_evidence ... absent at registration`). No `seldon task wait-on seldon:0d115437` was recorded. So the premise did not hold the task back, and nothing declared the order; the lease did. Under the filing's snapshot reading alone, SQ-124 would have launched at 14:51Z against a seldon without `gate_record.py` and stopped at its ADDENDUM's check, or worse.

The consumer reads this as a second duty the lease performs today: besides keeping a reader from seeing a write mid-run, it orders a consumer task behind the seldon task it depends on whenever that dependency was not declared. If the seldon thread narrows the lease, that ordering has to come from somewhere the consumer can see, such as c17's `wait_on`, which exists, or a premise check that cannot pass early. This cuts against a reading of the filing as "the lease is pure cost". It is not, in this episode; it was 81 minutes of the right order delivered by the wrong mechanism.
