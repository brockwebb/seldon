"""ATTR-001 (AD-034 ADDENDUM 05): every governed repository declares its append-only logs `merge=union`.

SEL-004 decision 4 (AD-034-R7) was installed in seldon's own `.gitattributes` and nowhere else, so `union_files`
returned nothing for squiddy, arnold, ai-readiness-kg and hazbrief-mcp, and every worktree session whose project's
main gained an event line meanwhile ended `rebase_conflict` (squiddy SQ-021, 2026-10-23, issue 295ad039).

What is held here: `seldon hooks install` writes and commits the declaration for the files the project has; the
dispatcher refuses a launch (`union_attribute_missing`, criterion c16) in a project without it, naming the files;
and, against real git, the declaration is what turns the SQ-021 conflict into a clean rebase.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from seldon.core import dispatch as D
from seldon.core import hooks as H
from seldon.core import worktree as WT
from tests.test_dispatch import project  # noqa: F401  (fixture)

SRC = Path(H.__file__).resolve().parents[2]


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    # The hooks run `python -m seldon hooks ...`: without SRC first on PYTHONPATH they would import the installed
    # seldon (the main checkout), not the code under test (tests/test_hooks.py, SQ-010 Part 8b).
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["PYTHONPATH"] = os.pathsep.join(x for x in (str(SRC), env.get("PYTHONPATH")) if x)
    return subprocess.run(["git", "-C", str(root), *args], check=check, capture_output=True, text=True, env=env)


def _project(tmp_path: Path, *, governed: bool = False, prior_art: bool = False, ignore=()) -> Path:
    """A git project with seldon's hooks installed and committed, an event store, and optionally a governed graph
    and a prior-art block. No `.gitattributes`: the state every governed repository but seldon was in."""
    p = tmp_path / "proj"
    p.mkdir()
    _git(p, "init", "-q", "-b", "main")
    _git(p, "config", "user.email", "t@t")
    _git(p, "config", "user.name", "t")
    config = {"project": {"name": "t"}, "event_store": {"path": "seldon_events.jsonl"}}
    (p / "seldon_events.jsonl").write_text('{"event_id": "e0"}\n')
    if governed:
        (p / "governed" / "ledger").mkdir(parents=True)
        (p / "governed" / "ledger" / "events.jsonl").write_text("")
        config["governed"] = {"graph_dir": "governed"}
    if prior_art:
        # A complete block (the commit gate validates it), as tests/test_hooks.py writes one.
        (p / "docs" / "design").mkdir(parents=True)
        (p / "docs" / "design" / "AD-036_baseline.txt").write_text("")
        config["prior_art"] = {
            "log": "state/prior_art_queries.jsonl",
            "internal_roots": [{"name": "self", "path": "."}],
            "internal": {"default_include": ["docs/design/**"], "suffixes": [".md"], "top_n": 20,
                         "max_file_bytes": 100000, "bm25": {"k1": 1.2, "b": 0.75}},
            "library": {"graph": str(tmp_path / "nolib"), "k": 20},
            "gate": {"design_dir": "docs/design", "baseline": "docs/design/AD-036_baseline.txt",
                     "exempt_globs": ["*_ADDENDUM_*.md"], "verdict_ledger_without_governed": "state/verdicts.jsonl"}}
    (p / "seldon.yaml").write_text(yaml.safe_dump(config))
    if ignore:
        (p / ".gitignore").write_text("\n".join(ignore) + "\n")
    H.install(p, python=sys.executable)
    _git(p, "add", "-A")
    _git(p, "commit", "-qm", "init")
    return p


def _config(p: Path) -> dict:
    return yaml.safe_load((p / "seldon.yaml").read_text())


# ------------------------------------------------------------------------------- the list

def test_the_append_only_files_are_the_ones_the_project_has(tmp_path):
    p = _project(tmp_path, governed=True, prior_art=True)
    assert H.append_only_paths(p, _config(p)) == [
        "seldon_events.jsonl", "governed/ledger/events.jsonl", "state/prior_art_queries.jsonl"]


def test_a_project_without_a_governed_graph_or_prior_art_block_has_only_its_event_store(tmp_path):
    p = _project(tmp_path)
    assert H.append_only_paths(p, _config(p)) == ["seldon_events.jsonl"]


def test_an_ignored_log_is_not_declared(tmp_path):
    # An untracked file is never merged, so it has nothing to declare (tests/test_hooks.py ignores state/).
    p = _project(tmp_path, prior_art=True, ignore=["state/"])
    assert H.append_only_paths(p, _config(p)) == ["seldon_events.jsonl"]


def test_an_unreadable_prior_art_ref_is_a_named_error_not_a_skip(tmp_path):
    p = _project(tmp_path)
    config = {**_config(p), "prior_art": {"ref": "../nowhere/seldon.yaml#prior_art", "gate": {"baseline": "b"}}}
    with pytest.raises(H.HookError, match="prior_art"):
        H.append_only_paths(p, config)


# ------------------------------------------------------------------------------- the writer

def test_install_writes_and_commits_the_declaration_through_the_hooks(tmp_path):
    p = _project(tmp_path, governed=True, prior_art=True)
    (p / "README.md").write_text("an unrelated edit the declaration must not sweep up\n")
    assert H.union_missing(p, _config(p)) == [
        "seldon_events.jsonl", "governed/ledger/events.jsonl", "state/prior_art_queries.jsonl"]
    out = H.declare_union(p, _config(p))
    assert out["added"] == ["seldon_events.jsonl", "governed/ledger/events.jsonl", "state/prior_art_queries.jsonl"]
    assert out["committed"] is True
    text = (p / ".gitattributes").read_text()
    assert "SEL-004 decision 4" in text
    for path in out["added"]:
        assert f"{path} merge=union\n" in text
    assert H.union_missing(p, _config(p)) == []
    # One commit, holding .gitattributes alone; the unrelated edit is still the operator's.
    shown = _git(p, "show", "--name-only", "--format=%s", "HEAD").stdout.split("\n")
    assert "AD-034 ADDENDUM 05" in shown[0]
    assert [x for x in shown[1:] if x] == [".gitattributes"]
    assert _git(p, "status", "--porcelain").stdout.strip() == "?? README.md"


def test_install_extends_an_existing_file_and_keeps_what_was_there(tmp_path):
    p = _project(tmp_path)
    (p / ".gitattributes").write_text("*.png binary\n")
    _git(p, "add", ".gitattributes")
    _git(p, "commit", "-qm", "attrs")
    out = H.declare_union(p, _config(p))
    assert out["added"] == ["seldon_events.jsonl"]
    text = (p / ".gitattributes").read_text()
    assert text.startswith("*.png binary\n")
    assert text.endswith("seldon_events.jsonl merge=union\n")


def test_install_is_idempotent(tmp_path):
    p = _project(tmp_path)
    H.declare_union(p, _config(p))
    head = _git(p, "rev-parse", "HEAD").stdout
    again = H.declare_union(p, _config(p))
    assert again == {"added": [], "committed": False, "commit": None, "path": ".gitattributes"}
    assert _git(p, "rev-parse", "HEAD").stdout == head


def test_a_declaration_git_already_reads_is_not_repeated(tmp_path):
    # A wider pattern someone wrote already makes the file union; the installer reads git's answer, not the text.
    p = _project(tmp_path)
    (p / ".gitattributes").write_text("*.jsonl merge=union\n")
    _git(p, "add", ".gitattributes")
    _git(p, "commit", "-qm", "attrs")
    assert H.declare_union(p, _config(p))["added"] == []


def test_seldon_hooks_install_writes_the_declaration(tmp_path, monkeypatch):
    from seldon.commands.hooks import hooks_group
    p = _project(tmp_path, governed=True)
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(x for x in (str(SRC), os.environ.get("PYTHONPATH")) if x))
    res = CliRunner().invoke(hooks_group, ["install", "--repo", str(p)], catch_exceptions=False)
    assert res.exit_code == 0, res.output
    assert "merge=union" in res.output
    assert H.union_missing(p, _config(p)) == []
    assert _git(p, "status", "--porcelain").stdout.strip() == ""


# ------------------------------------------------------------------------------- the refusal

def test_dispatch_reads_the_missing_declaration_as_a_value(tmp_path):
    p = _project(tmp_path, governed=True)
    state = D.union_state(p)
    assert state["ok"] is False
    assert state["missing"] == ["seldon_events.jsonl", "governed/ledger/events.jsonl"]
    H.declare_union(p, _config(p))
    assert D.union_state(p) == {"required": ["seldon_events.jsonl", "governed/ledger/events.jsonl"],
                                "missing": [], "ok": True}


def test_a_project_whose_append_only_files_are_undeclared_refuses_every_launch(project):
    # tests/test_dispatch.py's project: a dispatch block, a band, a clean tree; here with its event store tracked.
    from tests.test_dispatch import _commit, _row, _task_file
    p = project
    (p / "seldon_events.jsonl").write_text("")
    task = _task_file(p, "t")
    _commit(p)
    cfg = D.load_dispatch_config(p)
    band = D.resolve_standing_band(p, cfg["standing_band_ref"])
    row_in = _row(p, task, "accepted")
    union = D.union_state(p)
    row = D.evaluate(p, row_in, cfg, band, D.tree_state(p), None, {}, union=union)
    assert row["criteria"]["c16"] == {**union, "ok": False}
    assert D.first_refusal_reason(row) == "union_attribute_missing"
    from seldon.commands.dispatch import _refusal_lines
    lines = _refusal_lines([row], D.tree_state(p))
    assert any("union_attribute_missing" in ln for ln in lines)
    assert any("seldon_events.jsonl" in ln and "seldon hooks install" in ln for ln in lines)
    # Declared: c16 is absent, so the criteria vector of a healthy project is unchanged (as c13 to c15).
    H.declare_union(p, _config(p))
    row = D.evaluate(p, row_in, cfg, band, D.tree_state(p), None, {}, union=D.union_state(p))
    assert "c16" not in row["criteria"]
    assert row["eligible"] is True


@pytest.mark.usefixtures("neo4j_available", "clean_test_db")
def test_a_pass_declares_the_missing_attribute_itself_and_commits_it_alone(tmp_path):
    # AD-038-R1 applied: the four repositories without the declaration are fixed by their own dispatcher's next
    # pass, not wedged on c16 until someone runs the installer there.
    from seldon.commands.dispatch import dispatch_group
    from tests.dispatch_scaffold import make_project, run_cli
    p = make_project(tmp_path, union_store=False)
    assert H.union_missing(p, _config(p)) == ["seldon_events.jsonl"]
    before = _git(p, "rev-parse", "HEAD").stdout.strip()
    out = run_cli(p, dispatch_group, ["once"]).output
    assert "union: .gitattributes declares seldon_events.jsonl merge=union" in out
    assert H.union_missing(p, _config(p)) == []
    log = _git(p, "log", "--format=%s", "--name-only", f"{before}..HEAD").stdout
    assert "AD-034 ADDENDUM 05" in log and ".gitattributes" in log
    assert _git(p, "status", "--porcelain").stdout.strip() == ""


@pytest.mark.usefixtures("neo4j_available", "clean_test_db")
def test_a_pass_leaves_an_edited_gitattributes_alone_and_c16_names_the_files(tmp_path):
    from seldon.commands.dispatch import dispatch_group
    from tests.dispatch_scaffold import make_project, run_cli
    p = make_project(tmp_path, union_store=False)
    (p / ".gitattributes").write_text("*.png binary\n")
    out = run_cli(p, dispatch_group, ["once"]).output
    assert "union:" not in out or "uncommitted edits" in out
    assert (p / ".gitattributes").read_text() == "*.png binary\n"
    assert D.union_state(p)["missing"] == ["seldon_events.jsonl"]


# ------------------------------------------------------------------------------- the measured case

def _diverge(p: Path) -> None:
    """SQ-021's shape: a branch appends an event; main appends a different one meanwhile."""
    _git(p, "checkout", "-q", "-b", "worktree-x")
    with open(p / "seldon_events.jsonl", "a") as fh:
        fh.write('{"event_id": "branch"}\n')
    _git(p, "commit", "-qam", "branch: event")
    _git(p, "checkout", "-q", "main")
    with open(p / "seldon_events.jsonl", "a") as fh:
        fh.write('{"event_id": "main"}\n')
    _git(p, "commit", "-qam", "main: event")
    _git(p, "checkout", "-q", "worktree-x")


def test_without_the_declaration_the_rebase_conflicts_on_the_event_store(tmp_path):
    p = _project(tmp_path)
    _diverge(p)
    out = WT.rebase(p, "main")
    assert out["ok"] is False and out["conflicts"] == ["seldon_events.jsonl"]


def test_with_the_declaration_the_rebase_merges_by_union_and_the_check_passes(tmp_path):
    p = _project(tmp_path)
    H.declare_union(p, _config(p))
    _diverge(p)
    base = WT.show(p, "main", "seldon_events.jsonl")
    assert WT.rebase(p, "main")["ok"] is True
    merged = (p / "seldon_events.jsonl").read_bytes()
    assert merged.decode().splitlines() == ['{"event_id": "e0"}', '{"event_id": "main"}', '{"event_id": "branch"}']
    assert WT.check_union_text(merged, "event_id", base=base) == {"ok": True, "malformed": [], "duplicates": []}
