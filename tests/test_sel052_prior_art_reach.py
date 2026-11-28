"""SEL-052 Part A: the prior-art search reads every registered repository, from the one list of them.

factory's 2026-11-26 filing, item 1: `prior_art.internal_roots` listed six of the registered repositories; factory,
hazbrief-mcp, aacps-ai-policy and critical-thinking-ai were never searched, so "requirements elicitation" found
nothing in factory, whose `docs/se/strs.md` holds 56 stakeholder needs. `internal_roots_from` takes the rest from
factory's `portfolio.repositories`, and `docs/se/**` puts the requirement projections in the corpus.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from seldon.core import prior_art as pa


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _repo(path: Path, files: dict) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "t@t")
    _git(path, "config", "user.name", "t")
    for rel, text in files.items():
        (path / rel).parent.mkdir(parents=True, exist_ok=True)
        (path / rel).write_text(text, encoding="utf-8")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "init")
    return path


def _config(ws: Path, roots_from: str | None) -> dict:
    block = {
        "log": "state/q.jsonl",
        "internal_roots": [{"name": "kit", "path": "."}],
        "internal": {"default_include": ["docs/design/**", "docs/se/**"], "suffixes": [".md"], "top_n": 20,
                     "max_file_bytes": 100000, "bm25": {"k1": 1.2, "b": 0.75}},
        "library": {"graph": str(ws / "nolib"), "k": 20},
        "gate": {"design_dir": "docs/design", "baseline": "docs/design/base.txt", "exempt_globs": [],
                 "verdict_ledger_without_governed": "state/v.jsonl"},
    }
    if roots_from is not None:
        block[pa.ROOTS_FROM_KEY] = roots_from
    return {"prior_art": block}


@pytest.fixture
def ws(tmp_path):
    _repo(tmp_path / "kit", {"docs/design/AD-001.md": "# kit\n\nNothing on elicitation here.\n"})
    _repo(tmp_path / "fac", {
        "docs/se/strs.md": "# StRS\n\n| SN-01 | requirements elicitation from the operator's statements |\n",
        "seldon.yaml": yaml.safe_dump({"portfolio": {"repositories": {
            "kit": "../kit", "fac": ".", "other-name-for-kit": "../kit", "gone": "../gone"}}}),
    })
    return tmp_path


def test_without_the_key_only_the_listed_roots_are_searched(ws):
    s = pa.settings(ws / "kit", _config(ws, None))
    assert [r.name for r in s.roots] == ["kit"]


def test_the_portfolio_adds_every_repository_it_lists_once(ws):
    s = pa.settings(ws / "kit", _config(ws, "../fac/seldon.yaml#portfolio.repositories"))
    by = {r.name: r for r in s.roots}
    # `kit` keeps its explicit row; a second name for the same path is not a second root; a listed repository not on
    # disk is a root (its receipt would fail loudly), never silently dropped.
    assert list(by) == ["kit", "fac", "gone"]
    assert by["fac"].path == (ws / "fac").resolve()
    assert by["fac"].include == ("docs/design/**", "docs/se/**")


def test_a_need_in_a_registered_repository_is_found_by_the_search(ws):
    s = pa.settings(ws / "kit", _config(ws, "../fac/seldon.yaml#portfolio.repositories"))
    s = s.__class__(**{**s.__dict__, "roots": tuple(r for r in s.roots if r.name != "gone")})
    res = pa.Internal(s).search("requirements elicitation")
    assert [(h.root, h.path) for h in res["hits"]] == [("fac", "docs/se/strs.md")]
    receipts = pa.Internal(s).receipts(res)
    assert any("repo fac@" in r and "docs/se/strs.md" in r for r in receipts), receipts


@pytest.mark.parametrize("ref, needle", [
    ("no-hash", "not a reference"),
    # A portfolio file not on this machine is no longer refused: SEL-063 (AD-036-R32 as amended by ADDENDUM 17) makes
    # it a noted, narrowed search (tests/test_sel063_part_b.py).
    ("../fac/seldon.yaml#portfolio.missing", "has no"),
    ("../fac/seldon.yaml#portfolio", "not a {name: path} map"),
])
def test_a_bad_reference_is_refused_with_its_reason(ws, ref, needle):
    with pytest.raises(pa.PriorArtError, match=needle.replace("{", r"\{").replace("}", r"\}")):
        pa.settings(ws / "kit", _config(ws, ref))


def test_seldons_own_block_reaches_every_registered_repository():
    """The live configuration: every repository factory registers is a root of seldon's search (and so of every
    consumer's, whose block is a reference to seldon's)."""
    kit = Path(__file__).resolve().parents[1]
    config = yaml.safe_load((kit / "seldon.yaml").read_text(encoding="utf-8"))
    factory = pa.corpus_anchor(kit) / ".." / "factory" / "seldon.yaml"
    if not factory.is_file():
        pytest.skip("factory is not checked out beside seldon on this machine")
    listed = yaml.safe_load(factory.read_text(encoding="utf-8"))["portfolio"]["repositories"]
    names = {r.name for r in pa.settings(kit, config).roots}
    assert set(listed) <= names, sorted(set(listed) - names)
