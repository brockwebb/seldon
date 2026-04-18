# CC2: Infrastructure State-of-Play — 2026-04-18

**Date:** 2026-04-18
**Executor:** Claude Code session
**Purpose:** Diagnostic ground truth for evolution burst Phase C synthesis.
**Scope:** Wintermute and adjacent memory/skill infrastructure on Brock's M1 Pro.

---

## Summary Table

| Subsystem | Installed? | Running/active? | Last activity | Data present? | Appears useful? | Evidence |
|---|---|---|---|---|---|---|
| Neo4j runtime | Yes | Yes | 2026-04-18 | Yes | Yes (foundation) | Port 7687 open; 18 DBs online via Python driver |
| seldon-seldon-self | Yes | — | 2026-04-18 13:28 | 203 nodes | Yes | 201 Artifacts, active today |
| seldon-ontology | Yes | — | 2026-04-05 | 106 nodes | Yes | 105 OntologyTerm artifacts, master vocab DB |
| seldon-brock-projects | Yes | — | 2026-04-17 | 180 nodes | Yes | SFV paper project graph |
| seldon-sfv-paper | Yes | — | 2026-03-28 | 88 nodes | Yes | Older project DB; may be superseded by brock-projects |
| seldon-leibniz-pi | Yes | — | 2026-04-02 | 260 nodes | Yes | Active paper project |
| seldon-ai-workflow-design | Yes | — | 2026-04-09 | 324 nodes | Yes | Most populated Seldon project DB |
| seldon-ai4stats | Yes | — | 2026-03-23 | 47 nodes | Likely | Older project, less recent activity |
| seldon-icsp-notebook | Yes | — | 2026-04-17 | 550 nodes | Yes | Most populated; active yesterday |
| seldon-arnold | Yes | — | 2026-04-13 | 13 nodes | Unknown | Sparse; Arnold-specific |
| seldon-sas2graph | Yes | — | Unknown | Unknown | Unknown | Exists in DB list; not queried (no Seldon project config found) |
| seldon-test / seldon-test-project | Yes | — | Unknown | Unknown | No | Test DBs; disposable |
| wintermute-intake | Yes | — | Unknown | 7,660 nodes | Yes (dormant) | Entity:4255, Claim:2448, Document:776; no `created` timestamps; content is bookdown chapters, arXiv papers, PDFs |
| Wintermute repo | Yes | No | 2026-03-22 | Yes | Partial | Last commit Mar 22; no `seldon.yaml`; `.venv` intact |
| Wintermute runtime (~/.wintermute/) | Yes | Partial | 2026-04-18 | Yes (478 MB) | Yes (ClaudeClaw) | Active ClaudeClaw daemon; inbox, ingested, logs directories populated |
| Wintermute MCP server | Yes (code) | Unknown | 2026-04-15 | N/A | Unknown | `~/.wintermute/wintermute-mcp/server.py` exists (modified Apr 15); NOT registered in claude_desktop_config.json |
| LightRAG | Yes (venv only) | No | 2026-02-14 | No usable index | No | Installed in wintermute `.venv`; `rag_storage/` in repo is empty; logs last written Feb 14; never successfully indexed |
| claude-mem (thedotmack) | Yes | No | 2026-04-11 | Minimal | No | Installed v10.5.2; marked `.orphaned_at` Apr 11; no PID; `claude-mem.db` not found at expected path; chroma replaced by different dir structure |
| mv2 memory skill | Yes | Yes (active) | 2026-04-18 | Yes | Yes | `~/.claude/mind.mv2` (1.7 MB, Feb 28); `seldon/.claude/mind.mv2` (50 MB, today); `mind 2.mv2` (30 MB, Mar 14) |
| Hermes Agent | Yes (cloned) | No | 2026-03-04 | Yes (state.db) | Unknown | `~/.hermes/` exists with 15+ skill categories and state.db (1.8 MB, Mar 4); binary not on PATH; `hermes-agent` dir is the cloned repo, not an installed executable |
| Wintermute HTML explorer | No standalone | — | — | No | — | No `explorer.html` in repo or runtime; LightRAG webui exists as venv package asset (Feb 14) but was never deployed separately |
| ClaudeMEM | No evidence | — | — | — | — | No directory, config, or process named `claudemem` or `ClaudeMEM` found |

---

## Per-Subsystem Detail

### Neo4j Runtime

**Checked:** TCP probe to `localhost:7687`; Python neo4j driver query against `system` database.

**Found:** Port 7687 is open and accepting connections. Auth succeeds with credentials from `seldon/.env`. Running via Neo4j Desktop (two versions installed: `Neo4j Desktop.app` and `Neo4j Desktop 2.app`). `cypher-shell` is NOT on PATH — not installed as a standalone tool, only bundled inside Neo4j Desktop (and not findable via `find` on those `.app` bundles in the time allotted). All database queries done via Python `neo4j` driver instead.

**18 databases online:**
- `system`, `neo4j` (system DBs)
- `seldon-*` (14 project DBs — see table)
- `wintermute-intake` (1)
- `arnold`, `pragmatics`, `quarry`, `fscm-nist-rmf-map` (4 non-Seldon project DBs)

**Assessment:** Healthy, actively used. Foundation for everything else.

---

### Seldon Databases

**seldon-seldon-self** (203 nodes, last write today): The Seldon self-dogfood project. Active as of this session.

**seldon-ontology** (106 nodes, last write Apr 5): The master validity vocabulary DB per AD-017. 105 OntologyTerm artifacts. Last sync was Apr 5; yesterday's vocabulary_rules.yaml changes have not been ingested yet.

**seldon-icsp-notebook** (550 nodes, last write yesterday): Largest project DB. Most recently active.

**seldon-ai-workflow-design** (324 nodes, last write Apr 9): Most populated project overall.

**seldon-brock-projects** (180 nodes, last write Apr 17): The brock-projects umbrella (SFV paper). Updated yesterday as part of glossary migration.

**seldon-leibniz-pi** (260 nodes, last write Apr 2): Active paper project.

**seldon-sfv-paper** (88 nodes, last write Mar 28): Separate DB for SFV paper — may be a redundant project that predates the brock-projects umbrella. Relationship to `seldon-brock-projects` is unclear.

**seldon-ai4stats** (47 nodes, last write Mar 23): Sparse, older.

**seldon-arnold** (13 nodes, last write Apr 13): Sparse; Arnold-specific bookkeeping.

**seldon-sas2graph, seldon-test, seldon-test-project**: Not queried. Disposable or inactive.

**wintermute-intake** (7,660 nodes): Entity:4255, Claim:2448, Document:776. No `created` timestamps on nodes, so last-write is `None`. Content breakdown: 467 bookdown chapters, 257 untyped documents, 32 arXiv papers, 9 GitHub repos, 4 PDFs. This is the Wintermute knowledge graph. It has real content but no clear last-ingestion date.

---

### Wintermute Repo (`/Users/brock/Documents/GitHub/wintermute/`)

**Checked:** `git log -1`, `ls seldon.yaml`, directory listing.

**Found:** Exists. Last commit `2026-03-22`: "plan: knowledge wiki MVP implementation plan". Five recent commits are all planning documents (plan, spec, design). No `seldon.yaml` — not a Seldon-managed project. `.venv` is intact (Python 3.12). LightRAG is installed in the venv. `rag_storage/` directory exists but is empty (LightRAG never successfully created an index). Log files (`lightrag_server.log` 114 KB, `lightrag.log` 351 KB) last written Feb 14, 2026.

**Assessment:** Last development activity was late March (planning docs only, no code). The Feb 14 log files suggest the last operational run was during the initial spike. Code exists; data does not.

---

### Wintermute Runtime Data (`~/.wintermute/`, 478 MB)

**Checked:** `ls -la`, `du -sh`.

**Found:** 25 top-level entries. Key directories:
- `inbox/` — staging area for incoming content
- `ingested/` — processed content  
- `logs/` — active logs (Apr 16 last modified)
- `staging/` — staging content including the bookdown chapters that ended up in `wintermute-intake` DB
- `email_triage/` (Apr 16)
- `ontology/` (Apr 18 — updated today by ClaudeClaw?)
- `wintermute-mcp/` — MCP server code (Apr 15)
- `scripts/` — cron-called shell scripts
- `.claude/claudeclaw/` — ClaudeClaw daemon state

**Assessment:** More active than the repo. ClaudeClaw is running jobs against it. The 478 MB is mostly staging content and logs.

---

### Wintermute MCP Server

**Checked:** `claude_desktop_config.json` for wintermute entry; `~/.wintermute/wintermute-mcp/server.py`.

**Found:** `server.py` exists (20,828 bytes, last modified Apr 14–15). It is a `FastMCP`-based server that exposes Wintermute's staging pipeline and `wintermute-intake` Neo4j graph as MCP tools. **Not registered in `claude_desktop_config.json`** — no entry for `wintermute` or `wintermute-mcp`. Not accessible to Claude Desktop.

**Assessment:** Code is written and recently updated, but not wired into the active MCP config. Dormant capability.

---

### LightRAG

**Checked:** `pip show lightrag`; wintermute `.venv`; `rag_storage/`; log file dates.

**Found:** Not installed in the base conda environment. Installed in wintermute's `.venv` (Python 3.12). `rag_storage/` in the wintermute repo is empty. Last logs Feb 14, 2026. The LightRAG webui (`index.html`) exists as a package asset inside the venv, not as a deployed service. A `lightrag_server.log` (114 KB) and `lightrag.log` (351 KB) exist from Feb 14.

**Assessment:** Spike-and-abandoned. The index was never populated (empty `rag_storage/`). The logs from Feb 14 represent the only operational activity. No usable retrieval infrastructure.

---

### claude-mem (thedotmack)

**Checked:** `npm list -g`, `which claude-mem`, plugin cache directory, PID file.

**Found:** Installed as a Claude Code plugin at `~/.claude/plugins/cache/thedotmack/claude-mem/10.5.2/`. The `claude-mem` alias points to a bun-executed worker script. **Marked `.orphaned_at 1775956510826`** (Unix timestamp ~ Apr 11 2026) — the plugin framework orphaned it, likely during a Claude Code update. No PID file; not running. The `claude-mem.db` SQLite file is not at the expected path inside `10.5.2/`. A separate version `ecb09df42002` also exists in the cache. The chroma vector store directory replaced by `bun.lock`, `hooks/`, `modes/`, `skills/`, `ui/` directories — different structure than expected.

**Assessment:** Installed, orphaned Apr 11, not running. Data state is unclear (db not at expected location). This appears to be dead infrastructure.

---

### mv2 Memory Skill (Mind)

**Checked:** `find` for `*.mv2` files.

**Found:** Three `.mv2` files:
- `~/.claude/mind.mv2` — 1.7 MB, Feb 28 — the global mind (base install)
- `/Users/brock/Documents/GitHub/seldon/.claude/mind.mv2` — 52 MB, **today (Apr 18, 10:21)** — the project-specific mind, actively updated
- `/Users/brock/Documents/GitHub/seldon/.claude/mind 2.mv2` — 30 MB, Mar 14 — an older snapshot

`~/.claude/skills/` does not exist as a directory. The mv2 files are binary (not Rust source code). The mind.mv2 is a plugin/skill installed via ClaudeClaw (`memvid-mind-context` visible in session system-reminder).

**Assessment:** Active and working. The project mind is 52 MB and updated this session. This is the currently functional memory layer.

---

### Hermes Agent

**Checked:** `pip show hermes-agent`, `which hermes-agent`, `~/.hermes/`.

**Found:** `~/.hermes/` exists with a full runtime directory: `state.db` (1.8 MB, last modified Mar 4), 15+ skill category directories, `config.yaml`, `logs/`, `memories/`, `SOUL.md`. The `~/.hermes/hermes-agent` subdirectory is the **cloned hermes-agent repo** (cloned Feb 28 based on timestamps), not an installed binary. `hermes-agent` is not on PATH. Not installed via pip.

ClaudeClaw is registered as a launchd agent (`ai.wintermute.claudeclaw`, PID 3452) and runs via bun. The `~/.hermes/` directory may be from an older version of Hermes that was a different system; or it was set up during an initial install but never fully wired up.

**Assessment:** Runtime directory exists with modest data (last activity Mar 4). Not installed as an executable; not running. ClaudeClaw (which appears to be the evolved form of agent scheduling) is running instead and has its own job system.

---

### Wintermute HTML Explorer

**Checked:** `find` for `explorer.html`, `index.html` in wintermute directories.

**Found:** No dedicated Wintermute explorer HTML exists. The LightRAG package bundles a webui `index.html` (in the venv), but this was never deployed as a Wintermute-specific explorer. The staging content includes some HTML files (leaflet maps from census-r book). No standalone knowledge graph explorer.

**Assessment:** Does not exist as a distinct tool. The LightRAG webui was presumably the intended graph exploration interface but never got past the spike phase.

---

### ClaudeMEM

**Checked:** `find ~ -maxdepth 3 -name "*claudemem*"`.

**Found:** Nothing. No directory, config, process, or file named `claudemem` or `ClaudeMEM`.

**Assessment:** Never installed.

---

## Scheduled Processes

### Cron

Two cron entries:
1. `30 3 * * *` — `~/.wintermute/scripts/revert_kg_extract_schedule.sh` — reverts `knowledge_graph_extract` job schedule after a backlog-clearing run
2. `0 5 * * *` — `~/.wintermute/scripts/revert_prune_schedule.sh` — reverts `kg_prune` job schedule to nightly

These are one-shot schedule-reset scripts called after intensive runs. They write to job files in the ClaudeClaw jobs directory.

### Launchd

One relevant agent running:
- **`ai.wintermute.claudeclaw`** (PID 3452, `LastExitStatus=0`) — ClaudeClaw daemon. Running as `bun run .../claudeclaw/1.0.0/src/index.ts start --web`. This is the active autonomous job runner.

Active ClaudeClaw jobs found in `~/.wintermute/.claude/claudeclaw/jobs/`:
`api_key_watchdog`, `daily-activity-report`, `drain_inbox`, `email-triage-phase2`, `extract_arxiv`, `gemini_doc_review`, `graph_analytics`, `kg_calibration_digest`, `kg_index_rebuild`, `kg_prune`, `kg_review_scan`, `knowledge_graph_extract`, `medium-digest-scan`, `school_digest`, `search_papers`, `uh_ring_sync` (plus a `paused/` subdirectory).

**Assessment:** ClaudeClaw is the active autonomous agent layer. It is running Wintermute pipeline jobs on schedules (KG extraction, prune, inbox drain, email triage, arXiv search, etc.).

---

## MCP Configuration Audit

**Source:** `/Users/brock/Library/Application Support/Claude/claude_desktop_config.json`

All 14 configured MCP servers have commands that resolve to existing binaries. No stale paths found.

| Server | Command | Path exists? | Notes |
|---|---|---|---|
| gmail | `npx` | Yes | npm-based; no local path to check |
| trace | `/opt/anaconda3/bin/python` | Yes | Script path not checked |
| github | `npx` | Yes | npm-based |
| census-mcp | `/opt/anaconda3/envs/census-mcp/bin/python` | Yes | |
| neo4j-mcp | `neo4j-mcp` | Yes (on PATH) | Points to `arnold` DB |
| neo4j-pragmatics | `neo4j-mcp` | Yes | Points to `pragmatics` DB |
| neo4j-quarry | `neo4j-mcp` | Yes | Points to `quarry` DB |
| postgres-mcp | `/opt/anaconda3/envs/arnold/bin/postgres-mcp` | Yes | |
| arnold-profile | anaconda arnold env + script | Both exist | |
| arnold-training | anaconda arnold env + script | Both exist | |
| arnold-memory | anaconda arnold env + script | Both exist | |
| arnold-analytics | anaconda arnold env + script | Both exist | |
| arnold-journal | anaconda arnold env + script | Both exist | |
| seldon-mcp | `/opt/anaconda3/bin/seldon-mcp` | Yes | |

**Notable absences:** No `wintermute` MCP entry. No `claude-mem` MCP entry. No `hermes` MCP entry. The Wintermute knowledge graph (`wintermute-intake`) is accessible via `neo4j-mcp` if someone points it at that database, but there is no dedicated Wintermute tool server registered.

---

## Honest Unknowns

1. **`wintermute-intake` last ingestion date.** Nodes have no `created` timestamps, so last-write is indeterminate. Would need to inspect ClaudeClaw's job logs for `knowledge_graph_extract` to get the last run date.

2. **`seldon-sfv-paper` vs. `seldon-brock-projects` relationship.** Two Seldon databases exist for what appears to be the SFV paper. Which one is canonical? Checking the project configs for both databases (`seldon project list` or examining each DB's `_SeldonMeta` node) would clarify.

3. **claude-mem database location.** The `claude-mem.db` is not at `~/.claude/plugins/cache/thedotmack/claude-mem/10.5.2/claude-mem.db`. The plugin was orphaned on Apr 11. Whether any memory data was captured before orphaning and where it lives requires inspecting the ecb09df42002 version directory more carefully.

4. **LightRAG run history.** The 465 KB of logs from Feb 14 could say whether any documents were ever successfully indexed or whether the tool always errored. Did not read the logs.

5. **Hermes `~/.hermes/state.db` contents.** The 1.8 MB SQLite file from Mar 4 may contain memories, learned skills, or pipeline state from a brief operational period. Did not inspect the schema or content.

6. **Whether `~/.wintermute/ontology/` (modified today) is related to the Seldon ontology changes.** The timing coincides with yesterday's vocabulary_rules.yaml commit. Could be ClaudeClaw auto-updating something. Relationship unclear.

---

## Questions for Brock

1. **ClaudeClaw job load.** There are ~16 active ClaudeClaw jobs including KG extraction, email triage, arXiv search, and pruning. Are all of these intended to still be running? `kg_index_rebuild` and `knowledge_graph_extract` suggest ongoing Wintermute ingestion, but the Wintermute MCP server isn't registered for use. Who or what is consuming the extracted knowledge?

2. **`seldon-sfv-paper` vs. `seldon-brock-projects`.** Two Seldon project databases for what appears to be the same paper. The `seldon-sfv-paper` DB (88 nodes, last write Mar 28) looks like it predates the `brock-projects` umbrella approach. Is `seldon-sfv-paper` dead and safe to drop?

3. **`wintermute-intake` — active or archived?** The DB has 7,660 nodes with real content (bookdown chapters, arXiv papers) but no timestamps. ClaudeClaw jobs suggest ingestion is still occurring. Is the graph being read by anything, or just written to?

4. **Hermes vs. ClaudeClaw.** `~/.hermes/` has state from Mar 4; ClaudeClaw is running as a launchd agent with an active job queue. Are these the same concept at different versions, or were they parallel experiments? The `ai.wintermute.claudeclaw` label suggests ClaudeClaw is the successor.

5. **Wintermute MCP — intentionally not registered?** The `server.py` was updated Apr 14–15 but is not in `claude_desktop_config.json`. Is this because it's not ready, or was it deregistered? The neo4j-mcp servers can read `wintermute-intake` already, but the Wintermute server exposes staging pipeline tools that neo4j-mcp doesn't.
