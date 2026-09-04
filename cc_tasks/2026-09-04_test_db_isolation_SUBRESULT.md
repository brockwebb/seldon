# SUBRESULT — Per-process Neo4j test database isolation

**Date:** 2026-09-04
**Seldon task:** `0d2ce3d1`
**Worktree:** `/Users/brock/GitHub/seldon/.claude/worktrees/defect-fixes-ad028`
**Source defect:** 2026-09-03 defect sweep, `cc_tasks/2026-09-03_seldon_defect_sweep_registry_lifecycle_ontology_RESULT.md` §9.1 (corroborated independently in the lane-A §7.3, lane-B §—, lane-C §6.2 and lane-D §5.2 SUBRESULTs)

---

## 1. What was wrong

Every Neo4j-backed test in this suite depends on `tests/conftest.py::clean_test_db`,
which runs `MATCH (n) DETACH DELETE n` **before every test**. Until this change the
database it wiped was a single shared name, `seldon-test`, hardcoded in
`tests/conftest.py` and re-hardcoded as a literal in 29 other test modules.

Consequence: two `pytest` processes running at the same time delete each other's
fixture data mid-test. The 2026-09-03 sweep ran four lanes concurrently and saw
`assert 10 == 4` in `test_sync.py` that then passed 15/15 on an immediate serial
re-run, plus `neo4j.exceptions.ClientError: Unable to load NODE` and phantom empty
result sets. Four independent lanes each attributed instability to this and each
recommended the same fix.

This is what made parallel multi-agent work on this repo unsafe: the suite was not
a reliable signal while any other agent was running it.

---

## 2. What shipped

### New: `tests/testdb.py`

The one source of truth for the test database name, plus its lifecycle helpers.
Pure logic (no import-time Neo4j connection), so the safety-critical parts are
unit-testable without a server.

| Symbol | Purpose |
|---|---|
| `BASE_DATABASE` | `"seldon-test"` — the only place the literal appears |
| `TEST_DATABASE` | The resolved per-process name every test uses |
| `TEST_PROJECT_DATABASE` | `f"{TEST_DATABASE}-project"` — the ontology tests need a master/replica *pair* |
| `TEST_DATABASE_IS_EPHEMERAL` | Whether teardown must drop it |
| `resolve_database(env, pid)` | The resolution order below |
| `is_ephemeral(name, env)` | Is this name one we own and may destroy |
| `stale_pid(name, env, self_pid)` | Owning PID iff the database is an abandoned orphan |
| `stale_databases(names, ...)` | Filter a `SHOW DATABASES` listing down to orphans |
| `create_database(driver, name)` | `CREATE DATABASE … IF NOT EXISTS WAIT` |
| `drop_database(driver, name)` | Guarded `DROP DATABASE … IF EXISTS WAIT` |
| `sweep_stale_test_databases(driver)` | The self-healing step, run at session start |

### Changed: `tests/conftest.py`

- Imports `TEST_DATABASE` from `tests.testdb` instead of defining the literal.
  `tests/__init__.py` exists and the repo has no `[tool.pytest.ini_options]`, so
  pytest's default `prepend` import mode puts the repo root on `sys.path` and
  `from tests.testdb import …` resolves. Verified by the suite running green.
- `neo4j_driver` (session-scoped) now:
  1. sweeps orphan databases left by interrupted runs,
  2. creates this process's database **with `WAIT`**,
  3. drops this process's database (and its `-project` sibling) in a `finally`
     block at session teardown.

### Changed: 30 test modules

Every `"seldon-test"` literal is gone from `tests/*.py` except `BASE_DATABASE`
in `tests/testdb.py`. Three shapes were handled:

- `NEO4J_DB = "seldon-test"` module constants → `NEO4J_DB = TEST_DATABASE` (25 files).
- YAML written as a **Python string literal** — `"neo4j:\n  database: seldon-test\n"` —
  interpolated by concatenation, preserving the surrounding implicit string
  concatenation (`test_mcp_audit.py` ×2, `test_result_registry.py`, `test_paper_build.py` ×4).
- Dict literals `{"database": "seldon-test"}` (`test_verify.py` ×2, `test_paper_build.py` ×3),
  keyword arguments `database="seldon-test"` (`test_docs.py` ×2), and
  `session(database="seldon-test")` (`test_graph.py` ×14).
- `test_ontology.py` needs two databases; `TEST_MASTER_DB`/`TEST_PROJECT_DB` now
  derive from `TEST_DATABASE`/`TEST_PROJECT_DATABASE`, so its replica pair is
  per-process too.

`tests/test_testdb.py::test_no_hardcoded_database_literal_in_test_modules`
scans `tests/test_*.py` and fails if the literal is ever reintroduced.

### New: `scripts/test_db_concurrency_check.sh`

Reproducible harness for the evidence in §5, including the negative control that
demonstrates the defect still exists when both processes are forced onto one
database.

---

## 3. Resolution order

Documented in the `tests/testdb.py` module docstring. First match wins:

1. **`SELDON_TEST_DATABASE`** — used **verbatim** (whitespace-stripped). An
   explicit operator override for an environment that provisions one dedicated
   database, e.g. CI in a container torn down wholesale. Never swept, never
   dropped by the suite. Set but empty raises `ValueError` rather than silently
   falling through — an empty override is always a mistake.
2. **`PYTEST_XDIST_WORKER` set** → `seldon-test-p<pid>-<worker>`.
3. **Otherwise** → `seldon-test-p<pid>`.

Cases 2 and 3 are *ephemeral*: created at session start, dropped at session
teardown.

### Deviation from the task description (and why)

The task specified `seldon-test-<worker>` for the xdist case. **That is wrong and
would have reintroduced the bug it was meant to fix.** `gw0` exists in *every*
concurrent xdist run, so two agents each running `pytest -n 4` would collide on
`seldon-test-gw0` exactly as they collided on `seldon-test`. The PID is what
actually guarantees uniqueness — and under xdist each worker is its own process
with its own PID, so the PID scheme alone already covers the xdist case. The
worker id is retained purely as a readability aid when eyeballing
`SHOW DATABASES` output. Shipped form: `seldon-test-p<pid>-<worker>`.

(Second, smaller correction: the task said the literal was in "~20 test files".
It was in **30** — `grep -rn 'seldon-test' tests/` returned 67 hits.)

---

## 4. Sweeper safety argument

`sweep_stale_test_databases` runs at session start and issues `DROP DATABASE`.
A drop destroys data irrecoverably, and this server hosts 25 real project
databases (`seldon-leibniz-pi`, `seldon-seldon-self`, `seldon-sfv-paper`, …),
so the match is deliberately narrow. **All five conditions must hold** before a
name is a drop candidate:

1. It matches `EPHEMERAL_RE = ^seldon\-test-p(\d+)(?:-[A-Za-z0-9]+)*$` —
   anchored at both ends, requiring the literal string `seldon-test-p` followed
   by **at least one digit**.
2. It is not the `SELDON_TEST_DATABASE` override.
3. The embedded PID is not this process's own PID.
4. The embedded PID is `> 0`.
5. `os.kill(pid, 0)` reports the process does **not** exist.

Why this cannot reach a real project database:

- Real project databases are named `seldon-<project-slug>`. To match, a project
  would have to be slugged literally `test-p<digits>` — and Seldon derives slugs
  from project names, so this would require someone naming a project `test p123`.
  No such project exists; the pattern is checked against a representative real
  listing in `test_stale_databases_filters_a_realistic_listing`.
- `seldon-test` itself fails condition 1 (no `-p<digits>`). It is *never*
  swept, so an operator using `SELDON_TEST_DATABASE=seldon-test` for a serial
  run is safe, as is the legacy database that predates this change.
- `seldon-test-project` fails condition 1 (`project` is not digits).
- Neo4j's own `system` and `neo4j` databases fail condition 1.
- Condition 5 fails **safe** in both error directions: `PermissionError` (a live
  process owned by another user) is read as *alive*, and any other `OSError`
  propagates rather than being read as "dead". Nothing but an explicit
  `ProcessLookupError` authorises a drop.
- PID recycling fails safe: if the PID now belongs to an unrelated live process,
  the database is left alone as a harmless orphan rather than dropped out from
  under a running session.
- `drop_database` re-checks `is_ephemeral` and raises `ValueError` **before
  opening a Neo4j session**, so a caller mistake elsewhere in the suite cannot
  destroy a project database either.

`tests/test_testdb.py` carries 21 protected names through both `is_ephemeral`
and `stale_pid` (real project DBs, `system`, `neo4j`, and near-misses such as
`seldon-testp123`, `seldon-test-px1`, `seldon-test-p1x`, `xseldon-test-p1`,
`SELDON-TEST-P1`) and asserts every one is rejected, plus 5 names that must be
accepted, plus live/dead PID behaviour using real subprocesses.

**Live verification against the running server** (throwaway script, since deleted):
created `seldon-test-p<dead-pid>`, `seldon-test-p<live-pid>` and a decoy
`seldon-test-decoy-project`, then ran the sweeper.

```
orphan (dead pid) : seldon-test-p9952
in-use (live pid) : seldon-test-p9953
decoy             : seldon-test-decoy-project
swept             : ['seldon-test-p9952']
removed           : ['seldon-test-p9952']
real project DBs still present: True
SWEEPER CHECK: PASS
```

Only the orphan was dropped. `seldon-test`, `seldon-test-project`,
`seldon-seldon-self`, `seldon-leibniz-pi` and the live-PID database all survived.

---

## 5. Concurrency evidence

All commands run from the worktree root. `MODS` =
`tests/test_sync.py tests/test_task_lifecycle.py tests/test_verify.py` (79 tests).

### 5.1 Negative control — both processes forced onto ONE shared database

```
sh scripts/test_db_concurrency_check.sh control
```
which is equivalent to running, concurrently:
```
SELDON_TEST_DATABASE=seldon-test python -m dotenv -f .env run -- python -m pytest $MODS -q
SELDON_TEST_DATABASE=seldon-test python -m dotenv -f .env run -- python -m pytest $MODS -q
```

```
process B exit=1
process A exit=1
_conc/control-A.log: FAILED tests/test_verify.py::test_verify_quiet_exit_code_1 - assert 2 == 1
                     15 failed, 64 passed, 2 warnings in 9.75s
_conc/control-B.log: FAILED tests/test_verify.py::test_verify_quiet_exit_code_1 - neo4j.exceptions...
                     19 failed, 60 passed, 5 warnings in 9.78s
```

The defect reproduces on demand, and the failure signatures match the 2026-09-03
observations exactly (bogus assertion counts plus `neo4j.exceptions` errors).

### 5.2 Fixed — two concurrent processes, per-process databases

```
sh scripts/test_db_concurrency_check.sh fixed
```
```
process A exit=0
process B exit=0
_conc/fixed-A.log: 79 passed in 13.08s
_conc/fixed-B.log: 79 passed in 13.09s
```

### 5.3 Fixed — four concurrent processes (the original four-lane scenario)

```
sh scripts/test_db_concurrency_check.sh fixed4
```
```
process D exit=0
process A exit=0
process C exit=0
process B exit=0
_conc/fixed4-A.log: 79 passed in 16.60s
_conc/fixed4-B.log: 79 passed in 16.71s
_conc/fixed4-C.log: 79 passed in 16.61s
_conc/fixed4-D.log: 79 passed in 16.55s
```

### 5.4 Fixed — two concurrent runs of the FULL suite

```
sh scripts/test_db_concurrency_check.sh full
```
```
full suite A exit=0
full suite B exit=0
_conc/full-A.log: 1001 passed in 54.82s
_conc/full-B.log: 1001 passed in 54.81s
```

### 5.5 No residue

After every run above:

```
total databases: 30   (unchanged from before the work)
leftover seldon-test-p<pid> databases: none
seldon-test present: True | seldon-test-project present: True
```

---

## 6. Suite results and timing

Command: `python -m dotenv -f .env run -- python -m pytest tests/ -q`

| Run | Tests | Reported | Wall clock |
|---|---|---|---|
| Baseline (before any change) | **934 passed** | 40.45s | 41.48s |
| After, full suite | **1001 passed** | 46.68s | 47.68s |
| After, same 934 tests (`--ignore=tests/test_testdb.py`) | **934 passed** | 46.60s | 47.56s |
| After, same 934, `SELDON_TEST_DATABASE=seldon-test` (no create/drop) | **934 passed** | 40.29s | 41.35s |
| `tests/test_testdb.py` alone | 67 passed | 0.12s | 0.63s |

**Cost of the isolation: +6.3s, fixed, per pytest session** (40.29s → 46.60s on the
identical test set). It does not scale with test count. The new tests add 0.12s.
Measured components on this server:

- `CREATE DATABASE … WAIT`: 0.52s
- `DROP DATABASE … WAIT` (existing db): 0.60s
- `DROP DATABASE … IF EXISTS WAIT` (nonexistent): 0.011s — so the unconditional
  `-project` drop is free when the ontology tests did not run
- `SHOW DATABASES`: 0.004s
- `tests/test_ontology.py` alone: 12.80s shared → 16.02s per-process (+3.2s), from
  creating and dropping a *fresh* master/replica pair rather than reusing two
  long-lived ones

`WAIT` is load-bearing on `CREATE`: `CREATE DATABASE`/`DROP DATABASE` are
asynchronous by default and an incomplete create surfaces as `DatabaseNotFound`
in whichever test happens to run first.

Judgment: +6.3s fixed (15% of a 40s suite) buys a suite that is trustworthy while
other agents are running it. Under the previous scheme a concurrent run produced
15–19 spurious failures (§5.1), which costs far more than 6 seconds to
investigate. Not optimising further.

---

## 7. Corrections to the task description

1. **`seldon-test-<worker>` for xdist is wrong** and would have preserved the
   bug for `pytest -n` users. See §3. Shipped `seldon-test-p<pid>-<worker>`.
2. **"~20 test files"** — the literal was in **30** files, 67 occurrences.
3. The task's watch-out list named `tests/test_mcp_audit.py`, `tests/test_verify.py:442`
   and `tests/test_docs.py`. It missed `tests/test_paper_build.py` (4 YAML string
   blobs + 3 dict literals), `tests/test_result_registry.py` (1 YAML blob),
   `tests/test_graph.py` (14 inline `session(database=…)` calls with no module
   constant to hook), and `tests/test_ontology.py` (a *pair* of databases, where
   naively renaming only the master leaves `seldon-test-project` shared).

---

## 8. Follow-ups (not done, deliberately)

- **Legacy `seldon-test` and `seldon-test-project` remain on the server.** Nothing
  uses them now. They are deliberately left in place: they are the valid target of
  `SELDON_TEST_DATABASE=seldon-test`, and the sweeper is designed never to touch
  them. An operator may drop them by hand.
- **`seldon-ontology` master is still shared.** The lane-D SUBRESULT noted that
  ontology tests also write to the shared `seldon-ontology` master. They do not —
  `_do_ingest` monkeypatches `ONTOLOGY_MASTER_DB` to the test database, which is
  now per-process. That specific concern is resolved by this change; no separate
  work is needed.
- `pytest-xdist` is not currently a dependency. The xdist branch is implemented
  and unit-tested but not exercised end-to-end, since installing xdist was out of
  scope for this task.

---

## 9. Files changed

**New**
- `tests/testdb.py`
- `tests/test_testdb.py` (67 tests)
- `scripts/test_db_concurrency_check.sh`
- `cc_tasks/2026-09-04_test_db_isolation_SUBRESULT.md` (this file)

**Modified**
- `tests/conftest.py`
- `.gitignore` (ignore `_conc/` harness logs)
- `tests/test_agent_roles.py`, `test_artifacts.py`, `test_cc_complete.py`,
  `test_docs.py`, `test_docs_check.py`, `test_docs_generate.py`,
  `test_document_structure.py`, `test_graph.py`, `test_impact.py`,
  `test_init.py`, `test_issue.py`, `test_mcp_audit.py`,
  `test_mcp_audit_ingest.py`, `test_mcp_tools.py`, `test_numbering.py`,
  `test_ontology.py`, `test_paper_build.py`, `test_paper_context.py`,
  `test_paper_sync.py`, `test_relationship_types.py`, `test_result.py`,
  `test_result_registry.py`, `test_session_commands.py`, `test_staleness.py`,
  `test_sync.py`, `test_task.py`, `test_task_lifecycle.py`, `test_verify.py`,
  `test_verify_snapshot.py`

No production (`seldon/`) code was touched. Nothing was committed;
`seldon verify` was not run and no graph task was closed, per the task's ground rules.
