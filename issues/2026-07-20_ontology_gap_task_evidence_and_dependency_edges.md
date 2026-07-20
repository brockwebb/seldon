# Seldon Issue: relationship ontology lacks task-evidence and task-dependency edges

**Date:** 2026-07-20
**Severity:** Substantive (forces evidence artifacts to be registered without a link to the task they evidence; no first-class task dependencies)
**Found during:** icsp_notebook MCP v-next gated deploy + repo quiescence sweep (registering gate Results and G7 external evidence against a ResearchTask)
**Component:** relationship ontology / `seldon link` allowed from_types/to_types

---

## Problem

There is no sanctioned way to attach evidence to a `ResearchTask`, nor to express a dependency
between two tasks. Concretely, three edges are missing:

1. **Result → ResearchTask (evidence).** A gate `Result` can be `generated_by` a `Script`, but there
   is no edge to say the Result is evidence *for* / *satisfies* a `ResearchTask`. Gate outcomes end
   up registered as free-floating Results linked only to the producing script.
2. **GeneratedFile / DataFile → ResearchTask (evidence).** Registering an evidence file (e.g. a
   gate-evidence index, or the G7 external-dogfood transcript) against the task it evidences is
   impossible: `GeneratedFile` cannot originate `context_for` / `finding_in` / `informs` /
   `has_finding` (valid from_types exclude it, and none target `ResearchTask`). The artifact is
   registered but orphaned from its task.
3. **ResearchTask → ResearchTask (`depends_on` / `blocks`).** Task-to-task dependency exists as
   `--blocks` / `--depends-on` at task creation but is not expressible as a first-class relationship
   between two already-registered tasks via `seldon link`.

## Impact

Traceability breaks at the task boundary: "what evidence closed this task" and "what task depends on
what" cannot be walked in the graph, so provenance chains stop at the Result/artifact and task
dependencies live only in prose. Observed twice in one arc (mcp-v2 gate Results; G7 evidence file).

## Note only

Filed as a backlog note per the icsp_notebook quiescence sweep (S7c). No ontology changes made here —
this records the gap for a future ontology-remapping pass (cf. that project's DECISIONS D7 precedent
for how ontology remapping is handled deliberately).
