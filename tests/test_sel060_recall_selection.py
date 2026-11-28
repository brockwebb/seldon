"""SEL-060 Part B (AD-031-R5, R6): recall hands the hits a session has reason to open, each with why.

SEL-060 Part A counted 2,264 hits handed to 286 sessions: a RESULT the task cited was opened 43.8% of the time, one it
did not cite 2.2%, and two-thirds of every list was the second kind. These tests pin the selection that replaces it:
cited first, then the earlier task that changed the same files, then lexical hits only of kinds whose threshold is set,
and a list that may be empty. On main before SEL-060, `recall.selection`, `Hit.why` and `recall: {ref: ...}` do not
exist, so every test here fails there.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from seldon.core import recall as R

BASE = {
    "top_n": 8, "min_shared_terms": 2, "max_file_bytes": 2000000, "headline_chars": 120,
    "result_globs": ["cc_tasks/*_RESULT*.md"], "failure_terms": ["fail", "blocked"],
    "bm25": {"k1": 1.2, "b": 0.75}, "served": {"enabled": False, "k": 20, "rrf_k": 60, "graphs": {}},
}
SELECTION = {
    "mode": "touch", "noise_paths": ["seldon_events.jsonl", "cc_tasks/*"], "max_citing_share": 0.5,
    "max_tasks_per_file": 5, "max_file_hits": 2, "max_issue_hits": 1, "dead_end_days": 30,
    "lexical_min_shared_terms": {"result": None, "issue": 3, "decision": 3, "catch": 3, "worktree_kept": None,
                                 "superseded": None},
}


def _git(cwd: Path, *args: str, env: dict | None = None) -> None:
    import os

    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                   env={**os.environ, **(env or {})})


def _commit(repo: Path, message: str, files: dict, date: str = "2026-01-20T12:00:00") -> None:
    """A commit dated `date` (the replay reads history `--until` a task's day)."""
    for rel, text in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", message, env={"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date})


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        _git(tmp_path, *args)
    (tmp_path / "seldon_events.jsonl").write_text("", encoding="utf-8")
    _commit(tmp_path, "init", {"seldon.yaml": yaml.safe_dump({"project": {"name": "demo"}})}, "2025-12-31T12:00:00")
    # TASK-001 changed src/alpha.py; TASK-002 changed src/beta.py; both left a RESULT that shares many words with
    # the new task, which is what the lexical selection would have ranked.
    words = "frobnicator calibration oscillator drift pinned measured load"
    _commit(tmp_path, "TASK-001 Part A: alpha", {
        "src/alpha.py": "x = 1\n",
        "cc_tasks/2026-01-01_TASK-001_alpha.md": "# TASK-001 alpha\n",
        "cc_tasks/2026-01-01_TASK-001_alpha_RESULT.md": f"# RESULT: TASK-001 alpha\n{words}\n"}, "2026-01-01T12:00:00")
    _commit(tmp_path, "TASK-002 Part A: beta", {
        "src/beta.py": "y = 2\n",
        "cc_tasks/2026-01-02_TASK-002_beta.md": "# TASK-002 beta\n",
        "cc_tasks/2026-01-02_TASK-002_beta_RESULT.md": f"# RESULT: TASK-002 beta\n{words}\n"}, "2026-01-02T12:00:00")
    _commit(tmp_path, "TASK-003 Part A: gamma, a lexical twin", {
        "src/gamma.py": "z = 3\n",
        "cc_tasks/2026-01-03_TASK-003_gamma.md": "# TASK-003 gamma\n",
        "cc_tasks/2026-01-03_TASK-003_gamma_RESULT.md": f"# RESULT: TASK-003 gamma\n{words} {words}\n"},
            "2026-01-03T12:00:00")
    return tmp_path


def _config(selection=SELECTION) -> dict:
    block = dict(BASE)
    if selection is not None:
        block["selection"] = selection
    return {"project": {"name": "demo"}, "recall": block}


NEW_TASK = """# TASK-010 frobnicator calibration oscillator drift measured under load

**Parts:** A 1.0

It follows TASK-002, and it changes `src/alpha.py`.

## Part A: the oscillator drift
"""


def test_cited_then_files_then_nothing_lexical_for_results(repo: Path):
    r = R.recall(repo, _config(), NEW_TASK, task_stem="2026-02-01_TASK-010_frob")
    ids = [h.id for h in r.hits]
    assert ids == ["demo:2026-01-02_TASK-002_beta_RESULT", "demo:2026-01-01_TASK-001_alpha_RESULT"]
    why = {h.id: h.why for h in r.hits}
    assert why["demo:2026-01-02_TASK-002_beta_RESULT"] == "the task cites TASK-002"
    assert why["demo:2026-01-01_TASK-001_alpha_RESULT"] == "TASK-001 changed src/alpha.py"
    # TASK-003 shares the most words and is not cited and changed nothing the task names: Part A's 2.2% row.
    assert "demo:2026-01-03_TASK-003_gamma_RESULT" not in ids


def test_lexical_mode_is_recall_001_unchanged(repo: Path):
    r = R.recall(repo, _config(selection=None), NEW_TASK, task_stem="2026-02-01_TASK-010_frob")
    assert r.hits and r.hits[0].id == "demo:2026-01-03_TASK-003_gamma_RESULT"
    assert all(h.why == "" for h in r.hits)
    r2 = R.recall(repo, _config(), NEW_TASK, task_stem="2026-02-01_TASK-010_frob", selection={"mode": "lexical"})
    assert [h.id for h in r2.hits] == [h.id for h in r.hits]


def test_a_task_with_no_reason_gets_none(repo: Path):
    text = "# TASK-011 a quaternion lattice\n\n## Part A: lattice\n"
    r = R.recall(repo, _config(), text, task_stem="2026-02-02_TASK-011_lattice")
    assert r.hits == []
    assert R.render(r).startswith("Recall: none")


def test_a_template_citation_is_not_a_reason(repo: Path):
    # Three of the four task files cite TASK-002 (0.75 > 0.5): it is the template's, not this task's.
    for n in (4, 5):
        _commit(repo, f"TASK-00{n}", {f"cc_tasks/2026-01-0{n}_TASK-00{n}_x.md": "# x\nPer TASK-002.\n"})
    r = R.recall(repo, _config(), NEW_TASK, task_stem="2026-02-01_TASK-010_frob")
    assert "demo:2026-01-02_TASK-002_beta_RESULT" not in [h.id for h in r.hits]
    assert any("not a reason: TASK-002" in n for n in r.notes)


def test_a_file_every_task_changed_names_no_history(repo: Path):
    sel = {**SELECTION, "max_tasks_per_file": 1}
    _commit(repo, "TASK-004 also alpha", {"src/alpha.py": "x = 4\n",
                                          "cc_tasks/2026-01-04_TASK-004_a_RESULT.md": "# RESULT: TASK-004\n"})
    r = R.recall(repo, _config(sel), NEW_TASK, task_stem="2026-02-01_TASK-010_frob")
    assert [h.why for h in r.hits] == ["the task cites TASK-002"]


def test_as_of_hides_what_came_later(repo: Path):
    r = R.recall(repo, _config(), NEW_TASK, task_stem="2026-02-01_TASK-010_frob", as_of="2026-01-01")
    assert [h.id for h in r.hits] == ["demo:2026-01-01_TASK-001_alpha_RESULT"]


def test_why_is_a_second_line_and_old_payloads_still_render():
    h = R.Hit(kind="result", id="demo:x", date="2026-01-01", headline="H", repo="demo", path=None, status=None,
              dead_end=False, score=1.0, shared_terms=[], arms=["cited"], why="the task cites X-1")
    assert h.line() == "  - result  demo:x  2026-01-01  H\n      why: the task cites X-1"
    old = {k: v for k, v in h.__dict__.items() if k != "why"}
    block = R.prompt_block({"hits": [old]})
    assert "  - result  demo:x  2026-01-01  H\n" in block and "why:" not in block


@pytest.mark.parametrize("bad, says", [
    ({"mode": "nearest"}, "mode must be one of"),
    ({"mode": "touch"}, "is missing"),
    ({**SELECTION, "max_citing_share": 0}, "max_citing_share"),
    ({**SELECTION, "lexical_min_shared_terms": {"result": 0}}, "lexical_min_shared_terms"),
    ({**SELECTION, "lexical_min_shared_terms": {"novel": 3}}, "lexical_min_shared_terms"),
])
def test_a_malformed_selection_is_refused(bad, says):
    with pytest.raises(R.RecallError, match=says):
        R.settings(_config(bad))


def test_a_block_by_reference_with_local_overrides(tmp_path: Path):
    kit = tmp_path / "kit"
    kit.mkdir()
    (kit / "seldon.yaml").write_text(yaml.safe_dump({"recall": {**BASE, "selection": SELECTION, "top_n": 5}}))
    me = tmp_path / "me"
    me.mkdir()
    cfg = {"recall": {"ref": "../kit/seldon.yaml#recall", "top_n": 3}}
    s = R.settings(cfg, me)
    assert s.top_n == 3 and s.selection["mode"] == "touch" and s.k1 == 1.2
    with pytest.raises(R.RecallError, match="does not exist"):
        R.settings({"recall": {"ref": "../nowhere/seldon.yaml#recall"}}, me)
    with pytest.raises(R.RecallError, match="has no 'nope'"):
        R.settings({"recall": {"ref": "../kit/seldon.yaml#nope"}}, me)


def test_project_new_writes_the_reference_once(tmp_path: Path):
    from seldon.core import project_new as PN

    kit = tmp_path / "kit"
    kit.mkdir()
    (kit / "seldon.yaml").write_text(yaml.safe_dump({"recall": {**BASE, "selection": SELECTION}}))
    me = tmp_path / "me"
    me.mkdir()
    _git(me, "init", "-q", "-b", "main")
    (me / "seldon.yaml").write_text("project:\n  name: me\n", encoding="utf-8")
    cfg = {"_kit": yaml.safe_load((kit / "seldon.yaml").read_text())}
    step = PN.recall_step(me, cfg, kit)
    assert step.status == "changed"
    written = yaml.safe_load((me / "seldon.yaml").read_text())
    assert written["recall"]["ref"] == "../kit/seldon.yaml#recall"
    assert written["recall"]["served"]["enabled"] is False
    s = R.settings(written, me)
    assert s.selection["mode"] == "touch" and s.served_enabled is False
    assert PN.recall_step(me, cfg, kit).status == "ok"


def test_project_new_skips_a_kit_without_a_block_and_refuses_a_kit_reference(tmp_path: Path):
    from seldon.core import project_new as PN

    me = tmp_path / "me"
    me.mkdir()
    (me / "seldon.yaml").write_text("project:\n  name: me\n", encoding="utf-8")
    assert PN.recall_step(me, {"_kit": {}}, tmp_path).status == "skipped"
    assert "recall" not in yaml.safe_load((me / "seldon.yaml").read_text())
    with pytest.raises(PN.ProjectNewError, match="not a definition"):
        PN.recall_step(me, {"_kit": {"recall": {"ref": "x#recall"}}}, tmp_path)


def test_seldons_own_block_is_touch_and_resolves():
    cfg = yaml.safe_load((Path(__file__).resolve().parents[1] / "seldon.yaml").read_text())
    s = R.settings(cfg)
    assert s.selection["mode"] == "touch"
    assert s.selection["lexical_min_shared_terms"]["result"] is None
