# SEL-006: `cc register` verifies and commits the governing design note with the task; the MCP server refuses on a stale HEAD; `qc.parts_baseline` in every project

**Repo:** seldon. Cross-repo by absolute path: `/Users/brock/GitHub/squiddy`, `/Users/brock/GitHub/arnold`, `/Users/brock/GitHub/ai-readiness-kg` (Part C, one config line each). L4: commit, merge, push in every repo touched.
**Date:** 2026-10-14. **Authored by:** a Desktop session in squiddy (SQ7).
**Governing:** AD-036-R4 (a design note needs a passing verdict before it is committed or governs a registered task); DN-006 ADDENDUM_03 §2 (a registered task file is committed by the dispatcher, not by a person); DN-046 R-202 (a process records what it loaded and re-checks it). No new ruling: Part A applies the ADDENDUM_03 entailment to the note the task names; Part B applies R-202 to the MCP server process.
**Issues closed:** `231c255c` (self-registering tasks are invisible to the dispatcher), `1fed4254` (Desktop edited a note after a running session committed it), `fed23c36` (MCP server runs pre-merge code), `f6c69653` (parts_baseline in the other projects).

Glob and read every sibling `*SEL-006*ADDENDUM*.md`.
**Framework layer served (DN-005 §5 rule 1):** none (registration and server hygiene).
**Model:** primary
**Spend:** est. 0.5M tokens. Basis: `seldon qc chart` on 2026-10-14 shows six tasks at 0.16 to 0.64 of estimate, QC-002 at 0.20; this is a smaller change than QC-002. Zero model calls.
**Network:** none beyond git push.
**Exclusive:** yes
**Parts:** A 0.5, B 0.3, C 0.2.
**Premises:**
- premise: QC-002's stations are on main | check: `test -f seldon/core/stations.py`
- premise: no in_progress task in seldon | check: `seldon task list --state in_progress | grep -q "No ResearchTasks"`

## The condition

A Desktop session has no git. Everything it writes is untracked until a tool commits it. `cc register` already commits the task file (DN-006 ADDENDUM_03). The design note the task names is not committed by anything until the CC session's Step 0, so: the dispatcher cannot launch the task (c7 dirty tree), the operator pastes a launch line, and twice this week a Desktop session edited the note after a session had committed it. Six of the last seven squiddy tasks needed a paste for this reason alone.

## Stop condition (AD-037-R6 d, now by the dispatcher)

Tokens 0.6M. A step that fails twice the same way becomes a finding with a Seldon issue, not a third attempt.

## Part A: registration verifies and commits the governing note

1. `seldon cc register` reads the task's `**Governing:**` line. For each path under `docs/design/` it names that git does not track or that has uncommitted changes:
   - run `seldon prior-art verify` on it, recording the verdict (AD-036-R4). A FAIL refuses the registration with `governing_note_unverified`, naming the receipt that failed, and commits nothing.
   - on PASS, stage the note, its addenda beside it, and the task file, and commit them in ONE commit through the hook (QC-001 premise 6: the note's register records are staged with it, so run `seldon decision` label discovery first and refuse with `ruling_unrecorded` if a labelled ruling in the note has no record; the CC session's Step 0 then records them before the commit, as SQ-012 to SQ-015 did).
   - Decide which of the two orders holds and say so in the RESULT: records-before-commit (registration records the rulings itself, `decided_by: desktop`, from the note's bytes, AD-033-R3) is the one that removes Step 0 entirely. Take it if `seldon decision accept` is callable from registration without a model call; it is (the statements pass is separate, AD-033-R8, and stays in the CC session).
2. The `allow_untracked` flag is renamed in meaning, not name: it now means "commit what registration verified". A registration that leaves anything it read untracked is a defect; test it.
3. After registration the tree is clean on the paths the task names, so the dispatcher's c7 passes and the task launches on the next pass with no paste.
4. Tests, each failing on HEAD: an untracked governing note with passing receipts is committed with the task in one commit; a failing receipt refuses and commits nothing; a labelled ruling without a record is recorded by registration; a note with uncommitted edits after an earlier commit is committed as a new commit, never amended.

Acceptance:
- `check: pytest tests/test_cc_register_commits_note.py -q`
- `check: git -C /Users/brock/GitHub/seldon status --porcelain -- docs/design cc_tasks | wc -l | grep -qx 0` (run after this task registers its own RESULT, which has no note; the dogfood is the next Desktop-written task)

## Part B: the MCP server records the HEAD it loaded and refuses when the checkout moved

1. At start, `seldon-mcp` records seldon's HEAD and the sha256 of `models/registry.yaml` and `seldon.yaml`. Before every tool call it re-reads them. On a difference it refuses with `server_stale`: "seldon-mcp loaded <short> on <time>; the checkout is at <short>. Restart the MCP server (restart Claude Desktop)." The registry parse error of 2026-10-14 (`fed23c36`) must become that message.
2. Same check in the squiddy-library MCP, which imports squiddy.
3. Tests: a planted HEAD change after import produces `server_stale` and not the underlying error.

Acceptance:
- `check: pytest tests/test_mcp_server_stale.py -q`

## Part C: `qc.parts_baseline` in squiddy, arnold and ai-readiness-kg

1. Add `qc.parts_baseline` to each project's `seldon.yaml` with the baseline file listing tasks registered before this merge, as seldon's own does (QC-002 premise 9).
2. Every task registered after this in any project carries `**Parts:**` or is refused `parts_undeclared`.

Acceptance:
- `check:` `seldon cc register` on a fixture task without `**Parts:**` is refused in each of the three projects.

## Report

RESULT under 35 lines at `cc_tasks/2026-10-14_SEL-006_..._RESULT.md`: tokens per Part against 0.5M and the dispatcher's CPI; the order chosen in Part A.1 and why; the four Part A plants with their HEAD failures; the `server_stale` message verbatim; suites per repo (passed, skipped, xfailed, deselected, failed); constraints with their basis; premises found wrong. Then `seldon verify`, `seldon cc complete`, resolve the four issues, merge, push.
