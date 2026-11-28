"""SEL-063 Part A: recall and the graph (REVIEW-001 F-23 to F-27).

- F-23: `seldon cc rederive-description` past `--dry-run` named `update_artifact`, which `commands/cc.py` never
  imported, so it raised NameError after printing its plan.
- F-24: recall's stage 4 (dead ends) read the Issue threshold, not its own kind's, which seldon.yaml sets to null.
- F-25: `recall_audit` dated a RESULT's landing by the file's mtime, which a clone or rebase resets.
- F-26: `recall_audit`'s checkpoint key left out the recall block, so a changed block resumed stale rows.
- F-27: `seldon verify --fix` ended the edge from a completed task to a record superseded since (the record of what
  bound it when it ran), and read the projected state, which leaves out a branch's pending acceptances.

Each test here fails at the branch's base (`1c8d372`).
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from seldon.core import decisions as dr
from seldon.core import recall as R
from seldon.core import recall_audit as A
from tests.testdb import TEST_DATABASE


def _git(cwd: Path, *args: str, date: str | None = None) -> str:
    env = dict(os.environ)
    if date:
        env.update(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=env)
    assert r.returncode == 0, (args, r.stdout, r.stderr)
    return r.stdout


def _repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t"], ["config", "user.name", "t"],
                 ["config", "core.hooksPath", "/dev/null"]):
        _git(root, *args)
    return root


# ------------------------------------------------------------------------------------------------ F-23

@pytest.mark.usefixtures("neo4j_available")
def test_part_a_rederive_description_writes_past_the_dry_run(tmp_path, neo4j_driver, clean_test_db, monkeypatch):
    from seldon.commands.cc import cc_group
    from seldon.core.artifacts import create_artifact
    from seldon.domain.loader import load_domain_config

    root = tmp_path / "p"
    (root / "cc_tasks").mkdir(parents=True)
    (root / "seldon.yaml").write_text(yaml.safe_dump({
        "project": {"name": "p", "domain": "research"}, "event_store": {"path": "seldon_events.jsonl"},
        "neo4j": {"uri": os.getenv("NEO4J_URI", "bolt://localhost:7687"), "database": TEST_DATABASE}}))
    rel = "cc_tasks/2026-11-28_X-1_the_derived_title.md"
    (root / rel).write_text("# X-1: the derived title\n\nBody.\n", encoding="utf-8")
    domain = load_domain_config(Path(dr.__file__).parent.parent / "domain" / "research.yaml")
    req = domain.get_required_properties("ResearchTask")
    aid = create_artifact(project_dir=root, driver=neo4j_driver, database=TEST_DATABASE, domain_config=domain,
                          artifact_type="ResearchTask",
                          properties={**{k: "x" for k in req}, "name": "X-1", "description": "a stale description",
                                      "source_file": rel},
                          actor="human", authority="accepted")
    monkeypatch.chdir(root)
    out = CliRunner().invoke(cc_group, ["rederive-description", aid])
    assert out.exit_code == 0, (out.output, out.exception)
    assert "artifact_updated event written" in out.output
    with neo4j_driver.session(database=TEST_DATABASE) as s:
        got = s.run("MATCH (t:ResearchTask {artifact_id: $a}) RETURN t.description AS d", a=aid).single()["d"]
    assert got == "X-1: the derived title"


# ------------------------------------------------------------------------------------------------ F-24

SELECTION = {
    "mode": "touch", "noise_paths": ["seldon_events.jsonl", "cc_tasks/*"], "max_citing_share": 0.5,
    "max_tasks_per_file": 5, "max_file_hits": 2, "max_issue_hits": 1, "dead_end_days": 30,
    "lexical_min_shared_terms": {"result": None, "issue": 3, "decision": 3, "catch": 3, "worktree_kept": None,
                                 "superseded": None},
}
BLOCK = {"top_n": 8, "min_shared_terms": 2, "max_file_bytes": 2000000, "headline_chars": 120,
         "result_globs": ["cc_tasks/*_RESULT*.md"], "failure_terms": ["fail"], "bm25": {"k1": 1.2, "b": 0.75},
         "served": {"enabled": False, "k": 20, "rrf_k": 60, "graphs": {}}}
WORDS = "frobnicator calibration oscillator drift pinned measured load"


def _dead_end_hits(tmp_path: Path, worktree_kept_threshold) -> list:
    root = _repo(tmp_path / "demo")
    (root / "seldon.yaml").write_text("project: {name: demo}\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "init", date="2026-01-01T12:00:00")
    block = {**SELECTION, "lexical_min_shared_terms": {
        **SELECTION["lexical_min_shared_terms"], "worktree_kept": worktree_kept_threshold}}
    s = R.settings({"recall": {**BLOCK, "selection": block}}, root)
    sel = s.selection
    cands = [
        # A kept task of the same prefix, recent, sharing every word of the task and no file.
        R.Candidate(kind="worktree_kept", id="demo:2026-01-25_TASK-009_kept", date="2026-01-25",
                    headline="TASK-009 kept", repo="demo", text=f"{WORDS} {WORDS}", reason="merge_blocked"),
        R.Candidate(kind="issue", id="demo:issue-1", date="2026-01-20", headline="unrelated", repo="demo",
                    text="lattice quaternion"),
        R.Candidate(kind="result", id="demo:2026-01-02_TASK-002_beta_RESULT", date="2026-01-02",
                    headline="beta", repo="demo", text="something else entirely",
                    path="cc_tasks/2026-01-02_TASK-002_beta_RESULT.md"),
    ]
    task = f"# TASK-010 {WORDS}\n\n## Part A: the oscillator drift\n"
    return R._touch_hits(root, "demo", task, "2026-02-01_TASK-010_frob", R.query_of(task), cands, s, sel, [],
                         "2026-02-01")


def test_part_a_a_dead_end_is_held_to_its_own_kinds_threshold_not_the_issues(tmp_path):
    # seldon.yaml sets worktree_kept to null: no lexical reason. The Issue threshold (3 here) must not stand in.
    assert [h.id for h in _dead_end_hits(tmp_path, None)] == []


def test_part_a_a_dead_end_kind_with_a_threshold_still_gets_through_on_shared_words(tmp_path):
    hits = _dead_end_hits(tmp_path, 3)
    assert [h.id for h in hits] == ["demo:2026-01-25_TASK-009_kept"]
    assert hits[0].arms == ["dead_end"]


# ------------------------------------------------------------------------------------------- F-25, F-26

RESULT_REL = "cc_tasks/2026-01-02_TASK-002_beta_RESULT.md"
REPLAY_SELECTION = {"mode": "touch", "noise_paths": ["cc_tasks/*"], "max_citing_share": 1.0, "max_tasks_per_file": 5,
                    "max_file_hits": 1, "max_issue_hits": 0, "dead_end_days": 30,
                    "lexical_min_shared_terms": {"result": None}}
HIT = "demo:2026-01-02_TASK-002_beta_RESULT"


def _log(path: Path, ts: str) -> None:
    import json
    path.parent.mkdir(parents=True, exist_ok=True)
    tool = json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Read", "input": {"file_path": f"/x/{RESULT_REL}"}}]}})
    path.write_text(f"=== {ts} | dispatch | claude -p 'Read CLAUDE.md, then execute it.'\n{tool}\n", encoding="utf-8")


def _replay_repo(tmp_path: Path, result_committed: str, n: int = 1) -> Path:
    """A repository whose RESULT reached history at `result_committed`, and `n` sessions launched in 2026-02."""
    root = _repo(tmp_path / "demo")
    (root / "seldon.yaml").write_text(yaml.safe_dump({"project": {"name": "demo"},
                                                      "dispatch": {"log_dir": "logs/dispatch"}}))
    (root / "seldon_events.jsonl").write_text("")
    for i in range(n):
        stem = f"2026-02-{i + 1:02d}_TASK-1{i:02d}_t"
        (root / "cc_tasks").mkdir(exist_ok=True)
        (root / "cc_tasks" / f"{stem}.md").write_text("# TASK\nFollows TASK-002.\n")
        _log(root / "logs" / "dispatch" / f"{stem}.log", f"2026-02-{i + 1:02d}T10:00:00Z")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "tasks", date="2026-01-01T12:00:00Z")
    (root / RESULT_REL).write_text("# RESULT: TASK-002\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "TASK-002 result", date=result_committed)
    return root


def test_part_a_a_result_committed_before_the_launch_is_found_whatever_its_mtime(tmp_path):
    root = _replay_repo(tmp_path, "2026-01-02T12:00:00Z")
    # A clone or a rebase writes the file now: after the 2026-02 launch.
    os.utime(root / RESULT_REL, None)
    rows = A.replay_repository("demo", root, BLOCK, REPLAY_SELECTION, 30, tmp_path / "ck.jsonl",
                               progress=lambda m: None)
    assert [h["id"] for h in rows[0]["new"]] == [HIT]


def test_part_a_a_result_committed_after_the_launch_is_not_found_whatever_its_mtime(tmp_path):
    root = _replay_repo(tmp_path, "2026-03-01T12:00:00Z")
    os.utime(root / RESULT_REL, (1, 1))   # an old mtime, which the old code believed
    rows = A.replay_repository("demo", root, BLOCK, REPLAY_SELECTION, 30, tmp_path / "ck.jsonl",
                               progress=lambda m: None)
    assert rows[0]["new"] == []


def test_part_a_landing_times_come_from_the_first_commit_that_added_each_file(tmp_path):
    root = _replay_repo(tmp_path, "2026-01-02T12:00:00Z")
    (root / RESULT_REL).write_text("# RESULT: TASK-002, edited later\n")
    _git(root, "commit", "-qam", "edit", date="2026-04-01T00:00:00Z")
    untracked = "cc_tasks/2026-01-05_TASK-005_x_RESULT.md"
    (root / untracked).write_text("# not committed\n")
    os.utime(root / untracked, (1000, 1000))
    got = A.landed_times(root, [RESULT_REL, untracked])
    assert got[RESULT_REL] == A._epoch("2026-01-02T12:00:00Z")
    assert got[untracked] == 1000.0      # never committed: the file's own time is all there is


def test_part_a_a_changed_recall_block_does_not_resume_the_old_rows(tmp_path):
    """Constitution section 15 point 2: the key is derived from every input that decides a row."""
    root = _replay_repo(tmp_path, "2026-01-02T12:00:00Z", n=2)
    ck = tmp_path / "ck.jsonl"
    seen: list = []
    A.replay_repository("demo", root, BLOCK, REPLAY_SELECTION, 30, ck, progress=seen.append)
    assert len(seen) == 2
    seen.clear()
    A.replay_repository("demo", root, BLOCK, REPLAY_SELECTION, 30, ck, progress=seen.append)
    assert seen == []                                   # unchanged inputs: resumed, nothing recomputed
    A.replay_repository("demo", root, {**BLOCK, "top_n": 1}, REPLAY_SELECTION, 30, ck, progress=seen.append)
    assert len(seen) == 2                               # a changed block: every unit recomputed


# ------------------------------------------------------------------------------------------------ F-27

NOTE = "docs/design/2026-09-01_DN-001_first.md"
NOTE_TEXT = "# DN-001 first\n\n## R-1 First\n\nThe first ruling.\n\n## R-2 Second\n\nThe second ruling.\n"


def _record(local: str, line: int, text: str) -> dict:
    return {"id": f"proj:{local}", "kind": "decision", "statement": text,
            "source": {"path": NOTE, "lines": [line, line + 2],
                       "text": "\n".join(NOTE_TEXT.splitlines()[line - 1:line + 2])},
            "scope": ["proj"], "rationale": {"path": NOTE, "anchor": local}, "review_only": "none"}


def _cfg(root: Path) -> dict:
    return yaml.safe_load((root / "seldon.yaml").read_text(encoding="utf-8"))


def _register_tree(tmp_path: Path) -> tuple[Path, Path]:
    """A primary whose register holds proj:R-1 accepted and proj:R-2 proposed, and a linked worktree whose pending
    record accepts proj:R-2."""
    root = tmp_path / "proj"
    (root / "docs" / "design").mkdir(parents=True)
    (root / NOTE).write_text(NOTE_TEXT, encoding="utf-8")
    (root / "seldon.yaml").write_text(yaml.safe_dump({
        "project": {"name": "proj", "domain": "research"}, "event_store": {"path": "seldon_events.jsonl"},
        "neo4j": {"database": TEST_DATABASE},
        "decisions": {"repository": "proj", "design_notes": [
            {"glob": "docs/design/*.md", "pattern": r"^(?:#+\s*|\s*[-*]\s*\*\*|\*\*)(R-\d{1,3})\b",
             "id": "{repo}:{label}"}]}}), encoding="utf-8")
    (root / ".gitignore").write_text("seldon_events.jsonl\ndocs/decisions/.register.lock\n", encoding="utf-8")
    _repo(root)
    dr.create(dr.universe(root, _cfg(root)), "accept", _record("R-1", 3, "The first ruling."), date="2026-11-28",
              decided_by="desktop")
    dr.create(dr.universe(root, _cfg(root)), "propose", {**_record("R-2", 7, "The second ruling."),
                                                          "waits_on": "its pilot"},
              date="2026-11-28", decided_by="desktop")
    dr.write_rendered(dr.universe(root, _cfg(root)))
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base")
    wt = tmp_path / "wt"
    _git(root, "worktree", "add", "-q", "-b", "b", str(wt))
    dr.transition(dr.universe(wt, _cfg(wt)), "accept", "proj:R-2", date="2026-11-28", decided_by="desktop",
                  reason="the pilot passed")
    assert len(dr.Register("proj", wt).pending_files()) == 1
    return root, wt


def test_part_a_a_pending_acceptance_is_read_from_the_register(tmp_path):
    root, wt = _register_tree(tmp_path)
    assert dr.pending_acceptances(wt, _cfg(wt)) == {"proj:R-2"}
    assert dr.pending_acceptances(root, _cfg(root)) == set()       # the primary holds no pending record


def test_part_a_a_project_with_no_register_has_no_pending_acceptance(tmp_path):
    (tmp_path / "seldon.yaml").write_text("project: {name: bare}\n")
    assert dr.pending_acceptances(tmp_path, _cfg(tmp_path)) == set()


@pytest.mark.usefixtures("neo4j_available")
def test_part_a_verify_fix_ends_only_open_tasks_edges_and_keeps_a_pending_acceptance(tmp_path, neo4j_driver,
                                                                                    clean_test_db):
    from seldon.core.artifacts import create_artifact, create_link
    from seldon.core.events import read_events
    from seldon.domain.loader import load_domain_config

    domain = load_domain_config(Path(dr.__file__).parent.parent / "domain" / "research.yaml")
    root = tmp_path / "p"
    root.mkdir()

    def node(t, props, state=None):
        req = domain.get_required_properties(t)
        aid = create_artifact(project_dir=root, driver=neo4j_driver, database=TEST_DATABASE, domain_config=domain,
                              artifact_type=t, properties={**{k: "x" for k in req}, **props},
                              actor="human", authority="accepted")
        if state:
            with neo4j_driver.session(database=TEST_DATABASE) as s:
                s.run("MATCH (n:Artifact {artifact_id: $a}) SET n.state = $st", a=aid, st=state)
        return aid

    open_task = node("ResearchTask", {"name": "T-open"}, "in_progress")
    done_task = node("ResearchTask", {"name": "T-done"}, "completed")
    verified_task = node("ResearchTask", {"name": "T-verified"}, "verified")
    old = node("Decision", {"name": "proj:OLD", "decision_id": "proj:OLD"}, "superseded")
    pend = node("Decision", {"name": "proj:R-2", "decision_id": "proj:R-2"}, "proposed")
    for t in (open_task, done_task, verified_task):
        for d in (old, pend):
            create_link(project_dir=root, driver=neo4j_driver, database=TEST_DATABASE, domain_config=domain,
                        from_id=t, to_id=d, from_type="ResearchTask", to_type="Decision", rel_type="constrained_by",
                        actor="human", authority="accepted")
    rows = dr.non_binding_decision_edges(neo4j_driver, TEST_DATABASE, domain_config=domain,
                                         pending_accepted={"proj:R-2"})
    # The completed and verified tasks keep both edges as the record of what bound them when they ran; the open
    # task's edge to the record a pending acceptance makes binding stays too.
    assert [(r["task_name"], r["decision_id"]) for r in rows] == [("T-open", "proj:OLD")]
    removed = dr.prune_non_binding_decision_edges(project_dir=root, driver=neo4j_driver, database=TEST_DATABASE,
                                                  domain_config=domain, pending_accepted={"proj:R-2"})
    assert [(r["task_name"], r["decision_id"]) for r in removed] == [("T-open", "proj:OLD")]
    with neo4j_driver.session(database=TEST_DATABASE) as s:
        left = s.run("MATCH (t:ResearchTask)-[:CONSTRAINED_BY]->(d:Decision) "
                     "RETURN t.name AS t, d.decision_id AS d ORDER BY t, d").data()
    assert [(r["t"], r["d"]) for r in left] == [("T-done", "proj:OLD"), ("T-done", "proj:R-2"),
                                                ("T-open", "proj:R-2"), ("T-verified", "proj:OLD"),
                                                ("T-verified", "proj:R-2")]
    assert [e["event_type"] for e in read_events(root)].count("link_removed") == 1
