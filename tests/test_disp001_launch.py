"""DISP-001R Part A: the CLI names the worktree; a launch that never ran is `launch_failed`.

`cc_tasks/2026-10-19_DISP-001R_worktree_name_and_spend_floor.md` Part A, re-issuing DISP-001 and its ADDENDUM 01.
FRICTION-002 passed the task stem as `--worktree <stem>`, and CLI 2.1.302 refuses a name over 64 characters:
RECALL-001 (66) and MCP-001 (70) failed before any model turn and were recorded `session_failed -> blocked`. The
dispatcher now passes `--worktree` with no name, reads the worktree the CLI made from the session's `init` record
(`docs/evidence/disp001r/cli_init_probe.txt`), and records an exit before the first `assistant` message as
`launch_failed`: back on the queue, notified once, and held (c15) until the launcher or the task changes.

The stub `claude` (tests/dispatch_scaffold.py) behaves as the probed CLI does: it refuses a name over 64 characters,
generates one when none is given, cuts the worktree from HEAD and writes `init` before its first turn.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from seldon.commands import dispatch_worktree as W
from seldon.commands.dispatch import dispatch_group
from seldon.core import dispatch as D
from seldon.core.events import read_events
from seldon.domain.loader import load_domain_config
from tests.dispatch_scaffold import RESEARCH_YAML, add_task, git, make_project, register, run_cli, task_states, \
    write_stub

#: 90 characters: the longest stems in this repository run to 90 (DISP-001 "The defect, measured").
LONG_STEM = "2026-10-19_LONG-001_" + "a_task_stem_as_long_as_the_longest_in_this_repository_" + "x" * 16
INVALID = "Error: Invalid worktree name: must be 64 characters or fewer"


@pytest.fixture
def dc():
    return load_domain_config(RESEARCH_YAML)


@pytest.fixture(autouse=True)
def _no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)


def _events(p, kind):
    return [e["payload"] for e in read_events(p) if e["event_type"] == kind]


def _once(p):
    res = run_cli(p, dispatch_group, ["once"])
    assert res.exit_code == 0, res.output
    return res.output


def test_the_long_stem_is_ninety_characters():
    assert len(LONG_STEM) == 90


@pytest.mark.usefixtures("neo4j_available", "clean_test_db")
def test_a_90_character_stem_launches_without_error(tmp_path, neo4j_driver, dc):
    p = make_project(tmp_path)
    add_task(p, LONG_STEM)
    register(p, neo4j_driver, dc, LONG_STEM, "2026-10-19T00:00:00Z")
    write_stub(p, {LONG_STEM: {"write": {"out/long.txt": "long\n"}}})
    out = _once(p)

    launch = _events(p, D.EVENT_LAUNCHED)[-1]
    # No name on the command line: `--worktree` is its last word, so nothing can be read as the name.
    assert launch["command"].endswith(" --worktree"), launch["command"]
    assert launch["worktree_named_by"] == "cli" and launch["stem"] == LONG_STEM
    named = _events(p, W.EVENT_WORKTREE_NAMED)[-1]
    assert named["task_id"] == launch["task_id"] and named["stem"] == LONG_STEM
    assert named["worktree"].startswith(D.CLI_WORKTREE_DIR + "/") and len(Path(named["worktree"]).name) <= 64
    assert named["branch"] == D.CLI_BRANCH_PREFIX + Path(named["worktree"]).name
    assert named["init"]["subtype"] == "init" and named["init"]["cwd"]
    assert git(p, "rev-parse", "--verify", "--quiet", f"refs/heads/{named['branch']}").returncode == 0
    fin = _events(p, D.EVENT_FINISHED)[-1]
    assert fin["outcome"] == "merged" and fin["worktree"] == named["worktree"], (fin, out)
    assert task_states(neo4j_driver)[LONG_STEM] == "completed"
    assert git(p, "show", "main:out/long.txt").stdout == "long\n"


@pytest.mark.usefixtures("neo4j_available", "clean_test_db")
def test_a_cli_exiting_before_its_first_turn_is_launch_failed_proposed_and_not_relaunched(tmp_path, neo4j_driver,
                                                                                         dc):
    p = make_project(tmp_path)
    add_task(p, "lf")
    register(p, neo4j_driver, dc, "lf", "2026-10-19T00:00:00Z")
    write_stub(p, {"lf": {"launch_error": INVALID, "exit": 1}})
    _once(p)

    fin = _events(p, D.EVENT_FINISHED)[-1]
    assert fin["outcome"] == "launch_failed" and fin["stderr_line"] == INVALID, fin
    assert fin["repeat"] is False and fin["fingerprint"]["task_file_sha256"]
    # It never ran: back on the queue (`accepted`, the dispatchable state a claimed task returns to; the
    # ResearchTask machine has no edge back to `proposed`), never left `blocked`.
    assert task_states(neo4j_driver)["lf"] == "accepted"
    notes = [e for e in read_events(p) if e["event_type"] in ("dispatch_notify_failed", "dispatch_notified")]
    assert notes == [] or all(INVALID in str(n) or "launch_failed" in str(n) for n in notes)

    # The next pass does not relaunch it: c15 holds it while the launcher and the task are unchanged.
    launches = len(_events(p, D.EVENT_LAUNCHED))
    out = _once(p)
    assert len(_events(p, D.EVENT_LAUNCHED)) == launches, out
    assert "launch_failed: c15" in out, out


@pytest.mark.usefixtures("neo4j_available", "clean_test_db")
def test_a_changed_task_file_clears_the_launch_failed_hold(tmp_path, neo4j_driver, dc):
    """The negative control (AD-038-R6): the hold is not a block. A change the stderr line can depend on (here the
    task file) lets the dispatcher launch the task again."""
    p = make_project(tmp_path)
    add_task(p, "lf")
    register(p, neo4j_driver, dc, "lf", "2026-10-19T00:00:00Z")
    write_stub(p, {"lf": {"launch_error": INVALID, "exit": 1}})
    _once(p)
    write_stub(p, {"lf": {}})
    task = p / "cc_tasks" / "lf.md"
    task.write_text(task.read_text() + "\nAmended after the launch failure.\n")
    git(p, "commit", "-q", "-am", "amend lf")
    _once(p)
    fin = _events(p, D.EVENT_FINISHED)[-1]
    assert fin["outcome"] == "merged", fin
    assert task_states(neo4j_driver)["lf"] == "completed"
