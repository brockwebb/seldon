"""CC task completion tracking — seldon cc complete."""
from __future__ import annotations

import hashlib
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import click

from seldon.config import load_project_config, get_neo4j_driver, get_current_session
from seldon.core.artifacts import create_artifact, update_artifact, walk_to_completed
from seldon.domain.loader import load_domain_config


def _file_hash(path: Path) -> str:
    """Compute SHA-256 of file content."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


# Where the immutable SPEC ends and the append-only region begins.
#
# A task file has three lifecycles and only one is immutable:
#   spec     — the agreement, frozen at registration; this is what the hash guards
#   ruling   — new INPUT arriving after registration (deciding an already-posed
#              question is not a goalpost move)
#   findings — OUTPUT; cannot be part of the agreement, it does not exist yet
#
# Preferred terminator is the explicit marker; failing that, the first RULING /
# Findings / ADDENDUM heading. Heading match is tolerant of level, case and
# suffixes ("## Findings (2026-07-16, CC)").
_SPEC_END_MARKER_RE = re.compile(r"^\s{0,3}<!--\s*SPEC\s+END\s*-->", re.IGNORECASE)
_APPEND_HEADING_RE = re.compile(
    r"^\s{0,3}#{1,6}\s*(findings|ruling|addendum)\b", re.IGNORECASE
)

# Marks artifacts whose file_hash covers the SPEC ONLY (everything above the
# first Findings heading). Absent on artifacts registered before this scope
# existed — those carry a whole-file hash and are handled as legacy below.
HASH_SCOPE_SPEC = "spec"


def _split_spec(text: str) -> tuple[str, bool]:
    """Split task-file text at the end of the immutable spec region.

    Returns ``(spec_text, had_terminator)``. ``spec_text`` is everything ABOVE
    the terminator, right-stripped so trailing blank lines before it do not
    perturb the hash.

    An explicit ``<!-- SPEC END -->`` marker wins if present, so a task can put
    the boundary exactly where it wants; otherwise the first RULING / Findings /
    ADDENDUM heading terminates the spec.

    Why this exists: every task file in this project ends with "append findings
    under ## Findings", so hashing the whole file guarantees that a *correctly
    executed* task is hash-divergent by the time it is completed, and the
    sanctioned completion path can never succeed. Hashing the spec keeps the
    real invariant — **the spec is immutable, the append region is additive** —
    enforced, instead of abandoning enforcement to make completion possible.
    """
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if _SPEC_END_MARKER_RE.match(line):
            return "".join(lines[:i]).rstrip(), True
    for i, line in enumerate(lines):
        if _APPEND_HEADING_RE.match(line):
            return "".join(lines[:i]).rstrip(), True
    return text.rstrip(), False


def _spec_hash(path: Path) -> str:
    """SHA-256 of the task file's SPEC section (above the first Findings heading).

    Appending findings does not change this value; editing the spec does.
    """
    text = path.read_text(encoding="utf-8", errors="surrogateescape")
    spec, _ = _split_spec(text)
    return hashlib.sha256(spec.encode("utf-8", errors="surrogateescape")).hexdigest()


def _get_domain_config(config: dict):
    domain_name = config["project"].get("domain", "research")
    domain_yaml = Path(__file__).parent.parent / "domain" / f"{domain_name}.yaml"
    return load_domain_config(domain_yaml)


def _name_from_filepath(filepath: str) -> str:
    """Derive a human-readable name from a CC task filename.

    Strips date prefix (YYYY-MM-DD_), replaces underscores with spaces, drops .md.
    E.g. "cc_tasks/2026-04-03_some_task.md" → "some task"
    """
    stem = Path(filepath).stem  # drop .md
    # Strip leading date prefix YYYY-MM-DD_
    stem = re.sub(r"^\d{4}-\d{2}-\d{2}_", "", stem)
    return stem.replace("_", " ")


# Structural match for any metadata-style line: optional `**`, a capitalized key
# (words, spaces, `_`, `-`), a colon, optional closing `**`, then whitespace or
# end-of-string. Intentionally key-agnostic so new metadata keys (Location,
# Severity, Owner, Depends on, Estimate, …) are recognized without maintenance.
_METADATA_RE = re.compile(
    r"^\*?\*?[A-Z][A-Za-z0-9 _-]{0,40}:\*?\*?(\s|$)",
)

# A line that is entirely bold (`**...**`) is a callout or banner, never the
# task's subject. The canonical offender is the immutability banner every task
# file carries; it survives _METADATA_RE because its first sentence ends in `.`
# rather than `:`, so it needs its own rule.
_BOLD_ONLY_RE = re.compile(r"^\*\*\s*\S.*\S\s*\*\*$")

# ATX H1 (`# <title>`). A markdown header is a single physical line by
# construction, so a title-based description is immune to the hard-wrap
# fragmenting that let prose extraction capture a mid-sentence metadata
# continuation line as the "description".
_H1_RE = re.compile(r"^#\s+(.+?)\s*$")

# Boilerplate that may precede the subject in a task-file H1:
#   "CC Task: <subject>"        "Task: <subject>"
#   "CC Task T4: <subject>"     "CC Task — <subject>"
# The separator may be a colon, an em dash, an en dash, or a hyphen. Only the
# separator forms are stripped; "Task list overhaul" is a title, not boilerplate
# plus a subject, because nothing separates a prefix from a subject there.
_TITLE_BOILERPLATE_RE = re.compile(
    r"^(?:CC\s+)?Task(?:\s+[\w.-]+)?\s*[:—–-]\s*(.+)$", re.IGNORECASE
)

# An H1 that is *only* the boilerplate ("# CC Task", "# Task T4:") names no
# subject, so it must not become the description — fall through to prose.
_TITLE_BOILERPLATE_ONLY_RE = re.compile(
    r"^(?:CC\s+)?Task(?:\s+[\w.-]+)?\s*[:—–-]?\s*$", re.IGNORECASE
)


def _subject_from_h1(title: str) -> str:
    """Reduce an H1's text to the task subject.

    Strips a leading ``CC Task`` / ``Task`` prefix (with an optional task id and
    a colon, em dash, en dash or hyphen separator). A title carrying no such
    prefix is already the subject and is returned unchanged.

    Args:
        title: Text of the H1, with the leading ``#`` and surrounding whitespace
            already removed.

    Returns:
        The subject, or an empty string when the title is pure boilerplate and
        names no subject.
    """
    title = title.strip()
    if _TITLE_BOILERPLATE_ONLY_RE.match(title):
        return ""
    match = _TITLE_BOILERPLATE_RE.match(title)
    if match:
        return match.group(1).strip()
    return title


def _description_looks_like_metadata(text: str) -> bool:
    """Return True if text still looks like metadata or a banner, not a description.

    Used as a defensive second layer after extraction — if the chosen
    description matches the metadata pattern or is an all-bold banner line,
    emit a warning so the user knows auto-extraction went wrong.

    Args:
        text: The extracted description.

    Returns:
        True when the text should be treated as a failed extraction.
    """
    if not text:
        return False
    return bool(_METADATA_RE.match(text)) or bool(_BOLD_ONLY_RE.match(text))


#: How a description was obtained. Callers use this to decide whether the
#: "looks like metadata" warning is meaningful: a colon inside an authored H1
#: title ("Defect sweep: registry contract") is ordinary punctuation, while the
#: same shape found in the body is very likely a metadata key.
DESCRIPTION_SOURCE_TITLE = "h1"
DESCRIPTION_SOURCE_PROSE = "prose"
DESCRIPTION_SOURCE_FILENAME = "filename"


def _extract_description_with_source(filepath: Path) -> tuple[str, str]:
    """Extract a description and report which strategy produced it.

    Strategy, in order:
      1. The first H1's subject — the title with any ``CC Task`` / ``Task``
         boilerplate prefix stripped (see :func:`_subject_from_h1`). The title
         is where a task file states what it is about, and an H1 is a single
         physical line, so this is immune to the hard-wrap fragmenting that
         made prose extraction capture half a sentence. An H1 that is nothing
         but boilerplate names no subject and does not win.
      2. Otherwise, the first substantive PARAGRAPH — consecutive prose lines
         joined — skipping headers, horizontal rules, whole metadata blocks
         (a metadata line AND its hard-wrapped continuation lines), and
         all-bold banner paragraphs such as the immutability notice.
      3. Otherwise, the filename.

    Args:
        filepath: Path to the CC task markdown file.

    Returns:
        ``(description, source)`` where description is truncated to 200
        characters and source is one of :data:`DESCRIPTION_SOURCE_TITLE`,
        :data:`DESCRIPTION_SOURCE_PROSE`, :data:`DESCRIPTION_SOURCE_FILENAME`.

    Raises:
        OSError: If the file cannot be read.
    """
    lines = filepath.read_text().splitlines()

    # 1. Prefer the first H1's subject.
    for line in lines:
        h1 = _H1_RE.match(line.strip())
        if h1:
            subject = _subject_from_h1(h1.group(1))
            if subject:
                return subject[:200], DESCRIPTION_SOURCE_TITLE
            break  # H1 carries no subject → fall through to prose

    # 2. First substantive paragraph, metadata- and banner-aware.
    i, n = 0, len(lines)
    while i < n:
        stripped = lines[i].strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("---"):
            i += 1
            continue
        if _METADATA_RE.match(stripped):
            # Skip the whole metadata value, including hard-wrapped
            # continuation lines, up to the next blank line — otherwise the
            # second physical line of a wrapped **Priority:** becomes the
            # "description" (the original fragment bug).
            i += 1
            while i < n and lines[i].strip():
                i += 1
            continue
        # Candidate prose — collect the wrapped paragraph whole.
        para: list[str] = []
        while i < n:
            t = lines[i].strip()
            if not t or t.startswith("#") or t.startswith("---"):
                break
            para.append(t)
            i += 1
        joined = " ".join(para)
        if _BOLD_ONLY_RE.match(joined):
            # An all-bold paragraph is a banner (e.g. the immutability notice),
            # not the task subject. Keep looking.
            continue
        return joined[:200], DESCRIPTION_SOURCE_PROSE

    return filepath.name, DESCRIPTION_SOURCE_FILENAME


def _extract_description(filepath: Path) -> str:
    """Extract a one-line description from a CC task file.

    Thin wrapper over :func:`_extract_description_with_source` for callers that
    do not care how the description was obtained.

    Args:
        filepath: Path to the CC task markdown file.

    Returns:
        The extracted description, truncated to 200 characters.

    Raises:
        OSError: If the file cannot be read.
    """
    return _extract_description_with_source(filepath)[0]


def _warn_if_description_suspicious(
    filepath: Path,
    description: str,
    source: str = DESCRIPTION_SOURCE_PROSE,
) -> None:
    """Warn on stderr when an auto-extracted description looks wrong.

    A description taken from an authored H1 title is never flagged for metadata
    shape — a colon in a title is punctuation, not a metadata key — but a
    fallback to the filename is always flagged.

    Args:
        filepath: The task file the description came from.
        description: The extracted description.
        source: Which strategy produced it; see ``DESCRIPTION_SOURCE_*``.

    Returns:
        None. This never fails the registration.
    """
    if source == DESCRIPTION_SOURCE_FILENAME:
        looks_bad = True
    elif source == DESCRIPTION_SOURCE_TITLE:
        looks_bad = False
    else:
        looks_bad = _description_looks_like_metadata(description)
    if not looks_bad:
        return
    click.echo(
        "WARNING: extracted description may be metadata, not task description.\n"
        f"  File: {filepath}\n"
        f'  Extracted: "{description[:60]}..."\n'
        "  Consider adding a description section or using --description to override.",
        err=True,
    )


# ---------------------------------------------------------------------------
# Git tracking guard
# ---------------------------------------------------------------------------
#
# Why this exists: 37 of the 50 ResearchTasks in this project's own graph that
# name a source_file point at a file that is on neither disk nor any branch,
# because `cc_tasks/` was gitignored until commit c53b3c9. Each of those nodes
# records that a task existed without recording what it was, and two of them
# cannot be re-derived at all. Registration is the only moment at which that
# outcome is still preventable, so the check lives here.
#
# "Tracked" means git knows the path — in the index or in a commit. A file that
# has been `git add`ed but not yet committed counts, because the normal workflow
# is write spec → add → register → commit the spec and the RESULT together, and
# a guard that demanded a prior commit would make the sanctioned workflow
# impossible.

#: Path is in git's index or a commit — provenance is recoverable.
GIT_TRACKED = "tracked"
#: Path is inside a git work tree but git does not know it.
GIT_UNTRACKED = "untracked"
#: Path is inside a git work tree and matched by a .gitignore rule. This is the
#: exact condition that produced the 37 orphans, so it gets its own diagnostic.
GIT_IGNORED = "ignored"
#: There is no git work tree here at all — nothing can recover the file.
GIT_NO_REPO = "no-repo"
#: git is not installed or not on PATH.
GIT_UNAVAILABLE = "git-unavailable"


def _git(project_dir: Path, *args: str) -> subprocess.CompletedProcess:
    """Run a git command inside ``project_dir`` and return the completed process.

    Args:
        project_dir: Directory to run git in.
        *args: Arguments after ``git``.

    Returns:
        The completed process; the caller inspects ``returncode``.

    Raises:
        FileNotFoundError: If the git executable is not on PATH.
    """
    return subprocess.run(
        ["git", "-C", str(project_dir), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _git_tracking_status(project_dir: Path, task_path: Path) -> str:
    """Classify a task file's git provenance.

    Args:
        project_dir: Project root, used as git's working directory.
        task_path: Absolute path to the task file.

    Returns:
        One of :data:`GIT_TRACKED`, :data:`GIT_IGNORED`, :data:`GIT_UNTRACKED`,
        :data:`GIT_NO_REPO`, :data:`GIT_UNAVAILABLE`.
    """
    try:
        inside = _git(project_dir, "rev-parse", "--is-inside-work-tree")
    except FileNotFoundError:
        return GIT_UNAVAILABLE
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return GIT_NO_REPO

    listed = _git(project_dir, "ls-files", "--error-unmatch", "--", str(task_path))
    if listed.returncode == 0:
        return GIT_TRACKED

    # Untracked. Distinguish "ignored" because that is the failure mode that
    # actually happened here, and its remediation is different: editing
    # .gitignore, not `git add`.
    ignored = _git(project_dir, "check-ignore", "-q", "--", str(task_path))
    return GIT_IGNORED if ignored.returncode == 0 else GIT_UNTRACKED


#: Human-readable reason per non-tracked status, keyed by status constant.
_UNTRACKED_REASONS = {
    GIT_IGNORED: (
        "the file is matched by a .gitignore rule, so it will never be "
        "committed and its spec cannot be recovered later"
    ),
    GIT_UNTRACKED: (
        "git does not know this path — it is in neither the index nor a commit"
    ),
    GIT_NO_REPO: (
        "there is no git work tree here, so nothing can recover the file "
        "once it is deleted"
    ),
    GIT_UNAVAILABLE: (
        "git is not on PATH, so the file's provenance cannot be established"
    ),
}

#: Remediation per non-tracked status.
_UNTRACKED_REMEDIES = {
    GIT_IGNORED: "Un-ignore the path (edit .gitignore), then `git add`.",
    GIT_UNTRACKED: "Run `git add <file>` first.",
    GIT_NO_REPO: "Initialise a repository, or re-run with --allow-untracked.",
    GIT_UNAVAILABLE: "Install git, or re-run with --allow-untracked.",
}


def _enforce_git_tracking(
    project_dir: Path,
    task_path: Path,
    rel_path: str,
    command: str,
    allow_untracked: bool,
) -> None:
    """Refuse to register a task file git cannot recover, and warn either way.

    A tracked file always proceeds, with a reminder that the file must be
    committed alongside the RESULT — being in the index is not being in history.
    An untracked file is refused unless ``allow_untracked`` is set, in which
    case it proceeds with a loud warning naming the consequence.

    Args:
        project_dir: Project root.
        task_path: Absolute path to the task file.
        rel_path: Path as it will be stored in ``source_file``.
        command: Command name, for the error message ("cc register").
        allow_untracked: Operator override.

    Returns:
        None.

    Raises:
        SystemExit: Exit code 1 when the file is not tracked and no override
            was given.
    """
    status = _git_tracking_status(project_dir, task_path)

    if status == GIT_TRACKED:
        click.echo(
            f"NOTE: commit {rel_path} together with its RESULT. A registered "
            "task whose source file never reaches a commit becomes an "
            "undescribable stub in the graph.",
            err=True,
        )
        return

    reason = _UNTRACKED_REASONS[status]
    if allow_untracked:
        click.echo(
            f"WARNING: registering an untracked task file ({status}) — {reason}.\n"
            f"  File: {rel_path}\n"
            "  Proceeding because --allow-untracked was passed. Commit the file "
            "with its RESULT or this task becomes an undescribable stub.",
            err=True,
        )
        return

    click.echo(
        f"ERROR: refusing to register an untracked task file ({status}).\n"
        f"  File: {rel_path}\n"
        f"  Why: {reason}.\n"
        f"  A ResearchTask whose source_file cannot be recovered records that a\n"
        f"  task existed but not what it was — 37 such stubs already exist in\n"
        f"  this project's graph.\n"
        f"  Fix: {_UNTRACKED_REMEDIES[status]}\n"
        f"  Or override: seldon {command} {rel_path} --allow-untracked",
        err=True,
    )
    raise SystemExit(1)


def _find_existing(driver, database: str, rel_path: str) -> str | None:
    """Return artifact_id of any ResearchTask with matching source_file, or None."""
    with driver.session(database=database) as session:
        record = session.run(
            "MATCH (t:Artifact:ResearchTask {source_file: $sf}) RETURN t.artifact_id AS id",
            sf=rel_path,
        ).single()
    return record["id"] if record else None


def _get_artifact_state(driver, database: str, artifact_id: str) -> str | None:
    """Return the current state of an artifact, or None if not found."""
    with driver.session(database=database) as session:
        record = session.run(
            "MATCH (t:Artifact {artifact_id: $aid}) RETURN t.state AS state",
            aid=artifact_id,
        ).single()
    return record["state"] if record else None


def _get_artifact_file_hash(
    driver, database: str, artifact_id: str
) -> tuple[str | None, str | None]:
    """Return ``(file_hash, hash_scope)`` for an artifact.

    ``hash_scope`` is ``HASH_SCOPE_SPEC`` for artifacts registered with
    spec-scoped hashing, and None for legacy artifacts whose stored hash covers
    the whole file.
    """
    with driver.session(database=database) as session:
        record = session.run(
            "MATCH (t:Artifact {artifact_id: $aid}) "
            "RETURN t.file_hash AS fh, t.hash_scope AS scope",
            aid=artifact_id,
        ).single()
    if not record:
        return None, None
    return record["fh"], record["scope"]


@click.group("cc")
def cc_group():
    """CC task lifecycle commands."""
    pass


@cc_group.command("complete")
@click.argument("filepath")
@click.option("--note", default=None, help="Override auto-extracted description")
@click.option(
    "--allow-untracked",
    is_flag=True,
    default=False,
    help="Proceed even though git cannot recover the task file. "
         "The task will become an undescribable stub if the file is lost.",
)
def cc_complete(filepath, note, allow_untracked):
    """Record a CC task as completed in the graph.

    Creates a ResearchTask artifact in 'completed' state linked to the task file.
    Running twice on the same file warns instead of creating a duplicate.

    Refuses a task file git does not track unless --allow-untracked is passed;
    a source_file that never reaches a commit cannot be recovered later.

    FILEPATH is relative to project root or absolute.
    """
    project_dir = Path.cwd()
    config = load_project_config(project_dir)
    driver = get_neo4j_driver(config)
    database = config["neo4j"]["database"]
    domain_config = _get_domain_config(config)
    session_id = get_current_session(project_dir)

    # Resolve path
    task_path = Path(filepath)
    if not task_path.is_absolute():
        task_path = project_dir / task_path

    if not task_path.exists():
        click.echo(f"Error: file not found: {filepath}", err=True)
        driver.close()
        raise SystemExit(1)

    # Relative path for storage (from project root)
    try:
        rel_path = str(task_path.relative_to(project_dir))
    except ValueError:
        rel_path = str(task_path)

    try:
        _enforce_git_tracking(
            project_dir, task_path, rel_path, "cc complete", allow_untracked
        )
    except SystemExit:
        driver.close()
        raise

    # Duplicate guard — state-aware
    existing_id = _find_existing(driver, database, rel_path)
    if existing_id:
        current_state = _get_artifact_state(driver, database, existing_id)

        if current_state == "completed":
            click.echo(
                f"Warning: CC task already completed (id: {existing_id[:8]}...). "
                "No action taken.",
                err=True,
            )
            driver.close()
            raise SystemExit(0)

        # Verify SPEC immutability (hash check).
        #
        # The check is scoped to the spec — everything above the first Findings
        # heading — so that appending findings, which every task file instructs
        # the executor to do, does not make completion impossible. Editing the
        # spec after registration is still refused.
        registered_hash, hash_scope = _get_artifact_file_hash(driver, database, existing_id)
        if registered_hash is not None:
            current_hash = _spec_hash(task_path)
            legacy = hash_scope != HASH_SCOPE_SPEC

            ok = current_hash == registered_hash
            if not ok and legacy:
                # Pre-scope artifacts stored a WHOLE-FILE hash. An untouched
                # legacy file still matches that way; accept it rather than
                # refusing work that was never modified.
                ok = _file_hash(task_path) == registered_hash

            if not ok:
                extra = ""
                if legacy:
                    extra = (
                        "\n  NOTE: this task predates spec-scoped hashing, so its stored\n"
                        "  hash covers the WHOLE file including the Findings placeholder.\n"
                        "  If the spec is genuinely unedited and only findings were appended,\n"
                        "  transition it by UUID instead: seldon task update <uuid> --state ..."
                    )
                click.echo(
                    f"ERROR: Task SPEC has been modified since registration.\n"
                    f"  File: {rel_path}\n"
                    f"  Registered hash: {registered_hash[:16]}...\n"
                    f"  Current spec hash: {current_hash[:16]}...\n"
                    f"  Task immutability violated. Findings may be APPENDED under a\n"
                    f"  '## Findings' heading; the spec above it must not change. If the\n"
                    f"  spec needs changing, create an addendum file or a superseding task."
                    f"{extra}",
                    err=True,
                )
                driver.close()
                raise SystemExit(1)
        else:
            click.echo(
                "WARNING: Task has no registered file_hash. Skipping immutability check.\n"
                "  Legacy tasks registered before hash enforcement are not verified.",
                err=True,
            )

        # Pre-registered task — walk it to completed
        name = _name_from_filepath(rel_path)
        click.echo(
            f"Found pre-registered task (id: {existing_id[:8]}..., state: {current_state}). "
            "Walking to completed."
        )
        completed_at = datetime.now(timezone.utc).isoformat()
        try:
            update_artifact(
                project_dir=project_dir,
                driver=driver,
                database=database,
                artifact_id=existing_id,
                properties={"completed_at": completed_at},
                actor="cc",
                authority="accepted",
                session_id=session_id,
            )
            walk_to_completed(
                project_dir=project_dir,
                driver=driver,
                database=database,
                domain_config=domain_config,
                artifact_id=existing_id,
                current_state=current_state,
                actor="cc",
                session_id=session_id,
            )
            click.echo(f"Completed: {name}")
            click.echo(f"  source_file: {rel_path}")
            click.echo(f"  id: {existing_id[:8]}...")
            click.echo(f"  state: completed")
        finally:
            driver.close()
        return

    name = _name_from_filepath(rel_path)
    if note:
        description = note
    else:
        description, source = _extract_description_with_source(task_path)
        _warn_if_description_suspicious(task_path, description, source)
    completed_at = datetime.now(timezone.utc).isoformat()

    try:
        artifact_id = create_artifact(
            project_dir=project_dir,
            driver=driver,
            database=database,
            domain_config=domain_config,
            artifact_type="ResearchTask",
            properties={
                "description": description,
                "name": name,
                "source_file": rel_path,
                "completed_at": completed_at,
            },
            actor="cc",
            authority="accepted",
            session_id=session_id,
        )

        walk_to_completed(
            project_dir=project_dir,
            driver=driver,
            database=database,
            domain_config=domain_config,
            artifact_id=artifact_id,
            current_state="proposed",
            actor="cc",
            session_id=session_id,
        )

        click.echo(f"Recorded: {name}")
        click.echo(f"  source_file: {rel_path}")
        click.echo(f"  id: {artifact_id[:8]}...")
        click.echo(f"  state: completed")
    finally:
        driver.close()


@cc_group.command("register")
@click.argument("filepath")
@click.option("--description", default=None, help="Override auto-extracted description")
@click.option(
    "--allow-untracked",
    is_flag=True,
    default=False,
    help="Proceed even though git cannot recover the task file. "
         "The task will become an undescribable stub if the file is lost.",
)
def cc_register(filepath, description, allow_untracked):
    """Register a CC task file as a proposed ResearchTask in the graph.

    Use at task creation time to track the task before execution.
    Running twice on the same file warns instead of creating a duplicate.

    Refuses a task file git does not track unless --allow-untracked is passed;
    a source_file that never reaches a commit cannot be recovered later.

    FILEPATH is relative to project root or absolute.
    """
    project_dir = Path.cwd()
    config = load_project_config(project_dir)
    driver = get_neo4j_driver(config)
    database = config["neo4j"]["database"]
    domain_config = _get_domain_config(config)
    session_id = get_current_session(project_dir)

    task_path = Path(filepath)
    if not task_path.is_absolute():
        task_path = project_dir / task_path

    if not task_path.exists():
        click.echo(f"Error: file not found: {filepath}", err=True)
        driver.close()
        raise SystemExit(1)

    try:
        rel_path = str(task_path.relative_to(project_dir))
    except ValueError:
        rel_path = str(task_path)

    try:
        _enforce_git_tracking(
            project_dir, task_path, rel_path, "cc register", allow_untracked
        )
    except SystemExit:
        driver.close()
        raise

    existing_id = _find_existing(driver, database, rel_path)
    if existing_id:
        click.echo(
            f"Warning: CC task already registered (id: {existing_id[:8]}...). "
            "No duplicate created.",
            err=True,
        )
        driver.close()
        raise SystemExit(0)

    name = _name_from_filepath(rel_path)
    if description is None:
        description, source = _extract_description_with_source(task_path)
        _warn_if_description_suspicious(task_path, description, source)
    # Hash the SPEC only. Findings are appended after execution by convention,
    # so a whole-file hash would guarantee that every correctly-executed task is
    # divergent at completion time.
    content_hash = _spec_hash(task_path)

    try:
        artifact_id = create_artifact(
            project_dir=project_dir,
            driver=driver,
            database=database,
            domain_config=domain_config,
            artifact_type="ResearchTask",
            properties={
                "description": description,
                "name": name,
                "source_file": rel_path,
                "file_hash": content_hash,
                "hash_scope": HASH_SCOPE_SPEC,
            },
            actor="cc",
            authority="accepted",
            session_id=session_id,
        )
        click.echo(f"Registered: {name}")
        click.echo(f"  source_file: {rel_path}")
        click.echo(f"  id: {artifact_id[:8]}...")
        click.echo(f"  state: proposed")
    finally:
        driver.close()


def _find_by_artifact_id_prefix(
    driver, database: str, prefix: str
) -> list[dict]:
    """Return ResearchTasks whose artifact_id starts with ``prefix``.

    A prefix is accepted because every Seldon surface — `seldon go`, the
    briefing, this module's own output — prints artifact ids truncated to eight
    characters, so that is what a caller has to hand.

    Args:
        driver: Neo4j driver.
        database: Project database name.
        prefix: Full or leading portion of an artifact_id.

    Returns:
        Matching records with keys ``artifact_id``, ``source_file`` and
        ``description``. More than one match means the prefix is ambiguous.
    """
    with driver.session(database=database) as session:
        return session.run(
            "MATCH (t:Artifact:ResearchTask) "
            "WHERE t.artifact_id STARTS WITH $prefix "
            "RETURN t.artifact_id AS artifact_id, t.source_file AS source_file, "
            "t.description AS description",
            prefix=prefix,
        ).data()


@cc_group.command("rederive-description")
@click.argument("target")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show the derived description without writing an event.",
)
def cc_rederive_description(target, dry_run):
    """Re-parse a registered CC task file and update its description.

    TARGET is either an artifact_id (full, or the truncated prefix Seldon
    prints) or the task file's path.

    Descriptions extracted by an older parser stay wrong in the graph forever,
    because nothing re-reads the file after registration. This re-runs the
    current extractor and records the result as an `artifact_updated` EVENT —
    history is appended to, never rewritten.

    Exits non-zero if the target cannot be resolved, is ambiguous, or its
    source file is missing; a description cannot be re-derived from a file that
    is not there, and guessing one would be worse than failing.
    """
    project_dir = Path.cwd()
    config = load_project_config(project_dir)
    driver = get_neo4j_driver(config)
    database = config["neo4j"]["database"]
    session_id = get_current_session(project_dir)

    try:
        candidate_path = Path(target)
        if not candidate_path.is_absolute():
            candidate_path = project_dir / candidate_path
        try:
            rel_path = str(candidate_path.relative_to(project_dir))
        except ValueError:
            rel_path = str(candidate_path)

        artifact_id = _find_existing(driver, database, rel_path)
        if artifact_id is None:
            matches = _find_by_artifact_id_prefix(driver, database, target)
            if len(matches) > 1:
                ids = ", ".join(m["artifact_id"] for m in matches)
                click.echo(
                    f"Error: '{target}' matches {len(matches)} artifacts: {ids}",
                    err=True,
                )
                raise SystemExit(1)
            if not matches:
                click.echo(
                    f"Error: no registered CC task matches '{target}' "
                    "(tried source_file path, then artifact_id prefix).",
                    err=True,
                )
                raise SystemExit(1)
            artifact_id = matches[0]["artifact_id"]
            rel_path = matches[0]["source_file"]

        record = _find_by_artifact_id_prefix(driver, database, artifact_id)[0]
        old_description = record["description"]
        source_file = record["source_file"] or rel_path

        task_path = Path(source_file)
        if not task_path.is_absolute():
            task_path = project_dir / task_path
        if not task_path.is_file():
            click.echo(
                f"Error: source file missing on disk: {source_file}\n"
                f"  Artifact: {artifact_id}\n"
                "  The description is derived from the file; it cannot be "
                "re-derived without it.\n"
                "  Restore the file, or set the description explicitly with "
                "`seldon artifact update`.",
                err=True,
            )
            raise SystemExit(1)

        new_description, source = _extract_description_with_source(task_path)
        _warn_if_description_suspicious(task_path, new_description, source)

        click.echo(f"Artifact: {artifact_id}")
        click.echo(f"  source_file: {source_file}")
        click.echo(f"  before: {old_description!r}")
        click.echo(f"  after:  {new_description!r}")

        if new_description == old_description:
            click.echo("  unchanged — no event written.")
            return

        if dry_run:
            click.echo("  dry run — no event written.")
            return

        update_artifact(
            project_dir=project_dir,
            driver=driver,
            database=database,
            artifact_id=artifact_id,
            properties={"description": new_description},
            actor="cc",
            authority="accepted",
            session_id=session_id,
        )
        click.echo("  updated (artifact_updated event written).")
    finally:
        driver.close()
