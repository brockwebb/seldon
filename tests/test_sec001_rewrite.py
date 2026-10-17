"""Tests for scripts/sec001/rewrite_desktop_config.py (SEC-001R)."""

import importlib.util
import json
from pathlib import Path

import pytest

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
