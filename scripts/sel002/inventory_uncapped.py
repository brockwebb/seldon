"""Run the decision probe's own parser with its truncation caps lifted (SEL-002 Part B).

The seed reuses the probe's `inventory.py` (copied byte for byte to evidence/sel002/inventory/,
sha256 recorded); no second parser is written. Two caps in it truncate long units at 2,500
characters, which is why the probe lists DI-170 to DI-178 as truncated. SEL-002 says a record's
`source` carries the full body, so this runs the same source with exactly those two caps lifted
(each replacement asserted to occur once) and writes units_full.jsonl beside the capped output.
Zero model calls, no network.

    python scripts/sel002/inventory_uncapped.py /Users/brock/GitHub
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[2] / "evidence" / "sel002" / "inventory"
PATCHES = [
    ('u["text"] = "\\n".join(u["text"]).strip()[:2500]', 'u["text"] = "\\n".join(u["text"]).strip()'),
    ("end = labeled[j + 1].start() if j + 1 < len(labeled) else min(len(txt), m.start() + 2500)",
     "end = labeled[j + 1].start() if j + 1 < len(labeled) else len(txt)"),
    ('(OUT / "units.jsonl")', '(OUT / "units_full.jsonl")'),
    ('(OUT / "inventory_report.json")', '(OUT / "inventory_report_full.json")'),
]


def main(gh: str) -> None:
    src = (HERE / "inventory.py").read_text(encoding="utf-8")
    for old, new in PATCHES:
        assert src.count(old) == 1, f"patch target not found exactly once: {old}"
        src = src.replace(old, new)
    sys.argv = ["inventory.py", gh]
    code = compile(src, str(HERE / "inventory.py"), "exec")
    exec(code, {"__name__": "__main__", "__file__": str(HERE / "inventory.py")})


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(Path.home() / "GitHub"))
