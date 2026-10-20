"""Tests for scripts/sec001/rewrite_desktop_config.py (SEC-001R)."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest
import yaml

SCRIPT = Path(__file__).parent.parent / "scripts" / "sec001" / "rewrite_desktop_config.py"
_spec = importlib.util.spec_from_file_location("sec001_rewrite", SCRIPT)
rw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rw)

PATTERN = "TOKEN|API_KEY|SECRET|PASSWORD|PASS$"


def _cfg():
    return {"mcpServers": {
        "db": {"command": "srv", "args": ["-x"],
               "env": {"NEO4J_PASSWORD": "pw'1", "NEO4J_DATABASE": "arnold"}},
        "gh": {"command": "npx", "args": ["-y", "pkg"], "env": {"GITHUB_TOKEN": "tok"}},
        "plain": {"command": "p", "args": []},
    }}


def _spec_for(tmp_path, **servers):
    return {"launcher": "/L/mcp_launch.sh", "secret_key_pattern": PATTERN,
            "servers": {k: str(v) for k, v in servers.items()}}


def test_rewrites_only_when_env_holds_identical_value(tmp_path):
    (tmp_path / "db").mkdir()
    (tmp_path / "db" / ".env").write_text("NEO4J_PASSWORD=pw'1\nOTHER=x\n")
    (tmp_path / "gh").mkdir()  # no .env: must stay inline
    new, report, inline = rw.plan(_cfg(), _spec_for(tmp_path, db=tmp_path / "db", gh=tmp_path / "gh"))
    db = new["mcpServers"]["db"]
    assert db["command"] == "/L/mcp_launch.sh"
    assert db["args"] == [str(tmp_path / "db"), "--only", "NEO4J_PASSWORD", "--", "srv", "-x"]
    assert db["env"] == {"NEO4J_DATABASE": "arnold"}
    assert new["mcpServers"]["gh"]["env"] == {"GITHUB_TOKEN": "tok"}
    assert inline == ["gh"]
    assert new["mcpServers"]["plain"] == _cfg()["mcpServers"]["plain"]


def test_different_value_refuses(tmp_path):
    (tmp_path / ".env").write_text("NEO4J_PASSWORD=other\n")
    with pytest.raises(SystemExit) as e:
        rw.plan(_cfg(), _spec_for(tmp_path, db=tmp_path))
    assert "pw'1" not in str(e.value)


def test_unmapped_server_left_inline(tmp_path):
    _, _, inline = rw.plan(_cfg(), _spec_for(tmp_path))
    assert sorted(inline) == ["db", "gh"]


def test_redact_hides_every_secret_value():
    text = json.dumps(rw.redact(_cfg(), PATTERN))
    assert "pw'1" not in text and "tok" not in text
    assert "arnold" in text


# ----------------------------------------------- DISP-002 Part C: the evidence is committed by the run that writes it

def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


@pytest.fixture
def repo(tmp_path):
    """A repository with a config to read, a spec naming it, and nothing uncommitted."""
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _git(r, "config", "user.email", "t@t")
    _git(r, "config", "user.name", "t")
    (r / "README").write_text("x\n")
    _git(r, "add", "README")
    _git(r, "commit", "-q", "-m", "init")
    config = tmp_path / "claude_desktop_config.json"
    config.write_text(json.dumps(_cfg(), indent=2) + "\n")
    spec = tmp_path / "servers.yaml"
    spec.write_text(yaml.safe_dump({"config": str(config), "launcher": "/L/mcp_launch.sh",
                                    "secret_key_pattern": PATTERN, "servers": {}}))
    return r, spec


def test_evidence_run_leaves_a_clean_tree_with_one_path_scoped_commit(repo):
    r, spec = repo
    (r / "unrelated.txt").write_text("someone else's work\n")      # must not be swept into the commit
    ev = r / "docs" / "evidence" / "sec001" / "run1"
    assert rw.main(["--spec", str(spec), "--evidence", str(ev)]) == 1   # db and gh still inline: dry run
    assert _git(r, "status", "--porcelain", "--", "docs") == ""
    assert _git(r, "log", "-1", "--format=%s") == "sec001: evidence: docs/evidence/sec001/run1\n"
    assert sorted(_git(r, "show", "--name-only", "--format=", "HEAD").split()) == [
        "docs/evidence/sec001/run1/config_after.json", "docs/evidence/sec001/run1/servers.txt"]
    assert "unrelated.txt" in _git(r, "status", "--porcelain")
    assert "pw'1" not in (ev / "config_after.json").read_text()


def test_evidence_outside_docs_evidence_is_refused_before_anything_is_written(repo):
    r, spec = repo
    with pytest.raises(SystemExit) as e:
        rw.main(["--spec", str(spec), "--evidence", str(r / "elsewhere")])
    assert "docs/evidence/" in str(e.value)
    assert not (r / "elsewhere" / "config_after.json").exists()


def test_apply_refuses_from_a_linked_worktree(repo, monkeypatch):
    r, spec = repo
    wt = r.parent / "wt"
    _git(r, "worktree", "add", "-q", str(wt), "-b", "side")
    monkeypatch.chdir(wt)
    with pytest.raises(SystemExit) as e:
        rw.main(["--spec", str(spec), "--apply"])
    assert "primary checkout" in str(e.value)
    monkeypatch.chdir(r)
    assert rw.in_linked_worktree(r) is False
