# RESULT: SEL-044 (task 46540234): one brief and one handoff read every repository the portfolio project declares

**Date:** 2026-11-25. **Branch:** `worktree-enchanted-cuddling-cake`. **Answers:** factory's filing `6087e4d1`
(`cc_tasks/2026-11-13_filing_from_factory_the_operator_has_no_portfolio_entry_point.md`).
**Ruling:** AD-038 ADDENDUM 14, AD-038-R32 to R35 (prior-art verify PASS, sha256 `99598d282518`, event
`2fee2855`). **Code:** `seldon/core/portfolio.py` (new); `seldon/commands/go.py`, `seldon/commands/handoff.py`,
`seldon/mcp_server.py` (`--portfolio` / `portfolio`). **Tests:** `tests/test_sel044_portfolio.py` (18).
**Evidence:** `docs/evidence/sel044/`.

Recall used: none. The hits were read after the design was set. AD-039-R1 (handoffs are tracked and scanned) agrees
with what the code already does: the MCP portfolio handoff commits through the same governed-commit path as the
project's own handoff. It changed nothing.

## What was done

**Part A: measured.** `docs/evidence/sel044/part_a_measure.md`, from `tools/survey.py` (read-only). Twenty-one
directories hold a `seldon.yaml`. Three are git worktrees of `slosh-pipe` on the same database, so there are eighteen
repositories. Every one has an online graph with tasks, and six dispatch. There are eight differences from
`factory/registry.md`. factory and aacps-ai-policy both run a dispatcher, which the table says they lack.
ai-readiness-kg's dispatcher is stopped (`DISPATCH_STOP` present; last pass 2026-11-22), not only its rescan. arnold
and icsp_notebook each have a seldon graph (204 and 286 tasks). "seldon graph" in the queue column does not name a
database. `authoring` has no directory. Ten repositories with graphs are missing from the table, among them
federal-survey-concept-mapper with 27 open tasks.

**Part B: the ruling.** `docs/design/AD-038_ADDENDUM_14_...declares.md`, with register records R32 to R35 pending
(numbered at merge).
- R32: a project declares `portfolio.repositories`; the portfolio commands read every listed repository and write
  nothing to any of them.
- R33: a repository that cannot be read is listed with its reason and never dropped; a partial read names each
  reading that failed.
- R34: each reading is the repository's own. Counts are what its `task list` shows. The phase is the lease's phase,
  or `phase unknown` when the lease records none. The gate median is over wall seconds only, printed with its n.
- R35: the portfolio handoff, its time starting the next "completed since" window, side-by-side readers and no cache.

Prior art: gita and myrepos (found, not read beyond their descriptions, as the task says), scatter-gather (Hohpe and
Woolf, named), one library receipt and one internal receipt. Neither arm found anything on point.

**Part C: the brief and the handoff.**
- `seldon go --portfolio --brief` prints the one-screen brief. `seldon go --portfolio` prints it first, then the
  project's own orientation. `--json` prints the whole reading.
- `seldon handoff --portfolio --slug --summary --next` writes `handoffs/<date>_<slug>.md` in the portfolio project:
  the brief, one section per repository and one resume line. A second write to the same path is refused unless
  `--force`.
- The MCP tools `seldon_go(portfolio=True)` and `seldon_handoff(portfolio=True)` do the same; the MCP handoff commits
  through the governed-commit path.

Each row shows:
- open tasks by state;
- the running task and its phase: the pass lease's `phase` and every held worktree lease, read with
  `dispatch status`'s readers (`read_lease`, `lease_is_held`, `worktree_leases`, `stations.gate_progress`). It never
  calls `mark_phase`;
- the last pass;
- the alarm count;
- tasks completed since the last portfolio handoff;
- open filings (`task_kind: filing`);
- the wall-clock gate median with its n.

The alarms are:
- a stop file;
- a lease whose holder is gone;
- a stuck streak the dispatcher was notified of;
- a blocked task with its stored reason (where `ungated` and `interrupted_thrice` show);
- an open huddle;
- a reading that failed;
- a gate whose log has not grown for `portfolio.gate_silent_after_s`.

Thresholds come from `portfolio` config over `PORTFOLIO_DEFAULTS`, and an unknown key is refused.

**ADDENDUM 01** was applied as written:
- The phase is the lease's phase, read with `dispatch status`'s reader.
- In `gate`, the row's detail prints the gate's progress the way `dispatch status` does.
- A silent gate log is an alarm, with its threshold in config.
- The median is over `wall_seconds` on `gate_run` (`payload.wall_seconds`) and `gate_recorded`
  (`payload.gate.wall_seconds`). Records without it are left out and counted.

**Part D: cost.** The brief reads the real nine in 1.8 to 1.9 s, and the whole command takes 2.6 to 2.8 s. That is
under a tenth of the 30 s budget, so nothing was fixed and no cache was added. With one worker it reads in 2.1 to
2.2 s. All eighteen repositories read in 2.3 s. Most of the time is parsing about 110 MB of event stores, which
holds the GIL. Run on the real repositories, the brief's open counts and task ids equal each repository's own
`seldon task list` for 18 of 18 (`part_d_counts_vs_task_list.txt`). Only factory has a gate record with wall time.
seldon, squiddy and hazbrief-mcp show `no wall-clock gate records` because their records come from before SEL-043.

**Part E:** the return to factory, filed with `seldon cc return` from the `## For factory` section below (see
"Return" at the end).

## Deviations and things to know

1. **The tests were not written before the code.** Part C says "tests first", but `portfolio.py` was written first
   and the 18 tests straight after it. On their first run the tests found one real defect: the handoff marker was
   cut to whole seconds, so a task completed in the same second as the handoff was counted again in the next
   window. Fixed: the marker keeps microseconds.
2. `seldon handoff --portfolio` (the CLI) writes the file and does not commit it, the same as the project's own CLI
   handoff. The MCP form commits it. Neither ends the session file: a portfolio handoff sits beside the project's
   own handoff and does not close the session.
3. The stuck-streak file of another repository is read from beside that repository's lease, not through
   `stuck_state_path`. That function honours `SELDON_DISPATCH_STUCK_STATE`, which names the calling process's own
   project.
4. `worktree_leases` probes a supervising worktree lease's flock with `LOCK_NB` and releases it at once, exactly as
   `seldon dispatch status` and `seldon go` already do. It opens the lock file `a+` and writes nothing; the
   "nothing written" test checks size, mtime and hash of every file in every listed repository.
5. Two thresholds are ASSUMPTIONS with their bases stated in `PORTFOLIO_DEFAULTS`: `gate_silent_after_s` 900 (half
   of the stations' `check_timeout_s`) and `first_window_days` 7 (the span of the factory's hand gatherings).
   `max_workers` 8 is a bound, not a measurement.

## Return

Filed 2026-11-25 by `seldon cc return ... --to factory --answers
seldon:2026-11-13_filing_from_factory_the_operator_has_no_portfolio_entry_point` (after a `--dry-run`):
- The return is factory **FAC-13** (`6b857695`),
  `factory/cc_tasks/2026-11-25_FAC-13_one_brief_and_one_handoff_read_every_registered_repository_from_the_po.md`. It
  was committed in factory at `785520b` and sequenced after FAC-12.
- seldon's filing `6087e4d1` is closed by it (proposed to completed, AD-036-R17).
- Registration warned `store_dirty_before_registration`: factory's in-flight session `a97d7381` had already appended
  three uncommitted lines to factory's event store, so the return's two lines are uncommitted beside them. Factory's
  standing dispatcher reconciles append-only event-store lines whoever wrote them (`seldon/core/reconcile.py`,
  AD-038-R1), so its next pass commits all five. If it does not, the operator runs, in a shell in
  `/Users/brock/GitHub/factory`, `seldon dispatch once`.

## Tests

- `tests/test_sel044_portfolio.py`: 18 passed (26 s).
- Full suite (`-n 6`, run detached on commit `a7cb804`): **3558 passed, 2 failed, 7 skipped in 30 min 48 s**
  (`docs/evidence/sel044/full_suite_tail.txt`). Neither failure is this branch's:
  - `test_pa002_release_resolve::test_rebuilding_the_served_release_reproduces_the_served_index` is the known
    library-index drift. It fails on main too.
  - `test_sel024_gate_record::test_fixture_a_regate_whose_gate_outlasts_lock_wait_does_not_refuse_a_concurrent_filing`
    is the known timing flake under load (load average 9 to 25 during this run). It also failed alone here. Run on
    main's code (`af3b7df`, a shared clone under /tmp with `PYTHONPATH` set to the clone,
    `tools/main_clone.py`), it fails with the same assertion at line 419 (`sel024_on_main.txt`). This branch changes
    no filing, gate or dispatch code.
- `seldon verify` in the worktree: every check passes but two, File hashes (two old notes,
  `2026-09-15_standing_dispatcher.md` and `AD-036_ADDENDUM_01_self_test.md`) and Governed docs (209 never
  catalogued). Both are main's existing state; this branch touches neither. The Decision register check passes with
  the 4 pending records, numbered at merge.

## For factory

SEL-044 is on seldon main: one brief and one handoff now read every repository your portfolio block lists. Nothing
is written to any of them. To use it:

1. Declare the block in `factory/seldon.yaml` (paths are relative to factory's checkout). The worked example is the
   nine rows of `registry.md`; `authoring` is left out because it has no directory yet (listed, it would show as
   unreadable, never dropped):

   ```yaml
   portfolio:
     repositories:
       seldon: ../seldon
       squiddy: ../squiddy
       hazbrief-mcp: ../hazbrief-mcp
       ai-readiness-kg: ../ai-readiness-kg
       icsp_notebook: ../icsp_notebook
       arnold: ../arnold
       aacps-ai-policy: ../aacps-ai-policy
       factory: .
     # optional, defaults shown:
     # gate_silent_after_s: 900   # a running gate whose log has not grown this long is an alarm
     # first_window_days: 7       # "completed since" before the first portfolio handoff
     # max_workers: 8
   ```

2. The two commands, run in factory's checkout (or `seldon_go(portfolio=True, brief=True)` and
   `seldon_handoff(..., portfolio=True)` from Desktop):

   ```
   seldon go --portfolio --brief
   seldon handoff --portfolio --slug portfolio_<what> --summary "<one line>" --next "<first action>"
   ```

   `go --portfolio` without `--brief` prints the brief and then factory's own orientation. The handoff's time is
   where the next brief's "completed since" starts.

3. Differences in `registry.md`, measured 2026-11-25 (`seldon/docs/evidence/sel044/part_a_measure.md`). The table is
   yours to correct:
   - factory: the dispatcher column says "none", but factory runs a dispatcher (enabled, launchd job loaded, passing
     every few minutes). The queue column says "none", but factory has a graph, `seldon-factory`, with 15 tasks.
   - aacps-ai-policy: "none yet" in both columns, but it has a dispatcher (enabled, passing) and a graph,
     `seldon-aacps-ai-policy`, with 2 tasks.
   - ai-readiness-kg: "yes (rescan off)", but `.seldon/DISPATCH_STOP` is present, so the whole dispatcher is
     stopped. The last pass was 2026-11-22T10:06Z.
   - arnold: queue "KG-001" and dispatcher "launchd jobs", but its tasks are a seldon graph, `seldon-arnold` (204
     tasks, 10 open). It has no seldon dispatcher.
   - icsp_notebook: queue "manifest", but it also has a seldon graph, `seldon-icsp-notebook` (286 tasks, 23 open).
   - seldon and ai-readiness-kg: queue "seldon graph" does not name a database. They are `seldon-seldon-self` and
     `seldon-ai-readiness-kg`.
   - authoring (planned): no directory with a seldon.yaml exists yet.
   - Not in the table: ten repositories with seldon graphs, none dispatching. They are TickBiteRisk,
     ai-workflow-design, book_responsible_ai, brock_projects, census-web-concept-inventory,
     federal-survey-concept-mapper (27 open tasks), regs-comment-pipeline, sas_graph_code_conversion, slosh-pipe (and
     its three worktrees, one graph) and usai-harness. Whether they belong in the portfolio is your call. Listing all
     eighteen costs 2.3 s.

4. What the brief does not carry: spend and the bank. They are factory's own (F-016), and no repository records
   them for seldon to read.

The brief took under 3 s over the nine. Its counts equal each repository's own `seldon task list`, checked on all
eighteen.
