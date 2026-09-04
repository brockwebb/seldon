"""
seldon verify — project integrity checks.

Runs 9 checks in order: file hash integrity, ontology freshness,
glossary compliance, reference resolution, stale artifacts,
open blocking tasks, unregistered files, relationship-type case, and
task source-file resolution. Reports issues with actionable remediation
guidance.

Exit codes:
    Default mode:
        0 — all clean
        1 — warnings only (stale artifacts, open blocking tasks, missing task source files)
        2 — issues found (hash mismatch, ontology drift, unresolvable refs,
            unregistered files, non-canonical relationship types)
    Strict mode (--strict):
        0 — no Tier A violations (advisory findings may exist)
        2 — Tier A violations found (file hashes, ontology, glossary, references, unregistered files)
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import click

from seldon.config import (
    load_project_config,
    get_neo4j_driver,
    get_sections_dir,
    get_shared_ontology_sources,
    ONTOLOGY_MASTER_DB,
)
from seldon.domain.loader import load_domain_config
from seldon.paper.build import REFERENCE_PATTERN
from seldon.paper.glossary_check import find_vocabulary_rule_files, run_glossary_check
from seldon.paper.numbering import XREF_PATTERN


# ---------------------------------------------------------------------------
# Result data structures
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    """Outcome of a single verification check."""

    name: str
    symbol: str  # "pass", "warn", "fail"
    summary: str
    details: list[str] = field(default_factory=list)
    fixable: bool = False


SYMBOL_MAP = {
    "pass": "\u2713",   # ✓
    "warn": "\u26a0",   # ⚠
    "fail": "\u2717",   # ✗
}

# Checks whose failures block under --strict mode.
# Advisory checks (stale artifacts, blocking tasks) are always reported
# but never block.
#
# "Relationship types" and "Task source files" are deliberately NOT Tier A.
# Both report a property of accumulated graph history rather than of the change
# in hand: an executing agent cannot make either clean by doing its task
# correctly. --strict is the machine gate CC tasks run before a state
# transition, so putting a historical data condition in it would block every
# task in any project that adopted Seldon with a legacy graph. Default
# `seldon verify` still surfaces them (see each check for its severity).
TIER_A_CHECKS = frozenset({
    "File hashes",
    "Ontology",
    "Glossary",
    "References",
    "Unregistered files",
})


# ---------------------------------------------------------------------------
# Observability emission (AD-024)
# ---------------------------------------------------------------------------

def _emit_verify_metrics(
    project_name: str,
    results: list["CheckResult"],
    strict: bool,
) -> None:
    """Emit one metric row per check to the observability substrate.

    Best-effort: any exception is swallowed. Verify must never fail
    because observability is down.

    Metric names (dot-notation per AD-024 convention):
      seldon.verify.check.status   — 0=pass, 1=warn, 2=fail
      seldon.verify.run.tier_a_fail_count
    Dimensions: {project, check_name, strict, tier_a}.
    """
    import json
    import sqlite3
    from datetime import datetime, timezone
    from pathlib import Path

    db_path = Path.home() / ".seldon-observability" / "metrics.db"
    if not db_path.parent.exists():
        return  # substrate not initialized on this host; skip silently

    status_map = {"pass": 0, "warn": 1, "fail": 2}
    ts = datetime.now(timezone.utc).isoformat()
    tier_a_fail = sum(
        1 for r in results if r.symbol == "fail" and r.name in TIER_A_CHECKS
    )

    try:
        conn = sqlite3.connect(db_path, timeout=2.0)
        try:
            for r in results:
                dims = {
                    "project": project_name,
                    "check_name": r.name,
                    "strict": strict,
                    "tier_a": r.name in TIER_A_CHECKS,
                }
                conn.execute(
                    "INSERT INTO metrics(timestamp, metric_name, metric_value, "
                    "scope, dimensions, collected_by) VALUES (?,?,?,?,?,?)",
                    (
                        ts,
                        "seldon.verify.check.status",
                        float(status_map.get(r.symbol, -1)),
                        project_name,
                        json.dumps(dims),
                        "seldon_verify_v1",
                    ),
                )
            conn.execute(
                "INSERT INTO metrics(timestamp, metric_name, metric_value, "
                "scope, dimensions, collected_by) VALUES (?,?,?,?,?,?)",
                (
                    ts,
                    "seldon.verify.run.tier_a_fail_count",
                    float(tier_a_fail),
                    project_name,
                    json.dumps({"project": project_name, "strict": strict}),
                    "seldon_verify_v1",
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        # Never let observability break verify. Silent failure by design.
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_domain_config(config: dict):
    domain_name = config["project"].get("domain", "research")
    domain_yaml = Path(__file__).parent.parent / "domain" / f"{domain_name}.yaml"
    return load_domain_config(domain_yaml)


def _sha256(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tracked_content_dirs(project_dir: Path, config: dict = None) -> list[Path]:
    """Return content directories that should be scanned for unregistered files.

    Uses get_sections_dir from config if available, otherwise falls back
    to checking paper/sections/ and book/ under project_dir.
    """
    if config is not None:
        from seldon.config import get_sections_dir
        sections = get_sections_dir(config, project_dir)
        return [sections] if sections.exists() and sections.is_dir() else []

    candidates = [
        project_dir / "paper" / "sections",
        project_dir / "book",
    ]
    return [d for d in candidates if d.exists() and d.is_dir()]


# ---------------------------------------------------------------------------
# Check 1: File hash integrity
# ---------------------------------------------------------------------------

def _snapshot_note(n: int) -> str:
    """Informational suffix for the file-hash line (AD-027)."""
    return f"{n} snapshot artifact{'s' if n != 1 else ''}, drift not checked"


def check_file_hashes(driver, database: str, project_dir: Path) -> CheckResult:
    """Compare on-disk SHA-256 against content_hash stored in graph.

    Two carve-outs (AD-027):

    * Artifacts with ``snapshot: true`` record a file as it stood at registration;
      drift from the live file is the point of the artifact, so they are counted and
      reported informationally, never compared, and never offered to ``--fix``.
    * An artifact whose path resolves to a directory is a schema violation for that
      artifact (a DataFile/Script path must be a file). It is reported and the check
      continues instead of raising out of the whole verify run.
    """
    with driver.session(database=database) as session:
        records = session.run(
            "MATCH (a:Artifact) "
            "WHERE a.content_hash IS NOT NULL AND (a.file_path IS NOT NULL OR a.path IS NOT NULL) "
            "RETURN a"
        ).data()

    mismatched = []
    missing_files = []
    directories = []
    snapshots = 0
    total = 0

    for rec in records:
        node = dict(rec["a"])
        file_path_str = node.get("file_path") or node.get("path")
        if not file_path_str:
            continue

        if node.get("snapshot") is True:
            snapshots += 1
            continue

        file_path = Path(file_path_str)
        if not file_path.is_absolute():
            file_path = project_dir / file_path

        stored_hash = node.get("content_hash", "")
        total += 1

        if not file_path.exists():
            missing_files.append(file_path.name)
            continue

        if file_path.is_dir():
            directories.append(f"{file_path_str} ({node.get('artifact_type', 'Artifact')} "
                               f"{str(node.get('artifact_id', ''))[:8]})")
            continue

        disk_hash = _sha256(file_path)
        if disk_hash != stored_hash:
            mismatched.append(file_path.name)

    if mismatched or missing_files or directories:
        parts = []
        if mismatched:
            parts.append(f"{len(mismatched)} modified: {', '.join(mismatched)}")
        if missing_files:
            parts.append(f"{len(missing_files)} missing: {', '.join(missing_files)}")
        if directories:
            parts.append(
                f"{len(directories)} path{'es' if len(directories) != 1 else ''} "
                f"resolve{'s' if len(directories) == 1 else ''} to a directory "
                f"(schema violation): {', '.join(directories)}"
            )
        summary = " — ".join(parts)
        # Only drift is fixable by paper sync; a directory path is a registration error.
        fixable = bool(mismatched or missing_files)
        if fixable:
            summary += " — run `seldon paper sync`"
        if snapshots:
            summary += f" — {_snapshot_note(snapshots)}"
        return CheckResult(
            name="File hashes",
            symbol="fail",
            summary=summary,
            details=mismatched + missing_files + directories,
            fixable=fixable,
        )

    summary = f"All {total} tracked files in sync"
    if snapshots:
        summary += f" — {_snapshot_note(snapshots)}"
    return CheckResult(
        name="File hashes",
        symbol="pass",
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Check 2: Ontology freshness
# ---------------------------------------------------------------------------

def check_ontology_freshness(driver, database: str, config: dict) -> CheckResult:
    """Compare master ontology epoch against local replica epoch."""
    shared_cfg = config.get("shared_ontology")
    if not shared_cfg:
        return CheckResult(
            name="Ontology",
            symbol="pass",
            summary="No shared_ontology configured — skipping",
        )

    master_db = shared_cfg.get("master_db", ONTOLOGY_MASTER_DB)

    # Query master epoch
    try:
        with driver.session(database=master_db) as session:
            result = session.run(
                "MATCH (m:_OntologyMeta) RETURN m.epoch AS epoch"
            ).single()
            master_epoch = (result["epoch"] if result else None) or 0
    except Exception as exc:
        return CheckResult(
            name="Ontology",
            symbol="warn",
            summary=f"Could not query master ontology DB — {exc}",
        )

    # Query local replica epoch
    with driver.session(database=database) as session:
        result = session.run(
            "MATCH (m:_OntologyReplicaMeta) RETURN m.last_epoch AS epoch"
        ).single()
        local_epoch = (result["epoch"] if result else None) or 0

    if master_epoch > local_epoch:
        return CheckResult(
            name="Ontology",
            symbol="fail",
            summary=f"Local epoch {local_epoch}, master epoch {master_epoch} — run `seldon ontology sync`",
            fixable=True,
        )

    return CheckResult(
        name="Ontology",
        symbol="pass",
        summary=f"Up to date (epoch {local_epoch})",
    )


# ---------------------------------------------------------------------------
# Check 3: Glossary compliance
# ---------------------------------------------------------------------------

def _find_glossary(project_dir: Path, config: dict = None) -> Path | None:
    """Locate glossary.md using config paths, then conventional fallbacks.

    Used only for backward-compatibility when shared_ontology is not configured.
    """
    if config:
        for key in ("paper", "book"):
            content_dir = config.get("paths", {}).get(key)
            if content_dir:
                candidate = project_dir / content_dir / "glossary.md"
                if candidate.exists():
                    return candidate

    for candidate in [
        project_dir / "paper" / "glossary.md",
        project_dir / "book" / "glossary.md",
    ]:
        if candidate.exists():
            return candidate

    return None


def _find_check_script(project_dir: Path, glossary_path: Path) -> Path | None:
    """Locate check_glossary.py near the glossary or at fallback locations.

    Used only for backward-compatibility when shared_ontology is not configured.
    """
    candidates = [
        glossary_path.parent / "check_glossary.py",
        project_dir / "paper" / "check_glossary.py",
        project_dir / "check_glossary.py",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def check_glossary(project_dir: Path, config: dict = None) -> CheckResult:
    """Run glossary compliance check.

    Resolution order:
    1. shared_ontology configured → read vocabulary_rules.yaml companions →
       run built-in enforcement against section files. No local glossary needed.
    2. shared_ontology not configured, local glossary.md found →
       run project-local check_glossary.py (backward compat).
    3. Neither → warn with remediation hint.
    """
    cfg = config or {}

    # --- Path 1: shared_ontology (preferred) --------------------------------
    vocab_paths = get_shared_ontology_sources(cfg)
    if vocab_paths:
        rule_paths = find_vocabulary_rule_files(vocab_paths)
        if not rule_paths:
            return CheckResult(
                name="Glossary",
                symbol="warn",
                summary=(
                    "shared_ontology configured but no vocabulary_rules.yaml found — "
                    "add one alongside each vocabulary file to enable enforcement"
                ),
            )

        sections_dir = get_sections_dir(cfg, project_dir)
        section_paths = sorted(sections_dir.glob("*.md")) if sections_dir.exists() else []

        # Write keyword index alongside sections if the directory exists
        index_out = sections_dir.parent / "keyword_index.md" if sections_dir.exists() else None

        count, messages = run_glossary_check(rule_paths, section_paths, index_out)
        rule_labels = ", ".join(p.parent.name for p in rule_paths)

        if count:
            return CheckResult(
                name="Glossary",
                symbol="fail",
                summary=f"{count} violation{'s' if count != 1 else ''} found ({rule_labels})",
                details=messages[:10],
            )
        return CheckResult(
            name="Glossary",
            symbol="pass",
            summary=f"No violations ({rule_labels})",
        )

    # --- Path 2: local glossary.md + check_glossary.py (backward compat) ---
    glossary_path = _find_glossary(project_dir, cfg)
    if glossary_path is None:
        return CheckResult(
            name="Glossary",
            symbol="warn",
            summary=(
                "No shared_ontology configured and no local glossary.md found — "
                "vocabulary enforcement skipped. "
                "Add shared_ontology to seldon.yaml to enable central enforcement."
            ),
        )

    check_script = _find_check_script(project_dir, glossary_path)
    if check_script is None:
        return CheckResult(
            name="Glossary",
            symbol="pass",
            summary="No check_glossary.py found — skipping",
        )

    try:
        result = subprocess.run(
            [sys.executable, str(check_script)],
            capture_output=True,
            text=True,
            cwd=str(project_dir),
            timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return CheckResult(
            name="Glossary",
            symbol="warn",
            summary=f"Glossary check failed to run: {exc}",
        )

    rel_path = glossary_path.relative_to(project_dir)
    if result.returncode != 0:
        violations = [
            line.strip()
            for line in (result.stdout + result.stderr).splitlines()
            if line.strip()
        ]
        count = len(violations)
        return CheckResult(
            name="Glossary",
            symbol="fail",
            summary=f"{count} violation{'s' if count != 1 else ''} found ({rel_path})",
            details=violations[:10],
        )

    return CheckResult(
        name="Glossary",
        symbol="pass",
        summary=f"No violations ({rel_path})",
    )


# ---------------------------------------------------------------------------
# Check 4: Reference resolution
# ---------------------------------------------------------------------------

def check_references(driver, database: str, project_dir: Path) -> CheckResult:
    """Scan PaperSection files for unresolvable reference and XREF tokens."""
    # Get all PaperSection artifacts with file paths
    with driver.session(database=database) as session:
        records = session.run(
            "MATCH (a:Artifact:PaperSection) WHERE a.file_path IS NOT NULL RETURN a"
        ).data()

    section_files = []
    for rec in records:
        node = dict(rec["a"])
        fp = Path(node["file_path"])
        if not fp.is_absolute():
            fp = project_dir / fp
        if fp.exists():
            section_files.append(fp)

    if not section_files:
        return CheckResult(
            name="References",
            symbol="pass",
            summary="No PaperSection files to check",
        )

    # Collect all referenced names
    result_refs = set()   # (reftype, name) from REFERENCE_PATTERN
    xref_refs = set()     # (xreftype, name) from XREF_PATTERN

    for fp in section_files:
        text = fp.read_text(encoding="utf-8")
        for m in REFERENCE_PATTERN.finditer(text):
            result_refs.add((m.group(1), m.group(2)))
        for m in XREF_PATTERN.finditer(text):
            xref_refs.add((m.group(1), m.group(2)))

    total_tokens = len(result_refs) + len(xref_refs)

    # Check resolution against the graph
    unresolved = []

    with driver.session(database=database) as session:
        # Check result/figure/cite references
        reftype_to_label = {"result": "Result", "figure": "Figure", "cite": "Citation"}
        for reftype, name in result_refs:
            label = reftype_to_label.get(reftype)
            if not label:
                unresolved.append(f"{reftype}:{name} (unknown type)")
                continue
            result = session.run(
                f"MATCH (a:Artifact:{label}) WHERE a.name = $name RETURN count(a) AS n",
                name=name,
            ).single()
            if result["n"] == 0:
                unresolved.append(f"{reftype}:{name}")

        # Check XREF references (figure/table/section)
        xreftype_to_label = {
            "figure": "Figure",
            "table": "Table",
            "section": "PaperSection",
        }
        for xreftype, name in xref_refs:
            label = xreftype_to_label.get(xreftype)
            if not label:
                unresolved.append(f"{xreftype}:{name} (unknown type)")
                continue
            result = session.run(
                f"MATCH (a:Artifact:{label}) WHERE a.name = $name RETURN count(a) AS n",
                name=name,
            ).single()
            if result["n"] == 0:
                unresolved.append(f"{xreftype}:{name}")

    if unresolved:
        return CheckResult(
            name="References",
            symbol="fail",
            summary=f"{len(unresolved)} unresolvable: {', '.join(unresolved[:5])}",
            details=unresolved,
        )

    return CheckResult(
        name="References",
        symbol="pass",
        summary=f"All {total_tokens} tokens resolve",
    )


# ---------------------------------------------------------------------------
# Check 5: Stale artifacts
# ---------------------------------------------------------------------------

def check_stale_artifacts(driver, database: str) -> CheckResult:
    """Find artifacts in stale state and report blast radius."""
    with driver.session(database=database) as session:
        records = session.run(
            "MATCH (a:Artifact {state: 'stale'}) RETURN a"
        ).data()

    if not records:
        return CheckResult(
            name="Stale artifacts",
            symbol="pass",
            summary="None",
        )

    details = []
    with driver.session(database=database) as session:
        for rec in records:
            node = dict(rec["a"])
            name = node.get("name", node.get("artifact_id", "?")[:8])
            # Count direct dependents (incoming edges)
            dep_result = session.run(
                "MATCH (dep:Artifact)-[]->(a:Artifact {artifact_id: $id}) "
                "RETURN dep.name AS name",
                id=node["artifact_id"],
            ).data()
            dep_names = [d["name"] for d in dep_result if d["name"]]
            if dep_names:
                details.append(f"{name} (impacts: {', '.join(dep_names[:3])})")
            else:
                details.append(name)

    count = len(records)
    summary_items = details[:3]
    return CheckResult(
        name="Stale artifacts",
        symbol="warn",
        summary=f"{count} stale: {', '.join(summary_items)}",
        details=details,
    )


# ---------------------------------------------------------------------------
# Check 6: Open blocking tasks
# ---------------------------------------------------------------------------

def check_blocking_tasks(driver, database: str) -> CheckResult:
    """Find ResearchTasks in active states that block other artifacts."""
    with driver.session(database=database) as session:
        records = session.run(
            "MATCH (t:ResearchTask)-[:BLOCKS]->(target:Artifact) "
            "WHERE t.state IN ['accepted', 'in_progress'] "
            "RETURN t, collect(target.name) AS blocked_names"
        ).data()

    if not records:
        return CheckResult(
            name="Blocking tasks",
            symbol="pass",
            summary="None",
        )

    details = []
    for rec in records:
        task = dict(rec["t"])
        desc = (task.get("description") or task.get("name") or task.get("artifact_id", "?")[:8])[:50]
        blocked = [n for n in rec["blocked_names"] if n]
        if blocked:
            details.append(f"'{desc}' blocks {', '.join(blocked)}")
        else:
            details.append(f"'{desc}'")

    count = len(records)
    return CheckResult(
        name="Blocking tasks",
        symbol="warn",
        summary=f"{count} blocking: {details[0]}" if count == 1 else f"{count} blocking tasks",
        details=details,
    )


# ---------------------------------------------------------------------------
# Check 7: Unregistered files
# ---------------------------------------------------------------------------

def check_unregistered_files(
    driver, database: str, project_dir: Path, config: dict = None
) -> CheckResult:
    """Find .md files in tracked directories that have no corresponding artifact."""
    tracked_dirs = _tracked_content_dirs(project_dir, config)
    if not tracked_dirs:
        return CheckResult(
            name="Unregistered files",
            symbol="pass",
            summary="No tracked content directories found — skipping",
        )

    # Gather all .md files on disk
    disk_files: dict[str, Path] = {}
    for d in tracked_dirs:
        for md in sorted(d.glob("*.md")):
            disk_files[str(md)] = md

    if not disk_files:
        return CheckResult(
            name="Unregistered files",
            symbol="pass",
            summary="No content files found",
        )

    # Query all artifact file_path values
    with driver.session(database=database) as session:
        records = session.run(
            "MATCH (a:Artifact) WHERE a.file_path IS NOT NULL RETURN a.file_path AS fp"
        ).data()

    registered_paths = set()
    for rec in records:
        fp = rec["fp"]
        registered_paths.add(fp)
        # Also normalise to absolute
        abs_fp = Path(fp)
        if not abs_fp.is_absolute():
            abs_fp = project_dir / fp
        registered_paths.add(str(abs_fp))

    unregistered = []
    for path_str, path_obj in disk_files.items():
        if path_str not in registered_paths and str(path_obj) not in registered_paths:
            # Also check by relative path
            try:
                rel = str(path_obj.relative_to(project_dir))
            except ValueError:
                rel = ""
            if rel not in registered_paths:
                unregistered.append(path_obj)

    if unregistered:
        names = [p.name for p in unregistered]
        return CheckResult(
            name="Unregistered files",
            symbol="fail",
            summary=f"{len(unregistered)} unregistered: {', '.join(names[:5])}",
            details=[str(p) for p in unregistered],
            fixable=True,
        )

    return CheckResult(
        name="Unregistered files",
        symbol="pass",
        summary=f"All {len(disk_files)} files registered",
    )


# ---------------------------------------------------------------------------
# Check 8: Relationship-type case
# ---------------------------------------------------------------------------

#: Remediation command printed when non-canonical relationship types are found.
#: Deliberately NOT wired into `--fix`: renaming a relationship type deletes and
#: recreates edges, which is a migration, not a sync. It gets its own
#: dry-run-by-default command so the operator sees the plan before it runs.
REL_TYPE_MIGRATION_CMD = (
    "python scripts/migrations/2026-09-04_migrate_rel_type_case.py --apply"
)


def check_relationship_types(driver, database: str) -> CheckResult:
    """Fail when the graph holds relationships stored in non-canonical case.

    UPPERCASE is canonical by construction: ``seldon.core.artifacts.create_link``
    and ``remove_link`` both uppercase before writing, and event replay in
    ``seldon.core.sync`` does the same. A type stored in any other case cannot
    have come from a sanctioned write, and every type-filtered query in the
    codebase names the uppercase form — so the non-canonical twin is not merely
    untidy, it is *silently invisible*. That is why this is a ``fail`` and not a
    warning: the failure mode is a query returning a confidently wrong answer.

    It is still not Tier A. See ``TIER_A_CHECKS``.

    Uses a full relationship scan rather than ``db.relationshipTypes()``
    because Neo4j retains a type token after the last relationship carrying it
    is deleted; the metadata call would keep reporting a type this project has
    already migrated away from.

    Args:
        driver: Neo4j driver.
        database: Project database name. Scoped to this database only — the
            check never looks at any other project's graph.

    Returns:
        A CheckResult named "Relationship types".
    """
    from seldon.core.graph import find_noncanonical_rel_types

    with driver.session(database=database) as session:
        offenders = find_noncanonical_rel_types(session)

    if not offenders:
        return CheckResult(
            name="Relationship types",
            symbol="pass",
            summary="All canonical (uppercase)",
        )

    details = [
        f"{o['rel_type']} ({o['count']} relationship"
        f"{'s' if o['count'] != 1 else ''}) → should be {o['canonical']}"
        for o in offenders
    ]
    details.append(f"Migrate with: {REL_TYPE_MIGRATION_CMD}")
    total = sum(o["count"] for o in offenders)
    return CheckResult(
        name="Relationship types",
        symbol="fail",
        summary=(
            f"{len(offenders)} non-canonical type"
            f"{'s' if len(offenders) != 1 else ''} "
            f"({total} relationship{'s' if total != 1 else ''}) — "
            "invisible to type-filtered queries"
        ),
        details=details,
    )


# ---------------------------------------------------------------------------
# Check 9: Task source files
# ---------------------------------------------------------------------------

#: How many missing source files to name individually before summarising the
#: rest. This check runs before every commit and its finding is permanent for
#: settled history, so an uncapped dump would train the reader to skip it.
MAX_MISSING_DETAILS = 10


#: The state machine edge that identifies an *unfinished* ResearchTask.
#:
#: `seldon/domain/research.yaml` documents `superseded` as "an honest terminal
#: for a task overtaken/obsoleted *before* it finishes — reachable only from
#: active, non-finished states. NOT reachable from completed/verified." So the
#: set of states offering `superseded` is the domain config's own declaration of
#: which states mean "still awaiting execution", and reading it here keeps this
#: check and the orphan-supersede migration on one definition.
#:
#: A leaf-node test would be wrong: `completed` has a successor (`verified`) yet
#: is finished, so "no outgoing transitions" would misclassify every completed
#: task as open.
_UNFINISHED_MARKER_STATE = "superseded"


def open_task_states(domain_config) -> set[str]:
    """Return the ResearchTask states that mean "still awaiting execution".

    Args:
        domain_config: Loaded domain configuration.

    Returns:
        Set of state names from which :data:`_UNFINISHED_MARKER_STATE` is
        reachable. Empty if the domain defines no ResearchTask machine.
    """
    machine = domain_config.state_machines.get("ResearchTask", {})
    return {
        state
        for state, nexts in machine.items()
        if _UNFINISHED_MARKER_STATE in nexts
    }


def check_task_source_files(
    driver, database: str, project_dir: Path, config: dict = None
) -> CheckResult:
    """Report ResearchTasks naming a ``source_file`` that is not on disk.

    A ResearchTask's ``source_file`` is the task's specification — the only
    place its scope, success criteria and boundaries are recorded. When the file
    is gone the graph node is a stub: it says a task existed, not what it was.

    Severity is graded by whether the task is still open, because the two cases
    are different problems:

    * An **open** task (``proposed`` / ``accepted`` / ``in_progress`` /
      ``blocked``) with no spec on disk is a live obstruction — nobody can
      execute it. That is a ``warn``, listed individually.
    * A **finished** task with no spec on disk is settled history. The work
      completed (or was rejected, superseded, withdrawn) and the graph records
      the outcome; only the spec is lost, and losing the spec of a finished task
      does not un-finish it. Counted in the summary, never a warning.

    The alternative — warning on every missing file forever — produces a check
    that can never go green, which is a check people learn to ignore. This one
    goes green once the open orphans are resolved and goes amber again the
    moment a new one appears. The forward-looking half of the defect is enforced
    where it can be: at registration, by the git-tracking guard in
    ``seldon cc register`` / ``seldon cc complete``.

    Args:
        driver: Neo4j driver.
        database: Project database name.
        project_dir: Project root; relative ``source_file`` values resolve
            against it.
        config: Loaded project config, used to find the domain's state machine.
            When None, every state is treated as open — the conservative
            reading, since it can only over-report.

    Returns:
        A CheckResult named "Task source files".
    """
    with driver.session(database=database) as session:
        records = session.run(
            "MATCH (t:Artifact:ResearchTask) WHERE t.source_file IS NOT NULL "
            "RETURN t.artifact_id AS artifact_id, t.source_file AS source_file, "
            "t.state AS state ORDER BY t.source_file"
        ).data()

    if not records:
        return CheckResult(
            name="Task source files",
            symbol="pass",
            summary="No tasks carry a source_file",
        )

    missing = []
    for rec in records:
        path = Path(rec["source_file"])
        if not path.is_absolute():
            path = project_dir / path
        if not path.is_file():
            missing.append(rec)

    if not missing:
        return CheckResult(
            name="Task source files",
            symbol="pass",
            summary=f"All {len(records)} resolve on disk",
        )

    # No config → treat every state as open. Over-reporting is the safe failure
    # here; silently passing a live obstruction is not.
    open_states = (
        open_task_states(_get_domain_config(config))
        if config
        else {r["state"] for r in missing}
    )
    open_missing = [r for r in missing if r["state"] in open_states]
    settled_missing = [r for r in missing if r["state"] not in open_states]

    settled_note = (
        f"{len(settled_missing)} settled (finished task; spec lost, outcome recorded)"
    )

    if not open_missing:
        return CheckResult(
            name="Task source files",
            symbol="pass",
            summary=(
                f"No open task is missing its spec "
                f"({len(records) - len(missing)} of {len(records)} resolve on "
                f"disk); {settled_note}"
            ),
        )

    details = [
        f"{rec['artifact_id'][:8]}... [{rec['state']}] {rec['source_file']}"
        for rec in open_missing[:MAX_MISSING_DETAILS]
    ]
    if len(open_missing) > MAX_MISSING_DETAILS:
        details.append(
            f"... and {len(open_missing) - MAX_MISSING_DETAILS} more open task(s)"
        )
    if settled_missing:
        details.append(f"Also: {settled_note}")

    return CheckResult(
        name="Task source files",
        symbol="warn",
        summary=(
            f"{len(open_missing)} open task"
            f"{'s' if len(open_missing) != 1 else ''} name a source_file that is "
            f"not on disk — unexecutable as specified"
        ),
        details=details,
    )


# ---------------------------------------------------------------------------
# Fix actions
# ---------------------------------------------------------------------------

def _fix_file_hashes(project_dir: Path, quiet: bool = False) -> None:
    """Run seldon paper sync to update hashes."""
    kwargs = {}
    if quiet:
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.DEVNULL
    subprocess.run(
        [sys.executable, "-m", "seldon", "paper", "sync"],
        check=True,
        cwd=str(project_dir),
        **kwargs,
    )


def _fix_ontology(project_dir: Path, quiet: bool = False) -> None:
    """Run seldon ontology sync to pull latest vocabulary."""
    kwargs = {}
    if quiet:
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.DEVNULL
    subprocess.run(
        [sys.executable, "-m", "seldon", "ontology", "sync"],
        check=True,
        cwd=str(project_dir),
        **kwargs,
    )


def _fix_unregistered_files(
    driver, database: str, project_dir: Path, domain_config, unregistered_paths: list[str]
) -> int:
    """Create PaperSection artifacts for unregistered files. Returns count created."""
    from seldon.core.artifacts import create_artifact

    created = 0
    for path_str in unregistered_paths:
        path = Path(path_str)
        if not path.exists():
            continue

        name = path.stem
        title = name.replace("-", " ").replace("_", " ").title()
        content_hash = _sha256(path)

        try:
            file_path_val = str(path.relative_to(project_dir))
        except ValueError:
            file_path_val = str(path)

        create_artifact(
            project_dir=project_dir,
            driver=driver,
            database=database,
            domain_config=domain_config,
            artifact_type="PaperSection",
            properties={
                "name": name,
                "title": title,
                "file_path": file_path_val,
                "content_hash": content_hash,
            },
            actor="seldon-verify",
            authority="accepted",
        )
        created += 1

    return created


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------

@click.command("verify")
@click.option("--fix", is_flag=True, default=False,
              help="Auto-resolve fixable issues (file sync, ontology sync, register files).")
@click.option("--quiet", is_flag=True, default=False,
              help="Suppress all output; communicate only via exit code.")
@click.option("--strict", is_flag=True, default=False,
              help="Exit non-zero only on Tier A (mechanical) violations. "
                   "Advisory findings are reported but do not affect exit code.")
def verify_command(fix, quiet, strict):
    """Run 9 integrity checks on the current Seldon project.

    Checks file hashes, ontology freshness, glossary compliance, reference
    resolution, stale artifacts, blocking tasks, unregistered files,
    relationship-type case, and task source-file resolution.

    Exit codes: 0 = clean, 1 = warnings only, 2 = issues found.
    Use --strict to gate only on mechanical (Tier A) violations.
    """
    project_dir = Path.cwd()
    config = load_project_config(project_dir)
    driver = get_neo4j_driver(config)
    database = config["neo4j"]["database"]
    project_name = config["project"]["name"]
    domain_config = _get_domain_config(config)

    try:
        results = _run_all_checks(driver, database, config, project_dir)

        # Apply fixes if requested
        if fix:
            results = _apply_fixes(
                results, driver, database, project_dir, domain_config, config, quiet
            )
    finally:
        driver.close()

    # AD-024: emit one row per check to observability substrate (best-effort)
    _emit_verify_metrics(project_name, results, strict)

    # Output
    if not quiet:
        _print_report(project_name, results, strict=strict)

    # Exit code
    if strict:
        # Only Tier A failures are blocking
        tier_a_fail = any(
            r.symbol == "fail" and r.name in TIER_A_CHECKS
            for r in results
        )
        if tier_a_fail:
            raise SystemExit(2)
        else:
            raise SystemExit(0)
    else:
        # Default behavior: any fail → 2, any warn → 1, else 0
        has_fail = any(r.symbol == "fail" for r in results)
        has_warn = any(r.symbol == "warn" for r in results)
        if has_fail:
            raise SystemExit(2)
        elif has_warn:
            raise SystemExit(1)
        else:
            raise SystemExit(0)


def _run_all_checks(
    driver, database: str, config: dict, project_dir: Path
) -> list[CheckResult]:
    """Execute all 9 checks and return results."""
    return [
        check_file_hashes(driver, database, project_dir),
        check_ontology_freshness(driver, database, config),
        check_glossary(project_dir, config=config),
        check_references(driver, database, project_dir),
        check_stale_artifacts(driver, database),
        check_blocking_tasks(driver, database),
        check_unregistered_files(driver, database, project_dir, config),
        check_relationship_types(driver, database),
        check_task_source_files(driver, database, project_dir, config),
    ]


def _apply_fixes(
    results: list[CheckResult],
    driver,
    database: str,
    project_dir: Path,
    domain_config,
    config: dict,
    quiet: bool,
) -> list[CheckResult]:
    """Apply --fix actions and re-run affected checks."""
    check_names_to_fix = {
        "File hashes": _fix_file_hashes,
        "Ontology": _fix_ontology,
    }

    for r in results:
        if r.symbol == "fail" and r.fixable and r.name in check_names_to_fix:
            if not quiet:
                click.echo(f"  Fixing: {r.name}...")
            try:
                check_names_to_fix[r.name](project_dir, quiet=quiet)
            except subprocess.CalledProcessError as exc:
                if not quiet:
                    click.echo(f"  Fix failed for {r.name}: {exc}", err=True)

    # Handle unregistered files fix separately (needs driver)
    unreg = next((r for r in results if r.name == "Unregistered files"), None)
    if unreg and unreg.symbol == "fail" and unreg.fixable:
        if not quiet:
            click.echo(f"  Fixing: {unreg.name}...")
        count = _fix_unregistered_files(
            driver, database, project_dir, domain_config, unreg.details
        )
        if not quiet:
            click.echo(f"  Registered {count} file{'s' if count != 1 else ''}.")

    # Re-run checks after fixes
    return _run_all_checks(driver, database, config, project_dir)


def _print_report(
    project_name: str, results: list[CheckResult], strict: bool = False
) -> None:
    """Print the formatted verification report."""
    click.echo(f"\nseldon verify \u2014 {project_name}\n")

    # Find max name length for alignment
    max_name = max(len(r.name) for r in results)

    for r in results:
        sym = SYMBOL_MAP.get(r.symbol, "?")
        padded = r.name.ljust(max_name + 2)
        click.echo(f"  {sym} {padded}{r.summary}")
        for detail in r.details:
            click.echo(f"      {detail}")

    # Summary line
    issues = sum(1 for r in results if r.symbol == "fail")
    warnings = sum(1 for r in results if r.symbol == "warn")

    click.echo()
    if issues == 0 and warnings == 0:
        click.echo("  All checks passed.")
    else:
        parts = []
        if issues:
            parts.append(f"{issues} issue{'s' if issues != 1 else ''}")
        if warnings:
            parts.append(f"{warnings} warning{'s' if warnings != 1 else ''}")
        msg = ", ".join(parts) + "."
        fixable = sum(1 for r in results if r.symbol == "fail" and r.fixable)
        if fixable:
            msg += " Run `seldon verify --fix` to auto-resolve fixable issues."
        click.echo(f"  {msg}")

    if strict:
        advisory = sum(
            1 for r in results
            if r.symbol in ("fail", "warn") and r.name not in TIER_A_CHECKS
        )
        if advisory:
            click.echo(
                f"  Strict mode: {advisory} advisory finding{'s' if advisory != 1 else ''} "
                "reported but not blocking."
            )
    click.echo()
