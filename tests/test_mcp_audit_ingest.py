"""Tests for `seldon_audit_ingest` MCP tool and the audit_ingest helpers.

The plan_ingest path is fully exercised against synthetic fixtures (no graph).
The write_ingest path is exercised against the seldon-test Neo4j database.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from seldon.paper import audit_ingest
from seldon.paper.audit_ingest import (
    IngestFinding,
    _detect_layout,
    _extract_findings_from_parsed,
    _findings_summary,
    _normalize_severity,
    _strip_code_fences,
    plan_ingest,
)


# ── Helpers: synthetic run-dir builders ──────────────────────────────────────

def _write_yaml(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _build_nested_run(tmp_path: Path, run_id: str = "run-003", date: str = "2026-04-18") -> Path:
    """Layout used by run-003+: audits/<run>/<section_slug>/<gate>.yaml"""
    run_dir = tmp_path / "audits" / f"{run_id}_{date}"
    run_dir.mkdir(parents=True)
    _write_yaml(run_dir / "run_manifest.yaml", {
        "run_manifest": {
            "run_id": run_id,
            "date": date,
            "model": "claude-opus-4-6",
            "pipeline": "AD-019 + AD-020",
            "document_type": "academic_paper",
            "chapters_audited": ["06_classical_crosswalk", "07_operationalization"],
            "notes": "Test run manifest with notes.",
        }
    })
    # Section 06: content_audit with 2 findings + practitioner_stress_test with 1 question
    _write_yaml(run_dir / "06_classical_crosswalk" / "content_audit.yaml", {
        "section": "06_classical_crosswalk.md",
        "gate": "content_audit",
        "findings_count": 2,
        "findings": [
            {
                "id": "CA-06-01", "text": "Claim about validity.",
                "classification": "judgment", "citation_status": "uncited",
                "finding_type": "citation_gap", "severity": "high", "notes": "Needs citation.",
            },
            {
                "id": "CA-06-02", "text": "Another internal claim.",
                "classification": "judgment", "citation_status": "not_applicable",
                "finding_type": "none", "severity": "cosmetic",
            },
        ],
    })
    _write_yaml(run_dir / "06_classical_crosswalk" / "practitioner_stress_test.yaml", {
        "section": "06_classical_crosswalk.md",
        "gate": "practitioner_stress_test",
        "questions": [
            {"id": "PST-06-01", "question": "How does this distinguish from prior work?",
             "answerability": "partially_answerable", "notes": "Needs more text."}
        ],
    })
    # Section 07: argument_completeness with 1 finding
    _write_yaml(run_dir / "07_operationalization" / "argument_completeness.yaml", {
        "section": "07_operationalization.md",
        "gate": "argument_completeness",
        "findings": [
            {"id": "AC-07-01", "text": "Argument chain has a gap.", "severity": "medium"}
        ],
    })
    return run_dir


def _build_flat_run(tmp_path: Path, run_id: str = "run-001", date: str = "2026-04-13") -> Path:
    """Layout used by run-001: audits/<run>/section-NN_<gate>.yaml"""
    run_dir = tmp_path / "audits" / f"{run_id}_{date}"
    run_dir.mkdir(parents=True)
    _write_yaml(run_dir / "run_manifest.yaml", {
        "run_id": run_id, "date": date, "model": "claude-opus-4-6",
        "document_type": "academic_paper",
    })
    _write_yaml(run_dir / "section-01_content_audit.yaml", {
        "section": "section-01",
        "gate": "content_audit",
        "findings": [
            {"id": "CA-01-01", "text": "Claim 1", "severity": "low"},
            {"id": "CA-01-02", "text": "Claim 2", "severity": "high"},
        ],
    })
    _write_yaml(run_dir / "section-02_content_audit.yaml", {
        "section": "section-02",
        "gate": "content_audit",
        "findings": [
            {"id": "CA-02-01", "text": "Other claim", "severity": "medium"},
        ],
    })
    return run_dir


def _build_grouped_run(tmp_path: Path, run_id: str = "run-002", date: str = "2026-04-17") -> Path:
    """Layout used by run-002: audits/<run>/<gate>_all_sections.yaml"""
    run_dir = tmp_path / "audits" / f"{run_id}_{date}"
    run_dir.mkdir(parents=True)
    _write_yaml(run_dir / "run_manifest.yaml", {
        "run_id": run_id, "date": date, "model": "claude-opus-4-6",
        "document_type": "academic_paper",
        "chapters_audited": ["01_introduction", "02_related_work"],
    })
    _write_yaml(run_dir / "content_audit_all_sections.yaml", {
        "gate": "content_audit",
        "sections": [
            {"section_id": "01_introduction", "findings": [
                {"id": "CA-01-A", "text": "Intro claim", "severity": "low"},
            ]},
            {"section_id": "02_related_work", "findings": [
                {"id": "CA-02-A", "text": "Related-work claim", "severity": "high"},
            ]},
        ],
    })
    return run_dir


# ── _detect_layout ───────────────────────────────────────────────────────────

def test_detect_layout_nested(tmp_path: Path):
    run_dir = _build_nested_run(tmp_path)
    assert _detect_layout(run_dir) == "nested"


def test_detect_layout_flat(tmp_path: Path):
    run_dir = _build_flat_run(tmp_path)
    assert _detect_layout(run_dir) == "flat"


def test_detect_layout_grouped(tmp_path: Path):
    run_dir = _build_grouped_run(tmp_path)
    assert _detect_layout(run_dir) == "grouped"


# ── plan_ingest (no graph) ───────────────────────────────────────────────────

def test_plan_ingest_nested_extracts_findings(tmp_path: Path):
    run_dir = _build_nested_run(tmp_path)
    plan = plan_ingest(run_dir)
    assert plan.run_id == "run-003"
    assert plan.date == "2026-04-18"
    assert plan.model == "claude-opus-4-6"
    assert plan.layout == "nested"
    assert set(plan.sections) == {"06_classical_crosswalk", "07_operationalization"}
    assert len(plan.findings) == 4  # 2 + 1 question + 1
    gates = {f.gate for f in plan.findings}
    assert gates == {"content_audit", "practitioner_stress_test", "argument_completeness"}
    # Stress-test question becomes a stress_question finding
    pst = [f for f in plan.findings if f.gate == "practitioner_stress_test"][0]
    assert pst.finding_type == "stress_question"
    assert pst.text.startswith("How does this distinguish")


def test_plan_ingest_flat_layout(tmp_path: Path):
    run_dir = _build_flat_run(tmp_path)
    plan = plan_ingest(run_dir)
    assert plan.run_id == "run-001"
    assert plan.layout == "flat"
    assert len(plan.findings) == 3
    assert {f.section_slug for f in plan.findings} == {"section-01", "section-02"}


def test_plan_ingest_grouped_layout(tmp_path: Path):
    run_dir = _build_grouped_run(tmp_path)
    plan = plan_ingest(run_dir)
    assert plan.run_id == "run-002"
    assert plan.layout == "grouped"
    assert len(plan.findings) == 2
    assert {f.section_slug for f in plan.findings} == {"01_introduction", "02_related_work"}


def test_plan_ingest_missing_manifest_raises(tmp_path: Path):
    run_dir = tmp_path / "audits" / "run-099_2026-05-10"
    run_dir.mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        plan_ingest(run_dir)


def test_plan_ingest_missing_dir_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        plan_ingest(tmp_path / "does_not_exist")


def test_plan_ingest_unparseable_yaml_warns(tmp_path: Path):
    run_dir = _build_nested_run(tmp_path)
    # Corrupt one gate file
    (run_dir / "06_classical_crosswalk" / "content_audit.yaml").write_text(
        "this is :: not valid :: yaml\n  - {{{{", encoding="utf-8"
    )
    plan = plan_ingest(run_dir)
    # The other gates still produce findings
    assert any("content_audit.yaml: unparseable" in w for w in plan.gate_warnings)
    assert any(f.gate == "practitioner_stress_test" for f in plan.findings)


def test_plan_ingest_strips_code_fences(tmp_path: Path):
    run_dir = _build_nested_run(tmp_path)
    # Gemini-style fenced output
    fenced = "```yaml\nfindings:\n  - id: CA-06-99\n    text: Fenced claim.\n    severity: low\n```\n"
    (run_dir / "06_classical_crosswalk" / "content_audit.yaml").write_text(fenced, encoding="utf-8")
    plan = plan_ingest(run_dir)
    ids = {f.finding_id for f in plan.findings if f.gate == "content_audit"}
    assert "CA-06-99" in ids


# ── Unit helpers ─────────────────────────────────────────────────────────────

def test_strip_code_fences_no_fences():
    assert _strip_code_fences("findings: []") == "findings: []"


def test_strip_code_fences_strips():
    assert _strip_code_fences("```yaml\nkey: 1\n```") == "key: 1"


def test_normalize_severity_valid():
    for sev in ["blocking", "high", "medium", "low", "cosmetic"]:
        assert _normalize_severity(sev) == sev


def test_normalize_severity_invalid_defaults_low():
    assert _normalize_severity("HIGH-ish") == "low"
    assert _normalize_severity(None) == "low"
    assert _normalize_severity(42) == "low"


def test_extract_findings_from_top_level_list():
    parsed = [
        {"id": "X-01", "assertion": "A claim", "severity": "high"},
        {"id": "X-02", "assertion": "Another claim"},  # missing severity
    ]
    findings = _extract_findings_from_parsed(parsed, "secondary_sweep", "01_intro")
    assert len(findings) == 2
    assert findings[0].severity == "high"
    assert findings[1].severity == "low"  # defaulted


def test_extract_findings_handles_audit_sections_nesting():
    """argument_completeness sometimes nests under audit.sections[]."""
    parsed = {
        "audit": {
            "sections": [
                {"section_id": "06", "findings": [
                    {"id": "AC-06-01", "text": "Gap here.", "severity": "medium"}
                ]}
            ]
        }
    }
    findings = _extract_findings_from_parsed(parsed, "argument_completeness", "06")
    assert len(findings) == 1
    assert findings[0].finding_id == "AC-06-01"


def test_findings_summary_counts_severity_and_type():
    fs = [
        IngestFinding("X1", "citation_gap", "high", "content_audit", "t1", "01"),
        IngestFinding("X2", "citation_gap", "low", "content_audit", "t2", "01"),
        IngestFinding("X3", "stress_question", "low", "practitioner_stress_test", "t3", "01"),
    ]
    s = _findings_summary(fs)
    assert s["total"] == 3
    assert s["sev_high"] == 1
    assert s["sev_low"] == 2
    assert s["type_citation_gap"] == 2
    assert s["type_stress_question"] == 1


# ── Graph wiring (Neo4j-backed) ─────────────────────────────────────────────

pytestmark_graph = pytest.mark.usefixtures("neo4j_available")
NEO4J_DB = "seldon-test"


def _write_seldon_yaml(project_dir: Path):
    (project_dir / "seldon.yaml").write_text(
        f"project:\n  name: test\n  domain: research\n"
        f"neo4j:\n  database: {NEO4J_DB}\n  uri: bolt://localhost:7687\n"
        f"event_store:\n  path: seldon_events.jsonl\n"
        f"paths:\n  paper: paper\n  sections: paper/sections\n"
    )


@pytest.fixture
def domain_config():
    from seldon.domain.loader import load_domain_config
    return load_domain_config(Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml")


@pytest.mark.usefixtures("neo4j_available")
def test_write_ingest_creates_run_and_findings(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    from seldon.core.artifacts import create_artifact

    _write_seldon_yaml(project_dir)
    # Pre-create a PaperSection so finding_in/audited_in can wire up
    section_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="PaperSection",
        properties={"name": "06_classical_crosswalk", "title": "Crosswalk", "file_path": "paper/sections/06.md"},
        actor="test", authority="accepted",
    )

    run_dir = _build_nested_run(project_dir)
    plan = plan_ingest(run_dir)
    summary = audit_ingest.write_ingest(
        plan=plan, project_dir=project_dir, driver=neo4j_driver,
        database=NEO4J_DB, domain_config=domain_config, actor="test",
        advance_states=False,
    )

    assert summary["action"] == "ingested"
    assert summary["findings_written"] == 4
    assert summary["sections_linked"] == 1  # only 06 has a graph node
    assert summary["sections_missing_in_graph"] == ["07_operationalization"]

    with neo4j_driver.session(database=NEO4J_DB) as session:
        # AuditRun exists
        rec = session.run(
            "MATCH (r:Artifact:AuditRun {run_id: 'run-003'}) RETURN r.state AS state, r.model AS model"
        ).single()
        assert rec["state"] == "completed"
        assert rec["model"] == "claude-opus-4-6"

        # has_finding count (Neo4j stores rel types uppercased)
        rec = session.run(
            "MATCH (r:Artifact:AuditRun {run_id: 'run-003'})-[:HAS_FINDING]->(f:Artifact:AuditFinding) "
            "RETURN COUNT(f) AS n"
        ).single()
        assert rec["n"] == 4

        # audited_in edge from the one matched section
        rec = session.run(
            "MATCH (s:Artifact:PaperSection {name: '06_classical_crosswalk'})"
            "-[:AUDITED_IN]->(r:Artifact:AuditRun {run_id: 'run-003'}) RETURN COUNT(s) AS n"
        ).single()
        assert rec["n"] == 1

        # finding_in for findings on section 06 only (3 of 4)
        rec = session.run(
            "MATCH (f:Artifact:AuditFinding)-[:FINDING_IN]->(s:Artifact:PaperSection {name: '06_classical_crosswalk'}) "
            "RETURN COUNT(f) AS n"
        ).single()
        assert rec["n"] == 3


@pytest.mark.usefixtures("neo4j_available")
def test_write_ingest_is_idempotent(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    _write_seldon_yaml(project_dir)
    run_dir = _build_nested_run(project_dir)
    plan = plan_ingest(run_dir)

    first = audit_ingest.write_ingest(
        plan=plan, project_dir=project_dir, driver=neo4j_driver,
        database=NEO4J_DB, domain_config=domain_config, actor="test",
    )
    assert first["action"] == "ingested"

    second = audit_ingest.write_ingest(
        plan=plan, project_dir=project_dir, driver=neo4j_driver,
        database=NEO4J_DB, domain_config=domain_config, actor="test",
    )
    assert second["action"] == "already_ingested"
    assert second["existing_artifact_id"] == first["audit_run_id"]


@pytest.mark.usefixtures("neo4j_available")
def test_write_ingest_advances_state_when_no_high_severity(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    from seldon.core.artifacts import create_artifact

    _write_seldon_yaml(project_dir)
    section_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="PaperSection",
        properties={"name": "07_operationalization", "title": "Ops", "file_path": "paper/sections/07.md"},
        actor="test", authority="accepted",
    )
    # 07 only has a single medium-severity finding → eligible for advance
    run_dir = _build_nested_run(project_dir)
    plan = plan_ingest(run_dir)
    summary = audit_ingest.write_ingest(
        plan=plan, project_dir=project_dir, driver=neo4j_driver,
        database=NEO4J_DB, domain_config=domain_config, actor="test",
        advance_states=True,
    )
    advanced = [c for c in summary["state_changes"] if c["action"] == "advanced"]
    assert len(advanced) == 1
    assert advanced[0]["section"] == "07_operationalization"
    assert advanced[0]["to"] == "audited"

    with neo4j_driver.session(database=NEO4J_DB) as session:
        rec = session.run(
            "MATCH (s:Artifact:PaperSection {name: '07_operationalization'}) RETURN s.state AS state"
        ).single()
        assert rec["state"] == "audited"


@pytest.mark.usefixtures("neo4j_available")
def test_write_ingest_skips_state_advance_with_high_severity(
    neo4j_driver, project_dir, domain_config, clean_test_db
):
    from seldon.core.artifacts import create_artifact

    _write_seldon_yaml(project_dir)
    section_id = create_artifact(
        project_dir=project_dir, driver=neo4j_driver, database=NEO4J_DB,
        domain_config=domain_config, artifact_type="PaperSection",
        properties={"name": "06_classical_crosswalk", "title": "Crosswalk", "file_path": "paper/sections/06.md"},
        actor="test", authority="accepted",
    )
    run_dir = _build_nested_run(project_dir)
    plan = plan_ingest(run_dir)
    summary = audit_ingest.write_ingest(
        plan=plan, project_dir=project_dir, driver=neo4j_driver,
        database=NEO4J_DB, domain_config=domain_config, actor="test",
        advance_states=True,
    )
    skipped = [c for c in summary["state_changes"] if c["action"] == "skipped"]
    assert any(c["section"] == "06_classical_crosswalk" for c in skipped)
    with neo4j_driver.session(database=NEO4J_DB) as session:
        rec = session.run(
            "MATCH (s:Artifact:PaperSection {name: '06_classical_crosswalk'}) RETURN s.state AS state"
        ).single()
        assert rec["state"] == "proposed"  # unchanged
