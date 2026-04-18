#!/usr/bin/env python3
"""
Seldon Observability Collector — nightly_collector_v1

Collects Tier 1 (growth) and Tier 2 (curation) metrics from:
  - Neo4j project databases (node/edge counts, artifact states, stale items)
  - Seldon event log JSONL (event counts per project)
  - Filesystem signals (handoffs, cc_tasks)
  - Claude Code session JSONL (~/.claude/projects/) for token attribution

Writes insert-only rows to ~/.seldon-observability/metrics.db.
Safe to re-run: each run inserts a new timestamped snapshot.

Schema contract (see cc4_dashboard_design.md):
  metrics(id, timestamp, metric_name, scope, metric_value, dimensions, collected_by)
"""

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import yaml  # PyYAML — already in Seldon venv

DB_PATH = Path.home() / ".seldon-observability" / "metrics.db"
COLLECTOR_ID = "nightly_collector_v1"
GITHUB_ROOT = Path("/Users/brock/Documents/GitHub")
CLAUDE_PROJECTS_ROOT = Path.home() / ".claude" / "projects"

# Excluded databases
EXCLUDED_DBS = {"seldon-ontology", "seldon-test", "seldon-test-project",
                "neo4j", "system"}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS metrics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp TEXT NOT NULL,
  metric_name TEXT NOT NULL,
  metric_value REAL NOT NULL,
  scope TEXT NOT NULL,
  dimensions TEXT,
  collected_by TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_metrics_name_scope_time
  ON metrics(metric_name, scope, timestamp);
CREATE INDEX IF NOT EXISTS idx_metrics_timestamp
  ON metrics(timestamp);
"""


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn


def insert_metric(conn: sqlite3.Connection, ts: str, name: str, value: float,
                  scope: str, dimensions: Optional[dict] = None) -> None:
    dims_json = json.dumps(dimensions) if dimensions else None
    conn.execute(
        "INSERT INTO metrics(timestamp, metric_name, metric_value, scope, "
        "dimensions, collected_by) VALUES (?,?,?,?,?,?)",
        (ts, name, value, scope, dims_json, COLLECTOR_ID),
    )


# ---------------------------------------------------------------------------
# Project discovery
# ---------------------------------------------------------------------------

def discover_projects() -> list[dict]:
    """Return list of {slug, project_dir, db_name, event_log} dicts."""
    projects = []
    patterns = [
        GITHUB_ROOT / "*" / "seldon.yaml",
        GITHUB_ROOT / "*" / "*" / "seldon.yaml",
    ]
    for pattern in patterns:
        for yaml_path in sorted(GITHUB_ROOT.glob(str(pattern.relative_to(GITHUB_ROOT)))):
            try:
                config = yaml.safe_load(yaml_path.read_text())
                slug = config.get("project", {}).get("slug", yaml_path.parent.name)
                db_name = config.get("neo4j", {}).get("database", f"seldon-{slug}")
                event_log_rel = config.get("event_store", {}).get("path", "seldon_events.jsonl")
                event_log = yaml_path.parent / event_log_rel
                projects.append({
                    "slug": slug,
                    "project_dir": yaml_path.parent,
                    "db_name": db_name,
                    "event_log": event_log,
                    "seldon_yaml": yaml_path,
                })
            except Exception as e:
                print(f"  [warn] Could not parse {yaml_path}: {e}", file=sys.stderr)
    # Deduplicate by db_name
    seen = set()
    unique = []
    for p in projects:
        key = p["db_name"]
        if key not in seen and key not in EXCLUDED_DBS:
            seen.add(key)
            unique.append(p)
    return unique


# ---------------------------------------------------------------------------
# Neo4j collection
# ---------------------------------------------------------------------------

def collect_neo4j(conn: sqlite3.Connection, ts: str, projects: list[dict]) -> None:
    try:
        from neo4j import GraphDatabase
        from dotenv import load_dotenv
    except ImportError as e:
        print(f"  [error] Missing dependency: {e}. Neo4j metrics skipped.", file=sys.stderr)
        return

    # Load credentials
    env_path = GITHUB_ROOT / "seldon" / ".env"
    load_dotenv(env_path)
    password = os.getenv("NEO4J_PASSWORD")
    if not password:
        print("  [error] NEO4J_PASSWORD not set. Neo4j metrics skipped.", file=sys.stderr)
        return

    uri = "bolt://localhost:7687"
    try:
        driver = GraphDatabase.driver(uri, auth=("neo4j", password))
        # Quick connectivity check against a user database (system DB doesn't allow RETURN 1)
        with driver.session(database="neo4j") as s:
            s.run("RETURN 1").consume()
    except Exception as e:
        print(f"  [error] Neo4j connection failed: {e}", file=sys.stderr)
        return

    aggregate_nodes = 0
    aggregate_edges = 0

    for proj in projects:
        db = proj["db_name"]
        slug = proj["slug"]
        print(f"  Neo4j: {db} ({slug})")
        try:
            with driver.session(database=db) as s:
                # Node counts by artifact type
                r = s.run(
                    "MATCH (n:Artifact) RETURN labels(n) AS labels, count(*) AS ct"
                )
                total_nodes = 0
                for rec in r:
                    lbl_list = [l for l in rec["labels"] if l != "Artifact"]
                    label = lbl_list[0] if lbl_list else "Unknown"
                    count = rec["ct"]
                    total_nodes += count
                    insert_metric(conn, ts, "nodes.by_type", count, slug,
                                  {"label": label})

                insert_metric(conn, ts, "nodes.total", total_nodes, slug)
                aggregate_nodes += total_nodes

                # Edge counts by type
                r = s.run(
                    "MATCH ()-[rel]->() RETURN type(rel) AS rel_type, count(*) AS ct"
                )
                total_edges = 0
                for rec in r:
                    total_edges += rec["ct"]
                    insert_metric(conn, ts, "edges.by_type", rec["ct"], slug,
                                  {"rel_type": rec["rel_type"]})
                insert_metric(conn, ts, "edges.total", total_edges, slug)
                aggregate_edges += total_edges

                # Artifacts by state
                r = s.run(
                    "MATCH (a:Artifact) WHERE a.state IS NOT NULL "
                    "RETURN a.state AS state, count(*) AS ct"
                )
                for rec in r:
                    insert_metric(conn, ts, "artifacts.by_state", rec["ct"], slug,
                                  {"state": rec["state"]})

                # Stale proposed (> 7 days)
                r = s.run(
                    "MATCH (a:Artifact) WHERE a.state = 'proposed' "
                    "AND a.created_at < datetime() - duration({days: 7}) "
                    "RETURN count(*) AS ct"
                )
                rec = r.single()
                insert_metric(conn, ts, "artifacts.stale_proposed_7d",
                              rec["ct"] if rec else 0, slug)

                # Last activity timestamp (days since)
                r = s.run(
                    "MATCH (n) WHERE n.created_at IS NOT NULL OR n.updated_at IS NOT NULL "
                    "RETURN max(coalesce(n.updated_at, n.created_at)) AS last_write"
                )
                rec = r.single()
                last_write_str = rec["last_write"] if rec else None
                if last_write_str:
                    try:
                        lw_str = str(last_write_str)
                        insert_metric(conn, ts, "project.last_activity_ts", 0, slug,
                                      {"iso": lw_str})
                        # Parse ISO string (created_at stored as string in Neo4j)
                        lw_py = datetime.fromisoformat(lw_str.replace("Z", "+00:00"))
                        if lw_py.tzinfo is None:
                            lw_py = lw_py.replace(tzinfo=timezone.utc)
                        now_utc = datetime.now(timezone.utc)
                        days_since = (now_utc - lw_py).days
                        insert_metric(conn, ts, "project.days_since_activity",
                                      days_since, slug)
                    except Exception as e:
                        print(f"    [warn] last_write parse failed for {slug}: {e}",
                              file=sys.stderr)
                        insert_metric(conn, ts, "project.days_since_activity", -1, slug)
                else:
                    insert_metric(conn, ts, "project.days_since_activity", -1, slug)

                # Open Issues with no linked ResearchTask
                # Use CONTEXT_FOR as the observed linkage pattern; also check
                # REMEDIATED_BY for forward compatibility
                r = s.run(
                    "MATCH (i:Artifact) WHERE i.artifact_type = 'Issue' "
                    "AND i.state IN ['open', 'in_progress', 'proposed'] "
                    "AND NOT EXISTS { "
                    "  MATCH (i)-[]->(t:Artifact) "
                    "  WHERE t.artifact_type = 'ResearchTask' "
                    "} "
                    "RETURN count(*) AS ct"
                )
                rec = r.single()
                insert_metric(conn, ts, "issues.unremediated", rec["ct"] if rec else 0, slug)

                # Total open Issues (for context)
                r = s.run(
                    "MATCH (i:Artifact) WHERE i.artifact_type = 'Issue' "
                    "AND i.state IN ['open', 'in_progress', 'proposed'] "
                    "RETURN count(*) AS ct"
                )
                rec = r.single()
                insert_metric(conn, ts, "issues.open_total", rec["ct"] if rec else 0, slug)

        except Exception as e:
            print(f"  [error] Neo4j collection failed for {db}: {e}", file=sys.stderr)
            # Write a sentinel so the dashboard knows collection was attempted
            insert_metric(conn, ts, "collection.error", 1, slug,
                          {"error": str(e)[:200]})

    # Aggregate totals
    insert_metric(conn, ts, "nodes.total", aggregate_nodes, "aggregate")
    insert_metric(conn, ts, "edges.total", aggregate_edges, "aggregate")

    driver.close()


# ---------------------------------------------------------------------------
# Event log collection
# ---------------------------------------------------------------------------

def collect_event_logs(conn: sqlite3.Connection, ts: str, projects: list[dict]) -> None:
    for proj in projects:
        slug = proj["slug"]
        log_path = proj["event_log"]
        if log_path.exists():
            try:
                line_count = sum(1 for _ in open(log_path, "r", errors="replace"))
                insert_metric(conn, ts, "events.total_lines", line_count, slug)
                # Count by event_type
                from collections import Counter
                event_types: Counter = Counter()
                with open(log_path, "r", errors="replace") as fh:
                    for line in fh:
                        try:
                            rec = json.loads(line)
                            et = rec.get("event_type", "unknown")
                            event_types[et] += 1
                        except json.JSONDecodeError:
                            pass
                for event_type, count in event_types.most_common(10):
                    insert_metric(conn, ts, "events.by_type", count, slug,
                                  {"event_type": event_type})
            except Exception as e:
                print(f"  [warn] Event log error for {slug}: {e}", file=sys.stderr)
        else:
            insert_metric(conn, ts, "events.total_lines", 0, slug)


# ---------------------------------------------------------------------------
# Filesystem signals
# ---------------------------------------------------------------------------

def collect_filesystem(conn: sqlite3.Connection, ts: str, projects: list[dict]) -> None:
    for proj in projects:
        slug = proj["slug"]
        project_dir = proj["project_dir"]

        # Handoff count
        handoffs_dir = project_dir / "handoffs"
        handoff_count = len(list(handoffs_dir.glob("*.md"))) if handoffs_dir.exists() else 0
        insert_metric(conn, ts, "fs.handoff_count", handoff_count, slug)

        # CC task count
        cc_dir = project_dir / "cc_tasks"
        cc_count = len(list(cc_dir.glob("*.md"))) if cc_dir.exists() else 0
        insert_metric(conn, ts, "fs.cc_task_count", cc_count, slug)

        # Most recent handoff age (days)
        if handoffs_dir.exists():
            handoff_files = sorted(handoffs_dir.glob("*.md"), key=lambda p: p.stat().st_mtime,
                                   reverse=True)
            if handoff_files:
                mtime = datetime.fromtimestamp(handoff_files[0].stat().st_mtime, tz=timezone.utc)
                days_ago = (datetime.now(timezone.utc) - mtime).days
                insert_metric(conn, ts, "fs.latest_handoff_days_ago", days_ago, slug,
                              {"file": handoff_files[0].name})


# ---------------------------------------------------------------------------
# Token attribution from ~/.claude/projects/
# ---------------------------------------------------------------------------

def collect_tokens(conn: sqlite3.Connection, ts: str, projects: list[dict]) -> None:
    if not CLAUDE_PROJECTS_ROOT.exists():
        print("  [info] ~/.claude/projects/ absent — token metrics skipped", file=sys.stderr)
        insert_metric(conn, ts, "tokens.attribution_mode", 0, "aggregate",
                      {"mode": "unavailable", "reason": "~/.claude/projects/ absent"})
        return

    # Build project path → slug mapping
    # Claude uses path-encoded dir names: /Users/brock/Documents/GitHub/seldon →
    #   -Users-brock-Documents-GitHub-seldon
    def path_to_claude_dir(project_dir: Path) -> str:
        return str(project_dir).replace("/", "-")

    proj_by_claude_key: dict[str, str] = {}
    for proj in projects:
        key = path_to_claude_dir(proj["project_dir"])
        proj_by_claude_key[key] = proj["slug"]

    # One week window
    now_utc = datetime.now(timezone.utc)
    week_ago = now_utc - timedelta(days=7)

    # Accumulate per-slug per-week token totals
    from collections import defaultdict
    totals: dict[str, dict[str, int]] = defaultdict(lambda: {
        "input": 0, "output": 0, "cache_creation": 0, "cache_read": 0
    })

    for proj_dir in CLAUDE_PROJECTS_ROOT.iterdir():
        if not proj_dir.is_dir():
            continue
        dir_key = proj_dir.name
        slug = proj_by_claude_key.get(dir_key, "other")

        for jsonl_file in proj_dir.glob("*.jsonl"):
            try:
                with open(jsonl_file, "r", errors="replace") as fh:
                    for line in fh:
                        try:
                            rec = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if rec.get("type") != "assistant":
                            continue
                        ts_str = rec.get("timestamp")
                        if ts_str:
                            try:
                                rec_ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                                if rec_ts < week_ago:
                                    continue
                            except ValueError:
                                pass
                        usage = rec.get("message", {}).get("usage", {})
                        if not usage:
                            continue
                        totals[slug]["input"] += usage.get("input_tokens", 0)
                        totals[slug]["output"] += usage.get("output_tokens", 0)
                        totals[slug]["cache_creation"] += usage.get(
                            "cache_creation_input_tokens", 0)
                        totals[slug]["cache_read"] += usage.get(
                            "cache_read_input_tokens", 0)
            except Exception as e:
                print(f"  [warn] Token parse error in {jsonl_file.name}: {e}", file=sys.stderr)

    # Write metrics
    insert_metric(conn, ts, "tokens.attribution_mode", 1, "aggregate",
                  {"mode": "jsonl_parse", "source": "~/.claude/projects/"})

    for slug, tok in totals.items():
        for token_type, count in tok.items():
            insert_metric(conn, ts, f"tokens.{token_type}.weekly", count, slug)

    # Aggregate
    agg = {"input": 0, "output": 0, "cache_creation": 0, "cache_read": 0}
    for tok in totals.values():
        for k in agg:
            agg[k] += tok[k]
    for token_type, count in agg.items():
        insert_metric(conn, ts, f"tokens.{token_type}.weekly", count, "aggregate")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"[{ts}] Seldon observability collection starting")

    conn = init_db(DB_PATH)

    projects = discover_projects()
    print(f"  Discovered {len(projects)} projects: "
          f"{', '.join(p['slug'] for p in projects)}")

    errors = 0
    print("  Collecting Neo4j metrics...")
    try:
        collect_neo4j(conn, ts, projects)
    except Exception as e:
        print(f"  [error] Neo4j collection: {e}", file=sys.stderr)
        errors += 1

    print("  Collecting event log metrics...")
    try:
        collect_event_logs(conn, ts, projects)
    except Exception as e:
        print(f"  [error] Event log collection: {e}", file=sys.stderr)
        errors += 1

    print("  Collecting filesystem signals...")
    try:
        collect_filesystem(conn, ts, projects)
    except Exception as e:
        print(f"  [error] Filesystem collection: {e}", file=sys.stderr)
        errors += 1

    print("  Collecting token attribution...")
    try:
        collect_tokens(conn, ts, projects)
    except Exception as e:
        print(f"  [error] Token collection: {e}", file=sys.stderr)
        errors += 1

    conn.commit()
    row_count = conn.execute("SELECT count(*) FROM metrics").fetchone()[0]
    conn.close()

    print(f"  Total rows in DB: {row_count}")
    print(f"[{ts}] Collection complete. Errors: {errors}")
    return errors


if __name__ == "__main__":
    sys.exit(main())
