"""`waits_on` across graphs: a ResearchTask that waits on a task in another project's graph (AD-038-R8, SEL-008).

**Why this exists.** A `precedes` edge can only name a task in its own graph (AD-029), and projects on this machine
feed each other: hazbrief files defects to squiddy and waits on them, squiddy files to seldon. On 2026-10-24 hazbrief
HB-20 (`311388f9`) waited on squiddy SQ-048, and the only record of it was a handoff paragraph: the graph showed one
`precedes` edge, so a dispatcher reading it would have launched HB-20 into the failure it had already stopped on.

**The shape.** The edge is a property of the waiting task, ``waits_on_external``: a list of ``<project>:<artifact_id>``
strings, written by an ``artifact_updated`` event in the WAITING project's ledger only. The other graph is read and
never written. Neo4j cannot hold an edge between two databases, and each project owns its database (the
cross-project architecture table in ``~/GitHub/CLAUDE.md``), so the edge is stored where it is asserted and its target
is resolved where it lives, at the time of every read.

**Prior art.**

- Bazel external repositories and Make's cross-directory prerequisites: a dependency names its target by a qualified
  label (``@repo//pkg:target``) that the reader resolves through its own configuration, and the build that declares
  it never writes into the other repository. The qualifier here is the project name, resolved the way the decision
  register resolves a repository (``decisions.repositories``, then the side-by-side convention).
- GitHub's cross-repository references (``owner/repo#123``) and Jira's "is blocked by" links across projects: a
  blocking link is stored on the waiting issue and rendered with the target's live state.
- Airflow's ``ExternalTaskSensor``: a task waits on a task in another DAG, and the scheduler polls the other DAG's
  state; a target that cannot be read is "not yet", never "done". That is the fail-closed rule below.

**Satisfaction.** A wait is satisfied when its target is ``completed`` or ``verified``: terminal SUCCESS. This departs
from AD-029 section 3, where ``superseded`` and ``withdrawn`` also satisfy a ``precedes`` edge. A cross-project wait is
a dependency on work landing in another repository; a superseded target means the work moved to another task, and a
waiter that proceeded on it would proceed on nothing. Those targets are "dead ends": the wait stays unsatisfied and
``seldon verify`` names it so the operator re-points or removes it.

**Fail closed.** An unreadable other graph (no project, no database, a refused connection) is "not ready", logged,
never "ready". A surface that does not read the other graph at all counts every cross-project wait as unsatisfied
(:func:`seldon.core.precedence.precedence_view`); :func:`overlay` is what reads it and releases the satisfied ones.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

#: The ResearchTask property that holds the waits (declared in `seldon/domain/research.yaml`).
PROPERTY = "waits_on_external"

#: Joins the project and the task in a stored or typed target.
QUALIFIER = ":"

#: Target states that satisfy a wait: the work was done.
SATISFIED_STATES = frozenset({"completed", "verified"})

#: Target states that end without satisfying it: the wait needs re-pointing (`seldon verify` reports them).
DEAD_END_STATES = frozenset({"superseded", "withdrawn", "rejected"})

#: The typed form, quoted in every refusal.
GRAMMAR = "<project>:<task-prefix>"

#: A project name as the side-by-side convention spells a directory: no separators, no spaces.
_PROJECT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
#: A task reference: an artifact id or prefix, or (in an `**After:**` header) a cc_tasks file stem.
_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True)
class Target:
    """A typed or stored cross-project target, before resolution."""

    project: str
    ref: str

    @property
    def qualified(self) -> str:
        return f"{self.project}{QUALIFIER}{self.ref}"


@dataclass(frozen=True)
class TargetState:
    """What the other graph says about one target, as of the read.

    Attributes:
        state: The target's state, or None when it could not be read or no longer resolves.
        name: The target's name (its task-file stem), when it has one.
        description: The target's description.
        error: Why the target could not be read (the project or its graph); None when it was read. A target the
            graph was read for and did not contain has ``state`` None and ``missing`` True instead.
        missing: The other graph was read and holds no such task.
    """

    state: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    error: Optional[str] = None
    missing: bool = False

    @property
    def satisfied(self) -> bool:
        return self.error is None and self.state in SATISFIED_STATES


def is_qualified(text: str) -> bool:
    """True when ``text`` names a target in another project (it carries the qualifier)."""
    return QUALIFIER in (text or "")


def parse_target(text: str) -> Target:
    """Parse ``<project>:<task-prefix>``.

    Raises:
        ValueError: The text is not exactly one project name, one qualifier and one reference.
    """
    raw = (text or "").strip().strip("`")
    parts = raw.split(QUALIFIER)
    if len(parts) != 2 or not _PROJECT_RE.match(parts[0]) or not _REF_RE.match(parts[1]):
        raise ValueError(f"{text!r} is not a cross-project target; expected {GRAMMAR}, for example "
                         f"squiddy:3f2a1b9c (the project's name, as its directory or seldon.yaml "
                         f"tasks.projects names it, and a task id prefix)")
    return Target(project=parts[0], ref=parts[1])


def _anchor(project_dir: Path) -> Path:
    """The directory relative project paths resolve against: the PRIMARY checkout.

    In a git worktree (`.claude/worktrees/<stem>`) the side-by-side siblings are beside the primary checkout, not
    beside the worktree, which is where a worktree-relative `../squiddy` would look (the prior-art gate met this as
    `release_unavailable`, STD-001R). Outside a git work tree the project directory itself is the anchor.
    """
    from seldon.core.worktree import WorktreeError, primary_checkout

    try:
        return primary_checkout(Path(project_dir)).resolve()
    except WorktreeError:
        return Path(project_dir).resolve()


def project_root(name: str, project_dir: Path, config: Optional[dict]) -> Path:
    """The root of the Seldon project ``name`` names, from the waiting project's point of view.

    Resolution order, first match wins (the decision register's, `seldon.core.decisions.settings`):
    `tasks.projects.<name>` in the waiting project's seldon.yaml, then `decisions.repositories.<name>`, then the
    side-by-side convention (``<anchor>/../<name>``). Relative paths resolve against the primary checkout.

    Raises:
        ValueError: The resolved directory holds no seldon.yaml. The message names every place it looked.
    """
    config = config or {}
    anchor = _anchor(project_dir)
    looked: List[str] = []
    candidates: List[Tuple[str, Path]] = []
    configured = ((config.get("tasks") or {}).get("projects") or {}).get(name)
    if configured:
        candidates.append(("seldon.yaml tasks.projects", (anchor / configured)))
    registered = ((config.get("decisions") or {}).get("repositories") or {}).get(name)
    if registered:
        candidates.append(("seldon.yaml decisions.repositories", (anchor / registered)))
    candidates.append(("the side-by-side convention", anchor.parent / name))
    for source, path in candidates:
        path = path.resolve()
        if (path / "seldon.yaml").is_file():
            return path
        looked.append(f"{path} ({source})")
    raise ValueError(f"project {name!r} resolves to no Seldon project: no seldon.yaml at "
                     f"{'; '.join(looked)}. Name it under tasks.projects in this project's seldon.yaml.")


def _open(name: str, project_dir: Path, config: Optional[dict]):
    """A driver and database for the other project's graph, from ITS seldon.yaml. The caller closes the driver."""
    from seldon.config import get_neo4j_driver, load_project_config

    root = project_root(name, project_dir, config)
    other = load_project_config(root)
    database = (other.get("neo4j") or {}).get("database")
    if not database:
        raise ValueError(f"project {name!r} at {root} names no neo4j.database in its seldon.yaml")
    return get_neo4j_driver(other), database, root


def resolve(text: str, project_dir: Path, config: Optional[dict]) -> Tuple[str, dict]:
    """Resolve a typed target to its stored form and the target's node. Reads the other graph; writes nothing.

    Returns:
        ``(qualified full id, node properties)``.

    Raises:
        ValueError: The grammar, the project, an unknown or ambiguous prefix, or a target that is not a
            ResearchTask. Every one is raised before the caller writes anything.
    """
    from seldon.core.artifacts import resolve_artifact_id
    from seldon.core.graph import get_artifact

    target = parse_target(text)
    driver, database, root = _open(target.project, project_dir, config)
    try:
        full = resolve_artifact_id(driver, database, target.ref)
        with driver.session(database=database) as session:
            node = get_artifact(session, full)
    except ValueError as exc:
        raise ValueError(f"{exc} (in project {target.project!r}, {root})") from exc
    finally:
        driver.close()
    if node is None:
        raise ValueError(f"No artifact found matching '{target.ref}' in project {target.project!r}.")
    if node.get("artifact_type") != "ResearchTask":
        raise ValueError(f"{target.project}:{full[:8]} is a {node.get('artifact_type')}, not a ResearchTask: a task "
                         f"waits on tasks only.")
    return f"{target.project}{QUALIFIER}{full}", dict(node)


def resolve_after_ref(ref: str, project_dir: Path, config: Optional[dict]) -> str:
    """A `<project>:<ref>` entry of a task file's `**After:**` header, to its stored form.

    The ref is a cc_tasks stem or an id prefix, resolved in the OTHER graph by the same rule a local ref is
    (`seldon.commands.cc.resolve_after_refs`), so a stem and a prefix mean the same thing on both sides.

    Raises:
        ValueError: The project or the ref does not resolve to exactly one ResearchTask.
    """
    from seldon.commands.cc import resolve_after_refs

    target = parse_target(ref)
    driver, database, root = _open(target.project, project_dir, config)
    try:
        (full,) = resolve_after_refs(driver, database, [target.ref])
    finally:
        driver.close()
    return f"{target.project}{QUALIFIER}{full}"


def read_targets(qualified: Iterable[str], project_dir: Path, config: Optional[dict]) -> Dict[str, TargetState]:
    """Read every target's state, one connection per project. Never raises for a target: an unreadable project or
    graph is that target's ``error``, so one dark project cannot hide the others.
    """
    by_project: Dict[str, List[Tuple[str, str]]] = {}
    out: Dict[str, TargetState] = {}
    for q in qualified:
        try:
            t = parse_target(q)
        except ValueError as exc:
            out[q] = TargetState(error=str(exc))
            continue
        by_project.setdefault(t.project, []).append((q, t.ref))
    for project, rows in by_project.items():
        try:
            driver, database, _root = _open(project, project_dir, config)
        except Exception as exc:                                    # noqa: BLE001  (recorded per target)
            for q, _ in rows:
                out[q] = TargetState(error=f"{type(exc).__name__}: {exc}")
            continue
        try:
            with driver.session(database=database) as session:
                found = {r["id"]: r for r in session.run(
                    "MATCH (t:Artifact:ResearchTask) WHERE t.artifact_id IN $ids "
                    "RETURN t.artifact_id AS id, t.state AS state, t.name AS name, t.description AS description",
                    ids=[ref for _, ref in rows]).data()}
            for q, ref in rows:
                r = found.get(ref)
                out[q] = (TargetState(state=r["state"], name=r["name"], description=r["description"])
                          if r else TargetState(missing=True))
        except Exception as exc:                                    # noqa: BLE001  (recorded per target)
            # A refused connection, an absent database, an auth failure: each is "this graph could not be read",
            # and the caller treats it as not ready. Recorded with its type so the log says which.
            for q, _ in rows:
                out[q] = TargetState(error=f"{type(exc).__name__}: {exc}")
        finally:
            driver.close()
    return out


def render(qualified: str, st: Optional[TargetState]) -> str:
    """``squiddy:3f2a1b9c [proposed]``, ``[missing]`` when the graph holds no such task, ``[unreadable]`` when it
    could not be read."""
    from seldon.core.precedence import short

    if st is None or st.error:
        return f"{short(qualified)} [unreadable]"
    if st.missing:
        return f"{short(qualified)} [missing]"
    return f"{short(qualified)} [{st.state}]"


def overlay(view: dict, project_dir: Path, config: Optional[dict]) -> dict:
    """Release the satisfied cross-project waits of a :func:`~seldon.core.precedence.precedence_view`, in place.

    The raw view counts every cross-project wait as unsatisfied; this reads the other graphs and removes the
    satisfied ones from ``waits_on``, recomputes ``ready`` by the view's own rule, and adds ``external_states``
    (qualified id to :class:`TargetState`) for rendering.
    """
    external: Dict[str, List[str]] = view.get("external") or {}
    qualified = sorted({q for qs in external.values() for q in qs})
    states = read_targets(qualified, project_dir, config) if qualified else {}
    view["external_states"] = states
    if not qualified:
        return view
    for tid, qs in external.items():
        satisfied = {q for q in qs if states.get(q) and states[q].satisfied}
        view["waits_on"][tid] = [w for w in view["waits_on"].get(tid, []) if w not in satisfied]
    rank = view.get("rank") or {}
    open_set = set(view.get("open_states") or ())
    view["ready"] = [tid for tid in sorted(view["states"], key=lambda t: rank.get(t, len(rank)))
                     if view["states"].get(tid) in open_set and not view["waits_on"].get(tid)]
    return view


def unsatisfied_waits(project_dir: Path, tasks: Iterable[dict], config: Optional[dict] = None,
                      on_error: Optional[Callable[[str], None]] = None) -> Dict[str, List[dict]]:
    """The dispatcher's c17 input: each task's unsatisfied cross-project waits.

    Args:
        project_dir: The waiting project's root.
        tasks: Task rows carrying ``artifact_id`` and :data:`PROPERTY`.
        config: The waiting project's seldon.yaml, read from ``project_dir`` when None.
        on_error: Called with one line per target that could not be read, so the pass logs it.

    Returns:
        ``{task_id: [{"target", "state", "error"}]}``, holding only tasks with at least one unsatisfied wait. A
        target that could not be read is unsatisfied, with its ``error``.
    """
    if config is None:
        from seldon.config import load_project_config
        config = load_project_config(Path(project_dir))
    rows = [(t["artifact_id"], list(t.get(PROPERTY) or [])) for t in tasks]
    qualified = sorted({q for _, qs in rows for q in qs})
    if not qualified:
        return {}
    states = read_targets(qualified, project_dir, config)
    out: Dict[str, List[dict]] = {}
    for tid, qs in rows:
        unmet = []
        for q in qs:
            st = states.get(q) or TargetState(error="not read")
            if st.satisfied:
                continue
            if st.error and on_error:
                on_error(f"waits_on: {tid[:8]} -> {q}: the other graph could not be read ({st.error}); "
                         f"not ready")
            unmet.append({"target": q, "state": st.state,
                          "error": st.error or ("no longer resolves" if st.missing else None)})
        if unmet:
            out[tid] = unmet
    return out


# ---------------------------------------------------------------------------
# Write paths (the waiting project's ledger only)
# ---------------------------------------------------------------------------

def current_waits(driver, database: str, task_id: str) -> List[str]:
    """The task's stored waits, in order."""
    from seldon.core.graph import get_artifact

    with driver.session(database=database) as session:
        node = get_artifact(session, task_id)
    return list((node or {}).get(PROPERTY) or [])


def add_wait(project_dir: Path, driver, database: str, task_id: str, target: str, config: Optional[dict],
             actor: str, authority: str = "accepted", session_id: Optional[str] = None) -> Tuple[str, bool]:
    """Record that ``task_id`` (a full id, in this project) waits on ``target`` (typed, in another project).

    Resolves the target in the other graph before the one write; re-recording a wait is a no-op.

    Returns:
        ``(qualified full id, written)``.

    Raises:
        ValueError: As :func:`resolve`. Nothing is written.
    """
    from seldon.core.artifacts import commit_writes, plan_update_artifact

    qualified, _node = resolve(target, project_dir, config)
    waits = current_waits(driver, database, task_id)
    if qualified in waits:
        return qualified, False
    write = plan_update_artifact(project_dir=project_dir, driver=driver, database=database, artifact_id=task_id,
                                 properties={PROPERTY: waits + [qualified]}, actor=actor, authority=authority,
                                 session_id=session_id)
    commit_writes(project_dir, driver, database, [write])
    return qualified, True


def remove_wait(project_dir: Path, driver, database: str, task_id: str, target: str, actor: str,
                authority: str = "accepted", session_id: Optional[str] = None) -> str:
    """Remove one stored wait. The target need not resolve any more: removing a dead wait is the point.

    ``target`` is ``<project>:<prefix>``; it must match exactly one stored wait.

    Raises:
        ValueError: The grammar, or no (or more than one) stored wait matches. Nothing is written.
    """
    from seldon.core.artifacts import commit_writes, plan_update_artifact

    t = parse_target(target)
    waits = current_waits(driver, database, task_id)
    hits = [w for w in waits if w.split(QUALIFIER, 1)[0] == t.project
            and w.split(QUALIFIER, 1)[1].startswith(t.ref)]
    if len(hits) != 1:
        shown = ", ".join(waits) or "none"
        raise ValueError(f"{target!r} matches {len(hits)} of {task_id[:8]}'s cross-project waits ({shown}); "
                         f"nothing was removed.")
    remaining = [w for w in waits if w != hits[0]]
    write = plan_update_artifact(project_dir=project_dir, driver=driver, database=database, artifact_id=task_id,
                                 properties={PROPERTY: remaining or None}, actor=actor, authority=authority,
                                 session_id=session_id)
    commit_writes(project_dir, driver, database, [write])
    return hits[0]
