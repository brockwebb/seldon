"""SEL-013R: a task that answers a consumer's filing files its own return task in the consumer's repository (AD-036-R16).

`cc_tasks/2026-10-28_SEL-013R_a_consumer_filings_answer_files_its_own_return.md`. The incident: four hazbrief filings
into squiddy were answered by squiddy tasks whose RESULTs ended "For hazbrief: paste these steps"; the return went
through the operator's clipboard and a Desktop wrote HB-63, HB-64 and an ai-readiness-kg re-pin task by hand.

A. `**Answers:** <repo>:<ref>`: the grammar is a static check (AD-038-R12); registration resolves the ref in the other
   graph, refuses one that does not resolve and records the filing on the task.
B. `seldon cc complete` refuses an answering task until a return is registered and committed in the consumer;
   `seldon cc return` writes it from the RESULT's `For <consumer>` section and registers it there (AD-036-R12); the
   dispatcher's finish runs the same writer when the session did not.
C. The fixture: a task answering a fixture filing, completed, with its return registered in the fixture consumer.

The consumer is a second ephemeral database behind its own `seldon.yaml` and its own git repository, found by the
side-by-side convention, as hazbrief-mcp is found from squiddy.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from seldon.commands.cc import cc_group, register_task_file
from seldon.core import dispatch as D
from seldon.core import returns as RT
from seldon.core.events import read_events
from tests.test_sel008_cross_project_waits_and_block_reason import (  # noqa: F401  (fixtures)
    OTHER_DB, domain_config, other_db,
)
from tests.testdb import TEST_DATABASE

URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
STORE = "seldon_events.jsonl"
FILING_STEM = "2026-10-27_HB-37_a_filing_into_the_producer"
TASK_STEM = "2026-10-28_SEL-900_answer_the_consumers_filing"

neo4j_tests = pytest.mark.usefixtures("neo4j_available", "clean_test_db")


def _git(p: Path, *a, check=True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *a], cwd=p, check=check, capture_output=True, text=True)


def _repo(p: Path, name: str, database: str, origin: bool = False) -> Path:
    (p / "cc_tasks").mkdir(parents=True)
    _git(p, "init", "-q", "-b", "main")
    _git(p, "config", "user.email", "t@t")
    _git(p, "config", "user.name", "t")
    (p / STORE).write_text("", encoding="utf-8")
    (p / ".gitignore").write_text(".seldon/\nlogs/\n.claude/\n", encoding="utf-8")
    (p / "seldon.yaml").write_text(yaml.safe_dump({
        "project": {"name": name, "domain": "research", "slug": name},
        "neo4j": {"database": database, "uri": URI}, "event_store": {"path": STORE}}, sort_keys=False),
        encoding="utf-8")
    (p / "cc_tasks" / ".keep").write_text("", encoding="utf-8")
    _git(p, "add", "-A")
    _git(p, "commit", "-q", "-m", "init")
    if origin:
        bare = p.parent / f"{name}_origin.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True, capture_output=True)
        _git(p, "remote", "add", "origin", str(bare))
        _git(p, "push", "-q", "-u", "origin", "main")
    return p


def _config(p: Path) -> dict:
    return yaml.safe_load((p / "seldon.yaml").read_text(encoding="utf-8"))


@pytest.fixture
def consumer(tmp_path, other_db):
    """The consumer repository: its own git repository, graph and seldon.yaml, beside the producer."""
    return _repo(tmp_path / "consumer", "consumer", other_db, origin=True)


@pytest.fixture
def producer(tmp_path, monkeypatch, clean_test_db):
    """The answering repository, the working directory of every CLI call."""
    p = _repo(tmp_path / "producer", "producer", TEST_DATABASE)
    monkeypatch.chdir(p)
    return p


def _file_filing(consumer: Path, driver, dc, stem: str = FILING_STEM) -> str:
    f = consumer / "cc_tasks" / f"{stem}.md"
    f.write_text("# HB-37: a filing into the producer\n\n**Spend:** zero.\n**Network:** none.\n**After:** none\n\n"
                 "## 1. File it.\n", encoding="utf-8")
    out = register_task_file(project_dir=consumer, config=_config(consumer), driver=driver, database=OTHER_DB,
                             domain_config=dc, session_id=None, task_path=f, actor="cc", allow_untracked=True)
    return out["artifact_id"]


def _task_body(answers: str) -> str:
    return (f"# SEL-900: answer the consumer's filing\n\n**Spend:** zero.\n**Network:** none.\n**After:** none\n"
            f"**Answers:** {answers}\n\n## 1. Do the thing.\n")


def _answering_task(producer: Path, driver, dc, answers: str = "consumer:HB-37") -> tuple:
    f = producer / "cc_tasks" / f"{TASK_STEM}.md"
    f.write_text(_task_body(answers), encoding="utf-8")
    out = register_task_file(project_dir=producer, config=_config(producer), driver=driver, database=TEST_DATABASE,
                             domain_config=dc, session_id=None, task_path=f, actor="cc", allow_untracked=True)
    return f, out


RESULT_WITH_SECTION = """# RESULT: SEL-900

Landed the fix.

## For consumer

**Spend:** est. 0.05M tokens.
**Title:** re-pin the producer and run the suite

1. Re-pin `producer.pin` to the merge commit named above.
2. Run the suite; the pass is against the new pin.

## Not in this task

Nothing else.
"""


def _result(producer: Path, text: str = RESULT_WITH_SECTION) -> Path:
    r = producer / "cc_tasks" / f"{TASK_STEM}_RESULT.md"
    r.write_text(text, encoding="utf-8")
    return r


def _invoke(*args):
    return CliRunner().invoke(cc_group, list(args), catch_exceptions=False)


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


# ══════════════════════════════════════════════════════════════════════════════
# Part A: the header (no Neo4j)
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("value, project, ref", [
    ("hazbrief-mcp:HB-37", "hazbrief-mcp", "HB-37"),
    ("`squiddy:2026-10-27_SQ-089_x`.", "squiddy", "2026-10-27_SQ-089_x"),
    ("seldon:abcdef12", "seldon", "abcdef12"),
])
def test_the_answers_grammar_is_one_qualified_ref(value, project, ref):
    assert D.parse_answers(value) == {"kind": "ref", "project": project, "ref": ref, "error": None}


@pytest.mark.parametrize("bad", ["HB-37", "", "a:b, c:d", ":HB-37", "squiddy:"])
def test_an_answers_value_that_is_not_one_qualified_ref_is_refused(bad):
    parsed = D.parse_answers(bad)
    assert parsed["kind"] is None and "<repo>:<ref>" in parsed["error"]


def test_an_absent_answers_header_is_nothing():
    assert D.parse_answers(None)["kind"] == "absent"


def test_the_static_checks_refuse_a_bad_or_repeated_answers_header(tmp_path):
    f = tmp_path / "t.md"
    f.write_text(_task_body("HB-37"), encoding="utf-8")
    codes = [x["code"] for x in D.static_checks(f, None)["failures"]]
    assert D.ANSWERS_UNRESOLVED in codes
    f.write_text(_task_body("consumer:HB-37"), encoding="utf-8")
    assert D.static_checks(f, None)["failures"] == []
    f.write_text(_task_body("consumer:HB-37").replace("**After:** none\n", "**After:** none\n**Answers:** x:y\n"),
                 encoding="utf-8")
    assert [x["code"] for x in D.static_checks(f, None)["failures"]] == [f"{D.HEADER_REPEATED}:Answers"]


# ══════════════════════════════════════════════════════════════════════════════
# Part A: resolved at registration
# ══════════════════════════════════════════════════════════════════════════════

@neo4j_tests
@pytest.mark.parametrize("ref", ["HB-37", FILING_STEM, "id"])
def test_registration_resolves_the_filing_in_the_consumer_graph_and_records_it(
        neo4j_driver, producer, consumer, domain_config, ref):
    filing = _file_filing(consumer, neo4j_driver, domain_config)
    _f, out = _answering_task(producer, neo4j_driver, domain_config,
                              f"consumer:{filing[:8] if ref == 'id' else ref}")
    created = [e for e in read_events(producer) if e["event_type"] == "artifact_created"
               and e["payload"]["artifact_id"] == out["artifact_id"]]
    assert created[0]["payload"]["properties"][RT.PROPERTY] == f"consumer:{filing}"


@neo4j_tests
@pytest.mark.parametrize("answers", ["consumer:HB-99", "nowhere:HB-37"])
def test_registration_refuses_an_unresolvable_filing_and_writes_nothing(
        neo4j_driver, producer, consumer, domain_config, answers):
    _file_filing(consumer, neo4j_driver, domain_config)
    before = (producer / STORE).read_bytes()
    with pytest.raises(ValueError, match=D.ANSWERS_UNRESOLVED):
        _answering_task(producer, neo4j_driver, domain_config, answers)
    assert (producer / STORE).read_bytes() == before


# ══════════════════════════════════════════════════════════════════════════════
# Part B: the RESULT's section (no Neo4j)
# ══════════════════════════════════════════════════════════════════════════════

def test_the_consumer_section_carries_its_headers_and_ends_at_the_next_heading():
    s = RT.consumer_section(RESULT_WITH_SECTION, {"consumer"})
    assert s["headers"] == {"Spend": "est. 0.05M tokens.", "Title": "re-pin the producer and run the suite"}
    assert s["body"].startswith("1. Re-pin") and "Not in this task" not in s["body"]


def test_a_heading_for_another_consumer_is_not_this_ones():
    assert RT.consumer_section(RESULT_WITH_SECTION, {"hazbrief"}) is None


def test_the_retired_paste_heading_still_reads_as_the_section():
    s = RT.consumer_section("## For hazbrief: paste these steps\n\n1. x\n", {"hazbrief"})
    assert s["body"] == "1. x"


# ══════════════════════════════════════════════════════════════════════════════
# Part B and C: the refusal, the writer, the fixture
# ══════════════════════════════════════════════════════════════════════════════

@neo4j_tests
def test_fixture_an_answering_task_is_refused_then_returned_then_completed(
        neo4j_driver, producer, consumer, domain_config):
    """Part C's fixture: the answering task cannot complete with no return; `cc return` files one, numbered by the
    consumer's allocator, after its latest open task, registered there and committed there; then it completes."""
    filing = _file_filing(consumer, neo4j_driver, domain_config)
    task, out = _answering_task(producer, neo4j_driver, domain_config)
    _result(producer)
    rel = f"cc_tasks/{TASK_STEM}.md"

    refused = _invoke("complete", rel)
    assert refused.exit_code == 1
    assert RT.RETURN_UNFILED in refused.output and f"seldon cc return {rel} --to consumer" in refused.output

    filed = _invoke("return", rel, "--to", "consumer")
    assert filed.exit_code == 0, filed.output
    ret_rel = f"cc_tasks/{_today()}_HB-38_re_pin_the_producer_and_run_the_suite.md"
    assert f"return filed: {consumer}/{ret_rel}" in filed.output
    text = (consumer / ret_rel).read_text(encoding="utf-8")
    assert f"**Returns:** producer:{out['artifact_id']} (SEL-900)" in text
    assert f"**After:** {FILING_STEM}" in text
    assert "**Spend:** est. 0.05M tokens." in text and "**Network:** none beyond git." in text
    assert "1. Re-pin `producer.pin`" in text and f"producer/cc_tasks/{TASK_STEM}_RESULT.md" in text
    assert _git(consumer, "status", "--porcelain", "--", ret_rel).stdout == ""
    assert _git(consumer, "log", "-1", "--format=%s", "--", ret_rel).stdout.strip()
    with neo4j_driver.session(database=OTHER_DB) as s:
        row = s.run("MATCH (t:ResearchTask {source_file: $f}) RETURN t.state AS st, t.artifact_id AS id",
                    f=ret_rel).single()
        edge = s.run("MATCH (a:ResearchTask {artifact_id: $a})-[:PRECEDES]->(b:ResearchTask {artifact_id: $b}) "
                     "RETURN count(*) AS n", a=filing, b=row["id"]).single()["n"]
    assert row["st"] == "proposed" and edge == 1, "registered there, after the consumer's latest open task"

    done = _invoke("complete", rel)
    assert done.exit_code == 0, done.output
    with neo4j_driver.session(database=TEST_DATABASE) as s:
        assert s.run("MATCH (t:ResearchTask {artifact_id: $id}) RETURN t.state AS st",
                     id=out["artifact_id"]).single()["st"] == "completed"


@neo4j_tests
def test_the_mcp_complete_refuses_and_then_completes_by_the_same_gate(
        neo4j_driver, producer, consumer, domain_config):
    from seldon.mcp_server import seldon_cc_complete
    _file_filing(consumer, neo4j_driver, domain_config)
    _task, out = _answering_task(producer, neo4j_driver, domain_config)
    _result(producer)
    rel = f"cc_tasks/{TASK_STEM}.md"
    refused = seldon_cc_complete(filepath=rel, project_dir=str(producer))
    assert refused.startswith("Error:") and RT.RETURN_UNFILED in refused
    assert _invoke("return", rel).exit_code == 0
    assert "state: completed" in seldon_cc_complete(filepath=rel, project_dir=str(producer))


@neo4j_tests
def test_re_running_cc_return_reports_the_return_and_writes_no_second(
        neo4j_driver, producer, consumer, domain_config):
    _file_filing(consumer, neo4j_driver, domain_config)
    _answering_task(producer, neo4j_driver, domain_config)
    _result(producer)
    rel = f"cc_tasks/{TASK_STEM}.md"
    assert _invoke("return", rel).exit_code == 0
    again = _invoke("return", rel)
    assert again.exit_code == 0 and "return already filed" in again.output
    assert len([p for p in (consumer / "cc_tasks").glob("*HB-38*")]) == 1


@neo4j_tests
@pytest.mark.parametrize("result", [None, "# RESULT\n\nNo section.\n", "## For consumer\n\n**Author:** me\n\n1. x\n"])
def test_cc_return_refuses_without_a_usable_section_and_leaves_the_consumer_untouched(
        neo4j_driver, producer, consumer, domain_config, result):
    _file_filing(consumer, neo4j_driver, domain_config)
    _answering_task(producer, neo4j_driver, domain_config)
    if result is not None:
        _result(producer, result)
    head = _git(consumer, "rev-parse", "HEAD").stdout
    res = _invoke("return", f"cc_tasks/{TASK_STEM}.md")
    assert res.exit_code == 1, res.output
    assert _git(consumer, "rev-parse", "HEAD").stdout == head
    assert _git(consumer, "status", "--porcelain").stdout == ""


@neo4j_tests
def test_cc_return_refuses_a_to_that_is_not_the_answered_repository(neo4j_driver, producer, consumer, domain_config):
    _file_filing(consumer, neo4j_driver, domain_config)
    _answering_task(producer, neo4j_driver, domain_config)
    _result(producer)
    res = _invoke("return", f"cc_tasks/{TASK_STEM}.md", "--to", "squiddy")
    assert res.exit_code == 1 and "not the repository the task answers" in res.output


@neo4j_tests
def test_a_return_on_disk_but_unregistered_and_uncommitted_still_refuses_completion(
        neo4j_driver, producer, consumer, domain_config):
    _file_filing(consumer, neo4j_driver, domain_config)
    task, out = _answering_task(producer, neo4j_driver, domain_config)
    (consumer / "cc_tasks" / "2026-10-28_HB-38_by_hand.md").write_text(
        f"# HB-38: by hand\n\n**Returns:** producer:{out['artifact_id']}\n", encoding="utf-8")
    refusal = RT.completion_refusal(producer, _config(producer), task, out["artifact_id"])
    assert refusal.startswith(RT.RETURN_UNFILED)
    assert "not registered" in refusal and "not committed" in refusal


@neo4j_tests
def test_a_task_with_no_answers_header_completes_as_before(neo4j_driver, producer, domain_config):
    f = producer / "cc_tasks" / f"{TASK_STEM}.md"
    f.write_text(_task_body("x:y").replace("**Answers:** x:y\n", ""), encoding="utf-8")
    register_task_file(project_dir=producer, config=_config(producer), driver=neo4j_driver, database=TEST_DATABASE,
                       domain_config=domain_config, session_id=None, task_path=f, actor="cc", allow_untracked=True)
    assert RT.completion_refusal(producer, _config(producer), f, "x") is None
    assert _invoke("complete", f"cc_tasks/{TASK_STEM}.md").exit_code == 0


# ══════════════════════════════════════════════════════════════════════════════
# Part B: the dispatcher's finish files the return the session did not
# ══════════════════════════════════════════════════════════════════════════════

def _dispatch_run(tmp_path, neo4j_driver, dc, result_text: str):
    from seldon.commands.dispatch import dispatch_group
    from tests.dispatch_scaffold import add_task, make_project, register, run_cli, write_stub
    p = make_project(tmp_path)
    consumer = _repo(tmp_path / "consumer", "consumer", OTHER_DB, origin=True)
    filing = _file_filing(consumer, neo4j_driver, dc)
    stem = "sel013r_answering"
    add_task(p, stem, "**Answers:** consumer:HB-37\n")
    tid = register(p, neo4j_driver, dc, stem, "2026-10-28T00:00:00Z")
    write_stub(p, {stem: {"result_text": result_text}})
    res = run_cli(p, dispatch_group, ["once"])
    fin = [e["payload"] for e in read_events(p) if e["event_type"] == D.EVENT_FINISHED][-1]
    return p, consumer, filing, tid, res, fin


@pytest.mark.usefixtures("neo4j_available")
def test_the_dispatchers_finish_files_the_return_and_pushes_the_consumer(tmp_path, neo4j_driver, other_db,
                                                                         domain_config, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    p, consumer, _filing, tid, res, fin = _dispatch_run(tmp_path, neo4j_driver, domain_config, RESULT_WITH_SECTION)
    assert res.exit_code == 0, res.output
    assert fin["outcome"] == "merged", (fin, res.output)
    assert fin["merge"]["return"]["status"] == "written", fin["merge"]
    rel = fin["merge"]["return"]["rel_path"]
    assert "HB-38" in rel and (consumer / rel).is_file()
    assert any(r["push"] == "pushed" and Path(r["repo"]).name == "consumer" for r in fin["push_repos"]), fin
    assert _git(consumer, "rev-list", "--count", "@{u}..HEAD").stdout.strip() == "0"
    with neo4j_driver.session(database=TEST_DATABASE) as s:
        assert s.run("MATCH (t:ResearchTask {artifact_id: $id}) RETURN t.state AS st",
                     id=tid).single()["st"] == "completed"


@pytest.mark.usefixtures("neo4j_available")
def test_a_merged_task_whose_return_cannot_be_filed_is_blocked_not_completed(tmp_path, neo4j_driver, other_db,
                                                                              domain_config, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    p, consumer, _filing, tid, res, fin = _dispatch_run(tmp_path, neo4j_driver, domain_config, "# RESULT\n")
    assert fin["outcome"] == "return_unfiled", (fin, res.output)
    assert "return_unfiled" in res.output
    with neo4j_driver.session(database=TEST_DATABASE) as s:
        row = s.run("MATCH (t:ResearchTask {artifact_id: $id}) RETURN t.state AS st, t.block_reason AS why, "
                    "t.dispatch_merge AS m", id=tid).single()
    assert row["st"] == "blocked" and RT.RETURN_UNFILED in row["why"] and row["m"] == "merged"
    assert _git(consumer, "status", "--porcelain").stdout == ""
