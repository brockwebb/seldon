"""SEL-043 Part E(2) (AD-036-R29, R30): a rebuilt release the kit's reader refuses is `release_unavailable`, not a
traceback; and the rows of an older release come from the kit's own call when the kit has one.

squiddy's filing 9fb2e0b8: since SQ-139 `squiddy.index.Index` checks the index it is handed and raises
`IndexSchemaError` (`index_schema_mismatch: ...`) when it is opened, which `open_rebuilt` let through. And
`rebuild_release` names `iter_rows`' arguments itself, so it reads the corpus checkpoint under arm A's rule
(`q003-corpus/1`): 3 of 2,261 units differ from what the library's releases served. No row read changes until the kit
exposes the call (`squiddy.index.release_rows`); the known limit is recorded beside AD-036-R19.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from seldon.core import prior_art as pa


def test_a_rebuilt_index_the_kits_reader_refuses_is_release_unavailable(tmp_path):
    """The real reader on an index built with arm A's columns (no `text_sha256`), as `build_db` built it before
    SQ-139: it refuses when opened, and seldon answers `release_unavailable` by name."""
    import sqlite3
    from squiddy import index as ix
    if not hasattr(ix, "IndexSchemaError"):
        pytest.skip("the installed kit predates SQ-139's reader check")
    db = tmp_path / "corpus.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE rows (" + ", ".join(c for c in ix.INDEX_ROW_COLUMNS if c != "text_sha256") + ")")
    con.commit()
    con.close()
    info = {"dense_dir": str(tmp_path), "shards": [], "cfg": {"encoder": {"dimension": 4}}, "db": str(db),
            "release_sha256": "ab" * 32, "commit": "c0ffee", "rows": 0}
    with pytest.raises(pa.PriorArtError) as exc:
        pa.open_rebuilt(info, None)
    msg = str(exc.value)
    assert msg.startswith(pa.RELEASE_UNAVAILABLE) and "index_schema_mismatch" in msg and "abababababab" in msg


def test_any_other_error_of_the_reader_is_not_swallowed(monkeypatch, tmp_path):
    from squiddy import index as ix
    monkeypatch.setattr(ix, "Index", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk on fire")))
    info = {"dense_dir": str(tmp_path), "shards": [], "cfg": {"encoder": {"dimension": 4}}, "db": str(tmp_path / "x"),
            "release_sha256": "ab" * 32, "commit": "c0ffee", "rows": 0}
    with pytest.raises(RuntimeError, match="disk on fire"):
        pa.open_rebuilt(info, None)


def _kit(**extra):
    calls = []

    def iter_rows(path, manifest, render, stage, parsed):
        calls.append(("iter_rows", Path(path).name, parsed))
        return iter([{"row_id": "u1#0"}])
    kit = SimpleNamespace(iter_rows=iter_rows, meta_renderer=lambda cfg: "render", **extra)
    return kit, calls


def test_without_the_kits_call_the_rows_are_read_as_before():
    kit, calls = _kit()
    rows = pa.checkpoint_rows(kit, graph="g", cfg={}, wd=Path("/w"), manifest=[], stage="s", commit="c")
    assert rows == [{"row_id": "u1#0"}] and calls == [("iter_rows", pa.CORPUS_ROWS.split("/")[-1], None)]


def test_with_the_kits_call_the_release_is_read_under_the_rule_it_was_cut_under():
    seen = {}

    def release_rows(graph, manifest, *, commit):
        seen.update(graph=graph, commit=commit)
        return [{"row_id": "u1#0", "text_sha256": "f" * 64}]
    kit, calls = _kit(release_rows=release_rows)
    rows = pa.checkpoint_rows(kit, graph="g", cfg={}, wd=Path("/w"), manifest=[], stage="s", commit="c")
    assert rows[0]["text_sha256"] and seen == {"graph": "g", "commit": "c"} and calls == []


def test_the_kits_refusal_through_its_call_is_still_a_refusal():
    def release_rows(graph, manifest, *, commit):
        raise SystemExit("unit u9 has no rows under sq028r-corpus/2:pages")
    kit, _ = _kit(release_rows=release_rows)
    with pytest.raises(SystemExit):
        pa.checkpoint_rows(kit, graph="g", cfg={}, wd=Path("/w"), manifest=[], stage="s", commit="c")
