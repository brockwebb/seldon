"""DESK-002 Part A: a design note that labels a new ruling commits with its register record.

The commit gate (AD-033-R2, `seldon.core.hooks.decision_findings`) requires every label a new note
carries to have a record in the STAGED register. A Desktop session writes the record itself with
`seldon_decision_accept` (AD-033-R2: "registering a decision is part of writing the note"), so the
record and the rendered `REGISTER.md` are on disk and uncommitted when the task is registered. Before
DESK-002 two paths then failed, and each refused the note (Issue 5c689098; squiddy DN-048 / R-207 on
2026-10-16, DN-047 / R-206 on 2026-10-15):

  - `seldon cc register` planned a record only for a label with NO record, so a label whose record
    Desktop had already written was skipped, its file was not staged, and the hook refused the commit
    as `governing_note_uncommitted`;
  - `seldon_commit_governed` refused any `docs/decisions/` path as `outside_roots`.

Real git, the real hooks and (for registration) real Neo4j; the library arm is a stub, as in
`tests/test_hooks.py`.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from seldon.core import decisions as dr
from seldon.core import desktop_commit as DC
from seldon.core import hooks as H
from seldon.core import prior_art as pa
from tests import test_cc_register_commits_note as R
from tests.test_hooks import StubLibrary, _git, _good, repo  # noqa: F401 (fixture)

RULING = ("- **AD-099-R1. A probe ruling binds the probe.**\n"
          "  - It is recorded by Desktop before registration.\n\n"
          "Closing prose that is not the ruling.\n")
REG = "docs/decisions/register"
RENDERED = "docs/decisions/REGISTER.md"


def _desktop_accepts(project: Path, config: dict, note_rel: str, label: str = "AD-099-R1") -> list[str]:
    """What `seldon_decision_accept` does for a Desktop session: the record from the note's bytes,
    written through the one write path, and REGISTER.md rendered. Returns the record files written."""
    from seldon.commands.decision import run_write

    text = (project / note_rel).read_text(encoding="utf-8")
    s = dr.settings(project, config)
    spans = [x for x in dr.labeled_spans_in(s, note_rel, text) if x[1] == label]
    assert spans, f"{label} is not labelled in {note_rel}"
    qid, _label, start, end = spans[0]
    body = "\n".join(text.splitlines()[start - 1:end]).strip()
    rec = {"id": qid, "kind": "decision", "statement": "A probe ruling binds the probe.",
           "source": {"path": note_rel, "lines": [start, end],
                      "sha256": dr.sha256_file(project / note_rel), "text": body},
           "scope": [s.repository], "rationale": {"path": note_rel, "anchor": label},
           "review_only": "none"}
    written = run_write(project, "accept", record=rec, decided_by="desktop", date="2026-10-16",
                        reason="Desktop registers the ruling as part of writing the note (AD-033-R2)")
    return [p.relative_to(project).as_posix() for p in written]


# ------------------------------------------------------------------ registration (cc register)

@pytest.mark.usefixtures("neo4j_available", "clean_test_db")
def test_registration_commits_the_note_its_desktop_written_record_and_register_md_together(
        tmp_path, monkeypatch):
    """The squiddy SQ-017 case: the record Desktop wrote is on disk, uncommitted. Fails on HEAD with
    `governing_note_uncommitted ... labels t:AD-099-R1, which has no record in the staged register`."""
    repo = R.make_repo(tmp_path, monkeypatch)
    d = repo["dir"]
    R._write(repo, R.NOTE, R._good(repo, RULING))
    rec_files = _desktop_accepts(d, repo["config"], R.NOTE)
    assert len(rec_files) == 1 and (d / RENDERED).is_file()
    R._task(repo)
    before = R._head(repo)

    out = R.seldon_cc_register(R.TASK, project_dir=str(d), allow_untracked=True)

    assert out.startswith("Registered:"), out
    assert _git(d, "rev-parse", "HEAD~1").stdout.strip() == before            # ONE commit
    files = R._files_in(repo)
    assert R.NOTE in files and R.TASK in files
    assert rec_files[0] in files and RENDERED in files
    # Desktop's record is the one committed: registration wrote no second record for the label.
    assert sorted(p.name for p in (d / REG).glob("*.yaml")) == [Path(rec_files[0]).name]
    assert R._status(repo, "docs", "cc_tasks", "governed") == ""


# --------------------------------------------------------------------------- commit_governed

def _note_with_verdict(repo, body: str) -> str:
    """A note with a passing verdict committed first, as `seldon prior-art verify` commits its own
    lines (AD-036-R11); the gate then judges only the ruling's record."""
    note = "docs/design/AD-099_x.md"
    (repo["dir"] / note).write_text(body, encoding="utf-8")
    s = pa.settings(repo["dir"], repo["config"])
    pa.record_verdict(pa.verify_note(repo["dir"] / note, s, library=StubLibrary()), repo["dir"], repo["config"])
    _git(repo["dir"], "add", "governed/ledger/events.jsonl")
    _git(repo["dir"], "commit", "-qm", "verdict")
    return note


def test_commit_governed_commits_a_note_with_the_record_its_label_answers(repo):
    """Fails on HEAD: `outside_roots: docs/decisions/register/... is under none of ...`."""
    d = repo["dir"]
    note = _note_with_verdict(repo, _good(repo) + RULING)
    recs = _desktop_accepts(d, repo["config"], note)
    before = _head(repo)

    out = DC.commit_governed(d, [note, *recs, RENDERED], repo["config"])

    assert out.committed, out.detail
    assert _git(d, "rev-parse", "HEAD~1").stdout.strip() == before
    assert sorted(_git(d, "show", "--name-only", "--pretty=", "HEAD").stdout.split()) == \
        sorted([note, *recs, RENDERED])
    assert out.drafts == []
    assert "register: " in out.message
    assert _git(d, "status", "--porcelain", "--untracked-files=all", "--", note, REG, RENDERED).stdout == ""


def test_commit_governed_refuses_a_record_alone_and_stages_nothing(repo):
    """A register path without the note whose label it answers is still `outside_roots`. HEAD refused
    it too, as it refused every register path; the assertion on the reason fails on HEAD."""
    d = repo["dir"]
    note = _note_with_verdict(repo, _good(repo) + RULING)
    recs = _desktop_accepts(d, repo["config"], note)
    before = _head(repo)

    for paths in ([*recs], [*recs, RENDERED], [RENDERED]):
        out = DC.commit_governed(d, paths, repo["config"])
        assert not out.committed and out.refusal == DC.OUTSIDE_ROOTS, out
        assert "only with the design note whose label it answers" in out.detail, out.detail
    assert _head(repo) == before
    assert _git(d, "diff", "--cached", "--name-only").stdout == ""


def test_commit_governed_refuses_a_record_its_note_does_not_label(repo):
    """A note in the same call is not enough: the record must answer one of ITS labels."""
    d = repo["dir"]
    labelled = _note_with_verdict(repo, _good(repo) + RULING)
    recs = _desktop_accepts(d, repo["config"], labelled)
    _git(d, "add", labelled)
    other = "docs/design/AD-098_other.md"
    (d / other).write_text("# AD-098 another note\n\nNo ruling here.\n")

    out = DC.commit_governed(d, [other, *recs], repo["config"])

    assert not out.committed and out.refusal == DC.OUTSIDE_ROOTS, out
    assert "t:AD-099-R1" in out.detail


def test_the_gate_still_refuses_a_note_whose_label_has_no_record_anywhere(repo):
    """Regression guard, not a HEAD failure: DESK-002 widens what may be STAGED with a note, never
    what the hook admits. A labelled note with no record anywhere is refused by the hook."""
    d = repo["dir"]
    note = _note_with_verdict(repo, _good(repo) + RULING)
    before = _head(repo)

    out = DC.commit_governed(d, [note], repo["config"])

    assert not out.committed and out.refusal == DC.HOOK_REFUSED, out
    assert "labels t:AD-099-R1, which has no record in the staged register" in out.detail
    assert _head(repo) == before
    assert _git(d, "diff", "--cached", "--name-only").stdout == ""


def _head(repo) -> str:
    return _git(repo["dir"], "rev-parse", "HEAD").stdout.strip()
