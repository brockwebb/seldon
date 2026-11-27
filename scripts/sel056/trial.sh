#!/bin/bash
# SEL-056: rehearse the coarse-tier adoption on a scratch copy of graphs/seldon-biblio before touching the tracked one.
# Usage: scripts/sel056/trial.sh <scratch dir>   (copies graphs/seldon-biblio into it; writes nothing in the repository)
set -uo pipefail
here="$(cd "$(dirname "$0")/../.." && pwd)"
sq="$here/scripts/sel056/sq.sh"
scratch="${1:?usage: trial.sh <scratch dir>}"
rm -rf "$scratch" && mkdir -p "$scratch"
cp -R "$here/graphs/seldon-biblio" "$scratch/"
g="$scratch/seldon-biblio"
python3 - "$g/graph.yaml" <<'EOF'
import sys
p = sys.argv[1]; s = open(p).read()
s = s.replace("  - ExpressionOf: Edge\n", "  - ExpressionOf: Edge\n  - Passage: Node\n  - PassageOf: Edge\n", 1)
s = s.replace("\nemit:\n", "\ntiers:\n  coarse: [active]\nemit:\n", 1)
open(p, "w").write(s)
EOF
echo "== render"; "$sq" init "$g" --render --allow-schema-change 2>&1 | tail -3; echo "EXIT ${PIPESTATUS[0]}"
echo "== declare"; "$sq" schema declare --graph "$g" --by SEL-056 2>&1 | tail -3; echo "EXIT ${PIPESTATUS[0]}"
echo "== check"; "$sq" init "$g" --check 2>&1 | head -8; echo "EXIT ${PIPESTATUS[0]}"
echo "== tier"; "$sq" passage tier --graph "$g" 2>&1 | tail -3; echo "EXIT ${PIPESTATUS[0]}"
