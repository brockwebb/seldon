# RESULT: SEL-010R2, the dispatcher waits for the Desktop OODA between chained tasks, and a project adopts it in one step

**Task:** `09e3b92c`, `cc_tasks/2026-10-26_SEL-010R2_dispatch_waits_for_the_desktop_ooda_between_chained_tasks.md`.
The statement of record, `cc_tasks/2026-10-25_SEL-010_dispatch_waits_for_the_desktop_ooda_between_chained_tasks.md`,
is untouched.
**Date:** 2026-10-26. **Branch:** `worktree-glittery-churning-steele`. Commits `8f5e81b` (Parts A, B) and `d3e5ea0`
(Part C, the MCP surface, the addendum and the register records).
**Rulings:** AD-038-R10 and AD-038-R11, in `docs/design/AD-038_ADDENDUM_03_the_ooda_between_chained_tasks_and_adoption.md`.
Each is accepted with `--decided-by cc:09e3b92c`. The records are pending under `docs/decisions/register/pending/`
(00001, 00002), and the merge step numbers them on main (AD-033 ADDENDUM 01).
**Spend:** 257,798 tokens at Part C's boundary (`part_complete`), against an estimate of 0.4M. Zero model calls.
Network: none (no push; the dispatcher merges).

Recall used: seldon:AD-038-R9

(AD-038-R9 / c17 is the shape c18 copies. The ledger is read once per pass, the criterion is absent unless it applies,
and an unreadable input fails closed. SEL-005's plist and wrapper, the artifacts rather than its RESULT, are the shape
`dispatch adopt` writes.)

## Part A: c18, the OODA gate between `precedes` edges (AD-038-R10)

- **The criterion.** Suppose task N+1 has a `precedes` predecessor N that is `completed` or `verified`. N+1 is then
  eligible only when one of three things holds:
  - an `ooda_recorded` event names N;
  - `<N's stem>_OODA.md` is committed beside N's task file;
  - `dispatch.ooda_grace_s` seconds have passed since N's last move into `completed`.

  The completion time comes from the ledger, or else from the graph's `updated_at`, which is an upper bound. With
  neither, the task holds until a record exists (fail closed).
- **Defaults.** The grace defaults to `0`, which never waits, and c18 is then absent. With a grace above 0, c18 is
  present on every task it applies to. `dispatch_launched` therefore records `released_by` (`ooda_event` /
  `ooda_file` / `grace`), the completion time with its source, and the seconds elapsed. Superseded, withdrawn and
  rejected predecessors left no RESULT, so they hold nothing.
- **Refusal.** The reason is `ooda_pending`. The pass log's detail line names the predecessor, the grace left and
  the release line. A streak of `ooda_pending` raises `dispatch_stuck` like any other refusal, and that alarm is the
  operator's signal that an OODA is due.
- **Code.** `seldon/core/dispatch.py` (`ooda_waits`, `ooda_index`, `ooda_file`, `ooda_pending`, `ooda_record_event`,
  `evaluate`, `first_refusal_reason`) is wired into all four evaluation sites: `_survey`, `_pass`, and the parallel
  survey and pass.
- **Record surfaces.** CLI: `seldon dispatch ooda pending [--json]` and `seldon dispatch ooda record <N> [--note]`.
  MCP: `seldon_ooda_pending` and `seldon_ooda_record`, for a Desktop thread, which has no shell.
- **The reconciler.** It commits an untracked `_OODA.md` beside a registered task the way it commits an addendum, so
  a Desktop that writes the file does not have to commit it (AD-038-R1).
- **Fixture tests.** Each fixture fails exactly c18 or passes it. Covered: grace 0 is absent; held; the event
  releases; the file releases only once committed; the grace releases; superseded and withdrawn predecessors hold
  nothing; verified holds; `updated_at` bounds the grace; an unknown completion time fails closed; the last
  completion counts; bad grace values refuse at load; the refusal line; the reconciler. Graph-backed tests cover
  the CLI and the MCP tools.

## Part B: per-project candidacy headers and `seldon dispatch adopt` (AD-038-R11)

- **The list.** `dispatch.candidacy_headers` must include `Spend` and `Network` (`MINIMUM_HEADERS`) and may add any
  header. When the key is absent, it is the old three, so no project's candidates change. `REQUIRED_HEADERS` is kept
  byte for byte, which matters because SEL-011's premise greps that exact line.
- **`seldon dispatch adopt --project <dir> [--yes] [--dry-run] [...]`.** It adds only the keys the project lacks, and
  never rewrites one the project has. It copies the machine-wide values from the kit's block, meaning the primary
  checkout's `seldon.yaml`: from a worktree, the kit's relative `../squiddy` reference must resolve from the primary.
  It asks for the band reference (default: the kit's, re-rooted), the branch and the launchd label. It writes
  `enabled: false`, the minimum headers, `ooda_grace_s: 0`, the wrapper's `jobs.dispatch` caps, any missing ignore
  lines, and `scripts/jobs/<label>.plist`. The plist runs the kit's wrapper with the project and the plist as
  arguments; `seldon_dispatch.sh` takes both, and with no arguments behaves as before. Edits are made as text, so
  every comment survives, and are validated with `load_dispatch_config` plus the band's resolution before anything
  is written.
- **The adoption check against hazbrief, read only.** `seldon dispatch adopt --project ../hazbrief-mcp --yes
  --dry-run` exited 0 and wrote nothing:
  - It proposed 16 `dispatch:` keys and 3 `jobs.dispatch` keys.
  - The band reference was `../squiddy/squiddy/spend.yaml#job_token_cap_default`, and it resolved.
  - The label was `com.brock.hazbrief-mcp-dispatch`, with the plist at `hazbrief-mcp/scripts/jobs/com.brock.hazbrief-mcp-dispatch.plist`.
  - No ignore lines: hazbrief already ignores `.seldon/` and `logs/`, and `.git/info/exclude` covers `**/.claude/worktrees/`.
- **The registrar.** Both readers use the base file only, and that is now stated: `candidacy`'s docstring, R11, and
  the `parts_undeclared` refusal, which adds "an addendum cannot supply it, so a committed file that lacks it is
  re-filed as a new task file".

## Part C: the Desktop wake-up recipe

`docs/conventions/desktop_ooda.md` covers:

- how to turn the grace on, and why to schedule the reader first;
- the three readers: a Claude Code `/loop 30m ...` session in the primary checkout (the line to paste is in the
  file), a Desktop thread through `seldon_ooda_pending`, and the operator;
- the order to write in: an addendum for N+1, or a block or supersession of it, first, and the record last, because
  the record releases N+1;
- the record's shape.

`docs/design/2026-09-15_standing_dispatcher.md` now points at c18 and at `adopt`.

## The finding recorded before launch, and its corrections

1. **An addendum cannot repair a committed task file's headers.** SEL-010's ADDENDUM-00 (`9f4caa6`) carried every
   header, and registration still refused it with `parts_undeclared`. The registrar, the dispatcher's `candidacy`,
   the stations' Parts and Premises, and the Stop gate all read the base file. **Decided: they keep reading the base
   file only** (AD-038-R11). A candidacy read across several files would need a precedence rule (which addendum
   wins, and does a later one un-declare?) that all four readers would have to share. One file, one declaration,
   keeps registration and dispatch in agreement. The repair is a new file (`<id>R`), as SEL-010R2 is. The refusal
   now says so.
2. **TRIAGE-001's advice is wrong on the current code.** `cc_tasks/2026-10-15_TRIAGE-001_open_proposals_closed_as_history_RESULT.md:29`
   says `e60b17fe` "needs those headers and `**Parts:**` added in an addendum before it can launch". It cannot be
   fixed that way: an addendum supplies neither. `e60b17fe` launches only if it is re-filed as a new task file whose
   base carries `**Spend:**`, `**Network:**`, `**Framework layer served:**` (in seldon, which keeps the three) and
   `**Parts:**`. This RESULT is the correction of record. TRIAGE-001's RESULT is history and is not edited.
3. **The first observation (SEL-010 ADDENDUM-00).** SEL-010 was refused by the very header its item 2 proposed to
   make per-project (`Framework layer served`). Under R11, a project that adopts with `dispatch adopt` no longer
   inherits that header. seldon, squiddy and ai-readiness-kg keep it until they change their own key.

## Tests

- `tests/test_sel010r2_ooda_gate_and_adopt.py`: 33 tests (26 functions, some parametrized), all passing. Two use Neo4j: the CLI `ooda pending|record`,
  and the MCP tools.
- **Full suite**, run on `8f5e81b` (Parts A and B):

  ```
  python -m dotenv -f .env run -- python -m pytest tests/
  ```

  with `PYTHONPATH=<worktree>`. Result: 2903 passed, 7 skipped, 1 failed, in 37 min 38 s.
  - **The failure** is `tests/test_pa002_release_resolve.py::test_rebuilding_the_served_release_reproduces_the_served_index`
    (`release_unavailable`: squiddy's library `index:` block differs from the release's). It also fails on main
    (squiddy library index drift, Issue dbe38fac). This task touches no prior-art code.
  - **The skips:** six are `test_parts_gate_in_projects.py`, because squiddy, ai-readiness-kg and arnold are not
    checked out beside a worktree; one is the live-CLI probe.
- **After `d3e5ea0`** (the MCP tools, plus moving the pending rows into core), the affected files were re-run, not
  the whole suite. My file with `test_friction001_mcp_head.py`: 37 passed. `test_mcp001_fresh_process.py`,
  `test_mcp_tools.py`, `test_mcp_cc_git_guard.py`, `test_dispatch.py`, `test_dispatch_serial_transcript.py`,
  SEL-008's file and `test_friction001_reconcile.py`: 159 passed. The dispatcher's merge gate runs the full suite.
- **The serial transcript** (`tests/test_dispatch_serial_transcript.py`) is unchanged: its tasks have no
  predecessors, and its project has no grace.

## Decided on the grounding, for override

- **seldon's own `ooda_grace_s` stays 0.** A grace with no reader scheduled delays every chain by the grace and buys
  nothing. Turning it on is two steps, in this order, in the seldon repository:
  1. In a Claude Code window in `/Users/brock/GitHub/seldon` (the primary checkout), paste:

     ```
     /loop 30m Run `seldon dispatch ooda pending`. If it prints "ooda: nothing pending", stop. Otherwise, for each predecessor it lists, follow docs/conventions/desktop_ooda.md section 3 in the seldon repository: read the RESULT, write any addendum for the successor first, then the _OODA.md record last.
     ```

  2. In `seldon.yaml`, under `dispatch:`, add `ooda_grace_s: 3600` and commit it.
- **c18 does not hold on cross-project waits (c17).** Holding there would need a record in the other project's ledger,
  and AD-038-R8 forbids writing it.
- **The grace pairing has no measured basis.** "At least twice the wake-up interval" is a starting value. The
  `released_by` counts on `dispatch_launched` are the measure: every `grace` release is a task launched without
  anyone reading its predecessor's RESULT.

## Open and not done

- **SEL-011 overlaps this work.** It factors the static candidacy checks into one function shared by registration
  and dispatch. It should call `candidacy(task_file, cfg["candidacy_headers"])`, so that registration refuses
  against the project's list. Its premise line `REQUIRED_HEADERS = (HEADER_SPEND, HEADER_NETWORK, HEADER_LAYER)` is
  still true.
- **Pre-existing:** the wrapper still names `/opt/anaconda3` for python and seldon. `adopt` does not change that, so
  every adopted project runs the same interpreter seldon's job does.
- **hazbrief is not adopted.** It was read, never written. When the operator chooses, in a shell:
  1. `cd /Users/brock/GitHub/hazbrief-mcp && seldon dispatch adopt`, then follow the four numbered lines it prints:
     commit, `seldon hooks install`, `ln -s` + `launchctl bootstrap`, and `enabled: true` when ready.
