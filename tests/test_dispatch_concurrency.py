"""SEL-004 decision 1: independence is DECLARED, by resource, and never inferred.

`cc_tasks/2026-10-07_SEL-004_worktree_per_task_dispatch.md`. Two optional task headers,
`**Exclusive:** yes|no` (default yes) and `**Touches:** <resource>, ...`, and a scheduler that
launches a non-exclusive task only when its Touches is disjoint from every running task's.
The model is GitHub Actions `concurrency` groups and Make/Bazel declared outputs: the author
names the lock and the scheduler never guesses one.

Pure functions only; the passes that use them are in `test_dispatch_parallel.py`.
"""
from __future__ import annotations

import pytest

from seldon.core import dispatch as D

RESOURCES = {"neo4j": {"paths": []},
             "views": {"paths": ["docs/views/**", "site/"]},
             "spend_ledger": {"paths": ["state/spend_ledger.jsonl"]}}


def conc(exclusive=None, touches=None):
    return D.parse_concurrency(exclusive, touches, RESOURCES)


# ===================================================================== the header grammar

def test_a_task_with_neither_header_is_exclusive_and_undeclared():
    """"A task with neither header behaves exactly as now": it runs alone."""
    c = conc()
    assert c == {"declared": False, "exclusive": True, "resources": [], "paths": [],
                 "error": None}


def test_a_non_exclusive_task_names_resources_and_globs():
    c = conc("no", "neo4j, `kg/**`, ./Makefile, docs/a.md.")
    assert c["error"] is None and c["declared"] and c["exclusive"] is False
    assert c["resources"] == ["neo4j"]
    assert c["paths"] == ["kg/**", "Makefile", "docs/a.md"]


def test_touches_without_exclusive_keeps_the_default_yes():
    """Default yes is the spec's; an author who forgets `Exclusive: no` gets the safe
    reading, a task that runs alone, never the fast one."""
    c = conc(None, "kg/**")
    assert c["error"] is None and c["declared"] and c["exclusive"] is True


def test_touches_none_declares_nothing_touched():
    c = conc("no", "none — writes only its RESULT")
    assert c["error"] is None and c["resources"] == [] and c["paths"] == []


@pytest.mark.parametrize("exclusive,touches,needle", [
    ("maybe", "kg/**", "Exclusive"),
    ("no", None, "non-exclusive task must declare"),
    ("no", "", "Touches header is empty"),
    ("no", "neo4J", "unknown resource 'neo4J'"),
    ("no", "/abs/path", "'/abs/path'"),
    ("no", "kg/../secrets", "'kg/../secrets'"),
    ("no", "kg/a b.py", "'kg/a b.py'"),
    ("no", "kg/**, ,", "empty item"),
])
def test_an_unparseable_declaration_refuses_with_the_grammar_quoted(exclusive, touches,
                                                                     needle):
    """Refuse with the grammar quoted, as `network_undeclared` does (decision 1)."""
    c = conc(exclusive, touches)
    assert c["error"] is not None and needle in c["error"]
    assert D.CONCURRENCY_GRAMMAR in c["error"]


def test_parse_headers_reads_the_two_optional_headers():
    text = ("**Spend:** zero. **Network:** none.\n**Framework layer served:** none\n"
            "**Exclusive:** no\n**Touches:** neo4j, kg/**\n")
    assert D.parse_concurrency_headers(text) == {"Exclusive": "no", "Touches": "neo4j, kg/**"}
    # The three required headers' parse is unchanged by the two new ones.
    assert set(D.parse_headers(text)) == set(D.REQUIRED_HEADERS)


# ============================================================ glob overlap, conservatively

@pytest.mark.parametrize("a,b,overlap", [
    ("docs/**", "docs/a.md", True),
    ("src/a*.py", "src/b*.py", False),
    ("*.py", "*.md", False),
    ("*.md", "docs/a.md", True),
    ("kg/x.py", "kg/x.py", True),
    ("kg/x.py", "kg/y.py", False),
    ("kg/x.py", "kg/x.pyc", False),
    ("a/[bc].py", "a/b.py", True),
    ("site/", "site/index.html", True),
    ("docs/views", "docs/views/m.md", True),
    ("docs/views", "docs/viewsx.md", False),
    ("events/batch-*.jsonl", "events/batch-007.jsonl", True),
    ("events/batch-*.jsonl", "state/spend_ledger.jsonl", False),
])
def test_globs_may_overlap_is_sound(a, b, overlap):
    """Sound, not exact: a path matching both globs starts with both literal prefixes and
    ends with both literal suffixes, so prefixes or suffixes that are not related prove the
    globs disjoint. Anything else is treated as overlapping, so the failure direction is an
    unnecessary wait and never two writers on one file."""
    assert D.globs_may_overlap(a, b) is overlap
    assert D.globs_may_overlap(b, a) is overlap


def test_named_resources_overlap_by_name_and_by_their_paths():
    a, b = conc("no", "neo4j"), conc("no", "neo4j")
    assert D.touches_overlap(a, b, RESOURCES) == ["neo4j"]
    # `views` expands to docs/views/** and site/, so a raw path under it collides.
    assert D.touches_overlap(conc("no", "views"), conc("no", "site/app.js"), RESOURCES) == [
        "site/** ~ site/app.js"]
    assert D.touches_overlap(conc("no", "neo4j"), conc("no", "kg/**"), RESOURCES) == []


# ======================================================================== the launch plan

def _cand(tid, exclusive=None, touches=None):
    return {"task_id": tid, "concurrency": conc(exclusive, touches)}


def test_two_disjoint_non_exclusive_tasks_launch_together():
    plan = D.plan_launches([_cand("a", "no", "kg/**"), _cand("b", "no", "docs/**")], [], 2,
                           RESOURCES)
    assert plan["launch"] == ["a", "b"] and plan["deferred"] == {}


def test_overlapping_tasks_serialize_and_the_later_one_says_why():
    plan = D.plan_launches([_cand("a", "no", "kg/**"), _cand("b", "no", "kg/x.py")], [], 2,
                           RESOURCES)
    assert plan["launch"] == ["a"]
    assert plan["deferred"]["b"]["reason"] == "overlap"
    assert plan["deferred"]["b"]["with"] == ["a"]
    assert plan["deferred"]["b"]["overlap"] == ["kg/** ~ kg/x.py"]


def test_two_neo4j_tasks_serialize():
    plan = D.plan_launches([_cand("a", "no", "neo4j"), _cand("b", "no", "neo4j, kg/**")], [],
                           4, RESOURCES)
    assert plan["launch"] == ["a"] and plan["deferred"]["b"]["overlap"] == ["neo4j"]


def test_a_running_task_holds_its_resources():
    running = [{"task_id": "r", "concurrency": conc("no", "neo4j")}]
    plan = D.plan_launches([_cand("a", "no", "neo4j"), _cand("b", "no", "kg/**")], running, 3,
                           RESOURCES)
    assert plan["launch"] == ["b"] and plan["deferred"]["a"]["with"] == ["r"]


def test_an_exclusive_task_waits_for_running_ones_and_blocks_new_ones():
    """Writer preference (Courtois, Heymans and Parnas 1971, the second readers-writers
    problem): a waiting exclusive task holds everything, so a stream of disjoint tasks cannot
    starve it."""
    running = [{"task_id": "r", "concurrency": conc("no", "kg/**")}]
    plan = D.plan_launches([_cand("x"), _cand("b", "no", "docs/**")], running, 4, RESOURCES)
    assert plan["launch"] == []
    assert plan["deferred"]["x"] == {"reason": "exclusive_waits", "with": ["r"], "overlap": []}
    assert plan["deferred"]["b"]["reason"] == "exclusive" and plan["deferred"]["b"]["with"] == [
        "x"]


def test_an_exclusive_task_launches_alone_when_nothing_runs():
    plan = D.plan_launches([_cand("x"), _cand("b", "no", "docs/**")], [], 4, RESOURCES)
    assert plan["launch"] == ["x"] and plan["deferred"]["b"]["with"] == ["x"]


def test_a_running_exclusive_task_blocks_everything():
    running = [{"task_id": "x", "concurrency": conc()}]
    plan = D.plan_launches([_cand("b", "no", "docs/**")], running, 4, RESOURCES)
    assert plan["launch"] == [] and plan["deferred"]["b"]["reason"] == "exclusive"


def test_max_parallel_caps_launches_and_waiting_tasks_reserve_in_fifo_order():
    """A task waiting for a slot reserves its resources, so a later task that overlaps it
    cannot overtake it when a slot frees (per-resource FIFO, as GitHub Actions queues a
    concurrency group)."""
    plan = D.plan_launches([_cand("a", "no", "kg/**"), _cand("b", "no", "docs/**"),
                            _cand("c", "no", "docs/x.md")], [], 1, RESOURCES)
    assert plan["launch"] == ["a"]
    assert plan["deferred"]["b"]["reason"] == "max_parallel"
    assert plan["deferred"]["c"] == {"reason": "overlap", "with": ["b"],
                                     "overlap": ["docs/** ~ docs/x.md"]}


# =========================================================================== configuration

def _cfg(**over):
    block = {"enabled": True, "branch": "main", "standing_band_ref": "c.yaml#a",
             "poll_interval_s": 300, "permission_mode": "bypassPermissions",
             "stop_file": ".seldon/STOP", "log_dir": "logs", "lease_file": ".seldon/l"}
    block.update(over)
    return {"dispatch": block}


def test_max_parallel_defaults_to_one_and_adds_nothing_else(tmp_path):
    cfg = D.load_dispatch_config(tmp_path, _cfg())
    assert cfg["max_parallel"] == 1


@pytest.mark.parametrize("over,needle", [
    ({"max_parallel": 0}, "max_parallel"),
    ({"max_parallel": True}, "max_parallel"),
    ({"max_parallel": 2}, "gate_command"),
    ({"max_parallel": 2, "gate_command": "make gate", "resources": {"Bad Name": {}}},
     "resources"),
    ({"max_parallel": 2, "gate_command": "make gate", "resources": {"neo4j": {"paths": "x"}}},
     "resources"),
    ({"max_parallel": 2, "gate_command": "make gate", "shared_paths": ["/abs"]},
     "shared_paths"),
])
def test_a_malformed_parallel_config_refuses_at_load(tmp_path, over, needle):
    with pytest.raises(D.DispatchConfigError, match=needle):
        D.load_dispatch_config(tmp_path, _cfg(**over))


def test_a_parallel_config_fills_its_declared_defaults(tmp_path):
    cfg = D.load_dispatch_config(tmp_path, _cfg(max_parallel=3, gate_command="make gate"))
    for key, value in D.PARALLEL_DEFAULTS.items():
        assert cfg[key] == value
