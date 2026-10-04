"""SEL-002 Part E, step 1 (Seldon's environment): export the records that get a stand-alone statement.

    python scripts/sel002/statements_export.py

Every ACTIVE record (proposed or accepted) of the three registers that carries a statement of its own
(not a mirror, FC-16), in a deterministic order, with its verbatim source. Writes
evidence/sel002/statements/units.jsonl. The model work runs in Squiddy's environment
(scripts/sel002/statements.py), which reads only this file; the amend records are written back here
(scripts/sel002/statements_apply.py) through the one write path. Zero model calls.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

SELDON = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SELDON))

import yaml  # noqa: E402

from seldon.core import decisions as dr  # noqa: E402

OUT = SELDON / "evidence" / "sel002" / "statements" / "units.jsonl"


def main() -> int:
    u = dr.universe(SELDON, yaml.safe_load((SELDON / "seldon.yaml").read_text()))
    rows = []
    for repo in ("squiddy", "seldon", "arnold"):
        for rec in dr.list_records(u, [repo]):
            if rec.status not in dr.ACTIVE or rec.get("kind") == "mirror":
                continue
            text = (rec.get("source") or {}).get("text") or ""
            rows.append({"id": rec.id, "kind": rec.get("kind"), "status": rec.status,
                         "source_text": text, "source_sha256": hashlib.sha256(text.encode()).hexdigest(),
                         "chars": len(text)})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(f"{len(rows)} records to state ({sum(r['chars'] for r in rows):,} source characters) -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
