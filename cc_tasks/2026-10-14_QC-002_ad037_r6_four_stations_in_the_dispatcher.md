# QC-002: AD-037-R6's four inspection stations in the dispatcher: premise review, first article, milestone with earned value, andon with huddle. Zero model calls.

**Repo:** seldon. L4: commit, merge, push.
**Date:** 2026-10-14. **Authored by:** a Desktop session in squiddy (SQ7), on seldon's queue because the stations live in `seldon/core/dispatch.py` and `seldon/commands/dispatch.py`.
**Governing:** `docs/design/AD-037_in_process_quality_control_for_dispatched_sessions.md`, R6 (a) to (d), R7, R8, R9. No new design note: every ruling this task builds is accepted and on main (QC-001 Part B). AD-032 FC-15 and FC-28, FC-29 for the chart and the andon.
Also read:
- `cc_tasks/2026-10-11_QC-001_..._RESULT.md` (what QC-001 built: `seldon qc calibrate-judge`, the `checker` role, `criterion_unmarked`);
- `squiddy/cc_tasks/2026-10-13_SQ-015_..._RESULT.md` "Kit pass" (MODEL-003 merged into this checkout one minute into a squiddy kit pass: a cross-project environment change under a running session);
- `squiddy/cc_tasks/2026-10-12_SQ-013_..._RESULT.md` Part A (the first-article inspection done by hand, the shape station (b) automates);
- the five estimate-versus-actual pairs in section "The spend data" below.

Glob and read every sibling `*QC-002*ADDENDUM*.md`.
**Framework layer served (DN-005 §5 rule 1):** none (dispatcher control).
**Model:** primary
**Spend:** est. 1.5M tokens. Basis: SQ-012 to SQ-015 ran at 0.16, 0.58, about 0.6 and 0.64 of their estimates, all kit work of this shape; SQ-010, the one task with no stop condition, ran at 2.2. This estimate takes 1.5M as the ceiling a stop condition holds, not a prediction. Zero model calls beyond the session: the stations run `check:` commands; the judgment sampler is built and wired but calls nothing until QC-003 supplies a calibrated checker (R3, R5).
**Network:** none beyond git push.
**Exclusive:** yes

## The spend data

| task | estimate | actual | ratio |
|---|---|---|---|
| SQ-010 | 5M | 10.99M | 2.2 |
| SQ-012 | 6M | 0.94M | 0.16 |
| SQ-013 | 1.2M | 0.70M | 0.58 |
| SQ-014 | 0.6M | 0.36M plus an unmeasured first session | about 0.6 or more |
| SQ-015 | 1.5M | 0.956M | 0.64 |

These are the first points for FC-15's chart (R8, CPI). The estimates were Desktop guesses with no method; the chart is what replaces guessing.

## Stop condition (AD-032 FC-17; AD-037-R6 d, by hand one last time)

- **Tokens.** Print cumulative session tokens at every Part boundary. If they pass 1.8M, finish the Part in hand, write the RESULT, and stop.
- **Dogfood.** This task is the first article for its own station (b): after Part A lands, the dispatcher's next pass must evaluate THIS task's premises and Part records. If it cannot read them, stop and report; do not patch the records by hand.
- **Failures.** A step that fails twice the same way becomes a finding with a Seldon issue, not a third attempt.

## Part A: station (c), milestone with earned value, and the `part_complete` record

1. A dispatched session appends `part_complete` to the event store at each Part boundary: task id, Part name, planned share (from a `**Parts:**` header listing each Part's share of the estimate, which this task carries below), tokens used so far (from the CLI's stream-json usage), wall time.
2. The dispatcher's pass reads them, computes CPI = earned value / actual cost (earned = sum of planned shares of completed Parts, actual = tokens used over the estimate), and records `milestone` with the CPI.
3. At each `part_complete` the pass runs that Part's `check:` commands (R1 marks them) and records pass or fail. A failed check writes the session stop (station d). CPI below 0.8 opens a huddle record without stopping.
4. Tests: a planted `part_complete` with a failing `check:` stops the session; CPI below 0.8 writes a huddle and does not stop; a task with no `**Parts:**` header is refused at registration with `parts_undeclared` (tasks registered before this merge are baseline, as `criterion_unmarked` was).

**Parts:** A 0.35, B 0.25, C 0.25, D 0.15.

Acceptance:
- `check: pytest tests/test_dispatch_milestone.py -q` passes, and each of its three plants fails on HEAD before the change.
- `check: seldon cc register` refuses a fixture task with no `**Parts:**` header.

## Part B: station (a), pre-dispatch premise review

1. A task declares its premises in a `**Premises:**` block: each line `premise: <statement> | check: <command>` for a premise a command can decide (a count, a path exists, a state, a version, a label free), or `premise: <statement> | judgment: <why no command decides it>`.
2. The dispatcher runs every `check:` premise before launch. A false premise refuses the launch with `premise_false`, files an Issue naming the premise, and records `dispatch_refused`.
3. One premise is added to every task by the dispatcher itself, from SQ-015's finding: no other project's dispatcher holds a lease on a repository this task's environment names (`kit.yaml environment_packages` for squiddy; for seldon, the repositories in `decisions.repositories`). Two project dispatchers each at `max_parallel: 1` still ran MODEL-003 under SQ-015's kit pass. Record the refusal as `environment_in_flight`.
4. `judgment:` premises are listed in the launch record for the R2 checker and are not evaluated until QC-003.
5. Tests: a planted false `check:` premise refuses; a held lease in a named sibling repository refuses; a task with no premises block launches (premises are optional until the first task carries them; say so in the RESULT).

Acceptance:
- `check: pytest tests/test_dispatch_premises.py -q` passes, each plant failing on HEAD.
- `check:` `seldon dispatch status --json` shows the premise outcomes for the last pass.

## Part C: station (b), first article, and station (d), andon and huddle

1. **First article.** A task marks a loop with `**First article:** <loop name>, <check command over the first unit's output>`. The session stops after the first unit and appends `first_article` with the output path; the dispatcher runs the check and either writes `first_article_pass` (the session continues on its next poll) or the session stop. The session waits on the record, not on a person: a pass record within `poll_interval_s` continues it; a stop record ends it; nothing within three polls is a huddle.
2. **Andon.** `seldon dispatch stop <task>` writes the session stop; a session reads it at every Part or loop boundary and halts, writing `andon_halted`. The dispatcher's hard stop (FC-32 toxic class, disk or spend ceiling) kills nothing by hand: it writes the stop and lets the session halt at its boundary, then reaps the lease only if the session has not written `andon_halted` within one poll interval (DN-006's rule on killing processes stands).
3. **Huddle.** `seldon dispatch huddle <task> --reading <r> --cause <c> --gate <g>` writes the huddle record FC-29 specifies: the reading, the cause one level down, and the gate that now prevents it. A huddle opened by CPI (Part A) or by a first-article wait carries its reading automatically and leaves cause and gate for the session or the operator to fill; `seldon go` lists open huddles.
4. Tests: first-article pass continues the loop; first-article fail stops; an operator stop halts at the next boundary; a hard stop with no `andon_halted` reaps after one interval and not before.

Acceptance:
- `check: pytest tests/test_dispatch_first_article.py tests/test_dispatch_andon.py -q` passes, each plant failing on HEAD.
- `check:` `seldon go` in seldon shows an open huddle planted by the test fixture, then none after it is closed.

## Part D: R7's reserve, R8's chart, R9's gate, and the doctrine

1. **R7.** The task's spend reservation (FC-11) sets aside 10% for inspection. The sampler's rate falls when the reserve is low; `check:` commands never skip. Record the actual inspection share per task.
2. **R8.** `seldon qc chart` prints per project: premise-false rate, first-article reject rate, milestone defect rate, CPI per task, huddles per task. First reading only, from the five tasks above (CPI only; the other rates are zero until stations run). FC-15's individuals chart draws once 10 tasks exist.
3. **R9.** `tests/test_dispatch_parallel_held.py` now checks that R6 (a) to (d) are live (the four station records exist in the code path) before any project may opt in; the disk preflight (SQ-010 ADDENDUM 02 D3.4) stays as the second condition. Do not change `max_parallel` anywhere.
4. **Doctrine.** The session-side protocol (what a dispatched session appends and when) goes into `docs/conventions/dispatched_session_protocol.md`, and `seldon go` for a CC session prints its three lines. Every task written after this merge carries `**Parts:**` and may carry `**Premises:**` and `**First article:**`.

Acceptance:
- `check: seldon qc chart` prints the five CPI rows with the values in the table above.
- `check: pytest tests/test_dispatch_parallel_held.py -q` passes.
- `check: seldon verify` passes.

## Report

Write the RESULT, under 50 lines, to `cc_tasks/2026-10-14_QC-002_ad037_r6_four_stations_in_the_dispatcher_RESULT.md`. It covers:
- tokens at each Part boundary and in total, against 1.5M, with this task's own CPI as the dispatcher computed it (the dogfood);
- each station's record names and where the dispatcher reads them;
- the premise, first-article, andon and huddle plants, each with its test and its HEAD failure;
- the chart's first reading;
- the full suite (passed, skipped, xfailed, deselected, failed);
- each constraint with its basis (measured, external, inherited, assumption): the 0.8 CPI line, the 10% reserve, the one-interval reap, the three-poll huddle;
- premises found wrong.

Then `seldon verify`, `seldon cc complete`, merge, and push. QC-003 (the first real calibration run, Opus generator halves judged by Fable, R3 and R5) is authored after this RESULT, with the stations' reserve measured here as its spend basis.
