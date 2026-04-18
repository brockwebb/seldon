# Seldon Issue: check_glossary.py parser extracts explanation text as banned phrases

**Date:** 2026-03-26
**Severity:** Substantive (causes false positive violations; workaround exists but shouldn't be needed)
**Found during:** SFV paper edit cycle on 11_conclusion.md
**Component:** `check_glossary.py` — glossary parser

---

## Problem

The `parse_glossary()` function uses a regex to extract all quoted strings from "Do not write:" lines as banned phrases. It does not distinguish between:

1. Quoted strings that are the actual banned phrases
2. Quoted strings that appear inside explanation parentheticals

Example from the SFV paper glossary, T1 entry:

```
: Do not write: "terminology drift" (use "semantic drift" as the threat name; ...), "concept drift" (...)
```

The parser extracts three banned phrases: `"terminology drift"`, `"semantic drift"`, and `"concept drift"`. The second one is the *preferred* term, not a banned term. It appears in the explanation text, not as a banned synonym.

Result: every correct use of "Semantic Drift" in prose is flagged as a violation.

## Current Workaround

Reword the explanation to avoid quoting the preferred term:

```
: Do not write: "terminology drift" (Semantic Drift is the correct threat name; ...), "concept drift" (...)
```

This works but is fragile and non-obvious. Contributors writing glossary entries will naturally quote preferred terms in explanations and hit this bug.

## Proposed Fix

The parser should only extract banned phrases from the text *before* the first parenthetical, or use a more structured format that separates banned phrases from explanations. Options:

**Option A:** Only extract quoted strings that appear before the first `(` on the line. Explanation text inside parentheticals is ignored.

**Option B:** Use a delimiter (e.g., `|` or `→`) between the banned phrase and its explanation instead of parentheticals:
```
: Do not write: "terminology drift" → Semantic Drift is the correct threat name, "concept drift" → established ML term for data distribution shift
```

**Option C:** Add a `PREFERRED:` line type that registers the correct term, and the parser skips any banned-phrase match that is a substring of a preferred term.

Option A is the simplest and least disruptive to existing glossaries.

## Impact

Affects any project using check_glossary.py where "Do not write" explanations quote the preferred term. The leibniz-pi glossary avoided this by accident (its explanations don't quote preferred terms). The SFV paper glossary hit it on the first edit cycle.

## SFV Incident Catalog Reference

Logged as SFV-INC-006 (T2: False State Injection at the tooling level — the parser confidently asserts a phrase is banned when it was never banned).

---

*This is technically a T2 at the meta level: the tooling confabulated a ban that was never specified. The irony of an SFV countermeasure tool exhibiting an SFV threat is not lost.*
