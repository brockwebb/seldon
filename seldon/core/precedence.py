"""`precedes` — finish-to-start ordering between ResearchTasks (AD-029).

`A precedes B` means B is not expected to leave `proposed` until A is
terminal-complete. This is the finish-to-start dependency of precedence
diagramming (PMBOK PDM; Kelley & Walker 1959, the critical-path method), which
is the prior art this edge implements rather than reinvents.

Two invariants are enforced at write time, before any event is appended:

* **No self-loop.** A task cannot precede itself.
* **The subgraph is a DAG.** A write that would close a cycle is rejected, and
  the error names the path that would close it. Cycle detection is a
  reachability query in the direction the new edge would *not* go: adding
  ``A -> B`` is legal exactly when B cannot already reach A.

Enforcement stops there. `precedes` is **advisory** for state transitions:
moving a successor forward while a predecessor is unsatisfied warns and
proceeds. Gates bind the machine, not the operator — the operator may reorder
work, and a hard block would only teach them to delete edges.

Which predecessor states count as satisfied
-------------------------------------------
`completed` and `verified` are terminal-complete: the work was done.
`superseded` and `withdrawn` are also satisfied — the work was replaced or its
premise was retracted, so nothing is pending and a successor that waited on
them forever would be waiting on nothing.

`rejected` is deliberately **not** satisfied. A rejected predecessor is work
that was refused, not work that was resolved, and a chain hanging off one is a
plan that needs revising rather than a plan that is proceeding. Because
enforcement is advisory this costs nothing: it surfaces the broken chain in
`task list` and the briefing without blocking anything. `seldon task unprecede`
is the one-line fix once the operator agrees the chain is dead.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

#: Relationship type as declared in the domain config (lowercase).
REL_TYPE = "precedes"

#: Stored (canonical, uppercase) spelling of the edge in Neo4j.
REL_TYPE_UPPER = REL_TYPE.upper()

#: The artifact type at both ends of the edge.
ARTIFACT_TYPE = "ResearchTask"

#: Predecessor states that satisfy a `precedes` edge. See the module docstring
#: for why `rejected` is absent.
SATISFIED_PREDECESSOR_STATES = frozenset(
    {"completed", "verified", "superseded", "withdrawn"}
)

#: How a task is rendered inside an error message or a chain.
SHORT_ID = 8

Pair = Tuple[str, str]


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PrecedesEdge:
    """One stored `precedes` edge, with whatever its endpoints turned out to be.

    Endpoint labels are carried rather than assumed: `seldon verify` needs to
    report an edge whose endpoint is missing or is not a ResearchTask, and it
    cannot do that from a query that filters those cases out.
    """

    from_id: Optional[str]
    to_id: Optional[str]
    from_type: Optional[str]
    to_type: Optional[str]
    reason: Optional[str] = None

    @property
    def pair(self) -> Pair:
        return (self.from_id or "", self.to_id or "")


def read_edges(session) -> List[PrecedesEdge]:
    """Read every stored `precedes` edge in the project graph.

    Deliberately unfiltered by endpoint label — see :class:`PrecedesEdge`.

    Args:
        session: An open Neo4j session bound to the project database.

    Returns:
        Every `PRECEDES` edge, ordered by predecessor then successor creation
        time so that callers render deterministically.
    """
    records = session.run(
        f"MATCH (a)-[r:{REL_TYPE_UPPER}]->(b) "
        "RETURN a.artifact_id AS from_id, b.artifact_id AS to_id, "
        "       a.artifact_type AS from_type, b.artifact_type AS to_type, "
        "       r.reason AS reason "
        "ORDER BY a.created_at, b.created_at"
    ).data()
    return [
        PrecedesEdge(
            from_id=r["from_id"],
            to_id=r["to_id"],
            from_type=r["from_type"],
            to_type=r["to_type"],
            reason=r["reason"],
        )
        for r in records
    ]


def read_pairs(session) -> List[Pair]:
    """Read `precedes` edges as (predecessor, successor) id pairs.

    Args:
        session: An open Neo4j session bound to the project database.

    Returns:
        Pairs for every edge whose endpoints both carry an artifact_id.
    """
    return [e.pair for e in read_edges(session) if e.from_id and e.to_id]


def read_task_states(session) -> Dict[str, str]:
    """Map every ResearchTask's artifact_id to its current state.

    Args:
        session: An open Neo4j session bound to the project database.

    Returns:
        Mapping of artifact_id to state.
    """
    records = session.run(
        f"MATCH (t:{ARTIFACT_TYPE}) RETURN t.artifact_id AS id, t.state AS state"
    ).data()
    return {r["id"]: r["state"] for r in records if r["id"]}


def edge_exists(session, from_id: str, to_id: str) -> bool:
    """Return True if a `precedes` edge already runs from from_id to to_id.

    Args:
        session: An open Neo4j session bound to the project database.
        from_id: Predecessor artifact_id.
        to_id: Successor artifact_id.

    Returns:
        True when at least one such edge is stored.
    """
    record = session.run(
        f"MATCH (a {{artifact_id: $a}})-[r:{REL_TYPE_UPPER}]->(b {{artifact_id: $b}}) "
        "RETURN count(r) AS n",
        a=from_id,
        b=to_id,
    ).single()
    return bool(record and record["n"])


# ---------------------------------------------------------------------------
# Graph algorithms (pure — no Neo4j, no I/O)
# ---------------------------------------------------------------------------

def successors(pairs: Iterable[Pair]) -> Dict[str, List[str]]:
    """Build the forward adjacency map.

    Args:
        pairs: (predecessor, successor) id pairs.

    Returns:
        Mapping of predecessor id to its successor ids, in input order.
    """
    out: Dict[str, List[str]] = {}
    for a, b in pairs:
        out.setdefault(a, [])
        out.setdefault(b, [])
        if b not in out[a]:
            out[a].append(b)
    return out


def predecessors(pairs: Iterable[Pair]) -> Dict[str, List[str]]:
    """Build the reverse adjacency map.

    Args:
        pairs: (predecessor, successor) id pairs.

    Returns:
        Mapping of successor id to its predecessor ids, in input order.
    """
    out: Dict[str, List[str]] = {}
    for a, b in pairs:
        out.setdefault(a, [])
        out.setdefault(b, [])
        if a not in out[b]:
            out[b].append(a)
    return out


def find_path(pairs: Iterable[Pair], start: str, goal: str) -> Optional[List[str]]:
    """Return a shortest `precedes` path from start to goal, or None.

    Breadth-first, so the path reported in a rejection message is the shortest
    one and therefore the easiest for an operator to check by eye.

    Args:
        pairs: (predecessor, successor) id pairs.
        start: Node to start from.
        goal: Node to reach.

    Returns:
        The node ids from start to goal inclusive, or None when goal is not
        reachable from start. A start equal to goal returns ``[start]``.
    """
    if start == goal:
        return [start]

    adj = successors(pairs)
    if start not in adj:
        return None

    came_from: Dict[str, str] = {}
    seen: Set[str] = {start}
    queue: deque[str] = deque([start])

    while queue:
        node = queue.popleft()
        for nxt in adj.get(node, []):
            if nxt in seen:
                continue
            came_from[nxt] = node
            if nxt == goal:
                path = [goal]
                while path[-1] != start:
                    path.append(came_from[path[-1]])
                return list(reversed(path))
            seen.add(nxt)
            queue.append(nxt)
    return None


def cycle_if_added(
    pairs: Iterable[Pair], before: str, after: str
) -> Optional[List[str]]:
    """Return the cycle that adding ``before -> after`` would close, or None.

    Args:
        pairs: The `precedes` pairs already in effect.
        before: Proposed predecessor.
        after: Proposed successor.

    Returns:
        The closing cycle as ``[before, after, ..., before]``, or None when the
        edge is safe. A self-edge returns ``[before, before]``.
    """
    if before == after:
        return [before, before]
    back = find_path(pairs, after, before)
    if back is None:
        return None
    return [before] + back


def find_cycles(pairs: Iterable[Pair]) -> List[List[str]]:
    """Find one concrete cycle per cyclic region of the subgraph.

    Kahn (1962) topological sort is the detector: whatever survives repeated
    removal of in-degree-zero nodes lies on or downstream of a cycle. A DFS over
    that residue then extracts a concrete cycle to report, because "there is a
    cycle somewhere" is not actionable and a named path is.

    Args:
        pairs: (predecessor, successor) id pairs.

    Returns:
        Cycles, each as ``[n1, n2, ..., n1]``. Empty when the subgraph is a DAG.
    """
    pair_list = list(pairs)
    self_loops = [[a, a] for a, b in pair_list if a == b]
    acyclic_pairs = [(a, b) for a, b in pair_list if a != b]

    residue = _kahn_residue(acyclic_pairs)
    cycles: List[List[str]] = list(self_loops)
    if not residue:
        return cycles

    adj = {
        node: [n for n in succ if n in residue]
        for node, succ in successors(acyclic_pairs).items()
        if node in residue
    }

    unvisited = set(residue)
    while unvisited:
        root = min(unvisited)
        cycle = _dfs_find_cycle(adj, root)
        if cycle is None:
            unvisited.discard(root)
            continue
        cycles.append(cycle)
        unvisited -= set(cycle)
    return cycles


def _kahn_residue(pairs: Sequence[Pair]) -> Set[str]:
    """Return the nodes that survive Kahn's algorithm — the cyclic residue.

    Args:
        pairs: (predecessor, successor) id pairs, self-loops already removed.

    Returns:
        Set of node ids that could not be topologically ordered.
    """
    adj = successors(pairs)
    indegree = {node: 0 for node in adj}
    for _, b in pairs:
        indegree[b] += 1

    queue = deque(sorted(n for n, d in indegree.items() if d == 0))
    removed: Set[str] = set()
    while queue:
        node = queue.popleft()
        removed.add(node)
        for nxt in adj.get(node, []):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)
    return set(adj) - removed


def _dfs_find_cycle(adj: Dict[str, List[str]], root: str) -> Optional[List[str]]:
    """Extract one concrete cycle reachable from root, as ``[n, ..., n]``.

    Args:
        adj: Forward adjacency restricted to the cyclic residue.
        root: Node to search from.

    Returns:
        The cycle node ids, or None if none is reachable from root.
    """
    stack: List[Tuple[str, int]] = [(root, 0)]
    path: List[str] = [root]
    on_path: Set[str] = {root}

    while stack:
        node, index = stack.pop()
        children = adj.get(node, [])
        if index >= len(children):
            path.pop()
            on_path.discard(node)
            continue
        stack.append((node, index + 1))
        child = children[index]
        if child in on_path:
            start = path.index(child)
            return path[start:] + [child]
        stack.append((child, 0))
        path.append(child)
        on_path.add(child)
    return None


def topological_order(
    pairs: Iterable[Pair],
    nodes: Optional[Iterable[str]] = None,
    rank: Optional[Dict[str, int]] = None,
) -> List[str]:
    """Order nodes so every predecessor precedes its successors.

    Args:
        pairs: (predecessor, successor) id pairs.
        nodes: Nodes to order. Defaults to every node mentioned in ``pairs``.
        rank: Optional tie-break ordering (typically creation order). Nodes
            absent from it sort last, then by id, so the result is total and
            deterministic either way.

    Returns:
        The node ids in topological order. Nodes caught in a cycle are appended
        at the end in rank order rather than dropped, so a caller rendering a
        corrupt graph still shows every node it was given.
    """
    pair_list = [(a, b) for a, b in pairs if a != b]
    node_set = set(nodes) if nodes is not None else set(successors(pair_list))
    pair_list = [(a, b) for a, b in pair_list if a in node_set and b in node_set]

    rank = rank or {}

    def sort_key(node: str) -> Tuple[int, str]:
        return (rank.get(node, len(rank)), node)

    adj = {n: [] for n in node_set}
    indegree = {n: 0 for n in node_set}
    for a, b in pair_list:
        if b not in adj[a]:
            adj[a].append(b)
            indegree[b] += 1

    ready = sorted((n for n in node_set if indegree[n] == 0), key=sort_key)
    ordered: List[str] = []
    while ready:
        node = ready.pop(0)
        ordered.append(node)
        for nxt in adj[node]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready.append(nxt)
        ready.sort(key=sort_key)

    leftover = sorted(node_set - set(ordered), key=sort_key)
    return ordered + leftover


@dataclass(frozen=True)
class Chain:
    """One weakly connected component of the `precedes` subgraph.

    Attributes:
        nodes: Component members in topological order.
        pairs: The component's edges.
        is_simple_path: True when every node has at most one predecessor and at
            most one successor — i.e. when ``A -> B -> C`` is a faithful
            rendering rather than a lossy one.
    """

    nodes: List[str]
    pairs: List[Pair]
    is_simple_path: bool


def chains(
    pairs: Iterable[Pair], rank: Optional[Dict[str, int]] = None
) -> List[Chain]:
    """Group the `precedes` subgraph into its connected components.

    Components of a single node are not returned: a task with no ordering
    relation to anything is not a chain, and rendering it as one would bury the
    real chains in noise.

    Args:
        pairs: (predecessor, successor) id pairs.
        rank: Optional tie-break ordering (typically creation order), used both
            within a component and to order the components themselves.

    Returns:
        Chains, ordered by the rank of their first node.
    """
    pair_list = list(pairs)
    rank = rank or {}
    adj_undirected: Dict[str, Set[str]] = {}
    for a, b in pair_list:
        adj_undirected.setdefault(a, set()).add(b)
        adj_undirected.setdefault(b, set()).add(a)

    seen: Set[str] = set()
    out: List[Chain] = []
    for node in sorted(adj_undirected, key=lambda n: (rank.get(n, len(rank)), n)):
        if node in seen:
            continue
        members: Set[str] = set()
        queue = deque([node])
        while queue:
            cur = queue.popleft()
            if cur in members:
                continue
            members.add(cur)
            queue.extend(adj_undirected.get(cur, ()) - members)
        seen |= members
        if len(members) < 2:
            continue
        member_pairs = [(a, b) for a, b in pair_list if a in members and b in members]
        out.append(
            Chain(
                nodes=topological_order(member_pairs, members, rank),
                pairs=member_pairs,
                is_simple_path=_is_simple_path(member_pairs),
            )
        )
    return out


def _is_simple_path(pairs: Sequence[Pair]) -> bool:
    """Return True when the component is a single unbranched line.

    Args:
        pairs: The component's edges.

    Returns:
        True when no node has two predecessors or two successors, no edge is
        duplicated, and no node is a self-loop.
    """
    if len(set(pairs)) != len(pairs):
        return False
    if any(a == b for a, b in pairs):
        return False
    out_deg: Dict[str, int] = {}
    in_deg: Dict[str, int] = {}
    for a, b in pairs:
        out_deg[a] = out_deg.get(a, 0) + 1
        in_deg[b] = in_deg.get(b, 0) + 1
    return max(out_deg.values(), default=0) <= 1 and max(in_deg.values(), default=0) <= 1


# ---------------------------------------------------------------------------
# Satisfaction and readiness
# ---------------------------------------------------------------------------

def unsatisfied_predecessors(
    task_id: str, pairs: Iterable[Pair], states: Dict[str, str]
) -> List[str]:
    """Return the predecessors of task_id that are not yet satisfied.

    A predecessor whose id is absent from ``states`` counts as unsatisfied: it
    cannot be shown to be complete, and `seldon verify` reports the dangling
    endpoint separately.

    Args:
        task_id: The successor to examine.
        pairs: (predecessor, successor) id pairs.
        states: Mapping of artifact_id to state.

    Returns:
        Unsatisfied predecessor ids, in edge order.
    """
    return [
        p
        for p in predecessors(pairs).get(task_id, [])
        if states.get(p) not in SATISFIED_PREDECESSOR_STATES
    ]


def is_ready(
    task_id: str,
    state: str,
    open_state_set: Iterable[str],
    pairs: Iterable[Pair],
    states: Dict[str, str],
) -> bool:
    """Return True if the task is open and every predecessor is satisfied.

    Args:
        task_id: The task to examine.
        state: Its current state.
        open_state_set: The states that count as open, from the domain config.
        pairs: (predecessor, successor) id pairs.
        states: Mapping of artifact_id to state.

    Returns:
        True when work on this task can start now.
    """
    if state not in set(open_state_set):
        return False
    return not unsatisfied_predecessors(task_id, pairs, states)


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

def short(artifact_id: str) -> str:
    """Return the display prefix of an artifact_id.

    Args:
        artifact_id: Full artifact_id.

    Returns:
        Its first :data:`SHORT_ID` characters.
    """
    return (artifact_id or "?")[:SHORT_ID]


def render_node(node_id: str, states: Dict[str, str]) -> str:
    """Render one node as ``3f2a1b9c [in_progress]``.

    Args:
        node_id: Full artifact_id.
        states: Mapping of artifact_id to state.

    Returns:
        The short id followed by the bracketed state. A node absent from
        ``states`` renders as ``[missing]`` rather than silently as ``[?]`` —
        a dangling endpoint is a real finding, not a formatting gap.
    """
    return f"{short(node_id)} [{states.get(node_id, 'missing')}]"


def chain_lines(
    chain: "Chain", states: Dict[str, str], descriptions: Dict[str, Any]
) -> List[str]:
    """Render one chain for a briefing: its shape, then its members.

    A simple path renders as ``A → B → C``, which is faithful. A branching
    component does not: rendering a fan-out as a line would assert an ordering
    the graph does not contain, so its edges are listed one per line instead.

    Args:
        chain: The component to render.
        states: Mapping of artifact_id to state.
        descriptions: Mapping of artifact_id to task description.

    Returns:
        Unindented lines. The caller supplies indentation and any bullet.
    """
    lines: List[str] = []
    if chain.is_simple_path:
        lines.append(" → ".join(render_node(n, states) for n in chain.nodes))
    else:
        lines.append(
            f"(branching — {len(chain.nodes)} tasks, {len(chain.pairs)} edges)"
        )
        lines.extend(
            f"{render_node(a, states)} → {render_node(b, states)}"
            for a, b in chain.pairs
        )
    for node in chain.nodes:
        desc = (descriptions.get(node) or "")[:60]
        if desc:
            lines.append(f"{short(node)}  {desc}")
    return lines


def render_path(node_ids: Sequence[str]) -> str:
    """Render a node sequence as ``a1b2c3d4 → e5f6a7b8``.

    Args:
        node_ids: Node ids in order.

    Returns:
        The arrow-joined short ids.
    """
    return " → ".join(short(n) for n in node_ids)


# ---------------------------------------------------------------------------
# Write-time validation
# ---------------------------------------------------------------------------

def validate_precedes_write(
    driver, database: str, from_id: str, to_id: str
) -> None:
    """Reject a `precedes` write that would break the DAG invariant.

    The single gate for every write path — the CLI, the MCP tools and
    `seldon link create` all reach it through
    :func:`seldon.core.artifacts.create_link`, so none of them can author a
    cycle. It runs before the event is appended, so a rejected write leaves no
    trace in either the event log or the graph.

    Args:
        driver: Neo4j driver.
        database: Project database name.
        from_id: Proposed predecessor artifact_id.
        to_id: Proposed successor artifact_id.

    Raises:
        ValueError: On a self-loop, or when the edge would close a cycle. The
            message names the path that would close it.
    """
    if from_id == to_id:
        raise ValueError(
            f"A task cannot precede itself: {short(from_id)}."
        )

    with driver.session(database=database) as session:
        pairs = read_pairs(session)

    cycle = cycle_if_added(pairs, from_id, to_id)
    if cycle is not None:
        raise ValueError(
            f"'{REL_TYPE}' must stay acyclic: {short(from_id)} → {short(to_id)} "
            f"would close the cycle {render_path(cycle)}."
        )


# ---------------------------------------------------------------------------
# Write paths
# ---------------------------------------------------------------------------

@dataclass
class ChainResult:
    """What a `precede` / `chain` call actually did.

    Attributes:
        resolved: The full artifact_ids, in the order given.
        created: Pairs written by this call.
        skipped: Pairs that already existed, so nothing was written for them.
    """

    resolved: List[str]
    created: List[Pair]
    skipped: List[Pair]


def add_chain(
    project_dir: Path,
    driver,
    database: str,
    domain_config,
    task_ids: Sequence[str],
    reason: Optional[str] = None,
    actor: str = "human",
    authority: str = "accepted",
    session_id: Optional[str] = None,
) -> ChainResult:
    """Write the consecutive `precedes` pairs of a chain of tasks.

    ``add_chain([A, B, C])`` writes ``A -> B`` and ``B -> C``. Two ids is the
    degenerate case and is how `seldon task precede` is implemented, so both
    surfaces share one validator and one writer.

    All-or-nothing: every pair is validated against the graph *plus* the pairs
    earlier in this same call before the first event is appended, so a chain
    that goes wrong at its third link writes nothing at all. An existing pair is
    skipped rather than duplicated — re-running the same chain is a no-op, which
    is what makes a chain safe to keep in a runbook.

    Args:
        project_dir: Project root, for the JSONL event store.
        driver: Neo4j driver.
        database: Project database name.
        domain_config: Loaded domain configuration.
        task_ids: Two or more ResearchTask ids or unambiguous prefixes, in
            execution order.
        reason: Optional free text stored on every edge this call writes.
        actor: Actor string written to the events.
        authority: Authority string written to the events.
        session_id: Optional Seldon session id recorded on the events.

    Returns:
        A :class:`ChainResult` describing what was written and what was skipped.

    Raises:
        ValueError: If fewer than two ids are given, an id is unknown or
            ambiguous, an endpoint is not a ResearchTask, a pair is a self-loop,
            or a pair would close a cycle. Nothing is written in any of those
            cases.
    """
    from seldon.core.artifacts import create_link, resolve_artifact_id
    from seldon.core.graph import get_artifact

    if len(task_ids) < 2:
        raise ValueError(
            f"'{REL_TYPE}' needs at least two tasks; got {len(task_ids)}."
        )

    resolved = [resolve_artifact_id(driver, database, tid) for tid in task_ids]

    with driver.session(database=database) as session:
        for given, full_id in zip(task_ids, resolved):
            node = get_artifact(session, full_id)
            if node is None:
                raise ValueError(f"No artifact found matching '{given}'.")
            actual = node.get("artifact_type")
            if actual != ARTIFACT_TYPE:
                raise ValueError(
                    f"'{short(full_id)}' is a {actual}, not a {ARTIFACT_TYPE}: "
                    f"'{REL_TYPE}' orders tasks only."
                )
        working = set(read_pairs(session))

    created: List[Pair] = []
    skipped: List[Pair] = []
    for before, after in zip(resolved, resolved[1:]):
        if (before, after) in working:
            skipped.append((before, after))
            continue
        cycle = cycle_if_added(working, before, after)
        if cycle is not None:
            if before == after:
                raise ValueError(f"A task cannot precede itself: {short(before)}.")
            raise ValueError(
                f"'{REL_TYPE}' must stay acyclic: {short(before)} → {short(after)} "
                f"would close the cycle {render_path(cycle)}."
            )
        created.append((before, after))
        working.add((before, after))

    rel_properties = {"reason": reason} if reason else {}
    for before, after in created:
        create_link(
            project_dir=project_dir,
            driver=driver,
            database=database,
            domain_config=domain_config,
            from_id=before,
            to_id=after,
            from_type=ARTIFACT_TYPE,
            to_type=ARTIFACT_TYPE,
            rel_type=REL_TYPE,
            actor=actor,
            authority=authority,
            session_id=session_id,
            rel_properties=rel_properties,
        )

    return ChainResult(resolved=resolved, created=created, skipped=skipped)


def remove_precedence(
    project_dir: Path,
    driver,
    database: str,
    before_id: str,
    after_id: str,
    actor: str = "human",
    authority: str = "accepted",
    session_id: Optional[str] = None,
) -> Pair:
    """Remove one `precedes` edge.

    Args:
        project_dir: Project root, for the JSONL event store.
        driver: Neo4j driver.
        database: Project database name.
        before_id: Predecessor id or unambiguous prefix.
        after_id: Successor id or unambiguous prefix.
        actor: Actor string written to the event.
        authority: Authority string written to the event.
        session_id: Optional Seldon session id recorded on the event.

    Returns:
        The (predecessor, successor) pair that was removed, as full ids.

    Raises:
        ValueError: If either id is unknown or ambiguous, or no such edge
            exists. Nothing is written in either case.
    """
    from seldon.core.artifacts import remove_link, resolve_artifact_id

    before = resolve_artifact_id(driver, database, before_id)
    after = resolve_artifact_id(driver, database, after_id)

    with driver.session(database=database) as session:
        if not edge_exists(session, before, after):
            raise ValueError(
                f"No '{REL_TYPE}' edge from {short(before)} to {short(after)}."
            )

    remove_link(
        project_dir=project_dir,
        driver=driver,
        database=database,
        from_id=before,
        to_id=after,
        rel_type=REL_TYPE,
        actor=actor,
        authority=authority,
        session_id=session_id,
    )
    return (before, after)


# ---------------------------------------------------------------------------
# Briefing / listing views
# ---------------------------------------------------------------------------

def precedence_view(session, open_state_set: Iterable[str]) -> Dict[str, Any]:
    """Assemble everything the read surfaces need, in one pass over the graph.

    `seldon task list`, `seldon go` and `seldon briefing` all need the same
    three derived facts, and each computing them from its own queries is how
    they would drift apart.

    Args:
        session: An open Neo4j session bound to the project database.
        open_state_set: The states that count as open, from the domain config.

    Returns:
        Dict with keys:
            ``pairs`` — the `precedes` pairs;
            ``states`` — artifact_id to state for every ResearchTask;
            ``rank`` — artifact_id to creation-order index;
            ``waits_on`` — artifact_id to its unsatisfied predecessor ids;
            ``ready`` — open task ids with no unsatisfied predecessor, in
            creation order;
            ``chains`` — the connected components, as :class:`Chain` objects.
    """
    records = session.run(
        f"MATCH (t:{ARTIFACT_TYPE}) RETURN t.artifact_id AS id, t.state AS state, "
        "t.description AS description ORDER BY t.created_at"
    ).data()
    states = {r["id"]: r["state"] for r in records if r["id"]}
    descriptions = {r["id"]: r["description"] for r in records if r["id"]}
    rank = {r["id"]: i for i, r in enumerate(records) if r["id"]}

    pairs = read_pairs(session)
    open_set = set(open_state_set)

    waits_on = {
        tid: unsatisfied_predecessors(tid, pairs, states) for tid in states
    }
    ready = [
        tid
        for tid in sorted(states, key=lambda t: rank.get(t, len(rank)))
        if states.get(tid) in open_set and not waits_on[tid]
    ]

    return {
        "pairs": pairs,
        "states": states,
        "descriptions": descriptions,
        "rank": rank,
        "waits_on": waits_on,
        "ready": ready,
        "chains": chains(pairs, rank),
    }


#: Target states at which an unsatisfied predecessor is worth saying out loud.
#: Starting work is the moment the ordering matters; finishing or abandoning a
#: task is not, and warning there would only be noise.
ADVISORY_TARGET_STATES = frozenset({"accepted", "in_progress"})


def transition_warnings(
    driver, database: str, artifact_id: str, new_state: str
) -> List[str]:
    """Return advisory warnings for starting a task ahead of its predecessors.

    Advisory by design: the caller prints these and proceeds. Gates bind the
    machine, not the operator — an operator who reorders work deliberately must
    not have to delete graph edges to be allowed to do it.

    Args:
        driver: Neo4j driver.
        database: Project database name.
        artifact_id: The ResearchTask being transitioned.
        new_state: The state it is moving to.

    Returns:
        Zero or one warning line. Empty for any transition that is not a start,
        and for a start whose predecessors are all satisfied.
    """
    if new_state not in ADVISORY_TARGET_STATES:
        return []

    with driver.session(database=database) as session:
        pairs = read_pairs(session)
        states = read_task_states(session)

    unmet = unsatisfied_predecessors(artifact_id, pairs, states)
    if not unmet:
        return []

    listed = ", ".join(f"{short(p)} [{states.get(p, 'missing')}]" for p in unmet)
    plural = "s" if len(unmet) > 1 else ""
    return [
        f"Warning: {short(artifact_id)} → {new_state} with {len(unmet)} "
        f"unsatisfied predecessor{plural}: {listed}. "
        f"'{REL_TYPE}' is advisory — proceeding."
    ]
