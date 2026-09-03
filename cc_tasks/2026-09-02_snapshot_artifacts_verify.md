# CC Task: Snapshot artifacts must not fail the file-hash drift check

**Date:** 2026-09-02
**Authored by:** Desktop session (from ai-readiness-kg findings, `cc_tasks/2026-09-01_machine_diagnostic_stub_RESULT.md` §3)
**Immutable once written. Before starting: glob and read all sibling `2026-09-02_snapshot_artifacts_verify_ADDENDUM*.md` files.**

## Finding

`seldon verify`'s file-hash check is a drift instrument: it compares each artifact's stored `content_hash` to the file's current bytes and reports a mismatch as a problem. Some artifacts are deliberate snapshots (a schema at v0.1; a corpus manifest as of round 2). For those, drift is the point of the artifact, and `verify --fix` would erase the record by rewriting the stored hash to today's bytes. In ai-readiness-kg this produces a permanent false failure on three artifacts (`kg-schema-v0.1`, `corpus-manifest`, `corpus-manifest-round2`), which trains operators to ignore verify output.

A second defect from the same finding, already fixed locally in that project but worth guarding in code: `check_file_hashes` called `read_bytes()` on an artifact whose `path` was a directory and crashed the whole verify run. A `DataFile` path that resolves to a directory should be reported as a schema violation, not raise.

## Decision

Add an artifact property `snapshot: bool` (default false). Semantics: the artifact records a file as it stood at registration; its `content_hash` is the identity of that state, and the live file is expected to diverge. `verify` skips snapshot artifacts in the drift check and reports them in a separate informational line (`N snapshot artifacts, drift not checked`). `verify --fix` never touches a snapshot artifact's hash.

Directory guard: if an artifact's `path` resolves to a directory, `verify` reports it as a schema violation for that artifact and continues; it does not raise.

## Steps

1. Locate the artifact model, the CLI registration surface, and `check_file_hashes`. Add `snapshot` to the model with default false and a validator that accepts only bool. Expose it on registration and on the update/edit path so existing artifacts can be flagged.
2. Implement the skip + informational line and the `--fix` exclusion. Implement the directory guard.
3. Tests, with a mutation-tested positive control per project practice: a snapshot artifact whose file has changed passes verify; the same artifact with `snapshot` cleared fails; a non-snapshot artifact still fails on drift; a directory-path artifact yields a violation line and verify completes.
4. Ontology/glossary: if the artifact property vocabulary is documented, add `snapshot` with the one-paragraph semantics above. No new artifact type.
5. Design decision entry per this repo's convention, referencing the ai-readiness-kg RESULT that surfaced it.

## Constraints

- Zero model calls. Code, tests, docs only.
- Do not change hash algorithms or the meaning of `content_hash`.
- Do not touch any project database; the flag is set per artifact by the owning project after this lands.

## Completion

- Full test suite passes; report the count.
- Write `cc_tasks/2026-09-02_snapshot_artifacts_verify_RESULT.md`, including the exact CLI invocation an owning project uses to set `snapshot` on an existing artifact.
- `seldon cc complete cc_tasks/2026-09-02_snapshot_artifacts_verify.md`; commit and push.
