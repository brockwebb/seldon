"""A task that answers a consumer's filing files its own return task in the consumer's repository (AD-036-R16, SEL-013R).

**Why this exists.** Four hazbrief filings into squiddy were answered by squiddy tasks whose RESULTs ended "For
hazbrief: paste these steps". The answer went back through the operator's clipboard, and a Desktop then wrote
hazbrief HB-63 and HB-64 and ai-readiness-kg's re-pin task by hand. The dispatcher already crossed repositories
(AD-034-R12 pushes there; AD-036-R12 registers a filing there). The return path did not exist as a rule.

**The rule, in three parts.**

1. A task that answers a filing from another repository carries ``**Answers:** <repo>:<ref>``. Registration resolves
   the ref in that repository's graph and refuses one that does not resolve (``answers_unresolved``), and records the
   resolved filing on the task (``answers_external``).
2. ``seldon cc complete`` refuses such a task (``return_unfiled``) until a return task exists in the consumer's
   ``cc_tasks/``, registered in its graph and committed in its repository. The return names the answering task in its
   ``**Returns:**`` header, which is how it is found.
3. ``seldon cc return`` writes that file from the RESULT's ``For <consumer>`` section and registers it there through
   the one registrar (``register_task_file``, AD-036-R12), numbered by the consumer's own allocator (AD-038-R13).
   The dispatcher's finish step runs the same writer when the session did not.

**Prior art.** This is Request-Reply with a Return Address and a Correlation Identifier (Hohpe and Woolf, *Enterprise
Integration Patterns*, 2003, chapters "Request-Reply", "Return Address", "Correlation Identifier"): the request says
where the reply goes, and the reply carries the id of the request it answers so the requester can match it. Here the
``Answers:`` header is the correlation identifier and its qualifier is the return address; the return's ``Returns:``
header is the reply's correlation id, pointing back at the answering task. The departure: the reply is not a message
on a channel but a task file in the requester's own queue, held to the requester's own admission checks, because the
requester's dispatcher is what acts on it. Internal: cross-project waits (AD-038-R8, ``seldon.core.cross_project``)
resolve a ``<project>:<ref>`` in the other graph the same way, and this module uses that resolver.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# The answering task's header is parsed by the dispatcher's static checks; one grammar, read by both.
from seldon.core.dispatch import (
    ANSWERS_GRAMMAR, ANSWERS_UNRESOLVED, HEADER_ANSWERS, _header_value, parse_answers,
)

#: The return task's header naming the answering task: `<producer>:<artifact_id> (<token>)`.
HEADER_RETURNS = "Returns"

#: The ResearchTask property registration records the resolved filing in (`seldon/domain/research.yaml`).
PROPERTY = "answers_external"

#: `cc complete`'s refusal code, and the dispatcher's block reason, when no return is filed.
RETURN_UNFILED = "return_unfiled"

#: The consumer's open states, of which the latest registered task becomes the return's `After:` (AD-029). `blocked`
#: is open: a return queued behind a held task waits with it rather than jumping the consumer's own order.
OPEN_STATES = ("proposed", "accepted", "in_progress", "blocked")

#: Candidacy headers a return carries when neither the RESULT's section nor `returns.headers` in the producer's
#: seldon.yaml sets one. Each is the value most returns need: applying a landed change is a small, local task. The
#: section overrides any of them; `returns.headers` overrides these for a project. Order is the header order written.
DEFAULT_HEADERS = {
    "Spend": "est. 0.1M tokens. Basis: applying a change another repository landed; no model calls of its own.",
    "Network": "none beyond git.",
    "Framework layer served (DN-005 §5 rule 1)": "none (machine infrastructure).",
    "Parts": "A 1.00.",
}

#: Headers the writer owns. A section that sets one is refused: these say who wrote the return and what it answers.
OWNED_HEADERS = ("Status", "Author", HEADER_RETURNS, HEADER_ANSWERS)

#: Longest slug a return's filename carries, so a long title does not make an unwieldy path.
SLUG_MAX = 70

_SECTION_HEADING_RE = re.compile(r"^(?P<hashes>#{1,6})\s+For\s+(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)\b(?P<rest>.*)$",
                                 re.IGNORECASE)
_ANY_HEADING_RE = re.compile(r"^(?P<hashes>#{1,6})\s")
_SECTION_HEADER_RE = re.compile(r"^\*\*(?P<name>[A-Za-z][^*\n]*?):\*\*\s*(?P<value>.*)$")
_RETURNS_VALUE_RE = re.compile(r"^[\s`]*(?P<project>[A-Za-z0-9][A-Za-z0-9._-]*):(?P<id>[0-9a-f-]{36})\b")
_TOKEN_REF_RE = re.compile(r"^[A-Z][A-Z0-9]*-\d+[A-Za-z0-9]*$")


class ReturnError(RuntimeError):
    """A return that cannot be written or registered; the message names the cause and the fix."""


@dataclass
class Answered:
    """What a task's `Answers:` header names, resolved."""

    project: str
    ref: str
    root: Path
    artifact_id: str
    source_file: Optional[str]

    @property
    def qualified(self) -> str:
        return f"{self.project}:{self.artifact_id}"

    @property
    def token(self) -> Optional[str]:
        from seldon.core.numbering import file_token
        tok = file_token(self.source_file) if self.source_file else None
        return str(tok) if tok else (self.ref if _TOKEN_REF_RE.match(self.ref) else None)

    @property
    def label(self) -> str:
        return f"{self.project}:{self.token or self.artifact_id[:8]}"


@dataclass
class Found:
    """A return task found in the consumer's cc_tasks/."""

    rel_path: str
    registered: Optional[str] = None
    committed: Optional[str] = None
    problems: list = field(default_factory=list)


# ---------------------------------------------------------------- the header

def answers_of(text: str) -> dict:
    """The task's Answers header, parsed (`seldon.core.dispatch.parse_answers`)."""
    return parse_answers(_header_value(text, HEADER_ANSWERS))


def producer_name(project_dir: Path) -> str:
    """This repository's name as a sibling would qualify it: the primary checkout's directory name."""
    from seldon.core.cross_project import _anchor
    return _anchor(Path(project_dir)).name


def resolve_answers(text: str, project_dir: Path, config: Optional[dict]) -> Optional[Answered]:
    """The filing the task's Answers header names, resolved in the consumer's graph (read, never written).

    A task number (`HB-37`) resolves to the one ResearchTask holding it, an exact token first (`HB-37R` names the
    re-filing), else its identity; anything else resolves as an After ref does (a cc_tasks stem or an id prefix).

    Returns:
        None when the task carries no Answers header.

    Raises:
        ValueError: carrying `answers_unresolved`, when the header does not parse, the repository is not a Seldon
            project, or the ref names no task or more than one.
    """
    from seldon.core import cross_project as X

    parsed = answers_of(text)
    if parsed["kind"] == "absent":
        return None
    if parsed["kind"] is None:
        raise ValueError(f"{ANSWERS_UNRESOLVED}: {parsed['error']}")
    project, ref = parsed["project"], parsed["ref"]
    try:
        driver, database, root = X._open(project, project_dir, config)
    except ValueError as exc:
        raise ValueError(f"{ANSWERS_UNRESOLVED}: Answers {project}:{ref}: {exc}") from exc
    try:
        aid, src = _resolve_in(driver, database, ref)
    except ValueError as exc:
        raise ValueError(f"{ANSWERS_UNRESOLVED}: Answers {project}:{ref}: {exc} (in {root}). "
                         f"Grammar: {ANSWERS_GRAMMAR}.") from exc
    finally:
        driver.close()
    return Answered(project=project, ref=ref, root=root, artifact_id=aid, source_file=src)


def _resolve_in(driver, database: str, ref: str) -> tuple:
    from seldon.commands.cc import resolve_after_refs
    from seldon.core import numbering as N

    if _TOKEN_REF_RE.match(ref):
        holders = N.graph_holders(driver, database)
        exact = [h for h in holders if str(h.token) == ref]
        same = exact or [h for h in holders if h.token.identity == ref]
        if len(same) == 1:
            return same[0].artifact_id, same[0].source_file
        if len(same) > 1:
            raise ValueError(f"task number {ref} is held by {len(same)} tasks: "
                             f"{'; '.join(h.describe() for h in same)}; name one by its id prefix")
    (aid,) = resolve_after_refs(driver, database, [ref])
    with driver.session(database=database) as s:
        row = s.run("MATCH (t:Artifact:ResearchTask {artifact_id: $id}) RETURN t.source_file AS f", id=aid).single()
    return aid, (row["f"] if row else None)


# ---------------------------------------------------------------- finding a return

def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def returns_value(text: str) -> Optional[tuple]:
    """`(producer, artifact_id)` from a task file's Returns header, or None."""
    value = _header_value(text, HEADER_RETURNS)
    m = _RETURNS_VALUE_RE.match(value or "")
    return (m["project"], m["id"]) if m else None


def find_return(consumer_root: Path, producer: str, task_id: str) -> Optional[Found]:
    """The return task in the consumer's cc_tasks/ whose Returns header names `<producer>:<task_id>`, with whether
    the consumer's graph registers it and its repository has it committed. None when there is no such file."""
    from seldon.config import get_neo4j_driver, load_project_config

    task_dir = Path(consumer_root) / "cc_tasks"
    hits = []
    for p in sorted(task_dir.glob("*.md")) if task_dir.is_dir() else []:
        if p.stem.endswith("_RESULT") or "_ADDENDUM" in p.stem:
            continue
        if returns_value(p.read_text(encoding="utf-8", errors="replace")) == (producer, task_id):
            hits.append(p)
    if not hits:
        return None
    path = hits[-1]
    rel = str(path.relative_to(consumer_root))
    found = Found(rel_path=rel)
    if len(hits) > 1:
        found.problems.append(f"{len(hits)} files return this task ({', '.join(h.name for h in hits)})")
    cfg = load_project_config(Path(consumer_root))
    driver = get_neo4j_driver(cfg)
    try:
        with driver.session(database=cfg["neo4j"]["database"]) as s:
            row = s.run("MATCH (t:Artifact:ResearchTask {source_file: $f}) RETURN t.artifact_id AS id LIMIT 1",
                        f=rel).single()
    finally:
        driver.close()
    found.registered = row["id"] if row else None
    if not found.registered:
        found.problems.append(f"{rel} is not registered in {Path(consumer_root).name}'s graph")
    last = _git(Path(consumer_root), "log", "-1", "--format=%H", "--", rel)
    dirty = _git(Path(consumer_root), "status", "--porcelain", "--", rel)
    if last.returncode == 0 and last.stdout.strip() and not dirty.stdout.strip():
        found.committed = last.stdout.strip()
    else:
        found.problems.append(f"{rel} is not committed in {Path(consumer_root).name}"
                              + (f" ({dirty.stdout.strip()})" if dirty.stdout.strip() else ""))
    return found


def completion_refusal(project_dir: Path, config: Optional[dict], task_path: Path,
                       task_id: Optional[str]) -> Optional[str]:
    """`cc complete`'s gate: None for a task with no Answers header, or whose return is registered and committed in
    the consumer's repository; otherwise the `return_unfiled` refusal naming what is missing and the one command."""
    text = Path(task_path).read_text(encoding="utf-8", errors="replace")
    try:
        answered = resolve_answers(text, project_dir, config)
    except ValueError as exc:
        return f"{RETURN_UNFILED}: {exc}"
    if answered is None:
        return None
    fix = f"`seldon cc return {_rel(project_dir, task_path)} --to {answered.project}`"
    if task_id is None:
        return (f"{RETURN_UNFILED}: this task answers {answered.label} and is not registered, so no return can name "
                f"it; register it, then run {fix}")
    found = find_return(answered.root, producer_name(project_dir), task_id)
    if found is None:
        return (f"{RETURN_UNFILED}: this task answers {answered.label}, and no task in {answered.root}/cc_tasks/ "
                f"returns it (a `**{HEADER_RETURNS}:** {producer_name(project_dir)}:{task_id}` header). Run {fix}")
    if found.problems:
        return f"{RETURN_UNFILED}: the return {found.rel_path} for {answered.label}: {'; '.join(found.problems)}"
    return None


def _rel(project_dir: Path, path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(Path(project_dir).resolve()))
    except ValueError:
        return str(path)


# ---------------------------------------------------------------- the RESULT's section

def consumer_names(answered: Answered) -> set:
    """Every name a RESULT's `For <name>` heading may use for the consumer: its directory, project name and slug."""
    from seldon.config import load_project_config
    names = {answered.project.lower(), Path(answered.root).name.lower()}
    project = (load_project_config(Path(answered.root)).get("project") or {})
    names |= {str(project.get(k)).lower() for k in ("name", "slug") if project.get(k)}
    return names


def consumer_section(result_text: str, names: set) -> Optional[dict]:
    """The RESULT's `For <consumer>` section: `{heading, headers, body}`, or None when it has none.

    The heading is any level, `For <name>` with anything after the name (`## For hazbrief: what it does`). The
    section runs to the next heading of the same or a higher level. Bold header lines at its top (`**Spend:** ...`)
    set the return's headers; the rest, verbatim, is what the consumer does.
    """
    lines = result_text.splitlines()
    for i, line in enumerate(lines):
        m = _SECTION_HEADING_RE.match(line)
        if not m or m["name"].lower() not in names:
            continue
        level = len(m["hashes"])
        end = len(lines)
        for j in range(i + 1, len(lines)):
            h = _ANY_HEADING_RE.match(lines[j])
            if h and len(h["hashes"]) <= level:
                end = j
                break
        rest = lines[i + 1:end]
        headers, k = {}, 0
        while k < len(rest) and not rest[k].strip():
            k += 1
        while k < len(rest):
            hm = _SECTION_HEADER_RE.match(rest[k].strip())
            if not hm:
                break
            headers[hm["name"].strip()] = hm["value"].strip()
            k += 1
        body = "\n".join(rest[k:]).strip()
        return {"heading": line.strip(), "headers": headers, "body": body}
    return None


# ---------------------------------------------------------------- writing one

def _title_of(task_text: str) -> str:
    from seldon.commands.cc import _H1_RE, _subject_from_h1
    for line in task_text.splitlines():
        m = _H1_RE.match(line)
        if m:
            subject = _subject_from_h1(m.group(1))
            # A leading `<TOKEN>:` names the producer's task, not the return's subject.
            return re.sub(r"^[A-Z][A-Z0-9]*-\d+[A-Za-z0-9]*\s*:\s*", "", subject).strip()
    return ""


def slug(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    return s[:SLUG_MAX].rstrip("_") or "return"


def latest_open(driver, database: str) -> Optional[str]:
    """The stem of the consumer's most recently registered open task with a file, or None."""
    with driver.session(database=database) as s:
        row = s.run("MATCH (t:Artifact:ResearchTask) WHERE t.state IN $open AND t.source_file IS NOT NULL "
                    "AND t.source_file STARTS WITH 'cc_tasks/' "
                    "RETURN t.source_file AS f ORDER BY t.created_at DESC LIMIT 1", open=list(OPEN_STATES)).single()
    return Path(row["f"]).stem if row else None


def _prefix_for(answered: Answered, prefix: Optional[str]) -> str:
    if prefix:
        return prefix.strip().upper()
    from seldon.core.numbering import file_token
    tok = file_token(answered.source_file) if answered.source_file else None
    if tok is None and _TOKEN_REF_RE.match(answered.ref):
        return answered.ref.split("-", 1)[0]
    if tok is None:
        raise ReturnError(f"{answered.label} carries no task number, so the consumer's prefix is unknown; pass "
                          f"--prefix (the prefix {answered.project}'s task files use)")
    return tok.prefix


def render(*, token: str, title: str, producer: str, task_id: str, task_token: Optional[str], task_rel: str,
           result_rel: str, commit: Optional[str], where: str, answered: Answered, after: Optional[str],
           headers: dict, body: str, date: str) -> str:
    """The return task file's text."""
    named = task_token or task_id[:8]
    out = [f"# {token}: {title}", "",
           "**Status:** proposed",
           f"**Author:** `seldon cc return`, {date}, for {producer} {named} ({task_id[:8]}), which answered "
           f"{answered.label} (AD-036-R16).",
           f"**{HEADER_RETURNS}:** {producer}:{task_id} ({named})",
           f"**After:** {after or 'none'}"]
    out += [f"**{k}:** {v}" for k, v in headers.items()]
    out += ["", f"{answered.label} ({answered.artifact_id[:8]}) was filed into {producer}; {producer} task {named} "
                f"({task_id[:8]}) answered it. This task is that answer's return, filed by the answering task "
                f"rather than pasted by hand (AD-036-R16).", "",
            "## What landed, and where", "",
            f"- The answering task: `{producer}/{task_rel}`.",
            f"- Its RESULT: `{producer}/{result_rel}`. Read it in full before starting.",
            f"- The commit: {producer}@{commit or 'unknown'} ({where}).", "",
            f"## What {answered.project} does with it", "",
            body, ""]
    return "\n".join(out)


def write_return(project_dir: Path, config: Optional[dict], task_path: Path, task_id: str, *,
                 to: Optional[str] = None, prefix: Optional[str] = None, dry_run: bool = False,
                 result_path: Optional[Path] = None, actor: str = "cc", emit=None) -> dict:
    """Write and register the return of the task at `task_path` (registered as `task_id`) in its consumer.

    The file is written into the consumer's primary checkout and registered there by `register_task_file`, which
    commits it (AD-036-R12) and applies every gate the consumer's registration applies (the candidacy headers, the
    number, the After ref). An existing return is reported, not written twice.

    Returns:
        `{status, rel_path, consumer, artifact_id, token, text}`; `status` is `existing`, `written` or `dry_run`.

    Raises:
        ReturnError: no Answers header, `to` names another repository, no RESULT or no `For <consumer>` section in
            it, a section that sets a header the writer owns, or a registration the consumer refused (the file is
            removed again, so a refusal leaves the consumer's tree as it was).
    """
    from seldon.commands.cc import _get_domain_config, register_task_file
    from seldon.config import get_neo4j_driver, load_project_config
    from seldon.core import numbering as N

    say = emit or (lambda _m: None)
    project_dir = Path(project_dir)
    task_path = Path(task_path)
    text = task_path.read_text(encoding="utf-8", errors="replace")
    try:
        answered = resolve_answers(text, project_dir, config)
    except ValueError as exc:
        raise ReturnError(str(exc)) from exc
    if answered is None:
        raise ReturnError(f"{_rel(project_dir, task_path)} carries no `**{HEADER_ANSWERS}:**` header, so it answers "
                          f"no filing and has no consumer to return to. Grammar: {ANSWERS_GRAMMAR}.")
    if to and to not in (answered.project, Path(answered.root).name):
        raise ReturnError(f"--to {to} is not the repository the task answers ({answered.label})")
    producer = producer_name(project_dir)
    existing = find_return(answered.root, producer, task_id)
    if existing is not None:
        return {"status": "existing", "rel_path": existing.rel_path, "consumer": str(answered.root),
                "artifact_id": existing.registered, "problems": existing.problems, "token": None, "text": None}

    task_rel = _rel(project_dir, task_path)
    result_path = result_path or task_path.with_name(f"{task_path.stem}_RESULT.md")
    if not result_path.is_file():
        raise ReturnError(f"no RESULT at {_rel(project_dir, result_path)}: the return is written from its "
                          f"`## For {answered.project}` section")
    section = consumer_section(result_path.read_text(encoding="utf-8", errors="replace"), consumer_names(answered))
    if section is None or not section["body"]:
        raise ReturnError(f"{_rel(project_dir, result_path)} has no `## For {answered.project}` section with a body; "
                          f"it states what {answered.project} does with what landed, and the return is written "
                          f"from it")
    owned = [k for k in section["headers"] if k in OWNED_HEADERS or k == "After"]
    if owned:
        raise ReturnError(f"the `For {answered.project}` section sets {', '.join(owned)}, which the writer owns "
                          f"(who wrote the return, what it returns, and the consumer's own order)")
    title = section["headers"].pop("Title", None) or _title_of(text) or f"the return of {answered.label}"
    headers = {**DEFAULT_HEADERS, **(((config or {}).get("returns") or {}).get("headers") or {}),
               **section["headers"]}

    from seldon.core.numbering import file_token
    task_token = file_token(task_rel)
    head = _git(project_dir, "rev-parse", "HEAD")
    branch = _git(project_dir, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    commit = head.stdout.strip() if head.returncode == 0 else None
    main = ((config or {}).get("dispatch") or {}).get("branch", "main")
    where = (f"on {main}" if branch == main
             else f"on branch {branch}, which the dispatcher merges to {main}")

    ccfg = load_project_config(answered.root)
    driver = get_neo4j_driver(ccfg)
    database = ccfg["neo4j"]["database"]
    try:
        alloc = N.allocate(answered.root, driver, database, _prefix_for(answered, prefix))
        token = alloc["token"]
        after = latest_open(driver, database)
        date = datetime.now(timezone.utc).date().isoformat()
        body = render(token=token, title=title, producer=producer, task_id=task_id,
                      task_token=str(task_token) if task_token else None, task_rel=task_rel,
                      result_rel=_rel(project_dir, result_path), commit=commit, where=where, answered=answered,
                      after=after, headers=headers, body=section["body"], date=date)
        rel = f"cc_tasks/{date}_{token}_{slug(title)}.md"
        out = {"status": "dry_run", "rel_path": rel, "consumer": str(answered.root), "artifact_id": None,
               "token": token, "text": body}
        if dry_run:
            return out
        path = answered.root / rel
        if path.exists():
            raise ReturnError(f"{path} already exists and does not return this task; nothing was written")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        try:
            reg = register_task_file(project_dir=answered.root, config=ccfg, driver=driver, database=database,
                                     domain_config=_get_domain_config(ccfg), session_id=None, task_path=path,
                                     actor=actor, allow_untracked=True, emit=say)
        except (ValueError, FileNotFoundError) as exc:
            # Refused before anything was created there (every registration refusal is), so the file goes too:
            # a refused return left on disk would dirty the consumer's tree and its dispatcher would refuse c7.
            path.unlink(missing_ok=True)
            raise ReturnError(f"{answered.project} refused the return {rel}: {exc}") from exc
    finally:
        driver.close()
    found = find_return(answered.root, producer, task_id)
    out.update(status="written", artifact_id=reg["artifact_id"],
               problems=found.problems if found else [f"{rel} was written but is not found as a return"])
    return out
