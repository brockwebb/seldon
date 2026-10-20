"""Recall at registration: the repositories' own history, put in front of the task (RECALL-001).

**Why this exists.** AD-031-R1 says the rulings reach a task by retrieval from the governed graph,
and registration does that for RULINGS (`constrained_by`). The operator asked for more on 2026-10-02
and again on 2026-10-17: "have we tried this before, has this worked in the past". The record
already holds the answer, and nothing surfaced it at the point of decision: prior RESULTs, Issues
open and resolved, decision records, and the branches the dispatcher kept because they failed.
Squiddy DN-009 R-40 / EX-REQ-13 make internal precedent half of prior art. This module retrieves
that precedent when a task is registered, prints it, records it, and hands it to the launched
session ahead of CLAUDE.md. A second record, the RESULT's `Recall used:` line, measures whether a
hit changed the task (Part B), and that number decides whether a cross-agent knowledge exchange is
worth building.

**Prior art, adopted.** This is the retrieve step of case-based reasoning (Aamodt and Plaza 1994,
"Case-Based Reasoning: Foundational Issues", the retrieve / reuse / revise / retain cycle), and the
"active delivery" finding of lessons-learned systems (Weber, Aha and Becerra-Fernandez 2001,
"Intelligent lessons learned systems"): a repository a user must remember to query is rarely
queried, so the lesson is pushed into the process at the decision point. The agent-memory form of
the same cycle is ReMe (arXiv 2512.10696, in the squiddy library: retrieval, reranking and
rewriting of past experience before a step). What RECALL-001 adds is the measurement: a hit is
counted as USED only when the RESULT names it, so the chart reads the reuse rate rather than the
retrieval rate.

**Retrieval.** Two arms, zero model calls:

* the LEXICAL arm, Okapi BM25 (Robertson and Zaragoza 2009, textbook k1 and b from `recall.bm25`)
  over every candidate below, with Seldon's own tokenizer (`seldon.core.governed`'s word pattern
  and stop list, so recall and ruling binding read text the same way). A candidate must share
  `recall.min_shared_terms` distinct query terms with the task, so a task with no history prints
  `Recall: none` rather than the top of an arbitrary ranking;
* the SERVED arm, squiddy's hybrid `search` verb (FTS5 BM25 plus the pinned dense encoder, DN-025
  R-110) over each repository's governed graph named in `recall.served.graphs`. A served hit that
  is a RESULT document joins the same candidate; the two rankings are fused by reciprocal rank
  fusion (Cormack, Clarke and Buettcher 2009), k from config, the value squiddy itself uses.

An arm that cannot run (no index built, a broken register, a sibling missing) is NAMED in the
Recall block and in the record; it never drops out silently.

**Candidates**, per repository (this one, then each `decisions.repositories` sibling):

* ``result``: every file matching `recall.result_globs` (a task's RESULT);
* ``issue``: every Issue artifact folded from the repository's event store, open or resolved;
* ``decision`` (``catch`` for an operator catch, Part C): every record in its decision register,
  whatever its status, since a rejected or superseded decision is history too;
* ``worktree_kept`` and ``superseded``: tasks whose branch the dispatcher kept, or which were
  walked to superseded, with the reason the record gives. One whose reason names a failure
  (`recall.failure_terms`) is marked ``dead end``.

The query is the task's title, its premises and its Part headings (the task file's own statement of
what it is about); the task's own files are excluded.

**Records.** `recall_listed` (registration: the hits, the arms, the notes) and `recall_used` (the
RESULT's line, at `cc complete` or at the dispatcher's merge). Both are audit-only events: the
chart reads them, nothing projects them.
"""
from __future__ import annotations

import math
import os
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import yaml

#: Event types this module writes. Audit-only (`seldon.core.sync`): no graph node is projected.
EVENT_LISTED = "recall_listed"
EVENT_USED = "recall_used"

#: The RESULT line Part B requires. A task registered with a `recall_listed` record owes it.
USED_LINE_RE = re.compile(r"^[ \t>*-]*\**Recall used\**\s*:\**\s*(?P<value>.*)$", re.IGNORECASE | re.MULTILINE)

#: Kinds a hit can be. The order is the render order of the legend, not a ranking.
KINDS = ("result", "issue", "decision", "catch", "worktree_kept", "superseded")
DEAD_END_KINDS = frozenset({"worktree_kept", "superseded"})

#: The `recall:` keys every project that turns recall on must set. A missing key is a configuration
#: error named at registration, never a default the reader cannot see.
_REQUIRED = ("top_n", "min_shared_terms", "max_file_bytes", "headline_chars", "result_globs",
             "failure_terms", "bm25", "served")

_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
_PREMISE_RE = re.compile(r"^\s*-\s*premise:\s*(?P<text>[^|\n]+)", re.MULTILINE | re.IGNORECASE)
_PART_RE = re.compile(r"^##\s+Part\s+[^:\n]+:\s*(?P<text>.+?)\s*$", re.MULTILINE)


class RecallError(ValueError):
    """The `recall:` block is malformed, or a RESULT's `Recall used:` line is refused."""


@dataclass(frozen=True)
class Settings:
    top_n: int
    min_shared_terms: int
    max_file_bytes: int
    headline_chars: int
    result_globs: tuple
    failure_terms: tuple
    k1: float
    b: float
    served_enabled: bool
    served_k: int
    rrf_k: int
    served_graphs: dict


def settings(config: dict) -> Optional[Settings]:
    """The `recall:` block of seldon.yaml, validated, or None when the project has not turned recall on.

    Raises:
        RecallError: The block is present and a key is missing or malformed.
    """
    block = (config or {}).get("recall")
    if block is None:
        return None
    if not isinstance(block, dict):
        raise RecallError("seldon.yaml recall: must be a mapping")
    missing = [k for k in _REQUIRED if k not in block]
    if missing:
        raise RecallError(f"seldon.yaml recall: block missing {missing}")
    served = block["served"] or {}
    miss = [k for k in ("enabled", "k", "rrf_k", "graphs") if k not in served]
    if miss:
        raise RecallError(f"seldon.yaml recall.served missing {miss}")
    try:
        s = Settings(top_n=int(block["top_n"]), min_shared_terms=int(block["min_shared_terms"]),
                     max_file_bytes=int(block["max_file_bytes"]), headline_chars=int(block["headline_chars"]),
                     result_globs=tuple(block["result_globs"]), failure_terms=tuple(block["failure_terms"]),
                     k1=float(block["bm25"]["k1"]), b=float(block["bm25"]["b"]),
                     served_enabled=bool(served["enabled"]), served_k=int(served["k"]),
                     rrf_k=int(served["rrf_k"]), served_graphs=dict(served["graphs"] or {}))
    except (TypeError, ValueError, KeyError) as exc:
        raise RecallError(f"seldon.yaml recall: block is malformed: {exc}") from exc
    if s.top_n < 1 or s.min_shared_terms < 1:
        raise RecallError("seldon.yaml recall.top_n and recall.min_shared_terms must be at least 1")
    return s


# ================================================================================================ the query

def query_of(task_text: str) -> str:
    """The task's title, premises and Part headings: what the task file says it is about."""
    parts = []
    m = _H1_RE.search(task_text or "")
    if m:
        parts.append(m.group(1))
    parts.extend(p.group("text").strip() for p in _PREMISE_RE.finditer(task_text or ""))
    parts.extend(p.group("text").strip() for p in _PART_RE.finditer(task_text or ""))
    return "\n".join(x for x in parts if x)


def tokens(text: str) -> list[str]:
    """Seldon's tokenizer (`seldon.core.governed`): lowercased words of three or more characters, stop terms out."""
    from seldon.core.governed import STOP_TERMS, _WORD_RE

    return [w for w in (t.lower() for t in _WORD_RE.findall(text or "")) if w not in STOP_TERMS]


# =========================================================================================== the candidates

@dataclass
class Candidate:
    kind: str
    id: str
    date: str
    headline: str
    repo: str
    text: str
    path: Optional[str] = None
    status: Optional[str] = None
    reason: Optional[str] = None
    dead_end: bool = False
    task_id: Optional[str] = None


@dataclass
class Hit:
    kind: str
    id: str
    date: str
    headline: str
    repo: str
    path: Optional[str]
    status: Optional[str]
    dead_end: bool
    score: float
    shared_terms: list
    arms: list

    def line(self) -> str:
        """One line: kind, id, date, headline (the task's Part A step 2)."""
        kind = f"{self.kind} DEAD END" if self.dead_end else self.kind
        status = f" [{self.status}]" if self.status and self.kind in ("issue", "decision", "catch",
                                                                       "worktree_kept", "superseded") else ""
        return f"  - {kind}{status}  {self.id}  {self.date or '?'}  {self.headline}"


@dataclass
class Recall:
    query: str
    hits: list
    notes: list = field(default_factory=list)
    repositories: dict = field(default_factory=dict)

    def as_payload(self) -> dict:
        return {"query": self.query, "hits": [asdict(h) for h in self.hits], "notes": list(self.notes),
                "repositories": {k: str(v) for k, v in self.repositories.items()}}


def _clip(text: str, n: int) -> str:
    one = " ".join((text or "").split())
    return one if len(one) <= n else one[: n - 3].rstrip() + "..."


def _date_of(name: str) -> str:
    m = _DATE_RE.search(name or "")
    return m.group(1) if m else ""


def repositories(project_dir: Path, config: dict) -> dict:
    """`{name: root}`: this repository, then each sibling `decisions.repositories` names.

    A sibling's relative path is resolved against the PRIMARY checkout, not the working directory: from
    `.claude/worktrees/<name>`, `../squiddy` would name a directory inside the worktrees folder.
    """
    from seldon.core import worktree as WT

    project_dir = Path(project_dir).resolve()
    block = (config or {}).get("decisions") or {}
    own = block.get("repository") or ((config or {}).get("project") or {}).get("name") or project_dir.name
    try:
        base = WT.primary_checkout(project_dir)
    except WT.WorktreeError:
        base = project_dir
    out = {own: project_dir}
    for name, rel in (block.get("repositories") or {}).items():
        p = Path(os.path.expanduser(str(rel)))
        out[name] = p if p.is_absolute() else (base / p).resolve()
    return out


def _repo_config(root: Path) -> dict:
    cfg = root / "seldon.yaml"
    if not cfg.is_file():
        return {}
    return yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}


def _results(repo: str, root: Path, s: Settings) -> list[Candidate]:
    seen, out = set(), []
    for pattern in s.result_globs:
        for p in sorted(root.glob(pattern)):
            if p in seen or not p.is_file() or p.stat().st_size > s.max_file_bytes:
                continue
            seen.add(p)
            text = p.read_text(encoding="utf-8", errors="replace")
            m = _H1_RE.search(text)
            head = m.group(1) if m else next((ln for ln in text.splitlines() if ln.strip()), p.stem)
            out.append(Candidate(kind="result", id=f"{repo}:{p.stem}", date=_date_of(p.name),
                                 headline=_clip(head, s.headline_chars), repo=repo, text=text,
                                 path=p.relative_to(root).as_posix()))
    return out


def _fold_artifacts(events: list) -> dict:
    """`{artifact_id: {"type", "props", "state", "created", "changed"}}` from a repository's event store."""
    arts: dict = {}
    for e in events:
        p = e.get("payload") or {}
        t, aid = e.get("event_type"), p.get("artifact_id")
        if not aid:
            continue
        if t == "artifact_created":
            arts[aid] = {"type": p.get("artifact_type"), "props": dict(p.get("properties") or {}),
                         "state": p.get("to_state") or "proposed", "created": e.get("timestamp"),
                         "changed": e.get("timestamp")}
        elif aid in arts and t == "artifact_updated":
            arts[aid]["props"].update(p.get("properties") or {})
        elif aid in arts and t == "artifact_state_changed":
            arts[aid]["state"] = p.get("to_state")
            arts[aid]["changed"] = e.get("timestamp")
    return arts


def _names_failure(text: str, s: Settings) -> bool:
    low = (text or "").lower()
    return any(re.search(r"(?<![a-z])" + re.escape(t.lower()), low) for t in s.failure_terms)


def _from_events(repo: str, root: Path, s: Settings) -> list[Candidate]:
    """Issues and dead-end tasks, folded from the repository's event store."""
    from seldon.core.events import read_events

    if not (root / "seldon_events.jsonl").is_file():
        return []
    events = read_events(root)
    arts = _fold_artifacts(events)
    out = []
    for aid, a in arts.items():
        if a["type"] != "Issue":
            continue
        pr = a["props"]
        text = "\n".join(str(pr.get(k) or "") for k in ("name", "description", "resolution"))
        out.append(Candidate(kind="issue", id=f"{repo}:issue-{aid[:8]}", date=str(a["created"] or "")[:10],
                             headline=_clip(pr.get("name") or pr.get("description") or aid, s.headline_chars),
                             repo=repo, text=text, status=a["state"]))
    kept: dict = {}
    for e in events:
        if e.get("event_type") == "worktree_kept":
            p = e.get("payload") or {}
            if p.get("task_id"):
                kept.setdefault(p["task_id"], []).append((e.get("timestamp"), p))
    for aid, a in arts.items():
        if a["type"] != "ResearchTask" or (aid not in kept and a["state"] != "superseded"):
            continue
        pr = a["props"]
        src = pr.get("source_file") or ""
        stem = Path(src).stem if src else aid[:8]
        if aid in kept:
            kind, date = "worktree_kept", str(kept[aid][-1][0] or "")[:10]
            reason = " | ".join(f"{p.get('reason') or p.get('outcome') or ''}" for _ts, p in kept[aid])
            extra = "\n".join(str(p.get("result_reason") or "") for _ts, p in kept[aid])
        else:
            kind, date = "superseded", str(a["changed"] or "")[:10]
            reason = str(pr.get("superseded_reason") or pr.get("reason") or "")
            extra = ""
        text = "\n".join(str(x) for x in (pr.get("name"), pr.get("description"), reason, extra) if x)
        dead = _names_failure(reason, s)
        head = pr.get("name") or stem
        if reason:
            head = f"{head}: {reason}"
        out.append(Candidate(kind=kind, id=f"{repo}:{stem}", date=date, headline=_clip(head, s.headline_chars),
                             repo=repo, text=text, path=src or None, status=a["state"], reason=reason or None,
                             dead_end=dead, task_id=aid))
    return out


def _decisions(repo: str, root: Path, s: Settings) -> list[Candidate]:
    from seldon.core import decisions as dr

    block = (_repo_config(root).get("decisions") or {})
    reg = dr.Register(repo, root, block.get("register_dir", dr.DEFAULT_REGISTER_DIR))
    if not reg.exists():
        return []
    out = []
    for rec in dr.fold(reg.events()).values():
        statement = dr._statement_of(rec)
        kind = "catch" if rec.get("kind") == "catch" else "decision"
        head = statement.splitlines()[0] if statement else rec.id
        if kind == "catch":
            head = f"{rec.get('catch_class')}: {head}"
        out.append(Candidate(kind=kind, id=rec.id, date=str(rec.get("date") or ""),
                             headline=_clip(head, s.headline_chars), repo=repo, text=rec.text(),
                             path=(rec.get("source") or {}).get("path"), status=rec.status))
    return out


def candidates(repos: dict, s: Settings, notes: list) -> list[Candidate]:
    """Every candidate in every repository. A source that cannot be read is named in `notes`."""
    from seldon.core import decisions as dr

    out: list[Candidate] = []
    for repo, root in repos.items():
        if not Path(root).is_dir():
            notes.append(f"{repo}: {root} does not exist; its history is not searched")
            continue
        out.extend(_results(repo, root, s))
        try:
            out.extend(_from_events(repo, root, s))
        except (OSError, ValueError) as exc:
            notes.append(f"{repo}: event store unreadable ({type(exc).__name__}: {exc})")
        try:
            out.extend(_decisions(repo, root, s))
        except (dr.BrokenRegister, dr.RegisterError, OSError, yaml.YAMLError) as exc:
            notes.append(f"{repo}: decision register not searched ({_clip(str(exc), 200)})")
    return out


# =============================================================================================== the arms

def bm25(query_terms: list[str], cands: list[Candidate], s: Settings) -> list[tuple[int, float, list]]:
    """`[(candidate index, score, shared terms)]`, best first, for candidates sharing any query term.

    Okapi BM25 with idf = ln((N - df + 0.5) / (df + 0.5) + 1), the non-negative form (Robertson and
    Zaragoza 2009, eq. 3.3 with Lucene's +1).
    """
    q = sorted(set(query_terms))
    if not q or not cands:
        return []
    docs = [Counter(tokens(c.text + "\n" + c.headline)) for c in cands]
    n = len(docs)
    avg = sum(sum(d.values()) for d in docs) / n or 1.0
    df = {t: sum(1 for d in docs if t in d) for t in q}
    idf = {t: math.log((n - df[t] + 0.5) / (df[t] + 0.5) + 1.0) for t in q}
    out = []
    for i, d in enumerate(docs):
        shared = [t for t in q if t in d]
        if not shared:
            continue
        dl = sum(d.values())
        score = sum(idf[t] * d[t] * (s.k1 + 1) / (d[t] + s.k1 * (1 - s.b + s.b * dl / avg)) for t in shared)
        out.append((i, score, shared))
    out.sort(key=lambda r: (-r[1], cands[r[0]].id))
    return out


def _manifest_paths(graph_dir: Path) -> dict:
    """`{doc_id: repository-relative path}` from a governed graph's manifest."""
    man = graph_dir / "corpus" / "manifest.yaml"
    if not man.is_file():
        return {}
    data = yaml.safe_load(man.read_text(encoding="utf-8")) or {}
    return {d["id"]: d.get("source_url") for d in data.get("documents") or [] if isinstance(d, dict) and d.get("id")}


def served(query: str, repos: dict, cands: list[Candidate], s: Settings, notes: list) -> list[int]:
    """Candidate indices in the order squiddy's served `search` ranked their documents, over every configured graph.

    Only a document that is a candidate (a RESULT on disk) is kept: the served graph also holds rulings, which
    reach a task through `constrained_by` already (AD-031-R1), and task files, which are not outcomes.
    """
    if not s.served_enabled or not s.served_graphs:
        return []
    by_path = {(c.repo, c.path): i for i, c in enumerate(cands) if c.kind == "result"}
    ranked: list[tuple[float, int]] = []
    for repo, rel in s.served_graphs.items():
        root = repos.get(repo)
        if root is None:
            notes.append(f"served arm: {repo} is not a repository this project names; skipped")
            continue
        graph = (Path(root) / rel).resolve()
        if not (graph / "config.yaml").is_file():
            notes.append(f"served arm unavailable for {repo}: no governed graph at {graph}")
            continue
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        try:
            from squiddy.config import load_graph
            from squiddy.serve import Verbs

            res = Verbs(load_graph(str(graph))).search(query, k=s.served_k)
        except ImportError as exc:
            notes.append(f"served arm unavailable: squiddy is not importable here ({exc})")
            return [i for _r, i in sorted(ranked)]
        except Exception as exc:  # noqa: BLE001 -- a squiddy failure is NAMED on the Recall block, never dropped
            notes.append(f"served arm failed for {repo}: {type(exc).__name__}: {_clip(str(exc), 200)}")
            continue
        if res.get("error"):
            notes.append(f"served arm unavailable for {repo}: {_clip(str(res['error']), 200)}")
            continue
        paths = _manifest_paths(graph)
        for h in res.get("hits") or []:
            i = by_path.get((repo, paths.get(h.get("doc_id"))))
            if i is not None:
                ranked.append((float(h.get("rank") or 0), i))
    seen, out = set(), []
    for _r, i in sorted(ranked):
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def _excluded(c: Candidate, stem: str, task_id: Optional[str]) -> bool:
    """The task's own files (itself, its addenda, its RESULT) and its own records are not its history."""
    if task_id and c.task_id == task_id:
        return True
    name = Path(c.path).stem if c.path else c.id.split(":", 1)[-1]
    return bool(stem) and name.startswith(stem)


def recall(project_dir: Path, config: dict, task_text: str, *, task_stem: str = "",
           task_id: Optional[str] = None, use_served: Optional[bool] = None) -> Recall:
    """Retrieve, rank and return the task's history (Part A step 1).

    Args:
        project_dir: The registering repository.
        config: Its parsed seldon.yaml (with a `recall:` block).
        task_text: The task file's text.
        task_stem: The task file's stem; its own files are excluded.
        task_id: The task's artifact id, when it has one; its own records are excluded.
        use_served: Override `recall.served.enabled` (the CLI's `--no-served`).

    Raises:
        RecallError: The project has no `recall:` block, or it is malformed.
    """
    s = settings(config)
    if s is None:
        raise RecallError("seldon.yaml has no `recall:` block (RECALL-001)")
    if use_served is not None:
        s = Settings(**{**asdict(s), "served_enabled": bool(use_served)})
    repos = repositories(project_dir, config)
    notes: list[str] = []
    query = query_of(task_text)
    cands = [c for c in candidates(repos, s, notes) if not _excluded(c, task_stem, task_id)]
    lexical = bm25(tokens(query), cands, s)
    lex_rank = {i: (r, score, shared) for r, (i, score, shared) in enumerate(lexical, 1)
                if len(shared) >= s.min_shared_terms}
    served_order = served(query, repos, cands, s, notes) if query else []
    fused: dict[int, float] = {}
    arms: dict[int, list] = {}
    for i, (r, _score, _shared) in lex_rank.items():
        fused[i] = fused.get(i, 0.0) + 1.0 / (s.rrf_k + r)
        arms.setdefault(i, []).append("lexical")
    for r, i in enumerate(served_order, 1):
        fused[i] = fused.get(i, 0.0) + 1.0 / (s.rrf_k + r)
        arms.setdefault(i, []).append("served")
    shared_of = {i: sh for i, _sc, sh in lexical}
    order = sorted(fused, key=lambda i: (-fused[i], cands[i].id))[: s.top_n]
    hits = [Hit(kind=cands[i].kind, id=cands[i].id, date=cands[i].date, headline=cands[i].headline,
                repo=cands[i].repo, path=cands[i].path, status=cands[i].status, dead_end=cands[i].dead_end,
                score=round(fused[i], 6), shared_terms=shared_of.get(i, [])[:12], arms=arms[i]) for i in order]
    return Recall(query=query, hits=hits, notes=notes, repositories=repos)


# ============================================================================================ the outputs

def render(r: Recall) -> str:
    """The registration output's `Recall:` block (Part A step 2)."""
    lines = []
    if not r.hits:
        lines.append("Recall: none (no prior RESULT, issue, decision or dead end in "
                     f"{', '.join(r.repositories) or 'any repository'} matches this task)")
    else:
        lines.append(f"Recall: {len(r.hits)} hit(s) from the history of {', '.join(r.repositories)}:")
        lines.extend(h.line() for h in r.hits)
    lines.extend(f"  (note: {n})" for n in r.notes)
    return "\n".join(lines)


#: The launch prompt's preamble. Protocol text, not a tunable: it states the obligation Part B measures.
PROMPT_HEAD = ("Recall (RECALL-001): registration searched the repositories' own history for this task. Read these "
               "before CLAUDE.md. Your RESULT must carry a line `Recall used: <ids of the hits below that changed "
               "your approach>` or `Recall used: none`; `seldon cc complete` refuses a RESULT without it.")


def prompt_block(payload: Optional[dict]) -> str:
    """The text put ahead of the dispatch line, from a `recall_listed` payload; empty for a task registered without one."""
    if not payload:
        return ""
    hits = [Hit(**h) for h in payload.get("hits") or []]
    body = "\n".join(h.line() for h in hits) if hits else "  Recall: none"
    return f"{PROMPT_HEAD}\n{body}\n\n"


def listed(events: Iterable[dict], task_id: str) -> Optional[dict]:
    """The newest `recall_listed` payload for a task, or None."""
    found = None
    for e in events:
        if e.get("event_type") == EVENT_LISTED and (e.get("payload") or {}).get("task_id") == task_id:
            found = e["payload"]
    return found


def listed_ids(events: Iterable[dict], task_id: str) -> set:
    """Every hit id any `recall_listed` record of the task listed."""
    return {h["id"] for e in events if e.get("event_type") == EVENT_LISTED
            and (e.get("payload") or {}).get("task_id") == task_id
            for h in (e["payload"].get("hits") or [])}


def task_prompt_block(project_dir: Path, task_id: Optional[str]) -> str:
    """The launch prompt's Recall block for a task, read from the event store (empty when none was recorded)."""
    from seldon.core.events import read_events

    if not task_id:
        return ""
    return prompt_block(listed(read_events(Path(project_dir)), task_id))


def record_listed(project_dir: Path, r: Recall, *, task_id: str, source_file: str, actor: str,
                  session_id: Optional[str]) -> dict:
    from seldon.core.events import append_event, make_event

    payload = {"task_id": task_id, "source_file": source_file, **r.as_payload()}
    append_event(Path(project_dir), make_event(EVENT_LISTED, actor, "accepted", payload, session_id=session_id))
    return payload


# ============================================================================================ the measure

def used_value(text: str) -> Optional[str]:
    """The value of the RESULT's last `Recall used:` line, or None when it has none."""
    found = None
    for m in USED_LINE_RE.finditer(text or ""):
        found = m.group("value").strip().strip("*").strip()
    return found


def parse_used(value: str, allowed: set) -> list[str]:
    """The listed hit ids a `Recall used:` value names; `[]` for `none`.

    Raises:
        RecallError: The value is empty, or names no listed hit and is not `none`.
    """
    v = (value or "").strip()
    if not v:
        raise RecallError("the `Recall used:` line is empty; write the ids of the hits that changed the approach, "
                          "or `none`")
    if re.match(r"(?i)none\b", v):
        return []
    used = sorted(i for i in allowed if re.search(r"(?<![\w:.-])" + re.escape(i) + r"(?![\w-])", v))
    if not used:
        raise RecallError(f"`Recall used: {_clip(v, 120)}` names no hit registration listed for this task; "
                          f"the listed ids are: {', '.join(sorted(allowed)) or '(none: write `Recall used: none`)'}")
    return used


def used_for_completion(project_dir: Path, task_path: Path, task_id: str) -> Optional[dict]:
    """What `seldon cc complete` records for a task that was registered with a Recall list, or None for one without.

    Raises:
        RecallError: The RESULT has no `Recall used:` line, or the line is refused by :func:`parse_used`.
    """
    from seldon.core.events import read_events

    events = read_events(Path(project_dir))
    if listed(events, task_id) is None:
        return None
    sibling = task_path.with_name(f"{task_path.stem}_RESULT.md")
    candidates_ = [sibling] if sibling.is_file() else []
    candidates_.append(task_path)
    value, where = None, None
    for p in candidates_:
        value = used_value(p.read_text(encoding="utf-8", errors="replace"))
        if value is not None:
            where = p
            break
    if value is None:
        raise RecallError(f"the RESULT carries no `Recall used:` line (RECALL-001 Part B). This task was registered "
                          f"with a Recall list; add `Recall used: <ids that changed the approach>` or "
                          f"`Recall used: none` to {sibling.name} (or to the task file's findings)")
    used = parse_used(value, listed_ids(events, task_id))
    try:
        rel = where.resolve().relative_to(Path(project_dir).resolve()).as_posix()
    except ValueError:
        rel = str(where)
    return {"task_id": task_id, "used": used, "result_path": rel, "missing": False}


def record_used(project_dir: Path, payload: dict, *, actor: str, session_id: Optional[str]) -> None:
    from seldon.core.events import append_event, make_event

    append_event(Path(project_dir), make_event(EVENT_USED, actor, "accepted", payload, session_id=session_id))


def used_at_merge(project_dir: Path, task_id: str, result_rel: str) -> Optional[dict]:
    """The dispatcher's reading of a merged RESULT (it completes worktree tasks, not `cc complete`).

    A merge is never refused on it: the reading is recorded with `missing` or `refused` set, so the chart counts a
    RESULT that skipped the line rather than losing it. None for a task registered without a Recall list.
    """
    from seldon.core.events import read_events

    events = read_events(Path(project_dir))
    if listed(events, task_id) is None:
        return None
    p = Path(project_dir) / result_rel
    value = used_value(p.read_text(encoding="utf-8", errors="replace")) if p.is_file() else None
    row = {"task_id": task_id, "result_path": result_rel, "used": None, "missing": value is None}
    if value is not None:
        try:
            row["used"] = parse_used(value, listed_ids(events, task_id))
        except RecallError as exc:
            row["refused"] = str(exc)
    return row


def chart(events: list, catches: list) -> dict:
    """Part B and C's weekly series.

    Rows by the ISO week a task was first listed: `registered` (tasks with a `recall_listed` record), `with_hits`
    (at least one hit), `results_read` (a `recall_used` record exists, from `cc complete` or the merge), `used` (the
    RESULT names at least one listed hit). Catches by the ISO week of the record's date, per class.
    """
    from seldon.core.toil import week_of

    first: dict = {}
    for e in events:
        if e.get("event_type") == EVENT_LISTED:
            p = e.get("payload") or {}
            if p.get("task_id") and p["task_id"] not in first:
                first[p["task_id"]] = (week_of(e["timestamp"]), bool(p.get("hits")))
    used: dict = {}
    for e in events:
        if e.get("event_type") == EVENT_USED:
            p = e.get("payload") or {}
            used[p.get("task_id")] = p.get("used")
    weeks: dict = {}
    for tid, (w, has) in first.items():
        row = weeks.setdefault(w, {"week": w, "registered": 0, "with_hits": 0, "results_read": 0, "used": 0})
        row["registered"] += 1
        row["with_hits"] += int(has)
        if tid in used:
            row["results_read"] += 1
            row["used"] += int(bool(used[tid]))
    cw: dict = {}
    for c in catches:
        w = week_of(f"{c['date']}T00:00:00Z")
        row = cw.setdefault(w, {"week": w, "total": 0, "by_class": {}})
        row["total"] += 1
        row["by_class"][c["class"]] = row["by_class"].get(c["class"], 0) + 1
    return {"weeks": [weeks[w] for w in sorted(weeks)], "catches": [cw[w] for w in sorted(cw)]}


def catches(project_dir: Path, config: dict) -> list[dict]:
    """Every operator catch in this repository's register: `[{id, date, class, task}]`."""
    from seldon.core import decisions as dr

    s = dr.settings(project_dir, config)
    if s is None:
        return []
    reg = dr.Register(s.repository, s.root, s.register_dir)
    if not reg.exists():
        return []
    return [{"id": r.id, "date": str(r.get("date")), "class": r.get("catch_class"), "task": r.get("task")}
            for r in dr.fold(reg.events()).values() if r.get("kind") == "catch"]

