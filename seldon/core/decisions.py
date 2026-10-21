"""The decision register (AD-033). One register per repository, one write path, status derived.

WHAT THIS IS. A decision is a record with a lifecycle (AD-033-R3, R4), kept as YAML files in the
repository that owns it under `docs/decisions/register/`, one file per record event, never edited
(R1). `seldon decision` (CLI and MCP) is the only writer (R2); this module is that writer, the
fold that derives each record's status from its events, the projection of the fold into `Decision`
nodes in the project graph, the rendering of `docs/decisions/REGISTER.md`, the checks
`seldon verify` runs, and the binding `seldon cc register` applies (R7).

WHY FILES IN EACH REPOSITORY (R1). Git is the one store that has not lost records (C6: 451
documents lost in Wintermute; Arnold's `.gitignore` drops Seldon's `*.jsonl`). The files are the
append-only, hash-chained log; Neo4j holds a projection written only by replaying them, and
`REGISTER.md` is a rendered view (AD-033-R11; Helland 2015; Kleppmann 2017 ch. 11).

ONE EVENT ABOUT A RECORD LIVES IN THAT RECORD'S HOME REGISTER. A create lives where its id says
(`squiddy:` in Squiddy's register). A status change or an amendment of `squiddy:R-04` is written to
Squiddy's register even when the record that causes it is Seldon's `AD-033-R11`; the superseding
record is written to Seldon's. So a record's status is a fold of its own home register alone, and
no reader has to scan every repository to learn whether a decision still binds.

THE CHAIN is Squiddy DN-041 R-174's (`squiddy/decision_log.py`): each file carries `prev_hash`
(the previous file's `record_hash`, 64 zeros for the first) and `record_hash` (sha256 over the
file's data without `record_hash`, as canonical JSON). The form is reused, not imported: Seldon
reads Squiddy's formats and never imports its modules (AD-030-R10). Beyond DN-041, a file's bytes
must equal the canonical serialization of its data, so a hand edit that leaves the data equal
(reordered keys, a re-wrapped line) is caught too.

Prior art: Nygard 2011; MADR 4.0.0; Kruchten 2004; EIA-649C; Schneier and Kelsey 1999; AD-033
section 2 carries the rest.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import date as _date
from pathlib import Path
from typing import Any, Iterable, Optional

import yaml

#: The LinkML schema the register is validated against (see its description for why a reader).
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "domain" / "decision_register.yaml"

#: Where a repository keeps its register and its rendered view, when `seldon.yaml` says nothing.
DEFAULT_REGISTER_DIR = "docs/decisions/register"
DEFAULT_RENDERED = "docs/decisions/REGISTER.md"

#: The chain's start, DN-041's `_CHAIN_START`.
CHAIN_START = "0" * 64

#: The version stamped on every file this module writes.
WRITER = "seldon decision 0.1.0"

#: Statuses a record may still be acted on in (AD-033-R2: "does not exist or is not active").
ACTIVE = frozenset({"proposed", "accepted"})
#: The one status that binds (AD-033-R4).
BINDING = "accepted"

#: Fields an `amend` event may change. Everything else is fixed at creation (schema, `Changes`), save that
#: `source.sha256` may be corrected to the digest of the file's current bytes (`_source_correction`, DESK-002).
AMENDABLE = ("statement", "statement_check", "kind", "mirrors", "scope", "scope_note", "consumer",
             "review_only", "rationale")

#: Canonical key order for a register file: the slots of `RegisterFile`, which is also the order
#: a reader meets them in. Read from the schema at import so a slot added there is ordered here.
_ORDER: tuple[str, ...] = ()

#: A statement may not point at another record by position (AD-033-R3). Checked on statements
#: written after the seed (Part E); the seed's statement is the verbatim body, which may.
#:
#: Two kinds of pointer, after the distinction between ENDOPHORIC reference (anaphora and cataphora: the referent is
#: in the text itself) and EXOPHORIC reference (the referent is outside the text) of Halliday and Hasan, Cohesion in
#: English (1976), cited from knowledge and not in the library; the library holds the coreference framing, "find all
#: expressions (mentions) that refer to the same entity in a text" (lesson:2026-07-15_arXiv_2306_08302 #p15:476) and
#: anaphora and cataphora as mention-to-mention links inside a text (lesson:2026-06-13_arXiv_1808_09602 #p12:289);
#: receipts in SQ-010's evidence. A statement that resolves its own reference stands alone; one that points outside
#: itself does not.
#:   - `_DEICTIC`: positional pointers ("above", "below", "the following", "the previous section"). Their referent is
#:     a position in some other text, never a mention in the statement, so they are refused wherever they occur.
#:   - `_DEFINITE`: a definite reference to a document-like noun ("this decision", "the note"). It is deictic only
#:     when the statement has no earlier mention of that noun to be its antecedent. "A design note ... the note's
#:     hash" is anaphora resolved inside the statement and passes; a bare "the note" refers outside and is refused
#:     (SQ-010 Part 8, carried from HOOK-001: AD-036-R4's validator-passed statement was refused on exactly that).
_DEICTIC = re.compile(
    r"\b(?:(?:the|as|see|stated|listed|described|noted|defined|shown|named|given|mentioned)\s+(?:above|below)\b|"
    r"\b(?:above|below)\s*[.;:]?\s*$|\bthe following\s*:|\b(?:all|each|any|one) of the following\b|"
    r"\bthe (?:previous|preceding) (?:note|decision|record|ruling|section|rule|item|paragraph)s?\b)", re.I)
_DEFINITE = re.compile(
    r"\b(?:this (note|decision|record|ruling|section|document|addendum|rule)|the (note))\b", re.I)
# Comparatives are not pointers: "at or above 0.98", "the layer below the symptom", "the previous week" pass. The first
# form of this pattern refused them (SEL-002 Part E: 30 validator-passed statements refused on "above" or "below" as
# thresholds; re-landed after the correction, evidence/sel002/statements/reapply.json).


def deictic_reference(statement: str) -> Optional[str]:
    """The first pointer in a statement that needs text outside it (AD-033-R3), or None.

    A positional pointer (`_DEICTIC`) always counts. A definite reference (`_DEFINITE`) counts only when no earlier
    word of the statement is its head noun, singular or plural: that earlier mention is its antecedent.
    """
    m = _DEICTIC.search(statement)
    if m:
        return m.group(0)
    for m in _DEFINITE.finditer(statement):
        noun = (m.group(1) or m.group(2)).lower()
        if not re.search(rf"\b{noun}s?\b", statement[:m.start()], re.I):
            return m.group(0)
    return None


#: Native id forms, used to read an identifier out of task text (R7). A bare form is qualified by
#: the registering repository first, then by its imports in order.
_ID_FORMS = re.compile(
    r"\b(?:(?P<repo>[a-z][a-z0-9-]*):)?"
    r"(?P<local>AD-\d{3}-(?:R\d+|FC-\d{2})|DN-\d{3}-R\d+|EX-REQ-\d+|DI-\d{3}|ADR-\d{3}(?:-A\d{2})?|"
    r"FC-\d{2}|R-\d{1,3}|[a-z0-9]+(?:-[a-z0-9]+)*-B\d+)\b"
)


class RegisterError(ValueError):
    """A refusal. The message names what was refused and why; nothing was written."""


class BrokenRegister(SystemExit):
    """A register file the command did not write: a broken chain, a hash or byte mismatch."""


# ---------------------------------------------------------------------------
# The schema
# ---------------------------------------------------------------------------

@dataclass
class Schema:
    """The subset of a LinkML schema this register uses."""

    classes: dict[str, dict]
    slots: dict[str, dict]
    enums: dict[str, set[str]]

    def slot_names(self, cls: str) -> list[str]:
        out: list[str] = []
        c = self.classes[cls]
        if c.get("is_a"):
            out.extend(self.slot_names(c["is_a"]))
        for s in c.get("slots") or []:
            if s not in out:
                out.append(s)
        return out

    def required(self, cls: str) -> list[str]:
        req: list[str] = []
        c = self.classes[cls]
        if c.get("is_a"):
            req.extend(self.required(c["is_a"]))
        for s, usage in (c.get("slot_usage") or {}).items():
            if (usage or {}).get("required") and s not in req:
                req.append(s)
        return req


_SUPPORTED_SLOT_KEYS = {"range", "multivalued", "description", "required"}
_SUPPORTED_CLASS_KEYS = {"slots", "slot_usage", "is_a", "description"}


def load_schema(path: Path = SCHEMA_PATH) -> Schema:
    """Read the register's LinkML schema.

    Raises:
        RegisterError: If the file uses a construct the reader does not implement. Ignoring it
            would make the schema promise a check nothing runs.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    enums = {name: set((body or {}).get("permissible_values") or {})
             for name, body in (raw.get("enums") or {}).items()}
    slots = raw.get("slots") or {}
    for name, body in slots.items():
        extra = set(body or {}) - _SUPPORTED_SLOT_KEYS
        if extra:
            raise RegisterError(f"{path}: slot {name} uses {sorted(extra)}, which the register's "
                                f"schema reader does not implement")
    classes = raw.get("classes") or {}
    for name, body in classes.items():
        extra = set(body or {}) - _SUPPORTED_CLASS_KEYS
        if extra:
            raise RegisterError(f"{path}: class {name} uses {sorted(extra)}, which the register's "
                                f"schema reader does not implement")
    return Schema(classes=classes, slots=slots, enums=enums)


SCHEMA = load_schema()
_ORDER = tuple(SCHEMA.slot_names("RegisterFile"))


def _check_value(slot: str, value: Any, where: str) -> list[str]:
    """Range and multiplicity of one slot value, recursing into classes."""
    spec = SCHEMA.slots.get(slot)
    if spec is None:
        return [f"{where}: unknown field {slot!r}"]
    rng = spec.get("range", "string")
    if spec.get("multivalued"):
        if not isinstance(value, list):
            return [f"{where}: {slot} must be a list"]
        out: list[str] = []
        for i, v in enumerate(value):
            out.extend(_check_scalar(slot, rng, v, f"{where}.{slot}[{i}]"))
        return out
    return _check_scalar(slot, rng, value, f"{where}.{slot}")


def _check_scalar(slot: str, rng: str, value: Any, where: str) -> list[str]:
    if value is None:
        return []
    if rng in SCHEMA.enums:
        if value not in SCHEMA.enums[rng]:
            return [f"{where}: {value!r} is not one of {sorted(SCHEMA.enums[rng])}"]
        return []
    if rng in SCHEMA.classes:
        if not isinstance(value, dict):
            return [f"{where}: must be a mapping ({rng})"]
        out = []
        allowed = set(SCHEMA.slot_names(rng))
        for k, v in value.items():
            if k not in allowed:
                out.append(f"{where}: {k!r} is not a field of {rng}")
                continue
            out.extend(_check_value(k, v, where))
        for k in SCHEMA.required(rng):
            if _blank(value.get(k)):
                out.append(f"{where}: {rng} requires {k}")
        return out
    if rng == "integer":
        return [] if isinstance(value, int) and not isinstance(value, bool) else [f"{where}: must be an integer"]
    if rng == "boolean":
        return [] if isinstance(value, bool) else [f"{where}: must be true or false"]
    return [] if isinstance(value, str) else [f"{where}: must be a string"]


def _blank(v: Any) -> bool:
    return v is None or (isinstance(v, (str, list, dict)) and not v)


# ---------------------------------------------------------------------------
# Ids
# ---------------------------------------------------------------------------

def split_id(qid: str) -> tuple[str, str]:
    """`squiddy:R-112` to `("squiddy", "R-112")`. An unqualified id is refused."""
    if ":" not in (qid or ""):
        raise RegisterError(f"id {qid!r} is not repository-qualified (AD-033-R3: `squiddy:R-112`)")
    repo, local = qid.split(":", 1)
    if not repo or not local:
        raise RegisterError(f"id {qid!r} is not repository-qualified")
    return repo, local


def slug(qid: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", qid.lower()).strip("-")


# ---------------------------------------------------------------------------
# Serialization and the chain
# ---------------------------------------------------------------------------

class _Dumper(yaml.SafeDumper):
    """Literal blocks for multi-line text, so a verbatim span reads as itself."""


def _represent_str(dumper, data):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_Dumper.add_representer(str, _represent_str)


def ordered(data: dict) -> dict:
    """The record in canonical key order; nested mappings in their class's slot order."""
    out = {k: data[k] for k in _ORDER if k in data}
    for k in data:
        if k not in out:
            out[k] = data[k]
    for k, v in list(out.items()):
        rng = (SCHEMA.slots.get(k) or {}).get("range")
        if rng in SCHEMA.classes:
            names = SCHEMA.slot_names(rng)
            if isinstance(v, dict):
                out[k] = {n: v[n] for n in names if n in v} | {n: v[n] for n in v if n not in names}
            elif isinstance(v, list):
                out[k] = [({n: x[n] for n in names if n in x} | {n: x[n] for n in x if n not in names})
                          if isinstance(x, dict) else x for x in v]
    return out


def canonical_yaml(data: dict) -> str:
    return yaml.dump(ordered(data), Dumper=_Dumper, sort_keys=False, allow_unicode=True,
                     width=1_000_000, default_flow_style=False)


def digest(data: dict) -> str:
    """DN-041's `_digest`: sha256 of the canonical JSON of the record without its own hash."""
    body = {k: v for k, v in data.items() if k != "record_hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _span_text(lines: list[str], span: Any) -> Optional[str]:
    """The file's text at a record's `source.lines` (1-based, inclusive), or None for a span the file lacks."""
    if not (isinstance(span, list) and span and all(isinstance(n, int) for n in span)):
        return None
    a, b = span[0], span[-1]
    if not 1 <= a <= b <= len(lines):
        return None
    return "\n".join(lines[a - 1:b])


def checked_source(u: "Universe", qid: str, source: Any, *, given_sha: Any = None) -> Any:
    """`source` with `sha256` taken from the file's bytes, after checking it (Issue 5bfc2788, DESK-002 Part C).

    The register's convention is the digest of the WHOLE file at `source.path` in the record's home repository
    (squiddy seq 972 to 975: one digest each for different spans of one note), never a hash of the span or of a
    transcription. A caller-supplied digest that differs is refused, naming both. `source.text` must equal the file's
    text at `source.lines`, compared without leading and trailing whitespace, which is how registration takes the
    span (`governing_commit.plan_records`). A value that is not a mapping is returned as is, for the shape check.
    """
    if not isinstance(source, dict):
        return source
    repo, _ = split_id(qid)
    root = u.s.repositories.get(repo)
    rel = source.get("path") or ""
    path = Path(root) / rel if root else None
    if path is None or not rel or not path.is_file():
        raise RegisterError(f"source {rel!r} of {qid} resolves to no file in {repo}")
    actual = sha256_file(path)
    given = source.get("sha256") if given_sha is None else given_sha
    if not _blank(given) and given != actual:
        raise RegisterError(f"source.sha256 of {qid} is {given}, but {rel} hashes to {actual}: the register takes "
                            f"the digest of the whole file's bytes (omit it and it is computed)")
    span = _span_text(path.read_text(encoding="utf-8").splitlines(), source.get("lines"))
    if span is None:
        raise RegisterError(f"source.lines {source.get('lines')!r} of {qid} is not a span of {rel}")
    if span.strip() != str(source.get("text") or "").strip():
        raise RegisterError(f"source.text of {qid} is not the text of {rel} at lines {source.get('lines')}: "
                            f"a record carries the note's own bytes (AD-033-R3)")
    return dict(source, sha256=actual)


def file_name(seq: int, qid: str, event: str) -> str:
    return f"{seq:05d}_{slug(qid)}_{event}.yaml"


_FILE_RE = re.compile(r"^(\d{5})_([a-z0-9-]+)_([a-z]+)\.yaml$")

# LOOP-001 Part B (AD-033 ADDENDUM 01): a record written on a branch is not numbered there. STD-001R and DISP-001R
# both took seq 292 on 2026-10-19 because each branch appended `00292_...` after the same tail. A record written in
# a linked git worktree (the dispatcher's branch per task, AD-034) goes to `pending/` with a provisional id (its
# content hash) and no seq, prev_hash or record_hash; the merge step on the primary checkout appends every pending
# record to the chain in the order it was written (`Register.number`). Prior art: an append-only log with one writer
# assigns positions at the commit point, not at the proposal (Kafka's offset is assigned by the broker on append; a
# database sequence is drawn inside the transaction that commits).

#: The subdirectory of the register that holds a branch's unnumbered records.
PENDING_DIR = "pending"
#: `<n>_<provisional id, 16 hex>_<id-slug>_<event>.yaml`; `n` orders one branch's records, the hash keeps two
#: branches' names apart so their files never conflict.
_PENDING_RE = re.compile(r"^(\d{5})_([0-9a-f]{16})_([a-z0-9-]+)_([a-z]+)\.yaml$")
#: The fields only the chain gives a record.
_CHAIN_FIELDS = ("seq", "prev_hash", "record_hash")


def pending_name(n: int, pid: str, qid: str, event: str) -> str:
    return f"{n:05d}_{pid[:16]}_{slug(qid)}_{event}.yaml"


def provisional_id(data: dict) -> str:
    """sha256 of a record's content: the canonical JSON of its data without the chain's fields or this id."""
    body = {k: v for k, v in data.items() if k not in _CHAIN_FIELDS + ("provisional_id",)}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _load_quiet(path: Path) -> Any:
    """A register file's data, or None when it is not YAML (`verify` reports that file itself)."""
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return None


def is_linked_worktree(root: Path) -> bool:
    """True when `root` is a linked git worktree (its git dir is not the common dir): a branch the dispatcher cut
    for one task, whose register writes are provisional. False for a primary checkout and for a directory git does
    not know."""
    r = subprocess.run(["git", "-C", str(root), "rev-parse", "--path-format=absolute", "--git-dir",
                        "--git-common-dir"], capture_output=True, text=True)
    if r.returncode != 0:
        return False
    lines = r.stdout.split()
    return len(lines) == 2 and Path(lines[0]).resolve() != Path(lines[1]).resolve()


# ---------------------------------------------------------------------------
# One repository's register
# ---------------------------------------------------------------------------

@dataclass
class Register:
    """The register directory of one repository."""

    repository: str
    root: Path            # the repository root
    register_dir: str = DEFAULT_REGISTER_DIR

    @property
    def path(self) -> Path:
        return self.root / self.register_dir

    @property
    def pending_path(self) -> Path:
        return self.path / PENDING_DIR

    @property
    def provisional(self) -> bool:
        """Writes here are unnumbered (LOOP-001 Part B): the register's repository is a linked worktree."""
        if not hasattr(self, "_provisional"):
            self._provisional = is_linked_worktree(self.root)
        return self._provisional

    def exists(self) -> bool:
        return bool(self.files() or self.pending_files())

    def files(self) -> list[Path]:
        if not self.path.is_dir():
            return []
        return sorted(p for p in self.path.glob("*.yaml"))

    def pending_files(self) -> list[Path]:
        """The unnumbered records, in the order they were written."""
        if not self.pending_path.is_dir():
            return []
        return sorted(self.pending_path.glob("*.yaml"))

    def verify(self) -> list[str]:
        """Every finding about files the command did not write, or []."""
        return self._verify_chain() + self._verify_pending()

    def _verify_pending(self) -> list[str]:
        """The pending records' own checks (LOOP-001 Part B): name, canonical bytes, provisional id, shape, and no
        create of an id the chain or an earlier pending record already created. A pending record the chain already
        holds (its provisional id is there; a rebase re-adds the file main's numbering removed) is not a finding:
        it is skipped by `events` and removed by `number`, never numbered twice."""
        out: list[str] = []
        pending = self.pending_files()
        if not pending:
            return out
        created: set[str] = set()
        numbered: set[str] = set()
        for p in self.files():
            data = _load_quiet(p)
            if not isinstance(data, dict):
                continue
            if event_form(data) == "DecisionRecord":
                created.add(str(data.get("id")))
            if data.get("provisional_id"):
                numbered.add(data["provisional_id"])
        for p in pending:
            rel = p.relative_to(self.root).as_posix()
            m = _PENDING_RE.match(p.name)
            if not m:
                out.append(f"{rel}: the name is not <n>_<provisional id>_<id-slug>_<event>.yaml")
                continue
            raw = p.read_text(encoding="utf-8")
            try:
                data = yaml.safe_load(raw)
            except yaml.YAMLError as exc:
                out.append(f"{rel}: not YAML ({exc})")
                continue
            if not isinstance(data, dict):
                out.append(f"{rel}: not a mapping")
                continue
            pid = data.get("provisional_id")
            if pid in numbered:
                continue
            if any(k in data for k in _CHAIN_FIELDS):
                out.append(f"{rel}: a pending record carries no {'/'.join(_CHAIN_FIELDS)} (the chain gives them)")
            if pid != provisional_id(data):
                out.append(f"{rel}: the data does not hash to its provisional_id (edited after it was written)")
            elif m.group(2) != pid[:16]:
                out.append(f"{rel}: the name does not carry its provisional_id")
            if m.group(3) != slug(str(data.get("id", ""))) or m.group(4) != data.get("event"):
                out.append(f"{rel}: the name does not match the id and event inside")
            if canonical_yaml(data) != raw:
                out.append(f"{rel}: the bytes are not the canonical serialization of the data "
                           f"(the file was edited by hand)")
            try:
                home, _ = split_id(str(data.get("id")))
                if home != self.repository:
                    out.append(f"{rel}: holds an event about {data.get('id')}, whose home is not "
                               f"{self.repository}")
            except RegisterError as exc:
                out.append(f"{rel}: {exc}")
            probe = dict(data, seq=1, prev_hash=CHAIN_START, record_hash="x")
            probe.pop("provisional_id", None)
            out.extend(f"{rel}: {e}" for e in validate_shape(probe))
            if event_form(data) == "DecisionRecord":
                if data.get("id") in created:
                    out.append(f"{rel}: creates {data.get('id')}, which the register already holds (two branches "
                               f"decided the same id)")
                created.add(str(data.get("id")))
        return out

    def numbered_ids(self) -> dict[str, int]:
        """provisional id -> seq, for every chain record that was numbered from a pending one."""
        out: dict[str, int] = {}
        for p in self.files():
            data = _load_quiet(p)
            if isinstance(data, dict) and data.get("provisional_id"):
                out[data["provisional_id"]] = data.get("seq")
        return out

    def _verify_chain(self) -> list[str]:
        out: list[str] = []
        prev = CHAIN_START
        for n, p in enumerate(self.files(), 1):
            rel = p.relative_to(self.root).as_posix()
            m = _FILE_RE.match(p.name)
            if not m:
                out.append(f"{rel}: the name is not <seq>_<id-slug>_<event>.yaml")
                continue
            raw = p.read_text(encoding="utf-8")
            try:
                data = yaml.safe_load(raw)
            except yaml.YAMLError as exc:
                out.append(f"{rel}: not YAML ({exc})")
                prev = None
                continue
            if not isinstance(data, dict):
                out.append(f"{rel}: not a mapping")
                continue
            if int(m.group(1)) != n or data.get("seq") != n:
                out.append(f"{rel}: seq {data.get('seq')!r} at position {n} (a file was removed, "
                           f"renamed or inserted)")
            if m.group(2) != slug(str(data.get("id", ""))) or m.group(3) != data.get("event"):
                out.append(f"{rel}: the name does not match the id and event inside")
            if prev is not None and data.get("prev_hash") != prev:
                out.append(f"{rel}: prev_hash does not name the record_hash of file {n - 1} "
                           f"(the chain is broken)")
            if data.get("record_hash") != digest(data):
                out.append(f"{rel}: the data does not hash to its record_hash (edited after it "
                           f"was written)")
            if canonical_yaml(data) != raw:
                out.append(f"{rel}: the bytes are not the canonical serialization of the data "
                           f"(the file was edited by hand)")
            try:
                home, _ = split_id(str(data.get("id")))
                if home != self.repository:
                    out.append(f"{rel}: holds an event about {data.get('id')}, whose home is not "
                               f"{self.repository}")
            except RegisterError as exc:
                out.append(f"{rel}: {exc}")
            out.extend(f"{rel}: {e}" for e in validate_shape(data))
            prev = data.get("record_hash")
        return out

    def assert_tail(self) -> None:
        """The register still ends where this process last saw it end (no file added or removed
        behind its back). Cheap; the full check is `verify`."""
        files = self.files()
        want = getattr(self, "_tail", None)
        have = (len(files), files[-1].name if files else None)
        if want is not None and have != want:
            raise BrokenRegister(f"FATAL: the register of {self.repository} changed under this "
                                 f"process (expected {want}, found {have}); re-run to re-verify")

    def events(self, include_pending: bool = True) -> list[dict]:
        """Every event, after the register verifies. A broken register is fatal, never read.

        The chain's events in seq order, then (unless `include_pending` is False) the pending records in the order
        they were written, so a branch's own records bind its later commands; a pending record the chain already
        numbered is skipped. REGISTER.md renders the chain alone (`render_register`), so a branch never edits it."""
        bad = self.verify()
        if bad:
            raise BrokenRegister(
                f"FATAL: the decision register of {self.repository} at {self.path} does not "
                f"verify; a file the command did not write is refused, never read:\n  "
                + "\n  ".join(bad[:12]) + (f"\n  ... and {len(bad) - 12} more" if len(bad) > 12 else ""))
        files = self.files()
        self._tail = (len(files), files[-1].name if files else None)
        chain = [yaml.safe_load(p.read_text(encoding="utf-8")) for p in files]
        if not include_pending:
            return chain
        numbered = {e["provisional_id"] for e in chain if e.get("provisional_id")}
        pending = [yaml.safe_load(p.read_text(encoding="utf-8")) for p in self.pending_files()]
        return chain + [e for e in pending if e.get("provisional_id") not in numbered]

    def append_pending(self, data: dict) -> Path:
        """Write one event unnumbered, under `pending/` (LOOP-001 Part B). Caller holds the lock and has validated."""
        rec = {k: v for k, v in data.items() if k not in _CHAIN_FIELDS + ("provisional_id",)}
        rec["written_by"] = WRITER
        rec = ordered(rec)
        rec["provisional_id"] = provisional_id(rec)
        rec = ordered(rec)
        self.pending_path.mkdir(parents=True, exist_ok=True)
        path = self.pending_path / pending_name(len(self.pending_files()) + 1, rec["provisional_id"], rec["id"],
                                                rec["event"])
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(canonical_yaml(rec))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        return path

    def number(self) -> list[dict]:
        """Append every pending record to the chain, in written order, and remove its pending file (LOOP-001 Part
        B). The merge step calls this on the primary checkout under the pass lease. A pending record whose
        provisional id the chain already holds is removed and reported `already`, never numbered twice.

        Returns one row per pending file: `{provisional_id, id, event, seq, file, pending, already}`.

        Raises:
            RegisterError: In a linked worktree: a branch never numbers (that is the collision this prevents).
            BrokenRegister: The register, chain or pending, does not verify.
        """
        if self.provisional:
            raise RegisterError(f"{self.root} is a linked worktree: its records are numbered when its branch "
                                f"merges, on the primary checkout (LOOP-001, AD-033 ADDENDUM 01)")
        out: list[dict] = []
        with self.locked():
            self.events()                  # verifies chain and pending, or raises
            numbered = self.numbered_ids()
            for p in self.pending_files():
                data = yaml.safe_load(p.read_text(encoding="utf-8"))
                pid = data["provisional_id"]
                row = {"provisional_id": pid, "id": data["id"], "event": data["event"], "pending": p.name}
                if pid in numbered:
                    out.append({**row, "seq": numbered[pid], "file": None, "already": True})
                else:
                    path = self.append(data)
                    numbered[pid] = self._tail[0]
                    out.append({**row, "seq": self._tail[0], "file": path.name, "already": False})
                p.unlink()
            if self.pending_path.is_dir() and not any(self.pending_path.iterdir()):
                self.pending_path.rmdir()
        return out

    @contextlib.contextmanager
    def locked(self):
        """One writer at a time per register (fcntl advisory lock on a sibling file)."""
        self.path.mkdir(parents=True, exist_ok=True)
        lock = self.path.parent / ".register.lock"
        with open(lock, "a+") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    def append(self, data: dict) -> Path:
        """Write one event at the end of the chain. Caller holds the lock and has validated."""
        files = self.files()
        if files:
            last = yaml.safe_load(files[-1].read_text(encoding="utf-8"))
            seq, prev = last["seq"] + 1, last["record_hash"]
        else:
            seq, prev = 1, CHAIN_START
        rec = dict(data)
        rec["seq"] = seq
        rec["written_by"] = WRITER
        rec["prev_hash"] = prev
        rec.pop("record_hash", None)
        rec = ordered(rec)
        rec["record_hash"] = digest(rec)
        path = self.path / file_name(seq, rec["id"], rec["event"])
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(canonical_yaml(rec))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        self._tail = (seq, path.name)
        return path


def validate_shape(data: dict) -> list[str]:
    """Schema findings for one event, independent of any other record."""
    out: list[str] = []
    for k, v in data.items():
        out.extend(_check_value(k, v, data.get("id", "?")))
    ev = data.get("event")
    form = event_form(data)
    for k in SCHEMA.required(form):
        if k in ("written_by", "prev_hash", "record_hash", "seq") and k not in data:
            out.append(f"missing {k}")
        elif k not in ("written_by", "prev_hash", "record_hash", "seq") and _blank(data.get(k)) \
                and not (k == "operator_stated" and data.get(k) is False):
            out.append(f"{ev} requires {k}")
    if form == "DecisionRecord":
        if data.get("kind") == "mirror":
            if _blank(data.get("mirrors")):
                out.append("a mirror requires `mirrors` (FC-16)")
            if not _blank(data.get("statement")):
                out.append("a mirror carries no statement of its own (FC-16)")
        elif _blank(data.get("statement")):
            out.append(f"{ev} requires statement")
        if _blank(data.get("consumer")) and _blank(data.get("review_only")):
            out.append("a record names its consumer, or carries review_only with a reason (R6)")
        if data.get("kind") == "catch":
            for k in ("catch_class", "task"):
                if _blank(data.get(k)):
                    out.append(f"a catch requires {k} (RECALL-001 Part C)")
        elif not _blank(data.get("catch_class")) or not _blank(data.get("task")):
            out.append("catch_class and task belong to a catch only (RECALL-001 Part C)")
        if data.get("status") == "proposed" and _blank(data.get("waits_on")):
            out.append("a proposed record names the measurement it waits on (R4)")
        if data.get("status") not in (None, "proposed", "accepted"):
            out.append(f"a record is created proposed or accepted, not {data.get('status')}")
    if form == "Amend" and _blank(data.get("amendment")) and _blank(data.get("changes")):
        out.append("amend carries an amendment, field changes, or both")
    if data.get("operator_stated") is True and _blank(data.get("receipts")):
        out.append("operator_stated is true only with a receipt")
    return out


def event_form(data: dict) -> str:
    """Which schema class an event is an instance of."""
    ev = data.get("event")
    if ev == "amend":
        return "Amend"
    if ev in ("reject", "deprecate"):
        return "Transition"
    if ev == "supersede" and data.get("superseded_by"):
        return "Transition"
    if ev == "accept" and not data.get("source"):
        return "Transition"
    return "DecisionRecord"


# ---------------------------------------------------------------------------
# The fold
# ---------------------------------------------------------------------------

@dataclass
class Record:
    """One decision as its events say it stands now."""

    id: str
    home: str
    data: dict                       # the create event's data, with amended fields applied
    status: str
    superseded_by: Optional[str] = None
    amendments: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    @property
    def last_hash(self) -> str:
        return self.events[-1]["record_hash"]

    def text(self) -> str:
        """What a reader or a retriever sees: id, statement, verbatim source (AD-033 section 6)."""
        src = (self.data.get("source") or {}).get("text") or ""
        return "\n".join(x for x in (self.id, self.data.get("statement") or "", src) if x)


def fold(events: Iterable[dict]) -> dict[str, Record]:
    """Derive every record's current state from its events, in sequence (AD-033-R4)."""
    recs: dict[str, Record] = {}
    for ev in events:
        apply(recs, ev)
    return recs


def apply(recs: dict[str, Record], ev: dict) -> None:
    """Fold one event into the records it changes."""
    qid = ev["id"]
    kind = ev["event"]
    if event_form(ev) == "DecisionRecord":
        data = {k: v for k, v in ev.items()
                if k not in ("seq", "event", "written_by", "prev_hash", "record_hash")}
        recs[qid] = Record(id=qid, home=split_id(qid)[0], data=data,
                           status=ev.get("status") or ("proposed" if kind == "propose" else "accepted"),
                           events=[ev])
        return
    rec = recs.get(qid)
    if rec is None:
        raise BrokenRegister(f"FATAL: event {ev.get('seq')} ({kind}) names {qid}, which no "
                             f"earlier file created")
    rec.events.append(ev)
    if kind == "accept":
        rec.status = "accepted"
    elif kind == "reject":
        rec.status = "rejected"
    elif kind == "deprecate":
        rec.status = "deprecated"
    elif kind == "supersede":
        rec.status = "superseded"
        rec.superseded_by = ev.get("superseded_by")
    elif kind == "amend":
        if ev.get("amendment"):
            rec.amendments.append({**ev["amendment"], "seq": ev.get("seq"), "date": ev.get("date"),
                                   "decided_by": ev.get("decided_by"), "reason": ev.get("reason")})
        for k, v in (ev.get("changes") or {}).items():
            if v is None:
                rec.data.pop(k, None)
            else:
                rec.data[k] = v


# ---------------------------------------------------------------------------
# Configuration and the universe of registers a repository can name
# ---------------------------------------------------------------------------

@dataclass
class Settings:
    repository: str
    root: Path
    register_dir: str
    rendered: str
    imports: list[str]
    repositories: dict[str, Path]
    baseline_name: Optional[str]
    baseline_commit: Optional[str]
    design_notes: list[dict]
    consumer_roots: list[str]
    binding_limit: int
    probe_findings: Optional[Path] = None
    probe_exclusions: Optional[Path] = None


def settings(project_dir: Path, config: dict) -> Optional[Settings]:
    """The `decisions:` block of seldon.yaml, or None when the project declares no register.

    Raises:
        RegisterError: If the block is present and malformed. A misspelled key that silently
            fell back to a default would point the register at the wrong place.
    """
    block = config.get("decisions")
    if not block:
        return None
    root = Path(project_dir).resolve()
    known = {"repository", "register_dir", "rendered", "import", "repositories", "baseline",
             "design_notes", "consumer_roots", "binding_limit", "probe"}
    extra = set(block) - known
    if extra:
        raise RegisterError(f"seldon.yaml decisions: unknown key(s) {sorted(extra)}; known {sorted(known)}")
    if not block.get("repository"):
        raise RegisterError("seldon.yaml decisions.repository is required: the qualifier of this "
                            "repository's ids (`squiddy`, `seldon`, `arnold`)")
    repos: dict[str, Path] = {block["repository"]: root}
    for name, rel in (block.get("repositories") or {}).items():
        repos[name] = (root / rel).resolve()
    imports: list[str] = []
    for entry in block.get("import") or []:
        if isinstance(entry, dict):
            name = entry["repository"]
            if entry.get("path"):
                repos[name] = (root / entry["path"]).resolve()
        else:
            name = str(entry)
        imports.append(name)
        # Convention: repositories sit side by side (~/GitHub/<name>). Configured paths win.
        repos.setdefault(name, (root.parent / name).resolve())
    base = block.get("baseline") or {}
    return Settings(
        repository=block["repository"], root=root,
        register_dir=block.get("register_dir", DEFAULT_REGISTER_DIR),
        rendered=block.get("rendered", DEFAULT_RENDERED),
        imports=imports, repositories=repos,
        baseline_name=base.get("name"), baseline_commit=base.get("commit"),
        design_notes=list(block.get("design_notes") or []),
        consumer_roots=list(block.get("consumer_roots") or []),
        binding_limit=int(block.get("binding_limit", 8)),
        probe_findings=(root / block["probe"]["findings"]).resolve() if (block.get("probe") or {}).get("findings") else None,
        probe_exclusions=(root / block["probe"]["exclusions"]).resolve() if (block.get("probe") or {}).get("exclusions") else None,
    )


class Universe:
    """Every register a repository may name: its own, its imports and its configured neighbours."""

    def __init__(self, s: Settings):
        self.s = s
        self._registers: dict[str, Register] = {}
        self._records: dict[str, dict[str, Record]] = {}

    def register(self, repo: str) -> Register:
        if repo not in self._registers:
            root = self.s.repositories.get(repo)
            if root is None:
                raise RegisterError(f"repository {repo!r} is not known to {self.s.repository}'s "
                                    f"seldon.yaml (decisions.repositories or decisions.import)")
            self._registers[repo] = Register(repo, root, self._register_dir(repo, root))
        return self._registers[repo]

    def _register_dir(self, repo: str, root: Path) -> str:
        if repo == self.s.repository:
            return self.s.register_dir
        cfg = root / "seldon.yaml"
        if cfg.is_file():
            block = (yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}).get("decisions") or {}
            return block.get("register_dir", DEFAULT_REGISTER_DIR)
        return DEFAULT_REGISTER_DIR

    def records(self, repo: str) -> dict[str, Record]:
        if repo not in self._records:
            self._records[repo] = fold(self.register(repo).events())
        return self._records[repo]

    def forget(self, repo: str) -> None:
        self._records.pop(repo, None)

    def get(self, qid: str) -> Optional[Record]:
        repo, _ = split_id(qid)
        return self.records(repo).get(qid)

    def live_head(self, qid: str) -> str:
        """Follow `superseded_by` to the record that stands now."""
        seen = set()
        cur = qid
        while True:
            rec = self.get(cur)
            if rec is None or rec.status != "superseded" or not rec.superseded_by or cur in seen:
                return cur
            seen.add(cur)
            cur = rec.superseded_by

    def scope_repos(self) -> list[str]:
        """The repository and its imports: the records that bind its tasks (R1, R7)."""
        return [self.s.repository] + [r for r in self.s.imports if r != self.s.repository]


def universe(project_dir: Path, config: dict) -> Universe:
    s = settings(project_dir, config)
    if s is None:
        raise RegisterError("this project declares no decision register (seldon.yaml `decisions:`)")
    return Universe(s)


# ---------------------------------------------------------------------------
# The write path (AD-033-R2)
# ---------------------------------------------------------------------------

def _require_active(u: Universe, qid: str, role: str) -> Record:
    rec = u.get(qid)
    if rec is None:
        raise RegisterError(f"{role} {qid} does not exist in the {split_id(qid)[0]} register")
    if rec.status == "superseded":
        head = u.live_head(qid)
        raise RegisterError(f"{role} {qid} is already superseded by {rec.superseded_by}; the live "
                            f"head of its chain is {head} (a second supersession would fork the "
                            f"chain; supersede {head} instead)")
    if rec.status not in ACTIVE:
        raise RegisterError(f"{role} {qid} is {rec.status}, not active")
    return rec


def _require_exists(u: Universe, qid: str, role: str) -> Record:
    rec = u.get(qid)
    if rec is None:
        raise RegisterError(f"{role} {qid} does not exist in the {split_id(qid)[0]} register")
    return rec


def _base(event: str, qid: str, *, date: str, decided_by: str, operator_stated: bool,
          receipts: Optional[list[str]], reason: Optional[str]) -> dict:
    split_id(qid)
    d: dict[str, Any] = {"event": event, "id": qid, "date": date, "decided_by": decided_by,
                         "operator_stated": bool(operator_stated)}
    if receipts:
        d["receipts"] = list(receipts)
    if reason:
        d["reason"] = reason
    return d


def _check_shape_or_refuse(data: dict) -> None:
    probe = dict(data, seq=1, written_by=WRITER, prev_hash=CHAIN_START, record_hash="x")
    bad = validate_shape(probe)
    if bad:
        raise RegisterError(f"refused {data.get('event')} {data.get('id')}: " + "; ".join(bad))


def _write(u: Universe, data: dict) -> Path:
    """Append one event to its home register and fold it into the cached records.

    The register is verified in full the first time this process writes to it (a broken register
    refuses every write); after that only the tail this process wrote is re-checked, so a seed of
    a thousand records is not a thousand full re-reads. `seldon verify` re-checks everything.
    """
    repo, _ = split_id(data["id"])
    reg = u.register(repo)
    recs = u.records(repo)          # verifies in full on first use
    with reg.locked():
        reg.assert_tail()
        # LOOP-001 Part B: on a branch the record waits for its number until the branch merges.
        path = reg.append_pending(data) if reg.provisional else reg.append(data)
    apply(recs, yaml.safe_load(path.read_text(encoding="utf-8")))
    return path


def create(u: Universe, event: str, record: dict, *, date: str, decided_by: str,
           operator_stated: bool = False, receipts: Optional[list[str]] = None,
           reason: Optional[str] = None) -> list[Path]:
    """`propose`, `accept` of a new id, or `supersede` naming the records it replaces.

    Every refusal R2 lists is checked before the first file is written, so a refusal writes
    nothing. `supersede` also writes one transition into each superseded record's home register,
    so that record's status is a fold of its own register (module docstring).
    """
    if event not in ("propose", "accept", "supersede"):
        raise RegisterError(f"{event} does not create a record")
    qid = record["id"]
    data = _base(event, qid, date=date, decided_by=decided_by, operator_stated=operator_stated,
                 receipts=receipts, reason=reason)
    data["status"] = "proposed" if event == "propose" else record.get("status", "accepted")
    if event == "supersede" and data["status"] != "accepted":
        raise RegisterError("a superseding record is accepted when it is written; a proposed "
                            "replacement supersedes nothing until it is accepted")
    for k, v in record.items():
        if k in ("id", "status"):
            continue
        if v is not None:
            data[k] = v
    if event == "supersede" and _blank(data.get("supersedes")):
        raise RegisterError("supersede of a new record names what it supersedes")
    if event != "supersede" and data.get("supersedes"):
        raise RegisterError("only `seldon decision supersede` may name `supersedes`")
    if "source" in data:
        data["source"] = checked_source(u, qid, data["source"])
    _check_shape_or_refuse(data)
    if u.get(qid) is not None:
        raise RegisterError(f"id {qid} is already used in the {split_id(qid)[0]} register")
    for t in data.get("supersedes") or []:
        _require_active(u, t, "supersedes target")
    for a in data.get("amends") or []:
        _require_active(u, a["target"], "amends target")
    if data.get("mirrors"):
        _require_exists(u, data["mirrors"], "mirrors target")
    for c in data.get("constrains") or []:
        _require_exists(u, c, "constrains target")
    if data.get("rationale"):
        _rationale_resolves(u, qid, data["rationale"], refuse=True)
    written = [_write(u, data)]
    for t in data.get("supersedes") or []:
        tr = _base("supersede", t, date=date, decided_by=decided_by, operator_stated=operator_stated,
                   receipts=receipts, reason=reason or f"superseded by {qid}")
        tr["superseded_by"] = qid
        written.append(_write(u, tr))
    return written


def transition(u: Universe, event: str, qid: str, *, date: str, decided_by: str, reason: str,
               operator_stated: bool = False, receipts: Optional[list[str]] = None,
               superseded_by: Optional[str] = None) -> list[Path]:
    """`accept` of a proposed record, `reject`, `deprecate`, or `supersede` by an existing record."""
    data = _base(event, qid, date=date, decided_by=decided_by, operator_stated=operator_stated,
                 receipts=receipts, reason=reason)
    if event == "accept":
        rec = _require_exists(u, qid, "record")
        if rec.status != "proposed":
            raise RegisterError(f"{qid} is {rec.status}; only a proposed record is accepted")
    elif event == "reject":
        rec = _require_exists(u, qid, "record")
        if rec.status != "proposed":
            raise RegisterError(f"{qid} is {rec.status}; only a proposed record is rejected")
    elif event == "deprecate":
        _require_active(u, qid, "record")
    elif event == "supersede":
        if not superseded_by:
            raise RegisterError("supersede of an existing record names `superseded_by`")
        _require_active(u, qid, "supersede target")
        by = _require_exists(u, superseded_by, "superseded_by")
        if by.status != BINDING:
            raise RegisterError(f"superseded_by {superseded_by} is {by.status}; only an accepted "
                                f"record supersedes")
        if superseded_by == qid:
            raise RegisterError("a record cannot supersede itself")
        data["superseded_by"] = superseded_by
    else:
        raise RegisterError(f"{event} is not a transition")
    _check_shape_or_refuse(data)
    return [_write(u, data)]


def amend(u: Universe, qid: str, *, date: str, decided_by: str, reason: str,
          amendment: Optional[dict] = None, changes: Optional[dict] = None,
          operator_stated: bool = False, receipts: Optional[list[str]] = None) -> list[Path]:
    """An amendment to an active record's clause, field changes, or both (AD-033-R3, R8)."""
    rec = _require_active(u, qid, "amend target")
    data = _base("amend", qid, date=date, decided_by=decided_by, operator_stated=operator_stated,
                 receipts=receipts, reason=reason)
    if amendment:
        if amendment.get("by"):
            _require_active(u, amendment["by"], "amendment by")
            if amendment["by"] == qid:
                raise RegisterError("a record does not amend itself; change its fields instead")
        data["amendment"] = {k: v for k, v in amendment.items() if v is not None}
    if changes:
        bad = set(changes) - set(AMENDABLE) - {"source"}
        if bad:
            raise RegisterError(f"fields {sorted(bad)} are fixed at creation; amendable: {list(AMENDABLE)}, "
                                f"and source.sha256 to the file's digest")
        st = changes.get("statement")
        pointer = deictic_reference(st) if st else None
        if pointer:
            raise RegisterError(f"a statement names no other record by position (AD-033-R3): "
                                f"{pointer!r} in {st[:120]!r}")
        new_kind = changes.get("kind", rec.get("kind"))
        if new_kind == "mirror" and not changes.get("mirrors", rec.get("mirrors")):
            raise RegisterError("a mirror requires `mirrors`")
        if rec.get("kind") == "mirror" and new_kind != "mirror" and not changes.get("statement"):
            raise RegisterError("a mirror that becomes a decision carries its statement in the same event")
        if changes.get("mirrors"):
            _require_exists(u, changes["mirrors"], "mirrors target")
        if changes.get("rationale"):
            _rationale_resolves(u, qid, changes["rationale"], refuse=True)
        data["changes"] = dict(changes)
        if "source" in changes:
            data["changes"]["source"] = _source_correction(u, rec, changes["source"])
    _check_shape_or_refuse(data)
    return [_write(u, data)]


def _source_correction(u: Universe, rec: Record, change: Any) -> dict:
    """The record's `source` with only `sha256` changed, to the digest of the file's current bytes (DESK-002 Part C).

    A verifiable correction, not a rewrite: the record's span must still be the file's text at its lines, so the
    new digest names the bytes the record quotes. A different path, span or text is a different record and stays
    fixed at creation. The event carries the whole corrected `source`, so the fold (`apply`) needs no special case.
    """
    cur = rec.get("source") or {}
    if not isinstance(change, dict):
        raise RegisterError(f"source of {rec.id} is fixed at creation; an amend changes only source.sha256")
    moved = sorted(f"source.{k}" for k, v in change.items() if k != "sha256" and v != cur.get(k))
    if moved:
        raise RegisterError(f"fields {moved} are fixed at creation; an amend changes only source.sha256, "
                            f"to the digest of the file's current bytes")
    new = change.get("sha256")
    if _blank(new):
        raise RegisterError(f"an amend of {rec.id}'s source names the new source.sha256")
    fixed = checked_source(u, rec.id, cur, given_sha=new)
    if fixed["sha256"] == cur.get("sha256"):
        raise RegisterError(f"source.sha256 of {rec.id} is already {new}; nothing to correct")
    return fixed


def _rationale_resolves(u: Universe, qid: str, rationale: dict, refuse: bool = False) -> bool:
    repo, _ = split_id(qid)
    root = u.s.repositories.get(repo)
    ok = bool(root) and (Path(root) / rationale.get("path", "")).is_file()
    if not ok and refuse:
        raise RegisterError(f"rationale {rationale.get('path')!r} of {qid} resolves to no file in {repo}")
    return ok


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def show(u: Universe, qid: str) -> str:
    rec = u.get(qid)
    if rec is None:
        raise RegisterError(f"{qid} is not in the {split_id(qid)[0]} register")
    return render_record(rec)


def render_record(rec: Record) -> str:
    src = rec.get("source") or {}
    lines = [f"{rec.id}  [{rec.status}]  {rec.get('kind')}"]
    if rec.superseded_by:
        lines.append(f"  superseded by: {rec.superseded_by}")
    if rec.get("mirrors"):
        lines.append(f"  mirrors: {rec.get('mirrors')}")
    if rec.get("statement"):
        lines.append(f"  statement: {' '.join(str(rec.get('statement')).split())}")
    if rec.get("statement_check"):
        lines.append(f"  statement_check: {rec.get('statement_check')}")
    lines.append(f"  source: {src.get('path')}:{'-'.join(map(str, src.get('lines') or []))} "
                 f"(sha256 {str(src.get('sha256'))[:12]})")
    rat = rec.get("rationale") or {}
    lines.append(f"  rationale: {rat.get('path')}{'#' + rat['anchor'] if rat.get('anchor') else ''}")
    lines.append(f"  scope: {', '.join(rec.get('scope') or [])}"
                 + (f" ({rec.get('scope_note')})" if rec.get("scope_note") else ""))
    lines.append(f"  consumer: {', '.join(rec.get('consumer') or []) or '-'}"
                 + (f"; review_only: {rec.get('review_only')}" if rec.get("review_only") else ""))
    lines.append(f"  decided_by: {rec.get('decided_by')}; operator_stated: {rec.get('operator_stated')}; "
                 f"date: {rec.get('date')}")
    for k in ("supersedes", "constrains"):
        if rec.get(k):
            lines.append(f"  {k}: {', '.join(rec.get(k))}")
    for a in rec.get("amends") or []:
        lines.append(f"  amends {a['target']}: {a['clause']}")
    for a in rec.amendments:
        lines.append(f"  amended ({a.get('date')}, {a.get('decided_by')}"
                     + (f", by {a['by']}" if a.get("by") else "") + f"): {a['clause']}: "
                     + " ".join(str(a["text"]).split()))
    lines.append(f"  events: {', '.join(str(e.get('seq') or 'pending') + ' ' + e['event'] for e in rec.events)}")
    return "\n".join(lines)


def list_records(u: Universe, repos: Optional[list[str]] = None, status: Optional[str] = None) -> list[Record]:
    out = []
    for repo in repos or u.scope_repos():
        for rec in u.records(repo).values():
            if status and rec.status != status:
                continue
            out.append(rec)
    return sorted(out, key=lambda r: _sort_key(r.id))


def _sort_key(qid: str):
    repo, local = qid.split(":", 1)
    parts = re.split(r"(\d+)", local)
    return (repo, [int(p) if p.isdigit() else p for p in parts])


# ---------------------------------------------------------------------------
# REGISTER.md, rendered from the fold and never hand-edited
# ---------------------------------------------------------------------------

RENDER_BANNER = ("<!-- Rendered by `seldon decision project` from docs/decisions/register/. "
                 "Never edit by hand: change a decision with `seldon decision`, and this file "
                 "is rendered again (AD-033-R1). -->")


def render_register(u: Universe) -> str:
    # The chain alone (LOOP-001 Part B): a branch's pending records are rendered when the merge numbers them, so a
    # branch never edits REGISTER.md and two branches never conflict on it.
    recs = sorted(fold(u.register(u.s.repository).events(include_pending=False)).values(),
                  key=lambda r: _sort_key(r.id))
    counts: dict[str, int] = {}
    for r in recs:
        counts[r.status] = counts.get(r.status, 0) + 1
    out = [RENDER_BANNER, "", f"# Decision register: {u.s.repository}", ""]
    if u.s.baseline_name:
        out.append(f"Baseline {u.s.baseline_name} at `{u.s.baseline_commit}`. "
                   f"{len(recs)} records: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) + ".")
    if u.s.imports:
        out.append(f"Imports (their accepted records also bind this repository's tasks): "
                   f"{', '.join(u.s.imports)}.")
    out.append("")
    for status in ("accepted", "proposed", "superseded", "deprecated", "rejected"):
        group = [r for r in recs if r.status == status]
        if not group:
            continue
        out += [f"## {status.capitalize()} ({len(group)})", ""]
        for r in group:
            head = f"- **{r.id}**"
            if r.get("kind") == "mirror":
                head += f" mirrors {r.get('mirrors')}."
            else:
                st = " ".join(str(r.get("statement") or "").split())
                head += " " + (st if len(st) <= 600 else st[:600] + " [...]")
            if r.superseded_by:
                head += f" Superseded by {r.superseded_by}."
            out.append(head)
            src = r.get("source") or {}
            out.append(f"  - source `{src.get('path')}`:{'-'.join(map(str, src.get('lines') or []))}; "
                       f"decided by {r.get('decided_by')}"
                       + ("; operator-stated" if r.get("operator_stated") else "")
                       + (f"; waits on {r.get('waits_on')}" if r.status == "proposed" and r.get("waits_on") else "")
                       + (f"; consumer {', '.join(r.get('consumer'))}" if r.get("consumer") else
                          f"; review only: {r.get('review_only')}"))
            for a in r.amendments:
                out.append(f"  - amended{(' by ' + a['by']) if a.get('by') else ''} "
                           f"({a.get('decided_by')}, {a.get('date')}): {a['clause']}: "
                           + " ".join(str(a["text"]).split()))
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def write_rendered(u: Universe) -> Path:
    path = u.s.root / u.s.rendered
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_register(u), encoding="utf-8")
    return path


def number_register(project_dir: Path, config: dict) -> dict:
    """LOOP-001 Part B: number this repository's pending records (`Register.number`) and render REGISTER.md again.

    Returns `{"numbered": [rows], "already": [rows], "rendered": <rel> | None}`; nothing pending is all empty.
    """
    s = settings(project_dir, config)
    if s is None:
        return {"numbered": [], "already": [], "rendered": None}
    u = Universe(s)
    reg = u.register(s.repository)
    if not reg.pending_files():
        return {"numbered": [], "already": [], "rendered": None}
    rows = reg.number()
    write_rendered(Universe(s))
    return {"numbered": [r for r in rows if not r["already"]], "already": [r for r in rows if r["already"]],
            "rendered": s.rendered}


# ---------------------------------------------------------------------------
# Checks (`seldon decision check`, `seldon verify`)
# ---------------------------------------------------------------------------

def check(project_dir: Path, config: dict) -> list[str]:
    """Every finding `seldon verify` fails on for this repository's register, or [].

    1. A broken chain, a hash or byte mismatch (a file the command did not write).
    2. A labeled decision in a design note added after the baseline commit with no record.
    3. A record whose `rationale` resolves to no file.
    4. `REGISTER.md` differs from its rendering (it was edited by hand, or not re-rendered).
    """
    s = settings(project_dir, config)
    if s is None:
        return []
    u = Universe(s)
    reg = u.register(s.repository)
    findings = [f"register: {x}" for x in reg.verify()]
    if findings:
        return findings
    recs = u.records(s.repository)
    for rec in recs.values():
        rat = rec.get("rationale") or {}
        if not _rationale_resolves(u, rec.id, rat):
            findings.append(f"register: {rec.id} rationale {rat.get('path')!r} resolves to no file")
    for qid, path in labeled_decisions_after_baseline(s):
        if qid not in recs:
            findings.append(f"register: {path} (added after {s.baseline_name or 'the baseline'}) "
                            f"labels {qid}, which has no record (AD-033-R2)")
    for rel, line, label in unparsed_labels(s):
        findings.append(f"{UNPARSED}: {rel}:{line} {label} is in a heading or bold position and "
                        f"no `decisions.design_notes` pattern captures it (AD-036 section 6.1)")
    rendered = s.root / s.rendered
    if reg.exists():
        want = render_register(u)
        have = rendered.read_text(encoding="utf-8") if rendered.is_file() else None
        if have != want:
            findings.append(f"register: {s.rendered} is not the rendering of the register "
                            f"(run `seldon decision project`; never edit it by hand)")
    return findings


def _in_tree(root: Path, commit: str, rel: str) -> bool:
    r = subprocess.run(["git", "-C", str(root), "cat-file", "-e", f"{commit}:{rel}"],
                       capture_output=True, text=True)
    return r.returncode == 0


#: AD-036 section 6.1: a ruling label the register cannot see fails under this name.
UNPARSED = "ruling_label_unparsed"
#: A ruling label in a heading or bold position at the start of a line: `## AD-035-R1.`,
#: `### 2. R-40 ...`, `- **R3.**`, `**AD-033-R8.**`. The label forms are AD-036 section 6.1's.
_LABEL_POSITION_RE = re.compile(
    r"^(?:#{1,6}\s+(?:\d+(?:\.\d+)*\.?\s+)?|\s*(?:[-*]\s+)?\*\*)"
    r"(AD-\d{3}-R\d+|R-?\d{1,3})(?![\w-])")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")


def _design_note_paths(s: Settings) -> list[Path]:
    """Every design note the label check reads: `docs/design/**/*.md` plus each configured glob."""
    paths = set((s.root / "docs" / "design").rglob("*.md")) if (s.root / "docs" / "design").is_dir() \
        else set()
    for fam in s.design_notes:
        paths |= set(s.root.glob(fam["glob"]))
    return sorted(p for p in paths if p.is_file())


def unparsed_labels(s: Settings, all_notes: bool = False) -> list[tuple[str, int, str]]:
    """(path, line, label) for each ruling label in a heading or bold position that no configured
    pattern for that note captures (AD-036 section 6.1).

    The defect this closes: AD-035 was edited before commit from `**AD-035-Rn.**` to
    `## AD-035-Rn.` headings, the configured pattern reads only the bold form, and so no record
    was ever required for any AD-035 ruling: a label the register cannot parse is a label it
    cannot miss. By default only notes absent from the baseline tree are read, as with the
    missing-record check; `all_notes=True` reads every note (the PA-001 report over all repos).
    """
    out = []
    for p in _design_note_paths(s):
        rel = p.relative_to(s.root).as_posix()
        if not all_notes and s.baseline_commit and _in_tree(s.root, s.baseline_commit, rel):
            continue
        out.extend(unparsed_labels_in(s, rel, p.read_text(encoding="utf-8", errors="replace")))
    return out


def family_matches(glob: str, rel: str) -> bool:
    """Does a repository-relative path match a `decisions.design_notes` glob? Path.glob's rules:
    `*` stays inside one directory, `**` crosses them. Used where the file is a blob, not a path
    on disk (the commit hook reads the staged bytes, HOOK-001)."""
    out, i = [], 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
            continue
        if glob.startswith("**", i):
            out.append(".*")
            i += 2
            continue
        c = glob[i]
        out.append("[^/]*" if c == "*" else "[^/]" if c == "?" else re.escape(c))
        i += 1
    return re.fullmatch("".join(out), rel) is not None


def is_design_note(s: Settings, rel: str) -> bool:
    """Is this path one the label checks read: `docs/design/**/*.md` or a configured family?"""
    return (rel.startswith("docs/design/") and rel.endswith(".md")) or \
        any(family_matches(f["glob"], rel) for f in s.design_notes)


def unparsed_labels_in(s: Settings, rel: str, text: str) -> list[tuple[str, int, str]]:
    """(rel, line, label) for each label in a heading or bold position of `text` that no
    configured pattern of the note's families captures. `unparsed_labels` for one note's bytes."""
    pats = [re.compile(f["pattern"]) for f in s.design_notes if family_matches(f["glob"], rel)]
    out = []
    fence = False
    for n, line in enumerate(text.splitlines(), 1):
        if _FENCE_RE.match(line):
            fence = not fence
            continue
        if fence:
            continue
        m = _LABEL_POSITION_RE.match(line)
        if not m:
            continue
        label = m.group(1)
        if not any((cm := pat.match(line)) and cm.group(1) == label for pat in pats):
            out.append((rel, n, label))
    return out


def labeled_decisions_after_baseline(s: Settings) -> list[tuple[str, str]]:
    """(qualified id, path) for each label in a design note absent from the baseline tree.

    The note globs and label patterns are configuration (`decisions.design_notes`), one entry per
    family of notes: `glob`, `pattern` (one capture group, the label) and `id` (a template with
    `{repo}`, `{label}` and `{doc}`, the document's own identifier from its filename).
    """
    if not s.baseline_commit:
        return []
    out = []
    for fam in s.design_notes:
        for p in sorted(s.root.glob(fam["glob"])):
            rel = p.relative_to(s.root).as_posix()
            if _in_tree(s.root, s.baseline_commit, rel):
                continue
            out.extend((qid, rel) for qid in family_labels(s, fam, rel,
                                                          p.read_text(encoding="utf-8")))
    return sorted(set(out))


def labeled_ids_in(s: Settings, rel: str, text: str) -> list[str]:
    """Every qualified id the configured families label in one note's text (any family whose
    glob matches `rel`). `labeled_decisions_after_baseline` for one note's bytes."""
    out = []
    for fam in s.design_notes:
        if family_matches(fam["glob"], rel):
            out.extend(family_labels(s, fam, rel, text))
    return sorted(set(out))


def labeled_spans_in(s: Settings, rel: str, text: str) -> list[tuple[str, str, int, int]]:
    """`(qualified id, label, first line, last line)` for each ruling the configured families label
    in one note's text, the span being the ruling's verbatim body (AD-033-R3 `source.lines`).

    The span rules are the ones PA-001 and SEL-002 registered rulings by
    (`scripts/pa001/register_rulings.py`, `scripts/sel002/seed_db1.py` `section_span`), generalised
    so `seldon cc register` can record a Desktop note's rulings with no script (SEL-006 Part A):
      - a label in a heading (`## AD-035-R1.`) spans its section, to the line before the next heading
        of the same or a higher level;
      - a label in a list item (`- **R3.** ...`) spans the item with its deeper-indented lines, to the
        line before the next non-blank line indented no deeper than the item, or the next heading;
      - a label opening a bold paragraph (`**FC-30.** ...`) spans to the line before the next labelled
        line or heading, so a table or list the ruling carries stays in its span (AD-032 FC-30's record).
    Trailing blank lines are dropped. Lines inside fenced code are never a label.
    """
    lines = text.splitlines()
    fenced = set()
    fence = False
    for n, line in enumerate(lines, 1):
        if _FENCE_RE.match(line):
            fence = not fence
            fenced.add(n)
        elif fence:
            fenced.add(n)
    found = []
    for fam in s.design_notes:
        if not family_matches(fam["glob"], rel):
            continue
        pat = re.compile(fam["pattern"])
        for n, line in enumerate(lines, 1):
            if n in fenced or not (m := pat.match(line)):
                continue
            found.append((family_labels(s, fam, rel, line)[0], m.group(1), n))
    starts = {n for _q, _l, n in found}
    out = {(qid, label, n, _span_end(lines, n, starts)) for qid, label, n in found}
    return sorted(out, key=lambda r: (r[2], r[0]))


def _span_end(lines: list[str], start: int, starts: set) -> int:
    """The last line (1-based) of the ruling whose label is on line `start`; `starts` holds every
    labelled line of the note. See `labeled_spans_in`."""
    head = re.match(r"^(#{1,6})\s", lines[start - 1])
    indent = len(lines[start - 1]) - len(lines[start - 1].lstrip())
    bullet = re.match(r"^\s*[-*]\s", lines[start - 1]) is not None
    end = len(lines)
    for j in range(start + 1, len(lines) + 1):
        ln = lines[j - 1]
        h = re.match(r"^(#{1,6})\s", ln)
        if head:
            if h and len(h.group(1)) <= len(head.group(1)):
                end = j - 1
                break
            continue
        if h:
            end = j - 1
            break
        if not bullet and j in starts:
            end = j - 1
            break
        if bullet and ln.strip() and len(ln) - len(ln.lstrip()) <= indent:
            end = j - 1
            break
    while end > start and not lines[end - 1].strip():
        end -= 1
    return end


def family_labels(s: Settings, fam: dict, rel: str, text: str) -> list[str]:
    """The qualified ids one family's pattern labels in `text`, the note's own identifier taken
    from its filename (`doc_id`, default the AD-/DN- prefix, after any date)."""
    pat = re.compile(fam["pattern"], re.M)
    doc_re = re.compile(fam.get("doc_id", r"^((?:AD|DN)-\d{3})"))
    stem = re.sub(r"^\d{4}-\d{2}-\d{2}_", "", Path(rel).stem)
    m = doc_re.search(stem)
    doc = m.group(1) if m else stem
    return [fam["id"].format(repo=s.repository, label=lm.group(1), doc=doc)
            for lm in pat.finditer(text)]


# ---------------------------------------------------------------------------
# Consumers (AD-033-R6), filled mechanically
# ---------------------------------------------------------------------------

def cited_by(local_id: str, root: Path, roots: Iterable[str]) -> list[str]:
    """Repository-relative files under `roots` that cite `local_id` as a whole token."""
    pat = re.compile(r"(?<![\w-])" + re.escape(local_id) + r"(?![\w]|-\d)")
    out = []
    for r in roots:
        base = root / r
        paths = [base] if base.is_file() else sorted(base.rglob("*")) if base.is_dir() else []
        for p in paths:
            if not p.is_file() or p.suffix not in (".py", ".yaml", ".yml", ".mk", ".toml") \
                    or "__pycache__" in p.parts:
                continue
            try:
                if pat.search(p.read_text(encoding="utf-8")):
                    out.append(p.relative_to(root).as_posix())
            except UnicodeDecodeError:
                continue
    return out


# ---------------------------------------------------------------------------
# Binding at registration (AD-033-R7)
# ---------------------------------------------------------------------------

ADVISORY = "advisory until SEL-003"


@dataclass
class DecisionMatch:
    id: str
    status: str
    statement: str
    source_path: Optional[str]
    match_method: str
    match_score: Optional[float] = None
    matched_terms: list[str] = field(default_factory=list)

    def render(self) -> str:
        how = (f"concept overlap {self.match_score:.2f}: {', '.join(self.matched_terms[:6])}"
               if self.match_method == "concept_overlap" else "names it")
        text = " ".join((self.statement or "").split())
        return (f"  {self.id}  [{self.status}]  {self.source_path or '?'}  ({how})\n"
                f"    {text[:280]}{'...' if len(text) > 280 else ''}")


class Bound(list):
    """Matches that came from the register (AD-033-R7), so an empty result still renders as the
    register's binding block, advisory label included."""


def resolve_mentions(u: Universe, text: str) -> list[str]:
    """Record ids a text names, qualified: explicitly, else by this repository, then its imports."""
    out: list[str] = []
    for m in _ID_FORMS.finditer(text or ""):
        repo, local = m.group("repo"), m.group("local")
        candidates = [f"{repo}:{local}"] if repo else [f"{r}:{local}" for r in u.scope_repos()]
        for qid in candidates:
            try:
                if u.get(qid) is not None:
                    if qid not in out:
                        out.append(qid)
                    break
            except RegisterError:
                continue
    return out


def bind(u: Universe, task_text: str, threshold: float) -> list[DecisionMatch]:
    """Accepted records of this repository and its imports a task's text is constrained by.

    Identifier pass first (exact, never truncated), then the concept pass with Seldon's overlap
    score UNCHANGED (`seldon.core.governed.overlap_score`), over record text, capped at the
    configured limit: AD-033 section 6 arm O is this code, so it is not tuned here. Only accepted
    records bind; a superseded, deprecated, rejected or proposed record never reaches a match.
    """
    from seldon.core.governed import concept_terms, overlap_score

    # An operator catch is an observation, not a rule: it reaches a later task through recall (RECALL-001), never
    # as a binding.
    accepted = [r for repo in u.scope_repos() for r in u.records(repo).values()
                if r.status == BINDING and r.get("kind") != "catch"]
    by_id = {r.id: r for r in accepted}
    named = [q for q in resolve_mentions(u, task_text) if q in by_id]
    out = [DecisionMatch(id=q, status=BINDING, statement=_statement_of(by_id[q]),
                         source_path=(by_id[q].get("source") or {}).get("path"),
                         match_method="identifier") for q in named]
    task_terms = concept_terms(task_text)
    concept = []
    for r in accepted:
        if r.id in named:
            continue
        score, shared = overlap_score(task_terms, concept_terms(r.text()))
        if score >= threshold:
            concept.append(DecisionMatch(id=r.id, status=BINDING, statement=_statement_of(r),
                                         source_path=(r.get("source") or {}).get("path"),
                                         match_method="concept_overlap", match_score=round(score, 3),
                                         matched_terms=shared))
    concept.sort(key=lambda m: (-(m.match_score or 0.0), _sort_key(m.id)))
    return Bound(out + concept[:u.s.binding_limit])


def _statement_of(r: Record) -> str:
    if r.get("kind") == "mirror":
        return f"mirrors {r.get('mirrors')}"
    return str(r.get("statement") or "")


def render_binding(matches: list[DecisionMatch], written: int) -> str:
    if not matches:
        return (f"No accepted decision in the register binds this task ({ADVISORY}). If that is "
                f"wrong, the decision has no record: register it with `seldon decision`.")
    lines = [f"Bound by {len(matches)} accepted decision record(s), {ADVISORY} "
             f"({written} new edge(s)):"]
    lines.extend(m.render() for m in matches)
    return "\n".join(lines)


def today() -> str:
    return _date.today().isoformat()


# ---------------------------------------------------------------------------
# The projection into the project graph (AD-033-R1, R10)
# ---------------------------------------------------------------------------

ACTOR = "decision_register"

#: The force a positional Ruling carries once its repository has a register (AD-033-R7).
SEARCHABLE = "searchable"


def register_exists(project_dir: Path, config: dict) -> bool:
    s = settings(project_dir, config)
    return bool(s) and Register(s.repository, s.root, s.register_dir).exists()


def _props(rec: Record, imported: bool) -> dict:
    src = rec.get("source") or {}
    rat = rec.get("rationale") or {}
    statement = _statement_of(rec)
    props = {
        "name": rec.id, "decision_id": rec.id, "home_repository": rec.home, "imported": imported,
        "kind": rec.get("kind"), "statement": statement, "statement_check": rec.get("statement_check"),
        "source_path": src.get("path"), "source_lines": src.get("lines"),
        "source_sha256": src.get("sha256"), "source_text": src.get("text"),
        "scope": rec.get("scope"), "scope_note": rec.get("scope_note"),
        "rationale_path": rat.get("path"), "rationale_anchor": rat.get("anchor"),
        "consumer": rec.get("consumer") or [], "review_only": rec.get("review_only"),
        "waits_on": rec.get("waits_on"), "decided_by": rec.get("decided_by"),
        "operator_stated": bool(rec.get("operator_stated")), "decision_date": rec.get("date"),
        "superseded_by": rec.superseded_by, "mirrors": rec.get("mirrors"),
        "amendments": [f"{a['clause']} | {' '.join(str(a['text']).split())} | by {a.get('by') or a.get('decided_by')}"
                       for a in rec.amendments],
        "control_type": rec.get("control_type"), "pattern": rec.get("pattern"),
        "catch_class": rec.get("catch_class"), "task": rec.get("task"),
        "register_hash": rec.last_hash,
        "description": (statement.splitlines() or [""])[0][:200],
    }
    return {k: v for k, v in props.items() if v is not None}


@dataclass
class ProjectionReport:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    transitions: int = 0
    edges_created: dict[str, int] = field(default_factory=dict)
    edges_skipped: dict[str, int] = field(default_factory=dict)
    rulings_demoted: int = 0
    rendered: Optional[str] = None
    by_status: dict[str, int] = field(default_factory=dict)


def project(*, project_dir: Path, config: dict, driver, database: str, domain_config,
            session_id: Optional[str] = None, render: bool = True) -> ProjectionReport:
    """Replay the register (own and imported) into `Decision` nodes, and render REGISTER.md.

    The only write into the graph is this replay (AD-033-R11). Idempotent by `register_hash`: a
    record whose last event is what the node already carries is not rewritten. Every write goes
    through `seldon.core.artifacts`, so the project's own event store records the projection.
    """
    from seldon.core.artifacts import create_artifact, create_link, transition_state, update_artifact
    from seldon.core import governed

    u = universe(project_dir, config)
    rep = ProjectionReport()
    with driver.session(database=database) as session:
        have = {r["qid"]: r for r in session.run(
            "MATCH (d:Artifact:Decision) RETURN d.decision_id AS qid, d.artifact_id AS aid, "
            "d.state AS state, d.register_hash AS hash").data()}
    ids: dict[str, str] = {}
    records: list[Record] = []
    for repo in u.scope_repos():
        for rec in u.records(repo).values():
            records.append(rec)
            imported = repo != u.s.repository
            rep.by_status[rec.status] = rep.by_status.get(rec.status, 0) + 1
            props = _props(rec, imported)
            cur = have.get(rec.id)
            if cur is None:
                aid = create_artifact(project_dir=project_dir, driver=driver, database=database,
                                      domain_config=domain_config, artifact_type="Decision",
                                      properties=props, actor=ACTOR, authority="accepted",
                                      session_id=session_id)
                rep.created += 1
                state = domain_config.get_initial_state("Decision")
            else:
                aid, state = cur["aid"], cur["state"]
                if cur["hash"] == rec.last_hash and state == rec.status:
                    rep.unchanged += 1
                    ids[rec.id] = aid
                    continue
                update_artifact(project_dir=project_dir, driver=driver, database=database,
                                artifact_id=aid, properties=props, actor=ACTOR,
                                authority="accepted", session_id=session_id)
                rep.updated += 1
            if state != rec.status:
                transition_state(project_dir=project_dir, driver=driver, database=database,
                                 domain_config=domain_config, artifact_id=aid,
                                 artifact_type="Decision", current_state=state,
                                 new_state=rec.status, actor=ACTOR, authority="accepted",
                                 session_id=session_id)
                rep.transitions += 1
            ids[rec.id] = aid

    def link(a: str, b: str, rel: str, props: Optional[dict] = None) -> None:
        if a not in ids or b not in ids:
            rep.edges_skipped[rel] = rep.edges_skipped.get(rel, 0) + 1
            return
        if governed._link_exists(driver, database, ids[a], ids[b], rel):
            return
        create_link(project_dir=project_dir, driver=driver, database=database,
                    domain_config=domain_config, from_id=ids[a], to_id=ids[b],
                    from_type="Decision", to_type="Decision", rel_type=rel, actor=ACTOR,
                    authority="accepted", session_id=session_id, rel_properties=props or {})
        rep.edges_created[rel] = rep.edges_created.get(rel, 0) + 1

    for rec in records:
        for t in rec.get("supersedes") or []:
            link(rec.id, t, "supersedes")
        # A supersession declared by a transition (`superseded_by`) is the same relation from the other end.
        if rec.superseded_by:
            link(rec.superseded_by, rec.id, "supersedes")
        for a in rec.get("amends") or []:
            link(rec.id, a["target"], "amends", {"clause": a["clause"]})
        for a in rec.amendments:
            if a.get("by"):
                link(a["by"], rec.id, "amends", {"clause": a["clause"]})
        if rec.get("mirrors"):
            link(rec.id, rec.get("mirrors"), "mirrors")
        for c in rec.get("constrains") or []:
            link(rec.id, c, "constrains")

    if u.register(u.s.repository).exists():
        rep.rulings_demoted = demote_positional_rulings(
            project_dir=project_dir, driver=driver, database=database, session_id=session_id)
        if render:
            rep.rendered = str(write_rendered(u).relative_to(u.s.root))
    return rep


def demote_positional_rulings(*, project_dir: Path, driver, database: str,
                              session_id: Optional[str] = None) -> int:
    """AD-033-R7: once a repository has a register, its positional Rulings stop binding.

    They stay as searchable content: `force` becomes `searchable` and the parse's verdict is kept
    in `positional_force`, so nothing the parse said is lost. Written through `update_artifact`,
    so the change is an event, not a silent property edit.
    """
    from seldon.core.artifacts import update_artifact

    with driver.session(database=database) as session:
        rows = session.run("MATCH (r:Artifact:Ruling) WHERE r.force = 'binding' "
                           "RETURN r.artifact_id AS aid").data()
    for row in rows:
        update_artifact(project_dir=project_dir, driver=driver, database=database,
                        artifact_id=row["aid"],
                        properties={"force": SEARCHABLE, "positional_force": "binding"},
                        actor=ACTOR, authority="accepted", session_id=session_id)
    return len(rows)


def decision_artifact_ids(driver, database: str) -> dict[str, str]:
    with driver.session(database=database) as session:
        return {r["qid"]: r["aid"] for r in session.run(
            "MATCH (d:Artifact:Decision) RETURN d.decision_id AS qid, d.artifact_id AS aid").data()}


# ---------------------------------------------------------------------------
# The conflicts probe on the register (AD-033-R9, FC-18)
# ---------------------------------------------------------------------------

#: The decision probe's amendment verbs and identifier forms, verbatim from its inventory.py
#: (squiddy/docs/findings/2026-10-03_operator_audit/probe/inventory.py, AMEND and REF), with the
#: register's DN-NNN-Rn form added to REF so DN-037's records are read too.
PROBE_AMEND = re.compile(r"\b(amends?|amended|revises?|revised|supersed(?:es|ed|e)|replaces?|replaced|"
                         r"reverses?|reversed|withdraws?|withdrawn|overrides?|retires?|retired|narrows?|"
                         r"rescinds?)\b", re.I)
PROBE_REF = re.compile(r"\b(?:AD-\d{3}(?:-R\d+)?|DN-\d{3}(?:-R\d+)?|R-\d{1,3}|EX-REQ-\d+|DI-\d{3}|ADR-\d{3})\b")
_SENTENCE = re.compile(r"(?<=[.;])\s+|\n")


@dataclass
class ProbeReport:
    findings_total: int = 0
    open_contradictions: list[str] = field(default_factory=list)
    open_silent_supersessions: list[str] = field(default_factory=list)
    unrecorded_pairs: list[dict] = field(default_factory=list)
    excluded_pairs: list[dict] = field(default_factory=list)
    resolved: dict[str, list[str]] = field(default_factory=dict)
    active_records: int = 0

    @property
    def clean(self) -> bool:
        return not (self.open_contradictions or self.open_silent_supersessions or self.unrecorded_pairs)


def conflicts_probe(u: Universe, findings_path: Optional[Path], exclusions_path: Optional[Path]) -> ProbeReport:
    """Re-run the decision probe on the register.

    Two halves, both over ACTIVE records (proposed or accepted) of every register the universe names:
      1. The probe's own findings (conflicts.jsonl): a finding is resolved when some register event
         cites it ("Probe Fnn" in its reason) on one of its records, or none of its records is still
         active. A contradiction or silent supersession with neither is open.
      2. A fresh scan for silent supersession: a record whose own sentence uses one of the probe's
         amendment verbs about another active record must have that relation recorded (supersedes,
         superseded_by, an amendment by it, or a mirror of a record that has it), or be excluded in
         the reviewed exclusions file with its reason. A new contradiction in prose is not machine-
         detectable; it reaches the register as a new probe finding, which half 1 then holds open.
    """
    recs: dict[str, Record] = {}
    events: list[dict] = []
    for repo in sorted(u.s.repositories):
        try:
            recs.update(u.records(repo))
            events.extend(e for r in u.records(repo).values() for e in r.events)
        except RegisterError:
            continue
    rep = ProbeReport(active_records=sum(1 for r in recs.values() if r.status in ACTIVE))
    cited: dict[str, set[str]] = {}
    for e in events:
        for f in set(re.findall(r"\bprobe (F\d{2})\b", f"{e.get('reason') or ''} {' '.join(e.get('receipts') or [])}", re.I)):
            cited.setdefault(f.upper(), set()).add(e["id"])

    def qualify(ref: str, home: str) -> Optional[str]:
        cands = [f"{home}:{ref}"] + [f"{r}:{ref}" for r in sorted(u.s.repositories) if r != home]
        if re.fullmatch(r"R-\d", ref):
            cands.append(f"squiddy:R-0{ref[2:]}")
        return next((c for c in cands if c in recs), None)

    if findings_path and Path(findings_path).is_file():
        for line in Path(findings_path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            x = json.loads(line)
            rep.findings_total += 1
            ids = [q for q in (qualify(i.split(":", 1)[-1] if ":" in i else i,
                                       i.split(":", 1)[0] if ":" in i else "squiddy") for i in x["ids"]) if q]
            touched = sorted(cited.get(x["finding"], set()) & set(ids)) or sorted(cited.get(x["finding"], set()))
            still_active = [q for q in ids if recs[q].status in ACTIVE]
            if touched or not still_active:
                rep.resolved[x["finding"]] = touched or ["no record still active"]
            elif x["class"] == "CONTRADICTION":
                rep.open_contradictions.append(f"{x['finding']}: {', '.join(x['ids'])}")
            else:
                rep.open_silent_supersessions.append(f"{x['finding']} ({x['class']}): {', '.join(x['ids'])}")

    excluded = []
    if exclusions_path and Path(exclusions_path).is_file():
        excluded = yaml.safe_load(Path(exclusions_path).read_text(encoding="utf-8")) or []
    excl = {(e["record"], e["cites"]): e["reason"] for e in excluded}

    def related(a: str, b: str, seen: int = 0) -> bool:
        A, B = recs[a], recs[b]
        if B.superseded_by == a or A.superseded_by == b:
            return True
        if b in (A.get("supersedes") or []) or a in (B.get("supersedes") or []):
            return True
        if any(x.get("by") == a for x in B.amendments) or any(x.get("by") == b for x in A.amendments):
            return True
        if any(x.get("target") == b for x in A.get("amends") or []):
            return True
        if A.get("mirrors") == b or B.get("mirrors") == a:
            return True
        if seen < 2 and A.get("kind") == "mirror" and A.get("mirrors") in recs:
            return related(A.get("mirrors"), b, seen + 1)
        return False

    for qid, r in sorted(recs.items()):
        if r.status not in ACTIVE:
            continue
        for sent in _SENTENCE.split((r.get("source") or {}).get("text", "")):
            verb = PROBE_AMEND.search(sent)
            if not verb:
                continue
            for ref in sorted(set(PROBE_REF.findall(sent))):
                q = qualify(ref, r.home)
                if not q or q == qid or recs[q].status not in ACTIVE or related(qid, q):
                    continue
                row = {"record": qid, "cites": q, "verb": verb.group(0), "sentence": sent.strip()[:200]}
                if (qid, q) in excl:
                    rep.excluded_pairs.append({**row, "reason": excl[(qid, q)]})
                else:
                    rep.unrecorded_pairs.append(row)
    return rep
