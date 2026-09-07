# CC Task — Precedence check must read Artifact edges only

**Date:** 2026-09-07
**Project:** seldon
**Authored by:** Desktop session (ai-readiness-kg `2026-09-06_scan_targets_RESULT.md` §3; seldon ResearchTask `1ad92c2b`)
**Premise:** `seldon/core/precedence.py:read_edges()` runs `MATCH (a)-[r:PRECEDES]->(b)` with no endpoint label. A project database that co-tenants a domain KG (ai-readiness-kg's `kg/schema.yaml` whitelists `precedes: Concept → Concept`, BFO_0000063) yields 117 `? [missing] → ? [missing]` in `seldon verify` and makes readiness unanswerable. The co-tenancy under disjoint labels is the documented arrangement.
**Zero model spend.**

**Immutable once written. Changes require a new task file or an `_ADDENDUM-NN.md` sibling. Glob and read all siblings `2026-09-07_precedence_artifact_labels_ADDENDUM*.md` before starting.**

---

1. Every Cypher in `precedence.py` (and any other Seldon read of `PRECEDES`, `SUPERSEDED_BY`, `BLOCKS`, `DEPENDS_ON` — audit with a grep for unlabelled `MATCH (` patterns across `seldon/`) binds `:Artifact` on both endpoints. Keep the dangling-endpoint detection: an `:Artifact` endpoint without `artifact_id` or of the wrong type still reports as illegal.
2. Test: a fixture DB with a `(:Concept)-[:PRECEDES]->(:Concept)` edge beside a valid task chain; `seldon verify` green; readiness and chains unchanged; the illegal-endpoint case on an `:Artifact` edge still fires.
3. Add the unlabelled-pattern lint from ai-readiness-kg (`230b282f` §1.2) to seldon's own test suite for `seldon/core/` and `seldon/commands/`, allowlisting only patterns that are deliberately label-free and commented as such.
4. While there: `seldon task show <prefix>` resolves prefixes like every other task command (the RESULT of `012a1a36` §8).
5. AD addendum to AD-029 recording the co-tenancy rule: Seldon never reads a relationship by name alone.

RESULT: `cc_tasks/2026-09-07_precedence_artifact_labels_RESULT.md`. Full suite, `seldon verify` on the seldon repo, close `1ad92c2b` with the RESULT as evidence, `seldon cc complete`, commit, push.
