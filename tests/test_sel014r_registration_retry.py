"""SEL-014R Part C: a registration refused for a mechanical cause is retried once under a named rule (AD-038-R18).

`cc_tasks/2026-10-28_SEL-014R_the_ooda_is_a_knowledge_source_the_dispatcher_launches.md`;
`docs/design/AD-038_ADDENDUM_07_the_ooda_as_a_knowledge_source.md`.

The three causes of 2026-10-28's three hand-fixed refusals (the SQ11 work order, item 2): a `check:` that needs a shell
and is not under `sh -c`; a number another file holds (`number_taken`); a premise naming a path that does not exist in
a repository the task names. Each has one known repair, so the retry is a rule table (no model call). The premise
checks run for real (`stations.review_premises` with its `run_check`), and registration through the graph is the real
`register_task_file`.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from seldon.commands import cc
from seldon.core import numbering as N
from seldon.core import ooda as O
from seldon.core import stations as QS
from seldon.core.events import read_events
from tests.test_num001r_task_numbers_allocated import DOMAIN, _git, repo  # noqa: F401  (fixture)
from tests.testdb import TEST_DATABASE

TODAY = "2026-10-28"


def _review(pd, text):
    return QS.review_premises(Path(pd), text, dict(QS.STATIONS_DEFAULTS))


def _file(root: Path, stem: str, premises: list) -> Path:
    body = (f"# {stem.split('_')[1]}: a task\n\n**Date:** {TODAY}\n**Premises:**\n"
            + "".join(f"- premise: {s} | check: {c}\n" for s, c in premises) + "\n## Steps\n\nDo it.\n")
    p = root / "cc_tasks" / f"{stem}.md"
    p.write_text(body, encoding="utf-8")
    return p


def _never(*_a, **_k):
    raise AssertionError("not expected to be called")


# ================================================================================================ the rules

def test_mechanical_codes_are_read_from_the_refusal_prefix():
    assert O.mechanical_code("number_taken: SEL-001 is already registered ...") == "number_taken"
    assert O.mechanical_code("premise_false: 1 premise(s) do not hold") == "premise_false"
    assert O.mechanical_code("after_unresolved: ...") is None
    assert O.mechanical_code("AD-036-R4: refusing ... number_taken: x") is None


def test_a_shell_check_is_wrapped_in_sh_c_and_then_holds(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    text = "**Premises:**\n- premise: both exist | check: `test -d a && test -d b`\n"
    rows = _review(tmp_path, text)
    assert rows["false"] and "unexpected operator" in rows["false"][0]["check"]["tail"]
    fixed = O.repair_premises(tmp_path, text, rows["false"], TODAY)
    assert fixed["changes"][0]["rule"] == O.RULE_SH_C
    assert "check: `sh -c 'test -d a && test -d b'`" in fixed["text"]
    assert _review(tmp_path, fixed["text"])["ok"]


def test_a_substitution_check_is_wrapped_too(tmp_path):
    (tmp_path / "log.txt").write_text("x\nx\n", encoding="utf-8")
    text = "**Premises:**\n- premise: few lines | check: test $(grep -c x log.txt) -le 2\n"
    rows = _review(tmp_path, text)
    assert not rows["ok"]
    fixed = O.repair_premises(tmp_path, text, rows["false"], TODAY)
    assert _review(tmp_path, fixed["text"])["ok"]


def test_a_missing_path_in_a_named_sibling_repository_is_marked_stale_and_narrowed(tmp_path):
    proj, sib = tmp_path / "proj", tmp_path / "squiddy"
    for r in (proj, sib):
        (r / "docs" / "findings").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(r)], check=True)
    text = ("**Repo:** squiddy\n**Premises:**\n"
            "- premise: the evidence exists | check: test -f ../squiddy/docs/findings/x/claims.jsonl\n")
    rows = _review(proj, text)
    fixed = O.repair_premises(proj, text, rows["false"], TODAY)
    [c] = fixed["changes"]
    assert c["rule"] == O.RULE_STALE_EVIDENCE
    assert ("[stale_evidence: ../squiddy/docs/findings/x/claims.jsonl absent at registration 2026-10-28]"
            in c["after"]) and "check: test -d ../squiddy/docs/findings" in c["after"]
    assert _review(proj, fixed["text"])["ok"]


def test_a_missing_path_in_a_repository_the_task_does_not_name_is_not_narrowed(tmp_path):
    proj, other = tmp_path / "proj", tmp_path / "arnold"
    for r in (proj, other):
        r.mkdir()
        subprocess.run(["git", "init", "-q", str(r)], check=True)
    text = "**Premises:**\n- premise: it exists | check: test -f ../arnold/x.md\n"
    assert O.repair_premises(proj, text, _review(proj, text)["false"], TODAY) is None


def test_a_missing_path_in_this_projects_own_repository_is_not_narrowed(tmp_path):
    """Negative control: a premise false in the registering project is AD-038-R5's case and reaches its author
    (tests/test_friction001_registration_premises.py); narrowing it would make it vacuous (`test -d .`)."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    text = "**Premises:**\n- premise: the module exists | check: `test -f seldon/core/reconcile.py`\n"
    assert O.repair_premises(tmp_path, text, _review(tmp_path, text)["false"], TODAY) is None


def test_a_premise_that_is_simply_false_has_no_rule(tmp_path):
    (tmp_path / "f.txt").write_text("nothing\n", encoding="utf-8")
    text = "**Premises:**\n- premise: f mentions band | check: grep -q band f.txt\n"
    assert O.repair_premises(tmp_path, text, _review(tmp_path, text)["false"], TODAY) is None


def test_a_renumbered_name_keeps_the_slug_and_drops_the_refiling_mark():
    assert O.renumbered_name("2026-10-28_SEL-014R_the_ooda.md", "SEL-016") == "2026-10-28_SEL-016_the_ooda.md"
    assert O.renumbered_name("2026-10-28_HB-01b_acq.md", "HB-66") == "2026-10-28_HB-66_acq.md"
    text, change = O.retitled("# SEL-014R: the OODA\n\nbody SEL-014R\n", "SEL-014R", "SEL-016")
    assert text == "# SEL-016: the OODA\n\nbody SEL-014R\n" and change["line"] == 1


# ================================================================================================ the retry

def _holders(rel_taken: str):
    tok = N.file_token(rel_taken)
    return lambda: [N.Holder(tok, "f" * 36, "completed", rel_taken, "graph")]


def test_a_refusal_with_no_mechanical_cause_is_not_retried(repo):
    """Negative control: anything but the two codes is reported as today, and the file is untouched."""
    p = _file(repo, "2026-10-28_TST-001_a", [])
    before = p.read_text()
    assert O.retry_registration(repo, p, "after_unresolved: no task 'zz'", register=_never, holders=_never,
                                allocate=_never, review=_review, record=_never) is None
    assert p.read_text() == before


def test_a_premise_with_no_rule_is_not_retried_and_the_file_is_untouched(repo):
    (repo / "f.txt").write_text("nothing\n", encoding="utf-8")
    p = _file(repo, "2026-10-28_TST-001_a", [("shell", "test -d cc_tasks && test -d cc_tasks"),
                                              ("simply false", "grep -q band f.txt")])
    before = p.read_text()
    assert O.retry_registration(repo, p, "premise_false: 2 premise(s) ...", register=_never,
                                holders=lambda: [], allocate=_never, review=_review, record=_never) is None
    assert p.read_text() == before


def test_one_retry_applies_every_rule_and_records_it(repo):
    """A shell check AND a taken number, fixed in one retry, though registration named only the first."""
    p = _file(repo, "2026-10-28_TST-001_b", [("tasks dir", "test -d cc_tasks && test -d cc_tasks")])
    seen, records = [], []

    def register(path):
        seen.append(path)
        return {"artifact_id": "new-id", "rel_path": str(path.relative_to(repo))}

    out = O.retry_registration(repo, p, "premise_false: 1 premise(s) ...", register=register,
                               holders=_holders("cc_tasks/2026-10-28_TST-001_a.md"),
                               allocate=lambda prefix: f"{prefix}-002", review=_review, record=records.append)
    new = repo / "cc_tasks" / "2026-10-28_TST-002_b.md"
    assert seen == [new] and not p.exists() and new.is_file()
    assert new.read_text().startswith("# TST-002: a task")
    assert "sh -c 'test -d cc_tasks && test -d cc_tasks'" in new.read_text()
    [r] = records
    assert (r["outcome"], r["task_id"], r["rules"], r["first_refusal_code"]) == (
        "registered", "new-id", [O.RULE_NEXT_NUMBER, O.RULE_SH_C], "premise_false")
    assert out["retried"] == r and r["rule_of"] == "AD-038-R18"


def test_a_second_refusal_reaches_the_operator(repo):
    """Negative control: one retry, never two; the second refusal names the retry and is recorded."""
    p = _file(repo, "2026-10-28_TST-001_b", [("tasks dir", "test -d cc_tasks && test -d cc_tasks")])
    records, calls = [], []

    def register(path):
        calls.append(path)
        raise ValueError("after_unresolved: no task 'zz'")

    with pytest.raises(ValueError) as exc:
        O.retry_registration(repo, p, "premise_false: 1 premise(s) ...", register=register, holders=lambda: [],
                             allocate=_never, review=_review, record=records.append)
    assert len(calls) == 1
    assert "after one mechanical retry under AD-038-R18" in str(exc.value) and "premise_false" in str(exc.value)
    assert records[0]["outcome"] == "refused_again" and records[0]["second_refusal"].startswith("after_unresolved")


def test_a_tracked_file_is_moved_with_git_and_the_repair_committed(repo):
    p = _file(repo, "2026-10-28_TST-001_b", [])
    _git(repo, "add", "cc_tasks/2026-10-28_TST-001_b.md")
    _git(repo, "commit", "-qm", "file it")
    out = O.retry_registration(repo, p, "number_taken: TST-001 is already registered ...",
                               register=lambda path: {"artifact_id": "x"},
                               holders=_holders("cc_tasks/2026-10-28_TST-001_a.md"),
                               allocate=lambda prefix: "TST-005", review=_review, record=lambda r: None)
    assert out["retried"]["file"] == "cc_tasks/2026-10-28_TST-005_b.md"
    status = _git(repo, "status", "--porcelain").stdout
    assert status == "", status
    assert "AD-038-R18" in _git(repo, "log", "-1", "--format=%s").stdout


# ================================================================================================ through the graph

neo4j = pytest.mark.usefixtures("neo4j_available", "clean_test_db")


@neo4j
def test_cc_register_retries_a_taken_number_and_records_it_on_the_task(repo, neo4j_driver, monkeypatch):
    first = repo / "cc_tasks" / "2026-10-28_TST-001_first.md"
    first.write_text("# TST-001: first\n\n**Date:** 2026-10-28\n\n## Steps\n\nDo it.\n", encoding="utf-8")
    second = repo / "cc_tasks" / "2026-10-28_TST-001_second.md"
    second.write_text("# TST-001: second\n\n**Date:** 2026-10-28\n\n## Steps\n\nDo it.\n", encoding="utf-8")
    monkeypatch.chdir(repo)
    runner = CliRunner()
    res = runner.invoke(cc.cc_group, ["register", str(first), "--allow-untracked"])
    assert res.exit_code == 0, res.output
    res = runner.invoke(cc.cc_group, ["register", str(second), "--allow-untracked"])
    assert res.exit_code == 0, res.output
    assert "Retried under AD-038-R18 (next_number) after `number_taken`" in res.output
    moved = repo / "cc_tasks" / "2026-10-28_TST-002_second.md"
    assert moved.is_file() and not second.exists()
    assert moved.read_text().startswith("# TST-002: second")
    [ev] = [e for e in read_events(repo) if e["event_type"] == O.EVENT_REGISTRATION_RETRIED]
    p = ev["payload"]
    assert (p["outcome"], p["file"], p["original_file"]) == (
        "registered", "cc_tasks/2026-10-28_TST-002_second.md", "cc_tasks/2026-10-28_TST-001_second.md")
    with neo4j_driver.session(database=TEST_DATABASE) as s:
        row = s.run("MATCH (t:ResearchTask {source_file: $f}) RETURN t.artifact_id AS id",
                    f="cc_tasks/2026-10-28_TST-002_second.md").single()
    assert row and row["id"] == p["task_id"]


@neo4j
def test_the_mcp_register_tool_retries_the_same_way(repo, neo4j_driver):
    from seldon import mcp_server as m
    a = repo / "cc_tasks" / "2026-10-28_TST-001_first.md"
    a.write_text("# TST-001: first\n\n**Date:** 2026-10-28\n\n## Steps\n\nDo it.\n", encoding="utf-8")
    config = yaml.safe_load((repo / "seldon.yaml").read_text())
    cc.register_task_file(project_dir=repo, config=config, driver=neo4j_driver, database=TEST_DATABASE,
                          domain_config=DOMAIN, session_id=None, task_path=a, allow_untracked=True)
    b = repo / "cc_tasks" / "2026-10-28_TST-001_second.md"
    b.write_text("# TST-001: second\n\n**Date:** 2026-10-28\n\n## Steps\n\nDo it.\n", encoding="utf-8")
    out = m.seldon_cc_register.__wrapped__(filepath=str(b), project_dir=str(repo), allow_untracked=True)
    assert out.startswith("Registered:"), out
    assert "Retried under AD-038-R18" in out and "2026-10-28_TST-002_second.md" in out
