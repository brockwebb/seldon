#!/bin/sh
# SEL-048 addition: the lock_wait test under induced CPU contention, the trigger SEL-047 named (Part B: the old
# fixed 6 s window failed whenever the filing took longer under load). Usage: stress.sh <run name> <hogs> <test file>
# Starts <hogs> busy-loop processes (10 cores here), runs the one test through run.py, then stops the hogs.
cd "$(dirname "$0")/../../.." || exit 2
name=$1; hogs=$2; file=$3
pids=""
i=0
while [ "$i" -lt "$hogs" ]; do
  python -c "while True: pass" &
  pids="$pids $!"
  i=$((i + 1))
done
sleep 20   # let the 1-minute load average climb before the run records load_before
python docs/evidence/sel048/run.py "$name" -v -p no:randomly \
  "$file::test_fixture_a_regate_whose_gate_outlasts_lock_wait_does_not_refuse_a_concurrent_filing"
rc=$?
kill $pids
echo "STRESS EXIT $rc"
