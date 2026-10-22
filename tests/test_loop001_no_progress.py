"""LOOP-001 Part A (AD-034 ADDENDUM 04): the Stop hook ends a session on no progress, not on a count.

`cc_tasks/2026-10-20_LOOP-001_stop_hook_no_progress_rule.md` Part A. Each Stop the gate refuses is a round, and the
round records a fingerprint of its checks' outputs (exit code, stdout, stderr; volatile spans masked). Two consecutive
rounds with the same fingerprint end the session `no_progress`, which the finish reads as `stop_gate_unpassed`; rounds
whose outputs differ continue with no count. FRICTION-002's block cap (`stop_hook_block_cap`, 20, no measured basis)
is withdrawn: the loader refuses the key and the launch no longer sets `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`.

Prior art: the vendor's loop pattern (code.claude.com/docs/en/workflows, "keep fixing until a check passes ... or two
rounds in a row make no progress"); Reflexion (Shinn et al. 2023), a retry carries new information or stops. No model
call, no Neo4j.
"""
from __future__ import annotations

import sys

import pytest

from seldon.commands import dispatch as S
from seldon.core import stations as Q
from tests import stations_scaffold as F

#: A check that prints the tree's `state.txt` and fails: the session "makes progress" by changing that file.
STATE_CHECK = f"{sys.executable} -c \"import sys, pathlib; print(pathlib.Path('state.txt').read_text()); sys.exit(1)\""
#: The same, with pytest's summary line, whose duration differs on every run.
TIMED_CHECK = (f"{sys.executable} -c \"import sys, time, pathlib; print(pathlib.Path('state.txt').read_text()); "
               f"print('1 failed in %.4fs' % (time.time() % 7)); sys.exit(1)\"")


def _project(tmp_path, check=STATE_CHECK, state="first\n"):
    p = F.make_project(tmp_path, check_a=check)
    (p / "state.txt").write_text(state, encoding="utf-8")
    F.launch(p, session_id="child-1")
    F.write_log(p, 1000)
    F.record(p, Q.EVENT_PART_COMPLETE, {"part": "A", "planned_share": 0.5, "tokens": 10})
    return p


def test_two_identical_rounds_end_the_session_no_progress(tmp_path):
    p = _project(tmp_path)
    first = F.gate(p)
    assert first["block"] is True and first["record"]["verdict"] == "block"
    assert first["record"]["round"] == 1
    second = F.gate(p)
    assert second["block"] is False, "the same output twice is no progress: the session is let go"
    assert second["record"]["verdict"] == "no_progress"
    assert second["record"]["no_progress"] == {"rounds": [1, 2]}
    assert second["record"]["fingerprint"] == first["record"]["fingerprint"]
    assert second["hard_stop"] is None
    reading = S._gate_reading(p, F.TASK_ID, "child-1")
    assert reading["passed"] is False and reading["why"].startswith("no_progress"), reading


def test_three_rounds_whose_outputs_differ_continue(tmp_path):
    p = _project(tmp_path)
    rounds = []
    for n, state in enumerate(("first\n", "second\n", "third\n"), 1):
        (p / "state.txt").write_text(state, encoding="utf-8")
        out = F.gate(p)
        rounds.append(out["record"])
        assert out["block"] is True and out["record"]["verdict"] == "block", (n, out["record"])
        assert out["record"]["round"] == n
    assert len({r["fingerprint"] for r in rounds}) == 3


def test_a_round_that_passes_ends_the_session_pass(tmp_path):
    p = _project(tmp_path)
    assert F.gate(p)["record"]["verdict"] == "block"
    (p / "cc_tasks" / f"{F.STEM}.md").write_text(
        (p / "cc_tasks" / f"{F.STEM}.md").read_text(encoding="utf-8").replace(STATE_CHECK, F.PASS), encoding="utf-8")
    out = F.gate(p)
    assert out["block"] is False and out["record"]["verdict"] == "pass"
    assert S._gate_reading(p, F.TASK_ID, "child-1")["passed"] is True


def test_a_duration_alone_is_not_progress(tmp_path):
    """pytest prints its run time on the summary line; without the mask two identical failures never compare equal."""
    p = _project(tmp_path, check=TIMED_CHECK)
    assert F.gate(p)["record"]["verdict"] == "block"
    assert F.gate(p)["record"]["verdict"] == "no_progress"


def test_the_block_cap_key_is_refused_at_load():
    with pytest.raises(Q.StationsConfigError, match="stop_hook_block_cap"):
        Q.load_stations_config({"stations": {"stop_hook_block_cap": 20}})
    assert "stop_hook_block_cap" not in Q.STATIONS_DEFAULTS


def test_the_launch_sets_no_block_cap(tmp_path):
    p = F.make_project(tmp_path)
    env = S._worktree_env(p, {"env": {}}, F.config(p)["dispatch"])
    assert "CLAUDE_CODE_STOP_HOOK_BLOCK_CAP" not in env
    assert not hasattr(S, "STOP_HOOK_BLOCK_CAP_ENV")
