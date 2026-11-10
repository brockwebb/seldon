"""`seldon req migrate`: remove SEL-033's verbatim cells from requirement nodes, once (AD-013 ADDENDUM 02 s.4.1).

SEL-033 kept a load source's cells on each `SRS_Requirement` (`status_text`, `verified_by_text`, `satisfied_by_text`,
`validated_by`, `decision_text`) beside the state and the edges that are the same facts, and rendered the text
(review finding 83b09573). AD-013-R1 as amended keeps only authored fields. This module places each cell where
:func:`seldon.core.requirements.place_cells` says (an edge already carries it: dropped; a method: `verification_method`;
anything else: the `note`, never dropped), then removes the five properties, one `artifact_updated` event per node
through the event log. A node that carries none of them is skipped, so a second run writes nothing.

One-time by design: once every consumer has run it, this module and its command can be deleted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from seldon.core import req_load as RL
from seldon.core import requirements as RQ
from seldon.core.artifacts import plan_update_artifact

#: The node property each verbatim cell was kept in (SEL-033's COLUMN_PROPERTY), by the load field it came from.
VERBATIM = {"status": "status_text", "verified_by": "verified_by_text", "validated_by": "validated_by",
            "satisfied_by": "satisfied_by_text", "decision": "decision_text"}


@dataclass
class Migration:
    writes: list = field(default_factory=list)
    migrated: List[str] = field(default_factory=list)
    skipped: int = 0
    listed: List[str] = field(default_factory=list)     # `<id>: <what was kept in the note and why>`
    methods: Dict[str, str] = field(default_factory=dict)
    notes: Dict[str, Optional[str]] = field(default_factory=dict)


def plan_migration(project_dir: Path, driver, database: str, config: dict) -> Migration:
    """Plan the property updates that move every verbatim cell to its place and remove it.

    Raises:
        RequirementsError: a malformed `requirements:` block.
    """
    s = RQ.settings(config)
    out = Migration()
    with driver.session(database=database) as session:
        rows = session.run(
            f"MATCH (r:Artifact:{RQ.REQ_TYPE}) "
            "OPTIONAL MATCH (r)-[:VERIFIED_BY]->(t:Artifact:Script) "
            "WITH r, collect(DISTINCT t.test_node) AS tests "
            "OPTIONAL MATCH (r)-[:DERIVED_FROM]->(d:Artifact:Decision) "
            "WITH r, tests, collect(DISTINCT d.decision_id) AS decs "
            "OPTIONAL MATCH (x:Artifact)-[:SATISFIES]->(r) "
            "RETURN r, tests, decs, collect(DISTINCT x.name) AS sats").data()
    for row in sorted(rows, key=lambda r: RQ.natural_key(str(r["r"].get("requirement_id")))):
        node = dict(row["r"])
        if not any(p in node for p in VERBATIM.values()):
            out.skipped += 1
            continue
        rid, state = node["requirement_id"], node.get("state") or ""
        doc = node.get("document")
        label = s.labels(doc).get(state, state)
        none_text = (s.projection_for(doc or "") or {}).get("none_text") or s.none_text
        carried = RL.Carried(tests={t for t in row["tests"] if t},
                             satisfiers={(n or "").split()[0] for n in row["sats"] if n},
                             decisions={d.rsplit(":", 1)[-1] for d in row["decs"] if d})
        cells = {f: node[p] for f, p in VERBATIM.items() if node.get(p) is not None}
        note, method, listed = RL.place_cells(cells, state, label, s.status_map, none_text, carried)
        if node.get("note"):
            note = node["note"] + ("; " + note if note else "")
        props = {p: None for p in VERBATIM.values() if p in node}
        if note:
            props["note"] = note
        if method and not node.get("verification_method"):
            props["verification_method"] = method
            out.methods[rid] = method
        out.notes[rid] = note
        out.listed += [f"{rid}: {x}" for x in listed]
        out.writes.append(plan_update_artifact(project_dir=project_dir, driver=driver, database=database,
                                               artifact_id=node["artifact_id"], properties=props, actor=RQ.ACTOR,
                                               authority="accepted"))
        out.migrated.append(rid)
    return out


def migrate(project_dir: Path, driver, database: str, config: dict, dry_run: bool = False) -> Migration:
    """Plan, then write it in one append (AD-001) unless `dry_run`."""
    m = plan_migration(project_dir, driver, database, config)
    if m.writes and not dry_run:
        RQ.commit_writes(project_dir, driver, database, m.writes)
    return m
