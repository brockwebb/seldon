"""QC-001 Part G (AD-037-R9): parallel dispatch stays at `max_parallel: 1` in every project until R6's stations and
the dispatcher's disk preflight are live; a project opts in only by an accepted register record anchored at
AD-037-R9 that names it in its scope.

The portfolio test reads every `seldon.yaml` with a `dispatch:` block beside this repository (the operator's GitHub
root): it is the check that fails when one is raised above 1 without the record.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import yaml

from seldon.core import decisions, qc

SELDON = Path(__file__).resolve().parents[1]


def _rec(rid, anchor, scope, status="accepted"):
    data = {"rationale": {"anchor": anchor}, "scope": scope}
    return SimpleNamespace(id=rid, status=status, get=data.get)


def _yaml(tmp_path, repo, block):
    p = tmp_path / repo / "seldon.yaml"
    p.parent.mkdir(parents=True)
    p.write_text(yaml.safe_dump({"dispatch": block}), encoding="utf-8")
    return p


def test_above_one_without_an_opt_in_record_is_a_finding_and_with_one_is_not(tmp_path):
    p = _yaml(tmp_path, "proj", {"enabled": True, "max_parallel": 2})
    assert qc.parallel_findings(p, set()), "max_parallel 2 with no opt-in must be a finding"
    opted = qc.parallel_opt_ins([_rec("seldon:OPT-1", "AD-037-R9", ["proj"]),
                                 _rec("seldon:AD-037-R9", "AD-037-R9", ["other"]),
                                 _rec("seldon:OPT-2", "AD-037-R9", ["late"], status="proposed")])
    assert opted == {"proj"}, "only an accepted record other than the ruling itself opts a project in"
    assert qc.parallel_findings(p, opted) == []
    assert qc.parallel_findings(_yaml(tmp_path, "one", {"enabled": True}), set()) == [], "absent means 1"


def test_every_dispatch_block_in_the_portfolio_is_held_at_one():
    config = yaml.safe_load((SELDON / "seldon.yaml").read_text(encoding="utf-8"))
    u = decisions.universe(SELDON, config)
    opted = qc.parallel_opt_ins([r for repo in u.scope_repos() for r in u.records(repo).values()])
    files = [p for p in sorted(SELDON.parent.glob("*/seldon.yaml"))
             if isinstance((yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("dispatch"), dict)]
    assert SELDON / "seldon.yaml" in files
    findings = [f for p in files for f in qc.parallel_findings(p, opted)]
    assert findings == [], findings


# --------------------------------------------------------------------------------- SQ-012 Part F: at the dispatcher


def _project(tmp_path):
    p = tmp_path / "proj"
    p.mkdir()
    (p / "seldon_events.jsonl").write_text("", encoding="utf-8")
    return p


def _refusals(p):
    import json
    rows = [json.loads(x) for x in (p / "seldon_events.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    return [r for r in rows if r.get("event_type") == "dispatch_refused"]


def test_the_dispatcher_refuses_a_parallel_pass_with_no_opt_in_record(tmp_path, monkeypatch):
    """QC-001 premise 7: the hold was enforced by a test only. Now the pass itself refuses: no launch, a refusal
    event naming the reason, exit as an ordinary outcome."""
    from seldon.commands import dispatch as cmd
    from seldon.commands import dispatch_worktree as W

    def launched(*a, **k):
        raise AssertionError("a parallel pass launched with no opt-in record")

    monkeypatch.setattr(W, "pass_parallel", launched)
    p = _project(tmp_path)
    assert cmd._pass(p, {}, None, None, None, "s1", {"max_parallel": 2}, None, False) is None
    (ev,) = _refusals(p)
    assert ev["payload"]["reason"] == "parallel_not_opted_in" and ev["payload"]["max_parallel"] == 2


def test_an_opted_in_project_passes_to_the_parallel_pass(tmp_path, monkeypatch):
    from seldon.commands import dispatch as cmd
    from seldon.commands import dispatch_worktree as W
    monkeypatch.setattr(qc, "parallel_opted_in", lambda project_dir, config: True)
    monkeypatch.setattr(W, "pass_parallel", lambda *a, **k: "parallel")
    p = _project(tmp_path)
    assert cmd._pass(p, {}, None, None, None, "s1", {"max_parallel": 2}, None, False) == "parallel"
    assert _refusals(p) == []


def test_opt_ins_are_read_from_seldons_register_for_a_project_with_none(tmp_path):
    """A project with no register of its own is not opted in by seldon's register as it stands (no AD-037-R9 opt-in
    record exists yet), and the reader does not fail on it."""
    assert qc.parallel_opted_in(_project(tmp_path), {}) is False
