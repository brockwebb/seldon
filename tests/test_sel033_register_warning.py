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


class TestARegisterDeclaredOnABranchIsNumberedAtItsMerge:
    """Found running SEL-033 Part D: hazbrief-mcp's HB-144 declared the project's first `decisions:` block and wrote
    337 pending records on its branch; the merge fast-forwarded and numbered none, because the merge step read the
    config loaded before the fast-forward, which has no register (`number_merged_register` returned None at
    `s is None`). SEL-031's "register after the fact" route ends here, so it is fixed here: the merge reads the
    merged seldon.yaml, and the pre-merge verification reads the branch's."""

    def _repo(self, tmp_path):
        from tests.test_loop001_register_seq import NOTE, NOTE_TEXT, _git
        root = tmp_path / "proj"
        (root / "docs" / "design").mkdir(parents=True)
        (root / NOTE).write_text(NOTE_TEXT, encoding="utf-8")
        (root / "seldon.yaml").write_text(yaml.safe_dump({
            "project": {"name": "proj", "domain": "research"}, "event_store": {"path": "seldon_events.jsonl"}}))
        (root / ".gitignore").write_text("seldon_events.jsonl\ndocs/decisions/.register.lock\n", encoding="utf-8")
        _git(tmp_path, "init", "-q", "-b", "main", str(root))
        _git(root, "config", "user.email", "t@example.org")
        _git(root, "config", "user.name", "t")
        _git(root, "config", "core.hooksPath", "/dev/null")
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", "base: no register")
        wt = tmp_path / "wt-a"
        _git(root, "worktree", "add", "-q", "-b", "a", str(wt))
        cfg = yaml.safe_load((wt / "seldon.yaml").read_text())
        cfg["decisions"] = {"repository": "proj", "design_notes": [
            {"glob": "docs/design/*.md", "pattern": r"^(?:#+\s*|\s*[-*]\s*\*\*|\*\*)(R-\d{1,3})\b",
             "id": "{repo}:{label}"}]}
        (wt / "seldon.yaml").write_text(yaml.safe_dump(cfg))
        return root, wt, _git

    def test_the_first_register_a_branch_declares_is_numbered_when_it_merges(self, tmp_path):
        from seldon.commands import dispatch_worktree as W
        from tests.test_loop001_register_seq import _accept
        root, wt, git = self._repo(tmp_path)
        before = yaml.safe_load((root / "seldon.yaml").read_text())   # what the dispatcher loaded for the pass
        assert "decisions" not in before
        [path] = _accept(wt, "R-1", 3, "The kit never stores content.")
        assert path.parent.name == dr.PENDING_DIR
        git(wt, "add", "-A")
        git(wt, "commit", "-q", "-m", "a: declare the register, R-1")

        assert W._register_findings(wt, before) == [], "the branch's register is verified with the branch's config"
        git(root, "merge", "--ff-only", "-q", "a")
        out = W.number_merged_register(root, before, "sess-1", "task-a", "a")

        assert out is not None, "the merge numbered nothing: it read the pre-merge config"
        assert [(m["id"], m["seq"]) for m in out["mapping"]] == [("proj:R-1", 1)]
        assert dr.Register("proj", root).pending_files() == []
        assert git(root, "status", "--porcelain").stdout.strip() == ""

    def test_a_branch_whose_register_does_not_verify_is_still_refused(self, tmp_path):
        from seldon.commands import dispatch_worktree as W
        from tests.test_loop001_register_seq import _accept
        root, wt, git = self._repo(tmp_path)
        before = yaml.safe_load((root / "seldon.yaml").read_text())
        [path] = _accept(wt, "R-1", 3, "The kit never stores content.")
        path.write_text(path.read_text().replace("never stores", "always stores"))   # a hand edit
        assert W._register_findings(wt, before) != []


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
