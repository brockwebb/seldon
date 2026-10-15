"""SEL-006 Part C: write `qc.parts_baseline` for a project from its own graph (Issue f6c69653).

AD-037-R6 (c)'s `parts_undeclared` gate applies to a project once its seldon.yaml names
`qc.parts_baseline`: the task files registered before the gate, which are not re-checked for a
`**Parts:**` header (`seldon.core.stations.parts_registration_refusal`). Seldon's own list was read
the same way in QC-002 (`docs/evidence/qc002/parts_baseline.txt`, premise 9). Zero model calls; one
read-only Cypher query per project.

    python -m dotenv -f .env run -- python scripts/sel006/write_parts_baselines.py <project dir> [...]

Writes `<project>/docs/evidence/sel006/parts_baseline.txt` and prints the count. The seldon.yaml line
is added by hand (an edit, so the diff stays reviewable).
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from seldon.config import get_neo4j_driver, load_project_config

OUT = Path("docs/evidence/sel006/parts_baseline.txt")


def baseline(project: Path) -> list[str]:
    config = load_project_config(project)
    driver = get_neo4j_driver(config)
    try:
        with driver.session(database=config["neo4j"]["database"]) as s:
            rows = s.run("MATCH (t:Artifact:ResearchTask) WHERE t.source_file IS NOT NULL "
                         "RETURN DISTINCT t.source_file AS f").values()
    finally:
        driver.close()
    return sorted({r[0] for r in rows if r[0]})


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    for arg in argv:
        project = Path(arg).expanduser().resolve()
        files = baseline(project)
        if not files:
            raise SystemExit(f"FATAL: {project}: its graph holds no registered task; refusing to write an empty "
                             f"baseline (every task would then be held to the gate, which may be right, but say so)")
        out = project / OUT
        out.parent.mkdir(parents=True, exist_ok=True)
        head = (f"# AD-037-R6 (c) baseline (seldon SEL-006 Part C, Issue f6c69653): every task file registered in "
                f"{project.name}'s graph before the gate, read {date.today().isoformat()} from "
                f"(:ResearchTask).source_file\n# by seldon/scripts/sel006/write_parts_baselines.py. A listed task is "
                f"not re-checked for a `**Parts:**` header.\n")
        out.write_text(head + "\n".join(files) + "\n", encoding="utf-8")
        print(f"{project.name}: {len(files)} task file(s) -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
