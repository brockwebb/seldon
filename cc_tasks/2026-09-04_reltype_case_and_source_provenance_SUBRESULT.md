# SUBRESULT — Relationship-type case + CC task source-file provenance

**Date:** 2026-09-04
**Lane:** 3 of 3 (worktree `.claude/worktrees/defect-fixes-ad028`)
**Graph tasks:** `a9e7ed28` (rel-type case), `868d6bb0` (source-file provenance)
**Suite:** 1148 passed, 0 failed. Lane baseline at start was 1001; this lane
added 84 tests, the remaining delta is the other two lanes working in the same
worktree.

---

## 1. What shipped

### Task A — relationship-type case (`a9e7ed28`)

| File | Change |
|---|---|
| `seldon/core/graph.py` | `canonical_rel_type`, `_assert_safe_rel_type`, `find_noncanonical_rel_types`, `get_relationships_of_type`, `relationship_exists` |
| `seldon/commands/verify.py` | Check 8 — `Relationship types` |
| `seldon/core/sync.py` | `link_case_migrated` added to `_AUDIT_ONLY_EVENT_TYPES` (**cross-lane touch — see §5**) |
| `scripts/migrations/2026-09-04_migrate_rel_type_case.py` | New. Dry-run by default, `--apply` to write |
| `tests/test_verify_reltype_case.py` | 35 tests |
| `tests/test_verify_reltype_migration.py` | 16 tests |

### Task B — source-file provenance (`868d6bb0`)

| File | Change |
|---|---|
| `seldon/commands/verify.py` | Check 9 — `Task source files`; `open_task_states`; `MAX_MISSING_DETAILS` |
| `seldon/commands/cc.py` | Git-tracking guard on `cc register` and `cc complete`; `--allow-untracked` on both |
| `scripts/migrations/2026-09-04_supersede_orphan_source_file_tasks.py` | New. Dry-run by default, `--apply` to write |
| `tests/test_cc_git_guard.py` | 20 tests |
| `tests/test_cc_orphan_supersede_migration.py` | 13 tests |

`seldon verify` now runs 9 checks. Both new checks are scoped to the single
database named in the resolved project's `seldon.yaml`.

---

## 2. Evidence

### 2.1 Cross-database mixed-case audit (30 databases, read-only)

Every database on the server was scanned with
`MATCH ()-[r]->() RETURN type(r), count(r)`. Exactly one had a problem.

| Database | Rel types | Rels | Verdict |
|---|---:|---:|---|
| **seldon-seldon-self** | 9 | 61 | **MIXED — `INFORMS` 8 + `informs` 4** |
| arnold | 69 | 32,169 | clean |
| fss-policy-kg | 14 | 70,098 | clean |
| quarry | 14 | 15,355 | clean |
| seldon-ai-readiness-kg | 31 | 32,277 | clean |
| seldon-brock-projects | 9 | 1,465 | clean |
| seldon-icsp-notebook | 13 | 424 | clean |
| seldon-leibniz-pi | 11 | 244 | clean |
| seldon-ai-workflow-design | 11 | 139 | clean |
| seldon-book-responsible-ai | 6 | 98 | clean |
| seldon-sfv-paper | 6 | 54 | clean |
| seldon-tickbiterisk | 8 | 39 | clean |
| seldon-blank / -census-web-concept-inventory / -federal-survey-concept-mapper / -nsf-aiday2026 / -ontology / -usai-harness / -test-project / -test-p10863-project | 5 | 36 | clean |
| seldon-sas2graph | 1 | 1 | clean |
| wintermute-intake | 3,016 | 3,722,737 | clean |
| wintermute-p2-spike | 6 | 504 | clean |
| pragmatics | 2 | 50 | clean |
| neo4j | 6 | 213 | clean |
| fscm-nist-rmf-map, seldon-ai4stats, seldon-arnold, seldon-test, seldon-test-p10863, wintermute-v2 | 0 | 0 | empty |

**No other project database needed migration**, so nothing was written outside
`seldon-seldon-self`. The blast radius of a hard-failing check is therefore
zero today (see §3.1).

### 2.2 `seldon-seldon-self` migration — before / after

```
before:  9 rel types, 61 rels    INFORMS 8   informs 4
after:   8 rel types, 61 rels    INFORMS 12  informs 0
```

Edge count preserved exactly; only the spelling changed. The four migrated
edges:

| from | to | was | now |
|---|---|---|---|
| `92f7a5bc` phase_c_roadmap_75_15_10 | `28032a55` AD-022 | `informs` | `INFORMS` |
| `92f7a5bc` phase_c_roadmap_75_15_10 | `af6adb1f` AD-023 | `informs` | `INFORMS` |
| `92f7a5bc` phase_c_roadmap_75_15_10 | `ea4b99b9` AD-024 | `informs` | `INFORMS` |
| `ea4b99b9` AD-024 | `af6adb1f` AD-023 | `informs` | `INFORMS` |

Eight events written (4 × `link_created`, 4 × `link_case_migrated`).
Re-running `--apply` is a clean no-op: `nothing to migrate — all relationship
types are canonical.`

### 2.3 Where the lowercase edges came from

Not from a sanctioned write. Three independent pieces of evidence:

1. **No `created_at` property.** `graph.create_link` sets it on every edge; all
   four lacked it. The eight `INFORMS` edges all had it.
2. **No `link_created` events.** The log holds 13 `informs` `link_created`
   events; none of their `(from_id, to_id)` pairs matches any of the four.
3. **Replay cannot produce them.** `sync._apply_event` uppercases
   `payload["rel_type"]` unconditionally, so no event can create a lowercase
   edge.

They were written by raw Cypher outside the event path. They were also
**unremovable through the sanctioned API**: `artifacts.remove_link` uppercases
its `rel_type` argument, so asking it to delete `informs` deletes `INFORMS`.

### 2.4 Orphan count — verified, and the premise it contradicts

**37 is correct**, and it is still 37 today.

```
ResearchTask total       86
  with source_file       50
    resolve on disk      13
    MISSING              37   ← matches the sweep's figure exactly
  without source_file    36
```

But the actionable set is **3, not 37**:

| State of the orphan | Count | Superseded? |
|---|---:|---|
| `proposed` | 3 | **yes** |
| `completed` | 33 | no — `superseded` is unreachable from `completed` |
| `rejected` | 1 | no — terminal |

Superseded (reason recorded verbatim as `source_file lost pre-c53b3c9`):

* `e911fc13-0d18-438c-9ad8-9b7faabe0ddd` — `cc_tasks/2026-04-05_register_calibration_and_template.md`
* `7120e000-2a20-4a87-b3b8-100efb3a1dbb` — `cc_tasks/2026-04-16_file_issues_and_convention.md`
* `676c0e39-da69-4654-8450-78b10eba41be` — `cc_tasks/2026-05-07_ontology_tracer_bullet.md`

Both ids the task description singled out as unrecoverable (`7120e000`,
`676c0e39`) were in the eligible set. **No description was written or altered
for any task.** All 37 orphans have no git history either — confirmed with
`git log --all -- <path>` per file.

### 2.5 `seldon verify` after both migrations

```
  ✓ Relationship types  All canonical (uppercase)
  ✓ Task source files   No open task is missing its spec (13 of 50 resolve on
                        disk); 37 settled (finished task; spec lost, outcome
                        recorded)
  All checks passed.
```

(Run in-process against the worktree code — the `seldon` console script on PATH
resolves to the editable install in the main repo, not to this worktree.)

---

## 3. Judgement calls

### 3.1 Non-canonical rel type is a `fail`, but NOT Tier A

The task said "fails on any non-canonical rel type". I kept `fail` — so default
`seldon verify` exits 2 — but deliberately left the check out of `TIER_A_CHECKS`.

*Why `fail` and not a warning:* the failure mode is not untidiness. Every
type-filtered query in the codebase names the uppercase form, so a lowercase
twin is **silently skipped** and the query returns a confidently incomplete
answer. That is the same severity class as a hash mismatch.

*Why not Tier A:* `--strict` is the machine gate a CC task runs before a state
transition. This check reports a property of accumulated graph history, not of
the change in hand — an executing agent cannot make it clean by doing its task
correctly. Putting it in Tier A would block every commit in any project that
adopted Seldon with a legacy graph. The concrete blast radius today is nil
(§2.1), so `fail` is safe; Tier A membership is the part that would bite a
future adopter, and it is the part I withheld.

### 3.2 The migration is NOT wired into `verify --fix`

`--fix` currently runs `paper sync`, `ontology sync`, and registers files. A
case migration deletes and recreates edges. That deserves a dry-run-by-default
command whose plan you read before it runs, not a side effect of a flag. The
check's details name the exact command instead. This also settles the
"`--fix` must only ever act on the current project" concern outright: `--fix`
never touches relationship types at all, and the migration script resolves its
one database from `seldon.yaml` and refuses `seldon-ontology` explicitly.

### 3.3 The migration bypasses `artifacts.create_link` — deliberately

A case migration is a **rename**: it must preserve the edge set exactly and
change only the spelling. `artifacts.create_link` applies domain-config
relationship validation, and one of the four edges —
`AD-024 -[informs]-> AD-023` — **violates the domain config**, which permits
`informs` only for `DesignNote → ArchitecturalDecision`. Validating a rename
would either drop that edge or abort the whole migration.

So the script composes `make_event` / `append_event` with the `seldon.core.graph`
primitives directly — the same two layers `artifacts.py` composes, minus the
semantic validation. "This edge violates the domain config" is a real, separate
defect; it is now visible (nothing hides it) and needs its own decision. There
is no `verify` check for domain-invalid relationships today.

### 3.4 Migrating "by event" — why a new event type was needed

Two events per edge:

1. `link_created` (canonical name) — so a full replay reproduces the
   post-migration graph. Without it the migrated edges would be lost on replay,
   since nothing in the log ever created them.
2. `link_case_migrated` (audit-only) — records the removal.

`link_removed` would have been **actively wrong**: `sync._apply_event`
uppercases its `rel_type` too, so replaying it would delete the canonical edge
the migration had just established.

### 3.5 `cc register` / `cc complete`: what "untracked" means

"Tracked" = git knows the path, in the index **or** a commit. Decisions:

| Condition | Behaviour | Reason |
|---|---|---|
| Committed | proceed + reminder | recoverable |
| `git add`ed, not committed | **proceed** + reminder | the sanctioned workflow is write → add → register → commit spec with RESULT. Demanding a prior commit would make registration impossible. |
| Committed then modified (dirty) | proceed + reminder | dirty is not lost; the guard is about recoverability, not cleanliness |
| Untracked in a repo | **refuse**, exit 1 | `git add <file>` |
| Matched by `.gitignore` | **refuse**, exit 1, distinct diagnostic | this is the exact condition that produced the 37 orphans; its remedy is editing `.gitignore`, not `git add` |
| No git work tree at all | **refuse**, exit 1 | strictly worse than untracked — nothing can ever recover the file |
| `git` not on PATH | **refuse**, exit 1 | provenance is unestablishable; silently allowing would be the failure this task exists to stop |

`--allow-untracked` overrides all refusals and prints a loud warning naming the
consequence. The guard runs before any graph write. No existing test invoked
these CLI commands, so nothing regressed.

### 3.6 `Task source files` grades severity by whether the task is open

Warning on all 37 forever would produce a check that **can never go green** —
a smoke alarm people learn to ignore — and 37 detail lines on every pre-commit
run.

* **Open** task (`proposed` / `accepted` / `in_progress` / `blocked`) with no
  spec on disk → `warn`, listed individually, capped at 10 with an
  "…and N more" line.
* **Finished** task → counted in the summary, never a warning. The work
  finished and the graph records the outcome; losing the spec of a finished task
  does not un-finish it.

"Open" is read from the domain config, not hardcoded: it is the set of states
from which `superseded` is reachable, because `research.yaml` documents that
edge as "reachable only from active, non-finished states". A leaf-node test
would be wrong — `completed: [verified]` has a successor yet is finished.

This makes the check and the supersede migration one story: superseding the 3
open orphans is exactly what turns the check green, and it goes amber again the
moment a new open orphan appears. It is `warn`, never `fail` — a lost file is
history, unfixable by the session that trips it.

---

## 4. Other projects — reported, not migrated

None of the other 29 databases carried a non-canonical relationship type
(§2.1), so there was nothing to report to another project's owner and nothing
to migrate. Had there been, the migration script only ever acts on the database
resolved from the working directory's `seldon.yaml`.

---

## 5. Cross-lane needs and out-of-scope findings

1. **`seldon/core/sync.py` was edited by this lane** (one frozenset member plus
   a comment: `link_case_migrated` in `_AUDIT_ONLY_EVENT_TYPES`). That file is
   in neither this lane's owned list nor its do-not-edit list. It is required
   for correctness of the event this lane emits — without it, replay logs
   "Unknown event_type … skipped". Integrator: watch for a conflict.

2. **The MCP tools bypass the new git guard.**
   `seldon/mcp_server.py::seldon_cc_register` and `seldon_cc_complete`
   re-implement `cc.py`'s logic rather than calling the click commands, so a
   Desktop session can still register an untracked task file. The duplication is
   the underlying defect; the guard should move into a shared helper both
   surfaces call. Not this lane's file.

3. **`python -m seldon` is broken — `seldon verify --fix` is degraded.**
   There is no `seldon/__main__.py` in either the worktree or the main repo, so
   `_fix_file_hashes` and `_fix_ontology` (which shell out to
   `[sys.executable, "-m", "seldon", …]`) always fail. They fail loudly
   ("Fix failed for …"), not silently, so this is a defect and not a
   correctness hazard. It is in a file this lane owns but is outside both task
   scopes; not fixed, to avoid gold-plating. Fix is a two-line
   `seldon/__main__.py`.

4. **`seldon-seldon-self`'s event log cannot be replayed.** Nine legacy
   `artifact_state_changed` lines (lines 23–39) carry no `event_id`, so
   `read_events` raises `DuplicateEventError: Duplicate event_id 'None'`. That
   means `seldon sync --full-replay` is currently impossible on this project.
   Pre-existing, unrelated to this lane's appends (all of which carry ids), and
   worth its own graph task.

5. **One relationship violates the domain config.**
   `AD-024 -[INFORMS]-> AD-023` (ArchitecturalDecision → ArchitecturalDecision)
   is not permitted by `research.yaml`, which allows `informs` only from
   `DesignNote`. Migrated as-is, because a rename must not change semantics.
   There is no `verify` check for domain-invalid relationship endpoints; that is
   a candidate Check 10.

---

## 6. Premises in the task descriptions vs live state

| Premise | Verdict |
|---|---|
| A: `seldon-seldon-self` holds `INFORMS` (8) and `informs` (4) | **Confirmed exactly.** |
| A: canonical case is UPPERCASE | **Confirmed**, and stronger than stated — canonical *by construction*, in `artifacts.create_link`, `artifacts.remove_link` and `sync._apply_event`, all three of which call `.upper()`. |
| A: "audit every project DB … migrate by event" | Audited all 30. Only one needed migration. |
| B: "37 of 49 registered CC tasks … have no source file" | **37 is right; 49 is not.** 50 ResearchTasks carry a `source_file` (86 exist in total; 36 carry none). 37 of those 50 are missing. |
| B: "`7120e000` and `676c0e39` cannot be re-derived" | **Confirmed** — neither is on disk nor in any branch. Both were in the eligible set and were superseded without a description being invented. |
| B(3): "for the 37 orphans, supersede" | **Not executable as written.** 34 of the 37 are in terminal states (33 `completed`, 1 `rejected`) from which `superseded` is unreachable by design — `research.yaml` says so explicitly: "relabeling a finished task would corrupt the honest completion record". 3 were eligible and were superseded. The other 34 are recorded, untouched, and correctly so. |
