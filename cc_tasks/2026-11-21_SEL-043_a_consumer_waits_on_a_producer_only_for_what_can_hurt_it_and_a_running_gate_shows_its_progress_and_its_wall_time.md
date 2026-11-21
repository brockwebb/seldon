# SEL-043: a consumer's dispatcher waits on a producer only for what can hurt it, a running gate shows its progress and its wall time, and a release's rows come from the kit

**Status:** proposed
**Author:** Desktop session (seldon, SLD-2), 2026-11-21, the Saturday batch. Answers three squiddy filings: `44ba49df` (a consumer's dispatcher waited hours on squiddy's lease after squiddy's session had ended), `083863ef` (three findings in the merge round that are seldon's), `9fb2e0b8` (an older release rebuilds under arm A's rule; the reader refuses by name). The cross-project lease question was first filed on 2026-11-06 and deferred by SLD-1 as needing a design note; this is that note and its build.
**Repo:** seldon (primary). squiddy and hazbrief-mcp are read, never written; Part F files the returns. L4: commit, merge, push in seldon.
**After:** none
**Governing:** AD-037-R6 station (a) (`environment_in_flight`: no other project's dispatcher holds its lease on a repository this project's environment names); AD-034 (worktree per task; the merge round; R16 to R18 the gate record); AD-036 (R9 the zero-model-calls instrument; R19 superseded releases; R24 held releases through the kit's accessor); SEL-041 (the gate planner and the gate-run record, which this task extends and must not duplicate). Number new rulings under AD-037 and AD-036.
**Model:** primary
**Spend:** est. 1.1M tokens. Basis: one measurement of refusals across the dispatching repositories, one design note, a narrower station, streamed gate output and two timestamps in an existing record, one instrument measured, one error mapped, one return. Zero model calls.
**Network:** none
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes (edits `seldon/core/stations.py`, `seldon/commands/dispatch.py`, `seldon/commands/dispatch_worktree.py`, `seldon/core/prior_art.py`)
**Parts:** A 0.20, B 0.10, C 0.25, D 0.20, E 0.15, F 0.10.
**Premises:**
- premise: the lease filing is on main | check: test -f cc_tasks/2026-11-13_filing_from_squiddy_a_consumer_s_dispatcher_waited_hours_on_squiddy_s.md
- premise: the merge-round findings are on main | check: test -f cc_tasks/2026-11-15_filing_from_squiddy_what_squiddy_s_merge_round_pass_now_takes_and_writ.md
- premise: the rebuild filing is on main | check: test -f cc_tasks/2026-11-13_filing_from_squiddy_older_release_rebuild_readable_reader_refuses_by_name_and_rebuild_reads_arm_a_rule.md
- premise: SEL-041's gate record exists to extend | check: sh -c "ls cc_tasks/2026-11-21_SEL-041_*_RESULT.md" | at: launch

Read the three filings and SEL-041's RESULT first.

## The condition

1. **A consumer waited hours on a producer that was not touching it.** On 2026-11-13 hazbrief's only queued task was refused `environment_in_flight` from 18:05Z because squiddy's dispatcher held its lease. squiddy's session had ended at 17:37Z; the lease was held for the merge round's gate (three whole-suite runs, 2h05m to 2h40m). squiddy's work touched only squiddy's repository. The operator read the refusal as squiddy working on hazbrief's tree. Nothing shown said what the lease covered, what phase the holder was in, or how far along it was. The seldon thread has itself held three seldon tasks behind hazbrief's queue this month for the same station.
2. **A running gate is invisible.** `stations.run_check` captures the gate's output until it exits and keeps the last 1,500 characters; a two-hour gate and a hung one look the same from seldon.
3. **Gate seconds leave out sleep.** `time.monotonic()` does not advance while a Mac sleeps: a pass recorded 7,734 s ran 10,834 s by the wall clock.
4. **AD-036-R9's instrument is 41 percent of a squiddy suite run** (1,278 s of 3,095 s, about 9.8 GB at peak), run three times per pass, for an assertion that is a property of the commit.
5. **`rebuild_release` names the kit's row-reading arguments itself** and so reads the corpus checkpoint under arm A's rule: 3 of 2,261 units differ from what the release served, and a graph with no arm A lines gets `release_unavailable` for every older release. A reader's `IndexSchemaError` would reach seldon as a traceback.

## Prior art

Named here from memory and not fetched by the Desktop thread; this task has no network, so each is cited from seldon-biblio or the squiddy library if held, otherwise as unfetched, and the addendum says which:

- Readers-writer locking and its granularity (Gray et al. 1976, "Granularity of locks and degrees of consistency in a shared data base"): a lock is taken on the smallest object that protects the invariant, for the shortest time.
- Snapshot isolation (Berenson et al. 1995, "A Critique of ANSI SQL Isolation Levels"): a reader works from the version that was current when it began and is not blocked by a writer.
- Version pinning: a consumer builds against a recorded revision of a dependency (a lockfile), and the producer's work in progress is invisible to it until a new revision is published. Git's own model: a worktree's commits change no other checkout until a ref moves.

Seldon's own: AD-034 already runs every task in its own worktree, so a producer's primary checkout changes only at the merge's fast-forward. Whether station (a) was written before that was true is Part A's first question.

Run `seldon prior-art search` (internal and library arms) before the note.

## What to build

**A. Measure first, read only.** (1) What station (a) protects: for each consumer (hazbrief-mcp, aacps-ai-policy, factory, seldon, squiddy), what a dispatched session actually reads from each producer it names and from where (an installed package, an editable install of the producer's primary checkout, a path into its tree, its served graph), and at which moments the producer changes that thing (session, gate, fast-forward, release). (2) Every `environment_in_flight` refusal in every project's dispatch log and event store: count, hours waited, and the producer's phase during each (session, gate only, merge). (3) seldon's own cost for R9's instrument: seconds and peak memory of `test_the_suite_invokes_no_claude_by_default` in a full run.

**B. The design note** (AD-037 addendum), from A's numbers. Expected shape, to be confirmed or overturned by A: the station holds a consumer only across the window in which the thing it reads from the producer can change under it, and names that window; a producer's session and a producer's gate that touch nothing a consumer reads hold nobody. If A shows a consumer reads a producer's primary working tree live, the rule is a pin (the consumer records the producer revision it launched against) and the note says what the pin is. `prior-art verify` passing before C to E.

**C. The station and what a waiting operator is shown.** Build B's rule, tests first, with a two-repository fixture: a consumer is not refused while the producer's gate runs; it is refused, briefly, across the window B names; every refusal's record and `seldon dispatch status` state the holder, its task, its phase, since when, and the gate's progress when there is one.

**D. A running gate.** The gate's output is appended to the dispatch log line by line while it runs (the tail is still kept for the record). SEL-041's gate-run record gains wall-clock start and end, and seconds asleep where the host's power log gives them; elapsed time shown to a person is wall time. Tests with a gate that prints over time and a stubbed power log.

**E. Two smaller answers.** (1) R9's instrument: from A's measurement, rule whether the assertion holds when run once per pass or by a cheaper instrument on the same subject (the filing describes one); change seldon's own test accordingly and state exactly what a consumer running the instrument may now do. If the cheaper form cannot be shown to catch a seeded model call, leave it and say so. (2) `rebuild_release`: map `IndexSchemaError` to `release_unavailable`; state in the return that seldon wants the kit to expose one call that returns a release's rows under the rule it was cut under, and use it behind a version check when present. No change to which rows are read until that call exists; record the 3-of-2,261 difference as a known limit beside AD-036-R19.

**F. Returns.** One to squiddy answering all three filings, as a report of what changed and the one thing seldon asks for (E.2); a task there only for that. One line to hazbrief-mcp and to factory through the same return mechanism only if C changed what their dispatchers do.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 1.35M.

## Deliverables

A to F with tests; A's tables; the note and its rulings; the three filings answered; `cc_tasks/2026-11-21_SEL-043_a_consumer_waits_on_a_producer_only_for_what_can_hurt_it_and_a_running_gate_shows_its_progress_and_its_wall_time_RESULT.md`.
