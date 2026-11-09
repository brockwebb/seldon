"""SEL-036 (AD-036-R22): a governed Citation resolves to the bibliographic entry it names, as a pointer.

Against the per-process Neo4j test database (tests/testdb.py) and a scratch event store: two Citations as governed
sync writes them, a seed map naming three entries (one Citation names two works, one names none), and the catalog
entries. Pinned: one ExternalReference per entry (`<graph>:<entry id>`, carrying the identifier and nothing of the
entry's text), one `resolves_to` per pair, every write an event, a second run writing nothing, a Citation the graph
does not hold and an entry the catalog does not hold both reported, and the question the bridge exists for answered:
which works a document's rulings rest on.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from seldon.core import biblio_bridge as bb
from seldon.core.artifacts import create_artifact
from seldon.domain.loader import load_domain_config
from tests.conftest import TEST_DATABASE as DB

DOMAIN = load_domain_config(Path(__file__).resolve().parents[1] / "seldon" / "domain" / "research.yaml")

DOC = "docs/design/AD-029_task_precedence.md"

ENTRIES = {
    "kahn1962topological": {"id": "kahn1962topological", "title": "Topological sorting of large networks",
                            "doi": "10.1145/368996.369025", "resolved_by": "openalex",
                            "abstract": "NOT COPIED"},
    "kelley1959critical": {"id": "kelley1959critical", "title": "Critical-path planning and scheduling",
                           "doi": "10.1145/1460299.1460318", "resolved_by": "openalex"},
    "pmi_pmbok": {"id": "pmi_pmbok", "title": "PMBOK Guide", "standard_number": "ANSI/PMI 99-001"},
}
GOVERNED = {
    "ad029@kahn": {"seeds": ["kahn1962topological"]},
    "ad029@kelley": {"seeds": ["kelley1959critical", "pmi_pmbok"]},
    "ad036@r6": {"seeds": []},
    "nowhere@x": {"seeds": ["kahn1962topological"]},
    "ad029@ghost": {"seeds": ["not_in_catalog"]},
}


def _citation(project_dir, driver, name):
    return create_artifact(project_dir, driver, DB, DOMAIN, "Citation",
                           {"key": name, "name": name, "title": name, "raw": name, "source_document": DOC},
                           actor="test", authority="accepted")


@pytest.fixture
def world(tmp_path, neo4j_driver, clean_test_db):
    for name in ("ad029@kahn", "ad029@kelley", "ad036@r6", "ad029@ghost"):
        _citation(tmp_path, neo4j_driver, name)
    return {"dir": tmp_path, "driver": neo4j_driver}


def _run(world, **kw):
    return bb.bridge(world["dir"], world["driver"], DB, DOMAIN, GOVERNED, ENTRIES, "seldon-biblio",
                     actor="test", **kw)


def _events(d: Path, kind: str) -> list:
    rows = [json.loads(x) for x in (d / "seldon_events.jsonl").read_text().splitlines() if x.strip()]
    return [r for r in rows if r.get("event_type") == kind]


def test_each_citation_resolves_to_a_pointer_per_named_entry_through_the_event_store(world):
    rep = _run(world)
    assert (rep.references_created, rep.links_created) == (3, 3)
    assert rep.naming_no_work == ["ad036@r6"] and rep.citations_missing == ["nowhere@x"]
    assert rep.entries_missing == ["not_in_catalog"]
    with world["driver"].session(database=DB) as s:
        refs = {r["name"]: dict(r["e"]) for r in s.run(
            "MATCH (e:ExternalReference) RETURN e.name AS name, e")}
        pairs = sorted((r["c"], r["e"]) for r in s.run(
            "MATCH (c:Citation)-[:RESOLVES_TO]->(e:ExternalReference) RETURN c.name AS c, e.name AS e"))
    assert pairs == [("ad029@kahn", "seldon-biblio:kahn1962topological"),
                     ("ad029@kelley", "seldon-biblio:kelley1959critical"),
                     ("ad029@kelley", "seldon-biblio:pmi_pmbok")]
    kahn = refs["seldon-biblio:kahn1962topological"]
    assert (kahn["graph"], kahn["entry_id"], kahn["identifier"]) == (
        "seldon-biblio", "kahn1962topological", "doi:10.1145/368996.369025")
    assert refs["seldon-biblio:pmi_pmbok"]["identifier"] == "standard:ANSI/PMI 99-001"
    assert not any("NOT COPIED" in json.dumps(v) for v in refs.values())        # a pointer, never a copy
    assert len(_events(world["dir"], "artifact_created")) == 4 + 3               # the Citations, then the pointers
    assert len(_events(world["dir"], "link_created")) == 3


def test_a_second_run_writes_nothing(world):
    _run(world)
    rep = _run(world)
    assert (rep.references_created, rep.links_created) == (0, 0)
    assert (rep.references_existing, rep.links_existing) == (3, 3)
    assert len(_events(world["dir"], "link_created")) == 3


def test_a_dry_run_counts_and_writes_nothing(world):
    rep = _run(world, dry_run=True)
    assert (rep.references_created, rep.links_created) == (3, 3)   # what a real run writes, counted
    with world["driver"].session(database=DB) as s:
        assert s.run("MATCH (e:ExternalReference) RETURN count(e) AS n").single()["n"] == 0
        assert s.run("MATCH ()-[r:RESOLVES_TO]->() RETURN count(r) AS n").single()["n"] == 0


def test_the_governed_graph_answers_which_works_a_document_rests_on(world):
    _run(world)
    with world["driver"].session(database=DB) as s:
        got = bb.works_for_ruling(s, DOC)
    assert [w["name"] for w in got] == ["seldon-biblio:kahn1962topological", "seldon-biblio:kelley1959critical",
                                        "seldon-biblio:pmi_pmbok"]
