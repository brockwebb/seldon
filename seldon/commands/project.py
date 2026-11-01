"""`seldon project new`: a directory becomes a seldon project in one command (SEL-019).

    seldon project new <path> [--graph <name>] [--dispatch [--enable] [--no-load]] [--name N] [--database D] ...

The sequence and its reasons are in `seldon/core/project_new.py`.
"""
from __future__ import annotations

from pathlib import Path

import click
import yaml

from seldon.core import adopt as A
from seldon.core import hooks as H
from seldon.core import project_new as PN


@click.group("project")
def project_group():
    """Make a consumer project (SEL-019)."""


@project_group.command("new")
@click.argument("path", type=click.Path(file_okay=False, path_type=Path))
@click.option("--name", "project_name", default=None, help="the project's name (default: the directory's name)")
@click.option("--template", "template_name", default="blank", show_default=True, help="`seldon init` template")
@click.option("--database", default=None, help="the Neo4j database (default: seldon-<slug>, as `seldon init`)")
@click.option("--force-init", is_flag=True, help="`seldon init --force`: attach to a database that has artifacts")
@click.option("--graph", "graph", default=None,
              help="also initialize graphs/<name>/ with `squiddy init` from its graph.yaml (a skeleton when absent)")
@click.option("--dispatch", "dispatch", is_flag=True,
              help="adopt the standing dispatcher (`seldon dispatch adopt --yes`) and load its plist")
@click.option("--standing-band-ref", default=None, help="with --dispatch: adopt's --standing-band-ref")
@click.option("--branch", default=None, help="the branch: git init's, and adopt's --branch (default main)")
@click.option("--label", "launchd_label", default=None, help="with --dispatch: adopt's --label")
@click.option("--gate-command", default=None, help="with --dispatch: adopt's --gate-command (the project's suite)")
@click.option("--interpreter", default=None,
              help="with --dispatch: declare dispatch.stations.interpreter (AD-037-R15); it must import seldon")
@click.option("--no-load", is_flag=True, help="with --dispatch: write the plist but do not load it")
@click.option("--enable", is_flag=True, help="with --dispatch: set dispatch.enabled true once the plist is loaded")
def project_new(path, project_name, template_name, database, force_init, graph, dispatch, standing_band_ref, branch,
                launchd_label, gate_command, interpreter, no_load, enable):
    """Turn PATH into a seldon project: git, `seldon init`, the environment, `seldon hooks install`, and with
    --dispatch `seldon dispatch adopt` and its plist loaded; with --graph, `squiddy init` for graphs/<name>/.

    Each step acts only where the project lacks what it produces, so a second run changes nothing and says so.
    Everything written is committed through the hooks. Registers nothing: it prints what to register next.
    Exit 1 when a step refused (the steps before it are kept and committed)."""
    from seldon.commands.init import initialize_project
    from seldon.templates import loader as template_loader

    if (enable or no_load or interpreter or standing_band_ref or launchd_label or gate_command) and not dispatch:
        raise click.UsageError("--enable, --no-load, --interpreter, --standing-band-ref, --label and --gate-command "
                               "need --dispatch")
    if enable and no_load:
        raise click.UsageError("--enable needs the plist loaded; drop --no-load")
    kit_dir = PN.KIT_DIR
    try:
        cfg = PN.project_new_config(kit_dir)
        template = template_loader.load_template(template_name)
        if interpreter:
            PN.check_interpreter(interpreter)
    except (PN.ProjectNewError, A.AdoptError, template_loader.TemplateNotFoundError,
            template_loader.TemplateValidationError) as exc:
        raise click.ClickException(str(exc))

    project_dir = path.expanduser().resolve()
    steps = []
    try:
        steps.append(PN.ensure_repo(project_dir, branch or "main"))
        before = PN.dirty_paths(project_dir)

        # 1. `seldon init`
        if (project_dir / "seldon.yaml").is_file():
            steps.append(PN.Step("init", "ok", "seldon.yaml present"))
        else:
            initialize_project(project_dir, project_name or project_dir.name, template_name, template,
                               force=force_init, database=database)
            steps.append(PN.Step("init", "changed", f"seldon init {project_name or project_dir.name}"))

        # 1b. `.seldon/` in the tracked .gitignore (SEL-020): an existing project may lack it, or carry it only in
        #     .git/info/exclude, which no worktree or clone inherits.
        steps.append(PN.ignore_step(project_dir))

        # 2. `seldon hooks install` (core.hooksPath, the recorded interpreter, the union declaration)
        st = H.status(project_dir)
        res = H.install(project_dir)
        union = H.declare_union(project_dir, yaml.safe_load((project_dir / "seldon.yaml").read_text()) or {})
        if res.changed or union["added"]:
            steps.append(PN.Step("hooks", "changed",
                                 f"core.hooksPath {res.hooks_path}; {H.PYTHON_KEY} {res.python}"
                                 + (f"; committed {res.commit}" if res.commit else "")
                                 + (f"; merge=union {', '.join(union['added'])} ({union['commit']})"
                                    if union["added"] else "")))
        else:
            steps.append(PN.Step("hooks", "ok", "installed" if st["installed"] else "installed now"))

        # 3. `seldon dispatch adopt --yes` (unchanged; composed, never re-implemented)
        if dispatch:
            config = yaml.safe_load((project_dir / "seldon.yaml").read_text(encoding="utf-8")) or {}
            given = {"standing_band_ref": standing_band_ref, "branch": branch, "launchd_label": launchd_label}
            answers = {k: given.get(k) or default
                       for k, _q, default in A.questions(project_dir, config, cfg["_kit"], kit_dir)}
            if gate_command:
                answers["gate_command"] = gate_command
            out = A.adoption(project_dir, answers, kit_dir=kit_dir)
            if out["seldon_yaml"] or out["plist"] or out["gitignore_add"]:
                written = A.write_adoption(project_dir, out)
                steps.append(PN.Step("adopt", "changed", f"wrote {', '.join(written)}", written))
            else:
                steps.append(PN.Step("adopt", "ok", "dispatch block, log caps, ignores and plist present"))
        else:
            steps.append(PN.Step("adopt", "skipped", "no --dispatch"))

        # 4. the environment, the secret scan, the stations' environment premise, the declared interpreter
        new_text, added = PN.environment_text(project_dir, cfg, kit_dir, dispatch, interpreter)
        if new_text is not None:
            (project_dir / "seldon.yaml").write_text(new_text, encoding="utf-8")
            steps.append(PN.Step("environment", "changed", f"seldon.yaml + {', '.join(added)}", ["seldon.yaml"]))
        else:
            steps.append(PN.Step("environment", "ok", "environment, secret scan and stations present"))
        absent = PN.missing_siblings(project_dir, cfg["environment_packages"])
        if absent:
            steps.append(PN.Step("environment", "refused",
                                 f"no sibling directory for {absent} beside {project_dir}: the environment premise "
                                 f"names repositories that are not there. Clone them beside it, or edit "
                                 f"environment.packages."))

        # 5. `squiddy init` for the graph
        if graph:
            steps.append(PN.graph_step(project_dir, graph, PN.squiddy_command(cfg, kit_dir)))
        else:
            steps.append(PN.Step("graph", "skipped", "no --graph"))

        # 6. commit what this run wrote (only paths that were clean before it ran)
        mine = sorted(PN.dirty_paths(project_dir) - before)
        sha = PN.commit_paths(project_dir, mine, PN.COMMIT_MESSAGE.format(
            body="\n".join(f"- {s.name}: {s.status} {s.detail}".rstrip() for s in steps)))
        steps.append(PN.Step("commit", "changed", f"{sha}: {len(mine)} path(s)") if sha
                     else PN.Step("commit", "ok", "nothing to commit"))
        left = sorted(before & PN.dirty_paths(project_dir))
        if left:
            steps.append(PN.Step("commit", "refused", f"left uncommitted, dirty before this run: {', '.join(left)}"))

        # 7. load the plist, then 8. enable
        block = None
        if dispatch:
            from seldon.core import dispatch as D
            block = D.load_dispatch_config(project_dir)
            label = block.get("launchd_label")
            plist = project_dir / A.PLIST_DIR / f"{label}.plist"
            if no_load:
                steps.append(PN.Step("plist", "skipped", f"--no-load; {plist} written, not loaded"))
            else:
                steps.append(PN.load_plist(plist, label, Path(str(cfg["launch_agents_dir"]))))
            if enable:
                flipped = PN.enabled_text((project_dir / "seldon.yaml").read_text(encoding="utf-8"))
                if flipped is None:
                    steps.append(PN.Step("enable", "ok", f"dispatch.enabled is {block['enabled']}"))
                else:
                    (project_dir / "seldon.yaml").write_text(flipped, encoding="utf-8")
                    esha = PN.commit_paths(project_dir, ["seldon.yaml"], PN.ENABLE_COMMIT_MESSAGE)
                    steps.append(PN.Step("enable", "changed", f"dispatch.enabled true ({esha})"))
                block = D.load_dispatch_config(project_dir)
    except (PN.ProjectNewError, A.AdoptError, H.HookError) as exc:
        for s in steps:
            click.echo(f"  {s.name:12} {s.status:8} {s.detail}")
        raise click.ClickException(str(exc))

    changed = [s for s in steps if s.status == "changed"]
    refused = [s for s in steps if s.status == "refused"]
    click.echo(f"project new: {project_dir}" + ("" if changed else " (nothing changed; already a project)"))
    for s in steps:
        click.echo(f"  {s.name:12} {s.status:8} {s.detail}")
    click.echo("next:")
    click.echo(f"  register the first task (it commits the file): seldon cc register --project {project_dir} "
               f"cc_tasks/<YYYY-MM-DD_slug>.md")
    if dispatch and block is not None and not block.get("enabled"):
        click.echo(f"  then: seldon project new {project_dir} --dispatch --enable   (dispatch.enabled is false)")
    if graph and any(s.name == "graph" and s.status == "refused" for s in steps):
        click.echo(f"  fill graphs/{graph}/graph.yaml, then: seldon project new {project_dir} --graph {graph}")
    if refused:
        raise SystemExit(1)
