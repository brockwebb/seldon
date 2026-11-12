#!/bin/sh
# SEL-037 Part A/C: stage a seldon-biblio release's GITIGNORED outputs under the graph's archive root, then install
# them into the primary checkout. The release's tracked record (manifest, ledger, evidence, exports/*.md) arrives with
# the merge; these files never do, because they are ignored (graphs/seldon-biblio/.gitignore). `dispatch.worktree_links`
# cannot carry them (seldon.yaml, tests/test_sel037_worktree_links_exports.py), so a release built in a worktree is
# installed by copy: the route SEL-036 staged and SEL-037 Part A ran.
#
#   sh scripts/sel037/stage_release.sh <release label> <primary checkout>
#
# Copies only: the parse intermediates, the exports' JSON and KGX files, the served index and the factory records.
# Nothing in the primary is deleted; an older release's versioned exports stay, because a receipt may name them.
set -eu
REL=$1
PRIMARY=$2
G=graphs/seldon-biblio
ARCH="$HOME/kg-archive/seldon-biblio/build_outputs/$REL"
test -f "$G/exports/seldon_biblio_graph.json" || { echo "FATAL: no served export in $G/exports" >&2; exit 2; }
test -d "$PRIMARY/$G" || { echo "FATAL: $PRIMARY/$G is not the graph" >&2; exit 2; }
mkdir -p "$ARCH/corpus" "$ARCH/exports" "$ARCH/work" "$ARCH/factory"
cp -R "$G/corpus/parsed" "$ARCH/corpus/"
cp "$G"/exports/*.json "$G"/exports/*.jsonl "$ARCH/exports/"
cp -R "$G/work/index" "$ARCH/work/"
cp -R "$G/factory/records" "$ARCH/factory/"
echo "staged $REL at $ARCH"
cp -R "$ARCH/." "$PRIMARY/$G/"
echo "installed $REL into $PRIMARY/$G"
