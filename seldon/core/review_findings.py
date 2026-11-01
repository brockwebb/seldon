"""Review findings as Issues, traced to their fix, their test and the decisions they change (SEL-021).

Factory F-010: a review finding is an Issue, linked to its fix task, its test and any decision it changes; F-011:
cross-repository provenance is a `found_in` property, not prose. This module holds the one grammar for `found_in`
(the Issue property and the task file's `**Found in:**` header), the one grammar for a test reference, the checks
every write path applies before anything is written, the planned writes for the trace links, and the orphan rule
`seldon issue orphans` reports.

The trace is the requirements-traceability pattern (Gotel and Finkelstein 1994, pre- and post-specification trace;
DO-178C's bidirectional trace; ISO/IEC/IEEE 29148:2018), cited in factory `docs/architecture.md` section 2. The
disposition of a finding that is not fixed carries its justification as SARIF 2.1.0 carries a suppression's
`justification` and IEEE 1044-2009 an anomaly's disposition: a rejection without a stated reason is
not a disposition.

Edges (seldon/domain/research.yaml): `remediated_by` Issue -> ResearchTask (existing), `verified_by` Issue -> Script
(the Script stands for one test node; `test_node` holds the `path::node id`), `changes` Issue -> Decision or
ArchitecturalDecision.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

#: The `found_in` grammar, quoted by every refusal.
FOUND_IN_GRAMMAR = ("`<repo>:<path>#<finding id>`: the repository the review was filed in (its directory name), "
                    "the review file's path in it, and the finding's id in that file, e.g. "
                    "`factory:reviews/squiddy_code_review_max_findings.md#3`")
_FOUND_IN_RE = re.compile(
    r"^(?P<repo>[A-Za-z0-9][A-Za-z0-9._-]*):(?P<path>[^\s#:][^\s#]*)#(?P<finding>[^\s#]+)$")

#: The test reference grammar for `verified_by`.
TEST_REF_GRAMMAR = ("`<path>::<node id>`: a pytest node id relative to the project root, e.g. "
                    "`tests/test_issue.py::test_issue_wont_fix_path`")
_TEST_REF_RE = re.compile(r"^(?P<path>[^\s:]+)::(?P<node>\S+)$")

#: The task file's optional header (Part C). Its value is a `found_in`.
HEADER_FOUND_IN = "Found in"
FOUND_IN_UNPARSABLE = "found_in_unparsable"

ISSUE_TYPE = "review_finding"
FIXED = "fixed"

#: Task states that count as a finished fix for the orphan rule: `completed`, or `verified` after it.
FIX_DONE_STATES = ("completed", "verified")

#: The relationship names, as the domain config spells them.
REL_REMEDIATED_BY = "remediated_by"
REL_VERIFIED_BY = "verified_by"
REL_CHANGES = "changes"
DECISION_TYPES = ("Decision", "ArchitecturalDecision")


def parse_found_in(value: str) -> dict:
    """`{repo, path, finding}` for a `found_in` value.

    Raises:
        ValueError: when the value does not parse; the message quotes :data:`FOUND_IN_GRAMMAR`.
    """
    item = (value or "").strip()
    item = item[:-1] if item.endswith(".") else item
    item = item.strip().strip("`").strip()
    m = _FOUND_IN_RE.match(item)
    if not m:
        raise ValueError(f"found_in {value!r} does not parse; expected {FOUND_IN_GRAMMAR}")
    return {"repo": m.group("repo"), "path": m.group("path"), "finding": m.group("finding"), "value": item}


def parse_found_in_header(value: Optional[str]) -> dict:
    """The `**Found in:**` header's value: `{kind, found_in, error}`, shaped as `dispatch.parse_answers`.

    `kind` is `absent` (no header), `ref` (parses) or None (does not, and `error` says why).
    """
    if value is None:
        return {"kind": "absent", "found_in": None, "error": None}
    try:
        parsed = parse_found_in(value)
    except ValueError as exc:
        return {"kind": None, "found_in": None,
                "error": f"`**{HEADER_FOUND_IN}:**` header: {exc}"}
    return {"kind": "ref", "found_in": parsed["value"], "error": None}


def parse_test_ref(value: str, project_dir: Path) -> dict:
    """`{path, node, value}` for a `verified_by` test reference whose file exists under `project_dir`.

    The node id itself is not collected (that would run pytest); the file is the part a typo most often breaks.

    Raises:
        ValueError: when the reference does not parse or its file is not a file in the project.
    """
    item = (value or "").strip().strip("`").strip()
    m = _TEST_REF_RE.match(item)
    if not m:
        raise ValueError(f"verified_by {value!r} does not parse; expected {TEST_REF_GRAMMAR}")
    if Path(m.group("path")).is_absolute() or ".." in Path(m.group("path")).parts:
        raise ValueError(f"verified_by {value!r}: the path must be relative to the project root, inside it; "
                         f"expected {TEST_REF_GRAMMAR}")
    if not (Path(project_dir) / m.group("path")).is_file():
        raise ValueError(f"verified_by {value!r}: {m.group('path')} is not a file in {project_dir}")
    return {"path": m.group("path"), "node": m.group("node"), "value": item}


def review_properties(*, issue_type: str, found_in: Optional[str], severity: Optional[str],
                      disposition: Optional[str], disposition_evidence: Optional[str],
                      existing: Optional[dict] = None) -> dict:
    """The review properties to write, validated; `{}` when none is given.

    Rules, checked before anything is written:
    - a `review_finding` Issue names where it was found (`found_in`), on creation;
    - `found_in` parses (:data:`FOUND_IN_GRAMMAR`);
    - `disposition` is one of the enum's values;
    - a disposition other than `fixed` carries non-empty evidence, given now or already on the Issue;
    - evidence is never written without a disposition (given now or already on the Issue).

    Args:
        existing: the Issue's current properties, for an update; None on creation.

    Raises:
        ValueError: naming the rule broken.
    """
    from seldon.core.issue_utils import validate_issue_enum

    existing = existing or {}
    props: dict = {}
    if found_in is not None and str(found_in).strip():
        props["found_in"] = parse_found_in(found_in)["value"]
    elif issue_type == ISSUE_TYPE and not existing.get("found_in"):
        raise ValueError(f"a {ISSUE_TYPE} Issue needs found_in, {FOUND_IN_GRAMMAR}")
    if severity is not None and str(severity).strip():
        props["severity"] = str(severity).strip()
    if disposition is not None and str(disposition).strip():
        validate_issue_enum("disposition", disposition.strip())
        props["disposition"] = disposition.strip()
    if disposition_evidence is not None and str(disposition_evidence).strip():
        props["disposition_evidence"] = str(disposition_evidence).strip()
    final_disposition = props.get("disposition", existing.get("disposition"))
    final_evidence = props.get("disposition_evidence", existing.get("disposition_evidence")) or ""
    if "disposition_evidence" in props and not final_disposition:
        raise ValueError("disposition_evidence given with no disposition; name the disposition it supports")
    if final_disposition and final_disposition != FIXED and not str(final_evidence).strip():
        raise ValueError(f"disposition {final_disposition!r} needs disposition_evidence: the reason, with where "
                         f"it is recorded (a RESULT section, a decision id, a review reply)")
    return props


def _single(session, query: str, **params) -> list:
    return session.run(query, **params).data()


def resolve_task(session, ref: str) -> dict:
    """The ResearchTask `ref` names: an artifact id or unique prefix, or a task name (a cc_tasks file stem).

    Raises:
        ValueError: when it names no ResearchTask or more than one.
    """
    rows = _single(session,
                   "MATCH (t:Artifact:ResearchTask) WHERE t.artifact_id STARTS WITH $r OR t.name = $r "
                   "RETURN t.artifact_id AS id, t.name AS name", r=ref.strip())
    ids = {r["id"] for r in rows}
    if len(ids) != 1:
        raise ValueError(f"remediated_by {ref!r} names {len(ids) or 'no'} ResearchTask"
                         f"{'s' if len(ids) != 1 else ''}; give an artifact id, a unique prefix or a task name")
    return {"artifact_id": ids.pop(), "artifact_type": "ResearchTask"}


def resolve_decision(session, ref: str) -> dict:
    """The decision `ref` names: a register record id (`seldon:AD-034-R5`) or an ArchitecturalDecision name.

    Raises:
        ValueError: when it names none or more than one.
    """
    rows = _single(session,
                   "MATCH (d:Artifact) WHERE (d:Decision OR d:ArchitecturalDecision) "
                   "AND (d.name = $r OR d.decision_id = $r OR d.artifact_id = $r) "
                   "RETURN DISTINCT d.artifact_id AS id, d.artifact_type AS type", r=ref.strip())
    if len(rows) != 1:
        raise ValueError(f"changes {ref!r} names {len(rows) or 'no'} decision record"
                         f"{'s' if len(rows) != 1 else ''}; give the register id as `seldon decision` prints "
                         f"it (`<repo>:<id>`) or an ArchitecturalDecision name")
    return {"artifact_id": rows[0]["id"], "artifact_type": rows[0]["type"]}


def plan_trace_writes(*, project_dir: Path, driver, database: str, domain_config, issue_id: str,
                      remediated_by: list, verified_by: list, changes: list, actor: str,
                      session_id: Optional[str] = None) -> tuple[list, list]:
    """Planned writes for the trace links, every ref resolved and validated first; `(writes, labels)`.

    A test reference resolves to the Script that stands for it (`test_node` equal to the reference), created in the
    same append when there is none. Nothing is written here; the caller commits the writes with its own.

    Raises:
        ValueError: on the first ref that does not resolve or parse, before any write is planned.
    """
    from seldon.core.artifacts import plan_artifact, plan_link

    tasks, tests, decisions = [], [], []
    with driver.session(database=database) as session:
        for ref in remediated_by:
            tasks.append((ref, resolve_task(session, ref)))
        for ref in verified_by:
            parsed = parse_test_ref(ref, project_dir)
            rows = _single(session,
                           "MATCH (s:Artifact:Script) WHERE s.test_node = $v "
                           "RETURN s.artifact_id AS id ORDER BY s.created_at LIMIT 1", v=parsed["value"])
            tests.append((parsed, rows[0]["id"] if rows else None))
        for ref in changes:
            decisions.append((ref, resolve_decision(session, ref)))

    writes, labels = [], []

    def link(rel: str, to_id: str, to_type: str) -> None:
        writes.append(plan_link(driver=driver, database=database, domain_config=domain_config,
                                from_id=issue_id, to_id=to_id, from_type="Issue", to_type=to_type,
                                rel_type=rel, actor=actor, authority="accepted", session_id=session_id))

    for ref, node in tasks:
        link(REL_REMEDIATED_BY, node["artifact_id"], "ResearchTask")
        labels.append(f"REMEDIATED_BY {ref}")
    for parsed, script_id in tests:
        if script_id is None:
            script_id, creation = plan_artifact(
                project_dir=project_dir, domain_config=domain_config, artifact_type="Script",
                properties={"name": parsed["value"], "path": parsed["path"], "test_node": parsed["value"],
                            "description": "A test node a review finding is verified by (SEL-021)."},
                actor=actor, authority="accepted", session_id=session_id)
            writes.append(creation)
        link(REL_VERIFIED_BY, script_id, "Script")
        labels.append(f"VERIFIED_BY {parsed['value']}")
    for ref, node in decisions:
        link(REL_CHANGES, node["artifact_id"], node["artifact_type"])
        labels.append(f"CHANGES {ref}")
    return writes, labels


def orphans(driver, database: str) -> list[dict]:
    """Every `review_finding` Issue that is neither (a) remediated by a finished task AND verified by a test, nor
    (b) disposed of other than `fixed` with non-empty evidence. Each row says why, in `reasons`.
    """
    with driver.session(database=database) as session:
        rows = session.run(
            "MATCH (i:Artifact:Issue) WHERE i.issue_type = $t "
            "OPTIONAL MATCH (i)-[:REMEDIATED_BY]->(task:Artifact:ResearchTask) "
            "WITH i, collect(task.state) AS task_states "
            "OPTIONAL MATCH (i)-[:VERIFIED_BY]->(s:Artifact:Script) "
            "WITH i, task_states, count(s) AS tests "
            "RETURN i.artifact_id AS id, i.name AS name, i.found_in AS found_in, i.state AS state, "
            "i.disposition AS disposition, i.disposition_evidence AS evidence, i.description AS description, "
            "task_states, tests ORDER BY i.created_at",
            t=ISSUE_TYPE).data()
    out = []
    for r in rows:
        fixed_done = any(s in FIX_DONE_STATES for s in r["task_states"])
        if fixed_done and r["tests"] > 0:
            continue
        disposition = r["disposition"]
        if disposition and disposition != FIXED and str(r["evidence"] or "").strip():
            continue
        reasons = []
        if disposition and disposition != FIXED:
            reasons.append(f"disposition {disposition} has no evidence")
        else:
            if not r["task_states"]:
                reasons.append("no REMEDIATED_BY task")
            elif not fixed_done:
                reasons.append(f"fix task not completed ({', '.join(sorted(set(r['task_states'])))})")
            if r["tests"] == 0:
                reasons.append("no VERIFIED_BY test")
        out.append({**{k: r[k] for k in ("id", "name", "found_in", "state", "disposition", "description")},
                    "reasons": reasons})
    return out


def format_orphans(rows: list[dict]) -> str:
    """The report both surfaces print: one line per orphan, then the count."""
    lines = [f"{r['id'][:8]}  {r.get('found_in') or '(no found_in)'}  {'; '.join(r['reasons'])}"
             + (f"  — {(r.get('description') or '')[:60]}" if r.get("description") else "")
             for r in rows]
    lines.append(f"orphans: {len(rows)}")
    return "\n".join(lines)
