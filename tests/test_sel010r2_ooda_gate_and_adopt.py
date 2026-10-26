"""SEL-010R2: the dispatcher waits for the Desktop OODA between chained tasks, and a project adopts it in one step.

`cc_tasks/2026-10-26_SEL-010R2_dispatch_waits_for_the_desktop_ooda_between_chained_tasks.md` (statement of record:
`cc_tasks/2026-10-25_SEL-010_dispatch_waits_for_the_desktop_ooda_between_chained_tasks.md`); rulings AD-038-R10 and
R11 (`docs/design/AD-038_ADDENDUM_03_the_ooda_between_chained_tasks_and_adoption.md`).

A. c18: a task whose `precedes` predecessor completed is eligible once an OODA record for the predecessor exists (an
   `ooda_recorded` event, or a committed `<stem>_OODA.md`), or once `dispatch.ooda_grace_s` has passed since the
   completion. 0 never waits, and c18 is then absent. Each fixture fails exactly c18 or passes it.
B. `dispatch.candidacy_headers` (Spend and Network the minimum) and `seldon dispatch adopt`, against a project on disk
   and a kit on disk, so the real seldon.yaml is never read or written.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from seldon.core import adopt as A
from seldon.core import dispatch as D
from seldon.core import reconcile as R
from tests.test_dispatch import _commit, _row, _seldon_yaml, _task_file, project  # noqa: F401  (fixture)

SELDON_REPO = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)
PRED = "b" * 8 + "-pred"


def _cfg(project, **over):
    cfg = D.load_dispatch_config(project)
    cfg.update(over)
    return cfg


def _chained(project, pred_state="completed", **pred):
    """A successor task file whose one predecessor is `pred_state`, with a predecessor task file beside it."""
    _task_file(project, "n0")
    succ = _task_file(project, "n1")
    _commit(project)
    p = {"artifact_id": PRED, "state": pred_state, "name": "n0", "source_file": "cc_tasks/n0.md",
         "updated_at": None, **pred}
    return _row(project, succ, preds=[p])


def _completed_event(task_id, at):
    return {"event_type": "artifact_state_changed", "timestamp": at.isoformat().replace("+00:00", "Z"),
            "payload": {"artifact_id": task_id, "from_state": "in_progress", "to_state": "completed"}}


def _ooda_event(task_id, at=NOW):
    return {"event_type": D.EVENT_OODA_RECORDED, "timestamp": at.isoformat().replace("+00:00", "Z"),
            "payload": {"task_id": task_id, "by": "desktop", "note": "premise 2 was wrong"}}


def _eval(project, row, cfg, events):
    band = D.resolve_standing_band(project, cfg["standing_band_ref"])
    gates = D.ooda_waits(project, [row], cfg, D.ooda_index(events), NOW)
    return D.evaluate(project, row, cfg, band, D.tree_state(project), None, {}, ooda=gates)


# ══════════════════════════════════════════════════════════════════════════════
# Part A: c18
# ══════════════════════════════════════════════════════════════════════════════

def test_a_grace_of_zero_never_waits_and_c18_is_absent(project):
    """The default: installing this build changes no project's queue or criteria vector."""
    row = _chained(project)
    cfg = _cfg(project)
    assert cfg["ooda_grace_s"] == D.OODA_GRACE_S_DEFAULT == 0
    out = _eval(project, row, cfg, [_completed_event(PRED, NOW)])
    assert "c18" not in out["criteria"] and out["eligible"]


def test_c18_holds_a_chained_task_until_the_ooda_on_its_completed_predecessor(project):
    row = _chained(project)
    cfg = _cfg(project, ooda_grace_s=3600)
    out = _eval(project, row, cfg, [_completed_event(PRED, NOW - timedelta(seconds=60))])
    assert out["failed"] == ["c18"]
    assert D.first_refusal_reason(out) == "ooda_pending"
    w = out["criteria"]["c18"]["predecessors"][0]
    assert (w["released_by"], w["elapsed_s"], w["completed_at_source"]) == (None, 60, "ledger")
    assert w["ooda_file"] == "cc_tasks/n0_OODA.md"
    assert "ooda_pending" in D.REFUSAL_REASONS


def test_an_ooda_recorded_event_releases_it_and_the_vector_records_why(project):
    row = _chained(project)
    cfg = _cfg(project, ooda_grace_s=3600)
    out = _eval(project, row, cfg, [_completed_event(PRED, NOW - timedelta(seconds=60)), _ooda_event(PRED)])
    assert out["eligible"], out["failed"]
    g = out["criteria"]["c18"]
    assert g["ok"] and g["predecessors"][0]["released_by"] == "ooda_event"
    assert g["predecessors"][0]["ooda_event"]["note"] == "premise 2 was wrong"


def test_the_ooda_file_releases_it_only_once_committed(project):
    """The successor's worktree is cut from main's HEAD; an uncommitted record would not reach it."""
    row = _chained(project)
    cfg = _cfg(project, ooda_grace_s=3600)
    events = [_completed_event(PRED, NOW - timedelta(seconds=60))]
    (project / "cc_tasks" / "n0_OODA.md").write_text("# OODA on n0\n", encoding="utf-8")
    held = D.ooda_waits(project, [row], cfg, D.ooda_index(events), NOW)[row["artifact_id"]]
    assert not held["ok"]
    assert held["predecessors"][0]["ooda_file_exists"] and not held["predecessors"][0]["ooda_file_tracked"]
    _commit(project, "ooda")
    out = _eval(project, row, cfg, events)
    assert out["eligible"] and out["criteria"]["c18"]["predecessors"][0]["released_by"] == "ooda_file"


def test_the_grace_releases_it_without_a_record(project):
    row = _chained(project)
    cfg = _cfg(project, ooda_grace_s=600)
    out = _eval(project, row, cfg, [_completed_event(PRED, NOW - timedelta(seconds=601))])
    assert out["eligible"] and out["criteria"]["c18"]["predecessors"][0]["released_by"] == "grace"


@pytest.mark.parametrize("state", ["superseded", "withdrawn"])
def test_a_predecessor_that_left_no_result_does_not_hold_its_successor(project, state):
    row = _chained(project, pred_state=state)
    out = _eval(project, row, _cfg(project, ooda_grace_s=3600), [])
    assert "c18" not in out["criteria"] and out["eligible"]


def test_a_verified_predecessor_holds_like_a_completed_one(project):
    row = _chained(project, pred_state="verified")
    out = _eval(project, row, _cfg(project, ooda_grace_s=3600), [_completed_event(PRED, NOW)])
    assert out["failed"] == ["c18"]


def test_with_no_ledger_completion_the_graphs_updated_at_bounds_the_grace(project):
    row = _chained(project, updated_at="2026-10-26T11:00:00Z")
    out = _eval(project, row, _cfg(project, ooda_grace_s=600), [])
    w = out["criteria"]["c18"]["predecessors"][0]
    assert (w["released_by"], w["completed_at_source"], w["elapsed_s"]) == ("grace", "graph_updated_at", 3600)


def test_a_completion_time_nobody_recorded_fails_closed_until_a_record(project):
    row = _chained(project)
    cfg = _cfg(project, ooda_grace_s=600)
    out = _eval(project, row, cfg, [])
    w = out["criteria"]["c18"]["predecessors"][0]
    assert out["failed"] == ["c18"] and w["elapsed_s"] is None and "unknown" in w["message"]
    assert _eval(project, row, cfg, [_ooda_event(PRED)])["eligible"]


def test_the_grace_runs_from_the_last_completion():
    """A task redriven and completed again has a newer RESULT to read."""
    first, again = NOW - timedelta(hours=5), NOW - timedelta(minutes=1)
    idx = D.ooda_index([_completed_event(PRED, first), _completed_event(PRED, again)])
    assert D._parse_ts(idx["completed_at"][PRED]) == again


@pytest.mark.parametrize("bad", [-1, True, "600"])
def test_a_grace_that_is_not_a_non_negative_number_refuses_at_load(project, bad):
    _seldon_yaml(project, ooda_grace_s=bad)
    with pytest.raises(D.DispatchConfigError, match="ooda_grace_s"):
        D.load_dispatch_config(project)


def test_the_refusal_line_names_the_predecessor_and_the_command_that_releases_it(project):
    from seldon.commands import dispatch as S
    row = _chained(project)
    out = _eval(project, row, _cfg(project, ooda_grace_s=3600), [_completed_event(PRED, NOW - timedelta(seconds=60))])
    lines = S._refusal_lines([out], D.tree_state(project))
    assert lines[0].split()[1] == "ooda_pending:"
    assert "3540 s of 3600 s grace left" in lines[1]
    assert "cc_tasks/n0_OODA.md" in lines[1] and f"seldon dispatch ooda record {PRED[:8]}" in lines[1]


def test_the_reconciler_commits_an_untracked_ooda_file_beside_a_registered_task(project):
    """A Desktop session writes the file as it writes an addendum; the next pass commits it (AD-038-R1)."""
    _task_file(project, "n0")
    _commit(project)
    (project / "cc_tasks" / "n0_OODA.md").write_text("# OODA\n", encoding="utf-8")
    (project / "cc_tasks" / "stray_OODA.md").write_text("# not a task's\n", encoding="utf-8")
    found = R.classify(project, yaml.safe_load((project / "seldon.yaml").read_text()), {"cc_tasks/n0.md"})
    assert found["classes"]["task_files"]["paths"] == ["cc_tasks/n0_OODA.md"]
    assert [u["path"] for u in found["unreconciled"]] == ["cc_tasks/stray_OODA.md"]


# ══════════════════════════════════════════════════════════════════════════════
# Part B: per-project candidacy headers
# ══════════════════════════════════════════════════════════════════════════════

def _no_layer_file(project, stem="nolayer"):
    d = project / "cc_tasks"
    p = d / f"{stem}.md"
    p.write_text(f"# {stem}\n\n**Spend:** zero model calls.\n**Network:** none.\n**Owner:** hazbrief\n",
                 encoding="utf-8")
    _commit(project)
    return p


def test_a_project_without_the_key_keeps_the_three_headers(project):
    assert D.load_dispatch_config(project)["candidacy_headers"] == D.REQUIRED_HEADERS
    out = D.candidacy(_no_layer_file(project), D.REQUIRED_HEADERS)
    assert out["reason"] == f"no_header:{D.HEADER_LAYER}"


def test_a_project_on_the_minimum_does_not_require_the_framework_layer(project):
    _seldon_yaml(project, candidacy_headers=["Spend", "Network"])
    cfg = D.load_dispatch_config(project)
    f = _no_layer_file(project)
    band = D.resolve_standing_band(project, cfg["standing_band_ref"])
    out = D.evaluate(project, _row(project, f), cfg, band, D.tree_state(project), None, {})
    assert out["candidate"] and out["eligible"], out
    assert out["criteria"]["c9"]["framework_layer"] is None


def test_a_project_may_add_a_header_of_its_own(project):
    assert D.candidacy(_no_layer_file(project), ("Spend", "Network", "Owner"))["candidate"]
    assert D.candidacy(_task_file(project, "plain"), ("Spend", "Network", "Owner"))["reason"] == "no_header:Owner"


@pytest.mark.parametrize("bad", [["Spend"], ["Network", "Owner"], [], "Spend", [""]])
def test_a_list_without_the_kit_wide_minimum_refuses_at_load(project, bad):
    _seldon_yaml(project, candidacy_headers=bad)
    with pytest.raises(D.DispatchConfigError, match="candidacy_headers"):
        D.load_dispatch_config(project)


def test_the_parts_refusal_says_an_addendum_cannot_supply_the_header(tmp_path):
    """SEL-010's ADDENDUM-00 carried every header and registration still refused (the finding before launch)."""
    from seldon.core import stations as QS
    base = tmp_path / "cc_tasks"
    base.mkdir()
    (base / "t.md").write_text("# t\n", encoding="utf-8")
    (base / "t_ADDENDUM_00.md").write_text("# t addendum\n**Parts:** A 1.0.\n", encoding="utf-8")
    (tmp_path / "baseline.txt").write_text("", encoding="utf-8")
    msg = QS.parts_registration_refusal(base / "t.md", tmp_path, {"qc": {"parts_baseline": "baseline.txt"}})
    assert msg.startswith("parts_undeclared") and "an addendum cannot supply it" in msg


# ══════════════════════════════════════════════════════════════════════════════
# Part B: `seldon dispatch adopt`
# ══════════════════════════════════════════════════════════════════════════════

KIT_YAML = """\
dispatch:
  enabled: true
  branch: main
  standing_band_ref: controls.yaml#spend.daily_tokens
  poll_interval_s: 300
  permission_mode: bypassPermissions
  stop_file: .seldon/DISPATCH_STOP
  lease_file: .seldon/dispatch.lock
  log_dir: logs/dispatch
  notify: >-
    osascript -e 'display notification "$SELDON_NOTIFY_MESSAGE"'
  notify_timeout_s: 30
  stuck_after_passes: 3
  stuck_after_passes_by_criterion:
    dirty_tree: 1
  launchd_label: com.kit.kit-dispatch
  allow:
    - rule: Bash(cp *)
      instruction: "the kit's own"
jobs:
  dispatch:
    log_max_line_chars: 2000
    log_max_run_bytes: 2097152
    log_retention_days: 30
"""

PROJECT_YAML = """\
# The project's own comment, which adopt must keep.
event_store:
  path: seldon_events.jsonl
project:
  # inner comment
  name: hb
  slug: hb
  domain: research

# A comment before the last block.
prior_art:
  ref: ../kit/seldon.yaml#prior_art
"""


@pytest.fixture
def kit(tmp_path) -> Path:
    k = tmp_path / "kit"
    k.mkdir()
    (k / "seldon.yaml").write_text(KIT_YAML, encoding="utf-8")
    (k / "controls.yaml").write_text(yaml.safe_dump({"spend": {"daily_tokens": 1_000_000}}), encoding="utf-8")
    return k


@pytest.fixture
def adoptee(tmp_path) -> Path:
    p = tmp_path / "hb"
    p.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=p, check=True, capture_output=True)
    (p / "seldon.yaml").write_text(PROJECT_YAML, encoding="utf-8")
    (p / ".gitignore").write_text(".venv/\n", encoding="utf-8")
    return p


def _answers(adoptee, kit):
    return {k: d for k, _q, d in A.questions(adoptee, yaml.safe_load(PROJECT_YAML), A.kit_config(kit), kit)}


def test_adopt_asks_only_what_is_the_projects_and_defaults_the_band_to_the_kits_rerooted(adoptee, kit):
    ans = _answers(adoptee, kit)
    assert set(ans) == {"standing_band_ref", "branch", "launchd_label"}
    assert ans["standing_band_ref"] == "../kit/controls.yaml#spend.daily_tokens"
    assert ans["branch"] == "main" and ans["launchd_label"].endswith(".hb-dispatch")


def test_adopt_writes_a_block_that_validates_keeps_every_comment_and_a_plist_that_matches(adoptee, kit):
    out = A.adoption(adoptee, _answers(adoptee, kit), kit_dir=kit)
    written = A.write_adoption(adoptee, out)
    text = (adoptee / "seldon.yaml").read_text(encoding="utf-8")
    for comment in ("# The project's own comment", "# inner comment", "# A comment before the last block."):
        assert comment in text
    cfg = D.load_dispatch_config(adoptee)
    assert cfg["enabled"] is False and cfg["max_parallel"] == 1 and cfg["ooda_grace_s"] == 0
    assert cfg["candidacy_headers"] == D.MINIMUM_HEADERS
    assert cfg["allow"] == [] and "launchd_label" in cfg and cfg["launchd_label"] != "com.kit.kit-dispatch"
    assert D.resolve_standing_band(adoptee, cfg["standing_band_ref"]) == 1_000_000
    jobs = yaml.safe_load(text)["jobs"]["dispatch"]
    assert set(jobs) == set(A.JOB_KEYS)
    assert yaml.safe_load(text)["prior_art"] == {"ref": "../kit/seldon.yaml#prior_art"}
    plist = out["plist_path"].read_text(encoding="utf-8")
    assert f"<integer>{cfg['poll_interval_s']}</integer>" in plist
    assert f"<string>{kit / A.KIT_WRAPPER}</string>" in plist and f"<string>{adoptee.resolve()}</string>" in plist
    ignore = (adoptee / ".gitignore").read_text(encoding="utf-8")
    assert ".venv/" in ignore and ".seldon/dispatch.lock" in ignore and ".claude/worktrees/" in ignore
    assert set(written) == {"seldon.yaml", str(out["plist_path"].relative_to(adoptee.resolve())), ".gitignore"}
    # A second run finds nothing to add.
    again = A.adoption(adoptee, _answers(adoptee, kit), kit_dir=kit)
    assert (again["seldon_yaml"], again["plist"], again["gitignore_add"]) == (None, None, [])


def test_adopt_never_rewrites_a_key_the_project_already_has(adoptee, kit):
    (adoptee / "seldon.yaml").write_text(PROJECT_YAML + "dispatch:\n  # ours\n  poll_interval_s: 600\n  "
                                         "branch: trunk\n", encoding="utf-8")
    config = yaml.safe_load((adoptee / "seldon.yaml").read_text())
    ans = {k: d for k, _q, d in A.questions(adoptee, config, A.kit_config(kit), kit)}
    assert "branch" not in ans
    A.write_adoption(adoptee, A.adoption(adoptee, ans, kit_dir=kit))
    cfg = D.load_dispatch_config(adoptee)
    assert (cfg["poll_interval_s"], cfg["branch"]) == (600, "trunk")
    assert "# ours" in (adoptee / "seldon.yaml").read_text()


def test_adopt_refuses_a_band_reference_that_does_not_resolve_and_writes_nothing(adoptee, kit):
    before = (adoptee / "seldon.yaml").read_text()
    with pytest.raises(A.AdoptError, match="does not validate"):
        A.adoption(adoptee, {**_answers(adoptee, kit), "standing_band_ref": "nope.yaml#a.b"}, kit_dir=kit)
    assert (adoptee / "seldon.yaml").read_text() == before


def test_the_cli_dry_run_prints_the_block_and_the_plist_and_writes_nothing(adoptee, kit):
    """The real kit's machine-wide values (read, never written); the band is given, since no squiddy sits beside a
    temporary project."""
    from seldon.commands.dispatch import dispatch_group
    before = (adoptee / "seldon.yaml").read_text()
    res = CliRunner().invoke(dispatch_group, ["adopt", "--project", str(adoptee), "--yes", "--dry-run",
                                              "--standing-band-ref", os.path.relpath(kit / "controls.yaml", adoptee)
                                              + "#spend.daily_tokens"])
    assert res.exit_code == 0, res.output
    assert "dry run: nothing written" in res.output and "--- seldon.yaml as it would be written ---" in res.output
    assert "<key>StartInterval</key>" in res.output
    assert (adoptee / "seldon.yaml").read_text() == before and not (adoptee / A.PLIST_DIR).exists()


def test_the_wrapper_reads_the_project_and_plist_it_is_given(adoptee, kit, tmp_path):
    """The plist `adopt` writes runs the kit's wrapper with two arguments; the wrapper's interval check then reads
    THAT project's seldon.yaml and THAT plist, and refuses when they differ."""
    A.write_adoption(adoptee, A.adoption(adoptee, _answers(adoptee, kit), kit_dir=kit))
    plist = next((adoptee / A.PLIST_DIR).glob("*.plist"))
    plist.write_text(plist.read_text().replace("<integer>300</integer>", "<integer>600</integer>"))
    log = tmp_path / "wrapper.log"
    env = {**os.environ, "SELDON_DISPATCH_LOG": str(log), "NEO4J_PASSWORD": "unused"}
    res = subprocess.run(["/bin/bash", str(SELDON_REPO / A.KIT_WRAPPER), str(adoptee), str(plist)], env=env,
                         capture_output=True, text=True)
    assert res.returncode == 2, (res.stdout, res.stderr)
    assert "poll_interval_s=300 but the plist StartInterval=600" in log.read_text()


# ══════════════════════════════════════════════════════════════════════════════
# Part A, through the graph: `seldon dispatch ooda pending` and `ooda record`
# ══════════════════════════════════════════════════════════════════════════════

neo4j_tests = pytest.mark.usefixtures("neo4j_available", "clean_test_db")


@pytest.fixture
def chain_project(tmp_path, monkeypatch, clean_test_db):
    from tests.testdb import TEST_DATABASE
    p = tmp_path / "chain"
    p.mkdir()
    (p / "seldon_events.jsonl").touch()
    (p / "controls.yaml").write_text(yaml.safe_dump({"spend": {"daily_tokens": 1_000_000}}), encoding="utf-8")
    doc = {"project": {"name": "chain", "domain": "research", "slug": "chain"},
           "neo4j": {"database": TEST_DATABASE, "uri": os.getenv("NEO4J_URI", "bolt://localhost:7687")},
           "event_store": {"path": "seldon_events.jsonl"},
           "dispatch": {"enabled": False, "branch": "main", "standing_band_ref": "controls.yaml#spend.daily_tokens",
                        "poll_interval_s": 300, "permission_mode": "bypassPermissions",
                        "stop_file": ".seldon/DISPATCH_STOP", "log_dir": "logs/dispatch",
                        "lease_file": ".seldon/dispatch.lock", "ooda_grace_s": 3600}}
    (p / "seldon.yaml").write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    monkeypatch.chdir(p)
    return p


@neo4j_tests
def test_ooda_pending_lists_the_result_to_read_and_ooda_record_releases_it(neo4j_driver, chain_project):
    from seldon.commands.dispatch import _tasks, dispatch_group
    from seldon.core.events import read_events
    from seldon.core.precedence import add_chain
    from seldon.domain.loader import load_domain_config
    from tests.test_sel008_cross_project_waits_and_block_reason import RESEARCH_YAML, _task
    from tests.testdb import TEST_DATABASE
    dc = load_domain_config(RESEARCH_YAML)
    n0 = _task(chain_project, neo4j_driver, TEST_DATABASE, dc, "N", state="completed",
               source_file="cc_tasks/n0.md", name="n0")
    n1 = _task(chain_project, neo4j_driver, TEST_DATABASE, dc, "N+1", source_file="cc_tasks/n1.md", name="n1")
    add_chain(chain_project, neo4j_driver, TEST_DATABASE, dc, [n0, n1], reason="chain")

    runner = CliRunner()
    res = runner.invoke(dispatch_group, ["ooda", "pending", "--json"])
    assert res.exit_code == 0, res.output
    rows = json.loads(res.output)
    assert [(r["predecessor"], r["successor"]) for r in rows] == [(n0, n1)]
    assert rows[0]["result"] == "cc_tasks/n0_RESULT.md" and rows[0]["ooda_file"] == "cc_tasks/n0_OODA.md"
    assert 3500 < rows[0]["grace_left_s"] <= 3600

    # c18 holds n1 in a pass's evaluation now.
    cfg = D.load_dispatch_config(chain_project)
    tasks = _tasks(neo4j_driver, TEST_DATABASE)
    gate = D.ooda_waits(chain_project, tasks, cfg, D.ooda_index(read_events(chain_project)),
                        datetime.now(timezone.utc))
    assert not gate[n1]["ok"]

    refused = runner.invoke(dispatch_group, ["ooda", "record", n1[:8]])
    assert refused.exit_code == 1 and "proposed" in refused.output
    res = runner.invoke(dispatch_group, ["ooda", "record", n0[:8], "--note", "premise 2 wrong; addendum filed"])
    assert res.exit_code == 0, res.output
    ev = [e for e in read_events(chain_project) if e["event_type"] == D.EVENT_OODA_RECORDED]
    assert len(ev) == 1 and ev[0]["payload"]["task_id"] == n0 and ev[0]["actor"] == "desktop"
    gate = D.ooda_waits(chain_project, tasks, cfg, D.ooda_index(read_events(chain_project)),
                        datetime.now(timezone.utc))
    assert gate[n1]["ok"] and gate[n1]["predecessors"][0]["released_by"] == "ooda_event"
    assert runner.invoke(dispatch_group, ["ooda", "pending"]).output.strip() == "ooda: nothing pending"
