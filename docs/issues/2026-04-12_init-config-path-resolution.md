# Seldon Issue: `seldon init` vs `load_project_config` — Defensive Path Resolution

**Date:** 2026-04-12
**Reported by:** Brock (via Arnold project)
**Severity:** Medium — causes total MCP tool failure for affected projects

---

## Problem

`seldon init` correctly places `seldon.yaml` at project root. But when a project gets initialized incorrectly (e.g., by a CC session that puts files in `.seldon/` instead of root), `load_project_config()` fails hard with no fallback and no diagnostic help.

This happened with the Arnold project. The config ended up at `.seldon/seldon.yaml` instead of `seldon.yaml`. Every MCP tool failed. The error message says "Run `seldon init`" — but re-running init would create a duplicate database and overwrite state.

## Root Cause

`load_project_config()` in `config.py` only checks one path:

```python
config_path = base / "seldon.yaml"
```

No fallback to `.seldon/seldon.yaml`. No detection of the misconfiguration. No helpful error message beyond "not found."

## Requested Fix

1. **`load_project_config()` should check both locations** with clear precedence:
   - First: `base / "seldon.yaml"` (canonical, per init command)
   - Fallback: `base / ".seldon" / "seldon.yaml"` (common misplacement)
   - If found in fallback location, emit a warning: `"seldon.yaml found in .seldon/ — expected at project root. Run: mv .seldon/seldon.yaml ./seldon.yaml"`

2. **`seldon init` should validate post-init state** — after writing files, verify that `load_project_config()` can find them. If not, fail loud.

3. **`seldon init` should refuse to create files inside `.seldon/`** — `.seldon/` is for session state only. If a CC session or script tries to write config there, it should be caught.

4. **`seldon_events.jsonl` has the same problem** — `event_store.path` in the config is relative, and if the config is in `.seldon/`, the events file ends up there too. The path resolution should be relative to project root regardless of where the config file is found.

5. **Consider `SELDON_DEFAULT_PROJECT` env var behavior** — if this is set and the project has the misplaced config, it silently fails. The env var path should also get the two-location check.

## Context

This isn't theoretical — it happened because a Claude Code session initialized the project and put files in the wrong place. CC sessions follow instructions literally. If `seldon init` doesn't guard against this, it'll happen again. The fix is cheap and prevents a class of "everything is broken and the error doesn't help" failures.
