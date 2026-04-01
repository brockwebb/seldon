"""
seldon verify — project integrity checks.

Runs 7 checks in order: file hash integrity, ontology freshness,
glossary compliance, reference resolution, stale artifacts,
open blocking tasks, and unregistered files. Reports issues with
actionable remediation guidance.

Exit codes:
    0 — all clean
    1 — warnings only (stale artifacts, open blocking tasks)
    2 — issues found (hash mismatch, ontology drift, unresolvable refs, unregistered files)
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

from seldon.config import load_project_config, get_neo4j_driver, ONTOLOGY_MASTER_DB
from seldon.domain.loader import load_domain_config
from seldon.paper.build import REFERENCE_PATTERN
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

def check_file_hashes(driver, database: str, project_dir: Path) -> CheckResult:
    """Compare on-disk SHA-256 against content_hash stored in graph."""
    with driver.session(database=database) as session:
        records = session.run(
            "MATCH (a:Artifact) "
            "WHERE a.content_hash IS NOT NULL AND (a.file_path IS NOT NULL OR a.path IS NOT NULL) "
            "RETURN a"
        ).data()

    mismatched = []
    missing_files = []
    total = 0

    for rec in records:
        node = dict(rec["a"])
        file_path_str = node.get("file_path") or node.get("path")
        if not file_path_str:
            continue

        file_path = Path(file_path_str)
        if not file_path.is_absolute():
            file_path = project_dir / file_path

        stored_hash = node.get("content_hash", "")
        total += 1

        if not file_path.exists():
            missing_files.append(file_path.name)
            continue

        disk_hash = _sha256(file_path)
        if disk_hash != stored_hash:
            mismatched.append(file_path.name)

    if mismatched or missing_files:
        parts = []
        if mismatched:
            parts.append(f"{len(mismatched)} modified: {', '.join(mismatched)}")
        if missing_files:
            parts.append(f"{len(missing_files)} missing: {', '.join(missing_files)}")
        return CheckResult(
            name="File hashes",
            symbol="fail",
            summary=" — ".join(parts) + " — run `seldon paper sync`",
            details=mismatched + missing_files,
            fixable=True,
        )

    return CheckResult(
        name="File hashes",
        symbol="pass",
        summary=f"All {total} tracked files in sync",
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

def check_glossary(project_dir: Path) -> CheckResult:
    """Run glossary check if paper/glossary.md exists."""
    glossary_path = project_dir / "paper" / "glossary.md"
    if not glossary_path.exists():
        return CheckResult(
            name="Glossary",
            symbol="pass",
            summary="No glossary file found — skipping",
        )

    check_script = project_dir / "paper" / "check_glossary.py"
    if not check_script.exists():
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

    if result.returncode != 0:
        # Extract violation lines from output
        violations = [
            line.strip()
            for line in (result.stdout + result.stderr).splitlines()
            if line.strip()
        ]
        count = len(violations)
        return CheckResult(
            name="Glossary",
            symbol="fail",
            summary=f"{count} violation{'s' if count != 1 else ''} found",
            details=violations[:10],  # cap detail output
        )

    return CheckResult(
        name="Glossary",
        symbol="pass",
        summary="No violations",
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
def verify_command(fix, quiet):
    """Run 7 integrity checks on the current Seldon project.

    Checks file hashes, ontology freshness, glossary compliance, reference
    resolution, stale artifacts, blocking tasks, and unregistered files.

    Exit codes: 0 = clean, 1 = warnings only, 2 = issues found.
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

    # Output
    if not quiet:
        _print_report(project_name, results)

    # Exit code
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
    """Execute all 7 checks and return results."""
    return [
        check_file_hashes(driver, database, project_dir),
        check_ontology_freshness(driver, database, config),
        check_glossary(project_dir),
        check_references(driver, database, project_dir),
        check_stale_artifacts(driver, database),
        check_blocking_tasks(driver, database),
        check_unregistered_files(driver, database, project_dir, config),
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


def _print_report(project_name: str, results: list[CheckResult]) -> None:
    """Print the formatted verification report."""
    click.echo(f"\nseldon verify \u2014 {project_name}\n")

    # Find max name length for alignment
    max_name = max(len(r.name) for r in results)

    for r in results:
        sym = SYMBOL_MAP.get(r.symbol, "?")
        padded = r.name.ljust(max_name + 2)
        click.echo(f"  {sym} {padded}{r.summary}")

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
    click.echo()
