"""SEL-009 (AD-035 ADDENDUM 03): `models refresh` defers while a run holds the lock, the day boundary is one printed
value, and a project declares a tiered pilot.

The 2026-10-24 incident: a hazbrief Desktop registration's `ensure_fresh("register")` bumped the lock from CLI
2.1.309 to 2.1.310 at 00:09:23Z while hazbrief's HB-24 rating top-up was mid-run, and the re-pilot the bump forced
cost 4.21M weighted. AD-035-R7 already said "a run in flight keeps its lock entry to the end"; nothing implemented it
in `refresh`. Every test drives the fake CLI and fake npm of `tests/test_models.py`: no model call, no spend.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from seldon import models as M
from seldon.commands.models import models_group
from tests.models_fixture import FIXTURE_IDS
from tests.test_models import _fake_install, refresh_home  # noqa: F401  (fixture re-export)


# ------------------------------------------------------------------------------------------------ helpers

def _set_refresh(home: Path, **values) -> None:
    reg = yaml.safe_load((home / M.REGISTRY_FILE).read_text())
    reg["refresh"].update(values)
    (home / M.REGISTRY_FILE).write_text(yaml.safe_dump(reg, sort_keys=False))


def _project(root: Path, name: str, dispatch: bool = True) -> Path:
    """A sibling project with a `dispatch:` block naming its lease file and lease dir."""
    p = root / name
    (p / ".seldon" / "leases").mkdir(parents=True, exist_ok=True)
    cfg = {"project": {"name": name}, "neo4j": {"database": f"seldon-{name}"}}
    if dispatch:
        cfg["dispatch"] = {"enabled": True, "lease_file": ".seldon/dispatch.lock",
                           "lease_dir": ".seldon/leases"}
    (p / "seldon.yaml").write_text(yaml.safe_dump(cfg))
    return p


def _live_pid() -> int:
    """A PID that is alive and is not this process: a sleeping child, killed at teardown by the caller."""
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
    return proc


def _hold_lease(path: Path, pid: int, task: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"holder": f"dispatcher:test:{pid}", "pid": pid, "task": task,
                                "acquired_at": "2026-10-24T00:00:00Z"}))


def _events(repo: Path, kind: str) -> list:
    lines = [json.loads(x) for x in (repo / "seldon_events.jsonl").read_text().splitlines() if x]
    return [e for e in lines if e["event_type"] == kind]


def _locked_once(home: Path, tmp_path: Path) -> tuple:
    """Refresh once with no holders (the lock exists), and return the next day's install."""
    named = M.named_models()
    npm, runner, _ = _fake_install(tmp_path, "3.0.1", {**FIXTURE_IDS, **{m: m for m in named}})
    M.refresh(commit=False, npm=npm, runner=runner, today="2026-10-23")
    npm2, runner2, calls2 = _fake_install(tmp_path, "3.0.2", {**FIXTURE_IDS, **{m: m for m in named}})
    return npm2, runner2, calls2


@pytest.fixture
def sleeper():
    procs = []

    def start():
        p = _live_pid()
        procs.append(p)
        return p.pid
    yield start
    for p in procs:
        p.kill()
        p.wait()


# ----------------------------------------------------------------------------------- Part A: the deferral

def test_a_held_dispatcher_lease_in_a_holder_repo_defers_the_refresh_once_per_holder_set(
        refresh_home, tmp_path, sleeper):
    repo = refresh_home.parent
    other = _project(tmp_path, "hazbrief")
    _set_refresh(refresh_home, holders=[str(other)])
    npm, runner, calls = _locked_once(refresh_home, tmp_path)
    lock_bytes = (refresh_home / M.LOCK_FILE).read_bytes()
    n_cli, n_npm = len(calls["cli"]), len(calls["npm"])

    _hold_lease(other / ".seldon" / "dispatch.lock", sleeper(), task="hb-24")
    out = M.refresh(commit=False, npm=npm, runner=runner, today="2026-10-24")

    assert out.status == "deferred"
    assert (refresh_home / M.LOCK_FILE).read_bytes() == lock_bytes
    assert (len(calls["cli"]), len(calls["npm"])) == (n_cli, n_npm), "a deferral spends nothing"
    deferred = _events(repo, M.EVENT_REFRESH_DEFERRED)
    assert len(deferred) == 1
    p = deferred[0]["payload"]
    assert p["date"] == "2026-10-24" and p["lock_cli_version"] == "3.0.1"
    assert [(h["repo"], h["kind"], h["task"]) for h in p["holders"]] == [
        (str(other), "dispatch_lease", "hb-24")]

    again = M.refresh(commit=False, npm=npm, runner=runner, today="2026-10-24")
    assert again.status == "deferred"
    assert len(_events(repo, M.EVENT_REFRESH_DEFERRED)) == 1, "the same holders on the same day: no second line"


def test_a_live_worktree_lease_defers_the_refresh(refresh_home, tmp_path, sleeper):
    other = _project(tmp_path, "squiddy")
    _set_refresh(refresh_home, holders=[str(other)])
    npm, runner, _ = _locked_once(refresh_home, tmp_path)
    _hold_lease(other / ".seldon" / "leases" / "2026-10-24_SQ-1_x.lock", sleeper(), task="sq-1")
    out = M.refresh(commit=False, npm=npm, runner=runner, today="2026-10-24")
    assert out.status == "deferred"
    assert out.holders[0]["kind"] == "worktree_lease"


def test_the_calling_process_own_lease_is_not_a_holder(refresh_home, tmp_path):
    """The dispatcher refreshes at launch while it holds its own pass lease: that is the boundary, not a run."""
    other = _project(tmp_path, "seldon-like")
    _set_refresh(refresh_home, holders=[str(other)])
    npm, runner, _ = _locked_once(refresh_home, tmp_path)
    _hold_lease(other / ".seldon" / "dispatch.lock", os.getpid())
    out = M.refresh(commit=False, npm=npm, runner=runner, today="2026-10-24")
    assert out.status == "bumped"


def test_a_released_lease_and_a_dead_pid_hold_nothing(refresh_home, tmp_path):
    other = _project(tmp_path, "arnold")
    _set_refresh(refresh_home, holders=[str(other)])
    npm, runner, _ = _locked_once(refresh_home, tmp_path)
    (other / ".seldon" / "dispatch.lock").write_text(json.dumps({"holder": None, "pid": None}))
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    _hold_lease(other / ".seldon" / "leases" / "x.lock", dead.pid)
    assert M.refresh(commit=False, npm=npm, runner=runner, today="2026-10-24").status == "bumped"


def test_a_repo_with_no_dispatch_block_holds_nothing(refresh_home, tmp_path):
    other = _project(tmp_path, "plain", dispatch=False)
    _set_refresh(refresh_home, holders=[str(other)])
    npm, runner, _ = _locked_once(refresh_home, tmp_path)
    assert M.refresh(commit=False, npm=npm, runner=runner, today="2026-10-24").status == "bumped"


def test_a_missing_holder_directory_fails_loudly_and_the_lock_stands(refresh_home, tmp_path):
    npm, runner, _ = _locked_once(refresh_home, tmp_path)
    lock_bytes = (refresh_home / M.LOCK_FILE).read_bytes()
    _set_refresh(refresh_home, holders=[str(tmp_path / "gone")])
    with pytest.raises(M.ModelsError, match="gone"):
        M.refresh(commit=False, npm=npm, runner=runner, today="2026-10-24")
    assert (refresh_home / M.LOCK_FILE).read_bytes() == lock_bytes


def test_a_live_run_hold_defers_the_refresh_and_releases_after(refresh_home, tmp_path):
    _set_refresh(refresh_home, holds_dir=str(tmp_path / "holds"))
    npm, runner, _ = _locked_once(refresh_home, tmp_path)
    with M.hold("hb-24-topup", by="hazbrief"):
        out = M.refresh(commit=False, npm=npm, runner=runner, today="2026-10-24")
        assert out.status == "deferred"
        assert out.holders == [{"repo": None, "kind": "run_hold", "holder": "hazbrief", "task": "hb-24-topup",
                                "pid": os.getpid(), "path": str(tmp_path / "holds" / "hb-24-topup.lock")}]
    assert M.lock_holders() == []
    assert M.refresh(commit=False, npm=npm, runner=runner, today="2026-10-24").status == "bumped"


def test_a_run_name_is_one_path_segment(refresh_home, tmp_path):
    _set_refresh(refresh_home, holds_dir=str(tmp_path / "holds"))
    with pytest.raises(M.ModelsError, match="run name"):
        with M.hold("../escape"):
            pass


def test_the_hold_command_holds_while_its_command_runs_and_exits_with_its_code(refresh_home, tmp_path):
    _set_refresh(refresh_home, holds_dir=str(tmp_path / "holds"))
    probe = tmp_path / "seen.json"
    script = textwrap.dedent(f"""\
        import json
        from seldon import models as M
        json.dump(M.lock_holders(), open({str(probe)!r}, "w"))
        raise SystemExit(3)
        """)
    result = CliRunner().invoke(models_group, ["hold", "--run", "r1", "--by", "test", "--",
                                               sys.executable, "-c", script])
    assert result.exit_code == 3, result.output
    seen = json.loads(probe.read_text())
    assert [(h["kind"], h["task"], h["holder"]) for h in seen] == [("run_hold", "r1", "test")]
    assert M.lock_holders() == []


def test_force_refreshes_over_holders_and_names_them_on_the_bump(refresh_home, tmp_path):
    repo = refresh_home.parent
    _set_refresh(refresh_home, holds_dir=str(tmp_path / "holds"))
    npm, runner, _ = _locked_once(refresh_home, tmp_path)
    with M.hold("r2", by="op"):
        out = M.refresh(commit=False, npm=npm, runner=runner, today="2026-10-24", force=True)
    assert out.status == "bumped"
    bump = _events(repo, M.EVENT_LOCK_BUMPED)[-1]["payload"]
    assert [h["task"] for h in bump["forced_over_holders"]] == ["r2"]


def test_no_holders_refreshes_as_before(refresh_home, tmp_path):
    repo = refresh_home.parent
    npm, runner, _ = _locked_once(refresh_home, tmp_path)
    out = M.refresh(commit=False, npm=npm, runner=runner, today="2026-10-24")
    assert out.status == "bumped"
    assert "forced_over_holders" not in _events(repo, M.EVENT_LOCK_BUMPED)[-1]["payload"]
    assert _events(repo, M.EVENT_REFRESH_DEFERRED) == []


def test_a_first_refresh_with_no_lock_is_never_deferred(refresh_home, tmp_path):
    """With no lock there is nothing a run could hold, and every launcher fails without one."""
    _set_refresh(refresh_home, holds_dir=str(tmp_path / "holds"))
    named = M.named_models()
    npm, runner, _ = _fake_install(tmp_path, "3.0.1", {**FIXTURE_IDS, **{m: m for m in named}})
    with M.hold("r3"):
        assert M.refresh(commit=False, npm=npm, runner=runner, today="2026-10-24").status == "bumped"


# --------------------------------------------------------------------------------- Part A: the boundary

def test_the_cache_day_keys_on_the_configured_boundary():
    import datetime as dt
    at = dt.datetime(2026, 10, 24, 0, 9, 23, tzinfo=dt.timezone.utc)
    assert M.cache_day(at, "00:00") == "2026-10-24"
    assert M.cache_day(at, "00:45") == "2026-10-23"
    assert M.next_refresh_at("2026-10-23", "00:45") == "2026-10-24T00:45:00Z"


def test_a_malformed_boundary_is_refused_at_load(refresh_home):
    _set_refresh(refresh_home, cache_boundary_utc="25:00")
    with pytest.raises(M.ModelsError, match="cache_boundary_utc"):
        M.load_registry()


def test_show_prints_the_boundary_the_next_refresh_and_the_holders(refresh_home, tmp_path):
    _set_refresh(refresh_home, holds_dir=str(tmp_path / "holds"), cache_boundary_utc="00:45")
    _locked_once(refresh_home, tmp_path)
    with M.hold("r4", by="op"):
        result = CliRunner().invoke(models_group, ["show", "--project", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "day boundary 00:45Z" in result.output
    assert "next eligible 2026-10-24T00:45:00Z" in result.output
    assert "no clock job" in result.output
    assert "run_hold r4 (op" in result.output


# ------------------------------------------------------------------------------ Part B: the declaration

def _declare(project: Path, pilot) -> Path:
    project.mkdir(parents=True, exist_ok=True)
    (project / "seldon.yaml").write_text(yaml.safe_dump({"project": {"name": "p"}, "models": {"pilot": pilot}}))
    return project


GOOD = {"cost_calls": 50, "cost_band": 1.5, "content_sample": 75, "full_on": ["major", "band_tripped"]}


def test_a_valid_pilot_declaration_is_read_and_printed(refresh_home, tmp_path):
    p = _declare(tmp_path / "proj", GOOD)
    assert M.pilot_declaration(p) == GOOD
    result = CliRunner().invoke(models_group, ["show", "--project", str(p)])
    assert result.exit_code == 0, result.output
    assert "pilot (" in result.output and "cost_calls=50" in result.output
    assert "full_on=major,band_tripped" in result.output


def test_an_absent_declaration_is_none_and_says_so(refresh_home, tmp_path):
    p = tmp_path / "bare"
    p.mkdir()
    (p / "seldon.yaml").write_text(yaml.safe_dump({"project": {"name": "bare"}}))
    assert M.pilot_declaration(p) is None
    result = CliRunner().invoke(models_group, ["show", "--project", str(p)])
    assert "pilot: none declared" in result.output


@pytest.mark.parametrize("bad, words", [
    ({**GOOD, "cost_calls": 0}, "cost_calls"),
    ({**GOOD, "cost_calls": True}, "cost_calls"),
    ({**GOOD, "content_sample": "75"}, "content_sample"),
    ({**GOOD, "cost_band": 1.0}, "cost_band"),
    ({k: v for k, v in GOOD.items() if k != "cost_band"}, "cost_band"),
    ({**GOOD, "full_on": ["patch"]}, "full_on"),
    ({**GOOD, "full_on": "major"}, "full_on"),
    ({**GOOD, "sample": 3}, "unknown"),
    ({k: v for k, v in GOOD.items() if k != "content_sample"}, "content_sample"),
])
def test_a_malformed_declaration_is_refused_naming_the_key(tmp_path, bad, words):
    p = _declare(tmp_path / "proj", bad)
    with pytest.raises(M.ModelsError, match=words):
        M.pilot_declaration(p)


def test_a_band_without_band_tripped_is_allowed_as_a_recorded_line(tmp_path):
    decl = {"cost_calls": 50, "cost_band": 2.0, "content_sample": 75, "full_on": ["minor"]}
    assert M.pilot_declaration(_declare(tmp_path / "proj", decl)) == decl
