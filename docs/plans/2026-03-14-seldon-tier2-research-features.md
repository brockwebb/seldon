# Seldon Tier 2 — Result Registry, Task Tracking, Session Briefing/Closeout

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add result registry, task tracking, staleness propagation, and session briefing/closeout to Seldon's CLI, making the research workflow loop (`briefing` → work → `closeout`) fully functional.

**Architecture:** Builds on the existing `artifacts.py` / `graph.py` / `events.py` core without restructuring it. New files: `seldon/core/staleness.py`, `seldon/commands/result.py`, `seldon/commands/task.py`, `seldon/commands/session.py`. Session state stored in `.seldon/current_session.json`. Staleness propagation hooks into `artifacts.transition_state` — when any artifact goes stale, downstream artifacts that CITES it cascade automatically.

**Tech Stack:** Python 3.10+, click>=8.0, neo4j>=5.0, pydantic>=2.0, pyyaml>=6.0, pytest>=7.0. All Neo4j tests skip gracefully if unreachable (existing conftest pattern).

**Working directory:** `/Users/brock/Documents/GitHub/seldon/.worktrees/tier2-features`
**Branch:** `feat/tier2-features`
**Baseline:** 61 tests passing.

---

## Key Existing Patterns (read this before touching any code)

**Getting project context in a command** — copy this exactly, every command does this:
```python
config = load_project_config()
project_dir = Path.cwd()
driver = get_neo4j_driver(config)
domain_config = _get_domain_config(config)
database = config["neo4j"]["database"]
session_id = get_current_session(project_dir)  # may be None
```

**`_get_domain_config` helper** — copy this into every new command file:
```python
def _get_domain_config(config: dict):
    domain_name = config["project"].get("domain", "research")
    domain_yaml = Path(__file__).parent.parent / "domain" / f"{domain_name}.yaml"
    return load_domain_config(domain_yaml)
```

**Creating an artifact** — always this signature:
```python
artifact_id = create_artifact(
    project_dir=project_dir, driver=driver, database=database,
    domain_config=domain_config, artifact_type="Result",
    properties=props, actor="human", authority="accepted",
    session_id=session_id,
)
```

**Creating a link** — always this signature:
```python
create_link(
    project_dir=project_dir, driver=driver, database=database,
    domain_config=domain_config,
    from_id=from_id, to_id=to_id,
    from_type=from_type, to_type=to_type,
    rel_type="generated_by",
    actor="human", authority="accepted",
    session_id=session_id,
)
```

**State transition** — always fetch current state from Neo4j first:
```python
with driver.session(database=database) as session:
    node = get_artifact(session, artifact_id)
current_state = node["state"]
transition_state(
    project_dir=project_dir, driver=driver, database=database,
    domain_config=domain_config, artifact_id=artifact_id,
    artifact_type=node["artifact_type"], current_state=current_state,
    new_state="verified", actor="human", authority="accepted",
    session_id=session_id,
)
```

**Neo4j test file header** — every new Neo4j test file starts with:
```python
import pytest
from pathlib import Path
from seldon.domain.loader import load_domain_config

pytestmark = pytest.mark.usefixtures("neo4j_available")

NEO4J_DB = "seldon-test"
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"

@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)
```

**Database name rule:** Neo4j doesn't allow underscores in database names. Always use dashes. `seldon-test` not `seldon_test`. When creating databases via Cypher, backtick-quote: `` CREATE DATABASE `seldon-test` IF NOT EXISTS ``.

---

## File Map (complete picture of what changes)

```
seldon/
├── config.py                          MODIFY — add start_session, get_current_session, end_session
├── core/
│   ├── artifacts.py                   MODIFY — add session_id param to all 4 functions; hook staleness
│   └── staleness.py                   CREATE
├── commands/
│   ├── result.py                      CREATE
│   ├── task.py                        CREATE
│   └── session.py                     CREATE
├── cli.py                             MODIFY — register 3 new command groups + 2 top-level commands
└── domain/
    └── research.yaml                  MODIFY — add Result to implements.from_types
tests/
├── test_session_mgmt.py               CREATE — pure Python, no Neo4j
├── test_staleness.py                  CREATE — requires Neo4j
├── test_result.py                     CREATE — requires Neo4j
└── test_task.py                       CREATE — requires Neo4j
```

---

## Task 1: Session Management in `seldon/config.py`

**Goal:** Functions to start/read/end a session. No Neo4j. Pure Python.

**Files:**
- Modify: `seldon/config.py`
- Create: `tests/test_session_mgmt.py`

### Step 1.1 — Write failing tests

**File: `tests/test_session_mgmt.py`**

```python
"""
Session management tests. Pure Python — no Neo4j required.
"""
import json
import uuid
from pathlib import Path

import pytest

from seldon.config import start_session, get_current_session, get_current_session_data, end_session


def test_start_session_returns_valid_uuid(tmp_path):
    session_id = start_session(tmp_path)
    uuid.UUID(session_id)  # must be valid UUID


def test_start_session_creates_session_file(tmp_path):
    start_session(tmp_path)
    assert (tmp_path / ".seldon" / "current_session.json").exists()


def test_start_session_creates_seldon_dir(tmp_path):
    start_session(tmp_path)
    assert (tmp_path / ".seldon").is_dir()


def test_get_current_session_returns_session_id(tmp_path):
    session_id = start_session(tmp_path)
    assert get_current_session(tmp_path) == session_id


def test_get_current_session_none_when_no_session(tmp_path):
    assert get_current_session(tmp_path) is None


def test_get_current_session_data_has_started_at(tmp_path):
    start_session(tmp_path)
    data = get_current_session_data(tmp_path)
    assert "started_at" in data
    assert "session_id" in data


def test_end_session_clears_file(tmp_path):
    start_session(tmp_path)
    end_session(tmp_path)
    assert get_current_session(tmp_path) is None


def test_end_session_noop_when_no_session(tmp_path):
    end_session(tmp_path)  # must not raise


def test_start_session_overwrites_existing(tmp_path):
    id1 = start_session(tmp_path)
    id2 = start_session(tmp_path)
    assert id1 != id2
    assert get_current_session(tmp_path) == id2
```

### Step 1.2 — Run failing tests

```bash
cd /Users/brock/Documents/GitHub/seldon/.worktrees/tier2-features
python -m pytest tests/test_session_mgmt.py -v
```

Expected: `ImportError` — `start_session` not found.

### Step 1.3 — Add session functions to `seldon/config.py`

Add these imports at the top of `seldon/config.py` (after existing imports):
```python
import json
import uuid
from datetime import datetime, timezone
```

Add these functions at the bottom of `seldon/config.py`:

```python
def start_session(project_dir: Optional[Path] = None) -> str:
    """
    Generate a session UUID, write to .seldon/current_session.json, return session_id.
    Overwrites any existing session file.
    """
    base = Path(project_dir) if project_dir else Path.cwd()
    seldon_dir = base / ".seldon"
    seldon_dir.mkdir(exist_ok=True)
    session_id = str(uuid.uuid4())
    session_file = seldon_dir / "current_session.json"
    data = {
        "session_id": session_id,
        "started_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    with open(session_file, "w") as f:
        json.dump(data, f)
    return session_id


def get_current_session(project_dir: Optional[Path] = None) -> Optional[str]:
    """Return the active session_id, or None if no session file exists."""
    data = get_current_session_data(project_dir)
    return data["session_id"] if data else None


def get_current_session_data(project_dir: Optional[Path] = None) -> Optional[dict]:
    """Return full session dict (session_id, started_at), or None if no session."""
    base = Path(project_dir) if project_dir else Path.cwd()
    session_file = base / ".seldon" / "current_session.json"
    if not session_file.exists():
        return None
    with open(session_file) as f:
        return json.load(f)


def end_session(project_dir: Optional[Path] = None) -> None:
    """Delete the current session file. No-op if no session is active."""
    base = Path(project_dir) if project_dir else Path.cwd()
    session_file = base / ".seldon" / "current_session.json"
    if session_file.exists():
        session_file.unlink()
```

### Step 1.4 — Run tests

```bash
python -m pytest tests/test_session_mgmt.py -v
```

Expected: 9 tests pass.

### Step 1.5 — Run full suite to confirm nothing broke

```bash
python -m pytest tests/ -q
```

Expected: 70 passed (61 existing + 9 new).

### Step 1.6 — Commit

```bash
git add seldon/config.py tests/test_session_mgmt.py
git commit -m "feat: session management — start_session, get_current_session, end_session"
```

---

## Task 2: Thread `session_id` Through `seldon/core/artifacts.py`

**Goal:** Every artifact mutation (create, update, transition, link) accepts an optional `session_id` and passes it to `make_event`. No behavior change — purely additive.

**Files:**
- Modify: `seldon/core/artifacts.py`

**No new tests needed** — all 4 functions get `session_id: Optional[str] = None` added as a trailing kwarg. Existing tests still pass (no session_id = None = existing behavior).

### Step 2.1 — Update `seldon/core/artifacts.py`

Add `Optional` to the import at the top:
```python
from typing import Any, Dict, Optional
```

Then update each of the 4 function signatures and their `make_event` calls:

**`create_artifact`** — add `session_id: Optional[str] = None` as last param, pass to `make_event`:
```python
def create_artifact(
    project_dir: Path,
    driver: Driver,
    database: str,
    domain_config: DomainConfig,
    artifact_type: str,
    properties: Dict[str, Any],
    actor: str,
    authority: str,
    session_id: Optional[str] = None,
) -> str:
```
And in the body, change the `make_event` call to pass `session_id=session_id`.

**`update_artifact`** — same pattern:
```python
def update_artifact(
    project_dir: Path,
    driver: Driver,
    database: str,
    artifact_id: str,
    properties: Dict[str, Any],
    actor: str,
    authority: str,
    session_id: Optional[str] = None,
) -> None:
```

**`transition_state`** — same pattern:
```python
def transition_state(
    project_dir: Path,
    driver: Driver,
    database: str,
    domain_config: DomainConfig,
    artifact_id: str,
    artifact_type: str,
    current_state: str,
    new_state: str,
    actor: str,
    authority: str,
    session_id: Optional[str] = None,
) -> None:
```

**`create_link`** — same pattern:
```python
def create_link(
    project_dir: Path,
    driver: Driver,
    database: str,
    domain_config: DomainConfig,
    from_id: str,
    to_id: str,
    from_type: str,
    to_type: str,
    rel_type: str,
    actor: str,
    authority: str,
    session_id: Optional[str] = None,
) -> None:
```

### Step 2.2 — Verify full suite still passes

```bash
python -m pytest tests/ -q
```

Expected: 70 passed, 0 failed.

### Step 2.3 — Commit

```bash
git add seldon/core/artifacts.py
git commit -m "feat: thread session_id through all artifact mutation functions"
```

---

## Task 3: Staleness Propagation

**Goal:** When any artifact transitions to `stale`, automatically cascade the stale state to downstream artifacts that `CITES` it. New file `seldon/core/staleness.py`. Hook into `transition_state`.

Also update `research.yaml` to allow `Result → implements → SRS_Requirement` (needed for Task 4's `--requirement-id` flag).

**Files:**
- Create: `seldon/core/staleness.py`
- Modify: `seldon/core/artifacts.py` (add staleness hook at end of `transition_state`)
- Modify: `seldon/domain/research.yaml` (add Result to implements.from_types)
- Create: `tests/test_staleness.py`

### Step 3.1 — Write failing tests

**File: `tests/test_staleness.py`**

```python
"""
Staleness propagation tests. Requires Neo4j.
"""
import pytest
from pathlib import Path
from seldon.domain.loader import load_domain_config
from seldon.core.artifacts import create_artifact, create_link, transition_state
from seldon.core.graph import get_artifact
from seldon.core.staleness import propagate_staleness

pytestmark = pytest.mark.usefixtures("neo4j_available")

NEO4J_DB = "seldon-test"
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


def _make_result(project_dir, neo4j_driver, domain_config):
    return create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Result",
        properties={}, actor="human", authority="accepted",
    )


def _make_section(project_dir, neo4j_driver, domain_config):
    return create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="PaperSection",
        properties={}, actor="human", authority="accepted",
    )


def test_propagate_staleness_marks_citing_draft_section(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    result_id = _make_result(project_dir, neo4j_driver, domain_config)
    section_id = _make_section(project_dir, neo4j_driver, domain_config)

    # Advance section to draft
    transition_state(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=section_id,
        artifact_type="PaperSection", current_state="proposed", new_state="draft",
        actor="human", authority="accepted",
    )

    # Link section -[cites]-> result
    create_link(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config,
        from_id=section_id, to_id=result_id,
        from_type="PaperSection", to_type="Result",
        rel_type="cites", actor="human", authority="accepted",
    )

    affected = propagate_staleness(
        driver=neo4j_driver, database=NEO4J_DB,
        project_dir=project_dir, domain_config=domain_config,
        artifact_id=result_id,
    )

    assert section_id in affected

    with neo4j_driver.session(database=NEO4J_DB) as session:
        node = get_artifact(session, section_id)
    assert node["state"] == "stale"


def test_propagate_staleness_returns_affected_ids(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    result_id = _make_result(project_dir, neo4j_driver, domain_config)
    section1 = _make_section(project_dir, neo4j_driver, domain_config)
    section2 = _make_section(project_dir, neo4j_driver, domain_config)

    for s in [section1, section2]:
        transition_state(
            project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config, artifact_id=s,
            artifact_type="PaperSection", current_state="proposed", new_state="draft",
            actor="human", authority="accepted",
        )
        create_link(
            project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config,
            from_id=s, to_id=result_id,
            from_type="PaperSection", to_type="Result",
            rel_type="cites", actor="human", authority="accepted",
        )

    affected = propagate_staleness(
        driver=neo4j_driver, database=NEO4J_DB,
        project_dir=project_dir, domain_config=domain_config,
        artifact_id=result_id,
    )

    assert section1 in affected
    assert section2 in affected
    assert len(affected) == 2


def test_propagate_staleness_skips_non_citing_artifacts(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    result_id = _make_result(project_dir, neo4j_driver, domain_config)
    # Another result — not linked
    other_id = _make_result(project_dir, neo4j_driver, domain_config)

    affected = propagate_staleness(
        driver=neo4j_driver, database=NEO4J_DB,
        project_dir=project_dir, domain_config=domain_config,
        artifact_id=result_id,
    )

    assert other_id not in affected
    assert len(affected) == 0


def test_propagate_staleness_skips_proposed_section(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """PaperSection in 'proposed' state cannot go stale — skip it."""
    result_id = _make_result(project_dir, neo4j_driver, domain_config)
    section_id = _make_section(project_dir, neo4j_driver, domain_config)
    # section is in 'proposed' — state machine has no proposed→stale transition

    create_link(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config,
        from_id=section_id, to_id=result_id,
        from_type="PaperSection", to_type="Result",
        rel_type="cites", actor="human", authority="accepted",
    )

    affected = propagate_staleness(
        driver=neo4j_driver, database=NEO4J_DB,
        project_dir=project_dir, domain_config=domain_config,
        artifact_id=result_id,
    )

    # PaperSection can't go stale from proposed, so it should not be affected
    assert section_id not in affected

    with neo4j_driver.session(database=NEO4J_DB) as session:
        node = get_artifact(session, section_id)
    assert node["state"] == "proposed"


def test_transition_to_stale_auto_propagates(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """Transitioning a Result to stale should auto-propagate to citing sections."""
    result_id = _make_result(project_dir, neo4j_driver, domain_config)
    section_id = _make_section(project_dir, neo4j_driver, domain_config)

    transition_state(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=section_id,
        artifact_type="PaperSection", current_state="proposed", new_state="draft",
        actor="human", authority="accepted",
    )
    create_link(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config,
        from_id=section_id, to_id=result_id,
        from_type="PaperSection", to_type="Result",
        rel_type="cites", actor="human", authority="accepted",
    )

    # proposed → verified → stale
    transition_state(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=result_id,
        artifact_type="Result", current_state="proposed", new_state="verified",
        actor="human", authority="accepted",
    )
    transition_state(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=result_id,
        artifact_type="Result", current_state="verified", new_state="stale",
        actor="human", authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        node = get_artifact(session, section_id)
    assert node["state"] == "stale"
```

### Step 3.2 — Run failing tests

```bash
python -m pytest tests/test_staleness.py -v
```

Expected: `ImportError` — `seldon.core.staleness` not found.

### Step 3.3 — Update `research.yaml`

In `seldon/domain/research.yaml`, change:
```yaml
  implements:
    from_types: [Script]
    to_types: [SRS_Requirement]
```
to:
```yaml
  implements:
    from_types: [Script, Result]
    to_types: [SRS_Requirement]
```

### Step 3.4 — Create `seldon/core/staleness.py`

```python
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from neo4j import Driver

from seldon.core.state import InvalidStateTransition
from seldon.domain.loader import DomainConfig


def propagate_staleness(
    driver: Driver,
    database: str,
    project_dir: Path,
    domain_config: DomainConfig,
    artifact_id: str,
    actor: str = "system",
    session_id: Optional[str] = None,
) -> List[str]:
    """
    Find all downstream artifacts that CITES the given artifact.
    Transition each to 'stale' if the state machine permits it.

    Returns list of affected artifact_ids.

    Called automatically by artifacts.transition_state when new_state == 'stale'.
    Validation is best-effort: artifacts whose state machine does not permit
    a transition to 'stale' are silently skipped.
    """
    # Lazy import to avoid circular dependency (staleness → artifacts → staleness)
    from seldon.core.artifacts import transition_state
    from seldon.core.state import validate_transition

    with driver.session(database=database) as session:
        records = session.run(
            "MATCH (downstream:Artifact)-[:CITES]->(target:Artifact {artifact_id: $id}) "
            "RETURN downstream",
            id=artifact_id,
        ).data()

    affected: List[str] = []

    for r in records:
        downstream: Dict[str, Any] = dict(r["downstream"])
        ds_id = downstream["artifact_id"]
        ds_type = downstream.get("artifact_type", "")
        ds_state = downstream.get("state", "")

        # Skip if this type/state cannot transition to stale
        try:
            validate_transition(domain_config, ds_type, ds_state, "stale")
        except (InvalidStateTransition, ValueError):
            continue

        transition_state(
            project_dir=project_dir,
            driver=driver,
            database=database,
            domain_config=domain_config,
            artifact_id=ds_id,
            artifact_type=ds_type,
            current_state=ds_state,
            new_state="stale",
            actor=actor,
            authority="accepted",
            session_id=session_id,
        )
        affected.append(ds_id)

    return affected
```

### Step 3.5 — Hook staleness into `seldon/core/artifacts.py`

Add this at the very end of the `transition_state` function body (after the Neo4j write):

```python
    # Auto-propagate staleness downstream when an artifact goes stale
    if new_state == "stale":
        from seldon.core.staleness import propagate_staleness
        propagate_staleness(
            driver=driver,
            database=database,
            project_dir=project_dir,
            domain_config=domain_config,
            artifact_id=artifact_id,
            actor=actor,
            session_id=session_id,
        )
```

### Step 3.6 — Run tests

```bash
python -m pytest tests/test_staleness.py -v
```

Expected: 5 tests pass (or skip if Neo4j offline).

### Step 3.7 — Run full suite

```bash
python -m pytest tests/ -q
```

Expected: 75 passed (or 36 passed + 39 skipped if Neo4j offline).

### Step 3.8 — Commit

```bash
git add seldon/core/staleness.py seldon/core/artifacts.py seldon/domain/research.yaml tests/test_staleness.py
git commit -m "feat: staleness propagation — cascade stale state to citing artifacts"
```

---

## Task 4: Result Commands

**Goal:** `seldon result register|verify|list|trace|check-stale`

**Files:**
- Create: `seldon/commands/result.py`
- Create: `tests/test_result.py`

### Step 4.1 — Write failing tests

**File: `tests/test_result.py`**

```python
"""
Result registry tests. Requires Neo4j.
"""
import pytest
from pathlib import Path
from seldon.domain.loader import load_domain_config
from seldon.core.artifacts import create_artifact, create_link, transition_state
from seldon.core.graph import get_artifact
from seldon.core.events import read_events

pytestmark = pytest.mark.usefixtures("neo4j_available")

NEO4J_DB = "seldon-test"
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


def _make_result(project_dir, driver, domain_config, **props):
    return create_artifact(
        project_dir=project_dir, driver=driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Result",
        properties=props, actor="human", authority="accepted",
    )


def _make_script(project_dir, driver, domain_config):
    return create_artifact(
        project_dir=project_dir, driver=driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Script",
        properties={}, actor="human", authority="accepted",
    )


def _make_datafile(project_dir, driver, domain_config):
    return create_artifact(
        project_dir=project_dir, driver=driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="DataFile",
        properties={}, actor="human", authority="accepted",
    )


# ── register ──────────────────────────────────────────────────────────────────

def test_register_result_creates_node(neo4j_driver, project_dir, domain_config, clean_test_db):
    result_id = _make_result(project_dir, neo4j_driver, domain_config,
                             value=0.912, units="accuracy", description="test result")
    with neo4j_driver.session(database=NEO4J_DB) as session:
        node = get_artifact(session, result_id)
    assert node is not None
    assert node["value"] == 0.912
    assert node["units"] == "accuracy"
    assert node["state"] == "proposed"


def test_register_result_writes_event(neo4j_driver, project_dir, domain_config, clean_test_db):
    _make_result(project_dir, neo4j_driver, domain_config, value=0.5)
    events = read_events(project_dir)
    assert len(events) == 1
    assert events[0]["event_type"] == "artifact_created"


def test_register_with_script_id_creates_generated_by_link(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    result_id = _make_result(project_dir, neo4j_driver, domain_config, value=0.8)
    script_id = _make_script(project_dir, neo4j_driver, domain_config)

    create_link(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config,
        from_id=result_id, to_id=script_id,
        from_type="Result", to_type="Script",
        rel_type="generated_by", actor="human", authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        rel = session.run(
            "MATCH (r:Result {artifact_id: $rid})-[:GENERATED_BY]->(s:Script {artifact_id: $sid}) RETURN r",
            rid=result_id, sid=script_id,
        ).single()
    assert rel is not None


def test_register_with_data_ids_creates_computed_from_links(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    result_id = _make_result(project_dir, neo4j_driver, domain_config, value=0.7)
    data1 = _make_datafile(project_dir, neo4j_driver, domain_config)
    data2 = _make_datafile(project_dir, neo4j_driver, domain_config)

    for data_id in [data1, data2]:
        create_link(
            project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config,
            from_id=result_id, to_id=data_id,
            from_type="Result", to_type="DataFile",
            rel_type="computed_from", actor="human", authority="accepted",
        )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        rels = session.run(
            "MATCH (r:Result {artifact_id: $id})-[:COMPUTED_FROM]->(d:DataFile) RETURN d",
            id=result_id,
        ).data()
    assert len(rels) == 2


# ── verify ────────────────────────────────────────────────────────────────────

def test_verify_result_transitions_to_verified(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    result_id = _make_result(project_dir, neo4j_driver, domain_config, value=0.9)

    transition_state(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=result_id,
        artifact_type="Result", current_state="proposed", new_state="verified",
        actor="human", authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        node = get_artifact(session, result_id)
    assert node["state"] == "verified"


def test_verify_result_writes_state_changed_event(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    result_id = _make_result(project_dir, neo4j_driver, domain_config, value=0.9)
    transition_state(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=result_id,
        artifact_type="Result", current_state="proposed", new_state="verified",
        actor="human", authority="accepted",
    )
    events = read_events(project_dir)
    state_events = [e for e in events if e["event_type"] == "artifact_state_changed"]
    assert len(state_events) == 1
    assert state_events[0]["payload"]["to_state"] == "verified"


# ── list ──────────────────────────────────────────────────────────────────────

def test_list_results_by_state(neo4j_driver, project_dir, domain_config, clean_test_db):
    result1 = _make_result(project_dir, neo4j_driver, domain_config, value=0.1)
    result2 = _make_result(project_dir, neo4j_driver, domain_config, value=0.2)

    transition_state(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=result1,
        artifact_type="Result", current_state="proposed", new_state="verified",
        actor="human", authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        from seldon.core.graph import get_artifacts_by_state
        proposed = get_artifacts_by_state(session, "proposed")
        verified = get_artifacts_by_state(session, "verified")

    assert len(proposed) == 1
    assert len(verified) == 1


# ── trace ─────────────────────────────────────────────────────────────────────

def test_trace_result_returns_provenance_chain(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    result_id = _make_result(project_dir, neo4j_driver, domain_config, value=0.9)
    script_id = _make_script(project_dir, neo4j_driver, domain_config)
    data_id = _make_datafile(project_dir, neo4j_driver, domain_config)

    create_link(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config,
        from_id=result_id, to_id=script_id,
        from_type="Result", to_type="Script",
        rel_type="generated_by", actor="human", authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        from seldon.core.graph import get_provenance_chain
        chain = get_provenance_chain(session, result_id)

    chain_ids = {a["artifact_id"] for a in chain}
    assert script_id in chain_ids


# ── check-stale ───────────────────────────────────────────────────────────────

def test_check_stale_identifies_stale_results(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    result_id = _make_result(project_dir, neo4j_driver, domain_config, value=0.9)
    # proposed → verified → stale
    transition_state(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=result_id,
        artifact_type="Result", current_state="proposed", new_state="verified",
        actor="human", authority="accepted",
    )
    transition_state(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=result_id,
        artifact_type="Result", current_state="verified", new_state="stale",
        actor="human", authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        from seldon.core.graph import get_stale_artifacts
        stale = get_stale_artifacts(session)

    assert any(a["artifact_id"] == result_id for a in stale)
```

### Step 4.2 — Run failing tests

```bash
python -m pytest tests/test_result.py -v
```

Expected: skip if Neo4j offline, or run and pass (these tests use the existing `artifacts` layer directly — no new code needed to pass them). If they all pass, that's fine — the test file validates the behavior the CLI commands will expose.

### Step 4.3 — Create `seldon/commands/result.py`

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import click

from seldon.config import load_project_config, get_neo4j_driver, get_current_session
from seldon.core.artifacts import create_artifact, create_link, transition_state
from seldon.core.graph import get_artifact, get_artifacts_by_type, get_artifacts_by_state, get_provenance_chain, get_stale_artifacts, get_dependents
from seldon.domain.loader import load_domain_config


def _get_domain_config(config: dict):
    domain_name = config["project"].get("domain", "research")
    domain_yaml = Path(__file__).parent.parent / "domain" / f"{domain_name}.yaml"
    return load_domain_config(domain_yaml)


@click.group("result")
def result_group():
    """Manage Result artifacts — register, verify, trace provenance."""
    pass


@result_group.command("register")
@click.option("--value", required=True, type=float, help="Numeric result value")
@click.option("--units", default="", help="Units of measurement (e.g. 'accuracy', 'ms')")
@click.option("--description", default="", help="Human-readable description")
@click.option("--script-id", default=None, help="UUID of Script that generated this result")
@click.option("--data-ids", default=None, help="Comma-separated UUIDs of DataFile inputs")
@click.option("--requirement-id", default=None, help="UUID of SRS_Requirement this implements")
@click.option("--input-hash", default=None, help="SHA256 hash of input data")
def result_register(value, units, description, script_id, data_ids, requirement_id, input_hash):
    """Register a new Result artifact with optional provenance links."""
    config = load_project_config()
    project_dir = Path.cwd()
    driver = get_neo4j_driver(config)
    domain_config = _get_domain_config(config)
    database = config["neo4j"]["database"]
    session_id = get_current_session(project_dir)

    props = {
        "value": value,
        "run_timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if units:
        props["units"] = units
    if description:
        props["description"] = description
    if input_hash:
        props["input_data_hash"] = input_hash

    try:
        result_id = create_artifact(
            project_dir=project_dir, driver=driver, database=database,
            domain_config=domain_config, artifact_type="Result",
            properties=props, actor="human", authority="accepted",
            session_id=session_id,
        )

        links_created = []

        if script_id:
            create_link(
                project_dir=project_dir, driver=driver, database=database,
                domain_config=domain_config,
                from_id=result_id, to_id=script_id,
                from_type="Result", to_type="Script",
                rel_type="generated_by", actor="human", authority="accepted",
                session_id=session_id,
            )
            links_created.append(f"GENERATED_BY {script_id[:8]}...")

        if data_ids:
            for data_id in data_ids.split(","):
                data_id = data_id.strip()
                if data_id:
                    create_link(
                        project_dir=project_dir, driver=driver, database=database,
                        domain_config=domain_config,
                        from_id=result_id, to_id=data_id,
                        from_type="Result", to_type="DataFile",
                        rel_type="computed_from", actor="human", authority="accepted",
                        session_id=session_id,
                    )
                    links_created.append(f"COMPUTED_FROM {data_id[:8]}...")

        if requirement_id:
            create_link(
                project_dir=project_dir, driver=driver, database=database,
                domain_config=domain_config,
                from_id=result_id, to_id=requirement_id,
                from_type="Result", to_type="SRS_Requirement",
                rel_type="implements", actor="human", authority="accepted",
                session_id=session_id,
            )
            links_created.append(f"IMPLEMENTS {requirement_id[:8]}...")

        click.echo(f"Registered Result: {result_id}")
        click.echo(f"  value: {value} {units}")
        click.echo(f"  state: proposed")
        if links_created:
            click.echo(f"  links: {', '.join(links_created)}")

    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
    finally:
        driver.close()


@result_group.command("verify")
@click.argument("result_id")
def result_verify(result_id):
    """Mark a Result as verified (proposed → verified)."""
    config = load_project_config()
    project_dir = Path.cwd()
    driver = get_neo4j_driver(config)
    domain_config = _get_domain_config(config)
    database = config["neo4j"]["database"]
    session_id = get_current_session(project_dir)

    with driver.session(database=database) as session:
        node = get_artifact(session, result_id)

    if node is None:
        click.echo(f"Error: Result '{result_id}' not found", err=True)
        driver.close()
        raise SystemExit(1)

    try:
        transition_state(
            project_dir=project_dir, driver=driver, database=database,
            domain_config=domain_config, artifact_id=result_id,
            artifact_type="Result", current_state=node["state"], new_state="verified",
            actor="human", authority="accepted",
            session_id=session_id,
        )
        value = node.get("value", "?")
        units = node.get("units", "")
        click.echo(f"Verified Result: {result_id}")
        click.echo(f"  value: {value} {units}")
        click.echo(f"  state: proposed → verified")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
    finally:
        driver.close()


@result_group.command("list")
@click.option("--state", default=None, help="Filter by state (proposed/verified/published/stale)")
def result_list(state):
    """List Result artifacts."""
    config = load_project_config()
    driver = get_neo4j_driver(config)
    database = config["neo4j"]["database"]

    with driver.session(database=database) as session:
        if state:
            records = session.run(
                "MATCH (r:Result {state: $state}) RETURN r ORDER BY r.run_timestamp DESC",
                state=state,
            ).data()
        else:
            records = session.run(
                "MATCH (r:Result) RETURN r ORDER BY r.run_timestamp DESC"
            ).data()
        results = [dict(r["r"]) for r in records]

        # Check provenance for each result
        for r in results:
            script_rel = session.run(
                "MATCH (r:Result {artifact_id: $id})-[:GENERATED_BY]->(:Script) RETURN r LIMIT 1",
                id=r["artifact_id"],
            ).single()
            r["has_script"] = script_rel is not None
            data_rel = session.run(
                "MATCH (r:Result {artifact_id: $id})-[:COMPUTED_FROM]->(:DataFile) RETURN r LIMIT 1",
                id=r["artifact_id"],
            ).single()
            r["has_data"] = data_rel is not None

    driver.close()

    if not results:
        click.echo("No results found.")
        return

    click.echo(f"{'ID':10} {'VALUE':10} {'UNITS':12} {'STATE':12} {'SCRIPT':7} {'DATA':5} DESCRIPTION")
    click.echo("-" * 80)
    for r in results:
        rid = r.get("artifact_id", "?")[:8]
        val = str(r.get("value", "?"))[:9]
        units = (r.get("units") or "")[:11]
        st = (r.get("state") or "?")[:11]
        has_s = "yes" if r.get("has_script") else "no"
        has_d = "yes" if r.get("has_data") else "no"
        desc = (r.get("description") or "")[:30]
        click.echo(f"{rid:<10} {val:<10} {units:<12} {st:<12} {has_s:<7} {has_d:<5} {desc}")


@result_group.command("trace")
@click.argument("result_id")
def result_trace(result_id):
    """Show full provenance chain for a Result (upstream + downstream citations)."""
    config = load_project_config()
    driver = get_neo4j_driver(config)
    database = config["neo4j"]["database"]

    with driver.session(database=database) as session:
        node = get_artifact(session, result_id)
        if node is None:
            click.echo(f"Error: Result '{result_id}' not found", err=True)
            driver.close()
            raise SystemExit(1)

        upstream = get_provenance_chain(session, result_id)
        downstream = session.run(
            "MATCH (s:PaperSection)-[:CITES]->(r:Result {artifact_id: $id}) RETURN s",
            id=result_id,
        ).data()
        cited_by = [dict(r["s"]) for r in downstream]

    driver.close()

    val = node.get("value", "?")
    units = node.get("units", "")
    click.echo(f"\nResult: {result_id}")
    click.echo(f"  value: {val} {units}  state: {node.get('state', '?')}")

    if upstream:
        click.echo(f"\nProvenance (upstream):")
        for a in upstream:
            atype = a.get("artifact_type", "?")
            aid = a.get("artifact_id", "?")[:8]
            astate = a.get("state", "?")
            click.echo(f"  ← [{atype}] {aid}... ({astate})")
    else:
        click.echo("\nProvenance: none (no upstream links)")

    if cited_by:
        click.echo(f"\nCited by ({len(cited_by)} sections):")
        for s in cited_by:
            sid = s.get("artifact_id", "?")[:8]
            sstate = s.get("state", "?")
            click.echo(f"  → [PaperSection] {sid}... ({sstate})")
    else:
        click.echo("\nCited by: no sections")


@result_group.command("check-stale")
def result_check_stale():
    """List stale Results and what downstream artifacts they block."""
    config = load_project_config()
    driver = get_neo4j_driver(config)
    database = config["neo4j"]["database"]

    with driver.session(database=database) as session:
        stale = get_stale_artifacts(session)

        if not stale:
            click.echo("No stale results.")
            driver.close()
            return

        click.echo(f"Stale Results ({len(stale)}):\n")
        for r in stale:
            rid = r.get("artifact_id", "?")
            val = r.get("value", "?")
            units = r.get("units", "")
            click.echo(f"  ⚠ {rid[:8]}...  value={val} {units}")

            dependents = get_dependents(session, rid)
            if dependents:
                for d in dependents:
                    dtype = d.get("artifact_type", "?")
                    did = d.get("artifact_id", "?")[:8]
                    dstate = d.get("state", "?")
                    click.echo(f"      blocks: [{dtype}] {did}... ({dstate})")

    driver.close()
```

### Step 4.4 — Run tests

```bash
python -m pytest tests/test_result.py -v
python -m pytest tests/ -q
```

Expected: All result tests pass (or skip if no Neo4j). Full suite: 84 passed (or 36 passed + 48 skipped).

### Step 4.5 — Commit

```bash
git add seldon/commands/result.py tests/test_result.py seldon/domain/research.yaml
git commit -m "feat: result commands (register, verify, list, trace, check-stale)"
```

---

## Task 5: Task Commands

**Goal:** `seldon task create|list|update|show`

**Files:**
- Create: `seldon/commands/task.py`
- Create: `tests/test_task.py`

### Step 5.1 — Write failing tests

**File: `tests/test_task.py`**

```python
"""
Task tracking tests. Requires Neo4j.
"""
import pytest
from pathlib import Path
from seldon.domain.loader import load_domain_config
from seldon.core.artifacts import create_artifact, create_link, transition_state
from seldon.core.graph import get_artifact
from seldon.core.state import InvalidStateTransition

pytestmark = pytest.mark.usefixtures("neo4j_available")

NEO4J_DB = "seldon-test"
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


def _make_task(project_dir, driver, domain_config, description="Test task"):
    return create_artifact(
        project_dir=project_dir, driver=driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="ResearchTask",
        properties={"description": description}, actor="human", authority="accepted",
    )


def _make_result(project_dir, driver, domain_config):
    return create_artifact(
        project_dir=project_dir, driver=driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Result",
        properties={}, actor="human", authority="accepted",
    )


# ── create ────────────────────────────────────────────────────────────────────

def test_create_task_has_proposed_state(neo4j_driver, project_dir, domain_config, clean_test_db):
    task_id = _make_task(project_dir, neo4j_driver, domain_config)
    with neo4j_driver.session(database=NEO4J_DB) as session:
        node = get_artifact(session, task_id)
    assert node["state"] == "proposed"
    assert node["description"] == "Test task"


def test_create_task_with_blocks_creates_relationship(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    task_id = _make_task(project_dir, neo4j_driver, domain_config)
    result_id = _make_result(project_dir, neo4j_driver, domain_config)

    create_link(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config,
        from_id=task_id, to_id=result_id,
        from_type="ResearchTask", to_type="Result",
        rel_type="blocks", actor="human", authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        rel = session.run(
            "MATCH (t:ResearchTask {artifact_id: $tid})-[:BLOCKS]->(r:Result {artifact_id: $rid}) RETURN r",
            tid=task_id, rid=result_id,
        ).single()
    assert rel is not None


# ── list ──────────────────────────────────────────────────────────────────────

def test_list_open_tasks_excludes_completed(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    open_id = _make_task(project_dir, neo4j_driver, domain_config, "open task")
    done_id = _make_task(project_dir, neo4j_driver, domain_config, "done task")

    # advance done_id: proposed → accepted → in_progress → completed
    for from_s, to_s in [("proposed", "accepted"), ("accepted", "in_progress"), ("in_progress", "completed")]:
        transition_state(
            project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config, artifact_id=done_id,
            artifact_type="ResearchTask", current_state=from_s, new_state=to_s,
            actor="human", authority="accepted",
        )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        open_tasks = session.run(
            "MATCH (t:ResearchTask) WHERE t.state IN ['proposed','accepted','in_progress','blocked'] RETURN t"
        ).data()

    open_ids = {dict(r["t"])["artifact_id"] for r in open_tasks}
    assert open_id in open_ids
    assert done_id not in open_ids


# ── update ────────────────────────────────────────────────────────────────────

def test_update_task_state_valid_transition(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    task_id = _make_task(project_dir, neo4j_driver, domain_config)

    transition_state(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=task_id,
        artifact_type="ResearchTask", current_state="proposed", new_state="accepted",
        actor="human", authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        node = get_artifact(session, task_id)
    assert node["state"] == "accepted"


def test_update_task_state_invalid_raises(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    task_id = _make_task(project_dir, neo4j_driver, domain_config)

    with pytest.raises(InvalidStateTransition):
        transition_state(
            project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config, artifact_id=task_id,
            artifact_type="ResearchTask", current_state="proposed", new_state="completed",
            actor="human", authority="accepted",
        )


# ── show ──────────────────────────────────────────────────────────────────────

def test_show_task_with_blocks(neo4j_driver, project_dir, domain_config, clean_test_db):
    task_id = _make_task(project_dir, neo4j_driver, domain_config)
    result_id = _make_result(project_dir, neo4j_driver, domain_config)

    create_link(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config,
        from_id=task_id, to_id=result_id,
        from_type="ResearchTask", to_type="Result",
        rel_type="blocks", actor="human", authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        task_node = get_artifact(session, task_id)
        blocked_targets = session.run(
            "MATCH (t:ResearchTask {artifact_id: $id})-[:BLOCKS]->(target) RETURN target",
            id=task_id,
        ).data()

    assert task_node is not None
    assert len(blocked_targets) == 1
    assert dict(blocked_targets[0]["target"])["artifact_id"] == result_id
```

### Step 5.2 — Run failing tests

```bash
python -m pytest tests/test_task.py -v
```

Expected: All pass (or skip if no Neo4j). These test the existing `artifacts` layer directly.

### Step 5.3 — Create `seldon/commands/task.py`

```python
from __future__ import annotations

from pathlib import Path

import click

from seldon.config import load_project_config, get_neo4j_driver, get_current_session
from seldon.core.artifacts import create_artifact, create_link, transition_state
from seldon.core.graph import get_artifact
from seldon.domain.loader import load_domain_config


def _get_domain_config(config: dict):
    domain_name = config["project"].get("domain", "research")
    domain_yaml = Path(__file__).parent.parent / "domain" / f"{domain_name}.yaml"
    return load_domain_config(domain_yaml)


@click.group("task")
def task_group():
    """Manage ResearchTask artifacts — create, track, and update research action items."""
    pass


@task_group.command("create")
@click.option("--description", required=True, help="What needs to be done")
@click.option("--blocks", default=None, help="Comma-separated artifact UUIDs this task blocks")
@click.option("--depends-on", "depends_on", default=None, help="Comma-separated artifact UUIDs this task depends on")
def task_create(description, blocks, depends_on):
    """Create a new ResearchTask."""
    config = load_project_config()
    project_dir = Path.cwd()
    driver = get_neo4j_driver(config)
    domain_config = _get_domain_config(config)
    database = config["neo4j"]["database"]
    session_id = get_current_session(project_dir)

    try:
        task_id = create_artifact(
            project_dir=project_dir, driver=driver, database=database,
            domain_config=domain_config, artifact_type="ResearchTask",
            properties={"description": description},
            actor="human", authority="accepted",
            session_id=session_id,
        )

        links_created = []

        if blocks:
            for target_id in blocks.split(","):
                target_id = target_id.strip()
                if not target_id:
                    continue
                with driver.session(database=database) as session:
                    target_node = get_artifact(session, target_id)
                if target_node is None:
                    click.echo(f"Warning: artifact '{target_id}' not found — skipping BLOCKS link", err=True)
                    continue
                create_link(
                    project_dir=project_dir, driver=driver, database=database,
                    domain_config=domain_config,
                    from_id=task_id, to_id=target_id,
                    from_type="ResearchTask", to_type=target_node["artifact_type"],
                    rel_type="blocks", actor="human", authority="accepted",
                    session_id=session_id,
                )
                links_created.append(f"BLOCKS {target_id[:8]}...")

        if depends_on:
            for dep_id in depends_on.split(","):
                dep_id = dep_id.strip()
                if not dep_id:
                    continue
                with driver.session(database=database) as session:
                    dep_node = get_artifact(session, dep_id)
                if dep_node is None:
                    click.echo(f"Warning: artifact '{dep_id}' not found — skipping DEPENDS_ON link", err=True)
                    continue
                create_link(
                    project_dir=project_dir, driver=driver, database=database,
                    domain_config=domain_config,
                    from_id=task_id, to_id=dep_id,
                    from_type="ResearchTask", to_type=dep_node["artifact_type"],
                    rel_type="depends_on", actor="human", authority="accepted",
                    session_id=session_id,
                )
                links_created.append(f"DEPENDS_ON {dep_id[:8]}...")

        click.echo(f"Created ResearchTask: {task_id}")
        click.echo(f"  description: {description}")
        click.echo(f"  state: proposed")
        if links_created:
            click.echo(f"  links: {', '.join(links_created)}")

    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
    finally:
        driver.close()


@task_group.command("list")
@click.option("--state", default=None, help="Filter by specific state")
@click.option("--open", "open_only", is_flag=True, help="Show only open tasks (proposed/accepted/in_progress/blocked)")
def task_list(state, open_only):
    """List ResearchTask artifacts."""
    config = load_project_config()
    driver = get_neo4j_driver(config)
    database = config["neo4j"]["database"]

    OPEN_STATES = ["proposed", "accepted", "in_progress", "blocked"]

    with driver.session(database=database) as session:
        if open_only:
            records = session.run(
                "MATCH (t:ResearchTask) WHERE t.state IN $states RETURN t ORDER BY t.created_at",
                states=OPEN_STATES,
            ).data()
        elif state:
            records = session.run(
                "MATCH (t:ResearchTask {state: $state}) RETURN t ORDER BY t.created_at",
                state=state,
            ).data()
        else:
            records = session.run(
                "MATCH (t:ResearchTask) RETURN t ORDER BY t.created_at"
            ).data()
        tasks = [dict(r["t"]) for r in records]

        # Count blocks and depends_on for each
        for t in tasks:
            tid = t["artifact_id"]
            b_count = session.run(
                "MATCH (t:ResearchTask {artifact_id: $id})-[:BLOCKS]->(x) RETURN count(x) AS c",
                id=tid,
            ).single()["c"]
            d_count = session.run(
                "MATCH (t:ResearchTask {artifact_id: $id})-[:DEPENDS_ON]->(x) RETURN count(x) AS c",
                id=tid,
            ).single()["c"]
            t["blocks_count"] = b_count
            t["depends_count"] = d_count

    driver.close()

    if not tasks:
        click.echo("No tasks found.")
        return

    click.echo(f"{'ID':10} {'STATE':14} {'BLOCKS':7} {'DEPS':5} DESCRIPTION")
    click.echo("-" * 80)
    for t in tasks:
        tid = t.get("artifact_id", "?")[:8]
        st = (t.get("state") or "?")[:13]
        bc = t.get("blocks_count", 0)
        dc = t.get("depends_count", 0)
        desc = (t.get("description") or "")[:40]
        click.echo(f"{tid:<10} {st:<14} {bc:<7} {dc:<5} {desc}")


@task_group.command("update")
@click.argument("task_id")
@click.option("--state", required=True, help="New state to transition to")
def task_update(task_id, state):
    """Transition a ResearchTask to a new state."""
    config = load_project_config()
    project_dir = Path.cwd()
    driver = get_neo4j_driver(config)
    domain_config = _get_domain_config(config)
    database = config["neo4j"]["database"]
    session_id = get_current_session(project_dir)

    with driver.session(database=database) as session:
        node = get_artifact(session, task_id)

    if node is None:
        click.echo(f"Error: Task '{task_id}' not found", err=True)
        driver.close()
        raise SystemExit(1)

    old_state = node["state"]

    try:
        transition_state(
            project_dir=project_dir, driver=driver, database=database,
            domain_config=domain_config, artifact_id=task_id,
            artifact_type="ResearchTask", current_state=old_state, new_state=state,
            actor="human", authority="accepted",
            session_id=session_id,
        )
        click.echo(f"Updated Task: {task_id[:8]}...")
        click.echo(f"  state: {old_state} → {state}")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
    finally:
        driver.close()


@task_group.command("show")
@click.argument("task_id")
def task_show(task_id):
    """Show full detail for a ResearchTask including blocks and depends_on."""
    config = load_project_config()
    driver = get_neo4j_driver(config)
    database = config["neo4j"]["database"]

    with driver.session(database=database) as session:
        node = get_artifact(session, task_id)
        if node is None:
            click.echo(f"Error: Task '{task_id}' not found", err=True)
            driver.close()
            raise SystemExit(1)

        blocked_records = session.run(
            "MATCH (t:ResearchTask {artifact_id: $id})-[:BLOCKS]->(target) RETURN target",
            id=task_id,
        ).data()
        blocked = [dict(r["target"]) for r in blocked_records]

        dep_records = session.run(
            "MATCH (t:ResearchTask {artifact_id: $id})-[:DEPENDS_ON]->(dep) RETURN dep",
            id=task_id,
        ).data()
        deps = [dict(r["dep"]) for r in dep_records]

    driver.close()

    click.echo(f"\nTask: {task_id}")
    click.echo(f"  description: {node.get('description', '(none)')}")
    click.echo(f"  state:       {node.get('state', '?')}")
    click.echo(f"  created_at:  {node.get('created_at', '?')}")

    if blocked:
        click.echo(f"\n  Blocks ({len(blocked)}):")
        for b in blocked:
            btype = b.get("artifact_type", "?")
            bid = b.get("artifact_id", "?")[:8]
            bstate = b.get("state", "?")
            click.echo(f"    → [{btype}] {bid}... ({bstate})")
    else:
        click.echo(f"\n  Blocks: none")

    if deps:
        click.echo(f"\n  Depends on ({len(deps)}):")
        for d in deps:
            dtype = d.get("artifact_type", "?")
            did = d.get("artifact_id", "?")[:8]
            dstate = d.get("state", "?")
            click.echo(f"    ← [{dtype}] {did}... ({dstate})")
    else:
        click.echo(f"\n  Depends on: none")
```

### Step 5.4 — Run tests

```bash
python -m pytest tests/test_task.py -v
python -m pytest tests/ -q
```

Expected: All task tests pass (or skip). Full suite: 91 passed.

### Step 5.5 — Commit

```bash
git add seldon/commands/task.py tests/test_task.py
git commit -m "feat: task commands (create, list, update, show)"
```

---

## Task 6: Session Commands (`seldon briefing` + `seldon closeout`)

**Goal:** `seldon briefing` loads working memory from the graph. `seldon closeout` creates a LabNotebookEntry and prints session stats.

**Files:**
- Create: `seldon/commands/session.py`
- Create: `tests/test_session_commands.py`

### Step 6.1 — Write failing tests

**File: `tests/test_session_commands.py`**

```python
"""
Session briefing/closeout tests. Requires Neo4j.
"""
import pytest
from pathlib import Path
from seldon.domain.loader import load_domain_config
from seldon.core.artifacts import create_artifact, create_link, transition_state
from seldon.core.graph import get_artifact, get_artifacts_by_type
from seldon.core.events import read_events
from seldon.config import start_session, end_session, get_current_session

pytestmark = pytest.mark.usefixtures("neo4j_available")

NEO4J_DB = "seldon-test"
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


def _make_task(project_dir, driver, domain_config, desc="test"):
    return create_artifact(
        project_dir=project_dir, driver=driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="ResearchTask",
        properties={"description": desc}, actor="human", authority="accepted",
    )


def _make_result(project_dir, driver, domain_config, value=0.5):
    return create_artifact(
        project_dir=project_dir, driver=driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Result",
        properties={"value": value}, actor="human", authority="accepted",
    )


def _make_script(project_dir, driver, domain_config):
    return create_artifact(
        project_dir=project_dir, driver=driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Script",
        properties={}, actor="human", authority="accepted",
    )


# ── briefing queries ──────────────────────────────────────────────────────────

def test_briefing_open_tasks_query(neo4j_driver, project_dir, domain_config, clean_test_db):
    """Briefing should find all tasks in open states."""
    _make_task(project_dir, neo4j_driver, domain_config, "task 1")
    _make_task(project_dir, neo4j_driver, domain_config, "task 2")

    with neo4j_driver.session(database=NEO4J_DB) as session:
        records = session.run(
            "MATCH (t:ResearchTask) WHERE t.state IN ['proposed','accepted','in_progress','blocked'] RETURN t"
        ).data()
    assert len(records) == 2


def test_briefing_stale_results_query(neo4j_driver, project_dir, domain_config, clean_test_db):
    """Briefing should find stale results."""
    result_id = _make_result(project_dir, neo4j_driver, domain_config)
    transition_state(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=result_id,
        artifact_type="Result", current_state="proposed", new_state="verified",
        actor="human", authority="accepted",
    )
    transition_state(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_id=result_id,
        artifact_type="Result", current_state="verified", new_state="stale",
        actor="human", authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        from seldon.core.graph import get_stale_artifacts
        stale = get_stale_artifacts(session)
    assert any(a["artifact_id"] == result_id for a in stale)


def test_briefing_incomplete_provenance_query(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """Briefing should find Results with no GENERATED_BY Script."""
    result_with_script = _make_result(project_dir, neo4j_driver, domain_config, 0.8)
    result_no_script = _make_result(project_dir, neo4j_driver, domain_config, 0.9)
    script_id = _make_script(project_dir, neo4j_driver, domain_config)

    create_link(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config,
        from_id=result_with_script, to_id=script_id,
        from_type="Result", to_type="Script",
        rel_type="generated_by", actor="human", authority="accepted",
    )

    with neo4j_driver.session(database=NEO4J_DB) as session:
        records = session.run(
            "MATCH (r:Result) WHERE NOT (r)-[:GENERATED_BY]->(:Script) RETURN r"
        ).data()

    no_script_ids = {dict(r["r"])["artifact_id"] for r in records}
    assert result_no_script in no_script_ids
    assert result_with_script not in no_script_ids


# ── closeout ──────────────────────────────────────────────────────────────────

def test_closeout_creates_lab_notebook_entry(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """closeout should create a LabNotebookEntry artifact."""
    session_id = start_session(project_dir)

    # Create some artifacts during the session
    create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Result",
        properties={"value": 0.5}, actor="human", authority="accepted",
        session_id=session_id,
    )

    # Now create the LabNotebookEntry (what closeout does)
    entry_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="LabNotebookEntry",
        properties={"summary": "test session", "session_id": session_id},
        actor="human", authority="accepted",
        session_id=session_id,
    )

    end_session(project_dir)

    with neo4j_driver.session(database=NEO4J_DB) as session:
        entries = get_artifacts_by_type(session, "LabNotebookEntry")
    assert len(entries) == 1
    assert entries[0]["artifact_id"] == entry_id


def test_closeout_session_event_count(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """Events tagged with session_id should be countable."""
    session_id = start_session(project_dir)

    for _ in range(3):
        create_artifact(
            project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config, artifact_type="Result",
            properties={"value": 0.1}, actor="human", authority="accepted",
            session_id=session_id,
        )

    end_session(project_dir)

    all_events = read_events(project_dir)
    session_events = [e for e in all_events if e.get("session_id") == session_id]
    created = [e for e in session_events if e["event_type"] == "artifact_created"]

    assert len(created) == 3


def test_start_session_sets_current_session(project_dir):
    """start_session sets the active session ID."""
    sid = start_session(project_dir)
    assert get_current_session(project_dir) == sid
    end_session(project_dir)


def test_events_tagged_with_session_id(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    """Events created while a session is active carry the session_id."""
    session_id = start_session(project_dir)

    create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="Result",
        properties={"value": 0.5}, actor="human", authority="accepted",
        session_id=session_id,
    )

    end_session(project_dir)

    all_events = read_events(project_dir)
    assert all_events[0]["session_id"] == session_id
```

### Step 6.2 — Run failing tests

```bash
python -m pytest tests/test_session_commands.py -v
```

Expected: All pass (or skip if no Neo4j) — these tests use existing primitives.

### Step 6.3 — Create `seldon/commands/session.py`

```python
from __future__ import annotations

from pathlib import Path

import click

from seldon.config import (
    load_project_config, get_neo4j_driver,
    start_session, end_session, get_current_session, get_current_session_data,
)
from seldon.core.artifacts import create_artifact
from seldon.core.events import read_events
from seldon.core.graph import graph_stats, get_stale_artifacts
from seldon.domain.loader import load_domain_config


def _get_domain_config(config: dict):
    domain_name = config["project"].get("domain", "research")
    domain_yaml = Path(__file__).parent.parent / "domain" / f"{domain_name}.yaml"
    return load_domain_config(domain_yaml)


@click.command("briefing")
def briefing_command():
    """Load working memory: open tasks, stale results, incomplete provenance."""
    config = load_project_config()
    project_dir = Path.cwd()
    driver = get_neo4j_driver(config)
    database = config["neo4j"]["database"]
    project_name = config["project"]["name"]

    # Start a new session
    start_session(project_dir)

    with driver.session(database=database) as session:
        # 1. Open tasks
        open_task_records = session.run(
            "MATCH (t:ResearchTask) WHERE t.state IN ['proposed','accepted','in_progress','blocked'] "
            "RETURN t ORDER BY t.created_at"
        ).data()
        open_tasks = [dict(r["t"]) for r in open_task_records]

        # What each open task blocks
        for t in open_tasks:
            blocked = session.run(
                "MATCH (t:ResearchTask {artifact_id: $id})-[:BLOCKS]->(target) RETURN target",
                id=t["artifact_id"],
            ).data()
            t["_blocks"] = [dict(r["target"]) for r in blocked]

        # 2. Stale results
        stale = get_stale_artifacts(session)

        # 3. Incomplete provenance: Results with no GENERATED_BY Script
        no_script_records = session.run(
            "MATCH (r:Result) WHERE NOT (r)-[:GENERATED_BY]->(:Script) RETURN r"
        ).data()
        no_script = [dict(r["r"]) for r in no_script_records]

        # 4. Graph stats
        stats = graph_stats(session)

    driver.close()

    width = 50
    border = "═" * width
    click.echo(f"\n{border}")
    click.echo(f"  SELDON BRIEFING — {project_name}")
    click.echo(f"{border}\n")

    # Open tasks
    click.echo(f"OPEN TASKS ({len(open_tasks)}):")
    if open_tasks:
        state_icons = {"proposed": "○", "accepted": "○", "in_progress": "●", "blocked": "⚠"}
        for t in open_tasks:
            icon = state_icons.get(t.get("state", ""), "?")
            desc = (t.get("description") or "")[:50]
            st = t.get("state", "?")
            tid = t.get("artifact_id", "?")[:8]
            click.echo(f"  {icon} [{st}] {desc}")
            click.echo(f"      id: {tid}...")
            if t.get("_blocks"):
                for b in t["_blocks"]:
                    btype = b.get("artifact_type", "?")
                    bid = b.get("artifact_id", "?")[:8]
                    bstate = b.get("state", "?")
                    click.echo(f"      → blocks: [{btype}] {bid}... ({bstate})")
    else:
        click.echo("  (none)")

    # Stale results
    click.echo(f"\nSTALE RESULTS ({len(stale)}):")
    if stale:
        for r in stale:
            val = r.get("value", "?")
            units = r.get("units", "")
            rid = r.get("artifact_id", "?")[:8]
            desc = r.get("description", "")
            click.echo(f"  ⚠ {rid}...  {val} {units}  {desc}")
    else:
        click.echo("  (none)")

    # Incomplete provenance
    click.echo(f"\nINCOMPLETE PROVENANCE ({len(no_script)}):")
    if no_script:
        for r in no_script:
            rid = r.get("artifact_id", "?")[:8]
            val = r.get("value", "?")
            desc = r.get("description", "")
            click.echo(f"  ⚠ {rid}...  value={val}  {desc}  (no linked Script)")
    else:
        click.echo("  (none)")

    # Stats
    click.echo(f"\nGRAPH: {stats['total_nodes']} artifacts, {stats['total_relationships']} relationships")
    click.echo(f"{border}\n")


@click.command("closeout")
@click.option("--summary", default=None, help="Session summary text")
def closeout_command(summary):
    """Consolidate session into graph: create LabNotebookEntry, print session stats."""
    config = load_project_config()
    project_dir = Path.cwd()
    driver = get_neo4j_driver(config)
    domain_config = _get_domain_config(config)
    database = config["neo4j"]["database"]

    session_data = get_current_session_data(project_dir)
    session_id = session_data["session_id"] if session_data else None
    started_at = session_data["started_at"] if session_data else "unknown"

    if summary is None:
        summary = click.prompt("Session summary")

    # Count events from this session
    all_events = read_events(project_dir)
    if session_id:
        session_events = [e for e in all_events if e.get("session_id") == session_id]
    else:
        session_events = []

    created = [e for e in session_events if e["event_type"] == "artifact_created"]
    transitions = [e for e in session_events if e["event_type"] == "artifact_state_changed"]
    links = [e for e in session_events if e["event_type"] == "link_created"]

    # Breakdown of created artifact types
    type_counts: dict = {}
    for e in created:
        atype = e.get("payload", {}).get("artifact_type", "unknown")
        type_counts[atype] = type_counts.get(atype, 0) + 1
    type_summary = ", ".join(f"{cnt} {t}" for t, cnt in sorted(type_counts.items()))

    from datetime import datetime, timezone
    ended_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # Create LabNotebookEntry
    entry_props = {
        "summary": summary,
        "session_id": session_id or "none",
        "started_at": started_at,
        "ended_at": ended_at,
        "artifacts_created": len(created),
        "transitions": len(transitions),
        "links_created": len(links),
    }

    try:
        entry_id = create_artifact(
            project_dir=project_dir, driver=driver, database=database,
            domain_config=domain_config, artifact_type="LabNotebookEntry",
            properties=entry_props, actor="human", authority="accepted",
            session_id=session_id,
        )
    finally:
        driver.close()

    end_session(project_dir)

    width = 50
    border = "═" * width
    click.echo(f"\n{border}")
    click.echo(f"  SELDON CLOSEOUT")
    click.echo(f"{border}")
    click.echo(f"Session: {started_at}")
    click.echo(f"       → {ended_at}\n")
    click.echo(f"CREATED:     {len(created)} artifacts ({type_summary or 'none'})")
    click.echo(f"TRANSITIONS: {len(transitions)}")
    click.echo(f"LINKS:       {len(links)}")
    click.echo(f"\nSUMMARY: \"{summary}\"")
    click.echo(f"\nLogged as LabNotebookEntry: {entry_id}")
    click.echo(f"{border}\n")
```

### Step 6.4 — Run tests

```bash
python -m pytest tests/test_session_commands.py -v
python -m pytest tests/ -q
```

Expected: Full suite: 99 passed (or skipped pattern if no Neo4j).

### Step 6.5 — Commit

```bash
git add seldon/commands/session.py tests/test_session_commands.py
git commit -m "feat: session commands — briefing loads working memory, closeout creates LabNotebookEntry"
```

---

## Task 7: Wire CLI + Final Verification

**Goal:** Register all new commands. Verify `seldon --help` shows everything. Run full test suite.

**Files:**
- Modify: `seldon/cli.py`

### Step 7.1 — Update `seldon/cli.py`

Replace the entire file contents with:

```python
import click

from seldon.commands.init import init_command
from seldon.commands.status import status_command
from seldon.commands.rebuild import rebuild_command
from seldon.commands.artifact import artifact_group
from seldon.commands.link import link_group
from seldon.commands.result import result_group
from seldon.commands.task import task_group
from seldon.commands.session import briefing_command, closeout_command


@click.group()
@click.version_option()
def main():
    """Seldon — AI-assisted research artifact tracker."""
    pass


main.add_command(init_command, name="init")
main.add_command(status_command, name="status")
main.add_command(rebuild_command, name="rebuild")
main.add_command(artifact_group, name="artifact")
main.add_command(link_group, name="link")
main.add_command(result_group, name="result")
main.add_command(task_group, name="task")
main.add_command(briefing_command, name="briefing")
main.add_command(closeout_command, name="closeout")
```

### Step 7.2 — Reinstall and verify help

```bash
pip install -e ".[dev]" -q
seldon --help
```

Expected output includes:
```
Commands:
  artifact   Manage artifacts.
  briefing   Load working memory: open tasks, stale results...
  closeout   Consolidate session into graph...
  init       Initialize a new Seldon project...
  link       Manage artifact relationships.
  rebuild    Rebuild Neo4j graph from JSONL event log.
  result     Manage Result artifacts...
  status     Show project status...
  task       Manage ResearchTask artifacts...
```

Also verify subcommands:
```bash
seldon result --help
seldon task --help
```

### Step 7.3 — Run full test suite

```bash
python -m pytest tests/ -v
```

**Expected (Neo4j running):** 99 passed, 0 failed.

**Expected (Neo4j offline):** 36 passed, 63 skipped, 0 failed.

### Step 7.4 — Verify CC Task 4 checklist

```bash
# Initialize a test project (Neo4j must be running)
cd /tmp && rm -rf seldon-tier2-smoke && mkdir seldon-tier2-smoke && cd seldon-tier2-smoke
seldon init "Tier2 Smoke Test"

# Start session
seldon briefing
# Expected: structured report, session started

# Register a result
seldon result register --value 0.912 --units accuracy --description "Model accuracy on test set"
# Expected: Created Result: <uuid>

# Register a script, then link
seldon artifact create Script --property name=analysis.py
# Note the Script UUID
seldon result register --value 0.85 --units f1 --script-id <script-uuid>
# Expected: Created Result with GENERATED_BY link

# Verify a result
seldon result verify <result-uuid>
# Expected: state: proposed → verified

# List results
seldon result list
# Expected: table with results

# Create a task
seldon task create --description "Backfill 3 Anthropic parse failures"
# Expected: Created ResearchTask: <uuid>

# List open tasks
seldon task list --open
# Expected: 1 open task

# Update task state
seldon task update <task-uuid> --state accepted
# Expected: proposed → accepted

# Show task
seldon task show <task-uuid>
# Expected: detail with state=accepted

# Trace result provenance
seldon result trace <result-uuid>
# Expected: shows upstream Script

# Check stale
seldon result check-stale
# Expected: (none) if no stale results

# Closeout
seldon closeout --summary "Verified accuracy result, linked to script, created backfill task"
# Expected: structured closeout report, LabNotebookEntry created

# Cleanup
cd /tmp && rm -rf seldon-tier2-smoke
```

### Step 7.5 — Commit

```bash
cd /Users/brock/Documents/GitHub/seldon/.worktrees/tier2-features
git add seldon/cli.py
git commit -m "feat: wire tier2 commands into CLI (result, task, briefing, closeout)"
```

---

## Summary of Changes

| File | Action | Description |
|------|--------|-------------|
| `seldon/config.py` | Modify | Add `start_session`, `get_current_session`, `get_current_session_data`, `end_session` |
| `seldon/core/artifacts.py` | Modify | Add `session_id` param to all 4 functions; hook staleness propagation |
| `seldon/core/staleness.py` | Create | `propagate_staleness()` — cascade stale to CITES downstream |
| `seldon/domain/research.yaml` | Modify | Add `Result` to `implements.from_types` |
| `seldon/commands/result.py` | Create | `register`, `verify`, `list`, `trace`, `check-stale` |
| `seldon/commands/task.py` | Create | `create`, `list`, `update`, `show` |
| `seldon/commands/session.py` | Create | `briefing`, `closeout` |
| `seldon/cli.py` | Modify | Register all new commands |
| `tests/test_session_mgmt.py` | Create | 9 pure Python tests for session management |
| `tests/test_staleness.py` | Create | 5 Neo4j tests for staleness propagation |
| `tests/test_result.py` | Create | 9 Neo4j tests for result operations |
| `tests/test_task.py` | Create | 7 Neo4j tests for task operations |
| `tests/test_session_commands.py` | Create | 6 tests (1 pure + 5 Neo4j) for briefing/closeout |

**New test count:** 36 new tests (9 pure Python + 27 Neo4j-dependent)
**Total when done:** 97 tests (61 existing + 36 new)
