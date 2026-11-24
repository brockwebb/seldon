#!/bin/sh
# SEL-043 Part A(3): seconds and peak RSS (children included) of seldon's AD-036-R9 instrument, run alone, 3 times.
cd /Users/brock/GitHub/seldon/.claude/worktrees/iterative-moseying-clock || exit 9
for i in 1 2 3; do
  /usr/bin/time -l python -m dotenv -f .env run -- python -m pytest -q -p no:cacheprovider \
    "tests/test_no_live_model_calls.py::test_the_launcher_adjacent_suite_makes_zero_claude_calls" \
    > /tmp/sel043/r9_run_$i.txt 2>&1
  echo "RUN $i EXIT=$?" >> /tmp/sel043/r9_runs.txt
done
echo "EXIT=done" >> /tmp/sel043/r9_runs.txt
