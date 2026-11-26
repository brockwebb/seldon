#!/bin/sh
# SEL-048's runs, in the task's order, one at a time (no run beside another, so none adds load to the next).
# Launched detached under `caffeinate -i`; each run appends its own line to runs.jsonl.
cd "$(dirname "$0")/../../.." || exit 2
R="python docs/evidence/sel048/run.py"
POLLUTER="tests/test_sel008_cross_project_waits_and_block_reason.py::test_task_show_prints_the_edge_with_the_other_tasks_state_and_the_precedes_edges"
VICTIM="tests/test_sel018_relative_dispatch_paths.py::test_dispatch_status_reads_the_cap_from_a_worktree"

# Part B: the polluter then the victim, fixed order, three times; then the file alone (its acceptance).
for i in 1 2 3; do $R "sel018_polluter_then_victim_$i" -p no:randomly -v "$POLLUTER" "$VICTIM"; done
$R sel018_file_alone_1 -q tests/test_sel018_relative_dispatch_paths.py

# Part A: the sel024 file alone, ten times (the gate's form: random order left on, as gate_command runs).
for i in 01 02 03 04 05 06 07 08 09 10; do $R "sel024_alone_$i" -v tests/test_sel024_gate_record.py; done

# Part C: the dispatch_parallel file alone, once.
$R union_merge_file_alone_1 -v tests/test_dispatch_parallel.py
echo "SEQUENCE EXIT"
