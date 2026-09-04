"""Handoff recency selection for `seldon go`.

Covers the defect fixed in the 2026-09-03 defect sweep (lane D1): the picker
sorted the whole filename descending, so for two handoffs written on the same
day the trailing slug — which carries no recency information — decided the
winner. Observed live in ai-readiness-kg/handoffs/ on 2026-09-02, where
`2026-09-02_sensor_layer_and_june_consolidation.md` (13:42) beat
`2026-09-02_post_burn_reconciliation_and_g1_prior_art.md` (17:46) because
"sensor" > "post_burn" alphabetically.

`handoffs/` is gitignored in every Seldon project, so every fixture here is
built in a tmp_path.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from seldon.commands.go import (
    _find_latest_handoff,
    _handoff_sort_key,
    _read_latest_handoff,
    assemble_go_context,
)


def _write_handoff(handoffs_dir: Path, name: str, body: str, mtime: float) -> Path:
    """Create a handoff file with an explicit modification time.

    Args:
        handoffs_dir: Directory to create the file in.
        name: Filename.
        body: File contents.
        mtime: Modification time, epoch seconds.

    Returns:
        The created path.
    """
    path = handoffs_dir / name
    path.write_text(body)
    os.utime(path, (mtime, mtime))
    return path


@pytest.fixture
def handoffs_dir(tmp_path):
    d = tmp_path / "handoffs"
    d.mkdir()
    return d


class TestSameDateSlugCannotDecide:
    """The regression itself, reproduced from the observed filenames."""

    def test_mtime_breaks_the_tie_not_the_slug(self, tmp_path, handoffs_dir):
        _write_handoff(
            handoffs_dir,
            "2026-09-02_sensor_layer_and_june_consolidation.md",
            "EARLIER_SAME_DAY",
            mtime=1_756_800_000.0,
        )
        _write_handoff(
            handoffs_dir,
            "2026-09-02_post_burn_reconciliation_and_g1_prior_art.md",
            "LATER_SAME_DAY",
            mtime=1_756_814_760.0,
        )

        # Name-descending — the old behaviour — would pick "sensor...".
        assert _read_latest_handoff(str(tmp_path)) == "LATER_SAME_DAY"

    def test_mtime_tiebreak_holds_in_the_other_direction(self, tmp_path, handoffs_dir):
        """Same pair, mtimes swapped: the answer must swap too.

        Asserting only the first direction would pass for a picker that had
        merely flipped the sort order.
        """
        _write_handoff(
            handoffs_dir,
            "2026-09-02_sensor_layer_and_june_consolidation.md",
            "LATER_SAME_DAY",
            mtime=1_756_814_760.0,
        )
        _write_handoff(
            handoffs_dir,
            "2026-09-02_post_burn_reconciliation_and_g1_prior_art.md",
            "EARLIER_SAME_DAY",
            mtime=1_756_800_000.0,
        )
        assert _read_latest_handoff(str(tmp_path)) == "LATER_SAME_DAY"


class TestDatePrefixIsAuthoritative:
    def test_declared_date_beats_a_later_touch(self, tmp_path, handoffs_dir):
        """A handoff is about a session; touching an old file is not a new session."""
        _write_handoff(
            handoffs_dir, "2026-09-02_current.md", "SEPTEMBER", mtime=1_756_800_000.0
        )
        _write_handoff(
            handoffs_dir, "2026-04-04_ancient.md", "APRIL", mtime=1_900_000_000.0
        )
        assert _read_latest_handoff(str(tmp_path)) == "SEPTEMBER"

    def test_hyphen_separated_date_prefix_is_recognized(self, tmp_path, handoffs_dir):
        _write_handoff(
            handoffs_dir, "2026-09-02-current.md", "SEPTEMBER", mtime=1_756_800_000.0
        )
        _write_handoff(
            handoffs_dir, "2026-04-04-ancient.md", "APRIL", mtime=1_900_000_000.0
        )
        assert _read_latest_handoff(str(tmp_path)) == "SEPTEMBER"

    def test_date_only_filename_is_recognized(self, tmp_path, handoffs_dir):
        _write_handoff(handoffs_dir, "2026-09-02.md", "SEPTEMBER", mtime=1.0)
        _write_handoff(handoffs_dir, "2026-04-04.md", "APRIL", mtime=2.0)
        assert _read_latest_handoff(str(tmp_path)) == "SEPTEMBER"

    def test_a_number_that_is_not_a_date_prefix_is_not_treated_as_one(
        self, tmp_path, handoffs_dir
    ):
        """`20260902_x.md` has no `YYYY-MM-DD` prefix, so it competes on mtime."""
        key = _handoff_sort_key(
            _write_handoff(handoffs_dir, "20260902_x.md", "X", mtime=0.0)
        )
        assert key[0] == "1970-01-01"


class TestNoDatePrefix:
    def test_undated_file_competes_on_its_modification_date(
        self, tmp_path, handoffs_dir
    ):
        _write_handoff(
            handoffs_dir, "2026-04-04_dated.md", "DATED", mtime=1_900_000_000.0
        )
        # 2030-01-01 UTC — later than the dated file's declared April date.
        _write_handoff(handoffs_dir, "scratch_notes.md", "UNDATED", mtime=1_893_456_000.0)
        assert _read_latest_handoff(str(tmp_path)) == "UNDATED"

    def test_undated_file_loses_to_a_newer_dated_file(self, tmp_path, handoffs_dir):
        _write_handoff(
            handoffs_dir, "2026-09-02_dated.md", "DATED", mtime=1_756_800_000.0
        )
        # 2020-01-01 UTC.
        _write_handoff(handoffs_dir, "scratch_notes.md", "UNDATED", mtime=1_577_836_800.0)
        assert _read_latest_handoff(str(tmp_path)) == "DATED"


class TestMixedDirectory:
    def test_dotfiles_and_subdirectories_are_ignored(self, tmp_path, handoffs_dir):
        _write_handoff(
            handoffs_dir, "2026-09-02_real.md", "REAL_HANDOFF", mtime=1_756_800_000.0
        )
        # Filesystem debris that sorts high and is newer than every handoff.
        _write_handoff(handoffs_dir, ".DS_Store", "DEBRIS", mtime=1_900_000_000.0)
        (handoffs_dir / "archive").mkdir()
        (handoffs_dir / "archive" / "2030-01-01_nested.md").write_text("NESTED")

        latest = _find_latest_handoff(str(tmp_path))
        assert latest is not None
        assert latest.name == "2026-09-02_real.md"
        assert _read_latest_handoff(str(tmp_path)) == "REAL_HANDOFF"

    def test_dated_undated_and_debris_together(self, tmp_path, handoffs_dir):
        _write_handoff(handoffs_dir, "2026-04-04_old.md", "OLD", mtime=1.0)
        _write_handoff(handoffs_dir, "2026-09-02_a.md", "A_SAME_DAY", mtime=100.0)
        _write_handoff(handoffs_dir, "2026-09-02_z.md", "Z_SAME_DAY_EARLIER", mtime=50.0)
        _write_handoff(handoffs_dir, "README.md", "UNDATED", mtime=1.0)
        _write_handoff(handoffs_dir, ".hidden", "DEBRIS", mtime=1_900_000_000.0)
        assert _read_latest_handoff(str(tmp_path)) == "A_SAME_DAY"


class TestEmptyAndMissing:
    def test_missing_handoffs_directory_returns_none(self, tmp_path):
        assert _find_latest_handoff(str(tmp_path)) is None
        assert _read_latest_handoff(str(tmp_path)) is None

    def test_empty_handoffs_directory_returns_none(self, tmp_path, handoffs_dir):
        assert _read_latest_handoff(str(tmp_path)) is None

    def test_directory_of_only_debris_returns_none(self, tmp_path, handoffs_dir):
        _write_handoff(handoffs_dir, ".DS_Store", "DEBRIS", mtime=1.0)
        assert _read_latest_handoff(str(tmp_path)) is None

    def test_handoffs_path_that_is_a_file_returns_none(self, tmp_path):
        (tmp_path / "handoffs").write_text("not a directory")
        assert _read_latest_handoff(str(tmp_path)) is None


class TestGoContextUsesTheFixedPicker:
    def test_go_output_carries_the_newest_same_day_handoff(self, tmp_path, handoffs_dir):
        _write_handoff(
            handoffs_dir, "2026-09-02_zzz_older.md", "OLDER_BODY", mtime=100.0
        )
        _write_handoff(
            handoffs_dir, "2026-09-02_aaa_newer.md", "NEWER_BODY", mtime=200.0
        )
        output = assemble_go_context(project_dir=str(tmp_path))
        assert "NEWER_BODY" in output
        assert "OLDER_BODY" not in output
