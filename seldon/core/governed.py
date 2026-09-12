"""Import the governed-documents ledger into Seldon's own graph (AD-030).

AD-030-R10 makes the coupling between Seldon and Squiddy a stream specification rather than an
awareness: Squiddy parses a governed markdown file and returns ledger events conforming to a
schema Seldon supplied; Seldon consumes those events through its own write path and projects them
into its own database. This module is the whole of Seldon's half. It imports nothing from Squiddy
— a JSONL ledger is a file format, and the moment Seldon imported the producer it would be one
system with two repositories.

WHY THERE ARE TWO LEDGERS. Squiddy's `config.py` refuses any projection target whose database name
starts with `seldon-` (DI-005), and that guard is right: a second writer to a store whose single
write path lives elsewhere is the failure both repositories exist to prevent. So the governed graph
keeps its own ledger with no Neo4j backend, and what crosses the boundary is this file's reading of
that ledger.

IDEMPOTENCE IS BY CONTENT HASH (AD-030-R4). A document whose sha256 is unchanged produces no
events at all; a changed one produces an update and marks every edge that touches it `suspect`,
which is the existing stale-propagation discipline applied to structure instead of to Results.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from seldon.core import graph
from seldon.core.artifacts import create_artifact, transition_state, update_artifact

#: Where the governed graph lives, relative to the project root, when `seldon.yaml` says nothing.
DEFAULT_GRAPH_DIR = "governed"

#: The governed graph's ledger, relative to its own root.
LEDGER_RELATIVE = Path("ledger") / "events.jsonl"

#: Squiddy node class to Seldon artifact type. One-to-one by construction: the LinkML schema in
#: `governed/schema/governed.yaml` was written from the same five names AD-030 section 4 declares.
NODE_TYPES = {
    "Document": "Document",
    "Section": "Section",
    "Ruling": "Ruling",
    "Citation": "Citation",
    "Passage": "Passage",
}

#: Squiddy edge class to Seldon relationship type.
EDGE_TYPES = {
    "Contains": "contains",
    "Cites": "cites",
    "Extends": "extends",
    "DependsOn": "depends_on",
    "Mentions": "mentions",
    "Supersedes": "supersedes",
}

#: Properties copied verbatim from a governed node payload onto the Seldon artifact, per type.
#: Anything not listed is ledger bookkeeping (`asserted_at`, `status`, `prov_*`) that Seldon
#: records in its own envelope and must not duplicate as an artifact property.
NODE_PROPERTIES = {
    "Document": ("path", "content_hash", "doc_kind", "manifest_state", "reason", "decided_by",
                 "section_count", "ruling_count", "identifiers"),
    "Section": ("text", "content_hash", "heading", "section_path", "level", "span_start",
                "span_end", "identifiers"),
    "Ruling": ("text", "content_hash", "force", "matched_pattern", "ruling_identifier",
               "section_path", "span_start", "span_end", "identifiers"),
    "Citation": ("raw", "authors", "year", "doi"),
    "Passage": ("text", "content_hash", "quoted_in_section", "span_start", "span_end"),
}

#: Edge properties carried onto the Seldon relationship, per relationship type. Restricted to what
#: `research.yaml` declares, because `validate_relationship_properties` refuses anything else.
EDGE_PROPERTIES = {
    "cites": ("cito_type", "reason", "raw_reference"),
    "extends": ("raw_field",),
    "mentions": ("identifier", "identifier_kind", "occurrences"),
    "supersedes": ("reason",),
    "depends_on": (),
    "contains": (),
}

#: A leading identifier in a governed document's filename: `AD-030_...`, `DN-4_...`. This is how
#: this repository has always named its decisions, and the existing ArchitecturalDecision nodes
#: are named by exactly this string.
_FILENAME_IDENTIFIER_RE = re.compile(r"^((?:AD|DN)-\d+)")

#: A leading `YYYY-MM-DD_` in a filename, stripped when deriving a name.
_DATE_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[_-]")

#: An eight-hex artifact-id prefix, the form every Seldon surface prints.
_TASK_PREFIX_RE = re.compile(r"^[0-9a-f]{8}$")

#: Actor written on every event this module produces.
ACTOR = "governed_sync"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Locating and reading the ledger
# ---------------------------------------------------------------------------

def graph_dir(project_dir: Path, config: dict) -> Path:
    """Where the governed graph lives.

    Args:
        project_dir: Project root.
        config: Parsed seldon.yaml.

    Returns:
        Absolute path to the governed graph directory.
    """
    block = config.get("governed") or {}
    return Path(project_dir) / block.get("graph_dir", DEFAULT_GRAPH_DIR)


def ledger_path(project_dir: Path, config: dict) -> Path:
    """Path to the governed graph's ledger.

    Args:
        project_dir: Project root.
        config: Parsed seldon.yaml.

    Returns:
        Absolute path to `events.jsonl`.
    """
    return graph_dir(project_dir, config) / LEDGER_RELATIVE


@dataclass
class LedgerView:
    """The governed ledger replayed into its current state.

    Attributes:
        nodes: `(class, id)` to merged payload, last write winning per key — the same semantics
            Squiddy's own projection applies.
        edges: `(class, subject, object)` to merged payload.
    """

    nodes: dict[tuple[str, str], dict] = field(default_factory=dict)
    edges: dict[tuple[str, str, str], dict] = field(default_factory=dict)

    def documents(self) -> list[dict]:
        """Every Document payload, ordered by id."""
        return [p for (cls, _), p in sorted(self.nodes.items()) if cls == "Document"]


def read_ledger(path: Path) -> LedgerView:
    """Replay the governed ledger into its current state.

    Args:
        path: Path to `events.jsonl`.

    Returns:
        The replayed view. An absent ledger is an empty view, not an error: a project that has
        never run the ingest has nothing to sync, which is a state and not a fault.

    Raises:
        ValueError: If a line is not valid JSON. A corrupt ledger is fatal, never skipped —
            silently dropping one line would import a document with pieces missing and report
            success.
    """
    view = LedgerView()
    if not path.is_file():
        return view
    with path.open(encoding="utf-8") as handle:
        for lineno, raw in enumerate(handle, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"corrupt governed ledger at {path}:{lineno}: {exc}") from exc
            kind = event.get("kind")
            payload = event.get("payload") or {}
            etype = event.get("type")
            if kind == "node":
                view.nodes.setdefault((etype, payload.get("id")), {}).update(payload)
            elif kind == "edge":
                key = (etype, payload.get("subject"), payload.get("object"))
                view.edges.setdefault(key, {}).update(payload)
            elif kind == "retract":
                if "id" in payload:
                    view.nodes.pop((payload.get("type"), payload["id"]), None)
                elif "subject" in payload:
                    view.edges.pop(
                        (payload.get("type"), payload["subject"], payload["object"]), None
                    )
    return view


# ---------------------------------------------------------------------------
# Naming
# ---------------------------------------------------------------------------

def document_name(rel_path: str, claimed: Optional[set[str]] = None) -> str:
    """The Seldon `name` for a governed document.

    A design document names itself in its filename, and this repository's existing
    ArchitecturalDecision nodes are named by exactly that string (`AD-013`, `AD-021`). Following
    the convention rather than inventing one is what makes `MATCH (d {name: 'AD-030'})` the
    obvious query it looks like.

    TWO DOCUMENTS CAN SHARE A LEADING IDENTIFIER. `AD-030_governed_documents_as_graph_content.md`
    and `AD-030_implementation_findings_001.md` are not the same document — the second extends the
    first — but both filenames open with `AD-030`, so a name taken from the identifier alone
    collides and every query that uses it silently returns both. The bare identifier therefore goes
    to the FIRST claimant and every later one keeps its full stem. Callers iterate in sorted path
    order, which makes the assignment deterministic and stable across runs.

    Args:
        rel_path: Repo-relative path of the governed file.
        claimed: Names already taken, mutated in place as this one is claimed. None disables
            collision handling, which is correct only when naming a single document in isolation.

    Returns:
        The identifier when the filename carries one and it is free, else the filename stem with
        any date prefix stripped — the shape the DesignNote nodes already use.
    """
    stem = _DATE_PREFIX_RE.sub("", Path(rel_path).stem)
    match = _FILENAME_IDENTIFIER_RE.match(stem)
    name = match.group(1) if match else stem
    if claimed is not None:
        if name in claimed:
            name = stem
        claimed.add(name)
    return name


def assign_names(paths: Iterable[str]) -> dict[str, str]:
    """Assign a unique `name` to each governed document path.

    Args:
        paths: Repo-relative paths.

    Returns:
        Path to name. Sorted order makes the assignment deterministic; a path absent from the
        input cannot change the name of one that is present.
    """
    claimed: set[str] = set()
    return {path: document_name(path, claimed) for path in sorted(paths)}


# ---------------------------------------------------------------------------
# Reading Seldon's side
# ---------------------------------------------------------------------------

def existing_documents(driver, database: str) -> dict[str, dict]:
    """Every Document artifact already in the graph, keyed by its governed id.

    Args:
        driver: Neo4j driver.
        database: Database name.

    Returns:
        `governed_id` to `{artifact_id, content_hash, state, path}`.
    """
    with driver.session(database=database) as session:
        records = session.run(
            "MATCH (d:Artifact:Document) RETURN d.governed_id AS gid, "
            "d.artifact_id AS aid, d.content_hash AS hash, d.state AS state, d.path AS path, "
            "d.name AS name"
        ).data()
    return {
        r["gid"]: {"artifact_id": r["aid"], "content_hash": r["hash"],
                   "state": r["state"], "path": r["path"], "name": r["name"]}
        for r in records if r["gid"]
    }


def existing_children(driver, database: str) -> dict[str, dict]:
    """Every governed child artifact already in the graph, keyed by its governed id.

    Args:
        driver: Neo4j driver.
        database: Database name.

    Returns:
        `governed_id` to `{artifact_id, artifact_type, content_hash, state}`.
    """
    types = [t for t in NODE_TYPES.values() if t != "Document"]
    with driver.session(database=database) as session:
        records = session.run(
            "MATCH (n:Artifact) WHERE n.artifact_type IN $types AND n.governed_id IS NOT NULL "
            "RETURN n.governed_id AS gid, n.artifact_id AS aid, n.artifact_type AS type, "
            "n.content_hash AS hash, n.state AS state",
            types=types,
        ).data()
    return {
        r["gid"]: {"artifact_id": r["aid"], "artifact_type": r["type"],
                   "content_hash": r["hash"], "state": r["state"]}
        for r in records
    }


def legacy_nodes_by_path(driver, database: str) -> dict[str, dict]:
    """ArchitecturalDecision and DesignNote artifacts keyed by their `path`.

    A governed file that already has one of these carries a decision record this repository has
    been maintaining for months. The import points at it rather than re-deciding what it is.

    Args:
        driver: Neo4j driver.
        database: Database name.

    Returns:
        `path` to `{artifact_id, artifact_type, name}`.
    """
    with driver.session(database=database) as session:
        records = session.run(
            "MATCH (a:Artifact) WHERE a.artifact_type IN ['ArchitecturalDecision', 'DesignNote'] "
            "AND a.path IS NOT NULL "
            "RETURN a.path AS path, a.artifact_id AS aid, a.artifact_type AS type, a.name AS name"
        ).data()
    return {
        r["path"]: {"artifact_id": r["aid"], "artifact_type": r["type"], "name": r["name"]}
        for r in records
    }


def resolvable_targets(driver, database: str) -> tuple[dict[str, str], dict[str, str]]:
    """What an identifier reference can point at inside Seldon's graph.

    Args:
        driver: Neo4j driver.
        database: Database name.

    Returns:
        `(by_name, by_task_prefix)` — artifact name to `artifact_id` for the types a `mentions`
        edge may target, and eight-hex id prefix to full `artifact_id` for ResearchTasks. A
        prefix shared by two tasks is dropped from the map rather than guessed at.
    """
    with driver.session(database=database) as session:
        named = session.run(
            "MATCH (a:Artifact) WHERE a.artifact_type IN "
            "['Document', 'ArchitecturalDecision', 'DesignNote', 'SRS_Requirement'] "
            "AND a.name IS NOT NULL RETURN a.name AS name, a.artifact_id AS aid, "
            "a.artifact_type AS type"
        ).data()
        tasks = session.run(
            "MATCH (t:Artifact:ResearchTask) RETURN t.artifact_id AS aid"
        ).data()

    by_name: dict[str, str] = {}
    # A Document wins over a legacy node with the same name: both describe the same file, and the
    # Document is the one this import maintains.
    for record in sorted(named, key=lambda r: r["type"] != "Document"):
        by_name.setdefault(record["name"], record["aid"])

    prefixes: dict[str, list[str]] = {}
    for record in tasks:
        prefixes.setdefault(record["aid"][:8], []).append(record["aid"])
    by_prefix = {p: ids[0] for p, ids in prefixes.items() if len(ids) == 1}
    return by_name, by_prefix


def artifact_type_of(driver, database: str, artifact_id: str) -> Optional[str]:
    """Return an artifact's type, or None when it is absent.

    Args:
        driver: Neo4j driver.
        database: Database name.
        artifact_id: Full artifact id.

    Returns:
        The `artifact_type` property.
    """
    with driver.session(database=database) as session:
        record = session.run(
            "MATCH (a:Artifact {artifact_id: $aid}) RETURN a.artifact_type AS type",
            aid=artifact_id,
        ).single()
    return record["type"] if record else None


# ---------------------------------------------------------------------------
# Suspect propagation
# ---------------------------------------------------------------------------

def mark_edges_suspect(driver, database: str, artifact_ids: Iterable[str], reason: str) -> int:
    """Flag every relationship touching these artifacts for review.

    AD-030 section 4: a hash change on either end of an edge flags the edge. This reuses the
    stale-propagation discipline Results already have — the graph records that a link may no
    longer hold rather than deleting it, because deleting it would lose the fact that it once did.

    Args:
        driver: Neo4j driver.
        database: Database name.
        artifact_ids: Artifacts whose content changed.
        reason: Why, recorded on each edge.

    Returns:
        How many relationships were flagged.
    """
    ids = [i for i in artifact_ids if i]
    if not ids:
        return 0
    with driver.session(database=database) as session:
        record = session.run(
            "MATCH (a:Artifact)-[r]-(:Artifact) WHERE a.artifact_id IN $ids "
            "SET r.suspect = true, r.suspect_since = $now, r.suspect_reason = $reason "
            "RETURN count(r) AS n",
            ids=ids, now=_now_iso(), reason=reason,
        ).single()
    return record["n"] if record else 0


def clear_suspect(driver, database: str, artifact_ids: Iterable[str]) -> int:
    """Clear the suspect flag on relationships touching these artifacts.

    Called after a re-import has rewritten them from the document's current text: the edge has
    been re-derived, so the review the flag asked for has happened.

    Args:
        driver: Neo4j driver.
        database: Database name.
        artifact_ids: Artifacts whose edges were re-derived.

    Returns:
        How many relationships were cleared.
    """
    ids = [i for i in artifact_ids if i]
    if not ids:
        return 0
    with driver.session(database=database) as session:
        record = session.run(
            "MATCH (a:Artifact)-[r]-(:Artifact) WHERE a.artifact_id IN $ids AND r.suspect "
            "REMOVE r.suspect, r.suspect_since, r.suspect_reason RETURN count(r) AS n",
            ids=ids,
        ).single()
    return record["n"] if record else 0


# ---------------------------------------------------------------------------
# The admission invariant (AD-030-R5)
# ---------------------------------------------------------------------------

def admission_violations(view: LedgerView) -> list[str]:
    """Content edges whose Document is not `admitted` (AD-030-R5).

    The invariant the manifest-in-the-graph decision buys: one query, not a procedure. A declined
    or merely cataloged document must never receive a content edge, because a content edge asserts
    that the graph holds the document's content and a non-admitted document's content was never
    admitted.

    Args:
        view: The replayed ledger.

    Returns:
        One human-readable finding per violation. Empty when the invariant holds.
    """
    state_by_doc = {
        node_id: payload.get("manifest_state")
        for (cls, node_id), payload in view.nodes.items()
        if cls == "Document"
    }
    owner = {
        node_id: payload.get("doc_id")
        for (cls, node_id), payload in view.nodes.items()
        if cls != "Document"
    }
    findings = []
    for (etype, subject, obj) in sorted(view.edges):
        for endpoint in (subject, obj):
            doc = endpoint if endpoint in state_by_doc else owner.get(endpoint)
            if doc is None:
                continue
            state = state_by_doc.get(doc)
            if state != "admitted":
                findings.append(
                    f"{etype} edge {subject} -> {obj} touches document {doc}, whose "
                    f"manifest_state is {state!r}, not 'admitted' (AD-030-R5)"
                )
                break
    return findings


# ---------------------------------------------------------------------------
# The sync
# ---------------------------------------------------------------------------

@dataclass
class SyncReport:
    """What one `governed sync` run did.

    Attributes:
        documents_seen: Documents in the ledger.
        documents_created: Documents newly minted in Seldon's graph.
        documents_updated: Documents whose content hash had moved.
        documents_unchanged: Documents skipped because the hash matched.
        nodes_created: Child artifacts created, by type.
        nodes_updated: Child artifacts updated, by type.
        edges_created: Relationships created, by type.
        edges_suspect: Relationships flagged by a hash change.
        edges_cleared: Relationships whose suspect flag was cleared after re-derivation.
        linked_legacy: Documents matched to an existing ArchitecturalDecision or DesignNote.
        nodes_retired: Child artifacts the ledger no longer holds, by type.
        abstained: Identifier references that resolved to nothing, by identifier.
        violations: AD-030-R5 admission-invariant findings.
        dry_run: True when nothing was written.
    """

    documents_seen: int = 0
    documents_created: int = 0
    documents_updated: int = 0
    documents_unchanged: int = 0
    nodes_created: dict[str, int] = field(default_factory=dict)
    nodes_updated: dict[str, int] = field(default_factory=dict)
    edges_created: dict[str, int] = field(default_factory=dict)
    edges_suspect: int = 0
    edges_cleared: int = 0
    linked_legacy: int = 0
    nodes_retired: dict[str, int] = field(default_factory=dict)
    abstained: dict[str, int] = field(default_factory=dict)
    violations: list[str] = field(default_factory=list)
    dry_run: bool = False

    def bump(self, bucket: dict[str, int], key: str) -> None:
        """Increment one counter."""
        bucket[key] = bucket.get(key, 0) + 1

    @property
    def total_nodes_created(self) -> int:
        return sum(self.nodes_created.values())

    @property
    def total_edges_created(self) -> int:
        return sum(self.edges_created.values())


def out_of_date(project_dir: Path, config: dict, driver, database: str) -> list[str]:
    """Governed documents whose ledger hash differs from what the graph holds.

    Args:
        project_dir: Project root.
        config: Parsed seldon.yaml.
        driver: Neo4j driver.
        database: Database name.

    Returns:
        Repo-relative paths, sorted. Empty when the graph is current.
    """
    view = read_ledger(ledger_path(project_dir, config))
    have = existing_documents(driver, database)
    stale = []
    for payload in view.documents():
        current = have.get(payload["id"])
        if current is None or current["content_hash"] != payload.get("content_hash"):
            stale.append(payload.get("path") or payload["id"])
    return sorted(stale)


def _document_properties(payload: dict, rel_path: str, name: str) -> dict:
    """Seldon artifact properties for one governed Document payload.

    Args:
        payload: The Document node's ledger payload.
        rel_path: Repo-relative path of the file.
        name: The name assigned by :func:`assign_names`.

    Returns:
        Properties for the artifact, with None values dropped.
    """
    props = {
        "name": name,
        "governed_id": payload["id"],
        "title": payload.get("title"),
        "description": payload.get("title"),
    }
    for key in NODE_PROPERTIES["Document"]:
        if payload.get(key) is not None:
            props[key] = payload[key]
    return {k: v for k, v in props.items() if v is not None}


def _child_properties(cls: str, payload: dict, doc_path: str) -> dict:
    """Seldon artifact properties for one governed child payload."""
    props: dict[str, Any] = {
        "name": payload["id"],
        "governed_id": payload["id"],
        "source_document": doc_path,
    }
    for key in NODE_PROPERTIES[cls]:
        if payload.get(key) is not None:
            props[key] = payload[key]
    if cls == "Citation":
        # `key` and `title` are required on a Citation. A reference recovered from a governed
        # document has a document-scoped id, which is a key in the sense the slot means, and its
        # raw line stands in for a title until verification supplies a better one (AD-030-R6).
        props["key"] = payload["id"]
        props["title"] = payload.get("title") or (payload.get("raw") or "")[:200] or payload["id"]
    return props


def sync(
    *,
    project_dir: Path,
    config: dict,
    driver,
    database: str,
    domain_config,
    only: Optional[str] = None,
    dry_run: bool = False,
    session_id: Optional[str] = None,
) -> SyncReport:
    """Import the governed ledger into Seldon's graph.

    Args:
        project_dir: Project root.
        config: Parsed seldon.yaml.
        driver: Neo4j driver.
        database: Database name.
        domain_config: Loaded domain configuration.
        only: Sync just the document at this repo-relative path, or None for all.
        dry_run: Report what would change and write nothing.
        session_id: Session id stamped on the events.

    Returns:
        What the run did.

    Raises:
        ValueError: If the ledger is corrupt, or if the AD-030-R5 admission invariant does not
            hold. A content edge on a non-admitted document is not a warning: importing it would
            make Seldon's graph assert something the governed graph refuses to.
    """
    project_dir = Path(project_dir)
    view = read_ledger(ledger_path(project_dir, config))
    report = SyncReport(dry_run=dry_run)

    report.violations = admission_violations(view)
    if report.violations:
        raise ValueError(
            "AD-030-R5: content edges on documents that are not `admitted`:\n  "
            + "\n  ".join(report.violations[:10])
            + (f"\n  ... and {len(report.violations) - 10} more" if len(report.violations) > 10 else "")
        )

    documents = view.documents()
    if only:
        wanted = str(only)
        documents = [d for d in documents if d.get("path") == wanted or d["id"] == wanted]
        if not documents:
            raise ValueError(f"no governed document matches {only!r} in the ledger")
    report.documents_seen = len(documents)

    have_docs = existing_documents(driver, database)
    have_children = existing_children(driver, database)
    legacy = legacy_nodes_by_path(driver, database)
    # Names are assigned over EVERY document in the ledger, not over the subset being synced, so a
    # `--only` run cannot hand out a name a full run would have given to someone else.
    names = assign_names(
        d.get("path") or d["id"] for d in view.documents()
    )

    # Children, indexed by the document that owns them.
    children_by_doc: dict[str, list[tuple[str, dict]]] = {}
    for (cls, node_id), payload in sorted(view.nodes.items()):
        if cls == "Document":
            continue
        children_by_doc.setdefault(payload.get("doc_id") or "", []).append((cls, payload))

    wanted_docs = {d["id"] for d in documents}
    id_to_artifact: dict[str, str] = {}
    type_of: dict[str, str] = {}
    changed_documents: list[str] = []
    rederived: list[str] = []

    def write_node(cls: str, props: dict, existing: Optional[dict], state: Optional[str]) -> str:
        """Create or update one artifact; return its artifact_id."""
        artifact_type = NODE_TYPES[cls]
        if existing:
            if not dry_run:
                update_artifact(
                    project_dir=project_dir, driver=driver, database=database,
                    artifact_id=existing["artifact_id"], properties=props,
                    actor=ACTOR, authority="accepted", session_id=session_id,
                )
            report.bump(report.nodes_updated, artifact_type)
            return existing["artifact_id"]
        if dry_run:
            report.bump(report.nodes_created, artifact_type)
            return f"dry-run:{props['governed_id']}"
        artifact_id = create_artifact(
            project_dir=project_dir, driver=driver, database=database,
            domain_config=domain_config, artifact_type=artifact_type, properties=props,
            actor=ACTOR, authority="accepted", session_id=session_id,
        )
        report.bump(report.nodes_created, artifact_type)
        if state:
            current = domain_config.get_initial_state(artifact_type)
            if state != current:
                transition_state(
                    project_dir=project_dir, driver=driver, database=database,
                    domain_config=domain_config, artifact_id=artifact_id,
                    artifact_type=artifact_type, current_state=current, new_state=state,
                    actor=ACTOR, authority="accepted", session_id=session_id,
                )
        return artifact_id

    # ---- documents and their children ------------------------------------
    for payload in documents:
        governed_id = payload["id"]
        rel_path = payload.get("path") or governed_id
        existing = have_docs.get(governed_id)
        name = names.get(rel_path) or document_name(rel_path)
        # The hash covers the FILE. `name` is derived, so a change in how it is derived moves it
        # without moving the hash, and a document skipped as "unchanged" would keep a name the
        # current rule would never give it.
        unchanged = (
            existing is not None
            and existing["content_hash"] == payload.get("content_hash")
            and existing.get("name") == name
        )

        if unchanged:
            report.documents_unchanged += 1
            id_to_artifact[governed_id] = existing["artifact_id"]
            type_of[governed_id] = "Document"
            for cls, child in children_by_doc.get(governed_id, []):
                known = have_children.get(child["id"])
                if known:
                    id_to_artifact[child["id"]] = known["artifact_id"]
                    type_of[child["id"]] = known["artifact_type"]
            continue

        props = _document_properties(payload, rel_path, name)
        match = legacy.get(rel_path)
        if match:
            props["seldon_artifact_id"] = match["artifact_id"]
            report.linked_legacy += 1
        artifact_id = write_node(
            "Document", props, existing, payload.get("manifest_state") or "admitted"
        )
        id_to_artifact[governed_id] = artifact_id
        type_of[governed_id] = "Document"

        if existing:
            report.documents_updated += 1
            # SUSPECT FOLLOWS THE CONTENT HASH, NOT THE UPDATE. A document can be re-written here
            # because the way its `name` is derived changed, with its bytes untouched; flagging its
            # edges then would ask for a review of links nothing has disturbed, and a suspect flag
            # that fires on non-events is one people learn to clear without reading.
            if existing["content_hash"] != payload.get("content_hash"):
                changed_documents.append(artifact_id)
        else:
            report.documents_created += 1

        for cls, child in children_by_doc.get(governed_id, []):
            child_props = _child_properties(cls, child, rel_path)
            known = have_children.get(child["id"])
            child_id = write_node(cls, child_props, known, None)
            id_to_artifact[child["id"]] = child_id
            type_of[child["id"]] = NODE_TYPES[cls]
            if known:
                rederived.append(child_id)

    # A changed document's edges are flagged before the new ones are written, so a reader looking
    # at the graph mid-run sees "under review" rather than a half-rewritten structure.
    if changed_documents and not dry_run:
        report.edges_suspect = mark_edges_suspect(
            driver, database, changed_documents,
            "the governed document's content hash changed; this edge was re-derived (AD-030)",
        )

    # ---- edges -----------------------------------------------------------
    by_name, by_prefix = resolvable_targets(driver, database)

    for (etype, subject, obj), payload in sorted(view.edges.items()):
        rel_type = EDGE_TYPES.get(etype)
        if rel_type is None:
            continue
        from_id = id_to_artifact.get(subject)
        if from_id is None:
            continue
        to_id = id_to_artifact.get(obj)
        to_type = type_of.get(obj)
        if to_id is None:
            # A cross-document reference: the governed graph resolved what it could inside itself
            # and left the rest as an identifier. Resolve it here, where Seldon's own artifacts
            # are visible (AD-030-R10).
            resolved = _resolve_identifier(obj, by_name, by_prefix)
            if resolved is None:
                report.abstained[obj] = report.abstained.get(obj, 0) + 1
                continue
            to_id = resolved
            to_type = artifact_type_of(driver, database, to_id)
        from_type = type_of.get(subject)
        if not from_type or not to_type:
            report.abstained[obj] = report.abstained.get(obj, 0) + 1
            continue

        props = {k: payload[k] for k in EDGE_PROPERTIES.get(rel_type, ()) if payload.get(k) is not None}
        if dry_run:
            report.bump(report.edges_created, rel_type)
            continue
        if _link_exists(driver, database, from_id, to_id, rel_type):
            continue
        try:
            _create_link(
                project_dir=project_dir, driver=driver, database=database,
                domain_config=domain_config, from_id=from_id, to_id=to_id,
                from_type=from_type, to_type=to_type, rel_type=rel_type,
                session_id=session_id, rel_properties=props,
            )
        except ValueError:
            # An endpoint pair the domain does not declare. Counted as an abstention rather than
            # forced through: `research.yaml` is the statement of what may be linked, and an
            # import that overrode it would make that statement untrue.
            report.abstained[obj] = report.abstained.get(obj, 0) + 1
            continue
        report.bump(report.edges_created, rel_type)

    # ---- identifier mentions Seldon can resolve and Squiddy could not ----
    for governed_id, artifact_id in sorted(id_to_artifact.items()):
        payload = view.nodes.get(("Document", governed_id))
        if payload is None:
            continue
        for identifier in payload.get("identifiers") or []:
            target = _resolve_identifier(identifier, by_name, by_prefix)
            if target is None or target == artifact_id:
                report.abstained[identifier] = report.abstained.get(identifier, 0) + 1
                continue
            if dry_run:
                report.bump(report.edges_created, "mentions")
                continue
            if _link_exists(driver, database, artifact_id, target, "mentions"):
                continue
            to_type = artifact_type_of(driver, database, target)
            try:
                _create_link(
                    project_dir=project_dir, driver=driver, database=database,
                    domain_config=domain_config, from_id=artifact_id, to_id=target,
                    from_type="Document", to_type=to_type, rel_type="mentions",
                    session_id=session_id,
                    rel_properties={"identifier": identifier,
                                    "identifier_kind": _identifier_kind(identifier)},
                )
            except ValueError:
                report.abstained[identifier] = report.abstained.get(identifier, 0) + 1
                continue
            report.bump(report.edges_created, "mentions")

    if rederived and not dry_run:
        report.edges_cleared = clear_suspect(driver, database, rederived)

    # A child the ledger no longer holds — a section deleted from a document, a paragraph that a
    # pattern change no longer classifies as a Ruling — is RETIRED, never deleted. It was true of
    # the document once, edges point at it, and a graph that silently drops what it used to assert
    # cannot be audited. Only a full sync may do this: a `--only` run has seen one document and
    # knows nothing about what the rest of the corpus still holds.
    if only is None and not dry_run:
        report.nodes_retired = retire_absent_children(
            project_dir=project_dir, driver=driver, database=database,
            domain_config=domain_config, view=view, session_id=session_id,
        )

    return report


def retire_absent_children(
    *,
    project_dir: Path,
    driver,
    database: str,
    domain_config,
    view: LedgerView,
    session_id: Optional[str] = None,
) -> dict[str, int]:
    """Move every governed child artifact the ledger no longer holds to `retired`.

    Args:
        project_dir: Project root.
        driver: Neo4j driver.
        database: Database name.
        domain_config: Loaded domain configuration.
        view: The replayed ledger, which is the complete set of what should exist.
        session_id: Session id stamped on the events.

    Returns:
        Count retired, by artifact type.
    """
    live = {node_id for (cls, node_id) in view.nodes if cls != "Document"}
    have = existing_children(driver, database)
    retired: dict[str, int] = {}
    for governed_id, record in sorted(have.items()):
        if governed_id in live or record["state"] == "retired":
            continue
        artifact_type = record["artifact_type"]
        try:
            transition_state(
                project_dir=project_dir, driver=driver, database=database,
                domain_config=domain_config, artifact_id=record["artifact_id"],
                artifact_type=artifact_type, current_state=record["state"],
                new_state="retired", actor=ACTOR, authority="accepted",
                session_id=session_id,
            )
        except ValueError:
            # A type whose state machine has no `retired` (Citation: proposed/verified/stale).
            # Left alone and counted, rather than forced through a transition the domain refuses.
            retired[f"{artifact_type} (no retired state)"] = (
                retired.get(f"{artifact_type} (no retired state)", 0) + 1
            )
            continue
        retired[artifact_type] = retired.get(artifact_type, 0) + 1
    return retired


def _identifier_kind(identifier: str) -> str:
    """Classify an identifier reference for the edge property.

    Args:
        identifier: The reference as the text writes it.

    Returns:
        `AD`, `DN`, `TASK` or `OTHER`.
    """
    if identifier.startswith("AD-"):
        return "AD"
    if identifier.startswith("DN-"):
        return "DN"
    if _TASK_PREFIX_RE.match(identifier):
        return "TASK"
    return "OTHER"


def _resolve_identifier(
    identifier: str, by_name: dict[str, str], by_prefix: dict[str, str]
) -> Optional[str]:
    """The Seldon artifact an identifier reference names, when exactly one does.

    Args:
        identifier: The reference as the text writes it.
        by_name: Artifact name to id.
        by_prefix: Eight-hex id prefix to full id, for ResearchTasks.

    Returns:
        The artifact id, or None when nothing or more than one thing answers to it.
    """
    if identifier in by_name:
        return by_name[identifier]
    if _TASK_PREFIX_RE.match(identifier):
        return by_prefix.get(identifier)
    return None


def _link_exists(driver, database: str, from_id: str, to_id: str, rel_type: str) -> bool:
    """Whether this relationship is already stored."""
    canonical = graph.canonical_rel_type(rel_type)
    with driver.session(database=database) as session:
        return graph.relationship_exists(session, from_id, to_id, canonical)


def _create_link(**kwargs) -> None:
    """Thin indirection over `seldon.core.artifacts.create_link`, for test seams."""
    from seldon.core.artifacts import create_link

    create_link(actor=ACTOR, authority="accepted", **kwargs)


# ---------------------------------------------------------------------------
# Full-text index and search (AD-030 section 4)
# ---------------------------------------------------------------------------

#: Name of the Neo4j full-text index over governed document text.
FULLTEXT_INDEX = "governed_text"

#: Labels and properties the index covers. Section and Passage are what AD-030 section 4 names;
#: Ruling is included because a ruling is the unit a task is constrained by, and an index that
#: could not find one would leave `cc register`'s concept match with nothing to search.
FULLTEXT_LABELS = ("Section", "Ruling", "Passage", "Citation")
FULLTEXT_PROPERTIES = ("text", "raw")


def ensure_fulltext_index(driver, database: str) -> bool:
    """Create the governed full-text index if it is absent.

    Args:
        driver: Neo4j driver.
        database: Database name.

    Returns:
        True when the index exists after the call.

    Raises:
        RuntimeError: If the server rejects the index creation for any reason other than the
            index already existing. A silently absent index would make every search return
            nothing and look like an empty corpus.
    """
    labels = "|".join(FULLTEXT_LABELS)
    properties = ", ".join(f"n.{p}" for p in FULLTEXT_PROPERTIES)
    statement = (
        f"CREATE FULLTEXT INDEX {FULLTEXT_INDEX} IF NOT EXISTS "
        f"FOR (n:{labels}) ON EACH [{properties}]"
    )
    try:
        with driver.session(database=database) as session:
            session.run(statement)
    except Exception as exc:  # neo4j.exceptions.ClientError and friends
        raise RuntimeError(
            f"could not create the governed full-text index: {exc}. "
            f"Full-text indexes need Neo4j 5.x; without one `seldon governed search` cannot run."
        ) from exc
    return True


def search(
    driver, database: str, query: str, artifact_type: Optional[str] = None, limit: int = 20
) -> list[dict]:
    """Full-text search over governed document text.

    Args:
        driver: Neo4j driver.
        database: Database name.
        query: Lucene query string, as the caller typed it.
        artifact_type: Restrict to one governed type, or None for all.
        limit: Maximum hits.

    Returns:
        Hits ordered by score, each with `artifact_type`, `name`, `source_document`, `text`,
        `span_start`, `span_end` and `score`.

    Raises:
        RuntimeError: If the index cannot be created or the query cannot run.
    """
    ensure_fulltext_index(driver, database)
    cypher = (
        f"CALL db.index.fulltext.queryNodes('{FULLTEXT_INDEX}', $q) YIELD node, score "
        "WHERE $type IS NULL OR node.artifact_type = $type "
        "RETURN node.artifact_type AS artifact_type, node.name AS name, "
        "node.source_document AS source_document, coalesce(node.text, node.raw) AS text, "
        "node.span_start AS span_start, node.span_end AS span_end, score "
        "ORDER BY score DESC LIMIT $limit"
    )
    try:
        with driver.session(database=database) as session:
            return session.run(cypher, q=query, type=artifact_type, limit=int(limit)).data()
    except Exception as exc:
        raise RuntimeError(f"governed search failed for {query!r}: {exc}") from exc


def graph_counts(driver, database: str) -> dict:
    """Count what the import has put into the graph.

    Args:
        driver: Neo4j driver.
        database: Database name.

    Returns:
        `{"nodes": {type: n}, "edges": {type: n}, "suspect_edges": n}`, covering only the governed
        types and the edges among them.
    """
    types = list(NODE_TYPES.values())
    with driver.session(database=database) as session:
        nodes = session.run(
            "MATCH (n:Artifact) WHERE n.artifact_type IN $types AND n.governed_id IS NOT NULL "
            "RETURN n.artifact_type AS type, count(n) AS n",
            types=types,
        ).data()
        edges = session.run(
            "MATCH (a:Artifact)-[r]->(b:Artifact) "
            "WHERE a.governed_id IS NOT NULL OR b.governed_id IS NOT NULL "
            "RETURN type(r) AS type, count(r) AS n"
        ).data()
        suspect = session.run(
            "MATCH (:Artifact)-[r]->(:Artifact) WHERE r.suspect RETURN count(r) AS n"
        ).single()
    return {
        "nodes": {r["type"]: r["n"] for r in nodes},
        "edges": {r["type"]: r["n"] for r in edges},
        "suspect_edges": suspect["n"] if suspect else 0,
    }


# ---------------------------------------------------------------------------
# Matching a task to the rulings that constrain it (AD-030, `cc register`)
# ---------------------------------------------------------------------------

#: Default overlap a task's text and a ruling's text must share before the match is worth showing.
#: Config key `governed.ruling_match_threshold` in seldon.yaml. The value is a floor on noise, not
#: a claim about meaning: a lower one buries the identifier matches under coincidence, a higher one
#: finds only rulings the task already names, which the identifier pass has found already.
DEFAULT_RULING_MATCH_THRESHOLD = 0.18

#: Minimum length of a term considered for overlap. Three, not four: the terms that most sharply
#: distinguish one ruling from another in this corpus are three-letter domain acronyms — RPE, DOI,
#: API, RTM — and a four-character floor drops exactly those while keeping "that" and "with",
#: which distinguish nothing. Two-letter tokens really are grammar.
MIN_TERM_LENGTH = 3

#: Terms that appear in nearly every governed document and so distinguish nothing. Kept small and
#: explicit: a long stop list is a tuning knob pretending to be a fact.
STOP_TERMS = frozenset({
    "that", "this", "with", "from", "have", "has", "the", "and", "for", "not", "but", "are",
    "was", "were", "will", "would", "must", "never", "always", "into", "than", "then", "when",
    "which", "what", "each", "every", "only", "also", "because", "there", "their", "them",
    "they", "here", "been", "being", "does", "done", "make", "made", "more", "most", "such",
    "task", "tasks", "seldon", "file", "files", "graph", "node", "nodes", "edge", "edges",
    "run", "runs", "code", "test", "tests", "name", "names", "should", "shall", "may",
    # Three-letter tokens the lowered floor now admits and which carry no subject matter.
    "the", "and", "for", "not", "but", "are", "was", "its", "one", "two", "can", "all",
    "any", "how", "why", "who", "new", "old", "use", "via", "per", "out", "off", "yet",
    "add", "set", "get", "see", "own", "way", "let", "now", "you", "our", "its",
})

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{%d,}" % (MIN_TERM_LENGTH - 1))


def ruling_match_threshold(config: dict) -> float:
    """Read the concept-overlap threshold from the project config.

    Args:
        config: Parsed seldon.yaml.

    Returns:
        The configured threshold, or the module default when the key is absent.

    Raises:
        ValueError: If the configured value is not a number in `[0, 1]`. A threshold outside that
            range silently returns everything or nothing.
    """
    block = config.get("governed") or {}
    value = block.get("ruling_match_threshold", DEFAULT_RULING_MATCH_THRESHOLD)
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"governed.ruling_match_threshold must be a number, got {value!r}")
    if not 0.0 <= value <= 1.0:
        raise ValueError(
            f"governed.ruling_match_threshold must be between 0 and 1, got {value!r}"
        )
    return value


def concept_terms(text: str) -> set[str]:
    """The content terms of a piece of text, lowercased.

    Args:
        text: Any text.

    Returns:
        Terms long enough and common enough to carry subject matter.
    """
    return {
        word.lower() for word in _WORD_RE.findall(text or "")
        if word.lower() not in STOP_TERMS
    }


def overlap_score(task_terms: set[str], ruling_terms: set[str]) -> tuple[float, list[str]]:
    """Szymkiewicz-Simpson overlap between two term sets, and the terms they share.

    The overlap coefficient — shared terms over the size of the SMALLER set — rather than Jaccard,
    because a ruling is one or two sentences and a task file is pages: Jaccard would divide by the
    task's length and score every real match near zero.

    Args:
        task_terms: Terms from the task text.
        ruling_terms: Terms from the ruling text.

    Returns:
        `(score, shared_terms_sorted)`. Score is 0.0 when either side is empty.
    """
    if not task_terms or not ruling_terms:
        return 0.0, []
    shared = task_terms & ruling_terms
    return len(shared) / min(len(task_terms), len(ruling_terms)), sorted(shared)


@dataclass
class RulingMatch:
    """One ruling a task is constrained by.

    Attributes:
        artifact_id: The Ruling's artifact id.
        name: Its stable ruling id.
        ruling_identifier: The document's own label, when it writes one.
        force: binding, obligation, prohibition or recommendation.
        text: The verbatim ruling text.
        source_document: Path of the document it came from.
        match_method: `identifier` or `concept_overlap`.
        match_score: Overlap score; None for an identifier match, which is exact.
        matched_terms: Terms the task and the ruling share; empty for an identifier match.
    """

    artifact_id: str
    name: str
    ruling_identifier: Optional[str]
    force: Optional[str]
    text: str
    source_document: Optional[str]
    match_method: str
    match_score: Optional[float] = None
    matched_terms: list[str] = field(default_factory=list)

    def render(self) -> str:
        """One-line-plus-quote rendering for a tool response."""
        label = self.ruling_identifier or self.name
        how = (f"concept overlap {self.match_score:.2f}: "
               f"{', '.join(self.matched_terms[:6])}" if self.match_method == "concept_overlap"
               else "names it")
        text = " ".join((self.text or "").split())
        return (f"  {label}  [{self.force or '?'}]  {self.source_document or '?'}  ({how})\n"
                f"    {text[:280]}{'...' if len(text) > 280 else ''}")


#: States in which a Ruling no longer binds anything. A retired ruling's text left the document;
#: a superseded one was replaced. Either way a new task cannot be constrained by it, and returning
#: one from a match would be the graph asserting an obligation nothing imposes any more.
NON_BINDING_RULING_STATES = frozenset({"retired", "superseded"})


def read_rulings(driver, database: str, include_non_binding: bool = False) -> list[dict]:
    """Every Ruling artifact that still binds.

    A pattern change retired 161 rulings in one sync. They keep their nodes and their edges — the
    graph records what it used to assert rather than deleting it — but they must not reach a match,
    or `cc register` would constrain a new task by a ruling that no longer exists in any document.

    Args:
        driver: Neo4j driver.
        database: Database name.
        include_non_binding: Return retired and superseded rulings too. For auditing what was
            dropped, never for matching.

    Returns:
        One dict per ruling, with the properties a match needs.
    """
    cypher = (
        "MATCH (r:Artifact:Ruling) "
        + ("" if include_non_binding else "WHERE NOT r.state IN $excluded ")
        + "RETURN r.artifact_id AS artifact_id, r.name AS name, "
        "r.ruling_identifier AS ruling_identifier, r.force AS force, r.text AS text, "
        "r.source_document AS source_document, r.identifiers AS identifiers, "
        "r.state AS state"
    )
    with driver.session(database=database) as session:
        return session.run(cypher, excluded=sorted(NON_BINDING_RULING_STATES)).data()


def match_rulings(
    task_text: str, rulings: Iterable[dict], threshold: float, limit: int = 8
) -> list[RulingMatch]:
    """Find the rulings a task's text is constrained by.

    Two passes, and the order matters. An identifier match is exact — the task names `AD-030-R9`,
    so it is about `AD-030-R9` — and every such ruling is returned whatever its overlap. The
    concept pass is a weaker, lexical guess that fills the gap the identifier pass cannot: the
    defect AD-030 exists for is a task that reintroduced a retired field WITHOUT naming the ruling
    that retired it, so a mechanism that only found named rulings would not have caught it.

    Args:
        task_text: The task file's text.
        rulings: Ruling records, as :func:`read_rulings` returns them.
        threshold: Minimum overlap for the concept pass.
        limit: Maximum concept matches returned; identifier matches are never truncated.

    Returns:
        Identifier matches first, then concept matches by descending score.
    """
    rulings = list(rulings)
    task_terms = concept_terms(task_text)
    named = set(re.findall(r"\b[A-Z]{2,4}-\d+-R\d+\b", task_text or ""))
    named_docs = set(re.findall(r"\b(?:AD|DN)-\d+\b", task_text or ""))

    identifier_matches: list[RulingMatch] = []
    concept_matches: list[RulingMatch] = []
    claimed: set[str] = set()

    for ruling in rulings:
        identifier = ruling.get("ruling_identifier")
        if identifier and identifier in named:
            claimed.add(ruling["artifact_id"])
            identifier_matches.append(RulingMatch(
                artifact_id=ruling["artifact_id"], name=ruling["name"],
                ruling_identifier=identifier, force=ruling.get("force"),
                text=ruling.get("text") or "", source_document=ruling.get("source_document"),
                match_method="identifier",
            ))

    for ruling in rulings:
        if ruling["artifact_id"] in claimed:
            continue
        score, shared = overlap_score(task_terms, concept_terms(ruling.get("text") or ""))
        if score < threshold:
            continue
        # A ruling from a document the task explicitly names is stronger evidence than one from a
        # document it has never heard of, so it sorts first among concept matches.
        source = ruling.get("source_document") or ""
        names_doc = any(doc in source or doc in (ruling.get("ruling_identifier") or "")
                        for doc in named_docs)
        concept_matches.append(RulingMatch(
            artifact_id=ruling["artifact_id"], name=ruling["name"],
            ruling_identifier=ruling.get("ruling_identifier"), force=ruling.get("force"),
            text=ruling.get("text") or "", source_document=source or None,
            match_method="concept_overlap", match_score=round(score, 3),
            matched_terms=shared,
        ))
        concept_matches[-1].matched_terms = shared
        if names_doc:
            concept_matches[-1].match_score = round(min(1.0, score + 0.001), 3)

    identifier_matches.sort(key=lambda m: m.ruling_identifier or m.name)
    concept_matches.sort(key=lambda m: (-(m.match_score or 0.0), m.name))
    return identifier_matches + concept_matches[:limit]


def write_constrained_by(
    *,
    project_dir: Path,
    driver,
    database: str,
    domain_config,
    task_id: str,
    task_type: str,
    matches: Iterable[RulingMatch],
    session_id: Optional[str] = None,
) -> int:
    """Write a `constrained_by` edge from a task to each matched ruling.

    Args:
        project_dir: Project root.
        driver: Neo4j driver.
        database: Database name.
        domain_config: Loaded domain configuration.
        task_id: The task's artifact id.
        task_type: The task's artifact type.
        matches: The rulings it is constrained by.
        session_id: Session id stamped on the events.

    Returns:
        How many edges were written. An edge that already exists is not rewritten.
    """
    written = 0
    for match in matches:
        if _link_exists(driver, database, task_id, match.artifact_id, "constrained_by"):
            continue
        props: dict[str, Any] = {"match_method": match.match_method}
        if match.match_score is not None:
            props["match_score"] = match.match_score
        if match.matched_terms:
            props["matched_terms"] = match.matched_terms[:12]
        _create_link(
            project_dir=project_dir, driver=driver, database=database,
            domain_config=domain_config, from_id=task_id, to_id=match.artifact_id,
            from_type=task_type, to_type="Ruling", rel_type="constrained_by",
            session_id=session_id, rel_properties=props,
        )
        written += 1
    return written


#: Refusal text for AD-030-R9's task-registration half.
R9_TASK_MESSAGE = (
    "This CC task references no AD- or DN- identifier (AD-030-R9). Every CC task produced by a "
    "design session cites the decision it implements; a task that cites none is a decision being "
    "made in the task file, where nothing can find it later."
)

#: Identifier forms that satisfy the AD-030-R9 reference check.
_DESIGN_REFERENCE_RE = re.compile(r"\b(?:AD|DN)-\d+\b")


def references_a_design_note(text: str) -> bool:
    """Whether a CC task file names a design decision (AD-030-R9).

    Args:
        text: The task file's text.

    Returns:
        True when it names at least one `AD-` or `DN-` identifier.
    """
    return bool(_DESIGN_REFERENCE_RE.search(text or ""))


# ---------------------------------------------------------------------------
# Files the ledger has never heard of
# ---------------------------------------------------------------------------

#: Filenames under a governed directory that are not governed documents.
SKIP_FILENAMES = frozenset({"README.md"})


def governed_directories(project_dir: Path, config: dict) -> list[str]:
    """The governed directories this project declares (AD-030-R1).

    Read from the governed graph's own `config.yaml`, not restated here: the enumerator, the
    emitter and this check must agree on which directories are governed, and three copies of that
    list would be three chances to disagree.

    Args:
        project_dir: Project root.
        config: Parsed seldon.yaml.

    Returns:
        Repo-relative directory paths. Empty when the governed graph is absent or declares none.
    """
    import yaml

    path = graph_dir(project_dir, config) / "config.yaml"
    if not path.is_file():
        return []
    domain = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("domain") or {}
    return [entry["path"] for entry in (domain.get("governed_directories") or [])]


def uncataloged(project_dir: Path, config: dict) -> list[str]:
    """Governed markdown files the ledger has never heard of.

    AD-030-R1 says every governed document is graph content. A file that was written and never
    cataloged satisfies nothing: the hash check compares the ledger to the graph and cannot see a
    document that is in neither. This is the check that makes "every governed file" mean it.

    Args:
        project_dir: Project root.
        config: Parsed seldon.yaml.

    Returns:
        Sorted repo-relative paths with no Document in the ledger.
    """
    directories = governed_directories(project_dir, config)
    if not directories:
        return []
    known = {
        payload.get("path")
        for payload in read_ledger(ledger_path(project_dir, config)).documents()
    }
    root = Path(project_dir)
    missing = []
    for directory in directories:
        base = root / directory
        if not base.is_dir():
            continue
        for path in base.rglob("*.md"):
            if path.name.startswith(".") or path.name in SKIP_FILENAMES:
                continue
            rel = path.relative_to(root).as_posix()
            if rel not in known:
                missing.append(rel)
    return sorted(missing)
