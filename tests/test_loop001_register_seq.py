"""LOOP-001 Part B (AD-033 ADDENDUM 01): the register allocates its sequence at merge, not on the branch.

`cc_tasks/2026-10-20_LOOP-001_stop_hook_no_progress_rule.md` Part B. STD-001R and DISP-001R both took seq 292 on
2026-10-19 because `seldon decision accept` numbered each record on its own branch. A record written in a linked
worktree now goes to `pending/` with a provisional id (its content hash) and no seq; the dispatcher's merge step, on
the primary checkout, appends every pending record to the chain (`number_merged_register`), renders REGISTER.md,
commits, and records `register_numbered` with the mapping. A record is never numbered twice.

Prior art: an append-only log with one writer assigns positions at the commit point (Kafka's broker-assigned
offset; a database sequence drawn inside the committing transaction). Real git worktrees, no Neo4j, no model call.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from seldon.commands import dispatch_worktree as W
from seldon.core import decisions as dr
from seldon.core.events import read_events

NOTE = "docs/design/2026-09-01_DN-001_first.md"
NOTE_TEXT = ("# DN-001 first\n\n## R-1 A kit, not a system\n\nThe kit never stores content.\n\n"
             "## R-2 Old cost chart\n\nThe multiple stays as a reported number under a control chart.\n\n"
             "## R-3 Third\n\nA third ruling.\n")


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


def _accept(root: Path, local: str, line: int, text: str) -> list[Path]:
    return dr.create(dr.universe(root, _cfg(root)), "accept", _record(local, line, text), date="2026-10-20",
                     decided_by="desktop")


@pytest.fixture
def repo(tmp_path):
    """A primary checkout on `main` with one numbered record, and two linked worktrees on branches `a` and `b`."""
    root = tmp_path / "proj"
    (root / "docs" / "design").mkdir(parents=True)
    (root / NOTE).write_text(NOTE_TEXT, encoding="utf-8")
    (root / "seldon.yaml").write_text(yaml.safe_dump({
        "project": {"name": "proj", "domain": "research"}, "event_store": {"path": "seldon_events.jsonl"},
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
    for b in ("a", "b"):
        _git(root, "worktree", "add", "-q", "-b", b, str(tmp_path / f"wt-{b}"))
    return root


def _merge(root: Path, branch: str) -> dict | None:
    """What the dispatcher's `_merge` does for a branch: rebase onto main, verify, fast-forward, number."""
    wt = root.parent / f"wt-{branch}"
    _git(wt, "rebase", "-q", "main")
    assert W._register_findings(wt, _cfg(root)) == []
    _git(root, "merge", "--ff-only", "-q", branch)
    return W.number_merged_register(root, _cfg(root), "sess-1", f"task-{branch}", branch)


def _commit_on(wt: Path, msg: str) -> None:
    _git(wt, "add", "-A")
    _git(wt, "commit", "-q", "-m", msg)


def test_a_branch_writes_its_record_unnumbered(repo):
    wt = repo.parent / "wt-a"
    assert dr.is_linked_worktree(wt) and not dr.is_linked_worktree(repo)
    [path] = _accept(wt, "R-2", 7, "The multiple stays as a reported number under a control chart.")
    assert path.parent.name == dr.PENDING_DIR
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "seq" not in data and "prev_hash" not in data and "record_hash" not in data
    assert data["provisional_id"] == dr.provisional_id(data)
    reg = dr.Register("proj", wt)
    assert reg.verify() == [] and [p.name for p in reg.files()] == ["00001_proj-r-1_accept.yaml"]
    assert dr.fold(reg.events())["proj:R-2"].status == "accepted", "the branch's own record binds on the branch"
    with pytest.raises(dr.RegisterError, match="linked worktree"):
        reg.number()


def test_two_branches_merge_in_sequence_and_take_consecutive_seqs(repo):
    wa, wb = repo.parent / "wt-a", repo.parent / "wt-b"
    _accept(wa, "R-2", 7, "The multiple stays as a reported number under a control chart.")
    dr.write_rendered(dr.universe(wa, _cfg(wa)))
    _commit_on(wa, "a: R-2")
    _accept(wb, "R-3", 11, "A third ruling.")
    dr.write_rendered(dr.universe(wb, _cfg(wb)))
    _commit_on(wb, "b: R-3")

    first = _merge(repo, "a")
    second = _merge(repo, "b")   # the rebase of b over a's numbering: no conflict

    assert [(m["id"], m["seq"]) for m in first["mapping"]] == [("proj:R-2", 2)]
    assert [(m["id"], m["seq"]) for m in second["mapping"]] == [("proj:R-3", 3)]
    assert first["commit"]["committed"] and second["commit"]["committed"]
    reg = dr.Register("proj", repo)
    assert reg.verify() == []
    assert [p.name for p in reg.files()] == ["00001_proj-r-1_accept.yaml", "00002_proj-r-2_accept.yaml",
                                             "00003_proj-r-3_accept.yaml"]
    assert reg.pending_files() == []
    rendered = (repo / "docs/decisions/REGISTER.md").read_text(encoding="utf-8")
    assert "proj:R-2" in rendered and "proj:R-3" in rendered
    assert dr.check(repo, _cfg(repo)) == [], "REGISTER.md is the rendering of the numbered register"
    assert _git(repo, "status", "--porcelain").stdout.strip() == "", "numbering is committed"
    events = [e["payload"] for e in read_events(repo) if e["event_type"] == W.EVENT_REGISTER_NUMBERED]
    assert [e["branch"] for e in events] == ["a", "b"]
    assert events[0]["mapping"][0]["provisional_id"] == first["mapping"][0]["provisional_id"]


def test_a_record_already_numbered_keeps_its_number(repo):
    wa = repo.parent / "wt-a"
    [pending] = _accept(wa, "R-2", 7, "The multiple stays as a reported number under a control chart.")
    rel = pending.relative_to(wa).as_posix()
    _commit_on(wa, "a: R-2")
    first = _merge(repo, "a")
    assert first["mapping"][0]["seq"] == 2
    # The pending file comes back (a rebase re-applies the commit that added it): it is not numbered again.
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_text(_git(repo, "show", f"a:{rel}").stdout, encoding="utf-8")
    again = dr.number_register(repo, _cfg(repo))
    assert again["numbered"] == [] and [(r["id"], r["seq"]) for r in again["already"]] == [("proj:R-2", 2)]
    reg = dr.Register("proj", repo)
    assert len(reg.files()) == 2 and reg.pending_files() == [] and reg.verify() == []
    assert dr.number_register(repo, _cfg(repo)) == {"numbered": [], "already": [], "rendered": None}


def test_two_branches_creating_one_id_are_refused_before_the_merge(repo):
    wa, wb = repo.parent / "wt-a", repo.parent / "wt-b"
    _accept(wa, "R-2", 7, "The multiple stays as a reported number under a control chart.")
    _commit_on(wa, "a: R-2")
    _accept(wb, "R-2", 7, "The multiple stays as a reported number under a control chart, from b.")
    _commit_on(wb, "b: R-2")
    _merge(repo, "a")
    _git(wb, "rebase", "-q", "main")
    bad = W._register_findings(wb, _cfg(repo))
    assert any("already holds" in x for x in bad), bad
