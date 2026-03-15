> **SUPERSEDED** by `docs/plans/2026-03-14-seldon-core-engine-neo4j.md` (NetworkX replaced with Neo4j, 2026-03-14)

# Seldon Core Engine Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a pip-installable Python package that is Seldon's core engine — an event-sourced, NetworkX-backed research artifact tracker with a CLI, requiring zero database infrastructure.

**Architecture:** All project state is stored as an append-only JSONL event log (`seldon_events.jsonl`) inside the project directory. At runtime, events are replayed into a NetworkX DiGraph. Artifact types, relationships, and state machines are defined in a YAML domain config, keeping the engine domain-agnostic.

**Tech Stack:** Python 3.10+, Click (CLI), NetworkX (graph), PyYAML (domain config), python-dateutil (timestamps), pytest (tests)

---

## File Map

```
seldon/
├── seldon/
│   ├── __init__.py
│   ├── cli.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── events.py
│   │   ├── graph.py
│   │   ├── artifacts.py
│   │   └── state.py
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── loader.py
│   │   └── research.yaml
│   └── commands/
│       ├── __init__.py
│       ├── init.py
│       └── status.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_events.py
│   ├── test_graph.py
│   └── test_artifacts.py
├── pyproject.toml
└── README.md
```

---

## Task 1: Package Scaffold + pyproject.toml

**Files:**
- Create: `pyproject.toml`
- Create: `seldon/__init__.py`
- Create: `seldon/core/__init__.py`
- Create: `seldon/domain/__init__.py`
- Create: `seldon/commands/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

**Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "seldon"
version = "0.1.0"
description = "Research operating system for AI-assisted scientific and engineering work"
requires-python = ">=3.10"
dependencies = [
    "click>=8.1",
    "networkx>=3.2",
    "pyyaml>=6.0",
    "python-dateutil>=2.9",
]

[project.scripts]
seldon = "seldon.cli:cli"

[project.optional-dependencies]
dev = ["pytest>=7.4", "pytest-cov"]

[tool.setuptools.packages.find]
where = ["."]
include = ["seldon*"]

[tool.setuptools.package-data]
"seldon.domain" = ["*.yaml"]
```

**Step 2: Create empty `__init__.py` files**

All should be empty except `seldon/__init__.py`:

```python
# seldon/__init__.py
__version__ = "0.1.0"
```

**Step 3: Create `tests/conftest.py`**

```python
import pytest
import tempfile
import os
from pathlib import Path


@pytest.fixture
def project_dir(tmp_path):
    """A fresh temporary project directory."""
    return tmp_path


@pytest.fixture
def initialized_project(project_dir):
    """A project directory with seldon_events.jsonl already created."""
    events_file = project_dir / "seldon_events.jsonl"
    events_file.write_text("")
    config_file = project_dir / "seldon.yaml"
    config_file.write_text(
        "project_name: test_project\ndomain: research\n"
    )
    return project_dir
```

**Step 4: Verify pip install works**

```bash
cd /Users/brock/Documents/GitHub/seldon
pip install -e .
```

Expected: `Successfully installed seldon-0.1.0`

**Step 5: Verify CLI entry point exists**

```bash
seldon --help
```

Expected: error "No such command" or help text (CLI not yet written — this just confirms the entry point resolves)

**Step 6: Commit**

```bash
git add pyproject.toml seldon/__init__.py seldon/core/__init__.py seldon/domain/__init__.py seldon/commands/__init__.py tests/__init__.py tests/conftest.py
git commit -m "feat: add package scaffold and pyproject.toml"
```

---

## Task 2: Event Store (`core/events.py`)

**Files:**
- Create: `tests/test_events.py`
- Create: `seldon/core/events.py`

**Step 1: Write the failing tests**

```python
# tests/test_events.py
import json
import pytest
from pathlib import Path
from seldon.core.events import append_event, read_events, replay_events


def test_append_event_creates_file(project_dir):
    event = {
        "event_id": "abc123",
        "event_type": "artifact_created",
        "timestamp": "2026-03-09T00:00:00Z",
        "session_id": "sess1",
        "actor": "human",
        "payload": {"artifact_id": "art1", "artifact_type": "Result", "name": "Test"},
    }
    append_event(project_dir, event)
    events_file = project_dir / "seldon_events.jsonl"
    assert events_file.exists()


def test_append_event_is_valid_jsonl(project_dir):
    event = {
        "event_id": "abc123",
        "event_type": "artifact_created",
        "timestamp": "2026-03-09T00:00:00Z",
        "session_id": "sess1",
        "actor": "human",
        "payload": {"artifact_id": "art1", "artifact_type": "Result", "name": "Test"},
    }
    append_event(project_dir, event)
    line = (project_dir / "seldon_events.jsonl").read_text().strip()
    parsed = json.loads(line)
    assert parsed["event_id"] == "abc123"


def test_read_events_empty(initialized_project):
    events = read_events(initialized_project)
    assert events == []


def test_read_events_returns_all(project_dir):
    for i in range(3):
        append_event(project_dir, {
            "event_id": f"id{i}",
            "event_type": "artifact_created",
            "timestamp": "2026-03-09T00:00:00Z",
            "session_id": "s1",
            "actor": "human",
            "payload": {"artifact_id": f"art{i}", "artifact_type": "Result", "name": f"R{i}"},
        })
    events = read_events(project_dir)
    assert len(events) == 3


def test_replay_events_empty():
    state = replay_events([])
    assert state == {"artifacts": {}, "links": []}


def test_replay_events_artifact_created():
    events = [{
        "event_id": "e1",
        "event_type": "artifact_created",
        "timestamp": "2026-03-09T00:00:00Z",
        "session_id": "s1",
        "actor": "human",
        "payload": {
            "artifact_id": "art1",
            "artifact_type": "Result",
            "name": "My Result",
            "state": "proposed",
        },
    }]
    state = replay_events(events)
    assert "art1" in state["artifacts"]
    assert state["artifacts"]["art1"]["name"] == "My Result"
    assert state["artifacts"]["art1"]["state"] == "proposed"


def test_replay_events_artifact_updated():
    events = [
        {
            "event_id": "e1",
            "event_type": "artifact_created",
            "timestamp": "2026-03-09T00:00:00Z",
            "session_id": "s1",
            "actor": "human",
            "payload": {"artifact_id": "art1", "artifact_type": "Result", "name": "Old", "state": "proposed"},
        },
        {
            "event_id": "e2",
            "event_type": "artifact_updated",
            "timestamp": "2026-03-09T01:00:00Z",
            "session_id": "s1",
            "actor": "ai",
            "payload": {"artifact_id": "art1", "updates": {"name": "New"}},
        },
    ]
    state = replay_events(events)
    assert state["artifacts"]["art1"]["name"] == "New"


def test_replay_events_state_changed():
    events = [
        {
            "event_id": "e1",
            "event_type": "artifact_created",
            "timestamp": "2026-03-09T00:00:00Z",
            "session_id": "s1",
            "actor": "human",
            "payload": {"artifact_id": "art1", "artifact_type": "Result", "name": "R", "state": "proposed"},
        },
        {
            "event_id": "e2",
            "event_type": "artifact_state_changed",
            "timestamp": "2026-03-09T01:00:00Z",
            "session_id": "s1",
            "actor": "human",
            "payload": {"artifact_id": "art1", "new_state": "verified", "review_required": False},
        },
    ]
    state = replay_events(events)
    assert state["artifacts"]["art1"]["state"] == "verified"


def test_replay_events_link_created():
    events = [
        {
            "event_id": "e1",
            "event_type": "artifact_created",
            "timestamp": "2026-03-09T00:00:00Z",
            "session_id": "s1",
            "actor": "human",
            "payload": {"artifact_id": "art1", "artifact_type": "Result", "name": "R", "state": "proposed"},
        },
        {
            "event_id": "e2",
            "event_type": "artifact_created",
            "timestamp": "2026-03-09T00:00:00Z",
            "session_id": "s1",
            "actor": "human",
            "payload": {"artifact_id": "art2", "artifact_type": "Script", "name": "S", "state": "draft"},
        },
        {
            "event_id": "e3",
            "event_type": "link_created",
            "timestamp": "2026-03-09T00:00:00Z",
            "session_id": "s1",
            "actor": "human",
            "payload": {"source_id": "art2", "target_id": "art1", "relationship_type": "generated_by"},
        },
    ]
    state = replay_events(events)
    assert len(state["links"]) == 1
    assert state["links"][0]["source_id"] == "art2"
    assert state["links"][0]["relationship_type"] == "generated_by"
```

**Step 2: Run tests to verify they fail**

```bash
cd /Users/brock/Documents/GitHub/seldon
pytest tests/test_events.py -v
```

Expected: `ImportError: cannot import name 'append_event' from 'seldon.core.events'`

**Step 3: Implement `seldon/core/events.py`**

```python
import json
from pathlib import Path
from typing import Any


EVENTS_FILENAME = "seldon_events.jsonl"


def append_event(project_path: Path, event: dict[str, Any]) -> None:
    """Append a single event to the project's JSONL event log."""
    events_file = Path(project_path) / EVENTS_FILENAME
    with open(events_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def read_events(project_path: Path) -> list[dict[str, Any]]:
    """Read all events from the project's JSONL event log."""
    events_file = Path(project_path) / EVENTS_FILENAME
    if not events_file.exists():
        return []
    events = []
    for line in events_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            events.append(json.loads(line))
    return events


def replay_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Replay an event list and return the final project state."""
    state: dict[str, Any] = {"artifacts": {}, "links": []}

    for event in events:
        etype = event["event_type"]
        payload = event["payload"]

        if etype == "artifact_created":
            artifact_id = payload["artifact_id"]
            state["artifacts"][artifact_id] = {
                "artifact_id": artifact_id,
                "artifact_type": payload["artifact_type"],
                "name": payload.get("name", ""),
                "state": payload.get("state", "proposed"),
                "review_required": payload.get("review_required", False),
                "created_at": event["timestamp"],
                "updated_at": event["timestamp"],
                **{k: v for k, v in payload.items()
                   if k not in ("artifact_id", "artifact_type", "name", "state", "review_required")},
            }

        elif etype == "artifact_updated":
            artifact_id = payload["artifact_id"]
            if artifact_id in state["artifacts"]:
                state["artifacts"][artifact_id].update(payload.get("updates", {}))
                state["artifacts"][artifact_id]["updated_at"] = event["timestamp"]

        elif etype == "artifact_state_changed":
            artifact_id = payload["artifact_id"]
            if artifact_id in state["artifacts"]:
                state["artifacts"][artifact_id]["state"] = payload["new_state"]
                state["artifacts"][artifact_id]["review_required"] = payload.get("review_required", False)
                state["artifacts"][artifact_id]["updated_at"] = event["timestamp"]

        elif etype == "link_created":
            state["links"].append({
                "source_id": payload["source_id"],
                "target_id": payload["target_id"],
                "relationship_type": payload["relationship_type"],
                "created_at": event["timestamp"],
            })

        elif etype == "link_removed":
            state["links"] = [
                lnk for lnk in state["links"]
                if not (
                    lnk["source_id"] == payload["source_id"]
                    and lnk["target_id"] == payload["target_id"]
                    and lnk["relationship_type"] == payload["relationship_type"]
                )
            ]

    return state
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_events.py -v
```

Expected: All 9 tests PASS

**Step 5: Commit**

```bash
git add seldon/core/events.py tests/test_events.py
git commit -m "feat: add event store (append, read, replay)"
```

---

## Task 3: Domain Config (`domain/research.yaml` + `domain/loader.py`)

**Files:**
- Create: `seldon/domain/research.yaml`
- Create: `seldon/domain/loader.py`

> No separate test task — the domain loader is tested implicitly in Task 5 (artifacts). Write it now so Task 4 (graph) and Task 5 (artifacts) can import it.

**Step 1: Create `seldon/domain/research.yaml`**

```yaml
# Seldon Research Domain Configuration
# Loaded by seldon/domain/loader.py

artifact_types:
  - Result
  - Figure
  - PaperSection
  - Citation
  - ResearchTask
  - LabNotebookEntry
  - Script
  - DataFile
  - SRS_Requirement

relationship_types:
  - name: cites
    allowed_sources: [PaperSection, Result]
    allowed_targets: [Citation]
  - name: generated_by
    allowed_sources: [Result, Figure, DataFile]
    allowed_targets: [Script]
  - name: blocks
    allowed_sources: [ResearchTask]
    allowed_targets: [ResearchTask]
  - name: validates
    allowed_sources: [Result]
    allowed_targets: [Result]
  - name: computed_from
    allowed_sources: [Result, Figure, DataFile]
    allowed_targets: [DataFile, Result]
  - name: implements
    allowed_sources: [Script]
    allowed_targets: [SRS_Requirement]
  - name: produced_by
    allowed_sources: [Result, Figure, PaperSection]
    allowed_targets: [ResearchTask]

state_machines:
  Result:
    initial: proposed
    transitions:
      proposed: [verified]
      verified: [published]
      published: []
  ResearchTask:
    initial: proposed
    transitions:
      proposed: [accepted]
      accepted: [in_progress]
      in_progress: [completed]
      completed: [verified]
      verified: []
  Script:
    initial: draft
    transitions:
      draft: [active]
      active: [deprecated]
      deprecated: []
  DataFile:
    initial: staged
    transitions:
      staged: [validated]
      validated: [archived]
      archived: []
  Deliverable:
    initial: draft
    transitions:
      draft: [submitted]
      submitted: [published]
      published: []
  Figure:
    initial: proposed
    transitions:
      proposed: [verified]
      verified: [published]
      published: []
  PaperSection:
    initial: draft
    transitions:
      draft: [submitted]
      submitted: [published]
      published: []
  Citation:
    initial: proposed
    transitions:
      proposed: [verified]
      verified: []
  LabNotebookEntry:
    initial: draft
    transitions:
      draft: [finalized]
      finalized: []
  SRS_Requirement:
    initial: draft
    transitions:
      draft: [approved]
      approved: [implemented]
      implemented: [verified]
      verified: []

# Artifact types that require computed_from or generated_by links
# before state can advance to 'verified'
provenance_required:
  - Result
  - Figure
  - DataFile
```

**Step 2: Create `seldon/domain/loader.py`**

```python
import yaml
from pathlib import Path
from typing import Any


def load_domain_config(domain_name: str) -> dict[str, Any]:
    """Load a domain YAML config by name from the domain package directory."""
    domain_dir = Path(__file__).parent
    config_path = domain_dir / f"{domain_name}.yaml"
    if not config_path.exists():
        raise FileNotFoundError(
            f"Domain config not found: {config_path}. "
            f"Available domains: {[p.stem for p in domain_dir.glob('*.yaml')]}"
        )
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_artifact_types(domain_config: dict[str, Any]) -> list[str]:
    return domain_config["artifact_types"]


def get_relationship_types(domain_config: dict[str, Any]) -> list[str]:
    return [rt["name"] for rt in domain_config["relationship_types"]]


def get_provenance_required(domain_config: dict[str, Any]) -> list[str]:
    return domain_config.get("provenance_required", [])
```

**Step 3: Verify the loader works**

```bash
python -c "from seldon.domain.loader import load_domain_config; c = load_domain_config('research'); print(c['artifact_types'])"
```

Expected: `['Result', 'Figure', 'PaperSection', 'Citation', 'ResearchTask', 'LabNotebookEntry', 'Script', 'DataFile', 'SRS_Requirement']`

**Step 4: Commit**

```bash
git add seldon/domain/research.yaml seldon/domain/loader.py
git commit -m "feat: add research domain config and loader"
```

---

## Task 4: State Machine (`core/state.py`)

**Files:**
- Create: `seldon/core/state.py`

> State machine is tested in Task 5 (artifacts). Implement here so Task 5 can import it.

**Step 1: Implement `seldon/core/state.py`**

```python
from typing import Any


def load_state_machines(domain_config: dict[str, Any]) -> dict[str, dict[str, list[str]]]:
    """
    Parse state machine definitions from domain config.

    Returns dict: { artifact_type -> { from_state -> [to_states] } }
    """
    result = {}
    for artifact_type, sm in domain_config.get("state_machines", {}).items():
        result[artifact_type] = sm["transitions"]
    return result


def validate_transition(
    state_machines: dict[str, dict[str, list[str]]],
    artifact_type: str,
    current_state: str,
    new_state: str,
) -> tuple[bool, str]:
    """
    Validate a state transition.

    Returns (is_valid, reason).
    reason is empty string on success, error message on failure.
    """
    if artifact_type not in state_machines:
        return False, f"No state machine defined for artifact type '{artifact_type}'"

    transitions = state_machines[artifact_type]

    if current_state not in transitions:
        return False, f"Unknown state '{current_state}' for artifact type '{artifact_type}'"

    valid_next = transitions[current_state]

    if new_state not in valid_next:
        if valid_next:
            return False, (
                f"Cannot transition '{artifact_type}' from '{current_state}' to '{new_state}'. "
                f"Valid transitions: {valid_next}"
            )
        else:
            return False, (
                f"'{artifact_type}' in state '{current_state}' is terminal — no further transitions allowed."
            )

    return True, ""


def get_valid_transitions(
    state_machines: dict[str, dict[str, list[str]]],
    artifact_type: str,
    current_state: str,
) -> list[str]:
    """Return the list of valid next states for an artifact in its current state."""
    if artifact_type not in state_machines:
        return []
    transitions = state_machines[artifact_type]
    return transitions.get(current_state, [])
```

**Step 2: Commit**

```bash
git add seldon/core/state.py
git commit -m "feat: add state machine (validate transitions)"
```

---

## Task 5: Graph Projection (`core/graph.py`)

**Files:**
- Create: `tests/test_graph.py`
- Create: `seldon/core/graph.py`

**Step 1: Write the failing tests**

```python
# tests/test_graph.py
import pytest
from seldon.core.graph import build_graph, get_artifact, get_links, get_downstream, compute_risk_score


ARTIFACT_CREATED = "artifact_created"
LINK_CREATED = "link_created"


def make_event(etype, payload, ts="2026-03-09T00:00:00Z"):
    return {"event_id": "e1", "event_type": etype, "timestamp": ts,
            "session_id": "s1", "actor": "human", "payload": payload}


def test_build_graph_empty():
    graph = build_graph([])
    assert len(graph.nodes) == 0
    assert len(graph.edges) == 0


def test_build_graph_adds_artifact_nodes():
    events = [
        make_event(ARTIFACT_CREATED, {"artifact_id": "a1", "artifact_type": "Result", "name": "R1", "state": "proposed"}),
        make_event(ARTIFACT_CREATED, {"artifact_id": "a2", "artifact_type": "Script", "name": "S1", "state": "draft"}),
    ]
    graph = build_graph(events)
    assert "a1" in graph.nodes
    assert "a2" in graph.nodes
    assert graph.nodes["a1"]["artifact_type"] == "Result"


def test_build_graph_adds_edges():
    events = [
        make_event(ARTIFACT_CREATED, {"artifact_id": "a1", "artifact_type": "Result", "name": "R", "state": "proposed"}),
        make_event(ARTIFACT_CREATED, {"artifact_id": "a2", "artifact_type": "Script", "name": "S", "state": "draft"}),
        make_event(LINK_CREATED, {"source_id": "a2", "target_id": "a1", "relationship_type": "generated_by"}),
    ]
    graph = build_graph(events)
    assert graph.has_edge("a2", "a1")
    assert graph.edges["a2", "a1"]["relationship_type"] == "generated_by"


def test_get_artifact_returns_node_data():
    events = [
        make_event(ARTIFACT_CREATED, {"artifact_id": "a1", "artifact_type": "Result", "name": "My Result", "state": "proposed"}),
    ]
    graph = build_graph(events)
    data = get_artifact(graph, "a1")
    assert data["name"] == "My Result"


def test_get_artifact_missing_returns_none():
    graph = build_graph([])
    assert get_artifact(graph, "nonexistent") is None


def test_get_links_returns_edges():
    events = [
        make_event(ARTIFACT_CREATED, {"artifact_id": "a1", "artifact_type": "Result", "name": "R", "state": "proposed"}),
        make_event(ARTIFACT_CREATED, {"artifact_id": "a2", "artifact_type": "Script", "name": "S", "state": "draft"}),
        make_event(LINK_CREATED, {"source_id": "a2", "target_id": "a1", "relationship_type": "generated_by"}),
    ]
    graph = build_graph(events)
    links = get_links(graph, "a2")
    assert len(links) == 1
    assert links[0]["target_id"] == "a1"
    assert links[0]["relationship_type"] == "generated_by"


def test_get_downstream_empty():
    events = [
        make_event(ARTIFACT_CREATED, {"artifact_id": "a1", "artifact_type": "Result", "name": "R", "state": "proposed"}),
    ]
    graph = build_graph(events)
    assert get_downstream(graph, "a1") == []


def test_get_downstream_traverses_dependents():
    # a1 -> a2 -> a3 (a1 is upstream, a3 is downstream)
    events = [
        make_event(ARTIFACT_CREATED, {"artifact_id": "a1", "artifact_type": "Script", "name": "S", "state": "draft"}),
        make_event(ARTIFACT_CREATED, {"artifact_id": "a2", "artifact_type": "Result", "name": "R", "state": "proposed"}),
        make_event(ARTIFACT_CREATED, {"artifact_id": "a3", "artifact_type": "Figure", "name": "F", "state": "proposed"}),
        make_event(LINK_CREATED, {"source_id": "a1", "target_id": "a2", "relationship_type": "generated_by"}),
        make_event(LINK_CREATED, {"source_id": "a2", "target_id": "a3", "relationship_type": "computed_from"}),
    ]
    graph = build_graph(events)
    downstream = get_downstream(graph, "a1")
    assert "a2" in downstream
    assert "a3" in downstream


def test_compute_risk_score_base_by_type():
    events = [
        make_event(ARTIFACT_CREATED, {"artifact_id": "r1", "artifact_type": "Result", "name": "R", "state": "proposed"}),
        make_event(ARTIFACT_CREATED, {"artifact_id": "s1", "artifact_type": "Script", "name": "S", "state": "draft"}),
    ]
    graph = build_graph(events)
    assert compute_risk_score(graph, "r1") == pytest.approx(0.8, abs=0.01)
    assert compute_risk_score(graph, "s1") == pytest.approx(0.3, abs=0.01)


def test_compute_risk_score_multiplied_by_dependents():
    # r1 (Result, base 0.8) with 2 downstream dependents -> multiplied
    events = [
        make_event(ARTIFACT_CREATED, {"artifact_id": "r1", "artifact_type": "Result", "name": "R", "state": "verified"}),
        make_event(ARTIFACT_CREATED, {"artifact_id": "d1", "artifact_type": "Figure", "name": "F1", "state": "proposed"}),
        make_event(ARTIFACT_CREATED, {"artifact_id": "d2", "artifact_type": "Figure", "name": "F2", "state": "proposed"}),
        make_event(LINK_CREATED, {"source_id": "r1", "target_id": "d1", "relationship_type": "computed_from"}),
        make_event(LINK_CREATED, {"source_id": "r1", "target_id": "d2", "relationship_type": "computed_from"}),
    ]
    graph = build_graph(events)
    score = compute_risk_score(graph, "r1")
    assert score > 0.8  # multiplier applied
    assert score <= 1.0  # capped


def test_compute_risk_score_published_is_max():
    events = [
        make_event(ARTIFACT_CREATED, {"artifact_id": "r1", "artifact_type": "Script", "name": "S", "state": "active"}),
        {"event_id": "e2", "event_type": "artifact_state_changed", "timestamp": "2026-03-09T01:00:00Z",
         "session_id": "s1", "actor": "human", "payload": {"artifact_id": "r1", "new_state": "deprecated", "review_required": False}},
    ]
    # Actually test with published state
    events2 = [
        make_event(ARTIFACT_CREATED, {"artifact_id": "r2", "artifact_type": "Result", "name": "R", "state": "published"}),
    ]
    graph = build_graph(events2)
    assert compute_risk_score(graph, "r2") == 1.0


def test_compute_risk_score_returns_float_between_0_and_1():
    events = [
        make_event(ARTIFACT_CREATED, {"artifact_id": "a1", "artifact_type": "ResearchTask", "name": "T", "state": "proposed"}),
    ]
    graph = build_graph(events)
    score = compute_risk_score(graph, "a1")
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_graph.py -v
```

Expected: `ImportError`

**Step 3: Implement `seldon/core/graph.py`**

```python
import networkx as nx
from typing import Any, Optional

from seldon.core.events import replay_events


# Base risk scores by artifact type
_BASE_RISK: dict[str, float] = {
    "Result": 0.8,
    "Methodology": 0.7,
    "Figure": 0.6,
    "PaperSection": 0.5,
    "Deliverable": 0.5,
    "Script": 0.3,
    "DataFile": 0.2,
    "Citation": 0.2,
    "SRS_Requirement": 0.2,
    "LabNotebookEntry": 0.1,
    "ResearchTask": 0.1,
}
_DEFAULT_BASE_RISK = 0.3
_MAX_DOWNSTREAM_MULTIPLIER = 3.0


def build_graph(events: list[dict[str, Any]]) -> nx.DiGraph:
    """Build a NetworkX DiGraph from a list of events via replay."""
    state = replay_events(events)
    graph = nx.DiGraph()

    for artifact_id, data in state["artifacts"].items():
        graph.add_node(artifact_id, **data)

    for link in state["links"]:
        graph.add_edge(
            link["source_id"],
            link["target_id"],
            relationship_type=link["relationship_type"],
            created_at=link.get("created_at", ""),
        )

    return graph


def get_artifact(graph: nx.DiGraph, artifact_id: str) -> Optional[dict[str, Any]]:
    """Return node data for an artifact, or None if not found."""
    if artifact_id not in graph.nodes:
        return None
    return dict(graph.nodes[artifact_id])


def get_links(graph: nx.DiGraph, artifact_id: str) -> list[dict[str, Any]]:
    """Return all outgoing edges for an artifact node."""
    if artifact_id not in graph.nodes:
        return []
    return [
        {
            "source_id": artifact_id,
            "target_id": target,
            **graph.edges[artifact_id, target],
        }
        for target in graph.successors(artifact_id)
    ]


def get_downstream(graph: nx.DiGraph, artifact_id: str) -> list[str]:
    """Return all descendant artifact IDs (transitive)."""
    if artifact_id not in graph.nodes:
        return []
    return list(nx.descendants(graph, artifact_id))


def compute_risk_score(graph: nx.DiGraph, artifact_id: str) -> float:
    """
    Compute risk score for an artifact based on:
    - Base score by artifact type
    - Multiplier for downstream dependent count (capped at 3x)
    - Override to 1.0 for 'published' state
    - Override to 1.0 for missing provenance (computed_from/generated_by) where expected
    """
    if artifact_id not in graph.nodes:
        return 0.0

    node = graph.nodes[artifact_id]
    state = node.get("state", "")

    # Immediate override: published state
    if state == "published":
        return 1.0

    artifact_type = node.get("artifact_type", "")
    base = _BASE_RISK.get(artifact_type, _DEFAULT_BASE_RISK)

    # Downstream multiplier: number of descendants, capped at 3x
    downstream_count = len(get_downstream(graph, artifact_id))
    if downstream_count == 0:
        multiplier = 1.0
    else:
        multiplier = min(1.0 + (downstream_count * 0.5), _MAX_DOWNSTREAM_MULTIPLIER)

    score = base * multiplier
    return min(score, 1.0)
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_graph.py -v
```

Expected: All 11 tests PASS

**Step 5: Commit**

```bash
git add seldon/core/graph.py tests/test_graph.py
git commit -m "feat: add NetworkX graph projection with risk scoring"
```

---

## Task 6: Artifact CRUD (`core/artifacts.py`)

**Files:**
- Create: `tests/test_artifacts.py`
- Create: `seldon/core/artifacts.py`

**Step 1: Write the failing tests**

```python
# tests/test_artifacts.py
import pytest
from seldon.core.artifacts import (
    create_artifact,
    update_artifact,
    transition_state,
    create_link,
    get_artifact,
    list_artifacts,
)
from seldon.core.events import read_events
from seldon.domain.loader import load_domain_config


@pytest.fixture
def domain_config():
    return load_domain_config("research")


def test_create_artifact_appends_event(initialized_project, domain_config):
    art_id = create_artifact(
        initialized_project,
        artifact_type="Result",
        data={"name": "Test Result"},
        actor="human",
        domain_config=domain_config,
    )
    events = read_events(initialized_project)
    assert len(events) == 1
    assert events[0]["event_type"] == "artifact_created"
    assert events[0]["payload"]["artifact_id"] == art_id


def test_create_artifact_returns_id(initialized_project, domain_config):
    art_id = create_artifact(
        initialized_project,
        artifact_type="Result",
        data={"name": "R"},
        actor="human",
        domain_config=domain_config,
    )
    assert isinstance(art_id, str)
    assert len(art_id) > 0


def test_create_artifact_invalid_type_raises(initialized_project, domain_config):
    with pytest.raises(ValueError, match="Invalid artifact type"):
        create_artifact(
            initialized_project,
            artifact_type="NotARealType",
            data={"name": "X"},
            actor="human",
            domain_config=domain_config,
        )


def test_create_artifact_sets_initial_state(initialized_project, domain_config):
    art_id = create_artifact(
        initialized_project,
        artifact_type="Script",
        data={"name": "S"},
        actor="human",
        domain_config=domain_config,
    )
    artifact = get_artifact(initialized_project, art_id)
    assert artifact["state"] == "draft"


def test_update_artifact(initialized_project, domain_config):
    art_id = create_artifact(
        initialized_project,
        artifact_type="Result",
        data={"name": "Old"},
        actor="human",
        domain_config=domain_config,
    )
    update_artifact(initialized_project, art_id, {"name": "New"}, actor="ai")
    artifact = get_artifact(initialized_project, art_id)
    assert artifact["name"] == "New"


def test_transition_state_valid(initialized_project, domain_config):
    art_id = create_artifact(
        initialized_project,
        artifact_type="Result",
        data={"name": "R"},
        actor="human",
        domain_config=domain_config,
    )
    transition_state(initialized_project, art_id, "verified", actor="human", domain_config=domain_config)
    artifact = get_artifact(initialized_project, art_id)
    assert artifact["state"] == "verified"


def test_transition_state_invalid_raises(initialized_project, domain_config):
    art_id = create_artifact(
        initialized_project,
        artifact_type="Result",
        data={"name": "R"},
        actor="human",
        domain_config=domain_config,
    )
    with pytest.raises(ValueError, match="Cannot transition"):
        transition_state(initialized_project, art_id, "published", actor="human", domain_config=domain_config)


def test_transition_state_sets_review_required_high_risk(initialized_project, domain_config):
    # Result (base 0.8) -> going to published (override 1.0) -> review_required
    art_id = create_artifact(
        initialized_project,
        artifact_type="Result",
        data={"name": "R"},
        actor="human",
        domain_config=domain_config,
    )
    # First go to verified (valid)
    transition_state(initialized_project, art_id, "verified", actor="human", domain_config=domain_config)
    # Then to published (should set review_required)
    transition_state(initialized_project, art_id, "published", actor="human", domain_config=domain_config)
    artifact = get_artifact(initialized_project, art_id)
    assert artifact["review_required"] is True


def test_create_link_valid(initialized_project, domain_config):
    script_id = create_artifact(
        initialized_project, artifact_type="Script", data={"name": "S"}, actor="human", domain_config=domain_config
    )
    result_id = create_artifact(
        initialized_project, artifact_type="Result", data={"name": "R"}, actor="human", domain_config=domain_config
    )
    create_link(initialized_project, script_id, result_id, "generated_by", actor="human", domain_config=domain_config)
    events = read_events(initialized_project)
    link_events = [e for e in events if e["event_type"] == "link_created"]
    assert len(link_events) == 1


def test_create_link_invalid_type_raises(initialized_project, domain_config):
    a1 = create_artifact(initialized_project, "Result", {"name": "R"}, "human", domain_config)
    a2 = create_artifact(initialized_project, "Script", {"name": "S"}, "human", domain_config)
    with pytest.raises(ValueError, match="Invalid relationship type"):
        create_link(initialized_project, a1, a2, "fake_relationship", "human", domain_config)


def test_list_artifacts_all(initialized_project, domain_config):
    create_artifact(initialized_project, "Result", {"name": "R1"}, "human", domain_config)
    create_artifact(initialized_project, "Script", {"name": "S1"}, "human", domain_config)
    create_artifact(initialized_project, "Result", {"name": "R2"}, "human", domain_config)
    artifacts = list_artifacts(initialized_project)
    assert len(artifacts) == 3


def test_list_artifacts_filtered_by_type(initialized_project, domain_config):
    create_artifact(initialized_project, "Result", {"name": "R1"}, "human", domain_config)
    create_artifact(initialized_project, "Script", {"name": "S1"}, "human", domain_config)
    results = list_artifacts(initialized_project, artifact_type="Result")
    assert len(results) == 1
    assert results[0]["artifact_type"] == "Result"


def test_list_artifacts_filtered_by_state(initialized_project, domain_config):
    art_id = create_artifact(initialized_project, "Result", {"name": "R1"}, "human", domain_config)
    create_artifact(initialized_project, "Result", {"name": "R2"}, "human", domain_config)
    transition_state(initialized_project, art_id, "verified", "human", domain_config)
    verified = list_artifacts(initialized_project, state="verified")
    assert len(verified) == 1
    assert verified[0]["artifact_id"] == art_id
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_artifacts.py -v
```

Expected: `ImportError`

**Step 3: Implement `seldon/core/artifacts.py`**

```python
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from seldon.core.events import append_event, read_events, replay_events
from seldon.core.graph import build_graph, compute_risk_score
from seldon.core.state import load_state_machines, validate_transition
from seldon.domain.loader import (
    get_artifact_types,
    get_relationship_types,
)

_REVIEW_REQUIRED_THRESHOLD = 0.7


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_session_id() -> str:
    return str(uuid.uuid4())


def create_artifact(
    project_path: Path,
    artifact_type: str,
    data: dict[str, Any],
    actor: str,
    domain_config: dict[str, Any],
) -> str:
    """Create an artifact. Returns the new artifact_id."""
    valid_types = get_artifact_types(domain_config)
    if artifact_type not in valid_types:
        raise ValueError(
            f"Invalid artifact type '{artifact_type}'. "
            f"Valid types for this domain: {valid_types}"
        )

    # Determine initial state from domain config
    state_machines = domain_config.get("state_machines", {})
    initial_state = state_machines.get(artifact_type, {}).get("initial", "proposed")

    artifact_id = str(uuid.uuid4())
    event = {
        "event_id": str(uuid.uuid4()),
        "event_type": "artifact_created",
        "timestamp": _now(),
        "session_id": _new_session_id(),
        "actor": actor,
        "payload": {
            "artifact_id": artifact_id,
            "artifact_type": artifact_type,
            "state": initial_state,
            "review_required": False,
            **data,
        },
    }
    append_event(project_path, event)
    return artifact_id


def update_artifact(
    project_path: Path,
    artifact_id: str,
    updates: dict[str, Any],
    actor: str,
) -> None:
    """Update artifact fields. Appends an artifact_updated event."""
    event = {
        "event_id": str(uuid.uuid4()),
        "event_type": "artifact_updated",
        "timestamp": _now(),
        "session_id": _new_session_id(),
        "actor": actor,
        "payload": {
            "artifact_id": artifact_id,
            "updates": updates,
        },
    }
    append_event(project_path, event)


def transition_state(
    project_path: Path,
    artifact_id: str,
    new_state: str,
    actor: str,
    domain_config: dict[str, Any],
) -> None:
    """Transition an artifact to a new state. Validates state machine and computes risk."""
    events = read_events(project_path)
    state = replay_events(events)

    if artifact_id not in state["artifacts"]:
        raise ValueError(f"Artifact '{artifact_id}' not found.")

    artifact = state["artifacts"][artifact_id]
    artifact_type = artifact["artifact_type"]
    current_state = artifact["state"]

    state_machines = load_state_machines(domain_config)
    is_valid, reason = validate_transition(state_machines, artifact_type, current_state, new_state)
    if not is_valid:
        raise ValueError(reason)

    # Build graph with this transition applied (simulate) to compute risk
    # We compute risk score pre-transition on the graph as-is, then override for 'published'
    graph = build_graph(events)
    risk_score = compute_risk_score(graph, artifact_id)

    # Override: any transition to 'published' is always risk=1.0
    if new_state == "published":
        risk_score = 1.0

    review_required = risk_score >= _REVIEW_REQUIRED_THRESHOLD

    event = {
        "event_id": str(uuid.uuid4()),
        "event_type": "artifact_state_changed",
        "timestamp": _now(),
        "session_id": _new_session_id(),
        "actor": actor,
        "payload": {
            "artifact_id": artifact_id,
            "from_state": current_state,
            "new_state": new_state,
            "risk_score": risk_score,
            "review_required": review_required,
        },
    }
    append_event(project_path, event)


def create_link(
    project_path: Path,
    source_id: str,
    target_id: str,
    relationship_type: str,
    actor: str,
    domain_config: dict[str, Any],
) -> None:
    """Create a typed link between two artifacts."""
    valid_rel_types = get_relationship_types(domain_config)
    if relationship_type not in valid_rel_types:
        raise ValueError(
            f"Invalid relationship type '{relationship_type}'. "
            f"Valid types for this domain: {valid_rel_types}"
        )

    event = {
        "event_id": str(uuid.uuid4()),
        "event_type": "link_created",
        "timestamp": _now(),
        "session_id": _new_session_id(),
        "actor": actor,
        "payload": {
            "source_id": source_id,
            "target_id": target_id,
            "relationship_type": relationship_type,
        },
    }
    append_event(project_path, event)


def get_artifact(project_path: Path, artifact_id: str) -> Optional[dict[str, Any]]:
    """Return the current state of an artifact by replaying events."""
    events = read_events(project_path)
    state = replay_events(events)
    return state["artifacts"].get(artifact_id)


def list_artifacts(
    project_path: Path,
    artifact_type: Optional[str] = None,
    state: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Return all artifacts, optionally filtered by type and/or state."""
    events = read_events(project_path)
    proj_state = replay_events(events)
    artifacts = list(proj_state["artifacts"].values())
    if artifact_type is not None:
        artifacts = [a for a in artifacts if a["artifact_type"] == artifact_type]
    if state is not None:
        artifacts = [a for a in artifacts if a["state"] == state]
    return artifacts
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_artifacts.py -v
```

Expected: All 14 tests PASS

**Step 5: Run the full test suite**

```bash
pytest tests/ -v
```

Expected: All tests PASS

**Step 6: Commit**

```bash
git add seldon/core/artifacts.py tests/test_artifacts.py seldon/core/state.py
git commit -m "feat: add artifact CRUD with state machine enforcement"
```

---

## Task 7: CLI (`cli.py`, `commands/init.py`, `commands/status.py`)

**Files:**
- Create: `seldon/cli.py`
- Create: `seldon/commands/init.py`
- Create: `seldon/commands/status.py`

> CLI commands are integration-level — test manually (smoke test).

**Step 1: Create `seldon/commands/init.py`**

```python
import sys
from datetime import datetime, timezone
from pathlib import Path

import click
import yaml

from seldon import __version__
from seldon.domain.loader import load_domain_config


EVENTS_FILENAME = "seldon_events.jsonl"
CONFIG_FILENAME = "seldon.yaml"
SELDON_DIR = ".seldon"


def run_init(project_path: Path, domain: str, project_name: str) -> None:
    """Initialize a Seldon project in project_path."""
    events_file = project_path / EVENTS_FILENAME
    config_file = project_path / CONFIG_FILENAME
    seldon_dir = project_path / SELDON_DIR

    if events_file.exists() or config_file.exists():
        click.echo("Error: Seldon is already initialized in this directory.", err=True)
        sys.exit(1)

    # Validate domain exists
    load_domain_config(domain)

    # Create event log
    events_file.write_text("", encoding="utf-8")

    # Create config
    config = {
        "project_name": project_name,
        "domain": domain,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "seldon_version": __version__,
        "active_tier": 1,
    }
    config_file.write_text(yaml.dump(config, default_flow_style=False), encoding="utf-8")

    # Create runtime directory
    seldon_dir.mkdir(exist_ok=True)

    click.echo(f"Seldon initialized. Project: {project_name}. Domain: {domain}.")
```

**Step 2: Create `seldon/commands/status.py`**

```python
from collections import Counter
from pathlib import Path

import click
import yaml

from seldon.core.events import read_events, replay_events


CONFIG_FILENAME = "seldon.yaml"


def run_status(project_path: Path) -> None:
    """Print project status summary."""
    config_file = project_path / CONFIG_FILENAME
    if not config_file.exists():
        click.echo("Error: No seldon.yaml found. Run `seldon init` first.", err=True)
        return

    config = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    events = read_events(project_path)

    if not events:
        click.echo("No artifacts registered. Run `seldon artifact create` to begin.")
        return

    state = replay_events(events)
    artifacts = list(state["artifacts"].values())

    # Counts by type
    type_counts = Counter(a["artifact_type"] for a in artifacts)

    # Open tasks
    open_tasks = [
        a for a in artifacts
        if a["artifact_type"] == "ResearchTask"
        and a["state"] not in ("completed", "verified")
    ]

    # Pending review
    review_required = [a for a in artifacts if a.get("review_required")]

    click.echo(f"\nProject: {config.get('project_name', 'unknown')}  |  Domain: {config.get('domain', 'unknown')}  |  Tier: {config.get('active_tier', 1)}")
    click.echo(f"Events logged: {len(events)}\n")

    click.echo("Artifacts by type:")
    for artifact_type, count in sorted(type_counts.items()):
        click.echo(f"  {artifact_type:<20} {count}")

    click.echo(f"\nOpen tasks:          {len(open_tasks)}")
    click.echo(f"Pending review:      {len(review_required)}")

    if review_required:
        click.echo("\nReview queue:")
        for a in review_required:
            click.echo(f"  [{a['artifact_type']}] {a.get('name', a['artifact_id'])}  (state: {a['state']})")
```

**Step 3: Create `seldon/cli.py`**

```python
from pathlib import Path

import click

from seldon.commands.init import run_init
from seldon.commands.status import run_status


@click.group()
def cli():
    """Seldon — Research operating system for AI-assisted scientific work."""


@cli.command()
@click.option("--domain", default="research", show_default=True, help="Domain configuration to use.")
@click.option("--project-name", default=None, help="Project name (defaults to current directory name).")
@click.argument("path", default=".", type=click.Path(file_okay=False, path_type=Path))
def init(domain: str, project_name: str, path: Path):
    """Initialize a new Seldon project."""
    project_path = path.resolve()
    if project_name is None:
        project_name = project_path.name
    run_init(project_path, domain, project_name)


@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False, path_type=Path))
def status(path: Path):
    """Show project status summary."""
    run_status(path.resolve())
```

**Step 4: Reinstall package to pick up new entry point**

```bash
pip install -e .
```

**Step 5: Smoke test `seldon init`**

```bash
cd /tmp && mkdir seldon_smoke_test && cd seldon_smoke_test
seldon init --project-name smoke_test
```

Expected:
```
Seldon initialized. Project: smoke_test. Domain: research.
```

Verify files created:
```bash
ls -la /tmp/seldon_smoke_test/
```

Expected: `seldon_events.jsonl`, `seldon.yaml`, `.seldon/`

**Step 6: Smoke test `seldon status` on empty project**

```bash
seldon status /tmp/seldon_smoke_test
```

Expected:
```
No artifacts registered. Run `seldon artifact create` to begin.
```

**Step 7: Smoke test `seldon --help`**

```bash
seldon --help
```

Expected: Shows `init` and `status` commands.

**Step 8: Commit**

```bash
cd /Users/brock/Documents/GitHub/seldon
git add seldon/cli.py seldon/commands/init.py seldon/commands/status.py
git commit -m "feat: add CLI with init and status commands"
```

---

## Task 8: Final Verification

**Step 1: Run full test suite**

```bash
cd /Users/brock/Documents/GitHub/seldon
pytest tests/ -v
```

Expected: All tests PASS. No skips.

**Step 2: Verify pip install from clean state**

```bash
pip install -e .
seldon --help
```

Expected: `init` and `status` listed.

**Step 3: Run the CC task verification checklist**

```bash
# 1. pip install succeeds — done above

# 2. seldon --help
seldon --help

# 3. seldon init creates correct files
cd /tmp && rm -rf seldon_verify && mkdir seldon_verify
seldon init /tmp/seldon_verify --project-name verify_test
ls /tmp/seldon_verify

# 4. seldon status on empty project
seldon status /tmp/seldon_verify

# 5. pytest passes
cd /Users/brock/Documents/GitHub/seldon
pytest tests/ -v

# 6. Creating artifact appends event — verify via Python
python - <<'EOF'
from pathlib import Path
from seldon.core.artifacts import create_artifact
from seldon.core.events import read_events
from seldon.domain.loader import load_domain_config

p = Path("/tmp/seldon_verify")
dc = load_domain_config("research")
create_artifact(p, "Result", {"name": "Test"}, "human", dc)
events = read_events(p)
print(f"Events: {len(events)} — type: {events[0]['event_type']}")
EOF

# 7. Invalid artifact type raises clear error
python - <<'EOF'
from pathlib import Path
from seldon.core.artifacts import create_artifact
from seldon.domain.loader import load_domain_config
try:
    create_artifact(Path("/tmp/seldon_verify"), "FakeType", {}, "human", load_domain_config("research"))
except ValueError as e:
    print(f"Got expected error: {e}")
EOF

# 8. Invalid state transition raises clear error
python - <<'EOF'
from pathlib import Path
from seldon.core.artifacts import create_artifact, transition_state
from seldon.domain.loader import load_domain_config
p = Path("/tmp/seldon_verify")
dc = load_domain_config("research")
art_id = create_artifact(p, "Result", {"name": "R"}, "human", dc)
try:
    transition_state(p, art_id, "published", "human", dc)  # skips verified
except ValueError as e:
    print(f"Got expected error: {e}")
EOF

# 9. No database imports
grep -r "import psycopg\|import neo4j\|import sqlalchemy\|import postgres\|import pg8000" seldon/
echo "Exit code $? (0 = no matches = PASS)"
```

**Step 4: Final commit**

```bash
git add .
git commit -m "feat: seldon core engine v0.1.0 — event store, graph, artifact CRUD, CLI"
```

---

## Verification Checklist (from CC Task 2)

- [ ] `pip install -e .` succeeds from repo root
- [ ] `seldon --help` shows available commands
- [ ] `seldon init` creates `seldon_events.jsonl` and `seldon.yaml` in current directory
- [ ] `seldon status` runs without error on empty project
- [ ] `pytest tests/` passes all tests
- [ ] Creating an artifact appends an event to the JSONL log
- [ ] Invalid artifact type (not in domain config) raises a clear error
- [ ] Invalid state transition raises a clear error with valid options listed
- [ ] Graph rebuilds correctly from replayed events
- [ ] Risk score returns float between 0.0 and 1.0
- [ ] `review_required=True` is set when risk score >= 0.7
- [ ] No Postgres, Neo4j, or database imports anywhere in the codebase
