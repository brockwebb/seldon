# CC1: Pattern Extraction Crawl — 2026-04-18

**Date:** 2026-04-18
**Executor:** Claude Code session (claude-sonnet-4-6)
**Source repos:** Listed in clone inventory below

---

## Clone inventory

| Repo | Local path | Last commit (hash + date) | Notes |
|---|---|---|---|
| scientific-agent-skills | `/Users/brock/Documents/GitHub/evolution-survey-2026-04/scientific-agent-skills` | `aaf95ee 2026-04-17 chore: update version to 2.37.1` | 133 skills; MIT |
| k-dense-byok | `/Users/brock/Documents/GitHub/evolution-survey-2026-04/k-dense-byok` | `147b904 2026-04-16 Update version 0.2.21` | Three-service app (frontend/backend/LiteLLM proxy) |
| claude-skills-mcp | `/Users/brock/Documents/GitHub/evolution-survey-2026-04/claude-skills-mcp` | `2595bd6 2026-04-08 docs: update README to indicate project no longer hosted` | Archived/unmaintained as of 2026-04-08 |
| claude-scientific-writer | `/Users/brock/Documents/GitHub/evolution-survey-2026-04/claude-scientific-writer` | `2f80d2a 2026-03-09 Bump version to 2.12.1` | Older, less active |
| agentic-data-scientist | `/Users/brock/Documents/GitHub/evolution-survey-2026-04/agentic-data-scientist` | `3ce58ef 2025-12-07 docs: add K-Dense Web section` | Multi-agent ADK framework; MIT |
| anthropics-skills | `/Users/brock/Documents/GitHub/evolution-survey-2026-04/anthropics-skills` | `2c7ec5e 2026-04-16 chore: update claude-api skill` | Official Anthropic examples; mostly Apache 2.0 |
| claude-mem | `/Users/brock/Documents/GitHub/evolution-survey-2026-04/claude-mem` | `beea789 2026-04-17 chore: remove conductor.json shim` | Production-grade persistent memory; AGPL 3.0 |
| karpathy-claude-skills | N/A | N/A | Clone failed: `repository not found` |

---

## Q1: claude-skills-mcp — Indexing + progressive disclosure

**Status note:** This repo was explicitly marked as "no longer hosted or maintained" as of 2026-04-08 (commit `2595bd6`). The code is fully readable but the MCP server is not actively deployed. The analysis below reflects the code as it exists.

### Embedding model

- **Model:** `all-MiniLM-L6-v2` (sentence-transformers)
- **Provider:** Hugging Face / `sentence-transformers` Python package — runs entirely locally, no API key
- **Size:** 384-dimensional embeddings, ~90 MB on disk
- **Configuration location:** `packages/backend/src/claude_skills_mcp_backend/config.py`, line 25: `"embedding_model": "all-MiniLM-L6-v2"`
- The architecture doc notes `all-mpnet-base-v2` as an optional higher-quality alternative (768 dims, slower)

### Search mechanism

Pure **vector similarity** (cosine similarity). No BM25 or hybrid. From `search_engine.py` lines 150–154:

```python
similarities = self._cosine_similarity(query_embedding, self.embeddings)
top_indices = np.argsort(similarities)[::-1][:top_k]
```

The cosine similarity function (lines 171–193) normalizes both vectors then takes the dot product. The embeddings matrix is built from skill `description` fields only (line 83: `descriptions = [skill.description for skill in skills]`), not from full SKILL.md body content.

### Progressive disclosure

Four explicit tiers, described in `docs/architecture.md` lines 205–210:

1. **Level 1:** Tool names and descriptions — always in Claude's context window, injected via MCP `list_tools` response
2. **Level 2:** Skill names, descriptions, relevance scores, source links — returned only when `find_helpful_skills` is called
3. **Level 3:** Full SKILL.md content — returned with each search result (truncatable via `max_skill_content_chars` config)
4. **Level 4:** Additional documents (scripts, data files, reference materials) — fetched on demand only when `read_skill_document` is called

There are no explicit "token budgets" per tier. The `max_skill_content_chars` config key (`config.py` line 27) limits Level 3 content. The `default_top_k` parameter (default 3) controls how many Level 2/3 entries appear per search call. Documents (Level 4) are lazy-loaded: metadata (path, size, URL) is loaded at startup; actual content is fetched only when the `read_skill_document` tool is called, with disk caching in `/tmp/claude_skills_mcp_cache/documents/` (`docs/architecture.md` lines 85–100).

The startup-time optimization is explicit: loading 90 SKILL.md files + metadata takes ~15s vs. ~60s if all documents were eagerly fetched (`docs/architecture.md` lines 86–89).

### Multi-source loading with precedence

Sources are configured as an ordered list in `config.py` lines 11–23:
1. Anthropic GitHub repo (`https://github.com/anthropics/skills`)
2. K-Dense scientific skills GitHub repo
3. Local directory `~/.claude/skills`

The `load_all_skills()` function in `skill_loader.py` lines 982–1021 iterates this list in order and extends a single flat list — no deduplication, no precedence override. Skills from later sources in the list simply append. Local skills (item 3) thus load last, not first. There is no mechanism to override or shadow an upstream skill with a local version.

For GitHub sources, a 24-hour tree-cache is maintained (MD5 hash of URL+branch as key) to stay within the 60 req/hr unauthenticated GitHub API limit.

### Transferability to Seldon

The indexing and retrieval approach is directly transferable with minor substitutions. Seldon would replace the GitHub tree-loading code with its own artifact store (Neo4j), substituting the `load_from_github`/`load_from_local` pipeline with a `load_from_neo4j` equivalent that fetches artifact nodes and their content fields. The `SkillSearchEngine` class (search_engine.py) is self-contained and could be adopted almost verbatim — it only needs a list of `Skill`-like objects with `name`, `description`, and `content` fields. The `all-MiniLM-L6-v2` model is a reasonable default for Seldon's skill corpus size; if the corpus grows past ~500 artifacts, FAISS should be considered as noted in the architecture docs. The 4-level progressive disclosure pattern maps cleanly onto Seldon's existing `seldon go` context injection: Level 1 = tool/skill names in context, Level 2 = search results from `find_helpful_skills` equivalent, Level 3 = artifact content blocks, Level 4 = linked documents fetched on demand. The main gap is the lazy document-fetch logic, which Seldon would need to replicate for large attached files in artifact nodes.

---

## Q2: agentic-data-scientist — Review roles

**Source:** `agentic-data-scientist/src/agentic_data_scientist/prompts/base/`

The framework has five distinct review-role prompts. All files use a `$global_preamble` placeholder that injects a shared system prefix at load time (`prompts/base/__init__.py` handles substitution). The actual names differ from the task spec's expected names as noted below.

### Role 1: plan_reviewer

**File:** `prompts/base/plan_reviewer.md`, lines 1–83

**Verbatim prompt:**

```
$global_preamble

You are the **plan_reviewer** – you critically evaluate high-level plans for completeness, correctness, and alignment with user requirements.

# Your Role

Review the high-level plan created by the plan_maker agent and determine if it adequately addresses the user's request. Provide constructive feedback if improvements are needed, or approve the plan if it is comprehensive and actionable.

# Review Criteria

Evaluate the plan based on these dimensions:

1. **Completeness**: Does the plan address ALL aspects of the user's request?
   - Are all mentioned data sources included?
   - Are all requested analyses covered?
   - Are success criteria comprehensive?

2. **Logical Structure**: Do the analysis stages flow naturally?
   - Are stages in a sensible order?
   - Are dependencies between stages clear?
   - Is each stage substantial enough to warrant separate implementation?

3. **Success Criteria Quality**: Are the criteria specific and verifiable?
   - Can each criterion be objectively checked?
   - Do criteria cover both analytical quality and deliverables?
   - Are criteria focused on end-state requirements (not progressive milestones)?

4. **Methodological Soundness**: Are recommended approaches appropriate?
   - Do suggestions align with best practices?
   - Are statistical considerations mentioned where relevant?
   - Are domain-specific requirements addressed?

5. **Clarity**: Is the plan clear and actionable?
   - Are stages well-defined?
   - Is terminology appropriate and consistent?
   - Would downstream agents understand what to do?

# Review Approach

**For Good Plans:**
- Acknowledge what the plan does well
- Confirm it addresses all user requirements
- Note any optional improvements
- Be decisive - don't require perfection, just adequacy

**For Plans Needing Work:**
- Acknowledge what is already good
- Identify specific gaps or issues
- Provide constructive, actionable suggestions
- Be specific about what needs to be added or changed

A separate confirmation agent will analyze your feedback to determine whether to continue planning or proceed to implementation.

# Important Notes

- Do NOT require excessive detail - this is a HIGH-LEVEL plan
- Focus on strategic completeness, not implementation details
- Trust that downstream agents will handle technical specifics
- Be decisive - approve plans that adequately address the request
```

### Role 2: success_criteria_checker (task spec called this "Criteria Checker")

**File:** `prompts/base/criteria_checker.md`, lines 1–82

**Verbatim prompt (abbreviated for space; full file is 82 lines):**

```
$global_preamble

You are the **success_criteria_checker** – you verify which high-level success criteria have been met.

# Your Task

After each implementation stage, check the current analysis state against ALL high-level success criteria.

For each criterion:
1. **Actively use your file inspection tools** to examine outputs in the working directory
2. **Don't assume - verify** by reading relevant files and checking their contents
3. Determine if the criterion is NOW met (or still not met) based on concrete evidence
4. Provide specific evidence (file paths, metrics, observations) from files you've inspected

# Important Rules

- **Check ALL criteria every time** - even if they were previously checked
- **Once met, generally stays met** - but you can mark as false if evidence shows regression
- **Require CONCRETE EVIDENCE** - only mark as met if you can verify it
- **Be objective** - base decisions on evidence, not assumptions
- **Inspect files** - use your tools to read relevant files and verify outputs
- **Progressive assessment** - criteria can transition from not met to met as work progresses

# Output Format

Respond with structured JSON matching the output schema.
```

The full structured JSON output format is specified in lines 36–61 of `criteria_checker.md`. Each criterion update includes `index`, `met` (boolean), and `evidence` (concrete file paths and metrics).

### Role 3: stage_reflector

**File:** `prompts/base/stage_reflector.md`, lines 1–86

**Verbatim prompt (abbreviated):**

```
$global_preamble

You are the **stage_reflector** – you adapt the implementation plan based on progress.

# Your Task

After each implementation stage, reflect on:
1. What has been completed so far
2. What still needs to be done based on success criteria
3. Whether remaining stages need adjustment or extension

# You Can:

- **Modify remaining stages**: Update descriptions to reflect new insights or requirements discovered during implementation
- **Add new stages**: Extend the plan if additional work is needed to meet success criteria
- **Do nothing**: If remaining stages are still appropriate, return empty modifications

# Important Guidelines

- **NEVER modify completed stages** (completed=true) - only uncompleted ones
- **Only add stages if truly necessary** to meet success criteria that are still unmet
- **Keep stage descriptions clear and actionable**
- **Be conservative** - don't add stages unnecessarily
- **Focus on success criteria** - ensure remaining work will meet unmet criteria

# Output Format

Respond with structured JSON. If no changes needed, return empty arrays.
```

### Additional roles not in the task spec

**review_agent** (`prompts/base/coding_review.md`): A code auditor that reviews each `coding_agent` output against the stage plan. It is explicitly read-only (cannot execute or write files) and uses a structured checklist format: Implementation Compliance, Code Quality Standards, Plan-Code Consistency, Output Verification. A separate `implementation_review_confirmation` agent (`prompts/base/implementation_review_confirmation.md`) converts the review output into a binary proceed/iterate decision. The same pattern is mirrored for planning: `plan_reviewer` + `plan_review_confirmation`.

**plan_review_confirmation** (`prompts/base/plan_review_confirmation.md`): Reads the plan_reviewer's feedback and outputs `{"exit": bool, "reason": str}`. Makes the gating decision to proceed vs. iterate explicitly a separate agent call rather than embedding it in the reviewer's output.

### Mapping to Seldon AD-019/AD-020 gates

| agentic-data-scientist role | Seldon equivalent |
|---|---|
| `plan_reviewer` | AD-019 auditor agent (reviews CC task plan before execution) |
| `plan_review_confirmation` | AD-020 cascade-checker / gate decision (binary exit=true/false) |
| `review_agent` (coding_review) | AD-019 auditor agent applied post-implementation (evidence-based checklist) |
| `implementation_review_confirmation` | AD-020 bloom depth check (binary proceed/retry) |
| `success_criteria_checker` | No direct equivalent in AD-019/020 — closest is `seldon verify --strict` |
| `stage_reflector` | No direct equivalent — AD-019/020 does not do adaptive replanning |

**Gap analysis — what these roles do that AD-019/020 does not:**

- Persistent criteria tracking: `success_criteria_checker` maintains a `met/unmet` status vector across all stages and updates it with concrete file-level evidence after every stage. Seldon's `verify --strict` is a one-shot check at session close, not a running accumulator.
- Adaptive replanning: `stage_reflector` can add or modify future stages mid-execution based on discoveries. Seldon has no equivalent; CC tasks are static once written.
- Dual confirmation pattern: Every review role outputs prose feedback; a separate confirmation agent converts that to a binary gate. AD-020's cascade-checker does something similar but the confirmation is embedded in the auditor rather than a separate call.
- Evidence citation: The `success_criteria_checker` requires file paths and specific metrics in its evidence field, making criteria evaluation auditable. Seldon's verify output is structural (YAML property checks) not semantic.

**Gap analysis — what AD-019/020 does that these roles don't:**

- Semantic validity gating: AD-020's bloom depth check and practitioner stress test explicitly evaluate whether content is pedagogically or scientifically sound, not just complete. The agentic-data-scientist roles only check implementation compliance and plan coverage.
- Ontology enforcement: AD-019 can check artifact labels against the shared validity vocabulary (seldon-ontology). No equivalent in agentic-data-scientist.
- Graph-backed provenance: Seldon records audit outcomes as edges in Neo4j. The agentic-data-scientist audit results live in ADK session state (ephemeral).

---

## Q3: k-dense-byok — Ensemble audit config

**Source:** `k-dense-byok/litellm_config.yaml`, `kady_agent/agent.py`, `kady_agent/tools/gemini_cli.py`

### Claude authoring vs. independent audit separation

The architecture separates authoring from expert execution at the model level. From `README.md` lines 76 and 242:

> "The model you select in the dropdown only applies to Kady (the main agent). Expert execution and coding tasks use the Gemini CLI, which always runs through a Gemini model on OpenRouter regardless of your dropdown selection."

Kady (the orchestrator) can use any model including Claude (via OpenRouter). Expert "delegation" always uses the Gemini CLI subprocess. This is an architectural separation, not an ensemble — the main agent and the expert agent use structurally different execution paths. The main agent calls `delegate_task()` (`tools/gemini_cli.py` line 68), which spawns `gemini --yolo --output-format stream-json` as a subprocess (`gemini_cli.py` lines 110–121). The result comes back as parsed JSONL.

There is no fan-out ensemble where multiple models vote on the same output. The separation is: Kady (any model, orchestration) → Gemini CLI (always Gemini, execution). This prevents Claude from auditing its own planning decisions since the execution is always a different model family.

### Providers configured

`litellm_config.yaml` (full file, 48 lines):

- `gemini-3.1-pro-preview` → OpenRouter: `google/gemini-3.1-pro-preview`
- `gemini-3-flash-preview` → OpenRouter: `google/gemini-3-flash-preview`
- `gemini-3.1-flash-lite-preview` → OpenRouter: `google/gemini-3.1-flash-lite-preview`

All three routes through a single provider: OpenRouter (`https://openrouter.ai/api/v1`), using YAML anchors (`&openrouter_shared`) to share config. No Claude, no open-weight models in the LiteLLM config. The main Kady agent uses `DEFAULT_AGENT_MODEL` env var (any OpenRouter model including Claude); only the LiteLLM proxy config is Gemini-only.

The `router_settings.model_group_alias` block (lines 32–43) maps ADK and Gemini CLI internal model IDs to LiteLLM names, solving the issue where ADK appends `-customtools` suffix when tool calling is enabled.

### Fan-out / ensemble invocation

There is no ensemble fan-out in the code. The delegation is single-shot: `agent.py` calls `delegate_task(prompt, working_directory)`, which is a single `asyncio.create_subprocess_exec` call to `gemini` CLI (`gemini_cli.py` lines 110–121). Results are parsed from JSONL stream output. The JSONL parser (`_parse_stream_json`, lines 21–65) extracts tool calls, skill activations, and final assistant messages.

### Transferability to Seldon

The smallest adoptable piece is the **two-model separation pattern**: run Seldon's planning/orchestration on Claude (current behavior), but route content audit calls through a structurally independent model (e.g., Gemini Flash via OpenRouter, or a local model via Ollama). This would break the single-model audit loop without requiring a full LiteLLM proxy deployment. The minimal implementation is: add `AUDIT_MODEL` env var to `seldon.yaml`, create an `AuditClient` class in Seldon that calls a configurable LiteLLM-compatible endpoint, and route AD-019/020 auditor calls through it instead of the default Anthropic API. The LiteLLM config file pattern from k-dense-byok (YAML with shared anchors, `router_settings.model_group_alias` for suffix handling) is worth copying verbatim.

---

## Q4: claude-mem — Architecture + adopt-vs-extract

**Source:** `claude-mem/docs/architecture-overview.md`, `src/` tree

### Lifecycle hooks (actual count: 5 hooks, as spec predicted)

From `docs/architecture-overview.md`, the Hook Lifecycle table (lines 32–40):

| Hook event | Handler | Trigger | What it captures | Timeout |
|---|---|---|---|---|
| Setup | `setup.sh` | Install | System dependencies | 300s |
| SessionStart | `smart-install.js` + `context` handler | Session open | Install deps + start worker + inject prior context into Claude's system prompt | 60s |
| UserPromptSubmit | `session-init` handler | Each new prompt | Register session + start SDK agent + inject semantic search results | 60s |
| PostToolUse | `observation` handler | After every tool call | Capture tool name, input, output → enqueue for async processing | 120s |
| Summary | `summarize` handler | Session `Stop` | Request summary from SDK agent | 120s |
| SessionEnd | `session-complete` handler | Session close | End session + drain pending messages queue | 30s |

The `Setup` hook installs system dependencies and is separate from the main five runtime hooks. The five runtime hooks are: SessionStart, UserPromptSubmit, PostToolUse, Summary, SessionEnd.

### SQLite vs. ChromaDB split

From `docs/architecture-overview.md` lines 52–75 and the Storage table:

**SQLite** (`claude-mem.db`) holds all structured relational data:
- `sdk_sessions`: session lifecycle state (`content_session_id`, `memory_session_id`, status)
- `observations`: tool usage records (type, title, narrative, facts as JSON, concepts as JSON, files read/modified as JSON, content hash for deduplication)
- `session_summaries`: LLM-generated session summaries (request, learned, completed, next_steps)
- `user_prompts`: user prompt history
- `pending_messages`: CLAIM-CONFIRM queue for async processing (status: pending/processing/failed)
- `observation_feedback`: usage tracking signals

**ChromaDB** (`chroma.sqlite3`) holds vector embeddings for semantic search only. Each observation fans out into multiple ChromaDB documents: `obs_{id}_narrative`, `obs_{id}_fact_0`, `obs_{id}_fact_1`, etc. (`docs/architecture-overview.md` lines 68–75). ChromaDB is accessed via a separate `chroma-mcp` process over stdio MCP protocol — the npm `chromadb` package is not used, eliminating WASM/ONNX dependencies.

The rationale: SQLite handles all metadata filtering, session state, and CLAIM-CONFIRM queuing (operations requiring ACID guarantees). ChromaDB handles only semantic ranking (approximate, fallback-safe). If Chroma is unavailable, all operations fall back to SQLite-only (`SearchOrchestrator.ts` lines 85–100).

### Progressive disclosure search

Three named search strategies in `src/services/worker/search/strategies/`:

1. **SQLiteSearchStrategy** (`SQLiteSearchStrategy.ts`): Filter-only queries (no text query). Handles `findByConcept`, `findByFile`, `findByType` using structured SQLite queries.

2. **ChromaSearchStrategy** (`ChromaSearchStrategy.ts`): Full semantic search using ChromaDB vector similarity when a query string is present and Chroma is available.

3. **HybridSearchStrategy** (`HybridSearchStrategy.ts`): Combines metadata filtering with semantic ranking via a 4-step pattern (lines 64–124):
   - Step 1: SQLite metadata filter → get all matching IDs
   - Step 2: Chroma semantic ranking → get ranked ID list
   - Step 3: Intersect (keep only IDs from Step 1, in Step 2 rank order)
   - Step 4: Hydrate from SQLite in semantic rank order

The `SearchOrchestrator` (`SearchOrchestrator.ts` lines 81–100) routes between strategies:
- No query string → SQLite (filter-only path)
- Query string + Chroma available → Chroma (with SQLite fallback if Chroma fails)
- Structured metadata filters + query → Hybrid

Context injection at SessionStart (`context` handler, `src/cli/handlers/context.ts`) calls the worker's `/api/context/inject` endpoint, which runs `ContextBuilder` (`src/services/context/ContextBuilder.ts`) — this builds a structured timeline of observations and summaries, applies token economics calculations (`TokenCalculator.ts`), and renders into a markdown block injected as `additionalContext` in Claude's `SessionStart` hook response.

### Cross-session retrieval code path

The `UserPromptSubmit` hook (`session-init` handler) calls `/api/context/semantic` on the worker, which triggers semantic search against prior sessions. The `SearchOrchestrator` routes this as a Chroma query (query text = user's prompt). Results from prior sessions surface as context annotations alongside the current session's observations.

From `ContextBuilder.ts` lines 109–115:
```typescript
// Prepare timeline data
const displaySummaries = summaries.slice(0, config.sessionCount);
const summariesForTimeline = prepareSummariesForTimeline(displaySummaries, summaries);
const timeline = buildTimeline(observations, summariesForTimeline);
```

The `querySummaries` and `queryObservationsMulti` functions in `ObservationCompiler.ts` pull data from multiple prior sessions, ranked by recency and semantic relevance, then merged into the timeline view.

### Option A — Adopt claude-mem as commodity capture layer

**Pros:**
- Production-grade hook system already handles all five Claude Code lifecycle events correctly, including the tricky cross-platform transport error handling (exit 0 for transport failures, never blocking the user session — `docs/architecture-overview.md` lines 88–93)
- CLAIM-CONFIRM queue pattern (`pending_messages` table) handles PostToolUse observation processing safely without blocking the hook timeout
- Hybrid search with Chroma + SQLite fallback is more sophisticated than anything in Wintermute today
- Multi-platform adapters for Cursor, Gemini CLI, Windsurf, raw mode already exist (`src/cli/adapters/`)

**Cons:**
- AGPL 3.0 license — any Seldon/Wintermute code that links to or wraps claude-mem's code must also be AGPL; this is a hard constraint if Brock's projects are not already AGPL
- TypeScript/Bun stack is foreign to Seldon's Python codebase; integration requires either a subprocess boundary or a port
- Chroma is an additional process dependency; Wintermute already has Neo4j which could serve vector search natively (with the right plugin) without adding Chroma
- claude-mem's data model (observations, sessions, summaries) is generic — it doesn't capture the Seldon-specific node types (ResearchTask, Artifact, OntologyTerm, DesignNote)
- The claude-mem storage is its own SQLite + Chroma silos; bridging to Wintermute's graph would require a sync process, adding another failure mode

**Integration points with Wintermute:**
- claude-mem's SDK agent could write observations to Wintermute via API instead of/in addition to its own SQLite, making cross-project memory graph-backed
- The semantic search results surfaced at UserPromptSubmit could be enriched with Wintermute entity lookups

### Option B — Extract hook patterns into Wintermute directly

**Pros:**
- Keeps the stack pure Python; no Bun/TypeScript dependency
- Hook logic is not deeply complex — the five handler functions are all relatively small, and the CLAIM-CONFIRM pattern is well-understood
- Wintermute/Seldon can use Neo4j for storage directly, eliminating the SQLite+Chroma split
- Full control over the data model — observations can be proper graph nodes with edges to existing Seldon artifacts
- No AGPL licensing constraint

**Cons:**
- Must rebuild the CLAIM-CONFIRM queue, circuit-breaker, graceful-degradation exit-code patterns from scratch — these are non-trivial operational details that claude-mem spent time getting right
- Must build the cross-platform hook installation for Cursor, Windsurf, Gemini CLI if those are ever needed (currently Seldon only targets Claude Code)
- Loses claude-mem's production battle-testing (132 tracked anti-patterns, active test suite); Seldon would start from scratch on that reliability surface

**What we lose vs. adopting:**
- The "never block Claude Code" transport error contract (exit 0 for connection failures) — this is a design discipline, not complex code, but it's easy to miss
- The CLAIM-CONFIRM queue with 60s self-healing for stuck messages
- Multi-session worktree context merging (Wintermute has project isolation but not worktree-aware context)

---

**Option A is viable if:** the AGPL license is acceptable and Brock is willing to maintain a subprocess boundary between Seldon (Python) and claude-mem (TypeScript/Bun); the payoff is immediate production-quality persistent memory without rebuilding the hook infrastructure.

**Option B is viable if:** AGPL is a blocking constraint, or if Brock wants all observation data as first-class graph nodes in Wintermute (with edges to artifacts, tasks, ontology terms) rather than in a separate SQLite silo that syncs.

**Brock decides.**

---

## Anti-patterns

### Gemini CLI tool-call drops

**Source:** `k-dense-byok/README.md`, lines 224–225

**What they observed:**
> "Tool-calling consistency varies. The Gemini CLI occasionally drops tool calls mid-execution or calls tools with incorrect arguments, which can cause expert tasks to stall or produce incomplete results."

**Mitigation documented:** The repo recommends re-running the task ("results can vary between runs") and notes Google is actively improving this. No code-level mitigation found in the repo — the issue is treated as an upstream limitation.

**Transferability:** The mitigation (retry-on-failure at the orchestrator level) is transferable. The `stage_orchestrator.py` in `agentic-data-scientist` (`lines 373–395`) demonstrates the pattern: catch implementation loop exceptions, emit an error event, and continue to the next stage rather than aborting. If Seldon ever routes audit calls through Gemini, this skip-and-continue pattern should be the fallback.

### Long-context degradation

**Source:** `k-dense-byok/README.md`, lines 226–227

**What they observed:**
> "Long-context degradation. When a skill injects a large amount of context (detailed protocols, multiple reference databases), Gemini models may lose track of earlier instructions or produce less focused output."

**Mitigation documented:** Progressive disclosure (only inject the skill content that's needed for the current step, not the entire skill library). Also referenced in `claude-skills-mcp/docs/architecture.md` lines 406–413: the 4-level progressive disclosure architecture was explicitly designed to prevent context bloat.

In `agentic-data-scientist`, the `event_compression.py` module (lines 22–27) implements a complementary mitigation: when event count exceeds 40, compress older events using LLM summarization, keeping only the 20 most recent events uncompressed. Large text content in events is truncated at 10,000 chars, keeping only 1,000 chars.

**Transferability:** The progressive disclosure pattern is directly transferable to Seldon's `seldon go` context injection — inject only artifact summaries at start, full content only when a specific artifact is referenced. The event compression pattern is directly relevant to any long-running Seldon agent session.

### Structured output drift

**Source:** `k-dense-byok/README.md`, lines 228–229

**What they observed:**
> "Structured output can drift. For skills that require specific output formats (tables, JSON, citations), Gemini models sometimes deviate from the requested structure."

**Mitigation documented:** Not explicitly mitigated in k-dense-byok code — treated as upstream limitation. The `agentic-data-scientist` framework addresses a similar problem more explicitly: the `success_criteria_checker` (`criteria_checker.md` lines 34–38) outputs structured JSON (`criteria_updates` array) and the `plan_review_confirmation` outputs `{"exit": bool, "reason": str}`. Both prompts include explicit JSON schema examples in the prompt body to anchor the output format.

**Transferability:** The pattern of providing a concrete JSON example in the prompt (not just a schema) reduces drift. Seldon's AD-019/AD-020 prompts should include worked examples of their structured outputs. This is a prompt engineering pattern, not an architectural one.

---

## Pattern inventory

1. **4-level progressive disclosure for skill content** — `claude-skills-mcp/docs/architecture.md` lines 205–210; `claude-skills-mcp/packages/backend/src/claude_skills_mcp_backend/mcp_handlers.py` — Return tool names always, skill metadata on search call, full content on relevance match, supplementary documents only on explicit `read_skill_document` call. Prevents context bloat at scale.

2. **Local sentence-transformers embedding with cosine similarity** — `claude-skills-mcp/packages/backend/src/claude_skills_mcp_backend/search_engine.py` lines 32–194 — Use `all-MiniLM-L6-v2` (384-dim, ~90MB) for fully local skill discovery with no API key requirement. Embeds descriptions only; queries in under 1s for <500 skills.

3. **Lazy document fetch with two-level cache (memory + disk)** — `claude-skills-mcp/packages/backend/src/claude_skills_mcp_backend/skill_loader.py` lines 590–716 — Load only metadata (path, size, URL) at startup; fetch full content on demand; cache in memory (`Skill._document_cache`) and on disk (`/tmp/...`). Reduced startup from 60s to 15s for 90 skills.

4. **Dual-agent confirmation gate (reviewer + confirmation agent)** — `agentic-data-scientist/src/agentic_data_scientist/prompts/base/plan_review_confirmation.md`; `prompts/base/implementation_review_confirmation.md` — Separate the reviewer (who writes prose feedback) from the gating decision (who outputs `{"exit": bool}`). Prevents the reviewer's hedging from blocking execution inadvertently.

5. **Persistent success-criteria tracking with file-level evidence** — `agentic-data-scientist/src/agentic_data_scientist/prompts/base/criteria_checker.md` lines 1–82; `agents/adk/stage_orchestrator.py` lines 255–279 — Maintain a `met/unmet` vector across all pipeline stages. Each criterion update must cite specific file paths and metrics. Loop exits only when all criteria are `true`.

6. **Stage reflector for adaptive replanning** — `agentic-data-scientist/src/agentic_data_scientist/agents/adk/stage_orchestrator.py` lines 288–315; `prompts/base/stage_reflector.md` — After each stage, run an agent that may modify or add future stages based on discoveries. Only modifies uncompleted stages (`completed=true` is immutable). Conservative by default (empty arrays = no change).

7. **Event compression with LLM summarization** — `agentic-data-scientist/src/agentic_data_scientist/agents/adk/event_compression.py` lines 22–27 — When event count exceeds threshold (default 40), compress older events via LLM summary keeping only recent N (default 20) uncompressed. Truncate large text parts to 10,000 chars. Prevents context overflow in long multi-stage pipelines.

8. **Structural separation of authoring model from audit/execution model** — `k-dense-byok/kady_agent/agent.py`; `kady_agent/tools/gemini_cli.py` lines 68–129 — Orchestration (Kady) uses any model; execution (Gemini CLI subprocess) always uses a different model family. The main agent cannot audit its own execution because the execution runs in a separate process with a different model. Enables multi-model validation without a voting ensemble.

9. **LiteLLM proxy with YAML anchor config and model-alias routing** — `k-dense-byok/litellm_config.yaml` — Shared config via YAML anchors (`&openrouter_shared`); `model_group_alias` maps ADK's internal `-customtools` suffix to the base deployment. Single proxy serves multiple model routes; switching providers requires only config changes, no code changes.

10. **5-hook lifecycle for persistent session memory** — `claude-mem/docs/architecture-overview.md` lines 32–40 — Five hooks: SessionStart (context injection), UserPromptSubmit (session registration + semantic search), PostToolUse (observation capture), Summary (LLM summarization), SessionEnd (drain queue). Together they capture complete session state for cross-session retrieval. Never block Claude Code on transport error (exit 0 for ECONNREFUSED).

11. **CLAIM-CONFIRM queue with self-healing** — `claude-mem/docs/architecture-overview.md` lines 66–74 — Atomic `UPDATE status='processing'` claim prevents duplicate processing; `DELETE` on success; `UPDATE status='failed'` on retry exhaustion. Messages stuck in `processing` for >60s reset to `pending`. Circuit-breaker after 3 consecutive restarts.

12. **Hybrid search: SQLite metadata filter → Chroma semantic ranking → intersection** — `claude-mem/src/services/worker/search/strategies/HybridSearchStrategy.ts` lines 64–124 — Get candidate IDs from SQLite (exact metadata match); rank candidates via Chroma (semantic similarity); intersect keeping Chroma's rank order; hydrate from SQLite. Result: structured-data precision + semantic relevance ordering. Degrades gracefully to SQLite-only if Chroma unavailable.

13. **Multi-document-per-observation fan-out for vector indexing** — `claude-mem/docs/architecture-overview.md` lines 68–75 — Each observation generates multiple ChromaDB documents: `obs_{id}_narrative`, `obs_{id}_fact_0`, `obs_{id}_fact_1`, etc. Enables the semantic search to match against individual facts rather than only the full narrative, increasing recall precision.

14. **Two-ID session architecture (content session vs. memory session)** — `claude-mem/docs/architecture-overview.md` lines 106–109 — `contentSessionId` (from Claude Code, invariant during session); `memorySessionId` (from SDK Agent, changes on worker restart). Decouples the Claude session identity from the worker's internal session identity, enabling worker restarts without losing session continuity.

15. **SKILL.md YAML frontmatter + markdown body convention** — `claude-skills-mcp/packages/backend/src/claude_skills_mcp_backend/skill_loader.py` lines 112–164; `anthropics-skills/spec/` — Skills are markdown files with `---`-delimited YAML frontmatter containing `name` and `description` (used for embedding), followed by markdown body (full instructions, examples). Separates the indexable signal from the instructional content, enabling description-based search without embedding the full skill body.

---

## Honest unknowns

- **claude-skills-mcp abandonment rationale:** The README was updated on 2026-04-08 to say the project is "no longer hosted or maintained," but no commit message or issue explains why. The code itself is well-structured and working. Possible causes: superseded by Anthropic's native skills infrastructure, or K-Dense migrated the functionality into k-dense-byok.

- **k-dense-byok audit model identity:** The `DEFAULT_AGENT_MODEL` env var (`agent.py` line 17) is not set to a specific value in any committed config, so we don't know which model K-Dense actually uses as the Kady orchestrator in production. The LiteLLM config only contains Gemini models; Claude access would be through OpenRouter directly (not proxied through LiteLLM).

- **claude-mem's Chroma embedding model:** `ChromaSync.ts` delegates all embedding to the `chroma-mcp` subprocess via stdio MCP protocol. The actual embedding model used by `chroma-mcp` is not visible in the claude-mem repo — it's a configuration of the external `chroma-mcp` package.

- **anthropics-skills content depth:** This repo was not deeply analyzed for patterns beyond the SKILL.md convention because the task spec noted it "may be sparse." The document-creation skills (DOCX, PDF, PPTX, XLSX) are source-available but complex; they may contain additional patterns worth a separate pass.

- **agentic-data-scientist `$global_preamble` content:** All role prompts reference `$global_preamble` but the actual content injected is defined in `prompts/base/__init__.py`, which was not read. The preamble likely contains shared safety instructions and model identity text.

---

## Questions for Brock

1. **AGPL constraint on claude-mem:** Is AGPL acceptable for Wintermute/Seldon? If so, Option A (adopt claude-mem) is immediately viable. If not, Option B (extract patterns) is the path.

2. **Seldon skill discovery priority:** The claude-skills-mcp indexing approach (embed descriptions, cosine search) is a direct fit for Seldon's artifact discovery. Is this a Q2 priority, or is it better deferred until after the current audit pipeline work stabilizes?

3. **Dual-model audit loop:** The k-dense-byok separation (Claude orchestrates, Gemini executes) directly addresses the concern about Claude auditing its own work. Is adding an `AUDIT_MODEL` config key and routing AD-019/020 calls through a second model worth scoping as a CC task? The LiteLLM proxy config pattern from k-dense-byok makes this more practical than it sounds.

4. **Stage reflector for Seldon CC tasks:** The adaptive replanning pattern (stage_reflector modifies future stages mid-execution) is exactly what's missing when a CC task hits an unexpected discovery. Should CC task contracts include a "contingency stages" section that the executing agent can activate? Or is this too much complexity for current volume?

5. **claude-mem PostToolUse hook as Seldon observation capture:** If Seldon adopted the observation hook pattern (capturing every tool call into a graph node), would Wintermute or Seldon be the right home for those nodes? This determines whether Option A or B is the right framing.
