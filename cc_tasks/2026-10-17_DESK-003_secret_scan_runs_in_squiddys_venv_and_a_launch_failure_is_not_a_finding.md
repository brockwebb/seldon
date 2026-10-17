# DESK-003: the handoff secret scan runs under squiddy's venv launcher, and a scanner that did not run is `scan_failed`, never `secret_found`

**Repo:** seldon. L4: commit, merge, push. Work on a branch; merge before `part-complete`.
**Date:** 2026-10-17. **Authored by:** a Desktop session in squiddy (SQ8).
**Governing:** DESK-001 (Desktop commits through one governed path with a secret scan on handoffs); AD-038-R1 (machine-written state is the machine's to reconcile); AD-038-R6 (a control ships with its negative control).
**After:** none
**Resolves:** Issue `cf57b8e5` (handoff scanner runs the wrong python).
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Model:** primary
**Spend:** est. 0.12M tokens. Basis: two edits in one file, two tests, one hand commit of a held handoff.
**Parts:** A 0.6, B 0.4.
**Network:** none beyond git push.
**Exclusive:** yes
**Premises:**
- premise: the scan command is configured as a relative venv path | check: `grep -q "squiddy/.venv/bin/python" seldon.yaml`
- premise: squiddy's venv launcher is a symlink | check: `test -L /Users/brock/GitHub/squiddy/.venv/bin/python`
- premise: the held handoff is parked in the workbench | check: `test -f /Users/brock/GitHub/workbench/parked/2026-10-17_desktop_sq8_friction_class_ad038_work_order.md`

Glob and read every sibling `*DESK-003*ADDENDUM*.md`.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.2M.

## The defect, measured

`seldon/core/desktop_commit.py` `settings()` absolutizes a relative `desktop_commit.scan.command[0]` with `Path.resolve()`. That follows the venv symlink `../squiddy/.venv/bin/python` to the bare uv CPython binary, which has no `pyvenv.cfg` beside it, so it runs outside squiddy's venv, cannot import `squiddy`, and exits 1. `_scan()` maps every exit 1 to `SECRET_FOUND`. Result: every handoff this week was refused as "secret found" with a `ModuleNotFoundError` as the finding, and the untracked handoff then held the whole queue at c7 (seldon_dispatch.log, 2026-10-17 13:xx to 14:xx, four candidates refused per pass). The existing test `tests/test_desk001_desktop_commit.py::test_the_secret_scan_refuses_a_flagged_handoff` uses an absolute stub path, so the relative-path rewrite was never exercised.

## Part A: the fix, with its negative control

1. In `settings()`, absolutize lexically (`os.path.normpath(Path(project_dir) / command[0])`), not with `resolve()`. `project_dir` is already resolved by `commit_governed()`.
2. In `_scan()`, exit 1 is `SECRET_FOUND` only when the scanner's own trailer (`scanned N file(s); exit 1`) is in stdout. Any other non-zero exit, including exit 1 with no trailer, is `SCAN_FAILED` with stderr verbatim.
3. Two tests, each failing on HEAD: (i) `scan.command[0]` is a relative path to a symlink whose target lives in another directory; the spawned argv keeps the symlink path. (ii) The command exits 1 printing only an import error; the outcome is `SCAN_FAILED`, not `SECRET_FOUND`.
4. Full suite green. Merge.

Acceptance:
- `check: pytest tests/test_desk001_desktop_commit.py -q`
- `check: ! grep -n "command\[0\]).resolve()" seldon/core/desktop_commit.py`

## Part B: the held handoff comes back through the fixed path

1. Copy `/Users/brock/GitHub/workbench/parked/2026-10-17_desktop_sq8_friction_class_ad038_work_order.md` to `handoffs/` (same basename). Leave the parked copy.
2. `seldon commit-governed handoffs/2026-10-17_desktop_sq8_friction_class_ad038_work_order.md` from main after the Part A merge. It must commit (the scan now runs under the venv and finds nothing). If the scan flags a real secret, stop and file an issue naming the line number only.
3. Close `cf57b8e5` with the commit sha.

Acceptance:
- `check: git ls-files --error-unmatch handoffs/2026-10-17_desktop_sq8_friction_class_ad038_work_order.md`

## Report

RESULT under 15 lines: the two edits, the two tests' names, the handoff commit sha, tokens against 0.12M. Then `seldon verify`, `seldon cc complete`, merge, push.
