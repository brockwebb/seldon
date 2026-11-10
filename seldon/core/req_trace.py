"""`seldon req trace`: a test declares what it verifies, and the trace keeps the graph's edges to match (AD-013-R5).

A test function or class carries `@pytest.mark.verifies("VR-012", "VR-013")`. This module reads the project's test
files with the standard library's `ast` (no import, no collection: a file that does not import still traces, and
nothing in it runs), binds each marker to its pytest node id the way StrictDoc binds a marker to its function, and
plans the `verified_by` edges from each named requirement to the SEL-021 test `Script` of that node, marked
`declared_by: marker`. OpenFastTrace's rule is the model: the covering artifact declares the link, and the tracer
computes coverage; nobody types a test name into the requirement.

The plan (each run brings the graph to the markers, so a second run writes nothing):
- a marker edge is added where missing;
- a marker edge whose marker is gone is removed;
- a requirement a marker names has its imported test edges (SEL-033's, no `declared_by`) removed: the marker
  replaces them. A requirement no marker names keeps them;
- a marker naming no requirement, a marker argument that is not a string, and a file that does not parse are listed.

Evidence edges to a Result or Issue (AD-013-R6) are not test edges and are never touched. No state moves here: a
`verified` requirement left with no verifying edge is reported by `seldon verify` (AD-013-R1's invariant).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

from seldon.core import requirements as RQ

MARKER = "verifies"
DECLARED_BY = "marker"
#: The pytest marker line a project registers (`seldon project new` writes it; AD-013 ADDENDUM 02 section 4.3).
MARKER_LINE = "verifies(*ids): the requirements this test verifies (AD-013-R5)"
#: pytest's default test-file patterns (`python_files`).
FILE_GLOBS = ("test_*.py", "*_test.py")


@dataclass
class Scan:
    markers: Dict[str, List[str]] = field(default_factory=dict)   # node id -> requirement ids, in order
    unparsable: List[str] = field(default_factory=list)            # `<path>: <error>`
    malformed: List[str] = field(default_factory=list)             # `<node id>: <what>`
    files: int = 0


def _is_verifies(dec: ast.expr) -> bool:
    """`@pytest.mark.verifies(...)` or `@mark.verifies(...)`: a call whose function is `<...>mark.verifies`."""
    if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute) or dec.func.attr != MARKER:
        return False
    base = dec.func.value
    return (isinstance(base, ast.Attribute) and base.attr == "mark") or (isinstance(base, ast.Name) and base.id == "mark")


def _ids(dec: ast.Call, node_id: str, scan: Scan) -> List[str]:
    out = []
    for a in dec.args:
        if isinstance(a, ast.Constant) and isinstance(a.value, str) and a.value.strip():
            out.append(a.value.strip())
        else:
            scan.malformed.append(f"{node_id}: a verifies argument that is not a string literal "
                                  f"({ast.unparse(a)[:60]}); only literals are read (AD-013-R5)")
    return out


def _walk(body: List[ast.stmt], prefix: str, scan: Scan) -> None:
    for node in body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        node_id = f"{prefix}::{node.name}"
        ids: List[str] = []
        for dec in node.decorator_list:
            if _is_verifies(dec):
                ids += [i for i in _ids(dec, node_id, scan) if i not in ids]
        if ids:
            scan.markers.setdefault(node_id, [])
            scan.markers[node_id] += [i for i in ids if i not in scan.markers[node_id]]
        if isinstance(node, ast.ClassDef):
            _walk(node.body, node_id, scan)


def scan(project_dir: Path, test_paths: List[str]) -> Scan:
    """Every `verifies` marker under `test_paths`, by pytest node id (`path::func`, `path::Class`,
    `path::Class::method`; a parametrized test binds its function, not each case)."""
    out = Scan()
    root = Path(project_dir)
    files = set()
    for tp in test_paths:
        base = root / tp
        if base.is_file():
            files.add(base)
        elif base.is_dir():
            for g in FILE_GLOBS:
                files.update(p for p in base.rglob(g) if p.is_file())
    for path in sorted(files):
        rel = path.relative_to(root).as_posix()
        out.files += 1
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        except (SyntaxError, UnicodeDecodeError, ValueError) as exc:
            out.unparsable.append(f"{rel}: {type(exc).__name__}: {exc}")
            continue
        _walk(tree.body, rel, out)
    return out


@dataclass
class Trace:
    scan: Scan
    writes: list = field(default_factory=list)
    added: List[Tuple[str, str]] = field(default_factory=list)      # (requirement id, node id)
    removed: List[Tuple[str, str]] = field(default_factory=list)
    unknown: List[str] = field(default_factory=list)                # `<node id>: <requirement id>`
    tests_created: int = 0

    @property
    def findings(self) -> List[str]:
        return ([f"marker names no requirement: {u}" for u in self.unknown]
                + [f"does not parse: {u}" for u in self.scan.unparsable] + self.scan.malformed)


def plan_trace(project_dir: Path, driver, database: str, domain_config, config: dict) -> Trace:
    """Plan the edges that bring the graph to the markers (module docstring); nothing is written here.

    Raises:
        RequirementsError: a malformed `requirements:` block.
    """
    s = RQ.settings(config)
    sc = scan(project_dir, s.test_paths)
    tr = Trace(scan=sc)
    with driver.session(database=database) as session:
        reqs = {r["rid"]: r["id"] for r in session.run(
            f"MATCH (r:Artifact:{RQ.REQ_TYPE}) RETURN r.requirement_id AS rid, r.artifact_id AS id").data()}
        edges = session.run(
            f"MATCH (r:Artifact:{RQ.REQ_TYPE})-[e:VERIFIED_BY]->(t:Artifact:Script) WHERE t.test_node IS NOT NULL "
            "RETURN r.requirement_id AS rid, r.artifact_id AS rid_id, t.artifact_id AS sid, t.test_node AS node, "
            "e.declared_by AS by").data()
        scripts = RQ.test_scripts(session, sc.markers)
    wanted = set()
    for node, ids in sc.markers.items():
        for rid in ids:
            if rid in reqs:
                wanted.add((rid, node))
            else:
                tr.unknown.append(f"{node}: {rid}")
    named = {rid for rid, _ in wanted}
    have_marker = set()
    for e in edges:
        key = (e["rid"], e["node"])
        if e["by"] == DECLARED_BY and key in wanted:
            have_marker.add(key)
        elif e["by"] == DECLARED_BY or e["rid"] in named:
            tr.writes.append(RQ._plan_unlink(e["rid_id"], e["sid"], RQ.REL_VERIFIED_BY))
            tr.removed.append(key)
    for rid, node in sorted(wanted - have_marker):
        sid = scripts.get(node)
        if sid is None:
            sid, creation = RQ.plan_test_script(project_dir, domain_config, node)
            tr.writes.append(creation)
            scripts[node] = sid
            tr.tests_created += 1
        plan = RQ.Plan()
        RQ._link(plan, driver, database, domain_config, RQ.REL_VERIFIED_BY, (reqs[rid], RQ.REQ_TYPE),
                 (sid, "Script"), {"declared_by": DECLARED_BY})
        tr.writes += plan.writes
        tr.added.append((rid, node))
    return tr


def trace(project_dir: Path, driver, database: str, domain_config, config: dict, dry_run: bool = False) -> Trace:
    """Plan, then write it in one append (AD-001) unless `dry_run`."""
    tr = plan_trace(project_dir, driver, database, domain_config, config)
    if tr.writes and not dry_run:
        RQ.commit_writes(project_dir, driver, database, tr.writes)
    return tr
