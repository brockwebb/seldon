"""NUM-001R Part A: task numbers are allocated, not hand-minted (AD-038-R13).

`cc_tasks/2026-10-27_NUM-001R_task_numbers_allocated_and_headers_read_from_the_header_block.md`;
`docs/design/AD-038_ADDENDUM_05_task_numbers_allocated_and_headers_read_from_the_header_block.md`.

- `seldon task number <PREFIX>` (and the `seldon_task_number` MCP tool) print the next unused number, reading the graph
  and `cc_tasks/` in the primary checkout and every worktree.
- `register_task_file` refuses a file whose number another file holds (`number_taken`), naming the holder. An R
  re-filing is allowed over a withdrawn, superseded, rejected or still-open holder and refused over a running or
  finished one.

Real git and real Neo4j: the holders are read from the graph registration writes, and the worktrees from git.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from seldon.commands import cc
from seldon.commands.task import task_group
from seldon.core import numbering as N
from seldon.core.artifacts import create_task, transition_task, walk_to_completed
from seldon.domain.loader import load_domain_config
from seldon.mcp_server import seldon_task_number
from tests.testdb import TEST_DATABASE

DOMAIN = load_domain_config(Path(cc.__file__).parent.parent / "domain" / "research.yaml")
BODY = "# CC Task — {stem}\n\n**Date:** 2026-10-27\n\n## Steps\n\nDo the thing.\n"


# ------------------------------------------------------------------ the name grammar (no graph)

@pytest.mark.parametrize("name,expect", [
    ("2026-10-25_SEL-010_dispatch_waits.md", ("SEL", "010", "", "", "SEL-010")),
    ("2026-10-26_SEL-010R2_dispatch_waits.md", ("SEL", "010", "", "R2", "SEL-010")),
    ("2026-10-27_NUM-001R_task_numbers.md", ("NUM", "001", "", "R", "NUM-001")),
    ("2026-10-20_HB-01b_acquisition.md", ("HB", "01", "b", "", "HB-01b")),
    ("2026-10-26_SQ-021M2_sq021s_rebased.md", ("SQ", "021", "M2", "", "SQ-021M2")),
    ("2026-10-27_NUM-001R_task_numbers_RESULT.md", ("NUM", "001", "", "R", "NUM-001")),
])
def test_a_file_name_carries_its_number(name, expect):
    t = N.file_token(name)
    assert (t.prefix, t.digits, t.suffix, t.refile, t.identity) == expect


@pytest.mark.parametrize("name", ["2026-09-01_c2b_quickfacts_forensics.md", "2026-09-10_scan_frame_v5.md",
                                  "2026-10-17_deerflow-pilot_arnold.md", "README.md"])
def test_an_unnumbered_file_holds_nothing(name):
    assert N.file_token(name) is None


@pytest.mark.parametrize("desc,token", [
    ("NUM-001: task identifiers are minted by hand", "NUM-001"),
    ("MODEL-001 — Model selection is config-driven", "MODEL-001"),
    ("FRICTION-002 Part D step 3 (kill rule): over the first three", None),
    ("Task-file header parsing: anchor headers to line start", None),
])
def test_a_file_less_task_holds_the_number_its_description_leads_with(desc, token):
    t = N.description_token(desc)
    assert (str(t) if t else None) == token


def test_the_next_number_follows_the_highest_holder_whatever_its_suffix_and_keeps_the_width():
    holders = [N.Holder(N.file_token(n), None, None, n, "t") for n in (
        "2026-10-01_SEL-009_a.md", "2026-10-02_SEL-010R2_b.md", "2026-10-03_HB-51_c.md", "2026-10-04_HB-46b_d.md")]
    assert N.next_number("SEL", holders)["token"] == "SEL-011"
    assert N.next_number("HB", holders)["token"] == "HB-52"
    assert N.next_number("NEW", holders)["token"] == "NEW-001"
    with pytest.raises(N.NumberingError, match="not a task prefix"):
        N.next_number("sel-", holders)


# ------------------------------------------------------------------ registration and the allocator (graph)

def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch) -> Path:
    """A project with no dispatcher, so registration applies only the checks every project gets."""
    root = tmp_path / "proj"
    root.mkdir()
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        _git(root, *args)
    (root / "seldon.yaml").write_text(
        f"project:\n  name: test\n  domain: research\n"
        f"neo4j:\n  database: {TEST_DATABASE}\n  uri: {os.getenv('NEO4J_URI', 'bolt://localhost:7687')}\n"
        f"event_store:\n  path: seldon_events.jsonl\n", encoding="utf-8")
    (root / ".gitignore").write_text(".claude/\n", encoding="utf-8")
    (root / "cc_tasks").mkdir()
    (root / "cc_tasks" / ".keep").write_text("", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "init")
    # Gates that are not this task's: AD-030-R9's design note, the lock refresh, the prior-art holds.
    monkeypatch.setattr(cc, "enforce_design_reference", lambda *a, **k: None)
    monkeypatch.setattr(cc.models, "ensure_fresh", lambda *a, **k: None)
    from seldon.core import prior_art
    monkeypatch.setattr(prior_art, "registration_holds", lambda *a, **k: [])
    return root


def _write(repo: Path, stem: str) -> Path:
    p = repo / "cc_tasks" / f"{stem}.md"
    p.write_text(BODY.format(stem=stem), encoding="utf-8")
    return p


def _register(repo: Path, driver, stem: str, lines=None) -> dict:
    config = yaml.safe_load((repo / "seldon.yaml").read_text(encoding="utf-8"))
    return cc.register_task_file(project_dir=repo, config=config, driver=driver, database=TEST_DATABASE,
                                 domain_config=DOMAIN, session_id=None, task_path=_write(repo, stem),
                                 allow_untracked=True, emit=(lines.append if lines is not None else None))


def _task_count(driver) -> int:
    with driver.session(database=TEST_DATABASE) as s:
        return s.run("MATCH (t:ResearchTask) RETURN count(t) AS n").single()["n"]


neo4j = pytest.mark.usefixtures("neo4j_available", "clean_test_db")


@neo4j
def test_two_files_with_one_number_the_second_is_refused_and_names_the_holder(repo, neo4j_driver):
    first = _register(repo, neo4j_driver, "2026-10-21_SQ-019_ai_readiness_graph_onto_the_kit")
    with pytest.raises(ValueError) as exc:
        _register(repo, neo4j_driver, "2026-10-21_SQ-019_readmission_of_a_changed_unit")
    msg = str(exc.value)
    assert msg.startswith("number_taken: SQ-019 is already registered to another file"), msg
    assert first["artifact_id"][:8] in msg and "2026-10-21_SQ-019_ai_readiness_graph_onto_the_kit.md" in msg
    assert "seldon task number SQ" in msg
    assert _task_count(neo4j_driver) == 1, "a refusal creates nothing"


@neo4j
def test_registering_the_same_file_again_is_not_a_collision_with_itself(repo, neo4j_driver):
    first = _register(repo, neo4j_driver, "2026-10-21_SQ-019_one")
    again = _register(repo, neo4j_driver, "2026-10-21_SQ-019_one")
    assert again["existing"] and again["artifact_id"] == first["artifact_id"]


@neo4j
def test_a_lettered_sibling_is_its_own_number(repo, neo4j_driver):
    _register(repo, neo4j_driver, "2026-10-20_HB-01_acquisition")
    assert not _register(repo, neo4j_driver, "2026-10-20_HB-01b_acquisition_completion")["existing"]


@neo4j
def test_an_r_refiling_over_an_open_holder_registers_and_names_the_holder_to_supersede(repo, neo4j_driver):
    held = _register(repo, neo4j_driver, "2026-10-26_SEL-010_dispatch_waits")
    lines: list[str] = []
    out = _register(repo, neo4j_driver, "2026-10-26_SEL-010R_dispatch_waits", lines)
    assert out["refiles"] == [held["artifact_id"]]
    hint = next(ln for ln in lines if ln.lstrip().startswith("re-files SEL-010"))
    assert f"seldon task supersede {held['artifact_id'][:8]} --superseded-by {out['artifact_id']}" in hint


@neo4j
def test_an_r_refiling_over_a_withdrawn_holder_names_nothing_to_supersede(repo, neo4j_driver):
    held = _register(repo, neo4j_driver, "2026-10-26_SEL-010R_dispatch_waits")
    transition_task(repo, neo4j_driver, TEST_DATABASE, DOMAIN, held["artifact_id"], "proposed", "withdrawn",
                    actor="human", terminal_reason="c10 refused it")
    assert _register(repo, neo4j_driver, "2026-10-26_SEL-010R2_dispatch_waits")["refiles"] == []


@neo4j
def test_an_r_refiling_over_a_finished_holder_is_refused(repo, neo4j_driver):
    held = _register(repo, neo4j_driver, "2026-10-09_MODEL-002_explicit_effort")
    walk_to_completed(repo, neo4j_driver, TEST_DATABASE, DOMAIN, held["artifact_id"], "proposed")
    with pytest.raises(ValueError, match=r"number_taken: MODEL-002R re-files MODEL-002, but its holder ran or "
                                         r"finished \(completed\)"):
        _register(repo, neo4j_driver, "2026-10-12_MODEL-002R_pinned_roles")


@neo4j
def test_a_second_file_with_the_same_r_number_is_refused(repo, neo4j_driver):
    _register(repo, neo4j_driver, "2026-10-26_SEL-010R_dispatch_waits")
    with pytest.raises(ValueError, match="SEL-010R itself is registered to another file"):
        _register(repo, neo4j_driver, "2026-10-26_SEL-010R_a_different_slug")


@neo4j
def test_a_bare_number_reused_after_its_holder_was_withdrawn_is_refused(repo, neo4j_driver):
    """MODEL-002 and SEL-006 were each filed twice under the bare number; the R suffix is how a re-filing is named."""
    held = _register(repo, neo4j_driver, "2026-10-14_SEL-006_registration_commits")
    transition_task(repo, neo4j_driver, TEST_DATABASE, DOMAIN, held["artifact_id"], "proposed", "withdrawn",
                    actor="human", terminal_reason="re-filed")
    with pytest.raises(ValueError, match=r"number_taken: SEL-006 .* name the file SEL-006R<n>"):
        _register(repo, neo4j_driver, "2026-10-15_SEL-006_registration_commits")


@neo4j
def test_a_file_less_task_holds_the_number_its_description_claims(repo, neo4j_driver):
    tid, _ = create_task(repo, neo4j_driver, TEST_DATABASE, DOMAIN,
                         "NUM-001: task identifiers are minted by hand per Desktop thread", [], "desktop", "accepted")
    with pytest.raises(ValueError, match=rf"NUM-001 by {tid[:8]} \(proposed, no file; numbered by its description\)"):
        _register(repo, neo4j_driver, "2026-10-27_NUM-001_task_numbers_allocated")
    assert _register(repo, neo4j_driver, "2026-10-27_NUM-001R_task_numbers_allocated")["refiles"] == [tid]


@neo4j
def test_the_allocator_reads_the_graph_and_every_worktree(repo, neo4j_driver, monkeypatch):
    _register(repo, neo4j_driver, "2026-10-26_SEL-011_registration_refuses")
    _write(repo, "2026-10-27_SEL-012_written_not_registered")          # on main's disk, unregistered
    tree = repo / ".claude" / "worktrees" / "other"
    _git(repo, "worktree", "add", "-q", "-b", "worktree-other", str(tree))
    (tree / "cc_tasks" / "2026-10-27_SEL-013_on_an_unmerged_branch_RESULT.md").write_text("x", encoding="utf-8")

    monkeypatch.chdir(repo)
    r = CliRunner().invoke(task_group, ["number", "sel"])
    assert r.exit_code == 0, r.output
    assert r.output.splitlines()[0] == "SEL-014"
    assert "2 checkout(s)" in r.output
    mcp = seldon_task_number.__wrapped__(prefix="SEL", project_dir=str(repo))
    assert mcp.splitlines()[0] == "SEL-014"
    assert CliRunner().invoke(task_group, ["number", "DESK"]).output.splitlines()[0] == "DESK-001"


@neo4j
def test_the_allocator_refuses_a_prefix_that_is_not_one(repo, monkeypatch):
    monkeypatch.chdir(repo)
    r = CliRunner().invoke(task_group, ["number", "9x"])
    assert r.exit_code == 1 and "is not a task prefix" in r.output
