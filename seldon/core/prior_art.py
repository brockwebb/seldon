"""Prior-art receipts: search, verify, record (AD-036).

    seldon prior-art search --internal "<query>"   # the operator's own repositories
    seldon prior-art search --library "<query>"    # the squiddy library graph, in-process
    seldon prior-art verify docs/design/<note>.md  # re-run every receipt the note carries

**Why this exists.** The rule "search the prior art, internal and external, before writing a
design" was written in three repositories and bound in one (AD-036 section 1). A rule held in
prose decays inside an agent's session; a gate outside the agent does not. This module is the
gate's instrument: it runs the searches, prints what it found as RECEIPTS a note author pastes, and
re-runs a note's receipts to check that each cited hit is really there (AD-036-R1, R2).

**A receipt is a re-runnable query, not a logged assertion** (reproducible builds: a second party
re-derives the claim from declared inputs). So every receipt names the exact corpus it ran
against: a library receipt names the index release and its sha256; an internal receipt names the
repository and its commit. Verification re-runs the query against that named corpus and passes the
receipt only when every cited id or line is in the result. A corpus that is no longer loadable
fails as `release_unavailable`, naming it.

**The receipt grammar** (one bullet per receipt, inside `### External` or `### Internal` under a
`## Prior art` heading; prose around the bullets is allowed and ignored):

    - library receipt: query "<q>" | release <export file> sha256:<64 hex> | rows <row id>, <row id>
    - internal receipt: query "<q>" | repo <name>@<40-hex commit> | hits <path>:<line>, <path>:<line>
    - web receipt: url <https://...> | retrieved <YYYY-MM-DD>

`rows none` / `hits none` is the receipt of a search that found nothing, which is the only form a
"no prior art" finding may take (R1). A hit in a file the repository does not track (a gitignored
handoff) carries its content hash, `<path>:<line>#sha256=<12 hex>`, because a commit does not pin
it. A root that is not a git repository is named `<name>@tree:<64 hex>`, the digest of every file
searched. A query may not contain a double quote.

**The internal arm** is lexical: case-insensitive, every query term must occur in one paragraph
(a run of non-blank lines), each term matched at a word start, so `pin` finds `pinned`. Paragraphs
are ranked by BM25 (Robertson and Zaragoza 2009) with the parameters in `seldon.yaml`; ranking
only orders what is printed, and verification checks membership in the full match set, so a later
file that outranks a cited hit never fails a receipt. AD-036-R3 says "ripgrep": the semantics are
ripgrep's (a fixed-string, case-insensitive search), but the files are read from git's object
store at the named commit, because verification must re-run the search against that commit and
ripgrep reads only a working tree. The departure is recorded in AD-036 ADDENDUM 01.

**Where verdicts go.** `verify` appends one `provenance` event per run to the governed ledger
through squiddy's single write path (`squiddy.ledger.append`): the note's path and sha256, every
addendum's, each receipt's status and the overall verdict (AD-036-R4). `provenance` is the kit's
kind for statements about the graph that no projection imports, so `seldon governed sync` is
unchanged. `seldon verify` reads the newest verdict for a note's current hash.

**Dependencies.** The library arm and the ledger write import squiddy lazily; everything else is
the standard library, PyYAML and git.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import math
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

#: Bumped when the matching, ranking, grammar or verdict rules change. R5's recall control is
#: re-run on every bump, and every logged query and verdict carries it.
TOOL_VERSION = "prior-art/1"

#: Receipt statuses (PA-001 Part A step 2).
PASS = "pass"
ID_NOT_RETURNED = "id_not_returned"
RELEASE_UNAVAILABLE = "release_unavailable"
MALFORMED = "malformed"

#: The governed-ledger event type a verdict is written as.
VERDICT_EVENT = "prior_art_verdict"

_HEADING_RE = re.compile(r"^##\s+(?:\d+\.\s*)?Prior art\s*$", re.IGNORECASE)
_SUB_RE = re.compile(r"^###\s+(External|Internal)\b", re.IGNORECASE)
_RECEIPT_START_RE = re.compile(r"^\s*[-*]\s+(library|internal|web)\s+receipt:\s*(.*)$",
                               re.IGNORECASE)
_LOOSE_RECEIPT_RE = re.compile(r"^\s*[-*]\s+.*\breceipt\s*:", re.IGNORECASE)
_LIB_RE = re.compile(r'^query "([^"]+)" \| release (\S+) sha256:([0-9a-f]{64}) \| rows (.+)$')
_INT_RE = re.compile(r'^query "([^"]+)" \| repo ([A-Za-z0-9_.\-]+)@((?:tree:)?[0-9a-f]{40,64}) '
                     r'\| hits (.+)$')
_WEB_RE = re.compile(r"^url (https?://\S+) \| retrieved (\d{4}-\d{2}-\d{2})$")
_HIT_RE = re.compile(r"^(\S+?):(\d+)(?:#sha256=([0-9a-f]{12}))?$")
_ROW_RE = re.compile(r"^\S+#\S+$|^\S+$")
#: A sentence asserting that nothing was found. Allowed only beside a receipt that found nothing.
_NO_PRIOR_ART_RE = re.compile(r"\bno\s+(?:internal\s+|external\s+)?(?:prior\s+art|precedent)\b",
                              re.IGNORECASE)
_NOTE_ID_RE = re.compile(r"^((?:AD|DN)-\d{3})")


class PriorArtError(Exception):
    """Configuration or corpus problem. Fatal: no receipt is printed or verified around it."""


# ------------------------------------------------------------------------------ configuration

@dataclass(frozen=True)
class Root:
    name: str
    path: Path
    include: tuple


@dataclass(frozen=True)
class Settings:
    project_dir: Path
    log: Path
    roots: tuple
    suffixes: tuple
    top_n: int
    max_file_bytes: int
    k1: float
    b: float
    library_graph: Path
    library_k: int
    design_dir: str
    baseline: Path
    exempt_globs: tuple


_REQUIRED = ("log", "internal_roots", "internal", "library", "gate")


def settings(project_dir: Path, config: dict) -> Settings:
    """The `prior_art:` block of seldon.yaml, validated. Every key is required: a missing one is a
    configuration error named here, never a default the reader cannot see."""
    block = config.get("prior_art")
    if not isinstance(block, dict):
        raise PriorArtError("seldon.yaml has no `prior_art:` block (AD-036-R3)")
    missing = [k for k in _REQUIRED if k not in block]
    if missing:
        raise PriorArtError(f"seldon.yaml prior_art block missing {missing}")
    project_dir = Path(project_dir).resolve()
    internal, library, gate = block["internal"], block["library"], block["gate"]
    for name, sub, keys in (("internal", internal, ("default_include", "suffixes", "top_n",
                                                     "max_file_bytes", "bm25")),
                            ("library", library, ("graph", "k")),
                            ("gate", gate, ("design_dir", "baseline", "exempt_globs"))):
        miss = [k for k in keys if k not in (sub or {})]
        if miss:
            raise PriorArtError(f"seldon.yaml prior_art.{name} missing {miss}")
    roots = []
    for row in block["internal_roots"]:
        if not isinstance(row, dict) or not row.get("name") or not row.get("path"):
            raise PriorArtError(f"prior_art.internal_roots row {row!r} needs `name` and `path`")
        path = Path(os.path.expanduser(str(row["path"])))
        if not path.is_absolute():
            path = (project_dir / path)
        roots.append(Root(name=str(row["name"]), path=path.resolve(),
                          include=tuple(row.get("include") or internal["default_include"])))
    names = [r.name for r in roots]
    if len(set(names)) != len(names):
        raise PriorArtError(f"prior_art.internal_roots names are not unique: {names}")

    def rel(p: str) -> Path:
        q = Path(os.path.expanduser(str(p)))
        return q if q.is_absolute() else (project_dir / q).resolve()

    return Settings(project_dir=project_dir, log=rel(block["log"]), roots=tuple(roots),
                    suffixes=tuple(internal["suffixes"]), top_n=int(internal["top_n"]),
                    max_file_bytes=int(internal["max_file_bytes"]),
                    k1=float(internal["bm25"]["k1"]), b=float(internal["bm25"]["b"]),
                    library_graph=rel(library["graph"]), library_k=int(library["k"]),
                    design_dir=str(gate["design_dir"]), baseline=rel(gate["baseline"]),
                    exempt_globs=tuple(gate["exempt_globs"]))


def _glob_re(pattern: str) -> re.Pattern:
    """A path glob where `**` crosses directories and `*` does not."""
    out, i = [], 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
            if i < len(pattern) and pattern[i] == "/":
                i += 1
            continue
        out.append("[^/]*" if c == "*" else "[^/]" if c == "?" else re.escape(c))
        i += 1
    return re.compile("^" + "".join(out) + "$")


def _matcher(include: Iterable[str]):
    pats = [_glob_re(p) for p in include]
    return lambda rel: any(p.match(rel) for p in pats)


def _walk_bases(include: Iterable[str]) -> list[str]:
    """The literal directory prefix of each include glob, so a walk never descends into trees no
    glob can match (a repository's data or node_modules)."""
    bases = set()
    for p in include:
        parts = []
        for part in p.split("/"):
            if any(ch in part for ch in "*?["):
                break
            parts.append(part)
        bases.add("/".join(parts))
    return sorted(bases)


# ------------------------------------------------------------------------------- the corpus

@dataclass
class Doc:
    root: str
    path: str
    text: str
    tracked: bool
    sha12: str
    paragraphs: list = field(default_factory=list)   # (start, end, lowered text, length in terms)


@dataclass
class Corpus:
    root: Root
    identity: str               # 40-hex commit, or tree:<64 hex>
    docs: list
    untracked: int = 0
    dirty_tracked: int = 0
    skipped_large: int = 0


def _git(root: Path, *args: str, input_bytes: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], input=input_bytes,
                          capture_output=True, check=False)


def _is_git(root: Path) -> bool:
    r = _git(root, "rev-parse", "--show-toplevel")
    return r.returncode == 0 and Path(r.stdout.decode().strip()).resolve() == root.resolve()


def _split(text: str) -> list:
    """Paragraphs: maximal runs of non-blank lines, as (first line, last line, lowered text, n)."""
    out, start, buf = [], None, []
    lines = text.splitlines()
    for i, line in enumerate(lines, 1):
        if line.strip():
            if start is None:
                start = i
            buf.append(line)
        elif start is not None:
            body = "\n".join(buf)
            out.append((start, i - 1, body.lower(), max(1, len(body.split()))))
            start, buf = None, []
    if start is not None:
        body = "\n".join(buf)
        out.append((start, len(lines), body.lower(), max(1, len(body.split()))))
    return out


def _disk_files(root: Root, suffixes: tuple) -> dict:
    """Files on disk under the root that an include glob matches: {relative path: Path}."""
    match = _matcher(root.include)
    found = {}
    for base in _walk_bases(root.include):
        start = root.path / base if base else root.path
        if start.is_file():
            rel = start.relative_to(root.path).as_posix()
            if match(rel) and start.suffix in suffixes:
                found[rel] = start
            continue
        if not start.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(start):
            dirnames[:] = sorted(d for d in dirnames if d != ".git")
            for fn in filenames:
                p = Path(dirpath) / fn
                rel = p.relative_to(root.path).as_posix()
                if p.suffix in suffixes and match(rel):
                    found[rel] = p
    return found


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_corpus(root: Root, s: Settings, commit: str | None = None) -> Corpus:
    """Read a root's searchable files: tracked files from git's objects at `commit` (HEAD when
    None), plus files on disk the commit does not contain; or, for a non-git root, every file on
    disk, named by the digest of their paths and hashes.

    Raises:
        PriorArtError: `release_unavailable` when the root or the named commit cannot be read.
    """
    if not root.path.is_dir():
        raise PriorArtError(f"{RELEASE_UNAVAILABLE}: root {root.name} ({root.path}) does not exist")
    disk = _disk_files(root, s.suffixes)
    docs, skipped = [], 0
    if not _is_git(root.path):
        lines = []
        for rel in sorted(disk):
            data = disk[rel].read_bytes()
            lines.append(f"{rel}\0{_sha(data)}")
            if len(data) > s.max_file_bytes:
                skipped += 1
                continue
            docs.append(Doc(root.name, rel, data.decode("utf-8", "replace"), False, _sha(data)[:12]))
        identity = "tree:" + _sha("\n".join(lines).encode())
        if commit is not None and commit != identity:
            raise PriorArtError(f"{RELEASE_UNAVAILABLE}: {root.name}@{commit} is not the files on "
                                f"disk now ({identity}); a non-git root keeps no history")
        corpus = Corpus(root, identity, docs, untracked=len(docs), skipped_large=skipped)
    else:
        rev = commit or "HEAD"
        r = _git(root.path, "rev-parse", "--verify", f"{rev}^{{commit}}")
        if r.returncode != 0:
            raise PriorArtError(f"{RELEASE_UNAVAILABLE}: {root.name}@{rev} is not a commit in "
                                f"{root.path}")
        identity = r.stdout.decode().strip()
        ls = _git(root.path, "ls-tree", "-r", "-z", "--name-only", identity)
        if ls.returncode != 0:
            raise PriorArtError(f"{RELEASE_UNAVAILABLE}: cannot list {root.name}@{identity}")
        match = _matcher(root.include)
        tracked = sorted(p for p in ls.stdout.decode("utf-8", "replace").split("\0")
                         if p and match(p) and Path(p).suffix in s.suffixes)
        tracked_set = set(tracked)
        if tracked:
            req = "".join(f"{identity}:{p}\n" for p in tracked).encode()
            out = _git(root.path, "cat-file", "--batch", input_bytes=req)
            if out.returncode != 0:
                raise PriorArtError(f"{RELEASE_UNAVAILABLE}: cannot read blobs of "
                                    f"{root.name}@{identity}")
            buf, pos = out.stdout, 0
            for p in tracked:
                nl = buf.index(b"\n", pos)
                header = buf[pos:nl].split()
                if len(header) < 3 or header[1] != b"blob":
                    raise PriorArtError(f"{RELEASE_UNAVAILABLE}: {root.name}@{identity}:{p} "
                                        f"did not read as a blob")
                size = int(header[2])
                data = buf[nl + 1: nl + 1 + size]
                pos = nl + 1 + size + 1
                if size > s.max_file_bytes:
                    skipped += 1
                    continue
                docs.append(Doc(root.name, p, data.decode("utf-8", "replace"), True,
                                _sha(data)[:12]))
        untracked = 0
        for rel in sorted(set(disk) - tracked_set):
            data = disk[rel].read_bytes()
            if len(data) > s.max_file_bytes:
                skipped += 1
                continue
            docs.append(Doc(root.name, rel, data.decode("utf-8", "replace"), False,
                            _sha(data)[:12]))
            untracked += 1
        dirty = 0
        if commit is None:
            st = _git(root.path, "status", "--porcelain", "-z", "--untracked-files=no")
            dirty = sum(1 for e in st.stdout.decode("utf-8", "replace").split("\0")
                        if len(e) > 3 and e[3:] in tracked_set)
        corpus = Corpus(root, identity, docs, untracked=untracked, dirty_tracked=dirty,
                        skipped_large=skipped)
    for d in corpus.docs:
        d.paragraphs = _split(d.text)
    return corpus


# ------------------------------------------------------------------------------- the search

def terms_of(query: str) -> list[str]:
    q = (query or "").strip()
    if not q:
        raise PriorArtError("empty query")
    if '"' in q:
        raise PriorArtError('a query may not contain a double quote (the receipt grammar quotes it)')
    return [t.lower() for t in q.split()]


@dataclass
class Hit:
    root: str
    path: str
    start: int
    end: int
    score: float
    tracked: bool
    sha12: str

    def cite(self) -> str:
        return f"{self.path}:{self.start}" + ("" if self.tracked else f"#sha256={self.sha12}")


def search_corpora(query: str, corpora: list, s: Settings) -> list[Hit]:
    """Every paragraph containing every term, ranked by BM25 over all paragraphs of all corpora."""
    terms = terms_of(query)
    regs = [re.compile(r"(?<!\w)" + re.escape(t)) for t in terms]
    paras = [(c, d, p) for c in corpora for d in c.docs for p in d.paragraphs]
    n = len(paras) or 1
    avg = sum(p[3] for _c, _d, p in paras) / n
    df = [0] * len(terms)
    tf_rows = []
    for c, d, p in paras:
        low = p[2]
        tfs = []
        for i, (t, rg) in enumerate(zip(terms, regs)):
            k = len(rg.findall(low)) if t in low else 0
            if k:
                df[i] += 1
            tfs.append(k)
        if all(tfs):
            tf_rows.append((c, d, p, tfs))
    idf = [math.log(1 + (n - x + 0.5) / (x + 0.5)) for x in df]
    hits = []
    for c, d, p, tfs in tf_rows:
        norm = s.k1 * (1 - s.b + s.b * p[3] / avg)
        score = sum(w * tf * (s.k1 + 1) / (tf + norm) for w, tf in zip(idf, tfs))
        hits.append(Hit(d.root, d.path, p[0], p[1], round(score, 6), d.tracked, d.sha12))
    order = {r.name: i for i, r in enumerate(s.roots)}
    hits.sort(key=lambda h: (-h.score, order.get(h.root, 99), h.path, h.start))
    return hits


class Internal:
    """The internal arm with a per-process corpus cache keyed by (root, identity)."""

    def __init__(self, s: Settings):
        self.s = s
        self._cache: dict = {}

    def corpus(self, root: Root, commit: str | None = None) -> Corpus:
        key = (root.name, commit or "HEAD")
        if key not in self._cache:
            c = load_corpus(root, self.s, commit)
            self._cache[key] = c
            self._cache[(root.name, c.identity)] = c
        return self._cache[key]

    def search(self, query: str, roots: Iterable[str] | None = None) -> dict:
        wanted = set(roots) if roots else None
        corpora = [self.corpus(r) for r in self.s.roots if wanted is None or r.name in wanted]
        hits = search_corpora(query, corpora, self.s)
        return {"query": query, "hits": hits,
                "corpora": {c.root.name: {"identity": c.identity, "files": len(c.docs),
                                          "untracked": c.untracked, "dirty_tracked": c.dirty_tracked,
                                          "skipped_large": c.skipped_large} for c in corpora}}

    def receipts(self, result: dict, top_n: int | None = None) -> list[str]:
        """One receipt per searched root, citing that root's top hits (or `hits none`)."""
        top_n = top_n or self.s.top_n
        out = []
        for name, meta in result["corpora"].items():
            mine = [h for h in result["hits"] if h.root == name][:top_n]
            cites = ", ".join(h.cite() for h in mine) or "none"
            out.append(f'- internal receipt: query "{result["query"]}" | repo '
                       f'{name}@{meta["identity"]} | hits {cites}')
        return out


class Library:
    """The library arm: squiddy's served `search` verb, in-process (AD-036-R3)."""

    def __init__(self, s: Settings):
        self.s = s
        self._verbs = None

    def verbs(self):
        if self._verbs is None:
            # The library search is local; nothing here may reach a network (PA-001: Network none).
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
            # The internal arm forks git after the encoder has loaded; say so up front rather than
            # let the tokenizer library warn on every fork.
            os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
            try:
                from squiddy.config import load_graph
                from squiddy.serve import Verbs
            except ImportError as exc:
                raise PriorArtError(f"the library arm needs squiddy installed in this interpreter "
                                    f"(pip install -e <squiddy> --no-deps): {exc}") from exc
            if not self.s.library_graph.is_dir():
                raise PriorArtError(f"{RELEASE_UNAVAILABLE}: library graph "
                                    f"{self.s.library_graph} does not exist")
            self._verbs = Verbs(load_graph(str(self.s.library_graph)))
        return self._verbs

    def search(self, query: str, k: int | None = None) -> dict:
        terms_of(query)
        res = self.verbs().search(query, k=k or self.s.library_k)
        if res.get("error"):
            raise PriorArtError(f"{RELEASE_UNAVAILABLE}: library search failed: {res['error']}")
        rel = (res.get("index") or {}).get("release") or {}
        rows = [r["receipt"]["row_id"] for h in res["hits"] for r in h["rows"]
                if (r.get("receipt") or {}).get("row_id")]
        return {"query": query, "release": Path(str(rel.get("export"))).name,
                "sha256": rel.get("sha256"), "rows": rows, "hits": res["hits"]}

    @staticmethod
    def receipt(result: dict) -> str:
        rows = ", ".join(result["rows"]) or "none"
        return (f'- library receipt: query "{result["query"]}" | release {result["release"]} '
                f'sha256:{result["sha256"]} | rows {rows}')


def log_query(s: Settings, record: dict) -> None:
    """Append one line to the query log, flushed and fsynced (constitution section 15)."""
    s.log.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"ts": _now(), "tool": TOOL_VERSION, **record}, sort_keys=True,
                      default=str)
    with s.log.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")


# ------------------------------------------------------------------------------ parsing a note

@dataclass
class Receipt:
    section: str             # External | Internal
    kind: str                # library | internal | web | unknown
    line: int                # 1-based line in its file
    source: str              # the file it was read from (note or addendum)
    raw: str
    query: str | None = None
    release: str | None = None
    sha256: str | None = None
    rows: list = field(default_factory=list)
    repo: str | None = None
    commit: str | None = None
    hits: list = field(default_factory=list)      # (path, line, sha12 or None)
    url: str | None = None
    retrieved: str | None = None
    error: str | None = None                      # set when malformed
    status: str | None = None
    detail: str | None = None

    @property
    def empty(self) -> bool:
        return self.kind in ("library", "internal") and not (self.rows or self.hits)

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v not in (None, [], "")}


@dataclass
class Parsed:
    path: str
    has_section: bool = False
    subsections: dict = field(default_factory=dict)   # name -> list[Receipt]
    no_prior_art_sentences: dict = field(default_factory=dict)   # name -> [line]
    present: set = field(default_factory=set)


def _parse_receipt(section: str, kind: str, body: str, line: int, source: str, raw: str) -> Receipt:
    r = Receipt(section=section, kind=kind.lower(), line=line, source=source, raw=raw.strip())
    body = body.strip()
    if r.kind == "library":
        m = _LIB_RE.match(body)
        if not m:
            r.error = 'expected: query "<q>" | release <file> sha256:<64 hex> | rows <id>, ... or none'
            return r
        r.query, r.release, r.sha256, rows = m.groups()
        if rows.strip() != "none":
            r.rows = [x.strip() for x in rows.split(",") if x.strip()]
            if not r.rows or any(not _ROW_RE.match(x) for x in r.rows):
                r.error = "rows must be a comma-separated list of row ids, or none"
    elif r.kind == "internal":
        m = _INT_RE.match(body)
        if not m:
            r.error = ('expected: query "<q>" | repo <name>@<40-hex commit or tree:<64 hex>> | '
                       'hits <path>:<line>, ... or none')
            return r
        r.query, r.repo, r.commit, hits = m.groups()
        if not (re.fullmatch(r"[0-9a-f]{40}", r.commit) or re.fullmatch(r"tree:[0-9a-f]{64}",
                                                                         r.commit)):
            r.error = "commit must be the full 40-hex sha (or tree:<64 hex> for a non-git root)"
            return r
        if hits.strip() != "none":
            for x in [x.strip() for x in hits.split(",") if x.strip()]:
                hm = _HIT_RE.match(x)
                if not hm:
                    r.error = f"hit {x!r} is not <path>:<line> or <path>:<line>#sha256=<12 hex>"
                    return r
                r.hits.append((hm.group(1), int(hm.group(2)), hm.group(3)))
            if not r.hits:
                r.error = "hits must be a comma-separated list, or none"
    else:
        m = _WEB_RE.match(body)
        if not m:
            r.error = "expected: url <https://...> | retrieved <YYYY-MM-DD>"
            return r
        r.url, r.retrieved = m.groups()
    return r


def parse_note(path: Path, display: str | None = None) -> Parsed:
    """The `## Prior art` section of one file: its two subsections and their receipts."""
    out = Parsed(path=display or str(path))
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    in_section, sub, fence = False, None, False
    for i, line in enumerate(lines, 1):
        if line.lstrip().startswith("```"):
            fence = not fence
            continue
        if fence:
            continue
        if line.startswith("## ") or line.startswith("# "):
            in_section = bool(_HEADING_RE.match(line))
            out.has_section = out.has_section or in_section
            sub = None
            continue
        if not in_section:
            continue
        m = _SUB_RE.match(line)
        if m:
            sub = m.group(1).capitalize()
            out.present.add(sub)
            out.subsections.setdefault(sub, [])
            continue
        if line.startswith("### "):
            sub = None
            continue
        if sub is None:
            continue
        rm = _RECEIPT_START_RE.match(line)
        if rm:
            out.subsections[sub].append(_parse_receipt(sub, rm.group(1), rm.group(2), i,
                                                       out.path, line))
        elif _LOOSE_RECEIPT_RE.match(line):
            r = Receipt(section=sub, kind="unknown", line=i, source=out.path, raw=line.strip(),
                        error="a receipt is `library receipt:`, `internal receipt:` or "
                              "`web receipt:`")
            out.subsections[sub].append(r)
        elif _NO_PRIOR_ART_RE.search(line):
            out.no_prior_art_sentences.setdefault(sub, []).append(i)
    return out


def addenda_of(note: Path) -> list[Path]:
    """A note's addenda: `<AD-NNN or DN-NNN>_ADDENDUM_*.md` beside it (or `<stem>_ADDENDUM_*.md`
    for a note without an identifier). A note is immutable once committed, so its prior-art
    section is completed, never edited, by an addendum (AD-036-R7)."""
    m = _NOTE_ID_RE.match(note.name)
    prefix = m.group(1) if m else note.stem
    return sorted(p for p in note.parent.glob(f"{prefix}_ADDENDUM_*.md") if p != note)


# ----------------------------------------------------------------------------- verification

@dataclass
class Verdict:
    note: str
    sha256: str
    addenda: list
    verdict: str                 # pass | fail
    problems: list
    receipts: list

    def as_payload(self) -> dict:
        return {"note": self.note, "sha256": self.sha256, "addenda": self.addenda,
                "verdict": self.verdict, "problems": self.problems,
                "receipts": [r.as_dict() for r in self.receipts], "tool": TOOL_VERSION,
                "authority": "AD-036-R2, R4"}


def _rel(s: Settings, p: Path) -> str:
    try:
        return p.resolve().relative_to(s.project_dir).as_posix()
    except ValueError:
        return str(p)


def verify_note(note: Path, s: Settings, internal: Internal | None = None,
                library: Library | None = None, include_addenda: bool = True) -> Verdict:
    """Re-run every receipt in a note (and its addenda) and judge the section (AD-036-R1, R2)."""
    note = Path(note).resolve()
    if not note.is_file():
        raise PriorArtError(f"no such note: {note}")
    internal = internal or Internal(s)
    library = library or Library(s)
    files = [note] + (addenda_of(note) if include_addenda else [])
    parsed = [parse_note(f, _rel(s, f)) for f in files]
    problems = []
    if not any(p.has_section for p in parsed):
        problems.append("missing: no `## Prior art` section (AD-036-R1)")
    by_sub = {"External": [], "Internal": []}
    present = set()
    nopa = {"External": [], "Internal": []}
    for p in parsed:
        present |= p.present
        for sub, rs in p.subsections.items():
            by_sub[sub].extend(rs)
        for sub, ls in p.no_prior_art_sentences.items():
            nopa[sub].extend(f"{p.path}:{x}" for x in ls)
    for sub in ("External", "Internal"):
        if any(p.has_section for p in parsed) and sub not in present:
            problems.append(f"missing: no `### {sub}` subsection (AD-036-R1)")
        elif sub in present and not by_sub[sub]:
            if nopa[sub]:
                problems.append(f"empty: `### {sub}` asserts no prior art ({', '.join(nopa[sub])}) "
                                f"with no receipt of the query that found nothing (AD-036-R1)")
            else:
                problems.append(f"empty: `### {sub}` carries no receipt (AD-036-R1)")
        elif nopa[sub] and not any(r.empty for r in by_sub[sub]):
            problems.append(f"`### {sub}` asserts no prior art ({', '.join(nopa[sub])}) but no "
                            f"receipt in it found nothing (AD-036-R1)")
    ext = by_sub["External"]
    if ext and all(r.kind == "web" for r in ext):
        problems.append("External carries only web receipts; at least one library receipt is "
                        "required, even one that found nothing (AD-036-R1)")
    if any(r.kind == "web" for r in by_sub["Internal"]):
        problems.append("a web receipt is allowed in External only (AD-036-R1)")
    receipts = by_sub["External"] + by_sub["Internal"]
    for r in receipts:
        if r.error:
            r.status, r.detail = MALFORMED, r.error
    _verify_library([r for r in receipts if r.kind == "library" and not r.status], s, library)
    _verify_internal([r for r in receipts if r.kind == "internal" and not r.status], s, internal)
    for r in receipts:
        if r.kind == "web" and not r.status:
            r.status, r.detail = PASS, "well-formed; a web page is not re-fetched"
    bad = [r for r in receipts if r.status != PASS]
    for r in bad:
        problems.append(f"{r.source}:{r.line} {r.kind} receipt {r.status}: {r.detail}")
    return Verdict(note=_rel(s, note), sha256=_sha(note.read_bytes()),
                   addenda=[{"path": _rel(s, f), "sha256": _sha(f.read_bytes())} for f in files[1:]],
                   verdict="pass" if not problems else "fail", problems=problems,
                   receipts=receipts)


def _verify_library(receipts: list, s: Settings, library: Library) -> None:
    groups: dict = {}
    for r in receipts:
        groups.setdefault(r.query, []).append(r)
    for query, rs in groups.items():
        try:
            res = library.search(query)
        except PriorArtError as exc:
            for r in rs:
                r.status, r.detail = RELEASE_UNAVAILABLE, str(exc)
            continue
        log_query(s, {"arm": "library", "purpose": "verify", "query": query,
                      "release": res["release"], "sha256": res["sha256"], "rows": len(res["rows"])})
        got = set(res["rows"])
        for r in rs:
            if r.sha256 != res["sha256"]:
                r.status = RELEASE_UNAVAILABLE
                r.detail = (f"release {r.release} sha256:{r.sha256[:12]}... is not the one the "
                            f"index serves ({res['release']} sha256:{str(res['sha256'])[:12]}...)")
                continue
            missing = [x for x in r.rows if x not in got]
            if missing:
                r.status = ID_NOT_RETURNED
                r.detail = f"not returned in the top {s.library_k}: {', '.join(missing[:5])}"
            else:
                r.status, r.detail = PASS, f"{len(r.rows)} row(s) returned"


def _verify_internal(receipts: list, s: Settings, internal: Internal) -> None:
    roots = {r.name: r for r in s.roots}
    for r in receipts:
        root = roots.get(r.repo)
        if root is None:
            r.status, r.detail = MALFORMED, (f"repo {r.repo!r} is not in prior_art.internal_roots "
                                             f"({', '.join(roots)})")
            continue
        try:
            corpus = internal.corpus(root, r.commit)
        except PriorArtError as exc:
            r.status, r.detail = RELEASE_UNAVAILABLE, str(exc)
            continue
        hits = search_corpora(r.query, [corpus], s)
        log_query(s, {"arm": "internal", "purpose": "verify", "query": r.query,
                      "corpora": {root.name: corpus.identity}, "hits": len(hits)})
        found = {(h.path, h.start): h for h in hits}
        missing, moved = [], []
        for path, line, sha12 in r.hits:
            h = found.get((path, line))
            if h is None:
                missing.append(f"{path}:{line}")
            elif sha12 and h.sha12 != sha12:
                moved.append(f"{path} (sha256 now {h.sha12})")
            elif not sha12 and not h.tracked:
                missing.append(f"{path}:{line} (untracked at {r.commit[:12]}; cite it with "
                               f"#sha256={h.sha12})")
        if moved:
            r.status, r.detail = RELEASE_UNAVAILABLE, ("untracked file changed since the receipt: "
                                                       + ", ".join(moved))
        elif missing:
            r.status, r.detail = ID_NOT_RETURNED, "not in the result: " + ", ".join(missing[:5])
        else:
            r.status, r.detail = PASS, f"{len(r.hits)} hit(s) returned of {len(hits)}"


# ------------------------------------------------------------------------- the ledger verdict

def governed_ledger(project_dir: Path, config: dict) -> Path | None:
    """This project's governed ledger, or None when the project keeps no governed graph."""
    from seldon.core.governed import ledger_path
    p = ledger_path(Path(project_dir), config)
    return p if p.parent.is_dir() else None


def record_verdict(v: Verdict, project_dir: Path, config: dict) -> dict:
    """Append the verdict to the governed ledger through squiddy's single write path (R4)."""
    path = governed_ledger(project_dir, config)
    if path is None:
        raise PriorArtError("this project has no governed ledger to record a verdict in "
                            "(governed.graph_dir in seldon.yaml); AD-036-R4 needs one")
    try:
        from squiddy import ledger as L
    except ImportError as exc:
        raise PriorArtError(f"recording a verdict needs squiddy installed: {exc}") from exc
    event = L.make_event(run_id=L.new_run_id("prior_art_verify"), stage="prior_art_verify",
                         etype=VERDICT_EVENT, schema_version="1", kind="provenance", doc_id=None,
                         payload=v.as_payload(),
                         provenance={"source": f"seldon prior-art verify {v.note}",
                                     "tool": TOOL_VERSION, "authority": "AD-036-R4"})
    L.append(path, [event], canonical=path)
    return event


def verdicts(project_dir: Path, config: dict) -> dict:
    """{note path: newest verdict payload per note sha256} read from the governed ledger.

    Returns {note: {sha256: payload}} with the newest event winning for each (note, sha256).
    """
    path = governed_ledger(project_dir, config)
    if path is None or not path.is_file():
        return {}
    with path.open(encoding="utf-8") as fh:
        return verdicts_from_lines(fh, str(path))


def verdicts_from_lines(lines: Iterable[str], where: str) -> dict:
    """`verdicts` over ledger lines from any source: the file on disk, or a blob read from git's
    index or a commit (the commit hook judges the STAGED ledger, HOOK-001).

    Args:
        lines: The ledger's lines, in order.
        where: How to name the source in an error.

    Raises:
        PriorArtError: On a verdict line that is not JSON. A corrupt ledger is never half-read.
    """
    out: dict = {}
    for n, line in enumerate(lines, 1):
        if VERDICT_EVENT not in line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PriorArtError(f"corrupt governed ledger line {where}:{n}: {exc}") from exc
        if e.get("type") != VERDICT_EVENT:
            continue
        p = e.get("payload") or {}
        out.setdefault(p.get("note"), {})[p.get("sha256")] = p
    return out


# -------------------------------------------------------------------------------- the gate

def baseline(s: Settings) -> set:
    """The notes grandfathered by AD-036-R4: every design note on main at PA-001's merge."""
    if not s.baseline.is_file():
        raise PriorArtError(f"the AD-036 baseline list {s.baseline} does not exist")
    return baseline_from_text(s.baseline.read_text(encoding="utf-8"))


def baseline_from_text(text: str) -> set:
    """The baseline list's entries: one path per line, `#` comments and blank lines ignored."""
    return {ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")}


def is_gated(s: Settings, rel: str) -> bool:
    """Is this repository-relative path a gated design note (markdown under the design
    directory, at any depth, and not matching an exempt glob)? The rule `design_notes` walks."""
    if not rel.endswith(".md") or not rel.startswith(s.design_dir.rstrip("/") + "/"):
        return False
    name = rel.rsplit("/", 1)[-1]
    return not any(_glob_re(g).match(name) for g in s.exempt_globs)


def design_notes(s: Settings) -> list[str]:
    """Every gated design note: markdown under the design directory, less the exempt globs."""
    base = s.project_dir / s.design_dir
    if not base.is_dir():
        return []
    exempt = [_glob_re(g) for g in s.exempt_globs]
    out = []
    for p in sorted(base.rglob("*.md")):
        if any(e.match(p.name) for e in exempt):
            continue
        out.append(p.relative_to(s.project_dir).as_posix())
    return out


def gate_status(project_dir: Path, config: dict, notes: Iterable[str] | None = None) -> list[dict]:
    """For each gated note outside the baseline: does a passing verdict exist for its bytes?

    Returns one row per note checked: {note, sha256, ok, why}. A baseline note is not listed.
    """
    s = settings(project_dir, config)
    base = baseline(s)
    have = verdicts(project_dir, config)
    rows = []
    for rel in (notes if notes is not None else design_notes(s)):
        if rel in base:
            continue
        p = s.project_dir / rel
        if not p.is_file():
            rows.append({"note": rel, "sha256": None, "ok": False, "why": "file does not exist"})
            continue
        rows.append(judge(rel, _sha(p.read_bytes()), have))
    return rows


def judge(rel: str, sha: str, have: dict) -> dict:
    """One note's gate row: does `have` (from `verdicts`) hold a passing verdict for these bytes?

    Shared by `gate_status` (the working tree), the commit hook (the staged blob) and the bypass
    audit (the blob a past commit carried), so the three cannot disagree about what passes.
    """
    v = (have.get(rel) or {}).get(sha)
    if v is None:
        why = (f"no prior-art verdict for its current bytes (sha256 {sha[:12]}); run "
               f"`seldon prior-art verify {rel}` (AD-036-R4)")
        return {"note": rel, "sha256": sha, "ok": False, "why": why}
    if v.get("verdict") != "pass":
        return {"note": rel, "sha256": sha, "ok": False,
                "why": "prior-art verdict is fail: " + "; ".join(v.get("problems", [])[:3])
                       + " (AD-036-R4)"}
    return {"note": rel, "sha256": sha, "ok": True, "why": "pass"}


_GOVERNING_BLOCK_RE = re.compile(r"^\*\*Governing:\*\*(.*?)(?=^\*\*[A-Z][^*]*:\*\*|^#|\Z)",
                                 re.MULTILINE | re.DOTALL)
_PATH_RE = re.compile(r"(?:^|[\s`(/])((?:[\w.\-]+/)*docs/design/[\w.\-/]+\.md)")
_ID_RE = re.compile(r"\b((?:AD|DN)-\d{3})\b")


def governing_notes(task_text: str, project_dir: Path, s: Settings) -> list[str]:
    """The design notes in THIS project a task is governed by: every `docs/design/*.md` path the
    task names that resolves here, and every AD-/DN- identifier in its `**Governing:**` block,
    resolved to `docs/design/<id>_*.md` (addenda and errata excluded)."""
    project_dir = Path(project_dir).resolve()
    found = set()
    for m in _PATH_RE.finditer(task_text):
        raw = m.group(1)
        idx = raw.find(s.design_dir + "/")
        rel = raw[idx:] if idx >= 0 else raw
        if (project_dir / rel).is_file():
            found.add(rel)
    exempt = [_glob_re(g) for g in s.exempt_globs]
    for block in _GOVERNING_BLOCK_RE.findall(task_text):
        for ident in _ID_RE.findall(block):
            for p in sorted((project_dir / s.design_dir).glob(f"{ident}_*.md")):
                if not any(e.match(p.name) for e in exempt):
                    found.add(p.relative_to(project_dir).as_posix())
    return sorted(found)


def registration_refusal(task_path: Path, project_dir: Path, config: dict) -> str | None:
    """AD-036-R4, registration: the refusal text when a governing note has no passing verdict.

    None when every governing note in this project is baseline or has a passing verdict for its
    current bytes, or when the project declares no `prior_art:` block (the gate is per project).
    """
    if not isinstance(config.get("prior_art"), dict):
        return None
    s = settings(project_dir, config)
    text = Path(task_path).read_text(encoding="utf-8", errors="replace")
    notes = governing_notes(text, project_dir, s)
    bad = [r for r in gate_status(project_dir, config, notes) if not r["ok"]]
    if not bad:
        return None
    return ("AD-036-R4: refusing to register: the governing design note has no passing "
            "prior-art verdict: " + "; ".join(f"{r['note']}: {r['why']}" for r in bad))
