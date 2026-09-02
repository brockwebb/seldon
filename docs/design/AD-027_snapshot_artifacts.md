# AD-027: Snapshot Artifacts Are Exempt From Drift Checking

**Date:** 2026-09-02
**Status:** Accepted
**Origin:** ai-readiness-kg `cc_tasks/2026-09-01_machine_diagnostic_stub_RESULT.md` §3, via `cc_tasks/2026-09-02_snapshot_artifacts_verify.md`.
**Related:** AD-018 (`seldon verify`, file-hash check B4); AD-013 (domain property schemas).

## Context

`seldon verify`'s file-hash check is a drift instrument: for every artifact carrying a
`content_hash` and a `path`/`file_path`, it hashes the live file and reports a mismatch as a
failure, and `verify --fix` repairs it by rewriting the stored hash to today's bytes via
`paper sync`.

Some artifacts are deliberate snapshots. ai-readiness-kg registers `kg-schema-v0.1` against
`kg/schema.yaml` as the schema stood at v0.1, and `corpus-manifest` / `corpus-manifest-round2`
against `corpus/manifest.json` as of two rounds of ingestion. For those, the stored hash *is*
the record: it identifies which bytes the registration refers to, and the live file is
expected to diverge as the project moves on. Under the drift check they fail permanently,
which trains operators to read past verify output, and `--fix` would destroy the record by
overwriting the hash.

A second defect from the same finding: `check_file_hashes` called `read_bytes()` on an
artifact whose `path` was a directory (`corpus/bulk`) and the whole verify run crashed with
`IsADirectoryError`. A directory is not a valid DataFile path; that is a schema violation for
one artifact, not a reason to lose the other six checks.

## Decision

1. **`snapshot: bool`** is an artifact property, default false, declared on the three types
   that carry `content_hash` with a path (`Script`, `DataFile`, `PaperSection`) in
   `research.yaml`, and validated in `seldon.core.artifacts` on both create and update: only a
   real Python bool is accepted. The CLI parses `-p snapshot=true|false|1|0|yes|no`
   (case-insensitive) to a bool; any other literal is passed through so the validator refuses
   it rather than a string `"yes"` being stored and later read as truthy.

   Semantics: the artifact records a file as it stood at registration; `content_hash` is the
   identity of that state; the live file is expected to diverge.

2. **`verify` skips snapshot artifacts** in the drift comparison and reports them in the
   same line, informationally: `All N tracked files in sync — K snapshot artifacts, drift
   not checked`. They are not counted in N.

3. **`--fix` never touches a snapshot artifact's hash.** `--fix` delegates to `paper sync`;
   `sync_section` now returns status `snapshot` for a flagged artifact without computing or
   writing a hash. `paper sync` reports the count.

4. **Directory guard.** A path that resolves to a directory is reported as
   `N path(s) resolve to a directory (schema violation): <path> (<type> <id8>)`, the check
   continues, and the result is `fixable=False` unless real drift is also present (paper sync
   cannot repair a registration error).

## What this is not

- Not a new artifact type. A snapshot DataFile is a DataFile.
- Not a change to the hash algorithm or to what `content_hash` means; the flag changes only
  whether verify compares it.
- Not a project-database migration. Owning projects set the flag per artifact:

  ```
  seldon artifact update <artifact_id_or_prefix> -p snapshot=true
  ```

## Verification

`tests/test_verify_snapshot.py`, 25 tests. Every verify-side behaviour has a positive control
(the same artifact with `snapshot` cleared fails; the same section without the flag is synced).
Mutation-tested by hand on 2026-09-02: disabling the verify skip (3 failures), the sync guard
(1), the directory guard (2 crashes), and the bool validator (8) each fails the module.
