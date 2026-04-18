# CC3: Measurement-Function Audit — 2026-04-18

**Date:** 2026-04-18
**Executor:** Claude Code session
**Purpose:** For Phase C evolution burst synthesis. Kill-list input.

---

## Matrix

| Component | Claimed improvement | Measurement function | Do we know it works? |
|---|---|---|---|
| mv2 memory skill (Mind) | Cross-session project context — the `.mv2` file carries project-specific memory so new sessions don't start cold. Source: session system-reminder header. | Recall accuracy: did the session start with correct working state? Would require structured prompts + graded recall evaluation. NONE exists today — would need to build a session-start quiz protocol. | **Yes, qualitative evidence.** The 52 MB seldon project mind is loaded each session (confirmed by system-reminder). No accuracy measurement. |
| Seldon ontology sync (AD-017) | Terminology consistency across projects — prevents T1 Semantic Drift by centralizing the validity vocabulary in one master DB and pushing read-only replicas to project graphs. Source: AD-017. | Epoch drift: compare master epoch to each project's `_OntologyReplicaMeta.synced_epoch`. OntologyTerm count parity: master should equal replica. Violations would show as divergent counts. | **Yes, qualitative evidence.** 105 terms in master; 105 in ai-workflow-design and seldon-self replicas. But `synced_epoch` is `None` in all project replicas inspected — tracking metadata not fully wired. Sync happened (Apr 5 and Apr 13); epoch drift is undetectable. |
| AD-019 Agentic Content Audit | Content-level audit of prose — classifies assertions (fact/judgment/conjecture), identifies citation gaps, generates Perplexity queries, creates Issues for cross-section impacts. Source: AD-019, auditor.md agent. | Issue closure rate per audit run: how many `citation_gap` / `unsupported_claim` Issues were created and subsequently resolved? Run-over-run comparison: did blocking issues from run-N get closed by run-(N+1)? | **Yes, qualitative evidence.** 3 projects have audit runs (brock_projects, ai-workflow-design, icsp_notebook). brock_projects run-002 (Apr 17) assessed SFV as "ready_for_submission" after tracking all 4 prior blocking issues to resolution. Findings provably changed the paper. |
| AD-020 Multi-Lens Review | Comprehensiveness evaluation — catches what's missing (practitioner utility, cognitive depth, narrative structure) not just what's wrong. Source: AD-020, cascade-checker.md agent. | Convergent-finding uptake rate: how many multi-gate-convergent findings led to author edits? Did sections improve on re-audit after addressing synthesis recommendations? | **Yes, qualitative evidence.** bloom_depth_check, practitioner_stress_test, secondary_sweep, cascade_results all ran in brock_projects run-002. Run-manifest shows convergent findings with rankings. No uptake rate tracked (no before/after comparison structure). |
| Seldon MCP tools (seldon_go, seldon_task_*, seldon_issue_*, seldon_cc_*) | Desktop sessions can manage graph artifacts — create tasks, close stale items, register CC completions — without writing CC tasks. Source: AD-021, CLAUDE.md. | Desktop-originated vs. CC-originated mutation ratio. Stale `proposed` task cleanup rate. LabNotebookEntry creation rate post-MCP-tooling vs. before. | **Yes, qualitative evidence.** Events in JSONL show `"actor": "desktop"` state transitions. 26 completed ResearchTasks, 13 proposed in seldon-self graph. `seldon cc complete` confirmed working this session. |
| Claude project skills (briefing/closeout/result-register/task-track/research) | Structured session protocol — orient → work → close, with graph registration of results and tasks. Source: CLAUDE.md Session Protocol. | LabNotebookEntry creation rate. Result artifact count with provenance. Time-to-briefing (proxy: how often briefing produces actionable delta vs. stale). | **No, but should be measurable.** 7 LabNotebookEntries in seldon-self; most recent is Apr 3 (2+ weeks ago). Content hashes on PaperSections confirm sync runs. But usage has apparently lapsed — no closeout-generated entries visible since Apr 3. |
| Wintermute MCP server | Claude access to Wintermute staging pipeline tools and `wintermute-intake` graph via MCP. Source: `~/.wintermute/wintermute-mcp/server.py` (inferred from design). | MCP tool call success rate; staging pipeline throughput via tool vs. direct. | **Known broken.** `server.py` last modified Apr 14–15 and is functional code, but NOT registered in `claude_desktop_config.json`. Zero Claude instances can access it. Code exists, capability does not. |
| claude-mem (thedotmack v10.5.2) | Persistent cross-session memory via plugin. Source: plugin install. | Memory retrieval accuracy; session-start context quality with vs. without. | **Known broken.** Orphaned Apr 11 by Claude Code plugin framework update. Not running. No PID. `claude-mem.db` not found at expected path. No data recovery path identified. |
| Perplexity-verification external loop | Citation fact-checking for audit-flagged claims. Source: AD-019 §4.2 ("dual-path search"), auditor.md. | Verified citation rate: claims audited → queries generated → queries executed → sources confirmed. Error discovery rate (claimed X, Perplexity says Y). | **No idea.** AD-019 correctly generates `perplexity_queries.md` files in audit runs (confirmed in brock_projects and ai-workflow-design runs). Whether Brock executes the queries is entirely manual and untracked. Generation side works; verification side leaves no artifact. |
| seldon verify | Pre-commit integrity validation — 7 checks covering ontology vocabulary, graph connectivity, artifact state consistency, glossary violations. Source: verify.py, CLAUDE.md. | Violation count per run tracked over time. Check-specific pass/fail rates. Would reveal which checks catch real violations vs. always-pass. | **No, but should be measurable.** Runs and passes (`seldon verify --quiet` → OK confirmed). Violation counts ARE computed on each run but NOT logged to the JSONL event store. Zero historical trend data. One verify event found in the JSONL log (vs. presumably dozens of runs). |
| seldon paper audit — Tier 1 (structural) | Build blocking on unresolved references, broken cross-references, missing figure captions. Source: AD-016. | Build success/failure rate on Tier 1 violations. Count of critical violations caught before commit. | **No, but should be measurable.** Infrastructure is implemented. Content hashes exist on all 10 PaperSections in brock-projects graph. No historical build pass/fail record was found. |
| seldon paper audit — Tier 2/3 (prose + style) | Flags sentence length violations, banned phrases, glossary synonym violations. Source: AD-016, vocabulary_rules.yaml. | Violation count per section per audit run. Trend: did violation counts decrease after fixes? | **Yes, qualitative evidence.** Glossary gate caught 17 vocabulary violations in SFV sections during this burst (previously masked by a parser bug in the old check_glossary.py). Demonstrates real-violation detection. No longitudinal trend data. |
| seldon paper sync | Keeps graph current with disk — content hashes, `cites` edges, section state transitions from `review`/`published` back to `stale`. Source: CLAUDE.md Paper Editing Workflow. | Hash drift rate: sections on disk with different hash than graph. Stale-state transitions triggered per sync. | **Yes, qualitative evidence.** Content hashes present and current in brock-projects PaperSection nodes. `_OntologyReplicaMeta.synced_at` timestamps confirm sync ran. No hash-drift counter logged. |
| seldon paper build | Reference resolution + Quarto render. Validates that all `{{result:...}}`, `{{figure:...}}`, `{{cite:...}}` tokens resolve. Source: CLAUDE.md. | Unresolved reference count per build run. Build exit code (0 vs. 1). | **No, but should be measurable.** Build infrastructure exists and reference tokens are present in section files. No build run history found in the event log or audit run manifests. Whether it has been run on SFV sections recently is unknown. |
| seldon docs check | Documentation completeness checker — surfaces artifacts missing required documentation properties. Source: CLAUDE.md. | Documentation gap count per artifact type. Trend: did gap count decrease after documentation sessions? | **No idea.** Command exists. Zero evidence it has been run in any project, used to drive any documentation session, or produced any change in behavior. No output files, no event log entries, no mentions in handoffs found. |
| ClaudeClaw autonomous jobs (16 active) | Continuous Wintermute pipeline orchestration — KG extraction, email triage, arXiv search, inbox drain, pruning. Source: launchd agent, job files. | Job success/failure rate per job type. KG node growth rate per week. Email triage accuracy (emails correctly classified). arXiv paper relevance rate. | **No idea.** Daemon is running (PID 3452, LastExitStatus=0). Logs exist (Apr 16 most recent). But: what the jobs are PRODUCING is unexamined. No quality metric on KG extractions. No triage accuracy measurement. No relevance score on arXiv finds. Running blind. |
| Hermes Agent | Local orchestrator agent — arXiv triage, autonomous pipeline tasks. Source: `~/.hermes/` runtime directory, SOUL.md. | Agent task completion rate. Quality of autonomous outputs vs. manual baseline. | **Known broken.** `~/.hermes/` exists with state.db (Mar 4) but Hermes is not installed as an executable, not on PATH, not running. ClaudeClaw appears to be the operational successor. |

---

## Per-Component Notes

### mv2 memory skill (Mind)

Three `.mv2` files: global (`~/.claude/mind.mv2`, 1.7 MB, Feb 28), seldon project (`seldon/.claude/mind.mv2`, 52 MB, Apr 18), and an older seldon snapshot (`mind 2.mv2`, 30 MB, Mar 14). The project mind is actively updated this session (confirmed by system-reminder header). The 52 MB size suggests substantial accumulated context.

The measurement gap is that "working" is assumed from the fact that it loads. Whether the context it provides is accurate, relevant, and not stale is never tested. A memory file that loads doesn't mean the memories are right.

---

### Seldon ontology sync (AD-017)

AD-017 is marked "Implemented" and the evidence confirms it: 105 terms in master, 105 replicated to project DBs. The `_OntologyReplicaMeta` node records `synced_at` (timestamps Apr 5 and Apr 13 for two projects) but `synced_epoch` is `None` in all replicas inspected. This means the epoch-based delta sync — the mechanism designed to prevent redundant full syncs — is partially non-functional. `synced_at` is correct; epoch tracking is not.

The AD says projects "store the epoch they last synced to." They don't. This is a spec-vs-implementation gap.

---

### AD-019 Agentic Content Audit

Four audit runs across three projects (brock_projects: run-001 Apr 13, run-002 Apr 17; ai-workflow-design: runs 001–004 Apr 5–6; icsp_notebook: runs 001–003 Apr 16–17). The brock_projects run-002 manifest is the strongest evidence: it tracks 4 prior blocking issues to resolution and declares the SFV paper "ready_for_submission" — a direct statement of before/after quality change.

The Perplexity query file generation works (files exist in audit run directories). Execution is manual and leaves no trace in the system.

---

### AD-020 Multi-Lens Review

brock_projects run-002 ran all AD-020 gates: bloom_depth_check, practitioner_stress_test, secondary_sweep, cascade_results. The synthesis document ranks findings by convergent-gate count, which is the right mechanism. Whether the author addressed the synthesized recommendations is visible only by diffing sections — no automated tracking.

---

### Seldon MCP tools

`seldon-mcp` is registered in `claude_desktop_config.json` at `/opt/anaconda3/bin/seldon-mcp`. The JSONL event store shows Desktop-originated transitions ("actor": "desktop") and CC-originated ones ("actor": "cc"). This confirms the tool surface is live for both contexts. The per-project database isolation per AD-021 is working — MCP calls resolve the project-specific database from `seldon.yaml`.

---

### Claude project skills (briefing/closeout/result-register/task-track/research)

Five skills in `.claude/skills/`: briefing.md, closeout.md, research.md, result-register.md, task-track.md. Last modified Mar 10. The 7 LabNotebookEntries in seldon-self (all from Apr 3) suggest closeout was used actively then and has lapsed. Whether this is a workflow compliance gap or a period of Desktop-only sessions (which don't run CC-based closeout) is unclear.

---

### Wintermute MCP server

The `server.py` exposes staging pipeline tools (`ingest_document`, `query_graph`, `list_staged`, etc.) via FastMCP. It was updated Apr 14–15, suggesting recent development activity. But it is not registered — no entry in `claude_desktop_config.json`. No Claude instance can call it. This is dead capability, not dead code.

---

### Perplexity-verification external loop

This is a workflow, not installed software. AD-019 specifies it as "dual-path search (web + Perplexity) for every factual claim." The audit pipeline generates formatted query files. The actual Perplexity execution is fully manual — Brock opens Perplexity, runs queries, records results. No artifact captures whether queries were run, which claims were verified, or how many errors were found. The generation automation works; the execution and result capture do not exist as a system.

---

### seldon verify

Seven checks: graph connectivity, ontology vocabulary violations, artifact state consistency, Tier A blocking issues, and others. The command runs. One entry in the JSONL event log (from this session, which observed `seldon verify --quiet` → OK). The verify command does NOT write its results to the event store. There is no trend data. If the vocabulary gate catches 17 violations today but 0 violations in a month, that change is invisible.

---

### seldon paper audit — Tier 1 (structural)

The Tier 1 check structure (build blocking on unresolved references) exists in the codebase. Content hashes on PaperSection nodes in brock-projects confirm `paper sync` has run. No build failure log or build history found. The check is theoretically functional; its operational track record is not observable.

---

### seldon paper audit — Tier 2/3 (prose + style)

The vocabulary gate correctly detected 17 violations during this evolution burst — violations that the old `check_glossary.py` missed due to a parser bug (exempt substring matching the banned phrase itself). This is real-violation detection at the prose level. The measurement gap is no per-section, per-run violation count history.

---

### seldon paper sync

`_OntologyReplicaMeta.synced_at` timestamps and content hashes on PaperSection nodes confirm sync has run. The mechanism works. No hash-drift counter is logged, so there's no way to observe whether sections are going stale faster or slower over time.

---

### seldon paper build

Reference token resolution infrastructure exists. No build history in the event log or audit run manifests. Whether `paper build` has been run recently on the SFV paper with the new vocabulary_rules.yaml in place is unknown.

---

### seldon docs check

The `seldon docs check` command is listed in CLAUDE.md's skills table. No evidence of it ever being invoked was found in the JSONL event log, any audit run manifest, or any handoff file. No output directory, no mentions. The command may not be fully implemented or may be implemented but never used.

---

### ClaudeClaw autonomous jobs

The daemon runs 16 jobs: `api_key_watchdog`, `daily-activity-report`, `drain_inbox`, `email-triage-phase2`, `extract_arxiv`, `gemini_doc_review`, `graph_analytics`, `kg_calibration_digest`, `kg_index_rebuild`, `kg_prune`, `kg_review_scan`, `knowledge_graph_extract`, `medium-digest-scan`, `school_digest`, `search_papers`, `uh_ring_sync`. `knowledge_graph_extract` is writing to `wintermute-intake` (7,660 nodes), but no timestamps exist on nodes so growth rate is unknown. Email triage accuracy, arXiv relevance, and KG extraction quality are entirely unmonitored.

---

### Hermes Agent

`~/.hermes/` has a runtime directory with 15+ skill category subdirectories, `config.yaml`, `SOUL.md`, and `state.db` (1.8 MB, Mar 4). The subdirectory `~/.hermes/hermes-agent/` is the cloned repo, not an installed binary. Not on PATH. State was last written Mar 4, 2026 — 6 weeks ago. ClaudeClaw is the running autonomous agent; Hermes appears to be a prior or parallel experiment that was never fully operationalized.

---

## Measurement Dependency Chains

**Chain 1: Ontology → Verify → Paper Audit**
`seldon ontology ingest` (master write) → `seldon ontology sync` (replica pull) → `seldon verify` (vocabulary gate checks replicated terms) → `seldon paper audit` (glossary enforcement against sections). If the vocabulary hasn't been synced, verify uses stale terms. If verify doesn't run, the vocabulary gate is skipped.

**Chain 2: AD-019 → Perplexity Loop → Citation State**
AD-019 auditor generates citation gap Issues + Perplexity query files → Brock executes queries manually → Brock resolves Issues in graph via MCP or CC. If the manual step is skipped, citation gap Issues age out without closure, and the graph accumulates open Issues that are actually already resolved (or abandoned). No artifact tracks whether queries were run.

**Chain 3: Paper Sync → Paper Build → Build Validity**
`paper sync` (hash update, cites edges, state transitions) → `paper build` (reference resolution). If sync hasn't run after edits, build may succeed on stale graph state — the references resolve against cached provenance that no longer matches disk. Build validity depends on sync recency.

**Chain 4: AD-019 quality → AD-020 completeness**
AD-020 Tier 2/3 lenses are more useful after Tier 1 (AD-019) has verified the claims. Running practitioner stress test on content with unchecked facts is noise amplification — the practitioner "missing perspective" finding may point to a section that was already flagged for deletion by Tier 1. Gates should run in order; auditor.md enforces this.

**Chain 5: ClaudeClaw → Wintermute KG → Wintermute MCP**
ClaudeClaw `knowledge_graph_extract` job writes to `wintermute-intake` → Wintermute MCP would expose that graph to Claude instances → currently no Claude instance can read it (MCP not registered). The full pipeline: ingestion runs, quality is unmeasured, and the output is inaccessible to any consumer. End-to-end the chain is broken at the last step.

---

## Analysis

- **Components with no measurement function:** 4 of 17 — seldon docs check (no evidence of any run), ClaudeClaw job effectiveness (no quality metric on any job output), Perplexity-verification loop (execution side untracked), mv2 memory recall accuracy (no evaluation protocol). Additional components have measurement functions that were never built into tooling (seldon verify violation trend, paper build history).

- **Components claiming improvements we cannot verify:** 7 of 17 — Wintermute MCP (not accessible), claude-mem (dead), Hermes Agent (not running), Perplexity-verification loop (execution untracked), seldon docs check (never observed in use), ClaudeClaw job quality (output not evaluated), mv2 memory recall accuracy (no measurement protocol).

- **Biggest measurement gap:** ClaudeClaw. The daemon runs 16 jobs continuously, writing to the Wintermute knowledge graph and email triage output. Zero quality measurement exists on any of these jobs. The KG extraction may be producing duplicate entities, wrong claim classifications, or incoherent relationships — and there is no mechanism to detect this. 478 MB of runtime data accumulates with no verification that any of it is useful or correct. This is the highest-risk blind spot: an autonomous system operating at scale with no observable outcomes.

- **Easiest measurement win:** seldon verify. Violation counts are already computed on every run. Adding five lines to the JSONL event emitter — logging each check name and violation count — would produce a historical trend with zero additional infrastructure. A week of run history would reveal whether the vocabulary and ontology gates are catching real violations or are always-passing due to coverage gaps.

---

## Honest Unknowns

1. **Perplexity query execution rate.** Query files exist. Whether any were ever executed, and how many of the `citation_gap` Issues they were supposed to resolve were actually fact-checked, is completely unobservable. A simple convention (log the Perplexity session ID to the Issue artifact when resolving it) would close this.

2. **seldon docs check implementation status.** The command is listed in CLAUDE.md but no evidence of a run exists in any inspected artifact. It could be fully implemented and never used, partially implemented, or a stub. Did not run the command (per scope boundaries).

3. **ClaudeClaw job output quality.** The `wintermute-intake` graph has 7,660 nodes but no timestamps and no quality labels. Whether the KG extraction is accurate, whether email triage is correctly routing messages, whether arXiv search is surfacing relevant papers — all unknown. Answering this requires inspecting job logs and sampling outputs against a quality rubric.

4. **mv2 mind staleness.** The 52 MB project mind contains memories accumulated over weeks. Whether any of those memories are now incorrect (referring to code that was refactored, tasks that were completed, decisions that were reversed) is not assessed. A memory accuracy check would require sampling memories against current codebase state.

5. **AD-016 Tier 1 structural check operational record.** Whether `seldon paper build` has ever exited 1 on a Tier 1 violation in production (not test) is not knowable from the JSONL event log as currently structured.

---

## Questions for Brock

1. **Perplexity queries: are they being executed?** The audit pipeline generates `perplexity_queries.md` files in every run. The SFV run-002 will have one. Has Brock been running these against Perplexity and recording the results? If not, the "dual-path citation verification" that AD-019 describes is half-implemented.

2. **seldon docs check — real or aspirational?** Is `seldon docs check` fully implemented and just not used, or is it a stub from CLAUDE.md documentation that was never built? Answering this without running the command requires reading the source — not done per scope boundaries.

3. **ClaudeClaw job quality — is anyone reading the output?** The `daily-activity-report` job suggests some kind of digest is produced. Is that digest being read? Are the KG extractions feeding any downstream consumer? Or is ClaudeClaw running jobs that produce output nobody reads?

4. **mv2 mind: project vs. global.** The global mind (`~/.claude/mind.mv2`) is 1.7 MB from Feb 28 and apparently frozen. The seldon project mind (52 MB) is actively growing. Is the global mind effectively retired in favor of project-specific minds? If so, the `~/.claude/mind.mv2` is dead weight being loaded for every non-seldon session.

5. **Ontology sync epoch tracking.** All project replicas show `synced_epoch = None`. The sync mechanism works (terms are replicated) but epoch tracking doesn't. Is this a known gap, or is it an undetected implementation bug in the sync command?
