"""SEL-040 Parts C and D: an addendum files in one call, and a premise can wait for launch.

`cc_tasks/2026-11-16_SEL-040_..._premise_can_wait_for_launch.md`, AD-038-R26..R28.

* **C.** hazbrief's Desktop could not file an addendum through `seldon_cc_file`: the call treated
  `<stem>_ADDENDUM_NN_*.md` as a new task and refused it for the Spend and Network headers AD-038-R24 forbids an
  addendum to carry. It wrote the file with the Filesystem tool and committed it separately, the two-step sequence
  AD-038-R20 exists to remove. Now `cc file` recognises an addendum to a registered task: written and committed under
  the filing lock, nothing registered, and still refused if it carries a candidacy header.
* **D.** hazbrief HB-192 was refused at registration for a premise that HB-189's RESULT exists, while HB-189 ran. A
  premise line may now carry `| at: launch`: registration records it unevaluated, and station (a) evaluates it with the
  others before the session starts. A premise that only restates the After header is refused with a pointer to it.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from seldon.core import dispatch as D
from seldon.core import filing as F
from seldon.core import stations as Q
from tests.dispatch_scaffold import NEO4J_DB, git, make_project, register, run_cli
from tests.test_sel008_cross_project_waits_and_block_reason import domain_config  # noqa: F401  (fixture)

neo4j_tests = pytest.mark.usefixtures("neo4j_available", "clean_test_db")

BASE = "2026-11-16_SEL-900_base_task"
ADDENDUM = """# SEL-900 ADDENDUM 01: a correction while it runs

**Date:** 2026-11-17.

## 1. What changes

Step 3 reads the other file.
"""


@pytest.fixture
def proj(tmp_path, monkeypatch, neo4j_available, clean_test_db):
    for var in D.API_KEY_VARS:
        monkeypatch.setenv(var, "x")
        monkeypatch.delenv(var)
    return make_project(tmp_path)


def _base(p: Path, driver, dc) -> str:
    """The base task: its file committed and registered."""
    from tests.dispatch_scaffold import add_task
    add_task(p, BASE)
    return register(p, driver, dc, BASE, "2026-11-16T00:00:00Z")


def _graph_count(driver) -> int:
    with driver.session(database=NEO4J_DB) as s:
        return s.run("MATCH (t:ResearchTask) RETURN count(t) AS n").single()["n"]


def _set_state(driver, stem: str, state: str) -> None:
    with driver.session(database=NEO4J_DB) as s:
        s.run("MATCH (t:ResearchTask {source_file: $f}) SET t.state = $s", f=f"cc_tasks/{stem}.md", s=state)


# ------------------------------------------------------------------------------------------- Part C

@neo4j_tests
def test_an_addendum_to_a_running_task_files_in_one_call(proj, neo4j_driver, domain_config):  # noqa: F811
    p = proj
    _base(p, neo4j_driver, domain_config)
    _set_state(neo4j_driver, BASE, "in_progress")
    before = _graph_count(neo4j_driver)
    name = f"{BASE}_ADDENDUM_01_a_correction.md"
    out = F.file_task(p, ADDENDUM, name=name)
    assert out["addendum"] is True and out["base_task"] and out["rel_path"] == f"cc_tasks/{name}"
    assert out["artifact_id"] == out["base_task"], "an addendum is its base task's; nothing new is registered"
    assert _graph_count(neo4j_driver) == before
    assert git(p, "status", "--porcelain", "--", "cc_tasks").stdout == "", "written and committed"
    subject = git(p, "log", "-1", "--format=%s", "--", f"cc_tasks/{name}").stdout.strip()
    assert subject.startswith("addendum:") and BASE in subject


@neo4j_tests
def test_an_addendum_to_a_task_that_does_not_exist_is_refused_and_removed(proj):
    p = proj
    name = "2026-11-16_SEL-901_nothing_ADDENDUM_01_x.md"
    with pytest.raises(F.FilingError, match=F.ADDENDUM_ORPHAN):
        F.file_task(p, ADDENDUM, name=name)
    assert not (p / "cc_tasks" / name).exists()
    assert git(p, "status", "--porcelain").stdout == ""


@neo4j_tests
def test_an_addendum_whose_base_file_is_unregistered_is_refused(proj):
    p = proj
    (p / "cc_tasks" / f"{BASE}.md").write_text("# x\n", encoding="utf-8")
    git(p, "add", "--", f"cc_tasks/{BASE}.md")
    git(p, "commit", "-q", "-m", "base, unregistered")
    with pytest.raises(F.FilingError, match=F.ADDENDUM_ORPHAN):
        F.file_task(p, ADDENDUM, name=f"{BASE}_ADDENDUM_01_x.md")


@neo4j_tests
@pytest.mark.parametrize("header", ["**Spend:** est. 5M tokens.", "**Network:** api.example.com",
                                    "**Framework layer served (DN-005 §5 rule 1):** none.", "**Exclusive:** no"])
def test_an_addendum_still_may_not_carry_a_candidacy_header(proj, neo4j_driver, domain_config, header):  # noqa: F811
    p = proj
    _base(p, neo4j_driver, domain_config)
    name = f"{BASE}_ADDENDUM_02_raise.md"
    with pytest.raises(F.FilingError, match=D.ADDENDUM_CARRIES_HEADER):
        F.file_task(p, ADDENDUM.replace("**Date:** 2026-11-17.", "**Date:** 2026-11-17.\n" + header), name=name)
    assert not (p / "cc_tasks" / name).exists()


@neo4j_tests
def test_the_mcp_tool_files_an_addendum_in_one_call(proj, neo4j_driver, domain_config):  # noqa: F811
    from seldon import mcp_server as M
    p = proj
    _base(p, neo4j_driver, domain_config)
    tool = getattr(M.seldon_cc_file, "__wrapped__", M.seldon_cc_file)
    reply = tool(ADDENDUM, project_dir=str(p), filename=f"{BASE}_ADDENDUM_01_a_correction.md")
    assert reply.startswith("Filed addendum:"), reply
    assert "registers nothing" in reply
    assert git(p, "status", "--porcelain", "--", "cc_tasks").stdout == ""


def test_the_base_stem_of_an_addendum_name():
    assert F.addendum_base_stem(f"{BASE}_ADDENDUM_01_a_correction.md") == BASE
    assert F.addendum_base_stem(f"{BASE}_ADDENDUM_12.md") == BASE
    assert F.addendum_base_stem(f"{BASE}.md") is None


# ------------------------------------------------------------------------------------------- Part D

AFTER_TASK = """# T

**After:** 2026-11-15_HB-189_a_stable_night_brief
**Premises:**
- premise: the dispatcher's code is here | check: test -d seldon
- premise: HB-189's RESULT exists | check: test -f cc_tasks/2026-11-15_HB-189_a_stable_night_brief_RESULT.md
"""


def test_a_premise_may_wait_for_launch_and_registration_does_not_evaluate_it(tmp_path):
    text = ("**Premises:**\n- premise: the predecessor's export is on disk | check: test -f out/export.json "
            "| at: launch\n- premise: a directory | check: test -d .\n")
    parsed = Q.parse_premises(text)
    assert parsed["errors"] == []
    (first, second) = parsed["premises"]
    assert first["command"] == "test -f out/export.json" and first["at"] == "launch"
    assert second.get("at") is None
    reg = Q.review_premises(tmp_path, text, dict(Q.STATIONS_DEFAULTS), stage="registration")
    assert reg["ok"], reg["false"]
    assert [r["outcome"] for r in reg["premises"]] == ["at_launch", "true"]
    launch = Q.review_premises(tmp_path, text, dict(Q.STATIONS_DEFAULTS))
    assert not launch["ok"] and launch["false"][0]["statement"] == "the predecessor's export is on disk"


def test_registration_refuses_nothing_for_a_launch_premise_and_station_a_still_does(tmp_path):
    task = tmp_path / "cc_tasks" / "t.md"
    task.parent.mkdir()
    task.write_text("**Premises:**\n- premise: later | check: test -f nope.txt | at: launch\n", encoding="utf-8")
    assert Q.premises_registration_refusal(task, tmp_path, {}) is None
    (tmp_path / "nope.txt").write_text("x")
    assert Q.review_premises(tmp_path, task.read_text(), dict(Q.STATIONS_DEFAULTS))["ok"]


def test_an_unknown_at_value_is_unreadable():
    parsed = Q.parse_premises("**Premises:**\n- premise: x | check: true | at: lunch\n")
    assert parsed["premises"] == [] and parsed["errors"]


def test_a_premise_that_restates_the_after_header_is_refused_with_a_pointer(tmp_path):
    task = tmp_path / "t.md"
    task.write_text(AFTER_TASK, encoding="utf-8")
    refusal = Q.premises_registration_refusal(task, tmp_path, {})
    assert refusal and refusal.startswith(Q.PREMISE_RESTATES_AFTER), refusal
    assert "**After:**" in refusal and "HB-189's RESULT exists" in refusal
    assert "the dispatcher's code is here" not in refusal


def test_the_same_premise_without_an_after_header_is_an_ordinary_premise(tmp_path):
    task = tmp_path / "t.md"
    task.write_text(AFTER_TASK.replace("**After:** 2026-11-15_HB-189_a_stable_night_brief\n", ""),
                    encoding="utf-8")
    refusal = Q.premises_registration_refusal(task, tmp_path, {})
    assert refusal and refusal.startswith(Q.PREMISE_REGISTRATION_REFUSAL), "false as a premise, as before"


def test_a_premise_about_the_predecessors_output_is_not_a_restatement(tmp_path):
    (tmp_path / "seldon").mkdir()                    # the task's other premise holds
    task = tmp_path / "t.md"
    task.write_text(AFTER_TASK.replace(
        "- premise: HB-189's RESULT exists | check: test -f cc_tasks/2026-11-15_HB-189_a_stable_night_brief_RESULT.md",
        "- premise: HB-189's export is on disk | check: test -f out/hb189_export.json | at: launch"), encoding="utf-8")
    assert Q.premises_registration_refusal(task, tmp_path, {}) is None


@neo4j_tests
def test_a_launch_premise_is_evaluated_by_station_a_before_the_session_starts(proj, neo4j_driver,
                                                                              domain_config):  # noqa: F811
    """End to end: registered with a premise false at registration; station (a) refuses the launch while it is false,
    naming it, and launches once it holds."""
    from seldon.commands.dispatch import dispatch_group
    from seldon.core.events import read_events
    from tests.dispatch_scaffold import add_task, write_stub
    p = proj
    add_task(p, "a", "**Parts:** A 1.0.\n**Premises:**\n- premise: the predecessor wrote its export | "
                     "check: test -f export.json | at: launch\n")
    register(p, neo4j_driver, domain_config, "a", "2026-11-16T00:00:00Z")
    write_stub(p, {"a": {"write": {"out/a.txt": "a\n"}}})
    assert run_cli(p, dispatch_group, ["once"]).exit_code == 0
    refused = [e["payload"] for e in read_events(p) if e["event_type"] == D.EVENT_REFUSED
               and (e.get("payload") or {}).get("reason") == Q.REFUSED_PREMISE_FALSE]
    assert refused and refused[-1]["false"][0]["statement"] == "the predecessor wrote its export"
    assert not [e for e in read_events(p) if e["event_type"] == D.EVENT_LAUNCHED]


def test_the_dispatcher_re_checks_every_premise_at_launch_today():
    """Part D's measurement, kept as a test: station (a) runs `review_premises` over the whole block for every eligible
    task in the serial pass (`dispatch._pass` -> `review_launches` -> `_premise_review` ->
    `dispatch_stations.premise_review`; SEL-062's AD-038-R46 put the review in a stage the parallel pass and the lane
    share), so a launch premise needs no new evaluation point, only registration's deferral."""
    import inspect
    from seldon.commands import dispatch as S
    from seldon.commands import dispatch_stations as ST
    assert "review_launches(" in inspect.getsource(S._pass)
    assert "_premise_review(" in inspect.getsource(S.review_launches)
    assert "review_premises(" in inspect.getsource(ST.premise_review)
    assert "stage=" not in inspect.getsource(ST.premise_review), "station (a) evaluates every premise"


# ------------------------------------------------------------------------------------------- Part E (2)

@neo4j_tests
def test_an_issue_created_without_project_dir_says_the_default_chose_its_repository(proj, monkeypatch):
    """hazbrief's Issue 0c4232cb was written into seldon's graph by a call with no project_dir (SELDON_DEFAULT_PROJECT
    is seldon in Desktop's config), and the reply never said where it went. Recall lists it under seldon because it IS
    seldon's; the reply now names the repository, and the default when it chose it."""
    from seldon import mcp_server as M
    p = proj
    monkeypatch.setenv("SELDON_DEFAULT_PROJECT", str(p))
    tool = getattr(M.seldon_issue_create, "__wrapped__", M.seldon_issue_create)
    reply = tool("an-issue", "what is wrong")
    assert f"project: {p.resolve().name} ({p.resolve()})" in reply, reply
    assert "SELDON_DEFAULT_PROJECT chose it" in reply
    named = tool("another-issue", "what is wrong", project_dir=str(p))
    assert f"project: {p.resolve().name}" in named and "SELDON_DEFAULT_PROJECT" not in named


def _cfg(p: Path) -> dict:
    return yaml.safe_load((p / "seldon.yaml").read_text(encoding="utf-8"))
