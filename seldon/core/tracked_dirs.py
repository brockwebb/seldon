"""AD-039: `cc_tasks/` and `handoffs/` are tracked in every repository Seldon serves or scaffolds.

Only data blobs under them are ignored, by size (`*.json`, `*.jsonl`; arnold's 2026-08-13
precedent). A handoff is committed only after `python -m squiddy.secret_scan` passes (FC-02); the
scan, not an ignore rule, is what keeps secrets out of a public repository.

Two readers:

- `seldon verify` asks `ignored(project_dir)` and fails Tier A on any finding
  (`tracked_dirs_ignored`), quoting the source line git itself reports.
- `seldon init` writes `stanza()` into a new project's `.gitignore` with `ensure_stanza`.

Whether a path is ignored is git's decision, not a re-implementation of gitignore matching: the
check runs `git check-ignore --no-index -v` on one probe file per directory, which reads every
`.gitignore` on the path, `.git/info/exclude` and `core.excludesFile` in git's own precedence.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

#: The directories AD-039 requires tracked.
TRACKED_DIRS = ("cc_tasks", "handoffs")

#: A file name that stands for "any record under the directory". Not `.json`/`.jsonl`, which the
#: stanza ignores on purpose; `.md` is what task files and handoffs are.
PROBE_NAME = "probe.md"

#: The only lines AD-039 allows to ignore anything under the tracked directories.
BLOB_LINES = tuple(f"{d}/*.{ext}" for d in TRACKED_DIRS for ext in ("json", "jsonl"))

#: The comment `stanza()` puts above the blob lines.
STANZA_COMMENT = ("# AD-039: cc_tasks/ and handoffs/ are TRACKED; only data blobs under them are "
                  "ignored, by size. Handoffs are secret-scanned before commit (FC-02).")

#: The finding name `seldon verify` reports.
FINDING = "tracked_dirs_ignored"

#: The `seldon verify` check's report name (a Tier A check).
CHECK_NAME = "Tracked dirs"


class TrackedDirsError(Exception):
    """git could not answer whether a probe path is ignored."""


def stanza() -> str:
    """The comment line and the four blob lines, newline-terminated."""
    return "\n".join((STANZA_COMMENT,) + BLOB_LINES) + "\n"


def probes() -> list[str]:
    """One probe path per tracked directory, relative to the project root."""
    return [f"{d}/{PROBE_NAME}" for d in TRACKED_DIRS]


def ignored(project_dir: Path) -> list[dict]:
    """Every probe git would ignore in `project_dir`, with the rule that ignores it.

    Args:
        project_dir: A directory inside a git work tree. Probes are relative to it.

    Returns:
        One dict per ignored probe: `probe`, `source` (the file holding the rule, as git prints
        it), `line` (1-based), `pattern`. Empty when neither directory is ignored.

    Raises:
        TrackedDirsError: git failed for a reason other than "not ignored".
    """
    project_dir = Path(project_dir)
    r = subprocess.run(["git", "check-ignore", "--no-index", "-v", *probes()],
                       cwd=project_dir, capture_output=True, text=True)
    # Exit 0: at least one path ignored; 1: none ignored; anything else is an error (128: not a
    # repository, bad config).
    if r.returncode not in (0, 1):
        raise TrackedDirsError(f"git check-ignore exited {r.returncode}: {r.stderr.strip()}")
    out = []
    for row in r.stdout.splitlines():
        # `<source>:<linenum>:<pattern>\t<pathname>`; the pattern may itself contain ':'.
        meta, _, path = row.partition("\t")
        source, _, rest = meta.partition(":")
        num, _, pattern = rest.partition(":")
        if pattern.startswith("!"):
            # -v also prints the negation that last matched a path that is NOT ignored.
            continue
        out.append({"probe": path, "source": source, "line": int(num) if num.isdigit() else 0,
                    "pattern": pattern})
    return out


def describe(finding: dict) -> str:
    """One line for a finding: where the rule is, what it says, and the fix."""
    return (f"{FINDING}: {finding['source']}:{finding['line']}: `{finding['pattern']}` ignores "
            f"{finding['probe']}. Fix: delete that line and keep only the AD-039 blob lines "
            f"({', '.join(BLOB_LINES)}).")


def ensure_stanza(gitignore: Path, extra_lines: tuple[str, ...] = ()) -> list[str]:
    """Append any of `extra_lines` and the AD-039 stanza missing from `gitignore`, creating it.

    Existing lines are never removed or reordered: a rule that still ignores a tracked directory
    is reported by `ignored`, not silently rewritten.

    Args:
        gitignore: Path of the `.gitignore` to write.
        extra_lines: Lines to ensure before the stanza (`seldon init` passes `.env`).

    Returns:
        The lines appended, in order (empty when the file already held them all).
    """
    gitignore = Path(gitignore)
    text = gitignore.read_text() if gitignore.exists() else ""
    have = {ln.strip() for ln in text.splitlines()}
    add = [ln for ln in extra_lines if ln not in have]
    blob = [ln for ln in BLOB_LINES if ln not in have]
    if blob:
        add += ([STANZA_COMMENT] if STANZA_COMMENT not in have else []) + blob
    if add:
        sep = "" if not text or text.endswith("\n") else "\n"
        gitignore.write_text(text + sep + "\n".join(add) + "\n")
    return add
