"""CLI commands for Issue artifact management."""

from __future__ import annotations

from pathlib import Path

import click

from seldon.config import load_project_config, get_neo4j_driver, get_current_session
from seldon.core.artifacts import (
    create_artifact, create_link, transition_state, update_artifact,
)
from seldon.core.graph import get_artifact, find_any_artifact_by_name
from seldon.core.issue_utils import (
    ISSUE_ENUMS, eisenhower_quadrant, validate_issue_enum,
)
from seldon.domain.loader import load_domain_config


def _get_domain_config(config: dict):
    domain_name = config["project"].get("domain", "research")
    domain_yaml = Path(__file__).parent.parent / "domain" / f"{domain_name}.yaml"
    return load_domain_config(domain_yaml)


def _resolve_artifact(driver, database, identifier: str) -> dict | None:
    """Resolve an artifact by UUID or name."""
    with driver.session(database=database) as session:
        node = get_artifact(session, identifier)
        if node is not None:
            return node
        try:
            return find_any_artifact_by_name(session, identifier)
        except ValueError:
            return None


@click.group("issue")
def issue_group():
    """Manage Issue artifacts — track document quality problems."""
    pass


@issue_group.command("create")
@click.option("--description", required=True, help="What the issue is")
@click.option("--type", "issue_type", required=True, help="Category: " + ", ".join(ISSUE_ENUMS["issue_type"]))
@click.option("--importance", required=True, help="high, medium, low")
@click.option("--urgency", required=True, help="high, medium, low")
@click.option("--detection", required=True, help="How found: " + ", ".join(ISSUE_ENUMS["detection_method"]))
@click.option("--target", required=True, help="What to fix: " + ", ".join(ISSUE_ENUMS["target"]))
@click.option("--affects", default=None, help="Comma-separated artifact IDs/names this issue affects")
def issue_create(description, issue_type, importance, urgency, detection, target, affects):
    """Create a new Issue."""
    try:
        validate_issue_enum("issue_type", issue_type)
        validate_issue_enum("importance", importance)
        validate_issue_enum("urgency", urgency)
        validate_issue_enum("detection_method", detection)
        validate_issue_enum("target", target)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)

    config = load_project_config()
    project_dir = Path.cwd()
    driver = get_neo4j_driver(config)
    domain_config = _get_domain_config(config)
    database = config["neo4j"]["database"]
    session_id = get_current_session(project_dir)

    try:
        issue_id = create_artifact(
            project_dir=project_dir, driver=driver, database=database,
            domain_config=domain_config, artifact_type="Issue",
            properties={
                "description": description,
                "issue_type": issue_type,
                "importance": importance,
                "urgency": urgency,
                "detection_method": detection,
                "target": target,
            },
            actor="human", authority="accepted",
            session_id=session_id,
        )

        links_created = []
        if affects:
            for ref in affects.split(","):
                ref = ref.strip()
                if not ref:
                    continue
                target_node = _resolve_artifact(driver, database, ref)
                if target_node is None:
                    click.echo(f"Warning: artifact '{ref}' not found — skipping AFFECTS link", err=True)
                    continue
                create_link(
                    project_dir=project_dir, driver=driver, database=database,
                    domain_config=domain_config,
                    from_id=issue_id, to_id=target_node["artifact_id"],
                    from_type="Issue", to_type=target_node["artifact_type"],
                    rel_type="affects", actor="human", authority="accepted",
                    session_id=session_id,
                )
                links_created.append(f"AFFECTS {target_node.get('name', target_node['artifact_id'][:8])}")

        quadrant = eisenhower_quadrant(importance, urgency)
        click.echo(f"Created Issue: {issue_id}")
        click.echo(f"  description: {description}")
        click.echo(f"  type: {issue_type}")
        click.echo(f"  quadrant: {quadrant} (importance={importance}, urgency={urgency})")
        click.echo(f"  detection: {detection}")
        click.echo(f"  target: {target}")
        click.echo(f"  state: open")
        if links_created:
            click.echo(f"  links: {', '.join(links_created)}")

    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
    finally:
        driver.close()


# ── Importance/urgency sort key ──────────────────────────────────────────────

_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _sort_key(issue: dict) -> tuple:
    """Sort issues: importance desc, then urgency desc."""
    return (
        _PRIORITY_ORDER.get(issue.get("importance", "low"), 3),
        _PRIORITY_ORDER.get(issue.get("urgency", "low"), 3),
    )


@issue_group.command("list")
@click.option("--open", "open_only", is_flag=True, help="Show issues in open/in_progress/blocked states")
@click.option("--state", default=None, help="Filter by specific state")
@click.option("--importance", default=None, help="Filter by importance (high/medium/low)")
@click.option("--urgency", default=None, help="Filter by urgency (high/medium/low)")
@click.option("--type", "issue_type", default=None, help="Filter by issue_type")
def issue_list(open_only, state, importance, urgency, issue_type):
    """List Issue artifacts."""
    config = load_project_config()
    driver = get_neo4j_driver(config)
    database = config["neo4j"]["database"]

    OPEN_STATES = ["open", "in_progress", "blocked"]

    with driver.session(database=database) as session:
        if open_only:
            records = session.run(
                "MATCH (i:Issue) WHERE i.state IN $states RETURN i",
                states=OPEN_STATES,
            ).data()
        elif state:
            records = session.run(
                "MATCH (i:Issue {state: $state}) RETURN i",
                state=state,
            ).data()
        else:
            records = session.run("MATCH (i:Issue) RETURN i").data()

    driver.close()

    issues = [dict(r["i"]) for r in records]

    # Apply client-side filters
    if importance:
        issues = [i for i in issues if i.get("importance") == importance]
    if urgency:
        issues = [i for i in issues if i.get("urgency") == urgency]
    if issue_type:
        issues = [i for i in issues if i.get("issue_type") == issue_type]

    issues.sort(key=_sort_key)

    if not issues:
        click.echo("No issues found.")
        return

    click.echo(f"{'ID':10} {'STATE':12} {'IMP':6} {'URG':6} {'QUADRANT':10} {'TYPE':25} DESCRIPTION")
    click.echo("-" * 100)
    for i in issues:
        iid = i.get("artifact_id", "?")[:8]
        st = (i.get("state") or "?")[:11]
        imp = (i.get("importance") or "?")[:5]
        urg = (i.get("urgency") or "?")[:5]
        quad = eisenhower_quadrant(
            i.get("importance", ""), i.get("urgency", "")
        )[:9]
        itype = (i.get("issue_type") or "?")[:24]
        desc = (i.get("description") or "")[:40]
        click.echo(f"{iid:<10} {st:<12} {imp:<6} {urg:<6} {quad:<10} {itype:<25} {desc}")


@issue_group.command("update")
@click.argument("issue_id")
@click.option("--state", default=None, help="New state to transition to")
@click.option("--urgency", default=None, help="Update urgency (high/medium/low)")
@click.option("--resolution-notes", default=None, help="Notes on how the issue was resolved")
def issue_update(issue_id, state, urgency, resolution_notes):
    """Update an Issue — transition state or change urgency."""
    if state is None and urgency is None and resolution_notes is None:
        click.echo("Error: provide --state, --urgency, or --resolution-notes", err=True)
        raise SystemExit(1)

    config = load_project_config()
    project_dir = Path.cwd()
    driver = get_neo4j_driver(config)
    domain_config = _get_domain_config(config)
    database = config["neo4j"]["database"]
    session_id = get_current_session(project_dir)

    with driver.session(database=database) as sess:
        node = get_artifact(sess, issue_id)

    if node is None:
        click.echo(f"Error: Issue '{issue_id}' not found", err=True)
        driver.close()
        raise SystemExit(1)

    try:
        # Property updates (urgency, resolution_notes)
        props = {}
        if urgency:
            validate_issue_enum("urgency", urgency)
            props["urgency"] = urgency
        if resolution_notes:
            props["resolution_notes"] = resolution_notes
        if props:
            update_artifact(
                project_dir=project_dir, driver=driver, database=database,
                artifact_id=issue_id, properties=props,
                actor="human", authority="accepted",
                session_id=session_id,
            )

        # State transition
        if state:
            old_state = node["state"]
            transition_state(
                project_dir=project_dir, driver=driver, database=database,
                domain_config=domain_config, artifact_id=issue_id,
                artifact_type="Issue", current_state=old_state, new_state=state,
                actor="human", authority="accepted",
                session_id=session_id,
            )
            click.echo(f"Updated Issue: {issue_id[:8]}...")
            click.echo(f"  state: {old_state} → {state}")
        else:
            click.echo(f"Updated Issue: {issue_id[:8]}...")

        if urgency:
            new_quad = eisenhower_quadrant(node.get("importance", ""), urgency)
            click.echo(f"  urgency: {node.get('urgency', '?')} → {urgency} (quadrant: {new_quad})")
        if resolution_notes:
            click.echo(f"  resolution_notes: {resolution_notes}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
    finally:
        driver.close()


@issue_group.command("show")
@click.argument("issue_id")
def issue_show(issue_id):
    """Show full detail for an Issue including relationships."""
    config = load_project_config()
    driver = get_neo4j_driver(config)
    database = config["neo4j"]["database"]

    with driver.session(database=database) as session:
        node = get_artifact(session, issue_id)
        if node is None:
            click.echo(f"Error: Issue '{issue_id}' not found", err=True)
            driver.close()
            raise SystemExit(1)

        affects_records = session.run(
            "MATCH (i:Issue {artifact_id: $id})-[:AFFECTS]->(t) RETURN t",
            id=issue_id,
        ).data()
        affects = [dict(r["t"]) for r in affects_records]

        blocked_by_records = session.run(
            "MATCH (i:Issue {artifact_id: $id})-[:BLOCKED_BY]->(t) RETURN t",
            id=issue_id,
        ).data()
        blocked_by = [dict(r["t"]) for r in blocked_by_records]

        related_records = session.run(
            "MATCH (i:Issue {artifact_id: $id})-[:RELATED_ISSUE]-(t) RETURN DISTINCT t",
            id=issue_id,
        ).data()
        related = [dict(r["t"]) for r in related_records]

        resolved_by_records = session.run(
            "MATCH (i:Issue {artifact_id: $id})-[:RESOLVED_BY]->(t) RETURN t",
            id=issue_id,
        ).data()
        resolved_by = [dict(r["t"]) for r in resolved_by_records]

    driver.close()

    imp = node.get("importance", "?")
    urg = node.get("urgency", "?")
    quadrant = eisenhower_quadrant(imp, urg)

    click.echo(f"\nIssue: {issue_id}")
    click.echo(f"  description:      {node.get('description', '(none)')}")
    click.echo(f"  issue_type:       {node.get('issue_type', '?')}")
    click.echo(f"  state:            {node.get('state', '?')}")
    click.echo(f"  importance:       {imp}")
    click.echo(f"  urgency:          {urg}")
    click.echo(f"  quadrant:         {quadrant}")
    click.echo(f"  detection_method: {node.get('detection_method', '?')}")
    click.echo(f"  target:           {node.get('target', '?')}")
    click.echo(f"  created_at:       {node.get('created_at', '?')}")
    if node.get("resolution_notes"):
        click.echo(f"  resolution_notes: {node['resolution_notes']}")

    if affects:
        click.echo(f"\n  Affects ({len(affects)}):")
        for a in affects:
            atype = a.get("artifact_type", "?")
            aname = a.get("name") or a.get("artifact_id", "?")[:8]
            click.echo(f"    → [{atype}] {aname}")
    else:
        click.echo(f"\n  Affects: none")

    if blocked_by:
        click.echo(f"\n  Blocked by ({len(blocked_by)}):")
        for b in blocked_by:
            click.echo(f"    ← [Issue] {b.get('artifact_id', '?')[:8]}... {b.get('description', '')[:40]}")

    if related:
        click.echo(f"\n  Related issues ({len(related)}):")
        for r in related:
            click.echo(f"    ↔ [Issue] {r.get('artifact_id', '?')[:8]}... {r.get('description', '')[:40]}")

    if resolved_by:
        click.echo(f"\n  Resolved by ({len(resolved_by)}):")
        for rb in resolved_by:
            rbtype = rb.get("artifact_type", "?")
            click.echo(f"    → [{rbtype}] {rb.get('artifact_id', '?')[:8]}... {rb.get('description', '')[:40]}")


@issue_group.command("summary")
def issue_summary():
    """Show issue landscape — counts by state, quadrant, type, detection method."""
    config = load_project_config()
    driver = get_neo4j_driver(config)
    database = config["neo4j"]["database"]

    with driver.session(database=database) as session:
        records = session.run("MATCH (i:Issue) RETURN i").data()

    driver.close()

    issues = [dict(r["i"]) for r in records]

    if not issues:
        click.echo("No issues in this project.")
        return

    # Count by state
    state_counts: dict[str, int] = {}
    quadrant_counts: dict[str, int] = {}
    type_counts: dict[str, int] = {}
    detection_counts: dict[str, int] = {}

    for i in issues:
        st = i.get("state", "?")
        state_counts[st] = state_counts.get(st, 0) + 1

        quad = eisenhower_quadrant(i.get("importance", ""), i.get("urgency", ""))
        quadrant_counts[quad] = quadrant_counts.get(quad, 0) + 1

        itype = i.get("issue_type", "?")
        type_counts[itype] = type_counts.get(itype, 0) + 1

        det = i.get("detection_method", "?")
        detection_counts[det] = detection_counts.get(det, 0) + 1

    click.echo(f"Issue Summary ({len(issues)} total)\n")

    click.echo("By state:")
    for st in ["open", "in_progress", "blocked", "resolved", "verified", "wont_fix"]:
        count = state_counts.get(st, 0)
        if count:
            click.echo(f"  {st:<14} {count}")

    click.echo("\nBy Eisenhower quadrant:")
    # Sort by priority order
    quad_order = ["DO NOW", "DO SOON", "ACT SOON", "SCHEDULE", "PLAN", "BACKLOG", "BATCH", "DEFER", "ELIMINATE"]
    for q in quad_order:
        count = quadrant_counts.get(q, 0)
        if count:
            click.echo(f"  {q:<14} {count}")

    click.echo("\nBy issue type:")
    for itype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        click.echo(f"  {itype:<30} {count}")

    click.echo("\nBy detection method:")
    for det, count in sorted(detection_counts.items(), key=lambda x: -x[1]):
        click.echo(f"  {det:<20} {count}")
