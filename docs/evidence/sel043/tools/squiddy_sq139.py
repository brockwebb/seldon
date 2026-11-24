"""Run squiddy's SQ-139 release-receipt tests with this branch's seldon first on the path (read only in squiddy)."""
import os
import subprocess

WT = "/Users/brock/GitHub/seldon/.claude/worktrees/iterative-moseying-clock"
SQ = "/Users/brock/GitHub/squiddy"
env = {**os.environ, "PYTHONPATH": WT}
r = subprocess.run([f"{SQ}/.venv/bin/python", "-c", "import seldon, sys; print(seldon.__file__)"], cwd=SQ, env=env,
                   capture_output=True, text=True)
print("seldon imported from:", r.stdout.strip())
r = subprocess.run([f"{SQ}/.venv/bin/python", "-m", "pytest", "-q", "-p", "no:cacheprovider",
                    "tests/test_sq139_release_receipt_stage.py", "tests/test_sq124_gate_record.py", "tests/test_sq100_exclusion_currency_hold.py", "tests/test_sq096_pass_ledger_fork.py", "tests/test_suite001_declared_interpreter.py", "tests/test_sq010_holder_leases.py", "tests/test_sq139_index_reader_agrees_with_builder.py", "tests/test_sq015_completion_is_a_verifying_trace.py"], cwd=SQ, env=env, capture_output=True, text=True,
                   timeout=1800)
print(r.stdout[-1200:], r.stderr[-600:])
print("EXIT", r.returncode)
