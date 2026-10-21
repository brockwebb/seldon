"""PRUNE-002 Part B: `seldon go`'s command and MCP sections are generated from the registries, it does not re-send
the CLAUDE.md files inside Claude Code, and the instruction context a launch receives is measured per week.

No Neo4j: the go sections that read the graph degrade to a one-line notice without one.
"""
from __future__ import annotations

import re

import click
import pytest

from seldon.cli import main
from seldon.commands import go as G
from seldon.core import instruction_context as IC

_CMD_RE = re.compile(r"^- `seldon ([^`]+)`")
_TOOL_RE = re.compile(r"^- `(seldon_\w+)\(")


def _walk(cmd, path=()):
    """The test's own walk of the click tree, independent of go's."""
    if isinstance(cmd, click.Group):
        return {p for name, sub in cmd.commands.items() for p in _walk(sub, path + (name,))}
    return {" ".join(path)}


def _printed(section: str, regex) -> set:
    return {m.group(1) for line in section.splitlines() if (m := regex.match(line))}


def test_printed_commands_equal_the_registered_set():
    section = G._available_commands_section()
    printed = _printed(section, _CMD_RE)
    assert printed == _walk(main)
    assert {"governed sync", "models show", "dispatch redrive", "decision list", "prior-art search"} <= printed


def test_printed_mcp_tools_equal_the_registered_set():
    from seldon.mcp_server import RAW_TOOLS
    assert _printed(G._available_commands_section(), _TOOL_RE) == set(RAW_TOOLS)


def test_negative_control_a_new_command_appears_without_editing_go(monkeypatch):
    """A static list would miss a command registered after it was written; the generated one cannot."""
    @click.command("prune002-probe")
    def probe():
        """Probe command for the PRUNE-002 negative control."""
    monkeypatch.setitem(main.commands, "prune002-probe", probe)
    section = G._available_commands_section()
    assert "- `seldon prune002-probe` — Probe command for the PRUNE-002 negative control." in section


def test_the_hand_written_section_is_gone():
    assert not hasattr(G, "_AVAILABLE_COMMANDS_SECTION")


@pytest.fixture
def project(tmp_path, monkeypatch):
    standards = tmp_path / "standards.md"
    standards.write_text("STANDARDS_TOKEN_P002")
    monkeypatch.setenv("SELDON_SYSTEM_CLAUDE_MD", str(standards))
    (tmp_path / "CLAUDE.md").write_text("PROJECT_TOKEN_P002")
    return tmp_path


def test_claude_code_path_does_not_embed_either_file(project, monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    text = G.assemble_go_context(project_dir=str(project))
    assert "STANDARDS_TOKEN_P002" not in text and "PROJECT_TOKEN_P002" not in text
    first = text.splitlines()[0]
    assert first.startswith("Moving: ") and "Context: claude_code" in first
    data = G.assemble_go_context_as_dict(project_dir=str(project))
    assert data["context_path"] == "claude_code"
    assert data["system_standards"] is None and data["project_context"] is None


def test_desktop_path_embeds_both_files(project, monkeypatch):
    monkeypatch.delenv("CLAUDECODE", raising=False)
    text = G.assemble_go_context(project_dir=str(project))
    assert "STANDARDS_TOKEN_P002" in text and "PROJECT_TOKEN_P002" in text
    assert "Context: embedded" in text.splitlines()[0]
    data = G.assemble_go_context_as_dict(project_dir=str(project))
    assert data["context_path"] == "embedded" and data["project_context"] == "PROJECT_TOKEN_P002"


def test_explicit_flag_overrides_the_environment(project, monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    assert "PROJECT_TOKEN_P002" in G.assemble_go_context(project_dir=str(project), in_claude_code=False)


def test_measure_counts_both_files_and_the_claude_code_go_output(project, monkeypatch):
    seen = {}

    def fake_go(project_dir, in_claude_code):
        seen["in_claude_code"] = in_claude_code
        return "x" * 100
    monkeypatch.setattr(G, "assemble_go_context", fake_go)
    r = IC.measure(project)
    assert seen["in_claude_code"] is True
    assert (r["standards"], r["project_claude_md"], r["go"], r["total"]) == (20, 18, 100, 138)
    assert r["go_error"] is None


def test_measure_records_a_go_failure_and_reports_no_total(project, monkeypatch):
    def boom(project_dir, in_claude_code):
        raise RuntimeError("graph down")
    monkeypatch.setattr(G, "assemble_go_context", boom)
    r = IC.measure(project)
    assert r["go"] is None and r["total"] is None and r["go_error"] == "RuntimeError: graph down"


def test_by_week_reads_the_launch_records():
    def launch(ts, reading):
        payload = {"task_id": "t"} if reading is None else {"task_id": "t", IC.PAYLOAD_KEY: reading}
        return {"event_type": "dispatch_launched", "timestamp": ts, "payload": payload}
    events = [launch("2026-10-13T10:00:00Z", None),
              launch("2026-10-20T10:00:00Z", {"total": 30_000}),
              launch("2026-10-21T10:00:00Z", {"total": 50_000}),
              launch("2026-10-22T10:00:00Z", {"total": None, "go_error": "x"}),
              {"event_type": "part_complete", "timestamp": "2026-10-22T10:00:00Z", "payload": {}}]
    assert IC.by_week(events) == [
        {"week": "2026-W42", "n": 0, "median_total": None, "max_total": None, "unmeasured": 1},
        {"week": "2026-W43", "n": 2, "median_total": 40_000, "max_total": 50_000, "unmeasured": 1}]
