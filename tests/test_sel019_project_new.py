"""SEL-019: `seldon project new` turns a directory into a seldon project with a dispatcher and a squiddy graph.

The end-to-end tests run the real `seldon init` (against this process's test database), the real `seldon hooks
install` and the real `seldon dispatch adopt`; only `launchctl` is replaced (the plist load is mocked, as the task
says), the kit is a temporary one, and squiddy is a stub except in the one test that runs the real squiddy.
"""
from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from seldon.commands.project import project_group
from seldon.core import adopt as A
from seldon.core import dispatch as D
from seldon.core import project_new as PN
from tests.testdb import TEST_DATABASE

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
desktop_commit:
  scan:
    roots: [handoffs/]
    command: [../scanner/.venv/bin/python, -m, scanner.secret_scan]
project_new:
  environment_packages: [kit]
  squiddy_command: [bin/squiddy]
  launch_agents_dir: {agents}
jobs:
  dispatch:
    log_max_line_chars: 2000
    log_max_run_bytes: 2097152
    log_retention_days: 30
"""

#: A stand-in for `squiddy init <dir> --spec <spec>`: refuses a spec with no title, as squiddy's `load_spec` does,
#: and otherwise writes the record squiddy's init writes.
STUB_SQUIDDY = """#!{python}
import pathlib, sys, yaml
assert sys.argv[1] == "init" and sys.argv[3] == "--spec", sys.argv
spec = yaml.safe_load(open(sys.argv[4]))
if not spec.get("title"):
    print("squiddy: graph.yaml: missing `title:`. A graph with no title is not a graph.", file=sys.stderr)
    sys.exit(1)
d = pathlib.Path(sys.argv[2])
(d / ".squiddy_init.json").write_text("{{}}\\n")
(d / "config.yaml").write_text("engine: {{}}\\n")
"""


@pytest.fixture
def kit(tmp_path, monkeypatch) -> Path:
    k = tmp_path / "kit"
    (k / "bin").mkdir(parents=True)
    agents = tmp_path / "LaunchAgents"
    (k / "seldon.yaml").write_text(KIT_YAML.format(agents=agents), encoding="utf-8")
    (k / "controls.yaml").write_text(yaml.safe_dump({"spend": {"daily_tokens": 1_000_000}}), encoding="utf-8")
    stub = k / "bin" / "squiddy"
    stub.write_text(STUB_SQUIDDY.format(python=sys.executable), encoding="utf-8")
    stub.chmod(0o755)
    monkeypatch.setattr(PN, "KIT_DIR", k)
    return k


class FakeLaunchctl:
    """`launchctl print` fails until `bootstrap` has run for the label; every call is recorded."""

    def __init__(self):
        self.calls, self.loaded = [], set()

    def __call__(self, *args):
        self.calls.append(args)
        if args[0] == "print":
            rc = 0 if args[1] in self.loaded else 113
        elif args[0] == "bootstrap":
            label = Path(args[2]).name[:-len(".plist")]
            self.loaded.add(f"{args[1]}/{label}")
            rc = 0
        else:
            rc = 1
        return subprocess.CompletedProcess(["launchctl", *args], rc, "", "")


@pytest.fixture
def launchctl(monkeypatch):
    fake = FakeLaunchctl()
    monkeypatch.setattr(PN, "launchctl", fake)
    return fake


def _git(d, *args):
    return subprocess.run(["git", *args], cwd=d, capture_output=True, text=True, check=True).stdout


def _new(target, *extra):
    return CliRunner().invoke(project_group, ["new", str(target), "--database", TEST_DATABASE, *extra],
                              catch_exceptions=False)


# ══════════════════════════════════════════════════════════════════════════════
# End to end (Neo4j: `seldon init` creates and seeds the database)
# ══════════════════════════════════════════════════════════════════════════════

neo4j_tests = pytest.mark.usefixtures("neo4j_available", "clean_test_db")


@neo4j_tests
def test_a_temp_directory_becomes_a_project_with_a_dispatch_block_and_a_loaded_plist(tmp_path, kit, launchctl):
    target = tmp_path / "newproj"
    res = _new(target, "--dispatch", "--enable", "--gate-command", "pytest tests/ -q")
    assert res.exit_code == 0, res.output

    cfg = D.load_dispatch_config(target)
    assert cfg["enabled"] is True and cfg["branch"] == "main" and cfg["max_parallel"] == 1
    assert cfg["candidacy_headers"] == D.MINIMUM_HEADERS and cfg["gate_command"] == "pytest tests/ -q"
    assert D.resolve_standing_band(target, cfg["standing_band_ref"]) == 1_000_000
    config = yaml.safe_load((target / "seldon.yaml").read_text())
    assert config["neo4j"]["database"] == TEST_DATABASE and config["project"]["name"] == "newproj"
    assert config["environment"] == {"packages": ["kit"]}
    assert config["dispatch"]["stations"] == {"environment_ref": "seldon.yaml#environment.packages"}
    # The scan's program re-rooted from the kit to the project.
    assert config["desktop_commit"]["scan"]["command"][0] == "../scanner/.venv/bin/python"

    # The plist is loadable: it parses, names the label, and its interval is the block's.
    plist_path = target / A.PLIST_DIR / f"{cfg['launchd_label']}.plist"
    plist = plistlib.loads(plist_path.read_bytes())
    assert plist["Label"] == cfg["launchd_label"] and plist["StartInterval"] == cfg["poll_interval_s"]
    assert plist["ProgramArguments"][-2:] == [str(target.resolve()), str(plist_path.resolve())]
    link = tmp_path / "LaunchAgents" / f"{cfg['launchd_label']}.plist"
    assert link.is_symlink() and link.resolve() == plist_path.resolve()
    assert [c[0] for c in launchctl.calls] == ["print", "bootstrap"]
    assert launchctl.calls[1] == ("bootstrap", f"gui/{os.getuid()}", str(link))

    # Committed through the hooks: a clean tree on main, the hooks installed.
    assert _git(target, "status", "--porcelain") == ""
    assert _git(target, "symbolic-ref", "--short", "HEAD").strip() == "main"
    assert _git(target, "config", "--local", "core.hooksPath").strip() == ".githooks"
    tracked = _git(target, "ls-files").split()
    assert {"seldon.yaml", "seldon_events.jsonl", ".gitignore", str(plist_path.relative_to(target.resolve())),
            ".githooks/pre-commit"} <= set(tracked)
    assert ".env" not in tracked
    assert "seldon cc register --project" in res.output


@neo4j_tests
def test_a_second_run_on_an_adopted_project_changes_nothing_and_says_so(tmp_path, kit, launchctl):
    target = tmp_path / "newproj"
    assert _new(target, "--dispatch", "--enable").exit_code == 0
    head = _git(target, "rev-parse", "HEAD")
    before = {p: p.read_bytes() for p in target.rglob("*") if p.is_file() and ".git/" not in str(p)}
    launchctl.calls.clear()

    res = _new(target, "--dispatch", "--enable")
    assert res.exit_code == 0, res.output
    assert "nothing changed; already a project" in res.output
    assert " changed " not in res.output
    assert _git(target, "rev-parse", "HEAD") == head
    assert {p: p.read_bytes() for p in target.rglob("*") if p.is_file() and ".git/" not in str(p)} == before
    assert launchctl.calls == [("print", f"gui/{os.getuid()}/{D.load_dispatch_config(target)['launchd_label']}")]


@neo4j_tests
def test_an_existing_seldon_project_is_adopted_without_reinitializing(tmp_path, kit, launchctl):
    """aacps' shape: `seldon init` already ran by hand; `project new --dispatch` adds only the rest."""
    target = tmp_path / "newproj"
    assert _new(target).exit_code == 0
    created = yaml.safe_load((target / "seldon.yaml").read_text())["project"]["created_at"]
    assert "dispatch" not in yaml.safe_load((target / "seldon.yaml").read_text())
    res = _new(target, "--dispatch", "--no-load")
    assert res.exit_code == 0, res.output
    config = yaml.safe_load((target / "seldon.yaml").read_text())
    assert config["project"]["created_at"] == created and config["dispatch"]["enabled"] is False
    assert launchctl.calls == [] and "--no-load" in res.output
    assert "--dispatch --enable" in res.output
    assert _git(target, "status", "--porcelain") == ""


@neo4j_tests
def test_with_a_graph_the_skeleton_is_committed_and_the_refusal_is_reported(tmp_path, kit, launchctl):
    target = tmp_path / "newproj"
    res = _new(target, "--graph", "my-graph")
    assert res.exit_code == 1, res.output
    assert "squiddy init refused" in res.output and "missing `title:`" in res.output
    spec = target / "graphs" / "my-graph" / "graph.yaml"
    assert yaml.safe_load(spec.read_text())["name"] == "my_graph"
    assert "graphs/my-graph/graph.yaml" in _git(target, "ls-files").split()
    # The operator fills the spec; the next run initializes the graph and commits it.
    spec.write_text(spec.read_text().replace("title:\n", "title: my graph\n"))
    _git(target, "commit", "-qam", "fill the spec")
    res = _new(target, "--graph", "my-graph")
    assert res.exit_code == 0, res.output
    assert (target / "graphs" / "my-graph" / PN.SQUIDDY_INIT_RECORD).is_file()
    assert _git(target, "status", "--porcelain") == ""


# ══════════════════════════════════════════════════════════════════════════════
# The steps, without the database
# ══════════════════════════════════════════════════════════════════════════════

def test_the_graph_step_converges_skeleton_then_init_then_ok(tmp_path, kit):
    proj = tmp_path / "p"
    proj.mkdir()
    cmd = PN.squiddy_command(PN.project_new_config(kit), kit)
    assert cmd == [str(kit / "bin" / "squiddy")]
    first = PN.graph_step(proj, "g-1", cmd)
    assert first.status == "refused" and first.wrote == ["graphs/g-1/graph.yaml"]
    spec = proj / "graphs" / "g-1" / "graph.yaml"
    assert "{name}" not in spec.read_text() and yaml.safe_load(spec.read_text())["scope"] == {"topic": None}
    spec.write_text(spec.read_text().replace("title:\n", "title: t\n"))
    assert PN.graph_step(proj, "g-1", cmd).status == "changed"
    assert PN.graph_step(proj, "g-1", cmd).status == "ok"


#: The kit's own squiddy (the primary checkout's sibling), which `project_new.squiddy_command` names.
_SQUIDDY = A.KIT_DIR.parent / "squiddy" / ".venv" / "bin" / "squiddy"
REAL_SQUIDDY = _SQUIDDY if _SQUIDDY.is_file() else None


@pytest.mark.skipif(REAL_SQUIDDY is None, reason="no squiddy checkout beside seldon (the kit's squiddy_command)")
def test_the_real_squiddy_initializes_a_filled_skeleton(tmp_path):
    proj = tmp_path / "p"
    proj.mkdir()
    assert PN.graph_step(proj, "demo", [str(REAL_SQUIDDY)]).status == "refused"
    spec = proj / "graphs" / "demo" / "graph.yaml"
    text = spec.read_text().replace("title:\n", "title: the demo graph\n")
    text = text.replace("description:\n", "description: a demo\n").replace("  topic:\n", "  topic: demo things\n")
    spec.write_text(text)
    step = PN.graph_step(proj, "demo", [str(REAL_SQUIDDY)])
    assert step.status == "changed", step.detail
    assert (proj / "graphs" / "demo" / PN.SQUIDDY_INIT_RECORD).is_file()
    assert (proj / "graphs" / "demo" / "corpus" / "manifest.yaml").is_file()


def test_enable_flips_only_the_dispatch_blocks_line_and_keeps_its_comments():
    text = ("other:\n  enabled: false\ndispatch:\n  # THE KILL SWITCH\n  enabled: false\n  branch: main\n"
            "jobs:\n  enabled: false\n")
    out = PN.enabled_text(text)
    assert out == text.replace("  # THE KILL SWITCH\n  enabled: false", "  # THE KILL SWITCH\n  enabled: true")
    assert PN.enabled_text(out) is None


def test_the_plist_load_refuses_a_foreign_file_at_the_link(tmp_path, launchctl):
    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "com.x.plist").write_text("someone else's")
    with pytest.raises(PN.ProjectNewError, match="is not a symlink"):
        PN.load_plist(tmp_path / "mine.plist", "com.x", agents)
    assert launchctl.calls == []


def test_the_plist_load_reports_a_failed_bootstrap(tmp_path, monkeypatch):
    monkeypatch.setattr(PN, "launchctl", lambda *a: subprocess.CompletedProcess(a, 125, "", "Input/output error"))
    (tmp_path / "mine.plist").write_text("x")
    with pytest.raises(PN.ProjectNewError, match="exited 125: Input/output error"):
        PN.load_plist(tmp_path / "mine.plist", "com.x", tmp_path / "agents", uid=501)


def test_an_interpreter_that_cannot_import_seldon_is_refused(tmp_path):
    PN.check_interpreter(sys.executable)
    bad = tmp_path / "py"
    bad.write_text("#!/bin/sh\necho 'No module named seldon' >&2\nexit 1\n")
    bad.chmod(0o755)
    with pytest.raises(PN.ProjectNewError, match="cannot import seldon"):
        PN.check_interpreter(str(bad))


def test_a_directory_inside_another_repository_is_refused(tmp_path):
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    with pytest.raises(PN.ProjectNewError, match="is a repository of its own"):
        PN.ensure_repo(tmp_path / "inner", "main")


def test_the_dispatch_only_options_need_dispatch(tmp_path, kit):
    res = CliRunner().invoke(project_group, ["new", str(tmp_path / "x"), "--enable"])
    assert res.exit_code == 2 and "need --dispatch" in res.output
    assert not (tmp_path / "x").exists()


def test_the_kit_block_is_required_whole(tmp_path):
    (tmp_path / "seldon.yaml").write_text("project_new:\n  environment_packages: [squiddy]\n")
    with pytest.raises(PN.ProjectNewError, match="lacks"):
        PN.project_new_config(tmp_path)


def test_seldons_own_kit_block_loads():
    """The block this checkout ships (read from the worktree's file, not the primary's)."""
    cfg = PN.project_new_config(Path(__file__).resolve().parents[1])
    assert cfg["environment_packages"] == ["squiddy", "seldon"]
