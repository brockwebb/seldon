"""`**After:**` — the ordering a dispatcher can read, and the lint on the prose that cannot.

`ai-readiness-kg/cc_tasks/2026-09-19_seldon_hygiene_superseded_cadence_after.md` decisions 3
and 4.

**The condition, measured before the decision was taken.** DN-007 recorded that SEQUENCING
lines are "read into `precedes` edges inconsistently". They are not read at all: a repo-wide
`grep -rn -i sequencing seldon/` on 2026-09-19 returned ZERO hits. `cc register` wrote no edge;
dispatcher readiness (`core/dispatch.py`) reads `precedes` edges only; every such edge in that
project's graph was written by a Desktop session calling `seldon_task_chain` by hand, when it
remembered to. "Not launched before `X.md` is `completed` on the graph" is prose.

Decision 4 is the other half and it is deliberately a WARNING: Seldon does not guess an edge
from a sentence. It says the sentence is not read, and names the header that would be.
"""
from __future__ import annotations

import os
import textwrap
import uuid
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from seldon.commands.cc import AFTER_UNRESOLVED, cc_group, sequencing_lint
from seldon.core import dispatch as D
from seldon.core.artifacts import create_artifact
from seldon.core.precedence import read_pairs
from seldon.domain.loader import load_domain_config
from tests.testdb import TEST_DATABASE

pytestmark = pytest.mark.usefixtures("neo4j_available", "clean_test_db")

NEO4J_DB = TEST_DATABASE
RESEARCH_YAML = Path(__file__).parent.parent / "seldon" / "domain" / "research.yaml"
STORE = "seldon_events.jsonl"

BODY = textwrap.dedent("""\
    # CC Task — {stem}

    **Date:** 2026-09-19
    **Implements:** DN-006 decision 3.
    **Framework layer served (DN-005 §5 rule 1):** none.
    **Spend:** zero model calls. **Network:** none.
    {after}

    ## 1. Do the thing.
    """)

#: Copied verbatim from `ai-readiness-kg/cc_tasks/2026-09-16_neo4j_fixture_fails_not_skips.md`
#: line 43 on 2026-09-20, as decision 4 asks — copied, not read from that repo, so this suite
#: does not depend on another checkout.
REAL_SEQUENCING_LINE = (
    "**SEQUENCING:** §0 of the RESULT is captured at the start of the session, before "
    "§1 → §1 (merged before §2) → §2 → glob addenda → "
    "§3 (detached, logged, polled inside the turn) → §4 → push both repos. "
    "Not launched before `2026-09-16_headless_session_polls_to_completion.md` is `completed` "
    "on the graph.")


@pytest.fixture
def domain_config():
    return load_domain_config(RESEARCH_YAML)


@pytest.fixture
def project(tmp_path):
    p = tmp_path / "proj"
    (p / "cc_tasks").mkdir(parents=True)
    (p / STORE).write_text("", encoding="utf-8")
    (p / "seldon.yaml").write_text(yaml.safe_dump({
        "event_store": {"path": STORE},
        "neo4j": {"database": NEO4J_DB,
                  "uri": os.getenv("NEO4J_URI", "bolt://localhost:7687")},
        "project": {"domain": "research", "name": "t", "slug": "t"},
    }, sort_keys=False), encoding="utf-8")
    return p


def _write(project, stem, after=None, extra=""):
    line = f"**After:** {after}" if after is not None else ""
    path = project / "cc_tasks" / f"{stem}.md"
    path.write_text(BODY.format(stem=stem, after=line) + extra, encoding="utf-8")
    return path


def _register(project, stem, allow_untracked=True):
    prev = Path.cwd()
    os.chdir(project)
    try:
        argv = ["register", f"cc_tasks/{stem}.md"]
        if allow_untracked:
            argv.append("--allow-untracked")
        return CliRunner().invoke(cc_group, argv, catch_exceptions=False)
    finally:
        os.chdir(prev)


def _existing_task(project, driver, domain_config, stem) -> str:
    """A predecessor already in the graph, registered the way a prior task would have left it."""
    _write(project, stem)
    return create_artifact(
        project_dir=project, driver=driver, database=NEO4J_DB, domain_config=domain_config,
        artifact_type="ResearchTask",
        properties={"description": stem, "name": stem,
                    "source_file": f"cc_tasks/{stem}.md"},
        actor="desktop", authority="accepted")


def _pairs(driver):
    with driver.session(database=NEO4J_DB) as s:
        return set(read_pairs(s))


def _task_count(driver):
    with driver.session(database=NEO4J_DB) as s:
        return s.run("MATCH (t:Artifact:ResearchTask) RETURN count(t) AS n").single()["n"]


# ------------------------------------------------------------------------ the grammar alone

def test_the_grammar():
    assert D.parse_after(None)["kind"] == "absent"
    assert D.parse_after("none")["kind"] == "none"
    assert D.parse_after("none.")["kind"] == "none"
    assert D.parse_after("`a_b`, c_d.md")["refs"] == ["a_b", "c_d"]
    assert D.parse_after("cc_tasks/2026-09-01_x.md")["refs"] == ["2026-09-01_x"]
    assert D.parse_after("")["kind"] is None
    assert D.parse_after("after the scan")["kind"] is None
    assert "8 or more hex" in D.parse_after("a b")["error"]


def test_none_must_lead_the_value():
    """`the tasks in §2, none else` is not a declaration of no predecessor — the same
    correction `_NETWORK_NONE_RE` carries."""
    assert D.parse_after("the tasks in §2, none else")["kind"] is None


# ----------------------------------------------------------------------- resolution and edges

def test_a_stem_ref_writes_one_precedes_edge(project, neo4j_driver, domain_config):
    pred = _existing_task(project, neo4j_driver, domain_config, "2026-09-18_first")
    _write(project, "2026-09-19_second", after="2026-09-18_first")
    out = _register(project, "2026-09-19_second")
    assert out.exit_code == 0, out.output
    with neo4j_driver.session(database=NEO4J_DB) as s:
        new = s.run("MATCH (t:Artifact:ResearchTask) "
                    "WHERE t.source_file = 'cc_tasks/2026-09-19_second.md' "
                    "RETURN t.artifact_id AS id").single()["id"]
    assert (pred, new) in _pairs(neo4j_driver)


def test_a_ref_may_carry_the_md_suffix_or_the_directory(project, neo4j_driver, domain_config):
    pred = _existing_task(project, neo4j_driver, domain_config, "2026-09-18_first")
    _write(project, "2026-09-19_second", after="cc_tasks/2026-09-18_first.md")
    assert _register(project, "2026-09-19_second").exit_code == 0
    assert any(a == pred for a, _ in _pairs(neo4j_driver))


def test_an_id_prefix_ref_resolves(project, neo4j_driver, domain_config):
    pred = _existing_task(project, neo4j_driver, domain_config, "2026-09-18_first")
    _write(project, "2026-09-19_second", after=pred[:8])
    out = _register(project, "2026-09-19_second")
    assert out.exit_code == 0, out.output
    assert any(a == pred for a, _ in _pairs(neo4j_driver))


def test_several_refs_each_get_an_edge(project, neo4j_driver, domain_config):
    a = _existing_task(project, neo4j_driver, domain_config, "2026-09-18_a")
    b = _existing_task(project, neo4j_driver, domain_config, "2026-09-18_b")
    _write(project, "2026-09-19_c", after="2026-09-18_a, 2026-09-18_b")
    assert _register(project, "2026-09-19_c").exit_code == 0
    pairs = _pairs(neo4j_driver)
    assert {p[0] for p in pairs} == {a, b}


def test_none_writes_no_edge(project, neo4j_driver, domain_config):
    _existing_task(project, neo4j_driver, domain_config, "2026-09-18_first")
    _write(project, "2026-09-19_second", after="none")
    assert _register(project, "2026-09-19_second").exit_code == 0
    assert _pairs(neo4j_driver) == set()


def test_an_absent_header_writes_no_edge_and_is_not_a_refusal(project, neo4j_driver,
                                                              domain_config):
    """The header is OPTIONAL: nothing already queued changes behaviour when this ships."""
    _write(project, "2026-09-19_plain")
    out = _register(project, "2026-09-19_plain")
    assert out.exit_code == 0, out.output
    assert _pairs(neo4j_driver) == set()
    assert _task_count(neo4j_driver) == 1


def test_an_unresolvable_ref_refuses_and_writes_nothing(project, neo4j_driver, domain_config):
    _write(project, "2026-09-19_second", after="2026-09-18_never_existed")
    out = _register(project, "2026-09-19_second")
    assert out.exit_code == 1
    assert AFTER_UNRESOLVED in out.output
    assert "8 or more hex" in out.output, "the grammar is quoted"
    assert _task_count(neo4j_driver) == 0, "a refusal left a task in the graph"
    assert _pairs(neo4j_driver) == set()


def test_an_ambiguous_prefix_refuses_and_writes_nothing(project, neo4j_driver, domain_config):
    """Two ids sharing an 8-hex prefix. Constructed rather than hoped for: `create_artifact`
    takes the id, so the collision is exact and the test is not a lottery."""
    shared = "abcdef01"
    for i, stem in enumerate(("2026-09-18_a", "2026-09-18_b")):
        _write(project, stem)
        create_artifact(
            project_dir=project, driver=neo4j_driver, database=NEO4J_DB,
            domain_config=domain_config, artifact_type="ResearchTask",
            properties={"description": stem, "name": stem,
                        "source_file": f"cc_tasks/{stem}.md"},
            actor="desktop", authority="accepted",
            artifact_id=f"{shared}-0000-4000-8000-00000000000{i}")
    _write(project, "2026-09-19_c", after=shared)
    out = _register(project, "2026-09-19_c")
    assert out.exit_code == 1
    assert "ambiguous" in out.output
    assert _task_count(neo4j_driver) == 2, "a refusal created a third task"
    assert _pairs(neo4j_driver) == set()


def test_a_header_that_does_not_parse_refuses_and_writes_nothing(project, neo4j_driver):
    _write(project, "2026-09-19_bad", after="after the scan lands")
    out = _register(project, "2026-09-19_bad")
    assert out.exit_code == 1
    assert AFTER_UNRESOLVED in out.output
    assert _task_count(neo4j_driver) == 0


def test_a_self_reference_is_unresolvable_and_writes_nothing(project, neo4j_driver):
    """The self-loop case. A task file naming its OWN stem resolves to nothing, because the
    file is not registered yet — which is the same refusal, before `add_chain`'s guard is
    reached. The guard behind it is `validate_precedes_write`, exercised in
    `tests/test_precedence.py`; this asserts the path never gets there with a bad pair."""
    _write(project, "2026-09-19_self", after="2026-09-19_self")
    out = _register(project, "2026-09-19_self")
    assert out.exit_code == 1
    assert AFTER_UNRESOLVED in out.output
    assert _task_count(neo4j_driver) == 0


def test_re_registering_is_idempotent(project, neo4j_driver, domain_config):
    pred = _existing_task(project, neo4j_driver, domain_config, "2026-09-18_first")
    _write(project, "2026-09-19_second", after="2026-09-18_first")
    assert _register(project, "2026-09-19_second").exit_code == 0
    before = _pairs(neo4j_driver)
    second = _register(project, "2026-09-19_second")
    assert second.exit_code == 0
    assert "already registered" in second.output
    assert _pairs(neo4j_driver) == before
    assert _task_count(neo4j_driver) == 2
    assert len(before) == 1 and next(iter(before))[0] == pred


def test_the_edges_go_through_the_shared_writer(project, neo4j_driver, domain_config):
    """`add_chain` is the ONE writer `seldon task precede`, `seldon task chain` and
    `seldon_task_chain` already use, so the DAG guard is inherited rather than re-implemented.
    Asserted statically, because a second writer would pass every behavioural test above."""
    import inspect

    from seldon.commands import cc
    src = inspect.getsource(cc.write_after_edges)
    assert "add_chain" in src
    assert "create_link" not in src, "the After writer bypassed the precedence guard"


# ------------------------------------------------------------------------------ the MCP path

def test_the_mcp_tool_takes_the_same_path(project, neo4j_driver, domain_config, monkeypatch):
    from seldon import mcp_server

    pred = _existing_task(project, neo4j_driver, domain_config, "2026-09-18_first")
    _write(project, "2026-09-19_second", after="2026-09-18_first")
    out = mcp_server.seldon_cc_register("cc_tasks/2026-09-19_second.md",
                                        project_dir=str(project), allow_untracked=True)
    assert "Registered" in out, out
    assert "after:" in out
    assert any(a == pred for a, _ in _pairs(neo4j_driver))


def test_the_mcp_tool_refuses_an_unresolvable_ref(project, neo4j_driver):
    from seldon import mcp_server

    _write(project, "2026-09-19_second", after="2026-09-18_never_existed")
    out = mcp_server.seldon_cc_register("cc_tasks/2026-09-19_second.md",
                                        project_dir=str(project), allow_untracked=True)
    assert AFTER_UNRESOLVED in out
    assert _task_count(neo4j_driver) == 0


# --------------------------------------------------------------- decision 4: the lint

def test_the_lint_fires_on_a_real_sequencing_line():
    out = sequencing_lint(f"# t\n\n{REAL_SEQUENCING_LINE}\n", "2026-09-16_neo4j_fixture")
    assert out is not None
    assert "2026-09-16_headless_session_polls_to_completion" in out
    assert "**After:**" in out


def test_the_lint_is_silent_when_an_after_header_is_present():
    text = f"# t\n\n**After:** 2026-09-16_headless_session_polls_to_completion\n{REAL_SEQUENCING_LINE}\n"
    assert sequencing_lint(text, "2026-09-16_neo4j_fixture") is None


def test_the_lint_is_silent_on_a_sequencing_line_that_only_orders_sections():
    text = "# t\n\n**SEQUENCING:** §1 → §2 → §3 → push.\n"
    assert sequencing_lint(text, "2026-09-19_x") is None


def test_the_lint_does_not_fire_on_a_line_naming_only_this_task():
    text = "# t\n\n**SEQUENCING:** cc_tasks/2026-09-19_x.md runs its §1 first.\n"
    assert sequencing_lint(text, "2026-09-19_x") is None


def test_the_lint_warns_and_never_refuses(project, neo4j_driver):
    _write(project, "2026-09-19_seq", extra=f"\n{REAL_SEQUENCING_LINE}\n")
    out = _register(project, "2026-09-19_seq")
    assert out.exit_code == 0, out.output
    assert "states an ordering nothing reads" in out.output
    assert _task_count(neo4j_driver) == 1, "the lint refused a registration"
