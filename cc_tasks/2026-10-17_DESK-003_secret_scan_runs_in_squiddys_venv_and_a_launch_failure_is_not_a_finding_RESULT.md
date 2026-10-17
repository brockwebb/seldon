# DESK-003 RESULT

**Task:** `cc_tasks/2026-10-17_DESK-003_secret_scan_runs_in_squiddys_venv_and_a_launch_failure_is_not_a_finding.md` (no addenda). **Governing:** DESK-001, AD-038-R1, AD-038-R6.

- Edit 1, `seldon/core/desktop_commit.py` `settings()`: a relative scan program is absolutized with `os.path.normpath(project_dir / command[0])`, not `resolve()`, so `../squiddy/.venv/bin/python` stays the venv launcher.
- Edit 2, `_scan()`: exit 1 is `secret_found` only when stdout carries the scanner's trailer (`SCAN_FOUND_TRAILER`, `scanned N file(s); exit 1`); any other non-zero, including a bare exit 1, is `scan_failed` with stderr verbatim. `seldon.yaml` comment updated to match.
- Tests (each failed on HEAD): `test_a_relative_scan_program_keeps_its_symlink_path`, `test_a_scanner_that_did_not_run_is_scan_failed_not_secret_found`. The existing `test_the_secret_scan_refuses_a_flagged_handoff` stub now prints the real trailer.
- Full suite: 2608 passed (26:00). Fix 352fab6, merge e3a3317.
- Part B: the parked handoff was copied to `handoffs/` (the parked copy is still there). `seldon commit-governed` committed it at **4f268e1**, and the real scanner reported `scanned 1 file(s); exit 0`. Issue cf57b8e5 is resolved and names both shas.
- Stations: part-complete A (65,475 tokens) and B (69,110 tokens) both exited 0.
- Tokens: about 0.07M of the 0.12M estimate.
