# Seldon Paper Build — Database-Driven Manuscript Assembly

**Date:** 2026-03-15
**Status:** Design — AD-011
**Priority:** High — this solves a three-times-repeated failure mode

---

## AD-011: Database-Driven Paper Assembly (Not Flat Files)

**Decision:** Paper manuscripts cite Seldon Result artifacts by reference, not by literal value. The build step resolves references against the graph, validates consistency, and fails loudly on mismatches. No manual numbers registry. No manual figure map. The graph IS the registry.

**Rationale (from direct experience, three iterations):**

1. **Pragmatics paper v1:** No registry. Numbers drifted between sections. AI editing sessions introduced contradictions. Scorched earth restart required.
2. **Pragmatics paper v2:** Manual `numbers_registry.md` with status tracking. Manual `figure_table_map.yaml`. Better, but maintenance burden was high and AI editors still didn't reliably read the registry before writing numbers.
3. **Pragmatics paper v3 (final):** Same manual approach with stricter conventions. Worked, but required constant vigilance and manual audits. The registry was the source of truth but nothing *enforced* it.

**The failure pattern:** AI editing tools operate on flat text. They have no mechanism to check "is this number I'm about to write consistent with the authoritative value?" They operate on vibes and context window, which is stale by definition. Every editing pass is an opportunity for drift.

**The fix:** Numbers are never written as literals in section files. They're written as references that the build step resolves:

```markdown
The entropy fitness discovered Leibniz in {{result:entropy_minimal_5_5:value}}/5 seeds
({{result:entropy_minimal_5_5:units}}) within {{result:entropy_minimal_runtime:value}} seconds.
```

The build step:
1. Parses all `{{result:NAME:FIELD}}` references in section files
2. Queries Seldon's graph for each referenced Result
3. Substitutes the current verified value
4. **Fails with a clear error if:**
   - A referenced result doesn't exist in the graph
   - A referenced result is in `stale` state
   - A referenced result is in `proposed` state (not yet verified)
   - The same result is referenced with inconsistent formatting across sections
5. Assembles the resolved sections into the final `.qmd` file
6. Renders via Quarto

**What this eliminates:**
- Manual numbers registry (the graph replaces it)
- Number drift between sections (references resolve to one value)
- AI editors corrupting values (they write references, not values)
- Manual audit before submission (the build IS the audit)
- Stale figures in the paper (same pattern: `{{figure:F1:path}}` resolves from graph)

---

## Reference Syntax

### Results
```
{{result:NAME:FIELD}}
```

Fields: `value`, `units`, `description`, `state`

Examples:
```markdown
{{result:entropy_minimal_5_5:value}}         → 1.0
{{result:gp_pop2000_5_5:value}}              → 1.0  
{{result:entropy_minimal_runtime:value}}     → 369.9
{{result:info_rate_3_32:value}}              → 3.32
{{result:wrong_limit_ti_15_93:value}}        → 15.93
```

### Figures
```
{{figure:NAME:FIELD}}
```

Fields: `path`, `caption`, `state`

### Citations
```
{{cite:NAME:bibtex_key}}
```

Resolves to the BibTeX key, e.g., `@schmidt2009distilling`

---

## Build Script Design

```python
# paper/build.py (sketch)

import re
import sys
from pathlib import Path

# Connect to Seldon graph
from seldon.config import load_project_config, get_neo4j_driver
from seldon.core.graph import get_artifacts_by_type

REFERENCE_PATTERN = re.compile(r'\{\{(result|figure|cite):([^:}]+):([^}]+)\}\}')

def resolve_references(text: str, artifacts: dict) -> str:
    """Replace all {{type:name:field}} references with graph values."""
    errors = []
    
    def replacer(match):
        ref_type, name, field = match.groups()
        key = f"{ref_type}:{name}"
        if key not in artifacts:
            errors.append(f"MISSING: {key} not found in graph")
            return match.group(0)  # leave unreplaced
        
        artifact = artifacts[key]
        
        # Validate state
        state = artifact.get("state", "unknown")
        if state == "stale":
            errors.append(f"STALE: {key} is in stale state — re-verify before citing")
        elif state == "proposed":
            errors.append(f"UNVERIFIED: {key} is still proposed — verify before citing")
        
        value = artifact.get(field)
        if value is None:
            errors.append(f"NO FIELD: {key} has no field '{field}'")
            return match.group(0)
        
        return str(value)
    
    resolved = REFERENCE_PATTERN.sub(replacer, text)
    return resolved, errors


def build():
    # 1. Load all artifacts from Seldon graph
    config = load_project_config()
    driver = get_neo4j_driver(config)
    database = config["neo4j"]["database"]
    
    artifacts = {}
    with driver.session(database=database) as session:
        for record in session.run("MATCH (a:Artifact) WHERE a.name IS NOT NULL RETURN a").data():
            a = dict(record["a"])
            atype = a.get("artifact_type", "").lower()
            name = a["name"]
            # Map artifact_type to reference type
            type_map = {"Result": "result", "Figure": "figure", "Citation": "cite"}
            ref_type = type_map.get(a.get("artifact_type"), a.get("artifact_type", "").lower())
            artifacts[f"{ref_type}:{name}"] = a
    
    driver.close()
    
    # 2. Read and resolve all section files
    sections_dir = Path("paper/sections")
    all_errors = []
    resolved_sections = []
    
    for section_file in sorted(sections_dir.glob("*.md")):
        text = section_file.read_text()
        resolved, errors = resolve_references(text, artifacts)
        if errors:
            all_errors.extend([(section_file.name, e) for e in errors])
        resolved_sections.append((section_file.name, resolved))
    
    # 3. Report errors
    if all_errors:
        print("\n=== BUILD ERRORS ===")
        for filename, error in all_errors:
            print(f"  {filename}: {error}")
        print(f"\n{len(all_errors)} errors found. Fix before rendering.\n")
        
        if any("STALE" in e or "MISSING" in e for _, e in all_errors):
            print("FATAL: Stale or missing references. Build aborted.")
            sys.exit(1)
        else:
            print("WARNING: Non-fatal issues. Build continues.\n")
    
    # 4. Assemble .qmd
    # ... frontmatter + abstract + resolved sections → draft.qmd
    
    # 5. Render
    # subprocess.run(["quarto", "render", "draft.qmd"])


if __name__ == "__main__":
    build()
```

---

## What This Means for AI Editing

When an AI editor works on a section file, it sees:

```markdown
The entropy fitness discovered Leibniz in {{result:entropy_minimal_5_5:value}}/5 seeds
```

It CAN'T corrupt the number because the number isn't there — only the reference is. It can restructure the sentence, change the prose, move paragraphs around. But the actual value comes from the graph at build time.

If the AI removes a reference or replaces it with a literal, the build step will catch it — either the literal won't match the graph value (detectable by a post-build audit), or the reference count will change (detectable by diff).

If the AI invents a reference that doesn't exist (`{{result:made_up_thing:value}}`), the build fails with `MISSING: result:made_up_thing not found in graph`.

---

## Construct Validity Checking

Beyond number resolution, the build can run cross-reference checks:

1. **Consistency check:** Every `{{result:X:value}}` in the paper should resolve to the same value regardless of which section it appears in. (Trivially true with reference resolution, but catches cases where someone wrote a literal instead of a reference.)

2. **Coverage check:** Every Result artifact in verified state should be referenced by at least one PaperSection. Unreferenced results are either unused or missing from the paper.

3. **Provenance check:** Every referenced Result should have a GENERATED_BY or DERIVED_FROM link. Results with incomplete provenance get a build warning.

4. **Citation check:** Every `{{cite:X:bibtex_key}}` should have a matching entry in `references.bib`. Missing bib entries fail the build.

5. **Figure check:** Every `{{figure:X:path}}` should point to a file that actually exists. Missing figures fail the build.

6. **Staleness check:** Any referenced artifact in `stale` state fails the build. You must re-verify before the paper compiles.

---

## Implementation Plan

**Phase 1 (do now for leibniz-pi):**
- Write `paper/build.py` with reference resolution
- Use `{{result:NAME:value}}` syntax in section files
- Build validates against Seldon graph
- Quarto renders the resolved output

**Phase 2 (after leibniz-pi paper validates the pattern):**
- Move build.py logic into Seldon as `seldon paper build`
- Add `seldon paper init` that scaffolds the directory structure
- Add `seldon paper audit` that runs all construct validity checks without building
- Add `seldon paper numbers-registry` that exports the graph view as markdown (for human review, not as source of truth)

**Phase 3 (after second paper validates):**
- Template system for different venues (GECCO format, Quarto journal template, etc.)
- Figure generation integration (build step runs `generate_figures.py` before assembly)
- Writing conventions as a Seldon config checked at build time (sentence length, banned words, etc.)

---

## Relationship to Existing Patterns

| Manual Pattern | Seldon Paper Build Equivalent |
|----------------|-------------------------------|
| `numbers_registry.md` | `seldon result list` + build-time resolution |
| `figure_table_map.yaml` | Figure artifacts + build-time resolution |
| `WRITING_CONVENTIONS_PAPER.md` | Stays as-is (prose rules, not data) |
| Manual audit before submission | `seldon paper audit` / build validation |
| Copy-paste numbers into sections | `{{result:NAME:value}}` references |
| Human checks for contradictions | Build fails on stale/missing/inconsistent |

---

*This is AD-011. It replaces the paper_authoring_convention.md design spec written earlier today, which described the flat-file pattern. The flat-file pattern is the problem, not the solution.*
