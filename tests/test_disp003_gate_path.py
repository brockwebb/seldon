"""DISP-003R Part A (AD-037 ADDENDUM 02): a station's `check:` runs the code of the tree it runs in.

A check that starts with `seldon` ran the console script, which imports the PRIMARY checkout's code (seldon is
installed editable from it), so a branch that changed the code a check depends on could never pass its own gate
(PA-002's Part B, 2026-10-19). Each test plants a fake `seldon` package in a scratch tree: the tree's own code is the
only thing that prints its marker or exits 0, so the installed code cannot pass these checks.
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

from tests import stations_scaffold as F

MARKER = "DISP003-BRANCH-CODE-MARKER"

#: The fake package's `__main__`: `--version` prints the marker; `branch-only` exits 0 only when a CHILD process,
#: started from `/`, imports this same tree's `seldon` (what a hook a test spawns would import).
FAKE_MAIN = textwrap.dedent(f"""\
    import subprocess, sys
    if sys.argv[1:] == ["--version"]:
        print("{MARKER}")
        sys.exit(0)
    if sys.argv[1:] == ["branch-only"]:
        child = subprocess.run([sys.executable, "-c", "import seldon, sys; sys.exit(0 if seldon.BRANCH else 1)"],
                               cwd="/")
        sys.exit(child.returncode)
    sys.exit(5)
    """)


def _tree(root: Path) -> Path:
    pkg = root / "seldon"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("BRANCH = True\n", encoding="utf-8")
    (pkg / "__main__.py").write_text(FAKE_MAIN, encoding="utf-8")
    return root


def test_a_seldon_check_reports_the_trees_own_marker(tmp_path):
    from seldon.core import stations as S
    tree = _tree(tmp_path / "wt")
    r = S.run_check("seldon --version", tree, 60)
    assert r["outcome"] == "pass", r
    assert MARKER in r["tail"], "the check ran the installed seldon, not the tree's"
    assert r["interpreter"] == sys.executable
    assert r["pythonpath"].split(":")[0] == str(tree)


def test_a_check_that_passes_only_with_the_branchs_code_passes(tmp_path):
    from seldon.core import stations as S
    tree = _tree(tmp_path / "wt")
    r = S.run_check("seldon branch-only", tree, 60)
    assert r["outcome"] == "pass", r


def test_the_negative_control_the_installed_code_does_not_pass_it(tmp_path):
    """No new control without its negative control (AD-038-R6): in a tree WITHOUT the fake package, the same check
    runs the installed seldon, which has no `branch-only` command, and does not pass."""
    from seldon.core import stations as S
    empty = tmp_path / "empty"
    empty.mkdir()
    r = S.run_check("seldon branch-only", empty, 120)
    assert r["outcome"] != "pass", r
    assert MARKER not in S.run_check("seldon --version", empty, 120)["tail"]


def test_the_stop_gate_record_names_interpreter_and_path(tmp_path):
    p = F.make_project(tmp_path, check_a="seldon branch-only")
    tree = _tree(tmp_path / "wt")
    F.launch(p, at=F.ago(60))
    F.write_log(p, 1000)
    F.record(p, "part_complete", {"part": "A", "planned_share": 0.5, "tokens": 1000})
    out = F.gate(p, cwd=tree)
    rec = out["record"]
    assert rec["verdict"] == "pass", rec
    assert rec["interpreter"] == sys.executable
    assert rec["path"].split(":")[0] == str(tree)
    assert rec["parts"][0]["checks"][0]["pythonpath"].split(":")[0] == str(tree)
