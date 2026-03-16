from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import click

from seldon.config import load_project_config, get_neo4j_driver
from seldon.domain.loader import load_domain_config


def _get_domain_config(config: dict):
    domain_name = config["project"].get("domain", "research")
    domain_yaml = Path(__file__).parent.parent / "domain" / f"{domain_name}.yaml"
    return load_domain_config(domain_yaml)


def _artifact_display_name(artifact: dict) -> str:
    return artifact.get("name") or artifact.get("artifact_id", "?")[:8]


def run_docs_check(
    driver,
    database: str,
    domain_config,
    artifact_type_filter: Optional[str] = None,
) -> Dict:
    """
    Query graph and check documentation property completeness.

    Returns a dict with:
      - by_type: {type_name: {"complete": [...], "incomplete": [{name, missing}]}}
      - total_artifacts: int
      - fully_documented: int
      - required_total: int
      - required_present: int
      - doc_total: int
      - doc_present: int
    """
    result = {
        "by_type": {},
        "total_artifacts": 0,
        "fully_documented": 0,
        "required_total": 0,
        "required_present": 0,
        "doc_total": 0,
        "doc_present": 0,
    }

    types_to_check = (
        [artifact_type_filter]
        if artifact_type_filter
        else list(domain_config.artifact_types.keys())
    )

    with driver.session(database=database) as session:
        for atype in types_to_check:
            doc_props = domain_config.get_documentation_properties(atype)
            req_props = domain_config.get_required_properties(atype)

            records = session.run(
                f"MATCH (a:Artifact:{atype}) RETURN a"
            ).data()
            artifacts = [dict(r["a"]) for r in records]

            if not artifacts and not doc_props:
                continue

            type_result = {"complete": [], "incomplete": []}

            for artifact in artifacts:
                result["total_artifacts"] += 1

                # Required properties (track for stats only — validation enforces at creation)
                for rp in req_props:
                    result["required_total"] += 1
                    if rp in artifact and str(artifact[rp]).strip():
                        result["required_present"] += 1

                # Documentation properties
                missing_doc = []
                for dp in doc_props:
                    result["doc_total"] += 1
                    if dp in artifact and str(artifact[dp]).strip():
                        result["doc_present"] += 1
                    else:
                        missing_doc.append(dp)

                name = _artifact_display_name(artifact)
                if missing_doc:
                    type_result["incomplete"].append({"name": name, "missing": missing_doc})
                else:
                    type_result["complete"].append(name)
                    if not missing_doc:
                        result["fully_documented"] += 1

            if type_result["complete"] or type_result["incomplete"]:
                result["by_type"][atype] = type_result

    return result


@click.group("docs")
def docs_group():
    """Documentation completeness checking and generation."""
    pass


@docs_group.command("check")
@click.option("--type", "artifact_type", default=None,
              help="Filter to one artifact type.")
@click.option("--strict", is_flag=True, default=False,
              help="Exit code 1 if any documentation gaps.")
@click.option("--threshold", type=int, default=None,
              help="Exit code 1 if documentation completeness below N percent.")
@click.option("--json", "output_json", is_flag=True, default=False,
              help="Machine-readable JSON output.")
def docs_check(artifact_type, strict, threshold, output_json):
    """Report documentation property completeness for all artifacts."""
    config = load_project_config()
    driver = get_neo4j_driver(config)
    domain_config = _get_domain_config(config)

    try:
        data = run_docs_check(driver, config["neo4j"]["database"], domain_config, artifact_type)
    finally:
        driver.close()

    if output_json:
        click.echo(json.dumps(data, indent=2))
        return

    total = data["total_artifacts"]
    fully = data["fully_documented"]
    doc_total = data["doc_total"]
    doc_present = data["doc_present"]
    req_total = data["required_total"]
    req_present = data["required_present"]

    if total == 0:
        click.echo("No artifacts found.")
        return

    click.echo("\nDOCUMENTATION COMPLETENESS")
    click.echo("══════════════════════════\n")

    has_gaps = False
    for atype, type_data in sorted(data["by_type"].items()):
        count = len(type_data["complete"]) + len(type_data["incomplete"])
        click.echo(f"{atype} ({count} artifact{'s' if count != 1 else ''}):")
        for item in type_data["incomplete"]:
            has_gaps = True
            missing_str = ", ".join(item["missing"])
            click.echo(f"  ✗ {item['name']} — missing: {missing_str}")
        for name in type_data["complete"]:
            click.echo(f"  ✓ {name} — complete")
        click.echo("")

    pct = int(fully / total * 100) if total else 0
    click.echo(f"SUMMARY: {fully}/{total} artifacts fully documented ({pct}%)")
    if req_total:
        req_pct = int(req_present / req_total * 100)
        click.echo(f"  Required properties: {req_present}/{req_total} complete ({req_pct}%)")
    if doc_total:
        doc_pct = int(doc_present / doc_total * 100)
        click.echo(f"  Documentation properties: {doc_present}/{doc_total} complete ({doc_pct}%)")
    click.echo("")

    if strict and has_gaps:
        raise SystemExit(1)
    if threshold is not None and pct < threshold:
        raise SystemExit(1)


def _generate_docs(driver, database: str, domain_config, output_dir: Path) -> List[str]:
    """Generate documentation markdown files from graph data. Returns list of generated paths."""
    output_dir.mkdir(parents=True, exist_ok=True)
    generated = []
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    header = (
        f"<!-- Generated by `seldon docs generate` on {ts} -->\n"
        "<!-- Do not edit manually. Update artifact properties in the graph, then regenerate. -->\n\n"
    )

    with driver.session(database=database) as session:
        # Pull all artifacts
        records = session.run("MATCH (a:Artifact) RETURN a").data()
        all_artifacts = [dict(r["a"]) for r in records]

        # Pull relationships for provenance
        rel_records = session.run(
            "MATCH (a:Artifact)-[r]->(b:Artifact) RETURN a.artifact_id as from_id, "
            "type(r) as rel, b.artifact_id as to_id, b.artifact_type as to_type"
        ).data()

    # Index by type
    by_type: Dict[str, List[dict]] = {}
    by_id: Dict[str, dict] = {}
    for a in all_artifacts:
        atype = a.get("artifact_type", "Unknown")
        by_type.setdefault(atype, []).append(a)
        by_id[a.get("artifact_id", "")] = a

    # Index relationships
    rels_from: Dict[str, List[dict]] = {}
    rels_to: Dict[str, List[dict]] = {}
    for r in rel_records:
        rels_from.setdefault(r["from_id"], []).append(r)
        rels_to.setdefault(r["to_id"], []).append(r)

    def _prop(a: dict, key: str, fallback: str = "*not documented*") -> str:
        v = a.get(key)
        return str(v) if v is not None and str(v).strip() else fallback

    # ── scripts_reference.md ──────────────────────────────────────────────────
    scripts = by_type.get("Script", [])
    path = output_dir / "scripts_reference.md"
    lines = [header, "# Scripts Reference\n\n"]
    if scripts:
        for s in sorted(scripts, key=lambda x: x.get("name", "")):
            name = _prop(s, "name", s.get("artifact_id", "?")[:8])
            lines.append(f"## {name}\n\n")
            lines.append(f"- **Path:** {_prop(s, 'path')}\n")
            lines.append(f"- **Description:** {_prop(s, 'description')}\n")
            lines.append(f"- **Inputs:** {_prop(s, 'inputs')}\n")
            lines.append(f"- **Outputs:** {_prop(s, 'outputs')}\n")
            lines.append(f"- **Parameters:** {_prop(s, 'parameters')}\n")
            lines.append(f"- **Usage:** {_prop(s, 'usage')}\n")
            lines.append(f"- **Dependencies:** {_prop(s, 'dependencies')}\n")
            lines.append(f"- **State:** {_prop(s, 'state')}\n\n")
    else:
        lines.append("*No Script artifacts in graph.*\n")
    path.write_text("".join(lines))
    generated.append(str(path))

    # ── data_dictionary.md ────────────────────────────────────────────────────
    datafiles = by_type.get("DataFile", [])
    path = output_dir / "data_dictionary.md"
    lines = [header, "# Data Dictionary\n\n"]
    if datafiles:
        for d in sorted(datafiles, key=lambda x: x.get("name", "")):
            name = _prop(d, "name", d.get("artifact_id", "?")[:8])
            lines.append(f"## {name}\n\n")
            lines.append(f"- **Path:** {_prop(d, 'path')}\n")
            lines.append(f"- **Format:** {_prop(d, 'format')}\n")
            lines.append(f"- **Schema:** {_prop(d, 'schema_description')}\n")
            lines.append(f"- **Provenance:** {_prop(d, 'provenance_description')}\n")
            lines.append(f"- **Row count:** {_prop(d, 'row_count')}\n\n")
    else:
        lines.append("*No DataFile artifacts in graph.*\n")
    path.write_text("".join(lines))
    generated.append(str(path))

    # ── results_registry.md ───────────────────────────────────────────────────
    results = by_type.get("Result", [])
    path = output_dir / "results_registry.md"
    lines = [header, "# Results Registry\n\n"]
    if results:
        for r in sorted(results, key=lambda x: x.get("name", x.get("artifact_id", ""))):
            name = _prop(r, "name", r.get("artifact_id", "?")[:8])
            rid = r.get("artifact_id", "")
            lines.append(f"## {name}\n\n")
            lines.append(f"- **Value:** {_prop(r, 'value')} {r.get('units', '')}\n")
            lines.append(f"- **Description:** {_prop(r, 'description')}\n")
            lines.append(f"- **Interpretation:** {_prop(r, 'interpretation')}\n")
            lines.append(f"- **Methodology:** {_prop(r, 'methodology_note')}\n")
            lines.append(f"- **State:** {_prop(r, 'state')}\n")
            # Provenance links
            for rel in rels_from.get(rid, []):
                target = by_id.get(rel["to_id"], {})
                tname = _prop(target, "name", rel["to_id"][:8])
                lines.append(f"- **{rel['rel'].replace('_', ' ').title()}:** {tname}\n")
            lines.append("\n")
    else:
        lines.append("*No Result artifacts in graph.*\n")
    path.write_text("".join(lines))
    generated.append(str(path))

    # ── experiment_catalog.md ─────────────────────────────────────────────────
    path = output_dir / "experiment_catalog.md"
    lines = [header, "# Experiment Catalog\n\n"]
    if scripts:
        for s in sorted(scripts, key=lambda x: x.get("name", "")):
            sid = s.get("artifact_id", "")
            name = _prop(s, "name", sid[:8])
            lines.append(f"## {name}\n\n")
            lines.append(f"**Description:** {_prop(s, 'description')}\n\n")
            lines.append(f"**Parameters:** {_prop(s, 'parameters')}\n\n")
            # Results generated by this script
            generated_results = [
                by_id[rel["from_id"]]
                for rel in rels_to.get(sid, [])
                if rel["rel"] == "GENERATED_BY" and rel["from_id"] in by_id
            ]
            if generated_results:
                lines.append("**Results:**\n\n")
                for res in generated_results:
                    rname = _prop(res, "name", res.get("artifact_id", "?")[:8])
                    val = res.get("value", "?")
                    units = res.get("units", "")
                    state = res.get("state", "?")
                    lines.append(f"- `{rname}`: {val} {units} ({state})\n")
                lines.append("\n")
            else:
                lines.append("**Results:** *none linked*\n\n")
    else:
        lines.append("*No Script artifacts in graph.*\n")
    path.write_text("".join(lines))
    generated.append(str(path))

    # ── reproduction_guide.md ─────────────────────────────────────────────────
    pipeline_runs = by_type.get("PipelineRun", [])
    path = output_dir / "reproduction_guide.md"
    lines = [header, "# Reproduction Guide\n\n"]
    if pipeline_runs:
        for pr in pipeline_runs:
            prid = pr.get("artifact_id", "")
            lines.append(f"## Run {prid[:8]}\n\n")
            # Find linked script
            script_links = [
                by_id[rel["to_id"]]
                for rel in rels_from.get(prid, [])
                if rel["rel"] == "PRODUCED_BY" and rel["to_id"] in by_id
            ]
            if script_links:
                sname = _prop(script_links[0], "name", script_links[0].get("artifact_id", "?")[:8])
                lines.append(f"- **Script:** {sname}\n")
            lines.append(f"- **Timestamp:** {_prop(pr, 'run_timestamp')}\n")
            lines.append(f"- **Environment:** {_prop(pr, 'environment')}\n")
            lines.append(f"- **Runtime:** {_prop(pr, 'runtime')}\n")
            lines.append(f"- **Command:** `{_prop(pr, 'reproduction_command')}`\n\n")
    else:
        lines.append(
            "*No PipelineRun artifacts in graph.*\n\n"
            "To reproduce experiments, add PipelineRun artifacts via `seldon artifact create PipelineRun`.\n"
        )
    path.write_text("".join(lines))
    generated.append(str(path))

    return generated


@docs_group.command("generate")
@click.option("--output-dir", "output_dir", default="docs",
              help="Output directory for generated files (default: docs/).")
def docs_generate(output_dir):
    """Generate reference documentation from the graph into a docs/ directory."""
    config = load_project_config()
    driver = get_neo4j_driver(config)
    domain_config = _get_domain_config(config)
    out_path = Path(output_dir)

    try:
        generated = _generate_docs(driver, config["neo4j"]["database"], domain_config, out_path)
    finally:
        driver.close()

    click.echo("Generated:")
    for p in generated:
        click.echo(f"  {p}")
