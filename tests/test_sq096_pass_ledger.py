"""squiddy SQ-096 (DN-052 R-237): `seldon verify` and the pre-commit hook refuse a pass ledger forked from main's.

The rule is the project's own check (seldon.yaml `pass_ledger.check`); seldon runs it. These tests use a stub check in
the scratch repository, so seldon's suite does not depend on squiddy: a ledger must be main's lines followed by more
lines. What is tested is seldon's half: `verify` runs the check in the checkout and fails on exit 1 naming
`pass_ledger_forked`; the hook judges the STAGED blob, not the working tree; a real `git rebase` whose conflict on the
ledger is resolved to the branch's side is refused at `rebase --continue`; a project with no declaration is untouched.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from seldon.commands.verify import PL_CHECK_NAME, TIER_A_CHECKS, check_pass_ledger
from seldon.core import hooks as H
from seldon.core import pass_ledger as PL

SRC = Path(H.__file__).resolve().parents[2]
LEDGER = "kit/ledger/passes.jsonl"

#: The stub check. squiddy's real one (`squiddy.kitpass check`) also verifies each extending line chains onto its
#: predecessor; for seldon's plumbing, the prefix rule is enough.
STUB = '''import argparse, subprocess, sys
from pathlib import Path
ap = argparse.ArgumentParser()
ap.add_argument("--checkout", required=True); ap.add_argument("--ledger")
a = ap.parse_args()
co = Path(a.checkout)
branch = subprocess.run(["git", "-C", str(co), "symbolic-ref", "--quiet", "--short", "HEAD"],
                        capture_output=True, text=True).stdout.strip()
ref = "origin/main" if branch == "main" else "main"
main = subprocess.run(["git", "-C", str(co), "show", f"{ref}:LEDGER"], capture_output=True,
                      text=True, check=True).stdout.splitlines()
own = Path(a.ledger or co / "LEDGER").read_text().splitlines()
for n, (x, y) in enumerate(zip(own, main), 1):
    if x != y:
        print(f"pass_ledger_forked: line {n} is {x!r}; main's line {n} is {y!r}", file=sys.stderr)
        sys.exit(1)
print(f"not forked: {len(own)} line(s) against {ref}'s {len(main)}")
'''.replace("LEDGER", LEDGER)


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["PYTHONPATH"] = os.pathsep.join(x for x in (str(SRC), env.get("PYTHONPATH")) if x)
    env["GIT_EDITOR"] = "true"
    return subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t", *args],
                          check=check, capture_output=True, text=True, env=env)


def _append(root: Path, line: str) -> None:
    with (root / LEDGER).open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


@pytest.fixture
def proj(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    (root / "stubkit").mkdir()
    (root / "stubkit" / "__init__.py").write_text("")
    (root / "stubkit" / "check.py").write_text(STUB)
    (root / "kit" / "ledger").mkdir(parents=True)
    (root / LEDGER).write_text("line 1\nline 2\n")
    (root / "seldon.yaml").write_text(yaml.safe_dump({
        "project": {"name": "t"},
        "pass_ledger": {"path": LEDGER, "check": ["-m", "stubkit.check"]}}))
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "init")
    # the remote's main, which a checkout ON main is judged against (squiddy kit.yaml pass_ledger_main_remote)
    _git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    res = H.install(root, python=sys.executable)
    assert res.wrote_hook
    return root


def _fork(root: Path) -> None:
    """main and `feature` each append one line after line 2 and commit it: SQ-021M2's shape."""
    _git(root, "checkout", "-q", "-b", "feature")
    _append(root, "branch line 3")
    _git(root, "commit", "-qam", "a branch pass")
    _git(root, "checkout", "-q", "main")
    _append(root, "main line 3")
    _git(root, "commit", "-qam", "main's pass")
    _git(root, "checkout", "-q", "feature")


def test_verify_passes_a_chained_branch_and_fails_a_forked_one_naming_the_line(proj):
    config = yaml.safe_load((proj / "seldon.yaml").read_text())
    _git(proj, "checkout", "-q", "-b", "feature")
    _append(proj, "branch line 3")
    ok = check_pass_ledger(proj, config)
    assert ok.symbol == "pass", ok
    _git(proj, "commit", "-qam", "a branch pass")
    _git(proj, "checkout", "-q", "main")
    _append(proj, "main line 3")
    _git(proj, "commit", "-qam", "main's pass")
    _git(proj, "checkout", "-q", "feature")
    bad = check_pass_ledger(proj, config)
    assert bad.symbol == "fail" and PL.FORKED in bad.summary
    assert any("line 3" in d for d in bad.details)
    assert PL_CHECK_NAME in TIER_A_CHECKS


def test_verify_skips_a_project_that_declares_no_pass_ledger_and_refuses_a_malformed_declaration(proj):
    assert check_pass_ledger(proj, {"project": {"name": "t"}}).symbol == "pass"
    bad = check_pass_ledger(proj, {"pass_ledger": {"path": LEDGER, "check": "python -m x"}})
    assert bad.symbol == "fail" and "check" in bad.summary
    assert check_pass_ledger(proj, {"pass_ledger": {"path": LEDGER, "chek": []}}).symbol == "fail"


def test_a_check_that_cannot_run_fails_verify(proj):
    got = check_pass_ledger(proj, {"pass_ledger": {"path": LEDGER, "check": ["-m", "no_such_module"]}})
    assert got.symbol == "fail" and PL.FORKED not in got.summary


def test_a_rebase_resolved_to_the_branchs_side_is_refused_by_the_hook(proj):
    _fork(proj)
    r = _git(proj, "rebase", "main", check=False)
    assert r.returncode != 0 and "CONFLICT" in (r.stdout + r.stderr)
    _git(proj, "checkout", "--theirs", "--", LEDGER)      # in a rebase, "theirs" is the branch's commit
    _git(proj, "add", LEDGER)
    r = _git(proj, "rebase", "--continue", check=False)
    assert r.returncode != 0, r.stdout + r.stderr
    assert PL.FORKED in r.stdout + r.stderr and "line 3" in r.stdout + r.stderr
    # main's side, with the tip's pass recorded again on main's last line, goes through
    (proj / LEDGER).write_text(_git(proj, "show", f"main:{LEDGER}").stdout)   # main's side
    _append(proj, "the tip's pass, recorded again")
    _git(proj, "add", LEDGER)
    r = _git(proj, "rebase", "--continue", check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (proj / LEDGER).read_text().splitlines() == ["line 1", "line 2", "main line 3",
                                                        "the tip's pass, recorded again"]


def test_the_hook_judges_the_staged_ledger_not_the_working_tree(proj):
    _fork(proj)
    (proj / LEDGER).write_text("line 1\nline 2\nmain line 3\n")    # a good working tree...
    _git(proj, "add", LEDGER)
    (proj / LEDGER).write_text("line 1\nforked line 2\n")          # ...and an unstaged fork after it
    r = _git(proj, "commit", "-qm", "staged is main's", check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    (proj / LEDGER).write_text("line 1\nline 2\nmain line 3\nok\n")
    _git(proj, "add", LEDGER)
    _git(proj, "commit", "-qm", "extend")
    # the converse: a forked blob staged under a good working tree is refused
    (proj / LEDGER).write_text("line 1\nother 2\n")
    _git(proj, "add", LEDGER)
    (proj / LEDGER).write_text("line 1\nline 2\nmain line 3\nok\n")
    r = _git(proj, "commit", "-qm", "staged fork", check=False)
    assert r.returncode != 0 and PL.FORKED in r.stdout + r.stderr


def test_a_commit_that_does_not_stage_the_ledger_is_not_judged(proj):
    _fork(proj)                                                    # the branch is forked, but this commit
    (proj / "README.md").write_text("x\n")                         # does not touch the ledger
    _git(proj, "add", "README.md")
    r = _git(proj, "commit", "-qm", "unrelated", check=False)
    assert r.returncode == 0, r.stdout + r.stderr


def test_install_writes_the_sequencer_hook_and_without_it_the_rebase_goes_through(proj):
    """The removal control (kg_construction_methodology 7.9): the refusal above depends on the hook git's sequencer
    runs, `.githooks/prepare-commit-msg`, and not on something incidental."""
    rel = f"{H.HOOKS_DIR}/{H.PREPARE_COMMIT_MSG}"
    assert rel in H.seldon_hook_scripts() and (proj / rel).read_text() == H.PREPARE_COMMIT_MSG_SCRIPT
    assert _git(proj, "ls-files", "--error-unmatch", rel, check=False).returncode == 0   # committed by install
    assert H.status(proj)["sequenced"] is True
    (proj / rel).unlink()
    _git(proj, "commit", "-qam", "remove the sequencer hook", "--no-verify")
    assert H.status(proj)["sequenced"] is False and H.status(proj)["installed"] is True
    _fork(proj)
    assert _git(proj, "rebase", "main", check=False).returncode != 0
    _git(proj, "checkout", "--theirs", "--", LEDGER)
    _git(proj, "add", LEDGER)
    r = _git(proj, "rebase", "--continue", check=False)
    assert r.returncode == 0, r.stdout + r.stderr          # nothing refused it: pre-commit never ran
