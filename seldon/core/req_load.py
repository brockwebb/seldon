"""The onboarding load: an UNMARKED markdown requirements table into the graph (`seldon req import`, SEL-033, SEL-035).

Split from `seldon/core/requirements.py` by SEL-035: that module is the requirement record, the projection and the
checks; this one reads markdown. A table whose header names an id column and a statement column is a requirements
table; a `Key | File` table is the key map for `Set by`. Per row: the node and its authored fields (AD-013-R1);
`derived_from` its `Set by` and `Decision` keys; `verified_by` the test Scripts its verification cell names (SEL-021's
node-id grammar and two shorter forms, the only text grammar for tests there is, AD-013-R5); `satisfies` from the
tasks its status names; the state its status word maps to; and every other cell placed by :func:`place_cells`
(an edge carries it: dropped; a method: `verification_method`; anything else: the note, listed, never dropped;
Gotel and Finkelstein 1994). A marked file is output, not a source, and is refused (AD-013-R2).
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from seldon.core.artifacts import plan_artifact, plan_update_artifact
from seldon.core.requirements import (ACTOR, END_MARK, END_RE, REL_DERIVED_FROM, REL_SATISFIES, REL_VERIFIED_BY,
                                      REQ_TYPE, START_RE, Plan, RequirementsError, Settings, _link, _out_edges,
                                      _plan_unlink, _rows, apply, find_requirement, plan_test_script, plan_walk,
                                      settings, start_marker, status_word, test_scripts)


#: Cells that say "nothing here" in a load source, besides the none text: no fact to place.
EMPTY_CELLS = ("", "—", "-", "none", "none yet", "n/a")


_TEST_NODE_RE = re.compile(r"(?P<path>[\w./-]+\.py)::(?P<node>[\w\[\]./-]+)")


_PY_PATH_RE = re.compile(r"^[\w./-]+\.py$")


_TEST_NAME_RE = re.compile(r"^test_\w+$")


_TOKEN_RE = re.compile(r"`[^`]+`|[^\s;,`()]+")


_KEY_RE = re.compile(r"\b[A-Z][A-Z0-9]*-\d+[A-Za-z0-9]*(?:-[A-Z]\d+)?\b")


#: A verification or validation cell that names a method other than test (a judgment is an inspection, INCOSE).
_METHOD_WORDS = (("inspection", re.compile(r"\binspect", re.I)), ("analysis", re.compile(r"\banaly[sz]", re.I)),
                 ("demonstration", re.compile(r"\bdemonstrat", re.I)), ("inspection", re.compile(r"\bjudg", re.I)))


#: What separates a status word from the rest of its cell (`satisfied: HB-131R`, `met. Each rule ...`).
_SEP = " \t:;,.—–-"


def split_row(line: str) -> List[str]:
    """The cells of a GFM pipe-table row, split on unescaped pipes, each stripped; escapes are kept verbatim."""
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
    return next((idx for idx, h in enumerate(header) if h.strip().lower() in wanted), None)


@dataclass
class Row:
    """One requirement row of a load source."""

    requirement_id: str
    fields: Dict[str, str]              # field name -> cell (statement, set_by, ...)
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
        if [h.lower() for h in t.header] == ["key", "file"]:
            keys.update({c[0].strip("`"): c[1].strip("`") for _, c in t.rows if len(c) == 2})
            continue
        id_col = _column_index(t.header, columns["id"])
        st_col = _column_index(t.header, columns["statement"])
        if id_col is None or st_col is None:
            continue
        req_tables.append(ti)
        idx = {f: _column_index(t.header, names) for f, names in columns.items() if f != "id"}
        for line, cells in t.rows:
            if len(cells) != len(t.header):
                raise RequirementsError(f"{rel}:{line}: {len(cells)} cells under a {len(t.header)}-column header")
            rid = cells[id_col].strip()
            if not rid:
                raise RequirementsError(f"{rel}:{line}: a row with no id")
            rows.append(Row(requirement_id=rid, fields={f: cells[i] for f, i in idx.items() if i is not None},
                            section=t.heading, line=line, table=ti))
    if not rows:
        raise RequirementsError(f"{rel} holds no requirements table (a header naming {columns['id']} and "
                                f"{columns['statement']})")
    dup = [k for k, n in Counter(r.requirement_id for r in rows).items() if n > 1]
    if dup:
        raise RequirementsError(f"{rel}: id(s) repeated: {dup}")
    return Source(path=rel, tables=tables, req_tables=req_tables, rows=rows, keys=keys)


def test_refs(cell: str, project_dir: Path) -> Tuple[List[str], List[str]]:
    """The pytest node ids a verification cell names, in order, and the references that name no file.

    Three forms (SEL-033, the onboarding load only; AD-013-R5 adds no grammar): `path::node`; a test file followed
    by test names (`tests/x.py` `test_a`, `test_b`); a test file alone, itself a pytest node id. Anything else (a
    harness, "inspection") is not a test: :func:`place_cells` keeps it in the note.
    """
    refs: List[str] = []
    missing: List[str] = []
    for ref in named_refs(cell):
        path = ref.split("::", 1)[0]
        ok = (Path(project_dir) / path).is_file() and ".." not in Path(path).parts and not Path(path).is_absolute()
        (refs if ok else missing).append(ref)
    return refs, missing


def named_refs(cell: str) -> List[str]:
    """Every pytest node id a verification cell names, in order, whether or not its file exists."""
    return _scan_refs(cell)[0]


def _only_test_refs(cell: str) -> bool:
    """Whether the cell names at least one test and every token of it is part of a test reference (no harness, no
    prose, and no bare test name with no file before it: SEL-035 Part F, hazbrief's E-D2 to E-D6)."""
    refs, leftover = _scan_refs(cell)
    return bool(refs) and not leftover


def _scan_refs(cell: str) -> Tuple[List[str], List[str]]:
    """The node ids a cell names (three forms, see :func:`test_refs`) and the tokens no reference consumed."""
    out: List[str] = []
    leftover: List[str] = []

    def add(ref: str) -> None:
        if ref not in out:
            out.append(ref)

    current_file, file_used = None, True
    for raw in _TOKEN_RE.findall(cell or ""):
        tok = raw.strip("`").strip()
        m = _TEST_NODE_RE.fullmatch(tok)
        if m or (_PY_PATH_RE.match(tok) and "test" in Path(tok).name):
            if current_file and not file_used:
                add(current_file)
            current_file, file_used = (None, True) if m else (tok, False)
            if m:
                add(tok)
        elif current_file and _TEST_NAME_RE.match(tok):
            add(f"{current_file}::{tok}")
            file_used = True
        else:
            leftover.append(tok)
    if current_file and not file_used:
        add(current_file)
    return out, leftover


def set_by_keys(cell: str) -> List[str]:
    """The key of each `;`-separated part of a `Set by` cell: its first word (`DN-019 §3 row 2` -> `DN-019`)."""
    out = []
    for part in (cell or "").split(";"):
        part = part.strip().strip("`")
        if part and part not in ("—", "-"):
            out.append(part.split()[0].rstrip(",.:"))
    return out


def decision_keys(cell: str) -> List[str]:
    """The record ids a `Decision` cell lists (`HBD-001, HBD-006`; a `—` or blank lists none)."""
    return [k.strip("` ") for k in re.split(r"[;,]", cell or "") if k.strip("` ") not in ("", "—", "-")]


def method_named(text: str) -> Optional[str]:
    """The verification method other than test a cell names (`inspection`, `judged, not tested`), or None."""
    return next((m for m, rx in _METHOD_WORDS if rx.search(text or "")), None)


def _empty(cell: Optional[str], none_text: str) -> bool:
    return (cell or "").strip().lower() in EMPTY_CELLS + (none_text.lower(),)


@dataclass
class Carried:
    """What the graph carries for one requirement, so a cell that says only this is dropped, not kept."""

    tests: set = field(default_factory=set)        # test node ids of its verified_by Scripts
    satisfiers: set = field(default_factory=set)   # the keys (`HB-131R`) of its satisfies sources
    decisions: set = field(default_factory=set)    # the short ids (`HBD-012`) of its derived_from records


def place_cells(cells: Dict[str, str], state: str, label: str, status_map: Dict[str, str], none_text: str,
                carried: Carried) -> Tuple[Optional[str], Optional[str], List[str]]:
    """Where each non-authored cell of a load row goes (AD-013 ADDENDUM 02 section 4.1): `(note, method, listed)`.

    - status: its word is dropped when it is the state's label and the rest becomes the note; a word that maps to the
      state but is not its label stays at the head of the note (AD-013-R4's qualifier); a word that maps to another
      state, or none, keeps the whole cell in the note and is listed;
    - verified by / validated by: the none text, or (verified by) a cell of test references the edges carry, is
      dropped; any other cell is kept whole in the note under its column's name, and one naming inspection,
      analysis, demonstration or a judgment sets the method;
    - satisfied by / decision: dropped when the edges carry every key, else kept under the column's name and listed.

    Nothing an edge does not carry is dropped.
    """
    parts: List[str] = []
    listed: List[str] = []
    method = None
    st = (cells.get("status") or "").strip()
    if st:
        word = status_word(st, status_map)
        if word is not None and status_map[word] == state:
            # the label is implied by the state and dropped; a finer word (a qualifier) stays at the head
            rest = st[len(word):].lstrip(_SEP) if word.lower() == label.lower() else st
            if rest:
                parts.append(rest)
        else:
            parts.append(st)
            listed.append(f"status {st[:50]!r} maps to {status_map[word] if word else 'no state'}, the state is "
                          f"{state}: kept in the note")
    for f, name in (("verified_by", "verified by"), ("validated_by", "validated by")):
        text = (cells.get(f) or "").strip()
        if _empty(text, none_text):
            continue
        if f == "verified_by" and _only_test_refs(text) and set(named_refs(text)) <= carried.tests:
            continue
        m = method_named(text)
        if m:
            method = method or m
        else:
            listed.append(f"{name} {text[:50]!r}: no edge carries it; kept in the note")
        parts.append(f"{name}: {text}")
    for f, name, have in (("satisfied_by", "satisfied by", carried.satisfiers),
                          ("decision", "decision", carried.decisions)):
        text = (cells.get(f) or "").strip()
        if _empty(text, none_text):
            continue
        keys = decision_keys(text) if f == "decision" else _KEY_RE.findall(text)
        residue = re.sub(r"[\s,;`]", "", re.sub("|".join(map(re.escape, keys)), "", text)) if keys else text
        if keys and set(keys) <= have and not residue:
            continue
        parts.append(f"{name}: {text}")
        listed.append(f"{name} {text[:50]!r}: no edge carries it; kept in the note")
    return ("; ".join(parts) or None), method, listed


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


def plan_rows(project_dir: Path, driver, database: str, domain_config, src: Source, s: Settings,
              document: str) -> Plan:
    """Plan every write that brings the graph to an unmarked source's rows, idempotent on the requirement id.

    Per row: the node and its authored fields; `derived_from` its `Set by` and `Decision` keys; `verified_by` the test
    Scripts its verification cell names; `satisfies` from the tasks its status names; the state the status maps to
    (held at `implemented` with no test, AD-013-R1); the rest of its cells placed by :func:`place_cells`. A re-import
    prunes test, source and satisfier edges the row no longer names, so the graph mirrors the load.
    """
    plan = Plan()
    initial = domain_config.get_initial_state(REQ_TYPE)
    labels = s.labels(document)
    proj = s.projection_for(document) or {}
    none_text = proj.get("none_text") or s.none_text
    new_tests: Dict[str, str] = {}
    with driver.session(database=database) as session:
        refs_by_row = {r.requirement_id: test_refs(r.fields.get("verified_by", ""), project_dir) for r in src.rows}
        scripts = test_scripts(session, {x for refs, _ in refs_by_row.values() for x in refs})
        for row in src.rows:
            f, rid_text, where = row.fields, row.requirement_id, f"{src.path}:{row.line}"
            refs, missing = refs_by_row[rid_text]
            plan.unresolved += [f"{where} {rid_text}: verified_by {m!r} names no file in the project" for m in missing]
            sources, satisfiers, decisions = [], [], set()
            for k in set_by_keys(f.get("set_by", "")):
                hit = resolve_key(session, k, src.keys)
                if hit is None:
                    plan.unresolved.append(f"{where} {rid_text}: set_by {k!r} names no single artifact")
                elif hit not in sources:
                    sources.append(hit)
            for k in decision_keys(f.get("decision", "")):
                hit = resolve_key(session, k, src.keys)
                if hit is None or hit["type"] not in ("Decision", "ArchitecturalDecision"):
                    plan.unresolved.append(f"{where} {rid_text}: decision {k!r} names no projected register record "
                                           f"(run `seldon decision project`)")
                    continue
                decisions.add(k)
                if hit not in sources:
                    sources.append(hit)
            word = status_word(f.get("status", ""), s.status_map)
            target = s.status_map.get(word) if word else None
            sat_keys = []
            if target in ("implemented", "verified"):
                for k in _KEY_RE.findall(f.get("status", "")[len(word):]):
                    hit = resolve_key(session, k, src.keys)
                    if hit and hit["type"] == "ResearchTask" and hit not in satisfiers:
                        satisfiers.append(hit)
                        sat_keys.append(k)
            tests = []
            for ref in refs:
                sid = scripts.get(ref) or new_tests.get(ref)
                if sid is None:
                    sid, creation = plan_test_script(project_dir, domain_config, ref)
                    plan.writes.append(creation)
                    new_tests[ref] = sid
                    plan.tests_created += 1
                if sid not in tests:
                    tests.append(sid)

            existing = find_requirement(session, rid_text)
            state = (existing or {}).get("state") or initial
            if target is not None and target not in domain_config.state_machines.get(REQ_TYPE, {}):
                raise RequirementsError(f"requirements.status_map[{word!r}] = {target!r} is not a {REQ_TYPE} state")
            goal = target or state
            if goal == "verified" and not tests:
                goal = "implemented"
            note, method, listed = place_cells(f, goal, labels.get(goal, goal), s.status_map, none_text,
                                               Carried(tests=set(refs), satisfiers=set(sat_keys), decisions=decisions))
            plan.unresolved += [f"{where} {rid_text}: {x}" for x in listed]
            props = {"requirement_id": rid_text, "document": document, "description": f.get("statement", "")}
            for k, v in (("section", row.section), ("set_by", f.get("set_by")), ("note", note),
                         ("verification_method", method)):
                if v:
                    props[k] = v

            if existing is None:
                aid, creation = plan_artifact(project_dir=project_dir, domain_config=domain_config,
                                              artifact_type=REQ_TYPE, properties=props, actor=ACTOR,
                                              authority="accepted")
                plan.writes.append(creation)
                plan.created.append(rid_text)
                have = {"VERIFIED_BY": set(), "DERIVED_FROM": set(), "SATISFIES": set(), "KEPT": set()}
                changed = True
            else:
                aid = existing["artifact_id"]
                have = _out_edges(session, aid)
                diff = {k: v for k, v in props.items() if existing.get(k) != v}
                changed = bool(diff)
                if diff:
                    plan.writes.append(plan_update_artifact(project_dir=project_dir, driver=driver, database=database,
                                                            artifact_id=aid, properties=diff, actor=ACTOR,
                                                            authority="accepted"))
            me = (aid, REQ_TYPE)
            for sid in tests:
                if sid not in have["VERIFIED_BY"]:
                    _link(plan, driver, database, domain_config, REL_VERIFIED_BY, me, (sid, "Script"))
                    changed = True
            for x in sources:
                if x["id"] not in have["DERIVED_FROM"]:
                    _link(plan, driver, database, domain_config, REL_DERIVED_FROM, me, (x["id"], x["type"]))
                    changed = True
            for x in satisfiers:
                if x["id"] not in have["SATISFIES"]:
                    _link(plan, driver, database, domain_config, REL_SATISFIES, (x["id"], x["type"]), me)
                    changed = True
            wanted = {"VERIFIED_BY": set(tests) | have["KEPT"], "DERIVED_FROM": {x["id"] for x in sources},
                      "SATISFIES": {x["id"] for x in satisfiers}}
            for rel, ids in have.items():
                if rel == "KEPT":
                    continue
                for other in sorted(ids - wanted[rel]):
                    plan.writes.append(_plan_unlink(*((other, aid) if rel == "SATISFIES" else (aid, other)),
                                                    rel.lower()))
                    plan.links_removed += 1
                    changed = True
            if goal != state:
                walk = plan_walk(domain_config, aid, state, goal)
                if walk is None:
                    plan.unresolved.append(f"{where} {rid_text}: no path on the {REQ_TYPE} machine from {state} to "
                                           f"{goal}; state left {state}")
                    goal = state
                else:
                    plan.writes += walk
                    changed = True
            plan.states[goal] += 1
            if existing is not None:
                (plan.updated if changed else plan.unchanged).append(rid_text)
    return plan


def import_file(project_dir: Path, driver, database: str, domain_config, config: dict, rel: str, *,
                document: Optional[str] = None, column_overrides: Optional[Dict[str, str]] = None,
                dry_run: bool = False) -> Tuple[Plan, Source]:
    """`seldon req import`: load an UNMARKED markdown requirements file into the graph (AD-013-R1; onboarding only).

    Raises:
        RequirementsError: the file carries projection markers (it is output, AD-013-R2), or does not parse as a
            requirements source.
    """
    s = settings(config)
    path = Path(project_dir) / rel
    if path.is_file() and START_RE.search(path.read_text(encoding="utf-8")):
        raise RequirementsError(f"{rel} carries seldon:projection markers: its tables are output rendered from the "
                                f"graph, not a source (AD-013-R2). Change a requirement with `seldon req update <id>` "
                                f"(or `seldon req add <id>` for a new one), then `seldon docs generate`")
    columns = dict(s.columns)
    for f, name in (column_overrides or {}).items():
        if name:
            columns[f] = [name]
    src = read_source(project_dir, rel, columns)
    plan = plan_rows(project_dir, driver, database, domain_config, src, s, document or rel)
    if not dry_run:
        apply(project_dir, driver, database, plan)
    return plan, src


def mark_source(project_dir: Path, src: Source) -> bool:
    """`seldon req import --mark`: wrap each requirements table of the source in projection markers, once.

    The start marker carries the table's section and its own header labels, so the first render keeps the table's
    columns. A table already inside markers is left. Returns whether the file changed.
    """
    path = Path(project_dir) / src.path
    lines = path.read_text(encoding="utf-8").split("\n")
    inside, depth = set(), False
    for i, l in enumerate(lines):
        depth = depth or bool(START_RE.search(l))
        if depth:
            inside.add(i + 1)
        if END_RE.search(l):
            depth = False
    changed = False
    for ti in sorted(src.req_tables, key=lambda t: -src.tables[t].header_line):
        t = src.tables[ti]
        if t.header_line in inside:
            continue
        attrs = {"view": "table", **({"section": t.heading} if t.heading else {}), "headers": "|".join(t.header)}
        lines.insert(t.last_line, END_MARK)
        lines.insert(t.header_line - 1, start_marker(attrs))
        changed = True
    if changed:
        path.write_text("\n".join(lines), encoding="utf-8")
    return changed
