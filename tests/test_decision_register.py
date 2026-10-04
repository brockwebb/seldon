"""The decision register (AD-033, SEL-002 Part A). Each planted control is a defect the register
exists to refuse; `scripts/sel002/mutation_controls.py` re-runs these tests with the catching code
removed and records that each one then fails (evidence/sel002/mutation_controls.txt).

Planted controls (SEL-002 step 1, ADDENDUM 01):
  - a hand-edited record file fails the check (hash chain; canonical bytes);
  - a forked supersession is refused, and the refusal names the live head;
  - a supersession of a missing id is refused, and nothing is written;
  - a labeled decision in a note added after the baseline, with no record, fails the check;
  - an Arnold registration resolves `squiddy:R-112` (and bare `R-112`) through its import;
  - a superseded record never binds (the R-29 case, AD-033 section 1);
  - the Decision label is in the owned label set (Addendum 029-A);
  - legacy ArchitecturalDecision and DesignNote nodes are unchanged by the projection.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from seldon.core import decisions as dr
from seldon.core.sync import SELDON_OWNED_LABELS
from tests.testdb import TEST_DATABASE

NEO4J_DB = TEST_DATABASE
neo4j_tests = pytest.mark.usefixtures("neo4j_available")

DATE = "2026-10-04"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True,
                          text=True).stdout.strip()


def _repo(base: Path, name: str, *, imports=(), baseline: bool = True, extra_cfg: str = "",
          database: str = "seldon-test-unused") -> Path:
    """A repository with a `decisions:` block, a design note, and (optionally) a baseline commit."""
    root = base / name
    (root / "docs" / "design").mkdir(parents=True)
    (root / "docs" / "design" / "2026-09-01_DN-001_first.md").write_text(
        "# DN-001 first\n\n## R-1 A kit, not a system\n\nThe kit never stores content.\n\n"
        "## R-2 Old cost chart\n\nThe multiple stays as a reported number under a control chart.\n",
        encoding="utf-8")
    imp = "".join(f"\n    - {i}" for i in imports)
    (root / "seldon.yaml").write_text(
        f"project:\n  name: {name}\n  domain: research\n"
        f"neo4j:\n  database: {database}\n  uri: bolt://localhost:7687\n"
        "event_store:\n  path: seldon_events.jsonl\n"
        f"decisions:\n  repository: {name}\n"
        + (f"  import:{imp}\n" if imports else "")
        + "  design_notes:\n"
          "    - glob: docs/design/*.md\n"
          "      pattern: '^(?:#+\\s*|\\s*[-*]\\s*\\*\\*|\\*\\*)(R-\\d{1,3})\\b'\n"
          "      id: '{repo}:{label}'\n"
        + extra_cfg, encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    _git(root, "config", "user.email", "t@example.org")
    _git(root, "config", "user.name", "t")
    if baseline:
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", "baseline")
        sha = _git(root, "rev-parse", "HEAD")
        cfg = yaml.safe_load((root / "seldon.yaml").read_text())
        cfg["decisions"]["baseline"] = {"name": "DB-1", "commit": sha}
        (root / "seldon.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    return root


def _cfg(root: Path) -> dict:
    return yaml.safe_load((root / "seldon.yaml").read_text())


def _u(root: Path) -> dr.Universe:
    return dr.universe(root, _cfg(root))


def _record(repo: str, local: str, text: str, **extra) -> dict:
    rec = {
        "id": f"{repo}:{local}", "kind": "decision", "statement": text,
        "source": {"path": "docs/design/2026-09-01_DN-001_first.md", "lines": [3, 5],
                   "sha256": "0" * 64, "text": text},
        "scope": [repo],
        "rationale": {"path": "docs/design/2026-09-01_DN-001_first.md", "anchor": local},
        "review_only": "none",
    }
    rec.update(extra)
    return rec


def _accept(u: dr.Universe, repo: str, local: str, text: str, **extra) -> list[Path]:
    return dr.create(u, "accept", _record(repo, local, text, **extra), date=DATE,
                     decided_by="desktop")


# ---------------------------------------------------------------------------
# the record and the chain
# ---------------------------------------------------------------------------

def test_a_written_record_verifies_and_folds(tmp_path):
    root = _repo(tmp_path, "squiddy")
    u = _u(root)
    _accept(u, "squiddy", "R-1", "The kit never stores content.")
    dr.create(u, "propose", _record("squiddy", "R-3", "Reserve before dispatch.",
                                    waits_on="P3 spend governor"),
              date=DATE, decided_by="desktop")
    dr.transition(u, "accept", "squiddy:R-3", date=DATE, decided_by="cc:SEL-002",
                  reason="built by SQ-009")
    reg = dr.Register("squiddy", root)
    assert reg.verify() == []
    recs = dr.fold(reg.events())
    assert recs["squiddy:R-1"].status == "accepted"
    assert recs["squiddy:R-3"].status == "accepted"
    names = [p.name for p in reg.files()]
    assert names == ["00001_squiddy-r-1_accept.yaml", "00002_squiddy-r-3_propose.yaml",
                     "00003_squiddy-r-3_accept.yaml"]
    # status is derived: the proposing file still says proposed
    assert yaml.safe_load((reg.path / names[1]).read_text())["status"] == "proposed"


def test_planted_hand_edited_record_fails_the_check(tmp_path):
    root = _repo(tmp_path, "squiddy")
    u = _u(root)
    _accept(u, "squiddy", "R-1", "The kit never stores content.")
    _accept(u, "squiddy", "R-2", "The multiple stays as a reported number.")
    dr.write_rendered(_u(root))
    assert dr.check(root, _cfg(root)) == []
    f = sorted((root / "docs/decisions/register").glob("*.yaml"))[0]
    f.write_text(f.read_text().replace("never stores", "sometimes stores"), encoding="utf-8")
    findings = dr.check(root, _cfg(root))
    assert any("does not hash to its record_hash" in x for x in findings), findings
    with pytest.raises(dr.BrokenRegister):
        _u(root).records("squiddy")


def test_planted_reformatted_record_with_equal_data_fails_the_check(tmp_path):
    root = _repo(tmp_path, "squiddy")
    _accept(_u(root), "squiddy", "R-1", "The kit never stores content.")
    f = sorted((root / "docs/decisions/register").glob("*.yaml"))[0]
    data = yaml.safe_load(f.read_text())
    f.write_text(yaml.safe_dump(data, sort_keys=True), encoding="utf-8")   # same data, new bytes
    assert yaml.safe_load(f.read_text()) == data
    findings = dr.Register("squiddy", root).verify()
    assert any("not the canonical serialization" in x for x in findings), findings


def test_planted_removed_record_breaks_the_chain(tmp_path):
    root = _repo(tmp_path, "squiddy")
    u = _u(root)
    for i in (1, 2, 3):
        _accept(u, "squiddy", f"R-{i + 10}", f"Rule number {i}.")
    files = sorted((root / "docs/decisions/register").glob("*.yaml"))
    files[1].unlink()
    findings = dr.Register("squiddy", root).verify()
    assert any("chain is broken" in x or "seq" in x for x in findings), findings


# ---------------------------------------------------------------------------
# refusals (AD-033-R2)
# ---------------------------------------------------------------------------

def test_planted_forked_supersession_is_refused_naming_the_live_head(tmp_path):
    root = _repo(tmp_path, "squiddy")
    u = _u(root)
    _accept(u, "squiddy", "R-27", "The cost multiple gates every paper.")
    dr.create(u, "supersede", _record("squiddy", "R-29", "The multiple is a reported number.",
                                      supersedes=["squiddy:R-27"]), date=DATE, decided_by="desktop")
    dr.create(u, "supersede", _record("squiddy", "R-81", "A pilot multiple plus the ceiling gates.",
                                      supersedes=["squiddy:R-29"]), date=DATE, decided_by="desktop")
    before = len(list((root / "docs/decisions/register").glob("*.yaml")))
    with pytest.raises(dr.RegisterError) as exc:
        dr.create(u, "supersede", _record("squiddy", "R-90", "Something else gates cost.",
                                          supersedes=["squiddy:R-27"]), date=DATE, decided_by="desktop")
    msg = str(exc.value)
    assert "live head of its chain is squiddy:R-81" in msg, msg
    with pytest.raises(dr.RegisterError, match="live head of its chain is squiddy:R-81"):
        dr.transition(u, "supersede", "squiddy:R-29", date=DATE, decided_by="desktop",
                      reason="again", superseded_by="squiddy:R-81")
    assert len(list((root / "docs/decisions/register").glob("*.yaml"))) == before


def test_planted_supersession_of_a_missing_id_is_refused_and_writes_nothing(tmp_path):
    root = _repo(tmp_path, "squiddy")
    u = _u(root)
    _accept(u, "squiddy", "R-1", "The kit never stores content.")
    with pytest.raises(dr.RegisterError, match="squiddy:R-999 does not exist"):
        dr.create(u, "supersede", _record("squiddy", "R-5", "A new rule.",
                                          supersedes=["squiddy:R-999"]), date=DATE, decided_by="desktop")
    assert len(list((root / "docs/decisions/register").glob("*.yaml"))) == 1


def test_an_id_already_used_and_a_missing_field_are_refused(tmp_path):
    root = _repo(tmp_path, "squiddy")
    u = _u(root)
    _accept(u, "squiddy", "R-1", "The kit never stores content.")
    with pytest.raises(dr.RegisterError, match="already used"):
        _accept(u, "squiddy", "R-1", "Again.")
    rec = _record("squiddy", "R-7", "No rationale.")
    del rec["rationale"]
    with pytest.raises(dr.RegisterError, match="requires rationale"):
        dr.create(u, "accept", rec, date=DATE, decided_by="desktop")
    with pytest.raises(dr.RegisterError, match="waits on"):
        dr.create(u, "propose", _record("squiddy", "R-8", "Unnamed wait."), date=DATE,
                  decided_by="desktop")
    with pytest.raises(dr.RegisterError, match="only with a receipt"):
        dr.create(u, "accept", _record("squiddy", "R-9", "Said so."), date=DATE,
                  decided_by="operator", operator_stated=True)


def test_mirrors_carry_no_statement_and_amend_cannot_point_by_position(tmp_path):
    root = _repo(tmp_path, "squiddy")
    u = _u(root)
    _accept(u, "squiddy", "R-1", "The kit never stores content.")
    m = _record("squiddy", "DI-004", "restated", kind="mirror", mirrors="squiddy:R-1")
    with pytest.raises(dr.RegisterError, match="carries no statement"):
        dr.create(u, "accept", m, date=DATE, decided_by="inherited:wintermute")
    m.pop("statement")
    dr.create(u, "accept", m, date=DATE, decided_by="inherited:wintermute")
    with pytest.raises(dr.RegisterError, match="by position"):
        dr.amend(u, "squiddy:R-1", date=DATE, decided_by="cc:SEL-002", reason="R8",
                 changes={"statement": "As stated above, the kit stores nothing."})
    with pytest.raises(dr.RegisterError, match="fixed at creation"):
        dr.amend(u, "squiddy:R-1", date=DATE, decided_by="cc:SEL-002", reason="x",
                 changes={"source": {"path": "x"}})


def test_cross_repository_supersession_lands_in_the_target_home(tmp_path):
    squiddy = _repo(tmp_path, "squiddy")
    seldon = _repo(tmp_path, "seldon", extra_cfg="  repositories:\n    squiddy: ../squiddy\n")
    _accept(_u(squiddy), "squiddy", "R-4", "The store of truth is declared per graph.")
    u = _u(seldon)
    rec = _record("seldon", "AD-033-R11", "The log is the record of truth.",
                  supersedes=["squiddy:R-4"])
    written = dr.create(u, "supersede", rec, date=DATE, decided_by="operator",
                        operator_stated=True, receipts=["AD-033-R11"])
    assert written[0].parent == seldon / "docs/decisions/register"
    assert written[1].parent == squiddy / "docs/decisions/register"
    assert dr.fold(dr.Register("squiddy", squiddy).events())["squiddy:R-4"].status == "superseded"
    assert dr.Register("squiddy", squiddy).verify() == []


# ---------------------------------------------------------------------------
# labeled decisions after the baseline (AD-033-R2, verify)
# ---------------------------------------------------------------------------

def test_planted_labeled_decision_without_a_record_fails_the_check(tmp_path):
    root = _repo(tmp_path, "squiddy")
    u = _u(root)
    _accept(u, "squiddy", "R-1", "The kit never stores content.")
    dr.write_rendered(_u(root))
    assert dr.check(root, _cfg(root)) == []           # baseline notes owe nothing
    (root / "docs/design/2026-10-05_DN-002_new.md").write_text(
        "# DN-002\n\n## Decisions\n\n- **R-200 (a new rule).** Every call reserves first.\n",
        encoding="utf-8")
    findings = dr.check(root, _cfg(root))
    assert any("squiddy:R-200, which has no record" in x for x in findings), findings
    rec = _record("squiddy", "R-200", "Every call reserves first.")
    rec["rationale"]["path"] = "docs/design/2026-10-05_DN-002_new.md"
    _accept(_u(root), "squiddy", "R-200", "Every call reserves first.",
            rationale={"path": "docs/design/2026-10-05_DN-002_new.md", "anchor": "R-200"})
    dr.write_rendered(_u(root))
    assert dr.check(root, _cfg(root)) == []


def test_a_rationale_that_resolves_to_no_file_is_refused(tmp_path):
    root = _repo(tmp_path, "squiddy")
    with pytest.raises(dr.RegisterError, match="resolves to no file"):
        _accept(_u(root), "squiddy", "R-1", "x", rationale={"path": "docs/nowhere.md"})


def test_rendered_register_drift_fails_the_check(tmp_path):
    root = _repo(tmp_path, "squiddy")
    _accept(_u(root), "squiddy", "R-1", "The kit never stores content.")
    path = dr.write_rendered(_u(root))
    path.write_text(path.read_text() + "\nhand edit\n", encoding="utf-8")
    assert any("REGISTER.md" in x for x in dr.check(root, _cfg(root)))


# ---------------------------------------------------------------------------
# binding at registration (AD-033-R7)
# ---------------------------------------------------------------------------

def test_planted_arnold_registration_resolves_squiddy_r112(tmp_path):
    squiddy = _repo(tmp_path, "squiddy")
    arnold = _repo(tmp_path, "arnold", imports=("squiddy",))
    _accept(_u(squiddy), "squiddy", "R-112", "The extraction valve for future graphs is closed by default.")
    _accept(_u(arnold), "arnold", "ADR-017", "No remote-model dependencies in served components.")
    u = _u(arnold)
    for text in ("Plan the KG-004 step under squiddy:R-112.", "Plan the KG-004 step under R-112."):
        got = dr.bind(u, text, threshold=0.99)
        assert [m.id for m in got if m.match_method == "identifier"] == ["squiddy:R-112"], (text, got)
    assert dr.ADVISORY in dr.render_binding(dr.bind(u, "nothing relevant zzz", 0.99), 0)


def test_planted_superseded_record_never_binds_the_r29_case(tmp_path):
    root = _repo(tmp_path, "squiddy")
    u = _u(root)
    _accept(u, "squiddy", "R-29", "The cost multiple stays a reported number under a control chart.")
    dr.create(u, "supersede", _record("squiddy", "R-32", "The control chart of R-29 is withdrawn.",
                                      supersedes=["squiddy:R-29"]), date=DATE, decided_by="desktop")
    text = "SQ-009 cost multiple reported number control chart spend; see R-29 and R-32."
    got = [m.id for m in dr.bind(_u(root), text, threshold=0.1)]
    assert "squiddy:R-29" not in got and "squiddy:R-32" in got, got


def test_the_decision_label_joins_the_owned_label_set():
    assert "Decision" in SELDON_OWNED_LABELS


# ---------------------------------------------------------------------------
# CLI and MCP refuse identically
# ---------------------------------------------------------------------------

def test_cli_and_mcp_give_the_same_refusal(tmp_path, monkeypatch):
    from seldon.commands.decision import decision_group
    from seldon.mcp_server import seldon_decision_supersede

    root = _repo(tmp_path, "squiddy")
    u = _u(root)
    _accept(u, "squiddy", "R-27", "Gate every paper.")
    dr.create(u, "supersede", _record("squiddy", "R-29", "Report the number.",
                                      supersedes=["squiddy:R-27"]), date=DATE, decided_by="desktop")
    _accept(u, "squiddy", "R-81", "Pilot multiple.")
    monkeypatch.chdir(root)
    res = CliRunner().invoke(decision_group, ["supersede", "squiddy:R-27", "--by", "squiddy:R-81",
                                              "--decided-by", "desktop", "--reason", "x"])
    assert res.exit_code == 1
    mcp = seldon_decision_supersede(decided_by="desktop", project_dir=str(root),
                                    record_id="squiddy:R-27", superseded_by="squiddy:R-81",
                                    reason="x")
    assert "live head of its chain is squiddy:R-29" in mcp
    assert "live head of its chain is squiddy:R-29" in (res.output + (res.stderr if res.stderr_bytes else ""))


# ---------------------------------------------------------------------------
# the projection (Neo4j)
# ---------------------------------------------------------------------------

@neo4j_tests
def test_projection_leaves_legacy_decision_nodes_unchanged(tmp_path, neo4j_driver, clean_test_db,
                                                           monkeypatch):
    from seldon.core.artifacts import create_artifact
    from seldon.domain.loader import load_domain_config

    domain = load_domain_config(Path(dr.__file__).parent.parent / "domain" / "research.yaml")
    squiddy = _repo(tmp_path, "squiddy", database=NEO4J_DB)
    monkeypatch.chdir(squiddy)
    for t, name in (("ArchitecturalDecision", "AD-013"), ("DesignNote", "DN-legacy")):
        props = {"name": name, "title": name, "description": name, "path": f"docs/design/{name}.md",
                 "decision": "legacy", "rationale": "legacy", "status": "accepted",
                 "date": DATE, "context": "c", "content_hash": "0" * 64}
        req = domain.get_required_properties(t)
        create_artifact(project_dir=squiddy, driver=neo4j_driver, database=NEO4J_DB,
                        domain_config=domain, artifact_type=t,
                        properties={k: props.get(k, "x") for k in set(req) | {"name"}},
                        actor="human", authority="accepted")

    def legacy_counts():
        with neo4j_driver.session(database=NEO4J_DB) as s:
            return s.run("MATCH (a:Artifact) WHERE a.artifact_type IN "
                         "['ArchitecturalDecision','DesignNote'] "
                         "RETURN a.artifact_type AS t, count(a) AS n, "
                         "collect(a.updated_at) AS u ORDER BY t").data()

    before = legacy_counts()
    u = _u(squiddy)
    _accept(u, "squiddy", "R-29", "The multiple is a reported number.")
    dr.create(u, "supersede", _record("squiddy", "R-32", "The chart is withdrawn.",
                                      supersedes=["squiddy:R-29"]), date=DATE, decided_by="desktop")
    rep = dr.project(project_dir=squiddy, config=_cfg(squiddy), driver=neo4j_driver,
                     database=NEO4J_DB, domain_config=domain)
    assert rep.created == 2
    assert legacy_counts() == before
    with neo4j_driver.session(database=NEO4J_DB) as s:
        rows = s.run("MATCH (d:Decision) RETURN d.decision_id AS q, d.state AS st, "
                     "labels(d) AS l ORDER BY q").data()
        sup = s.run("MATCH (a:Artifact:Decision)-[:SUPERSEDES]->(b:Artifact:Decision) "
                    "RETURN a.decision_id AS a, b.decision_id AS b").data()
    assert [(r["q"], r["st"]) for r in rows] == [("squiddy:R-29", "superseded"),
                                                ("squiddy:R-32", "accepted")]
    assert all("Artifact" in r["l"] for r in rows)
    assert sup == [{"a": "squiddy:R-32", "b": "squiddy:R-29"}]
    again = dr.project(project_dir=squiddy, config=_cfg(squiddy), driver=neo4j_driver,
                       database=NEO4J_DB, domain_config=domain)
    assert (again.created, again.updated, again.unchanged) == (0, 0, 2)


@neo4j_tests
def test_cc_register_binds_accepted_decisions_only_and_says_advisory(tmp_path, neo4j_driver,
                                                                    clean_test_db, monkeypatch):
    from seldon.commands.cc import constraining_rulings, render_rulings
    from seldon.core.artifacts import create_artifact
    from seldon.domain.loader import load_domain_config

    domain = load_domain_config(Path(dr.__file__).parent.parent / "domain" / "research.yaml")
    squiddy = _repo(tmp_path, "squiddy", database=NEO4J_DB)
    monkeypatch.chdir(squiddy)
    u = _u(squiddy)
    _accept(u, "squiddy", "R-29", "The cost multiple stays a reported number under a control chart.")
    dr.create(u, "supersede", _record("squiddy", "R-32", "The control chart is withdrawn; cost is "
                                      "gated by the ceiling.", supersedes=["squiddy:R-29"]),
              date=DATE, decided_by="desktop")
    dr.project(project_dir=squiddy, config=_cfg(squiddy), driver=neo4j_driver, database=NEO4J_DB,
               domain_config=domain)
    task = squiddy / "task.md"
    task.write_text("# SQ-009\nDN-042: the cost multiple, the control chart, the ceiling; R-29.\n")
    tid = create_artifact(project_dir=squiddy, driver=neo4j_driver, database=NEO4J_DB,
                          domain_config=domain, artifact_type="ResearchTask",
                          properties={"description": "t"}, actor="cc", authority="accepted")
    matches, written = constraining_rulings(project_dir=squiddy, config=_cfg(squiddy),
                                            driver=neo4j_driver, database=NEO4J_DB,
                                            domain_config=domain, task_path=task, task_id=tid,
                                            session_id=None)
    ids = [m.id for m in matches]
    assert "squiddy:R-29" not in ids and "squiddy:R-32" in ids
    assert written == len(ids)
    assert "advisory until SEL-003" in render_rulings(matches, written)


# ---------------------------------------------------------------------------
# the conflicts probe on the register (AD-033-R9): positive controls before its verdict is cited
# ---------------------------------------------------------------------------

def _findings(path: Path, rows: list[dict]) -> Path:
    path.write_text("".join(__import__("json").dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def test_planted_silent_supersession_is_caught_by_the_probe(tmp_path):
    root = _repo(tmp_path, "squiddy")
    u = _u(root)
    _accept(u, "squiddy", "R-1", "The multiple stays a reported number.")
    _accept(u, "squiddy", "R-2", "The control chart of R-1 is withdrawn.")
    rep = dr.conflicts_probe(_u(root), None, None)
    assert [(p["record"], p["cites"]) for p in rep.unrecorded_pairs] == [("squiddy:R-2", "squiddy:R-1")]
    assert not rep.clean
    excl = tmp_path / "excl.yaml"
    excl.write_text("- {record: 'squiddy:R-2', cites: 'squiddy:R-1', reason: reviewed}\n")
    assert dr.conflicts_probe(_u(root), None, excl).clean
    dr.transition(_u(root), "supersede", "squiddy:R-1", date=DATE, decided_by="cc:x",
                  reason="Probe F99: recorded", superseded_by="squiddy:R-2")
    assert dr.conflicts_probe(_u(root), None, None).clean


def test_planted_open_contradiction_is_caught_by_the_probe(tmp_path):
    root = _repo(tmp_path, "squiddy")
    u = _u(root)
    _accept(u, "squiddy", "R-1", "Extraction is the only stage that calls a model.")
    _accept(u, "squiddy", "R-2", "A model call may choose among the returned descriptors.")
    f = _findings(tmp_path / "c.jsonl", [{"finding": "F99", "class": "CONTRADICTION",
                                          "ids": ["R-1", "R-2"], "evidence": []}])
    rep = dr.conflicts_probe(_u(root), f, None)
    assert rep.open_contradictions == ["F99: R-1, R-2"]
    dr.amend(_u(root), "squiddy:R-1", date=DATE, decided_by="cc:x", reason="Probe F99 (CONTRADICTION): amend",
             amendment={"clause": "only stage", "text": "model nodes are declared", "by": "squiddy:R-2"})
    rep = dr.conflicts_probe(_u(root), f, None)
    assert rep.open_contradictions == [] and rep.resolved == {"F99": ["squiddy:R-1"]}
