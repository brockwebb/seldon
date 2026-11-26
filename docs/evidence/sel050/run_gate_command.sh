#!/bin/sh
# SEL-050 Part B step 2: run `dispatch.gate_command` exactly as seldon.yaml reads it, from this worktree's root.
# Output: docs/evidence/sel050/full_run.log (whole run) and an EXIT line with pytest's exit status and wall seconds.
cd "$(dirname "$0")/../../.." || exit 2
cmd=$(python -c 'import yaml; print(yaml.safe_load(open("seldon.yaml"))["dispatch"]["gate_command"])') || exit 2
log=docs/evidence/sel050/full_run.log
{
  echo "command: $cmd"
  echo "start: $(date '+%Y-%m-%d %H:%M:%S %Z')"
} > "$log"
t0=$(date +%s)
sh -c "$cmd" >> "$log" 2>&1
rc=$?
echo "EXIT $rc after $(( $(date +%s) - t0 )) s, end $(date '+%Y-%m-%d %H:%M:%S %Z')" >> "$log"
