#!/bin/sh
# SEL-043 ADDENDUM 01 step 2: run a slice of the test files that sort before the two friction002 files, then those
# two files, serially, as gate_command runs them. Usage: bisect_run.sh <label> <first index> <last index> [tree]
# (1-based, over the sorted files before tests/test_friction002_stop_hook_gate.py; [tree] defaults to the current
# directory, and was /tmp/sel043_tip, an export of the unfixed replayed tip, once the fix was in the worktree).
# Writes /tmp/sel043_bisect/<label>.log and a final EXIT line.
label=$1; lo=$2; hi=$3; tree=${4:-.}
out=/tmp/sel043_bisect; mkdir -p "$out"
cd "$tree" || exit 2
files=$(ls tests/test_*.py | sort | awk '$0 < "tests/test_friction002_stop_hook_gate.py"' | sed -n "${lo},${hi}p")
echo "$files" > "$out/$label.files"
python -m dotenv -f "$SELDON_PRIMARY_CHECKOUT/.env" run -- env PYTHONPATH=. python -m pytest $files \
  tests/test_friction002_stop_hook_gate.py tests/test_friction002_worktree_only.py -q -p no:cacheprovider \
  --deselect tests/test_pa002_release_resolve.py::test_rebuilding_the_served_release_reproduces_the_served_index \
  > "$out/$label.log" 2>&1
echo "EXIT $?" >> "$out/$label.log"
