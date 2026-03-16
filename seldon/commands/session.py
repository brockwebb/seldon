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
from seldon.commands.docs import run_docs_check


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

    start_session(project_dir)

    with driver.session(database=database) as session:
        # 1. Open tasks
        open_task_records = session.run(
            "MATCH (t:ResearchTask) WHERE t.state IN ['proposed','accepted','in_progress','blocked'] "
            "RETURN t ORDER BY t.created_at"
        ).data()
        open_tasks = [dict(r["t"]) for r in open_task_records]

        for t in open_tasks:
            blocked = session.run(
                "MATCH (t:ResearchTask {artifact_id: $id})-[:BLOCKS]->(target) RETURN target",
                id=t["artifact_id"],
            ).data()
            t["_blocks"] = [dict(r["target"]) for r in blocked]

        # 2. Stale results
        stale = get_stale_artifacts(session)

        # 3. Incomplete provenance: Results with no GENERATED_BY Script and no DERIVED_FROM source
        no_script_records = session.run(
            "MATCH (r:Result) WHERE NOT (r)-[:GENERATED_BY]->(:Script) "
            "AND NOT (r)-[:DERIVED_FROM]->() RETURN r"
        ).data()
        no_script = [dict(r["r"]) for r in no_script_records]

        # 4. Graph stats
        stats = graph_stats(session)

    # 5. Documentation completeness (separate driver session for re-use)
    domain_config = _get_domain_config(config)
    driver2 = get_neo4j_driver(config)
    try:
        docs_data = run_docs_check(driver2, database, domain_config)
    finally:
        driver2.close()

    driver.close()

    width = 50
    border = "═" * width
    click.echo(f"\n{border}")
    click.echo(f"  SELDON BRIEFING — {project_name}")
    click.echo(f"{border}\n")

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

    click.echo(f"\nINCOMPLETE PROVENANCE ({len(no_script)}):")
    if no_script:
        for r in no_script:
            rid = r.get("artifact_id", "?")[:8]
            val = r.get("value", "?")
            desc = r.get("description", "")
            click.echo(f"  ⚠ {rid}...  value={val}  {desc}  (no linked Script)")
    else:
        click.echo("  (none)")

    total_a = docs_data["total_artifacts"]
    fully_a = docs_data["fully_documented"]
    doc_pct = int(fully_a / total_a * 100) if total_a else 0
    click.echo(f"\nDOCUMENTATION: {fully_a}/{total_a} artifacts fully documented ({doc_pct}%)")
    # Highlight types with most gaps
    gap_counts = {
        atype: len(td["incomplete"])
        for atype, td in docs_data["by_type"].items()
        if td["incomplete"]
    }
    for atype, gap_n in sorted(gap_counts.items(), key=lambda x: -x[1])[:2]:
        click.echo(f"  ⚠ {gap_n} {atype} artifact{'s' if gap_n != 1 else ''} missing docs")

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

    all_events = read_events(project_dir)
    if session_id:
        session_events = [e for e in all_events if e.get("session_id") == session_id]
    else:
        session_events = []

    created = [e for e in session_events if e["event_type"] == "artifact_created"]
    transitions = [e for e in session_events if e["event_type"] == "artifact_state_changed"]
    links = [e for e in session_events if e["event_type"] == "link_created"]

    type_counts: dict = {}
    for e in created:
        atype = e.get("payload", {}).get("artifact_type", "unknown")
        type_counts[atype] = type_counts.get(atype, 0) + 1
    type_summary = ", ".join(f"{cnt} {t}" for t, cnt in sorted(type_counts.items()))

    from datetime import datetime, timezone
    ended_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

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
