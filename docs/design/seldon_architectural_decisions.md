# Seldon — Architectural Decisions & Vision

**Date:** 2026-02-21
**Status:** Draft — Captures brainstorming decisions and future vision
**Context:** Synthesized from multiple design conversations about ANTS evolution, research workflow failures, and the ALMA paper analysis.

---

## 1. Core Architectural Decisions

### AD-001: ANTS Folds Into Seldon (Clean Build, Not Refactor)

**Decision:** ANTS (AI-Native Traceability System) v0.4 is proto-Seldon. Rather than patching ANTS v0.5 with renames and bolt-on features, Seldon v0.1 is a clean build that incorporates ANTS's proven patterns while shedding accumulated tech debt.

**Rationale:**
- ANTS v0.4 proved the core pattern: graph of typed artifacts, event-sourced JSONL, authority model, CLI interface, per-project database
- Tech debt includes: naming inconsistency from CLI rename ("trace" → "ants"), missing content search, no uninit capability, no individual artifact removal
- Patching creates more debt. Clean build with known-good patterns costs the same effort and produces a better foundation.

**What carries forward from ANTS:**
- NetworkX + JSONL architecture (zero infrastructure dependency)
- Authority model (AI proposes, human approves via batch)
- Event-sourced append-only log as source of truth
- Graph projection rebuilt from events
- Per-project scoped database

**What gets dropped:**
- MCP server interface (replaced by CLI commands, per AD-003)
- All naming inconsistencies
- Accumulated workarounds and band-aids

### AD-002: Domain-Agnostic Core Engine + Domain Configuration Layer

**Decision:** Seldon is a single system with swappable domain configurations. The engine is domain-agnostic. Artifact types, relationship types, and specialist roles are defined per-domain configuration.

**Rationale:**
- The traceability pattern is identical across research and engineering workflows — only the vocabulary differs
- Building separate systems (research-Seldon, engineering-Seldon) violates fractal architecture principle
- Domain config is schema, not code — adding a new domain shouldn't require new infrastructure

**Domain configuration defines:**

| Component | Research Config | Engineering Config |
|-----------|----------------|-------------------|
| Artifact types | Result, Figure, PaperSection, Citation, ResearchTask, LabNotebookEntry | Requirement, Module, Test, Decision, CodeFile |
| Relationship types | cites, generated_by, blocks, validates, computed_from | implements, traces_to, tested_by, depends_on |
| Specialist roles | Research Design, Methods & Analysis, Reproducibility, Documentation, etc. | Architecture, Implementation, QA, DevOps, etc. |
| Core engine | **Same** | **Same** |

**Implementation:** Research domain config is the first implementation. Engineering config comes when needed — not designed speculatively.

### AD-003: CLI Commands, Not MCP Servers

**Decision:** Seldon exposes functionality through Python CLI commands that Claude Code invokes via Bash. No MCP server.

**Rationale:**
- MCP servers create unnecessary complexity for single-project use cases
- Workspace-based isolation using labels on shared databases caused contamination in Wintermute — separate processes per project avoid this entirely
- CLI commands are testable, scriptable, and don't consume token overhead
- Claude Code's Bash tool is the natural interface — no adapter layer needed
- Project-scoped `.mcp.json` for external tools only (Neo4j, Postgres if needed)

### AD-004: Per-Project Database, No Shared Infrastructure

**Decision:** Each project gets its own Seldon instance with its own graph database (NetworkX + JSONL). No shared database across projects.

**Rationale:**
- Wintermute's LightRAG proved that workspace-based isolation on shared databases is insufficient — different projects contaminate each other's data
- A project's traceability graph is self-contained by definition
- Cross-project connections are a separate concern (see Parking Lot PL-003)
- Portability: the entire project state is a directory of files in the repo

### AD-005: Standard Interface Contract (update/retrieve)

**Decision:** All Seldon components interact through a standard `general_update()` / `general_retrieve()` interface contract, inspired by ALMA's memory design abstraction.

**Rationale:**
- ALMA (Xiong et al., 2026) demonstrated that standardizing the update/retrieve interface enables composable, domain-specialized memory modules
- Each specialist role can have a specialized retrieval profile without changing the engine
- The contract decouples storage implementation from access patterns
- Future optimization: retrieval strategies can evolve independently of the core graph

**Interface sketch:**
```python
class SeldonModule(ABC):
    async def retrieve(self, context: ProjectContext) -> Dict:
        """What does this role/component need to know right now?"""
        pass

    async def update(self, record: SessionRecord) -> None:
        """What did this session produce that's worth tracking?"""
        pass
```

**Key insight from ALMA:** Different domains need different retrieval strategies. Game environments with object interaction need fine-grained spatial knowledge; reasoning-heavy tasks need abstract strategy libraries. Similarly, the Research Design role needs literature and methodology patterns, while the Reproducibility role needs pipeline configs and data lineage. Same engine, different retrieval profiles per role.

### AD-006: Result Registry as First-Class Artifact Type

**Decision:** Every quantitative result cited in research output is a first-class artifact in the Seldon graph with full provenance.

**Rationale (from direct experience):**
- Numbers generated in-conversation drift between handoffs (91.2% vs 91.6%)
- No traceable path from cited number → script → data → SRS requirement
- Flat-file registries (numbers_registry.md) are manual, unenforced, and drift-prone
- 20x remediation cost when provenance is lost vs. captured at creation time

**Result artifact schema:**
```
Result {
    id, value, units, description,
    state: proposed | verified | published,
    generated_by: -> Script,
    computed_from: -> DataFile[],
    implements: -> SRS_Requirement,
    run_timestamp, input_data_hash,
    cited_in: -> PaperSection[] | Figure[]
}
```

**Provenance chain enforced by graph:**
```
PaperSection -> cites -> Figure -> contains -> Result -> generated_by -> Script -> implements -> SRS_Requirement
                                   Result -> computed_from -> DataFile -> produced_by -> PipelineRun
```

**Enforcement:** If a number doesn't exist in the registry with status >= `verified`, the system should flag citation attempts. No more "91.2% (source: some chat thread from February)."

### AD-007: Task Completion Tracking as First-Class Artifact Type

**Decision:** Research action items (backfill records, re-run scripts, verify counts) are first-class artifacts with state machines, not prose in handoff documents.

**Rationale (from direct experience):**
- Session creates 3 sub-tasks (#1, #2, #3). #1 gets done. Conversation pivots. #2 and #3 fall through the cracks.
- Weeks later, forensic archaeology through chat threads to figure out what didn't happen.
- Handoff prose doesn't enforce completion tracking — it's narrative, not state.
- The backfill disaster: 3 Anthropic parse failures were noted but never re-run because the task was never formalized as a trackable item.

**Task artifact schema:**
```
ResearchTask {
    id, description, created_in_session,
    state: proposed | accepted | in_progress | completed | verified,
    depends_on: -> [Result | DataFile | Script],
    blocks: -> [Result | PaperSection | Figure],
    evidence_of_completion: -> [file_hash | run_log | registry_entry]
}
```

**Session briefing integration:** `general_retrieve()` at session start surfaces open tasks that block downstream work. "You have an accepted task that was never completed: backfill 3 Anthropic records in rag_vs_pragmatics."

### AD-008: Wintermute Deferred — Emerges From Observed Need

**Decision:** The cross-project knowledge layer (Wintermute) is not designed now. It emerges after multiple project-level Seldon instances reveal actual cross-project patterns.

**Rationale:**
- Can't build the trunk before observing the branches
- The `central_library` repo was created from frustration with siloed knowledge — that frustration IS the requirements document, but it emerged from use
- Wintermute is architecturally just Seldon at meta-scale: same engine, different scope, artifact types are cross-project references
- Two or three running Seldon instances will make the cross-project requirements obvious rather than speculative

---

## 2. Implementation Priorities

### Phase 1: Seldon Core Engine
- Domain-agnostic graph engine (NetworkX + JSONL)
- Artifact CRUD with typed nodes and relationships
- State machines on artifacts (proposed → accepted → verified → published)
- Event-sourced append-only log
- Authority model (AI writes as proposed, human batch-approves)
- CLI interface (Python, pip-installable)
- `general_update()` / `general_retrieve()` interface contract

### Phase 2: Research Domain Configuration
- Artifact type schema: Result, Figure, PaperSection, Citation, ResearchTask, LabNotebookEntry, Script, DataFile, SRS_Requirement
- Relationship type schema: cites, generated_by, blocks, validates, computed_from, implements, produced_by
- Session briefing: retrieve open tasks, stale results, incomplete provenance chains
- Session closeout: capture action items as ResearchTask artifacts

### Phase 3: Pragmatics Paper as First Test
- Deploy on federal-survey-concept-mapper (already has 481 ANTS artifacts registered)
- Migrate relevant ANTS data to Seldon format
- Build result registry from existing verified numbers
- Formalize open tasks from conversation archaeology
- Validate that session briefings actually prevent the failure modes documented above

---

## 3. Parking Lot — Future Ideas

*Captured during brainstorming. Not committed. Preserved because best ideas emerge during associative flow, not structured planning.*

### PL-001: Wintermute as Service Mesh for Project Graphs
- Not a centralized knowledge store — a service bus that knows where things live
- SOA but stateful: each project is a bounded context with its own state
- Wintermute holds cross-project edges: "project A's concept X = project B's concept Y"
- The relationship itself is a first-class artifact with provenance
- Actual artifacts stay in project-level Seldon instances — Wintermute only holds symlinks and dedup index
- **Trigger:** Build after 2-3 project-level Seldon instances reveal actual cross-project needs

### PL-002: Distributed Knowledge with Dedup to Mother Core
- Knowledge stays distributed in project graphs by default
- Only genuinely duplicated entities get promoted to the shared core
- Promotion is a dedup function, not a migration — originals stay in place, canonical reference created
- Cross-project connections built by Wintermute as needed, not pre-designed
- **Analogy:** SOA architecture but not stateless — each service owns its data, the bus knows the topology

### PL-003: Fractal Agent Team with Specialist Retrieval Profiles
- Seven specialist roles: Lead/Chief Scientist, Documentation, Research Design, Methods & Analysis, Reproducibility & Validation, Project Coordination, Acquisition
- Each role gets a specialized `general_retrieve()` profile — different context for different work
- Research Design retrieves: literature, methodology patterns, related experiments
- Methods & Analysis retrieves: statistical techniques, validation approaches, prior results
- Reproducibility retrieves: pipeline configs, data lineage, environment specs
- Codenames for agents TBD — deliberately leaving space for the right names to emerge
- **Insight from ALMA:** Domain-specialized retrieval outperforms one-size-fits-all (ALMA found game environments need spatial knowledge while reasoning tasks need abstract strategy libraries)

### PL-004: Automated Run Provenance Capture
- When Claude Code executes an analysis script, structured output auto-registers results in Seldon
- Eliminates human transcription step (the exact failure mode: Claude computes number in-conversation, human copies to flat file, number drifts)
- Script emits structured JSON → Seldon `general_update()` ingests it → Result artifact created with full provenance
- **Pattern:** The script itself is the update event source, not a human writing prose after the fact

### PL-005: Drift Detection on Downstream Citations
- When a script re-runs and produces different numbers, every downstream citation flagged as stale
- Graph traversal: Result changed → find all PaperSection/Figure nodes that cite it → mark as needs_review
- Same pattern as ANTS relationship invalidation — upstream change propagates to dependents
- Prevents the "was it 91.2% or 91.6%?" problem structurally

### PL-006: Meta-Learning Memory Designs (ALMA-Inspired, Long-Term)
- ALMA's meta-learning loop (sample → reflect → implement → evaluate → archive) could optimize retrieval strategies
- Not for discovering memory architectures (we know what research workflows need) but for tuning retrieval — which context combinations actually help task completion?
- The archive + sampling probability concept (performance-weighted, visit-penalized) could optimize Wintermute's entity management
- **Caveat:** This is research-project-scale ambition. Don't build this until the basic system is running and producing data about what retrieval patterns work.

### PL-007: ALMA's Evaluation Framework for Research Validation
- Collection phase → Deployment phase maps to: collect knowledge during research → evaluate whether it helped produce better output
- Did the literature review actually inform the analysis? Did the lab notebook entries contribute to the paper?
- Quality signal Seldon could track: provenance completeness score, citation coverage, task completion rate per session
- **Use case:** "This paper section cites 4 results, but 2 have no traceable script. Provenance score: 50%."

### PL-008: Agent Codenames
- Specialist roles deserve codenames. For fun, for identity, for quick reference.
- Current universe: Wintermute (Neuromancer), Seldon (Foundation), ANTS (acronym)
- Candidates discussed: Ripley (Aliens — engineer under pressure), Naomi Nagata (Expanse — chief engineer), Motoko Kusanagi (Ghost in the Shell — cyberpunk continuity), Athena (wisdom + strategy, disguised as Mentor), Janeway (decisive captain), Stark (Iron Man — engineering archetype), Galt (Atlas Shrugged), Egon (Ghostbusters — the scientist)
- No rush. The right names emerge from use, not from a naming committee.

### PL-009: Sub-Module Composition Pattern for Wintermute
- ALMA's `Sub_memo_layer` abstraction: multiple specialized memory modules chain together (spatial priors → strategy library → risk tips → reflex rules)
- Maps to Wintermute's problem: how to organize and retrieve knowledge across heterogeneous sources
- Different sub-modules for different knowledge types, each with own storage and retrieval logic, orchestrated by a general pipeline
- **When:** After Wintermute architecture is actually being designed, not before

### PL-010: Shared Memory Core with Symlink Architecture
- Projects may have intra-project connections that are known and purpose-built
- Cross-project connections are curated, not automatic — Wintermute builds them for specific project pairs
- Dedup to mother core only for genuinely duplicated entities
- Central_library repo is the manual prototype of this pattern
- The "Unicron" model: doesn't consume projects, connects them. Consumption (dedup) only on confirmed duplication.

---

## 4. References

- Xiong, Y., Hu, S., & Clune, J. (2026). Learning to continually learn via meta-learning agentic memory designs. *Preprint.* arXiv:2602.07755v1
- ANTS v0.4: https://github.com/brockwebb/ai-native-traceability-system
- Seldon scaffold: https://github.com/brockwebb/seldon
- Wintermute: https://github.com/brockwebb/wintermute

---

## 5. Relationship to Prior Documents

| Document | Status | Notes |
|----------|--------|-------|
| ANTS SRS (ai-native-traceability-system/docs/) | Historical | Core patterns carry forward; specific requirements superseded by this document |
| ANTS design_decisions_2025-01-31.md | Historical | NetworkX + JSONL decision validated and retained |
| Seldon vision.md | Active | Vision statement still valid; scope expanded by AD-006, AD-007 |
| Seldon conops.md | Needs Update | Session workflow needs to incorporate result registry and task tracking |
| 2026-02-14 research_system_spec.md | Historical | "Tyranny of the Stochastic" framing and DOORS analysis still valid as motivation |

---

*This document will evolve as implementation proceeds. Parking lot items are not commitments — they're preserved ideas awaiting the right moment.*
