"""SEL-042 Parts D and E: `seldon verify` reads a branch's pending register records, and a file name the file system
cannot take is a refusal, not a traceback.

`cc_tasks/2026-11-21_SEL-042_a_stopped_session_is_never_merged_or_completed_the_merge_round_cannot_refuse_itself_and_verify_reads_pending_records.md`;
AD-033 ADDENDUM 02 (AD-033-R14) and AD-038 ADDENDUM 13 (AD-038-R30).

- D (squiddy `5b76278b`, hazbrief HB-193): in a worktree holding pending records (squiddy SQ-124's shape: two
  accepts and an amend of a numbered record) `seldon verify` raised `KeyError: 'record_hash'` and printed no check.
- E (hazbrief `1639fa20`): filing an addendum whose name is over 255 bytes raised `OSError: File name too long`.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from seldon.commands import cc as CC
from seldon.commands import verify as V
from seldon.core import decisions as dr
from seldon.core import filing as F
from seldon.domain.loader import load_domain_config
from tests.dispatch_scaffold import RESEARCH_YAML
from tests.testdb import TEST_DATABASE

NOTE = "docs/design/2026-09-01_DN-001_first.md"
NOTE_TEXT = ("# DN-001 first\n\n## R-1 A kit, not a system\n\nThe kit never stores content.\n\n"
             "## R-2 Second\n\nThe second ruling.\n\n## R-3 Third\n\nA third ruling.\n")


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    assert r.returncode == 0, (args, r.stdout, r.stderr)
    return r


def _cfg(root: Path) -> dict:
    return yaml.safe_load((root / "seldon.yaml").read_text(encoding="utf-8"))


def _record(local: str, line: int, text: str) -> dict:
    return {"id": f"proj:{local}", "kind": "decision", "statement": text,
            "source": {"path": NOTE, "lines": [line, line + 2],
                       "text": "\n".join(NOTE_TEXT.splitlines()[line - 1:line + 2])},
            "scope": ["proj"], "rationale": {"path": NOTE, "anchor": local}, "review_only": "none"}


def _accept(root: Path, local: str, line: int, text: str):
    return dr.create(dr.universe(root, _cfg(root)), "accept", _record(local, line, text), date="2026-11-21",
                     decided_by="desktop")


@pytest.fixture
def pending_tree(tmp_path, neo4j_driver, clean_test_db):
    """A primary with one numbered record (projected), and a linked worktree holding squiddy SQ-124's three pending
    records: two accepts and an amend of the numbered one."""
    root = tmp_path / "proj"
    (root / "docs" / "design").mkdir(parents=True)
    (root / NOTE).write_text(NOTE_TEXT, encoding="utf-8")
    (root / "seldon.yaml").write_text(yaml.safe_dump({
        "project": {"name": "proj", "domain": "research"}, "event_store": {"path": "seldon_events.jsonl"},
        "neo4j": {"database": TEST_DATABASE},
        "decisions": {"repository": "proj", "design_notes": [
            {"glob": "docs/design/*.md", "pattern": r"^(?:#+\s*|\s*[-*]\s*\*\*|\*\*)(R-\d{1,3})\b",
             "id": "{repo}:{label}"}]}}), encoding="utf-8")
    (root / ".gitignore").write_text("seldon_events.jsonl\ndocs/decisions/.register.lock\n", encoding="utf-8")
    _git(tmp_path, "init", "-q", "-b", "main", str(root))
    _git(root, "config", "user.email", "t@example.org")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "core.hooksPath", "/dev/null")
    _accept(root, "R-1", 3, "The kit never stores content.")
    dr.write_rendered(dr.universe(root, _cfg(root)))
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    dr.project(project_dir=root, config=_cfg(root), driver=neo4j_driver, database=TEST_DATABASE,
               domain_config=load_domain_config(RESEARCH_YAML))
    wt = tmp_path / "wt"
    _git(root, "worktree", "add", "-q", "-b", "b", str(wt))
    _accept(wt, "R-2", 7, "The second ruling.")
    _accept(wt, "R-3", 11, "A third ruling.")
    dr.amend(dr.universe(wt, _cfg(wt)), "proj:R-1", date="2026-11-21", decided_by="desktop",
             reason="SQ-124's amend of a numbered record", changes={"statement": "The kit stores no content."})
    assert len(dr.Register("proj", wt).pending_files()) == 3
    return root, wt


@pytest.mark.usefixtures("neo4j_available")
def test_verify_reports_the_pending_records_and_does_not_raise(pending_tree, neo4j_driver):
    root, wt = pending_tree
    with pytest.raises(KeyError, match="record_hash"):
        # The defect, as the filing traced it: `Record.last_hash` of a record whose last event is pending.
        dr.fold(dr.Register("proj", wt).events())["proj:R-1"].last_hash
    res = V.check_decisions(neo4j_driver, TEST_DATABASE, wt, _cfg(wt))
    assert res.symbol == "pass", (res.summary, res.details)
    line = "3 pending record(s), numbered at merge: proj:R-2 accept, proj:R-3 accept, proj:R-1 amend"
    assert line in res.summary and line in res.details


@pytest.mark.usefixtures("neo4j_available")
def test_every_other_check_still_prints_with_pending_records(pending_tree, neo4j_driver):
    root, wt = pending_tree
    results = V._run_all_checks(neo4j_driver, TEST_DATABASE, _cfg(wt), wt)
    names = [r.name for r in results]
    assert "Decision register" in names and len(names) == len(set(names)) >= 20, names
    (reg,) = [r for r in results if r.name == "Decision register"]
    assert "numbered at merge" in reg.summary


def test_with_no_pending_record_the_summary_is_unchanged():
    assert V._pending_line([]) is None


# ================================================================================ E: the name limit

STEM_HB207 = ("2026-11-19_HB-207_the_live_path_a_typed_line_with_a_common_name_and_now_as_the_time_draws_a_modelled_"
              "cloud_and_the_server_gains_a_decision_support_prompt")


def test_the_limit_is_the_file_systems(tmp_path):
    assert F.name_limit(tmp_path) == 255 and F.name_limit(tmp_path / "not" / "made") == 255


@pytest.mark.parametrize("ch", ["x", "é"], ids=["ascii", "two_byte_utf8"])
def test_at_the_limit_a_name_fits_and_one_byte_over_is_refused_with_the_room_left(tmp_path, ch):
    """Counted in bytes, as the file system counts them: `é` is two bytes in UTF-8, so the same character count can
    be over the limit."""
    prefix = f"{STEM_HB207}_ADDENDUM_01_"
    room = 255 - len(prefix.encode()) - len(".md")
    assert room == F.addendum_slug_room(STEM_HB207, 255) == 86
    fill = "y" * (room - len(ch.encode())) + ch
    at = f"{prefix}{fill}.md"
    assert len(at.encode()) == 255 and F.name_refusal(tmp_path, at) is None
    (tmp_path / at).write_text("fits\n")                                    # the file system takes it
    over = f"{prefix}{fill}z.md"
    msg = F.name_refusal(tmp_path, over)
    assert msg.startswith(f"{F.NAME_TOO_LONG}: ") and "is 256 bytes" in msg and "at most 255" in msg
    assert "leaves 86 byte(s) for the addendum's slug" in msg and "by 1 byte(s)" in msg
    if ch.isascii():
        with pytest.raises(OSError):
            (tmp_path / over).write_text("does not\n")                      # what the traceback was
    # Measured on this machine (APFS, 2026-11-21): a 256-byte name of 255 characters with one `é` IS written; APFS
    # counts characters. The refusal counts bytes anyway, as ext4 does, so a name that lands here also lands in every
    # clone of the repository: the stricter of the two limits.


def test_a_task_name_over_the_limit_names_the_room_after_the_date(tmp_path):
    name = "2026-11-21_" + "s" * 245 + ".md"
    msg = F.name_refusal(tmp_path, name)
    assert msg and "259 bytes" in msg and "241 byte(s) are left for the slug" in msg


def test_cc_file_refuses_an_addendum_name_over_the_limit_before_anything(tmp_path):
    """`file_addendum` refuses before the lock, the base-task lookup or a write: a driver that is touched fails."""
    name = f"{STEM_HB207}_ADDENDUM_01_{'s' * 87}.md"
    (tmp_path / "cc_tasks").mkdir()
    with pytest.raises(F.FilingError, match=F.NAME_TOO_LONG):
        F.file_addendum(tmp_path, {}, object(), "db", "# addendum\n", name)
    assert list((tmp_path / "cc_tasks").iterdir()) == []


def test_registration_warns_when_the_stem_leaves_little_room_for_an_addendum(tmp_path):
    (tmp_path / "cc_tasks").mkdir()
    assert CC.stem_room_warning(tmp_path, {}, STEM_HB207) is None                    # 86 bytes left
    long_stem = "2026-11-21_" + "t" * 180                                          # 255 - 191 - 16 = 48 left
    msg = CC.stem_room_warning(tmp_path, {}, long_stem)
    assert msg and CC.NAME_ROOM_WARNING in msg and "leaves 48 byte(s)" in msg and "below 60" in msg
    assert CC.stem_room_warning(tmp_path, {"filings": {"addendum_slug_warn_bytes": 40}}, long_stem) is None
