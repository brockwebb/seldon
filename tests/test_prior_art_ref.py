"""SQ-010 Part 0 (AD-036 ADDENDUM 03): a project's `prior_art:` block may be a reference to the
one definition in seldon's seldon.yaml, carrying only its own baseline; and a project with no
governed graph records its verdicts in the fallback verdict ledger.

Every directory here is a scratch directory under tmp_path laid out as siblings, the way the
operator's repositories sit under ~/GitHub: `seldon/` (the definer), `proj/` (a referencing
project with no governed graph) and `sib/` (a corpus root). No test reads a real repository.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from seldon.core import hooks as H
from seldon.core import prior_art as pa

LIB_SHA = "b" * 64


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    # GIT_* variables from an enclosing hook would point these commands at another repository.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run(["git", "-C", str(root), *args], check=check, capture_output=True,
                          text=True, env=env)


def _init(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")


class StubLibrary:
    def search(self, query, k=None):
        return {"query": query, "release": "lib.json", "sha256": LIB_SHA,
                "rows": ["lesson:x#p1:1:0-9"], "hits": []}


#: The definer's block: every path in it is RELATIVE, so the tests can see which directory each
#: one resolved against.
DEFINITION = {
    "log": "state/q.jsonl",
    "internal_roots": [{"name": "seldon", "path": "."}, {"name": "sib", "path": "../sib"}],
    "internal": {"default_include": ["docs/design/**"], "suffixes": [".md"], "top_n": 20,
                 "max_file_bytes": 100000, "bm25": {"k1": 1.2, "b": 0.75}},
    "library": {"graph": "../nolib", "k": 20},
    "gate": {"design_dir": "docs/design", "baseline": "docs/design/AD-036_baseline.txt",
             "exempt_globs": ["*_ADDENDUM_*.md", "*_erratum_*.md"],
             "verdict_ledger_without_governed": "state/prior_art_verdicts.jsonl"},
}
REF = {"ref": "../seldon/seldon.yaml#prior_art",
       "gate": {"baseline": "docs/design/AD-036_baseline.txt"}}


@pytest.fixture
def machine(tmp_path):
    """seldon/ (the definition), sib/ (a git corpus root) and proj/ (refers, no governed graph)."""
    definer = tmp_path / "seldon"
    definer.mkdir()
    (definer / "seldon.yaml").write_text(yaml.safe_dump({"prior_art": DEFINITION}))
    sib = tmp_path / "sib"
    _init(sib)
    (sib / "docs" / "design").mkdir(parents=True)
    (sib / "docs" / "design" / "DN-001_unit.md").write_text(
        "# DN-001\n\nIntro line.\n\nThe unit of extraction is the\nparagraph, measured.\n")
    _git(sib, "add", "-A")
    _git(sib, "commit", "-qm", "init")
    proj = tmp_path / "proj"
    _init(proj)
    (proj / "docs" / "design").mkdir(parents=True)
    (proj / "docs" / "design" / "AD-036_baseline.txt").write_text("docs/design/OLD.md\n")
    (proj / "docs" / "design" / "OLD.md").write_text("# an old note, no prior art\n")
    config = {"project": {"name": "proj"}, "prior_art": dict(REF)}
    (proj / "seldon.yaml").write_text(yaml.safe_dump(config))
    return {"tmp": tmp_path, "definer": definer, "sib": sib, "proj": proj, "config": config,
            "sib_sha": _git(sib, "rev-parse", "HEAD").stdout.strip()}


def _good(m) -> str:
    return (f"# AD-099 a note\n\n## 2. Prior art\n\n### External\n\n"
            f'- library receipt: query "unit of extraction" | release lib.json sha256:{LIB_SHA} '
            f"| rows lesson:x#p1:1:0-9\n\n### Internal\n\n"
            f'- internal receipt: query "unit of extraction" | repo sib@{m["sib_sha"]} '
            f"| hits docs/design/DN-001_unit.md:5\n\n## 3. Decisions\n")


# ------------------------------------------------------------------------- the reference

def test_part0_2_a_repo_without_its_own_internal_roots_resolves_seldons(machine):
    """SQ-010 Part 0 step 2: the referencing project names no internal_roots, and gets the
    definer's, resolved against the definer's directory."""
    assert "internal_roots" not in machine["config"]["prior_art"]
    s = pa.settings(machine["proj"], machine["config"])
    assert {r.name: r.path for r in s.roots} == {"seldon": machine["definer"].resolve(),
                                                 "sib": machine["sib"].resolve()}
    assert s.defined_in == (machine["definer"] / "seldon.yaml").resolve()
    # ...and the internal arm searches them: the sibling's paragraph is found from proj.
    res = pa.Internal(s).search("unit of extraction")
    assert any(h.root == "sib" and h.path == "docs/design/DN-001_unit.md" for h in res["hits"])


def test_corpus_paths_resolve_from_the_definer_state_paths_from_the_referencer(machine):
    s = pa.settings(machine["proj"], machine["config"])
    proj = machine["proj"].resolve()
    assert s.library_graph == (machine["tmp"] / "nolib").resolve()          # definer's ../nolib
    assert s.log == proj / "state" / "q.jsonl"
    assert s.baseline == proj / "docs" / "design" / "AD-036_baseline.txt"
    assert s.verdict_ledger_without_governed == proj / "state" / "prior_art_verdicts.jsonl"
    assert s.design_dir == "docs/design" and s.project_dir == proj


def test_a_block_the_project_defines_itself_resolves_everything_from_itself(machine):
    own = yaml.safe_load((machine["definer"] / "seldon.yaml").read_text())
    s = pa.settings(machine["definer"], own)
    assert s.defined_in is None
    assert {r.name: r.path for r in s.roots}["sib"] == machine["sib"].resolve()
    assert s.log == machine["definer"].resolve() / "state" / "q.jsonl"


@pytest.mark.parametrize("extra,named", [
    ({"log": "elsewhere.jsonl"}, "'log'"),
    ({"internal_roots": [{"name": "x", "path": "."}]}, "'internal_roots'"),
    ({"gate": {"baseline": "b.txt", "exempt_globs": []}}, "'gate.exempt_globs'"),
])
def test_a_referencing_block_that_sets_anything_but_its_baseline_is_refused(machine, extra,
                                                                           named):
    block = {**REF, **extra}
    with pytest.raises(pa.PriorArtError) as exc:
        pa.settings(machine["proj"], {"prior_art": block})
    msg = str(exc.value)
    assert named in msg and "One definition, never a copy" in msg
    assert str((machine["definer"] / "seldon.yaml").resolve()) in msg


def test_a_referencing_block_without_its_own_baseline_is_refused(machine):
    with pytest.raises(pa.PriorArtError, match="sets no `gate.baseline`"):
        pa.settings(machine["proj"], {"prior_art": {"ref": REF["ref"]}})


@pytest.mark.parametrize("ref,why", [
    ("../seldon/seldon.yaml", "is not a reference"),
    ("../nowhere/seldon.yaml#prior_art", "which does not exist"),
    ("../seldon/seldon.yaml#prior_art.nothing", "has no 'prior_art.nothing'"),
    ("../seldon/seldon.yaml#prior_art.log", "not a prior_art block"),
])
def test_a_bad_ref_is_refused_by_name(machine, ref, why):
    with pytest.raises(pa.PriorArtError, match=why):
        pa.settings(machine["proj"], {"prior_art": {**REF, "ref": ref}})


def test_a_ref_to_a_ref_is_refused(machine):
    middle = machine["tmp"] / "middle"
    middle.mkdir()
    (middle / "seldon.yaml").write_text(yaml.safe_dump({"prior_art": REF}))
    with pytest.raises(pa.PriorArtError, match="never a chain"):
        pa.settings(machine["proj"],
                    {"prior_art": {**REF, "ref": "../middle/seldon.yaml#prior_art"}})


def test_a_tilde_in_the_ref_is_expanded(machine, monkeypatch):
    monkeypatch.setenv("HOME", str(machine["tmp"]))
    s = pa.settings(machine["proj"], {"prior_art": {**REF, "ref": "~/seldon/seldon.yaml#prior_art"}})
    assert s.defined_in == (machine["definer"] / "seldon.yaml").resolve()


# --------------------------------------------------------------------- the fallback ledger

def test_a_project_with_no_governed_graph_records_and_reads_its_verdict_in_the_fallback(machine):
    proj, config = machine["proj"], machine["config"]
    assert pa.governed_ledger(proj, config) is None
    fallback = proj.resolve() / "state" / "prior_art_verdicts.jsonl"
    assert pa.verdict_ledger(proj, config) == fallback
    note = proj / "docs" / "design" / "AD-099_x.md"
    note.write_text(_good(machine))
    s = pa.settings(proj, config)
    v = pa.verify_note(note, s, library=StubLibrary())
    assert v.verdict == "pass", v.as_payload()
    pa.record_verdict(v, proj, config)
    assert fallback.is_file()
    rows = pa.gate_status(proj, config)
    assert rows == [{"note": "docs/design/AD-099_x.md", "sha256": rows[0]["sha256"], "ok": True,
                     "why": "pass"}]


def test_a_project_with_a_governed_graph_still_records_in_the_governed_ledger(machine):
    proj, config = machine["proj"], machine["config"]
    (proj / "governed" / "ledger").mkdir(parents=True)
    assert pa.verdict_ledger(proj, config) == pa.governed_ledger(proj, config)


# ---------------------------------------------------------------------------------- the hook

@pytest.fixture
def hooked(machine):
    proj = machine["proj"]
    (proj / "README.md").write_text("x\n")
    _git(proj, "add", "-A")
    _git(proj, "commit", "-qm", "init")
    assert H.install(proj, python=sys.executable).wrote_hook
    _git(proj, "add", "-A")
    _git(proj, "commit", "-qm", "install the commit gate")
    return machine


def test_the_hook_in_a_referencing_repo_refuses_a_note_without_a_verdict(hooked):
    proj = hooked["proj"]
    (proj / "docs" / "design" / "AD-099_x.md").write_text("# AD-099\n\nNo prior art section.\n")
    _git(proj, "add", "docs/design/AD-099_x.md")
    r = _git(proj, "commit", "-m", "planted", check=False)
    assert r.returncode != 0
    assert "docs/design/AD-099_x.md" in r.stderr and "AD-036-R4" in r.stderr


def test_the_hook_in_a_referencing_repo_passes_a_note_with_its_staged_fallback_verdict(hooked):
    proj, config = hooked["proj"], hooked["config"]
    note = proj / "docs" / "design" / "AD-099_x.md"
    note.write_text(_good(hooked))
    v = pa.verify_note(note, pa.settings(proj, config), library=StubLibrary())
    pa.record_verdict(v, proj, config)
    _git(proj, "add", "docs/design/AD-099_x.md")
    r = _git(proj, "commit", "-m", "note", check=False)     # verdict not staged yet
    assert r.returncode != 0
    assert "stage the verdict ledger state/prior_art_verdicts.jsonl" in r.stderr
    _git(proj, "add", "state/prior_art_verdicts.jsonl")
    r = _git(proj, "commit", "-m", "note", check=False)
    assert r.returncode == 0, r.stderr


def test_a_gitignored_fallback_ledger_is_read_where_it_lies(hooked):
    """A ledger git can never commit is all there is: its working-tree verdict counts."""
    proj, config = hooked["proj"], hooked["config"]
    (proj / ".gitignore").write_text("state/\n")
    _git(proj, "add", ".gitignore")
    _git(proj, "commit", "-qm", "ignore state")
    note = proj / "docs" / "design" / "AD-099_x.md"
    note.write_text(_good(hooked))
    pa.record_verdict(pa.verify_note(note, pa.settings(proj, config), library=StubLibrary()),
                      proj, config)
    _git(proj, "add", "docs/design/AD-099_x.md")
    r = _git(proj, "commit", "-m", "note", check=False)
    assert r.returncode == 0, r.stderr
