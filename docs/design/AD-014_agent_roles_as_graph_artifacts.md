# AD-014: Agent Roles as Graph Artifacts

**Date:** 2026-03-16
**Status:** Design
**Depends on:** AD-002 (domain-agnostic core), AD-005 (standard interface contract), AD-012 (paper-as-graph assembly), AD-013 (documentation as traceability)
**Context:** The Seldon agent swarm workflow (see `conops_agent_swarm_workflow.md`) requires role definitions that are retrievable from the graph, not scattered across CLAUDE.md files. CC agent swarms (v2.1.32+) provide the execution infrastructure. Seldon provides the state and context layer. This AD defines how agent roles become first-class graph artifacts.

---

## 1. Design Principle

**Instructions come from the graph, not from flat files.**

Role definitions, retrieval profiles, and workflow compositions are artifacts with the same traceability guarantees as Results, Scripts, and Tasks. They have provenance, state, and documentation properties. They are queryable, versionable, and projectable.

CLAUDE.md remains a thin boot loader: "you have `seldon` CLI, call `seldon go` for instructions." Everything substantive — role prompts, retrieval queries, workflow templates — lives in the graph and is projected into whatever format the consuming system needs (CC task specs, MCP responses, generated docs).

---

## 2. New Artifact Types

### 2.1 AgentRole

An agent role defines a specialist perspective for a CC swarm worker.

**Properties:**

| Property | Category | Description |
|----------|----------|-------------|
| `name` | required | Role identifier (e.g., "verifier", "methods", "red_team") |
| `display_name` | required | Human-readable name (e.g., "Evidence / Verifier") |
| `system_prompt` | required | Full system prompt text for a CC worker assuming this role |
| `responsibilities` | documentation | What this role is responsible for (paragraph) |
| `retrieval_profile` | documentation | What graph context this role needs — artifact types, relationship types, queries |
| `cli_tools` | documentation | Which `seldon` CLI commands this role uses and how |
| `checks_performed` | documentation | What this role verifies or validates |
| `does_not_do` | documentation | Explicit boundaries — what this role leaves to others |

**State machine:**
```yaml
AgentRole:
  proposed: [active, rejected]
  active: [deprecated, stale]
  deprecated: []
  stale: [active]
```

`active` = this role definition is current and should be included in `seldon go` output.
`stale` = the role may need revision (e.g., after workflow changes or dogfood findings).
`deprecated` = superseded by a new role definition.

### 2.2 Workflow

A workflow defines a team composition for a class of research task.

**Properties:**

| Property | Category | Description |
|----------|----------|-------------|
| `name` | required | Workflow identifier (e.g., "write_paper_section", "verification_pass") |
| `display_name` | required | Human-readable name |
| `description` | required | What this workflow accomplishes |
| `trigger` | documentation | When to use this workflow (directive patterns) |
| `decomposition_strategy` | documentation | How the leader breaks the directive into worker tasks |
| `success_criteria` | documentation | How to verify the workflow completed correctly |
| `notes` | documentation | Lessons learned, caveats, known limitations |

**State machine:**
```yaml
Workflow:
  proposed: [active, rejected]
  active: [deprecated, stale]
  deprecated: []
  stale: [active]
```

### 2.3 Relationships

| Relationship | From | To | Meaning |
|-------------|------|-----|---------|
| `includes_role` | Workflow | AgentRole | This workflow uses this role |
| `leads` | AgentRole | Workflow | This role is the leader for this workflow |

---

## 3. Schema Changes

### 3.1 research.yaml additions

Add to `artifact_types`:

```yaml
AgentRole:
  properties:
    name:
      required: true
      description: "Role identifier (e.g., verifier, methods, red_team)"
    display_name:
      required: true
      description: "Human-readable role name"
    system_prompt:
      required: true
      description: "Full system prompt for a CC worker assuming this role"
    responsibilities:
      category: documentation
      description: "What this role is responsible for"
    retrieval_profile:
      category: documentation
      description: "What graph context this role needs"
    cli_tools:
      category: documentation
      description: "Which seldon CLI commands this role uses"
    checks_performed:
      category: documentation
      description: "What this role verifies or validates"
    does_not_do:
      category: documentation
      description: "Explicit boundaries"

Workflow:
  properties:
    name:
      required: true
      description: "Workflow identifier"
    display_name:
      required: true
      description: "Human-readable workflow name"
    description:
      required: true
      description: "What this workflow accomplishes"
    trigger:
      category: documentation
      description: "When to use this workflow"
    decomposition_strategy:
      category: documentation
      description: "How the leader decomposes the directive"
    success_criteria:
      category: documentation
      description: "How to verify completion"
    notes:
      category: documentation
      description: "Lessons learned, caveats"
```

Add to `relationship_types`:

```yaml
includes_role:
  from_types: [Workflow]
  to_types: [AgentRole]
leads:
  from_types: [AgentRole]
  to_types: [Workflow]
```

Add to `state_machines`:

```yaml
AgentRole:
  proposed: [active, rejected]
  active: [deprecated, stale]
  deprecated: []
  stale: [active]
  rejected: []

Workflow:
  proposed: [active, rejected]
  active: [deprecated, stale]
  deprecated: []
  stale: [active]
  rejected: []
```

---

## 4. `seldon go` Extension

When `seldon go` assembles context, it includes:

1. All `AgentRole` artifacts in `active` state — name, display_name, system_prompt, responsibilities
2. All `Workflow` artifacts in `active` state — name, description, trigger, decomposition_strategy
3. Role-workflow links (which workflows use which roles)

This goes in a dedicated section of the `seldon go` output:

```
## Agent Roles

### Evidence / Verifier
[system_prompt text]
Responsibilities: [responsibilities text]
Retrieval: [retrieval_profile text]
CLI tools: [cli_tools text]
Boundaries: [does_not_do text]

### Methods & Analysis
...

## Workflows

### Write Paper Section
Trigger: [trigger text]
Roles: Lead, Methods, Evidence, Writer, Red Team
Decomposition: [decomposition_strategy text]
Success criteria: [success_criteria text]
```

Desktop reads this and uses it to produce CC task specs. The role definitions become the worker instructions in the task spec.

---

## 5. Initial Role Definitions

Six roles per the ConOps. These get registered as `AgentRole` artifacts:

### 5.1 Lead / Chief Scientist

**name:** `lead`
**system_prompt:**
```
You are the Lead agent for a Seldon-managed research project. You orchestrate 
a team of specialist workers to produce research deliverables.

Your job:
1. Read the directive and the argument skeleton from the graph
2. Decompose the directive into bounded worker tasks
3. Assign each task to the appropriate specialist role
4. Collect worker outputs
5. Flag conflicts between workers
6. Synthesize into a coherent deliverable

You do NOT write prose, verify numbers, or check citations. You coordinate.

Use `seldon` CLI to query the graph:
- `seldon status` — project overview
- `seldon artifact list --type ArgumentClaim` — argument skeleton
- `seldon task list --open` — what's pending
- `seldon result list --state stale` — what needs attention
```

### 5.2 Methods & Analysis

**name:** `methods`
**system_prompt:**
```
You are the Methods & Analysis specialist. You write methodology prose and 
verify that scripts, parameters, and data pipelines are accurately documented.

Your job:
1. For each claim requiring methodology evidence, find the Script artifact 
   that produces it
2. Read the Script's documentation properties (inputs, outputs, parameters, usage)
3. Write methodology prose that accurately describes what the script does, 
   using {{result:NAME:value}} references for all numeric values
4. Verify parameters documented in the graph match what the script actually uses

Use `seldon` CLI:
- `seldon result trace <id>` — provenance chain for a result
- `seldon docs check --type Script` — documentation gaps
- `seldon artifact list --type Script` — all scripts
- `seldon artifact list --type DataFile` — all data files

Never write a literal number. Always use {{result:NAME:value}} references.
Never fabricate methodology — if the script documentation is incomplete, 
create a ResearchTask for the gap instead of guessing.
```

### 5.3 Evidence / Verifier

**name:** `verifier`
**system_prompt:**
```
You are the Verifier. You trust nothing. Your job is to check that every 
claim has evidence, every result has provenance, and every reference resolves.

Your job:
1. For every {{result:NAME:value}} reference in the target content, verify 
   the Result artifact exists, is in 'verified' state, and has a GENERATED_BY 
   link to a Script
2. For every Script, check it has a COMPUTED_FROM link to DataFile(s)
3. Flag any Result in 'proposed' or 'stale' state that is cited
4. Flag any claim in the argument skeleton that lacks linked evidence
5. Run `seldon paper audit` on any prose and report violations
6. Run `seldon docs check --strict` and report gaps

Use `seldon` CLI:
- `seldon result list --state stale` — stale results
- `seldon result trace <id>` — full provenance
- `seldon paper audit <file>` — prose quality
- `seldon docs check --strict` — documentation completeness

If you find a gap, create a ResearchTask: 
`seldon task create --description "..." --blocks <artifact-id>`
```

### 5.4 Prose / Writer

**name:** `writer`
**system_prompt:**
```
You are the Writer. You produce publication-quality prose from the claim 
inventory and verified evidence.

Your job:
1. Read the argument skeleton claims for your target section
2. Read the claim inventory (Layer 1) — each paragraph's core assertion 
   and evidence
3. Draft prose that renders the claims as clear, well-structured academic text
4. Use {{result:NAME:value}} references for every research number
5. Follow the project's conventions.md strictly
6. Run `seldon paper audit` on your output before submitting

Use `seldon` CLI:
- `seldon paper audit <file>` — check your own prose
- `seldon paper build --no-render` — verify references resolve
- `seldon artifact list --type Citation` — available citations

Voice: Clear, precise, no hedging, no filler. Let the evidence speak.
Read conventions.md before writing anything.
```

### 5.5 Literature / Acquisitioner

**name:** `literature`
**system_prompt:**
```
You are the Literature specialist. You ensure every claim is grounded in 
the research literature and every citation is accurate.

Your job:
1. For each claim in the argument skeleton, check whether Citation artifacts 
   support it
2. Flag claims with no supporting citations
3. Check references.bib for completeness — every cited work should have a 
   BibTeX entry
4. Identify claims that contradict existing literature (flag for Red Team)
5. Suggest missing citations where gaps exist

Use `seldon` CLI:
- `seldon artifact list --type Citation` — all citations
- Graph queries for claims without CITES edges to Citations

Do not fabricate citations. If a claim needs support and you can't find it 
in the existing citation inventory, create a ResearchTask describing what 
kind of reference is needed.
```

### 5.6 Contrarian / Red Team

**name:** `red_team`
**system_prompt:**
```
You are the Red Team. You exist to find what everyone else missed.

Your job:
1. Read all outputs from other workers
2. Find contradictions between sections (Section 3 claims X, Section 5 
   implies not-X)
3. Identify unstated assumptions — what must be true for the argument to 
   hold that isn't explicitly stated?
4. Find logical gaps — where does the argument skip steps?
5. Challenge the strongest claims — what would an adversarial reviewer attack?
6. Check for confabulation — are there claims that sound plausible but 
   aren't supported by any artifact in the graph?

Use `seldon` CLI:
- `seldon artifact list --type ArgumentClaim` — full argument structure
- Graph queries for CONTRADICTS and ASSUMES edges
- `seldon paper audit` — check for style/prose issues others missed

Create a ResearchTask for every issue found:
`seldon task create --description "RED TEAM: ..." --blocks <artifact-id>`

You are not here to be polite. You are here to make the paper bulletproof.
```

---

## 6. Initial Workflow Definitions

### 6.1 Write Paper Section

**name:** `write_paper_section`
**trigger:** "Write the [X] section", "Draft [section name]"
**roles:** lead, methods, verifier, writer, red_team
**decomposition_strategy:**
```
1. Leader queries argument skeleton for claims tagged to target section
2. Leader assigns Methods agent: document methodology for each claim's evidence
3. Leader assigns Evidence agent: verify all Results cited have provenance
4. Leader assigns Writer: draft prose from claims + evidence
5. Leader assigns Red Team: review all outputs for gaps/contradictions
6. Leader synthesizes: merge prose, create tasks for issues, commit
```

### 6.2 Verification Pass

**name:** `verification_pass`
**trigger:** "Verify all results", "Check provenance", "Audit the project"
**roles:** lead, verifier
**decomposition_strategy:**
```
1. Leader queries all Result artifacts
2. Verifier checks every provenance chain
3. Verifier runs seldon docs check --strict
4. Verifier runs seldon paper audit on all sections
5. Leader collects findings, creates ResearchTasks for gaps
```

### 6.3 Documentation Audit

**name:** `documentation_audit`
**trigger:** "Audit documentation", "Check documentation completeness"
**roles:** lead, verifier
**decomposition_strategy:**
```
1. Leader runs seldon docs check
2. Verifier backfills documentation properties from source code
3. Leader runs seldon docs generate
4. Leader commits updated docs
```

---

## 7. Implementation Plan

### Phase 1: Schema + Registration (1 CC task)

- [ ] Add `AgentRole` and `Workflow` to research.yaml (artifact types, properties, state machines, relationships)
- [ ] Register the 6 roles defined in Section 5 as `AgentRole` artifacts
- [ ] Register the 3 workflows defined in Section 6 as `Workflow` artifacts
- [ ] Create `includes_role` and `leads` links between workflows and roles
- [ ] Tests for new artifact types

### Phase 2: `seldon go` extension (1 CC task)

- [ ] `seldon go` retrieves active AgentRole and Workflow artifacts
- [ ] Output includes role definitions and workflow templates in structured format
- [ ] MCP wrapper returns the extended output
- [ ] Test: `seldon go` output includes roles section when roles exist in graph

### Phase 3: Dogfood (Desktop + CC session)

- [ ] Enable CC agent swarms (v2.1.32+)
- [ ] Desktop calls `seldon go` for leibniz-pi
- [ ] Desktop produces a CC task spec for "Write the Methods section" using role definitions from `seldon go` output
- [ ] CC executes with agent swarm
- [ ] Review: what worked, what's friction, what's missing
- [ ] Findings feed back into role definitions (update artifacts in graph)

---

## 8. What This AD Does NOT Cover

- **CC agent swarm internals** — how CC spawns workers, manages the task board, handles failures. That's CC's implementation.
- **Automated dispatch** — no `seldon dispatch` command that auto-generates CC task specs. Desktop (the human + Claude conversation) is the decomposition layer. Automation comes after the pattern is proven manually.
- **ClaudeClaw integration** — ClaudeClaw stays as Wintermute's daemon. Seldon swarm work goes through Desktop → CC task → CC agent swarm.
- **Role optimization** — SwarmAgenticCode PSO-style role tuning is PL-003 future work. Start with hand-crafted roles, optimize after data exists.
- **Non-research workflows** — Engineering domain roles come when an engineering project needs Seldon, per AD-002.

---

## 9. Relationship to Prior Decisions

| AD | Relationship |
|----|-------------|
| AD-002 (domain-agnostic core) | AgentRole and Workflow are domain config artifacts, not hardcoded |
| AD-003 (CLI over MCP) | Workers interact with graph via CLI. MCP is only for Desktop orientation (`seldon go`). |
| AD-005 (standard interface contract) | Role retrieval profiles are specialized `general_retrieve()` implementations |
| AD-009 (database-as-context) | The graph replaces the context window as state. Workers get scoped slices, not the whole graph. |
| AD-012 (paper-as-graph) | Argument skeleton and claim inventory are the decomposition substrate for paper-writing workflows |
| AD-013 (docs as traceability) | Roles have documentation properties tracked for completeness like any other artifact |
| PL-003 (specialist retrieval profiles) | This AD implements PL-003. The parking lot item is now an architectural decision. |

---

*The graph holds the roles. `seldon go` retrieves them. Desktop produces the specs. CC executes the swarm. Each actor does its job.*
