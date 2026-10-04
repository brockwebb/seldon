# SEL-002 Part E: checkpoint plan (constitution sections 11 and 15), written before the first paid call

**Loop.** Two passes over the 585 active, non-mirror records of DB-1 after Part C
(`evidence/sel002/statements/units.jsonl`, `scripts/sel002/statements_export.py`): a writer call per record, then a
validator call per record that has a statement. Harness: `scripts/sel002/statements.py`, run in Squiddy's
environment; numbers in `scripts/sel002/statements.yaml`.

| Property | How |
|---|---|
| Unit of work | One model call: `sel002_writer` for a record, `sel002_validator` for a (record, statement) pair. |
| Checkpoint file | `evidence/sel002/statements/writer.jsonl`, `validator.jsonl`: Squiddy's `calls.Checkpoint`, one row per finished call, flushed and fsynced before the next lands; a torn last line is truncated on open. |
| Unit key | `calls.unit_key`: node, record id, sha256 of the source (writer) or of source plus statement (validator), sha256 of the model-relevant config, role, sha256 of the prompt template, model alias, transport profile. A changed prompt, model or transport is a new key; nothing stale is reused. |
| Resume rule | Re-running the same command skips completed keys (`calls.run_units`). A failed call is a row with its error, retried once across runs (`retry_attempts: 2`); an unparseable reply is asked again once inside the unit. |
| Progress | The call layer's line every 60 s or 10 units: done/total, rate, ETA, failures; to stdout and the run log. |
| Pilot | The first 10 records (writer, then validator), under `spend.declare_or_pilot` (no measured basis yet: its estimate is a guess, labelled one). The pilot's ledger rows become the measured basis. |
| Estimate | For the rest: `spend.estimate` over the ledger history of each node (same model alias and transport profile), every call priced cold (independent prompts). Reported with the pilot's actual and the ratio. |
| Ceilings | Each pass is a DN-042 job: its estimate, `token_cap` 1.25x the estimate, `call_cap` units x 2; the governor warns past +10% and refuses the reservation that would pass +20% (spend touchpoint, the operator's dated approval file). Before the bulk starts, the pilot actual plus both measured estimates is checked against the declared budget (3M weighted tokens, SEL-002's notional) plus its +20% band: past that line the run does not start and the report says so. STOP: `Stopped` from the call layer lands every call in flight first. |
| Failures | Rows, never crashes (`calls.run_units`); a governor refusal or a quota is a stop at touchpoint 1, not a row. |
| Partial results | `statements.py report` runs over whatever the checkpoints hold and states its n. A record with no passing verdict keeps its verbatim statement with `statement_check: failed` (AD-033-R8). |
| SIGKILL test | `scripts/sel002/statements_kill_test.py` (offline mock): kill mid-loop, restart, rows equal to an uninterrupted run, no completed call repeated. Result: `evidence/sel002/statements_kill_test.txt` (PASS, before any paid call). |

Statements land as `amend` records on the `statement` field (with `statement_check`), written in Seldon's environment
by `scripts/sel002/statements_apply.py` through the register's one write path; records are never edited.
