# CC Task: Implement `seldon verify --strict` Mode

**Date:** 2026-04-05
**Project:** seldon
**Reference:** Design note `docs/design/2026-04-05_hard_threshold_gating_for_mechanical_qc.md`, AD-016, AD-018, AD-020

---

## Context

`seldon verify` currently runs 7 checks and exits with code 0 (clean), 1 (warnings), or 2 (issues). All failures and warnings are treated equally — the exit code reflects the worst finding, but there is no distinction between mechanical violations (hash mismatch, broken reference) and advisory findings (stale artifacts, open blocking tasks).

This task adds a `--strict` flag that classifies checks into Tier A (hard gates — mechanical, unambiguous) and Tier B (advisory — judgment required). Under `--strict`, only Tier A failures produce a non-zero exit code.

**This task does NOT:**
- Modify state transition logic (Option A from design note — deferred)
- Add PQ-01 integration into verify (PQ checks live in `paper audit`, separate concern)
- Add an `--override` mechanism (deferred until `--strict` is dogfooded)
- Change default behavior — `seldon verify` without `--strict` behaves identically to current

## Tier Classification

### Tier A — Hard Gates (block under `--strict`)

| Check | Current symbol on failure | Rationale |
|-------|--------------------------|-----------|
| File hashes | `fail` | Content and graph are out of sync. Always wrong. |
| Ontology freshness | `fail` | Stale replica means glossary checks run against stale vocabulary. Staleness propagates — an out-of-sync ontology silently undermines downstream checks. |
| Glossary compliance | `fail` | Term used without definition. Mechanical. |
| Reference resolution | `fail` | Broken reference token. Mechanical. |
| Unregistered files | `fail` | Content file with no graph artifact. Mechanical. |

### Tier B — Advisory (report only, even under `--strict`)

| Check | Current symbol | Rationale |
|-------|----------------|-----------|
| Stale artifacts | `warn` | Informational — author may be mid-revision. |
| Blocking tasks | `warn` | Informational — author aware of blockers. |

## Deliverables

### 1. Add `TIER_A_CHECKS` constant to `verify.py`

At module level, after the `SYMBOL_MAP` dict, add:

```python
# Checks whose failures block under --strict mode.
# Advisory checks (stale artifacts, blocking tasks) are always reported
# but never block.
TIER_A_CHECKS = frozenset({
    "File hashes",
    "Ontology",
    "Glossary",
    "References",
    "Unregistered files",
})
```

### 2. Add `--strict` flag to CLI command

Add to the `@click.option` decorators on `verify_command`:

```python
@click.option("--strict", is_flag=True, default=False,
              help="Exit non-zero only on Tier A (mechanical) violations. "
                   "Advisory findings are reported but do not affect exit code.")
```

Update the function signature to accept `strict`.

### 3. Modify exit code logic in `verify_command`

Replace the current exit code block:

```python
    # Exit code
    has_fail = any(r.symbol == "fail" for r in results)
    has_warn = any(r.symbol == "warn" for r in results)

    if has_fail:
        raise SystemExit(2)
    elif has_warn:
        raise SystemExit(1)
    else:
        raise SystemExit(0)
```

With:

```python
    # Exit code
    if strict:
        # Only Tier A failures are blocking
        tier_a_fail = any(
            r.symbol == "fail" and r.name in TIER_A_CHECKS
            for r in results
        )
        if tier_a_fail:
            raise SystemExit(2)
        else:
            raise SystemExit(0)
    else:
        # Default behavior: any fail → 2, any warn → 1, else 0
        has_fail = any(r.symbol == "fail" for r in results)
        has_warn = any(r.symbol == "warn" for r in results)
        if has_fail:
            raise SystemExit(2)
        elif has_warn:
            raise SystemExit(1)
        else:
            raise SystemExit(0)
```

### 4. Update report output for `--strict` mode

In `_print_report`, add a `strict` parameter. When strict is True, append a label to Tier B findings so the user knows they're advisory:

- Pass `strict` through from `verify_command` to `_print_report`
- After the summary line, if `strict` and there are Tier B findings that would have been failures, add:
  ```
  Strict mode: N advisory finding(s) reported but not blocking.
  ```

### 5. Update docstring and module docstring

Update the module docstring at the top of `verify.py` to document:

```
Exit codes:
    Default mode:
        0 — all clean
        1 — warnings only (stale artifacts, open blocking tasks)
        2 — issues found (hash mismatch, ontology drift, unresolvable refs, unregistered files)
    Strict mode (--strict):
        0 — no Tier A violations (advisory findings may exist)
        2 — Tier A violations found (file hashes, ontology, glossary, references, unregistered files)
```

### 6. Add tests

In the appropriate test file (find existing verify tests), add:

- **Test: `--strict` exits 0 when only Tier B failures exist** — mock check results with stale artifacts `warn` but all Tier A checks `pass`. Assert exit code 0.
- **Test: `--strict` exits 2 when Tier A failure exists** — mock check results with file hash `fail`. Assert exit code 2.
- **Test: `--strict` exits 2 on ontology drift** — mock check results with ontology `fail`. Assert exit code 2.
- **Test: default mode unchanged** — existing tests should still pass. No regressions.

### 7. Update CLAUDE.md

In the **Paper Editing Workflow** section, update the mandatory edit cycle to mention `--strict`:

After the existing code block (`python paper/check_glossary.py` / `seldon paper sync` / `seldon paper build --no-render`), add:

```
For CC tasks, append `seldon verify --strict` to the cycle. If it exits non-zero,
fix Tier A violations before state transition or commit.
```

## Success Criteria

1. `seldon verify` (no flag) — behavior identical to current. All existing tests pass.
2. `seldon verify --strict` — exits 0 when only advisory findings exist, exits 2 when any Tier A check fails.
3. `seldon verify --strict` — exits 2 when ontology is out of sync.
4. `seldon verify --help` shows the `--strict` option with description.
5. At least 3 new tests covering strict mode exit code behavior.
6. CLAUDE.md updated with `--strict` guidance.
7. Module docstring updated.

## Do NOT

- Modify `core/artifacts.py` or `transition_state()` — that's Option A, deferred
- Add PQ-01 checks to verify — PQ checks are `paper audit`'s concern
- Add `--override` flag — deferred until `--strict` is dogfooded
- Change the Tier A/B classification from what's listed above without asking first
