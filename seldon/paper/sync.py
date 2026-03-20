"""
Paper sync module — reconciles PaperSection files on disk with graph state.

Run after editing section markdown files to:
- Detect content changes via SHA-256 hash comparison
- Update CITES edges for added/removed {{result:...}} and {{cite:...}} references
- Transition states to stale when content changes (review/published → stale)
- Register untracked section files as new PaperSection artifacts

Note: {{figure:...}} references are scanned but not tracked as CITES edges because
the domain config restricts cites to_types to [Result, Citation].
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from neo4j import Driver

from seldon.core import graph as graph_module
from seldon.core.artifacts import (
    create_artifact,
    create_link,
    remove_link,
    transition_state,
    update_artifact,
)
from seldon.domain.loader import DomainConfig
from seldon.paper.build import REFERENCE_PATTERN


# Ref types trackable as CITES edges from PaperSection
# (domain config: cites from_types=[PaperSection, Figure], to_types=[Result, Citation])
CITES_REF_TYPES = {"result": "Result", "cite": "Citation"}

# States that should auto-transition to stale when content changes
STALE_ON_EDIT = {"review", "published"}


@dataclass
class SyncResult:
    """Outcome of syncing a single section file against its graph artifact."""

    filename: str
    status: str  # "unchanged" | "updated" | "untracked" | "registered"
    refs_added: list = field(default_factory=list)
    refs_removed: list = field(default_factory=list)
    state_changed: bool = False
    artifact_id: Optional[str] = None


def compute_file_hash(path: Path) -> str:
    """Return SHA-256 hex digest of the file content."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scan_references(text: str) -> set:
    """
    Extract {{type:name:field}} reference tokens, returning set of "type:name" keys.

    Only includes result and cite types (those trackable as CITES edges from
    a PaperSection node). Figure references are excluded from edge tracking.
    """
    refs = set()
    for match in REFERENCE_PATTERN.finditer(text):
        ref_type = match.group(1)
        name = match.group(2)
        if ref_type in CITES_REF_TYPES:
            refs.add(f"{ref_type}:{name}")
    return refs


def get_paper_section_artifacts(driver: Driver, database: str) -> dict:
    """
    Load all PaperSection artifacts from the graph.

    Returns a dict keyed by both 'name' and 'file_path' for flexible lookup.
    If a section has both, it appears under both keys (same dict value).
    """
    with driver.session(database=database) as session:
        records = session.run(
            "MATCH (a:Artifact:PaperSection) RETURN a"
        ).data()

    result = {}
    for r in records:
        artifact = dict(r["a"])
        if artifact.get("name"):
            result[artifact["name"]] = artifact
        if artifact.get("file_path"):
            result[artifact["file_path"]] = artifact
    return result


def _get_cites_edges(driver: Driver, database: str, artifact_id: str) -> dict:
    """
    Return existing outgoing CITES edges from a PaperSection.

    Returns dict keyed by "reftype:name" → target artifact_id.
    """
    with driver.session(database=database) as session:
        records = session.run(
            "MATCH (s:Artifact {artifact_id: $id})-[:CITES]->(t:Artifact) "
            "RETURN t.artifact_id AS target_id, t.artifact_type AS target_type, "
            "t.name AS target_name",
            id=artifact_id,
        ).data()

    edges = {}
    for r in records:
        target_name = r.get("target_name")
        target_type = r.get("target_type", "")
        if not target_name:
            continue
        for ref_type, art_type in CITES_REF_TYPES.items():
            if art_type == target_type:
                edges[f"{ref_type}:{target_name}"] = r["target_id"]
                break
    return edges


def _find_artifact_by_name(driver: Driver, database: str, name: str) -> Optional[dict]:
    """Find any artifact by its name property. Returns artifact dict or None."""
    with driver.session(database=database) as session:
        return graph_module.find_any_artifact_by_name(session, name)


def _extract_title(section_path: Path) -> str:
    """Extract the first # heading from a markdown file, or use stem as fallback."""
    text = section_path.read_text()
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return section_path.stem


def _register_section(
    driver: Driver,
    database: str,
    project_dir: Path,
    domain_config: DomainConfig,
    section_path: Path,
    actor: str,
) -> str:
    """
    Create a new PaperSection artifact for an untracked section file.

    Stores content_hash and creates initial CITES edges for any references
    found in the file, so the artifact is fully synced immediately after registration.
    """
    name = section_path.stem
    title = _extract_title(section_path)
    content_hash = compute_file_hash(section_path)

    artifact_id = create_artifact(
        project_dir=project_dir,
        driver=driver,
        database=database,
        domain_config=domain_config,
        artifact_type="PaperSection",
        properties={
            "name": name,
            "title": title,
            "file_path": str(section_path),
            "content_hash": content_hash,
        },
        actor=actor,
        authority="accepted",
    )

    # Create initial CITES edges for references found in the file
    text = section_path.read_text()
    for ref_key in sorted(scan_references(text)):
        ref_type, ref_name = ref_key.split(":", 1)
        target = _find_artifact_by_name(driver, database, ref_name)
        if target is None:
            continue
        create_link(
            project_dir=project_dir,
            driver=driver,
            database=database,
            domain_config=domain_config,
            from_id=artifact_id,
            to_id=target["artifact_id"],
            from_type="PaperSection",
            to_type=CITES_REF_TYPES[ref_type],
            rel_type="cites",
            actor=actor,
            authority="accepted",
        )

    return artifact_id


def sync_section(
    driver: Driver,
    database: str,
    project_dir: Path,
    domain_config: DomainConfig,
    section_path: Path,
    artifact: Optional[dict],
    dry_run: bool = False,
    auto_stale: bool = False,
    register_untracked: bool = False,
    actor: str = "human",
) -> SyncResult:
    """
    Sync a single section file against its PaperSection artifact.

    Returns a SyncResult describing what changed (or would change in dry_run mode).
    When dry_run=True, no JSONL events are written and no graph mutations occur.
    """
    filename = section_path.name

    if artifact is None:
        if register_untracked and not dry_run:
            artifact_id = _register_section(
                driver, database, project_dir, domain_config, section_path, actor
            )
            return SyncResult(
                filename=filename,
                status="registered",
                artifact_id=artifact_id,
            )
        return SyncResult(filename=filename, status="untracked")

    current_hash = compute_file_hash(section_path)
    stored_hash = artifact.get("content_hash")

    if stored_hash == current_hash:
        return SyncResult(
            filename=filename,
            status="unchanged",
            artifact_id=artifact["artifact_id"],
        )

    # Hash changed — reconcile references
    text = section_path.read_text()
    current_refs = scan_references(text)
    existing_edges = _get_cites_edges(driver, database, artifact["artifact_id"])
    existing_ref_keys = set(existing_edges.keys())

    added_refs = sorted(current_refs - existing_ref_keys)
    removed_refs = sorted(existing_ref_keys - current_refs)

    current_state = artifact.get("state", "proposed")
    state_changed_would = current_state in STALE_ON_EDIT and auto_stale

    if not dry_run:
        for ref_key in added_refs:
            ref_type, ref_name = ref_key.split(":", 1)
            target = _find_artifact_by_name(driver, database, ref_name)
            if target is None:
                continue
            create_link(
                project_dir=project_dir,
                driver=driver,
                database=database,
                domain_config=domain_config,
                from_id=artifact["artifact_id"],
                to_id=target["artifact_id"],
                from_type="PaperSection",
                to_type=CITES_REF_TYPES[ref_type],
                rel_type="cites",
                actor=actor,
                authority="accepted",
            )

        for ref_key in removed_refs:
            target_id = existing_edges[ref_key]
            remove_link(
                project_dir=project_dir,
                driver=driver,
                database=database,
                from_id=artifact["artifact_id"],
                to_id=target_id,
                rel_type="cites",
                actor=actor,
                authority="accepted",
            )

        update_artifact(
            project_dir=project_dir,
            driver=driver,
            database=database,
            artifact_id=artifact["artifact_id"],
            properties={"content_hash": current_hash},
            actor=actor,
            authority="accepted",
        )

        if state_changed_would:
            transition_state(
                project_dir=project_dir,
                driver=driver,
                database=database,
                domain_config=domain_config,
                artifact_id=artifact["artifact_id"],
                artifact_type="PaperSection",
                current_state=current_state,
                new_state="stale",
                actor=actor,
                authority="accepted",
            )

    return SyncResult(
        filename=filename,
        status="updated",
        refs_added=added_refs,
        refs_removed=removed_refs,
        state_changed=state_changed_would,
        artifact_id=artifact["artifact_id"],
    )


def sync_all(
    driver: Driver,
    database: str,
    project_dir: Path,
    domain_config: DomainConfig,
    paper_dir: Path,
    dry_run: bool = False,
    auto_stale: bool = False,
    register_untracked: bool = False,
    actor: str = "human",
) -> list:
    """
    Discover section files and sync each against graph state.

    Sections are discovered from paper_dir/sections/*.md.
    Returns list of SyncResult for all sections found.
    """
    sections_dir = paper_dir / "sections"
    if not sections_dir.exists():
        return []

    section_paths = sorted(sections_dir.glob("*.md"))
    section_artifacts = get_paper_section_artifacts(driver, database)

    results = []
    for path in section_paths:
        # Look up by stem name first, then by full file path
        artifact = (
            section_artifacts.get(path.stem)
            or section_artifacts.get(str(path))
        )
        result = sync_section(
            driver=driver,
            database=database,
            project_dir=project_dir,
            domain_config=domain_config,
            section_path=path,
            artifact=artifact,
            dry_run=dry_run,
            auto_stale=auto_stale,
            register_untracked=register_untracked,
            actor=actor,
        )
        results.append(result)
    return results
