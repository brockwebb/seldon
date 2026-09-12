"""`seldon handoff` — session window, AD-030-R9 gate, generated document.

The gate is the point of the command, so it is tested from both sides: a
Desktop session that filed tasks and wrote no design note must be refused, and
the same session with a design note must close. The rest of the file pins the
two blocks that a next thread pastes verbatim — their wording is an interface,
not a formatting choice.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner

from seldon.commands.go import (
    R9_PREVIOUS_SESSION_NOTICE,
    _get_r9_notice,
    assemble_go_context,
)
from seldon.commands.handoff import handoff_command
from seldon.core.artifacts import create_artifact
from seldon.core.handoff import (
    DEFAULT_REQUIRE_DESIGN_NOTE,
    DEFAULT_SESSION_WINDOW_HOURS,
    NO_DISPATCH,
    R9_MESSAGE,
    R9Violation,
    SessionWindow,
    WINDOW_SOURCE_FALLBACK,
    WINDOW_SOURCE_HANDOFF,
    WINDOW_SOURCE_LABNOTEBOOK,
    build_handoff,
    check_r9,
    dispatch_block,
    events_in_window,
    handoff_boundary,
    handoff_settings,
    previous_session_window,
    registered_cc_tasks,
    resume_block,
    session_window,
    write_handoff,
)
from seldon.core.precedence import add_chain
from seldon.domain.loader import load_domain_config

from tests.testdb import TEST_DATABASE

NEO4J_DB = TEST_DATABASE
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"

neo4j_tests = pytest.mark.usefixtures("neo4j_available", "clean_test_db")


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


def _write_config(project_dir: Path, **handoff_block) -> None:
    """Write a seldon.yaml pointing at the test database.

    Args:
        project_dir: Project root.
        **handoff_block: Keys placed under the `handoff:` block. When empty, the
            block is omitted so the module defaults are exercised.
    """
    text = (
        "project:\n  name: test\n  domain: research\n"
        f"neo4j:\n  database: {NEO4J_DB}\n  uri: bolt://localhost:7687\n"
        "event_store:\n  path: seldon_events.jsonl\n"
    )
    if handoff_block:
        text += "handoff:\n"
        for key, value in handoff_block.items():
            rendered = str(value).lower() if isinstance(value, bool) else value
            text += f"  {key}: {rendered}\n"
    (project_dir / "seldon.yaml").write_text(text)


@pytest.fixture
def project(project_dir, monkeypatch):
    """A project root with seldon.yaml, handoffs/, docs/design/ and cc_tasks/."""
    _write_config(project_dir, session_window_hours=12, require_design_note=True)
    for sub in ("handoffs", "docs/design", "cc_tasks"):
        (project_dir / sub).mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(project_dir)
    return project_dir


def _config(project_dir: Path) -> dict:
    from seldon.config import load_project_config

    return load_project_config(project_dir)


def _desktop_task(project_dir, driver, domain_config, description="Desktop task", **props):
    """Create a ResearchTask stamped with the Desktop actor."""
    return create_artifact(
        project_dir=project_dir,
        driver=driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="ResearchTask",
        properties={"description": description, **props},
        actor="desktop",
        authority="accepted",
    )


def _touch(path: Path, moment: datetime) -> Path:
    """Write a file and set its mtime to a given instant."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {path.stem}\n")
    stamp = moment.timestamp()
    os.utime(path, (stamp, stamp))
    return path


def _window(hours_back: float = 12.0) -> SessionWindow:
    now = datetime.now(timezone.utc)
    return SessionWindow(
        start=now - timedelta(hours=hours_back),
        end=now + timedelta(seconds=1),
        source=WINDOW_SOURCE_FALLBACK,
        marker="test",
    )


# ---------------------------------------------------------------------------
# Config keys are read from seldon.yaml, not hardcoded
# ---------------------------------------------------------------------------

def test_settings_default_when_block_absent(project_dir):
    """A project whose config predates the handoff tool gets the documented defaults."""
    _write_config(project_dir)
    settings = handoff_settings(_config(project_dir))
    assert settings.session_window_hours == DEFAULT_SESSION_WINDOW_HOURS
    assert settings.require_design_note is DEFAULT_REQUIRE_DESIGN_NOTE


def test_settings_read_from_seldon_yaml(project_dir):
    """Both keys come out of the config, not out of the source."""
    _write_config(project_dir, session_window_hours=3, require_design_note=False)
    settings = handoff_settings(_config(project_dir))
    assert settings.session_window_hours == 3
    assert settings.require_design_note is False


@pytest.mark.parametrize("bad", ["nope", 0, -5])
def test_settings_reject_unusable_window(project_dir, bad):
    """A window that would silently truncate the report is refused, not coerced."""
    _write_config(project_dir, session_window_hours=bad)
    with pytest.raises(ValueError, match="session_window_hours"):
        handoff_settings(_config(project_dir))


def test_configured_window_drives_the_fallback(project_dir):
    """With no marker to bound the session, the window is exactly what config says."""
    _write_config(project_dir, session_window_hours=3)
    settings = handoff_settings(_config(project_dir))
    now = datetime.now(timezone.utc)
    window = session_window(project_dir, settings, now=now)
    assert window.source == WINDOW_SOURCE_FALLBACK
    assert window.start == now - timedelta(hours=3)


# ---------------------------------------------------------------------------
# Session window
# ---------------------------------------------------------------------------

def test_boundary_prefers_declared_date_over_a_foreign_mtime(tmp_path):
    """A checkout's mtime must not erase a handoff's declared session date."""
    path = _touch(
        tmp_path / "handoffs" / "2026-03-01_old.md",
        datetime(2026, 9, 12, 10, tzinfo=timezone.utc),
    )
    assert handoff_boundary(path).date() == datetime(2026, 3, 1).date()


def test_boundary_uses_mtime_when_it_agrees_with_the_declared_date(tmp_path):
    """Two sessions on one day bound precisely, not at midnight."""
    moment = datetime(2026, 3, 1, 15, 30, tzinfo=timezone.utc)
    path = _touch(tmp_path / "handoffs" / "2026-03-01_first.md", moment)
    assert handoff_boundary(path) == moment


def test_window_starts_at_the_newest_handoff(project):
    """The previous handoff bounds this session."""
    moment = datetime.now(timezone.utc) - timedelta(hours=2)
    _touch(project / "handoffs" / f"{moment:%Y-%m-%d}_prior.md", moment)
    settings = handoff_settings(_config(project))
    window = session_window(project, settings)
    assert window.source == WINDOW_SOURCE_HANDOFF
    assert abs((window.start - moment).total_seconds()) < 2


@neo4j_tests
def test_window_prefers_the_later_of_notebook_and_handoff(
    project, neo4j_driver, domain_config
):
    """A lab notebook entry written after the last handoff wins the boundary."""
    old = datetime.now(timezone.utc) - timedelta(hours=6)
    _touch(project / "handoffs" / f"{old:%Y-%m-%d}_prior.md", old)
    create_artifact(
        project_dir=project,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="LabNotebookEntry",
        properties={"summary": "mid-session note"},
        actor="cc",
        authority="accepted",
    )
    settings = handoff_settings(_config(project))
    window = session_window(project, settings, neo4j_driver, NEO4J_DB)
    assert window.source == WINDOW_SOURCE_LABNOTEBOOK


def test_window_falls_back_when_the_marker_is_in_the_future(project):
    """A handoff dated ahead must not silently produce an empty report."""
    ahead = datetime.now(timezone.utc) + timedelta(days=2)
    _touch(project / "handoffs" / f"{ahead:%Y-%m-%d}_ahead.md", ahead)
    settings = handoff_settings(_config(project))
    window = session_window(project, settings)
    assert window.source == WINDOW_SOURCE_FALLBACK


# ---------------------------------------------------------------------------
# AD-030-R9
# ---------------------------------------------------------------------------

@neo4j_tests
def test_r9_refuses_desktop_tasks_without_a_design_note(
    project, neo4j_driver, domain_config
):
    """The refusal path: tasks filed, no ruling written."""
    _desktop_task(project, neo4j_driver, domain_config)
    with pytest.raises(R9Violation) as exc:
        build_handoff(
            project_dir=project,
            config=_config(project),
            driver=neo4j_driver,
            database=NEO4J_DB,
            domain_config=domain_config,
            slug="x",
            summary="y",
            next_action="z",
        )
    assert str(exc.value) == R9_MESSAGE
    assert exc.value.verdict.violated


@neo4j_tests
def test_r9_passes_when_a_design_note_was_written(
    project, neo4j_driver, domain_config
):
    """A design note in the window discharges the obligation."""
    _desktop_task(project, neo4j_driver, domain_config)
    _touch(project / "docs" / "design" / "DN-001_thing.md", datetime.now(timezone.utc))
    document = build_handoff(
        project_dir=project,
        config=_config(project),
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        slug="x",
        summary="y",
        next_action="z",
    )
    assert document.r9.violated is False
    assert document.warnings == []


@neo4j_tests
def test_r9_warns_instead_of_refusing_when_configured(
    project, neo4j_driver, domain_config
):
    """require_design_note: false downgrades the gate to a warning, not silence."""
    _write_config(project, session_window_hours=12, require_design_note=False)
    _desktop_task(project, neo4j_driver, domain_config)
    document = build_handoff(
        project_dir=project,
        config=_config(project),
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        slug="x",
        summary="y",
        next_action="z",
    )
    assert document.r9.violated is True
    assert any(R9_MESSAGE in w for w in document.warnings)


@neo4j_tests
def test_r9_ignores_tasks_a_cc_session_created(project, neo4j_driver, domain_config):
    """AD-030-R11's allow-list of one: CC executes what was decided, so it owes no note."""
    create_artifact(
        project_dir=project,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="ResearchTask",
        properties={"description": "CC-created"},
        actor="cc",
        authority="accepted",
    )
    window = _window()
    verdict = check_r9(project, window, events_in_window(project, window))
    assert verdict.violated is False


@neo4j_tests
def test_r9_gates_an_actor_that_is_neither_cc_nor_desktop(
    project, neo4j_driver, domain_config
):
    """AD-030-R11: the gate was a deny-list on `desktop`, so an unknown actor escaped it."""
    create_artifact(
        project_dir=project,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_type="ResearchTask",
        properties={"description": "filed by something new"},
        actor="hermes",
        authority="accepted",
    )
    window = _window()
    verdict = check_r9(project, window, events_in_window(project, window))
    assert verdict.violated is True
    assert len(verdict.gated_task_ids) == 1


def test_r9_ignores_a_design_note_written_before_the_window(project):
    """A note from a previous session does not discharge this session's obligation."""
    old = datetime.now(timezone.utc) - timedelta(days=30)
    _touch(project / "docs" / "design" / "AD-001_old.md", old)
    window = _window()
    verdict = check_r9(
        project,
        window,
        [
            {
                "event_type": "artifact_created",
                "actor": "desktop",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payload": {"artifact_type": "ResearchTask", "artifact_id": "abc123"},
            }
        ],
    )
    assert verdict.violated is True
    assert verdict.design_notes == ()


# ---------------------------------------------------------------------------
# The two blocks
# ---------------------------------------------------------------------------

def test_resume_block_exact_text(tmp_path):
    """The resume block is pasted verbatim into a context-free thread."""
    path = tmp_path / "handoffs" / "2026-09-12_x.md"
    path.parent.mkdir(parents=True)
    path.write_text("x")
    assert resume_block(path, "read AD-030") == (
        f"seldon go --brief {path.resolve()}\n"
        "Read the handoff in full. Verify listed task IDs against the graph "
        "before acting.\n"
        "First action: read AD-030"
    )


def test_dispatch_block_line_per_task_in_order():
    """One line per task, in the order they must run."""
    assert dispatch_block(["cc_tasks/a.md", "cc_tasks/b.md"], "") == (
        "Read CLAUDE.md, then execute cc_tasks/a.md. "
        "Glob and read all sibling *ADDENDUM*.md first.\n"
        "Read CLAUDE.md, then execute cc_tasks/b.md. "
        "Glob and read all sibling *ADDENDUM*.md first."
    )


def test_dispatch_block_says_why_when_empty():
    """'None' without a reason leaves the next thread unable to act."""
    rendered = dispatch_block([], "no CC task file was registered in this window")
    assert rendered.startswith(NO_DISPATCH)
    assert "no CC task file was registered" in rendered


@neo4j_tests
def test_dispatch_lists_registered_proposed_tasks_in_order(
    project, neo4j_driver, domain_config
):
    """Registration order is execution order."""
    for name in ("a", "b"):
        _desktop_task(
            project,
            neo4j_driver,
            domain_config,
            description=f"task {name}",
            source_file=f"cc_tasks/2026-09-12_{name}.md",
        )
    window = _window()
    paths, reason = registered_cc_tasks(
        events_in_window(project, window), neo4j_driver, NEO4J_DB
    )
    assert paths == ["cc_tasks/2026-09-12_a.md", "cc_tasks/2026-09-12_b.md"]
    assert reason == ""


@neo4j_tests
def test_dispatch_excludes_tasks_that_left_proposed(
    project, neo4j_driver, domain_config
):
    """A task already started is not dispatch-ready, and the reason says so."""
    from seldon.core.artifacts import transition_state

    task_id = _desktop_task(
        project,
        neo4j_driver,
        domain_config,
        source_file="cc_tasks/2026-09-12_started.md",
    )
    transition_state(
        project_dir=project,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        artifact_id=task_id,
        artifact_type="ResearchTask",
        current_state="proposed",
        new_state="accepted",
        actor="cc",
        authority="accepted",
    )
    window = _window()
    paths, reason = registered_cc_tasks(
        events_in_window(project, window), neo4j_driver, NEO4J_DB
    )
    assert paths == []
    assert "still in `proposed`" in reason


# ---------------------------------------------------------------------------
# The generated document
# ---------------------------------------------------------------------------

@neo4j_tests
def test_document_is_generated_from_the_graph(project, neo4j_driver, domain_config):
    """Every section but the summary and the next action is read, not typed."""
    _touch(project / "docs" / "design" / "DN-002_note.md", datetime.now(timezone.utc))
    _touch(project / "cc_tasks" / "2026-09-12_work.md", datetime.now(timezone.utc))
    created = _desktop_task(
        project,
        neo4j_driver,
        domain_config,
        description="Ingest governed documents",
        source_file="cc_tasks/2026-09-12_work.md",
    )

    document = build_handoff(
        project_dir=project,
        config=_config(project),
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        slug="closeout",
        summary="One line about the session.",
        next_action="Run the ingest task.",
    )
    text = document.text

    # Headings match the format already in handoffs/.
    for heading in (
        "## One line",
        "## Graph changes",
        "## Files written",
        "## Open tasks",
        "## Resume line",
        "## CC dispatch text",
    ):
        assert heading in text

    assert "One line about the session." in text
    # Graph changes carry the short id and the description read from the event.
    assert created[:8] in text
    assert "Ingest governed documents" in text
    # Files written come from filesystem mtime inside the window.
    assert "`docs/design/DN-002_note.md`" in text
    assert "`cc_tasks/2026-09-12_work.md`" in text
    # Both blocks are embedded in the file, not only returned.
    assert document.resume in text
    assert document.dispatch in text
    assert "cc_tasks/2026-09-12_work.md" in document.dispatch


@neo4j_tests
def test_open_tasks_list_ready_first(project, neo4j_driver, domain_config):
    """AD-029 ordering: what may be started now comes before what waits."""
    _touch(project / "docs" / "design" / "DN-003.md", datetime.now(timezone.utc))
    first = _desktop_task(project, neo4j_driver, domain_config, description="First task")
    second = _desktop_task(
        project, neo4j_driver, domain_config, description="Second task"
    )
    add_chain(
        project_dir=project,
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        task_ids=[first, second],
        reason=None,
        actor="human",
        authority="accepted",
    )

    document = build_handoff(
        project_dir=project,
        config=_config(project),
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        slug="ordering",
        summary="s",
        next_action="n",
    )
    body = document.text.split("## Open tasks")[1].split("## Resume line")[0]
    assert body.index(first[:8]) < body.index(second[:8])
    assert f"▸ `{first[:8]}`" in body


@neo4j_tests
def test_write_refuses_to_replace_a_session_record(
    project, neo4j_driver, domain_config
):
    """A handoff is the record of a session that happened; --force is explicit."""
    _touch(project / "docs" / "design" / "DN-004.md", datetime.now(timezone.utc))
    _desktop_task(project, neo4j_driver, domain_config)
    kwargs = dict(
        project_dir=project,
        config=_config(project),
        driver=neo4j_driver,
        database=NEO4J_DB,
        domain_config=domain_config,
        slug="dup",
        summary="s",
        next_action="n",
    )
    write_handoff(build_handoff(**kwargs))
    with pytest.raises(FileExistsError):
        write_handoff(build_handoff(**kwargs))
    write_handoff(build_handoff(**kwargs), force=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@neo4j_tests
def test_cli_writes_and_prints_both_blocks(project, neo4j_driver, domain_config):
    """The success contract: a file on disk and both blocks on stdout."""
    _touch(project / "docs" / "design" / "DN-005.md", datetime.now(timezone.utc))
    _desktop_task(project, neo4j_driver, domain_config)

    result = CliRunner().invoke(
        handoff_command, ["--slug", "x", "--summary", "y", "--next", "z"]
    )
    assert result.exit_code == 0, result.output
    assert "## Resume block" in result.output
    assert "## CC dispatch block" in result.output
    written = list((project / "handoffs").glob("*_x.md"))
    assert len(written) == 1
    assert "First action: z" in written[0].read_text()


@neo4j_tests
def test_cli_refuses_an_r9_violation(project, neo4j_driver, domain_config):
    """Refusal exits non-zero and writes nothing."""
    _desktop_task(project, neo4j_driver, domain_config)
    result = CliRunner().invoke(
        handoff_command, ["--slug", "x", "--summary", "y", "--next", "z"]
    )
    assert result.exit_code == 1
    assert R9_MESSAGE in result.output
    assert list((project / "handoffs").glob("*.md")) == []


# ---------------------------------------------------------------------------
# seldon go
# ---------------------------------------------------------------------------

def test_go_prints_the_desktop_close_obligation(tmp_path):
    """The Desktop contract names the command and the rule."""
    context = assemble_go_context(project_dir=str(tmp_path), brief=True)
    assert "seldon handoff --slug <s> --summary <s> --next <s>" in context
    assert "AD-030-R9" in context


def test_go_reports_a_previous_session_that_violated_r9(project):
    """The next orient surfaces a close that should not have happened."""
    from seldon.core.events import append_event, make_event

    old = datetime.now(timezone.utc) - timedelta(days=2)
    recent = datetime.now(timezone.utc) - timedelta(hours=1)
    _touch(project / "handoffs" / f"{old:%Y-%m-%d}_earlier.md", old)
    _touch(project / "handoffs" / f"{recent:%Y-%m-%d}_latest.md", recent)

    event = make_event(
        event_type="artifact_created",
        actor="desktop",
        authority="accepted",
        payload={"artifact_id": "deadbeef-0000", "artifact_type": "ResearchTask"},
    )
    event["timestamp"] = (recent - timedelta(hours=3)).isoformat().replace(
        "+00:00", "Z"
    )
    append_event(project, event)

    notice = _get_r9_notice(str(project))
    assert notice is not None
    assert R9_PREVIOUS_SESSION_NOTICE in notice
    assert "deadbeef" in notice
    assert R9_PREVIOUS_SESSION_NOTICE in assemble_go_context(
        project_dir=str(project), brief=True
    )


def test_go_is_silent_when_the_previous_session_wrote_a_note(project):
    """No violation, no notice — the check must not become background noise."""
    from seldon.core.events import append_event, make_event

    old = datetime.now(timezone.utc) - timedelta(days=2)
    recent = datetime.now(timezone.utc) - timedelta(hours=1)
    _touch(project / "handoffs" / f"{old:%Y-%m-%d}_earlier.md", old)
    _touch(project / "handoffs" / f"{recent:%Y-%m-%d}_latest.md", recent)
    _touch(project / "docs" / "design" / "AD-999.md", recent - timedelta(hours=3))

    event = make_event(
        event_type="artifact_created",
        actor="desktop",
        authority="accepted",
        payload={"artifact_id": "deadbeef-0000", "artifact_type": "ResearchTask"},
    )
    event["timestamp"] = (recent - timedelta(hours=3)).isoformat().replace(
        "+00:00", "Z"
    )
    append_event(project, event)

    assert _get_r9_notice(str(project)) is None


def test_go_opens_on_the_named_handoff(project):
    """`seldon go --brief <path>` — the form the resume block emits — must work."""
    from seldon.cli import main

    newest = datetime.now(timezone.utc)
    _touch(project / "handoffs" / f"{newest:%Y-%m-%d}_newest.md", newest)
    named = project / "handoffs" / "2026-01-01_named.md"
    _touch(named, datetime(2026, 1, 1, tzinfo=timezone.utc))
    named.write_text("# NAMED HANDOFF MARKER\n")

    result = CliRunner().invoke(main, ["go", "--brief", str(named)])
    assert result.exit_code == 0, result.output
    assert "NAMED HANDOFF MARKER" in result.output


def test_go_reports_a_missing_named_handoff(project):
    """A path that does not exist is an error, not a silent fall-through."""
    from seldon.cli import main

    result = CliRunner().invoke(main, ["go", "--brief", str(project / "nope.md")])
    assert result.exit_code == 1
    assert "handoff not found" in result.output


def test_previous_window_is_none_without_a_handoff(project):
    """Nothing to bound, nothing to report."""
    settings = handoff_settings(_config(project))
    assert previous_session_window(project, settings) is None
