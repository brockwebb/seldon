"""SEL-044 Part A: survey every directory under ~/GitHub holding a seldon.yaml. Reads only."""
import json
import os
import sys
import time
from pathlib import Path

import yaml
from dotenv import dotenv_values

PRIMARY = Path("/Users/brock/GitHub/seldon")
env = dotenv_values(PRIMARY / ".env")
for k, v in env.items():
    os.environ.setdefault(k, v)

from neo4j import GraphDatabase  # noqa: E402

GITHUB = Path("/Users/brock/GitHub")
LAUNCH = Path.home() / "Library/LaunchAgents"
plists = {p.name for p in LAUNCH.glob("*dispatch*.plist")}

uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
user = os.environ.get("NEO4J_USER") or os.environ.get("NEO4J_USERNAME") or "neo4j"
pw = os.environ["NEO4J_PASSWORD"]
drv = GraphDatabase.driver(uri, auth=(user, pw))
with drv.session(database="system") as s:
    dbs = {r["name"]: r["currentStatus"] for r in s.run("SHOW DATABASES")}

rows = []
for y in sorted(GITHUB.glob("*/seldon.yaml")):
    root = y.parent
    row = {"repo": root.name}
    try:
        cfg = yaml.safe_load(y.read_text()) or {}
    except Exception as exc:
        row["config_error"] = str(exc)
        rows.append(row)
        continue
    db = (cfg.get("neo4j") or {}).get("database")
    row["database"] = db
    row["db_online"] = dbs.get(db)
    d = cfg.get("dispatch")
    row["dispatch_block"] = bool(d)
    row["dispatch_enabled"] = (d or {}).get("enabled") if d else None
    row["plist"] = [p for p in plists if root.name in p or (root.name == "ai-readiness-kg" and "airkg" in p)]
    ev = root / "seldon_events.jsonl"
    last = None
    n = 0
    registered = 0
    if ev.is_file():
        with ev.open() as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                n += 1
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                ts = e.get("timestamp")
                if ts and (last is None or ts > last):
                    last = ts
                if e.get("event_type") == "artifact_created" and (e.get("payload") or {}).get("artifact_type") == "ResearchTask":
                    registered += 1
    row["events"] = n
    row["last_event"] = last
    row["task_created_events"] = registered
    row["cc_tasks_files"] = len(list((root / "cc_tasks").glob("*.md"))) if (root / "cc_tasks").is_dir() else 0
    lp = root / ".seldon" / "dispatch_last_pass.json"
    if lp.is_file():
        try:
            row["last_pass_at"] = json.loads(lp.read_text()).get("at")
        except ValueError:
            row["last_pass_at"] = "unparseable"
    if db and dbs.get(db) == "online":
        with drv.session(database=db) as s:
            r = s.run("MATCH (t:ResearchTask) RETURN t.state AS st, count(*) AS c").data()
            row["tasks_by_state"] = {x["st"]: x["c"] for x in r}
    rows.append(row)
drv.close()
json.dump(rows, sys.stdout, indent=1, default=str)
