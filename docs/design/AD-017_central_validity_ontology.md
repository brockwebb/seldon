# AD-017: Central Validity Ontology

**Date:** 2026-03-22
**Updated:** 2026-03-28 — Implemented. Master/replica architecture built and deployed.
**Status:** Implemented
**Context:** Multiple projects (ai4stats, pragmatics, ai-workflow-design, future work) reference SFV validity terminology. Each maintaining its own definitions creates the exact terminology drift threat (T1) that SFV warns about.

---

## Decision

The canonical validity ontology lives in the **main Seldon repo** (`seldon/ontology/validity/VALIDITY_VOCABULARY.md`), not in any individual project repo. A dedicated master Neo4j database (`seldon-ontology`) holds the ingested graph. Project-level Seldon instances hold read-only replicas synced from master via epoch-based pull.

## Architecture (As Built)

```
VALIDITY_VOCABULARY.md  (human-readable source, version-controlled)
        │
        ▼  seldon ontology ingest (writes to master ONLY)
┌──────────────────────────────────┐
│  seldon-ontology (MASTER DB)     │  Single source of truth
│  :Artifact:OntologyTerm nodes    │  51 terms, 36 relationships (epoch 1)
│  :_OntologyMeta {epoch: N}       │  Monotonic epoch counter
└──────────┬───────────────────────┘
           │
           │  seldon ontology sync (read-only pull, epoch-based delta)
           │
     ┌─────┴──────┬──────────────┐
     ▼            ▼              ▼
  seldon-      seldon-        seldon-
  ai-workflow  sfv-paper      future-X
  -design      (pending)
  
  Read-only    Read-only      Auto-sync
  replica      replica        on init
  epoch: 1     
```

**Key properties:**
- **One master, many replicas.** `seldon-ontology` is the single write target. Project databases hold read-only copies.
- **Epoch-based sync.** Master has a monotonic epoch counter. Each project stores the epoch it last synced to. `seldon ontology sync` pulls deltas since last epoch.
- **Write protection enforced.** `create_artifact()` and `update_artifact()` refuse to touch OntologyTerm artifacts in project databases where `inheritance: read-only`.
- **Same artifact UUIDs everywhere.** Master assigns UUIDs; replicas copy them verbatim. References work across the boundary.
- **CDN/read-replica pattern.** Low write frequency, high read frequency. Vocabulary stabilizes over time; syncs become rare.

## Principles

1. **Markdown is the initialization source.** Human-readable, version-controlled definitions maintained in the Seldon repo.
2. **Master Neo4j database is the runtime source.** `seldon-ontology` holds the canonical graph. Projects sync from it.
3. **Seldon core owns the definitions.** No individual project is the de facto owner of cross-project terminology.
4. **Updates propagate via explicit sync.** Update the markdown → `seldon ontology ingest` → `seldon ontology sync` per project.
5. **Project instances inherit, they don't own.** Project-specific terms are separate artifacts linked to canonical terms via `references_ontology` relationships, not forks of definitions.
6. **No drift by design.** Read-only replicas cannot be modified locally. Changes flow upstream through the canonical vocabulary file only.

## Implementation

| Component | Location |
|-----------|----------|
| Vocabulary source | `seldon/ontology/validity/VALIDITY_VOCABULARY.md` |
| Parser | `seldon/ontology/parser.py` |
| CLI commands | `seldon/commands/ontology.py` (ingest, sync, list) |
| Domain config | `seldon/domain/research.yaml` (OntologyTerm type, state machine, 6 relationship types) |
| Write protection | `seldon/core/artifacts.py` (guard in create_artifact/update_artifact) |
| Tests | `tests/test_ontology.py` (27 tests) |

**CLI commands:**
- `seldon ontology ingest` — parses vocabulary markdown, writes to `seldon-ontology` master DB, increments epoch
- `seldon ontology sync` — pulls from master to project's local DB (epoch-based delta)
- `seldon ontology list [--category] [--verbose] [--master]` — display terms

**Term categories parsed:** framework, sub_dimension, threat, severity, tax_tier, argument, countermeasure, metric, classical_validity, terminology_decision, framework_term, boilerplate

## Relationship to SFV

This architecture is SFV operationalized at the organizational level:
- **Countermeasure for T1 (Semantic Drift):** Terms defined once in canonical vocabulary, replicated read-only
- **Countermeasure for T4 (State Supersession Failure):** Epoch-based sync ensures replicas reflect latest master state
- **Countermeasure for T5 (State Discontinuity):** New projects inherit existing terminology automatically on init
- **Config-driven vocabulary** as described in the SFV engineering countermeasures

## Consequences

- All future projects get validity terminology for free on `seldon init` (if `shared_ontology` configured)
- Updating a definition requires: edit markdown → ingest → sync per project
- Project-specific terms link to shared terms via graph relationships, never fork definitions
- 51 terms and 36 relationships ingested from VALIDITY_VOCABULARY.md at epoch 1

## Related

- Canonical vocabulary: `seldon/ontology/validity/VALIDITY_VOCABULARY.md`
- CC task: `cc_tasks/2026-03-27_ad017_shared_ontology_implementation.md`
- AD-013: Documentation as Traceability
- SFV Threat Taxonomy (T1-T5)
