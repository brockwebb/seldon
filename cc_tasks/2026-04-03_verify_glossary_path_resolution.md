# CC Task: Fix `seldon verify` Glossary Path Resolution

**Date:** 2026-04-03
**Repo:** seldon
**Scope:** Bug fix in `seldon/commands/verify.py`
**Related:** AD-017 (Central Validity Ontology), AD-018 (Document Structure Graph)

---

## Problem

`check_glossary()` in `verify.py` (line 202) hardcodes `paper/glossary.md` as the glossary path. Projects that use `book/glossary.md` (e.g., ai-workflow-design) get a silent "No glossary file found — skipping" and the entire glossary compliance check is non-functional. No banned synonym detection, no terminology consistency enforcement, nothing.

This was discovered when a CC task in ai-workflow-design added a glossary entry without any guardrail catching potential inconsistencies. The verify gate was absent, not passing.

## Root Cause

`_tracked_content_dirs()` (line 69) already handles both `paper/` and `book/` directories and reads from `seldon.yaml` config via `get_sections_dir()`. But `check_glossary()` doesn't use this pattern — it's a hardcoded path from before AD-018.

## Fix

### Step 1: Update `check_glossary()` to resolve the glossary path from config

Replace the hardcoded path with a resolution function that checks:

1. `seldon.yaml` → `paths.paper` or `paths.book` → look for `glossary.md` in that directory
2. Fallback to `paper/glossary.md` (existing behavior)
3. Fallback to `book/glossary.md`
4. If none found: return the current "No glossary file found" result — but change severity to WARN, not silent skip

Suggested implementation:

```python
def _find_glossary(project_dir: Path, config: dict = None) -> Path | None:
    """Locate glossary.md using config paths, then fallbacks."""
    # Try config-specified paths first
    if config:
        for key in ("paper", "book"):
            content_dir = config.get("paths", {}).get(key)
            if content_dir:
                candidate = project_dir / content_dir / "glossary.md"
                if candidate.exists():
                    return candidate

    # Fallback to conventional locations
    for candidate in [
        project_dir / "paper" / "glossary.md",
        project_dir / "book" / "glossary.md",
    ]:
        if candidate.exists():
            return candidate

    return None
```

### Step 2: Similarly resolve `check_glossary.py` path

The check script path (line 212) is also hardcoded to `paper/check_glossary.py`. Apply the same resolution pattern. The script might live alongside the glossary in the content directory, or at project root.

Search order for the check script:
1. Same directory as the found glossary
2. `paper/check_glossary.py` (existing)
3. Project root `check_glossary.py`

### Step 3: Pass config to `check_glossary()`

The `run_verify()` function (line 591) already has the config loaded. Pass it through:

```python
# Before (line 637):
check_glossary(project_dir),

# After:
check_glossary(project_dir, config=config),
```

Update the function signature accordingly.

### Step 4: Update the check result message

When glossary is found at a non-default path, include the path in the result summary so the operator knows which file was checked:

```python
# Instead of just "Glossary check passed"
summary=f"Glossary check passed ({glossary_path.relative_to(project_dir)})"
```

## Testing

1. Run `seldon verify` in a project with `paper/glossary.md` — should still work (regression)
2. Run `seldon verify` in ai-workflow-design (has `book/glossary.md`) — should now find and check it
3. Run `seldon verify` in a project with no glossary at all — should warn, not silently skip
4. Add a test in `tests/test_verify.py` for each case

## Do NOT

- Change the glossary file format or the check_glossary.py script behavior
- Add glossary management commands (that's a separate design decision)
- Touch the ontology sync path — this is only about the verify check finding the file
