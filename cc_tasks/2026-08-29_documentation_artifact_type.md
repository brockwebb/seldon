# Research domain config: add Documentation artifact type with ResearchTask linkage

**Date:** 2026-08-29. **Origin:** ai-readiness-kg task 3d86f16d discrepancy report.

## Defect

The research domain config has no `Documentation` artifact type. 3d86f16d had to register two project documents (methodology, crosswalk brief) as `DesignNote`, and `DesignNote` permits links only to `OntologyTerm` and `ArchitecturalDecision` — not `ResearchTask`. The producing-task linkage survives only as a free-text provenance property, invisible to every edge query. Documents produced by tasks are a core provenance pattern; the graph currently cannot express it.

## Change (research domain config only; master ontology untouched)

1. Add artifact type `Documentation` — state machine `draft → active → superseded` (no `verified`; documents are not gated results).
2. Allowed edges: `Documentation -produced_by-> ResearchTask`; `Documentation -documents-> {ArtifactType.*}` (wide by design — a document may describe anything); `Documentation -supersedes-> Documentation`.
3. Migration: re-type the two 3d86f16d artifacts from `DesignNote` to `Documentation` via typed events (append, never mutate), then create their `produced_by` edges to 3d86f16d. Verify with a graph query for `(:Documentation)-[:produced_by]->(:ResearchTask)` returning 2.
4. Tests: config loader accepts the type; edge validation rejects `Documentation -produced_by-> DesignNote` (wrong target); the two migrated artifacts round-trip through event replay.

## Prior art (DD-025 block)

Internal: ai-readiness-kg 3d86f16d RESULT (the defect record); AD-002 (domain config is schema, not code — this is precisely the kind of change AD-002 exists to make cheap); AD-006/AD-007 (Result and ResearchTask as first-class types establish the pattern Documentation completes). External: none required — this is vocabulary completion within an existing design, not a new design.

## Exit

Config change + tests green + migration events applied + replay verified; `seldon cc complete`; RESULT; commit and push.
