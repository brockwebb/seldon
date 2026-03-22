# AD-017: Central Validity Ontology

**Date:** 2026-03-22
**Status:** Accepted
**Context:** Multiple projects (ai4stats, pragmatics, future work) reference SFV validity terminology. Each maintaining its own definitions creates the exact terminology drift threat (T1) that SFV warns about.

---

## Decision

The canonical validity ontology lives in the **main Seldon repo**, not in any individual project repo. Project-level Seldon instances inherit shared terms through the Neo4j graph, not through owned files.

## Architecture

```
seldon/ (main repo)
  └── ontology/
      └── validity/
          └── SFV_TERMINOLOGY_BASELINE.md   (human-readable source)
          └── ...future shared glossaries...
              │
              ▼  (ingestion script populates graph)
          Neo4j (shared namespace: :ValidityTerm, :Threat, :SubDimension nodes)
              │
              ▼  (graph queries at runtime)
          seldon-ai4stats    ← reads from graph
          seldon-pragmatics  ← reads from graph
          seldon-future-X    ← reads from graph
```

## Principles

1. **Markdown is the initialization source.** Human-readable, version-controlled definitions maintained in the Seldon repo.
2. **Neo4j is the runtime source.** Projects query the graph for canonical terms. No local copies.
3. **Seldon core owns the definitions.** No individual project is the de facto owner of cross-project terminology.
4. **Updates propagate centrally.** Update the markdown, re-run ingestion, all projects see the change through the graph.
5. **Project instances inherit, they don't own.** A project instance can extend or annotate terms for its own context, but the canonical definition comes from the shared namespace.

## Migration for Existing Projects

- Identify where ai4stats, pragmatics, and any other projects currently define validity terms locally
- Move canonical definitions to `seldon/ontology/validity/`
- Replace local definitions with graph references
- Verify no project-level overrides conflict with canonical terms
- Existing research papers are NOT modified; this is forward-looking infrastructure

## Relationship to SFV

This architecture is SFV operationalized at the organizational level:
- **Countermeasure for T1 (Semantic Drift):** Terms defined once, queried from graph
- **Countermeasure for T5 (State Discontinuity):** New projects inherit existing terminology automatically
- **Config-driven vocabulary** as described in the SFV engineering countermeasures

## Consequences

- All future projects get validity terminology for free on Seldon init
- Updating a definition propagates to all projects through the graph
- Requires an ingestion script to populate Neo4j from markdown source files
- Need to establish a `seldon/ontology/` directory structure

## Related

- SFV Terminology Baseline: `ai4stats/docs/sfv/SFV_TERMINOLOGY_BASELINE.md` (current canonical source, to be migrated here)
- AD-013: Documentation as Traceability
- SFV Threat Taxonomy (T1-T5)
