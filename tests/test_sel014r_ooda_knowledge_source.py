"""SEL-014R Part B: the OODA between chained tasks is a knowledge source the dispatcher launches (AD-038-R16, R17).

`cc_tasks/2026-10-28_SEL-014R_the_ooda_is_a_knowledge_source_the_dispatcher_launches.md`;
`docs/design/AD-038_ADDENDUM_07_the_ooda_as_a_knowledge_source.md`.

The session is a shell stub standing in for `claude -p ... --worktree` (the `tests/test_dispatch_launch.py` pattern):
it cuts and enters `.claude/worktrees/<name>` as the CLI does, prints `init` and a first `assistant` message, may write
an addendum in its worktree, sleep, or report usage, and ends on a stream-json `result` whose text carries the
`OODA-VERDICT:` line. Everything else is the dispatcher's real code: `_launch_cmd`, `_run` with its inspector and
reap, the verdict check, the addendum's commit, the worktree's removal and the record.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from seldon.commands import dispatch as S
from seldon.commands import dispatch_ooda as DO
from seldon.core import dispatch as D
from seldon.core import ooda as O
from seldon.core.events import read_events
from tests.models_fixture import FIXTURE_IDS, use_stub_cli
from tests.test_dispatch import _commit, _seldon_yaml, _task_file, project  # noqa: F401  (fixture)

PRED = "b" * 8 + "-pred"
SUCC = "a" * 8 + "-succ"
NOW = datetime(2026, 10, 28, 12, 0, 0, tzinfo=timezone.utc)
ADDENDUM = "cc_tasks/n1_ADDENDUM_01_path_moved.md"


def _enable(project, **ooda):
    _seldon_yaml(project, ooda_grace_s=60, ooda={"enabled": True, "inspect_every_s": 0.2, **ooda})
    _commit(project, "enable")


def _chain(project):
    """n0 (completed, with a RESULT) precedes n1 (proposed). Returns the pass's task row for n1 and the due item."""
    _task_file(project, "n0")
    (project / "cc_tasks" / "n0_RESULT.md").write_text("# RESULT n0\n\nThe path moved to b/.\n", encoding="utf-8")
    _task_file(project, "n1")
    _commit(project, "chain")
    pred = {"artifact_id": PRED, "state": "completed", "name": "n0", "source_file": "cc_tasks/n0.md",
            "updated_at": "2026-10-28T11:00:00Z"}
    succ = {"artifact_id": SUCC, "name": "n1", "state": "proposed", "source_file": "cc_tasks/n1.md",
            "created_at": "2026-10-28T10:00:00Z", "predecessors": [pred]}
    return succ


def _stub(project, verdict: dict | None, *, addendum: str | None = None, sleep: float = 0, usage: int = 0,
          exit_code: int = 0, model_turn: bool = True, commit_on_branch: bool = False) -> Path:
    """A `claude` stand-in. `verdict` None prints a result with no verdict line."""
    bin_ = project / "bin"
    bin_.mkdir(exist_ok=True)
    text = "Read the RESULT.\n" + (f"{O.VERDICT_PREFIX} {json.dumps(verdict)}" if verdict is not None else "done")
    result = {"type": "result", "subtype": "success", "result": text, "usage": {"output_tokens": 1},
              "modelUsage": {FIXTURE_IDS["opus"]: {"outputTokens": 1, "inputTokens": 1}}}
    (bin_ / "result.json").write_text(json.dumps(result) + "\n", encoding="utf-8")
    assistant = {"type": "assistant", "message": {"id": "stub-1", "role": "assistant", "content": [],
                                                  "usage": {"input_tokens": usage, "output_tokens": 1}}}
    (bin_ / "assistant.json").write_text(json.dumps(assistant) + "\n", encoding="utf-8")
    lines = ["#!/bin/sh",
             'for a in "$@"; do last="$a"; done',
             'if [ "$last" = "--worktree" ]; then top="$(git rev-parse --show-toplevel)"; '
             'git -C "$top" worktree add -q -b worktree-ooda-stub "$top/.claude/worktrees/ooda-stub" HEAD '
             '|| exit 9; cd "$top/.claude/worktrees/ooda-stub" || exit 9; fi',
             'printf \'{"type":"system","subtype":"init","cwd":"%s"}\\n\' "$(pwd -P)"']
    if model_turn:
        lines.append(f'cat "{bin_ / "assistant.json"}"')
    if addendum:
        lines.append(f'printf "# ADDENDUM 01 to n1: the path moved\\n\\nRead b/ for a/.\\n" > {addendum}')
    if commit_on_branch:
        lines.append('printf "x\\n" > stray.txt && git add stray.txt && git commit -q -m stray')
    if sleep:
        lines.append(f"sleep {sleep}")
    lines += [f'cat "{bin_ / "result.json"}"', f"exit {exit_code}"]
    stub = bin_ / "claude"
    stub.write_text("\n".join(lines) + "\n", encoding="utf-8")
    stub.chmod(0o755)
    use_stub_cli(project.parent, stub)
    return stub


def _fire(project):
    config = yaml.safe_load((project / "seldon.yaml").read_text())
    cfg = D.load_dispatch_config(project, config)
    return DO.fire(project, config, cfg, None, [_chain(project)])


def _records(project):
    return [e for e in read_events(project) if e["event_type"] in O.RECORD_KINDS]


def _worktrees(project):
    out = subprocess.run(["git", "worktree", "list", "--porcelain"], cwd=project, capture_output=True, text=True)
    return [ln for ln in out.stdout.splitlines() if ln.startswith("worktree ") and ".claude/worktrees" in ln]


# ================================================================================================ configuration

def test_disabled_knowledge_source_fires_nothing_and_c18_is_absent(project):
    """Negative control (AD-038-R17): off, nothing is launched, c18 is absent, and `ooda_grace_s` holds nothing."""
    _seldon_yaml(project, ooda_grace_s=3600)
    succ = _chain(project)
    config = yaml.safe_load((project / "seldon.yaml").read_text())
    cfg = D.load_dispatch_config(project, config)
    assert cfg["ooda"]["enabled"] is False
    assert S._ooda_fire(project, config, cfg, None, None, None) == []
    assert D.ooda_waits(project, [succ], cfg, D.ooda_index([]), NOW) == {}


def test_an_enabled_source_needs_its_session_timeout(project):
    _seldon_yaml(project, ooda={"enabled": True})
    with pytest.raises(D.DispatchConfigError, match="ooda_grace_s"):
        D.load_dispatch_config(project)


@pytest.mark.parametrize("bad", [{"enabled": "yes"}, {"token_cap": 0}, {"max_per_pass": True}, {"colour": 1}])
def test_a_malformed_ooda_block_refuses_at_load(project, bad):
    _seldon_yaml(project, ooda_grace_s=60, ooda=bad)
    with pytest.raises(D.DispatchConfigError, match="dispatch.ooda"):
        D.load_dispatch_config(project)


# ================================================================================================ c18 (R17)

def _gate(project, succ, events):
    cfg = D.load_dispatch_config(project)
    return D.ooda_waits(project, [succ], cfg, D.ooda_index(events), NOW)[SUCC]


def _rec(kind, **payload):
    return {"event_type": kind, "timestamp": "2026-10-28T11:30:00Z", "payload": {"task_id": PRED, **payload}}


@pytest.mark.parametrize("kind", [O.OODA_OK, O.OODA_AMENDED, O.OODA_EXPIRED])
def test_ok_amended_and_expired_records_release(project, kind):
    _enable(project)
    g = _gate(project, _chain(project), [_rec(kind)])
    assert g["ok"] and g["predecessors"][0]["released_by"] == kind


def test_a_blocked_record_holds_and_a_later_desktop_record_releases(project):
    """Negative control: once a record exists, only `ooda_blocked` holds; a Desktop's answer after it releases."""
    _enable(project)
    succ = _chain(project)
    blocked = _rec(O.OODA_BLOCKED, question="which band?", answering_note="docs/design/AD-099.md")
    g = _gate(project, succ, [blocked])
    w = g["predecessors"][0]
    assert not g["ok"] and (w["held"], w["question"]) == ("blocked", "which band?")
    cfg = D.load_dispatch_config(project)
    band = D.resolve_standing_band(project, cfg["standing_band_ref"])
    row = D.evaluate(project, succ, cfg, band, D.tree_state(project), None, {},
                     ooda=D.ooda_waits(project, [succ], cfg, D.ooda_index([blocked]), NOW))
    assert D.first_refusal_reason(row) == "ooda_blocked" and "ooda_blocked" in D.REFUSAL_REASONS
    answered = {**_rec(D.EVENT_OODA_RECORDED, by="desktop"), "timestamp": "2026-10-28T11:40:00Z"}
    assert _gate(project, succ, [blocked, answered])["predecessors"][0]["released_by"] == "ooda_event"


def test_due_groups_successors_skips_recorded_predecessors_and_runs_oldest_first():
    p_old = {"artifact_id": "old", "state": "completed", "source_file": "cc_tasks/o.md"}
    p_new = {"artifact_id": "new", "state": "verified", "source_file": "cc_tasks/n.md"}
    p_done = {"artifact_id": "done", "state": "completed", "source_file": "cc_tasks/d.md"}
    p_open = {"artifact_id": "open", "state": "in_progress", "source_file": "cc_tasks/x.md"}
    tasks = [{"artifact_id": "s1", "state": "proposed", "predecessors": [p_new, p_done]},
             {"artifact_id": "s2", "state": "accepted", "predecessors": [p_old, p_new, p_open]},
             {"artifact_id": "s3", "state": "blocked", "predecessors": [p_old]}]
    rows = O.due(tasks, {"done": {"kind": O.OODA_OK}}, {"old": "2026-10-27T00:00:00Z", "new": "2026-10-28T00:00:00Z"},
                 lambda p: False)
    assert [(r["predecessor"]["artifact_id"], [s["artifact_id"] for s in r["successors"]]) for r in rows] == [
        ("old", ["s2"]), ("new", ["s1", "s2"])]


# ================================================================================================ the verdict

@pytest.mark.parametrize("text,reason", [
    ("all good", "no_verdict"),
    (f"{O.VERDICT_PREFIX} {{not json", "verdict_unreadable"),
    (f'{O.VERDICT_PREFIX} {{"verdict": "maybe"}}', "verdict_unreadable"),
    (f'{O.VERDICT_PREFIX} {{"verdict": "amended", "note": "x"}}', "addendum_missing"),
    (f'{O.VERDICT_PREFIX} {{"verdict": "blocked", "note": "x"}}', "verdict_unreadable"),
])
def test_a_verdict_the_dispatcher_cannot_check_is_refused(text, reason):
    v = O.parse_verdict(text)
    assert not v["ok"] and v["reason"] == reason and reason in O.EXPIRED_REASONS


def test_the_last_verdict_line_wins_and_backticks_are_tolerated():
    v = O.parse_verdict(f'{O.VERDICT_PREFIX} {{"verdict": "blocked", "question": "q", "answering_note": "n"}}\n'
                        f'`{O.VERDICT_PREFIX} {{"verdict": "ok", "note": "read"}}`')
    assert v["ok"] and (v["verdict"], v["note"]) == ("ok", "read")


def test_the_brief_names_the_result_the_successor_the_next_addendum_and_the_premise_outcomes(project):
    _enable(project)
    succ = _chain(project)
    (project / "cc_tasks" / "n1_ADDENDUM_01_earlier.md").write_text("# earlier\n", encoding="utf-8")
    item = {"predecessor": succ["predecessors"][0], "successors": [succ], "completed_at": None}
    review = lambda pd, text: {"premises": [{"statement": "a exists", "kind": "check", "outcome": "false",  # noqa
                                             "command": "test -d a", "check": {"tail": "exit 1"}}]}
    b = O.brief(project, {}, item, review, lambda text, stem, tid: (["  result seldon:x  2026  hit"], None))
    assert (b["result"], b["result_exists"]) == ("cc_tasks/n0_RESULT.md", True)
    s = b["successors"][0]
    assert s["addendum_prefix"] == "cc_tasks/n1_ADDENDUM_02_" and s["addenda"] == ["cc_tasks/n1_ADDENDUM_01_earlier.md"]
    text = O.prompt(b)
    assert "seldon go --brief" in text and "premise (false): a exists | check: test -d a -> exit 1" in text
    assert "cc_tasks/n1_ADDENDUM_02_" in text and O.VERDICT_PREFIX in text and "result seldon:x" in text


# ================================================================================================ the session

def test_an_ok_verdict_is_recorded_and_the_worktree_and_branch_are_removed(project):
    _enable(project)
    _stub(project, {"verdict": "ok", "note": "nothing in n1 changes"})
    [out] = _fire(project)
    assert out["kind"] == O.OODA_OK
    [rec] = _records(project)
    p = rec["payload"]
    assert (rec["event_type"], p["task_id"], p["note"], p["by"]) == (O.OODA_OK, PRED, "nothing in n1 changes",
                                                                     "knowledge_source")
    assert p["successors"] == [{"task_id": SUCC, "file": "cc_tasks/n1.md"}]
    assert p["session"]["exit"] == 0 and p["session"]["kept"] is False and p["session"]["branch_deleted"]
    assert _worktrees(project) == []
    assert (project / p["session"]["log"]).is_file() and p["session"]["log"].endswith(DO.LOG_SUFFIX)


def test_an_amended_verdict_commits_the_addendum_before_the_record(project):
    _enable(project)
    _stub(project, {"verdict": "amended", "note": "path moved", "addenda": [ADDENDUM]}, addendum=ADDENDUM)
    [out] = _fire(project)
    assert out["kind"] == O.OODA_AMENDED
    p = out["payload"]
    assert p["addenda"] == [ADDENDUM] and p["commit"]
    assert (project / ADDENDUM).read_text().startswith("# ADDENDUM 01 to n1")
    assert D.is_tracked(project, project / ADDENDUM)
    log = subprocess.run(["git", "log", "-1", "--format=%s", "--", ADDENDUM], cwd=project, capture_output=True,
                         text=True).stdout
    assert "OODA knowledge source" in log and "AD-038-R16" in log
    assert _worktrees(project) == []


def test_an_amended_verdict_without_its_addendum_is_expired(project):
    """Negative control: the dispatcher does not trust a verdict it cannot check, and the chain proceeds."""
    _enable(project)
    _stub(project, {"verdict": "amended", "note": "path moved", "addenda": [ADDENDUM]})
    [out] = _fire(project)
    assert (out["kind"], out["payload"]["reason"]) == (O.OODA_EXPIRED, "addendum_missing")
    assert not (project / ADDENDUM).exists()


def test_a_misnamed_addendum_is_expired(project):
    _enable(project)
    wrong = "cc_tasks/n1_ADDENDUM_07_skipped_ahead.md"
    _stub(project, {"verdict": "amended", "addenda": [wrong]}, addendum=wrong)
    [out] = _fire(project)
    assert (out["kind"], out["payload"]["reason"]) == (O.OODA_EXPIRED, "addendum_misnamed")
    assert not (project / wrong).exists()


def test_a_blocked_verdict_names_its_question_and_holds_the_successor(project):
    _enable(project)
    _stub(project, {"verdict": "blocked", "note": "needs a ruling", "question": "is c18 per-project?",
                    "answering_note": "docs/design/AD-038_the_machine_reconciles_its_own_state.md"})
    [out] = _fire(project)
    assert out["kind"] == O.OODA_BLOCKED and out["payload"]["question"] == "is c18 per-project?"
    succ = _chain(project)
    g = _gate(project, succ, read_events(project))
    assert not g["ok"] and g["predecessors"][0]["held"] == "blocked"
    rows = D.ooda_pending(project, [succ], D.load_dispatch_config(project), D.ooda_index(read_events(project)), NOW)
    assert [(r["predecessor"], r["question"]) for r in rows] == [(PRED, "is c18 per-project?")]


def test_an_expired_session_proceeds_and_says_why(project):
    """Negative control: a timeout is a record (`ooda_expired`), not a hold."""
    _enable(project)
    _seldon_yaml(project, ooda_grace_s=1, ooda={"enabled": True, "inspect_every_s": 0.2})
    _commit(project, "timeout 1s")
    _stub(project, {"verdict": "ok"}, sleep=30)
    [out] = _fire(project)
    p = out["payload"]
    assert (out["kind"], p["reason"]) == (O.OODA_EXPIRED, "timeout") and p["session"]["seconds"] < 25
    g = _gate(project, _chain(project), read_events(project))
    assert g["ok"] and g["predecessors"][0]["released_by"] == O.OODA_EXPIRED


def test_a_session_past_its_token_cap_is_reaped(project):
    _enable(project, token_cap=1000)
    _stub(project, {"verdict": "ok"}, usage=5000, sleep=30)
    [out] = _fire(project)
    assert (out["kind"], out["payload"]["reason"]) == (O.OODA_EXPIRED, "token_cap")
    assert out["payload"]["session"]["tokens"] >= 5000


@pytest.mark.parametrize("kw,reason", [({"exit_code": 3}, "exit_nonzero"), ({"model_turn": False}, "launch_failed")])
def test_a_failed_session_is_expired(project, kw, reason):
    _enable(project)
    _stub(project, {"verdict": "ok"}, **kw)
    [out] = _fire(project)
    assert (out["kind"], out["payload"]["reason"]) == (O.OODA_EXPIRED, reason)


def test_a_session_that_committed_on_its_branch_keeps_its_worktree(project):
    _enable(project)
    _stub(project, {"verdict": "ok", "note": "read"}, commit_on_branch=True)
    [out] = _fire(project)
    s = out["payload"]["session"]
    assert out["kind"] == O.OODA_OK and s["kept"] is True and "1 commit" in s["why"]
    assert len(_worktrees(project)) == 1


def test_a_recorded_predecessor_is_not_run_again(project):
    _enable(project)
    _stub(project, {"verdict": "ok"})
    assert len(_fire(project)) == 1
    assert _fire(project) == [] and len(_records(project)) == 1


def test_max_per_pass_bounds_the_runs_and_says_how_many_wait(project, capsys):
    _enable(project)
    _stub(project, {"verdict": "ok"})
    succ = _chain(project)
    other = {**succ["predecessors"][0], "artifact_id": "c" * 8 + "-pred", "updated_at": "2026-10-28T11:30:00Z"}
    succ2 = {**succ, "artifact_id": "d" * 8 + "-succ", "predecessors": [other]}
    config = yaml.safe_load((project / "seldon.yaml").read_text())
    cfg = D.load_dispatch_config(project, config)
    out = DO.fire(project, config, cfg, None, [succ, succ2])
    assert [o["payload"]["task_id"] for o in out] == [PRED]
    assert "1 more due" in capsys.readouterr().out
