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
