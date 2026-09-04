"""Recoverability check: replay the event log and compare against the live graph.

Recoverability is a declared guaranteed property of Seldon: the Neo4j graph is a
*projection* of the JSONL event log, and the log is the source of truth. That
claim is only true if it is measured. This module measures it — it replays a
project's whole event log into a throwaway database and diffs the result against
the live graph.

What a mismatch means
---------------------
A mismatch is **not** automatically a bug in replay. It is usually the opposite:
something wrote to the live graph *without* writing an event, so the live graph
holds state the log cannot reproduce. That state is unrecoverable — a rebuild
would silently lose it. The right response is to diagnose where the un-evented
write came from, not to paper over the difference by editing either side.

Scratch database safety
-----------------------
Prior art: ``tests/testdb.py``, which solves the same problem for the test
suite. Its argument is adopted here, with one deliberate strengthening.

* **Name.** ``seldon-replaycheck-p<pid>-<8 hex>``. The literal
  ``seldon-replaycheck-`` prefix is disjoint from ``seldon-test-`` (the suite's
  per-process databases) and from every real project database, which is
  ``seldon-<project slug>`` where the slug comes from `seldon.config.slugify`.
* **Creation is exclusive.** ``CREATE DATABASE`` is issued *without*
  ``IF NOT EXISTS``. If the name is somehow already taken the create fails and
  nothing is touched. This is the strengthening over ``testdb.py``, which uses
  ``IF NOT EXISTS`` because it wants to reclaim its own database across runs.
  Here it means: **this process only ever drops a database it exclusively
  created**, so no naming argument has to carry the whole safety burden alone.
* **Dropping is guarded.** `drop_scratch_database` refuses any name that does
  not match :data:`SCRATCH_RE`, so a caller mistake cannot destroy a project.
* **Orphans are reclaimed conservatively.** A crashed run leaves its database
  behind. `sweep_stale_scratch_databases` drops one only when the embedded PID
  names no live process — the same fail-safe as ``testdb.stale_pid``: a recycled
  PID that is now live leaves a harmless orphan rather than dropping a database
  out from under a running check.
"""
from __future__ import annotations

import logging
import os
import re
import secrets
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

#: Literal prefix owned by this module. Disjoint from `seldon-test-` and from
#: every real project database name.
SCRATCH_PREFIX = "seldon-replaycheck-"

#: Anchored pattern for names this module may create and drop. Nothing else is
#: ever a drop candidate.
SCRATCH_RE = re.compile(r"^" + re.escape(SCRATCH_PREFIX) + r"p(\d+)-[0-9a-f]{8}$")

#: Node labels excluded from the comparison. These are Seldon's own bookkeeping
#: nodes, not projected artifacts: `_SeldonMeta` holds the sync point (which is
#: written *by* replay and therefore always differs in wall-clock terms) and
#: `_OntologyReplicaMeta` holds the replica epoch. Comparing them would report a
#: guaranteed difference on every run and drown the real findings.
INTERNAL_LABELS = frozenset({"_SeldonMeta", "_OntologyReplicaMeta"})

#: Artifact types a project inherits rather than authors, so its own event log
#: is not their source of truth and replay is not the right recoverability test
#: for them. OntologyTerm is replicated from the `seldon-ontology` master by
#: `seldon ontology sync` (AD-017) and cannot be created locally at all.
INHERITED_ARTIFACT_TYPES = frozenset({"OntologyTerm"})


def scratch_database_name(pid: Optional[int] = None) -> str:
    """Generate a unique scratch database name for this process.

    Args:
        pid: Process id to embed. Defaults to ``os.getpid()``.

    Returns:
        A name matching :data:`SCRATCH_RE`. The random suffix lets one process
        run several checks (e.g. the all-projects sweep) without reusing a name.
    """
    pid = os.getpid() if pid is None else pid
    return f"{SCRATCH_PREFIX}p{pid}-{secrets.token_hex(4)}"


def is_scratch_database(name: str) -> bool:
    """Return True if ``name`` is a database this module owns.

    Args:
        name: Database name as reported by ``SHOW DATABASES``.

    Returns:
        True only for the anchored generated pattern.
    """
    return bool(SCRATCH_RE.match(name))


def _pid_alive(pid: int) -> bool:
    """Return True if a process with ``pid`` currently exists.

    Duplicated from ``tests/testdb._pid_alive`` rather than shared: ``tests/``
    is not a shipped package, so the installed ``seldon`` package cannot import
    from it. The behaviour, including the errno handling, is deliberately
    identical.

    Args:
        pid: Process id to probe.

    Returns:
        True if the process exists (including when owned by another user, which
        surfaces as PermissionError). False only when the OS reports no such
        process.

    Raises:
        OSError: For any errno other than ESRCH/EPERM. An unexpected failure
            must not be read as "dead", because that would authorise a drop.
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def stale_scratch_databases(names, self_pid: Optional[int] = None) -> List[str]:
    """Filter ``names`` down to abandoned scratch databases.

    Args:
        names: Database names, e.g. from ``SHOW DATABASES YIELD name``.
        self_pid: This process's PID. Defaults to ``os.getpid()``.

    Returns:
        The subset safe to drop, in input order: matching :data:`SCRATCH_RE`,
        not owned by this process, and naming a PID that is no longer alive.
    """
    self_pid = os.getpid() if self_pid is None else self_pid
    out: List[str] = []
    for name in names:
        match = SCRATCH_RE.match(name)
        if not match:
            continue
        pid = int(match.group(1))
        if pid <= 0 or pid == self_pid:
            continue
        if _pid_alive(pid):
            continue
        out.append(name)
    return out


def existing_databases(driver) -> List[str]:
    """List database names known to the server.

    Args:
        driver: A connected ``neo4j.Driver``.

    Returns:
        Database names as reported by ``SHOW DATABASES``.

    Raises:
        neo4j.exceptions.Neo4jError: If the query fails.
    """
    with driver.session(database="system") as session:
        return [record["name"] for record in session.run("SHOW DATABASES YIELD name")]


def create_scratch_database(driver, name: str) -> None:
    """Create the scratch database ``name``, exclusively.

    Args:
        driver: A connected ``neo4j.Driver``.
        name: Name to create. Must match :data:`SCRATCH_RE`.

    Returns:
        None.

    Raises:
        ValueError: If ``name`` is not a scratch database name.
        neo4j.exceptions.Neo4jError: If the database already exists or the
            create otherwise fails. Existing-name failure is intentional: it is
            what makes "we only drop what we created" true.
    """
    if not is_scratch_database(name):
        raise ValueError(
            f"refusing to create {name!r}: not a scratch database name "
            f"(pattern {SCRATCH_RE.pattern})"
        )
    with driver.session(database="system") as session:
        # WAIT: CREATE/DROP DATABASE are asynchronous by default, and a create
        # that has not completed produces confusing DatabaseNotFound errors.
        session.run(f"CREATE DATABASE `{name}` WAIT")


def drop_scratch_database(driver, name: str) -> None:
    """Drop the scratch database ``name``.

    Args:
        driver: A connected ``neo4j.Driver``.
        name: Name to drop. Must match :data:`SCRATCH_RE`.

    Returns:
        None.

    Raises:
        ValueError: If ``name`` is not a scratch database name.
        neo4j.exceptions.Neo4jError: If the drop fails and the database is still
            present.
    """
    if not is_scratch_database(name):
        raise ValueError(
            f"refusing to drop {name!r}: not a scratch database name "
            f"(pattern {SCRATCH_RE.pattern})"
        )
    from neo4j.exceptions import Neo4jError

    with driver.session(database="system") as session:
        try:
            session.run(f"DROP DATABASE `{name}` IF EXISTS WAIT")
        except Neo4jError:
            # A concurrent sweeper may have taken the same orphan. Benign — but
            # only if it really is gone. Anything else is a real failure.
            if name in existing_databases(driver):
                raise


def sweep_stale_scratch_databases(driver) -> List[str]:
    """Drop scratch databases whose owning process is gone.

    Args:
        driver: A connected ``neo4j.Driver``.

    Returns:
        The names actually dropped, so a caller can report them.

    Raises:
        neo4j.exceptions.Neo4jError: If listing or dropping fails.
    """
    stale = stale_scratch_databases(existing_databases(driver))
    for name in stale:
        drop_scratch_database(driver, name)
    return stale


# ---------------------------------------------------------------------------
# Graph fingerprinting
# ---------------------------------------------------------------------------

@dataclass
class GraphFingerprint:
    """A comparable summary of a graph's projected content.

    Attributes:
        node_count: Nodes excluding :data:`INTERNAL_LABELS`.
        relationship_count: Relationships between counted nodes.
        labels: Label → node count.
        rel_types: Relationship type → count.
        states: artifact_id → state, for every node carrying an artifact_id.
        types: artifact_id → artifact_type.
        edges: (from artifact_id, rel type, to artifact_id) → count.
    """

    node_count: int = 0
    relationship_count: int = 0
    labels: Dict[str, int] = field(default_factory=dict)
    rel_types: Dict[str, int] = field(default_factory=dict)
    states: Dict[str, str] = field(default_factory=dict)
    types: Dict[str, str] = field(default_factory=dict)
    edges: Counter = field(default_factory=Counter)


def fingerprint_graph(driver, database: str) -> GraphFingerprint:
    """Summarise a database into a comparable fingerprint.

    Args:
        driver: A connected ``neo4j.Driver``.
        database: Database to read. Read-only — no write is issued.

    Returns:
        A :class:`GraphFingerprint`.

    Raises:
        neo4j.exceptions.Neo4jError: If any query fails.
    """
    fp = GraphFingerprint()
    internal = list(INTERNAL_LABELS)

    with driver.session(database=database) as session:
        rows = session.run(
            "MATCH (n) WHERE NONE(l IN labels(n) WHERE l IN $internal) "
            "RETURN n.artifact_id AS aid, n.state AS state, "
            "n.artifact_type AS atype, labels(n) AS labels",
            internal=internal,
        )
        for row in rows:
            fp.node_count += 1
            for label in row["labels"]:
                fp.labels[label] = fp.labels.get(label, 0) + 1
            aid = row["aid"]
            if aid is not None:
                fp.states[aid] = row["state"]
                fp.types[aid] = row["atype"]

        rows = session.run(
            "MATCH (a)-[r]->(b) "
            "WHERE NONE(l IN labels(a) WHERE l IN $internal) "
            "  AND NONE(l IN labels(b) WHERE l IN $internal) "
            "RETURN a.artifact_id AS from_id, type(r) AS rel, "
            "b.artifact_id AS to_id",
            internal=internal,
        )
        for row in rows:
            fp.relationship_count += 1
            rel = row["rel"]
            fp.rel_types[rel] = fp.rel_types.get(rel, 0) + 1
            fp.edges[(row["from_id"], rel, row["to_id"])] += 1

    return fp


@dataclass
class ReplayComparison:
    """The diff between a live graph and a replay of its event log.

    Attributes:
        database: The live database compared.
        events_replayed: Number of events the replay applied.
        live: Fingerprint of the live graph.
        replayed: Fingerprint of the replayed graph.
        missing_artifacts: artifact_ids present live but absent after replay —
            i.e. graph state the log cannot reproduce.
        extra_artifacts: artifact_ids produced by replay but absent live.
        state_mismatches: (artifact_id, live state, replayed state).
        missing_edges: (from, rel, to, count) present live, absent after replay.
        extra_edges: (from, rel, to, count) produced by replay, absent live.
        error: Populated when the check could not run at all.
    """

    database: str
    events_replayed: int = 0
    live: Optional[GraphFingerprint] = None
    replayed: Optional[GraphFingerprint] = None
    missing_artifacts: List[str] = field(default_factory=list)
    extra_artifacts: List[str] = field(default_factory=list)
    state_mismatches: List[Tuple[str, Any, Any]] = field(default_factory=list)
    missing_edges: List[Tuple[Any, str, Any, int]] = field(default_factory=list)
    extra_edges: List[Tuple[Any, str, Any, int]] = field(default_factory=list)
    inherited_skipped: int = 0
    error: Optional[str] = None

    @staticmethod
    def _artifact_counts(fp: "GraphFingerprint") -> Tuple[int, int]:
        """Return (artifact nodes, edges between artifact nodes) for `fp`.

        The event log is the source of truth for Seldon *artifacts*, not for
        every node that happens to share the database. A project may legitimately
        store non-Seldon content alongside — `seldon-ai-readiness-kg` holds a
        knowledge graph of ~23k nodes that was never event-sourced and never
        claimed to be. Reporting raw node totals there renders a two-artifact
        divergence as a 23,000-node failure, and a check that cries wolf at that
        volume stops being read, which is worse than no check at all.

        Args:
            fp: Fingerprint to measure.

        Returns:
            Tuple of (count of nodes carrying an artifact_id, count of edges
            whose endpoints both carry one).
        """
        nodes = sum(
            1 for aid in fp.states
            if fp.types.get(aid) not in INHERITED_ARTIFACT_TYPES
        )
        edges = sum(
            count for (from_id, _rel, to_id), count in fp.edges.items()
            if from_id is not None and to_id is not None
        )
        return nodes, edges

    @property
    def matches(self) -> bool:
        """True when the replay reproduced the live graph exactly.

        Scoped to artifacts and the edges between them — see `_artifact_counts`.
        """
        if self.error is not None:
            return False
        return not (
            self.missing_artifacts
            or self.extra_artifacts
            or self.state_mismatches
            or self.missing_edges
            or self.extra_edges
        )

    def summary_lines(self) -> List[str]:
        """Render the diff as human-readable lines.

        Returns:
            One line per finding class, empty when the replay matched.
        """
        if self.error is not None:
            return [f"replay check could not run: {self.error}"]
        lines: List[str] = []
        if self.live and self.replayed:
            live_nodes, live_edges = self._artifact_counts(self.live)
            replayed_nodes, replayed_edges = self._artifact_counts(self.replayed)
            if live_nodes != replayed_nodes:
                lines.append(
                    f"artifact count: live {live_nodes}, replayed {replayed_nodes}"
                )
            if live_edges != replayed_edges:
                lines.append(
                    f"artifact relationship count: live {live_edges}, "
                    f"replayed {replayed_edges}"
                )
            # Non-artifact nodes are outside the log's remit by design. Stated
            # once, as context, so a large number here is not read as a failure.
            foreign = self.live.node_count - live_nodes - self.inherited_skipped
            if foreign:
                lines.append(
                    f"note: {foreign} live node(s) carry no artifact_id — not "
                    f"event-sourced, not compared"
                )
            if self.inherited_skipped:
                lines.append(
                    f"note: {self.inherited_skipped} inherited artifact(s) "
                    f"({', '.join(sorted(INHERITED_ARTIFACT_TYPES))}) not compared "
                    f"— recovered by `seldon ontology sync`, not by replay"
                )
        if self.missing_artifacts:
            lines.append(
                f"{len(self.missing_artifacts)} artifact(s) in the live graph that "
                f"replay does not produce — unrecoverable graph state"
            )
        if self.extra_artifacts:
            lines.append(
                f"{len(self.extra_artifacts)} artifact(s) produced by replay but "
                f"absent from the live graph"
            )
        if self.state_mismatches:
            lines.append(
                f"{len(self.state_mismatches)} artifact(s) whose replayed state "
                f"differs from the live state"
            )
        if self.missing_edges:
            lines.append(
                f"{len(self.missing_edges)} relationship(s) in the live graph that "
                f"replay does not produce — written outside the event path"
            )
        if self.extra_edges:
            lines.append(
                f"{len(self.extra_edges)} relationship(s) produced by replay but "
                f"absent from the live graph"
            )
        return lines


def compare_fingerprints(
    database: str,
    live: GraphFingerprint,
    replayed: GraphFingerprint,
    events_replayed: int,
) -> ReplayComparison:
    """Diff two fingerprints into a :class:`ReplayComparison`.

    Args:
        database: Name of the live database, for reporting.
        live: Fingerprint of the live graph.
        replayed: Fingerprint of the replayed graph.
        events_replayed: How many events the replay applied.

    Returns:
        The comparison. Pure function — no I/O.
    """
    cmp = ReplayComparison(
        database=database,
        events_replayed=events_replayed,
        live=live,
        replayed=replayed,
    )

    # Inherited artifacts are not projections of THIS project's log, so replay
    # cannot produce them and their absence is not lost state. OntologyTerm
    # nodes arrive via `seldon ontology sync` from the `seldon-ontology` master
    # (AD-017) and are read-only locally — `create_artifact` refuses to make one
    # in a project with `inheritance: read-only`, which is precisely why no
    # local event exists. Counting them made every project with a synced
    # ontology report permanent "unrecoverable graph state": 2 phantom findings
    # in each of 13 projects, burying the genuine ones. Their recoverability is
    # real and is provided by re-syncing from master.
    inherited_live = {
        aid for aid in live.states
        if live.types.get(aid) in INHERITED_ARTIFACT_TYPES
    }
    inherited_replayed = {
        aid for aid in replayed.states
        if replayed.types.get(aid) in INHERITED_ARTIFACT_TYPES
    }
    cmp.inherited_skipped = len(inherited_live)

    live_ids = set(live.states) - inherited_live
    replayed_ids = set(replayed.states) - inherited_replayed
    cmp.missing_artifacts = sorted(live_ids - replayed_ids)
    cmp.extra_artifacts = sorted(replayed_ids - live_ids)
    for aid in sorted(live_ids & replayed_ids):
        if live.states[aid] != replayed.states[aid]:
            cmp.state_mismatches.append((aid, live.states[aid], replayed.states[aid]))

    missing = live.edges - replayed.edges
    extra = replayed.edges - live.edges
    cmp.missing_edges = [
        (f, r, t, n) for (f, r, t), n in sorted(missing.items(), key=lambda kv: str(kv[0]))
    ]
    cmp.extra_edges = [
        (f, r, t, n) for (f, r, t), n in sorted(extra.items(), key=lambda kv: str(kv[0]))
    ]
    return cmp


def replay_check(
    project_path: Path,
    driver,
    database: str,
    sweep: bool = True,
) -> ReplayComparison:
    """Replay a project's event log into a scratch DB and diff it against live.

    The live database is **never written to**. The replay targets a scratch
    database created for this call and dropped in a ``finally`` block, so an
    exception mid-replay still cleans up.

    Args:
        project_path: Project root holding ``seldon_events.jsonl``.
        driver: A connected ``neo4j.Driver``.
        database: The live project database to compare against.
        sweep: Reclaim orphaned scratch databases from crashed runs first.

    Returns:
        A :class:`ReplayComparison`. Failures that are properties of *this*
        project (unreadable log, unreachable database) are captured in
        ``error`` rather than raised, so an all-projects sweep reports every
        project instead of stopping at the first broken one.

    Raises:
        ValueError: If the scratch database name guard rejects a name, which
            would indicate a bug in this module rather than a project problem.
    """
    from seldon.core.sync import full_replay

    cmp = ReplayComparison(database=database)

    if sweep:
        try:
            reclaimed = sweep_stale_scratch_databases(driver)
            if reclaimed:
                logger.info("reclaimed orphaned scratch databases: %s", reclaimed)
        except Exception as exc:  # pragma: no cover - server-dependent
            # Sweeping is housekeeping. Failing it must not fail the check.
            logger.warning("scratch database sweep failed: %s", exc)

    scratch = scratch_database_name()
    created = False
    try:
        live_fp = fingerprint_graph(driver, database)
        create_scratch_database(driver, scratch)
        created = True
        count = full_replay(project_path, driver, scratch)
        replayed_fp = fingerprint_graph(driver, scratch)
    except Exception as exc:
        cmp.error = f"{type(exc).__name__}: {exc}"
        return cmp
    finally:
        if created:
            try:
                drop_scratch_database(driver, scratch)
            except Exception as exc:  # pragma: no cover - server-dependent
                logger.error(
                    "failed to drop scratch database %s: %s — drop it by hand",
                    scratch,
                    exc,
                )

    return compare_fingerprints(database, live_fp, replayed_fp, count)
