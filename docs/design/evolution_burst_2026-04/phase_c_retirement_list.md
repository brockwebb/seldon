# Phase C — Infrastructure Retirement List

**Date:** 2026-04-18
**Status:** Final for this burst
**Scope:** Infrastructure, components, MCP tools, dead code. **NO projects. NO data. NO graph artifacts except where genuinely redundant.**

---

## Verification Pass (Run First)

- ✅ No project slugs appear as retirement targets below.
- ✅ No data or event-log entries appear as retirement targets.
- ✅ All items below are infrastructure, components, MCP registrations, or dead code.
- ✅ Each item has cited evidence from CC2 or CC3 (the only valid sources for retirement candidates).
- ✅ `seldon-sfv-paper` database explicitly retained per operator decision (2026-04-18). Not on this list.
- ✅ ClaudeClaw and its 16 jobs explicitly retained per operator clarification — operator is the consumer; "no measured consumer" was a measurement-gap error, not a missing-consumer fact.

---

## Tier 1 — Retire Now (Action This Burst)

These are safe to remove or deregister immediately. Evidence is unambiguous.

### R1. LightRAG installation + empty `rag_storage/`

**Evidence:** CC2 — installed in wintermute `.venv`, `rag_storage/` empty, logs frozen 2026-02-14. Spike-and-abandoned; no usable index was ever produced.
**Action:** Delete `.venv` LightRAG packages and `rag_storage/` directory. Keep any source notes (research value) but remove the runtime footprint.
**Reversibility:** High. LightRAG is a package install; reinstalling takes minutes.
**Risk if kept:** Confusion about whether Wintermute has a retrieval layer (it doesn't; this is dead weight).

### R2. claude-mem thedotmack install (v10.5.2)

**Evidence:** CC2 — marked `.orphaned_at` 2026-04-11 by Claude Code plugin framework update. `claude-mem.db` not at expected path. CC3 — "Known broken."
**Action:** Remove the orphaned install.
**Important:** This retirement is independent of the adopt-vs-extract decision made in Phase C. The operator chose **Option A (adopt claude-mem)**, which means a fresh, supported claude-mem install will follow as part of the 15% roadmap work. What's being retired here is the v10.5.2 install that's already been orphaned — not the adopt decision.
**Reversibility:** High.

### R3. Hermes Agent install (runtime without binary on PATH)

**Evidence:** CC2 — `~/.hermes/` runtime exists with state.db (frozen 2026-03-04), binary not on PATH. CC3 — "Known broken," parallel experiment superseded by ClaudeClaw.
**Action:** Archive `~/.hermes/state.db` (cheap insurance — 1.7 MB class), then remove the runtime directory.
**Reversibility:** High. Hermes Agent reinstalls from source if ever needed.
**Note:** The LeStat-on-Hermes vision document (`lestat_project_scope.md`, Feb 2026) is a design artifact, not a retirement target. That document's core thesis — autonomous foraging for Wintermute — is now realized through ClaudeClaw. The document stays as historical context.

### R4. Wintermute MCP server — not registered

**Evidence:** CC2 — code at `~/.wintermute/wintermute-mcp/server.py` updated 2026-04-14/15, but NOT present in `claude_desktop_config.json`. CC3 — zero consumers can reach it.
**Action:** **Conditional.** Two paths:
  - **(a) If AD-023 is promoted (sleep functions are Wintermute's center):** re-register the MCP server so the `wintermute arbitrate` interface has a Desktop path. Retirement **rescinded.**
  - **(b) If AD-023 is deferred:** deregister the code path formally by moving `server.py` to `_archived/` with a dated README. No point maintaining an unreachable endpoint.
**Operator note (2026-04-18):** AD-023 is being promoted this burst, so path (a) applies. Re-registration becomes a follow-on action, not a retirement.

### R5. `seldon-test` and `seldon-test-project` Neo4j databases

**Evidence:** CC2 — disposable by their own label. No production use.
**Action:** Drop both databases after confirming no active references in scripts or configs. Export schema first (cheap insurance).
**Reversibility:** High. Test databases regenerate trivially.

---

## Tier 2 — Known-Broken-But-Not-Retired (Keep With Explicit Status)

These look retirable on CC3's "Known broken" / "No idea" verdicts but have load-bearing reasons to keep.

### K1. `wintermute-intake` graph (7,660 nodes, no timestamps)

**Why not retired:** ClaudeClaw is actively writing to it, and the operator uses the extracted content. The measurement gap ("no timestamps") is a schema improvement, not a retirement signal. Retiring this would break ClaudeClaw's `knowledge_graph_extract` pipeline.
**Follow-on action (not retirement, roadmap):** Add `updated_at` to the Wintermute node schema. This is a 75% bucket item.

### K2. mv2 global mind (`~/.claude/mind.mv2`, 1.7 MB, frozen 2026-02-28)

**Why not retired:** CC3 flagged as "No idea" on retirement-vs-keep. The frozen timestamp is ambiguous — could be "retired in favor of project-specific minds" or "still loads but is rarely updated." No evidence of harm in keeping it.
**Follow-on action:** Not retirement. Operator decides if/when to sunset during normal mv2 work.

---

## Not On This List (And Why)

Items pre-surfaced in the reading notes that **did not make the final cut**, for scope-integrity reasons:

- **`seldon-sfv-paper` database** — retained by operator decision 2026-04-18. Unique state not yet confirmed migrated to `seldon-brock-projects`.
- **Any project** — standing principle. Projects are never retired. Includes `ai4stats`, `sas2graph`, `leibniz-pi`, all active and dormant projects.
- **ClaudeClaw or any of its 16 jobs** — the operator is the consumer. "No measured consumer" is a measurement-gap fact, not a missing-consumer fact. The consumer exists; the metric doesn't.
- **ADs AD-001 through AD-021** — CC1 pattern extraction didn't surface evidence that any of these are superseded. A dead-weight AD audit is noted as a post-burst task (not this burst).
- **Historical events, artifacts, graph nodes** — never killed. Event sourcing is non-negotiable.

---

## Summary Counts

| Tier | Count |
|---|---|
| Retire this burst (R1–R3, R5) | **4 items** |
| Conditional (R4, retired OR rescinded based on AD-023) | **1 item → 0 after AD-023 promotion** |
| Keep with explicit status (K1, K2) | **2 items** |
| Total infrastructure removed this burst | **4 items** |

Four items is the honest number. Not eye-popping, but scope-clean.

---

## AGPL Note (for AD-023 and roadmap)

Per operator decision 2026-04-18: AGPL tolerance is **fine for personal infra**. claude-mem adoption proceeds under Option A. If Seldon/Wintermute ever evolves into something other researchers would adopt, the AGPL boundary at the claude-mem layer becomes a live question — but that's a future-you problem, not a Phase C problem. Documented here so it's findable.

---

*End of retirement list. Verification pass complete. Ship.*
