"""Tests for AD-024 observability emission from seldon verify."""
import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

from seldon.commands.verify import CheckResult, _emit_verify_metrics


def test_emit_skipped_when_substrate_missing(tmp_path, monkeypatch):
    """If ~/.seldon-observability/ doesn't exist, emission is a no-op."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    results = [CheckResult(name="File hashes", symbol="pass", summary="ok")]
    # Should not raise
    _emit_verify_metrics("test-project", results, strict=False)


def test_emit_writes_one_row_per_check_plus_summary(tmp_path, monkeypatch):
    """Given N checks, emit N + 1 rows (N per-check + 1 summary)."""
    fake_home = tmp_path / "home"
    obs_dir = fake_home / ".seldon-observability"
    obs_dir.mkdir(parents=True)
    db_path = obs_dir / "metrics.db"

    # Initialize schema (matches observability_collect.py)
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE metrics (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          timestamp TEXT NOT NULL,
          metric_name TEXT NOT NULL,
          metric_value REAL NOT NULL,
          scope TEXT NOT NULL,
          dimensions TEXT,
          collected_by TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()

    monkeypatch.setattr(Path, "home", lambda: fake_home)

    results = [
        CheckResult(name="File hashes", symbol="pass", summary="ok"),
        CheckResult(name="Ontology", symbol="fail", summary="stale"),
        CheckResult(name="Stale artifacts", symbol="warn", summary="2 stale"),
    ]
    _emit_verify_metrics("test-project", results, strict=False)

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT metric_name, metric_value, dimensions FROM metrics ORDER BY id"
    ).fetchall()
    conn.close()

    # 3 per-check rows + 1 summary row
    assert len(rows) == 4

    per_check = [r for r in rows if r[0] == "seldon.verify.check.status"]
    assert len(per_check) == 3
    # Values: pass=0, fail=2, warn=1
    assert [r[1] for r in per_check] == [0.0, 2.0, 1.0]

    summary = [r for r in rows if r[0] == "seldon.verify.run.tier_a_fail_count"]
    assert len(summary) == 1
    # Tier A fails: only "Ontology" is Tier A
    assert summary[0][1] == 1.0


def test_emit_silent_on_db_error(tmp_path, monkeypatch):
    """If the DB is locked or corrupted, emit swallows the exception."""
    fake_home = tmp_path / "home"
    obs_dir = fake_home / ".seldon-observability"
    obs_dir.mkdir(parents=True)
    # Create a file that is NOT a valid SQLite DB
    (obs_dir / "metrics.db").write_text("not a database")

    monkeypatch.setattr(Path, "home", lambda: fake_home)

    results = [CheckResult(name="File hashes", symbol="pass", summary="ok")]
    # Should not raise
    _emit_verify_metrics("test-project", results, strict=False)
