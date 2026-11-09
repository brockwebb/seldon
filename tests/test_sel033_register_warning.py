"""SEL-033 Part E (AD-033-R13): a Seldon-managed project with no decision register is told so.

hazbrief-mcp ran twenty days, 143 tasks and seventeen design notes with no `decisions:` block, and `seldon init`,
`seldon go` and `seldon verify` never said so (its filing SEL-031). Each now reports "no decision register declared
(AD-033); rulings made in this project have no record", and `seldon project new` declares one by default.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from seldon.commands.go import assemble_go_context, assemble_go_context_as_dict
from seldon.commands.init import init_command
from seldon.commands.verify import TIER_A_CHECKS, check_decisions
from seldon.core import decisions as dr
from seldon.core import project_new as PN

UNREACHABLE_NEO4J_URI = "bolt://127.0.0.1:1"
NOTICE = "no decision register declared (AD-033); rulings made in this project have no record"


def _project(tmp_path: Path, decisions: dict | None) -> Path:
    cfg = {"project": {"name": "probe", "domain": "research"},
           "neo4j": {"database": "seldon-probe", "uri": UNREACHABLE_NEO4J_URI}}
    if decisions is not None:
        cfg["decisions"] = decisions
    (tmp_path / "seldon.yaml").write_text(yaml.safe_dump(cfg))
    return tmp_path


def test_the_notice_is_the_rulings_words():
    assert dr.NO_REGISTER_NOTICE == NOTICE
    assert dr.register_notice({}) == NOTICE
    assert dr.register_notice({"decisions": {"repository": "probe"}}) is None


class TestVerify:
    def test_a_project_with_no_register_warns_with_the_notice_and_the_remedy(self, tmp_path):
        p = _project(tmp_path, None)
        r = check_decisions(None, "unused", p, yaml.safe_load((p / "seldon.yaml").read_text()))
        assert r.symbol == "warn"
        assert r.summary == NOTICE
        assert any("decisions:" in d and "repository" in d for d in r.details)

    def test_the_warning_does_not_block_strict(self):
        # --strict blocks only a Tier A *fail*; the register check stays Tier A for its failures, and the missing
        # block is a warning (AD-033-R13: declaring it is the project's own act).
        assert "Decision register" in TIER_A_CHECKS

    def test_a_declared_empty_register_is_not_the_warning(self, tmp_path):
        p = _project(tmp_path, {"repository": "probe"})
        cfg = yaml.safe_load((p / "seldon.yaml").read_text())
        r = check_decisions(_NoDriver(), "unused", p, cfg)
        assert r.summary != NOTICE


class _NoDriver:
    """A driver whose session returns no rows: the register is empty, so the projection is trivially current."""

    def session(self, database=None):
        return _NoSession()


class _NoSession:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, *a, **k):
        return _Rows()


class _Rows:
    def data(self):
        return []


class TestGo:
    def test_go_reports_a_missing_register(self, tmp_path):
        p = _project(tmp_path, None)
        text = assemble_go_context(project_dir=str(p), brief=True, in_claude_code=True)
        assert "## Decision register" in text and NOTICE in text
        data = assemble_go_context_as_dict(project_dir=str(p), brief=True, in_claude_code=True)
        assert NOTICE in data["decision_register"]

    def test_go_is_silent_when_a_register_is_declared(self, tmp_path):
        p = _project(tmp_path, {"repository": "probe"})
        text = assemble_go_context(project_dir=str(p), brief=True, in_claude_code=True)
        assert "## Decision register" not in text
        assert assemble_go_context_as_dict(project_dir=str(p), brief=True, in_claude_code=True)[
            "decision_register"] is None

    def test_go_with_no_seldon_yaml_says_nothing_of_a_register(self, tmp_path):
        assert assemble_go_context_as_dict(project_dir=str(tmp_path), brief=True,
                                           in_claude_code=True)["decision_register"] is None


class TestInit:
    def test_init_warns_that_it_wrote_no_register(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NEO4J_URI", UNREACHABLE_NEO4J_URI)
        monkeypatch.delenv("SELDON_ONTOLOGY_PATH", raising=False)
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
        (tmp_path / "gitconfig").write_text("")
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            subprocess.run(["git", "init", "-q", td], check=True)
            result = runner.invoke(init_command, ["sel033-probe"])
            cfg = yaml.safe_load(Path(td, "seldon.yaml").read_text())
        assert result.exit_code == 0, result.output
        assert "decisions" not in cfg
        assert NOTICE in result.output


class TestProjectNew:
    def test_project_new_declares_the_register_by_default(self, tmp_path):
        d = tmp_path / "hb-probe"
        d.mkdir()
        p = _project(d, None)
        text, repo = PN.decisions_text(p)
        assert repo == "hb-probe"
        cfg = yaml.safe_load(text)
        assert cfg["decisions"] == {"repository": "hb-probe"}
        assert cfg["project"]["name"] == "probe", "the rest of seldon.yaml is kept"
        assert "AD-033-R13" in text
        (p / "seldon.yaml").write_text(text)
        assert dr.settings(p, cfg).repository == "hb-probe"
        assert PN.decisions_text(p) == (None, None), "idempotent: a declared register is left as it is"

    def test_an_empty_decisions_key_is_refused_not_overwritten(self, tmp_path):
        (tmp_path / "seldon.yaml").write_text("project:\n  name: probe\ndecisions:\n")
        with pytest.raises(PN.ProjectNewError, match="empty `decisions:`"):
            PN.decisions_text(tmp_path)

    def test_the_command_runs_the_step(self):
        src = (Path(__file__).parent.parent / "seldon" / "commands" / "project.py").read_text()
        assert "PN.decisions_text(project_dir)" in src
