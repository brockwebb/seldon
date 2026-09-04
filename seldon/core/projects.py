"""Discovery of Seldon projects on this machine.

Seldon has no cross-project registry — every project is a directory holding a
`seldon.yaml` that names its own Neo4j database. A fleet-wide audit therefore
needs a way to enumerate projects, and it must do so **without hardcoding
anybody's home directory** (engineering standards §2).

Resolution order for the roots to scan, first match wins:

1. Explicit ``--project-dir`` arguments — no scanning at all.
2. Explicit ``--roots`` arguments.
3. The ``SELDON_PROJECT_ROOTS`` environment variable, ``os.pathsep``-separated.
4. Nothing: the caller is told to supply roots, and falls back to the current
   project. A fleet audit that silently examined one project would be worse
   than one that says it found no roots.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

#: Environment variable naming the directories to scan for projects.
PROJECT_ROOTS_ENV_VAR = "SELDON_PROJECT_ROOTS"

#: How deep below a root to look for `seldon.yaml`. Projects live one or two
#: levels down (``<root>/<repo>`` and ``<root>/<repo>/<subrepo>``); going deeper
#: mostly walks build output.
DEFAULT_SCAN_DEPTH = 3

#: Directory names never descended into during a scan.
SKIP_DIRS = frozenset(
    {
        ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
        ".tox", ".mypy_cache", ".pytest_cache", "site-packages", ".claude",
        "build", "dist", ".quarto", "_site",
    }
)


@dataclass
class ProjectRef:
    """A discovered Seldon project.

    Attributes:
        path: Project root (the directory holding `seldon.yaml`).
        name: ``project.name`` from the config, or the directory name.
        database: ``neo4j.database`` from the config, or None if unset.
        config_error: Populated when `seldon.yaml` could not be parsed.
        not_a_project: Set when the file parsed but is not a Seldon project
            config at all — see `load_project_ref`. Distinct from
            `config_error`, which means a *Seldon* config that is broken.
    """

    path: Path
    name: str
    database: Optional[str]
    config_error: Optional[str] = None
    not_a_project: Optional[str] = None

    @property
    def event_log(self) -> Path:
        """Path to this project's JSONL event log (may not exist)."""
        from seldon.core.events import EVENTS_FILENAME

        return self.path / EVENTS_FILENAME


def roots_from_env(env: Optional[dict] = None) -> List[Path]:
    """Read scan roots from :data:`PROJECT_ROOTS_ENV_VAR`.

    Args:
        env: Mapping to read from. Defaults to ``os.environ``.

    Returns:
        Existing directories named by the variable, in order. Entries that do
        not exist are dropped — a stale entry in a shell profile should not
        abort a fleet audit.
    """
    env = os.environ if env is None else env
    raw = env.get(PROJECT_ROOTS_ENV_VAR) or ""
    out: List[Path] = []
    for part in raw.split(os.pathsep):
        part = part.strip()
        if not part:
            continue
        p = Path(part).expanduser()
        if p.is_dir():
            out.append(p)
    return out


def find_projects(roots: Iterable[Path], depth: int = DEFAULT_SCAN_DEPTH) -> List[ProjectRef]:
    """Scan ``roots`` for directories containing `seldon.yaml`.

    Args:
        roots: Directories to scan.
        depth: Maximum directory levels below each root to descend.

    Returns:
        Discovered projects, de-duplicated by resolved path and sorted by path.
        A directory that holds a `seldon.yaml` is not descended into further —
        a project's own subdirectories are part of that project.
    """
    seen: Dict[Path, ProjectRef] = {}

    def walk(directory: Path, level: int) -> None:
        if level > depth:
            return
        if (directory / "seldon.yaml").is_file():
            ref = load_project_ref(directory)
            seen.setdefault(ref.path, ref)
            return
        try:
            entries = sorted(directory.iterdir())
        except (PermissionError, OSError):
            return
        for entry in entries:
            if entry.name in SKIP_DIRS or entry.name.startswith("."):
                continue
            if entry.is_symlink():
                # A symlinked tree is reachable by its real path; following it
                # would double-report every project under a linked root.
                continue
            if entry.is_dir():
                walk(entry, level + 1)

    for root in roots:
        root = Path(root).expanduser()
        if root.is_dir():
            walk(root, 0)

    return [seen[p] for p in sorted(seen)]


def load_project_ref(project_dir: Path) -> ProjectRef:
    """Build a :class:`ProjectRef` from a directory holding `seldon.yaml`.

    Args:
        project_dir: Directory containing `seldon.yaml`.

    Returns:
        The reference. A config that cannot be parsed yields a ref with
        ``config_error`` set rather than raising — a fleet audit must report a
        broken project, not stop at it.
    """
    import yaml

    path = Path(project_dir).resolve()
    try:
        with open(path / "seldon.yaml") as f:
            config = yaml.safe_load(f) or {}
    except Exception as exc:
        return ProjectRef(
            path=path, name=path.name, database=None,
            config_error=f"{type(exc).__name__}: {exc}",
        )

    project = config.get("project") or {}
    neo4j = config.get("neo4j") or {}

    # `seldon.yaml` is not a reserved filename. `webdesktop/services/seldon.yaml`
    # is a *service definition* for a service that happens to be named "seldon"
    # (keys: name, subdomain, port, start_command) — matching on filename alone
    # put it in the fleet inventory as a project with no database. Harmless in a
    # read-only survey; not harmless for anything that iterates the inventory and
    # acts. A Seldon project config always carries a `project` or `neo4j`
    # mapping, so require at least one rather than trusting the name.
    if not isinstance(project, dict) or not isinstance(neo4j, dict):
        return ProjectRef(
            path=path, name=path.name, database=None,
            config_error="seldon.yaml: 'project'/'neo4j' must be mappings",
        )
    if not project and not neo4j:
        return ProjectRef(
            path=path, name=path.name, database=None,
            not_a_project=(
                "seldon.yaml has neither a 'project' nor a 'neo4j' section — "
                "not a Seldon project config"
            ),
        )

    return ProjectRef(
        path=path,
        name=project.get("name") or path.name,
        database=neo4j.get("database"),
    )


def resolve_projects(
    project_dirs: Iterable[str] = (),
    roots: Iterable[str] = (),
    depth: int = DEFAULT_SCAN_DEPTH,
    env: Optional[dict] = None,
) -> tuple[List[ProjectRef], List[str]]:
    """Resolve the project set for a fleet-wide command.

    Args:
        project_dirs: Explicit project roots. When any are given, no scan runs.
        roots: Directories to scan for projects.
        depth: Maximum scan depth below each root.
        env: Mapping to read :data:`PROJECT_ROOTS_ENV_VAR` from.

    Returns:
        ``(projects, notes)`` — the discovered projects and human-readable notes
        explaining how they were resolved, so a report can state its own scope
        instead of leaving the reader to guess it.
    """
    notes: List[str] = []

    explicit = [Path(p).expanduser() for p in project_dirs]
    if explicit:
        refs = [load_project_ref(p) for p in explicit if (Path(p) / "seldon.yaml").is_file()]
        missing = [str(p) for p in explicit if not (Path(p) / "seldon.yaml").is_file()]
        for m in missing:
            notes.append(f"no seldon.yaml in {m} — skipped")
        notes.append(f"scope: {len(refs)} explicitly named project(s)")
        return refs, notes

    scan_roots = [Path(r).expanduser() for r in roots]
    if scan_roots:
        notes.append("scope: --roots " + ", ".join(str(r) for r in scan_roots))
    else:
        scan_roots = roots_from_env(env)
        if scan_roots:
            notes.append(
                f"scope: ${PROJECT_ROOTS_ENV_VAR} = "
                + ", ".join(str(r) for r in scan_roots)
            )

    if not scan_roots:
        notes.append(
            f"no roots given: pass --roots, or set ${PROJECT_ROOTS_ENV_VAR}. "
            f"Falling back to the current project only."
        )
        cwd = Path.cwd()
        if (cwd / "seldon.yaml").is_file():
            return [load_project_ref(cwd)], notes
        return [], notes

    refs = find_projects(scan_roots, depth=depth)
    notes.append(f"found {len(refs)} project(s) at depth <= {depth}")
    return refs, notes
