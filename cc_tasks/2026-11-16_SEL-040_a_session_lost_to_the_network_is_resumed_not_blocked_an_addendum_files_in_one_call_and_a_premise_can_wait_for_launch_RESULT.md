# RESULT: SEL-040, a session lost to the network is resumed, an addendum files in one call, a premise can wait for launch

**Date:** 2026-11-18. **Branch:** `worktree-vectorized-greeting-river` (not merged by this session; the dispatcher
merges on green). **Task:** `b4a94a6b`.
Recall used: none. Registration listed eight hits (FRICTION-002, SEL-004, SEL-005, the `precedes` RESULT, DESK-002,
the AD-028 amendment, SEL-016 and AD-038-R16). None of them was opened. What changed the approach came from the
operator's memory notes (worktree guard shapes, the full suite's known failures, how register records are made) and
from the code itself.

## In plain terms

- **A session cut off by the network is now resumed by the dispatcher.** If the laptop lid closes or the network
  drops, the session is recorded `interrupted`, not `stop_gate_unpassed`. Once the API answers again, the dispatcher
  relaunches it in the same worktree and tells it where it stopped. This happens at most twice; a third cut waits for
  a person. HB-189's real log tail drives the test.
- **An addendum is filed in one call.** `seldon cc file` / `seldon_cc_file` write and commit it under the filing lock
  and register nothing. An addendum to a task that does not exist is refused, and so is one that carries Spend,
  Network, Framework layer or Exclusive.
- **A premise can wait for launch.** End the premise line with `| at: launch`. A premise that only says "the task this
  one is After has finished" is refused, with a pointer to the After header.
- **Both of hazbrief's observations had seldon causes, and both are fixed.** Merges numbered pending register records
  and never projected them; hazbrief's Issue `0c4232cb` was written into seldon's graph by a call that named no
  project, and the reply never said where it went.

## Part A: rulings

- `docs/design/AD-034_ADDENDUM_10_a_session_its_transport_cut_off_is_resumed_and_the_merge_projects_what_it_numbers.md`:
  AD-034-R21 (the class), R22 (two resumes, then `interrupted_thrice`; tokens carried), R23 (redrive on the probe,
  reopen the kept tree, state the interruption), R24 (the merge projects what it numbers).
- `docs/design/AD-038_ADDENDUM_12_an_addendum_files_in_one_call_and_a_premise_can_wait_for_launch.md`: AD-038-R26
  (addendum in one call), R27 (`at: launch`), R28 (a premise restating After is refused), R29 (a create reply names
  its repository).
- Prior art: KEP-3329's pod failure policy and the CLI's documented worktree reuse are cited as the mechanisms
  adopted. Slurm's requeue on node failure is named and not fetched. The library arm (`prior-art search --library`)
  did not return within two minutes from this worktree, so whether seldon-biblio or the squiddy library holds it is
  unchecked. Internal receipts: "redrive", "kept worktree", "decision project", "filing lock", "premise at
  registration".
- `prior-art verify` gave PASS for both addenda; the verdicts are in `governed/ledger/events.jsonl`. Eight register
  records are pending in `docs/decisions/register/pending/` (00001..00008, `decided_by: cc:b4a94a6b`), to be numbered
  at merge. `seldon decision check`: register clean.

## Part B: resume

**Reproduced first.** `tests/fixtures/sel040/hb189_log_tail.jsonl` is hazbrief HB-189's real stream tail: the last
model turns, ten `api_retry` records (10 of 10, no status), the synthetic "API Error ... (ENOTFOUND)" and the `result`
record. It was cut by `docs/evidence/sel040/cut_fixture.py` with content elided. Before the change, the end-to-end
test failed with `assert 'stop_gate_unpassed' == 'interrupted'` (`docs/evidence/sel040/reproduction.txt`).

**Built** (`seldon/core/interruption.py`, wired into `dispatch_worktree.finish_session`, `dispatch._launch_inplace`,
`_start_claimed`/`_supervise`, `redrive.auto_redrive`):

- The finish classes the session's end before it records a block. Evidence: `transport_error` (the CLI's own
  synthetic API error matching `dispatch.interruption.transport_patterns`), `retries_exhausted` (`api_retry` reached
  `max_retries` after the last model turn, not a 4xx refusal), and `host_slept` (a Sleep in `pmset -g log` between
  the last model turn and the end, used as corroboration).
- `interrupted` → blocked with `failure: interrupted`. The next pass probes the API's host with a TCP connect (no
  model call), records `interruption_probe` when its answer changes, and redrives only on `ok`. The relaunch passes
  `--worktree <kept name>`, keeps the first launch's `base`, and appends the RESUMED clause: when it was cut off, on
  what evidence, which resume of two, the branch, its last commit and subject, and the tokens already spent.
- The third interruption gives `interrupted_thrice`, which is not redriven. `dispatch_launched.resume.prior_tokens`
  is added to the token reading at the Stop gate's ceiling, the dispatcher's hard stop and `part-complete`.

**What the dispatcher can and cannot tell apart.** For HB-189 the host log shows "Entering Sleep state due to
'Clamshell Sleep'" at 10:37:00Z, 16 s after the last model record. A closed lid and a dropped network both reach the
CLI as transport failures and are both resumed. The host log, when it can be read, says which one it was. A process
killed from outside (a signal exit with no `result` record and no dispatcher stop) is ambiguous: an OS kill, an
out-of-memory kill and an operator's kill look alike. Without a host Sleep beside it, it is blocked for a person as
before, and `interruption.undecided` says why. A finish with no transport evidence carries no `interruption` field,
so an ordinary failure's record is unchanged. The serial transcript fixture still reproduces.

**Tests:** `tests/test_sel040_interrupted_session_resumed.py`, 19 tests:
- End to end on Neo4j with the stub CLI: the HB-189 tail is `interrupted`; a probe that fails holds the task and a
  probe that answers redrives it, reopens `.claude/worktrees/a`, merges, and the first session's work is on main; a
  third interruption is `interrupted_thrice` and not relaunched; a committed RESULT is never redriven.
- Unit tests: the classifier's exclusions (`no_progress`, `ceiling`, a dispatcher stop, a committed RESULT); a gate
  that only refused does not hide a later cut; a killed session counts only with a host Sleep beside it; a 401 is not
  transport; parsing of the power log; the probe; the config refusals; tokens carried.

**Not exercised live:** the real CLI reopening a kept `-p` worktree by name. The docs say it "opens it instead of
creating a new one" and, with `baseRef: head`, "reopens the worktree at its old tip". The stub CLI does the same. If
the real CLI ever cut a new tree instead, the RESUMED clause tells the session to merge the kept branch first. The
first real interruption will show which happens.

## Part C: an addendum in one call

`seldon/core/filing.py::file_addendum`, reached from `file_task` for any `*_ADDENDUM_*` name, so both `seldon cc
file` and `seldon_cc_file` get it. The base stem is read from the name. The base file must exist and be registered
(`addendum_without_task` otherwise, and nothing is written). AD-038-R24's four headers are still refused. The file is
written, `git add` + `git commit -- <path>` under the filing lock, and removed again if the commit fails. The reply
names the base task and the commit, and no artifact is created. Tests (in
`tests/test_sel040_addendum_files_and_launch_premises.py`): a running task's addendum; an addendum to a task that
does not exist (refused, removed); a base file that exists but is unregistered (refused); each of the four headers
(refused); the MCP tool.

## Part D: a premise that waits for launch

**Measured first:** every `check:` premise is already re-run at launch for the chosen task in the serial pass
(`_pass` → `_premise_review` → `dispatch_stations.premise_review` → `stations.review_premises`). The parallel pass
runs none, and both dispatching projects are serial (`max_parallel: 1`). This is kept as a test. Registration was the
only gap.

**Built:** `parse_premises` reads an optional `| at: launch`; any other value is unreadable.
`review_premises(stage="registration")` records such a premise as `at_launch` without running it, and the R18 retry
uses the same stage. `after_restating_premises` refuses at registration (`premise_restates_after`) a premise that
names an After predecessor (its stem or number, e.g. `HB-189`) together with its finishing (RESULT, complete,
finished, merged, done). The refusal points to the After header. A premise about the predecessor's output is kept.
Tests cover parsing, the registration deferral, the refusal and its non-trigger cases, and station (a) refusing a
false launch premise end to end.

## Part E: the two observations

Full write-up: `docs/evidence/sel040/part_e_findings.md`.

1. **HB-186's eleven records.** The graph never had them, so nothing lost them. HB-186 accepted them as pending
   records in its worktree, and its own verify ran with them moved aside. Its merge numbered them (seq 514..524,
   commit `cb9b3636`) and `number_merged_register` never projected. HB-187's `decision project` at 04:26:58Z the next
   day created them. The cause is seldon's. **Fixed:** the merge projects what it numbers (AD-034-R24) and records
   the result on `register_numbered.projected`. Test:
   `test_loop001_register_seq.py::test_the_records_a_merge_numbers_are_projected_into_the_graph`, which failed before
   the change.
2. **`seldon:issue-0c4232cb`.** Recall names an Issue by the store it was folded from, and that is correct here: the
   Issue's only `artifact_created` is in seldon's store (event `755661cb`, Desktop session `b67f54dd`). Desktop's
   `SELDON_DEFAULT_PROJECT` is seldon, `seldon_issue_create` with no `project_dir` resolves to it, and the reply never
   named the repository. **Fixed:** `seldon_issue_create` and `seldon_task_create` now reply with `project: <name>
   (<path>)` and say when the default chose it (AD-038-R29). The Issue stays in seldon's graph, because moving it
   would mean writing into hazbrief's graph.

## Part F: return

Filed with `seldon cc return` (below). The return is built from the next section.

## For hazbrief-mcp

Nothing in this return is needed for the 2026-11-20 submission; it reports what seldon changed after hz-18's report of 2026-11-16, and nothing here asks hazbrief to act before then.

1. **A session the network cuts off is now resumed, not blocked.** The dispatcher records it `interrupted`, not
   `stop_gate_unpassed`. That happens when the session ends on the CLI's "API Error ... (ENOTFOUND)" or similar, or
   on exhausted API retries, without a committed RESULT; a closed lid shows in the host's power log, as HB-189's did
   at 10:37:00Z. Once the API's host answers, a pass redrives the task and relaunches it in the SAME worktree. The
   prompt tells the new session when it was cut off, which commit it stopped at, and that tokens already spent count
   toward the task's ceiling. This happens at most twice; a third cut blocks with `interrupted_thrice` for a person. A
   session that committed its RESULT is never resumed; the regate answers it as before. HB-189's case now needs
   neither a resume addendum nor a hand redrive.
2. **An addendum files in one call.** Call `seldon_cc_file` with the file named
   `<task stem>_ADDENDUM_<NN>_<slug>.md`. It is written and committed under the filing lock and registers nothing. The
   task must be registered, and the addendum still may not carry Spend, Network, Framework layer or Exclusive.
3. **A premise can wait for launch.** Write `- premise: <statement> | check: <command> | at: launch`. Registration
   records it without running it, and the dispatcher runs it with the other premises before the session starts; a
   false one blocks the launch with the premise named. Do not write a premise that only says the After task has
   finished (HB-192's "HB-189's RESULT exists"): the After header already means that, and such a premise is refused at
   registration with a pointer to it. A premise about what the predecessor produced is fine, marked `at: launch`.
4. **The eleven missing decision records (HB-187).** The graph never had them, so it did not lose them. HB-186's
   records were pending in its worktree, and HB-186's verify ran with them set aside. Its merge numbered them
   (HBD-435..441, and the amendments to HBD-390, 429, 431, 434) but nothing projected them until HB-187 ran `seldon
   decision project`. This was seldon's defect; the merge now projects what it numbers.
5. **`seldon:issue-0c4232cb`.** That label is correct: the Issue was written into seldon's graph, not hazbrief's. A
   Desktop call with no `project_dir` falls back to the default project, which is seldon, and the reply did not say
   so. Replies now name the repository written to. To have the Issue in hazbrief's own graph, re-file it there with
   `project_dir` given, and a seldon session will close seldon's copy as a duplicate.
6. **A correction to a belief hz-18 reported.** A consumer thread may file a report of what it experienced into
   seldon's `cc_tasks`, as hazbrief did on 2026-11-15 (`bbfd478f`). That is the route, and it is not writing another
   project's work.

## Verification

- Full suite, `python -m dotenv -f .env run -- python -m pytest tests/ -n 6`: **3448 passed, 5 failed, 7 skipped**
  in 36 min. The five failures are the known ones:
  - `test_pa002_release_resolve::test_rebuilding_the_served_release_reproduces_the_served_index` (library drift,
    failing on main).
  - Three `test_dispatch_parallel` timing tests, which pass when run alone (3 passed, 3 min 36 s).
  - `test_sel024_gate_record::test_fixture_a_regate_whose_gate_outlasts_lock_wait_does_not_refuse_a_concurrent_filing`.
    It also fails alone, and fails identically on main's code in a `git clone --shared` of main
    (`/tmp/sel040/main_clone.py`) at load average 6 to 14. Not a regression.
- The SEL-040 files: `tests/test_sel040_interrupted_session_resumed.py` (19) and
  `tests/test_sel040_addendum_files_and_launch_premises.py` (18) pass, along with the extended
  `tests/test_loop001_register_seq.py` (5).
- `seldon decision check`: register clean. `seldon verify` was not run, because it crashes in a worktree that holds
  pending records (known); the dispatcher's merge numbers the records.

## Spend

Zero model calls. Tokens at Part A's boundary: 392,105 (estimate 0.9M; stop at 1.1M).
