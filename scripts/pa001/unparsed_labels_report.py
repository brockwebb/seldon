"""PA-001 Part F: run the `ruling_label_unparsed` check over every repository whose seldon.yaml
has a `decisions:` block, reading every note (not only those after the baseline), and write the
findings. Report only: PA-001 does not fix the notes it catches. Zero model calls.

    python scripts/pa001/unparsed_labels_report.py
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from seldon.core import decisions as dr

GITHUB = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parents[2] / "docs" / "evidence" / "pa001" / "unparsed_labels_all_repos.json"


def main() -> int:
    report = {}
    for cfg_path in sorted(GITHUB.glob("*/seldon.yaml")):
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        if not isinstance(cfg.get("decisions"), dict):
            continue
        s = dr.settings(cfg_path.parent, cfg)
        report[cfg_path.parent.name] = {
            "after_baseline": [list(x) for x in dr.unparsed_labels(s)],
            "all_notes": [list(x) for x in dr.unparsed_labels(s, all_notes=True)]}
    OUT.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    for repo, r in report.items():
        print(repo, "after baseline:", len(r["after_baseline"]), "all notes:", len(r["all_notes"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
