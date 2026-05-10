# AD-024 — Observability as Substrate

**Status:** Proposed, 2026-04-18. Promoted from CC4 deliverable (evolution burst 2026-04) as formalization of already-shipped infrastructure.
**Related:** AD-019/020 (gates that observability measures), AD-022 (CLI-default — observability CLI follows this principle), AD-023 (sleep functions whose value claim is measurable only via observability).

---

## Context

Before CC4, Seldon and Wintermute operated on qualitative signal: "the audit caught things," "the gate runs," "the graph has nodes." When CC3 asked the question "do we know each component works?" for 17 components, the answer for 4 was **"No idea"** and for 5 more was **"No, but should be measurable."**

Running a system with a third of its components unmeasured is a precondition for drift. Gates that no one verifies become ceremony. Functions that no one validates become decoration. The failure mode is not dramatic — it's slow, and the signal is absence: the system keeps running, papers keep shipping, and one day someone realizes a gate has been reporting zero violations for six months because of a bug, not because the system is clean.

The CC4 deliverable shipped a concrete observability substrate: a launchd-scheduled collector that parses Neo4j graphs, Seldon event logs, and Claude Code session JSONL files into an insert-only SQLite store; a Flask dashboard renders panels Q-a through Q-e against that store. At first baseline: 605 rows across 8 projects. Token attribution from Claude Code session files — not approximation. Dashboard is operational.

## Decision

**Observability is a substrate, not a feature. Every gate, every sleep function, every pipeline step that claims value must emit events to the substrate. The substrate is the primary evidence for retention, deprecation, and calibration decisions about Seldon, Wintermute, and related infrastructure.**

Concretely:
1. The CC4 dashboard + SQLite metrics store is the reference implementation of this substrate. Adjacent or future observability work extends this store; it does not build parallel stores.
2. Schema is insert-only, dot-notation metric names, JSON dimensions, versioned by `collected_by`. (See CC4 deliverable for full schema.)
3. New Seldon/Wintermute components are not considered complete unless they emit appropriate events to the substrate. This is a definition-of-done criterion, not a nice-to-have.
4. Decisions about component retention — whether a gate is catching violations, whether a function is producing signal, whether a pipeline is used — are made against substrate data when available, rather than qualitative recall.

## Consequences

**Positive:**
- Retirement decisions gain evidence. A component's deprecation case becomes "the substrate shows zero activity for N weeks and no known consumer" rather than "it feels dead."
- Calibration becomes data-driven. AD-019 audit gates, AD-023 sleep function thresholds, AD-020 stress-test metrics all have a uniform surface for tracking health.
- Drift detection works. A gate whose violation count trends to zero over time is either (a) catching fewer real violations (expected), (b) miscalibrated (actionable), or (c) silently broken (critical). The substrate exposes the trend; interpretation is human.
- Future tools inherit a measurement convention. "Emit metrics to `~/.seldon-observability/metrics.db` with dot-notation names" is cheap guidance that keeps the ecosystem coherent.

**Negative / cost:**
- Instrumentation work is ongoing overhead. Every new component carries a small observability tax.
- The substrate itself can be silently broken — a collector bug that skips a project, a schema change that drops a metric. The substrate needs its own integrity checks (nightly row counts, per-project freshness alerts). CC4 has identified but not fully resolved this — it's in the 75% roadmap bucket.
- Over-measurement is a failure mode. Metrics that no one looks at are worse than no metrics: they consume collector time and create false precision. Quarterly review: which panels does the operator actually look at? Which metrics inform decisions? Prune the rest.
- The substrate is local-only (SQLite, single-host). Multi-host or distributed observability is a v2 question, not addressed here.

**Reversibility:** High. The substrate is a file on disk; collectors are Python scripts; the dashboard is a Flask app. Nothing about this AD locks in a vendor, a cloud, or a protocol. Migration to a different backend (DuckDB, ClickHouse, etc.) is straightforward if ever needed.

## Known Limitations (from CC4 deliverable)

These are deferred work items, not reasons to delay the AD:
1. Tier 3 outcome quality not measured — future research problem.
2. Curation-rate panel is a stub until Sleep Function A emits events (unblocked by AD-023 implementation).
3. Single-snapshot baseline — 8-week trends need 7 more weeks of nightly runs.
4. `REMEDIATED_BY` edge type not yet in Seldon graph (75% roadmap item 75.4).
5. `updated_at` property absent on most nodes (75% roadmap item 75.3).
6. Non-Seldon Claude Code sessions attributed to `other` bucket — acceptable for now.
7. 7-day rolling token window, not accumulated weekly buckets.
8. Dashboard not daemonized — manual start required (75% roadmap item 75.9).

Each known limitation has either a roadmap item or an explicit "deferred, not needed yet" status. None block AD-024 promotion.

## Relation to Prior ADs

- **AD-019 (Agentic content audit) + AD-020 (Multi-lens review):** These ADs define gates. AD-024 is how we know the gates are working. Without AD-024 measurement, AD-019/020 gates are ceremonial.
- **AD-022 (CLI-default):** Dashboard has a web UI, but the collector is a CLI script (`scripts/observability_collect.py`). Emission side is CLI-friendly. AD-022 and AD-024 are compatible.
- **AD-023 (Sleep functions):** AD-023 claims sleep functions justify Wintermute's existence. The only way to know is to measure. AD-023 is the hardest test of AD-024 — if the substrate cannot surface sleep-function signal, AD-024 has a gap. Roadmap item 15.2 includes emitting the sleep-function metrics table from CC5 §Dashboard Integration.

## Open Questions

- Multi-host observability if a future architecture distributes Seldon/Wintermute across machines. Not scoped here.
- Access control / privacy for observability data. Currently local-only; if the dashboard is ever exposed, authentication becomes a concern.
- Retention policy for the SQLite store. Insert-only grows forever; periodic archival strategy is a future concern, not urgent at current volume.

---

*Short AD by design. The substrate already exists; this AD is the formalization. The discipline is in "new components emit events" — the rest is maintenance.*
