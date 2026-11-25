"""SEL-047 Part C: what pa002's live-library test compares, printed side by side (reads squiddy's library; writes only a
temporary directory). Run from the worktree root with PYTHONPATH=. and the primary's .env."""
import json
import tempfile
from pathlib import Path

from seldon.config import load_project_config
from seldon.core import prior_art as pa

root = Path(".").resolve()
s = pa.settings(root, load_project_config(root))
lib = pa.Library(s)
served = json.loads((s.library_graph / "work/index/index_manifest.json").read_text())
with tempfile.TemporaryDirectory() as t:
    info = pa.rebuild_release(lib.graph(), served["release"]["sha256"], Path(t))
print(json.dumps({"library_graph": str(s.library_graph), "served_release": served["release"],
                  "served_rows": served["rows"], "rebuilt_rows": info["rows"],
                  "served_row_fingerprint": served["row_fingerprint"], "rebuilt_row_fingerprint": info["row_fingerprint"],
                  "served_shard_set_sha256": served["dense"]["shard_set_sha256"],
                  "rebuilt_shard_set_sha256": info["shard_set_sha256"], "release_commit": info["commit"],
                  "rebuilt_shards": len(info["shards"]), "served_manifest_keys": sorted(served)}, indent=1))
