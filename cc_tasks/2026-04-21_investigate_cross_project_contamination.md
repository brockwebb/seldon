# CC Task: Investigate and Fix Cross-Project Graph Contamination

**Date:** 2026-04-21
**Scope:** Investigation + fix in `seldon/config.py` and/or project initialization logic
**Severity:** High — violates AD-004 (per-project database, no shared infrastructure) and creates silent data contamination
**Detection:** Observed in usai-harness project (2026-04-21). `seldon_task_list` on usai-harness returned 5 tasks (`SETUP-01` through `SETUP-05`) that belong to a different project (the crosswalk paper). The user flagged this explicitly: "SETUP-01 through SETUP-05 look like they leaked in from another project (the crosswalk paper). Seldon may be sharing a graph or those got created during init."

---

## Problem

Seldon's architectural guarantee (AD-004) is per-project database isolation: each project gets its own Neo4j database, and cross-project contamination is structurally prevented. The usai-harness observation indicates that guarantee is being violated somehow.

Three possible root causes, in decreasing likelihood:

### Root cause candidate 1: two `seldon.yaml` files pointing at the same database name

`seldon/config.py`'s `load_project_config()` reads `neo4j.database` from the project's `seldon.yaml` and trusts it. If two projects are initialized with the same `database:` value (either by user error or by `seldon init` not guaranteeing uniqueness), they write to the same Neo4j database. The isolation is by database NAME, not by process or path.

Check:
```bash
grep -r "database:" /Users/brock/Documents/GitHub/*/seldon.yaml
```

Confirm whether any two projects share a database name. If yes, that's the immediate bug: `seldon init` must enforce database name uniqueness, or `load_project_config` must fail loudly when a new project tries to attach to an existing database with pre-existing artifacts.

### Root cause candidate 2: `seldon init` on an existing project directory inherited prior state

If usai-harness was initialized in a directory that had been part of another project, OR if `seldon init` failed to create a fresh database and silently attached to an existing one, the crosswalk tasks would persist in the graph that usai-harness now believes is its own.

Check the database creation behavior in `seldon/commands/init.py`:
- Does it verify the database is empty before proceeding?
- Does it error if a database of that name already exists?
- Does it use `CREATE DATABASE IF NOT EXISTS`, which would attach to any existing DB silently?

### Root cause candidate 3: task name collision across projects with database sharing via slug aliasing

Lower likelihood. If `seldon_task_list` filters by something derivable across projects (e.g., slug substring match), cross-project leakage could happen at the QUERY level rather than storage level. Less likely given the code structure, but worth ruling out during investigation.

## Also relevant: path uniqueness

User asked: "pathname... at least from the github root is required? Tasks can end up having similar names — it's supposed to be kind of modular, but all within project, that isolation should prevent that... or if we need to fully qualify, we need more path."

Within a single project graph, `source_file` (relative to project root) is the uniqueness key in `_find_existing()` (see `seldon/commands/cc.py`). Two tasks named `setup-01.md` in different subdirectories are distinguishable because their `source_file` values differ (`cc_tasks/subdir-a/setup-01.md` vs `cc_tasks/subdir-b/setup-01.md`). That's fine.

Cross-project, `source_file` is NOT a sufficient uniqueness key. `cc_tasks/setup-01.md` could exist in both the crosswalk project and usai-harness. If the graphs are correctly isolated, this doesn't matter — each project's graph has its own `cc_tasks/setup-01.md` and they don't collide. If the graphs are NOT isolated (the root cause under investigation), then same-named tasks across projects conflict.

**Implication for the fix:** the answer is NOT to add project prefix to `source_file`. That's papering over a broken isolation guarantee. Fix the isolation. `source_file` stays relative-to-project-root as designed.

## Investigation

Before writing a fix, produce a diagnosis document: `notes/2026-04-21_cross_project_contamination_diagnosis.md`. Include:

1. **Evidence gathering**:
   - List all `seldon.yaml` files under `/Users/brock/Documents/GitHub/`.
   - For each, extract `project.name`, `project.slug`, `neo4j.database`.
   - Tabulate. Flag any database-name duplicates.

2. **Direct graph inspection**:
   - For each distinct Neo4j database, run:
     ```cypher
     MATCH (n:Artifact) WHERE n.source_file IS NOT NULL
     RETURN n.source_file, count(*) as cnt
     ORDER BY cnt DESC LIMIT 20
     ```
   - Identify which databases contain SETUP-01 through SETUP-05. Are they in the usai-harness database, the crosswalk database, or both? If both: confirmed contamination at storage level.

3. **Init behavior audit**:
   - Read `seldon/commands/init.py`. Document its database-creation semantics. Does it create fresh? Attach-if-exists? Fail-on-exists? Which Cypher/admin commands does it run?
   - Compare against AD-004's isolation requirement.

4. **Root cause conclusion**: one of the three candidates above, or a fourth surfaced by investigation.

## Fix

Scope of fix depends on root cause:

### If root cause 1 (duplicate database names):

- `seldon init` must check whether the requested database name is already in use by another `seldon.yaml` somewhere on disk. This is a weak check (can miss projects in other locations), but catches the common case.
- More robust: `seldon init` generates a database name from `project.slug` with a uniqueness suffix if collision detected.
- `load_project_config()` emits a warning on startup if it detects the database contains artifacts with `source_file` paths that don't exist under the current `project_dir`. Signal of wrong-graph attachment.

### If root cause 2 (init attached to existing database):

- `seldon init` must verify target database is empty before proceeding. Fail loudly if not. Offer `--force` flag for explicit override, never silent attachment.
- Add migration guidance: if user hits this, here's how to unstick.

### If root cause 3 (query-level leakage):

- Audit query-building code in `commands/task.py`, `commands/issue.py`, etc. for scope bugs. Fix as found.

## Tests

Add integration tests that:

1. Initialize two projects with distinct slugs but the same explicit database name. Expect failure or clear warning.
2. Initialize a project pointing at a database that already has artifacts from elsewhere. Expect failure or clear warning.
3. Initialize two projects with distinct slugs and auto-generated database names. Expect successful isolation — creating a task in one does not appear in the other's `seldon_task_list`.

## Retroactive cleanup for usai-harness

Out of scope for this task. After this bug is fixed, file a separate task to clean up the usai-harness graph: identify the 5 ghost tasks, determine their true home, either move them or delete them from usai-harness's graph.

## Verification

1. Investigation document committed to `notes/`.
2. Fix addresses identified root cause.
3. Integration tests pass.
4. Re-run the usai-harness scenario: `seldon_task_list` on usai-harness returns only usai-harness tasks, not crosswalk SETUP tasks.

## Out of scope

- Retroactive cleanup of the contaminated usai-harness graph (separate task, depends on this one).
- Architectural changes to the isolation model (AD-004 stands; this is a fidelity-to-design bug, not a design bug).
- Fixing the description auto-extraction bug observed in the same session (separate CC task).
