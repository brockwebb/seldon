# CC Task: Seldon Core Engine — Neo4j Pivot

**Date:** 2026-03-14
**Priority:** Critical path — this replaces the previous CC Task 2 (NetworkX scaffold)
**Output:** Seldon core engine with JSONL event store + Neo4j graph projection
**Repo:** `~/Documents/GitHub/seldon/`

---

## Architecture Decision Patch: AD-004-PATCH-001

**Original AD-004:** Per-project database, no shared infrastructure (NetworkX + JSONL)
**Patch:** Per-project Neo4j database + JSONL event store. NetworkX replaced as projection target.

**What stays:**
- JSONL append-only event log as source of truth (portable, git-friendly, the backup)
- Per-project isolation (each Seldon project gets its own Neo4j database)
- Event-sourced architecture (graph rebuilt from event replay)
- CLI interface (AD-003)
- Domain-agnostic core with config layer (AD-002)

**What changes:**
- Graph projection target: NetworkX (in-memory, ephemeral) → Neo4j (persistent, indexed, queryable)
- Query language: Python NetworkX API → Cypher
- Session startup: replay-from-scratch → graph already exists, check for new events since last sync
- Concurrent access: impossible with NetworkX → supported by Neo4j
- Agent retrieval: pre-computed Python traversal → Cypher queries (enables PL-013 RLM-style REPL retrieval)

**Why now:**
- Neo4j already running locally on M1 Pro (arnold, pragmatics, quarry databases exist)
- Infrastructure cost is zero — already paid
- NetworkX replay-from-scratch doesn't scale and provides no persistence between sessions
- Cypher is a dramatically better agent query interface than Python traversal code
- The "zero infrastructure dependency" argument assumed Neo4j wasn't already present. It is.

**What NetworkX was good for that we preserve differently:**
- Portability: JSONL event log IS the portable format. `seldon export` replays to fresh Neo4j instance.
- Git-friendliness: Events are JSONL text files in the repo. Neo4j data is NOT in git (it's a running service).
- Zero-dep development: For CI/testing, a NetworkX-based test harness can replay events without Neo4j. Production uses Neo4j.

---

## Dual-Layer Architecture

```
Source of Truth          Projection (queryable)       Backup
─────────────          ──────────────────────       ──────
JSONL event log   →    Neo4j graph database    →    git push / iCloud
(append-only)          (persistent, indexed)        (JSONL files only)
(in project repo)      (local service)              (Neo4j rebuilt from replay)
```

Every mutation:
1. Event appended to JSONL (source of truth)
2. Corresponding Cypher executed against Neo4j (projection)

Recovery from Neo4j failure:
1. `seldon rebuild` — replay all JSONL events into fresh Neo4j database
2. No data loss — JSONL is complete history

---

## What To Build

### 1. Package Structure

```
seldon/
├── seldon/
│   ├── __init__.py
│   ├── cli.py                  # Click CLI entry point
│   ├── core/
│   │   ├── __init__.py
│   │   ├── events.py           # JSONL event store — append, read, replay
│   │   ├── graph.py            # Neo4j graph operations (projection layer)
│   │   ├── artifacts.py        # Artifact CRUD (domain-agnostic)
│   │   ├── state.py            # State machine enforcement
│   │   └── sync.py             # Event→Neo4j sync (replay, incremental, rebuild)
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── loader.py           # Domain config YAML loader + validator
│   │   └── research.yaml       # Research domain config
│   └── commands/
│       ├── __init__.py
│       ├── init.py             # `seldon init` — creates project DB + event log
│       ├── status.py           # `seldon status` — graph stats, open tasks, stale results
│       └── rebuild.py          # `seldon rebuild` — replay events into fresh Neo4j DB
├── tests/
│   ├── __init__.py
│   ├── test_events.py          # JSONL event store tests (no Neo4j needed)
│   ├── test_graph.py           # Neo4j projection tests (requires Neo4j)
│   ├── test_artifacts.py       # Full CRUD integration tests
│   └── conftest.py             # Fixtures: temp Neo4j DB, sample events
├── pyproject.toml
└── README.md
```

### 2. Event Store (`core/events.py`) — UNCHANGED from original task

Append-only JSONL log. Every mutation is an event. This is the portable source of truth.

```json
{
  "event_id": "uuid4",
  "event_type": "artifact_created | artifact_updated | artifact_state_changed | link_created | link_removed",
  "timestamp": "ISO8601",
  "session_id": "uuid4",  
  "actor": "human | ai",
  "authority": "proposed | accepted",
  "payload": {
    "artifact_id": "...",
    "artifact_type": "Result | Script | DataFile | ...",
    "properties": {},
    "from_state": null,
    "to_state": "proposed"
  }
}
```

Functions:
- `append_event(project_path, event)` — write to `seldon_events.jsonl`
- `read_events(project_path)` — read all events, return list
- `read_events_since(project_path, last_event_id)` — incremental read for sync
- `event_count(project_path)` — fast count without loading all events

### 3. Neo4j Graph Projection (`core/graph.py`)

**Connection:** Each Seldon project connects to its own Neo4j database.
- Database name convention: `seldon_<project_slug>` (e.g., `seldon_pragmatics`, `seldon_sas_conversion`)
- Connection via `neo4j` Python driver (bolt protocol, localhost:7687)
- Credentials from project config (`seldon.yaml`) or environment variables

**Node schema (Cypher):**
```cypher
// All artifacts share a base pattern
CREATE (a:Artifact:Result {
    artifact_id: $id,
    artifact_type: 'Result',
    state: 'proposed',
    created_at: datetime(),
    created_by: 'ai',
    authority: 'proposed',
    // Type-specific properties stored as node properties
    value: 0.912,
    units: 'accuracy',
    description: 'Model accuracy on test set',
    run_timestamp: datetime(),
    input_data_hash: 'sha256:abc123'
})

// Double-label pattern: every node is :Artifact AND :<TypeLabel>
// Enables both generic queries (MATCH (a:Artifact)) and typed queries (MATCH (r:Result))
```

**Relationship schema (Cypher):**
```cypher
CREATE (result)-[:GENERATED_BY {created_at: datetime(), session_id: $sid}]->(script)
CREATE (result)-[:COMPUTED_FROM {created_at: datetime()}]->(datafile)
CREATE (section)-[:CITES {created_at: datetime()}]->(result)
CREATE (task)-[:BLOCKS {created_at: datetime()}]->(section)
```

**Indexes to create on init:**
```cypher
CREATE INDEX artifact_id IF NOT EXISTS FOR (a:Artifact) ON (a.artifact_id);
CREATE INDEX artifact_type IF NOT EXISTS FOR (a:Artifact) ON (a.artifact_type);
CREATE INDEX artifact_state IF NOT EXISTS FOR (a:Artifact) ON (a.state);
```

**Core functions:**
- `create_artifact(tx, artifact_type, properties)` — CREATE node with double-label
- `update_artifact(tx, artifact_id, properties)` — SET properties
- `change_state(tx, artifact_id, new_state)` — SET state (after state machine validation)
- `create_link(tx, from_id, to_id, rel_type, properties)` — CREATE relationship
- `remove_link(tx, from_id, to_id, rel_type)` — DELETE relationship
- `get_artifact(tx, artifact_id)` — MATCH by ID, return node
- `get_artifacts_by_type(tx, artifact_type)` — MATCH by type label
- `get_artifacts_by_state(tx, state)` — MATCH by state
- `get_neighbors(tx, artifact_id, rel_type=None, direction='both')` — traversal
- `get_provenance_chain(tx, artifact_id)` — recursive upstream traversal
- `get_dependents(tx, artifact_id)` — recursive downstream traversal (for staleness propagation)
- `get_stale_artifacts(tx)` — find all artifacts marked needs_review

### 4. Event→Neo4j Sync (`core/sync.py`)

The bridge between event store and graph projection.

- `full_replay(project_path, neo4j_driver)` — replay ALL events into empty Neo4j DB
- `incremental_sync(project_path, neo4j_driver)` — replay events since last sync point
- `get_sync_point(neo4j_driver)` — read last synced event_id from Neo4j metadata node
- `set_sync_point(neo4j_driver, event_id)` — write sync checkpoint

Sync point stored as a special metadata node in Neo4j:
```cypher
MERGE (m:SeldonMeta {key: 'sync_point'})
SET m.last_event_id = $event_id, m.synced_at = datetime()
```

### 5. State Machine (`core/state.py`) — UNCHANGED from original task

Validates transitions per artifact type per domain config.

```python
RESEARCH_STATE_MACHINES = {
    'Result': {
        'proposed': ['verified', 'rejected'],
        'verified': ['published', 'stale'],
        'published': ['stale'],
        'stale': ['verified'],  # re-verification after re-run
        'rejected': []
    },
    'ResearchTask': {
        'proposed': ['accepted', 'rejected'],
        'accepted': ['in_progress'],
        'in_progress': ['completed', 'blocked'],
        'completed': ['verified'],
        'blocked': ['in_progress'],
        'verified': [],
        'rejected': []
    }
    # ... other types
}
```

### 6. CLI Commands

**`seldon init <project-name>`**
1. Create `seldon.yaml` in current directory with project config
2. Create empty `seldon_events.jsonl`
3. Create Neo4j database: `CREATE DATABASE seldon_<slug> IF NOT EXISTS`
4. Create indexes
5. Create SeldonMeta sync point node
6. Print confirmation with project name and DB info

**`seldon status`**
1. Read `seldon.yaml` for project config
2. Connect to project's Neo4j database
3. Query: artifact counts by type, artifacts by state, open tasks, stale results
4. Print summary

**`seldon rebuild`**
1. Drop all nodes/relationships in project's Neo4j database  
2. Full replay from JSONL event log
3. Report: events replayed, artifacts created, relationships created, time elapsed

### 7. Project Config (`seldon.yaml`)

```yaml
project:
  name: "pragmatics-paper"
  slug: "pragmatics"
  domain: "research"
  created_at: "2026-03-14T10:00:00Z"

neo4j:
  uri: "bolt://localhost:7687"
  database: "seldon_pragmatics"
  # auth from environment: NEO4J_USERNAME, NEO4J_PASSWORD

event_store:
  path: "seldon_events.jsonl"
```

---

## What NOT To Build Yet

- No Postgres (Neo4j is the graph layer; Postgres is for Wintermute/arnold analytics)
- No MCP server
- No agent team infrastructure
- No `seldon briefing` / `seldon closeout` (Tier 2)
- No result registry commands (Tier 2)
- No `general_retrieve()` / `general_update()` interface (Tier 2)
- No RLM-style REPL retrieval (PL-013, much later)

---

## Dependencies

```
# pyproject.toml
[project]
name = "seldon"
version = "0.1.0"
dependencies = [
    "click>=8.0",
    "neo4j>=5.0",
    "pydantic>=2.0",
    "pyyaml>=6.0",
]

[project.scripts]
seldon = "seldon.cli:main"
```

---

## Verification Checklist

- [ ] `pip install -e .` succeeds
- [ ] `seldon --help` shows commands
- [ ] `seldon init test-project` creates seldon.yaml, seldon_events.jsonl, and Neo4j database `seldon_test_project`
- [ ] `seldon status` shows empty project stats
- [ ] Creating an artifact appends event to JSONL AND creates node in Neo4j
- [ ] Invalid artifact type (not in domain config) raises clear error
- [ ] Invalid state transition raises clear error with valid options
- [ ] `seldon rebuild` replays events into fresh Neo4j, result matches original
- [ ] Event count in JSONL matches node count in Neo4j after rebuild
- [ ] Tests pass with live Neo4j instance

---

## Backup Strategy

- **JSONL event log**: Lives in project directory. `git push` is the backup. Also syncs via iCloud if project dir is in an iCloud-synced location.
- **Neo4j data**: NOT backed up separately. It's a projection of the JSONL events. `seldon rebuild` recreates it from scratch. If Neo4j dies, you lose nothing — replay from JSONL.
- **seldon.yaml**: In project directory, git-tracked.

The JSONL event log is the only thing that matters for durability. Everything else is derived.
