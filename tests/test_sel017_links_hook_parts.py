"""SEL-017 (AD-034-R13, R14, R15): three defects hazbrief's sessions hit, each with the fixture the task names.

A. A session's own symlink to gitignored data is clean at merge. git matches a `dir/` pattern only against a
   directory, so a symlink at `graphs/g/work` is untracked and `dirty_paths` reported it: HB-64 and HB-72 ended
   `merge_blocked: uncommitted_changes` on four such links. A symlink at a tracked path still blocks.
B. A linked worktree's own config points `core.hooksPath` at its own `.githooks`, so `seldon verify` there finds
   the hook installed whatever the shared config's (absolute) value is.
C. A task with no `**Parts:**` header is one Part, `A 1.00`, for `part-complete` and the stations, with
   `parts_defaulted` on the records; registration still refuses a new file without the header.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from seldon.core import hooks as H
from seldon.core import worktree as WT


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    """A primary checkout ignoring hazbrief's four directories by trailing-slash patterns, each present with a
    file, and one linked worktree `wt` with none of them."""
    p = tmp_path / "primary"
    p.mkdir()
    _git(p, "init", "-q", "-b", "main")
    _git(p, "config", "user.email", "t@t")
    _git(p, "config", "user.name", "t")
    (p / ".gitignore").write_text("corpus/raw/\ngraphs/*/texts/\ngraphs/*/corpus/parsed/\ngraphs/*/work/\n",
                                  encoding="utf-8")
    (p / "graphs" / "g").mkdir(parents=True)
    (p / "graphs" / "g" / "graph.yaml").write_text("x: 1\n", encoding="utf-8")
    (p / "corpus").mkdir()
    (p / "corpus" / "manifest.yaml").write_text("[]\n", encoding="utf-8")
    (p / "notes.md").write_text("tracked\n", encoding="utf-8")
    _git(p, "add", "-A")
    _git(p, "commit", "-q", "-m", "init")
    for rel in ("corpus/raw", "graphs/g/texts", "graphs/g/corpus/parsed", "graphs/g/work"):
        (p / rel).mkdir(parents=True)
        (p / rel / "blob.bin").write_text("data\n", encoding="utf-8")
    wt = tmp_path / "wt"
    assert _git(p, "worktree", "add", "-q", "-b", "worktree-x", str(wt)).returncode == 0
    return p, wt


# ================================================================================ Part A

HAZBRIEF_LINKS = ["corpus/raw", "graphs/g/corpus/parsed", "graphs/g/texts", "graphs/g/work"]


def test_a_symlink_at_a_trailing_slash_ignored_path_is_clean(repo):
    p, wt = repo
    for rel in HAZBRIEF_LINKS:
        (wt / rel).parent.mkdir(parents=True, exist_ok=True)
        (wt / rel).symlink_to(p / rel)
    raw = _git(wt, "status", "--porcelain").stdout
    assert raw.strip(), "the plant: git itself reports the links (the HB-64 condition)"
    assert WT.dirty_paths(wt) == []
    assert WT.session_links(wt) == HAZBRIEF_LINKS


def test_the_own_path_rule_holds_for_a_target_outside_the_primary(repo, tmp_path):
    """Clean by its own path: the target is anywhere, the link's path is what `graphs/*/work/` ignores."""
    _, wt = repo
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (wt / "graphs" / "g" / "work").symlink_to(elsewhere)
    assert WT.dirty_paths(wt) == []


def test_the_target_rule_holds_for_a_link_at_an_unignored_path(repo):
    """Clean by its target: a link at a path nothing ignores, pointing into the primary at an ignored directory."""
    p, wt = repo
    (wt / "rawlink").symlink_to(p / "corpus" / "raw")
    assert WT.dirty_paths(wt) == []
    assert WT.session_links(wt) == ["rawlink"]


def test_a_symlink_to_a_tracked_path_still_blocks(repo):
    p, wt = repo
    (wt / "notes_link").symlink_to(p / "notes.md")
    assert WT.dirty_paths(wt) == ["notes_link"]
    assert WT.session_links(wt) == []


def test_a_symlink_replacing_a_tracked_file_still_blocks(repo):
    p, wt = repo
    (wt / "notes.md").unlink()
    (wt / "notes.md").symlink_to(p / "notes.md")
    assert WT.dirty_paths(wt) == ["notes.md"], "a type change is not untracked, so it is never a session link"


def test_a_directory_the_session_made_counts_clean_only_when_it_holds_links_alone(repo):
    p, wt = repo
    (wt / "graphs" / "h").mkdir(parents=True)
    (wt / "graphs" / "h" / "work").symlink_to(p / "graphs" / "g" / "work")
    assert WT.dirty_paths(wt) == [], "`graphs/h/` holds the link alone"
    assert WT.session_links(wt) == ["graphs/h/work"]
    (wt / "graphs" / "h" / "stray.txt").write_text("x\n", encoding="utf-8")
    assert WT.dirty_paths(wt) == ["graphs/h/"]
    assert WT.session_links(wt) == []


def test_configured_links_are_excluded_and_not_listed_as_the_sessions(repo):
    p, wt = repo
    (p / ".env").write_text("A=1\n", encoding="utf-8")
    assert WT.link(p, wt, [".env"]) == [".env"]
    (wt / "graphs" / "g" / "work").symlink_to(p / "graphs" / "g" / "work")
    assert WT.dirty_paths(wt, exclude=[".env"]) == []
    assert WT.session_links(wt, exclude=[".env"]) == ["graphs/g/work"]


@pytest.mark.usefixtures("neo4j_available")
def test_a_worktree_with_a_session_link_to_an_ignored_directory_merges(tmp_path, neo4j_driver, clean_test_db,
                                                                      monkeypatch):
    """End to end through the dispatcher's merge round: the session links `graphs/g/work` itself; the task merges
    and the merge record names the link `linked_by_session`. The merge mechanics are under test, not AD-037-R9's
    hold, so the opt-in stands in as `test_dispatch_parallel` stands it in."""
    from seldon.core import qc
    from seldon.domain.loader import load_domain_config
    monkeypatch.setattr(qc, "parallel_opted_in", lambda project_dir, config: True)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    from tests.dispatch_scaffold import RESEARCH_YAML, add_task, git, register, task_states, write_stub
    from tests import test_dispatch_parallel as TP
    dc = load_domain_config(RESEARCH_YAML)
    p = TP._project(tmp_path)
    with open(p / ".gitignore", "a", encoding="utf-8") as fh:
        fh.write("graphs/*/work/\n")
    git(p, "commit", "-q", "-m", "ignore work", "--", ".gitignore")
    git(p, "push", "-q")
    (p / "graphs" / "g" / "work").mkdir(parents=True)
    (p / "graphs" / "g" / "work" / "blob.bin").write_text("data\n", encoding="utf-8")
    add_task(p, "a", TP.NONEXCL.format(touches="out/a/"))
    ta = register(p, neo4j_driver, dc, "a", "2026-10-29T00:00:01Z")
    write_stub(p, {"a": {"write": {"out/a/x.txt": "a\n"}, "symlink": {"graphs/g/work": "graphs/g/work"}}})
    assert TP._once(p).count("launching") == 1
    TP._wait_settled(p, neo4j_driver, ["a"])
    fin = TP._finished(p, "a")[-1]
    assert fin["outcome"] == "merged", fin
    assert fin["merge"]["linked_by_session"] == ["graphs/g/work"]
    assert task_states(neo4j_driver)["a"] == "completed"
    assert fin["task_id"] == ta


# ================================================================================ Part B

@pytest.fixture
def hooked(tmp_path):
    """A primary with seldon's hook installed and committed, whose shared `core.hooksPath` something then made
    absolute (the state SEL-012 found in seldon and squiddy), and a fresh linked worktree."""
    p = tmp_path / "hp"
    p.mkdir()
    _git(p, "init", "-q", "-b", "main")
    _git(p, "config", "user.email", "t@t")
    _git(p, "config", "user.name", "t")
    (p / "README.md").write_text("x\n", encoding="utf-8")
    _git(p, "add", "README.md")
    _git(p, "commit", "-q", "-m", "init")
    H.install(p, python=sys.executable)
    _git(p, "config", "--local", "core.hooksPath", str(p / H.HOOKS_DIR))
    wt = tmp_path / "hwt"
    assert _git(p, "worktree", "add", "-q", "-b", "worktree-h", str(wt)).returncode == 0
    return p, wt


def test_a_fresh_worktree_reports_the_hook_installed_once_pointed(hooked):
    from seldon.commands.verify import check_commit_hook
    p, wt = hooked
    assert not H.status(wt)["installed"], "the plant: the absolute shared value does not resolve here"
    out = H.point_worktree(wt)
    assert out == {"ok": True, "changed": True, "error": None}
    st = H.status(wt)
    assert st["installed"] and st["scope"] == "worktree" and st["hooks_path"] == H.HOOKS_DIR
    assert check_commit_hook(wt, {}).symbol == "pass"
    # The primary's own value is not touched, and pointing again changes nothing.
    assert _git(p, "config", "--local", "--get", "core.hooksPath").stdout.strip() == str(p / H.HOOKS_DIR)
    assert H.point_worktree(wt) == {"ok": True, "changed": False, "error": None}


def test_a_worktree_without_the_tracked_hook_is_left_alone(repo):
    _, wt = repo
    assert H.point_worktree(wt) == {"ok": True, "changed": False, "error": None}
    assert _git(wt, "config", "--get", "extensions.worktreeConfig").stdout.strip() == ""


def test_name_worktree_points_the_worktree_and_records_it(hooked, monkeypatch):
    from seldon.commands import dispatch_worktree as DW
    from seldon.core import dispatch as D
    p, _ = hooked
    wt = p / D.CLI_WORKTREE_DIR / "named"
    assert _git(p, "worktree", "add", "-q", "-b", "worktree-named", str(wt)).returncode == 0
    extra = {"worktree_task": "t1", "stem": "s", "source_file": "cc_tasks/s.md", "child_session_id": "c1"}
    rec = DW.name_worktree(p, None, extra, {"cwd": str(wt)}, [], emit=False)
    assert "error" not in rec, rec
    assert rec["hooks_path"]["ok"] is True
    assert H.status(wt)["installed"]


# ================================================================================ Part C

def test_part_complete_on_a_task_without_parts_reads_one_part_and_notes_the_default(tmp_path, monkeypatch):
    from seldon.cli import main
    from seldon.core import stations as S
    from tests import stations_scaffold as F
    p = F.make_project(tmp_path, extra="")
    assert not S.parse_parts((p / "cc_tasks" / f"{F.STEM}.md").read_text())["declared"], "the plant"
    F.launch(p, at=F.ago(60))
    F.write_log(p, 400_000)
    monkeypatch.chdir(p)
    monkeypatch.setenv("SELDON_SESSION_ID", "child-1")
    r = CliRunner().invoke(main, ["dispatch", "part-complete", "--part", "A"])
    assert r.exit_code == 0, r.output
    assert "parts_defaulted" in r.output
    (pc,) = F.events(p, S.EVENT_PART_COMPLETE)
    assert pc["payload"]["planned_share"] == 1.0 and pc["payload"]["parts_defaulted"] is True

    # The milestone station computes CPI over the one Part: earned 1.0 over 400k / 2M actual.
    events = F.events(p)
    scfg = S.load_stations_config(F.config(p)["dispatch"])
    gate = S.stop_gate(p, S.last_launch(events, F.TASK_ID), events, scfg, p, None)
    F.record(p, S.EVENT_STOP_GATE, gate["record"], actor="cc")
    S.inspect(p, F.TASK_ID, F.events(p), scfg, 300, F.emitter(p))
    (m,) = F.events(p, S.EVENT_MILESTONE)
    assert m["payload"]["parts_defaulted"] is True and m["payload"]["earned"] == 1.0
    assert m["payload"]["cpi"] is not None

    r = CliRunner().invoke(main, ["dispatch", "part-complete", "--part", "B"])
    assert r.exit_code != 0, "the default is one Part, A, and nothing else"


def test_a_declared_header_is_not_defaulted_and_a_broken_one_keeps_its_error():
    from seldon.core import stations as S
    assert S.task_parts("**Parts:** A 0.5, B 0.5.\n")["defaulted"] is False
    broken = S.task_parts("**Parts:** A 0.5, B 0.6.\n")
    assert broken["parts"] == [] and "sum to 1.100" in broken["error"] and broken["defaulted"] is False
    assert S.task_parts("no header\n") == {"declared": False, "parts": [{"name": "A", "share": 1.0}],
                                           "error": None, "defaulted": True}


def test_registration_still_refuses_a_new_file_without_the_header(tmp_path):
    from seldon.core import stations as S
    from tests import stations_scaffold as F
    p = F.make_project(tmp_path, extra="")
    (p / "baseline.txt").write_text("\n", encoding="utf-8")
    refusal = S.parts_registration_refusal(p / "cc_tasks" / f"{F.STEM}.md", p,
                                           {"qc": {"parts_baseline": "baseline.txt"}})
    assert refusal and refusal.startswith(S.PARTS_REFUSAL)
