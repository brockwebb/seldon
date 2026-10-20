"""DISP-003R Part B step 1 (AD-036 ADDENDUM 07, AD-036-R14): a receipt that cites its own note is a self-citation.

AD-036 ADDENDUM 03 line 106 cites the base note's own line 95. Since SQ-012 the internal arm leaves the note under
verification (base and addenda) out of its own search, so that receipt read `id_not_returned` and AD-036 failed on
it forever; addenda are immutable (AD-036-R7), so it could never be corrected. A self-citation is now reported
`self_citation` and neither passes nor fails the note. Built on `tests/test_prior_art.py`'s synthetic corpus, with
the project itself added as an internal root (seldon's own `{name: seldon, path: .}`).
"""
from __future__ import annotations

import pytest

from seldon.core import prior_art as pa
from tests.test_prior_art import LIB_SHA, StubLibrary, _git, _good_body, _note, proj  # noqa: F401 (fixture)


@pytest.fixture
def selfproj(proj):  # noqa: F811
    """`proj` with the project itself an internal root, and a committed note AD-099 that passes on its own."""
    proj["config"]["prior_art"]["internal_roots"].append({"name": "self", "path": str(proj["dir"])})
    _note(proj, "AD-099_a_note.md", _good_body(proj))
    _git(proj["dir"], "add", "-A")
    _git(proj["dir"], "commit", "-q", "-m", "note")
    proj["self_sha"] = _git(proj["dir"], "rev-parse", "HEAD")
    return proj


def _addendum(proj, hits: str) -> None:
    _note(proj, "AD-099_ADDENDUM_01_more.md", "# AD-099 ADDENDUM 01\n\n## Prior art\n\n### Internal\n\n"
          f'- internal receipt: query "unit of extraction" | repo self@{proj["self_sha"]} | hits {hits}\n')


def _verify(proj):
    s = pa.settings(proj["dir"], proj["config"])
    return pa.verify_note(proj["dir"] / "docs" / "design" / "AD-099_a_note.md", s, library=StubLibrary())


def test_the_base_note_passes_alone(selfproj):
    v = _verify(selfproj)
    assert v.verdict == "pass", v.problems


def test_a_note_whose_only_failing_receipt_is_a_self_citation_passes_with_one_self_citation_line(selfproj):
    _addendum(selfproj, "docs/design/AD-099_a_note.md:5")
    v = _verify(selfproj)
    assert v.verdict == "pass", v.problems
    selfs = [r for r in v.receipts if r.status == pa.SELF_CITATION]
    assert len(selfs) == 1
    assert selfs[0].source == "docs/design/AD-099_ADDENDUM_01_more.md"
    assert "AD-099_a_note.md:5" in selfs[0].detail
    assert v.as_payload()["self_citations"] == ["docs/design/AD-099_ADDENDUM_01_more.md:7"]


def test_a_citation_of_another_addendum_of_the_same_note_is_a_self_citation_too(selfproj):
    _addendum(selfproj, "docs/design/AD-099_ADDENDUM_02_other.md:1")
    _note(selfproj, "AD-099_ADDENDUM_02_other.md", "# AD-099 ADDENDUM 02\n")
    v = _verify(selfproj)
    assert v.verdict == "pass", v.problems
    assert [r.status for r in v.receipts if r.source.endswith("ADDENDUM_01_more.md")] == [pa.SELF_CITATION]


def test_negative_control_a_missing_hit_outside_the_note_still_fails(selfproj):
    """AD-038-R6: the new status must not launder a real miss. A receipt citing a file outside the note that the
    search does not return is still `id_not_returned`, even beside a self-citation in the same receipt."""
    _addendum(selfproj, "docs/design/AD-099_a_note.md:5, docs/design/NOT_THERE.md:1")
    v = _verify(selfproj)
    assert v.verdict == "fail"
    (r,) = [r for r in v.receipts if r.source.endswith("ADDENDUM_01_more.md")]
    assert r.status == pa.ID_NOT_RETURNED and "NOT_THERE.md:1" in r.detail


def test_a_subsection_carried_only_by_self_citations_is_empty(selfproj):
    """A self-citation is not evidence of prior art, so it cannot be the only thing in a subsection."""
    body = (f"# AD-099 a note\n\n## Prior art\n\n### External\n\n"
            f'- library receipt: query "unit of extraction" | release lib.json sha256:{LIB_SHA} '
            f"| rows lesson:x#p1:1:0-9\n\n### Internal\n\n"
            f'- internal receipt: query "unit of extraction" | repo self@{selfproj["self_sha"]} '
            f"| hits docs/design/AD-099_a_note.md:1\n")
    _note(selfproj, "AD-099_a_note.md", body)
    v = _verify(selfproj)
    assert v.verdict == "fail"
    assert any("only self-citations" in p for p in v.problems), v.problems
