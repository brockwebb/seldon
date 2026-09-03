# CC Task: `seldon init` must derive the Neo4j database name from the PROJECT name

**Created:** 2026-07-04
**Status:** proposed
**Priority:** low (papercut with real blast radius)
**Type:** Enhancement — init/template behavior.
**Origin incident:** ai-readiness-kg (federation control plane Phase 2, Stage 1,
`~/.wintermute/cc_tasks/2026-07-04_federation_control_plane_phase2_execution.md`).

## Why

A project initialized from the `blank` template shipped with
`neo4j.database: seldon-blank` and `project.name/slug: blank` — the template's
OWN identity leaked into the project instead of being derived from it. The
ai-readiness-kg project ran for days against a database literally named
`seldon-blank`, which read as a placeholder/mistake to every external system
(the Wintermute federation registry refused to pin it until renamed). The
rename cost a full projection rebuild + ontology re-sync + database drop.

## What

- `seldon init` derives `neo4j.database` as `seldon-<project-slug>` from the
  PROJECT name the user supplies; the template supplies CONTENTS only, never
  identity fields (`project.name`, `project.slug`, `neo4j.database`).
- Guard: refuse to init (or loudly warn) when the resolved database name
  equals `seldon-<template-name>` — that is always the leak.
- Consider a `seldon rename-project` helper that does what the incident
  required by hand: update yaml → `CREATE DATABASE` → `rebuild` →
  `ontology sync` → verify counts → prompt to drop the old DB.

## Note from the incident

The manual rename path works and verified cleanly (126 nodes / 36 rels
byte-identical across old/new, `seldon verify` all green) — but
`ontology_synced` events are skipped on replay, so a plain `rebuild` leaves
the ontology replica at epoch 0 until `seldon ontology sync` is re-run. Any
`rename-project` helper must include that step, or rebuild should replay the
replica materialization.

Also unfixed by the rename: `project.name`/`slug` in ai-readiness-kg's
`seldon.yaml` still say `blank` (left untouched — unknown whether internals
key on slug; the init fix should make identity consistent in one place).
