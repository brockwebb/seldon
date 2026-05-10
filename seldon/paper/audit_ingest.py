"""Ingest AD-020 audit run directories into the Seldon graph.

Handles the three on-disk layouts observed in the SFV paper audits:
  - flat:    audits/<run>/section-NN_<gate>.yaml
  - grouped: audits/<run>/<gate>.yaml  (all sections in one file; e.g. run-002)
  - nested:  audits/<run>/<section_slug>/<gate>.yaml  (e.g. run-003+)

Creates AuditRun + AuditFinding artifacts and wires `has_finding`,
`finding_in`, and `audited_in` edges. Best-effort YAML parsing — gates
that fail to parse cleanly are noted in the manifest but do not abort.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Gate names recognized in audit run directories. cascade_results is read for
# context (synthesis) but not converted to AuditFindings.
KNOWN_GATES = (
    "content_audit",
    "practitioner_stress_test",
    "argument_completeness",
    "bloom_depth_check",
    "secondary_sweep",
)

VALID_SEVERITIES = {"blocking", "high", "medium", "low", "cosmetic"}


@dataclass
class IngestFinding:
    """In-memory representation of a finding before it's written to the graph."""
    finding_id: str
    finding_type: str
    severity: str
    gate: str
    text: str
    section_slug: str
    classification: str | None = None
    citation_status: str | None = None
    notes: str | None = None


@dataclass
class IngestPlan:
    """Outcome of scanning a run directory before any graph writes."""
    run_id: str
    date: str
    model: str
    pipeline: str
    document_type: str
    layout: str
    run_dir: Path
    sections: list[str] = field(default_factory=list)
    findings: list[IngestFinding] = field(default_factory=list)
    gate_warnings: list[str] = field(default_factory=list)
    sweep_synthesis: str | None = None
    manifest_notes: str | None = None
    raw_manifest: dict[str, Any] = field(default_factory=dict)


# ── Layout detection ─────────────────────────────────────────────────────────

_SECTION_FILE_RE = re.compile(r"^section-(\d{2,})_([a-z_]+)\.yaml$")


def _detect_layout(run_dir: Path) -> str:
    """Return 'nested' | 'flat' | 'grouped'.

    nested:  any subdirectory contains content_audit.yaml
    flat:    any top-level file matches section-NN_<gate>.yaml
    grouped: top-level <gate>.yaml files exist with no per-section subdirs
    """
    for child in run_dir.iterdir():
        if child.is_dir() and (child / "content_audit.yaml").exists():
            return "nested"
    for child in run_dir.iterdir():
        if child.is_file() and _SECTION_FILE_RE.match(child.name):
            return "flat"
    return "grouped"


# ── Manifest parsing ─────────────────────────────────────────────────────────

def _load_manifest(run_dir: Path) -> dict[str, Any]:
    """Read run_manifest.yaml. Returns the inner run_manifest dict if wrapped."""
    manifest_path = run_dir / "run_manifest.yaml"
    if not manifest_path.exists():
        raise FileNotFoundError(f"run_manifest.yaml not found in {run_dir}")
    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    if isinstance(raw, dict) and "run_manifest" in raw and isinstance(raw["run_manifest"], dict):
        return raw["run_manifest"]
    return raw


def _resolve_sections_for_layout(run_dir: Path, layout: str, manifest: dict) -> list[str]:
    """List section slugs present in the run, per layout."""
    if layout == "nested":
        slugs = [c.name for c in run_dir.iterdir() if c.is_dir()]
        return sorted(slugs)
    if layout == "flat":
        slugs: set[str] = set()
        for child in run_dir.iterdir():
            m = _SECTION_FILE_RE.match(child.name)
            if m:
                slugs.add(f"section-{m.group(1)}")
        return sorted(slugs)
    # grouped — fall back to manifest's `chapters_audited` or the section_id
    # entries from the older overall_summary block
    if "chapters_audited" in manifest:
        return list(manifest["chapters_audited"])
    if "sections" in manifest and isinstance(manifest["sections"], list):
        return [str(s.get("section_id") or s.get("file") or "") for s in manifest["sections"]]
    return []


# ── Gate YAML parsing ────────────────────────────────────────────────────────

_CODE_FENCE_RE = re.compile(r"^```[a-z]*\s*\n|\n```\s*$", re.IGNORECASE)


def _strip_code_fences(text: str) -> str:
    """Strip leading/trailing ```yaml fences if present (Gemini does this)."""
    return _CODE_FENCE_RE.sub("", text.strip()).strip()


def _load_gate_yaml(gate_file: Path) -> Any:
    """Tolerant YAML loader: strips code fences, returns None on parse error."""
    try:
        text = gate_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    text = _strip_code_fences(text)
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError:
        return None


def _default_finding_type(gate: str, raw_finding_type: Any) -> str:
    """Pick a finding_type when the YAML doesn't supply one."""
    if isinstance(raw_finding_type, str) and raw_finding_type and raw_finding_type != "none":
        return raw_finding_type
    if gate == "practitioner_stress_test":
        return "stress_question"
    if gate == "content_audit":
        return "review_finding"
    return "review_finding"


def _normalize_severity(raw: Any) -> str:
    if isinstance(raw, str) and raw.lower() in VALID_SEVERITIES:
        return raw.lower()
    return "low"


def _coerce_text(item: dict) -> str | None:
    for key in ("text", "question", "assertion", "claim", "issue", "finding", "description"):
        v = item.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _extract_findings_from_parsed(
    parsed: Any, gate: str, section_slug: str
) -> list[IngestFinding]:
    """Pull a list of findings out of a parsed gate YAML doc.

    Robust to several shapes seen in practice:
      - content_audit:           {findings: [...]}
      - practitioner_stress_test:{questions: [...]}
      - other gates / Gemini quirks: top-level list of dicts
    """
    if parsed is None:
        return []
    items: list[dict] = []
    if isinstance(parsed, dict):
        for key in ("findings", "questions", "issues", "items"):
            if isinstance(parsed.get(key), list):
                items = [x for x in parsed[key] if isinstance(x, dict)]
                break
        if not items:
            # Gates like argument_completeness sometimes nest under
            # `audit.sections[].findings[]`. Try one level down.
            inner = parsed.get("audit")
            if isinstance(inner, dict) and isinstance(inner.get("sections"), list):
                for section_block in inner["sections"]:
                    if isinstance(section_block, dict) and isinstance(section_block.get("findings"), list):
                        items.extend(x for x in section_block["findings"] if isinstance(x, dict))
    elif isinstance(parsed, list):
        items = [x for x in parsed if isinstance(x, dict)]

    out: list[IngestFinding] = []
    for idx, item in enumerate(items, start=1):
        text = _coerce_text(item)
        if text is None:
            continue
        fid = str(item.get("id") or f"{gate[:2].upper()}-{section_slug[:6]}-{idx:02d}")
        out.append(
            IngestFinding(
                finding_id=fid,
                finding_type=_default_finding_type(gate, item.get("finding_type")),
                severity=_normalize_severity(item.get("severity")),
                gate=gate,
                text=text[:500],  # keep node properties bounded
                section_slug=section_slug,
                classification=item.get("classification") if isinstance(item.get("classification"), str) else None,
                citation_status=item.get("citation_status") if isinstance(item.get("citation_status"), str) else None,
                notes=(item.get("notes") if isinstance(item.get("notes"), str) else None),
            )
        )
    return out


def _scan_gate_files(
    run_dir: Path, layout: str, section_slugs: list[str]
) -> tuple[list[IngestFinding], list[str]]:
    """Return (findings, warnings) by walking gate YAML files per layout."""
    findings: list[IngestFinding] = []
    warnings: list[str] = []

    if layout == "nested":
        for slug in section_slugs:
            section_dir = run_dir / slug
            if not section_dir.is_dir():
                continue
            for gate in KNOWN_GATES:
                gate_file = section_dir / f"{gate}.yaml"
                if not gate_file.exists():
                    continue
                parsed = _load_gate_yaml(gate_file)
                if parsed is None:
                    warnings.append(f"{slug}/{gate}.yaml: unparseable")
                    continue
                findings.extend(_extract_findings_from_parsed(parsed, gate, slug))

    elif layout == "flat":
        # filenames like section-01_content_audit.yaml
        for child in run_dir.iterdir():
            m = _SECTION_FILE_RE.match(child.name)
            if not m:
                continue
            sec_num = m.group(1)
            gate = m.group(2)
            if gate not in KNOWN_GATES:
                continue
            slug = f"section-{sec_num}"
            parsed = _load_gate_yaml(child)
            if parsed is None:
                warnings.append(f"{child.name}: unparseable")
                continue
            findings.extend(_extract_findings_from_parsed(parsed, gate, slug))

    else:  # grouped
        for gate in KNOWN_GATES:
            # Either <gate>.yaml or <gate>_all_sections.yaml (run-002 style)
            for candidate_name in (f"{gate}.yaml", f"{gate}_all_sections.yaml"):
                candidate = run_dir / candidate_name
                if not candidate.exists():
                    continue
                parsed = _load_gate_yaml(candidate)
                if parsed is None:
                    warnings.append(f"{candidate.name}: unparseable")
                    break
                # Grouped files have either a `sections: [{section_id, findings: [...]}]`
                # shape or a single shared list. Try both.
                if isinstance(parsed, dict) and isinstance(parsed.get("sections"), list):
                    for section_block in parsed["sections"]:
                        if not isinstance(section_block, dict):
                            continue
                        slug = str(section_block.get("section_id") or section_block.get("file") or "unknown")
                        slug = Path(slug).stem if "/" in slug else slug
                        findings.extend(_extract_findings_from_parsed(section_block, gate, slug))
                else:
                    findings.extend(_extract_findings_from_parsed(parsed, gate, "all_sections"))
                break  # don't double-count if both naming variants exist

    return findings, warnings


# ── sweep synthesis ─────────────────────────────────────────────────────────

def _read_sweep_synthesis(run_dir: Path) -> str | None:
    """Return the first 2000 chars of sweep_synthesis.md if present."""
    for name in ("sweep_synthesis.md", "review_synthesis.yaml"):
        path = run_dir / name
        if path.exists():
            return path.read_text(encoding="utf-8")[:2000]
    return None


# ── Plan builder ─────────────────────────────────────────────────────────────

def plan_ingest(run_dir: Path) -> IngestPlan:
    """Inspect a run directory and produce an IngestPlan without touching the graph."""
    run_dir = run_dir.resolve()
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Run directory not found: {run_dir}")
    manifest = _load_manifest(run_dir)
    layout = _detect_layout(run_dir)
    sections = _resolve_sections_for_layout(run_dir, layout, manifest)
    findings, warnings = _scan_gate_files(run_dir, layout, sections)
    sweep = _read_sweep_synthesis(run_dir)

    run_id = str(manifest.get("run_id") or run_dir.name.split("_")[0])
    return IngestPlan(
        run_id=run_id,
        date=str(manifest.get("date") or ""),
        model=str(manifest.get("model") or manifest.get("baseline_model") or "unknown"),
        pipeline=str(manifest.get("pipeline") or "AD-020"),
        document_type=str(manifest.get("document_type") or "academic_paper"),
        layout=layout,
        run_dir=run_dir,
        sections=sections,
        findings=findings,
        gate_warnings=warnings,
        sweep_synthesis=sweep,
        manifest_notes=(manifest.get("notes") if isinstance(manifest.get("notes"), str) else None),
        raw_manifest=manifest,
    )


# ── Graph wiring ─────────────────────────────────────────────────────────────

def _audit_run_exists(driver, database: str, run_id: str) -> str | None:
    """Return artifact_id of an existing AuditRun with this run_id, or None."""
    with driver.session(database=database) as session:
        rec = session.run(
            "MATCH (r:Artifact:AuditRun {run_id: $rid}) RETURN r.artifact_id AS id LIMIT 1",
            rid=run_id,
        ).single()
    return rec["id"] if rec else None


def _find_paper_section_by_slug(driver, database: str, slug: str) -> str | None:
    """Match PaperSection by `name` equal to the slug. Returns artifact_id or None."""
    with driver.session(database=database) as session:
        rec = session.run(
            "MATCH (s:Artifact:PaperSection {name: $slug}) RETURN s.artifact_id AS id LIMIT 1",
            slug=slug,
        ).single()
    return rec["id"] if rec else None


def write_ingest(
    plan: IngestPlan,
    project_dir: Path,
    driver,
    database: str,
    domain_config,
    actor: str = "desktop",
    advance_states: bool = False,
) -> dict[str, Any]:
    """Apply an IngestPlan to the graph.

    Returns a summary dict with counts and any per-section state transitions.
    Idempotent: if an AuditRun with the same run_id already exists, returns
    early with action='already_ingested'.
    """
    from seldon.core.artifacts import create_artifact, create_link, transition_state

    existing_run_id = _audit_run_exists(driver, database, plan.run_id)
    if existing_run_id is not None:
        return {
            "action": "already_ingested",
            "run_id": plan.run_id,
            "existing_artifact_id": existing_run_id,
        }

    # 1. Create AuditRun artifact
    rel_run_dir = ""
    try:
        rel_run_dir = str(plan.run_dir.relative_to(project_dir))
    except ValueError:
        rel_run_dir = str(plan.run_dir)

    # Neo4j accepts primitives + arrays only — JSON-encode the summary dict
    audit_run_props = {
        "name": plan.run_id,
        "run_id": plan.run_id,
        "date": plan.date,
        "model": plan.model,
        "pipeline": plan.pipeline,
        "document_type": plan.document_type,
        "run_dir": rel_run_dir,
        "gates_run": sorted({f.gate for f in plan.findings}),
        "findings_summary": json.dumps(_findings_summary(plan.findings), sort_keys=True),
    }
    if plan.manifest_notes:
        audit_run_props["notes"] = plan.manifest_notes[:1000]
    if plan.sweep_synthesis:
        audit_run_props["sweep_synthesis"] = plan.sweep_synthesis

    audit_run_id = create_artifact(
        project_dir=project_dir, driver=driver, database=database,
        domain_config=domain_config, artifact_type="AuditRun",
        properties=audit_run_props,
        actor=actor, authority="accepted",
    )

    # Move AuditRun: proposed -> completed (state machine reflects terminal record)
    transition_state(
        project_dir=project_dir, driver=driver, database=database,
        domain_config=domain_config, artifact_id=audit_run_id,
        artifact_type="AuditRun",
        current_state="proposed", new_state="completed",
        actor=actor, authority="accepted",
    )

    # 2. Sections that exist in the graph get audited_in edges. Use the union
    # of plan.sections (from manifest/layout) and the section_slugs that
    # appear on the findings themselves — grouped layouts often omit the
    # manifest-level section list but the gate YAML still names sections.
    candidate_slugs = set(plan.sections) | {f.section_slug for f in plan.findings if f.section_slug}
    section_artifact_ids: dict[str, str] = {}
    for slug in candidate_slugs:
        sid = _find_paper_section_by_slug(driver, database, slug)
        if sid:
            section_artifact_ids[slug] = sid
            create_link(
                project_dir=project_dir, driver=driver, database=database,
                domain_config=domain_config,
                from_id=sid, to_id=audit_run_id,
                from_type="PaperSection", to_type="AuditRun",
                rel_type="audited_in", actor=actor, authority="accepted",
            )

    # 3. AuditFinding artifacts + edges
    findings_written = 0
    sections_missing: set[str] = set()
    for f in plan.findings:
        finding_props = {
            "name": f.finding_id,
            "finding_id": f.finding_id,
            "finding_type": f.finding_type,
            "severity": f.severity,
            "gate": f.gate,
            "text": f.text,
            "section_slug": f.section_slug,
        }
        if f.classification:
            finding_props["classification"] = f.classification
        if f.citation_status:
            finding_props["citation_status"] = f.citation_status
        if f.notes:
            finding_props["notes"] = f.notes[:1000]

        finding_id = create_artifact(
            project_dir=project_dir, driver=driver, database=database,
            domain_config=domain_config, artifact_type="AuditFinding",
            properties=finding_props,
            actor=actor, authority="accepted",
        )
        transition_state(
            project_dir=project_dir, driver=driver, database=database,
            domain_config=domain_config, artifact_id=finding_id,
            artifact_type="AuditFinding",
            current_state="proposed", new_state="open",
            actor=actor, authority="accepted",
        )
        findings_written += 1

        create_link(
            project_dir=project_dir, driver=driver, database=database,
            domain_config=domain_config,
            from_id=audit_run_id, to_id=finding_id,
            from_type="AuditRun", to_type="AuditFinding",
            rel_type="has_finding", actor=actor, authority="accepted",
        )
        section_id = section_artifact_ids.get(f.section_slug)
        if section_id:
            create_link(
                project_dir=project_dir, driver=driver, database=database,
                domain_config=domain_config,
                from_id=finding_id, to_id=section_id,
                from_type="AuditFinding", to_type="PaperSection",
                rel_type="finding_in", actor=actor, authority="accepted",
            )
        else:
            sections_missing.add(f.section_slug)

    # 4. Optional state advance
    state_changes: list[dict] = []
    if advance_states:
        for slug, sid in section_artifact_ids.items():
            high_open = any(
                f.section_slug == slug and f.severity in ("blocking", "high")
                for f in plan.findings
            )
            if high_open:
                state_changes.append({"section": slug, "action": "skipped", "reason": "high-severity findings present"})
                continue
            current_state = _get_section_state(driver, database, sid)
            if current_state in (None, "audited"):
                state_changes.append({"section": slug, "action": "no_change", "reason": f"current_state={current_state}"})
                continue
            try:
                transition_state(
                    project_dir=project_dir, driver=driver, database=database,
                    domain_config=domain_config, artifact_id=sid,
                    artifact_type="PaperSection",
                    current_state=current_state, new_state="audited",
                    actor=actor, authority="accepted",
                )
                state_changes.append({"section": slug, "action": "advanced", "from": current_state, "to": "audited"})
            except Exception as exc:
                state_changes.append({"section": slug, "action": "failed", "error": str(exc)})

    return {
        "action": "ingested",
        "run_id": plan.run_id,
        "audit_run_id": audit_run_id,
        "sections_linked": len(section_artifact_ids),
        "sections_total": len(plan.sections),
        "sections_missing_in_graph": sorted(sections_missing),
        "findings_written": findings_written,
        "gate_warnings": plan.gate_warnings,
        "state_changes": state_changes,
    }


def _get_section_state(driver, database: str, section_id: str) -> str | None:
    with driver.session(database=database) as session:
        rec = session.run(
            "MATCH (s:Artifact {artifact_id: $id}) RETURN s.state AS state",
            id=section_id,
        ).single()
    return rec["state"] if rec else None


def _findings_summary(findings: list[IngestFinding]) -> dict[str, int]:
    """Return counts by severity and by finding_type."""
    out: dict[str, int] = {"total": len(findings)}
    for sev in VALID_SEVERITIES:
        n = sum(1 for f in findings if f.severity == sev)
        if n:
            out[f"sev_{sev}"] = n
    type_counts: dict[str, int] = {}
    for f in findings:
        type_counts[f.finding_type] = type_counts.get(f.finding_type, 0) + 1
    for ftype, n in type_counts.items():
        out[f"type_{ftype}"] = n
    return out
