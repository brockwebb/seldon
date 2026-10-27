"""AD-038-R13 (NUM-001R Part A): task numbers are allocated, not hand-minted.

A task file's name carries a number, `<date>_<PREFIX>-<NNN><suffix>_<slug>.md` (`SEL-011`, `HB-01b`, `SEL-010R2`).
Until this module nothing allocated it: each Desktop thread minted the next number from what it could see, so two
threads wrote squiddy SQ-019 within three hours on 2026-10-21 (a0e43099, 6b38bc3f), and each file told its session to
glob every sibling `*SQ-019*ADDENDUM*`, so each would have read the other's addenda. The same week had two SEL-007s.

Two halves, the pattern every system with human-readable sequential keys uses (an issue tracker's `PROJ-123`, PEP
numbers, RFC numbers): an allocator that reads what is taken and proposes the next, and a uniqueness check where the
key is committed, which is what makes the allocator safe without a lock. Two threads that read the same state get the
same proposal; the second registration is refused (`number_taken`) and its author asks again. That is optimistic
concurrency control with the unique constraint at insert (a database unique index under a read-then-insert), not a
reservation; AD-033-R12 (a decision's `seq` assigned at merge) is this repository's own precedent for numbering at
the point of commit rather than at authoring.

- :func:`next_number` reads the graph and `cc_tasks/` in the primary checkout and every open worktree, so a number
  written on an unmerged branch is taken.
- :func:`registration_refusal` reads the graph only: a number is "registered" when a ResearchTask holds it.

**Identity.** The token's identity is `<PREFIX>-<digits><suffix>`. A letter suffix is a distinct task (hazbrief's
HB-01b to HB-01e, squiddy's SQ-021M and SQ-021M2 are siblings filed on purpose while the base was open). A trailing
`R` or `R<n>` is a re-filing of the same identity (SEL-010R, SEL-010R2): allowed when every other holder of that
identity is withdrawn, superseded or rejected, or still open and not running (proposed, accepted, blocked), because
the re-filing is registered first and the holder superseded `--superseded-by` it afterwards: all five R re-filings
over an open holder in seldon's event log (DESK-002R, SEC-001R, DISP-001R, STD-001R, DISP-003R) were registered 4 to
34 seconds before their holder was superseded, because `task supersede --superseded-by` needs the new id. A holder
that is running or finished
(in_progress, completed, verified) refuses: that number names work that happened.

A task with no file is a holder too, named by a leading `<TOKEN>:` or `<TOKEN> —` in its description (`NUM-001:
task identifiers are minted by hand ...`); a description that only mentions a token (`FRICTION-002 Part D step 3`)
holds nothing.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

#: The task directory every project uses (CLAUDE.md §6; AD-039's tracked directories).
TASK_DIR = "cc_tasks"

#: Zero-padding for a prefix's first number. Every seldon and squiddy prefix uses three digits (SEL-001, SQ-001);
#: a prefix that already has numbers keeps the widest width it has used (hazbrief's HB-51 stays two).
DEFAULT_WIDTH = 3

#: Refused as a re-filing's holder: the number names work that ran or finished. Every other state (the open ones a
#: re-filing supersedes, and the terminal ones that ended without running to completion) lets an R re-filing through.
HELD_STATES = ("in_progress", "completed", "verified")

#: The refusal code, beside the dispatcher's own codes.
NUMBER_TAKEN = "number_taken"

_PREFIX_RE = re.compile(r"^[A-Z][A-Z0-9]*$")
#: `<PREFIX>-<digits><suffix><R re-filing>`; the suffix is lazy so a trailing `R<n>` is read as the re-filing marker.
_TOKEN = r"(?P<prefix>[A-Z][A-Z0-9]*)-(?P<digits>\d+)(?P<suffix>[A-Za-z0-9]*?)(?P<refile>R\d*)?"
_FILE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_" + _TOKEN + r"(?=_|\.md$)")
_DESC_RE = re.compile(r"^\s*" + _TOKEN + r"\s*(?::|—|–|--)")


class NumberingError(RuntimeError):
    """A prefix that is not a prefix, or a repository git cannot list."""


@dataclass(frozen=True)
class Token:
    prefix: str
    digits: str
    suffix: str
    refile: str

    @property
    def number(self) -> int:
        return int(self.digits)

    @property
    def identity(self) -> str:
        """`SEL-010` for SEL-010, SEL-010R and SEL-010R2; `HB-01b` for HB-01b."""
        return f"{self.prefix}-{self.digits}{self.suffix}"

    def __str__(self) -> str:
        return f"{self.identity}{self.refile}"


@dataclass(frozen=True)
class Holder:
    token: Token
    artifact_id: str | None
    state: str | None
    source_file: str | None
    where: str

    def describe(self) -> str:
        if self.artifact_id:
            return (f"{self.artifact_id[:8]} ({self.state}, "
                    f"{self.source_file or 'no file; numbered by its description'})")
        return f"{self.source_file} ({self.where})"


def _token(m: re.Match | None) -> Token | None:
    if not m:
        return None
    return Token(m["prefix"], m["digits"], m["suffix"] or "", m["refile"] or "")


def file_token(path: str | Path) -> Token | None:
    """The number a task file's name carries, or None for an unnumbered file."""
    return _token(_FILE_RE.match(Path(path).name))


def description_token(text: str | None) -> Token | None:
    """The number a file-less task claims by its description's leading `<TOKEN>:`, or None."""
    return _token(_DESC_RE.match(text or ""))


def graph_holders(driver, database: str) -> list[Holder]:
    """Every ResearchTask that holds a number, by its file's name or, with no file, its description."""
    with driver.session(database=database) as s:
        rows = s.run("MATCH (t:Artifact:ResearchTask) RETURN t.artifact_id AS id, t.source_file AS f, "
                     "t.state AS st, t.description AS d").data()
    out = []
    for r in rows:
        tok = file_token(r["f"]) if r["f"] else description_token(r["d"])
        if tok:
            out.append(Holder(tok, r["id"], r["st"], r["f"], "graph"))
    return out


def worktrees(project_dir: Path) -> list[Path]:
    """The primary checkout and every worktree git lists for `project_dir`'s repository."""
    r = subprocess.run(["git", "worktree", "list", "--porcelain"], cwd=project_dir, capture_output=True, text=True)
    if r.returncode != 0:
        raise NumberingError(f"git cannot list the worktrees of {project_dir}: {r.stderr.strip()}")
    return [Path(line.split(" ", 1)[1]) for line in r.stdout.splitlines() if line.startswith("worktree ")]


def file_holders(project_dir: Path) -> list[Holder]:
    """Every numbered file under `cc_tasks/` in every worktree, RESULTs and addenda included (they carry it too).

    A project in a subdirectory of its repository reads the same subdirectory of each worktree.
    """
    project_dir = Path(project_dir).resolve()
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=project_dir, capture_output=True, text=True)
    if top.returncode != 0:
        raise NumberingError(f"{project_dir} is not in a git work tree: {top.stderr.strip()}")
    sub = project_dir.relative_to(Path(top.stdout.strip()).resolve())
    out = []
    for tree in worktrees(project_dir):
        task_dir = tree / sub / TASK_DIR
        if not task_dir.is_dir():
            continue
        for p in sorted(task_dir.glob("*.md")):
            tok = file_token(p)
            if tok:
                out.append(Holder(tok, None, None, f"{TASK_DIR}/{p.name}", str(tree)))
    return out


def next_number(prefix: str, holders: list[Holder]) -> dict:
    """The next unused number for `prefix`: `{token, highest, width, seen}`.

    One more than the highest number any holder carries under the prefix, whatever its suffix, so a re-filing or a
    lettered sibling never hands out its own base again.
    """
    if not _PREFIX_RE.match(prefix or ""):
        raise NumberingError(f"{prefix!r} is not a task prefix: expected capital letters and digits starting with a "
                             f"letter (SEL, SQ, HB)")
    mine = [h for h in holders if h.token.prefix == prefix]
    highest = max(mine, key=lambda h: h.token.number, default=None)
    width = max((len(h.token.digits) for h in mine), default=DEFAULT_WIDTH)
    n = (highest.token.number if highest else 0) + 1
    return {"token": f"{prefix}-{n:0{width}d}", "highest": highest, "width": width, "seen": len(mine)}


def registration_refusal(rel_path: str, holders: list[Holder]) -> tuple[str | None, list[Holder]]:
    """`(refusal or None, open holders an R re-filing should supersede)` for registering `rel_path`.

    `holders` are the graph's (:func:`graph_holders`). The file's own registration, if any, is not a holder of its
    own number.
    """
    own = file_token(rel_path)
    if own is None:
        return None, []
    others = [h for h in holders if h.token.identity == own.identity and h.source_file != rel_path]
    if not others:
        return None, []
    named = "; ".join(f"{h.token} by {h.describe()}" for h in others)
    if not own.refile:
        return (f"{NUMBER_TAKEN}: {own} is already registered to another file in this repository ({named}). "
                f"Ask `seldon task number {own.prefix}` for the next unused number, or name the file "
                f"{own.identity}R<n> if it re-files that task"), []
    same = [h for h in others if str(h.token) == str(own)]
    held = [h for h in others if h.state in HELD_STATES]
    if same or held:
        why = (f"{own} itself is registered to another file" if same
               else f"its holder ran or finished ({', '.join(h.state for h in held)}), and a re-filing is allowed "
                    f"only over a withdrawn, superseded, rejected or still-open holder")
        return (f"{NUMBER_TAKEN}: {own} re-files {own.identity}, but {why} ({named}). Ask `seldon task number "
                f"{own.prefix}` for a new number"), []
    open_holders = [h for h in others if h.state not in ("withdrawn", "superseded", "rejected")]
    return None, open_holders


def allocate(project_dir: Path, driver, database: str, prefix: str) -> dict:
    """:func:`next_number` over the graph and every worktree's `cc_tasks/`: `{token, highest, width, seen, trees}`."""
    prefix = (prefix or "").strip().upper()
    holders = graph_holders(driver, database) + file_holders(Path(project_dir))
    return {**next_number(prefix, holders), "trees": len(worktrees(Path(project_dir)))}


def render(out: dict) -> str:
    """The allocator's reply: the token on the first line, where it came from on the second."""
    h = out["highest"]
    after = f"after {h.token} ({h.describe()})" if h else "the first under this prefix"
    return (f"{out['token']}\n  next unused number, {after}; read from the graph and cc_tasks/ in "
            f"{out['trees']} checkout(s). Registration refuses a number another file holds (number_taken).")
