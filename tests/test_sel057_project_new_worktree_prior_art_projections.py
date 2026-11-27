"""SEL-057: `seldon project new` is right in a dispatched worktree, and it writes the prior-art block and the
projections (aacps-ai-policy AP-03's filing, b0966092).

Part A: in a linked git worktree (`<primary>/.claude/worktrees/<name>`, the dispatcher's layout), every value
`project new` writes into `seldon.yaml` is the REPOSITORY's (the primary checkout's), never the worktree's: the
register's repository name, the sibling check, the scan program's relative path, the standing-band reference and the
plist's project. A linked worktree is transient, so the launchd job is never loaded from one.

Part B: the `prior_art` step writes AD-036 ADDENDUM 03's reference block and the project's own baseline; the
`projections` step declares the kit's standard projections in `docs.projections` and writes their marked files,
rendered from the graph, with no requirement authored.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from seldon.core import adopt as A
from seldon.core import prior_art as PA
from seldon.core import project_new as PN
from seldon.core import requirements as RQ
from tests.test_sel019_project_new import _git, _new, kit, launchctl  # noqa: F401  (fixtures)
from tests.testdb import TEST_DATABASE

neo4j_tests = pytest.mark.usefixtures("neo4j_available", "clean_test_db")

PROJECT = "realproj"
MINIMAL_SELDON_YAML = f"""\
project:
  name: {PROJECT}
  slug: {PROJECT}
neo4j:
  uri: bolt://localhost:7687
  database: {TEST_DATABASE}
"""


def _repo(tmp_path: Path, seldon_yaml: str = MINIMAL_SELDON_YAML) -> Path:
    """A primary checkout beside the kit (tmp/kit, so `environment_packages: [kit]` is its sibling)."""
    primary = tmp_path / PROJECT
    primary.mkdir()
    _git(primary, "init", "-q", "-b", "main")
    _git(primary, "config", "user.email", "t@example.com")
    _git(primary, "config", "user.name", "t")
    (primary / "seldon.yaml").write_text(seldon_yaml, encoding="utf-8")
    (primary / ".gitignore").write_text(".claude/worktrees/\n", encoding="utf-8")
    _git(primary, "add", "-A")
    _git(primary, "commit", "-qm", "init")
    return primary


def _worktree(primary: Path, name: str = "cozy-inventing-diffie") -> Path:
    """The dispatcher's layout: `<primary>/.claude/worktrees/<name>` on `worktree-<name>`."""
    wt = primary / ".claude" / "worktrees" / name
    _git(primary, "worktree", "add", "-q", "-b", f"worktree-{name}", str(wt))
    return wt


# ══════════════════════════════════════════════════════════════════════════════
# Part A: the values are the repository's, not the worktree's
# ══════════════════════════════════════════════════════════════════════════════

def test_the_register_is_named_after_the_repository_not_the_worktree(tmp_path):
    """Filing item 1: `decisions.repository cozy-inventing-diffie` was written from a dispatched worktree."""
    wt = _worktree(_repo(tmp_path))
    text, repo = PN.decisions_text(wt)
    assert repo == PROJECT
    assert yaml.safe_load(text)["decisions"] == {"repository": PROJECT}


def test_the_siblings_are_looked_for_beside_the_primary_checkout(tmp_path, kit):
    """Filing item 2: `no sibling directory for [...] beside .../.claude/worktrees/<name>`, exit 1."""
    primary = _repo(tmp_path)
    wt = _worktree(primary)
    assert PN.missing_siblings(primary, ["kit"]) == []
    assert PN.missing_siblings(wt, ["kit"]) == []
    assert PN.missing_siblings(wt, ["kit", "absent"]) == ["absent"]


def test_the_scan_program_is_relative_to_the_primary_checkout(tmp_path, kit):
    """`seldon.yaml` relative paths resolve at the primary (`worktree.anchor`, SEL-018), so the re-rooted scan
    program written from a worktree must be the one written from the primary."""
    primary = _repo(tmp_path)
    wt = _worktree(primary)
    cfg = PN.project_new_config(kit)
    from_primary, _ = PN.environment_text(primary, cfg, kit, False, None)
    from_wt, _ = PN.environment_text(wt, cfg, kit, False, None)
    cmd = yaml.safe_load(from_wt)["desktop_commit"]["scan"]["command"]
    assert cmd == yaml.safe_load(from_primary)["desktop_commit"]["scan"]["command"]
    assert cmd[0] == "../scanner/.venv/bin/python"


def test_adopt_from_a_worktree_writes_the_primarys_band_reference_and_plist_project(tmp_path, kit):
    primary = _repo(tmp_path)
    wt = _worktree(primary)
    config = yaml.safe_load((wt / "seldon.yaml").read_text())
    answers = {k: d for k, _q, d in A.questions(wt, config, A.kit_config(kit), kit)}
    assert answers["standing_band_ref"] == "../kit/controls.yaml#spend.daily_tokens"
    out = A.adoption(wt, answers, kit_dir=kit)
    assert f"<string>{primary.resolve()}</string>" in out["plist"]
    assert ".claude/worktrees" not in out["plist"]


@neo4j_tests
def test_project_new_in_a_dispatched_worktree_exits_zero_and_converges(tmp_path, kit, launchctl):
    """The whole command, run where AP-03 ran it: in a linked worktree of an existing project. It exits 0, names the
    register after the project, refuses nothing, loads no launchd job from the transient tree, and a second run
    changes nothing."""
    primary = _repo(tmp_path)
    wt = _worktree(primary)
    res = _new(wt, "--dispatch", "--enable")
    assert res.exit_code == 0, res.output
    assert "refused" not in res.output, res.output
    config = yaml.safe_load((wt / "seldon.yaml").read_text())
    assert config["decisions"] == {"repository": PROJECT}
    assert config["prior_art"]["ref"] == "../kit/seldon.yaml#prior_art"
    assert config["dispatch"]["standing_band_ref"] == "../kit/controls.yaml#spend.daily_tokens"
    assert launchctl.calls == [], "a launchd job is never loaded from a linked worktree"
    assert f"seldon project new {primary.resolve()} --dispatch --enable" in res.output
    assert _git(wt, "status", "--porcelain") == ""

    head = _git(wt, "rev-parse", "HEAD")
    again = _new(wt, "--dispatch", "--enable")
    assert again.exit_code == 0, again.output
    assert "nothing changed; already a project" in again.output, again.output
    assert _git(wt, "rev-parse", "HEAD") == head


# ══════════════════════════════════════════════════════════════════════════════
# Part B: the prior-art block and its baseline
# ══════════════════════════════════════════════════════════════════════════════

def _design_notes(repo: Path) -> None:
    d = repo / "docs" / "design"
    d.mkdir(parents=True)
    (d / "DN-001_scope.md").write_text("# scope\n")
    (d / "DN-001_ADDENDUM_01_more.md").write_text("# more\n")
    (d / "notes.txt").write_text("not a note\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "notes")
    (d / "DN-002_untracked.md").write_text("# not on the branch\n")


def test_the_prior_art_step_writes_addendum_03s_reference_and_the_baseline(tmp_path, kit):
    primary = _repo(tmp_path)
    _design_notes(primary)
    cfg = PN.project_new_config(kit)
    step = PN.prior_art_step(primary, cfg, kit)
    assert step.status == "changed", step.detail
    assert set(step.wrote) == {"seldon.yaml", "docs/design/AD-036_baseline.txt"}
    config = yaml.safe_load((primary / "seldon.yaml").read_text())
    assert config["prior_art"] == {"ref": "../kit/seldon.yaml#prior_art",
                                   "gate": {"baseline": "docs/design/AD-036_baseline.txt"}}
    s = PA.settings(primary, config)                    # resolves to the kit's one definition
    assert s.defined_in == (kit / "seldon.yaml").resolve()
    # The baseline is the gated notes the branch tracks: not the addendum, not the untracked note, not the .txt.
    assert PA.baseline(s) == {"docs/design/DN-001_scope.md"}
    assert PN.prior_art_step(primary, cfg, kit).status == "ok"


def test_the_prior_art_ref_from_a_worktree_is_the_primarys(tmp_path, kit):
    wt = _worktree(_repo(tmp_path))
    step = PN.prior_art_step(wt, PN.project_new_config(kit), kit)
    assert step.status == "changed", step.detail
    assert yaml.safe_load((wt / "seldon.yaml").read_text())["prior_art"]["ref"] == "../kit/seldon.yaml#prior_art"


def test_a_project_that_defines_or_references_prior_art_is_left_alone(tmp_path, kit):
    primary = _repo(tmp_path, MINIMAL_SELDON_YAML + "prior_art:\n  ref: ../kit/seldon.yaml#prior_art\n  gate:\n"
                                                    "    baseline: mine.txt\n")
    (primary / "mine.txt").write_text("# mine\n")
    before = (primary / "seldon.yaml").read_text()
    assert PN.prior_art_step(primary, PN.project_new_config(kit), kit).status == "ok"
    assert (primary / "seldon.yaml").read_text() == before
    assert not (primary / "docs" / "design" / "AD-036_baseline.txt").exists()


def test_a_declared_block_whose_baseline_is_missing_gets_its_baseline(tmp_path, kit):
    primary = _repo(tmp_path, MINIMAL_SELDON_YAML + "prior_art:\n  ref: ../kit/seldon.yaml#prior_art\n  gate:\n"
                                                    "    baseline: docs/design/AD-036_baseline.txt\n")
    step = PN.prior_art_step(primary, PN.project_new_config(kit), kit)
    assert step.status == "changed" and step.wrote == ["docs/design/AD-036_baseline.txt"], step
    assert PA.baseline_from_text((primary / "docs/design/AD-036_baseline.txt").read_text()) == set()


def test_a_kit_without_a_prior_art_definition_is_refused(tmp_path, kit):
    (kit / "seldon.yaml").write_text(yaml.safe_dump({k: v for k, v in A.kit_config(kit).items()
                                                     if k != "prior_art"}))
    primary = _repo(tmp_path)
    with pytest.raises(PN.ProjectNewError, match="prior_art"):
        PN.prior_art_step(primary, PN.project_new_config(kit), kit)


# ══════════════════════════════════════════════════════════════════════════════
# Part B: the projections
# ══════════════════════════════════════════════════════════════════════════════

def _need(rid: str, doc: str, text: str) -> dict:
    return {"requirement_id": rid, "description": text, "document": doc, "state": "proposed", "_tests": [],
            "_sources": [], "_decisions": [], "_satisfiers": []}


def test_the_projections_step_declares_the_kits_set_and_writes_marked_files(tmp_path, kit):
    primary = _repo(tmp_path)
    step = PN.projections_step(primary, PN.project_new_config(kit), lambda: [])
    assert step.status == "changed", step.detail
    assert set(step.wrote) == {"seldon.yaml", "docs/se/strs.md", "docs/se/rtm.md"}
    config = yaml.safe_load((primary / "seldon.yaml").read_text())
    declared = config["docs"]["projections"]
    assert [p["path"] for p in declared] == ["docs/se/strs.md", "docs/se/rtm.md"]
    assert all("title" not in p and "documents" not in p for p in declared), "kit-only keys are not declared"
    s = RQ.settings(config)                              # the declaration validates as AD-013-R2's block
    for p in s.projections:
        text = (primary / p["path"]).read_text()
        assert RQ.START_RE.search(text), f"{p['path']} carries seldon:projection markers"
        assert RQ.stamped_revision(text), f"{p['path']} is stamped"
        r = RQ.render_projection(primary, p, [], s)      # `seldon docs generate --check` is clean
        assert not r.changed, p["path"]
        assert "| ID |" in text and "0 requirements" in text
    rtm = (primary / "docs/se/rtm.md").read_text()
    assert 'document="docs/se/strs.md"' in rtm
    assert PN.projections_step(primary, PN.project_new_config(kit), lambda: []).status == "ok"


def test_the_projections_render_the_graphs_requirements_and_author_none(tmp_path, kit):
    """A requirement already in the graph is rendered where its document is declared; the step adds none."""
    primary = _repo(tmp_path)
    nodes = [_need("N-1", "docs/se/strs.md", "the operator's need")]
    assert PN.projections_step(primary, PN.project_new_config(kit), lambda: nodes).status == "changed"
    strs = (primary / "docs/se/strs.md").read_text()
    rtm = (primary / "docs/se/rtm.md").read_text()
    assert "| N-1 | the operator's need |" in strs and "1 requirements" in strs
    assert "N-1" in rtm
    config = yaml.safe_load((primary / "seldon.yaml").read_text())
    s = RQ.settings(config)
    assert all(not RQ.render_projection(primary, p, nodes, s).changed for p in s.projections)


def test_a_declared_projection_whose_file_is_missing_gets_its_file_and_nothing_else(tmp_path, kit):
    primary = _repo(tmp_path, MINIMAL_SELDON_YAML + "docs:\n  projections:\n  - path: docs/REQ.md\n"
                                                    "    kind: requirements\n")
    before = (primary / "seldon.yaml").read_text()
    step = PN.projections_step(primary, PN.project_new_config(kit), lambda: [])
    assert step.status == "changed" and step.wrote == ["docs/REQ.md"], step
    assert (primary / "seldon.yaml").read_text() == before
    assert RQ.START_RE.search((primary / "docs/REQ.md").read_text())
    assert PN.projections_step(primary, PN.project_new_config(kit), lambda: []).status == "ok"


def test_an_existing_projection_file_is_never_overwritten(tmp_path, kit):
    primary = _repo(tmp_path, MINIMAL_SELDON_YAML + "docs:\n  projections:\n  - path: docs/REQ.md\n"
                                                    "    kind: requirements\n")
    (primary / "docs").mkdir()
    (primary / "docs/REQ.md").write_text("# hand file\n")
    calls = []
    step = PN.projections_step(primary, PN.project_new_config(kit), lambda: calls.append(1) or [])
    assert step.status == "ok" and calls == [], "the graph is read only when a file must be written"
    assert (primary / "docs/REQ.md").read_text() == "# hand file\n"


def test_a_graph_that_cannot_be_read_refuses_the_step_with_the_cause(tmp_path, kit):
    primary = _repo(tmp_path)

    def down():
        raise OSError("connection refused")

    step = PN.projections_step(primary, PN.project_new_config(kit), down)
    assert step.status == "refused" and "connection refused" in step.detail, step
    assert not (primary / "docs/se/strs.md").exists()


def test_seldons_own_kit_block_names_the_baseline_and_the_se_projections():
    cfg = PN.project_new_config(Path(__file__).resolve().parents[1])
    assert cfg["prior_art_baseline"] == "docs/design/AD-036_baseline.txt"
    paths = [p["path"] for p in cfg["projections"]]
    assert paths == ["docs/se/strs.md", "docs/se/syrs.md", "docs/se/icd.md", "docs/se/rtm.md"]
    RQ.settings({"docs": {"projections": [{k: v for k, v in p.items() if k not in PN.PROJECTION_KIT_KEYS}
                                          for p in cfg["projections"]]}})


@neo4j_tests
def test_a_new_project_carries_the_prior_art_block_and_current_projections(tmp_path, kit, launchctl):
    """End to end on a fresh directory: both blocks written, the files committed, and a fresh render from the
    project's own (empty) graph changes nothing, so factory's `requirements_regenerate_clean` passes."""
    from seldon.config import get_neo4j_driver
    target = tmp_path / "newproj"
    res = _new(target)
    assert res.exit_code == 0, res.output
    config = yaml.safe_load((target / "seldon.yaml").read_text())
    assert config["prior_art"]["gate"]["baseline"] == "docs/design/AD-036_baseline.txt"
    assert [p["path"] for p in config["docs"]["projections"]] == ["docs/se/strs.md", "docs/se/rtm.md"]
    tracked = set(_git(target, "ls-files").split())
    assert {"docs/design/AD-036_baseline.txt", "docs/se/strs.md", "docs/se/rtm.md"} <= tracked
    assert "state/prior_art_queries.jsonl merge=union" in (target / ".gitattributes").read_text()
    driver = get_neo4j_driver(config)
    try:
        assert RQ.stale_projections(target, driver, config["neo4j"]["database"], config) == []
    finally:
        driver.close()
    assert _git(target, "status", "--porcelain") == ""
