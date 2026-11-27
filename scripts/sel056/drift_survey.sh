#!/bin/bash
# SEL-056: `squiddy init --check` (read-only) over the consumer graphs that declare none of SQ-151's classes, to see
# whether SQ-151's base.yaml comment block alone drifts their rendered schema (R-290 says no existing schema changes).
# Usage: scripts/sel056/drift_survey.sh <graph dir> ...
set -uo pipefail
sq="$(cd "$(dirname "$0")" && pwd)/sq.sh"
for g in "$@"; do
  echo "== $g"
  "$sq" init "$g" --check 2>&1 | grep -E "^[a-z-]+ " | head -4
done
