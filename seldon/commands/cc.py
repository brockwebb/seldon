"""CC task completion tracking — seldon cc complete."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import click

from seldon.config import load_project_config, get_neo4j_driver, get_current_session
from seldon.core.artifacts import create_artifact, transition_state
from seldon.domain.loader import load_domain_config


def _get_domain_config(config: dict):
    domain_name = config["project"].get("domain", "research")
    domain_yaml = Path(__file__).parent.parent / "domain" / f"{domain_name}.yaml"
    return load_domain_config(domain_yaml)


def _name_from_filepath(filepath: str) -> str:
    """Derive a human-readable name from a CC task filename.

    Strips date prefix (YYYY-MM-DD_), replaces underscores with spaces, drops .md.
    E.g. "cc_tasks/2026-04-03_some_task.md" → "some task"
    """
    stem = Path(filepath).stem  # drop .md
    # Strip leading date prefix YYYY-MM-DD_
    stem = re.sub(r"^\d{4}-\d{2}-\d{2}_", "", stem)
    return stem.replace("_", " ")


def _extract_description(filepath: Path) -> str:
    """Extract first non-blank, non-header line from a CC task file."""
    for line in filepath.read_text().splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped[:200]
    return filepath.name


def _find_existing(driver, database: str, rel_path: str) -> str | None:
    """Return artifact_id of any ResearchTask with matching source_file, or None."""
    with driver.session(database=database) as session:
        record = session.run(
            "MATCH (t:Artifact:ResearchTask {source_file: $sf}) RETURN t.artifact_id AS id",
            sf=rel_path,
        ).single()
    return record["id"] if record else None


def _walk_to_completed(
    project_dir: Path,
    driver,
    database: str,
    domain_config,
    artifact_id: str,
    session_id: str | None,
) -> None:
    """Advance a ResearchTask through proposed→accepted→in_progress→completed."""
    transitions = [
        ("proposed", "accepted"),
        ("accepted", "in_progress"),
        ("in_progress", "completed"),
    ]
    for current, new in transitions:
        transition_state(
            project_dir=project_dir,
            driver=driver,
            database=database,
            domain_config=domain_config,
            artifact_id=artifact_id,
            artifact_type="ResearchTask",
            current_state=current,
            new_state=new,
            actor="cc",
            authority="accepted",
            session_id=session_id,
        )


@click.group("cc")
def cc_group():
    """CC task lifecycle commands."""
    pass


@cc_group.command("complete")
@click.argument("filepath")
@click.option("--note", default=None, help="Override auto-extracted description")
def cc_complete(filepath, note):
    """Record a CC task as completed in the graph.

    Creates a ResearchTask artifact in 'completed' state linked to the task file.
    Running twice on the same file warns instead of creating a duplicate.

    FILEPATH is relative to project root or absolute.
    """
    project_dir = Path.cwd()
    config = load_project_config(project_dir)
    driver = get_neo4j_driver(config)
    database = config["neo4j"]["database"]
    domain_config = _get_domain_config(config)
    session_id = get_current_session(project_dir)

    # Resolve path
    task_path = Path(filepath)
    if not task_path.is_absolute():
        task_path = project_dir / task_path

    if not task_path.exists():
        click.echo(f"Error: file not found: {filepath}", err=True)
        driver.close()
        raise SystemExit(1)

    # Relative path for storage (from project root)
    try:
        rel_path = str(task_path.relative_to(project_dir))
    except ValueError:
        rel_path = str(task_path)

    # Duplicate guard
    existing_id = _find_existing(driver, database, rel_path)
    if existing_id:
        click.echo(
            f"Warning: CC task already recorded as completed (id: {existing_id[:8]}...). "
            "No duplicate created.",
            err=True,
        )
        driver.close()
        raise SystemExit(0)

    name = _name_from_filepath(rel_path)
    description = note if note else _extract_description(task_path)
    completed_at = datetime.now(timezone.utc).isoformat()

    try:
        artifact_id = create_artifact(
            project_dir=project_dir,
            driver=driver,
            database=database,
            domain_config=domain_config,
            artifact_type="ResearchTask",
            properties={
                "description": description,
                "name": name,
                "source_file": rel_path,
                "completed_at": completed_at,
            },
            actor="cc",
            authority="accepted",
            session_id=session_id,
        )

        _walk_to_completed(
            project_dir=project_dir,
            driver=driver,
            database=database,
            domain_config=domain_config,
            artifact_id=artifact_id,
            session_id=session_id,
        )

        click.echo(f"Recorded: {name}")
        click.echo(f"  source_file: {rel_path}")
        click.echo(f"  id: {artifact_id[:8]}...")
        click.echo(f"  state: completed")
    finally:
        driver.close()
