# RESULT: SEL-052, what factory reported this week is answered

**Task:** `cc_tasks/2026-11-26_SEL-052_what_factory_reported_this_week_is_answered.md` (ad161bd6). No addenda existed.
**Branch:** `worktree-keen-rolling-pike`. The dispatcher merges.
**Decisions:** AD-036 ADDENDUM 16 (AD-036-R31 to R34), AD-038 ADDENDUM 15 (AD-038-R36 to R39), AD-013 ADDENDUM 03
(AD-013-R7), each with its accepted register record (pending, numbered at merge).
Recall used: none. The registration's recall hits were not opened; the session's own memory of the HOOK-001 and
returns traps was used instead.

## What the time went to (the two observations)

- **CTAI-006R** (critical-thinking-ai `2e2bc082`). All five Parts passed. The session ended with one untracked
  directory in its worktree, `graphs/critical-thinking-evidence/archive:inbox/`, holding a `.gitkeep`. The merge round
  refused it as `merge_blocked: uncommitted_changes` at 2026-11-26T22:55:16Z. The finish's one banner went out and was
  not seen. A person redrove the task at 23:15:18Z (20 minutes 2 seconds later), and a second session took 3 minutes
  15 seconds to delete one directory and merge (23:18:48Z). Two seldon gaps: nothing rang for the block after its
  finish (fixed, AD-038-R36), and the Stop gate let the session end with a tree the merge would refuse (fixed,
  AD-038-R37).
- **CTAI-008** (critical-thinking-ai `63f7b0a3`, a return). It ran from 2026-11-27T01:00:57Z to 02:04:56Z: 3,845 s of
  wall clock, of which 341 s was API time (the log's `result` record). The other 58 minutes were the consumer work
  its return asked for: the extraction run it resumed (`extract.py run --phase b`, polled at 10 s intervals), a
  re-parse of every held document (the fresh worktree lacks the gitignored `corpus/parsed/` intermediates the kept
  tree had; one document's parse failed and was copied from the kept tree), and two release cuts. So the return was
  not "nothing to build". Its default `**Spend:**`, "no model calls of its own", was wrong for it. It then ended
  `merge_blocked: ungated` (02:05:11Z): the return template declared `**Parts:** A 1.00.` with no `check:`, and
  critical-thinking-ai declares no gate command. It is blocked now. With this branch merged, AD-038-R36 rings for it.
  The template now carries a check (AD-036-R34).

## Part A

1. **What writes the absolute `core.hooksPath`: the Claude Code CLI.** I read the CLI bundle
   (`/opt/homebrew/lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe`, 2.1.325). Its post-create worktree step
   (`xTt`) reads `core.hooksPath` from the common config. When the value is relative, it resolves it against the main
   checkout and runs `git config core.hooksPath <absolute>` in the new worktree, which writes the SHARED config. So
   every `claude --worktree` launch, which means every dispatched task, makes the primary's value absolute. seldon's
   own primary showed it at this writing: `local /Users/brock/GitHub/seldon/.githooks`.
   - The red test is `tests/test_sel052_hook_path.py`. It transcribes that step as `cli_worktree_hook_step`. On the
     old install, 5 of 5 tests failed; the first failed with
     `core.hooksPath is '/private/var/.../primary/.githooks', not '.githooks'`.
   - The fix (AD-036-R31) leaves the CLI nothing to write. `install` now writes the shared value as the main
     worktree's `.githooks`, absolute; this is the CLI's own fixed point. It writes the relative `.githooks` into the
     checkout's own `config.worktree`, which wins (`extensions.worktreeConfig`).
   - I measured on git 2.50.1 that `git worktree add` copies `config.worktree` into a new worktree. So an unpointed
     worktree also runs its own checkout's hook, which is HOOK-001's property restored.
   - `status` now reports a relative value left in the shared config as not installed. The dispatcher's
     `ensure_installed` runs every pass, and on its first pass after the merge it moves seldon's, factory's and
     critical-thinking-ai's primaries, because all three run seldon's editable code.
2. **The prior-art filing (factory, 2026-11-26).**
   - Item 1: the new key `prior_art.internal_roots_from: ../factory/seldon.yaml#portfolio.repositories` reads the one
     list of registered repositories (AD-036-R32). `docs/se/**` and `docs/requirements/**` joined `default_include`.
     Live check: a search for "requirements elicitation" now reads 11 roots, and factory returns `DN-002` hits.
   - Item 2: `seldon_req_add` and `seldon_req_update` are on seldon-mcp, as one `write_one` call.
   - Item 3: `SRS_Requirement` gained `disposition` with `disposition_reason`, `disposition_ends_when` and
     `disposition_task`. A write that leaves a disposition without its grounds is refused, and the Status cell shows
     the disposition (AD-013-R7).
   - Item 4: `decision accept --from` of a new record with no `source` is now refused before any file is written.
3. **The spec-check filing.** Besides the hook path:
   - `seldon decision project` in a worktree with pending records raised `KeyError: 'record_hash'`. It now projects
     numbered records only and reports the pending ones, which is AD-033-R14 as SEL-042 applied it to verify.
   - The rest are not taken here; they are listed under "Not done".
4. **A hold that waits on a person.** A `blocked` task now rings `notify` with outcome `held`, its block reason, its
   age and the command that clears it. It rings once it has been blocked `held_alarm_after_s` (900 s), and again
   every `held_repeat_s` (86,400 s); each ring is one `dispatch_held` event (AD-038-R36). FAC-06's ten days would
   have rung ten times, and CTAI-006R's twenty minutes once.

## Part B

1. **The return-task filing.**
   - Item 1: `cc return` now waits on the consumer's latest open task that can run, never a filing or a FUTURE task.
     Registration refuses an `After:` that names a filing, as `after_unrunnable` (AD-036-R33).
   - Item 1, the survey of every registered repository (22 return files): squiddy SQ-143 is superseded. seldon's
     SEL-051 is open and waits After the prior-art filing this task answers. This task's return closes that filing,
     which releases SEL-051.
   - Item 2: the warning is already on stderr (`click.echo(..., err=True)` in `_cross_waits`). What SEL-047 saw was
     Click 8.1.7's `CliRunner()`, which folds stderr into `result.output`. The real command's stdout parses as JSON,
     and `tests/test_sel052_status_json_stdout.py` pins it.
   - Item 3: the schema a client sees is the one the long-lived seldon-mcp server registered at its start. The child
     runs HEAD's code but receives only the old schema's arguments. An answer now names every parameter the server
     did not send and says to restart the server (AD-038-R39). Measured through the CLI: the portfolio brief is
     2,983 characters (about 750 tokens), 9 repositories, 2.3 s.
   - Item 4: not taken. Recorded as Issue `88c9f4d8` with the question to measure first.
2. **The worktree-link filing.** A declared link the checkout already made is now recorded on
   `dispatch_worktree_named` as `links_skipped` with its reason. When the repository tracks something at or under the
   path, every launch prints the remedy (AD-038-R38). factory's form for the inbox is in the section for factory.
3. **A return with nothing to build completes without a session where the record allows it.** It does when the
   answering RESULT's `## For <consumer>` section carries `**Nothing to build:** <reason>`. The return is still
   written and registered as the record, then walked to `completed` at filing, with its lines recorded in the
   consumer (AD-036-R34). This could not apply to CTAI-008: its consumer did have work.

## Tests

New, all passing on the branch:
- `tests/test_sel052_hook_path.py`
- `tests/test_sel052_held_alarm.py`
- `tests/test_sel052_prior_art_reach.py`
- `tests/test_sel052_filing_answers.py`
- `tests/test_sel052_stop_gate_dirt.py`
- `tests/test_sel052_worktree_link_skip.py`
- `tests/test_sel052_returns.py`
- `tests/test_sel052_status_json_stdout.py`
- `tests/test_sel052_mcp_stale_schema.py`

Changed for the new hook layout: `tests/test_hooks.py` (unhooking now clears both scopes) and the
`tests/test_sel017_links_hook_parts.py` fixture (it plants the pre-SEL-052 install).

Full suite on the branch at `38c675a` (`-n 6`, 2026-11-27T02:47Z, 2,131 s): 3,597 passed, 8 skipped, 5 failed.
- Four of the five failures came from this branch's hook layout, as intended:
  - `test_dispatch_serial_transcript` (both parametrizations) had a golden transcript in which the two
    `hooks_path.changed` values now read `false`. I re-recorded it with an erratum; nothing else differs.
  - `test_sel019_project_new::test_a_temp_directory_becomes_a_project_...` read the `--local` scope.
  - `test_cc_register_commits_note::test_a_commit_the_hook_refuses_...` planted its refusing hook in the shared
    scope, which the checkout's own scope now overrides.

  I updated all four at `e9805a2`, and they pass on a rerun.
- The fifth, `test_sel019_project_new::test_the_real_squiddy_initializes_a_filled_skeleton`, is squiddy's own
  `init` refusing its spec ("the emitter builds ['AffiliatedWith', ...] ... the spec does not declare them"). It
  fails identically on seldon main's code in a `/tmp` shared clone with squiddy beside it, so it is not this branch's.

## Not done, and why

- **Spec-check WARNING and CRITICAL rows:**
  - seldon's `seldon.yaml` declares no `docs.projections` and no `environment.packages`.
  - `seldon verify` reports File hashes modified for `2026-09-15_standing_dispatcher.md` and
    `AD-036_ADDENDUM_01_self_test.md`.
  - `seldon project new` writes no `prior_art:` block.
  - There is no read-only command for "the graph answers" or "the prior_art block resolves".

  Each is a separate change with its own grounding. The hook row and the `decision project` traceback were the ones
  with a defect behind them.
- **The union_merge flake** (Issue `88c9f4d8`): not taken here.
- **A `seldon docs check` rule that every need has a disposition:** this waits on a second project asking for it
  (AD-013-R7).
- **Session dirt behind a `dir/` ignore pattern.** While testing, I found that a link at a path ignored only by a
  `dir/` pattern collapses to its parent in `git status`, and `dirty_paths` then reports the parent. The remedy text
  says to use a pattern with no trailing slash; the predicate is unchanged.

## For the consumer

One return goes to factory, covering all five filings and the two observations. It is written from the next section.
Filed as factory FAC-34 (`15f2cdde`), committed in factory at `2f53656` by its registration. All five filings are
completed in seldon's graph: `61cafca4`, `6544f067`, `6530b579`, `179b57bc` and `706c40a2` (AD-036-R17). SEL-051's
predecessor, `61cafca4`, is completed, so SEL-051 no longer waits. Filing `81e09bae` ("a project needs a premise the
dispatcher evaluates") arrived during this session and is not answered here.

## For factory

**Title:** what seldon did with this week's five filings and two observations

This return covers seldon's answers (SEL-052) to factory's filings of 2026-11-24, 25 and 26, and to the two
observations the coordinator relayed. The changes are on seldon's branch `worktree-keen-rolling-pike`, which seldon's
dispatcher merges to main. factory's dispatcher runs seldon's editable code, so they reach factory at that merge.

### What factory does

1. **The inbox link (2026-11-25 filing).** factory's `corpus/inbox/` is tracked (`.gitkeep`), so every checkout
   creates it and `dispatch.worktree_links` cannot link it. Seldon now records the skip and prints the remedy at every
   launch, but the fix is factory's. In factory's checkout, run these one at a time, then commit:

       git rm --cached corpus/inbox/.gitkeep
       printf '/corpus/inbox\n' >> .gitignore

   The pattern has no trailing slash on purpose. The link is a symlink, which a `corpus/inbox/` pattern does not
   match, and git would then list `corpus/` as untracked and block every merge. The primary's own `corpus/inbox/`
   directory and its files stay where they are.
2. **The MCP portfolio brief (2026-11-26 filing, item 3).** The brief is reachable from `seldon_go(project_dir,
   brief=true, portfolio=true)` once the seldon-mcp server serves the current schema. The server registered its
   schema when it started, before SEL-044 added `portfolio`, so a client could not pass it. This is the operator's
   step, after seldon's merge: quit Claude Desktop and reopen it. Measured on 2026-11-27: 2,983 characters, about 750
   tokens, 9 repositories, 2.3 s. Until then, an answer from that server ends with a note naming the dropped
   parameter.
3. **The hook path (spec-check filing).** No step for factory. The writer was the Claude Code CLI's worktree step.
   Seldon's dispatcher moves factory's primary to the new layout on its first pass after the merge, and
   `seldon hooks status` then exits 0. Running `seldon hooks install` in factory's checkout does the same at once.
4. **Requirement dispositions (prior-art filing, item 3).** factory may write `--disposition` (with
   `--disposition-reason`, `--disposition-ends-when` or `--disposition-task`) on `seldon req add|update`, or the same
   fields on the new `seldon_req_add` and `seldon_req_update` MCP tools. It may then stop parsing the `note` clause.
   Moving its existing needs over is factory's choice; nothing in seldon requires it.

### What factory asked to know back

- **Filing of 2026-11-24 (a hold tells nobody).** A blocked task now rings `notify` with its reason, its age and the
  command that clears it: once after 15 minutes, then once a day (`dispatch.held_alarm_after_s`,
  `dispatch.held_repeat_s`). A session can no longer end with a tree the merge would refuse. CTAI-006R's twenty
  minutes is the case both rules close.
- **Prior-art filing.** All four registered repositories are now searched, from factory's `portfolio.repositories`,
  and `docs/se/**` is in the corpus. The MCP requirement verbs and the disposition are in. A `decision accept --from`
  with no `source` is refused before anything is written.
- **Return-task filing.**
  - Item 1: a return is no longer written `After:` a filing, and registration refuses one that is. Of the 22 return
    files in the registered repositories, SQ-143 is superseded. seldon's SEL-051 was waiting on the prior-art filing,
    which this return closes.
  - Item 2: the warning was already on stderr. The test harness mixed the streams.
  - Item 3: see step 2 above.
  - Item 4: seldon did not take it in this task. It is Issue `88c9f4d8` in seldon's graph.
- **CTAI-008** (it reached critical-thinking-ai, not factory, but the coordinator asked). Its 64 minutes were the
  extraction and releases its return asked it to run, not seldon overhead. It is blocked `ungated` because the return
  template had no check; new returns carry one. CTAI-008's own file still has none, so a plain redrive would block
  `ungated` again. What clears it is a gate in critical-thinking-ai: declare `dispatch.gate_command` in its
  `seldon.yaml` (factory's own form is `python -m pytest tests/`), then run `seldon dispatch redrive 63f7b0a3` in
  its checkout. That is critical-thinking-ai's change, not factory's, and the coordinator decides it.
