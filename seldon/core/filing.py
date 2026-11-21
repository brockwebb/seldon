"""A consumer's filing, and the one call that writes, commits and registers a task file (SEL-023, AD-036-R17, AD-038-R20).

**Why this exists.** AD-036-R12 says a consumer files into the producer's `cc_tasks/` and registers there; AD-038-R11
refuses any file without candidacy headers. Both were in force, so a filing that followed R12 could not register
(ai-readiness-kg AR-7 into squiddy, 2026-11-03), and two header-less filings registered before R11 (squiddy 6ffde0f7,
18001e38) showed as `no_source_file` or `no_header` on every pass. Between a Desktop's write and its register, the
untracked file failed c7 for the producer's whole queue (squiddy twice on 2026-10-30, once on 2026-11-03).

**What it holds.**

- :func:`designs_fix_refusal`: the consumer rule's registration half. A filing reports what the consumer experienced;
  one whose headings or labels carry a fix for the producer is refused (`filing_designs_fix`). The operator's rule,
  2026-11-03: consumers report and never design or implement the producer's fix.
- :func:`registration_properties`: what registration records from the `Kind`, `Filed by` and `Dispatch` headers.
- :func:`filing_lock`: an `fcntl.flock` the filer holds over write, commit and register, and the dispatcher's pass
  holds while it reads the tree (reconcile, c7, candidacy). Neither sees the other's half-state, so no pass can see an
  untracked task file between its write and its registration.
- :func:`file_task`: `seldon cc file` and `seldon_cc_file`.

**Prior art.** The write-and-register-in-one-call is an atomic publish under a mutual-exclusion lock: the write
becomes visible to the reader only in its finished state, the same contract as a database transaction's isolation
(Gray and Reuter, *Transaction Processing*, 1993, ch. 7: a reader never observes another writer's uncommitted
state) and as `flock(2)` advisory locking between cooperating processes. The lock is the dispatcher's own lease
primitive (`seldon.core.dispatch.Lease`, DD-019), reused rather than re-invented, with `acquire_waiting` for both
sides because both hold it for seconds. The draft-fix refusal is a lint over headings (the pattern list is config).
"""
from __future__ import annotations

import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from seldon.core import dispatch as D

#: The `seldon.yaml` block these settings come from. Top-level, not under `dispatch:`: a project with no dispatcher
#: still files and registers, and the lock is the filer's as much as the pass's.
CONFIG_BLOCK = "filings"
#: Where the lock lives. Under `.seldon/` (gitignored runtime state, beside the dispatcher's lease).
LOCK_FILE_DEFAULT = ".seldon/filing.lock"
#: How long either side waits for the other. NO MEASURED BASIS beyond this: a registration takes seconds (premises,
#: recall) and a pass's tree-reading half takes seconds; two minutes is far past both and short of the 5-minute poll.
LOCK_WAIT_S_DEFAULT = 120

#: Headings or bold labels that carry a fix rather than a report (`filing_designs_fix`). Case-insensitive, matched
#: against a markdown heading's text or a line-leading `**<label>:**`. Overridden by `filings.fix_headings`.
FIX_HEADINGS_DEFAULT = (
    r"\b(?:proposed|suggested|candidate|recommended|possible)\s+(?:fix|fixes|solution|solutions|design|designs|"
    r"change|changes|remedy|remedies|implementation)\b",
    r"^(?:the\s+)?(?:fix|fixes)\b",
    r"^(?:how\s+to\s+fix|remedy|remedies|patch|implementation\s+plan)\b",
)
FILING_DESIGNS_FIX = "filing_designs_fix"
LOCK_TIMEOUT = "filing_lock_timeout"
FILE_EXISTS = "file_exists"
#: SEL-040 Part C (AD-038-R26): an addendum whose base task file is absent or unregistered.
ADDENDUM_ORPHAN = "addendum_without_task"

#: `<stem>_ADDENDUM_<NN>[_<slug>].md` (DN-006 decision 3's pattern, as `dispatch.is_addendum_name` reads it), with the
#: base task's stem captured.
_ADDENDUM_BASE_RE = re.compile(r"^(?P<stem>.+?)_ADDENDUM[_-]?(?P<nn>\d+)(?:[_-][^/]*)?\.md$")

_HEADING_RE = re.compile(r"^#{1,6}\s+(?P<text>.+?)\s*#*\s*$")
_LABEL_RE = re.compile(r"^\s*(?:[-*+]\s+)?\*\*(?P<text>[^*\n]+?):?\*\*")


class FilingError(RuntimeError):
    """A filing that cannot be written or registered; the message names the cause and the fix."""


# ------------------------------------------------------------ the file system's name limit (SEL-042 Part E)

#: SEL-042 (AD-038-R30): a name longer than the file system takes, refused before anything is written.
NAME_TOO_LONG = "name_too_long"
#: The limit when `pathconf` cannot say: POSIX NAME_MAX on APFS, HFS+, ext4 and NTFS's UTF-16 units alike.
NAME_MAX_FALLBACK = 255
#: The fixed bytes an addendum adds to its task's stem: `_ADDENDUM_NN_` and `.md`.
ADDENDUM_FIXED_BYTES = len("_ADDENDUM_01_") + len(".md")
#: The slug room below which registration warns that the task's stem leaves too little for an addendum's slug. A
#: FIRST VALUE, not a measurement: hazbrief HB-207's stem left 86 bytes and its filer saw "about 50" as tight; 60
#: is room for a ten-word slug. Overridden by `filings.addendum_slug_warn_bytes`.
ADDENDUM_SLUG_WARN_BYTES = 60


def name_limit(directory: Path) -> int:
    """The longest file name, in bytes, the file system holding `directory` takes (`pathconf(PC_NAME_MAX)`, on the
    nearest existing ancestor). Falls back to `NAME_MAX_FALLBACK` where the platform cannot say."""
    q = Path(directory)
    while not q.exists() and q != q.parent:
        q = q.parent
    try:
        return int(os.pathconf(q, "PC_NAME_MAX"))
    except (OSError, ValueError, AttributeError):
        return NAME_MAX_FALLBACK


def addendum_slug_room(stem: str, limit: int) -> int:
    """Bytes left for an addendum's slug under task stem `stem`: `limit` less the stem and `_ADDENDUM_NN_` + `.md`."""
    return limit - len(stem.encode("utf-8")) - ADDENDUM_FIXED_BYTES


def name_refusal(directory: Path, name: str) -> Optional[str]:
    """`name_too_long: ...` when `name` (UTF-8 bytes, as the file system counts) exceeds the limit of the volume
    holding `directory`, stating the limit and the bytes left for the slug; None when it fits."""
    limit = name_limit(directory)
    used = len(name.encode("utf-8"))
    if used <= limit:
        return None
    stem = addendum_base_stem(name)
    if stem is not None:
        room = addendum_slug_room(stem, limit)
        where = (f"its task's stem ({len(stem.encode('utf-8'))} bytes) leaves {max(room, 0)} byte(s) for the "
                 f"addendum's slug after `_ADDENDUM_NN_` and `.md`")
    else:
        m = re.match(r"^(\d{4}-\d{2}-\d{2}_)", name)
        fixed = len(m.group(1)) if m else 0
        where = f"{max(limit - fixed - len('.md'), 0)} byte(s) are left for the slug after the date and `.md`"
    return (f"{NAME_TOO_LONG}: {name!r} is {used} bytes and the file system takes at most {limit}; {where}. Shorten "
            f"the slug by {used - limit} byte(s). Nothing was written.")


def settings(config: Optional[dict]) -> dict:
    """The `filings:` block with defaults. Raises FilingError on a malformed one."""
    block = (config or {}).get(CONFIG_BLOCK) or {}
    if not isinstance(block, dict):
        raise FilingError(f"seldon.yaml `{CONFIG_BLOCK}:` must be a mapping, got {block!r}")
    wait = block.get("lock_wait_s", LOCK_WAIT_S_DEFAULT)
    if isinstance(wait, bool) or not isinstance(wait, (int, float)) or wait < 0:
        raise FilingError(f"{CONFIG_BLOCK}.lock_wait_s must be a number of seconds, 0 or more, got {wait!r}")
    lock = block.get("lock_file", LOCK_FILE_DEFAULT)
    if not isinstance(lock, str) or not lock.strip():
        raise FilingError(f"{CONFIG_BLOCK}.lock_file must be a path, got {lock!r}")
    heads = block.get("fix_headings", list(FIX_HEADINGS_DEFAULT))
    if not isinstance(heads, list) or not all(isinstance(h, str) and h for h in heads):
        raise FilingError(f"{CONFIG_BLOCK}.fix_headings must be a list of regular expressions, got {heads!r}")
    try:
        compiled = [re.compile(h, re.IGNORECASE) for h in heads]
    except re.error as exc:
        raise FilingError(f"{CONFIG_BLOCK}.fix_headings holds a pattern that does not compile: {exc}") from exc
    return {"lock_file": lock, "lock_wait_s": wait, "fix_headings": compiled}


# ---------------------------------------------------------------- the consumer rule, at registration

def designs_fix_refusal(task_path: Path, config: Optional[dict]) -> Optional[str]:
    """None, or the `filing_designs_fix` refusal for a filing whose headings or labels carry the producer's fix.

    A filing reports what the consumer experienced; the producer's thread designs the fix "from a holistic ...
    solution" (the operator, 2026-11-03). The check reads structure (headings and line-leading bold labels) and not
    prose, so "this filing proposes no fix" in a sentence is not a hit. Fenced code is skipped.
    """
    try:
        s = settings(config)
    except FilingError as exc:
        return f"{FILING_DESIGNS_FIX}: the check cannot run ({exc})"
    hits, fenced = [], False
    lines = Path(task_path).read_text(encoding="utf-8", errors="replace").splitlines()
    for n, line in enumerate(lines, 1):
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if fenced:
            continue
        m = _HEADING_RE.match(line) or _LABEL_RE.match(line)
        if not m:
            continue
        label = m.group("text").strip()
        if any(p.search(label) for p in s["fix_headings"]):
            hits.append(f"line {n}: {label!r}")
    if not hits:
        return None
    return (f"{FILING_DESIGNS_FIX}: this filing carries a fix for the producer ({'; '.join(hits[:5])}). A filing "
            f"reports what the consumer experienced; the producer designs and implements the fix (AD-036-R17, the "
            f"operator's rule of 2026-11-03). Drop the section and state the observation, the evidence and what the "
            f"consumer wants to know back.")


def registration_properties(text: str) -> dict:
    """The properties registration records from a task file's `Kind`, `Filed by` and `Dispatch` headers.

    Absent headers record nothing, so a task file without them is created exactly as before.
    """
    out = {}
    if D.kind_of_text(text) == D.KIND_FILING:
        out["task_kind"] = D.KIND_FILING
        filed_by = D._header_value(text, D.HEADER_FILED_BY)
        name = (filed_by or "").strip().strip("`*_ .").split()[0] if (filed_by or "").strip() else None
        if name:
            out["filed_by"] = name
        return out
    mode = D.parse_dispatch(D._header_value(text, D.HEADER_DISPATCH))
    if mode["mode"] == D.DISPATCH_HAND:
        out["dispatch_mode"] = D.DISPATCH_HAND
        if mode["launcher"]:
            out["dispatch_launcher"] = mode["launcher"]
    return out


# ---------------------------------------------------------------- the lock

def lock_path(project_dir: Path, config: Optional[dict]) -> Path:
    return Path(project_dir) / settings(config)["lock_file"]


@contextmanager
def filing_lock(project_dir: Path, config: Optional[dict], timeout_s: Optional[float] = None, holder: str = ""):
    """Hold the project's filing lock, waiting up to `timeout_s` (default `filings.lock_wait_s`).

    Raises:
        FilingError: carrying `filing_lock_timeout` and the holder's record, when it is still held at the deadline.
    """
    s = settings(config)
    wait = s["lock_wait_s"] if timeout_s is None else timeout_s
    path = Path(project_dir) / s["lock_file"]
    try:
        lease = D.acquire_waiting(path, wait, extra={"purpose": holder} if holder else None)
    except D.LeaseHeld as held:
        raise FilingError(f"{LOCK_TIMEOUT}: {path} is held by {held.body.get('holder')} "
                          f"({held.body.get('purpose') or 'unnamed'}) past {wait}s") from held
    try:
        yield lease
    finally:
        lease.__exit__(None, None, None)


# ---------------------------------------------------------------- write, commit and register, in one call

def default_name(content: str, today: str) -> str:
    """`<today>_<slug of the title line>.md`, the cc_tasks naming convention."""
    from seldon.core.returns import slug
    title = next((ln.lstrip("#").strip() for ln in content.splitlines() if ln.startswith("#")), "")
    if not title:
        raise FilingError("the content has no `# <title>` line to name the file from; pass a file name")
    return f"{today}_{slug(title)}.md"


def file_task(project_dir: Path, content: str, *, name: Optional[str] = None, actor: str = "cc",
              session_id: Optional[str] = None, emit=None) -> dict:
    """Write `content` to `<project>/cc_tasks/<name>`, commit it through the hooks and register it, under the lock.

    The registration is `register_task_file` with `allow_untracked=True`, which commits the untracked file it accepts
    (AD-036-R12) after every gate, and applies the AD-038-R18 retry, as `seldon cc register` does. A refusal deletes
    the file again, so a refused filing leaves the project's tree as it was. The whole sequence holds the filing
    lock, which the dispatcher's pass takes before it reads the tree.

    Returns:
        The registration's outcome (`register_task_file`'s dict) with `path` and `rel_path`.

    Raises:
        FilingError: a malformed name, a file already there, the lock not acquired, or the registration's refusal.
    """
    from datetime import datetime, timezone

    from seldon.commands.cc import _get_domain_config, register_task_file, retry_mechanical_refusal
    from seldon.config import get_neo4j_driver, load_project_config

    project_dir = Path(project_dir).expanduser().resolve()
    config = load_project_config(project_dir)
    name = name or default_name(content, datetime.now(timezone.utc).date().isoformat())
    if "/" in name or not name.endswith(".md") or name.startswith("."):
        raise FilingError(f"file name {name!r} must be a bare `<YYYY-MM-DD>_<slug>.md` (it is written into cc_tasks/)")
    too_long = name_refusal(project_dir / "cc_tasks", name)
    if too_long:
        raise FilingError(too_long)
    path = project_dir / "cc_tasks" / name
    rel = f"cc_tasks/{name}"
    driver = get_neo4j_driver(config)
    database = config["neo4j"]["database"]
    if D.is_addendum_name(name):
        try:
            return file_addendum(project_dir, config, driver, database, content, name)
        finally:
            driver.close()
    try:
        with filing_lock(project_dir, config, holder=f"seldon cc file {rel}"):
            if path.exists():
                raise FilingError(f"{FILE_EXISTS}: {rel} already exists; nothing was written (a task file is never "
                                  f"overwritten: file a new one, or an ADDENDUM)")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

            def _register(p: Path) -> dict:
                return register_task_file(project_dir=project_dir, config=config, driver=driver, database=database,
                                          domain_config=_get_domain_config(config), session_id=session_id,
                                          task_path=p, actor=actor, allow_untracked=True, emit=emit)
            try:
                try:
                    out = _register(path)
                except ValueError as first:
                    out = retry_mechanical_refusal(project_dir=project_dir, config=config, driver=driver,
                                                   database=database, session_id=session_id, task_path=path,
                                                   refusal=str(first), register=_register, actor=actor)
                    if out is None:
                        raise
            except (ValueError, FileNotFoundError) as exc:
                # Every registration refusal comes before anything is created, so the file goes too: a refused filing
                # left on disk would dirty the tree and the dispatcher would refuse c7 for the whole queue.
                # Only the path this call wrote: a path named inside a refusal's text may be someone else's file.
                if path.exists() and D.git(project_dir, "ls-files", "--error-unmatch", "--", rel).returncode != 0:
                    path.unlink()
                raise FilingError(f"{rel} was refused and removed: {exc}") from exc
    finally:
        driver.close()
    out["path"] = str(project_dir / out["rel_path"])
    return out


# ---------------------------------------------------------------- an addendum, in one call (SEL-040 Part C)

def addendum_base_stem(name: str) -> Optional[str]:
    """The stem of the task an addendum's file name belongs to, or None when the name is not an addendum's."""
    m = _ADDENDUM_BASE_RE.match(Path(name).name)
    return m.group("stem") if m else None


def file_addendum(project_dir: Path, config: dict, driver, database: str, content: str, name: str) -> dict:
    """Write an addendum into cc_tasks/ and commit it, under the filing lock; register nothing (AD-038-R26).

    An addendum belongs to its base task: the dispatcher and the session read it as the task's sibling (the dispatch
    line tells every session to read `<stem>_ADDENDUM*.md`), so it needs no artifact, no candidacy headers and no
    registration gate. What it still may not do is carry a candidacy header (AD-038-R24), and it must belong to a
    task: the base file must exist and be registered (`addendum_without_task` otherwise). A refused or uncommittable
    addendum is removed again, so the tree is left as it was (AD-038-R20's contract).

    Returns ``{artifact_id, base_task, base_file, rel_path, path, addendum, existing, source_commit}``; `artifact_id`
    is the base task's id, the task the addendum amends.
    """
    from seldon.commands.cc import _find_existing

    rel = f"cc_tasks/{name}"
    path = Path(project_dir) / rel
    too_long = name_refusal(path.parent, name)
    if too_long:
        raise FilingError(too_long)
    stem = addendum_base_stem(name)
    if stem is None:
        raise FilingError(f"{name!r} reads as an addendum but not as `<task stem>_ADDENDUM_<NN>[_<slug>].md`; name it "
                          f"after its task's file")
    base_rel = f"cc_tasks/{stem}.md"
    refusal = D.addendum_header_refusal(content)
    if refusal:
        raise FilingError(f"{rel} was refused and not written: {refusal}")
    with filing_lock(project_dir, config, holder=f"seldon cc file {rel}"):
        base_id = _find_existing(driver, database, base_rel) if (Path(project_dir) / base_rel).is_file() else None
        if base_id is None:
            raise FilingError(f"{ADDENDUM_ORPHAN}: {rel} names task file {base_rel}, which "
                              f"{'is not registered' if (Path(project_dir) / base_rel).is_file() else 'does not exist'}"
                              f"; an addendum amends a registered task. Nothing was written.")
        if path.exists():
            raise FilingError(f"{FILE_EXISTS}: {rel} already exists; nothing was written (an addendum is never "
                              f"overwritten: file the next number)")
        path.write_text(content, encoding="utf-8")
        added = D.git(project_dir, "add", "--", rel)
        done = None if added.returncode else D.git(
            project_dir, "commit", "-q", "-m",
            f"addendum: {rel} to task {base_id[:8]} ({stem}), filed in one call (AD-038-R26)", "--", rel)
        if added.returncode or done.returncode:
            failed = added if added.returncode else done
            D.git(project_dir, "rm", "--cached", "-q", "--ignore-unmatch", "--", rel)
            path.unlink()
            raise FilingError(f"{rel} could not be committed and was removed: "
                              f"{(failed.stderr or failed.stdout).strip()[-500:]}")
        sha = D.git(project_dir, "rev-parse", "HEAD").stdout.strip()
    return {"artifact_id": base_id, "base_task": base_id, "base_file": base_rel, "rel_path": rel,
            "path": str(path), "addendum": True, "existing": False, "source_commit": sha}
