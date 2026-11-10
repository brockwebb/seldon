"""Requirements as graph content; the requirements table and the RTM are projections of it (AD-013 ADDENDA 01, 02).

**What this module owns.**

- the **authored record** (AD-013-R1 as amended by ADDENDUM 02): a requirement's `requirement_id`, `description`,
  `set_by`, `document`, `section`, `verification_method` and `note`. Nothing else about it is stored as text: its
  status is its state, and its trace is its edges (`derived_from` its source, `verified_by` what verifies it,
  `satisfies` from what meets it). `seldon req add` / `seldon req update` write it (:func:`write_one`);
- the **projection** (`seldon docs generate requirements|rtm`, AD-013-R2, R4): the blocks between
  `<!-- seldon:projection ... -->` and `<!-- /seldon:projection -->` markers (Cog's generated regions) are rendered,
  and every cell that is not an authored field is computed from the state and the edges at render (sphinx-needs'
  dynamic functions; OpenFastTrace's computed coverage). Line 1 stamps the revision, the sha256 of the rendered
  blocks; a file whose blocks no longer hash to its stamp was edited by hand and is refused, as Cog `-c` refuses,
  unless the edit is discarded;
- the **checks** (AD-013-R3, R6): requirements with no verification, counted by method, and stale projections.

The vocabulary follows ISO/IEC/IEEE 29148 (identifier, statement, source, verification method, status), ReqIF and
SysML v2 (satisfy, verify, derive). Beside it: the onboarding load of an unmarked markdown table
(`seldon/core/req_load.py`), the test-declared trace (AD-013-R5, `seldon/core/req_trace.py`) and the one-time
removal of SEL-033's verbatim cells (`seldon/core/req_migrate.py`). Design notes:
`docs/design/AD-013_ADDENDUM_01_requirements_as_graph_content.md`,
`docs/design/AD-013_ADDENDUM_02_authored_once_computed_everywhere_else.md`.
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

#: AD-013-R1: the fields a person authors. Every other projection cell is computed (AD-013-R4).
AUTHORED = ("requirement_id", "description", "set_by", "document", "section", "verification_method", "note")
#: The verification methods of ISO/IEC/IEEE 15288 and INCOSE; `test` is the default (AD-013-R1, R6).
METHODS = ("test", "inspection", "analysis", "demonstration")
DEFAULT_METHOD = "test"
#: The types whose node may verify a requirement of a non-test method (AD-013-R6; Document is out, AD-030 s.4).
EVIDENCE_TYPES = ("Result", "Issue")
#: The computed sources a projection column may name (AD-013-R4).
COMPUTED = ("@status", "@state", "@verified_by", "@satisfied_by", "@derived_from", "@decision")

#: The text a projection prints in a verification cell with no `verified_by` edge (hazbrief-mcp's own wording,
#: HB-134R2); `requirements.none_text`, or a projection's own `none_text`, overrides it.
DEFAULT_NONE_TEXT = "none yet"
#: The text a projection prints for an empty attribute.
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

#: The columns a projection renders when its `docs.projections` entry names none.
DEFAULT_PROJECTION_COLUMNS: Dict[str, List[Dict[str, str]]] = {
    "requirements": [
        {"header": "ID", "source": "requirement_id"},
        {"header": "Requirement", "source": "description"},
        {"header": "Set by", "source": "set_by"},
        {"header": "Verified by", "source": "@verified_by"},
        {"header": "Status", "source": "@status"},
    ],
    "rtm": [
        {"header": "ID", "source": "requirement_id"},
        {"header": "Requirement", "source": "description"},
        {"header": "Derived from", "source": "@derived_from"},
        {"header": "Satisfied by", "source": "@satisfied_by"},
        {"header": "Verified by", "source": "@verified_by"},
        {"header": "Status", "source": "@status"},
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
_PLACEHOLDER_RE = re.compile(r"\{(total|unverified|status_counts|status:[^}]+|state:[^}]+|prefix:[^}]+)\}")


class RequirementsError(ValueError):
    """A load or a projection that cannot proceed; the message names what to fix."""


class EditedBlocks(RequirementsError):
    """A projection whose marker blocks no longer hash to the revision on its line 1 (AD-013-R2)."""


# ─────────────────────────────────────────────────────────────── settings


@dataclass
class Settings:
    """The `requirements:` and `docs.projections` blocks of seldon.yaml, with their defaults."""

    columns: Dict[str, List[str]]
    status_map: Dict[str, str]
    state_labels: Dict[str, str]
    none_text: str
    empty_text: str
    counts_template: str
    test_paths: List[str]
    projections: List[Dict[str, Any]]

    def projection_for(self, document: str) -> Optional[Dict[str, Any]]:
        return next((p for p in self.projections if p["path"] == document), None)

    def labels(self, document: Optional[str]) -> Dict[str, str]:
        """The state labels of `document`'s projection, over the project's (AD-013-R4)."""
        p = self.projection_for(document or "")
        return {**self.state_labels, **((p or {}).get("state_labels") or {})}


def settings(config: dict) -> Settings:
    """Read the blocks; refuse a malformed one by name (a misspelled key must not fall back silently).

    Raises:
        RequirementsError: an unknown key, a projection with no path or an unknown kind, or a column whose source is
            neither an authored field nor a computed one (AD-013-R4).
    """
    block = (config or {}).get("requirements") or {}
    known = {"columns", "status_map", "state_labels", "none_text", "empty_text", "counts_template", "test_paths"}
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
        extra = set(p) - {"path", "kind", "columns", "counts_template", "state_labels", "none_text"}
        if extra:
            raise RequirementsError(f"seldon.yaml docs.projections[{i}]: unknown key(s) {sorted(extra)}")
        cols = p.get("columns") or DEFAULT_PROJECTION_COLUMNS[kind]
        for c in cols:
            if c.get("source") not in AUTHORED + COMPUTED:
                raise RequirementsError(
                    f"seldon.yaml docs.projections[{i}] ({p['path']}) column {c.get('header')!r}: source "
                    f"{c.get('source')!r} is neither an authored field {list(AUTHORED)} nor computed {list(COMPUTED)}; "
                    f"a column the graph cannot compute is not a projection column (AD-013-R4)")
        projections.append({"path": p["path"], "kind": kind, "columns": cols,
                            "counts_template": p.get("counts_template"), "state_labels": p.get("state_labels") or {},
                            "none_text": p.get("none_text")})
    tp = block.get("test_paths", ["tests"])
    return Settings(columns=columns, status_map=dict(block.get("status_map") or {}),
                    state_labels=dict(block.get("state_labels") or {}),
                    none_text=block.get("none_text", DEFAULT_NONE_TEXT),
                    empty_text=block.get("empty_text", DEFAULT_EMPTY_TEXT),
                    counts_template=block.get("counts_template", DEFAULT_COUNTS_TEMPLATE),
                    test_paths=[tp] if isinstance(tp, str) else list(tp), projections=projections)


# ─────────────────────────────────────────────────────────────── markdown tables


# ─────────────────────────────────────────────────────────────── cell readers


def status_word(text: str, status_map: Dict[str, str]) -> Optional[str]:
    """The status-map key `text` starts with (the longest; case-insensitive; followed by a non-letter or the end),
    or None. `not met (ruled out)` matches before `not met`, and `met` never matches `metadata`."""
    s = (text or "").strip().lower()
    best = None
    for key in status_map:
        k = key.lower()
        if s.startswith(k) and (len(s) == len(k) or not s[len(k)].isalnum()):
            if best is None or len(k) > len(best):
                best = key
    return best


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


def test_scripts(session, refs: Iterable[str]) -> Dict[str, str]:
    """test node id -> the SEL-021 test `Script` that stands for it (the oldest, when several)."""
    rows = _rows(session, "MATCH (s:Artifact:Script) WHERE s.test_node IN $refs "
                          "RETURN s.test_node AS t, s.artifact_id AS id ORDER BY s.created_at", refs=list(refs))
    out: Dict[str, str] = {}
    for r in rows:
        out.setdefault(r["t"], r["id"])
    return out


def plan_test_script(project_dir: Path, domain_config, ref: str) -> Tuple[str, PlannedWrite]:
    """A new SEL-021 test `Script` for the pytest node id `ref`."""
    return plan_artifact(project_dir=project_dir, domain_config=domain_config, artifact_type="Script",
                         properties={"name": ref, "path": ref.split("::", 1)[0], "test_node": ref,
                                     "description": "A test node a requirement is verified by (AD-013-R5)."},
                         actor=ACTOR, authority="accepted")


def _out_edges(session, rid: str) -> Dict[str, set]:
    """A requirement's edges by type. `KEPT` holds the `verified_by` targets a load never prunes: a marker's
    (AD-013-R5, the trace owns them) and evidence (AD-013-R6, `req update --evidence` owns them)."""
    rows = _rows(session,
                 f"MATCH (r:Artifact:{REQ_TYPE} {{artifact_id: $id}})-[e:VERIFIED_BY|DERIVED_FROM]->(t:Artifact) "
                 "RETURN type(e) AS rel, t.artifact_id AS to, "
                 "(e.declared_by IS NOT NULL OR t.artifact_type <> 'Script') AS kept", id=rid)
    rows += _rows(session,
                  f"MATCH (t:Artifact)-[e:SATISFIES]->(r:Artifact:{REQ_TYPE} {{artifact_id: $id}}) "
                  "RETURN type(e) AS rel, t.artifact_id AS to, false AS kept", id=rid)
    out: Dict[str, set] = {"VERIFIED_BY": set(), "DERIVED_FROM": set(), "SATISFIES": set(), "KEPT": set()}
    for r in rows:
        out[r["rel"]].add(r["to"])
        if r["kept"] and r["rel"] == "VERIFIED_BY":
            out["KEPT"].add(r["to"])
    return out


def qualifying_edges(session, artifact_id: str, method: Optional[str]) -> int:
    """The `verified_by` edges that let a requirement of `method` be `verified` (AD-013-R1, R6): a test Script for
    method test; a test Script, Result or Issue for the others."""
    targets = ["Script"] if (method or DEFAULT_METHOD) == "test" else ["Script", *EVIDENCE_TYPES]
    return _rows(session, "MATCH (r:Artifact {artifact_id: $id})-[:VERIFIED_BY]->(t:Artifact) "
                          "WHERE t.artifact_type IN $types AND (t.artifact_type <> 'Script' OR t.test_node IS NOT NULL) "
                          "RETURN count(t) AS n", id=artifact_id, types=targets)[0]["n"]


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


def plan_walk(domain_config, artifact_id: str, start: str, goal: str) -> Optional[List[PlannedWrite]]:
    """The state changes from `start` to `goal`, or None when the machine has no path."""
    steps = state_path(domain_config.state_machines.get(REQ_TYPE, {}), start, goal)
    if steps is None:
        return None
    out, cur = [], start
    for nxt in steps:
        out.append(plan_state_change(domain_config=domain_config, artifact_id=artifact_id, artifact_type=REQ_TYPE,
                                     current_state=cur, new_state=nxt, actor=ACTOR, authority="accepted"))
        cur = nxt
    return out


# ─────────────────────────────────────────────────────────────── the onboarding load


@dataclass
class Plan:
    """What an import, an add or an update will write, and what did not resolve."""

    writes: List[PlannedWrite] = field(default_factory=list)
    created: List[str] = field(default_factory=list)
    updated: List[str] = field(default_factory=list)
    unchanged: List[str] = field(default_factory=list)
    unresolved: List[str] = field(default_factory=list)
    links_added: int = 0
    links_removed: int = 0
    tests_created: int = 0
    states: Counter = field(default_factory=Counter)


def _plan_unlink(from_id: str, to_id: str, rel: str) -> PlannedWrite:
    event = make_event(event_type="link_removed", actor=ACTOR, authority="accepted",
                       payload={"from_id": from_id, "to_id": to_id, "rel_type": rel})

    def project(session) -> None:
        graph.remove_link(session, from_id, to_id, rel.upper())

    return PlannedWrite(event=event, project=project)


def _link(plan: Plan, driver, database: str, dc, rel: str, frm: Tuple[str, str], to: Tuple[str, str],
          props: Optional[dict] = None) -> None:
    plan.writes.append(plan_link(driver=driver, database=database, domain_config=dc, from_id=frm[0], to_id=to[0],
                                 from_type=frm[1], to_type=to[1], rel_type=rel, actor=ACTOR, authority="accepted",
                                 rel_properties=props))
    plan.links_added += 1


def apply(project_dir: Path, driver, database: str, plan: Plan) -> None:
    """Write the plan: one append to the event log, then the graph (AD-001, SEL-007's all-or-nothing boundary)."""
    if plan.writes:
        commit_writes(project_dir, driver, database, plan.writes)


# ─────────────────────────────────────────────────────────────── add and update


def write_one(project_dir: Path, driver, database: str, domain_config, config: dict, rid: str, *, create: bool,
              fields: Dict[str, Optional[str]], state: Optional[str] = None, evidence: Iterable[str] = (),
              dry_run: bool = False) -> Plan:
    """`seldon req add` (create) and `seldon req update` (change): the authored fields, a state walk and evidence
    edges. Fields given as None keep the node's values.

    Raises:
        RequirementsError: add of a known id or update of an unknown one; a new requirement with no statement; a
            field that is not authored; an unknown method; evidence that is not a Result or Issue; a state the machine
            cannot reach, or `verified` with no qualifying `verified_by` edge (AD-013-R1, R6).
    """
    bad = set(fields) - set(AUTHORED)
    if bad:
        raise RequirementsError(f"{sorted(bad)} are not authored fields of a requirement {list(AUTHORED)} (AD-013-R1)")
    method = fields.get("verification_method")
    if method is not None and method not in METHODS:
        raise RequirementsError(f"verification method {method!r}: one of {list(METHODS)}")
    machine = domain_config.state_machines.get(REQ_TYPE, {})
    if state is not None and state not in machine:
        raise RequirementsError(f"state {state!r} is not a {REQ_TYPE} state ({sorted(machine)})")
    plan = Plan()
    with driver.session(database=database) as session:
        existing = find_requirement(session, rid)
        if create and existing is not None:
            raise RequirementsError(f"{rid} exists; change it with `seldon req update {rid}`")
        if not create and existing is None:
            raise RequirementsError(f"{rid} is not a requirement in the graph; create it with `seldon req add {rid}`")
        if create and not (fields.get("description") or "").strip():
            raise RequirementsError(f"{rid} is a new requirement; give its statement (--statement)")
        props = {k: v for k, v in fields.items() if v is not None}
        if existing is None:
            props["requirement_id"] = rid
            aid, creation = plan_artifact(project_dir=project_dir, domain_config=domain_config, artifact_type=REQ_TYPE,
                                          properties=props, actor=ACTOR, authority="accepted")
            plan.writes.append(creation)
            plan.created.append(rid)
            cur = domain_config.get_initial_state(REQ_TYPE)
        else:
            aid, cur = existing["artifact_id"], existing.get("state")
            diff = {k: v for k, v in props.items() if existing.get(k) != v}
            if diff:
                plan.writes.append(plan_update_artifact(project_dir=project_dir, driver=driver, database=database,
                                                        artifact_id=aid, properties=diff, actor=ACTOR,
                                                        authority="accepted"))
        linked = 0
        for eid in evidence:
            rows = _rows(session, "MATCH (a:Artifact {artifact_id: $id}) RETURN a.artifact_type AS t", id=eid)
            if not rows or rows[0]["t"] not in EVIDENCE_TYPES:
                raise RequirementsError(f"--evidence {eid}: not a {' or '.join(EVIDENCE_TYPES)} artifact (AD-013-R6)")
            have = _out_edges(session, aid)["VERIFIED_BY"] if existing else set()
            if eid not in have:
                _link(plan, driver, database, domain_config, REL_VERIFIED_BY, (aid, REQ_TYPE), (eid, rows[0]["t"]))
                linked += 1
        if state is not None and state != cur:
            m = props.get("verification_method") or (existing or {}).get("verification_method")
            if state == "verified" and not (linked and (m or DEFAULT_METHOD) != DEFAULT_METHOD) \
                    and not (existing and qualifying_edges(session, aid, m)):
                raise RequirementsError(
                    f"{rid} cannot be verified: method {m or DEFAULT_METHOD} needs a verified_by edge to "
                    + ("a test (`@pytest.mark.verifies` and `seldon req trace`)" if (m or "test") == "test" else
                       "the Result or Issue recording its evidence (`--evidence <id>`)") + " (AD-013-R1, R6)")
            walk = plan_walk(domain_config, aid, cur, state)
            if walk is None:
                raise RequirementsError(f"no path on the {REQ_TYPE} machine from {cur} to {state}")
            plan.writes += walk
        if existing is not None:
            (plan.updated if plan.writes else plan.unchanged).append(rid)
        plan.states[state or cur] += 1
    if not dry_run:
        apply(project_dir, driver, database, plan)
    return plan


# ─────────────────────────────────────────────────────────────── the projection


def load_requirements(driver, database: str) -> List[dict]:
    """Every requirement with its edges, for rendering: each a node dict plus `_tests` (verified_by targets),
    `_sources` (derived_from targets), `_decisions` (the register records among them) and `_satisfiers`."""
    with driver.session(database=database) as session:
        rows = _rows(session,
                     f"MATCH (r:Artifact:{REQ_TYPE}) "
                     "OPTIONAL MATCH (r)-[:VERIFIED_BY]->(t:Artifact) "
                     "WITH r, collect(DISTINCT coalesce(t.test_node, t.name, t.path)) AS tests "
                     "OPTIONAL MATCH (r)-[:DERIVED_FROM]->(d:Artifact) "
                     "WITH r, tests, collect(DISTINCT coalesce(d.requirement_id, d.decision_id, d.name, d.path)) AS srcs,"
                     " collect(DISTINCT CASE WHEN d:Decision THEN d.decision_id "
                     "                       WHEN d:ArchitecturalDecision THEN d.name END) AS decs "
                     "OPTIONAL MATCH (s:Artifact)-[:SATISFIES]->(r) "
                     "RETURN r, tests, srcs, decs, collect(DISTINCT coalesce(s.name, s.path)) AS sats")
    out = []
    for row in rows:
        node = dict(row["r"])
        node["_tests"] = sorted((t for t in row["tests"] if t), key=natural_key)
        node["_sources"] = sorted(x for x in row["srcs"] if x)
        node["_decisions"] = sorted({x.rsplit(":", 1)[-1] for x in row["decs"] if x}, key=natural_key)
        node["_satisfiers"] = sorted(x for x in row["sats"] if x)
        out.append(node)
    out.sort(key=lambda n: natural_key(str(n.get("requirement_id", ""))))
    return out


def status_cell(node: dict, labels: Dict[str, str], status_map: Dict[str, str]) -> str:
    """AD-013-R4: the state's label, then `: ` and the note. A note that opens with a status word mapped to the
    current state is the project's finer name for it (`changed`, `partial`) and is shown alone; once the state moves,
    the word no longer maps to it and the label is prefixed."""
    state = str(node.get("state") or "")
    label = labels.get(state, state)
    note = " ".join(str(node.get("note") or "").split())
    if not note:
        return label
    word = status_word(note, status_map)
    if word is not None and status_map[word] == state:
        return note
    return f"{label}: {note}"


@dataclass
class View:
    """What a projection needs to compute its cells: the settings and its own labels and none text."""

    s: Settings
    labels: Dict[str, str]
    none_text: str

    @classmethod
    def of(cls, s: Settings, proj: Optional[Dict[str, Any]]) -> "View":
        proj = proj or {}
        return cls(s=s, labels={**s.state_labels, **(proj.get("state_labels") or {})},
                   none_text=proj.get("none_text") or s.none_text)


def cell_value(node: dict, source: str, v: View) -> str:
    """One cell (AD-013-R4): an authored field as it is, else computed from the state and the edges."""
    if source == "@verified_by":
        if node.get("_tests"):
            return "; ".join(node["_tests"])
        m = node.get("verification_method") or DEFAULT_METHOD
        return v.none_text if m == DEFAULT_METHOD else f"{m}: {v.none_text}"
    if source == "@derived_from":
        return "; ".join(node.get("_sources") or []) or v.s.empty_text
    if source == "@decision":
        return ", ".join(node.get("_decisions") or []) or v.s.empty_text
    if source == "@satisfied_by":
        return "; ".join(node.get("_satisfiers") or []) or v.s.empty_text
    if source == "@state":
        return str(node.get("state") or "")
    if source == "@status":
        return status_cell(node, v.labels, v.s.status_map)
    val = node.get(source)
    return v.s.empty_text if val is None or not str(val).strip() else str(val)


def _cell(value: Any) -> str:
    return re.sub(r"(?<!\\)\|", r"\\|", " ".join(str(value).split()))


def render_table(nodes: List[dict], columns: List[Dict[str, str]], v: View) -> str:
    heads = [c["header"] for c in columns]
    lines = ["| " + " | ".join(heads) + " |", "|" + "|".join("---" for _ in heads) + "|"]
    lines += ["| " + " | ".join(_cell(cell_value(n, c["source"], v)) for c in columns) + " |" for n in nodes]
    return "\n".join(lines)


def render_counts(nodes: List[dict], template: str, v: View) -> str:
    """The counts sentence: `{total}`, `{unverified}` (no `verified_by` edge), `{status:<word>}` (rendered Status
    cells opening with the word), `{state:<state>}`, `{prefix:<text>}` (statements starting with the text) and
    `{status_counts}` (each status word, in the map's order, `N word`)."""
    cells = [status_cell(n, v.labels, v.s.status_map).lower() for n in nodes]

    def opens(word: str) -> int:
        w = word.lower()
        return sum(1 for c in cells if c.startswith(w) and (len(c) == len(w) or not c[len(w)].isalnum()))

    def value(m: re.Match) -> str:
        key = m.group(1)
        if key == "total":
            return str(len(nodes))
        if key == "unverified":
            return str(sum(1 for n in nodes if not n.get("_tests")))
        if key == "status_counts":
            parts = [f"{opens(w)} {w}" for w in v.s.status_map if opens(w)]
            return ", ".join(parts or [f"{c} {st}" for st, c in sorted(Counter(n.get("state") for n in nodes).items())])
        kind, arg = key.split(":", 1)
        if kind == "status":
            return str(opens(arg))
        if kind == "state":
            return str(sum(1 for n in nodes if n.get("state") == arg))
        return str(sum(1 for n in nodes if str(n.get("description") or "").startswith(arg)))

    return _PLACEHOLDER_RE.sub(value, template)


def _attrs(text: str) -> Dict[str, str]:
    return {m.group(1): (m.group(2).replace('\\"', '"') if m.group(2) is not None else m.group(3))
            for m in _ATTR_RE.finditer(text)}


def start_marker(attrs: Dict[str, str]) -> str:
    return "<!-- seldon:projection " + " ".join(f'{k}="' + v.replace('"', '\\"') + '"' for k, v in attrs.items()) \
        + " -->"


def block_columns(rel: str, section: Optional[str], headers: Optional[str],
                  columns: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """The columns a table block renders: the projection's, or, when the block's start marker names
    `headers="A|B|C"` (written by `req import --mark` from the source table), those labels in that order, each mapped
    to the projection column of the same header (case-insensitive).

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
                                    f"source for; add `{{header: {label}, source: <authored field or @computed>}}` to "
                                    f"its docs.projections columns, or drop it from the block's `headers`")
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
    edited: List[str] = field(default_factory=list)   # rows of a hand-edited file that differ from the render

    @property
    def changed(self) -> bool:
        return self.text != self.current


def _blocks(text: str) -> List[Tuple[re.Match, re.Match, bool]]:
    """Each marker block: (start match, end match, inline?). A block is inline when text follows its start marker
    on the same line."""
    out, pos = [], 0
    for m in START_RE.finditer(text):
        if m.start() < pos:
            continue
        end = END_RE.search(text, m.end())
        if end is None:
            raise RequirementsError(f"line {text.count(chr(10), 0, m.start()) + 1}: a seldon:projection start marker "
                                    f"with no end marker ({END_MARK})")
        out.append((m, end, not text[m.end():end.start()].startswith("\n")))
        pos = end.end()
    return out


def _body(text: str, m: re.Match, end: re.Match, inline: bool) -> str:
    body = text[m.end():end.start()]
    return body if inline else body[1:-1] if body.endswith("\n") else body[1:]


def _revision(bodies: List[str]) -> str:
    return hashlib.sha256("\n\x00\n".join(bodies).encode("utf-8")).hexdigest()[:16]


def stamped_revision(text: Optional[str]) -> Optional[str]:
    m = HEADER_RE.match((text or "").split("\n", 1)[0])
    return m.group("rev") if m else None


def hand_edited(text: Optional[str]) -> bool:
    """Whether a rendered file's blocks no longer hash to the revision on its line 1 (Cog's checksum, AD-013-R2).
    A file with no stamp (never rendered) is not edited."""
    rev = stamped_revision(text)
    if rev is None:
        return False
    return _revision([_body(text, *b) for b in _blocks(text)]) != rev


def render_projection(project_dir: Path, proj: Dict[str, Any], nodes: List[dict], s: Settings) -> Rendered:
    """Render one declared projection (AD-013-R2, R4).

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
        v = View.of(s, s.projection_for(doc) or proj)
        if attrs.get("view") == "counts":
            body = render_counts(pool, proj.get("counts_template") or s.counts_template, v)
        else:
            section = attrs.get("section")
            rows = [n for n in pool if (n.get("section") or None) == (section or None)]
            if doc == rel:
                shown.update(n["requirement_id"] for n in rows)
            body = render_table(rows, block_columns(rel, section, attrs.get("headers"), columns), v)
        bodies.append(body)
        return body

    if current is not None and not START_RE.search(current):
        # A hand file with no markers is never overwritten: its prose is not the graph's to replace.
        raise RequirementsError(f"{rel} exists and has no seldon:projection markers; run `seldon req import --mark "
                                f"{rel}` to wrap its tables, or move it aside so the projection is rendered whole")
    if current is None:
        base = ("# Requirements" if proj["kind"] == "requirements" else "# Requirements traceability matrix") + "\n"
    else:
        base = "\n".join(l for l in current.split("\n") if not HEADER_RE.match(l)).lstrip("\n")
    out, pos = [], 0
    for m, end, inline in _blocks(base):
        body = block(_attrs(m.group("attrs")))
        out += [base[pos:m.end()], body if inline else "\n" + body + "\n"]
        pos = end.start()
    text = "".join(out) + base[pos:]
    unplaced = [n["requirement_id"] for n in mine if n["requirement_id"] not in shown]
    sections: List[Optional[str]] = []
    for n in mine:
        if n["requirement_id"] in unplaced and n.get("section") not in sections:
            sections.append(n.get("section"))
    for sec in sections:
        attrs = {"view": "table", **({"section": sec} if sec else {})}
        body = render_table([n for n in mine if n.get("section") == sec], columns, View.of(s, proj))
        bodies.append(body)
        text = text.rstrip("\n") + "\n\n" + (f"## {sec}\n\n" if sec else "") + start_marker(attrs) + "\n" + body \
            + "\n" + END_MARK + "\n"
    revision = _revision(bodies)
    header = (f"<!-- seldon:projection-revision {revision} (the tables and counts between seldon:projection markers "
              f"are rendered from the graph by `seldon docs generate {proj['kind']}`; change a requirement with "
              f"`seldon req`, not here; AD-013-R2) -->")
    full = header + "\n" + text
    edited = []
    if hand_edited(current):
        new = set(full.split("\n"))
        edited = [l for l in current.split("\n") if l not in new and not HEADER_RE.match(l)]
    return Rendered(path=rel, kind=proj["kind"], text=full, current=current, revision=revision,
                    unplaced=unplaced if current is not None else [], edited=edited)


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


def refuse_edited(rendered: List[Rendered]) -> None:
    """AD-013-R2: a projection whose blocks were edited by hand is never overwritten.

    Raises:
        EditedBlocks: naming each edited file and its rows that differ from the render.
    """
    hit = [r for r in rendered if r.current is not None and hand_edited(r.current)]
    if hit:
        lines = []
        for r in hit:
            lines.append(f"{r.path}: its marker blocks no longer hash to revision {stamped_revision(r.current)} "
                         f"(edited by hand); {len(r.edited)} line(s) differ from the render:")
            lines += [f"    {l[:200]}" for l in r.edited[:20]] + (["    ..."] if len(r.edited) > 20 else [])
        raise EditedBlocks("\n".join(lines) + "\nA table inside projection markers is output (AD-013-R2): make the "
                           "change with `seldon req update <id>` and re-render, or re-render with `--discard-edits` "
                           "to drop the edit. Nothing was written.")


def write_and_commit(project_dir: Path, rendered: List[Rendered], commit: bool = True,
                     discard_edits: bool = False) -> dict:
    """Write the changed projections, then commit exactly those paths through the hooks (AD-038-R15: a command
    commits what it writes). A hand-edited projection refuses the whole write unless `discard_edits` (AD-013-R2).

    Raises:
        EditedBlocks: a projection's blocks were edited by hand and `discard_edits` is false.
    """
    from seldon.core.dispatch import commit_paths, git

    if not discard_edits:
        refuse_edited(rendered)
    changed = [r for r in rendered if r.changed]
    for r in changed:
        p = Path(project_dir) / r.path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(r.text, encoding="utf-8")
    # A discarded edit can restore the committed bytes exactly: written, but nothing to commit.
    dirty = [r for r in changed if not commit or git(project_dir, "status", "--porcelain", "--", r.path).stdout.strip()]
    if not dirty or not commit:
        return {"written": [r.path for r in changed], "committed": False,
                "reason": "nothing_to_commit" if not dirty else "no_commit"}
    kinds = sorted({r.kind for r in dirty})
    revs = ", ".join(f"{r.path} {r.revision}" for r in dirty)
    msg = (f"docs: render {' and '.join(kinds)} projection(s) from the graph (AD-013-R2)\n\n"
           f"seldon docs generate {' '.join(kinds)}; graph revision per file: {revs}")
    out = commit_paths(Path(project_dir), [r.path for r in dirty], msg)
    out["written"] = [r.path for r in changed]
    return out


# ─────────────────────────────────────────────────────────────── the checks (AD-013-R3, R6)


def unverified(driver, database: str) -> List[dict]:
    """Requirements with no qualifying `verified_by` edge, rejected ones excepted, each with its method
    (AD-013-R6): a test Script for method test; a test Script, Result or Issue for the others."""
    with driver.session(database=database) as session:
        return _rows(session,
                     f"MATCH (r:Artifact:{REQ_TYPE}) WHERE coalesce(r.state, '') <> 'rejected' "
                     "WITH r, coalesce(r.verification_method, 'test') AS m "
                     "OPTIONAL MATCH (r)-[:VERIFIED_BY]->(t:Artifact) "
                     "WHERE (t:Script AND t.test_node IS NOT NULL) OR (m <> 'test' AND t.artifact_type IN $ev) "
                     "WITH r, m, count(t) AS n WHERE n = 0 "
                     "RETURN r.requirement_id AS id, r.state AS state, r.document AS document, m AS method "
                     "ORDER BY r.requirement_id", ev=list(EVIDENCE_TYPES))


def by_method(rows: List[dict]) -> Dict[str, List[str]]:
    """Unverified ids grouped by method, test first (AD-013-R6)."""
    out: Dict[str, List[str]] = {}
    for r in sorted(rows, key=lambda r: (r["method"] != DEFAULT_METHOD, r["method"])):
        out.setdefault(r["method"], []).append(r["id"])
    return out


def count(driver, database: str) -> int:
    with driver.session(database=database) as session:
        return _rows(session, f"MATCH (r:Artifact:{REQ_TYPE}) RETURN count(r) AS n")[0]["n"]


def stale_projections(project_dir: Path, driver, database: str, config: dict) -> List[str]:
    """One finding per declared projection whose file is missing, was edited by hand, or differs from a fresh render
    because the graph moved; and per requirement of a marked file that no block shows."""
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
        elif hand_edited(r.current):
            out.append(f"{r.path}: its blocks were edited by hand, so `seldon docs generate {r.kind}` refuses it; "
                       f"make the change with `seldon req update` and re-render with `--discard-edits`")
        elif r.changed:
            out.append(f"{r.path}: the graph moved since revision {stamped_revision(r.current)}; run "
                       f"`seldon docs generate {r.kind}`")
        if r.unplaced:
            out.append(f"{r.path}: {len(r.unplaced)} requirement(s) of this document in no block "
                       f"(first: {', '.join(r.unplaced[:5])}); `seldon docs generate {r.kind}` appends them")
    return out
