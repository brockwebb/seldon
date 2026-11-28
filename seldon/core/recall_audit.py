"""Is recall used? Counted from the dispatched sessions' own logs (SEL-060 Part A).

**Why this exists.** RECALL-001 hands every launched session up to `recall.top_n` hits from the history of its
repository and its neighbours, and measures USE by the RESULT's `Recall used:` line. That line is the session's own
report, and the record of 2026-11-27 (SEL-055: "I opened none of the eight recall hits") said the hits were not even
read. Whether a hit was OPENED is a fact in the session's log, not a report, so this module counts it there.

**Prior art.** Retrieval judged by what the user does with a result, not by its rank: click-through as implicit
relevance feedback (Joachims 2002, "Optimizing search engines using clickthrough data", KDD; Joachims et al. 2005,
"Accurately interpreting clickthrough data as implicit feedback", SIGIR, which shows a click is relative evidence
biased by position and presentation, so the open rate is reported beside the rank it was opened at). Here a "click" is
a tool call that reads the hit; the RESULT's line is the explicit judgment beside it.

**What is counted, per dispatched session** (`<log_dir>/<task stem>.log`, the dispatcher's stream-json transcript):

* HANDED: the hit lines of the launch prompt's Recall block (`  - <kind> ... <id>  <date>  <headline>`), read from
  the log's own `=== <ts> | dispatch | ...` header, so a hit counts only if the session was given it. Every launch
  header in the log is read (a redrive relaunches into the same log); the union is the session's hits.
* OPENED: any tool call (Read, Bash, Grep, Glob, Edit, an Agent's prompt) whose input names the hit: a RESULT or
  task file by its file name (or a glob that matches it), an Issue by its id prefix, a decision record by its local
  id (`AD-031-R3`, `R-266`) or its register file. A decision's design note being read is counted apart
  (`note_read`): sessions read the governing notes anyway, so it is not evidence that the hit was looked at.
* USED: the RESULT's `Recall used:` line names the hit (the `recall_used` record, or the RESULT on disk when the
  dispatcher has not yet read it).

Zero model calls; it reads files only.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import yaml

from seldon.core import recall as RC

#: A launch header the dispatcher writes before each session's transcript (`seldon/commands/dispatch.py`,
#: `dispatch_worktree.py`): `=== <iso timestamp> | <mode> | <command line, the prompt quoted inside it>`.
HEADER_RE = re.compile(r"^=== (?P<ts>\d{4}-\d{2}-\d{2}T[0-9:.]+Z?) \| (?P<mode>[^|]+)\|")
#: One hit line as `recall.Hit.line` renders it: `  - <kind>[ DEAD END][ [status]]  <id>  <date>  <headline>`.
HIT_LINE_RE = re.compile(r"^  - (?P<kind>[a-z_]+)(?P<dead> DEAD END)?(?: \[[^\]]*\])?  (?P<id>\S+)  ")
#: Logs the dispatcher writes beside a session's transcript that are not sessions.
NOT_SESSION_RE = re.compile(r"\.(gate|supervisor|ooda)\.log$")
#: Tools whose input is what the session writes, not what it reads. A Bash `cat > file <<EOF` is still counted: it is
#: rare, and telling it from a read would need a shell parser.
WRITE_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit", "TodoWrite"})
_ISSUE_ID_RE = re.compile(r"issue-(?P<prefix>[0-9a-f]{6,})$")


class AuditError(ValueError):
    """The audit's configuration or a repository it was pointed at cannot be read."""


# ======================================================================================== the repositories

def resolve_ref_map(ref: str, base: Path) -> dict:
    """`{name: absolute path}` from `<file>#<dotted.key>` naming a `{name: path}` map, paths relative to that file.

    The `internal_roots_from` form (SEL-052): the registered repositories come from ONE list, factory's
    `portfolio.repositories`, never a second copy here.

    Raises:
        AuditError: A malformed reference, a missing file or key, or a value that is not a `{name: path}` map.
    """
    if not isinstance(ref, str) or "#" not in ref:
        raise AuditError(f"{ref!r} is not a reference: expected `<file>#<dotted.key>`")
    rel, dotted = ref.split("#", 1)
    written = Path(os.path.expanduser(rel))
    target = (written if written.is_absolute() else Path(base) / written).resolve()
    if not target.is_file():
        raise AuditError(f"{ref!r} names {target}, which does not exist")
    node = yaml.safe_load(target.read_text(encoding="utf-8"))
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            raise AuditError(f"{ref!r}: {target} has no {dotted!r}")
        node = node[part]
    if not isinstance(node, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in node.items()):
        raise AuditError(f"{ref!r} resolves to {node!r}, not a {{name: path}} map")
    out = {}
    for name, path in node.items():
        q = Path(os.path.expanduser(path))
        out[name] = q if q.is_absolute() else (target.parent / q).resolve()
    return out


def registered_repositories(project_dir: Path, config: dict) -> dict:
    """Every registered repository, from `recall.audit.repositories_from` resolved against the primary checkout.

    Raises:
        AuditError: The key is missing or does not resolve.
    """
    from seldon.core import worktree as WT

    block = ((config or {}).get("recall") or {}).get("audit") or {}
    ref = block.get("repositories_from")
    if not ref:
        raise AuditError("seldon.yaml recall.audit.repositories_from is not set (`<file>#<dotted.key>`, the "
                         "portfolio's list of registered repositories)")
    try:
        base = WT.primary_checkout(Path(project_dir))
    except WT.WorktreeError:
        base = Path(project_dir)
    return resolve_ref_map(ref, Path(base).resolve())


def log_dir_of(root: Path) -> Optional[Path]:
    """A repository's dispatch log directory (`dispatch.log_dir` in its seldon.yaml), or None when it declares none."""
    cfg = root / "seldon.yaml"
    if not cfg.is_file():
        return None
    data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    rel = (data.get("dispatch") or {}).get("log_dir")
    if not rel:
        return None
    p = Path(os.path.expanduser(str(rel)))
    return p if p.is_absolute() else root / p


# ================================================================================================ one log

@dataclass
class Session:
    """What one dispatched session's log says: when it launched, what it was handed and every tool input it sent."""
    stem: str
    path: Path
    launches: list = field(default_factory=list)       # ISO timestamps of the launch headers
    handed: dict = field(default_factory=dict)          # hit id -> kind (as the prompt rendered it)
    recall_block: bool = False                          # the prompt carried a Recall block at all
    inputs: list = field(default_factory=list)          # every tool call's input, as one string each
    read_paths: list = field(default_factory=list)      # the file paths file tools named (Read, Edit, Write)


def _tool_inputs(obj: dict) -> Iterable[tuple]:
    msg = obj.get("message") or {}
    for c in msg.get("content") or []:
        if isinstance(c, dict) and c.get("type") == "tool_use":
            yield c.get("name") or "", c.get("input") or {}


def parse_log(path: Path) -> Session:
    """Read one dispatch log: its launch headers' Recall blocks and its sessions' tool calls.

    A line that is neither a header, a hit line of a header, nor a JSON object is skipped: the dispatcher also writes
    its own notes into the log. A JSON line that does not parse is skipped the same way (a killed session can leave a
    torn last line); the count of such lines is not a measure this audit reports.
    """
    s = Session(stem=path.name[:-len(".log")], path=path)
    in_header = False
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = HEADER_RE.match(line)
            if m:
                in_header = m.group("mode").strip() == "dispatch"
                if in_header:
                    s.launches.append(m.group("ts"))
                    if "Recall (RECALL-001)" in line:
                        s.recall_block = True
                continue
            if line.startswith("{"):
                in_header = False
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if obj.get("type") != "assistant":
                    continue
                for name, inp in _tool_inputs(obj):
                    if name in WRITE_TOOLS:
                        # What a session WRITES is not what it read: its RESULT names the hits in `Recall used:`,
                        # and counting that as an open made used-but-never-read hits look opened.
                        continue
                    s.inputs.append(json.dumps(inp, ensure_ascii=False))
                    fp = inp.get("file_path") or inp.get("notebook_path")
                    if fp:
                        s.read_paths.append(str(fp))
                continue
            if in_header:
                if "Recall (RECALL-001)" in line:
                    s.recall_block = True
                h = HIT_LINE_RE.match(line)
                if h:
                    s.handed.setdefault(h.group("id"), h.group("kind"))
    return s


_GLOB_TOKEN_RE = re.compile(r"[^\s\"'`;|&<>()]*[*?][^\s\"'`;|&<>()]*")


#: A glob names one file only when its last component keeps this many literal characters once the wildcards and the
#: suffixes every RESULT shares are taken out: `*SEL-047*` (7) and `2026-11-27_SEL-055_*` name a task, `*.md`,
#: `*_RESULT*.md` and `./.git/*` name every file (the first audit counted those as opening all eight hits).
GLOB_MIN_LITERAL = 7
#: A glob that matches more of the repositories' task files than this is a sweep (`2026-11-27_OODA-0*`), not an
#: open of any one of them. Three: a task's file, its RESULT and one addendum.
GLOB_MAX_MATCHES = 3
_SHARED_SUFFIX_RE = re.compile(r"(?i)(_?result)|(\.md)|(\.markdown)")


def _named(text: str, name: str, universe: frozenset = frozenset()) -> bool:
    """`text` names the file `name` outright, or by a shell glob whose last component matches it and is specific:
    enough literal characters, and (when `universe`, the task files' names, is given) few enough matches in it."""
    if name in text:
        return True
    for tok in _GLOB_TOKEN_RE.findall(text):
        last = tok.replace("\\", "").rstrip("/").rsplit("/", 1)[-1]
        if not last or not any(ch in last for ch in "*?"):
            continue
        literal = _SHARED_SUFFIX_RE.sub("", re.sub(r"[*?]|\[[^\]]*\]", "", last))
        if len(literal) < GLOB_MIN_LITERAL or not fnmatch.fnmatchcase(name, last):
            continue
        if universe and sum(1 for u in universe if fnmatch.fnmatchcase(u, last)) > GLOB_MAX_MATCHES:
            continue
        return True
    return False


def opened(hit: dict, inputs: list, universe: frozenset = frozenset()) -> tuple[bool, bool]:
    """`(opened, note_read)` for one handed hit (its `recall_listed` payload, or `{id, kind}` alone).

    opened: an input names the hit itself. note_read: a decision's design note was named (counted apart).
    """
    hid, kind = hit["id"], hit.get("kind") or ""
    local = hid.split(":", 1)[-1]
    joined = inputs
    if kind in ("result", "worktree_kept", "superseded"):
        names = {f"{local}.md"}
        if hit.get("path"):
            names.add(Path(hit["path"]).name)
        if kind == "result":
            names.add(f"{local}.md")
        return any(_named(t, n, universe) for t in joined for n in names), False
    if kind == "issue":
        m = _ISSUE_ID_RE.search(local)
        prefix = m.group("prefix") if m else local
        return any(prefix in t for t in joined), False
    if kind in ("decision", "catch"):
        repo = hid.split(":", 1)[0]
        rx = re.compile(r"(?<![\w-])" + re.escape(local) + r"(?![\w-])")
        reg = f"{repo}-{local.lower()}_"
        hit_open = any(rx.search(t) or reg in t for t in joined)
        note = Path(hit["path"]).name if hit.get("path") else None
        return hit_open, bool(note) and any(note in t for t in joined)
    return any(local in t for t in joined), False


# ============================================================================================ one repository

def _first_listed(events: list) -> Optional[str]:
    for e in events:
        if e.get("event_type") == RC.EVENT_LISTED:
            return e.get("timestamp")
    return None


def _listed_by_stem(events: list) -> dict:
    """`{task stem: {task_id, hits: {id: hit payload}}}` from every `recall_listed` record (newest wins per hit)."""
    out: dict = {}
    for e in events:
        if e.get("event_type") != RC.EVENT_LISTED:
            continue
        p = e.get("payload") or {}
        src = p.get("source_file") or ""
        if not src:
            continue
        row = out.setdefault(Path(src).stem, {"task_id": p.get("task_id"), "hits": {}})
        row["task_id"] = p.get("task_id") or row["task_id"]
        for h in p.get("hits") or []:
            row["hits"][h["id"]] = h
    return out


def _used_by_task(events: list) -> dict:
    """`{task_id: recall_used payload}`, the newest per task."""
    out = {}
    for e in events:
        if e.get("event_type") == RC.EVENT_USED:
            p = e.get("payload") or {}
            if p.get("task_id"):
                out[p["task_id"]] = p
    return out


def _used_from_result(root: Path, stem: str, handed: set) -> Optional[dict]:
    """The RESULT on disk's reading, for a task the dispatcher has not read yet. None when there is no RESULT."""
    p = root / "cc_tasks" / f"{stem}_RESULT.md"
    if not p.is_file():
        return None
    value = RC.used_value(p.read_text(encoding="utf-8", errors="replace"))
    if value is None:
        return {"used": None, "missing": True}
    try:
        return {"used": RC.parse_used(value, handed), "missing": False}
    except RC.RecallError as exc:
        return {"used": None, "missing": False, "refused": str(exc)}


def task_file_names(roots: Iterable) -> frozenset:
    """Every `cc_tasks/*.md` file name in these repositories: the universe a glob is judged a sweep against."""
    return frozenset(p.name for r in roots if Path(r, "cc_tasks").is_dir() for p in Path(r, "cc_tasks").glob("*.md"))


def audit_repository(name: str, root: Path, universe: frozenset = frozenset()) -> dict:
    """Every dispatched session of one repository since recall was turned on there, with its hits' fates.

    Returns `{repo, recall_on_since, log_dir, sessions: [...], notes: [...]}`; each session row carries
    `{stem, launched, recall_block, hits: [{id, kind, opened, note_read, used, shared_terms, arms, rank}],
    result: used|none|missing|refused|no_result}`.
    """
    from seldon.core.events import read_events

    notes: list = []
    out = {"repo": name, "root": str(root), "recall_on_since": None, "log_dir": None, "sessions": [], "notes": notes}
    if not (root / "seldon_events.jsonl").is_file():
        notes.append("no event store")
        return out
    events = read_events(root)
    since = _first_listed(events)
    out["recall_on_since"] = since
    ld = log_dir_of(root)
    out["log_dir"] = str(ld) if ld else None
    if ld is None or not ld.is_dir():
        notes.append("no dispatch log directory")
        return out
    if since is None:
        notes.append("recall never listed a hit here (no `recall_listed` record)")
        return out
    listed = _listed_by_stem(events)
    used_ev = _used_by_task(events)
    for log in sorted(ld.glob("*.log")):
        if NOT_SESSION_RE.search(log.name):
            continue
        s = parse_log(log)
        if not s.launches or max(s.launches)[:19] < since[:19]:
            continue
        row = listed.get(s.stem) or {"task_id": None, "hits": {}}
        tid = row["task_id"]
        used_payload = used_ev.get(tid) if tid else None
        if used_payload is None:
            used_payload = _used_from_result(root, s.stem, set(s.handed))
        used_ids = set((used_payload or {}).get("used") or [])
        if used_payload is None:
            result = "no_result"
        elif used_payload.get("refused"):
            result = "refused"
        elif used_payload.get("missing"):
            result = "missing"
        else:
            result = "used" if used_ids else "none"
        tf = root / "cc_tasks" / f"{s.stem}.md"
        cites = set(RC.cited(tf.read_text(encoding="utf-8", errors="replace"))) if tf.is_file() else set()
        hits = []
        for rank, (hid, kind) in enumerate(s.handed.items(), 1):
            payload = row["hits"].get(hid) or {"id": hid, "kind": kind}
            op, note = opened(payload, s.inputs, universe)
            local = hid.split(":", 1)[-1]
            ref = local if kind in ("decision", "catch") else RC.task_code(local)
            hits.append({"id": hid, "kind": kind, "rank": rank, "opened": op, "note_read": note,
                         "cited": bool(ref) and ref in cites,
                         "used": hid in used_ids, "shared_terms": len(payload.get("shared_terms") or []),
                         "arms": list(payload.get("arms") or [])})
        out["sessions"].append({"stem": s.stem, "task_id": tid, "launched": min(s.launches),
                                "recall_block": s.recall_block, "hits": hits, "result": result,
                                "tool_calls": len(s.inputs)})
    return out


# ================================================================================================ the table

def _blank() -> dict:
    return {"sessions": 0, "with_hits": 0, "handed": 0, "opened": 0, "used": 0, "used_unopened": 0, "note_read": 0,
            "sessions_opening_any": 0, "sessions_using_any": 0}


def tables(repos: list) -> dict:
    """The baseline: by repository, by hit kind, by rank, by shared-term count and by arm."""
    by_repo, by_kind, by_rank, by_terms, by_arms, by_cited = {}, {}, {}, {}, {}, {}
    total = _blank()
    results = Counter()
    for r in repos:
        row = by_repo.setdefault(r["repo"], _blank())
        for s in r["sessions"]:
            results[s["result"]] += 1
            for t in (row, total):
                t["sessions"] += 1
                t["with_hits"] += int(bool(s["hits"]))
                t["sessions_opening_any"] += int(any(h["opened"] for h in s["hits"]))
                t["sessions_using_any"] += int(any(h["used"] for h in s["hits"]))
            for h in s["hits"]:
                arms = "+".join(sorted(h["arms"])) or "unknown"
                terms = h["shared_terms"] if h["shared_terms"] < 8 else 8
                for t in (row, total, by_kind.setdefault(h["kind"], _blank()),
                          by_rank.setdefault(h["rank"], _blank()), by_terms.setdefault(terms, _blank()),
                          by_arms.setdefault(arms, _blank()),
                          by_cited.setdefault(f"{'cited' if h.get('cited') else 'not cited'} {h['kind']}", _blank())):
                    t["handed"] += 1
                    t["opened"] += int(h["opened"])
                    t["used"] += int(h["used"])
                    t["used_unopened"] += int(h["used"] and not h["opened"])
                    t["note_read"] += int(h["note_read"])
    return {"total": total, "by_repo": by_repo, "by_kind": by_kind, "by_rank": dict(sorted(by_rank.items())),
            "by_shared_terms": dict(sorted(by_terms.items())), "by_arms": by_arms,
            "by_cited": dict(sorted(by_cited.items())), "results": dict(results)}


def _pct(n: int, d: int) -> str:
    return f"{100.0 * n / d:.1f}%" if d else "n/a"


def render_markdown(t: dict, repos: list) -> str:
    """The tables as Markdown, each with its n."""
    lines = []

    def table(title: str, rows: dict, key: str):
        lines.append(f"### {title}\n")
        lines.append(f"| {key} | sessions | handed | opened | opened share | used | used share | used, never opened "
                     f"| design note read |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for k, v in rows.items():
            lines.append(f"| {k} | {v['sessions'] or ''} | {v['handed']} | {v['opened']} | {_pct(v['opened'], v['handed'])}"
                         f" | {v['used']} | {_pct(v['used'], v['handed'])} | {v['used_unopened']} | {v['note_read']} |")
        lines.append("")

    since = {r["repo"]: (r["recall_on_since"] or "never")[:10] for r in repos}
    lines.append("| repository | recall on since | dispatched sessions since | with hits | sessions that opened any "
                 "| sessions whose RESULT used any | notes |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in repos:
        v = t["by_repo"].get(r["repo"], _blank())
        lines.append(f"| {r['repo']} | {since[r['repo']]} | {v['sessions']} | {v['with_hits']} | "
                     f"{v['sessions_opening_any']} | {v['sessions_using_any']} | {'; '.join(r['notes'])} |")
    lines.append("")
    table("Hits by repository", {k: v for k, v in t["by_repo"].items()} | {"**all**": t["total"]}, "repository")
    table("Hits by kind", t["by_kind"], "kind")
    table("Hits the task file itself cites (its code or record id), by kind", t["by_cited"], "cited, kind")
    table("Hits by rank in the list", t["by_rank"], "rank")
    table("Hits by shared query terms (lexical arm; 8 means 8 or more, 0 a served-only hit)", t["by_shared_terms"],
          "shared terms")
    table("Hits by arm", t["by_arms"], "arms")
    lines.append(f"RESULT readings: {', '.join(f'{k} {v}' for k, v in sorted(t['results'].items()))}.")
    return "\n".join(lines) + "\n"


def run(project_dir: Path, config: dict, only: Optional[list] = None) -> dict:
    """Audit every registered repository (or `only` those). A repository that is not on disk is named, not dropped."""
    repos = registered_repositories(project_dir, config)
    universe = task_file_names(repos.values())
    rows = []
    for name, root in repos.items():
        if only and name not in only:
            continue
        if not Path(root).is_dir():
            rows.append({"repo": name, "root": str(root), "recall_on_since": None, "log_dir": None,
                         "sessions": [], "notes": [f"{root} does not exist"]})
            continue
        rows.append(audit_repository(name, Path(root), universe))
    return {"repositories": rows, "tables": tables(rows)}



# ================================================================================ SEL-060 Part C: the replay

#: A RESULT file name inside a tool input: the history a session went and read, whether or not recall handed it.
_RESULT_NAME_RE = re.compile(r"[\w.-]+_(?:RESULT|result)[\w.-]*\.md")


def consulted_results(inputs: list) -> set:
    """The RESULT file names a session's tool calls named: the earlier work it actually consulted."""
    return {m.group(0) for t in inputs for m in _RESULT_NAME_RE.finditer(t)}


def _result_name(hit: dict) -> Optional[str]:
    if hit.get("kind") != "result":
        return None
    return Path(hit["path"]).name if hit.get("path") else f"{hit['id'].split(':', 1)[-1]}.md"


def recent_sessions(root: Path, n: int) -> list:
    """The last `n` dispatched sessions of a repository with a task file on disk, oldest first, by first launch."""
    ld = log_dir_of(root)
    if ld is None or not ld.is_dir():
        return []
    rows = []
    for log in ld.glob("*.log"):
        if NOT_SESSION_RE.search(log.name):
            continue
        s = parse_log(log)
        if s.launches and (root / "cc_tasks" / f"{s.stem}.md").is_file():
            rows.append(s)
    rows.sort(key=lambda s: min(s.launches))
    return rows[-n:]


def checkpoint_rows(path: Path) -> dict:
    """`{key: row}` from a JSONL checkpoint; a torn last line (a killed run) is dropped and that unit re-done."""
    out = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            out[row["key"]] = row
    return out


def _append(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def landed_times(root: Path, rels: Iterable[str]) -> dict:
    """`{path: epoch seconds}`: when each file reached this checkout's history, as the committer time of the first
    commit that added it (`git log --diff-filter=A`; the record of when a file landed, SEL-063, REVIEW-001 F-25).

    Committer time, because the dispatcher rebases a branch onto main just before it merges, so a commit's committer time
    is when it reached main; `--no-renames` so a file renamed into place counts as added there. A path git has never
    recorded (an uncommitted RESULT) has only the file's own time; a path not on disk is 0.0, as before.

    Raises:
        AuditError: git cannot read the repository's history.
    """
    import subprocess

    wanted = sorted(set(rels))
    out = {}
    # A tree that is not a git repository has no history to read: every file's own time is all there is.
    in_git = subprocess.run(["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"], capture_output=True,
                            text=True).stdout.strip() == "true"
    if wanted and in_git:
        dirs = sorted({str(Path(r).parent) for r in wanted})
        proc = subprocess.run(["git", "-C", str(root), "log", "--no-renames", "--diff-filter=A", "--format=%x00%ct",
                               "--name-only", "--", *dirs], capture_output=True, text=True)
        if proc.returncode != 0:
            raise AuditError(f"git log in {root} failed: {proc.stderr.strip()[:300]}")
        want = set(wanted)
        when = None
        # Newest first, so the last addition seen for a path is its first.
        for line in proc.stdout.splitlines():
            if line.startswith("\x00"):
                when = float(line[1:])
            elif line in want and when is not None:
                out[line] = when
    for rel in wanted:
        if rel not in out:
            f = Path(root) / rel
            out[rel] = f.stat().st_mtime if f.is_file() else 0.0
    return out


def replay_repository(name: str, root: Path, recall_block: dict, new_selection: dict, n: int, checkpoint: Path,
                      progress=print) -> list:
    """Re-run registration's recall for the last `n` dispatched tasks of one repository, under the old selection and
    the new, as of each task's launch day, and read each session's log for what it opened and consulted.

    OLD is the `recall_listed` record the task got at its registration when there is one (what the session was in
    fact handed), else RECALL-001's lexical selection replayed with the served arm off (a repository with no recall
    block has no served graph configured for it). NEW is `new_selection`. One row per task is appended to
    `checkpoint` as it completes, keyed by repository, stem and the selection's digest, so re-running the same
    command resumes (constitution section 15); the replay makes no model or network call.
    """
    import hashlib

    from seldon.core.events import read_events

    cfg_path = root / "seldon.yaml"
    config = (yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}) if cfg_path.is_file() else {}
    config = {**config, "recall": recall_block}
    # SEL-063 (REVIEW-001 F-26; constitution section 15.2): the key is derived from every input that decides a row.
    # The recall block decides both sides (its `top_n`, `bm25` and thresholds), so it is hashed with the selection.
    digest = hashlib.sha256(json.dumps({"recall": recall_block, "selection": new_selection}, sort_keys=True,
                                       default=str).encode()).hexdigest()[:12]
    done = checkpoint_rows(checkpoint)
    events = read_events(root) if (root / "seldon_events.jsonl").is_file() else []
    listed = _listed_by_stem(events)
    s = RC.settings(config, root)
    repos = RC.repositories(root, config)
    pool = RC.candidates(repos, s, [])
    universe = task_file_names(repos.values())
    # When each RESULT reached this checkout: a same-day RESULT written after the task launched was not there to be
    # recalled (the first replay "found" OODA-024 for OODA-011).
    # SEL-063 (REVIEW-001 F-25): when it reached the history, not the file's mtime, which a clone or rebase resets.
    by_repo: dict = {}
    for c in pool:
        if c.kind == "result" and c.path and c.repo in repos:
            by_repo.setdefault(c.repo, []).append(c)
    landed = {}
    for repo, cs in by_repo.items():
        times = landed_times(Path(repos[repo]), [c.path for c in cs])
        landed.update({c.id: times[c.path] for c in cs})
    rows = []
    sessions = recent_sessions(root, n)
    for k, sess in enumerate(sessions, 1):
        key = f"{name}:{sess.stem}:{digest}"
        if key in done:
            rows.append(done[key])
            continue
        text = (root / "cc_tasks" / f"{sess.stem}.md").read_text(encoding="utf-8", errors="replace")
        as_of = min(sess.launches)[:10]
        launched = _epoch(min(sess.launches))
        pool_then = [c for c in pool if landed.get(c.id, 0.0) <= launched]
        rec = listed.get(sess.stem)
        if rec and rec["hits"]:
            old = list(rec["hits"].values())
            old_source = "recorded"
        else:
            old = [h.__dict__ for h in RC.recall(root, config, text, task_stem=sess.stem, as_of=as_of,
                                                 use_served=False, selection={"mode": "lexical"}, pool=pool_then).hits]
            old_source = "replayed"
        tid = (rec or {}).get("task_id")
        new = [h.__dict__ for h in RC.recall(root, config, text, task_stem=sess.stem, task_id=tid, as_of=as_of,
                                             selection=new_selection, pool=pool_then).hits]
        consulted = consulted_results(sess.inputs)

        def fate(hits):
            return [{"id": h["id"], "kind": h["kind"], "why": h.get("why") or "",
                     "opened": opened(h, sess.inputs, universe)[0]} for h in hits]

        row = {"key": key, "repo": name, "stem": sess.stem, "as_of": as_of, "old_source": old_source,
               "old": fate(old), "new": fate(new), "consulted": sorted(consulted),
               "consulted_in_old": sorted(consulted & {x for x in map(_result_name, old) if x}),
               "consulted_in_new": sorted(consulted & {x for x in map(_result_name, new) if x})}
        _append(checkpoint, row)
        rows.append(row)
        progress(f"replay {name} {k}/{len(sessions)} {sess.stem[:60]}: old {len(old)} ({old_source}), "
                 f"new {len(new)}")
    return rows


def _epoch(ts: str) -> float:
    from datetime import datetime, timezone

    return datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=timezone.utc).timestamp()


def replay_summary(rows: list) -> dict:
    """Per repository: hits per task under each selection, how many were opened, and how much of the history the
    sessions consulted each selection held."""
    out = {}
    for r in rows:
        t = out.setdefault(r["repo"], {"tasks": 0, "old_recorded": 0, "old_hits": 0, "new_hits": 0, "old_opened": 0,
                                       "new_opened": 0, "old_empty": 0, "new_empty": 0, "consulted": 0,
                                       "consulted_in_old": 0, "consulted_in_new": 0})
        t["tasks"] += 1
        t["old_recorded"] += int(r["old_source"] == "recorded")
        for side in ("old", "new"):
            t[f"{side}_hits"] += len(r[side])
            t[f"{side}_opened"] += sum(1 for h in r[side] if h["opened"])
            t[f"{side}_empty"] += int(not r[side])
        t["consulted"] += len(r["consulted"])
        t["consulted_in_old"] += len(r["consulted_in_old"])
        t["consulted_in_new"] += len(r["consulted_in_new"])
    return out
