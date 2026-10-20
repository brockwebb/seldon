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
searched. A query may not contain a double quote. A hit path is percent-encoded (RFC 3986 section
2.1) for `%`, `,` and whitespace, the three characters the grammar uses or splits on; every other
character is written as it is (AD-036 ADDENDUM 04).

**The internal arm** is lexical: case-insensitive, every query term must occur in one paragraph
(a run of non-blank lines), each term matched at a word start, so `pin` finds `pinned`. Paragraphs
are ranked by BM25 (Robertson and Zaragoza 2009) with the parameters in `seldon.yaml`; ranking
only orders what is printed, and verification checks membership in the full match set, so a later
file that outranks a cited hit never fails a receipt. AD-036-R3 says "ripgrep": the semantics are
ripgrep's (a fixed-string, case-insensitive search), but the files are read from git's object
store at the named commit, because verification must re-run the search against that commit and
ripgrep reads only a working tree. The departure is recorded in AD-036 ADDENDUM 01.

**Where verdicts go.** `verify` appends one `provenance` event per run to the governed ledger
(or, in a project with no governed graph, to `gate.verdict_ledger_without_governed`; AD-036
ADDENDUM 03) through squiddy's single write path (`squiddy.ledger.append`): the note's path and sha256, every
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
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import yaml

#: Bumped when the matching, ranking, grammar or verdict rules change. R5's recall control is
#: re-run on every bump, and every logged query and verdict carries it.
TOOL_VERSION = "prior-art/1"

#: Receipt statuses (PA-001 Part A step 2).
PASS = "pass"
ID_NOT_RETURNED = "id_not_returned"
RELEASE_UNAVAILABLE = "release_unavailable"
MALFORMED = "malformed"
#: AD-036-R14 (ADDENDUM 07, DISP-003R): an internal receipt whose every cited location is inside the note under
#: verification (its base or any addendum). The internal arm leaves that note out of its own search (a note is not
#: prior art for itself), so such a receipt can never be returned; it neither passes nor fails the note.
SELF_CITATION = "self_citation"
#: Statuses that do not fail a note.
NOT_FAILING = (PASS, SELF_CITATION)

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
#: A note's identifier, at the start of its name (seldon `AD-036_...`) or after a date prefix
#: (squiddy `2026-10-10_DN-043_...`). SQ-010 Part 0: anchored at the start only, a date-prefixed note
#: never found its addenda.
_NOTE_ID_RE = re.compile(r"^(?:\d{4}-\d{2}-\d{2}_)?((?:AD|DN)-\d{3})(?=_|\.md$)")


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
    #: Where a verdict goes in a project that keeps no governed graph (AD-036 ADDENDUM 03).
    verdict_ledger_without_governed: Path
    #: The seldon.yaml whose block was used, when the project's block is a `ref`; None when the
    #: project defines the block itself.
    defined_in: Optional[Path] = None


_REQUIRED = ("log", "internal_roots", "internal", "library", "gate")

#: The key that makes a project's `prior_art:` block a reference (AD-036 ADDENDUM 03).
REF_KEY = "ref"
#: What a referencing block may set for itself, and nothing else: one definition, never a copy
#: (SQ-010 Part 0). The baseline is per project because it lists THAT project's grandfathered
#: notes; every other key is the machine's one rule and lives only in the file the ref names.
REF_LOCAL_KEYS = {"ref": None, "gate": ("baseline",)}


def resolve_block(project_dir: Path, config: dict) -> tuple[dict, Path, Optional[Path]]:
    """The `prior_art:` block this project runs under: its own, or the one its `ref` names.

    A referencing block is `ref: <file>#<dotted.key>` plus `gate.baseline`, the same
    `<file>#<dotted.path>` form as `dispatch.standing_band_ref` (`seldon.core.dispatch.
    resolve_standing_band`). The file is relative to the referencing seldon.yaml's directory, and
    `~` is expanded. It is read from disk even inside the commit hook: the defining file belongs to
    another repository, whose index this repository's commit cannot stage.

    Returns:
        `(block, definer_dir, defined_in)`: the block with the project's own baseline merged in,
        the directory corpus paths resolve against, and the defining file (None for a block the
        project defines itself, whose definer_dir is the project).

    Raises:
        PriorArtError: No block; a referencing block that sets anything but `ref` and
            `gate.baseline`, or omits the baseline; a malformed ref; a missing file or key; a
            target that is itself a ref (a chain would make "the one definition" two hops away).
    """
    project_dir = Path(project_dir).resolve()
    block = config.get("prior_art")
    if not isinstance(block, dict):
        raise PriorArtError("seldon.yaml has no `prior_art:` block (AD-036-R3)")
    if REF_KEY not in block:
        return block, project_dir, None
    ref = block[REF_KEY]
    if not isinstance(ref, str) or "#" not in ref:
        raise PriorArtError(f"prior_art.ref {ref!r} is not a reference: expected "
                            f"`<file>#<dotted.key>` (AD-036 ADDENDUM 03)")
    rel, dotted = ref.split("#", 1)
    target = Path(os.path.expanduser(rel))
    if not target.is_absolute():
        target = project_dir / target
    target = target.resolve()
    extra = sorted(set(block) - set(REF_LOCAL_KEYS))
    gate_local = block.get("gate") or {}
    if not isinstance(gate_local, dict):
        raise PriorArtError("prior_art.gate in a referencing block must be a mapping holding "
                            "only `baseline`")
    extra += [f"gate.{k}" for k in sorted(set(gate_local) - set(REF_LOCAL_KEYS["gate"]))]
    if extra:
        raise PriorArtError(f"prior_art is a reference to {target}, so it may set only `ref` and "
                            f"`gate.baseline`; it also sets {extra}. One definition, never a copy: "
                            f"change those in {target} (AD-036 ADDENDUM 03)")
    if not gate_local.get("baseline"):
        raise PriorArtError(f"prior_art is a reference to {target} and sets no `gate.baseline`; "
                            f"each project lists its own grandfathered notes (AD-036-R4, "
                            f"ADDENDUM 03)")
    if not target.is_file():
        raise PriorArtError(f"prior_art.ref {ref!r} names {target}, which does not exist")
    node = yaml.safe_load(target.read_text(encoding="utf-8"))
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            raise PriorArtError(f"prior_art.ref {ref!r}: {target} has no {dotted!r}")
        node = node[part]
    if not isinstance(node, dict):
        raise PriorArtError(f"prior_art.ref {ref!r} resolves to {type(node).__name__}, not a "
                            f"prior_art block")
    if REF_KEY in node:
        raise PriorArtError(f"prior_art.ref {ref!r} resolves to another reference "
                            f"({node[REF_KEY]!r}); a ref must name the definition itself, never "
                            f"a chain (AD-036 ADDENDUM 03)")
    merged = dict(node)
    merged["gate"] = {**(node.get("gate") or {}), "baseline": gate_local["baseline"]}
    return merged, target.parent, target


def corpus_anchor(definer_dir: Path) -> Path:
    """The directory a block's relative CORPUS paths resolve against: `definer_dir`, or, when it lies in a linked git
    worktree, the same directory in that repository's primary checkout (AD-036 ADDENDUM 06).

    The corpus is the machine's: `../squiddy` in seldon's block names the repository beside the primary checkout.
    Resolved inside a dispatched session's worktree (`<primary>/.claude/worktrees/<name>`) it named
    `.claude/worktrees/squiddy`, which does not exist, so every sibling receipt and every library receipt verified
    from a worktree failed as `release_unavailable` (MCP-001 RESULT, 2026-10-17). A worktree shares the primary's
    object store, so a receipt's commit is readable from either; only the on-disk layout differs. A directory that is
    not in a git work tree, or is the primary itself, is returned unchanged.
    """
    definer_dir = Path(definer_dir).resolve()
    top = _git(definer_dir, "rev-parse", "--show-toplevel")
    common = _git(definer_dir, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if top.returncode != 0 or common.returncode != 0:
        return definer_dir
    common_dir = Path(common.stdout.decode().strip()).resolve()
    if common_dir.name != ".git":
        return definer_dir            # a bare repository's worktree: no primary checkout to anchor at
    primary, here = common_dir.parent, Path(top.stdout.decode().strip()).resolve()
    if here == primary:
        return definer_dir
    return primary / definer_dir.relative_to(here)


def settings(project_dir: Path, config: dict) -> Settings:
    """The `prior_art:` block of seldon.yaml, validated. Every key is required: a missing one is a
    configuration error named here, never a default the reader cannot see.

    The block may be a reference (`resolve_block`). Paths then resolve by origin, the rule
    TypeScript's tsconfig `extends` uses ("relative paths found in the configuration file will be
    resolved relative to the configuration file they originated in"), split by what a path names:
    the CORPUS (internal_roots[].path, library.graph) is the machine's and resolves against the
    defining file's directory; the PROJECT'S OWN STATE (log, gate.design_dir, gate.baseline,
    gate.verdict_ledger_without_governed) resolves against the project using the block. For a
    block a project defines itself the two directories are the same.

    A defining file inside a linked git worktree anchors its corpus at the PRIMARY checkout
    (`corpus_anchor`, AD-036 ADDENDUM 06): `../squiddy` names the primary's sibling, and a
    dispatched session's worktree under `.claude/worktrees/` has no siblings.
    """
    project_dir = Path(project_dir).resolve()
    block, definer_dir, defined_in = resolve_block(project_dir, config)
    corpus_dir = corpus_anchor(definer_dir)
    where = f"{defined_in} prior_art" if defined_in else "seldon.yaml prior_art"
    missing = [k for k in _REQUIRED if k not in block]
    if missing:
        raise PriorArtError(f"{where} block missing {missing}")
    internal, library, gate = block["internal"], block["library"], block["gate"]
    for name, sub, keys in (("internal", internal, ("default_include", "suffixes", "top_n",
                                                     "max_file_bytes", "bm25")),
                            ("library", library, ("graph", "k")),
                            ("gate", gate, ("design_dir", "baseline", "exempt_globs",
                                            "verdict_ledger_without_governed"))):
        miss = [k for k in keys if k not in (sub or {})]
        if miss:
            raise PriorArtError(f"{where}.{name} missing {miss}")

    def at(base: Path, p: str) -> Path:
        q = Path(os.path.expanduser(str(p)))
        return q if q.is_absolute() else (base / q).resolve()

    roots = []
    for row in block["internal_roots"]:
        if not isinstance(row, dict) or not row.get("name") or not row.get("path"):
            raise PriorArtError(f"prior_art.internal_roots row {row!r} needs `name` and `path`")
        roots.append(Root(name=str(row["name"]), path=at(corpus_dir, row["path"]),
                          include=tuple(row.get("include") or internal["default_include"])))
    names = [r.name for r in roots]
    if len(set(names)) != len(names):
        raise PriorArtError(f"prior_art.internal_roots names are not unique: {names}")

    return Settings(project_dir=project_dir, log=at(project_dir, block["log"]), roots=tuple(roots),
                    suffixes=tuple(internal["suffixes"]), top_n=int(internal["top_n"]),
                    max_file_bytes=int(internal["max_file_bytes"]),
                    k1=float(internal["bm25"]["k1"]), b=float(internal["bm25"]["b"]),
                    library_graph=at(corpus_dir, library["graph"]), library_k=int(library["k"]),
                    design_dir=str(gate["design_dir"]), baseline=at(project_dir, gate["baseline"]),
                    exempt_globs=tuple(gate["exempt_globs"]),
                    verdict_ledger_without_governed=at(project_dir,
                                                       gate["verdict_ledger_without_governed"]),
                    defined_in=defined_in)


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
        return f"{encode_hit_path(self.path)}:{self.start}" + ("" if self.tracked else f"#sha256={self.sha12}")


def encode_hit_path(path: str) -> str:
    """A hit path as a receipt writes it: `%`, `,` and whitespace percent-encoded, nothing else.

    MODEL-003 found the defect: a path containing spaces (ai-readiness-kg `docs/research/AI Readiness  A ...md`)
    was printed as-is, and the verifier, which reads a hit as one non-space token and splits hits on commas, called
    the receipt `malformed`. Only the characters the grammar itself uses are encoded, so every path the old grammar
    could express is written exactly as before and `urllib.parse.unquote` reads it back unchanged."""
    out = []
    for ch in path:
        if ch == "%" or ch == "," or ch.isspace():
            out.append("".join(f"%{b:02X}" for b in ch.encode("utf-8")))
        else:
            out.append(ch)
    return "".join(out)


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

    def search(self, query: str, roots: Iterable[str] | None = None, exclude: frozenset = frozenset()) -> dict:
        """`exclude` is `note_keys` of the note the receipts are for: a note is not prior art for itself, and a receipt
        naming its own bytes cannot verify once it is inserted (QC-001 premise 3)."""
        wanted = set(roots) if roots else None
        corpora = [self.corpus(r) for r in self.s.roots if wanted is None or r.name in wanted]
        hits = [h for h in search_corpora(query, corpora, self.s) if (h.root, h.path) not in exclude]
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


#: The library graph's export register: one row per release, carrying the first 16 hex of the release's sha256.
#: Its name and place are the kit's (`squiddy.registers` writes it, `squiddy.gates.derive_position` reads it), so
#: this is a file-format coupling, as the governed ledger is (AD-030-R10), not a tunable.
EXPORT_REGISTER = "EXPORT_VERSIONS.md"
#: The corpus checkpoint and the dense shard directory inside the index work directory, as `squiddy.index.build`
#: names them (`wd / "corpus_rows.jsonl"`, `wd / "dense"`). The same coupling as EXPORT_REGISTER.
CORPUS_ROWS = "corpus_rows.jsonl"
DENSE_DIR = "dense"


class Library:
    """The library arm: squiddy's served `search` verb, in-process (AD-036-R3), and any older release a receipt names,
    rebuilt from the library's own checkpoints (AD-036 ADDENDUM 06)."""

    def __init__(self, s: Settings):
        self.s = s
        self._verbs = None
        self._graph = None
        self._qenc = None
        self._digests: dict = {}
        #: The one rebuilt older release held open: `(sha256, index, info, TemporaryDirectory)`. One at a time,
        #: because each holds a dense matrix the size of the served one; `_verify_library` orders its work by release.
        self._rebuilt = None

    @staticmethod
    def _offline() -> None:
        # The library search is local; nothing here may reach a network (PA-001: Network none).
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        # The internal arm forks git after the encoder has loaded; say so up front rather than
        # let the tokenizer library warn on every fork.
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    def graph(self):
        """The library graph's squiddy `Graph`, loaded once."""
        if self._graph is None:
            self._offline()
            try:
                from squiddy.config import load_graph
            except ImportError as exc:
                raise PriorArtError(f"the library arm needs squiddy installed in this interpreter "
                                    f"(pip install -e <squiddy> --no-deps): {exc}") from exc
            if not self.s.library_graph.is_dir():
                raise PriorArtError(f"{RELEASE_UNAVAILABLE}: library graph "
                                    f"{self.s.library_graph} does not exist")
            self._graph = load_graph(str(self.s.library_graph))
        return self._graph

    def verbs(self):
        if self._verbs is None:
            graph = self.graph()
            from squiddy.serve import Verbs
            self._verbs = Verbs(graph)
            # One query encoder for the served index and any rebuilt one (`Verbs` reads this attribute when it opens
            # its index): each is the pinned model, so two would only double the memory.
            self._verbs._query_encoder = self._encoder
        return self._verbs

    def _encoder(self, q: str):
        if self._qenc is None:
            from squiddy import index as ix
            self._qenc = ix.query_encoder(ix.load_config(self.graph())["encoder"])
        return self._qenc(q)

    @staticmethod
    def _rows(hits: list) -> list:
        return [r["receipt"]["row_id"] for h in hits for r in h["rows"]
                if (r.get("receipt") or {}).get("row_id")]

    def search(self, query: str, k: int | None = None) -> dict:
        """The served release's top-k: the receipt `search --library` prints, and verification's current-release
        path."""
        terms_of(query)
        res = self.verbs().search(query, k=k or self.s.library_k)
        if res.get("error"):
            raise PriorArtError(f"{RELEASE_UNAVAILABLE}: library search failed: {res['error']}")
        rel = (res.get("index") or {}).get("release") or {}
        return {"query": query, "release": Path(str(rel.get("export"))).name,
                "sha256": rel.get("sha256"), "rows": self._rows(res["hits"]), "hits": res["hits"],
                "index": "served"}

    def exports_dir(self) -> Path:
        """Where the library keeps its release exports (the graph's `exports_dir`)."""
        return Path(self.graph().path("exports_dir"))

    def export_path(self, release: str) -> Path:
        """The export file a receipt's `release` names. A release is a file NAME in the exports directory; a name
        carrying a path is refused rather than followed out of it."""
        if not release or Path(release).name != release or release in (".", ".."):
            raise PriorArtError(f"{RELEASE_UNAVAILABLE}: release {release!r} is not a file name in the library's "
                                f"exports directory")
        return self.exports_dir() / release

    def _digest(self, path: Path) -> str:
        st = path.stat()
        key = (str(path), st.st_size, st.st_mtime_ns)
        if key not in self._digests:
            self._digests[key] = _sha_file(path)
        return self._digests[key]

    def search_release(self, query: str, release: str, sha256: str, k: int | None = None) -> dict:
        """The top-k of the release a receipt NAMES (AD-036-R2, R3; ADDENDUM 06): its export must be on disk and hash
        to `sha256`; its index is rebuilt in a temporary directory (`rebuild_release`) and queried exactly as the
        served one is.

        Raises:
            PriorArtError: `release_unavailable`, naming the path looked for, when the export is absent or its
                bytes do not hash to `sha256`, or when the release cannot be rebuilt (the reason named).
        """
        terms_of(query)
        path = self.export_path(release)
        if not path.is_file():
            raise PriorArtError(f"{RELEASE_UNAVAILABLE}: release {release} is not on disk: looked for {path}")
        got = self._digest(path)
        if got != sha256:
            raise PriorArtError(f"{RELEASE_UNAVAILABLE}: {path} hashes to sha256:{got[:12]}..., not the "
                                f"sha256:{sha256[:12]}... the receipt names")
        idx, info = self._release_index(release, sha256, path)
        res = idx.search(query, k or self.s.library_k)
        return {"query": query, "release": release, "sha256": sha256, "rows": self._rows(res["hits"]),
                "hits": res["hits"], "index": "rebuilt", "export_path": str(path),
                "commit": info.get("commit"), "index_rows": info.get("rows")}

    def _release_index(self, release: str, sha256: str, path: Path):
        """`(index, info)` for an older release, rebuilt once and held until another release is asked for."""
        if self._rebuilt and self._rebuilt[0] == sha256:
            return self._rebuilt[1], self._rebuilt[2]
        self.close()
        import tempfile
        tmp = tempfile.TemporaryDirectory(prefix="prior-art-release-")
        try:
            idx, info = self._rebuild(sha256, Path(tmp.name))
        except BaseException:
            tmp.cleanup()
            raise
        self._rebuilt = (sha256, idx, info, tmp)
        return idx, info

    def _rebuild(self, sha256: str, work: Path):
        """`(index, info)`: the release rebuilt in `work` and opened for query."""
        info = rebuild_release(self.graph(), sha256, work)
        return open_rebuilt(info, self._encoder), info

    def close(self) -> None:
        """Drop the rebuilt release and its temporary directory."""
        if self._rebuilt:
            self._rebuilt[3].cleanup()
            self._rebuilt = None

    @staticmethod
    def receipt(result: dict) -> str:
        rows = ", ".join(result["rows"]) or "none"
        return (f'- library receipt: query "{result["query"]}" | release {result["release"]} '
                f'sha256:{result["sha256"]} | rows {rows}')


def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def release_commit(register: Path, sha256: str) -> str | None:
    """The first commit of the register's repository whose `register` carries the release's digest (its first 16 hex
    in backticks, as the kit writes a row), or None.

    That commit records the release, so it holds the corpus manifest the release's index was built from: on
    2026-10-19 the commit recording `20261017_sq018_02` held a `corpus/manifest.yaml` hashing to exactly the sha256
    the served index manifest records (AD-036 ADDENDUM 06)."""
    register = Path(register).resolve()
    r = _git(register.parent, "log", "--reverse", "--format=%H", f"-S`{sha256[:16]}`", "--", register.name)
    if r.returncode != 0:
        return None
    lines = r.stdout.decode().split()
    return lines[0] if lines else None


def rebuild_release(graph, sha256: str, work: Path) -> dict:
    """Rebuild the library index of the release whose export hashes to `sha256`, in `work`, encoding nothing.

    The served index is rebuilt in place at every release, so an older release's index survives only as its inputs,
    and the kit keeps every one of them (AD-036 ADDENDUM 06):

    1. the corpus manifest, from the commit that recorded the release (`release_commit`);
    2. the rows, from the index's corpus checkpoint, which keeps one line per (unit, content sha256, rule) and never
       drops one (`squiddy.index.iter_rows`; a unit it lacks is a refusal, not a gap);
    3. the database, built by the kit's own `build_db` into `work`;
    4. the vectors, from the dense shard log, which never deletes a shard: for each entry, the shard KEYED under the
       key the kit computes from that entry's rows at that release (`squiddy.index.unit_key`), live or retired,
       its bytes and row ids verified as the kit verifies them.

    The query-time configuration is today's `index:` block, which must equal the block at the release's commit;
    otherwise the rebuilt index would rank under parameters the receipt never ran with.

    Returns:
        `{commit, db, dense_dir, shards, rows, row_fingerprint, shard_set_sha256, cfg, release_sha256}`, which
        `open_rebuilt` opens for query.

    Raises:
        PriorArtError: `release_unavailable`, naming what is missing.
    """
    from squiddy import index as ix
    unavailable = f"{RELEASE_UNAVAILABLE}: release sha256:{sha256[:12]}... cannot be rebuilt"
    try:
        cfg = ix.load_config(graph)
    except ix.NotApplicable as exc:
        raise PriorArtError(f"{unavailable}: the library declares no index ({exc})") from exc
    if ix.units_source(cfg) == ix.UNITS_LEDGER_NODES:
        raise PriorArtError(f"{unavailable}: an index over ledger nodes depends on the ledger at the release, which "
                            f"this rebuild does not replay")
    register = Path(graph.path("exports_dir")) / EXPORT_REGISTER
    commit = release_commit(register, sha256)
    if commit is None:
        raise PriorArtError(f"{unavailable}: no commit of {register} carries `{sha256[:16]}`")
    top = _git(register.parent, "rev-parse", "--show-toplevel")
    repo = Path(top.stdout.decode().strip()).resolve()

    def at_commit(p: Path) -> str:
        rel = Path(p).resolve().relative_to(repo).as_posix()
        r = _git(repo, "show", f"{commit}:{rel}")
        if r.returncode != 0:
            raise PriorArtError(f"{unavailable}: {rel} is not in commit {commit[:12]}: "
                                f"{r.stderr.decode().strip()}")
        return r.stdout.decode("utf-8")

    control = Path(ix.control_path(graph))
    then = (yaml.safe_load(at_commit(control)) or {}).get("index")
    now = (yaml.safe_load(control.read_text(encoding="utf-8")) or {}).get("index")
    if then != now:
        raise PriorArtError(f"{unavailable}: the `index:` block of {control} at {commit[:12]} differs from today's; "
                            f"the release ranked under other parameters")
    manifest = (yaml.safe_load(at_commit(graph.manifest_path)) or {}).get("documents")
    if not isinstance(manifest, list):
        raise PriorArtError(f"{unavailable}: the corpus manifest at {commit[:12]} has no `documents` list")
    stage = ix.in_graph_stage(graph)
    wd = ix.work_dir(graph, cfg)
    try:
        rows = list(ix.iter_rows(wd / CORPUS_ROWS, manifest, ix.meta_renderer(cfg), stage, None))
    except SystemExit as exc:          # the kit's refusal: a unit of that release has no checkpointed rows
        raise PriorArtError(f"{unavailable}: {exc}") from exc
    db = Path(work) / "corpus.db"
    built = ix.build_db(rows, db)
    del rows
    enc, dense = cfg["encoder"], cfg["dense"]
    text_sha = {e["id"]: (e["text_sha256"] if ix.acquired(e) else None) for e in manifest if ix.indexed(e, stage)}
    ddir = wd / DENSE_DIR
    log = ddir / ix.SHARD_LOG
    if not log.is_file():
        raise PriorArtError(f"{unavailable}: no dense shard log at {log}")
    keyed = {(ev["entry"], ev["key"]): ev for ev in ix.read_jsonl(log) if ev.get("event") == "keyed"}
    shards = []
    for entry, erows in sorted(ix.unit_rows(db).items()):
        key = ix.unit_key(entry, text_sha.get(entry), erows, enc, dense["pad_to"])
        rec = keyed.get((entry, key))
        if rec is None:
            raise PriorArtError(f"{unavailable}: entry {entry} has no dense shard keyed {key[:12]} in {log}")
        p = ddir / rec["npy"]
        if not p.is_file() or _sha_file(p) != rec["npy_sha256"]:
            raise PriorArtError(f"{unavailable}: dense shard {p} is missing or does not hash to its keyed line")
        want = [row for _rid, row, _t in erows]
        if json.loads((ddir / rec["ids"]).read_text(encoding="utf-8")) != want:
            raise PriorArtError(f"{unavailable}: dense shard {p}: its row ids are not the release's rows for {entry}")
        shards.append({**rec, "row_ids": want})
    return {"commit": commit, "db": str(db), "dense_dir": str(ddir), "shards": shards, "rows": built["rows"],
            "row_fingerprint": ix.row_fingerprint(db), "shard_set_sha256": ix.shard_set_sha256(shards),
            "cfg": cfg, "release_sha256": sha256}


def open_rebuilt(info: dict, query_encoder) -> object:
    """A rebuilt release (`rebuild_release`) opened for query through the kit's own `Index`: the served query path,
    line for line."""
    import numpy as np
    from squiddy import index as ix
    ddir = Path(info["dense_dir"])
    parts, ids = [], []
    for s in info["shards"]:
        parts.append(np.load(ddir / s["npy"]))
        ids.extend(s["row_ids"])
    dim = int(info["cfg"]["encoder"]["dimension"])
    matrix = np.concatenate(parts, axis=0) if parts else np.zeros((0, dim), dtype="float32")
    man = {"rule": ix.INDEX_RULE, "release": {"sha256": info["release_sha256"], "rebuilt_from": info["commit"]},
           "rows": info["rows"]}
    return ix.Index(Path(info["db"]), (ids, matrix), info["cfg"], query_encoder, man)


def note_keys(s: Settings, paths: Iterable[Path]) -> frozenset:
    """`{(root name, path within the root)}` for each file that lies inside an internal root: what the internal arm
    leaves out when it searches for, or verifies, the receipts of these files (QC-001 premise 3)."""
    out = set()
    for p in paths:
        rp = Path(p).resolve()
        for r in s.roots:
            try:
                out.add((r.name, rp.relative_to(r.path.resolve()).as_posix()))
            except ValueError:
                continue
    return frozenset(out)


def log_query(s: Settings, record: dict) -> None:
    """Append one line to the query log, flushed and fsynced (constitution section 15).

    The log is `s.log`, resolved against the calling project (AD-036-R10), and each line names that project, so a
    line that is ever found in the wrong repository says whose it is."""
    s.log.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"ts": _now(), "tool": TOOL_VERSION, "project": s.project_dir.name, **record},
                      sort_keys=True, default=str)
    with s.log.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")


# ------------------------------------------------------------------ the calling project (AD-036-R10)

PROJECT_FILE = "seldon.yaml"


def project_of(path: Path) -> Path | None:
    """The nearest directory at or above `path` holding a `seldon.yaml`, or None.

    The discovery rule git uses for `.git`: a command run anywhere inside a project acts on that project."""
    p = Path(path).expanduser().resolve()
    for d in ([p] if p.is_dir() else []) + list(p.parents):
        if (d / PROJECT_FILE).is_file():
            return d
    return None


def calling_project(explicit: Path | str | None, note: Path | str | None, cwd: Path | str) -> Path:
    """The repository whose evidence a search or a verify is (AD-036-R10).

    In order: `explicit` (`--project`, or an MCP `project_dir`); the repository holding `note` (a relative note is
    read against `cwd`); the project at or above `cwd`. A receipt's log line belongs beside the document the receipt
    supports, so a search run from seldon's checkout for a squiddy note is logged, and committed, in squiddy.

    Raises:
        PriorArtError: `explicit` holds no seldon.yaml, or none of the three resolves to a project.
    """
    if explicit is not None:
        d = Path(explicit).expanduser().resolve()
        if not (d / PROJECT_FILE).is_file():
            raise PriorArtError(f"--project {d} holds no {PROJECT_FILE}")
        return d
    cwd = Path(cwd).expanduser().resolve()
    if note:
        n = Path(note).expanduser()
        found = project_of(n if n.is_absolute() else cwd / n)
        if found is not None:
            return found
    found = project_of(cwd)
    if found is None:
        raise PriorArtError(f"no {PROJECT_FILE} at or above {cwd}; run from a project or pass --project")
    return found


# ------------------------------------------------------------- committing what was written (AD-036-R11)

def _git_out(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True)


def append_state(project_dir: Path, paths: Iterable[Path]) -> dict:
    """`{path: True}` for each path whose working copy differs from HEAD (or that is untracked and present) BEFORE a
    run writes to it. A run commits only the files it found clean: lines already waiting in a file are someone
    else's, and a commit made by this run must contain only this run's lines (the rule the event store's per-tool
    commits keep)."""
    out = {}
    for p in paths:
        p = Path(p)
        rel = _rel_to(project_dir, p)
        if rel is None:
            out[str(p)] = True
            continue
        head = _git_out(project_dir, "show", f"HEAD:{rel}")
        if head.returncode != 0:
            out[str(p)] = p.exists()
        else:
            out[str(p)] = (p.read_bytes() if p.exists() else b"") != head.stdout
    return out


def _rel_to(project_dir: Path, p: Path) -> str | None:
    try:
        return Path(p).resolve().relative_to(Path(project_dir).resolve()).as_posix()
    except ValueError:
        return None


def _appended_lines_ok(project_dir: Path, rel: str, accept) -> str | None:
    """None when the file's change against HEAD is append-only and every appended line parses and passes `accept`;
    otherwise the reason."""
    path = Path(project_dir) / rel
    head = _git_out(project_dir, "show", f"HEAD:{rel}")
    base = head.stdout if head.returncode == 0 else b""
    work = path.read_bytes()
    if not work.startswith(base):
        return "not_append_only"
    for raw in work[len(base):].decode("utf-8").splitlines():
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            return "unparseable"
        if not accept(row):
            return "foreign_lines"
    return None


def _is_log_line(row: dict) -> bool:
    return str(row.get("tool", "")).startswith("prior-art/")


def _is_verdict_line(row: dict) -> bool:
    return row.get("type") == VERDICT_EVENT


def _lease_defers(project_dir: Path, config: dict) -> bool:
    """Is another session working here under a dispatcher lease? Then nothing is committed beside it (DN-006
    ADDENDUM 04: "a pass never commits without the lease"); the next pass that takes the lease commits the lines
    (`commit_leftovers`). A session the lease launched (`SELDON_SESSION_ID` is its child session) is not "another
    session": committing its own writes is its job."""
    from seldon.core import dispatch as D
    try:
        cfg = D.load_dispatch_config(Path(project_dir), config)
    except (D.DispatchConfigError, OSError):
        return False
    if not D.lease_is_held(project_dir, cfg):
        return False
    body = D.read_lease(Path(project_dir) / cfg["lease_file"]) or {}
    sid = os.environ.get("SELDON_SESSION_ID")
    if not sid or not body.get("task"):
        return True
    from seldon.core import stations
    store = Path(project_dir) / (config or {}).get("event_store", {}).get("path", "seldon_events.jsonl")
    events = []
    if store.is_file():
        with store.open(encoding="utf-8") as fh:
            for raw in fh:
                if '"dispatch_launched"' in raw:
                    try:
                        events.append(json.loads(raw))
                    except json.JSONDecodeError:
                        continue
    launch = stations.launch_for_session(events, sid)
    return not (launch and (launch.get("payload") or {}).get("task_id") == body.get("task"))


def commit_appends(project_dir: Path, config: dict, written: dict, message: str) -> dict:
    """Commit the prior-art files this run appended to, path-scoped and through the hooks (AD-036-R11).

    Args:
        project_dir: The calling project.
        config: Its seldon.yaml.
        written: `{path: dirty_before}` from `append_state`, for the files the run appended to.
        message: The commit message.

    Returns:
        `{committed, reason, ...}`; `reason` is None, `not_a_work_tree`, `lease_held`, `nothing_to_commit`,
        `dirty_before_this_run`, `not_append_only`, `unparseable`, `foreign_lines`, `git_add_failed` or
        `git_commit_failed`. **Never raises on a git state**: the search or verify did its work, and its bookkeeping
        reports rather than undoing it. The caller prints any reason that leaves a file dirty.
    """
    from seldon.core import dispatch as D
    project_dir = Path(project_dir).resolve()
    top = _git_out(project_dir, "rev-parse", "--show-toplevel")
    if top.returncode != 0 or Path(top.stdout.decode().strip()).resolve() != project_dir:
        return {"committed": False, "reason": "not_a_work_tree"}
    rels, skipped = [], []
    for p, dirty_before in written.items():
        rel = _rel_to(project_dir, Path(p))
        if rel is None or not Path(p).exists():
            continue
        if D.git(project_dir, "check-ignore", "-q", "--", rel).returncode == 0:
            continue
        if dirty_before:
            skipped.append(rel)
            continue
        rels.append(rel)
    if not rels:
        return {"committed": False, "reason": "dirty_before_this_run" if skipped else "nothing_to_commit",
                "skipped": skipped}
    for rel in rels:
        why = _appended_lines_ok(project_dir, rel, lambda row: _is_log_line(row) or _is_verdict_line(row))
        if why:
            return {"committed": False, "reason": why, "path": rel, "skipped": skipped}
    if _lease_defers(project_dir, config):
        return {"committed": False, "reason": "lease_held", "skipped": skipped}
    out = D.commit_paths(project_dir, rels, message)
    out["skipped"] = skipped + out.get("skipped", [])
    return out


def prior_art_paths(project_dir: Path, config: dict) -> list[Path]:
    """The files `search` and `verify` append to in this project: the query log and the verdict ledger."""
    s = settings(project_dir, config)
    return [s.log, verdict_ledger(project_dir, config)]


def commit_leftovers(project_dir: Path, config: dict) -> dict:
    """The dispatcher pass's sweep: commit prior-art lines a run left uncommitted (a run deferred by the lease, or one
    whose commit failed). Called by a pass that holds the lease with no claim in flight, before it reads the tree.

    Commits the query log only when every appended line is a query-log line, and the verdict ledger only when every
    appended line is a verdict; a ledger carrying anyone else's lines is theirs to commit, and stays dirty for c7 to
    name. Returns `{committed, reason, ...}` as `commit_appends` does; `no_prior_art_block` when the project has none.
    """
    from seldon.core import dispatch as D
    if not isinstance((config or {}).get("prior_art"), dict):
        return {"committed": False, "reason": "no_prior_art_block"}
    project_dir = Path(project_dir).resolve()
    s = settings(project_dir, config)
    rels = []
    for p, accept in ((s.log, _is_log_line), (verdict_ledger(project_dir, config), _is_verdict_line)):
        rel = _rel_to(project_dir, p)
        if rel is None or not p.is_file():
            continue
        if D.git(project_dir, "check-ignore", "-q", "--", rel).returncode == 0:
            continue
        head = _git_out(project_dir, "show", f"HEAD:{rel}")
        if head.returncode == 0 and p.read_bytes() == head.stdout:
            continue
        if _appended_lines_ok(project_dir, rel, accept) is None:
            rels.append(rel)
    if not rels:
        return {"committed": False, "reason": "nothing_to_commit"}
    return D.commit_paths(project_dir, rels, f"record: prior-art lines left uncommitted ({', '.join(rels)}), "
                                             f"committed by the standing dispatcher (AD-036-R11)")


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
                r.hits.append((urllib.parse.unquote(hm.group(1)), int(hm.group(2)), hm.group(3)))
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
    if m is None:
        return sorted(p for p in note.parent.glob(f"{note.stem}_ADDENDUM_*.md") if p != note)
    # Same identifier, with or without a date prefix: an addendum is dated the day it is written,
    # which is rarely the base note's date.
    return sorted(p for p in note.parent.glob("*_ADDENDUM_*.md")
                  if p != note and (a := _NOTE_ID_RE.match(p.name)) and a.group(1) == m.group(1))


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
                "receipts": [r.as_dict() for r in self.receipts],
                "self_citations": [f"{r.source}:{r.line}" for r in self.receipts if r.status == SELF_CITATION],
                "tool": TOOL_VERSION, "authority": "AD-036-R2, R4, R14"}


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
    owned = library is None
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
    try:
        _verify_library([r for r in receipts if r.kind == "library" and not r.status], s, library)
    finally:
        if owned:
            library.close()       # a rebuilt release's temporary index goes with the Library that built it
    _verify_internal([r for r in receipts if r.kind == "internal" and not r.status], s, internal,
                     exclude=note_keys(s, files))
    for r in receipts:
        if r.kind == "web" and not r.status:
            r.status, r.detail = PASS, "well-formed; a web page is not re-fetched"
    for sub in ("External", "Internal"):
        rs = by_sub[sub]
        if rs and all(r.status == SELF_CITATION for r in rs):
            problems.append(f"`### {sub}` carries only self-citations, which are not prior art (AD-036-R14)")
    bad = [r for r in receipts if r.status not in NOT_FAILING]
    for r in bad:
        problems.append(f"{r.source}:{r.line} {r.kind} receipt {r.status}: {r.detail}")
    return Verdict(note=_rel(s, note), sha256=_sha(note.read_bytes()),
                   addenda=[{"path": _rel(s, f), "sha256": _sha(f.read_bytes())} for f in files[1:]],
                   verdict="pass" if not problems else "fail", problems=problems,
                   receipts=receipts)


def _verify_library(receipts: list, s: Settings, library: Library) -> None:
    """Each library receipt re-run against the release it NAMES (AD-036-R2, R3; ADDENDUM 06).

    A receipt naming the served release is judged on the served search, as before. Any other receipt is re-run with
    `library.search_release`, which rebuilds the named release when its export is on disk with the named digest and
    raises `release_unavailable` (naming the path) when it is not. That work runs grouped by release, so each older
    release is rebuilt once per verification. Every run is logged with the release it ran against."""
    def judge(r: Receipt, res: dict) -> None:
        got = set(res["rows"])
        missing = [x for x in r.rows if x not in got]
        if missing:
            r.status = ID_NOT_RETURNED
            r.detail = f"not returned in the top {s.library_k}: {', '.join(missing[:5])}"
        else:
            r.status, r.detail = PASS, f"{len(r.rows)} row(s) returned"

    def logged(res: dict) -> None:
        log_query(s, {"arm": "library", "purpose": "verify", "query": res["query"], "release": res["release"],
                      "sha256": res["sha256"], "rows": len(res["rows"]), "index": res.get("index", "served"),
                      **{k: res[k] for k in ("export_path", "commit") if res.get(k)}})

    groups: dict = {}
    for r in receipts:
        groups.setdefault(r.query, []).append(r)
    elsewhere: dict = {}
    for query, rs in groups.items():
        try:
            res = library.search(query)
        except PriorArtError as exc:
            served_error, res = str(exc), None
        else:
            served_error = None
            logged(res)
        for r in rs:
            if res is not None and r.sha256 == res["sha256"]:
                judge(r, res)
            else:
                elsewhere.setdefault((r.sha256, r.release, query), []).append((r, served_error))
    for (sha, release, query), items in sorted(elsewhere.items()):
        try:
            res = library.search_release(query, release, sha)
        except PriorArtError as exc:
            for r, served_error in items:
                r.status = RELEASE_UNAVAILABLE
                r.detail = str(exc) + (f" (and the served search failed: {served_error})" if served_error else "")
            continue
        logged(res)
        for r, _e in items:
            judge(r, res)


def _verify_internal(receipts: list, s: Settings, internal: Internal, exclude: frozenset = frozenset()) -> None:
    """Each receipt re-run at its commit. The note being verified and its addenda (`exclude`) are left out of the
    search: a note is not prior art for itself (QC-001 premise 3). A cited location inside them is therefore a
    self-citation, not a miss (AD-036-R14): a receipt citing only such locations is `self_citation` and is not
    re-run; in a receipt that also cites other locations those are checked as usual and the self-citations named."""
    roots = {r.name: r for r in s.roots}
    for r in receipts:
        root = roots.get(r.repo)
        if root is None:
            r.status, r.detail = MALFORMED, (f"repo {r.repo!r} is not in prior_art.internal_roots "
                                             f"({', '.join(roots)})")
            continue
        own = [f"{path}:{line}" for path, line, _sha in r.hits if (root.name, path) in exclude]
        if r.hits and len(own) == len(r.hits):
            r.status, r.detail = SELF_CITATION, ("cites the note under verification, which is not prior art for "
                                                 "itself: " + ", ".join(own[:5]) + " (AD-036-R14)")
            continue
        try:
            corpus = internal.corpus(root, r.commit)
        except PriorArtError as exc:
            r.status, r.detail = RELEASE_UNAVAILABLE, str(exc)
            continue
        hits = [h for h in search_corpora(r.query, [corpus], s) if (h.root, h.path) not in exclude]
        log_query(s, {"arm": "internal", "purpose": "verify", "query": r.query,
                      "corpora": {root.name: corpus.identity}, "hits": len(hits)})
        found = {(h.path, h.start): h for h in hits}
        missing, moved = [], []
        for path, line, sha12 in r.hits:
            h = found.get((path, line))
            if (root.name, path) in exclude:
                continue                    # a self-citation beside other hits: named below, never a miss
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
            r.status, r.detail = PASS, f"{len(r.hits) - len(own)} hit(s) returned of {len(hits)}"
        if own:
            r.detail += "; self-citation(s) not checked: " + ", ".join(own[:5]) + " (AD-036-R14)"


# ------------------------------------------------------------------------- the ledger verdict

def governed_ledger(project_dir: Path, config: dict) -> Path | None:
    """This project's governed ledger, or None when the project keeps no governed graph."""
    from seldon.core.governed import ledger_path
    p = ledger_path(Path(project_dir), config)
    return p if p.parent.is_dir() else None


def verdict_ledger(project_dir: Path, config: dict) -> Path:
    """Where this project's AD-036-R4 verdicts live: the governed ledger when the project keeps a
    governed graph, otherwise `gate.verdict_ledger_without_governed` (AD-036 ADDENDUM 03).

    Before the fallback a project with no governed graph could not record a verdict, so once the
    gate reached it (SQ-010 Part 0) every new design note would have been refused for good.
    """
    gov = governed_ledger(project_dir, config)
    if gov is not None:
        return gov
    return settings(project_dir, config).verdict_ledger_without_governed


def record_verdict(v: Verdict, project_dir: Path, config: dict) -> dict:
    """Append the verdict to the verdict ledger through squiddy's single write path (R4)."""
    path = verdict_ledger(project_dir, config)
    try:
        from squiddy import ledger as L
    except ImportError as exc:
        raise PriorArtError(f"recording a verdict needs squiddy installed: {exc}") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    event = L.make_event(run_id=L.new_run_id("prior_art_verify"), stage="prior_art_verify",
                         etype=VERDICT_EVENT, schema_version="1", kind="provenance", doc_id=None,
                         payload=v.as_payload(),
                         provenance={"source": f"seldon prior-art verify {v.note}",
                                     "tool": TOOL_VERSION, "authority": "AD-036-R4"})
    L.append(path, [event], canonical=path)
    return event


def verdicts(project_dir: Path, config: dict) -> dict:
    """{note path: newest verdict payload per note sha256} read from the verdict ledger.

    Returns {note: {sha256: payload}} with the newest event winning for each (note, sha256).
    """
    path = verdict_ledger(project_dir, config)
    if not path.is_file():
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
    """The design notes in THIS project a task is governed by, read from its `**Governing:**` block only
    (AD-036-R15): every `docs/design/*.md` path in the block that resolves here, and every AD-/DN- identifier
    in it, resolved to `docs/design/<id>_*.md` (addenda and errata excluded). A `docs/design/` path anywhere
    else in the task (a premise, the note a task repairs) is text: STD-001 and DISP-003 were held
    `governing_unverified` for naming the note they repair."""
    project_dir = Path(project_dir).resolve()
    found = set()
    blocks = _GOVERNING_BLOCK_RE.findall(task_text)
    for block in blocks:
        for m in _PATH_RE.finditer(block):
            raw = m.group(1)
            idx = raw.find(s.design_dir + "/")
            rel = raw[idx:] if idx >= 0 else raw
            if (project_dir / rel).is_file():
                found.add(rel)
    exempt = [_glob_re(g) for g in s.exempt_globs]
    for block in blocks:
        for ident in _ID_RE.findall(block):
            for p in sorted((project_dir / s.design_dir).glob(f"*{ident}_*.md")):
                own = _NOTE_ID_RE.match(p.name)
                if own and own.group(1) == ident and not any(e.match(p.name) for e in exempt):
                    found.add(p.relative_to(project_dir).as_posix())
    return sorted(found)


def registration_holds(task_path: Path, project_dir: Path, config: dict) -> list[dict]:
    """AD-036-R4 as amended by ADDENDUM 05 (DESK-001): the governing notes of this project with no
    passing verdict for their current bytes, as `gate_status` rows. Registration records and
    reports them; the dispatcher refuses the task on them (`governing_unverified`). Empty when the
    project declares no `prior_art:` block (the gate is per project)."""
    if not isinstance(config.get("prior_art"), dict):
        return []
    s = settings(project_dir, config)
    text = Path(task_path).read_text(encoding="utf-8", errors="replace")
    notes = governing_notes(text, project_dir, s)
    return [r for r in gate_status(project_dir, config, notes) if not r["ok"]]


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
