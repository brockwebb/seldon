"""SEL-064 (squiddy SQ-156, DN-063 ADDENDUM 02 R-318; seldon's filing c923eb5a): the library arm says whether the
release it searched is sealed.

squiddy builds the served index at release stage 15, before the gates that read it and before the seal, so a
search in that window, or after a later gate killed the release, answers from a release no register holds. squiddy
now reports that on every answer as `index.release_sealed` (true, false, or null for a ledger that seals nothing).
What is pinned here: `Library.search` carries the value through; the CLI flags a graph whose release is not sealed
and warns on stderr; a receipt is still printed and its line is unchanged (the decision in the SEL-064 RESULT: not
refused, because the receipt names its export by sha256 and verification rebuilds that export, AD-036-R19 resolves
it when it cannot, and squiddy R-306/R-307 keep a gate-killed release's export on disk).
"""
from __future__ import annotations

import pytest
from click.testing import CliRunner

from seldon.commands import prior_art as cmd
from seldon.core import prior_art as pa
from tests.test_prior_art import LIB_SHA, proj  # noqa: F401  (proj is a fixture)


class _Verbs:
    """squiddy's `Verbs.search` answer, as SQ-156 shapes its `index`."""

    def __init__(self, index: dict):
        self.index = index

    def search(self, q, k=None):
        return {"question": q, "hits": [{"rank": 1, "doc_id": "d1",
                                         "rows": [{"text": "t", "receipt": {"row_id": "d1#meta"}}]}],
                "index": self.index}


def _lib(proj, monkeypatch, index: dict) -> pa.Library:
    s = pa.settings(proj["dir"], proj["config"])
    lib = pa.Library(s, proj["tmp"] / "library", "library")
    monkeypatch.setattr(lib, "verbs", lambda: _Verbs(index))
    return lib


@pytest.mark.parametrize("sealed", [True, False, None])
def test_library_search_carries_release_sealed(proj, monkeypatch, sealed):
    idx = {"release": {"export": "/x/exports/lib_20261128.json", "sha256": LIB_SHA}, "release_sealed": sealed}
    res = _lib(proj, monkeypatch, idx).search("q")
    assert res["release_sealed"] is sealed
    assert (res["release"], res["sha256"], res["rows"]) == ("lib_20261128.json", LIB_SHA, ["d1#meta"])


def test_a_squiddy_that_does_not_report_it_reads_as_none(proj, monkeypatch):
    """A squiddy before SQ-156 has no `release_sealed`; the arm says nothing it was not told."""
    idx = {"release": {"export": "/x/exports/lib.json", "sha256": LIB_SHA}}
    assert _lib(proj, monkeypatch, idx).search("q")["release_sealed"] is None


def _run_cli(monkeypatch, sealed):
    out = {"arm": "library", "query": "q", "receipts": ["- library receipt: RECEIPT-LINE"], "release": "lib.json",
           "sha256": LIB_SHA, "total_hits": 1, "top": [], "seconds": 0.0, "project": ".", "notes": [],
           "commit": {"committed": True},
           "graphs": [{"graph": "library", "origin": "own", "release": "lib.json", "sha256": LIB_SHA,
                       "release_sealed": sealed, "total_hits": 1, "receipt": "- library receipt: RECEIPT-LINE",
                       "top": []}]}
    monkeypatch.setattr(cmd, "run_search", lambda *a, **k: out)
    return CliRunner(mix_stderr=False).invoke(cmd.search_command, ["q", "--library"])


def test_cli_flags_an_unsealed_release_and_still_prints_the_receipt(monkeypatch):
    r = _run_cli(monkeypatch, False)
    assert r.exit_code == 0, r.output
    assert "NOT SEALED" in r.stdout
    assert "release_sealed false" in r.stderr and "library" in r.stderr
    assert "- library receipt: RECEIPT-LINE" in r.stdout


@pytest.mark.parametrize("sealed", [True, None])
def test_cli_is_quiet_for_a_sealed_release_or_a_ledger_that_seals_nothing(monkeypatch, sealed):
    r = _run_cli(monkeypatch, sealed)
    assert r.exit_code == 0, r.output
    assert "NOT SEALED" not in r.stdout and "release_sealed" not in r.stderr
