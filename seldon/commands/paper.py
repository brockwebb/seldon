from __future__ import annotations

from pathlib import Path

import click

from seldon.config import load_project_config, get_neo4j_driver
from seldon.domain.loader import load_domain_config
from seldon.paper.qc import (
    load_qc_config,
    load_style_config,
    run_tier2,
    run_tier3,
    format_violations,
)
from seldon.paper.build import build_paper


def _get_domain_config(config: dict):
    domain_name = config["project"].get("domain", "research")
    domain_yaml = Path(__file__).parent.parent / "domain" / f"{domain_name}.yaml"
    return load_domain_config(domain_yaml)


@click.group("paper")
def paper_group():
    """Paper authoring: prose QC and graph-driven manuscript assembly."""
    pass


@paper_group.command("audit")
@click.argument("files", nargs=-1, type=click.Path(exists=True))
@click.option("--tier", type=click.Choice(["2", "3"]), default=None,
              help="Run only Tier 2 (prose) or Tier 3 (style) checks.")
@click.option("--qc-config", "qc_config_path", default=None, type=click.Path(),
              help="Override Tier 2 config path.")
@click.option("--style-config", "style_config_path", default=None, type=click.Path(),
              help="Override Tier 3 config path.")
def paper_audit(files, tier, qc_config_path, style_config_path):
    """Check markdown prose for quality (Tier 2) and style (Tier 3) violations.

    FILES defaults to paper/sections/*.md relative to the current directory.
    """
    project_dir = Path.cwd()

    # Resolve files
    if files:
        paths = [Path(f) for f in files]
    else:
        default_dir = project_dir / "paper" / "sections"
        if not default_dir.exists():
            click.echo(f"No files provided and {default_dir} does not exist.", err=True)
            raise SystemExit(1)
        paths = sorted(default_dir.glob("*.md"))
        if not paths:
            click.echo(f"No .md files found in {default_dir}.", err=True)
            raise SystemExit(1)

    # Load configs
    qc_config = load_qc_config(Path(qc_config_path) if qc_config_path else None)
    style_config = load_style_config(Path(style_config_path) if style_config_path else None)

    run_tier2_checks = tier in (None, "2")
    run_tier3_checks = tier in (None, "3")

    tier2_violations = []
    tier3_violations = []

    for path in paths:
        text = path.read_text()
        if run_tier2_checks:
            tier2_violations.extend(run_tier2(text, qc_config, filename=str(path)))
        if run_tier3_checks:
            tier3_violations.extend(run_tier3(text, style_config, filename=str(path)))

    if run_tier2_checks:
        click.echo(format_violations(tier2_violations, "TIER 2: Prose Quality"))
    if run_tier3_checks:
        click.echo(format_violations(tier3_violations, "TIER 3: Style Preferences"))

    # Exit 1 if any Tier 2 violations
    if run_tier2_checks and tier2_violations:
        raise SystemExit(1)


@paper_group.command("sync")
@click.option("--register-untracked", is_flag=True, default=False,
              help="Auto-create PaperSection artifacts for untracked section files.")
@click.option("--dry-run", is_flag=True, default=False,
              help="Show what would change without writing anything.")
@click.option("--auto-stale", is_flag=True, default=False,
              help="Automatically transition changed sections to stale if in review or published state.")
def paper_sync(register_untracked, dry_run, auto_stale):
    """Reconcile section files on disk with graph state.

    Detects content changes, updates CITES edges for added/removed references,
    and optionally transitions changed sections to stale. Run after editing sections.
    """
    from seldon.paper.sync import sync_all
    from seldon.config import get_sections_dir

    project_dir = Path.cwd()
    config = load_project_config()
    sections_dir = get_sections_dir(config, project_dir)

    driver = get_neo4j_driver(config)
    domain_config = _get_domain_config(config)
    database = config["neo4j"]["database"]

    try:
        results = sync_all(
            driver=driver,
            database=database,
            project_dir=project_dir,
            domain_config=domain_config,
            sections_dir=sections_dir,
            dry_run=dry_run,
            auto_stale=auto_stale,
            register_untracked=register_untracked,
        )
    finally:
        driver.close()

    if not results:
        click.echo(f"No section files found in {sections_dir}.")
        return

    click.echo("PAPER SYNC REPORT")
    click.echo("═" * 50)
    click.echo()

    col_width = max(len(r.filename) for r in results) + 3
    counts = {"updated": 0, "untracked": 0, "unchanged": 0, "registered": 0}

    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
        name_col = r.filename.ljust(col_width, ".")

        if r.status == "unchanged":
            click.echo(f"  {name_col} unchanged")
        elif r.status == "untracked":
            click.echo(f"  {name_col} untracked (no PaperSection artifact)")
        elif r.status == "registered":
            click.echo(f"  {name_col} REGISTERED")
        elif r.status == "updated":
            parts = []
            if r.refs_added:
                parts.append(f"{len(r.refs_added)} ref{'s' if len(r.refs_added) != 1 else ''} added")
            if r.refs_removed:
                parts.append(f"{len(r.refs_removed)} ref{'s' if len(r.refs_removed) != 1 else ''} removed")
            if r.state_changed:
                parts.append("→ stale")
            detail = f" ({', '.join(parts)})" if parts else ""
            prefix = "[dry-run] " if dry_run else ""
            click.echo(f"  {name_col} {prefix}UPDATED{detail}")
            if r.suspected_oob:
                click.echo(
                    f"  {'':>{col_width}} ⚠ SUSPECTED OUT-OF-BAND EDIT "
                    f"(section was '{r.prior_state}') — was this change tracked via a CC task?",
                    err=True,
                )

    click.echo()
    summary_parts = []
    if counts.get("updated"):
        summary_parts.append(f"{counts['updated']} updated")
    if counts.get("registered"):
        summary_parts.append(f"{counts['registered']} registered")
    if counts.get("untracked"):
        summary_parts.append(f"{counts['untracked']} untracked")
    if counts.get("unchanged"):
        summary_parts.append(f"{counts['unchanged']} unchanged")
    click.echo(f"Summary: {', '.join(summary_parts)}")


@paper_group.command("register")
@click.argument("files", nargs=-1, type=click.Path(exists=True))
@click.option("--all", "register_all", is_flag=True, default=False,
              help="Register all section files from configured sections directory.")
def paper_register(files, register_all):
    """Register section files as PaperSection artifacts.

    Creates PaperSection artifacts with name, title, file_path, and content_hash.
    Skips files that already have a PaperSection artifact.

    Provide FILE paths explicitly, or use --all to discover *.md in the sections directory.
    """
    from seldon.paper.sync import get_paper_section_artifacts, _register_section
    from seldon.config import get_sections_dir

    project_dir = Path.cwd()
    config = load_project_config()
    driver = get_neo4j_driver(config)
    domain_config = _get_domain_config(config)
    database = config["neo4j"]["database"]

    try:
        if register_all:
            sections_dir = get_sections_dir(config, project_dir)
            if not sections_dir.exists():
                click.echo(f"Error: {sections_dir} does not exist.", err=True)
                raise SystemExit(1)
            paths = sorted(sections_dir.glob("*.md"))
        elif files:
            paths = [Path(f) for f in files]
        else:
            click.echo("Error: specify files or use --all.", err=True)
            raise SystemExit(1)

        if not paths:
            click.echo("No section files found.")
            return

        existing = get_paper_section_artifacts(driver, database)
        registered = 0
        skipped = 0

        for path in paths:
            if path.stem in existing or str(path) in existing:
                click.echo(f"  {path.name} ... skipped (already registered)")
                skipped += 1
                continue
            artifact_id = _register_section(
                driver, database, project_dir, domain_config, path, actor="human"
            )
            click.echo(f"  {path.name} ... registered ({artifact_id[:8]})")
            registered += 1

    finally:
        driver.close()

    click.echo(f"\nRegistered {registered}, skipped {skipped}.")


def _get_downstream_tree(session, root_id: str, max_depth: int) -> dict:
    """
    BFS reverse traversal from root_id: find all artifacts that depend on it.

    "Impact" of an artifact = everything that points to it (directly or transitively).
    An edge ``dependent -[REL]-> target`` means ``dependent`` depends on ``target``.
    So to find impact of ``root``, we walk incoming edges — what points to root,
    then what points to those, and so on.

    Returns a dict:
        {
            "nodes": {artifact_id: {"artifact": {...}, "rel_type": str,
                                    "parent_id": str, "depth": int}},
            "root_children": [artifact_id, ...]   # direct dependents of root
        }

    Nodes reachable via multiple paths are de-duplicated (first path wins).
    "parent_id" here means "the node this dependent was reached from" — the node
    *closer to the root* in the reverse-traversal tree.
    """
    from collections import deque

    visited: dict = {}  # artifact_id -> node data
    queue: deque = deque()

    def _query_incoming(node_id: str):
        """Return list of (dependent_artifact_dict, rel_type_str) pointing to node_id."""
        records = session.run(
            "MATCH (dep:Artifact)-[r]->(a:Artifact {artifact_id: $id}) "
            "RETURN dep, type(r) AS rel",
            id=node_id,
        ).data()
        return [(dict(rec["dep"]), rec["rel"].lower()) for rec in records]

    # Seed: direct dependents of root (depth 1)
    for dep, rel in _query_incoming(root_id):
        dep_id = dep["artifact_id"]
        if dep_id not in visited:
            visited[dep_id] = {
                "artifact": dep,
                "rel_type": rel,
                "parent_id": root_id,
                "depth": 1,
            }
            queue.append((dep_id, 1))

    # BFS for transitive dependents
    while queue:
        current_id, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for dep, rel in _query_incoming(current_id):
            dep_id = dep["artifact_id"]
            # Avoid root (cycles) and already-visited nodes
            if dep_id != root_id and dep_id not in visited:
                visited[dep_id] = {
                    "artifact": dep,
                    "rel_type": rel,
                    "parent_id": current_id,
                    "depth": depth + 1,
                }
                queue.append((dep_id, depth + 1))

    root_children = [nid for nid, n in visited.items() if n["parent_id"] == root_id]

    return {"nodes": visited, "root_children": root_children}


def _render_tree(tree: dict, root_name: str) -> list[str]:
    """Render the impact tree as ASCII-art lines."""
    nodes = tree["nodes"]
    root_children = tree["root_children"]

    lines = [f"Impact analysis for: {root_name}"]

    def _render_children(child_ids, prefix=""):
        for i, cid in enumerate(child_ids):
            is_last = (i == len(child_ids) - 1)
            node = nodes[cid]
            artifact = node["artifact"]
            connector = "└──" if is_last else "├──"
            a_type = artifact.get("artifact_type", "Artifact")
            name = artifact.get("name", cid[:8])
            rel = node["rel_type"]
            state = artifact.get("state", "")
            state_str = f" → {state.upper()}" if state else ""
            lines.append(f"  {prefix}{connector} {a_type}: {name} ({rel}){state_str}")

            # Recurse into children
            child_prefix = prefix + ("    " if is_last else "│   ")
            child_ids_of_node = [
                nid for nid, n in nodes.items()
                if n["parent_id"] == cid
            ]
            _render_children(child_ids_of_node, child_prefix)

    _render_children(root_children)
    return lines


def _blast_radius_summary(tree: dict) -> str:
    """Produce a 'Blast radius: N sections, M figures, ...' summary line."""
    nodes = tree["nodes"]
    if not nodes:
        return "Blast radius: 0 dependents"

    counts: dict[str, int] = {}
    for node in nodes.values():
        a_type = node["artifact"].get("artifact_type", "Artifact")
        counts[a_type] = counts.get(a_type, 0) + 1

    type_labels = {
        "PaperSection": "section",
        "Figure": "figure",
        "Table": "table",
        "Result": "result",
        "Script": "script",
    }
    parts = []
    for a_type, count in sorted(counts.items()):
        label = type_labels.get(a_type, a_type.lower())
        plural = "s" if count != 1 else ""
        parts.append(f"{count} {label}{plural}")

    return f"Blast radius: {', '.join(parts)}"


@paper_group.command("impact")
@click.argument("artifact_name")
@click.option("--depth", default=10, show_default=True,
              help="Maximum traversal depth.")
def paper_impact_command(artifact_name, depth):
    """Show downstream impact of an artifact — what would be affected if it changed.

    ARTIFACT_NAME is the 'name' property of any artifact in the graph.

    Traverses all incoming dependency edges up to --depth hops and displays a tree
    of affected artifacts plus a blast-radius summary by type.
    """
    from seldon.core.graph import find_any_artifact_by_name

    config = load_project_config()
    driver = get_neo4j_driver(config)
    database = config["neo4j"]["database"]

    try:
        with driver.session(database=database) as session:
            try:
                artifact = find_any_artifact_by_name(session, artifact_name)
            except ValueError as e:
                click.echo(f"Error: {e}", err=True)
                raise SystemExit(1)
            if artifact is None:
                click.echo(
                    f"Error: no artifact with name='{artifact_name}' found.", err=True
                )
                raise SystemExit(1)

            tree = _get_downstream_tree(session, artifact["artifact_id"], max_depth=depth)
    finally:
        driver.close()

    lines = _render_tree(tree, artifact_name)
    for line in lines:
        click.echo(line)
    click.echo()
    click.echo(_blast_radius_summary(tree))


@paper_group.command("context")
@click.argument("section_name")
@click.option("--format", "output_format", type=click.Choice(["text", "yaml"]),
              default="text", show_default=True,
              help="Output format: human-readable text or machine-readable YAML.")
def paper_context_command(section_name, output_format):
    """Show structured context for drafting or revising a section.

    Queries the graph for SECTION_NAME and outputs its semantic anchor properties,
    assumes/assumed-by relationships, cross-references, and sibling sections.
    """
    from seldon.paper.context import get_section_context, format_context_text, format_context_yaml

    config = load_project_config()
    driver = get_neo4j_driver(config)
    database = config["neo4j"]["database"]

    try:
        ctx = get_section_context(driver, database, section_name)
    finally:
        driver.close()

    if ctx is None:
        click.echo(
            f"Error: no PaperSection with name='{section_name}' found in graph.", err=True
        )
        raise SystemExit(1)

    section = ctx["section"]
    has_anchors = bool(section.get("core_argument") or section.get("claims"))
    if not has_anchors:
        click.echo(
            f"Note: No anchor properties set for '{section_name}'. "
            "Run anchor population first to fill core_argument and claims.",
            err=True,
        )

    if output_format == "yaml":
        click.echo(format_context_yaml(ctx))
    else:
        click.echo(format_context_text(ctx))


@paper_group.command("build")
@click.option("--skip-qc", is_flag=True, default=False,
              help="Skip Tier 2 and Tier 3 QC. Tier 1 structural checks always run.")
@click.option("--strict", is_flag=True, default=False,
              help="Treat Tier 2 warnings as errors.")
@click.option("--output", "output_path", default=None, type=click.Path(),
              help="Override output .qmd path.")
@click.option("--no-render", is_flag=True, default=False,
              help="Resolve references and run QC but do not call Quarto.")
@click.option("--qc-config", "qc_config_path", default=None, type=click.Path(),
              help="Override Tier 2 config path.")
@click.option("--style-config", "style_config_path", default=None, type=click.Path(),
              help="Override Tier 3 config path.")
def paper_build(skip_qc, strict, output_path, no_render, qc_config_path, style_config_path):
    """Resolve graph references, run QC, assemble .qmd, and render via Quarto."""
    project_dir = Path.cwd()
    paper_dir = project_dir / "paper"

    exit_code = build_paper(
        project_dir=project_dir,
        paper_dir=paper_dir,
        output_path=Path(output_path) if output_path else None,
        skip_qc=skip_qc,
        strict=strict,
        no_render=no_render,
        qc_config_path=Path(qc_config_path) if qc_config_path else None,
        style_config_path=Path(style_config_path) if style_config_path else None,
    )
    raise SystemExit(exit_code)
