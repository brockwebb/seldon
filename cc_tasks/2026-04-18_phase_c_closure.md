# CC Task: Register Phase C Synthesis Outputs and Close Evolution Burst

**Date:** 2026-04-18
**Project:** seldon (`/Users/brock/Documents/GitHub/seldon`)
**Priority:** Burst closure — do this before any new architectural work begins
**Parent handoff:** `handoffs/2026-04-18_phase_c_evolution_burst_closeout.md`
**Plan anchor being closed:** `38b0698b`

---

## Context

Phase C synthesis of evolution burst 2026-04 is complete. Four synthesis docs, three AD docs, and one handoff are on disk and need to be registered as graph artifacts. Once registered, plan anchor `38b0698b` closes and the burst is done.

This task is mechanical. No design judgment required. Run the commands, verify, close.

**Standing rule reminder:** CC tasks are immutable once written. If a step fails in a way that requires spec changes, stop and report — do not improvise modifications.

---

## Pre-flight

```bash
cd /Users/brock/Documents/GitHub/seldon
seldon verify
```

If `seldon verify` fails before any of this task runs, stop. Report the failure. Do not register new artifacts into an already-broken graph.

Also confirm the six files exist:

```bash
ls -1 \
  docs/design/evolution_burst_2026-04/phase_c_retirement_list.md \
  docs/design/evolution_burst_2026-04/phase_c_roadmap_75_15_10.md \
  docs/design/AD-022_cli_default_mcp_exception.md \
  docs/design/AD-023_wintermute_sleep_functions.md \
  docs/design/AD-024_observability_as_substrate.md \
  handoffs/2026-04-18_phase_c_evolution_burst_closeout.md
```

All six must exist. If any are missing, stop and report.

---

## Deliverable 1 — Register the three ADs

Each AD is an `ArchitecturalDecision` artifact. Use `seldon artifact create` with the actual file paths relative to repo root.

### AD-022

```bash
seldon artifact create \
  --type ArchitecturalDecision \
  --name "AD-022" \
  --path "docs/design/AD-022_cli_default_mcp_exception.md" \
  --property "title=CLI-Default, MCP-Exception" \
  --property "description=Default to CLI invocation via bash for tool use; MCP is justified only by a concrete need for structured mid-reasoning I/O." \
  --property "state=proposed"
```

Create `informs` edge to `AD-003` (the original CLI-vs-MCP decision that this generalizes). If AD-003 is not registered under that name, locate it by filepath (`docs/design/` or search `seldon artifact list --type ArchitecturalDecision`) and use the actual graph ID.

### AD-023

```bash
seldon artifact create \
  --type ArchitecturalDecision \
  --name "AD-023" \
  --path "docs/design/AD-023_wintermute_sleep_functions.md" \
  --property "title=Wintermute Sleep Functions as Architectural Center" \
  --property "description=Wintermute's distinctive value is graph-plus-sleep-functions. Sleep functions (collapse, disambiguate, infer) are the product; the graph is the substrate." \
  --property "state=proposed"
```

No supersedes. Load-bearing AD for Wintermute — flagged in handoff as having reversibility clause at 90 days.

### AD-024

```bash
seldon artifact create \
  --type ArchitecturalDecision \
  --name "AD-024" \
  --path "docs/design/AD-024_observability_as_substrate.md" \
  --property "title=Observability as Substrate" \
  --property "description=Formalizes CC4 dashboard as substrate for measuring curation quality, not only growth — pruning, disambiguation, and consolidation are how the system demonstrates it is working." \
  --property "state=proposed"
```

Create `informs` edge from AD-024 to AD-023 (the sleep-function AD whose effectiveness AD-024 provides the substrate to measure).

---

## Deliverable 2 — Register the two synthesis docs

Both are `DesignNote` artifacts with `note_type=synthesis`. These are outputs of the evolution burst, not decisions themselves — the decisions are the ADs above.

### Retirement list

```bash
seldon artifact create \
  --type DesignNote \
  --name "phase_c_retirement_list" \
  --path "docs/design/evolution_burst_2026-04/phase_c_retirement_list.md" \
  --property "title=Phase C Retirement List (Evolution Burst 2026-04)" \
  --property "description=Four Tier-1 retirement targets, one conditional (rescinded by AD-023 promotion), two keep-with-status. Infrastructure only — no projects or data." \
  --property "note_type=synthesis" \
  --property "state=active"
```

### 75/15/10 roadmap

```bash
seldon artifact create \
  --type DesignNote \
  --name "phase_c_roadmap_75_15_10" \
  --path "docs/design/evolution_burst_2026-04/phase_c_roadmap_75_15_10.md" \
  --property "title=Phase C Roadmap 75/15/10 (Evolution Burst 2026-04)" \
  --property "description=13-item 75% bucket, 5-item 15% bucket, 2 innovation bets with written kill criteria. Defines three-item commit point for burst closure." \
  --property "note_type=synthesis" \
  --property "state=active"
```

Create `informs` edges from the roadmap to: AD-022, AD-023, AD-024 (the three ADs the roadmap operationalizes).

---

## Deliverable 3 — Register the handoff

```bash
seldon artifact create \
  --type Handoff \
  --name "phase_c_evolution_burst_closeout_2026-04-18" \
  --path "handoffs/2026-04-18_phase_c_evolution_burst_closeout.md" \
  --property "title=Phase C Evolution Burst Closeout" \
  --property "description=Final Phase C synthesis handoff. Four outputs on disk, three-item commit point defined, burst awaiting closure of plan anchor 38b0698b." \
  --property "state=final"
```

If the `Handoff` artifact type does not exist in the research domain config, register as `DesignNote` with `note_type=handoff` instead and report the fallback in your completion note.

---

## Deliverable 4 — Close plan anchor `38b0698b`

Via MCP (Desktop would also do this, but CC can too):

```
seldon_task_close (MCP) — task_id: 38b0698b
  note: "Phase C synthesis complete. Four outputs delivered. See handoffs/2026-04-18_phase_c_evolution_burst_closeout.md."
```

If `seldon_task_close` is not available from the CC session, use the CLI equivalent:

```bash
seldon task update 38b0698b --state completed \
  --note "Phase C synthesis complete. Four outputs delivered. See handoffs/2026-04-18_phase_c_evolution_burst_closeout.md."
```

Prefer MCP if available — it's the canonical closure path for graph state.

---

## Deliverable 5 — Verify and close this CC task

```bash
seldon verify
seldon cc complete cc_tasks/2026-04-18_phase_c_closure.md
```

Then confirm plan anchor is closed:

```
seldon_query (MCP):
  MATCH (p:ResearchTask {id: '38b0698b'}) RETURN p.state
```

Expected output: `completed`.

---

## Success Criteria

- Six new artifacts registered (3 ADs, 2 synthesis notes, 1 handoff or fallback DesignNote).
- Node count increases by 6.
- Edges exist: AD-022 → informs → AD-003; AD-024 → informs → AD-023; roadmap → informs → AD-022/AD-023/AD-024.
- Plan anchor `38b0698b` state = `completed`.
- `seldon verify` passes clean at end of task.
- `seldon cc complete` run on this file.

---

## What NOT To Do

- Do not modify any of the six files being registered. They are final.
- Do not register AD-001 through AD-021, even if they show up as unregistered during `seldon verify`. Dead-weight AD audit is explicitly deferred per handoff Section "What This Burst Did NOT Commit To."
- Do not create additional edges beyond those specified. Edge design is Desktop's responsibility; CC executes specified edges only.
- Do not promote any artifact state beyond what's specified (`proposed` for ADs, `active` for synthesis notes, `final` for handoff). State promotion is a Desktop decision.
- Do not start any retirement-list item (LightRAG removal, Hermes Agent removal, etc.) as part of this task. That is a separate CC task in the three-item commit point.

---

## Reporting

At task completion, report:
1. Six artifacts registered with their graph IDs.
2. Edges created (source → type → target).
3. Plan anchor final state.
4. Final `seldon verify` output (one line is fine: "pass" or the failure).
5. Any fallbacks used (e.g., Handoff type missing, artifact name collision).

If any step fails in a way that requires re-running or spec interpretation, stop and report — do not improvise.
