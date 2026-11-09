"""SEL-036 Part E (1): write each governed Citation's `resolves_to` link to the seldon-biblio entry it names.

    python -m dotenv -f <seldon>/.env run -- python scripts/sel036/bridge.py --dry-run
    python -m dotenv -f <seldon>/.env run -- python scripts/sel036/bridge.py --json graphs/seldon-biblio/evidence/sel036/bridge.json

Run from the seldon checkout's root. The map is the seed file's `governed:` block, the entries are the catalog
(`corpus/candidates/seldon_biblio_candidates.yaml`), the database is seldon.yaml's `neo4j.database`. The writer is
`seldon.core.biblio_bridge.bridge` (AD-036-R22): idempotent, through the event store. Zero network, zero model calls.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from seldon.config import get_current_session, get_neo4j_driver, load_project_config  # noqa: E402
from seldon.core import biblio_bridge as bb  # noqa: E402
from seldon.domain.loader import load_domain_config  # noqa: E402

GRAPH = ROOT / "graphs" / "seldon-biblio"
SEEDS = GRAPH / "intake" / "seeds.yaml"
CANDIDATES = GRAPH / "corpus" / "candidates" / "seldon_biblio_candidates.yaml"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", type=Path)
    a = ap.parse_args(argv)
    config = load_project_config(ROOT)
    governed = yaml.safe_load(SEEDS.read_text(encoding="utf-8"))["governed"]
    entries = {e["id"]: e for e in yaml.safe_load(CANDIDATES.read_text(encoding="utf-8"))["candidates"]}
    domain = load_domain_config(ROOT / "seldon" / "domain" / f"{config['project'].get('domain', 'research')}.yaml")
    driver = get_neo4j_driver(config)
    try:
        rep = bb.bridge(ROOT, driver, config["neo4j"]["database"], domain, governed, entries, GRAPH.name,
                        actor="cc:91998dc1", authority="accepted", session_id=get_current_session(ROOT),
                        dry_run=a.dry_run)
    finally:
        driver.close()
    out = {"dry_run": a.dry_run, "database": config["neo4j"]["database"], **rep.as_dict()}
    print(json.dumps({k: (v if not isinstance(v, list) else len(v)) for k, v in out.items()}, indent=1))
    if a.json:
        a.json.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return 1 if rep.citations_missing or rep.entries_missing else 0


if __name__ == "__main__":
    sys.exit(main())
