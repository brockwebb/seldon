# RECALL-001: registration retrieves the repositories' own history (RESULTs, issues, decisions, dead-end branches) for every task, prints the hits into its launch prompt, and measures whether a hit changed the task

**Repo:** seldon. Cross-repo read by absolute path: squiddy's governed graphs for every repository Seldon serves. L4: commit, merge, push. Work on a branch; merge before each `part-complete`.
**Date:** 2026-10-17. **Authored by:** a Desktop session in squiddy (SQ8).
**Governing:** AD-031-R1 (rulings reach the task by retrieval from the governed graph), DN-009 R-40 / EX-REQ-13 in squiddy (internal precedent is half of prior art). This is the mechanism half of SEL-003; SEL-003's three-arm measurement (about 11M tokens) stays parked and is not a precondition. The operator stated the requirement on 2026-10-02 (the system surfaces already-recorded rulings and ingested knowledge at the point of decision; he refuses to be the continuity layer) and again on 2026-10-17 ("have we tried this before, has this worked in the past").
**After:** c48b3fd6
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Model:** primary
**Spend:** est. 0.6M tokens. Basis: the search verbs exist in squiddy's served MCP (search, claims_in, mentions); this task wires them into registration and launch, and adds one measurement.
**Parts:** A 0.5, B 0.3, C 0.2.
**Network:** none beyond git push.
**Exclusive:** yes
**Premises:**
- premise: seldon's governed graph is served | check: `test -f governed/corpus/manifest.yaml`
- premise: squiddy's search verb is importable | check: `/Users/brock/GitHub/squiddy/.venv/bin/python -c "import squiddy.serve"`

Glob and read every sibling `*RECALL-001*ADDENDUM*.md`.

## Stop condition (AD-037-R6, by the dispatcher)

Token ceiling 0.72M. Zero model calls: retrieval is lexical and dense over the served graph, no judge.

## Part A: retrieval at registration

1. At `seldon cc register`, query the repository's governed graph (and, where `decisions.repositories` names siblings, theirs) with the task's title, premises and Part headings. Return, ranked: prior RESULTs, open and resolved Issues, decision records, and `worktree_kept` or superseded tasks whose reason text matches.
2. Print the top hits in the registration output under `Recall:` with one line each (kind, id, date, headline), and write them into the task's launch prompt so the session reads them before CLAUDE.md.
3. A hit of kind `superseded` or `worktree_kept` whose reason names a failure is marked `dead end` in the list.
4. Tests, each failing on HEAD: a task whose title matches a past RESULT lists it; a dead-end branch is marked; a task with no history prints `Recall: none`; the launch prompt carries the list.

Acceptance:
- `check: pytest tests/test_recall001_registration.py -q`

## Part B: the measurement

1. Every RESULT gains a required line `Recall used:` naming which listed hits changed the task's approach, or `none`. `seldon cc complete` refuses a RESULT without it.
2. `qc chart` reports per week: tasks registered, tasks with at least one hit, tasks whose RESULT names a used hit. This is the number that decides whether the message-board and cross-agent knowledge-exchange design (squiddy DN-040 area, operator 2026-10-03) is worth building: if hits are used often, build it; if rarely, the retrieval is enough.
3. Tests: `cc complete` refuses a RESULT without the line; the chart counts.

Acceptance:
- `check: pytest tests/test_recall001_measure.py -q`

## Part C: operator judgment is recorded

1. A new CLI and MCP verb, `seldon decision operator-catch <task> --class <error class> --text "<what he saw>"`, writes a Decision record with `decided_by: operator`, `kind: catch`, bound to the task. It is for the touchpoint-3 case: the operator saw something the system did not (2026-10-17 example: a fixed slice count across varying segment lengths blowing up a solver).
2. `qc chart` reports operator catches per week by class. That series is the measured boundary of L4.
3. Tests: the record validates; the chart counts it.

Acceptance:
- `check: pytest tests/test_recall001_operator_catch.py -q`

## Report

RESULT under 30 lines: tokens per Part against 0.6M; the first `Recall:` output on a real task; the first chart reading; premises found wrong. Then `seldon verify`, `seldon cc complete`, merge, push.
