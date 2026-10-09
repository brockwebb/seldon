"""PA-001 (AD-036): the prior-art receipts tool, its verification, and the gate at both points.

Every corpus here is synthetic (a scratch git repository, a scratch non-git folder, a stub
library), so no test reads the operator's repositories or loads the library index. The gate tests
end with the removal check of kg_construction_methodology section 7.9: each gate is switched off in
turn and the same planted note is shown to get through, so the test is known to depend on the gate.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from seldon.core import prior_art as pa

LIB_SHA = "a" * 64


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True,
                          text=True).stdout.strip()


def _repo(root: Path, files: dict) -> str:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    return _git(root, "rev-parse", "HEAD")


SIBLING = {
    "docs/design/DN-001_unit.md": "# DN-001\n\nIntro line.\n\nThe unit of extraction is the\n"
                                  "paragraph, measured.\n\nUnrelated text.\n",
    "docs/research/note.md": "A model pin is a product fact.\n\nCheck vendor docs first.\n",
    "src/code.md": "unit of extraction outside the corpus\n",
}


@pytest.fixture
def proj(tmp_path):
    """A project with a `prior_art:` block, one git sibling, one non-git root and a governed ledger."""
    project = tmp_path / "proj"
    _repo(project, {"README.md": "x\n"})
    sha = _repo(tmp_path / "sib", SIBLING)
    (tmp_path / "sib" / ".gitignore").write_text("handoffs/\n")
    (tmp_path / "sib" / "handoffs").mkdir()
    (tmp_path / "sib" / "handoffs" / "h.md").write_text("Session.\n\nunit of extraction again\n")
    (tmp_path / "loose").mkdir()
    (tmp_path / "loose" / "a.md").write_text("the unit of extraction, loose\n")
    (project / "governed" / "ledger").mkdir(parents=True)
    (project / "docs" / "design").mkdir(parents=True)
    (project / "docs" / "design" / "AD-036_baseline.txt").write_text("docs/design/OLD.md\n")
    (project / "docs" / "design" / "OLD.md").write_text("# an old note, no prior art\n")
    config = {
        "governed": {"graph_dir": "governed"},
        "prior_art": {
            "log": "state/q.jsonl",
            "internal_roots": [{"name": "sib", "path": str(tmp_path / "sib")},
                               {"name": "loose", "path": str(tmp_path / "loose"),
                                "include": ["**"]}],
            "internal": {"default_include": ["docs/design/**", "docs/research/**", "handoffs/**"],
                         "suffixes": [".md"], "top_n": 20, "max_file_bytes": 100000,
                         "bm25": {"k1": 1.2, "b": 0.75}},
            "library": {"graph": str(tmp_path / "nolib"), "k": 20},
            "gate": {"design_dir": "docs/design", "baseline": "docs/design/AD-036_baseline.txt",
                     "exempt_globs": ["*_ADDENDUM_*.md", "*_erratum_*.md"]},
        },
    }
    return {"dir": project, "config": config, "sha": sha, "tmp": tmp_path}


class StubLibrary:
    """Answers every query with the same release and rows; counts calls."""

    def __init__(self, rows=("lesson:x#p1:1:0-9",), sha=LIB_SHA):
        self.rows, self.sha, self.calls = list(rows), sha, 0

    def search(self, query, k=None):
        self.calls += 1
        return {"query": query, "release": "lib.json", "sha256": self.sha, "rows": self.rows,
                "hits": []}


def _settings(proj):
    return pa.settings(proj["dir"], proj["config"])


def _note(proj, name, body) -> Path:
    p = proj["dir"] / "docs" / "design" / name
    p.write_text(body)
    return p


def _good_body(proj, internal_hits="docs/design/DN-001_unit.md:5", rows="lesson:x#p1:1:0-9"):
    return (f"# AD-099 a note\n\n## 2. Prior art\n\n### External\n\n"
            f'- library receipt: query "unit of extraction" | release lib.json sha256:{LIB_SHA} '
            f"| rows {rows}\n\n### Internal\n\nProse is allowed.\n\n"
            f'- internal receipt: query "unit of extraction" | repo sib@{proj["sha"]} '
            f"| hits {internal_hits}\n\n## 3. Decisions\n")


# --------------------------------------------------------------------------- the internal arm

def test_internal_search_matches_all_terms_in_one_paragraph_inside_the_declared_corpus(proj):
    s = _settings(proj)
    res = pa.Internal(s).search("unit of extraction")
    cites = {(h.root, h.cite().split("#")[0]) for h in res["hits"]}
    assert ("sib", "docs/design/DN-001_unit.md:5") in cites     # terms across two lines, one para
    assert ("loose", "a.md:1") in cites
    assert not any("src/code.md" in c for _r, c in cites)       # outside the include globs
    untracked = [h for h in res["hits"] if h.path == "handoffs/h.md"]
    assert untracked and not untracked[0].tracked                # gitignored, read from disk
    assert res["corpora"]["sib"]["identity"] == proj["sha"]
    assert res["corpora"]["loose"]["identity"].startswith("tree:")


def test_word_start_matching_finds_inflections_but_not_infixes(proj):
    s = _settings(proj)
    assert pa.Internal(s).search("model pin")["hits"]
    assert not pa.Internal(s).search("odel")["hits"]


def test_printed_receipts_round_trip_through_verify(proj):
    s = _settings(proj)
    tool = pa.Internal(s)
    receipts = tool.receipts(tool.search("unit of extraction"))
    body = ("# AD-099\n\n## Prior art\n\n### External\n\n"
            f'- library receipt: query "q" | release lib.json sha256:{LIB_SHA} | rows none\n\n'
            "### Internal\n\n" + "\n".join(receipts) + "\n")
    v = pa.verify_note(_note(proj, "AD-099_x.md", body), s, library=StubLibrary())
    assert v.verdict == "pass", v.problems
    assert {r.status for r in v.receipts} == {pa.PASS}


def test_a_cited_line_the_query_does_not_return_fails_id_not_returned(proj):
    s = _settings(proj)
    v = pa.verify_note(_note(proj, "AD-099_x.md", _good_body(
        proj, internal_hits="docs/design/DN-001_unit.md:7")), s, library=StubLibrary())
    assert v.verdict == "fail"
    assert [r.status for r in v.receipts if r.kind == "internal"] == [pa.ID_NOT_RETURNED]


def test_a_commit_that_does_not_exist_is_release_unavailable(proj):
    s = _settings(proj)
    body = _good_body(proj).replace(proj["sha"], "0" * 40)
    v = pa.verify_note(_note(proj, "AD-099_x.md", body), s, library=StubLibrary())
    assert [r.status for r in v.receipts if r.kind == "internal"] == [pa.RELEASE_UNAVAILABLE]


def test_receipts_re_run_at_the_named_commit_not_the_working_tree(proj):
    s = _settings(proj)
    sib = proj["tmp"] / "sib"
    (sib / "docs/design/DN-001_unit.md").write_text("rewritten, nothing matches\n")
    _git(sib, "commit", "-qam", "rewrite")
    v = pa.verify_note(_note(proj, "AD-099_x.md", _good_body(proj)), s, library=StubLibrary())
    assert v.verdict == "pass", v.problems


def test_an_untracked_hit_carries_its_hash_and_fails_when_the_file_moves(proj):
    s = _settings(proj)
    h = [x for x in pa.Internal(s).search("unit of extraction")["hits"]
         if x.path == "handoffs/h.md"][0]
    body = _good_body(proj, internal_hits=h.cite())
    assert pa.verify_note(_note(proj, "AD-099_x.md", body), s,
                          library=StubLibrary()).verdict == "pass"
    (proj["tmp"] / "sib" / "handoffs" / "h.md").write_text("Session.\n\nunit of extraction edited\n")
    v = pa.verify_note(_note(proj, "AD-099_x.md", body), s, library=StubLibrary())
    assert [r.status for r in v.receipts if r.kind == "internal"] == [pa.RELEASE_UNAVAILABLE]


def test_a_non_git_root_is_named_by_its_tree_digest_and_fails_when_it_changes(proj):
    s = _settings(proj)
    tool = pa.Internal(s)
    rec = [r for r in tool.receipts(tool.search("unit of extraction")) if "loose@" in r][0]
    body = (f"# AD-099\n\n## Prior art\n\n### External\n\n- library receipt: query \"q\" | release "
            f"lib.json sha256:{LIB_SHA} | rows none\n\n### Internal\n\n{rec}\n")
    assert pa.verify_note(_note(proj, "AD-099_x.md", body), s,
                          library=StubLibrary()).verdict == "pass"
    (proj["tmp"] / "loose" / "b.md").write_text("new\n")
    v = pa.verify_note(_note(proj, "AD-099_x.md", body), s, library=StubLibrary())
    assert [r.status for r in v.receipts if r.kind == "internal"] == [pa.RELEASE_UNAVAILABLE]


# ---------------------------------------------------------------------------- the library arm

def test_a_library_row_the_query_does_not_return_fails(proj):
    s = _settings(proj)
    v = pa.verify_note(_note(proj, "AD-099_x.md", _good_body(proj, rows="lesson:y#p9:9:0-1")), s,
                       library=StubLibrary())
    assert [r.status for r in v.receipts if r.kind == "library"] == [pa.ID_NOT_RETURNED]


def test_a_library_receipt_for_another_release_is_release_unavailable(proj):
    s = _settings(proj)
    v = pa.verify_note(_note(proj, "AD-099_x.md", _good_body(proj)), s,
                       library=StubLibrary(sha="b" * 64))
    assert [r.status for r in v.receipts if r.kind == "library"] == [pa.RELEASE_UNAVAILABLE]


def test_one_library_query_cited_twice_runs_once(proj):
    s = _settings(proj)
    body = _good_body(proj).replace("### Internal", (
        f'- library receipt: query "unit of extraction" | release lib.json sha256:{LIB_SHA} '
        f"| rows lesson:x#p1:1:0-9\n\n### Internal"))
    lib = StubLibrary()
    pa.verify_note(_note(proj, "AD-099_x.md", body), s, library=lib)
    assert lib.calls == 1


# ------------------------------------------------------------------------- the section rules

@pytest.mark.parametrize("body,needle", [
    ("# AD-099\n\nNo section here.\n", "no `## Prior art` section"),
    ("# AD-099\n\n## Prior art\n\n### External\n\n- library receipt: query \"q\" | release "
     f"lib.json sha256:{LIB_SHA} | rows none\n", "no `### Internal` subsection"),
    ("# AD-099\n\n## Prior art\n\n### External\n\n- library receipt: query \"q\" | release "
     f"lib.json sha256:{LIB_SHA} | rows none\n\n### Internal\n\nNo prior art found.\n",
     "asserts no prior art"),
    ("# AD-099\n\n## Prior art\n\n### External\n\n- web receipt: url https://x.org | retrieved "
     "2026-10-09\n\n### Internal\n\n- internal receipt: query \"q\" | repo sib@{sha} | hits none\n",
     "only web receipts"),
    ("# AD-099\n\n## Prior art\n\n### External\n\n- library receipt: query q | rows none\n\n"
     "### Internal\n\n- internal receipt: query \"q\" | repo sib@{sha} | hits none\n", "malformed"),
    ("# AD-099\n\n## Prior art\n\n### External\n\n- library receipt: query \"q\" | release "
     f"lib.json sha256:{LIB_SHA} | rows none\n\n### Internal\n\n- internal receipt: query \"q\" | "
     "repo sib@{short} | hits none\n", "malformed"),
])
def test_section_rules_refuse(proj, body, needle):
    s = _settings(proj)
    body = body.replace("{sha}", proj["sha"]).replace("{short}", proj["sha"][:12])
    v = pa.verify_note(_note(proj, "AD-099_x.md", body), s, library=StubLibrary())
    assert v.verdict == "fail"
    assert any(needle in p for p in v.problems), v.problems


def test_no_prior_art_with_the_receipt_of_the_empty_query_passes(proj):
    s = _settings(proj)
    body = (f"# AD-099\n\n## Prior art\n\n### External\n\n- library receipt: query \"q\" | "
            f"release lib.json sha256:{LIB_SHA} | rows none\n\n### Internal\n\nNo internal "
            f"precedent:\n\n- internal receipt: query \"zzqx nothing\" | repo sib@{proj['sha']} "
            f"| hits none\n")
    v = pa.verify_note(_note(proj, "AD-099_x.md", body), s, library=StubLibrary())
    assert v.verdict == "pass", v.problems


def test_an_addendum_completes_a_notes_section(proj):
    s = _settings(proj)
    note = _note(proj, "AD-099_x.md", "# AD-099\n\n## Prior art\n\n### External\n\n"
                 f'- library receipt: query "q" | release lib.json sha256:{LIB_SHA} | rows none\n'
                 "\n### Internal\n\nSearched by reading.\n")
    assert pa.verify_note(note, s, library=StubLibrary()).verdict == "fail"
    _note(proj, "AD-099_ADDENDUM_01_receipts.md", "# addendum\n\n## Prior art\n\n### Internal\n\n"
          f'- internal receipt: query "unit of extraction" | repo sib@{proj["sha"]} | hits '
          "docs/design/DN-001_unit.md:5\n")
    v = pa.verify_note(note, s, library=StubLibrary())
    assert v.verdict == "pass", v.problems
    assert [a["path"] for a in v.addenda] == ["docs/design/AD-099_ADDENDUM_01_receipts.md"]


# --------------------------------------------------------------------------------- the gate

def _record(proj, note, lib=None):
    s = _settings(proj)
    v = pa.verify_note(note, s, library=lib or StubLibrary())
    pa.record_verdict(v, proj["dir"], proj["config"])
    return v


def _task(proj, governing: str) -> Path:
    p = proj["dir"] / "cc_tasks" / "t.md"
    p.parent.mkdir(exist_ok=True)
    p.write_text(f"# T\n\n**Governing:** {governing}\n**Model:** primary\n\n## Work\n")
    return p


def test_commit_gate_refuses_a_note_without_a_passing_verdict(proj):
    from seldon.commands.verify import check_prior_art
    note = _note(proj, "AD-099_x.md", "# AD-099\n\nNo section.\n")
    r = check_prior_art(proj["dir"], proj["config"])
    assert r.symbol == "fail" and r.fixable
    assert any("AD-099_x.md" in d and "AD-036-R4" in d for d in r.details)
    _record(proj, note)          # a verdict now exists, and it is fail
    r = check_prior_art(proj["dir"], proj["config"])
    assert r.symbol == "fail" and not r.fixable
    assert any("no `## Prior art` section" in d for d in r.details)


def test_commit_gate_passes_a_verified_note_and_the_baseline(proj):
    from seldon.commands.verify import check_prior_art
    note = _note(proj, "AD-099_x.md", _good_body(proj))
    assert _record(proj, note).verdict == "pass"
    r = check_prior_art(proj["dir"], proj["config"])
    assert r.symbol == "pass", r.details          # OLD.md is baseline and never checked
    ledger = proj["dir"] / "governed" / "ledger" / "events.jsonl"
    events = [json.loads(x) for x in ledger.read_text().splitlines()]
    assert events[-1]["kind"] == "provenance" and events[-1]["type"] == pa.VERDICT_EVENT
    assert events[-1]["payload"]["sha256"] == pa._sha(note.read_bytes())


def test_editing_a_verified_note_needs_a_new_verdict(proj):
    from seldon.commands.verify import check_prior_art
    note = _note(proj, "AD-099_x.md", _good_body(proj))
    _record(proj, note)
    note.write_text(note.read_text() + "\nedited\n")
    assert check_prior_art(proj["dir"], proj["config"]).symbol == "fail"


def test_registration_gate_refuses_a_task_governed_by_an_unverified_note(proj):
    _note(proj, "AD-099_x.md", "# AD-099\n\nNo section.\n")
    refusal = pa.registration_refusal(_task(proj, "`docs/design/AD-099_x.md`"), proj["dir"],
                                      proj["config"])
    assert refusal and refusal.startswith("AD-036-R4") and "AD-099_x.md" in refusal
    # By identifier in the Governing block too.
    assert pa.registration_refusal(_task(proj, "AD-099 R1"), proj["dir"], proj["config"])


def test_registration_gate_passes_a_verified_or_baseline_note(proj):
    note = _note(proj, "AD-099_x.md", _good_body(proj))
    _record(proj, note)
    assert pa.registration_refusal(_task(proj, "docs/design/AD-099_x.md"), proj["dir"],
                                   proj["config"]) is None
    assert pa.registration_refusal(_task(proj, "docs/design/OLD.md"), proj["dir"],
                                   proj["config"]) is None


def test_cc_register_refuses_before_creating_anything(proj, monkeypatch):
    """The register code path raises the AD-036 refusal before it touches the graph."""
    from seldon.commands import cc
    _note(proj, "AD-099_x.md", "# AD-099\n\nNo section.\n")
    task = _task(proj, "docs/design/AD-099_x.md")
    _git(proj["dir"], "add", "-A")
    _git(proj["dir"], "commit", "-qm", "task")
    monkeypatch.setattr(cc, "_find_existing", lambda *a, **k: pytest.fail("graph was touched"))
    with pytest.raises(ValueError, match="AD-036-R4"):
        cc.register_task_file(project_dir=proj["dir"], config=proj["config"], driver=None,
                              database="x", domain_config=None, session_id=None, task_path=task,
                              actor="cc")


@pytest.mark.parametrize("gate", ["commit", "registration"])
def test_each_gate_removed_lets_the_planted_note_through(proj, monkeypatch, gate):
    """Methodology section 7.9: switch the gate off and the same planted note is not refused, so
    the refusal tests above depend on the gate and not on something incidental."""
    from seldon.commands.verify import check_prior_art
    _note(proj, "AD-099_x.md", "# AD-099\n\nNo section.\n")
    monkeypatch.setattr(pa, "gate_status", lambda *a, **k: [])
    if gate == "commit":
        assert check_prior_art(proj["dir"], proj["config"]).symbol == "pass"
    else:
        assert pa.registration_refusal(_task(proj, "docs/design/AD-099_x.md"), proj["dir"],
                                       proj["config"]) is None


def test_verification_logs_every_query(proj):
    s = _settings(proj)
    pa.verify_note(_note(proj, "AD-099_x.md", _good_body(proj)), s, library=StubLibrary())
    rows = [json.loads(x) for x in s.log.read_text().splitlines()]
    assert {r["arm"] for r in rows} == {"internal", "library"}
    assert all(r["purpose"] == "verify" and r["tool"] == pa.TOOL_VERSION for r in rows)
