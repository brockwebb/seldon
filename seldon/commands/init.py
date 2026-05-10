from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import click
import yaml

from seldon.config import slugify
from seldon.core.graph import create_indexes
from seldon.templates import loader as template_loader


DEFAULT_TEMPLATE = "blank"


def _apply_template(
    driver, database: str, project_dir: Path, template: Dict[str, Any]
) -> int:
    """Seed the graph with the template's bootstrap tasks. Returns count seeded."""
    from seldon.domain.loader import load_domain_config
    from seldon.core.artifacts import create_artifact

    domain_yaml = Path(__file__).parent.parent / "domain" / "research.yaml"
    domain_config = load_domain_config(domain_yaml)

    tasks = template.get("bootstrap_tasks", [])
    for task in tasks:
        props = {"description": task["description"]}
        if task.get("name"):
            props["name"] = task["name"]
        create_artifact(
            project_dir=project_dir,
            driver=driver,
            database=database,
            domain_config=domain_config,
            artifact_type="ResearchTask",
            properties=props,
            actor="seldon",
            authority="accepted",
        )
    return len(tasks)


def _database_has_artifacts(driver, database: str) -> bool:
    """Return True if the database contains any Artifact nodes."""
    with driver.session(database=database) as session:
        record = session.run(
            "MATCH (n:Artifact) RETURN count(n) AS n LIMIT 1"
        ).single()
    return bool(record and record["n"] > 0)


def _print_templates() -> None:
    click.echo("Available project templates:")
    for name in template_loader.list_templates():
        try:
            tpl = template_loader.load_template(name)
            desc = tpl.get("description", "").strip()
        except template_loader.TemplateValidationError as e:
            desc = f"(invalid: {e})"
        click.echo(f"  {name:<12}  {desc}")


@click.command("init")
@click.argument("project_name", required=False)
@click.option(
    "--template",
    "template_name",
    default=DEFAULT_TEMPLATE,
    show_default=True,
    help="Project template to apply at init (see --list-templates).",
)
@click.option(
    "--list-templates",
    "list_templates",
    is_flag=True,
    help="List available templates and exit.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Proceed even if the target Neo4j database already contains artifacts.",
)
def init_command(
    project_name: str | None,
    template_name: str,
    list_templates: bool,
    force: bool,
):
    """Initialize a new Seldon project in the current directory."""
    if list_templates:
        _print_templates()
        return

    if not project_name:
        click.echo(
            "Error: project_name is required. "
            "Use `seldon init <name>` or `seldon init --list-templates` to see options.",
            err=True,
        )
        raise SystemExit(2)

    # Validate template BEFORE any filesystem or Neo4j side effects.
    try:
        template = template_loader.load_template(template_name)
    except (
        template_loader.TemplateNotFoundError,
        template_loader.TemplateValidationError,
    ) as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)

    from dotenv import load_dotenv
    from neo4j import GraphDatabase

    project_dir = Path.cwd()
    load_dotenv(project_dir / ".env", override=False)
    slug = slugify(project_name)
    database = f"seldon-{slug}"
    events_path = "seldon_events.jsonl"

    # 1. Create seldon.yaml
    ontology_env = os.getenv("SELDON_ONTOLOGY_PATH")
    if ontology_env:
        ontology_source = str(Path(ontology_env))
    else:
        ontology_source = str(Path(__file__).parent.parent.parent / "ontology")

    config = {
        "project": {
            "name": project_name,
            "slug": slug,
            "domain": "research",
            "template": template_name,
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        },
        "neo4j": {
            "uri": "bolt://localhost:7687",
            "database": database,
        },
        "event_store": {
            "path": events_path,
        },
        "shared_ontology": {
            "source": ontology_source,
            "vocabularies": [
                "validity/VALIDITY_VOCABULARY.md",
            ],
            "inheritance": "read-only",
        },
    }
    config_path = project_dir / "seldon.yaml"
    if config_path.exists():
        click.echo(f"seldon.yaml already exists. Aborting.")
        raise SystemExit(1)

    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

    # 2. Create empty event log
    events_file = project_dir / events_path
    if not events_file.exists():
        events_file.touch()

    # 3. Create .seldon/ directory for session state
    seldon_dir = project_dir / ".seldon"
    seldon_dir.mkdir(exist_ok=True)

    # 4. Create .env template if not present
    env_file = project_dir / ".env"
    if not env_file.exists():
        env_file.write_text(
            "# Neo4j credentials\n"
            "# NEO4J_USERNAME=neo4j\n"
            "# NEO4J_PASSWORD=password\n"
        )

    # 5. Connect to Neo4j and set up project database
    uri = "bolt://localhost:7687"
    username = os.getenv("NEO4J_USERNAME") or os.getenv("NEO4J_USER") or "neo4j"
    password = os.getenv("NEO4J_PASSWORD") or os.getenv("NEO4J_PASS") or "password"

    ontology_status = None
    seeded_count = 0
    try:
        extra_kwargs = {}
        try:
            from neo4j import NotificationMinimumSeverity
            extra_kwargs["notifications_min_severity"] = NotificationMinimumSeverity.OFF
            extra_kwargs["warn_notification_severity"] = NotificationMinimumSeverity.OFF
        except ImportError:
            pass
        driver = GraphDatabase.driver(uri, auth=(username, password), **extra_kwargs)

        with driver.session(database="system") as session:
            session.run(f"CREATE DATABASE `{database}` IF NOT EXISTS WAIT")

        # Emptiness guard: refuse to attach to a database that already has
        # artifacts, unless --force is given. Protects against slug collisions
        # across directories silently sharing a graph.
        if _database_has_artifacts(driver, database) and not force:
            driver.close()
            # Roll back the on-disk state we just wrote so the user can retry cleanly.
            try:
                config_path.unlink()
            except OSError:
                pass
            click.echo(
                f"Error: Neo4j database '{database}' already contains artifacts.\n"
                f"  This usually means another project is using the same database name,\n"
                f"  or a prior init left state behind. To proceed anyway, rerun with --force.\n"
                f"  To start fresh, drop the database manually and re-run init.",
                err=True,
            )
            raise SystemExit(1)

        with driver.session(database=database) as session:
            create_indexes(session)
            session.run(
                "MERGE (m:_SeldonMeta {key: 'sync_point'}) "
                "ON CREATE SET m.last_event_id = null, m.created_at = $now",
                now=datetime.now(timezone.utc).isoformat(),
            )

        seeded_count = _apply_template(driver, database, project_dir, template)

        from seldon.config import load_project_config
        config_loaded = load_project_config(project_dir)
        if "shared_ontology" in config_loaded:
            try:
                from seldon.commands.ontology import _do_sync
                result = _do_sync(driver, database, project_dir, config_loaded)
                ontology_status = (
                    f"Shared ontology synced "
                    f"(epoch {result['epoch']}, {result['terms']} terms)."
                )
            except Exception as e:
                ontology_status = (
                    f"Warning: ontology sync failed "
                    f"(master may not be populated): {e}"
                )

        driver.close()
        neo4j_status = (
            f"Neo4j database '{database}' ready "
            f"(template '{template_name}', {seeded_count} bootstrap task"
            f"{'s' if seeded_count != 1 else ''} seeded)."
        )
    except SystemExit:
        raise
    except Exception as e:
        neo4j_status = f"Warning: Neo4j setup failed: {e}"

    click.echo(f"Initialized Seldon project: {project_name}")
    click.echo(f"  Slug:       {slug}")
    click.echo(f"  Template:   {template_name}")
    click.echo(f"  Database:   {database}")
    click.echo(f"  Events:     {events_path}")
    click.echo(f"  Config:     seldon.yaml")
    click.echo(f"  {neo4j_status}")
    if ontology_status:
        click.echo(f"  {ontology_status}")
    click.echo(f"  Note: add .env to your .gitignore (credentials live there)")
