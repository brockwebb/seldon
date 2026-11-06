# RESULT: SEL-023 (task 841bd7c7): a consumer filing is a kind the registrar accepts, a hand task is refused by the dispatcher, a filing is written and registered in one call, and every pass pushes

**Date:** 2026-11-06. **Branch:** `worktree-delegated-honking-lighthouse` (the dispatcher merges it).
**Rulings:** AD-036-R17 and R18 (`docs/design/AD-036_ADDENDUM_10_a_filing_is_a_kind_and_a_consumer_reports.md`);
AD-038-R19, R20 and R21 (`docs/design/AD-038_ADDENDUM_08_hand_dispatch_one_call_filing_and_a_push_on_every_pass.md`).
Records in `docs/decisions/register/pending/` (00001 to 00005), numbered on main by the merge step.
**Tests:** `tests/test_sel023_filing_kind_hand_dispatch_file_and_push.py` (36). Suite results: §6.

Recall used: seldon:2026-10-28_SEL-013R_a_consumer_filings_answer_files_its_own_return_RESULT, seldon:AD-036-R16, seldon:AD-036-R12, seldon:2026-10-26_SEL-011_registration_refuses_what_dispatch_would_refuse_and_every_non_candidate_gets_a_reason_RESULT, seldon:2026-10-15_DESK-001_desktop_writes_are_committed_RESULT

## 1. What was measured before building

- **The squiddy filing and its ADDENDUM 01 were read in full** (the task's instruction). Observation 6 is half right
  on seldon's own log. The Desktop commit `428a4c89` (13:07:54Z, 2026-11-03) went out at the next pass, 13:11:50Z
  (`push: pushed 1 commit(s)`, `logs/dispatch/seldon_dispatch.rotated_20261104T021957Z.log`): a pass with nothing
  eligible already pushed. The passes that did not push were those that exited on a held lease, those with a claim
  in flight, and those the graph outage ended. Also, launchd starts no pass while a serial holder runs its session,
  so a commit made during an hour's session waited the hour. Part D closes those exits; it does not add a push to
  passes that already had one.
- **squiddy 6ffde0f7 and 18001e38 are already `superseded`** in squiddy's graph (read 2026-11-06, both created
  2026-10-20). No pass lists a terminal task, so the retag Part E asks squiddy to do has nothing to act on. The return
  says so and asks squiddy to confirm, retagging only a filing still open (§5).
- **"The system CLAUDE.md that `seldon go` embeds, under the Desktop section"** is `_ROLE_SECTION` in
  `seldon/commands/go.py`: the only Desktop section `seldon go` sends, and the same in every project.
  `~/GitHub/CLAUDE.md` has no Desktop section and is in no repository. The rule went into `_ROLE_SECTION`, which is
  tracked, tested and reaches every consumer's Desktop.

## 2. What landed, by Part

**A. `**Kind:** filing`** (AD-036-R17). `seldon/core/dispatch.py`: `HEADER_KIND`, `parse_kind`, `kind_of_text`. In
`static_checks` a filing returns at once, as not a candidate with reason `filing`, and no failures: any other header
it sets is ignored, not refused. `evaluate` reads `task_kind` from the graph before the file, so an older filing
retagged with `seldon task update --kind filing` lists as `filing`. In `register_task_file` a filing skips the
design-note reference, criteria, premises, the governing-note verdict, After/Answers/Found in, recall and
constraining rulings. It records `task_kind: filing` and `filed_by`. It still meets git recoverability (registration
commits it), the number check and a repeated `Kind:` header. Without the line, the same file is refused as before
(fixture: `test_without_the_kind_line_the_filing_is_refused_as_today`). The squiddy filing in this tree had no
`Kind:` line. Two header lines were added (commit `0c37d62`; it was committed and unregistered, so no registered hash
bound it), and it is registered as **647df468**, a filing filed by squiddy.

**B. `**Dispatch:** hand`** (AD-038-R19). `parse_dispatch` and `hand_message`. Registration accepts the task and
records `dispatch_mode` and `dispatch_launcher` (the prose after `hand`). The dispatcher lists it as
`not_a_candidate: dispatch_hand` with a line naming who launches it, reading the graph before the file. Any other
value is `dispatch_unparsable`. `seldon task update --dispatch hand|dispatcher` sets it on a registered task.

**C. One call writes, commits and registers** (AD-038-R20). `seldon/core/filing.py` holds `filing_lock`, a flock on
`filings.lock_file` built on the dispatcher's own `Lease`/`acquire_waiting`, and `file_task`.
`seldon cc file --project <repo> --content-file <path> [--name]` and the MCP tool `seldon_cc_file(content,
project_dir, filename)` write the file and register it under the lock (registration commits it through the hooks,
with the AD-038-R18 retry). A refusal deletes only the file the call wrote, and an existing path is refused. The pass
takes the same lock (`_filing_guard`, waiting up to `filings.lock_wait_s`) before its sweep, reconcile, cadence and
candidacy, and releases it before any launch (`_release_filing`, serial and parallel). A pass that cannot take it
evaluates nothing and prints why. `seldon cc return` writes and registers under the consumer's lock.
`seldon_commit_governed` and `seldon commit-governed` register each committed base task file no task holds (never an
addendum, RESULT or OODA record) after the commit. A refused registration is reported with the file left committed,
so the tree stays clean. Fixture: `test_cc_file_writes_commits_and_registers_under_the_lock_a_pass_cannot_enter`
runs a pass inside the window: it sees `?? cc_tasks/...` and is refused the lock, so it evaluates nothing.

**D. The pass pushes** (AD-038-R21). `seldon/commands/dispatch.py` adds `_push_unless_tried` at the end of every pass
(in the `finally` around `_pass`), on the lease-held exit, and on each holder inspection tick (`_pushing` around
`holder_inspector`). A per-pass record of the HEAD already tried (`_PUSH_TRIED_AT`, reset when a pass begins) keeps an
idle pass to one `push:` line, so the serial transcript is unchanged, while the next pass still retries a failed
push. STOP, `enabled: false`, an inherited API key and a missing commit gate still end the pass before the push.

**E. The consumer rule and the return.** `seldon/commands/go.py` `_ROLE_SECTION`, Desktop section: "A Consumer
Thread Reports; It Does Not Fix (AD-036-R17)". It says to file with `seldon_cc_file`, headed `**Kind:** filing` and
`**Filed by:**`. Registration refuses a filing whose headings or line-leading bold labels carry a fix
(`filing_designs_fix`, patterns in `filings.fix_headings`; squiddy's own filing passes the check). An Issue has no
field naming a producer, so for Issues the rule lands in what `go` sends, not in a refusal. AD-036-R18:
`resolve_answers` resolves `**Answers:** <this repo>:<ref>` here, requires a filing, and returns to its `Filed by`
(or `--to`). `write_return` numbers the return by the consumer's most common prefix and walks the filing to
`completed` once the return is registered. `seldon cc return --answers` supplies the value for a task file with no
header, which is SEL-023's own case. The return to squiddy: §5.

## 3. Deviations, with grounding

1. **The retag in Part E is not performed in squiddy:** both tasks are already superseded (§1). The return names
   the retag command for any filing still open and asks for nothing else.
2. **The "system CLAUDE.md" is go's Desktop section** (§1), not `~/GitHub/CLAUDE.md`.
3. **A clean tree is not a precondition of the push.** The task says "a pass that ends with the branch ahead and a
   clean tree pushes". A dirty working tree changes nothing about which commits are pushed, so the push does not wait
   on it; the stated case is a subset of what now happens.
4. **Tests were written after the code within this session, not before** (CLAUDE.md §5 asks for test-first on a bug
   fix). Each fixture states the incident it replays.

## 4. Not done, and why

- The race a Desktop opens by writing through the Filesystem tools and then calling `seldon_commit_governed` is
  narrowed (one call instead of two), not closed. `seldon_cc_file` closes it, and `go` names it. AD-038 ADDENDUM 08
  §4.3 records this.

## For squiddy

**Title:** SEL-023 answered the consumer filing of 2026-11-03: confirm the two hazbrief filings are closed and change nothing else

seldon SEL-023 answers squiddy's filing of 2026-11-03 (registered in seldon as 647df468, a `**Kind:** filing`) and its
ADDENDUM 01. What landed in seldon, on main once SEL-023 merges:

- (a) A consumer filing headed `**Kind:** filing` and `**Filed by:** <repo>` registers in the producer's graph with
  no candidacy headers. It is never a dispatcher candidate (listed as `filing`) and closes when the task answering it
  files its return, or by `seldon task withdraw` (AD-036-R17). A header-less filing registered earlier is retagged
  by one `seldon task update <id> --kind filing`.
- (b) Both. The rule is in the Desktop section `seldon go` sends ("A Consumer Thread Reports; It Does Not Fix"), and
  registration refuses a filing whose headings carry the producer's fix (`filing_designs_fix`). Issues have no field
  naming a producer, so for an Issue it is the rule alone.
- (c) A mechanism. `seldon_cc_file` (MCP) and `seldon cc file --project <repo> --content-file <path>` write, commit
  and register a task file in one call, under a filing lock the producer's pass also takes (AD-038-R20).
  `seldon_commit_governed` on an unregistered `cc_tasks/` task file registers it in the same call.
- Observation 6: every dispatcher pass now ends by pushing what main is ahead by, including a pass that finds the
  lease held and each holder tick during a session (AD-038-R21). A Desktop commit reaches origin within one poll
  interval in any repository with a dispatcher.
- `**Dispatch:** hand` (your W7): the dispatcher never launches such a task (AD-038-R19).

What squiddy does, in this order:

1. Read the state of the two filings the request named: `seldon task show 6ffde0f7` and `seldon task show 18001e38`.
   Both read `superseded` in squiddy's graph on 2026-11-06, so no pass lists them and there is nothing to retag.
2. Only if either is open again: `seldon task update <id> --kind filing` (one call each; needs seldon main at or
   after SEL-023's merge).
3. Nothing else. Write the RESULT saying which of 1 or 2 applied.

## 5. The return

- The squiddy filing is registered in seldon as **647df468** (`task_kind: filing`, `filed_by: squiddy`). Its event
  line was committed by its registration (`9c2ec2c`).
- `python -m seldon cc return <SEL-023 task file> --answers seldon:647df468` (this branch's code) wrote
  `squiddy/cc_tasks/2026-11-06_SQ-123_sel_023_answered_the_consumer_filing_of_2026_11_03_confirm_the_two_haz.md`. It
  was registered in squiddy's graph as **da244cbe** and committed on squiddy main by its registration, through
  squiddy's hooks: `343e8a8e` (the file) and `f9955059` (its event lines). squiddy's tree is clean afterwards. Its
  `**Returns:**` header names `seldon:841bd7c7-…` (SEL-023). It is not pushed from this session; squiddy's dispatcher
  pushes it on its next pass (that repository's idle pass already pushes).
- The return closed the filing: 647df468 `proposed -> completed`. The lines were committed here as `c2c220f`.
- **A defect found by the dry run and fixed here.** The allocator offered **SQ-121**, which squiddy's graph already
  holds as an idea (`f5977b0f`, "SQ-121 (idea, no file yet): ..."). `numbering._DESC_RE` required the colon directly
  after the token, so that holder was invisible to the allocator and to `number_taken`. The regex now admits one
  parenthetical before the colon (`b5a6947`, test `test_a_numbered_idea_with_a_parenthetical_holds_its_number`). The
  fix only makes the allocator see more holders, never fewer. Re-run, the allocator gave SQ-123 (after SQ-122, also
  an idea).
- SEL-023's file carries no `**Answers:**` header, so `seldon cc complete` and the dispatcher's merge-time writer
  apply no return gate to it. The return was filed by this session, which is why `--answers` exists.

## 6. Verification

- `tests/test_sel023_filing_kind_hand_dispatch_file_and_push.py`: 40 passed (36 plus the 4 parametrized cases of the
  numbering fix).
- Related subset (every `test_dispatch*`, SEL-013R, DESK-00x, go, MCP-001, MCP tools, PRUNE-002, SEL-011, NUM-001R,
  SEL-021, SEL-022, cc register, FRICTION-001/002, SEL-018), run before the numbering fix: **579 passed, 1 skipped,
  EXIT=0** (12 min 46 s, `-n 6`). The serial transcript test is among them and passes unchanged.
- NUM-001R after the numbering fix: 39 passed.
- Full suite on the branch's final code (`python -m dotenv -f .env run -- python -m pytest -n 6 tests/`):
  **3207 passed, 7 skipped, 2 failed** (23 min 13 s). Neither failure is this task's:
  - `test_pa002_release_resolve::test_rebuilding_the_served_release_reproduces_the_served_index`:
    `release_unavailable ... no commit of squiddy/graphs/library/exports/EXPORT_VERSIONS.md carries 7b72aaa89fe005d3`,
    the library-index drift known on main (Issue dbe38fac). This branch touches neither the test nor `prior_art.py`.
  - `test_dispatch_parallel::test_two_disjoint_non_exclusive_tasks_run_concurrently_and_both_merge`: a timing
    assertion under `-n 6`, known to flake; **passed alone** (1 passed, 36 s).
- `seldon dispatch part-complete` ran for A to E, with no stop. Tokens at E: 333,927, against the 0.8M stop.
- Live: the squiddy filing registered as a filing, its return filed and registered in squiddy, the filing closed
  (§5).
