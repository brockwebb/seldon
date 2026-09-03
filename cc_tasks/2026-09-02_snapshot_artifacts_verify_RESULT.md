# RESULT — 2026-09-02_snapshot_artifacts_verify

**Run:** 2026-09-02, Claude Code. **Addenda:** globbed
`cc_tasks/2026-09-02_snapshot_artifacts_verify_ADDENDUM*.md` at start — none exist.
**Base commit:** `86b039b`. **Model calls:** 0.

## What landed

| step | where |
|---|---|
| 1. property + validator + CLI | `seldon/core/artifacts.py` `validate_snapshot_property`, called from `create_artifact` and `update_artifact`; `seldon/commands/artifact.py` `_parse_properties` parses `snapshot=` to bool and the `update` command now surfaces `ValueError` as `Error: …` exit 1 instead of a traceback |
| 2. verify skip + informational line, `--fix` exclusion, directory guard | `seldon/commands/verify.py` `check_file_hashes`; `seldon/paper/sync.py` `sync_section` (new status `snapshot`); `seldon/commands/paper.py` reports it |
| 3. tests | `tests/test_verify_snapshot.py`, 25 tests (7 no-DB, 18 Neo4j) |
| 4. property vocabulary | `seldon/domain/research.yaml`: `snapshot` declared on `Script`, `DataFile`, `PaperSection`, category `system`, with the semantics paragraph |
| 5. design decision | `docs/design/AD-027_snapshot_artifacts.md`; pointer added to `CLAUDE.md` |

Design choice recorded in the AD: the flag is declared on the three hash-carrying types
rather than as an undeclared cross-type system property, so `seldon docs check` and the
domain loader see it. Validation lives in core, not the domain loader, because the loader has
no per-property type system (AD-013 declares `required`/`category`/`description` only) and
adding one for a single bool would be scope beyond this task.

## The invocation an owning project uses

```
seldon artifact update <artifact_id or 8+ char prefix> -p snapshot=true
```

For ai-readiness-kg's three (ids read from its graph on 2026-09-02):

```
seldon artifact update 530f0650 -p snapshot=true    # kg-schema-v0.1      kg/schema.yaml
seldon artifact update ed75f634 -p snapshot=true    # corpus-manifest     corpus/manifest.json
seldon artifact update f358e62a -p snapshot=true    # corpus-manifest-round2  corpus/manifest.json
```

Run from the owning project's root (the command reads `seldon.yaml` from cwd). Accepted
literals: `true|false|1|0|yes|no`, case-insensitive. Anything else is refused:
`Error: Property 'snapshot' must be a boolean (true/false), got 'maybe'`.

## Tests

Neo4j credentials are loaded from `.env` via python-dotenv (the file's line 4 does not
`source` cleanly in zsh, so the shell form in CLAUDE.md skips every DB test silently; the
dotenv form runs them).

| | |
|---|---|
| full suite | **694 passed, 1 failed** |
| the failure | `tests/test_paper_build.py::test_build_paper_unknown_xref_passthrough`, exit code 1 vs 0 — **pre-existing**: reproduced on a clean worktree of `86b039b` before this change. Not touched; out of scope. |
| new module | 25 passed |
| mutation matrix | verify skip disabled → 3 fail; sync guard disabled → 1 fail; directory guard disabled → 2 crash (`IsADirectoryError`, the original defect); validator disabled → 8 fail. All restored; `git diff` confirms only the intended edits remain. |

## Discrepancies and notes

- The task's "add `snapshot` to the model" assumes a typed artifact model; the model is the
  YAML property schema plus untyped dict properties. Handled as described above.
- `seldon_events.jsonl` in this repo carried 64 uncommitted lines from earlier sessions before
  this task started; `seldon cc complete` appends to the same file, so those lines travel in
  this commit. `docs/design/guarded_incremental_change_cycle.md` was also untracked
  beforehand and is left as found.
- Constraint check: no hash algorithm changed, no project database touched, zero model calls.
