# RESULT: SEL-058, three open filings from hazbrief and factory are answered

**Task:** `cc_tasks/2026-11-27_SEL-058_three_open_filings_from_hazbrief_and_factory_are_answered.md` (`987aff52`).
**Branch:** `worktree-cryptic-stargazing-lampson`. Not merged or completed here; the dispatcher merges on green.
**Addenda:** none existed (`*SEL-058*ADDENDUM*.md` matched nothing).
**Decisions:** AD-037 ADDENDUM 06 (R22, R23), AD-034 ADDENDUM 14 (R41), AD-033 ADDENDUM 03 (R15, R16); five pending
register records; `seldon prior-art verify` exit 0 on each note, recorded before the code commit. `seldon decision
check`: clean.
**Commits:** `9562d37` red tests; `27d0dff` notes and records; `db0fd13` code; `2bed7be` the Hive block.

Recall used: seldon:2026-11-21_SEL-042_a_stopped_session_is_never_merged_or_completed_the_merge_round_cannot_refuse_itself_and_verify_reads_pending_records_RESULT, seldon:2026-11-27_SEL-055_the_gate_runs_what_a_change_can_break_and_no_queue_waits_an_hour_for_a_one_line_change_RESULT, seldon:2026-11-27_SEL-054_four_things_the_factory_needs_from_the_dispatcher_are_built_RESULT

The SEL-042 RESULT is where hazbrief got the check-line form ("give each Part a `check:` line"). The SEL-055 RESULT
says which items of `1e367024` it left open. The SEL-054 RESULT says what `dispatch.hive` does and how the controls
try it. Nothing below repeats their work. SEL-057's RESULT was read too. It touches none of these filings.

## Part A: the two hazbrief filings

Red first: `9562d37` added `tests/test_sel058_hazbrief_filings.py`. Against HEAD `a5616f4` all 12 failed. The 13th
test was written during the work and was red before its fix (`KeyError: 'dispatcher:environment_in_flight'`).

### Filing `1e367024` (2026-11-24): a bare check line, a blocked merge completed ungated, a lease wait

1. **A Part's bare `check:` line was not read. It still held at HEAD.** `stations.part_criteria` read only criteria
   under an Acceptance label. HB-221's `check: uv run pytest ...` directly under `## Part A:` read as `[]`.
   - **Fix (AD-037-R22).** Both forms are read, each command once and in order: the Acceptance items, and a `check:`
     or `judgment:` line standing on its own at the start of a line in the Part, outside a fenced block.
   - The Stop gate, the finish's `checks_run` and the regate (`dispatch_worktree.task_checks`) all read through
     `part_criteria`, so one change covers all three.
   - Tests: `test_a_parts_bare_check_line_is_read_as_its_check`,
     `test_bare_and_acceptance_checks_are_read_once_each_and_a_bare_judgment_too`,
     `test_the_regate_runs_a_bare_check_line_too`.
2. **`cc complete` completed a blocked task with no gate evidence. It still held at HEAD.**
   - **Fix (AD-034-R41).** A `blocked` task completes only on a passing, clean `gate_run` of the tree the dispatch
     branch holds at that moment. The record's id is stored on the task as `completion_gate`.
   - Otherwise the command refuses as `blocked_ungated`, writes nothing, and names `seldon gate main` as the remedy.
   - The operator's `--ungated "<reason>"` completes the task anyway and records the reason as `completed_ungated`.
   - Tests: `test_completion_evidence_is_a_passing_clean_gate_of_the_branch_tip`,
     `test_cc_complete_refuses_a_blocked_task_with_no_gate_on_main_then_completes_on_one`,
     `test_cc_complete_of_a_blocked_task_is_overridden_only_with_a_recorded_reason`.
3. **The lease wait. SEL-043 fixed part of it; the rest still held.**
   - **What SEL-043 fixed** (`a8452ca`, merged 2026-11-25, AD-037-R17 to R19). The 2026-11-24 wait was in SEL-045's
     session phase, and a consumer no longer waits there. Every refusal now names the holder, task, phase and gate
     progress.
   - **What still held.** Nothing rang. hazbrief's store has one `dispatch_refused` `environment_in_flight` at
     15:34:02Z and no `dispatch_stuck`, because station (a) runs after the task streak and was never counted.
   - **Fix (AD-037-R23).** A wait is a standing streak, `dispatcher:environment_in_flight`, one streak per holding
     window. It rings `dispatch_stuck` and `notify` once after 12 reviewed passes: one hour at a 300 s poll, past
     seldon's 2,408 s full gate. A project can set its own count under
     `dispatch.stuck_after_passes_by_criterion.environment_in_flight`.
   - **A second defect found while building it.** `_stuck` rewrote the streak file from task refusals alone, so every
     `dispatcher:` streak counted after it restarted at one on each pass. That included SEL-054's
     `project_premise_false` and `limit_control_failed`. The task streak now keeps them.
   - Tests: `test_a_lease_wait_rings_once_at_its_threshold_and_clears`,
     `test_the_task_streak_pass_keeps_the_standing_streaks`.
4. **The governing-note hold: not a defect.** The alarm fired. hazbrief's store has `dispatch_stuck`
   `governing_unverified` for HB-225 at 2026-11-24T08:04:15Z, after three passes, with a `STUCK:` line in its log. So
   `notify` ran once. Nobody saw it, which is about how hazbrief's notifier delivers. Nothing changed here.

### Filing of 2026-11-27: the register from a worktree, import projection, the stale binding

1. **A worktree read no imported register. It still held at HEAD.** The test's resolved path was
   `hazbrief/.claude/worktrees/seldon`.
   - **Fix.** `decisions.settings` now resolves `repositories`, `import` paths and the side-by-side default against
     `worktree.anchor`, which is the primary checkout. This applies AD-034-R8 the way SEL-018 did, so it needs no new
     ruling.
   - The project's own register stays the worktree's.
   - Test: `test_a_worktree_resolves_imported_registers_against_the_primary_checkout`.
2. **An import's new records were never projected automatically. It still held at HEAD.**
   - **Fix (AD-033-R15).** With no session in flight, the pass projects when an import's numbered register files have
     changed since its last projection. The check is a sha256 per import, kept in `<lease dir>/register_imports.json`.
     It runs in both the serial and the parallel pass.
   - A projection that changes something writes `register_projected`, and the pass commits its lines.
   - A failure keeps the old fingerprint and is retried on the next pass, recorded once per distinct error.
   - Tests: `test_the_imports_fingerprint_changes_when_an_import_adds_a_record_and_ignores_pending`,
     `test_the_pass_projects_once_per_change_of_an_import`, `test_a_failed_import_projection_is_retried_on_the_next_pass`.
3. **A stale binding had no fix. It still held at HEAD.**
   - **Fix (AD-033-R16).** The `binding:` finding is now fixable. `seldon verify --fix` re-projects, then ends each
     `constrained_by` edge to a Decision that is not `accepted`, as a `link_removed` event.
   - It does not re-bind the task to the superseding record: that is registration's matching.
   - Test: `test_verify_fix_ends_a_binding_to_a_decision_no_longer_accepted`.

Acceptance: `git log --oneline main..HEAD -- tests` lists `9562d37` and `db0fd13`.

### Tests

- New: 13 of 13 pass.
- Related suites at `-n 6`, run twice:
  - First run: 253 passed, 2 failed.
    - `test_sel022_standing_pre_lease_refusals::test_a_copied_project_map_still_rings_api_key_present_on_its_first_pass`
      asserted the exact threshold map. The new key is intended, so the expectation was updated, with a comment.
    - `test_dispatch_stuck_and_journal::test_a_project_with_no_dispatch_block_is_left_alone` matched "committed" in the
      version banner's "uncommitted changes". It passed once the code was committed.
  - Second run: 264 passed, covering `test_dispatch_parallel`, `test_governed`, `test_sel052_returns`,
    `test_desk001_desktop_commit`, `test_sel043_running_gate`, `test_sel042_ooda_boundary`, `test_cc_complete` and
    `test_dispatch_stuck_and_journal`.
- The full suite is left to the dispatcher's merge gate.

## Part B: the Hive declaration, SEL-003, and the returns

1. **The Hive block.**
   - `grep -q "def mint" /Users/brock/GitHub/factory/scripts/hive.py` found it, so FAC-41 is merged.
   - `dispatch.hive` is in `seldon.yaml` exactly as filed, with a comment citing filing `cd079f2d` and AD-038-R43
     and R44.
   - There is no `.claude/settings.json` in this repository, and the primary checkout's `settings.local.json` has no
     Hive hook, so there was nothing to remove.
   - `seldon dispatch controls`, exit 0:

         held     guard          {"tool_name": "Read", "tool_input": {"file_path": "/Users/brock/.factory/hive/secrets/planted-control"}}
         held     guard          {"tool_name": "Bash", "tool_input": {"command": "cat /Users/brock/.factory/hive/secrets/planted-control"}}
         held     spend_ceiling  {"tokens": 2400000, "ceiling": 1200000}
         untried  network          (the Network line reaches a session only as SELDON_NETWORK_ALLOWLIST, read by a consumer's fetch helper; seldon sets no host rule of its own, so there is nothing of seldon's to try)
         limits fingerprint b0fe9f88e6225563: every tried limit held

2. **SEL-003 is withdrawn (`e60b17fe`, proposed to withdrawn).** It was not overtaken: nothing has run its three-arm
   measurement. The premise that it runs now is false:
   - the operator parked it as poor value at about 11M tokens (`docs/research/2026-10-17_where_things_stand.md`);
   - RECALL-001 built its mechanism half without it;
   - its file has no Spend, Network or Framework header, so it can never be a candidate (AD-038-R11);
   - its frozen spec counts 660 records against about 800 today, so it would need a new pre-registration anyway.

   AD-033-R7 (as amended) keeps registration's Decision binding labelled advisory while no arm is picked. Re-filing it
   as SEL-003R is a spend above the cap, so that is the operator's decision, and this task does not file it.

## Not done, and why

- R23's twelve passes are not measured as a distribution of producer windows. The basis is one baseline (2,408 s), and
  the constant says so.
- The full suite was not run here. The dispatcher's merge gate runs it.

## For the consumer

There are two returns, one per consumer. Each is written from its section below and filed with `seldon cc return`.
Both are `Nothing to build`: the fixes reach each consumer through seldon's editable install when the dispatcher merges
this branch.

- hazbrief-mcp: answers `1e367024` (2026-11-24) and the 2026-11-27 worktree-register filing.
- factory: answers `cd079f2d` (declare the Hive).

## For hazbrief-mcp

**Title:** what seldon changed for hazbrief's check-line, blocked-completion, lease-wait and worktree-register filings
**Nothing to build:** every change is in seldon and reaches hazbrief through seldon's editable install when seldon's dispatcher merges SEL-058; hazbrief changes no file.

This answers two filings: `1e367024` (2026-11-24, a Part's bare check line, a blocked merge completed ungated, a lease
wait, a governing-note hold) and the 2026-11-27 filing on the decision register from a worktree. The changes are on
seldon's branch `worktree-cryptic-stargazing-lampson` (SEL-058). Decisions: AD-037-R22 and R23, AD-034-R41,
AD-033-R15 and R16.

0. **Is it merged?** `grep -q 'def completion_evidence' ../seldon/seldon/core/gate_plan.py`. If that fails, seldon has
   not merged SEL-058 yet, and none of the following is live.

Answers to "What hazbrief wants to know back":

1. **The form a Part's check takes.** Both forms are read now (AD-037-R22):
   - a `check: <command>` (or `judgment: <why>`) line on its own at the start of a line in the Part, outside a fenced
     block, which is HB-221's form;
   - the items under an `Acceptance:` label.

   HB-217's relayed form was not read before this. Desktop's 2026-11-24 handoff in seldon records that it was wrong. It
   works now, and a task written that way is gated by its own checks at the Stop gate, so the round no longer runs
   `gate_command` again as evidence.
2. **Completing a task the round blocked.** No: a completion with no gate evidence was not intended, and it is refused
   now (AD-034-R41). `seldon cc complete` on a `blocked` task needs one of these:
   - a passing, clean gate of the tree main holds: run `seldon gate main`, or wait for the scheduled run;
   - the operator's `--ungated "<reason>"`, which is recorded on the task.
3. **Waiting on a producer.** Since SEL-043 (merged 2026-11-25), hazbrief waits on seldon's or squiddy's lease only in
   the producer's pass and merge phases, or while its task writes what hazbrief reads, not for its whole session. Every
   refusal line names the holder, task, phase and gate progress. Now a wait that lasts a holding window of 12 reviewed
   passes (one hour at hazbrief's 300 s poll) also rings `dispatch_stuck` and `notify` once (AD-037-R23). To change the
   count, set `dispatch.stuck_after_passes_by_criterion.environment_in_flight` in hazbrief's `seldon.yaml`.
4. **The HB-225 hold** did ring: `dispatch_stuck` `governing_unverified` at 2026-11-24T08:04:15Z in hazbrief's store.
   If nobody saw it, look at how hazbrief's `dispatch.notify` delivers.

The register filing:

1. From a worktree, `decisions.repositories`, `decisions.import` and the side-by-side default resolve against the
   primary checkout. The comment in hazbrief's `seldon.yaml` is now true.
2. With no session in flight, hazbrief's pass projects the register whenever seldon's or squiddy's numbered records
   change. The first pass after the merge projects once in full. `docs/evidence/hb240/repair_register.py` is no longer
   needed.
3. `seldon verify --fix` ends a `constrained_by` edge to a Decision that is no longer accepted (a `link_removed` event),
   after re-projecting. It does not re-bind the task.

## For factory

**Title:** seldon declares the Hive in its dispatch block
**Nothing to build:** seldon did what the filing asked of its own repository; factory changes nothing.

This answers factory's filing `cd079f2d` (FAC-41). seldon's `seldon.yaml` now declares, under `dispatch:`, exactly the
filed block:

    hive:
      mint_command: /opt/anaconda3/bin/python /Users/brock/GitHub/factory/scripts/hive.py mint
      notices_hook: /opt/anaconda3/bin/python /Users/brock/GitHub/factory/scripts/hive.py notices --hook
      secrets_dir: ~/.factory/hive/secrets

There was no Hive hook in seldon's `.claude/settings.json` to remove (seldon has none tracked). `seldon dispatch
controls` in seldon: both guard plants on `~/.factory/hive/secrets` held, the spend ceiling held, the network line is
untried by design, and the command exited 0. The block takes effect for seldon's sessions once seldon's dispatcher
merges SEL-058.
