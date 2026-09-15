"""The standing dispatcher, criterion by criterion and incident by incident.

Implements the test set `ai-readiness-kg/cc_tasks/2026-09-15_standing_dispatcher.md` §1 asks
for, against `ai-readiness-kg/docs/design/2026-09-15_DN-006_standing_dispatcher.md`.

**Every eligibility criterion gets a fixture task file that fails exactly that one.** A suite
that only tested the happy path would prove the evaluator can say yes; the whole value of a
criteria vector is that it says *which* criterion said no, and a fixture that fails two at once
cannot show that.

**The stub `claude` is a shell script, not the CLI.** Zero model calls: the dispatcher's launch
path is a `subprocess.run` of whatever `dispatch.cli` names, so a script that writes a RESULT
and touches the graph exercises the whole claim/launch/finish path with no spend and no network.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest
import yaml

from seldon.core import dispatch as D

SELDON_REPO = Path(__file__).resolve().parents[1]


# =============================================================== fixtures: a project on disk

def _controls(project: Path, daily_tokens: int = 55_000_000) -> None:
    (project / "controls.yaml").write_text(yaml.safe_dump(
        {"spend": {"daily_tokens": daily_tokens, "call_class_floors": {"extraction": 111000}}}
    ), encoding="utf-8")


def _seldon_yaml(project: Path, **over) -> dict:
    block = {"enabled": True, "branch": "main",
             "standing_band_ref": "controls.yaml#spend.daily_tokens",
             "poll_interval_s": 300, "permission_mode": "bypassPermissions",
             "stop_file": ".seldon/DISPATCH_STOP", "log_dir": "logs/dispatch",
             "lease_file": ".seldon/dispatch.lock", "cli": "claude"}
    block.update(over)
    doc = {"event_store": {"path": "seldon_events.jsonl"},
           "neo4j": {"database": "test", "uri": "bolt://localhost:7687"},
           "project": {"domain": "research", "name": "t", "slug": "t"},
           "dispatch": block}
    (project / "seldon.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    return doc


TASK_BODY = textwrap.dedent("""\
    # CC Task — {title}

    **Date:** 2026-09-15
    **Framework layer served (DN-005 §5 rule 1):** {layer}
    **Spend:** {spend} **Network:** {network}

    ## 1. Do the thing.
    """)


def _task_file(project: Path, stem: str, *, layer="§2.2 Tier M", spend="zero model calls.",
               network="none.", track=True) -> Path:
    d = project / "cc_tasks"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{stem}.md"
    p.write_text(TASK_BODY.format(title=stem, layer=layer, spend=spend, network=network),
                 encoding="utf-8")
    if track:
        subprocess.run(["git", "add", str(p.relative_to(project))], cwd=project, check=True,
                       capture_output=True)
    return p


@pytest.fixture
def project(tmp_path) -> Path:
    """A git repository with a controls.yaml, a seldon.yaml and a clean tree on `main`."""
    p = tmp_path / "proj"
    p.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=p, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=p, check=True,
                   capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=p, check=True, capture_output=True)
    _controls(p)
    _seldon_yaml(p)
    # The runtime directories are ignored, exactly as they are in the real project: a STOP file
    # or a lease that counted as a dirty tree would make c7 fail every time c8 did, and no
    # fixture could then isolate either.
    (p / ".gitignore").write_text(".seldon/\nlogs/\n", encoding="utf-8")
    (p / "cc_tasks").mkdir()
    subprocess.run(["git", "add", "-A"], cwd=p, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=p, check=True, capture_output=True)
    return p


def _commit(project: Path, msg="add") -> None:
    subprocess.run(["git", "add", "-A"], cwd=project, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", msg], cwd=project, check=True, capture_output=True)


def _row(project: Path, task_file: Path, state="proposed", preds=(), **over) -> dict:
    t = {"artifact_id": "a" * 8 + "-task", "name": task_file.stem, "state": state,
         "source_file": str(task_file.relative_to(project)), "created_at": "2026-09-15T00:00:00Z",
         "predecessors": list(preds)}
    t.update(over)
    return t


def _evaluate(project: Path, task_file: Path, *, state="proposed", preds=(), cfg_over=None,
              claim=None, lease=None):
    cfg = D.load_dispatch_config(project)
    cfg.update(cfg_over or {})
    band = D.resolve_standing_band(project, cfg["standing_band_ref"])
    return D.evaluate(project, _row(project, task_file, state, preds), cfg, band,
                      D.tree_state(project), claim, lease or {})


# ============================================================== configuration and the band

def test_the_standing_band_is_a_reference_and_resolves_to_what_controls_yaml_holds(project):
    """DN-006 §5: the band is the same number the spend guard enforces. A copy in seldon.yaml
    would drift silently the first time the operator moved the cap, and nothing would say so."""
    assert D.resolve_standing_band(project, "controls.yaml#spend.daily_tokens") == 55_000_000
    _controls(project, 12_000_000)
    assert D.resolve_standing_band(project, "controls.yaml#spend.daily_tokens") == 12_000_000


@pytest.mark.parametrize("ref,fragment", [
    ("controls.yaml", "not a reference"),
    ("nope.yaml#spend.daily_tokens", "does not exist"),
    ("controls.yaml#spend.no_such_key", "has no"),
    ("controls.yaml#spend.call_class_floors", "not an integer"),
])
def test_a_band_reference_that_cannot_resolve_is_a_hard_error(project, ref, fragment):
    """Never a default. A dispatcher that fell back to some number on a broken reference would
    be enforcing a ceiling nobody set."""
    with pytest.raises(D.DispatchConfigError, match=fragment):
        D.resolve_standing_band(project, ref)


def test_a_missing_dispatch_block_refuses_rather_than_guessing(project):
    doc = yaml.safe_load((project / "seldon.yaml").read_text())
    del doc["dispatch"]
    (project / "seldon.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    with pytest.raises(D.DispatchConfigError, match="no `dispatch:` block"):
        D.load_dispatch_config(project)


def test_enabled_must_be_a_real_bool(project):
    """A kill switch that can be the string 'false' — truthy — is a kill switch nobody can
    read (DD-004)."""
    _seldon_yaml(project, enabled="false")
    with pytest.raises(D.DispatchConfigError, match="must be a bool"):
        D.load_dispatch_config(project)


# ==================================================================== candidacy: the headers

def test_a_task_file_with_all_three_headers_is_a_candidate(project):
    f = _task_file(project, "good")
    c = D.candidacy(f)
    assert c["candidate"] and c["reason"] is None
    assert c["headers"][D.HEADER_LAYER].startswith("§2.2")


@pytest.mark.parametrize("stem,body,missing", [
    ("no_spend", "**Date:** x\n**Framework layer served:** none\n**Network:** none\n", "Spend"),
    ("no_network", "**Date:** x\n**Framework layer served:** none\n**Spend:** zero\n", "Network"),
    ("no_layer", "**Date:** x\n**Spend:** zero\n**Network:** none\n", "Framework layer served"),
])
def test_a_file_missing_any_required_header_is_not_a_candidate(project, stem, body, missing):
    """DN-006 decision 2 plus ADDENDUM_01. **Not a candidate**, not "ineligible": the opt-in is
    that nothing already queued changes behaviour when the job is installed, and `status` says
    so in one word."""
    p = project / "cc_tasks" / f"{stem}.md"
    p.write_text(f"# t\n\n{body}\n", encoding="utf-8")
    c = D.candidacy(p)
    assert not c["candidate"]
    assert c["reason"].startswith("no_header:") and missing in c["reason"]


def test_a_framework_layer_header_naming_no_layer_is_not_a_candidate(project):
    """ADDENDUM_01's own criterion. The header being present is not the rule; DN-005 §5 rule 1
    is that a LAYER is named, and a header carrying prose that names none is the shape a rule
    nobody enforces decays into."""
    p = project / "cc_tasks" / "vague.md"
    p.write_text("# t\n\n**Framework layer served:** advances the work generally.\n"
                 "**Spend:** zero **Network:** none\n", encoding="utf-8")
    c = D.candidacy(p)
    assert not c["candidate"]
    assert c["reason"] == "framework_layer_names_no_layer"


@pytest.mark.parametrize("value", ["§2.1", "§2.5", "Tier M", "tier o", "Tier D", "none"])
def test_every_accepted_framework_layer_spelling(project, value):
    p = project / "cc_tasks" / "x.md"
    p.write_text(f"# t\n\n**Framework layer served:** {value}\n"
                 f"**Spend:** zero **Network:** none\n", encoding="utf-8")
    assert D.candidacy(p)["candidate"]


@pytest.mark.parametrize("value,expect", [
    ("zero model calls.", 0), ("zero", 0), ("12M tokens", 12_000_000),
    ("500K tokens", 500_000), ("1,500,000 tokens", 1_500_000), ("up to 3.5M tokens", 3_500_000),
    ("whatever it takes", None),
])
def test_the_spend_header_reads_as_a_token_count_or_refuses(value, expect):
    """`None` is a refusal and never a zero. A Spend line nobody can parse is the one case
    where guessing costs money."""
    assert D.spend_tokens(value) == expect


# ============================================== c1..c9, one fixture failing exactly one each

def test_all_nine_criteria_pass_on_a_clean_task(project):
    f = _task_file(project, "clean")
    _commit(project)
    row = _evaluate(project, f)
    assert row["candidate"]
    assert row["eligible"], json.dumps(row["criteria"], indent=1)
    assert sorted(row["criteria"]) == [f"c{i}" for i in range(1, 10)]


def test_c1_fails_when_the_task_file_is_not_git_tracked(project):
    """A source_file git cannot recover is a task whose spec cannot be read back later; `seldon
    cc register` refuses one for the same reason."""
    f = _task_file(project, "untracked", track=False)
    # IGNORED, not merely unstaged. An unstaged file is dirt, so it would fail c7 as well and
    # the fixture would stop isolating c1; an ignored one is untracked and invisible to
    # `git status`, which is exactly "git cannot recover this task file".
    (project / ".gitignore").write_text(".seldon/\nlogs/\ncc_tasks/untracked.md\n",
                                        encoding="utf-8")
    _commit(project)
    row = _evaluate(project, f)
    assert row["failed"] == ["c1"]
    assert row["criteria"]["c1"]["git_tracked"] is False


def test_c1_fails_from_a_state_that_is_not_open(project):
    f = _task_file(project, "done")
    _commit(project)
    row = _evaluate(project, f, state="completed")
    assert row["failed"] == ["c1"] and row["criteria"]["c1"]["state"] == "completed"


def test_c2_fails_when_a_predecessor_is_blocked(project):
    """DN-006 decision 2: `blocked` and `rejected` are deliberately absent from the satisfied
    set. A successor whose predecessor is blocked is a successor whose premise nobody checked."""
    f = _task_file(project, "successor")
    _commit(project)
    row = _evaluate(project, f, preds=[{"artifact_id": "p1", "state": "blocked"}])
    assert row["failed"] == ["c2"]
    assert row["criteria"]["c2"]["unsatisfied"] == [{"id": "p1", "state": "blocked"}]


@pytest.mark.parametrize("state", list(D.PREDECESSOR_SATISFIED))
def test_c2_passes_on_every_satisfied_predecessor_state(project, state):
    f = _task_file(project, f"succ_{state}")
    _commit(project)
    row = _evaluate(project, f, preds=[{"artifact_id": "p1", "state": state}])
    assert row["criteria"]["c2"]["ok"]


def test_c3_fails_when_a_sibling_addendum_supersedes_the_base_task(project):
    f = _task_file(project, "superseded_base")
    (project / "cc_tasks" / "superseded_base_ADDENDUM_01.md").write_text(
        "# ADDENDUM 01\n\n**Date:** 2026-09-15. **Status:** SUPERSEDED — do not execute.\n",
        encoding="utf-8")
    _commit(project)
    row = _evaluate(project, f)
    assert row["failed"] == ["c3"]
    assert row["criteria"]["c3"]["superseding"] == "superseded_base_ADDENDUM_01.md"


def test_c3_also_reads_the_one_historical_spelling_the_repo_actually_used(project):
    """The marker survey over 34 addenda found exactly one base-task supersession, spelled
    `**Status of base task: SUPERSEDED — DO NOT EXECUTE.**`
    (`2026-09-01_harness_reconciliation_ADDENDUM-01.md`). One instance is not a convention, so
    `**Status:** SUPERSEDED` is what gets written from here on — but a matcher that read only
    the new spelling would report the single genuinely superseded task in that repository as
    executable, which is the one outcome c3 exists to prevent."""
    f = _task_file(project, "historical")
    (project / "cc_tasks" / "historical_ADDENDUM-01.md").write_text(
        "# ADDENDUM-01\n\n**Date:** 2026-09-01. **Status of base task: SUPERSEDED — DO NOT "
        "EXECUTE.**\n", encoding="utf-8")
    _commit(project)
    assert _evaluate(project, f)["failed"] == ["c3"]


def test_c3_does_not_read_an_amending_addendum_as_a_supersession(project):
    """Four of the five Status lines in that repository say `**Status:** AMENDS the base task.
    Does not supersede it.` A case-insensitive match reads the sentence that says the opposite
    as a supersession, which is why the marker is upper-case `SUPERSEDED` and nothing else."""
    f = _task_file(project, "amended")
    (project / "cc_tasks" / "amended_ADDENDUM_01.md").write_text(
        "# ADDENDUM 01\n\n**Status:** AMENDS the base task. Does not supersede it.\n",
        encoding="utf-8")
    _commit(project)
    row = _evaluate(project, f)
    assert row["criteria"]["c3"]["ok"]
    assert row["criteria"]["c3"]["addenda"] == ["amended_ADDENDUM_01.md"]


def test_c3_ignores_a_marker_below_the_ten_line_window(project):
    f = _task_file(project, "late_marker")
    (project / "cc_tasks" / "late_marker_ADDENDUM_01.md").write_text(
        "# ADDENDUM 01\n" + "\n" * 14 + "**Status:** SUPERSEDED\n", encoding="utf-8")
    _commit(project)
    assert _evaluate(project, f)["criteria"]["c3"]["ok"]


def test_c4_fails_above_the_standing_band(project):
    _controls(project, 1_000_000)
    f = _task_file(project, "expensive", spend="up to 12M tokens.")
    _commit(project)
    row = _evaluate(project, f)
    assert row["failed"] == ["c4"]
    assert row["criteria"]["c4"] == {"spend_header": "up to 12M tokens. **Network:** none.",
                                     "declared_tokens": 12_000_000,
                                     "standing_band": 1_000_000,
                                     "band_ref": "controls.yaml#spend.daily_tokens",
                                     "ok": False}


def test_c4_fails_on_an_unparseable_spend_header(project):
    f = _task_file(project, "vague_spend", spend="as needed.")
    _commit(project)
    row = _evaluate(project, f)
    assert row["failed"] == ["c4"] and row["criteria"]["c4"]["declared_tokens"] is None


def test_c5_fails_when_the_network_header_declares_hosts(project):
    f = _task_file(project, "networked", network="the sixteen FSS hosts.")
    _commit(project)
    row = _evaluate(project, f)
    assert row["failed"] == ["c5"]
    assert D.first_refusal_reason(row) == "network_undeclared"


def test_c5_accepts_the_cadence_provenance_decision_8_will_write(project):
    """DN-006 decision 5's second limb. Decision 8 is not implemented here; the criterion
    recognises its output now so it does not have to change when the cadence task lands."""
    f = _task_file(project, "cadenced", network="hosts, under cadence monthly_scan.")
    _commit(project)
    assert _evaluate(project, f)["criteria"]["c5"]["ok"]


def test_c6_fails_while_a_dispatcher_claim_is_in_flight(project):
    """Concurrency is one (DD-019). Two runners on one queue is the batch-identity defect at
    runner grain, and that one spent 22.0M against a 12M ceiling."""
    f = _task_file(project, "concurrent")
    _commit(project)
    row = _evaluate(project, f, claim={"artifact_id": "other", "claimed_by": "dispatcher:h:1"})
    assert row["failed"] == ["c6"]


def test_c7_fails_on_a_dirty_tree_and_names_the_paths(project):
    f = _task_file(project, "dirty")
    _commit(project)
    (project / "scratch.txt").write_text("x", encoding="utf-8")
    row = _evaluate(project, f)
    assert row["failed"] == ["c7"]
    assert row["criteria"]["c7"]["dirty_paths"] == ["scratch.txt"]


def test_c7_fails_on_the_wrong_branch(project):
    f = _task_file(project, "branchy")
    _commit(project)
    subprocess.run(["git", "checkout", "-b", "side"], cwd=project, check=True,
                   capture_output=True)
    row = _evaluate(project, f)
    assert row["failed"] == ["c7"]
    assert row["criteria"]["c7"] == {"branch": "side", "configured_branch": "main",
                                     "dirty": False, "dirty_count": 0, "dirty_paths": [],
                                     "ok": False}


def test_c8_fails_when_disabled(project):
    f = _task_file(project, "off")
    _commit(project)
    row = _evaluate(project, f, cfg_over={"enabled": False})
    assert row["failed"] == ["c8"]
    assert D.first_refusal_reason(row) == "disabled"


def test_c8_fails_while_a_stop_file_exists(project):
    """The burn's idiom, reused rather than a third kill switch invented (DN-006 §2)."""
    f = _task_file(project, "stopped")
    _commit(project)
    (project / ".seldon").mkdir(exist_ok=True)
    (project / ".seldon" / "DISPATCH_STOP").write_text("operator", encoding="utf-8")
    row = _evaluate(project, f)
    assert row["failed"] == ["c8"]
    assert D.first_refusal_reason(row) == "stop_file"


def test_a_system_wide_refusal_is_reported_ahead_of_a_task_specific_one(project):
    """`disabled` is a fact about the PASS. Reporting `network_undeclared` on a disabled pass
    would put a task's name on a refusal that had nothing to do with it."""
    f = _task_file(project, "both", network="hosts.")
    _commit(project)
    row = _evaluate(project, f, cfg_over={"enabled": False})
    assert set(row["failed"]) == {"c5", "c8"}
    assert D.first_refusal_reason(row) == "disabled"


def test_a_task_with_no_source_file_is_not_a_candidate_and_gets_no_criteria(project):
    """23 of the 24 tasks open in ai-readiness-kg at this writing were created with `seldon
    task create` and carry no source_file. They are not candidates and they never evaluate,
    which is the opt-in working."""
    cfg = D.load_dispatch_config(project)
    row = D.evaluate(project, {"artifact_id": "x", "state": "proposed", "source_file": None},
                     cfg, 10, D.tree_state(project), None, {})
    assert row["candidate"] is False and row["criteria"] == {}
    assert row["not_a_candidate_reason"] == "no_source_file"


def test_fifo_is_the_only_ordering(project):
    """DN-006 decision 9. The Desktop orders work with `precedes` edges; a priority field would
    be a value nobody measured."""
    rows = [{"task_id": "b", "created_at": "2026-09-15T02:00:00Z"},
            {"task_id": "a", "created_at": "2026-09-15T01:00:00Z"},
            {"task_id": "c", "created_at": "2026-09-15T03:00:00Z"}]
    assert [r["task_id"] for r in D.fifo(rows)] == ["a", "b", "c"]


# ================================================================================ the lease

def test_a_second_instance_cannot_take_the_lease(project):
    path = project / ".seldon" / "dispatch.lock"
    with D.Lease(path):
        with pytest.raises(D.LeaseHeld):
            with D.Lease(path):
                pass


def test_the_lease_is_held_against_a_REAL_second_process(project, tmp_path):
    """A mocked flock proves the mock works. `fcntl.flock` is per open-file-description and
    per PROCESS, so a same-process second acquire is a weaker claim than the one the lease
    makes; this takes the lock in a child and asserts the parent is refused while it lives."""
    path = project / ".seldon" / "dispatch.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    ready, done = tmp_path / "ready", tmp_path / "done"
    script = tmp_path / "holder.py"
    script.write_text(textwrap.dedent(f"""
        import sys, time, pathlib
        sys.path.insert(0, {str(SELDON_REPO)!r})
        from seldon.core.dispatch import Lease
        with Lease(pathlib.Path({str(path)!r})):
            pathlib.Path({str(ready)!r}).write_text("y")
            while not pathlib.Path({str(done)!r}).exists():
                time.sleep(0.02)
    """), encoding="utf-8")
    child = subprocess.Popen([sys.executable, str(script)])
    try:
        for _ in range(500):
            if ready.exists():
                break
            time.sleep(0.02)
        assert ready.exists(), "the holder process never took the lease"
        with pytest.raises(D.LeaseHeld) as caught:
            with D.Lease(path):
                pass
        assert str(child.pid) in caught.value.body["holder"]
        assert caught.value.body["pid"] == child.pid
    finally:
        done.write_text("y")
        child.wait(timeout=10)
    # and it is free the moment the holder exits
    with D.Lease(path):
        pass


def test_reap_refuses_while_the_holder_pid_is_alive(project):
    """DD-022's orphan rule, adopted unchanged: PID liveness, never age. An age threshold
    releases a lease a healthy long-running holder still needs."""
    path = project / ".seldon" / "dispatch.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"holder": "dispatcher:h:%d" % os.getpid(), "pid": os.getpid(),
                                "acquired_at": "now", "task": None}), encoding="utf-8")
    out = D.reap_lease(path)
    assert out == {"reaped": False, "reason": "holder_alive",
                   "holder": f"dispatcher:h:{os.getpid()}", "pid": os.getpid()}
    assert path.is_file()


def test_reap_releases_a_lease_whose_holder_is_gone(project):
    path = project / ".seldon" / "dispatch.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    path.write_text(json.dumps({"holder": f"dispatcher:h:{dead.pid}", "pid": dead.pid}),
                    encoding="utf-8")
    out = D.reap_lease(path)
    assert out["reaped"] and out["reason"] == "holder_gone"
    assert not path.exists()


def test_reap_on_no_lease_file_is_not_an_error(project):
    assert D.reap_lease(project / ".seldon" / "nothing.lock")["reason"] == "no_lease_file"


# ===================================================================== the DD-007 API-key gate

def test_an_api_key_in_the_environment_is_detected(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    assert D.api_key_present() is None
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")
    assert D.api_key_present() == "ANTHROPIC_API_KEY"


def test_the_launch_command_is_the_protocol_sentence_with_the_permission_mode():
    """The prompt is `CLAUDE.md`'s own dispatch line, not a paraphrase: a dispatcher that
    reworded it would be sending a session a different instruction from the one an operator
    sends, and the difference would show up only in what the session did."""
    from seldon.commands.dispatch import DISPATCH_LINE, _launch_cmd
    rel = "cc_tasks/2026-09-15_standing_dispatcher.md"
    prompt = DISPATCH_LINE.format(rel=rel, stem=Path(rel).stem)
    cmd = _launch_cmd({"cli": "claude", "permission_mode": "bypassPermissions"}, prompt)
    assert cmd == ["claude", "-p", prompt, "--permission-mode", "bypassPermissions"]
    assert prompt == (
        "Read CLAUDE.md, then execute cc_tasks/2026-09-15_standing_dispatcher.md. Glob and "
        "read all sibling 2026-09-15_standing_dispatcher_ADDENDUM*.md files before starting; "
        "an addendum can amend or SUPERSEDE the base task.")


def test_the_claim_path_walks_proposed_through_accepted():
    """`proposed -> in_progress` is not an edge on the ResearchTask state machine. DN-006
    decision 4 calls the claim "the in_progress transition"; from `proposed` it is two, and the
    walk is the shape `walk_to_completed` already uses."""
    from seldon.commands.dispatch import CLAIM_PATH
    from seldon.domain.loader import load_domain_config
    dc = load_domain_config(SELDON_REPO / "seldon" / "domain" / "research.yaml")
    sm = dc.state_machines["ResearchTask"]
    assert "in_progress" not in sm["proposed"]
    assert CLAIM_PATH["proposed"] == ["accepted", "in_progress"]
    assert CLAIM_PATH["accepted"] == ["in_progress"]
    state = "proposed"
    for target in CLAIM_PATH["proposed"]:
        assert target in sm[state]
        state = target
