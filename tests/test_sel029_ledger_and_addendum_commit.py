"""SEL-029 Parts B and C: the verdict ledger commits beside its note; a task addendum cannot carry a candidacy header.

Part B (AD-036-R20, answering SEL-026). The commit gate (AD-036-R4) reads a note's verdict from the STAGED ledger and
its refusal says "stage the verdict ledger with the note"; `seldon_commit_governed` refused that ledger as
`outside_roots`, so a verified note could not be committed through the tool the gate's message addresses (hazbrief-mcp
DN-022, committed by hand). The ledger is now accepted beside a design note or addendum whose current bytes have a
verdict in it, mirroring DESK-002's register exception; alone, or beside files it holds no verdict for, it still
refuses. The message stays `desktop: design: <basename>`.

Part C (AD-038-R24, answering SEL-027). HB-115's addendum raised its Spend; the dispatcher reads candidacy headers from
the task file only (AD-038-R11), so the ceiling stayed at the base line and the andon halted the run. An addendum
carrying `**Spend:**`, `**Network:**`, `**Framework layer served:**` or `**Exclusive:**` is refused at
`seldon_commit_governed` and at `seldon_cc_register`, the rule and the remedy in one line.

Real git and the real hooks (the `repo` fixture of `tests/test_hooks.py`, whose verdict ledger is the governed ledger);
the library arm is a stub. The CLI and the MCP tool are both driven.
"""
from __future__ import annotations

import pytest
from click.testing import CliRunner

from seldon.commands.commit_governed import commit_governed_command
from seldon.core import desktop_commit as DC
from seldon.core import dispatch as D
from seldon.core import prior_art as pa
from seldon.mcp_server import seldon_commit_governed as _registered_commit_governed
from tests import test_cc_register_commits_note as R
from tests.test_hooks import StubLibrary, _git, _good, repo  # noqa: F401 (fixture)

#: The tool's body, in this process (AD-038-R3): the registered tool runs in a fresh process on the primary's code.
seldon_commit_governed = _registered_commit_governed.__wrapped__

LEDGER = "governed/ledger/events.jsonl"
NOTE = "docs/design/AD-099_x.md"
ADDENDUM = "docs/design/AD-099_ADDENDUM_01_more.md"
REFUSAL = ("addendum_carries_header: **Spend:**; headers are read from the task file only (AD-038-R11); to change one, "
           "re-file the task with an R suffix")


def _verified_note(repo, addendum: bool = False) -> None:
    """A note (and optionally its addendum) written and verified, its verdict appended to the ledger and NOT
    committed: the state a Desktop session is in after `seldon_prior_art_verify`."""
    d = repo["dir"]
    (d / NOTE).write_text(_good(repo), encoding="utf-8")
    if addendum:
        (d / ADDENDUM).write_text("# AD-099 ADDENDUM 01\n\nA completion of the note.\n", encoding="utf-8")
    s = pa.settings(d, repo["config"])
    v = pa.verify_note(d / NOTE, s, library=StubLibrary())
    assert v.verdict == "pass", v.problems
    pa.record_verdict(v, d, repo["config"])
    assert _git(d, "status", "--porcelain", "--", LEDGER).stdout.strip(), "the verdict line is uncommitted"


def _head(repo) -> str:
    return _git(repo["dir"], "rev-parse", "HEAD").stdout.strip()


def _committed(repo) -> list[str]:
    return sorted(_git(repo["dir"], "show", "--name-only", "--pretty=", "HEAD").stdout.split())


# ------------------------------------------------------------------------------------------------- Part B

def test_the_ledger_commits_beside_the_note_it_holds_a_verdict_for(repo):
    """Fails on HEAD: `outside_roots: governed/ledger/events.jsonl is under none of ...` (SEL-026 step 3)."""
    d = repo["dir"]
    _verified_note(repo)
    before = _head(repo)
    out = DC.commit_governed(d, [NOTE, LEDGER], repo["config"])
    assert out.committed, out.detail
    assert _git(d, "rev-parse", "HEAD~1").stdout.strip() == before
    assert _committed(repo) == sorted([NOTE, LEDGER])
    assert out.message == "desktop: design: AD-099_x.md"
    assert out.drafts == []
    assert _git(d, "status", "--porcelain", "--", NOTE, LEDGER).stdout == ""


def test_without_the_ledger_the_hook_still_refuses_and_says_to_stage_it(repo):
    """The ruling of AD-036-R20: the gate does not read a verdict from the ledger on disk; the staged ledger is the
    proof. Without the ledger the note is not a draft (it has a passing verdict on disk), so the hook refuses it."""
    d = repo["dir"]
    _verified_note(repo)
    before = _head(repo)
    out = DC.commit_governed(d, [NOTE], repo["config"])
    assert not out.committed and out.refusal == DC.HOOK_REFUSED, out
    assert f"then stage the verdict ledger {LEDGER} with the note" in out.detail
    assert _head(repo) == before


def test_the_ledger_alone_refuses_and_stages_nothing(repo):
    d = repo["dir"]
    _verified_note(repo)
    before = _head(repo)
    out = DC.commit_governed(d, [LEDGER], repo["config"])
    assert not out.committed and out.refusal == DC.OUTSIDE_ROOTS, out
    assert "only beside a design note or addendum it holds a verdict for" in out.detail
    assert _head(repo) == before
    assert _git(d, "diff", "--cached", "--name-only").stdout == ""


def test_the_ledger_beside_a_note_it_holds_no_verdict_for_refuses(repo):
    d = repo["dir"]
    _verified_note(repo)
    (d / NOTE).write_text(_good(repo) + "\nAn edit after the verdict.\n", encoding="utf-8")
    out = DC.commit_governed(d, [NOTE, LEDGER], repo["config"])
    assert not out.committed and out.refusal == DC.OUTSIDE_ROOTS, out
    assert f"no verdict for the current bytes of {NOTE}" in out.detail
    assert _git(d, "diff", "--cached", "--name-only").stdout == ""


def test_the_ledger_commits_beside_an_addendum_its_verdict_carries(repo):
    d = repo["dir"]
    _verified_note(repo, addendum=True)
    _git(d, "add", NOTE)
    _git(d, "commit", "-qm", "draft: the note, by hand", "--no-verify")
    out = DC.commit_governed(d, [ADDENDUM, LEDGER], repo["config"])
    assert out.committed, out.detail
    assert _committed(repo) == sorted([ADDENDUM, LEDGER])
    assert out.message == "desktop: design: AD-099_ADDENDUM_01_more.md"


def test_the_cli_and_the_mcp_tool_share_the_ledger_path(repo):
    d = repo["dir"]
    _verified_note(repo)
    refused = seldon_commit_governed(paths=[LEDGER], project_dir=str(d))
    assert refused.startswith(f"REFUSED {DC.OUTSIDE_ROOTS}: {LEDGER}: "), refused
    res = CliRunner().invoke(commit_governed_command, [LEDGER, "--project", str(d)])
    assert res.exit_code != 0 and f"REFUSED {DC.OUTSIDE_ROOTS}: {LEDGER}: " in res.output, res.output
    res = CliRunner().invoke(commit_governed_command, [NOTE, LEDGER, "--project", str(d)])
    assert res.exit_code == 0, res.output
    assert "desktop: design: AD-099_x.md" in res.output
    (d / NOTE).write_text(_good(repo) + "\nA second paragraph, verified again.\n", encoding="utf-8")
    s = pa.settings(d, repo["config"])
    pa.record_verdict(pa.verify_note(d / NOTE, s, library=StubLibrary()), d, repo["config"])
    ok = seldon_commit_governed(paths=[NOTE, LEDGER], project_dir=str(d))
    assert ok.startswith("committed ") and "desktop: design: AD-099_x.md" in ok, ok
    assert _committed(repo) == sorted([NOTE, LEDGER])


# ------------------------------------------------------------------------------------------------- Part C

TASK_ADDENDUM = "cc_tasks/2026-11-08_SEL-T_probe_ADDENDUM_01_raise.md"


def _addendum(d, body: str) -> None:
    (d / "cc_tasks").mkdir(exist_ok=True)
    (d / TASK_ADDENDUM).write_text(body, encoding="utf-8")


@pytest.mark.parametrize("line,header", [
    ("**Spend:** est. 1.2M tokens.", "Spend"),
    ("**Network:** none.", "Network"),
    ("**Framework layer served (DN-005 §5 rule 1):** none.", "Framework layer served"),
    ("- **Exclusive:** yes", "Exclusive"),
])
def test_the_refusal_names_each_candidacy_header(line, header):
    text = f"# ADDENDUM 01\n\n## 4. A raise\n\n{line}\n"
    assert D.addendum_header_refusal(text) == (
        f"addendum_carries_header: **{header}:**; headers are read from the task file only (AD-038-R11); to change "
        f"one, re-file the task with an R suffix")


def test_a_header_quoted_in_code_is_prose_not_a_header():
    text = ("# ADDENDUM 01\n\nThe base file's `**Spend:**` line stands.\n\n```\n**Network:** none.\n```\n"
            "Spend rises to 1200000 for the Part 0 work.\n")
    assert D.addendum_header_refusal(text) is None


def test_an_addendum_with_a_spend_line_is_refused_at_commit_governed(repo):
    d = repo["dir"]
    _addendum(d, "# SEL-T ADDENDUM 01\n\n## 4. Spend\n\n**Spend:** est. 1.2M tokens.\n")
    before = _head(repo)
    out = DC.commit_governed(d, [TASK_ADDENDUM], repo["config"])
    assert not out.committed and out.refusal == D.ADDENDUM_CARRIES_HEADER, out
    assert out.detail.startswith(REFUSAL), out.detail
    assert _head(repo) == before
    assert _git(d, "diff", "--cached", "--name-only").stdout == ""
    assert seldon_commit_governed(paths=[TASK_ADDENDUM], project_dir=str(d)).startswith(f"REFUSED {REFUSAL}")


def test_an_addendum_without_a_header_commits_as_before(repo):
    d = repo["dir"]
    _addendum(d, "# SEL-T ADDENDUM 01\n\n## 4. A correction\n\nStep 3 reads the other file.\n")
    out = DC.commit_governed(d, [TASK_ADDENDUM], repo["config"])
    assert out.committed, out.detail
    assert out.message == f"desktop: task: {TASK_ADDENDUM.split('/')[-1]}"
    assert out.registered == [] and out.unregistered == []


def test_a_base_task_file_with_a_spend_line_is_not_an_addendum():
    assert D.is_addendum_name("2026-11-08_SEL-T_probe_ADDENDUM_01_raise.md")
    assert not D.is_addendum_name("2026-11-08_SEL-T_probe.md")


@pytest.mark.usefixtures("neo4j_available", "clean_test_db")
def test_an_addendum_with_a_spend_line_is_refused_at_cc_register(tmp_path, monkeypatch):
    repo = R.make_repo(tmp_path, monkeypatch)
    d = repo["dir"]
    _addendum(d, "# SEL-T ADDENDUM 01\n\n**Spend:** est. 1.2M tokens.\n")
    out = R.seldon_cc_register(TASK_ADDENDUM, project_dir=str(d), allow_untracked=True)
    assert out.startswith(f"Error: {REFUSAL}. File: {TASK_ADDENDUM}"), out
    assert "cite the AD or DN" not in out
    res = CliRunner().invoke(R.cc_group, ["register", TASK_ADDENDUM, "--allow-untracked", "--project", str(d)])
    assert res.exit_code != 0
    assert f"ERROR: {REFUSAL}. File: {TASK_ADDENDUM}" in res.output, res.output
    assert "cite the AD or DN" not in res.output
