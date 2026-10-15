# RESULT: SEL-006 (task 1b8ef64d), registration commits the governing note; server_stale; parts baselines

**Spend.** 0 model calls. Tokens at the station markers, against 0.5M: A 196,215 (CPI 1.27); B 247,356 cumulative and C 248,198 cumulative (CPI 1.62, 2.01). B and C were marked after both were built, so their split is not measured; closeout ran after the last marker. No addenda existed.
**Part A order: records-before-commit.** `decisions.create` is the register's one write path (AD-033-R2) and makes no model call, so registration records a note's unrecorded labelled rulings itself (`decided_by: desktop`, verbatim span, AD-033-R3/R4), and the executing session has no Step 0. The AD-033-R8 statement pass stays with that session. Spans use `decisions.labeled_spans_in`, which generalises PA-001/SEL-002's rules. It agrees with 101 of 113 recorded spans; 10 of the 12 differences are seed spans that start on a blank line.
**Part A plants** (`tests/test_cc_register_commits_note.py`, 6 tests; real git, real hook, real Neo4j). All 6 failed at HEAD e8f46de, each with `AD-036-R4: refusing to register ... no prior-art verdict` (`docs/evidence/sel006/partA_head_failures.txt`):
1. An untracked note with passing receipts is committed with the task and the verdict ledger in ONE commit, and nothing is left dirty.
2. A failing receipt refuses with `governing_note_unverified`, commits nothing, and keeps the fail verdict for the dispatcher's sweep.
3. A labelled ruling without a record is recorded by registration and committed with the note.
4. A note edited after its first commit is committed as a child commit; the first commit's tree is unchanged.
5. (added) Without `--allow-untracked`, the registration refuses with `governing_note_uncommitted`.
6. (added) When the hook refuses the commit, the tree is restored and nothing is registered.
**server_stale, verbatim:** `server_stale: seldon-mcp loaded <short> on <YYYY-MM-DD HH:MM TZ>; the checkout is at <short> (<what> changed since). Restart the MCP server (restart Claude Desktop).` seldon-mcp returns it with the prefix `Error: `. squiddy serve returns `{"error": ...}`, naming `squiddy-<graph>`.
- The fed23c36 plant (role family None) returns this message. With the guard removed, the same call returns `model_not_in_lock ... family None is not one of`.
- Part B's tests failed at c817457 (ImportError, `docs/evidence/sel006/partB_head_failures.txt`). The squiddy tests failed on squiddy main.

**Suites.**
- seldon (branch before Part C's test): 2498 passed, 0 skipped, 0 xfailed, 0 deselected, 0 failed. Part C's test: 6 passed.
- squiddy worktree full suite: 2121 passed, 10 skipped, 12 failed. 11 of the failures came from gitignored graph artifacts the worktree lacks. The 12th (x001 harvest_walk_complete) was already failing on main.
- squiddy main after the merge: those 12 plus the serve tests, 30 passed, 0 failed.
- ai-readiness-kg, the 5 files that read seldon.yaml: 158 passed, 2 skipped, 2 deselected (`-m "not slow"`, real-rate runbook runs), 0 failed. arnold: not run; no test reads seldon.yaml.

**Constraints and decisions, with basis.**
- (1) Part B compares the HEAD tree of `seldon/` (`squiddy/`) and config sha256s, not HEAD. Basis: the MCP tools commit their own journal lines, so a HEAD check would refuse every session's second call. The message still names both HEADs.
- (2) A FAIL verdict is recorded but not committed, as "commits nothing" requires. It stays for `prior_art.commit_leftovers` (AD-036-R11's sweep).
- (3) The verdict ledger is staged with the note only when its uncommitted lines are all prior-art lines. Otherwise the registration refuses rather than sweeping up other writers' lines.
- (4) squiddy serve carries its own copy of the check. Basis: seldon is only squiddy's optional `models` extra, and the read-only server should not depend on it.
- (5) Part C baselines are each project's `(:ResearchTask).source_file` list (`scripts/sel006/write_parts_baselines.py`): squiddy 96, arnold 188, ai-readiness-kg 209.
- (6) squiddy's harvest walk got dispositions for the 3 new `evidence/sel006` directories and for 5 seldon directories (disp_c7, model003, qc002) that were already missing them.

**Premises found wrong.**
- The premise (`stations.py` on main) was true.
- Part A's second check is a shell pipeline. The station runs it as argv with no shell, so it passes vacuously (Issue 9f0dcad1). Run in a shell after the RESULT commit, it gives 0 lines.
- Part C's check is a description, not a command. It was recorded `unrunnable` and huddle fac9af69 is closed. It is replaced by `pytest tests/test_parts_gate_in_projects.py -q` and real CLI refusals in all three projects (`docs/evidence/sel006/partC_cli_refusals.txt`).
- The CLI prints the AD/DN fix line under `parts_undeclared` (Issue 1027bc62).
- **Restart Claude Desktop** to load this code; until then the old seldon-mcp has no guard.
