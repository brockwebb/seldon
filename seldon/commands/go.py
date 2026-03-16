from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import click

from seldon.config import load_project_config, get_neo4j_driver
from seldon.domain.loader import load_domain_config


_ROLE_SECTION = """\
## Role

You are orienting to a Seldon-managed project. Your job is to design, plan, and produce CC task files — not write code directly. All implementation work goes through CC tasks conforming to the standards below. If you need to write code, write a CC task spec that tells Claude Code how to write the code.

CC task files go in `cc_tasks/` with naming convention `YYYY-MM-DD_<descriptive_slug>.md`."""

_AVAILABLE_COMMANDS_SECTION = """\
## Available Seldon Commands

- `seldon status` — project overview
- `seldon briefing` — detailed session briefing
- `seldon closeout` — end session, log notebook entry
- `seldon artifact create/list` — manage artifacts
- `seldon link create/list` — manage relationships
- `seldon result register/verify/list/trace` — result registry
- `seldon task create/list/update` — task tracking
- `seldon docs check` — documentation completeness
- `seldon docs generate` — project reference docs from graph
- `seldon paper audit` — prose quality checks
- `seldon paper build` — reference resolution + assembly"""


def _read_system_standards() -> Optional[str]:
    """Read system CLAUDE.md from env var or default location. Returns None if not found."""
    env_path = os.environ.get("SELDON_SYSTEM_CLAUDE_MD")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p.read_text()
    fallback = Path.home() / "Documents" / "GitHub" / "CLAUDE.md"
    if fallback.exists():
        return fallback.read_text()
    return None


def _read_project_claude_md(project_dir: str) -> Optional[str]:
    """Read CLAUDE.md from project_dir. Returns None if not found."""
    p = Path(project_dir) / "CLAUDE.md"
    if p.exists():
        return p.read_text()
    return None


def _read_latest_handoff(project_dir: str) -> Optional[str]:
    """Read the most recent handoff file. Returns None if none found."""
    handoffs_dir = Path(project_dir) / "handoffs"
    if not handoffs_dir.exists():
        return None
    files = sorted(
        (f for f in handoffs_dir.iterdir() if f.is_file()),
        key=lambda f: f.name,
        reverse=True,
    )
    if not files:
        return None
    return files[0].read_text()


def _format_project_state(briefing_data: dict) -> str:
    """Format briefing data dict into a markdown project state section."""
    open_tasks = briefing_data["open_tasks"]
    stale = briefing_data["stale_artifacts"]
    incomplete = briefing_data["incomplete_provenance"]
    docs = briefing_data["docs_health"]
    stats = briefing_data["graph_stats"]

    lines = ["## Project State", ""]
    lines.append(f"**Open Tasks:** {len(open_tasks)}")
    for t in open_tasks:
        desc = (t.get("description") or "")[:80]
        state = t.get("state", "?")
        lines.append(f"- [{state}] {desc}")

    lines.append("")
    lines.append(f"**Stale Artifacts:** {len(stale)}")
    for r in stale:
        rid = r.get("artifact_id", "?")[:8]
        val = r.get("value", "?")
        units = r.get("units", "")
        desc = r.get("description", "")
        lines.append(f"- {rid}...  {val} {units}  {desc}")

    lines.append("")
    lines.append(f"**Incomplete Provenance:** {len(incomplete)}")
    for r in incomplete:
        rid = r.get("artifact_id", "?")[:8]
        val = r.get("value", "?")
        desc = r.get("description", "")
        lines.append(f"- {rid}...  value={val}  {desc}")

    total_a = docs.get("total_artifacts", 0)
    fully_a = docs.get("fully_documented", 0)
    doc_pct = int(fully_a / total_a * 100) if total_a else 0
    lines.append("")
    lines.append(f"**Documentation:** {fully_a}/{total_a} artifacts fully documented ({doc_pct}%)")

    lines.append("")
    lines.append(
        f"**Graph:** {stats.get('total_nodes', 0)} nodes, "
        f"{stats.get('total_relationships', 0)} relationships"
    )

    return "\n".join(lines)


def _get_project_state_section(project_dir: str) -> str:
    """Return formatted project state section, degrading gracefully on any error."""
    try:
        from seldon.commands.session import get_briefing_data

        config = load_project_config(project_dir)
        driver = get_neo4j_driver(config)
        database = config["neo4j"]["database"]

        domain_name = config["project"].get("domain", "research")
        domain_yaml = Path(__file__).parent.parent / "domain" / f"{domain_name}.yaml"
        domain_config = load_domain_config(domain_yaml)

        try:
            briefing_data = get_briefing_data(driver, database, domain_config)
        finally:
            driver.close()

        return _format_project_state(briefing_data)

    except FileNotFoundError:
        return "## Project State\n\n*No seldon.yaml found — project state unavailable.*"
    except Exception:
        return "## Project State\n\n*Neo4j unavailable or query failed — project state unavailable.*"


def assemble_go_context(
    project_dir: str = ".",
    brief: bool = False,
) -> str:
    """Assemble full orientation context for an AI consumer."""
    sections = []

    # Section 1 — Role Directive (always)
    sections.append(_ROLE_SECTION)

    # Section 2 — Engineering Standards (skip if brief=True)
    if not brief:
        contents = _read_system_standards()
        if contents is None:
            sections.append("## Engineering Standards\n\n*System CLAUDE.md not found.*")
        else:
            sections.append(f"## Engineering Standards\n\n{contents}")

    # Section 3 — Project Context
    project_claude_md = _read_project_claude_md(project_dir)
    if project_claude_md is None:
        sections.append("## Project Context\n\n*No CLAUDE.md found in project directory.*")
    else:
        sections.append(f"## Project Context\n\n{project_claude_md}")

    # Section 4 — Latest Handoff
    handoff = _read_latest_handoff(project_dir)
    if handoff is None:
        sections.append("## Latest Handoff\n\n*No handoffs found.*")
    else:
        sections.append(f"## Latest Handoff\n\n{handoff}")

    # Section 5 — Project State
    sections.append(_get_project_state_section(project_dir))

    # Section 6 — Available Commands (always)
    sections.append(_AVAILABLE_COMMANDS_SECTION)

    return "\n\n---\n\n".join(sections)


def assemble_go_context_as_dict(
    project_dir: str = ".",
    brief: bool = False,
) -> dict:
    """Assemble orientation context as a structured dict for JSON output."""
    # Role
    role = _ROLE_SECTION

    # Engineering Standards
    if brief:
        system_standards = None
    else:
        contents = _read_system_standards()
        if contents is None:
            system_standards = "*System CLAUDE.md not found.*"
        else:
            system_standards = contents

    # Project Context
    project_claude_md = _read_project_claude_md(project_dir)
    if project_claude_md is None:
        project_context = "*No CLAUDE.md found in project directory.*"
    else:
        project_context = project_claude_md

    # Latest Handoff
    handoff = _read_latest_handoff(project_dir)
    if handoff is None:
        latest_handoff = "*No handoffs found.*"
    else:
        latest_handoff = handoff

    # Project State
    project_state = _get_project_state_section(project_dir)

    # Available Commands
    available_commands = _AVAILABLE_COMMANDS_SECTION

    return {
        "role": role,
        "system_standards": system_standards,
        "project_context": project_context,
        "latest_handoff": latest_handoff,
        "project_state": project_state,
        "available_commands": available_commands,
    }


@click.command("go")
@click.option("--brief", is_flag=True, default=False, help="Skip system CLAUDE.md.")
@click.option("--json", "output_json", is_flag=True, default=False, help="JSON output.")
def go_command(brief, output_json):
    """Orient an AI agent: engineering standards, project context, open tasks, commands."""
    project_dir = str(Path.cwd())

    if output_json:
        data = assemble_go_context_as_dict(project_dir=project_dir, brief=brief)
        click.echo(json.dumps(data, indent=2))
    else:
        output = assemble_go_context(project_dir=project_dir, brief=brief)
        click.echo(output)
