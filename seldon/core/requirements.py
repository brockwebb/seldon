"""Requirements as graph content, and the requirements table and RTM as projections of it (SEL-033, AD-013 ADDENDUM 01).

**What this module owns.** AD-013 declared `SRS_Requirement` in 2026-03 and nothing loaded or rendered it, so a project
kept its requirements in markdown and the graph held the file's hash (hazbrief-mcp SEL-032). Here are:

- the **load** (`seldon req import`, `seldon req add`, AD-013-R1): a markdown pipe table becomes `SRS_Requirement`
  nodes, idempotent on the requirement id, with `derived_from` to the source its `Set by` key names, `verified_by` to
  the test `Script` its `Verified by` cell names (SEL-021's test-node Script) and `satisfies` from the task its status
  names. What does not resolve is listed, never dropped (Gotel and Finkelstein 1994);
- the **projection** (`seldon docs generate requirements|rtm`, AD-013-R2): each file `docs.projections` declares has
  blocks between `<!-- seldon:projection ... -->` and `<!-- /seldon:projection -->` markers (Cog's generated regions),
  and only those blocks are rendered, so a file keeps its prose. A header line names the graph revision, the sha256 of
  the rendered blocks, so an unchanged graph renders the same bytes and commits nothing;
- the **checks** (AD-013-R3): requirements with no `verified_by` edge, and projections whose file differs from a fresh
  render.

The vocabulary follows ISO/IEC/IEEE 29148 (identifier, statement, source, verification, status), ReqIF (an object
with typed attributes and typed relations; a document is a hierarchy over objects) and SysML v2 (satisfy, verify,
derive). The design note is `docs/design/AD-013_ADDENDUM_01_requirements_as_graph_content.md`.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from seldon.core import graph
from seldon.core.artifacts import (PlannedWrite, commit_writes, plan_artifact, plan_link, plan_state_change,
                                   plan_update_artifact)
from seldon.core.events import make_event

#: The artifact type and the edges, as the domain config spells them.
REQ_TYPE = "SRS_Requirement"
REL_DERIVED_FROM = "derived_from"
REL_VERIFIED_BY = "verified_by"
REL_SATISFIES = "satisfies"

#: The actor every write of this module carries.
ACTOR = "seldon-req"

#: The text a projection prints in a verification cell with no `verified_by` edge (hazbrief-mcp's own wording,
#: HB-134R2; a project overrides it in `requirements.none_text`).
DEFAULT_NONE_TEXT = "none yet"
#: The text a projection prints for an empty attribute (hazbrief-mcp's `Validated by` dash).
DEFAULT_EMPTY_TEXT = "—"

#: Header names the importer recognises for each column, case-insensitively. A project overrides any of them in
#: `seldon.yaml` `requirements.columns.<field>` (a list), and `seldon req import --<field>-column` overrides both.
#: `id` and `statement` are required for a table to be a requirements table; the rest are optional.
DEFAULT_COLUMNS: Dict[str, List[str]] = {
    "id": ["ID"],
    "statement": ["Requirement", "Criterion", "Statement"],
    "set_by": ["Set by", "Source"],
    "verified_by": ["Verified by", "Checked by"],
    "validated_by": ["Validated by"],
    "satisfied_by": ["Satisfied by"],
    "status": ["Status", "State"],
    # hazbrief-mcp HB-144: the register records that state a row's ruling (`HBD-002, HBD-006`).
    "decision": ["Decision"],
}

#: The node property each optional column is kept in, verbatim (AD-013-R1: the edges carry the trace, the verbatim
#: cell keeps the source's wording for the projection).
COLUMN_PROPERTY = {
    "statement": "description",
    "set_by": "set_by",
    "verified_by": "verified_by_text",
    "validated_by": "validated_by",
    "satisfied_by": "satisfied_by_text",
    "status": "status_text",
    "decision": "decision_text",
}

#: The columns a projection renders when its `docs.projections` entry names none. A source is a node property, or one
#: of the computed sources: `@verified_by` (the test nodes of the `verified_by` edges), `@derived_from`,
#: `@satisfied_by`, `@state`, `@status` (status_text, else the state).
DEFAULT_PROJECTION_COLUMNS: Dict[str, List[Dict[str, str]]] = {
    "requirements": [
        {"header": "ID", "source": "requirement_id"},
        {"header": "Requirement", "source": "description"},
        {"header": "Set by", "source": "set_by"},
        {"header": "Verified by", "source": "@verified_by"},
        {"header": "Validated by", "source": "validated_by"},
        {"header": "Status", "source": "@status"},
    ],
    "rtm": [
        {"header": "ID", "source": "requirement_id"},
        {"header": "Requirement", "source": "description"},
        {"header": "Derived from", "source": "@derived_from"},
        {"header": "Satisfied by", "source": "@satisfied_by"},
        {"header": "Verified by", "source": "@verified_by"},
        {"header": "State", "source": "@state"},
    ],
}
KINDS = tuple(DEFAULT_PROJECTION_COLUMNS)

#: The counts sentence when neither the projection nor `requirements.counts_template` names one.
DEFAULT_COUNTS_TEMPLATE = "{total} requirements: {status_counts}; {unverified} with no verifying test"

START_RE = re.compile(r"<!--\s*seldon:projection\s+(?P<attrs>.*?)\s*-->")
END_MARK = "<!-- /seldon:projection -->"
END_RE = re.compile(r"<!--\s*/seldon:projection\s*-->")
HEADER_RE = re.compile(r"^<!-- seldon:projection-revision (?P<rev>[0-9a-f]+) .*-->$")
_ATTR_RE = re.compile(r'(\w+)=(?:"((?:[^"\\]|\\.)*)"|(\S+))')
_TEST_NODE_RE = re.compile(r"(?P<path>[\w./-]+\.py)::(?P<node>[\w\[\]./-]+)")
_PY_PATH_RE = re.compile(r"^[\w./-]+\.py$")
_TEST_NAME_RE = re.compile(r"^test_\w+$")
_KEY_RE = re.compile(r"\b[A-Z][A-Z0-9]*-\d+[A-Za-z0-9]*(?:-[A-Z]\d+)?\b")
_PLACEHOLDER_RE = re.compile(r"\{(total|unverified|status_counts|status:[^}]+|state:[^}]+|prefix:[^}]+)\}")


class RequirementsError(ValueError):
    """A load or a projection that cannot proceed; the message names what to fix."""


# ─────────────────────────────────────────────────────────────── settings


@dataclass
class Settings:
    """The `requirements:` and `docs.projections` blocks of seldon.yaml, with their defaults."""

    columns: Dict[str, List[str]]
    status_map: Dict[str, str]
    none_text: str
    empty_text: str
    counts_template: str
    projections: List[Dict[str, Any]]


def settings(config: dict) -> Settings:
    """Read the blocks; refuse a malformed one by name (a misspelled key must not fall back silently).

    Raises:
        RequirementsError: an unknown key, a projection with no path or an unknown kind.
    """
    block = (config or {}).get("requirements") or {}
    known = {"columns", "status_map", "none_text", "empty_text", "counts_template"}
    extra = set(block) - known
    if extra:
        raise RequirementsError(f"seldon.yaml requirements: unknown key(s) {sorted(extra)}; known {sorted(known)}")
    columns = {k: list(v) for k, v in DEFAULT_COLUMNS.items()}
    for k, v in (block.get("columns") or {}).items():
        if k not in DEFAULT_COLUMNS:
            raise RequirementsError(f"seldon.yaml requirements.columns.{k}: unknown field; known {sorted(DEFAULT_COLUMNS)}")
        columns[k] = [v] if isinstance(v, str) else list(v)
    projections = []
    for i, p in enumerate(((config or {}).get("docs") or {}).get("projections") or []):
        if not isinstance(p, dict) or not p.get("path"):
            raise RequirementsError(f"seldon.yaml docs.projections[{i}] needs a `path`")
        kind = p.get("kind", "requirements")
        if kind not in KINDS:
            raise RequirementsError(f"seldon.yaml docs.projections[{i}].kind {kind!r}: one of {list(KINDS)}")
        extra = set(p) - {"path", "kind", "columns", "counts_template"}
        if extra:
            raise RequirementsError(f"seldon.yaml docs.projections[{i}]: unknown key(s) {sorted(extra)}")
        projections.append({"path": p["path"], "kind": kind,
                            "columns": p.get("columns") or DEFAULT_PROJECTION_COLUMNS[kind],
                            "counts_template": p.get("counts_template")})
    return Settings(columns=columns, status_map=dict(block.get("status_map") or {}),
                    none_text=block.get("none_text", DEFAULT_NONE_TEXT),
                    empty_text=block.get("empty_text", DEFAULT_EMPTY_TEXT),
                    counts_template=block.get("counts_template", DEFAULT_COUNTS_TEMPLATE),
                    projections=projections)


# ─────────────────────────────────────────────────────────────── markdown tables


def split_row(line: str) -> List[str]:
    """The cells of a GFM pipe-table row, split on unescaped pipes, each stripped; escapes are kept verbatim so a
    rendered row reproduces the source."""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    return [c.strip() for c in re.split(r"(?<!\\)\|", s)]


def _is_separator(cells: List[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", c) for c in cells)


@dataclass
class Table:
    header: List[str]
    rows: List[Tuple[int, List[str]]]   # (1-based line number, cells)
    heading: Optional[str]              # the nearest markdown heading above the table
    header_line: int                    # 1-based
    last_line: int                      # 1-based, the last row


def parse_tables(text: str) -> List[Table]:
    """Every pipe table in `text`, with the heading it sits under."""
    lines = text.splitlines()
    tables: List[Table] = []
    heading = None
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^#{1,6}\s+(.*?)\s*#*\s*$", line)
        if m:
            heading = m.group(1).strip()
        if line.lstrip().startswith("|") and i + 1 < len(lines) and _is_separator(split_row(lines[i + 1])):
            header = split_row(line)
            rows = []
            j = i + 2
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                rows.append((j + 1, split_row(lines[j])))
                j += 1
            tables.append(Table(header=header, rows=rows, heading=heading, header_line=i + 1, last_line=j))
            i = j
            continue
        i += 1
    return tables


def _column_index(header: List[str], names: List[str]) -> Optional[int]:
    wanted = [n.strip().lower() for n in names]
    for idx, h in enumerate(header):
        if h.strip().lower() in wanted:
            return idx
    return None


@dataclass
class Row:
    """One requirement row of a load source."""

    requirement_id: str
    fields: Dict[str, str]              # field name -> verbatim cell (statement, set_by, ...)
    section: Optional[str]
    line: int
    table: int                          # index into the source's tables


@dataclass
class Source:
    path: str                           # relative to the project
    tables: List[Table]
    req_tables: List[int]               # indices of the tables that are requirements tables
    rows: List[Row]
    keys: Dict[str, str]                # a `Key | File` table's map


def read_source(project_dir: Path, rel: str, columns: Dict[str, List[str]]) -> Source:
    """Parse a markdown requirements file.

    A table is a requirements table when its header names an id column and a statement column. A table whose header
    is `Key | File` is the key map for `Set by`.

    Raises:
        RequirementsError: the file is missing, holds no requirements table, or repeats an id.
    """
    path = Path(project_dir) / rel
    if not path.is_file():
        raise RequirementsError(f"{rel} is not a file in {project_dir}")
    tables = parse_tables(path.read_text(encoding="utf-8"))
    rows: List[Row] = []
    req_tables: List[int] = []
    keys: Dict[str, str] = {}
    for ti, t in enumerate(tables):
        lower = [h.lower() for h in t.header]
        if lower == ["key", "file"]:
            for _, cells in t.rows:
                if len(cells) == 2:
                    keys[cells[0].strip("`")] = cells[1].strip("`")
            continue
        id_col = _column_index(t.header, columns["id"])
        st_col = _column_index(t.header, columns["statement"])
        if id_col is None or st_col is None:
            continue
        req_tables.append(ti)
        idx = {f: _column_index(t.header, names) for f, names in columns.items() if f not in ("id",)}
        for line, cells in t.rows:
            if len(cells) != len(t.header):
                raise RequirementsError(f"{rel}:{line}: {len(cells)} cells under a {len(t.header)}-column header")
            rid = cells[id_col].strip()
            if not rid:
                raise RequirementsError(f"{rel}:{line}: a row with no id")
            fields = {f: cells[i] for f, i in idx.items() if i is not None}
            rows.append(Row(requirement_id=rid, fields=fields, section=t.heading, line=line, table=ti))
    if not rows:
        raise RequirementsError(f"{rel} holds no requirements table (a header naming {columns['id']} and "
                                f"{columns['statement']})")
    dup = [k for k, n in Counter(r.requirement_id for r in rows).items() if n > 1]
    if dup:
        raise RequirementsError(f"{rel}: id(s) repeated: {dup}")
    return Source(path=rel, tables=tables, req_tables=req_tables, rows=rows, keys=keys)


# ─────────────────────────────────────────────────────────────── cell readers


def status_word(status_text: str, status_map: Dict[str, str]) -> Optional[str]:
    """The status-map key `status_text` starts with (the longest; case-insensitive; followed by a non-letter or the
    end), or None. `not met (ruled out)` matches before `not met`, and `met` never matches `metadata`."""
    s = (status_text or "").strip().lower()
    best = None
    for key in status_map:
        k = key.lower()
        if s.startswith(k) and (len(s) == len(k) or not s[len(k)].isalnum()):
            if best is None or len(k) > len(best):
                best = key
    return best


def test_refs(cell: str, project_dir: Path) -> Tuple[List[str], List[str]]:
    """The pytest node ids a verification cell names, in order, and the references that name no file.

    Three forms: `path::node` (SEL-021's grammar); a test file followed by test names (`tests/x.py` `test_a`,
    `test_b`); a test file alone, itself a pytest node id. Anything else (a harness, "inspection") is not a test and is
    neither a ref nor unresolved: it stays in the verbatim cell.
    """
    refs: List[str] = []
    missing: List[str] = []
    text = cell or ""
    seen = set()

    def add(ref: str, path: str) -> None:
        if ref in seen:
            return
        seen.add(ref)
        if (Path(project_dir) / path).is_file() and ".." not in Path(path).parts and not Path(path).is_absolute():
            refs.append(ref)
        else:
            missing.append(ref)

    # Tokens in order: backticked spans and bare words, split on `;`, `,` and whitespace.
    tokens = re.findall(r"`[^`]+`|[^\s;,`()]+", text)
    current_file = None
    file_used = True
    for raw in tokens:
        tok = raw.strip("`").strip()
        m = _TEST_NODE_RE.fullmatch(tok)
        if m:
            if current_file and not file_used:
                add(current_file, current_file)
            current_file, file_used = None, True
            add(tok, m.group("path"))
            continue
        if _PY_PATH_RE.match(tok) and "test" in Path(tok).name:
            if current_file and not file_used:
                add(current_file, current_file)
            current_file, file_used = tok, False
            continue
        if current_file and _TEST_NAME_RE.match(tok):
            add(f"{current_file}::{tok}", current_file)
            file_used = True
            continue
    if current_file and not file_used:
        add(current_file, current_file)
    return refs, missing


def set_by_keys(cell: str) -> List[str]:
    """The key of each `;`-separated part of a `Set by` cell: its first word (`DN-019 §3 row 2` -> `DN-019`)."""
    out = []
    for part in (cell or "").split(";"):
        part = part.strip().strip("`")
        if not part or part in ("—", "-"):
            continue
        out.append(part.split()[0].rstrip(",.:"))
    return out


def decision_keys(cell: str) -> List[str]:
    """The record ids a `Decision` cell lists (`HBD-001, HBD-006`; a `—` or blank lists none)."""
    return [k.strip("` ") for k in re.split(r"[;,]", cell or "") if k.strip("` ") not in ("", "—", "-")]


def natural_key(rid: str) -> list:
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", rid)]


# ─────────────────────────────────────────────────────────────── graph reads


def _rows(session, query: str, **params) -> list:
    return session.run(query, **params).data()


def find_requirement(session, rid: str) -> Optional[dict]:
    rows = _rows(session, f"MATCH (r:Artifact:{REQ_TYPE} {{requirement_id: $rid}}) RETURN r", rid=rid)
    if len(rows) > 1:
        raise RequirementsError(f"{len(rows)} {REQ_TYPE} nodes carry requirement_id {rid!r}; ids are unique per "
                                f"project (AD-013-R1)")
    return dict(rows[0]["r"]) if rows else None


def resolve_key(session, key: str, keymap: Dict[str, str]) -> Optional[dict]:
    """The artifact a `Set by` or status key names: through the source's key map to a file (a task's source_file, a
    DesignNote's path), else a task whose name starts with the key, a register record, an ArchitecturalDecision, or a
    requirement (a parent). None when nothing or more than one artifact matches. A governed Document is never a
    target: AD-030 section 4 closes its edge set, so a requirement whose source is one lists it as unresolved."""
    path = keymap.get(key)
    if path:
        rows = _rows(session,
                     "MATCH (a:Artifact) WHERE (a:ResearchTask AND a.source_file = $p) "
                     "OR (a:DesignNote AND a.path = $p) "
                     "RETURN DISTINCT a.artifact_id AS id, a.artifact_type AS type", p=path)
        if len(rows) == 1:
            return rows[0]
    rows = _rows(session,
                 "MATCH (a:Artifact) WHERE (a:ResearchTask AND (a.name = $k OR a.name STARTS WITH $k + ' ')) "
                 "OR (a:Decision AND a.decision_id ENDS WITH ':' + $k) "
                 "OR (a:ArchitecturalDecision AND a.name = $k) "
                 f"OR (a:{REQ_TYPE} AND a.requirement_id = $k) "
                 "RETURN DISTINCT a.artifact_id AS id, a.artifact_type AS type", k=key)
    return rows[0] if len(rows) == 1 else None


def _test_scripts(session, refs: Iterable[str]) -> Dict[str, str]:
    rows = _rows(session, "MATCH (s:Artifact:Script) WHERE s.test_node IN $refs "
                          "RETURN s.test_node AS t, s.artifact_id AS id ORDER BY s.created_at", refs=list(refs))
    out: Dict[str, str] = {}
    for r in rows:
        out.setdefault(r["t"], r["id"])
    return out


def _out_edges(session, rid: str) -> Dict[str, set]:
    rows = _rows(session,
                 f"MATCH (r:Artifact:{REQ_TYPE} {{artifact_id: $id}})-[e:VERIFIED_BY|DERIVED_FROM]->(t:Artifact) "
                 "RETURN type(e) AS rel, t.artifact_id AS to", id=rid)
    rows += _rows(session,
                  f"MATCH (t:Artifact)-[e:SATISFIES]->(r:Artifact:{REQ_TYPE} {{artifact_id: $id}}) "
                  "RETURN type(e) AS rel, t.artifact_id AS to", id=rid)
    out: Dict[str, set] = {"VERIFIED_BY": set(), "DERIVED_FROM": set(), "SATISFIES": set()}
    for r in rows:
        out[r["rel"]].add(r["to"])
    return out


# ─────────────────────────────────────────────────────────────── state walk


def state_path(machine: Dict[str, List[str]], start: str, goal: str) -> Optional[List[str]]:
    """The shortest sequence of states after `start` that ends at `goal` on the domain's machine, [] when already
    there, None when unreachable (breadth-first)."""
    if start == goal:
        return []
    prev = {start: None}
    q = deque([start])
    while q:
        s = q.popleft()
        for n in machine.get(s, []):
            if n not in prev:
                prev[n] = s
                if n == goal:
                    path = [n]
                    while prev[path[-1]] != start:
                        path.append(prev[path[-1]])
                    return list(reversed(path))
                q.append(n)
    return None


# ─────────────────────────────────────────────────────────────── the load


@dataclass
class Plan:
    """What an import or an add will write, and what did not resolve."""

    writes: List[PlannedWrite] = field(default_factory=list)
    created: List[str] = field(default_factory=list)
    updated: List[str] = field(default_factory=list)
    unchanged: List[str] = field(default_factory=list)
    unresolved: List[str] = field(default_factory=list)
    links_added: int = 0
    links_removed: int = 0
    tests_created: int = 0
    states: Counter = field(default_factory=Counter)


@dataclass
class Spec:
    """One requirement as a load names it: its properties, the target state and the refs to resolve."""

    requirement_id: str
    properties: Dict[str, str]
    status_text: Optional[str]
    test_refs: List[str]
    set_by_keys: List[str]
    satisfier_keys: List[str]
    decision_keys: List[str]
    where: str                           # for messages: `<file>:<line>` or `req add`


def spec_from_row(row: Row, src: Source, project_dir: Path, s: Settings, document: str) -> Tuple[Spec, List[str]]:
    """The Spec of one source row, and the unresolved test references it names."""
    f = row.fields
    props = {"requirement_id": row.requirement_id, "document": document}
    if row.section:
        props["section"] = row.section
    for field_name, prop in COLUMN_PROPERTY.items():
        if field_name in f:
            props[prop] = f[field_name]
    refs, missing = test_refs(f.get("verified_by", ""), project_dir)
    status = f.get("status")
    word = status_word(status or "", s.status_map) if status is not None else None
    satisfiers = []
    if word and s.status_map.get(word) in ("implemented", "verified"):
        tail = (status or "")[len(word):]
        satisfiers = _KEY_RE.findall(tail)
    where = f"{src.path}:{row.line}"
    return (Spec(requirement_id=row.requirement_id, properties=props, status_text=status,
                 test_refs=refs, set_by_keys=set_by_keys(f.get("set_by", "")), satisfier_keys=satisfiers,
                 decision_keys=decision_keys(f.get("decision", "")), where=where),
            [f"{where} {row.requirement_id}: verified_by {m!r} names no file in the project" for m in missing])


def plan_specs(project_dir: Path, driver, database: str, domain_config, specs: List[Spec], s: Settings,
               keymap: Dict[str, str], prune: bool = True) -> Plan:
    """Plan every write that brings the graph to `specs`, idempotent on the requirement id.

    - a new id is created; a known id has its changed properties updated;
    - the state walks the domain machine to the status map's target; `verified` needs a `verified_by` edge
      (AD-013-R1), so a requirement mapped there with none is held at `implemented`;
    - `verified_by`, `derived_from` and `satisfies` edges are added where missing and, with `prune`, removed where the
      load no longer names them, so the graph mirrors the load.

    Nothing is written here; :func:`apply` commits the plan in one append.
    """
    plan = Plan()
    machine = domain_config.state_machines.get(REQ_TYPE, {})
    initial = domain_config.get_initial_state(REQ_TYPE)
    new_tests: Dict[str, str] = {}
    with driver.session(database=database) as session:
        scripts = _test_scripts(session, {r for sp in specs for r in sp.test_refs})
        for sp in specs:
            existing = find_requirement(session, sp.requirement_id)
            # resolve before any write is planned for this row
            sources = []
            for k in sp.set_by_keys:
                hit = resolve_key(session, k, keymap)
                if hit is None:
                    plan.unresolved.append(f"{sp.where} {sp.requirement_id}: set_by {k!r} names no single artifact")
                elif hit["id"] not in [x["id"] for x in sources]:
                    sources.append(hit)
            for k in sp.decision_keys:
                hit = resolve_key(session, k, keymap)
                if hit is None or hit["type"] not in ("Decision", "ArchitecturalDecision"):
                    plan.unresolved.append(f"{sp.where} {sp.requirement_id}: decision {k!r} names no projected "
                                           f"register record (run `seldon decision project`)")
                elif hit["id"] not in [x["id"] for x in sources]:
                    sources.append(hit)
            satisfiers = []
            for k in sp.satisfier_keys:
                hit = resolve_key(session, k, keymap)
                if hit and hit["type"] == "ResearchTask" and hit["id"] not in [x["id"] for x in satisfiers]:
                    satisfiers.append(hit)
            tests = []
            for ref in sp.test_refs:
                sid = scripts.get(ref) or new_tests.get(ref)
                if sid is None:
                    sid, creation = plan_artifact(
                        project_dir=project_dir, domain_config=domain_config, artifact_type="Script",
                        properties={"name": ref, "path": ref.split("::", 1)[0], "test_node": ref,
                                    "description": "A test node a requirement is verified by (SEL-033)."},
                        actor=ACTOR, authority="accepted")
                    plan.writes.append(creation)
                    new_tests[ref] = sid
                    plan.tests_created += 1
                if sid not in tests:
                    tests.append(sid)

            # the node
            if existing is None:
                rid, creation = plan_artifact(project_dir=project_dir, domain_config=domain_config,
                                              artifact_type=REQ_TYPE, properties=dict(sp.properties),
                                              actor=ACTOR, authority="accepted")
                plan.writes.append(creation)
                plan.created.append(sp.requirement_id)
                state = initial
                have = {"VERIFIED_BY": set(), "DERIVED_FROM": set(), "SATISFIES": set()}
                changed = True
            else:
                rid = existing["artifact_id"]
                state = existing.get("state") or initial
                have = _out_edges(session, rid)
                diff = {k: v for k, v in sp.properties.items() if existing.get(k) != v}
                changed = bool(diff)
                if diff:
                    plan.writes.append(plan_update_artifact(project_dir=project_dir, driver=driver,
                                                            database=database, artifact_id=rid, properties=diff,
                                                            actor=ACTOR, authority="accepted"))

            # the edges
            def link(rel: str, from_id: str, to_id: str, from_type: str, to_type: str) -> None:
                plan.writes.append(plan_link(driver=driver, database=database, domain_config=domain_config,
                                             from_id=from_id, to_id=to_id, from_type=from_type, to_type=to_type,
                                             rel_type=rel, actor=ACTOR, authority="accepted"))
                plan.links_added += 1

            for sid in tests:
                if sid not in have["VERIFIED_BY"]:
                    link(REL_VERIFIED_BY, rid, sid, REQ_TYPE, "Script")
                    changed = True
            for src in sources:
                if src["id"] not in have["DERIVED_FROM"]:
                    link(REL_DERIVED_FROM, rid, src["id"], REQ_TYPE, src["type"])
                    changed = True
            for sat in satisfiers:
                if sat["id"] not in have["SATISFIES"]:
                    link(REL_SATISFIES, sat["id"], rid, sat["type"], REQ_TYPE)
                    changed = True
            if prune:
                wanted = {"VERIFIED_BY": set(tests), "DERIVED_FROM": {x["id"] for x in sources},
                          "SATISFIES": {x["id"] for x in satisfiers}}
                for rel, ids in have.items():
                    for other in sorted(ids - wanted[rel]):
                        frm, to = (other, rid) if rel == "SATISFIES" else (rid, other)
                        plan.writes.append(_plan_unlink(frm, to, rel.lower()))
                        plan.links_removed += 1
                        changed = True

            # the state
            target = state
            if sp.status_text is not None:
                word = status_word(sp.status_text, s.status_map)
                if word is None:
                    if s.status_map:
                        plan.unresolved.append(f"{sp.where} {sp.requirement_id}: status {sp.status_text[:60]!r} "
                                               f"is not in requirements.status_map; state left {state}")
                elif s.status_map[word] not in machine:
                    raise RequirementsError(f"requirements.status_map[{word!r}] = {s.status_map[word]!r} is not a "
                                            f"{REQ_TYPE} state ({sorted(machine)})")
                else:
                    target = s.status_map[word]
            if target == "verified" and not tests:
                target = "implemented"
            if target != state:
                steps = state_path(machine, state, target)
                if steps is None:
                    plan.unresolved.append(f"{sp.where} {sp.requirement_id}: no path on the {REQ_TYPE} machine "
                                           f"from {state} to {target}; state left {state}")
                    target = state
                else:
                    cur = state
                    for nxt in steps:
                        plan.writes.append(plan_state_change(domain_config=domain_config, artifact_id=rid,
                                                             artifact_type=REQ_TYPE, current_state=cur,
                                                             new_state=nxt, actor=ACTOR, authority="accepted"))
                        cur = nxt
                    changed = True
            plan.states[target] += 1
            if existing is not None:
                (plan.updated if changed else plan.unchanged).append(sp.requirement_id)
    return plan


def _plan_unlink(from_id: str, to_id: str, rel: str) -> PlannedWrite:
    event = make_event(event_type="link_removed", actor=ACTOR, authority="accepted",
                       payload={"from_id": from_id, "to_id": to_id, "rel_type": rel})

    def project(session) -> None:
        graph.remove_link(session, from_id, to_id, rel.upper())

    return PlannedWrite(event=event, project=project)


def apply(project_dir: Path, driver, database: str, plan: Plan) -> None:
    """Write the plan: one append to the event log, then the graph (AD-001, SEL-007's all-or-nothing boundary)."""
    if plan.writes:
        commit_writes(project_dir, driver, database, plan.writes)


def import_file(project_dir: Path, driver, database: str, domain_config, config: dict, rel: str, *,
                document: Optional[str] = None, column_overrides: Optional[Dict[str, str]] = None,
                dry_run: bool = False) -> Tuple[Plan, Source]:
    """`seldon req import`: load a markdown requirements file into the graph (AD-013-R1, R2).

    Raises:
        RequirementsError: the file does not parse as a requirements source.
    """
    s = settings(config)
    columns = dict(s.columns)
    for f, name in (column_overrides or {}).items():
        if name:
            columns[f] = [name]
    src = read_source(project_dir, rel, columns)
    specs, unresolved = [], []
    for row in src.rows:
        sp, missing = spec_from_row(row, src, project_dir, s, document or rel)
        specs.append(sp)
        unresolved.extend(missing)
    plan = plan_specs(project_dir, driver, database, domain_config, specs, s, src.keys)
    plan.unresolved = unresolved + plan.unresolved
    if not dry_run:
        apply(project_dir, driver, database, plan)
    return plan, src


def add_one(project_dir: Path, driver, database: str, domain_config, config: dict, rid: str, *,
            statement: Optional[str], set_by: Optional[str], verified_by: List[str], validated_by: Optional[str],
            status: Optional[str], section: Optional[str], document: Optional[str],
            dry_run: bool = False) -> Plan:
    """`seldon req add`: create or update one requirement. Options not given keep the node's current values; a new
    requirement needs a statement.

    Raises:
        RequirementsError: a new id with no statement, or a test reference that names no file.
    """
    s = settings(config)
    with driver.session(database=database) as session:
        existing = find_requirement(session, rid)
    if existing is None and not (statement or "").strip():
        raise RequirementsError(f"{rid} is a new requirement; give its statement (--statement)")
    props = {"requirement_id": rid}
    if statement is not None:
        props["description"] = statement
    for prop, value in (("set_by", set_by), ("validated_by", validated_by), ("status_text", status),
                        ("section", section), ("document", document)):
        if value is not None:
            props[prop] = value
    if existing is not None:
        for prop in ("description", "set_by", "validated_by", "status_text", "section", "document",
                     "decision_text", "satisfied_by_text"):
            if prop not in props and existing.get(prop) is not None:
                props[prop] = existing[prop]
    refs: List[str] = []
    if verified_by:
        refs, missing = test_refs("; ".join(verified_by), project_dir)
        if missing or not refs:
            raise RequirementsError(f"--verified-by {missing or verified_by}: not a test file or node in the project")
        props["verified_by_text"] = "; ".join(refs)
    elif existing is not None:
        with driver.session(database=database) as session:
            rows = _rows(session, f"MATCH (r:Artifact:{REQ_TYPE} {{artifact_id: $id}})-[:VERIFIED_BY]->"
                                  "(t:Artifact:Script) RETURN t.test_node AS t", id=existing["artifact_id"])
        refs = [r["t"] for r in rows if r["t"]]
        if existing.get("verified_by_text") is not None:
            props["verified_by_text"] = existing["verified_by_text"]
    keys = set_by_keys(props.get("set_by", ""))
    word = status_word(props.get("status_text") or "", s.status_map)
    satisfiers = (_KEY_RE.findall((props.get("status_text") or "")[len(word):])
                  if word and s.status_map.get(word) in ("implemented", "verified") else [])
    sp = Spec(requirement_id=rid, properties=props, status_text=props.get("status_text"), test_refs=refs,
              set_by_keys=keys, satisfier_keys=satisfiers, decision_keys=decision_keys(props.get("decision_text", "")),
              where="req add")
    plan = plan_specs(project_dir, driver, database, domain_config, [sp], s, {})
    if not dry_run:
        apply(project_dir, driver, database, plan)
    return plan


# ─────────────────────────────────────────────────────────────── the projection


def load_requirements(driver, database: str) -> List[dict]:
    """Every requirement with its edges, for rendering: each a node dict plus `_tests` (test nodes), `_sources`
    (derived_from targets' labels) and `_satisfiers` (satisfies sources' labels)."""
    with driver.session(database=database) as session:
        rows = _rows(session,
                     f"MATCH (r:Artifact:{REQ_TYPE}) "
                     "OPTIONAL MATCH (r)-[:VERIFIED_BY]->(t:Artifact) "
                     "WITH r, collect(DISTINCT coalesce(t.test_node, t.path, t.name)) AS tests "
                     "OPTIONAL MATCH (r)-[:DERIVED_FROM]->(d:Artifact) "
                     "WITH r, tests, collect(DISTINCT coalesce(d.requirement_id, d.decision_id, d.name, d.path)) AS srcs "
                     "OPTIONAL MATCH (s:Artifact)-[:SATISFIES]->(r) "
                     "RETURN r, tests, srcs, collect(DISTINCT coalesce(s.name, s.path)) AS sats")
    out = []
    for row in rows:
        node = dict(row["r"])
        node["_tests"] = [t for t in row["tests"] if t]
        node["_sources"] = sorted(x for x in row["srcs"] if x)
        node["_satisfiers"] = sorted(x for x in row["sats"] if x)
        out.append(node)
    out.sort(key=lambda n: natural_key(str(n.get("requirement_id", ""))))
    return out


def _ordered_tests(node: dict) -> List[str]:
    """The test nodes in the order the verbatim cell lists them, then any other edge, sorted (the graph is the truth
    of which tests; the cell keeps the source's order)."""
    tests = list(node.get("_tests") or [])
    text = node.get("verified_by_text") or ""
    order = {t: text.find(t) for t in tests if t in text}
    return sorted([t for t in tests if t in order], key=lambda t: order[t]) + sorted(t for t in tests if t not in order)


def _cell(value: Any) -> str:
    text = " ".join(str(value).split())
    return re.sub(r"(?<!\\)\|", r"\\|", text)


def cell_value(node: dict, source: str, s: Settings) -> str:
    if source == "@verified_by":
        tests = _ordered_tests(node)
        return "; ".join(tests) if tests else s.none_text
    if source == "@derived_from":
        return "; ".join(node.get("_sources") or []) or s.empty_text
    if source == "@satisfied_by":
        return "; ".join(node.get("_satisfiers") or []) or s.empty_text
    if source == "@state":
        return str(node.get("state") or "")
    if source == "@status":
        return str(node.get("status_text") or node.get("state") or "")
    v = node.get(source)
    if v is None or not str(v).strip():
        return s.empty_text
    return str(v)


def render_table(nodes: List[dict], columns: List[Dict[str, str]], s: Settings) -> str:
    heads = [c["header"] for c in columns]
    lines = ["| " + " | ".join(heads) + " |", "|" + "|".join("---" for _ in heads) + "|"]
    for n in nodes:
        lines.append("| " + " | ".join(_cell(cell_value(n, c["source"], s)) for c in columns) + " |")
    return "\n".join(lines)


def render_counts(nodes: List[dict], template: str, s: Settings) -> str:
    """The counts sentence: `{total}`, `{unverified}` (no `verified_by` edge), `{status:<word>}` (status_text starting
    with a status-map key), `{state:<state>}`, `{prefix:<text>}` (statements starting with the text) and
    `{status_counts}` (each status word, in the map's order, `N word`)."""
    words = Counter(status_word(n.get("status_text") or "", s.status_map) for n in nodes)

    def value(m: re.Match) -> str:
        key = m.group(1)
        if key == "total":
            return str(len(nodes))
        if key == "unverified":
            return str(sum(1 for n in nodes if not n.get("_tests")))
        if key == "status_counts":
            parts = [f"{words[w]} {w}" for w in s.status_map if words[w]]
            if not parts:
                parts = [f"{c} {st}" for st, c in sorted(Counter(n.get("state") for n in nodes).items())]
            return ", ".join(parts)
        kind, arg = key.split(":", 1)
        if kind == "status":
            return str(words[arg] if arg in s.status_map else
                       sum(1 for n in nodes if (n.get("status_text") or "").lower().startswith(arg.lower())))
        if kind == "state":
            return str(sum(1 for n in nodes if n.get("state") == arg))
        return str(sum(1 for n in nodes if str(n.get("description") or "").startswith(arg)))

    return _PLACEHOLDER_RE.sub(value, template)


def _attrs(text: str) -> Dict[str, str]:
    return {m.group(1): (m.group(2).replace('\\"', '"') if m.group(2) is not None else m.group(3))
            for m in _ATTR_RE.finditer(text)}


def _quote(v: str) -> str:
    return '"' + v.replace('"', '\\"') + '"'


def start_marker(attrs: Dict[str, str]) -> str:
    return "<!-- seldon:projection " + " ".join(f"{k}={_quote(v)}" for k, v in attrs.items()) + " -->"


def block_columns(rel: str, section: Optional[str], headers: Optional[str],
                  columns: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """The columns a table block renders: the projection's columns, or, when the block's start marker names
    `headers="A|B|C"` (written by `req import --mark` from the source table), those labels in that order, each
    mapped to the projection column of the same header (case-insensitive). One file's tables may differ in
    columns (hazbrief-mcp's RTM: a `Decision` column on the design-note tables only, HB-144).

    Raises:
        RequirementsError: a label the projection declares no column for.
    """
    if not headers:
        return columns
    by_label = {c["header"].strip().lower(): c for c in columns}
    out = []
    for label in headers.split("|"):
        col = by_label.get(label.strip().lower())
        if col is None:
            raise RequirementsError(f"{rel}: block {section!r} has a column {label!r} the projection declares no "
                                    f"source for; add `{{header: {label}, source: <property or @computed>}}` to its "
                                    f"docs.projections columns")
        out.append({"header": label, "source": col["source"]})
    return out


@dataclass
class Rendered:
    path: str
    kind: str
    text: str                # the file as it would be rendered
    current: Optional[str]   # the file on disk, None when absent
    revision: str
    unplaced: List[str]      # requirements of this document that no table block shows

    @property
    def changed(self) -> bool:
        return self.text != self.current


def _replace_blocks(text: str, render_block) -> str:
    """Replace each marker block's body with `render_block(attrs)`, keeping the markers and the text around them.
    A block is inline when its start marker is followed by text on the same line, and a table block otherwise."""
    out, pos = [], 0
    for m in START_RE.finditer(text):
        if m.start() < pos:
            continue
        end = END_RE.search(text, m.end())
        if end is None:
            line = text.count("\n", 0, m.start()) + 1
            raise RequirementsError(f"line {line}: a seldon:projection start marker with no end marker "
                                    f"({END_MARK})")
        attrs = _attrs(m.group("attrs"))
        body = render_block(attrs)
        inline = not text[m.end():end.start()].startswith("\n")
        out.append(text[pos:m.end()])
        out.append(body if inline else "\n" + body + "\n")
        pos = end.start()
    out.append(text[pos:])
    return "".join(out)


def render_projection(project_dir: Path, proj: Dict[str, Any], nodes: List[dict], s: Settings) -> Rendered:
    """Render one declared projection (AD-013-R2).

    A file with marker blocks keeps everything outside them; a table block shows the requirements of its `document`
    (default: this file) under its `section`, a counts block (`view="counts"`) the counts sentence of its `document`.
    Requirements of this file that no table block shows are appended as new blocks, one per section. A file with no
    blocks, or no file, is rendered whole: a title and one block per section.
    """
    rel = proj["path"]
    path = Path(project_dir) / rel
    current = path.read_text(encoding="utf-8") if path.is_file() else None
    columns = proj["columns"]
    by_doc: Dict[str, List[dict]] = {}
    for n in nodes:
        by_doc.setdefault(str(n.get("document") or ""), []).append(n)
    mine = by_doc.get(rel, [])
    shown: set = set()
    bodies: List[str] = []

    def block(attrs: Dict[str, str]) -> str:
        doc = attrs.get("document", rel)
        pool = by_doc.get(doc, [])
        if attrs.get("view") == "counts":
            body = render_counts(pool, proj.get("counts_template") or s.counts_template, s)
        else:
            section = attrs.get("section")
            rows = [n for n in pool if (n.get("section") or None) == (section or None)]
            if doc == rel:
                shown.update(n["requirement_id"] for n in rows)
            body = render_table(rows, block_columns(rel, section, attrs.get("headers"), columns), s)
        bodies.append(body)
        return body

    if current is not None and not START_RE.search(current):
        # A hand file with no markers is never overwritten: its prose is not the graph's to replace.
        raise RequirementsError(f"{rel} exists and has no seldon:projection markers; run `seldon req import --mark "
                                f"{rel}` to wrap its tables, or move it aside so the projection is rendered whole")
    base = current
    if base is None:
        title = "# Requirements" if proj["kind"] == "requirements" else "# Requirements traceability matrix"
        base = title + "\n"
    else:
        base = "\n".join(l for l in base.split("\n") if not HEADER_RE.match(l)).lstrip("\n")
    text = _replace_blocks(base, block)
    sections: List[Optional[str]] = []
    for n in mine:
        if n["requirement_id"] not in shown and n.get("section") not in sections:
            sections.append(n.get("section"))
    unplaced = [n["requirement_id"] for n in mine if n["requirement_id"] not in shown]
    for sec in sections:
        attrs = {"view": "table"}
        if sec:
            attrs["section"] = sec
        rows = [n for n in mine if n.get("section") == sec]
        body = render_table(rows, columns, s)
        bodies.append(body)
        text = text.rstrip("\n") + "\n\n" + (f"## {sec}\n\n" if sec else "") + start_marker(attrs) + "\n" + body \
            + "\n" + END_MARK + "\n"
    revision = hashlib.sha256("\n\x00\n".join(bodies).encode("utf-8")).hexdigest()[:16]
    header = (f"<!-- seldon:projection-revision {revision} (the tables and counts between seldon:projection markers "
              f"are rendered from the graph by `seldon docs generate {proj['kind']}`; change a requirement with "
              f"`seldon req`, not here; AD-013-R2) -->")
    return Rendered(path=rel, kind=proj["kind"], text=header + "\n" + text, current=current, revision=revision,
                    unplaced=unplaced if current is not None else [])


def render_all(project_dir: Path, driver, database: str, config: dict, kind: Optional[str] = None) -> List[Rendered]:
    """Render every declared projection (of `kind`, when given).

    Raises:
        RequirementsError: no projection declared, or a malformed block.
    """
    s = settings(config)
    projs = [p for p in s.projections if kind is None or p["kind"] == kind]
    if not projs:
        raise RequirementsError(f"seldon.yaml declares no `docs.projections` entry"
                                f"{' of kind ' + kind if kind else ''}; declare one with its path, e.g. "
                                f"`docs: {{projections: [{{path: docs/REQUIREMENTS.md, kind: {kind or 'requirements'}}}]}}`")
    nodes = load_requirements(driver, database)
    return [render_projection(project_dir, p, nodes, s) for p in projs]


def write_and_commit(project_dir: Path, rendered: List[Rendered], commit: bool = True) -> dict:
    """Write the changed projections, then commit exactly those paths through the hooks (AD-038-R15: a command
    commits what it writes)."""
    from seldon.core.dispatch import commit_paths

    changed = [r for r in rendered if r.changed]
    for r in changed:
        p = Path(project_dir) / r.path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(r.text, encoding="utf-8")
    if not changed or not commit:
        return {"written": [r.path for r in changed], "committed": False,
                "reason": "nothing_to_commit" if not changed else "no_commit"}
    kinds = sorted({r.kind for r in changed})
    revs = ", ".join(f"{r.path} {r.revision}" for r in changed)
    msg = (f"docs: render {' and '.join(kinds)} projection(s) from the graph (AD-013-R2)\n\n"
           f"seldon docs generate {' '.join(kinds)}; graph revision per file: {revs}")
    out = commit_paths(Path(project_dir), [r.path for r in changed], msg)
    out["written"] = [r.path for r in changed]
    return out


def mark_source(project_dir: Path, src: Source) -> bool:
    """`seldon req import --mark`: wrap each requirements table of the source in projection markers, once.

    The start marker carries the table's section and its own header labels, so the first render reproduces the
    table's wording. A table already inside markers is left. Returns whether the file changed.
    """
    path = Path(project_dir) / src.path
    lines = path.read_text(encoding="utf-8").split("\n")
    inside = set()
    depth = False
    for i, l in enumerate(lines):
        if START_RE.search(l):
            depth = True
        if depth:
            inside.add(i + 1)
        if END_RE.search(l):
            depth = False
    changed = False
    for ti in sorted(src.req_tables, key=lambda t: -src.tables[t].header_line):
        t = src.tables[ti]
        if t.header_line in inside:
            continue
        attrs = {"view": "table"}
        if t.heading:
            attrs["section"] = t.heading
        attrs["headers"] = "|".join(t.header)
        lines.insert(t.last_line, END_MARK)
        lines.insert(t.header_line - 1, start_marker(attrs))
        changed = True
    if changed:
        path.write_text("\n".join(lines), encoding="utf-8")
    return changed


# ─────────────────────────────────────────────────────────────── the checks (AD-013-R3)


def unverified(driver, database: str) -> List[dict]:
    """Requirements with no `verified_by` edge, rejected ones excepted (a withdrawn requirement binds nothing)."""
    with driver.session(database=database) as session:
        return _rows(session,
                     f"MATCH (r:Artifact:{REQ_TYPE}) WHERE NOT (r)-[:VERIFIED_BY]->(:Artifact) "
                     "AND coalesce(r.state, '') <> 'rejected' "
                     "RETURN r.requirement_id AS id, r.state AS state, r.document AS document "
                     "ORDER BY r.requirement_id")


def count(driver, database: str) -> int:
    with driver.session(database=database) as session:
        return _rows(session, f"MATCH (r:Artifact:{REQ_TYPE}) RETURN count(r) AS n")[0]["n"]


def stale_projections(project_dir: Path, driver, database: str, config: dict) -> List[str]:
    """One finding per declared projection whose file is missing or differs from a fresh render, and per requirement
    of a marked file that no block shows."""
    s = settings(config)
    if not s.projections:
        return []
    nodes = load_requirements(driver, database)
    out = []
    for p in s.projections:
        try:
            r = render_projection(project_dir, p, nodes, s)
        except RequirementsError as exc:
            out.append(f"{p['path']}: {exc}")
            continue
        if r.current is None:
            out.append(f"{r.path}: not rendered; run `seldon docs generate {r.kind}`")
        elif r.changed:
            m = HEADER_RE.match(r.current.split("\n", 1)[0])
            why = ("the graph moved since revision " + m.group("rev")) if m and m.group("rev") != r.revision \
                else "the file was edited outside the graph"
            out.append(f"{r.path}: differs from a fresh render ({why}); run `seldon docs generate {r.kind}`")
        if r.unplaced:
            out.append(f"{r.path}: {len(r.unplaced)} requirement(s) of this document in no block "
                       f"(first: {', '.join(r.unplaced[:5])}); `seldon docs generate {r.kind}` appends them")
    return out
