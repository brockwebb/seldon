"""CC task completion tracking — seldon cc complete."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

import click

from seldon.config import load_project_config, get_neo4j_driver, get_current_session
from seldon.core.artifacts import create_artifact, update_artifact, walk_to_completed
from seldon.domain.loader import load_domain_config


def _file_hash(path: Path) -> str:
    """Compute SHA-256 of file content."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


# Structural match for any metadata-style line: optional `**`, a capitalized key
# (words, spaces, `_`, `-`), a colon, optional closing `**`, then whitespace or
# end-of-string. Intentionally key-agnostic so new metadata keys (Location,
# Severity, Owner, Depends on, Estimate, …) are recognized without maintenance.
_METADATA_RE = re.compile(
    r"^\*?\*?[A-Z][A-Za-z0-9 _-]{0,40}:\*?\*?(\s|$)",
)


def _description_looks_like_metadata(text: str) -> bool:
    """Return True if text still looks like a metadata line.

    Used as a defensive second layer after extraction — if the chosen
    description matches the metadata pattern, emit a warning so the user
    knows something went wrong with auto-extraction.
    """
    if not text:
        return False
    return bool(_METADATA_RE.match(text))


def _extract_description(filepath: Path) -> str:
    """Extract first substantive line from a CC task file.

    Skips blank lines, markdown headers (#), horizontal rules (---),
    and any metadata-style line (``**Key:**`` or bare ``Key:`` prefix).
    Falls back to the filename if no substantive line is found.
    """
    for line in filepath.read_text().splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        if stripped.startswith("---"):
            continue
        if _METADATA_RE.match(stripped):
            continue
        return stripped[:200]
    return filepath.name


def _warn_if_description_suspicious(filepath: Path, description: str) -> None:
    """Emit a stderr warning when an auto-extracted description looks like metadata
    or fell back to the filename. Does not fail the registration.
    """
    looks_bad = (
        _description_looks_like_metadata(description)
        or description == filepath.name
    )
    if not looks_bad:
        return
    click.echo(
        "WARNING: extracted description may be metadata, not task description.\n"
        f"  File: {filepath}\n"
        f'  Extracted: "{description[:60]}..."\n'
        "  Consider adding a description section or using --description to override.",
        err=True,
    )


def _find_existing(driver, database: str, rel_path: str) -> str | None:
    """Return artifact_id of any ResearchTask with matching source_file, or None."""
    with driver.session(database=database) as session:
        record = session.run(
            "MATCH (t:Artifact:ResearchTask {source_file: $sf}) RETURN t.artifact_id AS id",
            sf=rel_path,
        ).single()
    return record["id"] if record else None


def _get_artifact_state(driver, database: str, artifact_id: str) -> str | None:
    """Return the current state of an artifact, or None if not found."""
    with driver.session(database=database) as session:
        record = session.run(
            "MATCH (t:Artifact {artifact_id: $aid}) RETURN t.state AS state",
            aid=artifact_id,
        ).single()
    return record["state"] if record else None


def _get_artifact_file_hash(driver, database: str, artifact_id: str) -> str | None:
    """Return the file_hash of an artifact, or None if not set."""
    with driver.session(database=database) as session:
        record = session.run(
            "MATCH (t:Artifact {artifact_id: $aid}) RETURN t.file_hash AS fh",
            aid=artifact_id,
        ).single()
    return record["fh"] if record else None


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

    # Duplicate guard — state-aware
    existing_id = _find_existing(driver, database, rel_path)
    if existing_id:
        current_state = _get_artifact_state(driver, database, existing_id)

        if current_state == "completed":
            click.echo(
                f"Warning: CC task already completed (id: {existing_id[:8]}...). "
                "No action taken.",
                err=True,
            )
            driver.close()
            raise SystemExit(0)

        # Verify file immutability (hash check)
        registered_hash = _get_artifact_file_hash(driver, database, existing_id)
        if registered_hash is not None:
            current_hash = _file_hash(task_path)
            if current_hash != registered_hash:
                click.echo(
                    f"ERROR: Task file has been modified since registration.\n"
                    f"  File: {rel_path}\n"
                    f"  Registered hash: {registered_hash[:16]}...\n"
                    f"  Current hash:    {current_hash[:16]}...\n"
                    f"  Task immutability violated. If changes are needed, create an\n"
                    f"  addendum file or a new superseding task. The original task file\n"
                    f"  must not be modified after registration.",
                    err=True,
                )
                driver.close()
                raise SystemExit(1)
        else:
            click.echo(
                "WARNING: Task has no registered file_hash. Skipping immutability check.\n"
                "  Legacy tasks registered before hash enforcement are not verified.",
                err=True,
            )

        # Pre-registered task — walk it to completed
        name = _name_from_filepath(rel_path)
        click.echo(
            f"Found pre-registered task (id: {existing_id[:8]}..., state: {current_state}). "
            "Walking to completed."
        )
        completed_at = datetime.now(timezone.utc).isoformat()
        try:
            update_artifact(
                project_dir=project_dir,
                driver=driver,
                database=database,
                artifact_id=existing_id,
                properties={"completed_at": completed_at},
                actor="cc",
                authority="accepted",
                session_id=session_id,
            )
            walk_to_completed(
                project_dir=project_dir,
                driver=driver,
                database=database,
                domain_config=domain_config,
                artifact_id=existing_id,
                current_state=current_state,
                actor="cc",
                session_id=session_id,
            )
            click.echo(f"Completed: {name}")
            click.echo(f"  source_file: {rel_path}")
            click.echo(f"  id: {existing_id[:8]}...")
            click.echo(f"  state: completed")
        finally:
            driver.close()
        return

    name = _name_from_filepath(rel_path)
    if note:
        description = note
    else:
        description = _extract_description(task_path)
        _warn_if_description_suspicious(task_path, description)
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

        walk_to_completed(
            project_dir=project_dir,
            driver=driver,
            database=database,
            domain_config=domain_config,
            artifact_id=artifact_id,
            current_state="proposed",
            actor="cc",
            session_id=session_id,
        )

        click.echo(f"Recorded: {name}")
        click.echo(f"  source_file: {rel_path}")
        click.echo(f"  id: {artifact_id[:8]}...")
        click.echo(f"  state: completed")
    finally:
        driver.close()


@cc_group.command("register")
@click.argument("filepath")
@click.option("--description", default=None, help="Override auto-extracted description")
def cc_register(filepath, description):
    """Register a CC task file as a proposed ResearchTask in the graph.

    Use at task creation time to track the task before execution.
    Running twice on the same file warns instead of creating a duplicate.

    FILEPATH is relative to project root or absolute.
    """
    project_dir = Path.cwd()
    config = load_project_config(project_dir)
    driver = get_neo4j_driver(config)
    database = config["neo4j"]["database"]
    domain_config = _get_domain_config(config)
    session_id = get_current_session(project_dir)

    task_path = Path(filepath)
    if not task_path.is_absolute():
        task_path = project_dir / task_path

    if not task_path.exists():
        click.echo(f"Error: file not found: {filepath}", err=True)
        driver.close()
        raise SystemExit(1)

    try:
        rel_path = str(task_path.relative_to(project_dir))
    except ValueError:
        rel_path = str(task_path)

    existing_id = _find_existing(driver, database, rel_path)
    if existing_id:
        click.echo(
            f"Warning: CC task already registered (id: {existing_id[:8]}...). "
            "No duplicate created.",
            err=True,
        )
        driver.close()
        raise SystemExit(0)

    name = _name_from_filepath(rel_path)
    if description is None:
        description = _extract_description(task_path)
        _warn_if_description_suspicious(task_path, description)
    content_hash = _file_hash(task_path)

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
                "file_hash": content_hash,
            },
            actor="cc",
            authority="accepted",
            session_id=session_id,
        )
        click.echo(f"Registered: {name}")
        click.echo(f"  source_file: {rel_path}")
        click.echo(f"  id: {artifact_id[:8]}...")
        click.echo(f"  state: proposed")
    finally:
        driver.close()
