#!/usr/bin/env python3
"""
Backfill updated_at on existing Artifact nodes.

Strategy: for any Artifact missing updated_at, set it to created_at (if
present) or to the migration timestamp (if created_at is also missing).

Idempotent: skips nodes that already have updated_at.

Usage:
    python scripts/migrations/2026-04-18_backfill_updated_at.py [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add repo root to path so we can import seldon
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from seldon.config import load_project_config, get_neo4j_driver


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would change; do not write.")
    parser.add_argument("--project-dir", type=Path, default=Path.cwd(),
                        help="Project root (default: cwd).")
    args = parser.parse_args()

    config = load_project_config(args.project_dir)
    driver = get_neo4j_driver(config)
    database = config["neo4j"]["database"]

    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        with driver.session(database=database) as session:
            # Count candidates
            count_result = session.run(
                "MATCH (a:Artifact) WHERE a.updated_at IS NULL RETURN count(a) AS n"
            ).single()
            n_missing = count_result["n"]
            print(f"Nodes missing updated_at: {n_missing}")

            if args.dry_run or n_missing == 0:
                print("Dry run or nothing to do — exiting.")
                return

            # Backfill: prefer created_at, fallback to migration timestamp
            result = session.run(
                """
                MATCH (a:Artifact)
                WHERE a.updated_at IS NULL
                SET a.updated_at = coalesce(a.created_at, $now_iso)
                RETURN count(a) AS updated
                """,
                now_iso=now_iso,
            ).single()
            print(f"Backfilled: {result['updated']} nodes")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
