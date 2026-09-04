"""`seldon task` — ResearchTask lifecycle CLI.

Mirrors the MCP task tools (`seldon_task_*`) so that a Desktop thread and a terminal
session drive the same state machine through the same code. The close walk, the
terminal-state rules and the claim marker all live in `seldon.core.artifacts`; this
module is argument parsing and presentation only (AD-028).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import click

from seldon.config import load_project_config, get_neo4j_driver, get_current_session
from seldon.core.artifacts import (
    create_artifact,
    create_link,
    open_states,
    resolve_artifact_id,
    transition_task,
    walk_to_completed,
)
from seldon.core.graph import get_artifact
from seldon.domain.loader import load_domain_config

# Actor recorded on events written by this CLI. The MCP tools write 'desktop'.
CLI_ACTOR = "human"

ARTIFACT_TYPE = "ResearchTask"


def _get_domain_config(config: dict):
    domain_name = config["project"].get("domain", "research")
    domain_yaml = Path(__file__).parent.parent / "domain" / f"{domain_name}.yaml"
    return load_domain_config(domain_yaml)


def _open_project():
    """Open the project config, driver, domain config and session for a task command.

    Returns:
        Tuple of (project_dir, driver, database, domain_config, session_id).
    """
    config = load_project_config()
    project_dir = Path.cwd()
    driver = get_neo4j_driver(config)
    domain_config = _get_domain_config(config)
    database = config["neo4j"]["database"]
    session_id = get_current_session(project_dir)
    return project_dir, driver, database, domain_config, session_id


def _load_task(driver, database, task_id: str):
    """Resolve a task id or prefix and load its node.

    Args:
        driver: Neo4j driver.
        database: Database name.
        task_id: Full artifact_id or unambiguous prefix.

    Returns:
        Tuple of (full_artifact_id, node properties dict).

    Raises:
        SystemExit: With a diagnostic on stderr if the id is unknown or ambiguous.
    """
    try:
        full_id = resolve_artifact_id(driver, database, task_id)
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        driver.close()
        raise SystemExit(1)

    with driver.session(database=database) as session:
        node = get_artifact(session, full_id)
    if node is None:
        click.echo(f"Error: Task '{task_id}' not found", err=True)
        driver.close()
        raise SystemExit(1)
    return full_id, node


def _terminal_transition(task_id, new_state, reason, superseded_by):
    """Shared body for `task withdraw` and `task supersede`.

    Args:
        task_id: Full artifact_id or unambiguous prefix.
        new_state: Terminal state to move to ('withdrawn' or 'superseded').
        reason: Operator-supplied reason, stored as `terminal_reason`.
        superseded_by: Optional artifact id the task was superseded by.

    Raises:
        SystemExit: With a diagnostic on stderr on any validation failure. Nothing
            is written to the event store or the graph in that case.
    """
    project_dir, driver, database, domain_config, session_id = _open_project()
    try:
        full_id, node = _load_task(driver, database, task_id)
        old_state = node["state"]
        transition_task(
            project_dir=project_dir, driver=driver, database=database,
            domain_config=domain_config, artifact_id=full_id,
            current_state=old_state, new_state=new_state,
            actor=CLI_ACTOR, authority="accepted", session_id=session_id,
            terminal_reason=reason, superseded_by=superseded_by,
        )
        click.echo(f"Updated Task: {full_id[:8]}...")
        click.echo(f"  state: {old_state} → {new_state}")
        click.echo(f"  reason: {reason}")
        if superseded_by:
            click.echo(f"  superseded_by: {superseded_by}")
    except Exception as e:
        # Reported, never swallowed: transition_task validates every precondition
        # before its first write, so a failure here left the graph untouched.
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
    finally:
        driver.close()


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


def _parse_claimed_at(raw) -> datetime | None:
    """Parse a stored `claimed_at` value into an aware UTC datetime.

    Args:
        raw: The property value read from the graph (ISO-8601 string, a Neo4j
            temporal, or None).

    Returns:
        An aware UTC datetime, or None when the value is absent or unparseable.
    """
    if raw is None:
        return None
    text = raw.isoformat() if hasattr(raw, "isoformat") else str(raw)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@task_group.command("list")
@click.option("--state", default=None, help="Filter by one specific state")
@click.option(
    "--open", "open_only", is_flag=True,
    help="Show only open tasks. Same set as the default; kept for explicitness.",
)
@click.option(
    "--all", "show_all", is_flag=True,
    help="Include terminal and completed tasks, which the default view hides.",
)
@click.option(
    "--stale-claims", "stale_claims", type=float, default=None, metavar="HOURS",
    help="Report in_progress tasks claimed more than HOURS ago. Report only — "
         "no task is transitioned or released.",
)
def task_list(state, open_only, show_all, stale_claims):
    """List ResearchTask artifacts.

    By default this shows only *open* tasks — those from which live work is still
    possible. Terminal states (verified/rejected/superseded/withdrawn) and
    `completed` are hidden unless `--all` or an explicit `--state` is given. The open
    set is derived from the domain config's state machine, not hardcoded, so a
    terminal state added to `research.yaml` drops out of this view automatically.
    """
    config = load_project_config()
    driver = get_neo4j_driver(config)
    domain_config = _get_domain_config(config)
    database = config["neo4j"]["database"]

    selected = [f for f in (state, open_only, show_all, stale_claims is not None) if f]
    if len(selected) > 1:
        click.echo(
            "Error: --state, --open, --all and --stale-claims are mutually exclusive.",
            err=True,
        )
        driver.close()
        raise SystemExit(1)

    open_set = open_states(domain_config, ARTIFACT_TYPE)
    cutoff = None
    if stale_claims is not None:
        if stale_claims < 0:
            click.echo("Error: --stale-claims HOURS must not be negative.", err=True)
            driver.close()
            raise SystemExit(1)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=stale_claims)

    with driver.session(database=database) as session:
        if show_all:
            records = session.run(
                "MATCH (t:ResearchTask) RETURN t ORDER BY t.created_at"
            ).data()
        elif state:
            records = session.run(
                "MATCH (t:ResearchTask {state: $state}) RETURN t ORDER BY t.created_at",
                state=state,
            ).data()
        elif stale_claims is not None:
            records = session.run(
                "MATCH (t:ResearchTask {state: 'in_progress'}) RETURN t ORDER BY t.created_at"
            ).data()
        else:
            records = session.run(
                "MATCH (t:ResearchTask) WHERE t.state IN $states RETURN t ORDER BY t.created_at",
                states=open_set,
            ).data()
        tasks = [dict(r["t"]) for r in records]

        for t in tasks:
            tid = t["artifact_id"]
            t["blocks_count"] = session.run(
                "MATCH (t:ResearchTask {artifact_id: $id})-[:BLOCKS]->(x) RETURN count(x) AS c",
                id=tid,
            ).single()["c"]
            t["depends_count"] = session.run(
                "MATCH (t:ResearchTask {artifact_id: $id})-[:DEPENDS_ON]->(x) RETURN count(x) AS c",
                id=tid,
            ).single()["c"]

    driver.close()

    unmarked = 0
    if stale_claims is not None:
        stale = []
        for t in tasks:
            claimed_at = _parse_claimed_at(t.get("claimed_at"))
            if claimed_at is None:
                unmarked += 1
            elif claimed_at < cutoff:
                stale.append(t)
        tasks = stale

    if not tasks:
        if stale_claims is not None:
            click.echo(f"No in_progress tasks claimed more than {stale_claims}h ago.")
            if unmarked:
                click.echo(
                    f"  ({unmarked} in_progress task(s) carry no claim marker — "
                    f"claimed before claim tracking existed, or claimed by a path "
                    f"that does not record it.)"
                )
            return
        click.echo("No tasks found.")
        return

    if stale_claims is not None:
        click.echo(
            f"Stale claims (in_progress, claimed > {stale_claims}h ago): {len(tasks)}"
        )
        click.echo("Report only — no task has been transitioned or released.")

    click.echo(f"{'ID':10} {'STATE':14} {'BLOCKS':7} {'DEPS':5} {'CLAIM':28} DESCRIPTION")
    click.echo("-" * 110)
    for t in tasks:
        tid = t.get("artifact_id", "?")[:8]
        st = (t.get("state") or "?")[:13]
        bc = t.get("blocks_count", 0)
        dc = t.get("depends_count", 0)
        desc = (t.get("description") or "")[:40]
        claim = ""
        if t.get("state") == "in_progress":
            by = t.get("claimed_by") or "?"
            at = t.get("claimed_at")
            at_text = str(at)[:19] if at else "?"
            claim = f"{by}@{at_text}"[:27]
        click.echo(f"{tid:<10} {st:<14} {bc:<7} {dc:<5} {claim:<28} {desc}")

    if stale_claims is not None and unmarked:
        click.echo(
            f"\n{unmarked} further in_progress task(s) carry no claim marker and "
            f"cannot be aged."
        )


@task_group.command("update")
@click.argument("task_id")
@click.option("--state", required=True, help="New state to transition to")
@click.option(
    "--reason", default=None,
    help="Why the task ended. Required for --state withdrawn and --state superseded.",
)
@click.option(
    "--superseded-by", "superseded_by", default=None, metavar="ARTIFACT_ID",
    help="Artifact that overtook this task. Only valid with --state superseded.",
)
@click.option(
    "--claimed-by", "claimed_by", default=None, metavar="AGENT",
    help=f"Agent identifier recorded on the accepted → in_progress transition "
         f"(default: '{CLI_ACTOR}').",
)
def task_update(task_id, state, reason, superseded_by, claimed_by):
    """Transition a ResearchTask to a new state.

    `withdrawn` and `superseded` require `--reason`; the reason is stored as
    `terminal_reason` on the task. The `accepted → in_progress` transition records
    `claimed_by` and `claimed_at`.
    """
    project_dir, driver, database, domain_config, session_id = _open_project()
    try:
        full_id, node = _load_task(driver, database, task_id)
        old_state = node["state"]

        transition_task(
            project_dir=project_dir, driver=driver, database=database,
            domain_config=domain_config, artifact_id=full_id,
            current_state=old_state, new_state=state,
            actor=CLI_ACTOR, authority="accepted", session_id=session_id,
            claimed_by=claimed_by, terminal_reason=reason,
            superseded_by=superseded_by,
        )
        click.echo(f"Updated Task: {full_id[:8]}...")
        click.echo(f"  state: {old_state} → {state}")
        if reason:
            click.echo(f"  reason: {reason}")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
    finally:
        driver.close()


@task_group.command("close")
@click.argument("task_id")
@click.option("--note", default=None, help="Note explaining why the task is closed")
def task_close(task_id, note):
    """Close a ResearchTask by walking it from its current state to completed.

    Identical state walk to the MCP `seldon_task_close` tool — both call
    `seldon.core.artifacts.walk_to_completed`, so both emit the same event sequence.
    """
    project_dir, driver, database, domain_config, session_id = _open_project()
    try:
        full_id, node = _load_task(driver, database, task_id)
        old_state = node["state"]
        desc = (node.get("description") or "")[:60]

        if old_state == "completed":
            click.echo(f"Already completed: {full_id[:8]}... — {desc}")
            return

        transitions = walk_to_completed(
            project_dir=project_dir, driver=driver, database=database,
            domain_config=domain_config, artifact_id=full_id,
            current_state=old_state, actor=CLI_ACTOR, session_id=session_id,
        )
        click.echo(f"Closed: {full_id[:8]}... — {desc}")
        click.echo(f"  path: {old_state} → " + " → ".join(
            t.split(" → ")[1] for t in transitions
        ))
        if note:
            click.echo(f"  note: {note}")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
    finally:
        driver.close()


@task_group.command("withdraw")
@click.argument("task_id")
@click.option("--reason", required=True, help="Why the task's premise no longer holds")
def task_withdraw(task_id, reason):
    """Withdraw a ResearchTask: its premise turned out to be false.

    Terminal. Reachable only from an open state — a completed or verified task is
    never relabelled, because that would corrupt the honest completion record.
    """
    _terminal_transition(task_id, "withdrawn", reason, None)


@task_group.command("supersede")
@click.argument("task_id")
@click.option("--reason", required=True, help="What overtook this task, and why")
@click.option(
    "--superseded-by", "superseded_by", default=None, metavar="ARTIFACT_ID",
    help="Artifact (task, AD, design note or result) that overtook this task. "
         "Validated: an unknown id or an illegal edge endpoint is a hard error "
         "and the task's state is left unchanged.",
)
def task_supersede(task_id, reason, superseded_by):
    """Supersede a ResearchTask: the work was valid but something else overtook it.

    Terminal. Reachable only from an open state. With `--superseded-by` a
    `superseded_by` edge is written from this task to the artifact that overtook it.
    """
    _terminal_transition(task_id, "superseded", reason, superseded_by)


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
