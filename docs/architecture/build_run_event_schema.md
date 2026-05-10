# BuildRun Event Schema

**Status:** Active
**Defined by:** AD-025 (DeerFlow as Build-Time Harness)
**Schema version:** 1.0
**Schema file:** `seldon/schemas/build_run.json`
**Emitter:** `seldon/scripts/emit_build_run.py`

---

## What is a BuildRun event?

A `BuildRun` is the single structured provenance record emitted by a build-time harness (DeerFlow, or any future bounded-build orchestrator) at run completion. It captures **what was attempted** in a build: the goal, the models invoked, the subagents dispatched, the files produced, the validation outcome, and the cost.

It is the artifact-level provenance boundary between an opaque orchestrator's internal trace and Seldon's queryable graph projection. The orchestrator's deep trace (e.g., DeerFlow's `state.db`) lives outside Seldon. The BuildRun event lives inside.

A `BuildRun` is emitted regardless of run outcome — successful runs and failed runs both emit. A killed-on-cost-overrun run emits a BuildRun with `validation_results: fail` and `terminal_reason: cost_overrun`. **Provenance for failures is as valuable as provenance for successes.** This is the construct-validity standard AD-025 §Provenance contract demands.

---

## Where it lands

A BuildRun is emitted as **two Seldon envelope events** appended to the target project's event log at `<project_root>/seldon_events.jsonl`:

1. An `artifact_created` envelope creating the BuildRun artifact with all its properties (state: `proposed`).
2. An `artifact_state_changed` envelope transitioning the BuildRun to its terminal state (`completed` if `terminal_reason == "success"` and `validation_results.seldon_verify != "fail"`, otherwise `failed`).

Both envelope events share a `session_id` so the projection can group them.

After the next `seldon rebuild`, the BuildRun materializes as a `BuildRun` artifact node in that project's Neo4j graph (e.g., `seldon-arnold` for an Arnold pilot run) in the appropriate terminal state.

**Why two events instead of one?** Seldon's event log is uniformly envelope-style (`artifact_created`, `artifact_updated`, `artifact_state_changed`, `link_created`, `link_removed`). BuildRuns are artifacts in the domain config — they go through the same lifecycle as everything else. Emitting create + state-change preserves audit symmetry: every artifact has at least one creation event, and every state transition is its own event.

**Schema scope.** The JSON schema at `seldon/schemas/build_run.json` describes the BuildRun **artifact properties** — i.e. what goes inside `payload.properties` of the `artifact_created` envelope. The envelope itself is built by the seldon library (`seldon.core.events.make_event`) and is not redescribed here.

## Neo4j storage note (complex-field flattening)

Neo4j allows only primitive types or arrays-of-primitives on node properties. Four BuildRun fields are nested objects/arrays-of-objects: `models_used`, `subagents`, `files_produced`, `validation_results`. The emit script (`seldon/scripts/emit_build_run.py`) JSON-stringifies these four fields when writing to `payload.properties`. The full structure is preserved as a string and round-trips via `json.loads()`. The JSONL line on disk reflects the same flattening, so JSONL-grep queries on those four fields work against the JSON-string representation. Top-level scalar fields (`run_id`, `terminal_reason`, `total_cost_usd`, etc.) are stored natively and Cypher-queryable directly.

---

## Schema (v1.0)

```yaml
event_type: build_run
schema_version: "1.0"

# === Identity ===
run_id:
  type: string                  # uuid4
  required: true
goal:
  type: string                  # full prompt or path-derived spec text
  required: true
goal_hash:
  type: string                  # sha256(goal text), hex, lowercase
  required: true
plan_hash:
  type: string                  # sha256 of orchestrator's planning-phase output
  required: true
ad_reference:
  type: string                  # AD authorizing the run, e.g. "AD-025"
  required: false

# === Models invoked ===
models_used:
  type: array
  required: true
  items:
    provider: string            # openrouter, anthropic, openai, etc.
    model: string               # moonshotai/kimi-k2, claude-opus-4-7, etc.
    role: string                # planner, implementer, validator, summarizer, ...
    input_tokens: integer
    output_tokens: integer
    cache_creation_input_tokens: integer  # 0 if not applicable
    cache_read_input_tokens: integer      # 0 if not applicable
    invocations: integer        # how many times this model was called in this role
    cost_usd: number

# === Subagent fan-out (orchestrator-spawned) ===
subagents:
  type: array
  required: false               # populated when the orchestrator runs subagents
  items:
    name: string                # e.g. "sparky", "doc", "pt", "arnold"
    role: string                # data, constraint, proposal, synthesis, ...
    invocations: integer
    cumulative_cost_usd: number # null if not separately tracked

# === Files produced ===
files_produced:
  type: array
  required: true
  items:
    path: string                # absolute path
    content_hash: string        # sha256 of file contents at emission time
    commit_sha: string          # git SHA if committed; null if uncommitted
    artifact_type: string       # Seldon artifact type: GeneratedFile, Script,
                                # AgentRole, ArchitecturalDecision, etc.
    bytes: integer

# === Validation ===
validation_results:
  type: object
  required: false
  properties:
    seldon_verify: { enum: [pass, fail, skipped] }
    tests:        { type: object }    # framework-specific (pytest/mocha/...)
    lint:         { type: object }
    custom_checks:{ type: object }    # project-specific assertions

# === Lifecycle ===
started_at:
  type: timestamp                # ISO-8601 UTC
  required: true
completed_at:
  type: timestamp                # ISO-8601 UTC
  required: true
duration_seconds:
  type: integer
  required: true
total_cost_usd:
  type: number                   # sum across models_used[*].cost_usd
  required: true

# === Outcome ===
terminal_reason:
  type: string                   # success, cost_overrun, wallclock_overrun,
                                 # invocation_overrun, error, manual_kill
  required: true
internal_trace_ref:
  type: string                   # path/hash to orchestrator's deep trace
                                 # e.g. ~/deer-flow/.deer-flow/data/<run>.db
  required: true
notes:
  type: string                   # operator-facing free text, optional
  required: false
```

---

## Required fields summary

`run_id`, `goal`, `goal_hash`, `plan_hash`, `models_used`, `files_produced`, `started_at`, `completed_at`, `duration_seconds`, `total_cost_usd`, `terminal_reason`, `internal_trace_ref`.

Optional: `ad_reference`, `subagents`, `validation_results`, `notes`.

---

## Graph projection

After Seldon projects the event into Neo4j, a BuildRun node has these edges:

```
BuildRun --produces--> GeneratedFile
                   --> Script
                   --> AgentRole
                   --> Workflow
                   --> ArchitecturalDecision
                   --> DesignNote
```

The `produces` edge to a typed artifact is created when `files_produced[i].artifact_type` matches a Seldon artifact type. If `artifact_type: GeneratedFile`, the BuildRun produces a generic GeneratedFile node (path + hash, nothing more). If `artifact_type: AgentRole`, the projection picks up the Seldon AgentRole properties from a parallel AgentRole artifact registered separately.

Failures still project: a BuildRun with `terminal_reason: cost_overrun` projects with the `produces` edges to whatever partial files were captured, plus `validation_results.seldon_verify: fail`. Querying for "what did this run actually produce?" works the same way for failed runs.

---

## Why this shape

**Single event per run.** A BuildRun is one row, not a sequence. The orchestrator's internal turn-by-turn trace stays in the orchestrator (DeerFlow's `state.db`). Seldon's graph captures the artifact-level boundary, not the cognition.

**Hashes for dedup and audit.** `goal_hash` and `plan_hash` let downstream tools recognize identical or similar runs without comparing prose. `content_hash` on each produced file lets the projection detect drift between what the run claimed to produce and what's actually on disk at projection time.

**Costs are first-class.** `total_cost_usd` and per-model breakdown are required. AD-025 §What Kills This AD §3 ("Token economics fail") is monitored from BuildRun queries directly, not from receipts pasted into closeouts.

**Subagent fan-out is optional.** Not every orchestrator runs subagents; `subagents` is populated when present, omitted when not. A solo-run build still emits a valid BuildRun.

**Terminal reason is required.** Whether a run succeeded, failed, was killed, or errored out is a first-class property — not encoded only in `validation_results`. This makes "show me killed runs from the last week" a one-line graph query.

---

## Compatibility

This schema is additive to AD-025. It does not amend AD-025. Future AD-revisions may extend this schema (bump `schema_version`) but must preserve required fields for backward compatibility.

The schema is project-agnostic: any Seldon project can receive BuildRun events from any compliant orchestrator. The pilot is `seldon-arnold` (DeerFlow scaffolding the Arnold coaching team). Future runs may target `seldon-wintermute` (foraging skill scaffolding), `seldon-leibniz-pi` (paper-build harness), etc.
