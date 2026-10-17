"""DESK-002 Part C: the register takes `source.sha256` from the file, and checks `source.text` (Issue 5bfc2788).

The register's convention is the digest of the whole file at `source.path` (squiddy seq 972 to 975 carry one digest
each for different spans of DN-046). squiddy R-206 (seq 984) was written with a 12-hex prefix of a hash over a
transcription, because `seldon_decision_accept` stored whatever it was given; and `decision amend` refused every
change to `source`, so the wrong value could not be corrected. Each test below fails on the code before Part C.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from seldon.core import decisions as dr
from tests.test_decision_register import DATE, _repo, _u

NOTE = "docs/design/2026-09-01_DN-001_first.md"
#: The ruling's span in the fixture note (`_repo`): its heading and its body, lines 3 to 5.
SPAN = (3, 5)


def _span(root: Path) -> str:
    lines = (root / NOTE).read_text(encoding="utf-8").splitlines()
    return "\n".join(lines[SPAN[0] - 1:SPAN[1]])


def _record(root: Path, local: str = "R-1", **source) -> dict:
    text = _span(root)
    src = {"path": NOTE, "lines": list(SPAN), "text": text}
    src.update(source)
    return {"id": f"squiddy:{local}", "kind": "decision", "statement": "The kit never stores content.",
            "source": {k: v for k, v in src.items() if v is not None}, "scope": ["squiddy"],
            "rationale": {"path": NOTE, "anchor": local}, "review_only": "none"}


def _files(root: Path) -> list[Path]:
    return dr.Register("squiddy", root).files()


def test_accept_with_a_wrong_digest_refuses_naming_both_values(tmp_path):
    root = _repo(tmp_path, "squiddy")
    true = dr.sha256_file(root / NOTE)
    with pytest.raises(dr.RegisterError) as exc:
        dr.create(_u(root), "accept", _record(root, sha256="6b2045ebee75"), date=DATE, decided_by="desktop")
    assert "6b2045ebee75" in str(exc.value) and true in str(exc.value)
    assert _files(root) == []


@pytest.mark.parametrize("event", ["accept", "propose"])
def test_accept_or_propose_with_no_digest_computes_it_from_the_file(tmp_path, event):
    root = _repo(tmp_path, "squiddy")
    rec = _record(root)
    if event == "propose":
        rec["waits_on"] = "a named measurement"
    [path] = dr.create(_u(root), event, rec, date=DATE, decided_by="desktop")
    assert yaml.safe_load(path.read_text())["source"]["sha256"] == dr.sha256_file(root / NOTE)
    assert dr.Register("squiddy", root).verify() == []


def test_accept_with_the_true_digest_passes(tmp_path):
    root = _repo(tmp_path, "squiddy")
    [path] = dr.create(_u(root), "accept", _record(root, sha256=dr.sha256_file(root / NOTE)),
                       date=DATE, decided_by="desktop")
    assert path.is_file()


def test_accept_whose_text_is_not_the_file_at_its_lines_refuses(tmp_path):
    root = _repo(tmp_path, "squiddy")
    with pytest.raises(dr.RegisterError, match="source.text"):
        dr.create(_u(root), "accept", _record(root, text="The kit never stores content (a transcription)."),
                  date=DATE, decided_by="desktop")
    assert _files(root) == []


def test_accept_whose_source_names_no_file_refuses(tmp_path):
    root = _repo(tmp_path, "squiddy")
    with pytest.raises(dr.RegisterError, match="resolves to no file"):
        dr.create(_u(root), "accept", _record(root, path="docs/design/missing.md"), date=DATE, decided_by="desktop")


def _plant_r206(root: Path) -> None:
    """A record as the old write path left R-206: a 12-hex digest, the verbatim span (written past `create`)."""
    reg = dr.Register("squiddy", root)
    reg.path.mkdir(parents=True, exist_ok=True)
    data = dict(_record(root, local="R-206", sha256="6b2045ebee75"), event="accept", status="accepted",
                date=DATE, decided_by="desktop", operator_stated=False)
    reg.append(data)


def test_amend_to_the_files_true_digest_succeeds(tmp_path):
    root = _repo(tmp_path, "squiddy")
    _plant_r206(root)
    true = dr.sha256_file(root / NOTE)
    dr.amend(_u(root), "squiddy:R-206", date=DATE, decided_by="desktop", reason="5bfc2788",
             changes={"source": {"sha256": true}})
    rec = _u(root).get("squiddy:R-206")
    assert rec.get("source")["sha256"] == true
    assert rec.get("source")["text"] == _span(root) and rec.get("source")["lines"] == list(SPAN)
    assert dr.Register("squiddy", root).verify() == []


@pytest.mark.parametrize("bad", ["0" * 64, "6b2045ebee75", ""])
def test_amend_to_any_other_digest_refuses(tmp_path, bad):
    root = _repo(tmp_path, "squiddy")
    _plant_r206(root)
    before = _files(root)
    with pytest.raises(dr.RegisterError, match="sha256"):
        dr.amend(_u(root), "squiddy:R-206", date=DATE, decided_by="desktop", reason="5bfc2788",
                 changes={"source": {"sha256": bad}})
    assert _files(root) == before


@pytest.mark.parametrize("field,value", [("path", "docs/design/other.md"), ("lines", [3, 4]),
                                         ("text", "A different ruling.")])
def test_amend_of_any_other_source_field_still_refuses(tmp_path, field, value):
    root = _repo(tmp_path, "squiddy")
    _plant_r206(root)
    (root / "docs/design/other.md").write_text("A different ruling.\n", encoding="utf-8")
    with pytest.raises(dr.RegisterError, match="fixed at creation"):
        dr.amend(_u(root), "squiddy:R-206", date=DATE, decided_by="desktop", reason="5bfc2788",
                 changes={"source": {field: value, "sha256": dr.sha256_file(root / NOTE)}})


def test_amend_of_the_digest_refuses_when_the_text_no_longer_matches_the_file(tmp_path):
    root = _repo(tmp_path, "squiddy")
    _plant_r206(root)
    note = root / NOTE
    note.write_text(note.read_text(encoding="utf-8").replace("never stores", "sometimes stores"), encoding="utf-8")
    with pytest.raises(dr.RegisterError, match="source.text"):
        dr.amend(_u(root), "squiddy:R-206", date=DATE, decided_by="desktop", reason="5bfc2788",
                 changes={"source": {"sha256": dr.sha256_file(note)}})
