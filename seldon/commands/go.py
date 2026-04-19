from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import click

from seldon.config import load_project_config, get_neo4j_driver
from seldon.domain.loader import load_domain_config


_ROLE_SECTION = """\
## Role & Behavioral Contract

You are orienting to a Seldon-managed project.

### If You Are a Desktop Session (Claude Desktop, claude.ai)

- You design, plan, review, and produce CC task specs. You do NOT write project files directly.
- If you are about to create or modify a tracked file (anything in book/, paper/, sections/, or any file registered as a Seldon artifact), STOP. Write a CC task instead.
- The only files you may write directly: CC tasks (in cc_tasks/), handoffs (in handoffs/), and design notes (in docs/).
- CC task files go in `cc_tasks/` with naming convention `YYYY-MM-DD_<descriptive_slug>.md`.
- CC task files are immutable once written. If changes are needed, write a new file or get explicit permission.
- For trivial housekeeping (creating tasks, closing stale items, marking CC tasks complete), use MCP tools directly: `seldon_task_create`, `seldon_task_update`, `seldon_task_close`, `seldon_issue_create`, `seldon_cc_complete`, `seldon_cc_register`, `seldon_query`.
- You do NOT perform prose audits, glossary checks, cross-reference scans, or any compliance verification directly (no grep substitutes, no container-side scripts). These are `seldon verify`, `seldon paper audit`, and `seldon paper sync` responsibilities — CLI tools that run on the user's machine via CC. If an audit is needed, write a CC task whose first step invokes the appropriate Seldon CLI tools. Findings go into the graph as Issues/ResearchTasks, not as prose in chat.

### If You Are a CC Session (Claude Code)

- Execute the CC task you were given.
- After completing the task, run `seldon cc complete <task-filepath>` to record it in the graph.
- After any edit to section/chapter files, run `seldon verify` before reporting completion.
- `seldon verify --fix` handles automatic fixes (file sync, ontology sync, file registration).
- Report any issues that `--fix` cannot resolve.

### All Sessions

- Start with `seldon go` (this command) to orient.
- End with `seldon closeout` for session handoff, then `seldon verify` before commit.
- Never write literal numbers for research results — use `{{result:NAME:value}}`.
- Never hardcode figure/table numbers — use `{{figure:NAME}}` and `{{table:NAME}}`.
- The graph is the source of truth, not files. Files are projections of graph state.
- Before describing any workflow, process, or pipeline to the user, verify by reading the relevant convention document (docs/conventions/) or querying the graph. Never reconstruct a process from inference. If you don't know, say so.
- Before asserting the state of a task, artifact, or run, query the graph first. Do not rely on memory or handoff text that may be stale."""

_AVAILABLE_COMMANDS_SECTION = """\
## Available Seldon Commands

### Session
- `seldon go` — orient to project (this command)
- `seldon briefing` — detailed session briefing
- `seldon closeout` — end session, log notebook entry
- `seldon verify [--fix] [--quiet]` — **run before every commit**: checks file integrity, ontology freshness, glossary, references, stale artifacts, unregistered files

### Artifacts & Links
- `seldon artifact create/list/update` — manage artifacts
- `seldon link create/list` — manage relationships
- `seldon result register/verify/list/trace` — result registry
- `seldon task create/list/update` — task tracking
- `seldon issue create/list/update/show/summary` — issue tracking (Eisenhower 3×3)
- `seldon cc complete <filepath>` — record a CC task as completed (run after each task)

### Paper/Book
- `seldon paper sync` — reconcile graph with files on disk (content hashes, subsection parsing, reference edges)
- `seldon paper build [--no-render]` — resolve `{{result:...}}`, `{{figure:...}}`, `{{table:...}}` tokens and assemble
- `seldon paper audit` — prose quality checks (Tier 2/3)
- `seldon paper impact <n>` — blast radius: what's affected if this artifact changes
- `seldon paper context <section-name> [--format yaml|text]` — structured context for drafting/revision (anchor props, assumes, cross-refs, siblings)

### Ontology
- `seldon ontology ingest` — parse vocabulary markdown, write to master (seldon-ontology)
- `seldon ontology sync` — pull latest vocabulary from master into this project
- `seldon ontology list [--category] [--verbose] [--master]` — show inherited terms

### Documentation
- `seldon docs check` — documentation completeness
- `seldon docs generate` — project reference docs from graph
- `seldon status` — project overview

### MCP Tools (Desktop sessions)
- `seldon_go(project_dir, brief)` — orient to project
- `seldon_task_create(description, project_dir, blocks)` — create ResearchTask
- `seldon_task_update(task_id, state, project_dir, note)` — single state transition
- `seldon_task_close(task_id, project_dir, note)` — walk task to completed in one call
- `seldon_task_list(project_dir, state_filter, brief)` — list tasks by state
- `seldon_issue_create(name, description, importance, urgency, project_dir)` — create Issue
- `seldon_issue_update(issue_id, project_dir, state, importance, urgency)` — update Issue
- `seldon_cc_complete(filepath, project_dir, note)` — mark CC task completed
- `seldon_cc_register(filepath, project_dir)` — register CC task as proposed
- `seldon_query(cypher, project_dir)` — read-only Cypher query"""


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


def _get_handoff_reconciliation(project_dir: str, handoff_text: str) -> Optional[str]:
    """Query completed CC tasks and annotate any mentioned in the handoff.

    Returns a markdown reconciliation section, or None if nothing to annotate.
    """
    try:
        config = load_project_config(project_dir)
        driver = get_neo4j_driver(config)
        database = config["neo4j"]["database"]

        try:
            with driver.session(database=database) as session:
                records = session.run(
                    "MATCH (t:Artifact:ResearchTask) "
                    "WHERE t.source_file STARTS WITH 'cc_tasks/' AND t.state = 'completed' "
                    "RETURN t.source_file AS source_file, t.completed_at AS completed_at, "
                    "t.name AS name"
                ).data()
        finally:
            driver.close()

        matches = []
        for r in records:
            source_file = r.get("source_file", "")
            filename = Path(source_file).name
            if filename in handoff_text or source_file in handoff_text:
                completed_at = r.get("completed_at", "")[:19] if r.get("completed_at") else "?"
                matches.append(f"- ✓ {source_file} — COMPLETED [{completed_at}Z]")

        if not matches:
            return None

        lines = ["### Handoff Reconciliation (from graph)", ""]
        lines.extend(matches)
        return "\n".join(lines)

    except Exception:
        return None


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
    sys_total = docs.get("system_total", 0)
    sys_present = docs.get("system_present", 0)
    if sys_total and sys_present < sys_total:
        sys_pct = int(sys_present / sys_total * 100)
        lines.append(f"**⚠ System properties:** {sys_present}/{sys_total} ({sys_pct}%) — run sync commands")

    open_issues = briefing_data.get("open_issues", [])
    do_now = [i for i in open_issues if i.get("importance") == "high" and i.get("urgency") == "high"]
    issue_count = len(open_issues)
    do_now_count = len(do_now)
    lines.append("")
    lines.append(f"**Open Issues:** {issue_count} ({do_now_count} in DO NOW quadrant)")
    for issue in do_now:
        name = issue.get("name", "?")
        state = issue.get("state", "?")
        lines.append(f"- ⚡ [{state}] {name}")

    lines.append("")
    lines.append(
        f"**Graph:** {stats.get('total_nodes', 0)} nodes, "
        f"{stats.get('total_relationships', 0)} relationships"
    )

    return "\n".join(lines)


def _get_agent_roles_section(project_dir: str) -> Optional[str]:
    """Return formatted Agent Roles and Workflows section, or None if unavailable."""
    try:
        config = load_project_config(project_dir)
        driver = get_neo4j_driver(config)
        database = config["neo4j"]["database"]

        try:
            with driver.session(database=database) as session:
                role_records = session.run(
                    "MATCH (r:AgentRole {state: 'active'}) RETURN r ORDER BY r.name"
                ).data()
                roles = [dict(r["r"]) for r in role_records]

                workflow_records = session.run(
                    "MATCH (w:Workflow {state: 'active'}) RETURN w ORDER BY w.name"
                ).data()
                workflows = [dict(r["w"]) for r in workflow_records]

                workflow_roles: dict[str, list[str]] = {}
                for wf in workflows:
                    wf_id = wf["artifact_id"]
                    linked = session.run(
                        "MATCH (w:Workflow {artifact_id: $id})-[:INCLUDES_ROLE]->(r:AgentRole) "
                        "RETURN r.display_name as name ORDER BY r.name",
                        id=wf_id,
                    ).data()
                    workflow_roles[wf_id] = [r["name"] for r in linked]
        finally:
            driver.close()

        if not roles and not workflows:
            return None

        lines: list[str] = []

        if roles:
            lines.append("## Agent Roles")
            lines.append("")
            for role in roles:
                display_name = role.get("display_name") or role.get("name", "Unknown")
                lines.append(f"### {display_name}")
                system_prompt = role.get("system_prompt")
                if system_prompt:
                    lines.append(system_prompt)
                    lines.append("")
                responsibilities = role.get("responsibilities")
                if responsibilities:
                    lines.append(f"**Responsibilities:** {responsibilities}")
                retrieval_profile = role.get("retrieval_profile")
                if retrieval_profile:
                    lines.append(f"**Retrieval:** {retrieval_profile}")
                cli_tools = role.get("cli_tools")
                if cli_tools:
                    lines.append(f"**CLI tools:** {cli_tools}")
                does_not_do = role.get("does_not_do")
                if does_not_do:
                    lines.append(f"**Boundaries:** {does_not_do}")
                lines.append("")

        if workflows:
            lines.append("---")
            lines.append("")
            lines.append("## Workflows")
            lines.append("")
            for wf in workflows:
                display_name = wf.get("display_name") or wf.get("name", "Unknown")
                lines.append(f"### {display_name}")
                trigger = wf.get("trigger")
                if trigger:
                    lines.append(f"**Trigger:** {trigger}")
                wf_id = wf["artifact_id"]
                role_names = workflow_roles.get(wf_id, [])
                if role_names:
                    lines.append(f"**Roles:** {', '.join(role_names)}")
                decomposition_strategy = wf.get("decomposition_strategy")
                if decomposition_strategy:
                    lines.append("**Decomposition:**")
                    lines.append(decomposition_strategy)
                success_criteria = wf.get("success_criteria")
                if success_criteria:
                    lines.append(f"**Success criteria:** {success_criteria}")
                lines.append("")

        # Strip trailing blank lines and return
        while lines and lines[-1] == "":
            lines.pop()

        return "\n".join(lines)

    except Exception:
        return None


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
        return "## Project State\n\n*Seldon graph not available. Project may not be initialized.*"


GATE_PROFILES: dict[str, dict] = {
    "academic_paper": {
        "gates": ["content_audit", "practitioner_stress_test", "bloom_depth_check", "secondary_sweep", "cascade_results", "review_synthesis"],
        "skipped": [],
    },
    "book_chapter": {
        "gates": ["content_audit", "practitioner_stress_test", "bloom_depth_check", "secondary_sweep", "cascade_results", "review_synthesis"],
        "skipped": [],
    },
    "policy_brief": {
        "gates": ["content_audit", "practitioner_stress_test", "secondary_sweep", "cascade_results", "review_synthesis"],
        "skipped": ["bloom_depth_check"],
    },
    "blog_post": {
        "gates": ["content_audit", "practitioner_stress_test", "secondary_sweep", "cascade_results", "review_synthesis"],
        "skipped": ["bloom_depth_check"],
    },
    "course_handout": {
        "gates": ["content_audit", "practitioner_stress_test", "bloom_depth_check", "secondary_sweep", "cascade_results", "review_synthesis"],
        "skipped": [],
    },
}


_VERDICT_SEVERITY = {
    "needs_revision": 0,
    "conditional_pass": 1,
    "conditionally_ready": 2,
    "clean": 3,
    "ready_to_ship": 4,
    "ready_for_submission": 4,
}


def _extract_verdict(manifest: dict) -> str:
    """Extract the run-level verdict from a run_manifest dict.

    Checks in priority order:
    1. Top-level ``verdict`` or ``overall_verdict``
    2. ``paper_status`` (semantic status field used by some runs)
    3. ``delta_summary.verdict`` (overall summary for delta runs)
    4. Worst-case aggregate across ``chapters_audited[N].verdict``
    5. ``"unknown"`` if nothing found
    """
    # 1. Top-level canonical fields
    for key in ("verdict", "overall_verdict"):
        v = manifest.get(key)
        if v and isinstance(v, str):
            return v

    # 2. paper_status (semantic equivalent used by some manifests)
    v = manifest.get("paper_status")
    if v and isinstance(v, str):
        return v

    # 3. delta_summary.verdict
    delta = manifest.get("delta_summary")
    if isinstance(delta, dict):
        v = delta.get("verdict")
        if v and isinstance(v, str):
            return v

    # 4. Aggregate across chapters_audited per-chapter verdicts (worst-case)
    chapters = manifest.get("chapters_audited", [])
    if isinstance(chapters, list) and chapters:
        chapter_verdicts = [
            c.get("verdict") for c in chapters
            if isinstance(c, dict) and c.get("verdict")
        ]
        if chapter_verdicts:
            # Return the worst verdict by severity rank (lowest score = worst)
            return min(
                chapter_verdicts,
                key=lambda v: _VERDICT_SEVERITY.get(v, 99),
            )

    return "unknown"


def _get_pipeline_section(project_dir: str) -> Optional[str]:
    """Return Audit Pipeline section for seldon go output, or None on error."""
    try:
        import yaml

        seldon_yaml = Path(project_dir) / "seldon.yaml"
        if not seldon_yaml.exists():
            return None

        with open(seldon_yaml) as f:
            config = yaml.safe_load(f)

        review_cfg = config.get("review", {}) or {}
        doc_type = review_cfg.get("document_type")

        lines = ["## Audit Pipeline", ""]

        if not doc_type:
            lines.append("**Not configured.** Add `review.document_type` to seldon.yaml to enable.")
            return "\n".join(lines)

        lines.append(f"**Document type:** {doc_type}")

        profile = GATE_PROFILES.get(doc_type)
        if profile:
            lines.append(f"**Gates:** {', '.join(profile['gates'])}")
            if profile["skipped"]:
                lines.append(f"**Skipped gates:** {', '.join(profile['skipped'])} ({doc_type})")
        else:
            lines.append(f"**Gates:** *(unknown profile for '{doc_type}' — update GATE_PROFILES)*")

        # Agent definitions
        agents_dir = Path(project_dir) / ".claude" / "agents"
        auditor_ok = (agents_dir / "auditor.md").exists()
        cascade_ok = (agents_dir / "cascade-checker.md").exists()
        auditor_sym = "✓" if auditor_ok else "✗"
        cascade_sym = "✓" if cascade_ok else "✗"
        agent_line = f"**Agent definitions:** auditor.md {auditor_sym}, cascade-checker.md {cascade_sym}"
        if not auditor_ok or not cascade_ok:
            agent_line += " — see docs/conventions/audit_pipeline.md §7"
        lines.append(agent_line)

        # Latest audit run
        audits_dir = Path(project_dir) / "audits"
        if audits_dir.is_dir():
            run_dirs = sorted(
                [d for d in audits_dir.iterdir() if d.is_dir() and d.name.startswith("run-")],
                key=lambda d: d.name,
            )
            if run_dirs:
                latest = run_dirs[-1]
                manifest_path = latest / "run_manifest.yaml"
                verdict = "unknown"
                if manifest_path.exists():
                    with open(manifest_path) as f:
                        manifest = yaml.safe_load(f) or {}
                    verdict = _extract_verdict(manifest)
                lines.append(f"**Last run:** {latest.name} — verdict: {verdict}")
            else:
                lines.append("**Last run:** *(none)*")
        else:
            lines.append("**Last run:** *(audits/ not found)*")

        return "\n".join(lines)

    except Exception:
        return None


def _resolve_project_dir(project_dir: str) -> str:
    """Resolve project_dir, falling back to SELDON_DEFAULT_PROJECT if project_dir is '.'."""
    if project_dir != ".":
        return project_dir
    env_path = os.environ.get("SELDON_DEFAULT_PROJECT")
    if env_path and (Path(env_path) / "seldon.yaml").exists():
        return env_path
    return project_dir


def assemble_go_context(
    project_dir: str = ".",
    brief: bool = False,
) -> str:
    """Assemble full orientation context for an AI consumer."""
    project_dir = _resolve_project_dir(project_dir)
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
        handoff_section = f"## Latest Handoff\n\n{handoff}"
        reconciliation = _get_handoff_reconciliation(project_dir, handoff)
        if reconciliation:
            handoff_section += f"\n\n{reconciliation}"
        sections.append(handoff_section)

    # Section 5 — Project State
    sections.append(_get_project_state_section(project_dir))

    # Section 5.5 — Audit Pipeline
    pipeline = _get_pipeline_section(project_dir)
    if pipeline is not None:
        sections.append(pipeline)

    # Section 6 — Agent Roles (optional — omit if no roles exist)
    agent_roles = _get_agent_roles_section(project_dir)
    if agent_roles is not None:
        sections.append(agent_roles)

    # Section 7 — Available Commands (always)
    sections.append(_AVAILABLE_COMMANDS_SECTION)

    return "\n\n---\n\n".join(sections)


def assemble_go_context_as_dict(
    project_dir: str = ".",
    brief: bool = False,
) -> dict:
    """Assemble orientation context as a structured dict for JSON output."""
    project_dir = _resolve_project_dir(project_dir)
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

    # Agent Roles
    agent_roles = _get_agent_roles_section(project_dir)

    # Available Commands
    available_commands = _AVAILABLE_COMMANDS_SECTION

    return {
        "role": role,
        "system_standards": system_standards,
        "project_context": project_context,
        "latest_handoff": latest_handoff,
        "project_state": project_state,
        "audit_pipeline": _get_pipeline_section(project_dir),
        "agent_roles": agent_roles,
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
