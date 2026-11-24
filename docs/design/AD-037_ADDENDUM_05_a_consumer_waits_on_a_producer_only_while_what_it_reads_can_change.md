# AD-037 ADDENDUM 05: a consumer waits on a producer only while what it reads can change, and a running gate shows its progress and its wall time

**Date:** 2026-11-24. **Status:** Accepted. Implemented by SEL-043 Parts A to D
(`cc_tasks/2026-11-21_SEL-043_a_consumer_waits_on_a_producer_only_for_what_can_hurt_it_and_a_running_gate_shows_its_progress_and_its_wall_time.md`),
answering squiddy's filings `44ba49df` (a consumer's dispatcher waited hours on squiddy's lease) and `083863ef` (items 1
and 2: a gate's output is held until it exits; its seconds leave out sleep). **Narrows:** AD-037-R6 station (a), the
premise the dispatcher adds to every task (`environment_in_flight`). **Extends:** AD-034-R33 (the `gate_run` record,
SEL-041) and AD-034-R16 (the declared pass record). Five new rulings, AD-037-R17 to R21.
**Code:** `seldon/core/dispatch.py` (`PHASE_*`, `mark_phase`, the lease's first body); `seldon/core/stations.py`
(`HOLDING_PHASES`, `environment_premise`, `environment_pin`, `gate_progress`, `run_check`'s `stream_to`,
`asleep_seconds`, `wall_fields`); `seldon/commands/dispatch.py` (the session phase, the refusal record and message,
`status`); `seldon/commands/dispatch_worktree.py` (`_gate_phase`, `_merge_phased`, `record_pass`'s log);
`seldon/core/gate_record.py`, `seldon/core/gate_plan.py` (the wall clock on both gate records).
**Tests:** `tests/test_sel043_environment_window.py`, `tests/test_sel043_running_gate.py`.
**Evidence:** `docs/evidence/sel043/` (tables, the scripts that made them, their outputs).

## 1. Evidence

1. **What a consumer reads from a producer, and from where** (`docs/evidence/sel043/imports.json`, read 2026-11-24).
   Every consumer's interpreter imports seldon and squiddy as editable installs of the producers' PRIMARY checkouts:
   the dispatcher's python (`/opt/anaconda3`), which every project's checks and hooks run, has both from
   `/Users/brock/GitHub/{seldon,squiddy}`; squiddy's `.venv` has both from there too; aacps-ai-policy's gate runs
   squiddy's `.venv`; hazbrief's own `.venv` has neither and reaches squiddy through squiddy's `.venv`
   (`corpus/ingest_config.yaml` `squiddy_python`) and seldon through the dispatcher's python; factory has no `.venv`.
   They also read files of the producers' trees by path: hazbrief reads `../squiddy/squiddy/spend.yaml` and both
   producers' `governed` graphs. So a consumer reads a producer's primary working tree live.
2. **When a producer's primary changes under its dispatcher.** Every repository dispatches serially
   (`max_parallel: 1`, `docs/evidence/sel043/tools/survey_cfg.py`), so one pass lease is held from the pass that claims
   a task to the end of its merge round. Since AD-034 the session works in its own worktree and the merge round's gate
   runs there; the primary is written by the pass (journal commits, reconcile, the claim's records), by the merge round
   outside its gate (rebase checks under the lease, the fast-forward, numbering, the finish's commits) and, in any
   phase, by a session whose task's Repo line names another repository (DISP-004R), which commits there by path.
   Desktop's governed commits write a primary under no lease at all, before or after this addendum.
3. **Every `environment_in_flight` refusal** in every dispatching repository's store, 2026-10-17 to 2026-11-24
   (`docs/evidence/sel043/refusals_table.md`, method in `tools/refusals2.py`: a refusal waits until the consumer's next
   launch or the producer's `dispatch_finished`, whichever is first; intervals unioned per consumer; the producer's
   dispatch split at `launched + wall_clock_s` and at its last gate record):

   | consumer | producer | refusals | hours waited | in producer session | in producer gate | in producer merge | between tasks |
   |---|---|---|---|---|---|---|---|
   | factory | squiddy | 1 | 2.9 | 0.6 | 2.3 | 0.00 | 0.00 |
   | hazbrief-mcp | seldon | 17 | 13.5 | 12.3 | 0.0 | 1.12 | 0.17 |
   | hazbrief-mcp | squiddy | 18 | 21.6 | 10.1 | 10.2 | 1.25 | 0.09 |
   | seldon | squiddy | 7 | 9.2 | 7.4 | 1.8 | 0.03 | 0.00 |
   | squiddy | seldon | 9 | 5.9 | 5.6 | 0.0 | 0.03 | 0.26 |
   | all | | 52 | 53.3 | 36.0 | 14.3 | 2.42 | 0.52 |

   50.3 of the 53.3 hours (94 percent) fell in a producer's session or gate. Before SEL-041 (2026-11-21) seldon's
   merge-round gates left no gate record, so a seldon round reads as all merge: 2.42 hours is an upper bound. Three of
   the 52 refusals named a producer task whose Repo line wrote another repository, and each wrote the very consumer it
   held (seldon `841bd7c7` into squiddy; seldon `c4d813a9` and `0a8a6776` into hazbrief-mcp;
   `docs/evidence/sel043/push_repos.txt`): those holds were protective and stay.
4. **A running gate was invisible and its seconds left out sleep** (filing `083863ef` items 1 and 2).
   `stations.run_check` captured the declared pass record's output until it exited and kept 1,500 characters; the
   gate-command path (`gate_plan.run`) already wrote to `<stem>.gate.log` as it ran. `time.monotonic()` stops while
   macOS sleeps: SQ-133R's pass was recorded 7,734.6 s and ran 10,834 s by the wall clock. This host's power log
   (`pmset -g log`) began on 2026-11-17 when read on 2026-11-24, so it can no longer say how long the 11-13 pass slept
   (`docs/evidence/sel043/asleep_sq133r.txt`): an answer from the power log is available only while macOS keeps it.

## 2. Prior art

### External

- **Lock granularity** (Gray, Lorie, Putzolu and Traiger, "Granularity of locks and degrees of consistency in a shared
  data base", 1976): a lock is taken on the smallest object that protects the invariant, for the shortest time.
  Adopted: the old station locked a whole repository for a whole dispatch; R17 holds only across the phases that write
  what a consumer reads. Cited by its published name; not fetched (Network: none), and not in either library (receipt
  below).
- **Snapshot isolation** (Berenson, Bernstein, Gray, Melton, O'Neil and O'Neil, "A Critique of ANSI SQL Isolation
  Levels", 1995): a reader works from the version current when it began and is not blocked by a writer whose work is
  not yet committed. AD-034 already gives the producer's side of this: a worktree's commits are invisible to every
  other checkout until a ref moves. Adopted for the window (a writer's uncommitted work blocks nobody); departed from
  for the read itself, which is NOT a snapshot here: an editable install reads the live tree, so R18 records the
  version read instead of isolating it. Cited by name; not fetched.
- **Version pinning and lockfiles**: a consumer builds against a recorded revision of a dependency, and the producer's
  work in progress is invisible until a new revision is published. Adopted as R18's record. Making it an isolation
  (installing a pinned copy per launch) is not built: no consumer installs the producers by version today.
- **Monotonic clocks and suspend** (Python's `time.monotonic` documentation and PEP 418, which name
  `mach_absolute_time` as the macOS source, a clock that does not advance during sleep): cited by name, not fetched;
  the filing's 7,734.6 s against 10,834 s is the measurement on this host. Adopted: a record keeps monotonic seconds
  for the work done and adds wall time and the power log's sleep beside them (R21).
- The library arm holds none of these (searched 2026-11-24, both graphs; the hits are unrelated rows):
- library receipt: query "granularity of locks degrees of consistency shared data base" | graph seldon-biblio | release seldon_biblio_graph_20261111_sel037_2026-11-11.json sha256:076422bb8382009ff8c0105c7ae07dd9b2f2a86b7ff7fd24b4674e219c6b7b4c | rows doc_rfc9162_1#b374:67759-67929, doc_rfc9162_1#b143:23899-24154, doc_rfc9162_1#b133:23224-23306, doc_who_trs1033_annex4_1#b2399:655563-655578, doc_who_trs1033_annex4_1#b735:259845-260020, doc_who_trs1033_annex4_1#b1683:454342-454682, doc_premis_3_0_1#b917:403173-403439, doc_premis_3_0_1#b223:75874-76194, doc_premis_3_0_1#b226:76254-76271, arxiv_2406_14325#b33:18571-20159, arxiv_2406_14325#b110:57629-59020, arxiv_2406_14325#b23:12143-12452, yu2026multiagentmemory#b80:15387-15521, yu2026multiagentmemory#b36:4119-4569, yu2026multiagentmemory#b49:7664-8528, ilyas2023growing#b73:25582-26639, ilyas2023growing#b65:22582-22769, ilyas2023growing#b12:2304-2656, doc_w3c_prov_o_1#b1245:100118-100213, doc_omg_reqif_1_2_1#b951:105699-105738, doc_omg_reqif_1_2_1#b1494:123241-123407, doc_rfc8493_1#b71:12908-12971, doc_rfc8493_1#b33:6888-7291, arxiv_2104_03986#b221:80664-80929, arxiv_2104_03986#b148:57321-57622, arxiv_2104_03986#b16:5392-6326, li2024kgllm#b117:34575-34680, li2024kgllm#b44:12965-14768, li2024kgllm#b107:31672-31897, clark2014micropublications#b399:96141-96162, clark2014micropublications#b243:61447-61646, clark2014micropublications#b337:81309-81529, ilyas2022saga#b241:84764-85144, ilyas2022saga#b146:59549-60575, ilyas2022saga#b67:20534-21059, liu2024lostmiddle#b72:22359-22841, liu2024lostmiddle#b84:27734-28073, liu2024lostmiddle#b71:21978-22357, liang2026skillnet#b76:22391-23009, liang2026skillnet#b308:121343-121861, liang2026skillnet#b171:70357-70598, chen2023chatgpt#b26:13592-14162, chen2023chatgpt#b29:15158-15881, chen2023chatgpt#b90:35143-35685, fuchss2025lissa#b142:57039-57524, fuchss2025lissa#b178:72211-72565, fuchss2025lissa#b215:82526-82963, doc_omg_sysml_v2_1#b574:278397-278767, doc_omg_sysml_v2_1#b3719:813527-813730, doc_omg_sysml_v2_1#b7369:1072622-1072805, doc_omg_kerml_1#b3423:640748-641638, doc_omg_kerml_1#b605:233590-234150, doc_omg_kerml_1#b3399:635511-635964, amodei2016concrete#b207:95794-95887, amodei2016concrete#b113:63684-64458, amodei2016concrete#b301:110564-110728
- library receipt: query "snapshot isolation critique ANSI SQL isolation levels" | graph library | release library_graph_20261110_sq133r_b.r1_2026-11-13.json sha256:c38db2b4106bbc762c984d545e044a60ac0a91923254ba2e4de8cf8a3964d784 | rows lesson:2026-05-09_arXiv_2604_08224#p31:216:3871-4726, lesson:2026-05-09_arXiv_2604_08224#p31:214:3358-3398, lesson:2026-02-22_arXiv_2402_10890#p13:109:1584-2223, lesson:2026-02-22_arXiv_2402_10890#p3:17:0-487, lesson:2026-02-22_arXiv_2402_10890#p16:139:823-1016, lesson:2026-05-09_arXiv_2601_03543#p3:54:3017-3116, lesson:2026-05-09_arXiv_2601_03543#p1:23:2210-2219, lesson:2026-05-09_arXiv_2601_03543#p13:244:79-96, lesson:2026-07-25_arXiv_2603_22528#p34:586:1134-1289, lesson:2026-07-25_arXiv_2603_22528#p34:584:916-928, lesson:2026-07-25_arXiv_2603_22528#p36:621:113-154, lesson:2026-05-09_arXiv_2604_23338#p35:475:669-749, lesson:2026-04-12_arXiv_2401_06066#p12:251:825-1270, lesson:2026-04-12_arXiv_2401_06066#p11:236:2256-2545, lesson:2026-04-12_arXiv_2401_06066#p12:249:193-764, lesson:2026-02-22_arXiv_2412_11716#p17:272:1065-1071, lesson:2026-02-22_arXiv_2412_11716#p17:282:1647-1653, lesson:2026-02-22_arXiv_2412_11716#p17:273:1073-1081, lesson:2026-06-16_arXiv_2606_08932#p5:153:4325-5590, lesson:2026-06-16_arXiv_2606_08932#p6:163:1136-2052, lesson:2026-06-16_arXiv_2606_08932#p4:97:935-1498, lesson:2026-02-04_arXiv_2503_16233#p20:503:847-1713, lesson:2026-02-04_arXiv_2503_16233#p22:514:0-1318, lesson:2026-02-04_arXiv_2503_16233#p22:515:1320-3288, lesson:2026-02-22_arXiv_2304_05128#p32:589:1209-1547, lesson:2026-02-22_arXiv_2304_05128#p6:77:1602-1677, lesson:2026-02-22_arXiv_2304_05128#p6:80:2136-2211, lesson:2026-04-01_arXiv_2507_09089#p46:533:711-1081, lesson:2026-04-01_arXiv_2507_09089#p46:534:1083-1860, lesson:2026-04-01_arXiv_2507_09089#p5:44:2083-2526, lesson:2026-02-22_arXiv_2503_20020#p33:547:3430-3557, lesson:2026-02-21_arXiv_2305_16291#p35:638:2281-2309, lesson:2026-02-21_arXiv_2305_16291#p30:524:115-129, lesson:2026-02-21_arXiv_2305_16291#p37:666:134-150, lesson:2026-02-22_arXiv_2507_20534#p19:493:803-1581, lesson:2026-02-22_arXiv_2507_20534#p12:372:2524-2578, lesson:2026-04-05_arXiv_2603_28052#p22:356:95-110, lesson:2026-04-05_arXiv_2603_28052#p17:271:1671-1975, lesson:2026-04-05_arXiv_2603_28052#p6:129:3465-4007, lesson:2026-04-12_arXiv_2404_14469#p10:209:307-1063, lesson:2026-04-12_arXiv_2404_14469#p8:188:1182-3286, lesson:2026-02-22_arXiv_2506_02158#p7:162:2950-2989, lesson:2026-02-22_arXiv_2506_02158#p7:148:737-805, lesson:2026-06-20_arXiv_2603_27277#p5:109:3219-3824, lesson:2026-04-12_arXiv_2303_08774#p25:452:3166-3192, lesson:2026-04-12_arXiv_2303_08774#p97:1341:0-168, lesson:2026-04-12_arXiv_2303_08774#p25:453:3194-3592, lesson:2026-08-25_arXiv_2606_08317#p4:52:3181-3336, lesson:2026-08-25_arXiv_2606_08317#p12:223:2151-2157, lesson:2026-08-25_arXiv_2606_08317#p16:332:343-1011

### Internal

- internal receipt: query "primary checkout is then touched only by the dispatcher" | repo seldon@0d980545529e93b51a9a58fa2cd4156acb154496 | hits docs/decisions/REGISTER.md:9
- internal receipt: query "environment_packages" | repo squiddy@0a00d72d79c1799fc095f5b2cd25904318aecad6 | hits docs/design/2026-10-26_DN-051_the_kits_environment_is_a_committed_lock.md:15
- internal receipt: query "cross-project lease environment_in_flight producer consumer" | repo seldon@0d980545529e93b51a9a58fa2cd4156acb154496 | hits none

The register's AD-034 records (FRICTION-002, AD-034 ADDENDUM 01) state that a dispatched task runs in its own worktree
and the primary is touched only by the dispatcher's commits and merges: that is why a producer's session and gate can
hold nobody. squiddy's DN-051 (R-233) and its DN-043 R-188 record each kit pass against its environment, the
`environment_packages` checkouts included: the same pin R18 makes at a consumer's launch, already made by squiddy's
pass. Station (a) itself (QC-002, AD-037-R6) came from SQ-015's kit pass and was written before AD-034 put every task
in a worktree (2026-10-14 against FRICTION-002's 2026-10-17): it locked the repository because, when written, a
session did work in the primary.

## 3. Rulings

- **AD-037-R17. Station (a) holds a consumer on a producer's lease only while the producer can be changing what the consumer reads: in the producer's pass and merge phases, when the lease records no phase, and in any phase while the producer's task writes, by path, the consumer or a repository the consumer reads.**
  The pass lease records `phase` (`pass`, `session`, `gate`, `merge`) and `phase_since`; the holder marks them
  (`mark_phase`). A lease starts in `pass`; the serial pass marks `session` before the CLI runs, with `writes` (the
  Repo line's other repositories); a gate marks `gate` for its run and puts the previous phase back; the finish marks
  `merge` when it starts and whenever it takes the lease. A lease with no phase is a holder running code from before
  this ruling and holds, as before (fail-safe). A refusal is recorded once per holding window (`acquisitions` and
  `windows`), so a serial producer's one lease can refuse in its pass and again in its merge.
- **AD-037-R18. A launch records, for each producer its environment names, the revision of the producer's primary checkout it read: `pins` in the premise review, `{head, branch, dirty}`.**
  A consumer imports the producer's working tree live (section 1 item 1), so the pin is a record of the version run
  against, not an isolation. A producer that merges during the consumer's session changes the code under it, as it
  always could; the pin says from which revision.
- **AD-037-R19. Every `environment_in_flight` refusal and `seldon dispatch status` say, for each producer lease, who holds it, on which task, in which phase and since when, why it holds this project or not, and the progress of the gate it is running.**
  The refusal's `held` carries the holder, task, `acquired_at`, `phase`, `phase_since`, `writes`, `why` and `gate`
  (`gate_progress`); the dispatcher prints one line per lease. `status --json` adds `environment` (`held`,
  `not_holding`, `pins`) and `lease_gate` for this project's own running gate; the text form prints each.
- **AD-037-R20. A running gate's output reaches the dispatch log line by line while it runs: the declared pass record's too, in the task's gate log beside the gate command's, and the lease names that log and where this run starts in it.**
  `run_check(stream_to=...)` appends each line as it is printed (stderr merged into stdout), between a `=== <time> |
  gate record | <command>` line and an `EXIT=` line; the tail is still kept for the record. `gate_progress` reads
  the log from the run's offset: wall seconds since start, lines, the last line, how long ago the log last grew, and
  whether `EXIT=` is written. A log that stopped growing is what tells a hung gate from a running one.
- **AD-037-R21. Every gate record carries its wall-clock start and end, its wall seconds and the seconds the host slept, from its power log; time shown to a person is wall time.**
  `seconds` stays monotonic (the work done). `asleep_s` comes from `pmset -g log`, read only when wall and monotonic
  seconds differ by more than 2 s, and is null, never zero, where the host has no power log or it does not reach back
  to the gate's start. `seldon qc chart`'s gate line uses wall seconds; the slow-gate warning (AD-034-R36) stays on
  monotonic seconds, because a host that slept through a gate did not make the gate slow.

## 4. What this does not change

1. A consumer still never launches while a producer fast-forwards or numbers its register, and a producer's Desktop
   commits remain outside any lease.
2. A parallel supervisor (`max_parallel` above 1) holds the pass lease only to merge; it marks `merge` when it does.
   No repository runs parallel today.
3. The session's own Stop gate runs inside the session phase and holds nobody; only the merge round's gates mark
   `gate`.
4. What the waiting costs is still the producer's: squiddy's three-run kit pass is squiddy's (SQ-138), and R9's
   instrument is ruled in AD-036 ADDENDUM 15.
