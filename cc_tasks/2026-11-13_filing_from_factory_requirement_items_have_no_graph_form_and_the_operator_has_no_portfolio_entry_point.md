# Filing from factory: requirement items have no graph form, and the operator has no portfolio entry point

**Kind:** filing
**Filed by:** factory
**Status:** proposed
**Date:** 2026-11-13. Written by the factory Desktop session (FCT-2). Reports what the factory experienced; the answer is Seldon's.

## What the factory experienced

### 1. Requirement items cannot be nodes with trace edges

The operator said on 2026-11-13 that he does not see the systems engineering documents he expects in the factory, held
as items in the graph. Factory F-014 now fixes a document set (OpsCon, StRS, SyRS, interface control, verification
plan) whose every requirement is one item with a stable id, a statement, a source receipt and trace targets. Factory
task FAC-05 (944ebed9) writes them as Markdown in that form.

What is missing: nothing the factory can call turns such an item into a node, or its `Traces to` line into an edge, in
a graph that can be queried or crawled. The factory checked Seldon's open tasks and found none for it, and found no
design note under `docs/design/` dated November 2026. The research domain configuration has `SRS_Requirement` as an artifact
type for a paper's analysis; the factory found no type for a stakeholder or system requirement, an interface or a
verification, and no trace relationship between requirement levels.

The operator's standing statements on this, as the factory holds them: requirements are individual items in the graph
linked by edges to other documents, in manageable pieces; prior art and existing open-source tools come first; it
must not become brittle or DOORS-like.

### 2. Seldon's own requirements set is a vision and a conops

`docs/requirements/` in seldon holds `vision.md` and `conops.md`. The factory found no stakeholder or system
requirements specification for Seldon itself. The operator's words: Seldon was supposed to have the systems
engineering and research discipline built in, and needs to dogfood it. Reported as observed; the factory did not
search the decision register for requirement-like records.

### 3. The operator's entry point is per repository

The operator runs `seldon go` and reads a handoff in one repository at a time. On 2026-11-13 he said he now starts at
the factory and expects a factory-level go and handoff. Factory F-016 records that the factory is Seldon at portfolio
scope and that the factory will not build a second engine. Today a `go` or a handoff in the factory repository reads
the factory's graph only; the factory coordinator gathers every other repository's state by hand, one
`seldon_task_list` call per repository, as it did on 2026-11-01, 2026-11-02 and 2026-11-13.

## What the factory needs, stated as outcomes

- An item id in a factory document resolves to a node, and its traces to edges, without the text being rewritten.
- One brief in the factory repository lists every registered repository's open tasks, running task, last dispatcher
  pass and alarms, with counts equal to each repository's own task list; one handoff carries per-repository sections
  and one resume line.

## References

factory `decisions.md` F-011, F-014, F-016; factory `docs/2026-11-13_factory_level_up_documents_bank_entry_point_view.md`;
factory `docs/plan.md` stages 3a and 3d; factory `registry.md`.
