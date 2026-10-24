# AD-035 ADDENDUM 03: a run holds the lock, the day boundary is one printed value, and a project declares its pilot

**Date:** 2026-10-24. **Written by:** SEL-009 (`cc_tasks/2026-10-24_SEL-009_models_refresh_does_not_bump_the_lock_under_a_held_lease.md`,
task 30c0de2c, with its ADDENDUM-00 and ADDENDUM-01).
**Implements:** AD-035-R7 ("A run in flight keeps its lock entry to the end"), which `seldon models refresh` never
honoured. **Amends:** AD-035-R2's "cached for the day", whose day now turns over at a configured instant. Three new
rulings, numbered from the register.

## Evidence: the 2026-10-24 bump

- `models/models.lock.yaml` moved from CLI 2.1.309 to 2.1.310 with `resolved_at: '2026-10-24T00:09:23.634936Z'`
  (commit 7977d66). Seldon's ledger has the `models_lock_bumped` line at 00:09:23Z. hazbrief-mcp's ledger has
  `artifact_created` by `desktop` (task `17cc0b1e`) at 00:09:26Z. So the refresh was a Desktop registration's
  `ensure_fresh("register")` (`seldon/commands/cc.py:1253`), the first trigger after the UTC day turned over.
- hazbrief's HB-24 rating top-up was mid-run at that moment, in an interactive Claude Code session
  (`hazbrief-mcp-8b`). It was not under a dispatcher lease, because hazbrief-mcp's `seldon.yaml` has no `dispatch:`
  block. Its resume was refused by squiddy's `pin_cli` with `cli_not_piloted`. That stranded 6,701 claims for 1 h 47 min,
  and the re-pilot it forced cost 4,212,332 weighted (hazbrief `cc_tasks/2026-10-24_HB-25_..._RESULT.md`; squiddy
  SQ-038R ADDENDUM-00 section 1).
- **Why R7 did not hold.** `refresh()` (`seldon/models.py`) had no notion of a run. It checked the day cache and the
  branch, then installed, probed and wrote the lock. The lock keeps one head (`cli:`, `families:`), not an entry per
  run, and no API existed for a run to register against it. The dispatcher honoured R7 for its own launches only: it
  refreshes before a launch and carries the spec in the lease (`seldon/commands/dispatch.py`, "AD-035 R2 and R7").
  Any reader of the lock head mid-run saw the bump. Before R-232, squiddy's `pin_cli` was such a reader
  (`lock_path, lock_ver = client.executable, ...`; it refused a declaration that was not the lock's). squiddy R-232
  (SQ-038R, 7322bc7) now holds the binary a run started on. That is the consumer's defence, and this note does not
  duplicate it.
- **The holder list the task suggested would have missed it.** `prune.repositories` in seldon's `seldon.yaml` is
  `[., ../squiddy, ../arnold, ../ai-readiness-kg]`, with no hazbrief-mcp. And hazbrief holds no dispatcher lease to be
  found in any list. A run outside the dispatcher needs a way to say it is running.

## The rules

- **AD-035-R13. While a run holds the lock, `seldon models refresh` does not move it; it records the deferral.**
  A refresh that finds a live holder writes nothing to the lock and spends nothing (no npm call, no probe). It appends one
  `lock_refresh_deferred` event to seldon's event store, with the cache day, the holders and the lock's CLI version.
  A second deferral on the same day with the same holders writes no second line. The event is not committed by the
  refresh, because the dispatcher's reconciler commits store lines (AD-038-R1). The CLI exits 0 with status `deferred`.
  There are two kinds of holder:
  (a) a live dispatcher lease in any repository named by `refresh.holders` in `models/registry.yaml`. That is the
  global `dispatch.lease_file` by `lease_is_held`, or a worktree lease under `dispatch.lease_dir` by
  `worktree_holder_alive`. The list resolves against the seldon primary checkout, and a lease naming the calling
  process is excluded, since the dispatcher's own launch is the boundary R7 allows;
  (b) a run hold, an flock on `<refresh.holds_dir>/<run>.lock` taken for the run's life by
  `seldon models hold --run <name> -- <command>`, or `seldon.models.hold(...)` in process.
  A listed repository that does not exist fails the refresh loudly, and the current lock stands. A first refresh,
  with no lock, is never deferred. `--force` refreshes anyway, and the `models_lock_bumped` payload names the overridden
  holders as `forced_over_holders`.
  Code: `seldon/models.py` `lock_holders`, `hold`, `refresh`, `_already_deferred`, `_primary_root`;
  `seldon/commands/models.py` `models_hold`, `models_refresh`; tests
  `tests/test_sel009_refresh_defers_and_pilot_declaration.py`.
- **AD-035-R14. The instant the day's cache turns over is one configured value, and `seldon models show` prints it with the next eligible refresh.**
  `refresh.cache_boundary_utc` (`HH:MM`, UTC, validated at load; `"00:00"` keeps R2's behaviour) sets the day a
  refresh keys on: the date of now minus the boundary. `show` prints the boundary, the next eligible instant (the
  lock's cache day plus one day, at the boundary) and the live holders. It also says that no clock job runs the refresh:
  it runs at the first `seldon cc register` or dispatcher launch after that instant with no holder. An operator who
  plans a run around the bump reads that instant instead of remembering one.
  Code: `seldon/models.py` `cache_day`, `next_refresh_at`, `show`; `seldon/commands/models.py` `models_show`.
- **AD-035-R15. A project declares a tiered pilot for a CLI change in its own `seldon.yaml`; Seldon validates it and the consumer that pilots acts on it.**
  The declaration is `models: {pilot: {cost_calls, cost_band, content_sample, full_on}}`. `cost_calls` and
  `content_sample` are whole numbers of at least 1. `cost_band` is a ratio above 1, required when `full_on` names
  `band_tripped`. `full_on` is drawn from `major`, `minor` and `band_tripped`. `seldon.models.pilot_declaration(project_dir)`
  returns it, or None, and refuses an unknown key or a bad value naming it. `seldon models show [--project DIR]` prints it.
  It is not in the lock, because the lock is never edited by hand (R1, R2).
  The contract, for the reader (squiddy `pin_cli` and `squiddy pilot`, filed as a squiddy task):
  - the first `cost_calls` calls on the new CLI are read against the recorded pilot's weighted cost per call;
  - the band is tripped when the ratio is above `cost_band` or below its inverse;
  - `content_sample` units are re-run and compared on content;
  - the full pilot runs when a `full_on` condition holds: `major` is a change in X of X.Y.Z, `minor` a change in X or Y,
    `band_tripped` a tripped band;
  - the full pilot always runs when the content comparison fails;
  - the cost line is always recorded, because it is the line that moved on 2026-10-24 (SQ-038R ADDENDUM-00 section 4).
  Code: `seldon/models.py` `pilot_declaration`, `PILOT_*`.

*Scope, recorded rather than widened:*
- Seldon writes nothing in squiddy or hazbrief. Two consumer tasks are filed: a squiddy task to read R15's declaration,
  and a hazbrief task to run long rating and extraction runs under `seldon models hold`. hazbrief has no dispatcher, so
  R13 (a) cannot see its runs.
- A busy parallel dispatcher can defer the refresh for a whole day. That is R7's price, and it is visible: every
  deferral is a ledger line naming who held the lock. `--force` is the operator's override.

## Prior art

### External

- library receipt: query "reduced inspection switching rules acceptance sampling" | release library_graph_20261017_sq018_02_2026-10-17.json sha256:99984ba3da90146a73ab4e9d8ddf15687551cb2cc2659be90d16e525253ecfb5 | rows lesson:2026-06-16_arXiv_2606_08932#p12:291:286-412, lesson:2026-06-16_arXiv_2606_08932#p6:171:5804-6549, lesson:2026-06-16_arXiv_2606_08932#p12:295:1135-2685, lesson:2026-02-22_arXiv_2506_01341#p5:157:4346-4796, lesson:2026-02-22_arXiv_2506_01341#p20:380:2315-2342, lesson:2026-02-22_arXiv_2506_01341#p22:414:503-530, lesson:2026-02-22_arXiv_2501_12599#p7:191:3985-4774, lesson:2026-03-17_arXiv_2602_03587#p40:853:2120-2249, lesson:2026-04-05_arXiv_2603_03823#p15:224:2385-2526, lesson:2026-04-12_arXiv_2407_21783#p18:257:689-2352, lesson:2026-04-12_arXiv_2407_21783#p43:634:397-589, lesson:2026-04-12_arXiv_2407_21783#p58:899:3008-3688, lesson:2026-02-22_arXiv_2407_06985#p2:26:3357-3851, lesson:2026-02-22_arXiv_2407_06985#p2:16:2857-2907, lesson:2026-02-22_arXiv_2408_14033#p5:140:2691-2701, lesson:2026-03-17_arXiv_2603_04448#p18:302:511-521, lesson:2026-02-22_arXiv_2504_08066#p13:104:1739-1787, lesson:2026-02-22_arXiv_2504_08066#p12:90:1630-2451, lesson:2026-02-22_arXiv_2504_08066#p41:562:2615-2765, lesson:2026-05-09_arXiv_2605_06161#p7:139:1314-3051, lesson:2026-05-09_arXiv_2605_06161#p16:303:3229-3503, lesson:2026-05-09_arXiv_2605_06161#p4:86:2561-4034, lesson:2026-02-26_arXiv_2602_14740#p28:396:783-824, lesson:2026-02-22_arXiv_2502_11903#p21:598:4122-4146, lesson:2026-02-22_arXiv_2405_07960#p27:211:1941-1985, lesson:2026-02-22_arXiv_2405_07960#p27:214:2020-2059, lesson:2026-02-22_arXiv_2405_07960#p29:229:211-535, lesson:2026-02-22_arXiv_2507_02592#p2:24:4010-4534, lesson:2026-02-22_arXiv_2507_02592#p6:82:2098-2132, lesson:2026-02-22_arXiv_2411_00816#p8:174:3029-3081, lesson:2026-02-22_arXiv_2411_00816#p9:217:395-774, lesson:2024-05-17_arXiv_2204_04198#p115:2628:927-1311, lesson:2024-05-17_arXiv_2204_04198#p112:2530:1038-1128, lesson:2024-05-17_arXiv_2204_04198#p192:4624:2629-3908, lesson:2026-06-16_arXiv_2606_15474#p3:24:3152-3686, lesson:2026-06-16_arXiv_2606_15474#p9:154:1173-1879, lesson:2026-06-16_arXiv_2606_15474#p8:135:1909-2509, lesson:2026-02-22_arXiv_2507_20534#p14:417:200-232, lesson:2026-02-22_arXiv_2507_20534#p32:753:276-324, lesson:2026-02-22_arXiv_2509_00710#p3:37:4883-5256

  The library returned nothing on point. Its rows are LLM-training "rejection sampling" and generic "inspection" uses.
  The engineering and standards sources below are the prior art, and each decided one thing here:

- **flock(1) and `fcntl.flock`.** A command runs while a lock is held, and the kernel releases the lock when the holder
  dies. *Decided here:* a run hold is `seldon models hold --run <name> -- <command>`, an flock for the command's life.
  It is never a record with an age, so a crashed run cannot hold the lock forever. The dispatcher's lease uses the same
  guard (DN-006 section 5, DD-022's PID rule).
- **Renovate's schedule and Dependabot's update windows.** A dependency bump is proposed only inside a declared time
  window, and the window is configuration. *Decided here:* the day boundary is one configured value that `show` prints
  (R14). Renovate also does not rebase a branch someone is working on. That is R13's deferral: no bump under a holder.
- **Change freezes in release management (ITIL change control).** No change lands while a measured or released system
  is in use, and the freeze has an explicit override that is recorded. *Decided here:* `--force` exists and the bump
  names whose run it moved under (`forced_over_holders`).
- **ISO 2859-1 switching rules** (normal, reduced and tightened inspection). A supplier with a clean record is
  inspected on a reduced sample, and one failure switches back to full inspection. *Decided here:* R15's tiers. A
  patch release with a clean record is checked on `cost_calls` and `content_sample`, and a tripped band or failed
  content switches to the full pilot.
- **ISO/IEC 17025:2017** 6.4.10 (intermediate checks on equipment) against 7.2.2.2 (re-validation when a change
  affects the original validation), as cited in squiddy SQ-062. *Decided here:* the tiered pilot is the intermediate
  check, and `full_on` names when it becomes a re-validation.

### Internal

- internal receipt: query "run in flight keeps its lock entry" | repo seldon@20f9c8e50aca22896b8f8421036d6b2b6ecc6ed7 | hits docs/design/AD-035_config_driven_model_selection.md:71, docs/decisions/register/00220_seldon-ad-035-r7_accept.yaml:25, docs/decisions/register/00220_seldon-ad-035-r7_accept.yaml:15, docs/decisions/REGISTER.md:9
- internal receipt: query "run in flight keeps its lock entry" | repo squiddy@254ec4f8c8f2e247e0a75053e5bc5bc5dbce367c | hits docs/EXTRACTION_DESIGN_SPEC.md:365, docs/decisions/REGISTER.md:9
- internal receipt: query "cli_not_piloted" | repo seldon@20f9c8e50aca22896b8f8421036d6b2b6ecc6ed7 | hits none
- internal receipt: query "cli_not_piloted" | repo squiddy@254ec4f8c8f2e247e0a75053e5bc5bc5dbce367c | hits docs/design/2026-10-24_DN-006_ADDENDUM_01_r232_a_run_holds_its_piloted_binary.md:76, docs/decisions/register/01020_squiddy-r-232_accept.yaml:29, docs/design/2026-10-24_DN-006_ADDENDUM_01_r232_a_run_holds_its_piloted_binary.md:95, docs/EXTRACTION_DESIGN_SPEC.md:103
- internal receipt: query "tiered pilot cost band" | repo seldon@20f9c8e50aca22896b8f8421036d6b2b6ecc6ed7 | hits none
- internal receipt: query "tiered pilot cost band" | repo squiddy@254ec4f8c8f2e247e0a75053e5bc5bc5dbce367c | hits none

The first search finds R7 itself (`AD-035_config_driven_model_selection.md:71` and its register record 00220). squiddy's
spec line 365 restates it for the extraction daemon. No code in either repository implemented it in the refresh. The
second search finds squiddy's R-232 note (DN-006 ADDENDUM 01, lines 76 and 95) and its register record 01020: the
consumer's half, which holds the binary and requalifies a CLI by an equivalence run under `equivalence_tolerance`. R15
gives that routine a project-declared sample size instead of the whole recorded pilot. The third search, for the
mechanism's own words, found nothing in seldon or squiddy. squiddy SQ-086 (proposed, 2026-10-24) argues for a per-call
rate band read at the 50th call against a declared baseline, with hazbrief's band at 0.67x to 1.5x. That is the same
statistical-process-control reading R15's `cost_calls` and `cost_band` declare.

## Negative control (AD-038-R6)

In `tests/test_sel009_refresh_defers_and_pilot_declaration.py`, three tests passed on the base 20f9c8e and still pass:
`test_the_calling_process_own_lease_is_not_a_holder`, `test_a_released_lease_and_a_dead_pid_hold_nothing` and
`test_a_repo_with_no_dispatch_block_holds_nothing`. In each case the refresh bumps, exactly as before SEL-009. The
24 tests that need a holder to defer, the boundary or the declaration failed on the base
(`docs/evidence/sel009/red_run_on_base_20f9c8e.txt`).
