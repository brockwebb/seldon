"""Desktop session closeout: the session window, the AD-030-R9 gate, and the
handoff document rendered from graph state.

`seldon handoff` (CLI) and `seldon_handoff` (MCP) are two surfaces over this one
module, so a Desktop thread closing through MCP and an operator closing through
the terminal produce byte-identical output.

Three things happen here, in this order:

1. **The session window is derived, never declared.** "This session" starts at
   the newest LabNotebookEntry or the newest handoff file, whichever is later,
   and falls back to a configured number of hours when neither exists. Asking
   the operator to type a window would make the report a claim rather than a
   reading of the record.
2. **AD-030-R9 is enforced.** A Desktop session that created ResearchTasks and
   wrote no design note closed with tasks instead of a decision record; the
   rulings those tasks implement would exist nowhere addressable. This module
   refuses that close.
3. **The handoff is generated.** Prose the operator owns is exactly three
   strings — summary, next action, slug. Everything else is read from the event
   log, the graph and the filesystem (AD-030-R2: derived artifacts are never
   authored by hand).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from seldon.core.events import read_events

#: Fallback session window used only when `handoff.session_window_hours` is
#: absent from seldon.yaml. Projects created by `seldon init` carry the key, so
#: this covers pre-existing projects whose config predates the handoff tool.
DEFAULT_SESSION_WINDOW_HOURS = 12

#: Fallback for `handoff.require_design_note`. AD-030-R9 is binding by default;
#: a project opts down to a warning, never up to silence.
DEFAULT_REQUIRE_DESIGN_NOTE = True

#: Directory whose contents satisfy the AD-030-R9 design-note obligation.
DESIGN_DIR = "docs/design"

#: Directories reported under "Files written". Both are governed directories
#: per AD-030-R1; handoffs/ is excluded because this command writes into it.
REPORTED_DIRS = (DESIGN_DIR, "cc_tasks")

#: Directory holding handoff documents.
HANDOFFS_DIR = "handoffs"

#: THE ALLOW-LIST OF ONE (AD-030-R11). The R9 design-note gate binds every actor except `cc`.
#:
#: It was a deny-list on `desktop` at first, which is the same thing only while `desktop` is the
#: only other actor that exists. An autonomous agent, a script, a typo in an actor string — each
#: would have escaped the gate silently, and an unknown actor escaping a gate silently is the
#: failure mode AD-030 section 2 describes. Stated as what is exempt, the list cannot rot: a new
#: actor is gated by default and someone has to decide to exempt it.
#:
#: `cc` is exempt because CC executes decisions someone else made. Anything else that files a task
#: is deciding, and a decision owes a design note.
EXEMPT_ACTORS = frozenset({"cc"})

#: Actor stamped on artifacts created through the MCP tools (Desktop sessions).
#: Matches `seldon.mcp_server.MCP_ACTOR`; duplicated as a constant rather than
#: imported because importing the MCP server pulls in the `mcp` package, which
#: this module must not require.
DESKTOP_ACTOR = "desktop"


def actor_is_gated(actor: str | None) -> bool:
    """Whether an actor owes a design note when it files a task (AD-030-R11).

    Args:
        actor: The actor string on the creating event, or None.

    Returns:
        True for every actor but `cc`. A missing actor is gated: an event that does not say who
        wrote it is exactly the case the allow-list exists to catch.
    """
    return (actor or "") not in EXEMPT_ACTORS

#: Refusal text for AD-030-R9. Fixed wording — Desktop threads and the CLI both
#: quote it, and the operator greps for it.
R9_MESSAGE = (
    "Desktop design session closed without a design note (AD-030-R9). "
    "Write docs/design/<note>.md, then rerun."
)

#: Task states that count as "closed" in the graph-changes report.
CLOSED_STATES = ("completed", "verified")

#: Terminal states reported separately from closure (AD-028).
WITHDRAWN_STATE = "withdrawn"
SUPERSEDED_STATE = "superseded"

#: `YYYY-MM-DD` prefix on a handoff filename. Mirrors the ordering convention
#: `seldon.commands.go` already applies: the declared session date is
#: authoritative, the slug after it is not.
_HANDOFF_DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?!\d)")


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HandoffSettings:
    """Configuration for one project's closeout behaviour.

    Attributes:
        session_window_hours: Fallback window length when no LabNotebookEntry
            and no handoff file exist to bound the session.
        require_design_note: True refuses an AD-030-R9 violation; False warns.
    """

    session_window_hours: float
    require_design_note: bool


def handoff_settings(config: dict) -> HandoffSettings:
    """Read the `handoff` block of a project config.

    Args:
        config: Parsed seldon.yaml.

    Returns:
        The project's settings, with module defaults filling absent keys.

    Raises:
        ValueError: If `handoff.session_window_hours` is present but is not a
            positive number. A misconfigured window silently truncating the
            report is the failure this refuses.
    """
    block = config.get("handoff") or {}
    hours = block.get("session_window_hours", DEFAULT_SESSION_WINDOW_HOURS)
    try:
        hours = float(hours)
    except (TypeError, ValueError):
        raise ValueError(
            f"handoff.session_window_hours must be a number, got {hours!r}"
        )
    if hours <= 0:
        raise ValueError(
            f"handoff.session_window_hours must be positive, got {hours!r}"
        )
    require = block.get("require_design_note", DEFAULT_REQUIRE_DESIGN_NOTE)
    return HandoffSettings(
        session_window_hours=hours,
        require_design_note=bool(require),
    )


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def _parse_iso(value: Any) -> Optional[datetime]:
    """Parse a Seldon timestamp into an aware UTC datetime.

    Seldon writes `...Z`-suffixed ISO-8601; Neo4j may return a native temporal
    type instead. Both are accepted; anything else yields None rather than an
    exception, because a single malformed timestamp must not make a closeout
    impossible.

    Args:
        value: Timestamp as a string, a datetime, or a Neo4j temporal.

    Returns:
        Aware UTC datetime, or None when the value cannot be read as a time.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    to_native = getattr(value, "to_native", None)
    if callable(to_native):
        native = to_native()
        if isinstance(native, datetime):
            return native if native.tzinfo else native.replace(tzinfo=timezone.utc)
        return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def handoff_boundary(path: Path) -> datetime:
    """Return the instant a handoff file marks the end of its session.

    The filename's declared session date is authoritative — that is the existing
    project convention, and it is the only marker that survives a fresh clone,
    where every file's mtime is the checkout time. The modification time is used
    only when it agrees with the declared date, which is what makes a second
    session on the same day bound precisely instead of being folded into the
    first.

    A file with no date prefix has no declared date, so its mtime stands alone.

    Args:
        path: Handoff file.

    Returns:
        Aware UTC datetime bounding the end of that session.

    Raises:
        OSError: If the file's metadata cannot be read.
    """
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    match = _HANDOFF_DATE_PREFIX_RE.match(path.name)
    if not match:
        return mtime
    declared = datetime.strptime(match.group(1), "%Y-%m-%d").replace(
        tzinfo=timezone.utc
    )
    if mtime.date() == declared.date():
        return mtime
    return declared


def handoff_files(project_dir: Path) -> list[Path]:
    """Return handoff files newest-first by declared session date, then mtime.

    Dotfiles are excluded so filesystem debris (`.DS_Store`) can never be read
    as a session boundary.

    Args:
        project_dir: Project root.

    Returns:
        Handoff paths, most recent first. Empty when the directory is absent.
    """
    directory = Path(project_dir) / HANDOFFS_DIR
    if not directory.is_dir():
        return []
    candidates = [
        f for f in directory.iterdir() if f.is_file() and not f.name.startswith(".")
    ]

    def key(path: Path) -> tuple[str, float]:
        mtime = path.stat().st_mtime
        match = _HANDOFF_DATE_PREFIX_RE.match(path.name)
        date_str = (
            match.group(1)
            if match
            else datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%d")
        )
        return (date_str, mtime)

    return sorted(candidates, key=key, reverse=True)


def latest_labnotebook_time(driver, database: str) -> Optional[datetime]:
    """Return the creation time of the newest LabNotebookEntry, or None.

    Args:
        driver: Neo4j driver.
        database: Database name.

    Returns:
        Aware UTC datetime, or None when the project has no lab notebook
        entries.
    """
    with driver.session(database=database) as session:
        record = session.run(
            "MATCH (e:Artifact:LabNotebookEntry) "
            "RETURN max(e.created_at) AS newest"
        ).single()
    return _parse_iso(record["newest"]) if record else None


# ---------------------------------------------------------------------------
# Session window
# ---------------------------------------------------------------------------

#: How a window's start was decided. Reported so a reader can tell a real
#: boundary from the fallback.
WINDOW_SOURCE_LABNOTEBOOK = "labnotebook"
WINDOW_SOURCE_HANDOFF = "handoff"
WINDOW_SOURCE_FALLBACK = "fallback"


@dataclass(frozen=True)
class SessionWindow:
    """The half-open interval `[start, end)` a closeout reports on.

    Attributes:
        start: Beginning of the window (aware UTC).
        end: End of the window (aware UTC).
        source: Which marker decided `start` — one of the `WINDOW_SOURCE_*`
            constants.
        marker: Human-readable description of that marker.
    """

    start: datetime
    end: datetime
    source: str
    marker: str

    def contains(self, moment: Optional[datetime]) -> bool:
        """Return True when `moment` falls inside the window.

        Args:
            moment: Instant to test, or None.

        Returns:
            False for None, so an unreadable timestamp is never counted as
            in-window evidence.
        """
        if moment is None:
            return False
        return self.start <= moment < self.end


def session_window(
    project_dir: Path,
    settings: HandoffSettings,
    driver=None,
    database: Optional[str] = None,
    now: Optional[datetime] = None,
) -> SessionWindow:
    """Derive the window this session covers.

    The start is the newest LabNotebookEntry or the newest handoff file,
    whichever is later; with neither, it is `session_window_hours` before now.

    Args:
        project_dir: Project root.
        settings: Project handoff settings.
        driver: Neo4j driver, or None to skip the LabNotebookEntry marker.
        database: Database name; required when `driver` is given.
        now: End of the window; defaults to the current time.

    Returns:
        The derived window.
    """
    end = now or datetime.now(timezone.utc)
    candidates: list[tuple[datetime, str, str]] = []

    if driver is not None and database:
        entry_time = latest_labnotebook_time(driver, database)
        if entry_time is not None:
            candidates.append(
                (entry_time, WINDOW_SOURCE_LABNOTEBOOK, "newest LabNotebookEntry")
            )

    files = handoff_files(project_dir)
    if files:
        newest = files[0]
        candidates.append(
            (
                handoff_boundary(newest),
                WINDOW_SOURCE_HANDOFF,
                f"{HANDOFFS_DIR}/{newest.name}",
            )
        )

    if candidates:
        start, source, marker = max(candidates, key=lambda c: c[0])
        # A marker in the future (clock skew, a handoff dated ahead) would make
        # the window empty and the report silently blank. Fall back instead.
        if start < end:
            return SessionWindow(start=start, end=end, source=source, marker=marker)

    hours = settings.session_window_hours
    return SessionWindow(
        start=end - timedelta(hours=hours),
        end=end,
        source=WINDOW_SOURCE_FALLBACK,
        marker=f"last {hours:g}h (handoff.session_window_hours)",
    )


def previous_session_window(
    project_dir: Path,
    settings: HandoffSettings,
) -> Optional[SessionWindow]:
    """Derive the window the most recent handoff covered.

    Used by `seldon go` to report, at the next orient, a Desktop session that
    closed in violation of AD-030-R9. It reads only the filesystem, so it works
    without a graph connection.

    Args:
        project_dir: Project root.
        settings: Project handoff settings.

    Returns:
        The previous session's window, or None when no handoff exists.
    """
    files = handoff_files(project_dir)
    if not files:
        return None
    end = handoff_boundary(files[0])
    if len(files) > 1:
        start = handoff_boundary(files[1])
        source, marker = WINDOW_SOURCE_HANDOFF, f"{HANDOFFS_DIR}/{files[1].name}"
        if start >= end:
            start = end - timedelta(hours=settings.session_window_hours)
            source = WINDOW_SOURCE_FALLBACK
            marker = f"last {settings.session_window_hours:g}h"
    else:
        start = end - timedelta(hours=settings.session_window_hours)
        source = WINDOW_SOURCE_FALLBACK
        marker = f"last {settings.session_window_hours:g}h"
    return SessionWindow(start=start, end=end, source=source, marker=marker)


# ---------------------------------------------------------------------------
# Reading the window
# ---------------------------------------------------------------------------

def events_in_window(project_dir: Path, window: SessionWindow) -> list[dict]:
    """Return every event whose timestamp falls in the window, in append order.

    Args:
        project_dir: Project root holding the JSONL event log.
        window: The session window.

    Returns:
        Matching events.

    Raises:
        seldon.core.events.DuplicateEventError: If the log is corrupt.
    """
    return [
        e
        for e in read_events(Path(project_dir))
        if window.contains(_parse_iso(e.get("timestamp")))
    ]


def gated_task_ids(events: Iterable[dict]) -> list[str]:
    """Return ids of ResearchTasks a gated actor created in these events.

    This is the AD-030-R9 trigger: a session that filed tasks was a design session, whether or not
    it called itself one. Which actors count is AD-030-R11's allow-list of one — see
    :func:`actor_is_gated`.

    Args:
        events: Events already restricted to the window.

    Returns:
        Artifact ids, in event order.
    """
    ids: list[str] = []
    for event in events:
        if event.get("event_type") != "artifact_created":
            continue
        if not actor_is_gated(event.get("actor")):
            continue
        payload = event.get("payload") or {}
        if payload.get("artifact_type") != "ResearchTask":
            continue
        artifact_id = payload.get("artifact_id")
        if artifact_id:
            ids.append(artifact_id)
    return ids


def files_touched(
    project_dir: Path, window: SessionWindow, directories: Iterable[str]
) -> list[str]:
    """Return repo-relative paths under `directories` modified inside the window.

    Filesystem mtime is the only signal available for a file the graph does not
    yet know about, which is precisely the case AD-030-R9 tests: a design note
    written minutes ago and not yet ingested.

    Args:
        project_dir: Project root.
        window: The session window.
        directories: Repo-relative directories to scan, recursively.

    Returns:
        Sorted repo-relative paths.
    """
    root = Path(project_dir)
    found: list[str] = []
    for directory in directories:
        base = root / directory
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.name.startswith("."):
                continue
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            if window.contains(mtime):
                found.append(str(path.relative_to(root)))
    return sorted(found)


def design_notes_in_graph(
    project_dir: Path, window: SessionWindow, driver, database: str
) -> list[str]:
    """Return design notes the GRAPH holds that were written inside the window (AD-030-R7... R9).

    The stronger form of the check. A file's mtime says the bytes were touched; a Document or
    DesignNote node whose content hash matches the file on disk says the decision was actually
    ingested and is addressable — which is the whole obligation AD-030-R9 states. A note written
    and never ingested satisfies the letter of "a file appeared" and none of the point.

    Falls back to nothing (not to an error) when the project has no governed graph: the mtime
    check is still run alongside, and a project that has not adopted AD-030's ingest is not in
    violation of it.

    Args:
        project_dir: Project root.
        window: The session window.
        driver: Neo4j driver.
        database: Database name.

    Returns:
        Sorted repo-relative paths of design documents the graph holds whose file mtime falls in
        the window.
    """
    touched = set(files_touched(project_dir, window, [DESIGN_DIR]))
    if not touched or driver is None or not database:
        return []
    with driver.session(database=database) as session:
        records = session.run(
            "MATCH (d:Artifact) WHERE d.artifact_type IN ['Document', 'DesignNote', "
            "'ArchitecturalDecision'] AND d.path IN $paths RETURN DISTINCT d.path AS path",
            paths=sorted(touched),
        ).data()
    return sorted(r["path"] for r in records)


def design_notes_written(
    project_dir: Path,
    window: SessionWindow,
    driver=None,
    database: Optional[str] = None,
) -> list[str]:
    """Return the design notes that discharge AD-030-R9 for this window.

    Two readings of "wrote a design note", and the obligation is discharged by either:

    * a file under `docs/design/` was created or modified in the window — the filesystem form,
      which works before the governed graph exists and in a project that never adopts it;
    * the graph holds a Document, DesignNote or ArchitecturalDecision at that path — the node
      form AD-030's ingest makes possible, and the stronger of the two.

    The node check is not made the *only* check, because that would fail a session that wrote a
    note correctly and closed before the pre-commit ingest ran — punishing the right behaviour for
    the timing of a hook.

    Args:
        project_dir: Project root.
        window: The session window.
        driver: Neo4j driver, or None to run the filesystem form alone.
        database: Database name; required when `driver` is given.

    Returns:
        Sorted repo-relative paths under `docs/design/`.
    """
    from_disk = files_touched(project_dir, window, [DESIGN_DIR])
    if driver is None or not database:
        return from_disk
    in_graph = design_notes_in_graph(project_dir, window, driver, database)
    return sorted(set(from_disk) | set(in_graph))


@dataclass(frozen=True)
class R9Verdict:
    """Outcome of the AD-030-R9 design-note check.

    Attributes:
        violated: True when Desktop filed tasks and wrote no design note.
        gated_task_ids: Ids of the tasks a gated actor created in the window.
        design_notes: Design-note files found in the window.
    """

    violated: bool
    gated_task_ids: tuple[str, ...] = ()
    design_notes: tuple[str, ...] = ()


def check_r9(
    project_dir: Path,
    window: SessionWindow,
    events: Iterable[dict],
    driver=None,
    database: Optional[str] = None,
) -> R9Verdict:
    """Evaluate AD-030-R9 over one window.

    The rule fires only when both halves hold: Desktop created at least one
    ResearchTask, and no design note was written. A Desktop session that filed
    nothing was not a design session; one that wrote a note discharged the
    obligation. See :func:`design_notes_written` for what counts as writing one.

    Args:
        project_dir: Project root.
        window: The session window.
        events: Events already restricted to that window.
        driver: Neo4j driver, so the graph form of the note check can run.
        database: Database name; required when `driver` is given.

    Returns:
        The verdict, carrying the evidence on both sides.
    """
    task_ids = gated_task_ids(events)
    notes = design_notes_written(project_dir, window, driver, database)
    return R9Verdict(
        violated=bool(task_ids) and not notes,
        gated_task_ids=tuple(task_ids),
        design_notes=tuple(notes),
    )


# ---------------------------------------------------------------------------
# Graph reads
# ---------------------------------------------------------------------------

def short(artifact_id: str) -> str:
    """Return the eight-character form every Seldon surface prints.

    Args:
        artifact_id: Full artifact_id.

    Returns:
        The first eight characters.
    """
    return artifact_id[:8]


@dataclass
class GraphChange:
    """One task-lifecycle change inside the window.

    Attributes:
        kind: `created`, `closed`, `withdrawn` or `superseded`.
        artifact_id: Full artifact_id.
        state: The task's state after the change.
        description: Task description, read from the graph when available.
        actor: Actor that wrote the event.
    """

    kind: str
    artifact_id: str
    state: str = ""
    description: str = ""
    actor: str = ""


def _task_properties(driver, database: str, ids: Iterable[str]) -> dict[str, dict]:
    """Read description and state for the given ResearchTasks.

    Args:
        driver: Neo4j driver.
        database: Database name.
        ids: Artifact ids to look up.

    Returns:
        Mapping of artifact_id to `{"description": ..., "state": ...}`. Ids
        absent from the graph are omitted.
    """
    id_list = [i for i in ids if i]
    if not id_list:
        return {}
    with driver.session(database=database) as session:
        records = session.run(
            "MATCH (t:Artifact:ResearchTask) WHERE t.artifact_id IN $ids "
            "RETURN t.artifact_id AS id, t.description AS description, "
            "t.state AS state",
            ids=id_list,
        ).data()
    return {
        r["id"]: {
            "description": r.get("description") or "",
            "state": r.get("state") or "",
        }
        for r in records
    }


def graph_changes(
    events: Iterable[dict], driver=None, database: Optional[str] = None
) -> list[GraphChange]:
    """Summarise the task lifecycle changes recorded in the window.

    Reads the event log rather than the graph so a task created and then closed
    inside one window reports both facts, which a snapshot of current state
    cannot show.

    Args:
        events: Events already restricted to the window.
        driver: Neo4j driver, or None to omit descriptions.
        database: Database name; required when `driver` is given.

    Returns:
        Changes in event order.
    """
    changes: list[GraphChange] = []
    for event in events:
        payload = event.get("payload") or {}
        event_type = event.get("event_type")
        if event_type == "artifact_created":
            if payload.get("artifact_type") != "ResearchTask":
                continue
            changes.append(
                GraphChange(
                    kind="created",
                    artifact_id=payload.get("artifact_id", ""),
                    state=payload.get("to_state", "") or "",
                    description=(payload.get("properties") or {}).get(
                        "description", ""
                    ),
                    actor=event.get("actor", "") or "",
                )
            )
        elif event_type == "artifact_state_changed":
            to_state = payload.get("to_state") or ""
            if to_state in CLOSED_STATES:
                kind = "closed"
            elif to_state == WITHDRAWN_STATE:
                kind = WITHDRAWN_STATE
            elif to_state == SUPERSEDED_STATE:
                kind = SUPERSEDED_STATE
            else:
                continue
            changes.append(
                GraphChange(
                    kind=kind,
                    artifact_id=payload.get("artifact_id", ""),
                    state=to_state,
                    actor=event.get("actor", "") or "",
                )
            )

    if driver is not None and database:
        props = _task_properties(
            driver, database, [c.artifact_id for c in changes if not c.description]
        )
        for change in changes:
            if not change.description:
                change.description = props.get(change.artifact_id, {}).get(
                    "description", ""
                )
        # A state change reported here must name a ResearchTask; anything else
        # is another artifact type sharing the event stream.
        known = set(props) | {c.artifact_id for c in changes if c.kind == "created"}
        changes = [c for c in changes if c.artifact_id in known]

    return changes


@dataclass
class OpenTask:
    """One open ResearchTask, as rendered in the handoff.

    Attributes:
        artifact_id: Full artifact_id.
        state: Current state.
        description: Task description.
        ready: True when no unsatisfied predecessor blocks it (AD-029).
    """

    artifact_id: str
    state: str
    description: str
    ready: bool


def open_tasks(driver, database: str, domain_config) -> list[OpenTask]:
    """Return open tasks with ready ones first (AD-029 ordering).

    Args:
        driver: Neo4j driver.
        database: Database name.
        domain_config: Loaded domain configuration, for the open-state set.

    Returns:
        Open tasks: ready ones in creation order, then the blocked ones.
    """
    from seldon.core.artifacts import open_states
    from seldon.core.precedence import precedence_view

    open_set = set(open_states(domain_config, "ResearchTask"))
    with driver.session(database=database) as session:
        view = precedence_view(session, open_set)

    states = view["states"]
    descriptions = view["descriptions"]
    rank = view["rank"]
    ready = list(view["ready"])
    ready_set = set(ready)

    blocked = sorted(
        (t for t in states if states[t] in open_set and t not in ready_set),
        key=lambda t: rank.get(t, len(rank)),
    )

    return [
        OpenTask(
            artifact_id=tid,
            state=states.get(tid, "?"),
            description=descriptions.get(tid) or "",
            ready=tid in ready_set,
        )
        for tid in [*ready, *blocked]
    ]


# ---------------------------------------------------------------------------
# CC dispatch
# ---------------------------------------------------------------------------

#: Rendered when no registered CC task in the window is still awaiting
#: execution. The reason follows on the next line — a bare "none" leaves the
#: next thread unable to tell "nothing was filed" from "everything already ran".
NO_DISPATCH = "No CC task ready"


def registered_cc_tasks(
    events: Iterable[dict], driver=None, database: Optional[str] = None
) -> tuple[list[str], str]:
    """Return the CC task files registered in the window and still `proposed`.

    Args:
        events: Events already restricted to the window.
        driver: Neo4j driver, or None to skip the state filter.
        database: Database name; required when `driver` is given.

    Returns:
        `(paths, reason)` — repo-relative task-file paths in registration order,
        and, when that list is empty, why it is empty.
    """
    registered: list[tuple[str, str]] = []
    for event in events:
        if event.get("event_type") != "artifact_created":
            continue
        payload = event.get("payload") or {}
        if payload.get("artifact_type") != "ResearchTask":
            continue
        source_file = (payload.get("properties") or {}).get("source_file") or ""
        if not source_file.startswith("cc_tasks/"):
            continue
        artifact_id = payload.get("artifact_id", "")
        if artifact_id:
            registered.append((artifact_id, source_file))

    if not registered:
        return [], "no CC task file was registered in this session window"

    if driver is None or not database:
        return [path for _, path in registered], ""

    props = _task_properties(driver, database, [aid for aid, _ in registered])
    still_proposed = [
        path
        for aid, path in registered
        if props.get(aid, {}).get("state") == "proposed"
    ]
    if not still_proposed:
        return [], (
            f"{len(registered)} CC task file(s) were registered in this window, "
            "and none is still in `proposed` — they have already been started "
            "or closed"
        )
    return still_proposed, ""


def dispatch_block(paths: Iterable[str], reason: str) -> str:
    """Render the CC dispatch block.

    Args:
        paths: Repo-relative CC task file paths, in execution order.
        reason: Why the list is empty; used only when `paths` is empty.

    Returns:
        One dispatch line per task, or `NO_DISPATCH` and the reason.
    """
    lines = [
        f"Read CLAUDE.md, then execute {path}. "
        "Glob and read all sibling *ADDENDUM*.md first."
        for path in paths
    ]
    if lines:
        return "\n".join(lines)
    return f"{NO_DISPATCH} — {reason}." if reason else NO_DISPATCH


def resume_block(handoff_path: Path, next_action: str) -> str:
    """Render the resume block the next Desktop thread opens with.

    The wording is fixed: it is pasted verbatim into a fresh thread that has no
    other context, so every clause in it is load-bearing.

    Args:
        handoff_path: Path to the handoff document; rendered absolute.
        next_action: The first action for the next session (`--next`).

    Returns:
        The three-line block, without fencing.
    """
    return (
        f"seldon go --brief {Path(handoff_path).resolve()}\n"
        "Read the handoff in full. Verify listed task IDs against the graph "
        "before acting.\n"
        f"First action: {next_action}"
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

@dataclass
class HandoffDocument:
    """A rendered handoff and the two blocks the caller echoes back.

    Attributes:
        path: Where the document was (or will be) written.
        text: Full markdown of the document.
        resume: The resume block, unfenced.
        dispatch: The CC dispatch block, unfenced.
        window: The window the document reports on.
        r9: The AD-030-R9 verdict for that window.
        warnings: Non-fatal notices to print alongside the result.
    """

    path: Path
    text: str
    resume: str
    dispatch: str
    window: SessionWindow
    r9: R9Verdict
    warnings: list[str] = field(default_factory=list)


def _render_changes(changes: list[GraphChange]) -> list[str]:
    """Render the Graph changes section body.

    Args:
        changes: Lifecycle changes in the window.

    Returns:
        Markdown lines.
    """
    if not changes:
        return ["- *(no task lifecycle changes in this window)*"]
    lines = []
    for change in changes:
        desc = change.description.strip().replace("\n", " ")
        if len(desc) > 120:
            desc = desc[:117] + "..."
        state = f" [{change.state}]" if change.state else ""
        actor = f" ({change.actor})" if change.actor else ""
        suffix = f" — {desc}" if desc else ""
        lines.append(
            f"- {change.kind}: `{short(change.artifact_id)}`{state}{actor}{suffix}"
        )
    return lines


def _render_open_tasks(tasks: list[OpenTask]) -> list[str]:
    """Render the Open tasks section body, ready tasks first.

    Args:
        tasks: Open tasks, already ordered.

    Returns:
        Markdown lines. The `▸` marker matches `seldon task list`.
    """
    if not tasks:
        return ["- *(no open tasks)*"]
    lines = []
    for task in tasks:
        marker = "▸ " if task.ready else "  "
        desc = (task.description or "").strip().replace("\n", " ")
        if len(desc) > 120:
            desc = desc[:117] + "..."
        lines.append(f"- {marker}`{short(task.artifact_id)}` [{task.state}] {desc}")
    return lines


def render_handoff(
    *,
    path: Path,
    slug: str,
    summary: str,
    next_action: str,
    window: SessionWindow,
    changes: list[GraphChange],
    files: list[str],
    tasks: list[OpenTask],
    dispatch: str,
    prior_handoff: Optional[str],
    date: str,
) -> str:
    """Render the handoff document.

    Headings follow the format already in `handoffs/`, so a reader (and
    `seldon go`, which pastes the newest handoff into its orientation context)
    sees one shape across hand-written and generated documents.

    Args:
        path: Where the document will live; used to build the resume block.
        slug: Slug from `--slug`, used in the title.
        summary: One-line summary from `--summary`.
        next_action: First action for the next session, from `--next`.
        window: The window reported on.
        changes: Task lifecycle changes in the window.
        files: Repo-relative governed files touched in the window.
        tasks: Open tasks, ready first.
        dispatch: Rendered CC dispatch block.
        prior_handoff: Repo-relative path of the previous handoff, or None.
        date: `YYYY-MM-DD` session date.

    Returns:
        The full markdown document.
    """
    title = slug.replace("-", " ").replace("_", " ")
    lines: list[str] = [
        f"# Handoff: {date} {title}",
        "",
        f"**Date:** {date}",
        "**From:** Desktop session",
        "**To:** Next Desktop session",
        f"**Prior handoff:** {f'`{prior_handoff}`' if prior_handoff else '*(none)*'}",
        f"**Session window:** {window.start.isoformat()} → {window.end.isoformat()} "
        f"(from {window.marker})",
        "",
        "*Generated by `seldon handoff` from graph, event log and filesystem "
        "state. Only the summary and the first action are authored (AD-030-R2).*",
        "",
        "---",
        "",
        "## One line",
        "",
        summary,
        "",
        "## Graph changes",
        "",
        *_render_changes(changes),
        "",
        "## Files written",
        "",
    ]
    if files:
        lines.extend(f"- `{f}`" for f in files)
    else:
        lines.append("- *(no governed files touched in this window)*")
    lines.extend(
        [
            "",
            "## Open tasks",
            "",
            *_render_open_tasks(tasks),
            "",
            "## Resume line (copy/paste to open the next Desktop thread)",
            "",
            "```",
            resume_block(path, next_action),
            "```",
            "",
            "## CC dispatch text (Seldon Claude Code window, run in this order)",
            "",
            "```",
            dispatch,
            "```",
            "",
        ]
    )
    return "\n".join(lines)


class R9Violation(Exception):
    """Raised when AD-030-R9 refuses a close.

    Attributes:
        verdict: The evidence behind the refusal.
    """

    def __init__(self, verdict: R9Verdict):
        super().__init__(R9_MESSAGE)
        self.verdict = verdict


def build_handoff(
    *,
    project_dir: Path,
    config: dict,
    driver,
    database: str,
    domain_config,
    slug: str,
    summary: str,
    next_action: str,
    now: Optional[datetime] = None,
) -> HandoffDocument:
    """Assemble the handoff document for the current session.

    Args:
        project_dir: Project root.
        config: Parsed seldon.yaml.
        driver: Neo4j driver.
        database: Database name.
        domain_config: Loaded domain configuration.
        slug: Filename slug.
        summary: One-line summary.
        next_action: First action for the next session.
        now: End of the session window; defaults to the current time.

    Returns:
        The rendered document, not yet written to disk.

    Raises:
        R9Violation: When the window violates AD-030-R9 and
            `handoff.require_design_note` is true.
        ValueError: If the `handoff` config block is malformed.
    """
    project_dir = Path(project_dir)
    settings = handoff_settings(config)
    end = now or datetime.now(timezone.utc)
    window = session_window(project_dir, settings, driver, database, now=end)
    events = events_in_window(project_dir, window)

    verdict = check_r9(project_dir, window, events, driver, database)
    warnings: list[str] = []
    if verdict.violated:
        if settings.require_design_note:
            raise R9Violation(verdict)
        warnings.append(
            f"WARNING: {R9_MESSAGE} "
            "(handoff.require_design_note is false, so this is a warning.)"
        )

    changes = graph_changes(events, driver, database)
    files = files_touched(project_dir, window, REPORTED_DIRS)
    tasks = open_tasks(driver, database, domain_config)
    paths, reason = registered_cc_tasks(events, driver, database)
    dispatch = dispatch_block(paths, reason)

    existing = handoff_files(project_dir)
    prior = f"{HANDOFFS_DIR}/{existing[0].name}" if existing else None

    date = end.strftime("%Y-%m-%d")
    path = project_dir / HANDOFFS_DIR / f"{date}_{slug}.md"

    text = render_handoff(
        path=path,
        slug=slug,
        summary=summary,
        next_action=next_action,
        window=window,
        changes=changes,
        files=files,
        tasks=tasks,
        dispatch=dispatch,
        prior_handoff=prior,
        date=date,
    )

    return HandoffDocument(
        path=path,
        text=text,
        resume=resume_block(path, next_action),
        dispatch=dispatch,
        window=window,
        r9=verdict,
        warnings=warnings,
    )


def write_handoff(document: HandoffDocument, force: bool = False) -> Path:
    """Write a rendered handoff to disk.

    Args:
        document: The rendered document.
        force: Overwrite an existing file at the same path.

    Returns:
        The path written.

    Raises:
        FileExistsError: If the path exists and `force` is false. A handoff is
            a session record; silently replacing one destroys the record of a
            session that actually happened.
    """
    path = document.path
    if path.exists() and not force:
        raise FileExistsError(
            f"{path} already exists. Choose another --slug, or pass --force to "
            "replace this session record."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document.text, encoding="utf-8")
    return path
