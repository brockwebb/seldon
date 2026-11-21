# SEL-041 Part C: does testmon earn a place on seldon's suite?

pytest-testmon 2.3.1 installed into a scratch environment (`/tmp/sel041/tm`, `--system-site-packages`; never into the
shared one), run on a shared clone of this branch under `/tmp` with seldon's siblings symlinked beside it
(`tm_build.py`). Measured 2026-11-21.

1. **The map builds under xdist.** `pytest tests/ --testmon -n 6` built `.testmondata` (2.7 MB) in 3,167 s (52:47):
   3,476 passed, 5 failed, all five known on main under load (`tm_build_summary.txt`: sel024 lock_wait, three
   `test_dispatch_parallel` timing tests, pa002 library drift). The same suite without testmon took a median of
   1,680 s over its last 19 runs (`../README.md`), so the map costs about 1.9 times a full gate, under a load average
   that reached 65 during the build.
2. **In-process changes: 20 of 20 right.** Twenty functions in `seldon/core` and `seldon/commands`, picked every 25th
   of the 501 with one to three test files calling them by name (`tm_seeds.py`), each seeded with a no-op first line;
   testmon's selection (`--testmon-nocollect --collect-only`) included the calling test file 19 times. The 20th,
   `project_new.launchctl`, is replaced by a fake in its only caller (`test_sel019_project_new.py`,
   `monkeypatch.setattr(PN, "launchctl", fake)`), so the real function never runs there and not selecting the file is
   correct. Selections ranged from 3 to 58 test files of 196.
3. **Subprocess changes: 2 of 41.** `seldon hooks pre-commit` runs only inside `git commit` -> `.githooks/pre-commit`
   -> `python -m seldon hooks pre-commit`, a grandchild of the test process. 41 test files build a scaffold project
   (which installs the commit gate) and commit through it without naming the hook. With the command's body seeded,
   testmon selected 3 files in all and 2 of the 41 (`tm_sub.py`, `tm_sub.json`): 39 misses.

**Verdict: the arm is left out.** The task's bar was "any miss ... and the arm is reported and left out". Selection
is right for code a test runs in its own process and blind to code run through git hooks and other grandchild
processes, which is how seldon's dispatcher, hooks and stations are exercised. `dispatch.gate.coverage_map` accepts
`none` only (`seldon/core/gate_plan.py`, `COVERAGE_MAPS`); declared slices ship alone (AD-034-R30).
