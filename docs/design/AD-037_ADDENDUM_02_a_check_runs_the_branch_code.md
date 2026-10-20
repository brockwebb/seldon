# AD-037 ADDENDUM 02: a station's check runs the code of the tree it runs in

**Date:** 2026-10-20. **Written by:** DISP-003R Part A (`cc_tasks/2026-10-20_DISP-003R_gate_runs_the_branch_code.md`).
**Amends:** where AD-037-R6's stations get the code a `check:` runs. AD-038-R4 already says a station inspects the tree
the session works in; this says the check also runs that tree's code. One new ruling, numbered from the register.

## Evidence: PA-002 (`314a3942`), 2026-10-19

PA-002's branch `worktree-delegated-floating-coral` changed `seldon/core/prior_art.py`. Its Part B acceptance was
`check: seldon prior-art verify docs/design/AD-036_prior_art_receipts_gate.md`. The Stop gate ran that check in the
worktree as the station is meant to (AD-038-R4). But `seldon` is a console script, and seldon is pip-installed
editable from the primary checkout, so the check ran main's verifier, not the branch's. The branch could never pass its
own gate. It finished `stop_gate_unpassed` with exit 0, its RESULT committed and its tests green
(`logs/seldon_dispatch.log`: `finished 314a3942 stop_gate_unpassed exit=0 result=True -> blocked`).

`pytest` checks did not have this defect for their own process. `python -m pytest` with the worktree as cwd puts the
worktree first on `sys.path`. They did have it for every child they started: git hooks and `seldon` subprocesses
imported main (memory note "worktree hooks run main code", DESK-001).

## The rule

- **AD-037-R14. A station runs every `check:` with the tree it runs in first on the import path, and runs a check's `seldon` as `<interpreter> -m seldon`.**
  `run_check` sets `PYTHONPATH` to the check's cwd, followed by whatever the environment already carried, so every
  child the check starts imports the same tree. A check whose first word is `seldon` or `pytest` runs as
  `<the dispatcher's python> -m <it>`. The `stop_gate` record names `interpreter` and `path`. Each check row names
  `interpreter` and `pythonpath`. This covers every station that calls `run_check`: the Stop gate, the first article and
  the premises. A premise runs in the primary checkout, so its path is the primary and nothing changes for it.
  Code: `seldon/core/stations.py` `MODULE_COMMANDS`, `check_argv`, `tree_path`, `run_check`, `stop_gate`.

*Scope, recorded rather than widened:* only `seldon` and `pytest` are mapped. A check that names `python` gets the
first `python` on the hook's PATH, and the tree on `PYTHONPATH` makes that interpreter import the tree too. Any other
console script still runs its installed code. That is the right default for a tool that is not under change, such as
`git`, `grep` or `test`.

## Prior art

### External

- library receipt: query "test the code under development not the installed copy import path" | release library_graph_20261017_sq018_02_2026-10-17.json sha256:99984ba3da90146a73ab4e9d8ddf15687551cb2cc2659be90d16e525253ecfb5 | rows lesson:2026-02-22_arXiv_2410_05080#p38:595:1640-1836

  The library's top rows are code-generation benchmarks, such as the ground-truth program listing cited above. None of
  them is about which copy of a package a test imports. The engineering sources below are the prior art.
- **Test the package being built, not an installed copy.** pytest's "Good Integration Practices"
  (docs.pytest.org/en/stable/explanation/goodpractices.html) explains the `src` layout and import modes so that
  tests import the code under test rather than a copy on `site-packages`. tox and nox build and install the package
  under test into a fresh environment for the same reason. Seldon's checks cannot do that per check, which would take
  minutes, so R14 gets the same guarantee from the import path.
- **The interpreter's own search-path rules.** Python's documentation, "The initialization of the sys.path module
  search path" (docs.python.org/3/library/sys_path_init.html): `python -m` prepends the cwd, and `PYTHONPATH` entries
  come before site-packages and are inherited by child processes. R14 relies on exactly these two rules.
- **CI runs the change's own revision.** GitHub Actions runs a `pull_request` workflow on the merge ref of the change,
  never on the default branch's code. A gate that reads a change and runs other code is not gating the change.

### Internal

- internal receipt: query "PYTHONPATH worktree" | repo seldon@c614ab674e87ea4174b8b986051b1393648dba41 | hits docs/design/AD-034_ADDENDUM_02_breaker_does_not_veto_green.md:12
- internal receipt: query "stop gate check worktree" | repo seldon@20d7e7c02ffb85a2c39980792d4c781f30a72118 | hits docs/design/AD-038_the_machine_reconciles_its_own_state.md:13

AD-034 ADDENDUM 02's evidence (line 12) is DISP-001R's session running `pytest` with `PYTHONPATH` set to its worktree
by hand. That was the workaround for this defect, applied per session, and the classifier refused it. R14 makes the
station do it. AD-038's diagnosis (lines 13 to 17, item 4) is the defect one level up: the station inspected the wrong
tree. AD-038-R4 fixed the tree; R14 fixes the code that runs in it.

## Negative control (AD-038-R6)

`tests/test_disp003_gate_path.py::test_the_negative_control_the_installed_code_does_not_pass_it`. In a tree without
the planted package, the same `seldon branch-only` check runs the installed seldon and does not pass, and
`seldon --version` does not print the marker. The three positive tests fail on HEAD before this change. Two of them,
the marker and the branch-only check, fail with the installed `seldon, version 0.1.0` in place of the marker. The
third fails because the record carries no `interpreter`.
