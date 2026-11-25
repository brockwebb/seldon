"""SEL-047 Part C: does today's `squiddy.index.row_fingerprint`, run on the SERVED index's own database, still give the
fingerprint the served manifest recorded? If yes, the rebuilt rows differ in content from the served rows; if no, the
fingerprint (or the served database) changed after the manifest was written. Reads only."""
import json
from pathlib import Path

from squiddy import index as ix

from seldon.config import load_project_config
from seldon.core import prior_art as pa

root = Path(".").resolve()
s = pa.settings(root, load_project_config(root))
idx = s.library_graph / "work" / "index"
served = json.loads((idx / "index_manifest.json").read_text())
db = served.get("db") or {}
db_path = Path(db.get("path")) if isinstance(db, dict) and db.get("path") else None
if db_path is not None and not db_path.is_absolute():
    db_path = s.library_graph / db_path
cands = [db_path] if db_path else sorted(idx.glob("*.db"))
out = {"built_utc": served.get("built_utc"), "manifest_db": db, "manifest_row_fingerprint": served["row_fingerprint"]}
for p in cands:
    if p and p.is_file():
        out[str(p)] = {"row_fingerprint_now": ix.row_fingerprint(p), "mtime": p.stat().st_mtime}
print(json.dumps(out, indent=1, default=str))
