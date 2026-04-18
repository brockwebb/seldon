# CC4: Baseline Observability Dashboard — Design Doc

**Date:** 2026-04-18
**Status:** Implemented; baseline running.
**Collector:** `scripts/observability_collect.py`
**Dashboard:** `scripts/observability_dashboard.py --port 8765`
**DB:** `~/.seldon-observability/metrics.db` (605 rows, first snapshot 2026-04-18)

---

## Metric definitions

### `nodes.total`

- **Definition:** Total count of `:Artifact` nodes in a project's Neo4j database.
- **Unit:** Integer (node count)
- **Source:** `MATCH (n:Artifact) RETURN count(*) AS ct` per project database
- **Frequency:** Nightly (03:00 local), on-demand when collector is run manually
- **Scope semantics:** project slug OR `aggregate` (sum across all project DBs)

### `nodes.by_type`

- **Definition:** Node count broken down by Artifact sub-type (ResearchTask, PaperSection, Issue, etc.)
- **Unit:** Integer
- **Source:** `MATCH (n:Artifact) RETURN labels(n), count(*)` — strips the `:Artifact` base label to get the type label
- **Frequency:** Nightly
- **Scope:** project slug; dimensions JSON includes `{"label": "ResearchTask"}`

### `edges.total`

- **Definition:** Total relationship count in project database.
- **Unit:** Integer
- **Source:** `MATCH ()-[r]->() RETURN count(r)`
- **Frequency:** Nightly
- **Scope:** project slug OR `aggregate`

### `edges.by_type`

- **Definition:** Edge count by relationship type (CONTAINS_SECTION, CONTEXT_FOR, etc.)
- **Unit:** Integer
- **Source:** `MATCH ()-[r]->() RETURN type(r), count(*)`
- **Frequency:** Nightly
- **Scope:** project slug; dimensions JSON includes `{"rel_type": "CONTAINS_SECTION"}`

### `artifacts.by_state`

- **Definition:** Artifact count by state (proposed, accepted, in_progress, completed, etc.)
- **Unit:** Integer
- **Source:** `MATCH (a:Artifact) WHERE a.state IS NOT NULL RETURN a.state, count(*)`
- **Frequency:** Nightly
- **Scope:** project slug; dimensions JSON includes `{"state": "proposed"}`

### `artifacts.stale_proposed_7d`

- **Definition:** Count of artifacts stuck in `proposed` state for more than 7 days.
- **Unit:** Integer
- **Source:** `MATCH (a:Artifact) WHERE a.state = 'proposed' AND a.created_at < datetime() - duration({days: 7}) RETURN count(*)`
- **Frequency:** Nightly
- **Scope:** project slug. Threshold of 7 days is hardcoded in the collector; adjust via source edit.

### `project.last_activity_ts`

- **Definition:** ISO timestamp of the most recently created or updated artifact node.
- **Unit:** ISO 8601 string (stored in `dimensions` JSON)
- **Source:** `MATCH (n) WHERE n.created_at IS NOT NULL RETURN max(n.created_at)`
- **Frequency:** Nightly
- **Scope:** project slug; metric_value is always 0 (sentinel); actual timestamp in `dimensions.iso`

### `project.days_since_activity`

- **Definition:** Integer number of days between the latest artifact `created_at` and now.
- **Unit:** Integer (days). -1 means no timestamped nodes found.
- **Source:** Computed from `project.last_activity_ts` at collection time
- **Frequency:** Nightly
- **Scope:** project slug

### `issues.unremediated`

- **Definition:** Count of open/in-progress/proposed Issues with no outbound relationship to a ResearchTask.
- **Unit:** Integer
- **Source:** Cypher MATCH checking Issue nodes with state in ('open','in_progress','proposed') and NOT EXISTS any relationship pointing to a ResearchTask artifact.
- **Note:** The spec called this metric `REMEDIATED_BY` edge based — but no such edge type exists in the graph as of 2026-04-18. The query uses presence/absence of any Issue→ResearchTask relationship edge. When `REMEDIATED_BY` is implemented, update the query to be specific.
- **Frequency:** Nightly
- **Scope:** project slug

### `issues.open_total`

- **Definition:** Total open/in-progress/proposed Issues per project.
- **Unit:** Integer
- **Source:** `MATCH (i:Artifact) WHERE i.artifact_type = 'Issue' AND i.state IN [...] RETURN count(*)`
- **Frequency:** Nightly
- **Scope:** project slug

### `events.total_lines`

- **Definition:** Line count of the project's `seldon_events.jsonl` file (proxy for total event volume).
- **Unit:** Integer (line count)
- **Source:** `wc -l` equivalent on the event_store path from `seldon.yaml`
- **Frequency:** Nightly
- **Scope:** project slug

### `events.by_type`

- **Definition:** Event count by `event_type` field in the JSONL (top-10 types).
- **Unit:** Integer
- **Source:** Parse each JSONL line, count by `event_type`
- **Frequency:** Nightly
- **Scope:** project slug; dimensions JSON includes `{"event_type": "artifact_created"}`

### `fs.handoff_count`

- **Definition:** Number of Markdown files in `<project>/handoffs/`.
- **Unit:** Integer
- **Source:** `glob("handoffs/*.md")`
- **Frequency:** Nightly
- **Scope:** project slug

### `fs.cc_task_count`

- **Definition:** Number of Markdown files in `<project>/cc_tasks/`.
- **Unit:** Integer
- **Source:** `glob("cc_tasks/*.md")`
- **Frequency:** Nightly
- **Scope:** project slug

### `fs.latest_handoff_days_ago`

- **Definition:** Days since the most recently modified handoff file.
- **Unit:** Integer (days)
- **Source:** `stat` mtime of most recent `.md` in `handoffs/`
- **Frequency:** Nightly
- **Scope:** project slug; dimensions JSON includes `{"file": "2026-04-18_...md"}`

### `tokens.input.weekly` / `tokens.output.weekly` / `tokens.cache_creation.weekly` / `tokens.cache_read.weekly`

- **Definition:** Per-project weekly token totals, broken down by token type, for assistant messages in the 7 days before the collection run.
- **Unit:** Integer (token count)
- **Source:** Parse `~/.claude/projects/<dir>/*.jsonl`, filter to `type=assistant` records with `timestamp` within the last 7 days, sum `message.usage.{input_tokens, output_tokens, cache_creation_input_tokens, cache_read_input_tokens}`.
- **Project attribution:** Claude Code stores sessions under path-encoded directory names (e.g., `/Users/brock/Documents/GitHub/seldon` → `-Users-brock-Documents-GitHub-seldon`). Project slug is looked up by matching the directory name to known project paths from `seldon.yaml` discovery. Sessions not matching any known project are attributed to scope `other`.
- **Frequency:** Nightly
- **Scope:** project slug OR `aggregate`

### `tokens.attribution_mode`

- **Definition:** Which token attribution method is active.
- **Unit:** 0 = unavailable, 1 = jsonl_parse
- **Source:** Checked at collection time: does `~/.claude/projects/` exist and contain JSONL files?
- **Frequency:** Nightly
- **Scope:** `aggregate`; dimensions JSON includes `{"mode": "jsonl_parse"}`

---

## Collection architecture

- **Schedule:** Nightly at 03:00 local time via launchd (`com.seldon.observability`)
- **Plist:** `~/Library/LaunchAgents/com.seldon.observability.plist` (not in git — per-machine)
- **Collector script:** `scripts/observability_collect.py` in seldon repo (version-controlled)
- **Working directory:** `/Users/brock/Documents/GitHub/seldon`
- **Python interpreter:** `/opt/anaconda3/bin/python3` (the active conda base environment)
- **Credential handling:** The collector uses `python-dotenv` to load `seldon/.env` at runtime. NEO4J_PASSWORD is NOT embedded in the plist. The plist has no `EnvironmentVariables` block.
- **Failure modes:**
  - Neo4j down: collector logs error to `collect.err`, skips Neo4j metrics, inserts a `collection.error` sentinel row, continues with other collection types. Returns nonzero exit code.
  - JSONL parse error: individual file errors are logged to stderr and skipped; remaining files continue.
  - Missing project: projects where `seldon.yaml` can't be parsed are logged to stderr and skipped.
  - DB error: fatal — collector exits nonzero.
- **Manual run:** `cd /Users/brock/Documents/GitHub/seldon && python3 scripts/observability_collect.py`
- **Log files:** `~/.seldon-observability/collect.log` (stdout) and `collect.err` (stderr)
- **Last-successful-collection surfaced:** The dashboard `/api/last-collection` endpoint returns the max timestamp in the DB, which is the most recent successful collection.

### Project discovery

The collector scans `glob("/Users/brock/Documents/GitHub/*/seldon.yaml")` and `glob("/Users/brock/Documents/GitHub/*/*/seldon.yaml")` to discover projects. From each `seldon.yaml`, it reads:
- `project.slug` → the scope identifier
- `neo4j.database` → which Neo4j database to query
- `event_store.path` → relative path to the JSONL event log

Databases in `EXCLUDED_DBS` (`seldon-ontology`, `seldon-test`, `seldon-test-project`, `neo4j`, `system`) are skipped.

---

## SQLite schema

```sql
CREATE TABLE IF NOT EXISTS metrics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp TEXT NOT NULL,          -- ISO 8601 UTC
  metric_name TEXT NOT NULL,        -- dot-notation: domain.subdomain.leaf
  metric_value REAL NOT NULL,       -- numeric value
  scope TEXT NOT NULL,              -- project slug OR 'aggregate'
  dimensions TEXT,                  -- nullable JSON for extra dimensions
  collected_by TEXT NOT NULL        -- 'nightly_collector_v1'
);

CREATE INDEX IF NOT EXISTS idx_metrics_name_scope_time
  ON metrics(metric_name, scope, timestamp);
CREATE INDEX IF NOT EXISTS idx_metrics_timestamp
  ON metrics(timestamp);
```

**Design rationale:**

- **`metric_name` is dot-notation** (e.g., `nodes.by_type`, `tokens.input.weekly`). Enables prefix queries (`WHERE metric_name LIKE 'tokens.%'`) without a separate category column.
- **`scope` is project slug OR `'aggregate'`** — nothing else. Enforced by convention in the collector. The dashboard filters by `scope != 'aggregate'` to get per-project views.
- **`dimensions` is nullable JSON** — avoids column proliferation for label type, edge type, event type, token type, etc. Callers parse the JSON. The alternative (one column per dimension) would require schema migration for every new dimension.
- **Insert-only, no UPDATEs** — every collection run inserts a new timestamped snapshot. Historical time series is preserved. To see current state, filter on `max(timestamp)`. To see trends, group by timestamp. Deletion is never needed; the DB grows at approximately 250–300 rows/night.
- **`collected_by`** supports future collector versioning: if `nightly_collector_v2` changes how a metric is computed, the field allows filtering to a consistent version when building trend charts.

---

## Dashboard sections

### Panel Q-a: Graph growth

**Shows:** Line charts of total artifact node count and total edge count per project across all collection snapshots. A stub box notes that curation rate (merge/split/prune events) is deferred until sleep functions exist.

**Reads:** `nodes.total`, `edges.total` — all timestamps, all non-aggregate scopes.

**Supports decisions:** Which projects are actively growing vs. stagnant? Are edges growing proportionally to nodes (suggesting real relationship structure) or lagging (suggesting isolated nodes)?

### Panel Q-b: Stale proposed artifacts

**Shows:** Bar chart — count of artifacts stuck in `proposed` state for more than 7 days, per project. Projects with zero stale items shown in gray; non-zero in amber.

**Reads:** `artifacts.stale_proposed_7d` — latest snapshot only.

**Supports decisions:** Which projects have artifact backlogs that need triage? Proposed items older than 7 days are likely forgotten (should be rejected or promoted).

### Panel Q-c: Dormant projects

**Shows:** Table with project slug, last activity timestamp, days since last activity, and a dormant/active badge. Projects with > 14 days since last graph write are flagged dormant in red.

**Reads:** `project.days_since_activity`, `project.last_activity_ts` — latest snapshot.

**Supports decisions:** Which projects are Phase C kill candidates? Dormant projects may indicate completed work (OK) or abandoned work (kill candidate). The table gives Brock the data; the Phase C kill/keep decision is manual.

### Panel Q-d: Unremediated open issues

**Shows:** Table with project slug, total open issue count, and count of open issues with no linked ResearchTask.

**Reads:** `issues.unremediated`, `issues.open_total` — latest snapshot.

**Supports decisions:** Are open issues being actioned or accumulating? An unremediated issue is one where no remediation task exists — it may be a real gap or may reflect that the linkage pattern (Issue→ResearchTask edge) hasn't been created. As of 2026-04-18, all projects show 0 unremediated issues, likely because the Issue→ResearchTask edge type is not yet in use rather than because all issues are remediated.

### Panel Q-e: Token burn

**Shows:** Stacked bar chart of weekly token totals (input / output / cache creation / cache read) per project for the latest snapshot. Attribution note indicates which data source is active (JSONL parse or approximation).

**Reads:** `tokens.*.weekly` — latest snapshot, all non-aggregate scopes; `tokens.attribution_mode`.

**Supports decisions:** Which projects consume the most tokens? Is cache read increasing (good — indicates warm cache usage)? Are cache creation tokens high (indicates cold cache — session context not being reused)?

---

## Token-attribution approach

### Primary mode: JSONL parse (currently active)

Claude Code writes one JSONL file per session to `~/.claude/projects/<path-encoded-dir>/`. Each line is a JSON record. Assistant-type records contain a `message.usage` object with:

```json
{
  "input_tokens": 3,
  "cache_creation_input_tokens": 28182,
  "cache_read_input_tokens": 0,
  "output_tokens": 8
}
```

The collector parses all JSONL files in all project subdirectories, filters to records with `timestamp` in the last 7 days, and sums token types per project. Project attribution uses the Claude path-encoding convention: `/Users/brock/Documents/GitHub/seldon` encodes to `-Users-brock-Documents-GitHub-seldon`.

Sessions not matching any known Seldon project are attributed to scope `other`. This includes projects that don't have `seldon.yaml` (non-Seldon projects using Claude Code).

**Current limitation:** The `other` bucket is large (78,929 input tokens out of 91,470 total in the first snapshot) because most Claude Code sessions are not in Seldon-tracked projects. This is expected; the dashboard shows per-project Seldon usage accurately.

### Fallback mode: unavailable

If `~/.claude/projects/` is absent, the collector records `tokens.attribution_mode` with `metric_value=0` and `dimensions.mode="unavailable"`. No token metrics are written. The dashboard shows an attribution note explaining the gap.

---

## Known limitations

1. **Tier 3 outcome quality not measured.** This is a scope decision. Content correctness, citation accuracy, claim verification rates — these require semantic evaluation and are a future research problem, not a metric collection problem.

2. **Curation rate stub.** The Q-a curation rate panel (merge/split/prune event counts) shows zero with a note. Sleep functions (CC5) generate the events that would populate this. The stub is structural — no fake numbers.

3. **Backfill: one snapshot today.** Historical backfill was not implemented. Forward-going nightly collection begins from 2026-04-18. 30-day backfill from event log replay is explicitly deferred to future work.

4. **`REMEDIATED_BY` edge not yet in graph.** The `issues.unremediated` metric uses presence/absence of any Issue→ResearchTask edge. No `REMEDIATED_BY` edge type exists as of this implementation. When the edge type is introduced, update the Cypher query in the collector.

5. **`updated_at` not present in most nodes.** Neo4j generates warnings on the `last_activity` query because `updated_at` is not a universal property. The query correctly degrades to `created_at` only. All activity timestamps are based on creation time.

6. **Projects without seldon.yaml excluded.** Non-Seldon projects in the GitHub directory (ai-demos, sas_graph_code_conversion unless they have seldon.yaml) are not in the graph metrics. Their tokens are attributed to `other`.

7. **Token data covers only the trailing 7 days.** Each collection snapshot reflects the last 7 days of sessions. There is no accumulation of weekly buckets — each run overwrites with the current week's window. To build an 8-week view, the collector must retain 8 consecutive weekly snapshots, which takes 7 weeks of nightly runs.

8. **Dashboard not daemonized.** Run manually: `python3 scripts/observability_dashboard.py --port 8765`. A launchd service for the dashboard server is deferred to future work.

---

## How this ties to CC3

CC3's measurement-function audit identified components with no measurement function. The following CC3 findings now have corresponding metrics in this dashboard:

| CC3 component | CC3 verdict | CC4 metric |
|---|---|---|
| `seldon verify` violation tracking | No, but should be measurable | Not yet — verify violations need to write to JSONL event log. Q for future collector version. |
| Graph growth (node/edge counts) | Implicit baseline | `nodes.total`, `edges.total` — Q-a panel |
| Stale proposed artifacts | No explicit metric | `artifacts.stale_proposed_7d` — Q-b panel |
| Dormant projects | No explicit metric | `project.days_since_activity` — Q-c panel |
| Open unremediated issues | No explicit metric | `issues.unremediated` — Q-d panel |
| Token burn per project | No explicit metric | `tokens.*.weekly` — Q-e panel |
| AD-019/020 audit pipeline activity | Qualitative only | `events.by_type` with event_type=audit captures partial signal; full audit pipeline instrumentation is future work |

**Remaining CC3 gaps not yet wired to this dashboard:**
- `seldon verify` violation count per run (needs event log integration)
- ClaudeClaw job success/failure rate (needs ClaudeClaw → event log bridge)
- Perplexity query execution tracking (fully manual, no artifact trail)
- AD-019 issue closure rate (would need to compute open vs. closed Issues over time — implementable but not in this baseline)

---

## Future work (explicitly deferred)

- **Tier 3 outcome quality metrics** — citation verification rate, claim accuracy, audit uptake rate. These require semantic evaluation infrastructure and are a future paper/research task, not a collection script problem.
- **Historical backfill** — replay the seldon event logs to reconstruct daily snapshots for the last 30 days. The event logs exist; the reconstruction logic needs to be written.
- **Alerting and thresholds** — no alerting in this baseline. Future: launchd job that posts to Slack/email when dormant-project count increases or stale-proposed count exceeds a threshold.
- **`seldon verify` violation logging** — add 5 lines to `verify.py` to emit violation counts to the JSONL event store. Then add a collector query that reads those events. This is the "easiest measurement win" identified in CC3.
- **Multi-machine collection** — if Brock runs Seldon on a second machine, the metrics DB would need to be in a shared location or merged. Deferred until the need arises.
- **Dashboard as launchd service** — the dashboard server currently must be started manually. A second plist (`com.seldon.observability.dashboard`) could keep it always-on. Deferred.
- **8-week token trend view** — the current token panel shows a single weekly snapshot per collection run. After 8 weeks of nightly runs, the dashboard will automatically show 8 bars. No code change needed; the limitation is purely temporal.
- **Issue→ResearchTask `REMEDIATED_BY` edge adoption** — when this edge type is introduced in Seldon's schema, update the `issues.unremediated` Cypher query to be specific to `REMEDIATED_BY` rather than checking for any Issue→ResearchTask edge.
