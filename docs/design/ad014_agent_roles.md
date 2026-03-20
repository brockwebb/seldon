# CC Task: AD-014 Phase 1 — Agent Roles as Graph Artifacts

**Date:** 2026-03-16
**Priority:** High — prerequisite for agent swarm workflows
**Depends on:** AD-013 complete, working CLI + Neo4j
**Repo:** ~/Documents/GitHub/seldon/
**Design spec:** docs/design/AD-014_agent_roles_as_graph_artifacts.md — READ THIS FIRST
**ConOps:** docs/design/conops_agent_swarm_workflow.md — READ THIS TOO

---

## Objective

Add AgentRole and Workflow artifact types to Seldon domain config, register the six specialist roles and three workflow templates from AD-014, and extend seldon go to include role definitions in its output.

---

## Files to Read Before Starting

- docs/design/AD-014_agent_roles_as_graph_artifacts.md — Full spec (Sections 2-6)
- docs/design/conops_agent_swarm_workflow.md — How the pieces fit together
- seldon/domain/research.yaml — Current domain config (you are adding to it)
- seldon/domain/loader.py — DomainConfig model (verify new types parse)
- The file implementing seldon go — you are extending this
- seldon/core/artifacts.py — create_artifact for registering roles

---

## What To Build

### 1. Schema Changes in research.yaml

Add AgentRole and Workflow to artifact_types with property schemas per AD-014 Section 2.

AgentRole properties: name (required), display_name (required), system_prompt (required), responsibilities (doc), retrieval_profile (doc), cli_tools (doc), checks_performed (doc), does_not_do (doc).

Workflow properties: name (required), display_name (required), description (required), trigger (doc), decomposition_strategy (doc), success_criteria (doc), notes (doc).

Add to relationship_types:
- includes_role: from_types [Workflow], to_types [AgentRole]
- leads: from_types [AgentRole], to_types [Workflow]

Add state machines for both:
- proposed: [active, rejected]
- active: [deprecated, stale]
- deprecated: []
- stale: [active]
- rejected: []

### 2. Register Six Roles

Copy the FULL system prompts and ALL properties from AD-014 Section 5. Do not summarize or truncate system prompts — they are the actual instructions workers receive.

Register each with seldon artifact create. Set --authority accepted. Transition state to active.

Roles:
1. lead (Lead / Chief Scientist) — AD-014 Section 5.1
2. methods (Methods & Analysis) — AD-014 Section 5.2
3. verifier (Evidence / Verifier) — AD-014 Section 5.3
4. writer (Prose / Writer) — AD-014 Section 5.4
5. literature (Literature / Acquisitioner) — AD-014 Section 5.5
6. red_team (Contrarian / Red Team) — AD-014 Section 5.6

### 3. Register Three Workflows

From AD-014 Section 6. Register each, transition to active.

1. write_paper_section — roles: lead, methods, verifier, writer, red_team
2. verification_pass — roles: lead, verifier
3. documentation_audit — roles: lead, verifier

### 4. Create Relationship Links

Use seldon link create for each:
- Each workflow -> includes_role -> each of its roles
- lead -> leads -> each workflow

### 5. Extend seldon go

Add a section to seldon go output that:
1. Queries all AgentRole artifacts in active state
2. Queries all Workflow artifacts in active state
3. Queries includes_role and leads relationships
4. Formats into the output with headers: Agent Roles, Workflows
5. Each role shows: display_name, system_prompt, responsibilities, retrieval_profile, cli_tools, does_not_do
6. Each workflow shows: display_name, trigger, roles (from links), decomposition_strategy, success_criteria
7. If no roles exist, skip section silently

MCP wrapper inherits this automatically.

### 6. Tests

Update tests/test_domain.py:
- New artifact types parse from research.yaml
- New relationship types validate
- New state machines work

New tests/test_agent_roles.py:
- Create AgentRole with required properties succeeds
- Create AgentRole missing system_prompt fails
- State transitions proposed->active->stale->active work
- Create Workflow succeeds
- includes_role and leads links validate correctly

Update tests/test_go.py:
- seldon go includes Agent Roles section when roles exist
- seldon go omits section when no roles exist

---

## What NOT To Do

- Do NOT build dispatch automation — Desktop produces CC task specs manually
- Do NOT change existing artifact types — only add new ones
- Do NOT modify the MCP server file — it wraps the same function
- Do NOT build CC agent swarm integration — CC native feature handles that

---

## Verification

```bash
cd ~/Documents/GitHub/seldon
pytest tests/ -v
seldon artifact list --type AgentRole     # 6 roles, all active
seldon artifact list --type Workflow      # 3 workflows, all active
seldon go                                 # includes Agent Roles and Workflows
```

Post-build: Update CLAUDE.md with AD-014 reference. Commit.
