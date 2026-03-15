from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import click

from seldon.config import load_project_config, get_neo4j_driver, get_current_session
from seldon.core.artifacts import create_artifact, create_link, transition_state
from seldon.core.graph import get_artifact, get_artifacts_by_type, get_artifacts_by_state, get_provenance_chain, get_stale_artifacts, get_dependents, find_artifact_by_property
from seldon.domain.loader import load_domain_config


def _get_domain_config(config: dict):
    domain_name = config["project"].get("domain", "research")
    domain_yaml = Path(__file__).parent.parent / "domain" / f"{domain_name}.yaml"
    return load_domain_config(domain_yaml)


@click.group("result")
def result_group():
    """Manage Result artifacts — register, verify, trace provenance."""
    pass


@result_group.command("register")
@click.option("--value", required=True, type=float, help="Numeric result value")
@click.option("--units", default="", help="Units of measurement (e.g. 'accuracy', 'ms')")
@click.option("--description", default="", help="Human-readable description")
@click.option("--script-id", default=None, help="UUID of Script that generated this result")
@click.option("--data-ids", default=None, help="Comma-separated UUIDs of DataFile inputs")
@click.option("--script-name", default=None, help="Name of Script artifact (resolved by 'name' property)")
@click.option("--script-path", default=None, help="Path of Script artifact (resolved by 'path' property)")
@click.option("--data-name", default=None, help="Comma-separated names of DataFile artifacts")
@click.option("--requirement-id", default=None, help="UUID of SRS_Requirement this implements")
@click.option("--input-hash", default=None, help="SHA256 hash of input data")
def result_register(value, units, description, script_id, data_ids, script_name, script_path, data_name, requirement_id, input_hash):
    """Register a new Result artifact with optional provenance links."""
    config = load_project_config()
    project_dir = Path.cwd()
    driver = get_neo4j_driver(config)
    domain_config = _get_domain_config(config)
    database = config["neo4j"]["database"]
    session_id = get_current_session(project_dir)

    # Resolve script reference: --script-id takes priority, then --script-name, then --script-path
    resolved_script_id = script_id
    if resolved_script_id is None and script_name:
        with driver.session(database=database) as sess:
            node = find_artifact_by_property(sess, "Script", "name", script_name)
        if node is None:
            click.echo(f"Warning: no Script with name='{script_name}' found. Skipping link.", err=True)
        else:
            resolved_script_id = node["artifact_id"]

    if resolved_script_id is None and script_path:
        with driver.session(database=database) as sess:
            node = find_artifact_by_property(sess, "Script", "path", script_path)
        if node is None:
            click.echo(f"Warning: no Script with path='{script_path}' found. Skipping link.", err=True)
        else:
            resolved_script_id = node["artifact_id"]

    # Resolve data_name → additional data_ids
    resolved_data_names: list[str] = []
    if data_name:
        for dname in data_name.split(","):
            dname = dname.strip()
            if not dname:
                continue
            with driver.session(database=database) as sess:
                node = find_artifact_by_property(sess, "DataFile", "name", dname)
            if node is None:
                click.echo(f"Warning: no DataFile with name='{dname}' found. Skipping link.", err=True)
            else:
                resolved_data_names.append(node["artifact_id"])

    props = {
        "value": value,
        "run_timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if units:
        props["units"] = units
    if description:
        props["description"] = description
    if input_hash:
        props["input_data_hash"] = input_hash

    try:
        result_id = create_artifact(
            project_dir=project_dir, driver=driver, database=database,
            domain_config=domain_config, artifact_type="Result",
            properties=props, actor="human", authority="accepted",
            session_id=session_id,
        )

        links_created = []

        if resolved_script_id:
            create_link(
                project_dir=project_dir, driver=driver, database=database,
                domain_config=domain_config,
                from_id=result_id, to_id=resolved_script_id,
                from_type="Result", to_type="Script",
                rel_type="generated_by", actor="human", authority="accepted",
                session_id=session_id,
            )
            links_created.append(f"GENERATED_BY {resolved_script_id[:8]}...")

        if data_ids:
            for data_id in data_ids.split(","):
                data_id = data_id.strip()
                if data_id:
                    create_link(
                        project_dir=project_dir, driver=driver, database=database,
                        domain_config=domain_config,
                        from_id=result_id, to_id=data_id,
                        from_type="Result", to_type="DataFile",
                        rel_type="computed_from", actor="human", authority="accepted",
                        session_id=session_id,
                    )
                    links_created.append(f"COMPUTED_FROM {data_id[:8]}...")

        for data_id in resolved_data_names:
            create_link(
                project_dir=project_dir, driver=driver, database=database,
                domain_config=domain_config,
                from_id=result_id, to_id=data_id,
                from_type="Result", to_type="DataFile",
                rel_type="computed_from", actor="human", authority="accepted",
                session_id=session_id,
            )
            links_created.append(f"COMPUTED_FROM {data_id[:8]}... (by name)")

        if requirement_id:
            create_link(
                project_dir=project_dir, driver=driver, database=database,
                domain_config=domain_config,
                from_id=result_id, to_id=requirement_id,
                from_type="Result", to_type="SRS_Requirement",
                rel_type="implements", actor="human", authority="accepted",
                session_id=session_id,
            )
            links_created.append(f"IMPLEMENTS {requirement_id[:8]}...")

        click.echo(f"Registered Result: {result_id}")
        click.echo(f"  value: {value} {units}")
        click.echo(f"  state: proposed")
        if links_created:
            click.echo(f"  links: {', '.join(links_created)}")

    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
    finally:
        driver.close()


@result_group.command("verify")
@click.argument("result_id")
def result_verify(result_id):
    """Mark a Result as verified (proposed → verified)."""
    config = load_project_config()
    project_dir = Path.cwd()
    driver = get_neo4j_driver(config)
    domain_config = _get_domain_config(config)
    database = config["neo4j"]["database"]
    session_id = get_current_session(project_dir)

    with driver.session(database=database) as session:
        node = get_artifact(session, result_id)

    if node is None:
        click.echo(f"Error: Result '{result_id}' not found", err=True)
        driver.close()
        raise SystemExit(1)

    try:
        transition_state(
            project_dir=project_dir, driver=driver, database=database,
            domain_config=domain_config, artifact_id=result_id,
            artifact_type="Result", current_state=node["state"], new_state="verified",
            actor="human", authority="accepted",
            session_id=session_id,
        )
        value = node.get("value", "?")
        units = node.get("units", "")
        click.echo(f"Verified Result: {result_id}")
        click.echo(f"  value: {value} {units}")
        click.echo(f"  state: {node['state']} → verified")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
    finally:
        driver.close()


@result_group.command("list")
@click.option("--state", default=None, help="Filter by state (proposed/verified/published/stale)")
def result_list(state):
    """List Result artifacts."""
    config = load_project_config()
    driver = get_neo4j_driver(config)
    database = config["neo4j"]["database"]

    with driver.session(database=database) as session:
        if state:
            records = session.run(
                "MATCH (r:Result {state: $state}) RETURN r ORDER BY r.run_timestamp DESC",
                state=state,
            ).data()
        else:
            records = session.run(
                "MATCH (r:Result) RETURN r ORDER BY r.run_timestamp DESC"
            ).data()
        results = [dict(r["r"]) for r in records]

        for r in results:
            script_rel = session.run(
                "MATCH (r:Result {artifact_id: $id})-[:GENERATED_BY]->(:Script) RETURN r LIMIT 1",
                id=r["artifact_id"],
            ).single()
            r["has_script"] = script_rel is not None
            data_rel = session.run(
                "MATCH (r:Result {artifact_id: $id})-[:COMPUTED_FROM]->(:DataFile) RETURN r LIMIT 1",
                id=r["artifact_id"],
            ).single()
            r["has_data"] = data_rel is not None

    driver.close()

    if not results:
        click.echo("No results found.")
        return

    click.echo(f"{'ID':10} {'VALUE':10} {'UNITS':12} {'STATE':12} {'SCRIPT':7} {'DATA':5} DESCRIPTION")
    click.echo("-" * 80)
    for r in results:
        rid = r.get("artifact_id", "?")[:8]
        val = str(r.get("value", "?"))[:9]
        units = (r.get("units") or "")[:11]
        st = (r.get("state") or "?")[:11]
        has_s = "yes" if r.get("has_script") else "no"
        has_d = "yes" if r.get("has_data") else "no"
        desc = (r.get("description") or "")[:30]
        click.echo(f"{rid:<10} {val:<10} {units:<12} {st:<12} {has_s:<7} {has_d:<5} {desc}")


@result_group.command("trace")
@click.argument("result_id")
def result_trace(result_id):
    """Show full provenance chain for a Result (upstream + downstream citations)."""
    config = load_project_config()
    driver = get_neo4j_driver(config)
    database = config["neo4j"]["database"]

    with driver.session(database=database) as session:
        node = get_artifact(session, result_id)
        if node is None:
            click.echo(f"Error: Result '{result_id}' not found", err=True)
            driver.close()
            raise SystemExit(1)

        upstream = get_provenance_chain(session, result_id)
        downstream = session.run(
            "MATCH (s:PaperSection)-[:CITES]->(r:Result {artifact_id: $id}) RETURN s",
            id=result_id,
        ).data()
        cited_by = [dict(r["s"]) for r in downstream]

    driver.close()

    val = node.get("value", "?")
    units = node.get("units", "")
    click.echo(f"\nResult: {result_id}")
    click.echo(f"  value: {val} {units}  state: {node.get('state', '?')}")

    if upstream:
        click.echo(f"\nProvenance (upstream):")
        for a in upstream:
            atype = a.get("artifact_type", "?")
            aid = a.get("artifact_id", "?")[:8]
            astate = a.get("state", "?")
            click.echo(f"  ← [{atype}] {aid}... ({astate})")
    else:
        click.echo("\nProvenance: none (no upstream links)")

    if cited_by:
        click.echo(f"\nCited by ({len(cited_by)} sections):")
        for s in cited_by:
            sid = s.get("artifact_id", "?")[:8]
            sstate = s.get("state", "?")
            click.echo(f"  → [PaperSection] {sid}... ({sstate})")
    else:
        click.echo("\nCited by: no sections")


@result_group.command("check-stale")
def result_check_stale():
    """List stale Results and what downstream artifacts they block."""
    config = load_project_config()
    driver = get_neo4j_driver(config)
    database = config["neo4j"]["database"]

    with driver.session(database=database) as session:
        stale = get_stale_artifacts(session)

        if not stale:
            click.echo("No stale results.")
            driver.close()
            return

        click.echo(f"Stale Results ({len(stale)}):\n")
        for r in stale:
            rid = r.get("artifact_id", "?")
            val = r.get("value", "?")
            units = r.get("units", "")
            click.echo(f"  ⚠ {rid[:8]}...  value={val} {units}")

            dependents = get_dependents(session, rid)
            if dependents:
                for d in dependents:
                    dtype = d.get("artifact_type", "?")
                    did = d.get("artifact_id", "?")[:8]
                    dstate = d.get("state", "?")
                    click.echo(f"      blocks: [{dtype}] {did}... ({dstate})")

    driver.close()
