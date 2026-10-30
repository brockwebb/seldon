"""Git worktrees for the parallel dispatcher: one task, one worktree, one branch.

`cc_tasks/2026-10-07_SEL-004_worktree_per_task_dispatch.md` decisions 2 to 5, recorded as
AD-034 (`docs/design/AD-034_worktree_per_task_dispatch.md`).

**Why worktrees.** A dispatched session works in a checkout, and two sessions in one checkout
share an index, a HEAD and every file. ai-readiness-kg's recollection suite died at 35% on
2026-10-07 when a Desktop session committed in the checkout it was running in. `git worktree`
gives each session its own working tree, index and HEAD over one shared object store and one
set of refs, which is the standard way to run parallel agent sessions on one repository
(git-worktree(1)).

**What this module is.** Git plumbing and the one lock discipline, nothing that reads the graph
or writes the event store. The command module composes these; keeping them here keeps each one
testable against a scratch repository.

Prior art for the merge these helpers serve: the merge queue ("not rocket science rule",
Graydon Hoare's bors for Rust, 2014; GitHub's merge queue): main only ever moves to a commit
that was tested as it will be, so the branch is rebased onto the main it will land on, re-gated
when that changed what it touched, and fast-forwarded only if main has not moved since.
"""
from __future__ import annotations

import fcntl
import json
import os
import subprocess
from contextlib import contextmanager
from pathlib import Path

#: The primary checkout's absolute path, set in every worktree session's environment. A
#: non-Python tool reads it; Python code may call :func:`primary_checkout`, which derives the
#: same path from git and needs no environment.
PRIMARY_CHECKOUT_ENV = "SELDON_PRIMARY_CHECKOUT"


class WorktreeError(RuntimeError):
    """A git state the parallel dispatcher cannot work with, named."""


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})


def primary_checkout(path: Path) -> Path:
    """The primary checkout of the repository `path` is in, from a worktree or from itself.

    Every worktree shares the primary's git directory (`git rev-parse --git-common-dir`), and
    the primary checkout is that directory's parent. This is how a worktree session resolves a
    file that must be ONE file across all worktrees, such as a spend ledger (decision 5):
    resolved against its own root it would get its own copy, and each parallel run would check
    a daily cap against a ledger the others never write, which is DD-019's batch-identity
    defect at worktree grain.

    Raises:
        WorktreeError: `path` is not in a git work tree, or the repository's git directory is
            not a `.git` directory inside a checkout (a bare repository has no primary).
    """
    r = git(Path(path), "rev-parse", "--path-format=absolute", "--git-common-dir")
    if r.returncode != 0:
        raise WorktreeError(f"{path} is not inside a git work tree: {r.stderr.strip()}")
    common = Path(r.stdout.strip())
    if common.name != ".git":
        raise WorktreeError(f"git common dir {common} is not a checkout's .git directory; "
                            f"there is no primary checkout to resolve to")
    return common.parent


@contextmanager
def locked(path: Path):
    """An exclusive `fcntl.flock` on the file itself, held for the body of the `with`.

    The discipline ai-readiness-kg's spend guard already uses (`kg/spend.py`, DD-022: the
    ledger opened `a+` and flocked for the whole read, compute and append), so a process using
    this and a process using that exclude each other on the same file. The pass holds it while
    it stages and commits a shared append-only file, so no append lands half-staged.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        yield fh
    finally:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        fh.close()


def rev(repo: Path, ref: str) -> str | None:
    r = git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    return r.stdout.strip() if r.returncode == 0 else None


def is_ignored(repo: Path, rel: str) -> bool:
    return git(repo, "check-ignore", "-q", "--", rel).returncode == 0


def add(primary: Path, worktree: Path, branch: str, base: str) -> dict:
    """`git worktree add <worktree> -b <branch> <base>`. `{ok, stderr}`; never raises."""
    r = git(primary, "worktree", "add", "-q", "-b", branch, str(worktree), base)
    return {"ok": r.returncode == 0, "stderr": (r.stderr or r.stdout).strip()}


def remove(primary: Path, worktree: Path) -> dict:
    """Remove a MERGED task's worktree. The branch is kept: nothing deletes a branch
    (FRICTION-002 Part B step 3, AD-034 ADDENDUM 01).

    The Claude Code CLI locks a worktree it enters with `--worktree` (`git worktree list`
    shows `locked`), and git refuses to remove a locked worktree, so it is unlocked first; an
    unlock of a worktree that is not locked fails harmlessly and is not reported. `--force` on
    the removal is for the symlinks `link` made and for untracked build debris; the caller has
    already checked that nothing tracked is modified or unstaged.
    """
    git(primary, "worktree", "unlock", str(worktree))
    r = git(primary, "worktree", "remove", "--force", str(worktree))
    return {"worktree_removed": r.returncode == 0,
            "stderr": "" if r.returncode == 0 else (r.stderr or r.stdout).strip()}


def link(primary: Path, worktree: Path, rels: list) -> list:
    """Symlink each existing `rel` from the primary checkout into the worktree. Returns the
    paths linked; a path absent from the primary is skipped, not invented."""
    done = []
    for rel in rels:
        src, dst = Path(primary) / rel, Path(worktree) / rel
        if not src.exists() or dst.exists() or dst.is_symlink():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.symlink_to(src)
        done.append(rel)
    return done


def _porcelain(repo: Path, *flags: str) -> list:
    """`git status --porcelain -z` as `[(XY, path)]`. `-z`, so a path is never quoted; a rename's or copy's second
    record (its source) is consumed, not listed."""
    recs = git(repo, "status", "--porcelain", "-z", *flags).stdout.split("\0")
    out, i = [], 0
    while i < len(recs):
        rec = recs[i]
        i += 1
        if len(rec) < 4:
            continue
        out.append((rec[:2], rec[3:]))
        if rec[0] in "RC":
            i += 1
    return out


def _ignored_as_directory(repo: Path, rel: str) -> bool:
    """Would `rel` be ignored were it a directory? git cannot be asked directly: `git check-ignore rel/` refuses a
    symlink ("beyond a symbolic link"), and without the slash a symlink is a file, which a `dir/` pattern never
    matches (gitignore(5): "If there is a separator at the end of the pattern then the pattern will only match
    directories"). So git answers it about a scratch work tree holding `rel` as an empty directory and the only
    `.gitignore` files that can bear on it, `rel`'s ancestors', with the repository's own git directory supplying
    `info/exclude` and `core.excludesFile`. `--no-index`: the scratch tree has no index of its own to agree with."""
    import shutil
    import tempfile
    repo = Path(repo)
    gitdir = git(repo, "rev-parse", "--path-format=absolute", "--git-dir").stdout.strip()
    scratch = Path(tempfile.mkdtemp(prefix="seldon-ignore-"))
    try:
        (scratch / rel).mkdir(parents=True)
        parts = Path(rel).parts
        for depth in range(len(parts)):
            src = repo.joinpath(*parts[:depth], ".gitignore")
            if src.is_file() and not src.is_symlink():
                shutil.copyfile(src, scratch.joinpath(*parts[:depth], ".gitignore"))
        r = subprocess.run(["git", f"--git-dir={gitdir}", f"--work-tree={scratch}", "check-ignore", "-q",
                            "--no-index", "--", rel.rstrip("/") + "/"],
                           cwd=scratch, capture_output=True, text=True,
                           env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
        return r.returncode == 0
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _clean_link(repo: Path, rel: str, primary: Path | None) -> bool:
    """SEL-017 Part A (AD-034-R13): an untracked symlink git would not report had it been the directory it points
    to. Clean when its own path is ignored once the trailing slash of a `dir/` pattern is disregarded, or when its
    target is inside the primary checkout at a path the primary ignores."""
    path = Path(repo) / rel
    if not path.is_symlink():
        return False
    if _ignored_as_directory(repo, rel):
        return True
    if primary is None:
        return False
    target = Path(os.path.realpath(path))
    try:
        trel = target.relative_to(Path(primary).resolve())
    except ValueError:
        return False
    return bool(trel.parts) and is_ignored(primary, trel.as_posix())


def session_links(repo: Path, exclude=()) -> list:
    """The untracked paths of `repo` that are a session's own links to gitignored data, which `dirty_paths` counts
    clean: each is a symlink `_clean_link` accepts. A collapsed untracked directory (`corpus/`, made by the session
    to hold its link) is listed by the link paths inside it, and only when every untracked path inside it is such a
    link. `exclude` (the dispatcher's configured `worktree_links`) is left out: those are recorded as `linked`."""
    return _untracked_split(repo, exclude)[0]


def _untracked_split(repo: Path, exclude=()) -> tuple:
    """`(links, clean_entries)`: the session links under `repo`'s untracked entries, and the default-porcelain
    untracked entries that consist of nothing else."""
    entries = [p for xy, p in _porcelain(repo) if xy == "??" and p not in set(exclude)]
    if not entries:
        return [], set()
    try:
        primary = primary_checkout(repo)
    except WorktreeError:
        primary = None
    every = [p for xy, p in _porcelain(repo, "--untracked-files=all") if xy == "??"]
    verdict = {p: _clean_link(repo, p.rstrip("/"), primary) for p in every
               if p not in set(exclude) and (Path(repo) / p.rstrip("/")).is_symlink()}
    links, clean = [], set()
    for entry in entries:
        inside = [p for p in every if p == entry or (entry.endswith("/") and p.startswith(entry))]
        if inside and all(verdict.get(p) for p in inside):
            clean.add(entry)
            links.extend(p.rstrip("/") for p in inside)
    return sorted(set(links)), clean


def dirty_paths(repo: Path, exclude=()) -> list:
    """`git status --porcelain` paths, minus `exclude` and minus a session's own links to gitignored data
    (`session_links`, SEL-017 Part A): a symlink at a path a `dir/` pattern ignores is clean exactly as the
    directory would be. A symlink at a tracked path is a type change, never untracked, so it still counts. Not
    stripped: see `tree_state`."""
    _, clean = _untracked_split(repo, exclude)
    return [p for _, p in _porcelain(repo) if p not in set(exclude) and p not in clean]


def ignored_paths(repo: Path, exclude=()) -> list:
    """Gitignored paths present in a worktree (`git status --ignored`), minus `exclude`.
    Removing a merged worktree discards these, so they are named before it is removed."""
    out = git(repo, "status", "--porcelain", "--ignored").stdout
    paths = [ln[3:] for ln in out.split("\n") if ln.startswith("!! ")]
    return [x for x in paths if x.rstrip("/") not in {e.rstrip("/") for e in exclude}]


def changed_files(repo: Path, a: str, b: str) -> list:
    # `--no-renames`: a rename lists both the old and the new path, so a write set never
    # loses the file the task moved away from.
    r = git(repo, "diff", "--name-only", "--no-renames", a, b)
    return sorted(p for p in r.stdout.splitlines() if p)


def rebase(worktree: Path, onto: str) -> dict:
    """Rebase the worktree's branch onto `onto`. `{ok, conflicts, stderr}`.

    A conflict is never resolved here (decision 3): the unmerged paths are read, the rebase is
    aborted so the branch is exactly as the session left it, and the caller reports the files.
    `merge=union` paths merge by git's own union driver during the rebase (decision 4).
    """
    r = git(worktree, "rebase", "-q", onto)
    if r.returncode == 0:
        return {"ok": True, "conflicts": [], "stderr": ""}
    conflicts = sorted(p for p in git(worktree, "diff", "--name-only",
                                      "--diff-filter=U").stdout.splitlines() if p)
    git(worktree, "rebase", "--abort")
    return {"ok": False, "conflicts": conflicts, "stderr": (r.stderr or r.stdout).strip()}


def union_files(repo: Path, paths: list) -> list:
    """The subset of `paths` git merges with the union driver (`merge=union` in
    `.gitattributes`). The attribute is the one source of truth for "append-only": the files
    git merges by union are exactly the files whose merge result must be checked."""
    if not paths:
        return []
    r = git(repo, "check-attr", "merge", "--", *paths)
    out = []
    for line in r.stdout.splitlines():
        path, _, value = line.rpartition(": merge: ")
        if value.strip() == "union":
            out.append(path)
    return out


def show(repo: Path, rev_: str, path: str) -> bytes | None:
    r = subprocess.run(["git", "show", f"{rev_}:{path}"], cwd=repo, capture_output=True)
    return r.stdout if r.returncode == 0 else None


def check_union_text(data: bytes, key: str, base: bytes | None = None) -> dict:
    """Decision 4's post-merge check on one `merge=union` file's content.

    Every non-empty line must parse as a JSON object, and `key` must be unique among the lines
    that carry it. The union driver keeps both sides' lines and can neither see a line that
    lost its newline (two records fused into one unparseable line) nor a record both sides
    appended under one id, so the check reads the result rather than trusting the driver.

    With `base` (main's content before the merge) only what the merge ADDED is judged: a line
    present in `base` is not the branch's, so a defect already on main does not block every
    task that appends to the file. An added line is still a duplicate when its key is
    already in `base`.

    Returns `{ok, malformed: [line numbers], duplicates: [key values]}`.
    """
    def decode(raw):
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return obj if isinstance(obj, dict) else None

    base_lines: dict[str, int] = {}
    seen: set = set()
    for raw in (base or b"").decode("utf-8", errors="replace").splitlines():
        if raw.strip():
            base_lines[raw] = base_lines.get(raw, 0) + 1
            obj = decode(raw)
            if obj is not None and key in obj:
                seen.add(obj[key])
    malformed, dupes = [], []
    for n, raw in enumerate(data.decode("utf-8", errors="replace").splitlines(), start=1):
        if not raw.strip():
            continue
        if base_lines.get(raw, 0) > 0:
            base_lines[raw] -= 1   # this occurrence came from main
            continue
        obj = decode(raw)
        if obj is None:
            malformed.append(n)
            continue
        if key in obj:
            if obj[key] in seen and obj[key] not in dupes:
                dupes.append(obj[key])
            seen.add(obj[key])
    return {"ok": not malformed and not dupes, "malformed": malformed, "duplicates": dupes}
