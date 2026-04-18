#!/usr/bin/env python3
"""
Seldon Observability Dashboard

Single-file server using stdlib http.server + Plotly (CDN).
No Flask, no Plotly install required.

Usage:
    python3 scripts/observability_dashboard.py --port 8765
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

DB_PATH = Path.home() / ".seldon-observability" / "metrics.db"


# ---------------------------------------------------------------------------
# Data access helpers
# ---------------------------------------------------------------------------

def get_db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"metrics.db not found at {DB_PATH}. Run the collector first.")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def query(sql: str, params: tuple = ()) -> list[dict]:
    conn = get_db()
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def latest_ts() -> str:
    rows = query("SELECT max(timestamp) AS ts FROM metrics")
    return rows[0]["ts"] if rows else "unknown"


def last_collection_info() -> dict:
    ts = latest_ts()
    count = query("SELECT count(*) AS ct FROM metrics WHERE timestamp=?", (ts,))
    return {"timestamp": ts, "row_count": count[0]["ct"] if count else 0}


# ---------------------------------------------------------------------------
# Metric query helpers
# ---------------------------------------------------------------------------

def get_metric_series(metric_name: str, scope: str = None) -> list[dict]:
    """Return time-series rows for a metric, optionally filtered by scope."""
    if scope:
        return query(
            "SELECT timestamp, metric_value, scope, dimensions FROM metrics "
            "WHERE metric_name=? AND scope=? ORDER BY timestamp",
            (metric_name, scope),
        )
    return query(
        "SELECT timestamp, metric_value, scope, dimensions FROM metrics "
        "WHERE metric_name=? ORDER BY timestamp",
        (metric_name,),
    )


def get_latest(metric_name: str) -> list[dict]:
    """Return latest value per scope for a given metric."""
    ts = latest_ts()
    return query(
        "SELECT scope, metric_value, dimensions FROM metrics "
        "WHERE metric_name=? AND timestamp=? ORDER BY scope",
        (metric_name, ts),
    )


def get_scopes() -> list[str]:
    rows = query(
        "SELECT DISTINCT scope FROM metrics WHERE scope != 'aggregate' ORDER BY scope"
    )
    return [r["scope"] for r in rows]


def get_stale_proposed_detail() -> list[dict]:
    """Return per-scope stale proposed counts, plus best-available timestamps."""
    ts = latest_ts()
    return query(
        "SELECT scope, metric_value AS count FROM metrics "
        "WHERE metric_name='artifacts.stale_proposed_7d' AND timestamp=? "
        "ORDER BY metric_value DESC",
        (ts,),
    )


def get_dormant_projects() -> list[dict]:
    ts = latest_ts()
    rows = query(
        "SELECT scope, metric_value AS days_since, dimensions FROM metrics "
        "WHERE metric_name='project.days_since_activity' AND timestamp=? "
        "ORDER BY metric_value DESC",
        (ts,),
    )
    # Augment with last_activity_ts ISO string
    ts_rows = query(
        "SELECT scope, dimensions FROM metrics "
        "WHERE metric_name='project.last_activity_ts' AND timestamp=?",
        (ts,),
    )
    ts_map = {}
    for r in ts_rows:
        try:
            dims = json.loads(r["dimensions"] or "{}")
            ts_map[r["scope"]] = dims.get("iso", "unknown")
        except Exception:
            ts_map[r["scope"]] = "unknown"
    for row in rows:
        row["last_activity_iso"] = ts_map.get(row["scope"], "unknown")
    return rows


def get_token_series() -> dict:
    """Return per-scope weekly token totals by type for the last 8 weeks."""
    rows = query(
        "SELECT timestamp, scope, metric_name, metric_value FROM metrics "
        "WHERE metric_name LIKE 'tokens.%.weekly' AND scope != 'aggregate' "
        "ORDER BY timestamp, scope"
    )
    return rows


# ---------------------------------------------------------------------------
# API handlers
# ---------------------------------------------------------------------------

ROUTES: dict = {}


def route(path: str):
    def decorator(fn):
        ROUTES[path] = fn
        return fn
    return decorator


@route("/api/last-collection")
def api_last_collection(params: dict) -> dict:
    return last_collection_info()


@route("/api/scopes")
def api_scopes(params: dict) -> dict:
    return {"scopes": get_scopes()}


@route("/api/panel/growth")
def api_panel_growth(params: dict) -> dict:
    """Q-a: Graph growth — nodes and edges per project over time."""
    nodes = get_metric_series("nodes.total")
    edges = get_metric_series("edges.total")

    def group_by_scope(rows):
        by_scope: dict = {}
        for r in rows:
            scope = r["scope"]
            if scope == "aggregate":
                continue
            by_scope.setdefault(scope, {"x": [], "y": []})
            by_scope[scope]["x"].append(r["timestamp"])
            by_scope[scope]["y"].append(r["metric_value"])
        return by_scope

    return {
        "nodes": group_by_scope(nodes),
        "edges": group_by_scope(edges),
        "curation_stub": {
            "note": "Curation rate (merge/split/prune) awaiting sleep function implementation (CC5 → future).",
            "value": 0,
        },
    }


@route("/api/panel/stale-proposed")
def api_panel_stale(params: dict) -> dict:
    """Q-b: Stale proposed artifacts (> 7 days)."""
    rows = get_stale_proposed_detail()
    return {"projects": rows, "threshold_days": 7}


@route("/api/panel/dormant")
def api_panel_dormant(params: dict) -> dict:
    """Q-c: Dormant projects (days since last graph write)."""
    rows = get_dormant_projects()
    dormant_threshold = 14
    for r in rows:
        r["dormant"] = r["days_since"] >= dormant_threshold or r["days_since"] < 0
    return {"projects": rows, "dormant_threshold_days": dormant_threshold}


@route("/api/panel/issues")
def api_panel_issues(params: dict) -> dict:
    """Q-d: Unremediated open issues per project."""
    ts = latest_ts()
    unremediated = query(
        "SELECT scope, metric_value AS unremediated FROM metrics "
        "WHERE metric_name='issues.unremediated' AND timestamp=? ORDER BY scope",
        (ts,),
    )
    open_total = query(
        "SELECT scope, metric_value AS open_total FROM metrics "
        "WHERE metric_name='issues.open_total' AND timestamp=? ORDER BY scope",
        (ts,),
    )
    open_map = {r["scope"]: r["open_total"] for r in open_total}
    for r in unremediated:
        r["open_total"] = open_map.get(r["scope"], 0)
    return {"projects": unremediated}


@route("/api/panel/tokens")
def api_panel_tokens(params: dict) -> dict:
    """Q-e: Token burn — input/output/cache per project per week."""
    rows = get_token_series()
    # Restructure: {scope: {metric_name: [(timestamp, value)]}}
    by_scope: dict = {}
    for r in rows:
        scope = r["scope"]
        mname = r["metric_name"]
        by_scope.setdefault(scope, {})
        by_scope[scope].setdefault(mname, [])
        by_scope[scope][mname].append({
            "timestamp": r["timestamp"],
            "value": r["metric_value"],
        })
    # Check attribution mode
    mode_rows = query(
        "SELECT dimensions FROM metrics WHERE metric_name='tokens.attribution_mode' "
        "ORDER BY timestamp DESC LIMIT 1"
    )
    mode = "unknown"
    if mode_rows:
        try:
            dims = json.loads(mode_rows[0]["dimensions"] or "{}")
            mode = dims.get("mode", "unknown")
        except Exception:
            pass
    return {"by_scope": by_scope, "attribution_mode": mode}


# ---------------------------------------------------------------------------
# HTML page
# ---------------------------------------------------------------------------

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Seldon Observability Dashboard</title>
  <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', monospace;
           background: #0d1117; color: #c9d1d9; padding: 16px; }
    h1 { color: #58a6ff; margin-bottom: 4px; font-size: 1.4em; }
    .meta { color: #8b949e; font-size: 0.82em; margin-bottom: 20px; }
    .panel { background: #161b22; border: 1px solid #30363d; border-radius: 8px;
             padding: 16px; margin-bottom: 20px; }
    .panel h2 { color: #e6edf3; font-size: 1em; margin-bottom: 12px;
                border-bottom: 1px solid #30363d; padding-bottom: 8px; }
    .stub-box { background: #1c2128; border: 1px dashed #484f58; border-radius: 4px;
                padding: 12px; color: #8b949e; font-size: 0.85em; margin-top: 8px; }
    table { width: 100%; border-collapse: collapse; font-size: 0.85em; }
    th { color: #8b949e; text-align: left; padding: 6px 8px;
         border-bottom: 1px solid #30363d; }
    td { padding: 5px 8px; border-bottom: 1px solid #21262d; }
    tr.dormant td { color: #f85149; }
    tr.active td { color: #3fb950; }
    .badge { display: inline-block; padding: 1px 6px; border-radius: 10px;
             font-size: 0.75em; }
    .badge-red { background: #3d1c1c; color: #f85149; }
    .badge-green { background: #1a3421; color: #3fb950; }
    .badge-gray { background: #21262d; color: #8b949e; }
    .attr-note { color: #8b949e; font-size: 0.78em; margin-top: 8px; }
    #loading { color: #58a6ff; font-size: 0.9em; padding: 20px 0; }
  </style>
</head>
<body>
  <h1>Seldon Observability Dashboard</h1>
  <div class="meta" id="meta">Loading...</div>

  <div class="panel">
    <h2>Q-a: Graph Growth</h2>
    <div id="chart-nodes" style="height:280px;"></div>
    <div id="chart-edges" style="height:220px;"></div>
    <div class="stub-box">
      <strong>Curation rate stub</strong> — metric awaiting sleep function implementation (CC5 → future).
      Current value: <strong>0 / N</strong> events with merge/split/prune operations.
    </div>
  </div>

  <div class="panel">
    <h2>Q-b: Stale Proposed Artifacts (&gt;7 days in <code>proposed</code> state)</h2>
    <div id="chart-stale" style="height:240px;"></div>
  </div>

  <div class="panel">
    <h2>Q-c: Dormant Projects</h2>
    <div id="table-dormant"></div>
  </div>

  <div class="panel">
    <h2>Q-d: Unremediated Open Issues</h2>
    <div id="table-issues"></div>
  </div>

  <div class="panel">
    <h2>Q-e: Token Burn (last 8 weeks)</h2>
    <div id="chart-tokens" style="height:320px;"></div>
    <div class="attr-note" id="token-attr-note"></div>
  </div>

<script>
const COLORS = [
  '#58a6ff','#3fb950','#d29922','#f85149','#bc8cff','#79c0ff',
  '#56d364','#ffa657','#ff7b72','#a5d6ff'
];

async function fetchJson(url) {
  const r = await fetch(url);
  return r.json();
}

function plotlyLayout(title, ytitle='') {
  return {
    title: { text: title, font: { color: '#8b949e', size: 12 } },
    paper_bgcolor: '#161b22', plot_bgcolor: '#161b22',
    font: { color: '#c9d1d9', size: 11 },
    xaxis: { gridcolor: '#21262d', color: '#8b949e' },
    yaxis: { gridcolor: '#21262d', color: '#8b949e', title: ytitle },
    legend: { bgcolor: '#0d1117', bordercolor: '#30363d', borderwidth: 1 },
    margin: { t: 30, b: 40, l: 50, r: 10 },
  };
}

async function renderGrowth() {
  const d = await fetchJson('/api/panel/growth');
  const scopes = Object.keys(d.nodes);

  // Nodes chart
  const nodeTraces = scopes.map((s, i) => ({
    x: d.nodes[s].x, y: d.nodes[s].y,
    type: 'scatter', mode: 'lines+markers',
    name: s, line: { color: COLORS[i % COLORS.length] }
  }));
  Plotly.newPlot('chart-nodes', nodeTraces,
    plotlyLayout('Artifact nodes per project (all time)', 'node count'), {responsive: true});

  // Edges chart
  const edgeTraces = Object.keys(d.edges).map((s, i) => ({
    x: d.edges[s].x, y: d.edges[s].y,
    type: 'scatter', mode: 'lines+markers',
    name: s, line: { color: COLORS[i % COLORS.length] }
  }));
  Plotly.newPlot('chart-edges', edgeTraces,
    plotlyLayout('Relationship edges per project', 'edge count'), {responsive: true});
}

async function renderStale() {
  const d = await fetchJson('/api/panel/stale-proposed');
  const projs = d.projects.filter(p => p.scope !== 'aggregate');
  const trace = {
    x: projs.map(p => p.scope),
    y: projs.map(p => p.count),
    type: 'bar',
    marker: { color: projs.map(p => p.count > 0 ? '#d29922' : '#21262d') },
    text: projs.map(p => p.count > 0 ? p.count : '0'),
    textposition: 'auto',
  };
  Plotly.newPlot('chart-stale', [trace],
    { ...plotlyLayout('Artifacts stuck in proposed > 7 days', 'count'),
      showlegend: false },
    {responsive: true});
}

async function renderDormant() {
  const d = await fetchJson('/api/panel/dormant');
  let html = '<table><thead><tr><th>Project</th><th>Last activity</th>' +
    '<th>Days since</th><th>Status</th></tr></thead><tbody>';
  for (const r of d.projects) {
    if (r.scope === 'aggregate') continue;
    const days = r.days_since >= 0 ? r.days_since : '?';
    const dormant = r.dormant;
    const cls = dormant ? 'dormant' : 'active';
    const badge = dormant
      ? `<span class="badge badge-red">dormant >${d.dormant_threshold_days}d</span>`
      : `<span class="badge badge-green">active</span>`;
    const iso = r.last_activity_iso !== 'unknown'
      ? r.last_activity_iso.replace('T', ' ').substring(0, 16) + ' UTC'
      : '—';
    html += `<tr class="${cls}"><td>${r.scope}</td><td>${iso}</td>` +
      `<td>${days}</td><td>${badge}</td></tr>`;
  }
  html += '</tbody></table>';
  document.getElementById('table-dormant').innerHTML = html;
}

async function renderIssues() {
  const d = await fetchJson('/api/panel/issues');
  let html = '<table><thead><tr><th>Project</th><th>Open issues</th>' +
    '<th>Unremediated (no linked task)</th></tr></thead><tbody>';
  for (const r of d.projects) {
    if (r.scope === 'aggregate') continue;
    const badge = r.unremediated > 0
      ? `<span class="badge badge-red">${r.unremediated}</span>`
      : `<span class="badge badge-green">0</span>`;
    html += `<tr><td>${r.scope}</td><td>${r.open_total}</td>` +
      `<td>${badge}</td></tr>`;
  }
  html += '</tbody></table>';
  document.getElementById('table-issues').innerHTML = html;
}

async function renderTokens() {
  const d = await fetchJson('/api/panel/tokens');
  const scopes = Object.keys(d.by_scope).filter(s => s !== 'aggregate');

  // Build stacked bar: one group per scope, stacked by token type
  const tokenTypes = ['tokens.input.weekly', 'tokens.output.weekly',
                      'tokens.cache_creation.weekly', 'tokens.cache_read.weekly'];
  const typeLabels = {'tokens.input.weekly': 'Input',
                      'tokens.output.weekly': 'Output',
                      'tokens.cache_creation.weekly': 'Cache creation',
                      'tokens.cache_read.weekly': 'Cache read'};
  const typeColors = {'tokens.input.weekly': '#58a6ff',
                      'tokens.output.weekly': '#3fb950',
                      'tokens.cache_creation.weekly': '#d29922',
                      'tokens.cache_read.weekly': '#bc8cff'};

  // Collect all timestamps used
  const allTs = new Set();
  for (const sc of scopes) {
    for (const tt of tokenTypes) {
      const entries = d.by_scope[sc]?.[tt] || [];
      entries.forEach(e => allTs.add(e.timestamp));
    }
  }
  const timestamps = [...allTs].sort().slice(-8); // last 8 snapshots

  const traces = [];
  for (const tt of tokenTypes) {
    const yValues = scopes.map(sc => {
      const entries = d.by_scope[sc]?.[tt] || [];
      const latest = entries.filter(e => timestamps.includes(e.timestamp)).pop();
      return latest ? latest.value : 0;
    });
    traces.push({
      name: typeLabels[tt],
      x: scopes,
      y: yValues,
      type: 'bar',
      marker: { color: typeColors[tt] },
    });
  }

  Plotly.newPlot('chart-tokens', traces,
    { ...plotlyLayout('Token usage (weekly snapshot, latest)', 'tokens'),
      barmode: 'stack' },
    {responsive: true});

  const modeNote = d.attribution_mode === 'jsonl_parse'
    ? 'Source: parsed from ~/.claude/projects/ JSONL session files (primary mode).'
    : `Attribution mode: ${d.attribution_mode}. See design doc for details.`;
  document.getElementById('token-attr-note').textContent = modeNote;
}

async function renderMeta() {
  const d = await fetchJson('/api/last-collection');
  const ts = d.timestamp || 'unknown';
  const short = ts.substring(0, 16).replace('T', ' ') + ' UTC';
  document.getElementById('meta').textContent =
    `Last collection: ${short} (${d.row_count} rows) · Refresh page to reload data`;
}

// Render all panels
(async () => {
  try {
    await Promise.all([
      renderMeta(), renderGrowth(), renderStale(),
      renderDormant(), renderIssues(), renderTokens()
    ]);
  } catch (e) {
    console.error('Dashboard render error:', e);
    document.body.insertAdjacentHTML('afterbegin',
      `<div style="background:#3d1c1c;padding:12px;margin-bottom:16px;border-radius:4px;">
        Dashboard error: ${e.message}</div>`);
  }
})();
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        # Suppress access log noise; errors still show
        pass

    def log_error(self, fmt: str, *args) -> None:
        sys.stderr.write(f"[ERROR] {fmt % args}\n")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        params = {k: v[0] if len(v) == 1 else v
                  for k, v in parse_qs(parsed.query).items()}

        # API routes
        if path in ROUTES:
            try:
                data = ROUTES[path](params)
                body = json.dumps(data).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                err = json.dumps({"error": str(e)}).encode()
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(err)
            return

        # Root → dashboard HTML
        if path in ("/", "/index.html"):
            body = HTML_PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # 404
        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"Not found")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Seldon Observability Dashboard")
    parser.add_argument("--port", type=int, default=8765, help="HTTP port (default 8765)")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default 127.0.0.1)")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"ERROR: {DB_PATH} not found. Run the collector first:", file=sys.stderr)
        print(f"  python3 scripts/observability_collect.py", file=sys.stderr)
        sys.exit(1)

    server = HTTPServer((args.host, args.port), DashboardHandler)
    url = f"http://{args.host}:{args.port}/"
    print(f"Seldon Observability Dashboard")
    print(f"  Serving at: {url}")
    print(f"  DB: {DB_PATH}")
    cinfo = last_collection_info()
    print(f"  Last collection: {cinfo['timestamp']} ({cinfo['row_count']} rows)")
    print(f"  Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
