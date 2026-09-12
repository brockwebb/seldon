#!/bin/sh
# Reset the governed graph to "nothing has ever been admitted": empty manifest, empty ledger, no
# evidence, no caches. The four governed files themselves are never touched.
#
# This exists because a partial reset is worse than none: stage records left behind make `make`
# skip the stages that would have recomputed the manifest, and the ledger then records a document
# state that no stage actually decided.
set -eu
GRAPH="$(cd "$(dirname "$0")" && pwd)"
rm -rf "$GRAPH/evidence" "$GRAPH/work" "$GRAPH/ledger" "$GRAPH/exports" \
       "$GRAPH/corpus/parsed" "$GRAPH/corpus/resolved" "$GRAPH/corpus/acquisition_state.json"
mkdir -p "$GRAPH/evidence" "$GRAPH/work" "$GRAPH/ledger" "$GRAPH/exports"
cat > "$GRAPH/corpus/manifest.yaml" <<'MANIFEST'
# The governed-documents manifest: one entry per governed markdown file ever considered (AD-030-R5).
#
# NEVER HAND-EDITED. `squiddy catalog` appends entries from `catalog_governed.py`'s enumeration of
# the four governed directories; `squiddy.assess` writes the decision; `squiddy.acquire` writes the
# hash and the byte count; `squiddy.write` flips the stage on the far side of the append. A field
# set by hand here is a claim no stage made, and the manifest-to-ledger gate will disagree with it.

schema:
  profile: seldon-governed-documents-manifest

metadata:
  policy: local_authored
  governed_by: docs/design/AD-030_governed_documents_as_graph_content.md

documents: []
MANIFEST
echo "reset $GRAPH: empty manifest, empty ledger, no evidence"
