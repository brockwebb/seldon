"""MODEL-003 squiddy guard: run squiddy's test_the_shim_sees_a_planted_call_and_the_gate_stops_one unchanged, except
that its nested run's PYTHONPATH also carries the seldon worktree under test (the test's `_env` sets PYTHONPATH to
squiddy's root only, so under a PYTHONPATH-based test the nested run imported the main checkout's seldon while
reading the worktree's registry: mixed versions, not the change under test)."""
import os, sys, tempfile
from pathlib import Path
sys.path.insert(0, "/Users/brock/GitHub/squiddy")
import tests.test_pa001_zero_model_calls as t
orig = t._env
def _env(bindir, home):
    env = orig(bindir, home)
    env["PYTHONPATH"] = os.pathsep.join(["/Users/brock/GitHub/seldon-model003", env["PYTHONPATH"]])
    return env
t._env = _env
t.test_the_shim_sees_a_planted_call_and_the_gate_stops_one(Path(tempfile.mkdtemp(prefix="model003-shim-")))
print("PASSED test_the_shim_sees_a_planted_call_and_the_gate_stops_one (worktree seldon in the nested run)")
