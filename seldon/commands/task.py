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
    BLOCKED_STATE,
    BLOCK_REASON_PROPERTY,
    create_task,
    open_states,
    resolve_artifact_id,
    set_block_reason,
    transition_task,
    walk_to_completed,
)
from seldon.core import cross_project
from seldon.core.graph import get_artifact
from seldon.core import precedence
from seldon.domain.loader import load_domain_config

# Actor recorded on events written by this CLI. The MCP tools write 'desktop'.
CLI_ACTOR = "human"

ARTIFACT_TYPE = "ResearchTask"

#: Marks a task that is open and has no unsatisfied `precedes` predecessor —
#: i.e. one work can start on right now (AD-029).
READY_MARKER = "\u25b8"  # ▸


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
        warnings = transition_task(
            project_dir=project_dir, driver=driver, database=database,
            domain_config=domain_config, artifact_id=full_id,
            current_state=old_state, new_state=new_state,
            actor=CLI_ACTOR, authority="accepted", session_id=session_id,
            terminal_reason=reason, superseded_by=superseded_by,
        )
        for line in warnings:
            click.echo(line, err=True)
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


#: Appended to every refusal of `task create`: since SEL-007 the command validates
#: everything before its first write, so a refusal means the ledger is untouched.
NOTHING_WRITTEN = "Nothing was written: no task was created."


def _split_ids(raw):
    """Comma-separated ids from an option value, blanks dropped."""
    return [part.strip() for part in (raw or "").split(",") if part.strip()]


@task_group.command("create")
@click.option("--description", required=True, help="What needs to be done")
@click.option("--blocks", default=None, help="Comma-separated artifact ids or prefixes this task blocks")
@click.option(
    "--depends-on", "depends_on", default=None,
    help="Comma-separated artifact ids or prefixes this task depends on (a Result, "
         "DataFile, Script or Document). To order tasks, use `seldon task precede`.",
)
def task_create(description, blocks, depends_on):
    """Create a new ResearchTask.

    All or nothing (SEL-007): every --blocks and --depends-on target is resolved
    and every edge validated before the first write, and the task and its links
    are appended to the event log in one write. An unknown target or an illegal
    edge is refused and nothing is created.
    """
    project_dir, driver, database, domain_config, session_id = _open_project()
    links = [("blocks", t) for t in _split_ids(blocks)]
    links += [("depends_on", t) for t in _split_ids(depends_on)]

    try:
        task_id, written = create_task(
            project_dir=project_dir, driver=driver, database=database,
            domain_config=domain_config, description=description, links=links,
            actor=CLI_ACTOR, authority="accepted", session_id=session_id,
        )
    except ValueError as e:
        click.echo(f"Error: {e}\n{NOTHING_WRITTEN}", err=True)
        raise SystemExit(1)
    finally:
        driver.close()

    click.echo(f"Created ResearchTask: {task_id}")
    click.echo(f"  description: {description}")
    click.echo(f"  state: proposed")
    if written:
        click.echo("  links: " + ", ".join(
            f"{rel.upper()} {target[:8]}..." for rel, target in written
        ))


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
                "MATCH (t:Artifact:ResearchTask {artifact_id: $id})"
                f"-[:BLOCKS]->(x:Artifact) RETURN count(x) AS c",
                id=tid,
            ).single()["c"]
            t["depends_count"] = session.run(
                "MATCH (t:Artifact:ResearchTask {artifact_id: $id})"
                f"-[:DEPENDS_ON]->(x:Artifact) RETURN count(x) AS c",
                id=tid,
            ).single()["c"]

        # One pass for the whole `precedes` view (AD-029), shared with the
        # briefing so the two surfaces cannot disagree about what is ready.
        view = precedence.precedence_view(session, open_set)

    driver.close()
    # AD-038-R8: release the cross-project waits whose targets are done, by reading the other graphs.
    cross_project.overlay(view, Path.cwd(), config)

    for t in tasks:
        tid = t["artifact_id"]
        t["waits_on"] = view["waits_on"].get(tid, [])
        t["ready"] = t.get("state") in open_set and not t["waits_on"]

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

    click.echo(
        f"{'':2}{'ID':10} {'STATE':14} {'BLOCKS':7} {'DEPS':5} "
        f"{'WAITS_ON':22} {'CLAIM':28} DESCRIPTION"
    )
    click.echo("-" * 130)
    any_ready = False
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
        waits = t.get("waits_on") or []
        waits_text = ", ".join(precedence.short(w) for w in waits)[:22] or "-"
        marker = READY_MARKER if t.get("ready") else " "
        any_ready = any_ready or bool(t.get("ready"))
        # AD-038-R7: a block says why, on the same line, so the list answers "blocked on what?".
        why = (f"  [blocked: {t.get(BLOCK_REASON_PROPERTY) or 'no reason recorded'}]"
               if t.get("state") == BLOCKED_STATE else "")
        click.echo(
            f"{marker:<2}{tid:<10} {st:<14} {bc:<7} {dc:<5} "
            f"{waits_text:<22} {claim:<28} {desc}{why}"
        )

    if any_ready:
        click.echo(
            f"\n{READY_MARKER} = ready: open, with no unsatisfied predecessor."
        )

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
    help="Why the task ended or is blocked. Required for --state withdrawn, --state "
         "superseded and --state blocked. On a task already blocked, --state blocked "
         "--reason replaces the stored reason and changes nothing else.",
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
    `terminal_reason` on the task. `blocked` is reachable from every open state and
    requires `--reason`, stored as `block_reason` and cleared when the task leaves
    `blocked` (AD-038-R7). The `accepted → in_progress` transition records
    `claimed_by` and `claimed_at`.
    """
    project_dir, driver, database, domain_config, session_id = _open_project()
    blocking = state == BLOCKED_STATE
    try:
        full_id, node = _load_task(driver, database, task_id)
        old_state = node["state"]

        if blocking and old_state == BLOCKED_STATE and not (claimed_by or superseded_by):
            # Already blocked: the reason is replaced, nothing else moves (AD-038-R7).
            set_block_reason(project_dir=project_dir, driver=driver, database=database,
                             artifact_id=full_id, current_state=old_state, block_reason=reason,
                             actor=CLI_ACTOR, session_id=session_id)
            warnings = []
        else:
            warnings = transition_task(
                project_dir=project_dir, driver=driver, database=database,
                domain_config=domain_config, artifact_id=full_id,
                current_state=old_state, new_state=state,
                actor=CLI_ACTOR, authority="accepted", session_id=session_id,
                claimed_by=claimed_by,
                terminal_reason=None if blocking else reason,
                superseded_by=superseded_by,
                block_reason=reason if blocking else None,
            )
        for line in warnings:
            click.echo(line, err=True)
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
            on_warning=lambda line: click.echo(line, err=True),
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


def _precede_body(task_ids, reason, verb):
    """Shared body for `task precede` and `task chain`.

    Args:
        task_ids: Two or more task ids or unambiguous prefixes, in execution order.
        reason: Optional free text stored on every edge written by this call.
        verb: Word used in the output line ('Precedes' or 'Chained').

    Raises:
        SystemExit: With a diagnostic on stderr on any validation failure. The
            whole call is validated before its first write, so a failure here
            means nothing was written.
    """
    project_dir, driver, database, domain_config, session_id = _open_project()
    try:
        result = precedence.add_chain(
            project_dir=project_dir, driver=driver, database=database,
            domain_config=domain_config, task_ids=list(task_ids), reason=reason,
            actor=CLI_ACTOR, authority="accepted", session_id=session_id,
        )
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
    finally:
        driver.close()

    click.echo(f"{verb}: {precedence.render_path(result.resolved)}")
    for before, after in result.created:
        click.echo(f"  + {precedence.short(before)} → {precedence.short(after)}")
    for before, after in result.skipped:
        click.echo(
            f"  = {precedence.short(before)} → {precedence.short(after)} "
            f"(already recorded)"
        )
    if reason and result.created:
        click.echo(f"  reason: {reason}")


@task_group.command("precede")
@click.argument("before_id")
@click.argument("after_id")
@click.option(
    "--reason", default=None,
    help="Why the successor waits on the predecessor. Stored on the edge.",
)
def task_precede(before_id, after_id, reason):
    """Record that BEFORE_ID must finish before AFTER_ID starts.

    Finish-to-start ordering (AD-029). Advisory: nothing is blocked, but the
    successor is reported as waiting until the predecessor is completed,
    verified, superseded or withdrawn.

    The `precedes` subgraph must stay acyclic — an edge that would close a cycle
    is refused and the error names the cycle. Re-running an edge that already
    exists is a no-op.
    """
    _precede_body([before_id, after_id], reason, "Precedes")


@task_group.command("chain")
@click.argument("task_ids", nargs=-1, required=True)
@click.option(
    "--reason", default=None,
    help="Why the tasks are ordered this way. Stored on every edge written.",
)
def task_chain(task_ids, reason):
    """Order a whole sequence of tasks: TASK_IDS in execution order.

    `seldon task chain A B C` writes A → B and B → C. All-or-nothing: if any
    link would be a self-loop or close a cycle, nothing at all is written.
    Existing links are left alone, so re-running a chain is safe.
    """
    if len(task_ids) < 2:
        click.echo(
            "Error: a chain needs at least two tasks.", err=True
        )
        raise SystemExit(1)
    _precede_body(task_ids, reason, "Chained")


@task_group.command("unprecede")
@click.argument("before_id")
@click.argument("after_id")
def task_unprecede(before_id, after_id):
    """Remove the `precedes` edge from BEFORE_ID to AFTER_ID.

    The way an operator retires an ordering that no longer reflects the plan —
    including a chain hanging off a rejected predecessor.
    """
    project_dir, driver, database, domain_config, session_id = _open_project()
    try:
        before, after = precedence.remove_precedence(
            project_dir=project_dir, driver=driver, database=database,
            before_id=before_id, after_id=after_id,
            actor=CLI_ACTOR, authority="accepted", session_id=session_id,
        )
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
    finally:
        driver.close()

    click.echo(
        f"Removed: {precedence.short(before)} → {precedence.short(after)}"
    )


@task_group.command("wait-on")
@click.argument("task_id")
@click.argument("target")
def task_wait_on(task_id, target):
    """Record that TASK_ID waits on TARGET, a task in ANOTHER project's graph.

    TARGET is `<project>:<task-prefix>` (AD-038-R8). The project name resolves
    through this project's seldon.yaml `tasks.projects`, then
    `decisions.repositories`, then the side-by-side convention (`../<project>`).
    One event is written, in THIS project's ledger; the other graph is read and
    never written. A target that resolves to no ResearchTask is refused before
    any write. The wait is satisfied when the target is completed or verified;
    until then the dispatcher holds TASK_ID (c17), and a declared block on it is
    lifted by the dispatcher once every wait is satisfied.
    """
    project_dir, driver, database, domain_config, session_id = _open_project()
    try:
        full_id, _node = _load_task(driver, database, task_id)
        qualified, written = cross_project.add_wait(
            project_dir, driver, database, full_id, target, load_project_config(project_dir),
            actor=CLI_ACTOR, session_id=session_id)
    except ValueError as e:
        click.echo(f"Error: {e}\nNothing was written.", err=True)
        raise SystemExit(1)
    finally:
        driver.close()
    if written:
        click.echo(f"Waits on: {precedence.short(full_id)} ⇢ {precedence.short(qualified)}")
    else:
        click.echo(f"= {precedence.short(full_id)} ⇢ {precedence.short(qualified)} (already recorded)")


@task_group.command("unwait")
@click.argument("task_id")
@click.argument("target")
def task_unwait(task_id, target):
    """Remove TASK_ID's wait on TARGET (`<project>:<task-prefix>`). The target need not resolve."""
    project_dir, driver, database, domain_config, session_id = _open_project()
    try:
        full_id, _node = _load_task(driver, database, task_id)
        removed = cross_project.remove_wait(project_dir, driver, database, full_id, target,
                                            actor=CLI_ACTOR, session_id=session_id)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
    finally:
        driver.close()
    click.echo(f"Removed: {precedence.short(full_id)} ⇢ {precedence.short(removed)}")


@task_group.command("show")
@click.argument("task_id")
def task_show(task_id):
    """Show full detail for a ResearchTask including blocks and depends_on.

    TASK_ID may be a full artifact_id or any unambiguous prefix — the same
    resolution every other `seldon task` command already accepts. `show` is the
    command an operator reaches for after reading an 8-character short id out of
    `task list` or a chain, so requiring the full UUID here made it the one
    command that could not consume the output of the others.
    """
    config = load_project_config()
    driver = get_neo4j_driver(config)
    database = config["neo4j"]["database"]

    full_id, node = _load_task(driver, database, task_id)

    with driver.session(database=database) as session:
        blocked_records = session.run(
            "MATCH (t:Artifact:ResearchTask {artifact_id: $id})"
            "-[:BLOCKS]->(target:Artifact) RETURN target",
            id=full_id,
        ).data()
        blocked = [dict(r["target"]) for r in blocked_records]

        dep_records = session.run(
            "MATCH (t:Artifact:ResearchTask {artifact_id: $id})"
            "-[:DEPENDS_ON]->(dep:Artifact) RETURN dep",
            id=full_id,
        ).data()
        deps = [dict(r["dep"]) for r in dep_records]

        # AD-029 ordering, both directions: `show` is where a reader confirms what a task waits on.
        preceded_by = session.run(
            "MATCH (p:Artifact:ResearchTask)-[:PRECEDES]->(t:Artifact {artifact_id: $id}) "
            "RETURN p.artifact_id AS id, p.state AS state ORDER BY p.created_at", id=full_id).data()
        precedes = session.run(
            "MATCH (t:Artifact {artifact_id: $id})-[:PRECEDES]->(s:Artifact:ResearchTask) "
            "RETURN s.artifact_id AS id, s.state AS state ORDER BY s.created_at", id=full_id).data()

    driver.close()

    waits = list(node.get(cross_project.PROPERTY) or [])
    as_of = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    external = cross_project.read_targets(waits, Path.cwd(), config) if waits else {}

    click.echo(f"\nTask: {full_id}")
    click.echo(f"  description: {node.get('description', '(none)')}")
    click.echo(f"  state:       {node.get('state', '?')}")
    if node.get("state") == BLOCKED_STATE:
        click.echo(f"  blocked:     {node.get(BLOCK_REASON_PROPERTY) or '(no reason recorded)'}")
    click.echo(f"  created_at:  {node.get('created_at', '?')}")

    if preceded_by:
        click.echo(f"\n  Preceded by ({len(preceded_by)}):")
        for p in preceded_by:
            click.echo(f"    ← {precedence.short(p['id'])} ({p['state']})")
    if precedes:
        click.echo(f"\n  Precedes ({len(precedes)}):")
        for p in precedes:
            click.echo(f"    → {precedence.short(p['id'])} ({p['state']})")
    if waits:
        click.echo(f"\n  Waits on, in other projects ({len(waits)}), as of {as_of}:")
        for q in waits:
            st = external.get(q)
            label = (st.name or (st.description or "")[:60]) if st and not st.error else ""
            line = f"    ⇢ {cross_project.render(q, st)} {label}".rstrip()
            if st and st.error:
                line += f" — {st.error}"
            click.echo(line)

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
