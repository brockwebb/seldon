# FRICTION-001: AD-038 in Seldon. The dispatcher reconciles machine state before c7; blocked tasks redrive; the MCP server runs HEAD; stations inspect the session's tree; registration runs premises

**Repo:** seldon. L4: commit, merge, push. Work on a branch in a worktree; merge before each `part-complete` (the station checks main until Part D lands).
**Date:** 2026-10-17. **Authored by:** a Desktop session in squiddy (SQ8).
**Implements:** `docs/design/AD-038_the_machine_reconciles_its_own_state.md` (R1 to R6; prior-art verdict PASS, event f89ca2f1; register seq 286 to 291). There is no Step 0.
**Resolves:** Issues `02d52bc4`, `70bf1a21`, `c5e0f12c`, `59b2db84`, and seldon task fb3b11bc's descendants on c7 reporting.
**After:** 3bb19003
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Model:** primary
**Spend:** est. 1.5M tokens. Basis: DESK-001 (1.2M est., 0.44M actual) touched two of these five areas; this touches five plus a new command.
**Parts:** A 0.30, B 0.15, C 0.20, D 0.20, E 0.15.
**Network:** none beyond git push.
**Exclusive:** yes
**Premises:**
- premise: DESK-002R merged its Part A | check: `test -f tests/test_desk002_ruling_commits_with_record.py`
- premise: the station module exists | check: `test -f seldon/core/stations.py`

Glob and read every sibling `*FRICTION-001*ADDENDUM*.md`.

## Stop condition (AD-037-R6, by the dispatcher)

Token ceiling 1.8M. A Part whose full suite fails on the branch is not merged; record and stop.

## Part A: R1, reconcile before c7

1. In `_pass`, before `tree_state` is read for c7 and while holding the lease: commit every dirty path in the governed classes (event store, `docs/decisions/register/*`, `docs/decisions/REGISTER.md`, prior-art query log and verdict ledger, cadence, registered task files and their addenda). Path-scoped, hooks on, one commit per class with a message naming the class and the writers found.
2. Remove `COMMITTABLE_ACTORS`. Keep the append-only check for ledgers; a non-append-only change is reported and left for c7.
3. c7's refusal names the paths it could not reconcile and why.
4. Tests, each failing on HEAD: a `governed_sync` line in the store is committed and the task launches; a `cc` line likewise; a dirty source file still refuses and is named; a non-append-only store change refuses and is named.

Acceptance:
- `check: pytest tests/test_friction001_reconcile.py -q`

## Part B: R2, redrive

1. `research.yaml`: add `blocked -> accepted`.
2. `seldon dispatch redrive <task>` and MCP `seldon_dispatch_redrive`: clear `claimed_by`, write `dispatch_redrive` naming the answered stop, move to `accepted`.
3. Automatic redrive in `_pass` for stops whose reason is `check_unrunnable_wrong_tree` or `database_unavailable` (Part D and E write these).
4. Tests: a blocked task redriven is a candidate on the next pass; redrive refuses a task that is not blocked; the record names the stop.

Acceptance:
- `check: pytest tests/test_friction001_redrive.py -q`

## Part C: R3, the MCP server runs HEAD

1. Every mutating tool in `mcp_server.py` runs `sys.executable -m seldon <command>` in the repository and relays stdout; the stale guard applies to read-only tools only and never returns the restart message for mutating ones.
2. Tests: after a commit under `seldon/` in a temp repo, a mutating tool succeeds and a read-only tool reports stale without asking for a restart.

Acceptance:
- `check: pytest tests/test_friction001_mcp_head.py -q`

## Part D: R4, stations inspect the session's tree

1. `part_complete` and `first_article` carry `cwd` and `branch`; the stations run checks there.
2. A check naming a missing file is `unrunnable` (huddle), with reason `check_unrunnable_wrong_tree` when the file exists on the session's branch but not in cwd.
3. Tests: the DESK-002 case passes; a genuinely failing test still stops the line.

Acceptance:
- `check: pytest tests/test_friction001_stations_tree.py -q`

## Part E: R5 and R6

1. Registration runs `check:` premises; a false one refuses with the output.
2. A Neo4j `DatabaseUnavailable` in `_pass` becomes a handled refusal with one STUCK notification per outage, not a traceback (59b2db84).
3. `seldon qc chart` reports per week: passes refused on machine dirt, operator interventions (count `dispatch_redrive` by a non-dispatcher actor, Desktop restarts inferred from `server_stale` refusals, superseded-never-launched tasks).
4. Tests for each.

Acceptance:
- `check: pytest tests/test_friction001_registration_premises.py -q`

## Report

RESULT under 30 lines: tokens per Part against 1.5M; each test's failure on HEAD; full-suite counts per merge; the first `qc chart` toil reading; premises found wrong. Then `seldon verify`, `seldon cc complete`, resolve the four Issues, merge, push.
