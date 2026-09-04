"""Tests for the `seldon_audit` MCP tool.

The tool orchestrates AD-020 audit gates by writing run directories and
calling `seldon.paper.audit_dispatch.dispatch`. These tests mock the
dispatch call so no API hit is made.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from seldon.mcp_server import seldon_audit, _next_run_id, _resolve_paper_root

from tests.testdb import TEST_DATABASE


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_project(tmp_path: Path, paper_subdir: str = "paper") -> Path:
    """Build a minimal Seldon project at tmp_path with a paper section file."""
    (tmp_path / "seldon.yaml").write_text(
        "project:\n  name: test\n  domain: research\n"
        "neo4j:\n  database: " + TEST_DATABASE + "\n  uri: bolt://localhost:7687\n"
        "event_store:\n  path: seldon_events.jsonl\n"
        f"paths:\n  paper: {paper_subdir}\n  sections: {paper_subdir}/sections\n"
    )
    sections = tmp_path / paper_subdir / "sections"
    sections.mkdir(parents=True)
    section = sections / "00_abstract.md"
    section.write_text("# Abstract\n\nThis is the abstract content.\n")
    return section


def _fake_dispatch(prompt: str, system=None, **kwargs) -> str:
    """Return a minimal valid gate YAML so the tool's findings summary path runs."""
    return (
        "section: \"00_abstract.md\"\n"
        "gate: \"content_audit\"\n"
        "findings_count: 2\n"
        "findings:\n"
        "  - id: \"CA-00-01\"\n"
        "    text: \"Sample claim.\"\n"
        "    severity: \"low\"\n"
        "  - id: \"CA-00-02\"\n"
        "    text: \"Another claim.\"\n"
        "    severity: \"medium\"\n"
    )


# ── _next_run_id ─────────────────────────────────────────────────────────────

def test_next_run_id_empty_dir(tmp_path: Path):
    audits = tmp_path / "audits"
    audits.mkdir()
    assert _next_run_id(audits) == "run-001"


def test_next_run_id_missing_dir(tmp_path: Path):
    assert _next_run_id(tmp_path / "no-such-dir") == "run-001"


def test_next_run_id_increments_past_max(tmp_path: Path):
    audits = tmp_path / "audits"
    audits.mkdir()
    (audits / "run-001_2026-04-13").mkdir()
    (audits / "run-002_2026-04-17").mkdir()
    (audits / "run-005_2026-04-19").mkdir()
    (audits / "stray_file.txt").write_text("ignore me")
    assert _next_run_id(audits) == "run-006"


# ── _resolve_paper_root ──────────────────────────────────────────────────────

def test_resolve_paper_root_from_paths_paper(tmp_path: Path):
    section = _make_project(tmp_path, paper_subdir="paper")
    config = {"paths": {"paper": "paper", "sections": "paper/sections"}}
    root = _resolve_paper_root(tmp_path, config)
    assert root == (tmp_path / "paper").resolve()


def test_resolve_paper_root_fallback_convention(tmp_path: Path):
    """When paths.paper is missing, the function tries common conventions."""
    (tmp_path / "paper").mkdir()
    config = {}
    root = _resolve_paper_root(tmp_path, config)
    assert root == (tmp_path / "paper").resolve()


def test_resolve_paper_root_none_when_no_match(tmp_path: Path):
    assert _resolve_paper_root(tmp_path, {}) is None


# ── seldon_audit happy paths ─────────────────────────────────────────────────

@patch("seldon.paper.audit_dispatch.dispatch", side_effect=_fake_dispatch)
def test_audit_full_sweep_writes_all_gates(_mock, tmp_path: Path):
    section = _make_project(tmp_path)
    result = seldon_audit(
        section=str(section),
        project_dir=str(tmp_path),
        gates="all",
    )
    assert "complete: 00_abstract" in result
    # All 5 gates ran
    run_dirs = list((tmp_path / "paper" / "audits").iterdir())
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]
    assert run_dir.name.startswith("run-001_")
    section_run = run_dir / "00_abstract"
    expected_gates = {
        "content_audit", "practitioner_stress_test", "argument_completeness",
        "bloom_depth_check", "secondary_sweep",
    }
    written = {p.stem for p in section_run.glob("*.yaml")}
    assert written == expected_gates


@patch("seldon.paper.audit_dispatch.dispatch", side_effect=_fake_dispatch)
def test_audit_single_gate_filter(_mock, tmp_path: Path):
    section = _make_project(tmp_path)
    seldon_audit(
        section=str(section),
        project_dir=str(tmp_path),
        gates="content_audit",
    )
    run_dir = next((tmp_path / "paper" / "audits").iterdir())
    written = list((run_dir / "00_abstract").glob("*.yaml"))
    assert [p.name for p in written] == ["content_audit.yaml"]


@patch("seldon.paper.audit_dispatch.dispatch", side_effect=_fake_dispatch)
def test_audit_manifest_records_metadata(_mock, tmp_path: Path):
    section = _make_project(tmp_path)
    seldon_audit(
        section=str(section),
        project_dir=str(tmp_path),
        gates="content_audit,argument_completeness",
    )
    run_dir = next((tmp_path / "paper" / "audits").iterdir())
    manifest = yaml.safe_load((run_dir / "run_manifest.yaml").read_text())
    rm = manifest["run_manifest"]
    assert rm["run_id"].startswith("run-")
    assert rm["pipeline"] == "AD-019 + AD-020"
    assert rm["sections_audited"] == ["00_abstract"]
    assert set(rm["gates_run"]) == {"content_audit", "argument_completeness"}
    assert rm["gates_failed"] == []
    assert rm["findings_summary"]["content_audit"] == 2


@patch("seldon.paper.audit_dispatch.dispatch", side_effect=_fake_dispatch)
def test_audit_explicit_run_id_override(_mock, tmp_path: Path):
    section = _make_project(tmp_path)
    seldon_audit(
        section=str(section),
        project_dir=str(tmp_path),
        gates="content_audit",
        run_id="run-042",
    )
    run_dir = next((tmp_path / "paper" / "audits").iterdir())
    assert run_dir.name.startswith("run-042_")


@patch("seldon.paper.audit_dispatch.dispatch", side_effect=_fake_dispatch)
def test_audit_increments_past_existing(_mock, tmp_path: Path):
    section = _make_project(tmp_path)
    audits = tmp_path / "paper" / "audits"
    audits.mkdir(parents=True)
    (audits / "run-003_2026-04-18").mkdir()
    seldon_audit(
        section=str(section),
        project_dir=str(tmp_path),
        gates="content_audit",
    )
    new_run = sorted(audits.iterdir())[-1]
    assert new_run.name.startswith("run-004_")


# ── seldon_audit error / edge cases ──────────────────────────────────────────

def test_audit_missing_section_returns_error(tmp_path: Path):
    _make_project(tmp_path)
    result = seldon_audit(
        section="paper/sections/does_not_exist.md",
        project_dir=str(tmp_path),
        gates="content_audit",
    )
    assert result.startswith("Error: section file not found")


def test_audit_invalid_gate_returns_error(tmp_path: Path):
    section = _make_project(tmp_path)
    result = seldon_audit(
        section=str(section),
        project_dir=str(tmp_path),
        gates="not_a_real_gate",
    )
    assert result.startswith("Error: unknown gate")


def test_audit_no_paper_root_returns_error(tmp_path: Path):
    (tmp_path / "seldon.yaml").write_text(
        "project:\n  name: test\n  domain: research\n"
        "neo4j:\n  database: " + TEST_DATABASE + "\n  uri: bolt://localhost:7687\n"
        "event_store:\n  path: seldon_events.jsonl\n"
    )
    section = tmp_path / "random.md"
    section.write_text("orphan\n")
    result = seldon_audit(
        section=str(section),
        project_dir=str(tmp_path),
        gates="content_audit",
    )
    assert result.startswith("Error: cannot resolve paper root")


@patch("seldon.paper.audit_dispatch.dispatch")
def test_audit_per_gate_error_isolated(mock_dispatch, tmp_path: Path):
    """One gate failing must not prevent other gates from running."""
    section = _make_project(tmp_path)
    call_count = {"n": 0}

    def flaky(prompt, system=None, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("simulated provider 500")
        return _fake_dispatch(prompt, system=system, **kwargs)

    mock_dispatch.side_effect = flaky
    result = seldon_audit(
        section=str(section),
        project_dir=str(tmp_path),
        gates="content_audit,practitioner_stress_test,argument_completeness",
    )
    run_dir = next((tmp_path / "paper" / "audits").iterdir())
    manifest = yaml.safe_load((run_dir / "run_manifest.yaml").read_text())
    rm = manifest["run_manifest"]
    assert len(rm["gates_run"]) == 2
    assert len(rm["gates_failed"]) == 1
    assert rm["gates_failed"][0]["gate"] == "practitioner_stress_test"
    assert "simulated provider 500" in rm["gates_failed"][0]["error"]
    # The two successful gates' YAMLs are on disk
    written = {p.stem for p in (run_dir / "00_abstract").glob("*.yaml")}
    assert written == {"content_audit", "argument_completeness"}
    assert "✗" in result  # summary text shows the failure


@patch("seldon.paper.audit_dispatch.dispatch", side_effect=_fake_dispatch)
def test_audit_model_override_restores_env(_mock, tmp_path: Path, monkeypatch):
    """Passing audit_model temporarily sets AUDIT_MODEL and restores it."""
    section = _make_project(tmp_path)
    monkeypatch.setenv("AUDIT_MODEL", "anthropic/original")
    seldon_audit(
        section=str(section),
        project_dir=str(tmp_path),
        gates="content_audit",
        audit_model="gemini/temporary",
    )
    import os
    assert os.environ.get("AUDIT_MODEL") == "anthropic/original"


@patch("seldon.paper.audit_dispatch.dispatch", side_effect=_fake_dispatch)
def test_audit_model_override_unsets_when_no_prior(_mock, tmp_path: Path, monkeypatch):
    """If AUDIT_MODEL was unset before, override is cleaned up after."""
    section = _make_project(tmp_path)
    monkeypatch.delenv("AUDIT_MODEL", raising=False)
    seldon_audit(
        section=str(section),
        project_dir=str(tmp_path),
        gates="content_audit",
        audit_model="gemini/temporary",
    )
    import os
    assert "AUDIT_MODEL" not in os.environ


@patch("seldon.paper.audit_dispatch.dispatch", side_effect=lambda *a, **kw: "this is not yaml :::: {{{")
def test_audit_malformed_yaml_does_not_crash(_mock, tmp_path: Path):
    """Garbage YAML from the model must not abort the run."""
    section = _make_project(tmp_path)
    result = seldon_audit(
        section=str(section),
        project_dir=str(tmp_path),
        gates="content_audit",
    )
    assert "complete: 00_abstract" in result
    run_dir = next((tmp_path / "paper" / "audits").iterdir())
    # Raw output still written
    assert (run_dir / "00_abstract" / "content_audit.yaml").exists()
    # Manifest doesn't crash; findings_summary may omit this gate
    manifest = yaml.safe_load((run_dir / "run_manifest.yaml").read_text())
    assert manifest["run_manifest"]["gates_run"] == ["content_audit"]
