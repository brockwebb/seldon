#!/bin/bash
# SEL-056: the graph-scope conformance gates on two scratch copies of the primary checkout's graphs/seldon-biblio
# (tracked files plus its gitignored exports, parsed texts and index, which a worktree does not hold): one as it is
# on main, one with the coarse tier adopted. Read-only on the repository; the scratch copies take the writes.
# Usage: scripts/sel056/conformance_pair.sh <scratch dir>
set -uo pipefail
here="$(cd "$(dirname "$0")/../.." && pwd)"
sq="$here/scripts/sel056/sq.sh"
py=/Users/brock/GitHub/squiddy/.venv/bin/python
primary="${SELDON_PRIMARY_CHECKOUT:?SELDON_PRIMARY_CHECKOUT is not set}"
scratch="${1:?usage: conformance_pair.sh <scratch dir>}"
rm -rf "$scratch" && mkdir -p "$scratch/base" "$scratch/adopt"
cp -R "$primary/graphs/seldon-biblio" "$scratch/base/"
cp -R "$primary/graphs/seldon-biblio" "$scratch/adopt/"
# the adopted copy takes this branch's tracked spec and rendered files
cp "$here/graphs/seldon-biblio/graph.yaml" "$scratch/adopt/seldon-biblio/graph.yaml"
"$sq" init "$scratch/adopt/seldon-biblio" --render --allow-schema-change > "$scratch/adopt_render.log" 2>&1
echo "render EXIT $?"
"$sq" schema declare --graph "$scratch/adopt/seldon-biblio" --by SEL-056 > "$scratch/adopt_declare.log" 2>&1
echo "declare EXIT $?"
for arm in base adopt; do
  ( cd "$scratch/$arm" && "$py" -m squiddy.conformance run --graph seldon-biblio --scope graph \
      --json "$scratch/$arm.json" > "$scratch/$arm.log" 2>&1 )
  echo "$arm conformance EXIT $?"
done
