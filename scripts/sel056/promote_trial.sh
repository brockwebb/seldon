#!/bin/bash
# SEL-056: on the adopted scratch copy conformance_pair.sh made, refuse a whole extraction of a coarse entry, promote
# one cited passage, promote it again (idempotence), refuse a quote that is not in the text, then re-run item 42.
# Usage: scripts/sel056/promote_trial.sh <scratch dir given to conformance_pair.sh>
set -uo pipefail
here="$(cd "$(dirname "$0")/../.." && pwd)"
sq="$here/scripts/sel056/sq.sh"
py=/Users/brock/GitHub/squiddy/.venv/bin/python
scratch="${1:?usage: promote_trial.sh <scratch dir>}"
cd "$scratch/adopt" || exit 2
quote="an objective function that is too expensive to evaluate frequently"
echo "== whole extraction of a coarse entry (expect refusal)"
"$sq" extract --graph seldon-biblio --id amodei2016concrete 2>&1 | tail -2; echo "EXIT ${PIPESTATUS[0]}"
for n in 1 2; do
  echo "== promote ($n)"
  "$sq" passage promote --graph seldon-biblio --id amodei2016concrete --exact "$quote" \
      --for "SEL-056 rehearsal: a quote a ruling would cite" --by SEL-056 2>&1 | tail -3; echo "EXIT ${PIPESTATUS[0]}"
done
echo "== promote a quote not in the text (expect refusal)"
"$sq" passage promote --graph seldon-biblio --id amodei2016concrete --exact "not a sentence Amodei et al. wrote" \
    --for "SEL-056 rehearsal" --by SEL-056 2>&1 | tail -2; echo "EXIT ${PIPESTATUS[0]}"
echo "== Passage events in the ledger"
grep -c '"Passage"' seldon-biblio/ledger/*.jsonl
echo "== item 42"
"$py" -m squiddy.conformance run --graph seldon-biblio --scope graph --gate passages_grounded 2>&1 | tail -3
echo "EXIT ${PIPESTATUS[0]}"
