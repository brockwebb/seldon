# SEL-041 Part A: what the gates cost, and what a slice would have selected

Measured 2026-11-21 by SEL-041 (read only). Every number below comes from a script in `tools/`, run against the
primary checkouts under `/Users/brock/GitHub` at seldon `24400dd`. JSON outputs sit beside this file.

## 1. The dispatching repositories and their gates

`tools/survey_repos.py` (seldon.yaml `dispatch` blocks), `tools/collect.py` (`pytest --collect-only -q -m ""`),
`tools/gate_times.py` (pytest summary lines in each repository's `logs/dispatch/*.log`; a run counts as a full-suite
run when its total is at least 90% of the largest total seen there, because the summary line does not name the command
that printed it; a session's stream-json and its `.ooda.log` repeat the same tool result, so a run can appear twice),
`tools/squiddy_ledger.py` (squiddy's `kit/ledger/passes.jsonl`, which records seconds per seeded run).

| repository | gate | tests | recorded full runs (n) | wall seconds: median (min to max) | source |
|---|---|---|---|---|---|
| seldon | `gate_command`: the whole suite, `pytest tests/ -q` (sessions add `-n 6`) | 3,482 | 19 (2026-11-01 to 11-21) | 1,680 (1,340 to 4,316) | session logs |
| hazbrief-mcp | `gate_command`: two pytest steps (`not slow and not load_sensitive` at `-n auto --maxprocesses 6`; `load_sensitive` at `-n 3`) then ruff | 8,469 | 20 step-1 runs (2026-11-20 to 11-21) | step 1: 2,228 (2,117 to 2,650) | session logs |
| hazbrief-mcp | the same gate, timed whole by HB-194 | about 8,040 | 5 step-1 runs, 4 step-2 runs (2026-11-17) | step 1: 3,676 to 5,304; step 2: 890 to 1,057; ruff about 1 s; the filing's 76 to 89 minutes | `hazbrief-mcp/docs/evidence/hb194/three_gates.tsv` |
| hazbrief-mcp | step 1 per task, HB-151 to HB-189 | 6,275 to 7,980 | 39 | 718 to 5,887; median 1,853 | `hazbrief-mcp/docs/evidence/hb193/gate_history.tsv` |
| squiddy | `gate_record`: the kit pass (`squiddy.kitpass record-pass`, three seeded runs serial) | about 2,900 in the kit pass | 20 passes (2026-10-14 to 11-15) | per seeded run 1,418 (10-16) rising to 3,587 (11-15); a pass is up to three runs | kit pass ledger |
| aacps-ai-policy | `gate_command`: squiddy's pytest over `tests/` | not collected (no runs recorded) | 0 | none recorded | no dispatch logs |
| ai-readiness-kg | **no gate command** | n/a | n/a | n/a | its session logs hold squiddy suite runs (3,492 to 3,533 tests, 201 to 3,796 s), which are not its gate |
| factory | **no gate command** (AD-034-R26: its check-less tasks block `ungated`) | 21 | 2 session runs | 10.7 to 10.9 | session logs |

Gate evidence by source (ADDENDUM 01 item 5, `tools/evidence_sources.py`): no merge in any repository has yet been
recorded under AD-034-R26. seldon's 43 merges, hazbrief's 138, squiddy's 51, ai-readiness-kg's 12 and factory's 4 all
predate SEL-042, so the store holds **zero `merge_gate` runs** so far, and one re-gate in seldon (DISP-001R,
2026-10-20, 2,572 s). The double gate SEL-042's return described for hazbrief (the session's own full gate, then the
round's `merge_gate`) begins with the next hazbrief merge. SEL-042's own two full runs in seldon were 25:40 (3,462
passed) and 25:51 (3,472 passed) at `-n 6`.

## 2. The last thirty merged tasks, replayed against slices

`tools/replay.py`: for each of the last thirty merges in the repository's event store, the files the branch changed
(`git diff --name-only base...commit`), grouped by top-level directory, and the share of the suite (by collected test
count) three slice granularities would have selected:

- **G1, top-level directory**: a change under the package selects the whole suite.
- **G2, package sub-directory** (`seldon/core`, `seldon/commands`, `src/hazbrief/brief`): the test files whose static
  import closure touches that sub-directory.
- **G3, module**: the test files whose transitive static import closure holds a changed module.

In every model changed test files select themselves, documents and records (`cc_tasks/`, `handoffs/`, `docs/`, the
event store, `state/`, `logs/`, `*.md`) select nothing, and `conftest.py`, `pyproject.toml` and the lock go full. Two
readings: **strict**, where any other path no slice names goes full (SEL-041 rule 4), and **declared**, where every
such path is assumed declared `tests: none` (the most a project could save by declaring slices for its non-code paths).

| repository | reading | tasks going full (of 30) | tasks selecting 10% or less | tasks selecting nothing | median share |
|---|---|---|---|---|---|
| seldon | strict | 27 (G1 = G2 = G3) | 3 | 3 | 1.00 |
| seldon | declared | 26 (G1 = G2 = G3) | 4 | 3 | 1.00 |
| hazbrief-mcp | strict | 23 (G1 = G2 = G3) | 7 | 3 | 1.00 |
| hazbrief-mcp | declared | 12 (G1 = G2 = G3) | 17 | 4 | 0.01 |

What the strict reading went full on: in seldon, `governed/ledger/events.jsonl` (11 tasks), `seldon.yaml` (10),
`scripts/` (16 files), `graphs/` (134 files); in hazbrief, `scripts/` (65 files), `fixtures/` (1,190 files),
`graphs/` (113), `src/hazbrief/brief/orchestrator.yaml`, `.gitignore`, `corpus/`.

## 3. Why the three granularities agree: each suite's import structure (`tools/hub.py`)

- **seldon.** `tests/conftest.py` imports `seldon.cli`, whose closure is 114 modules, the whole package; so every test
  file depends statically on every module, and the median module is depended on by 100% of the suite. Without
  conftest's closure the median is still 89%: 75 of seldon's 112 modules have an import closure over 80% of the
  package (every `seldon.commands.*` module, and the core modules that import them). Only 2 modules are depended on
  by less than a quarter of the suite.
- **hazbrief-mcp.** conftest imports only `hazbrief.config`. The median module is depended on by 71% of the suite;
  13 of 94 modules by less than a quarter. Five modules (`hazbrief.command`, `hazbrief.brief.cli`, `.entry`, `.start`,
  `.web`) import more than 80% of the package. Every one of the 12 hazbrief tasks that changed `src/` would still
  have gone full at every granularity.

## 4. What this says before building

A by-directory slice **would still select the whole suite for most tasks in both repositories**, for two different
reasons:

1. **Paths no slice names.** Most of hazbrief's tasks change `scripts/`, `fixtures/`, `graphs/` or `corpus/` beside
   their documents. Declaring those paths (a slice each, with the tests that read them, or `tests: none`) moves
   hazbrief from 23 full gates in 30 to 12, and 17 of 30 tasks to 10% of the suite or less. That saving is the
   kit's to enable (declared slices) and hazbrief's to declare.
2. **Import structure.** A task that changes `src/` (hazbrief) or `seldon/` (seldon) selects the whole suite under
   any static granularity, because a test-wide fixture or a handful of hub modules import everything. That is
   Fowler's third caveat ("the saving disappears when a change touches code most tests use"), and it is each
   project's suite structure to fix, not the kit's: seldon's conftest imports the CLI; hazbrief's five entry modules
   import the package. A coverage map (testmon) could be finer than static imports, since importing a module does not
   execute it; Part C measures whether it is safe on seldon's suite.

So the build goes ahead (the kit must be able to declare slices, and documents-only tasks, 3 of 30 in each repository,
must stop paying the whole suite), and the returns say plainly that the larger saving depends on each suite's
structure.
