# Phase C — 75/15/10 Roadmap + Three-Item Commit Point

**Date:** 2026-04-18
**Status:** Final for this burst
**Scope:** Post-burst engineering direction. Commit point ends the burst; everything else is backlog with explicit prioritization.

---

## Three-Item Commit Point

**These three items ship this burst. When all three are done, the burst is over and the operator returns to papers.** No fourth item. If a fourth feels essential, it goes in the 75% bucket, not the commit point.

### Commit 1 — `seldon verify` violation logging

**What:** Add ~5 lines to `seldon/commands/verify.py` to emit each violation to the JSONL event store with timestamp, violation type, artifact reference, and severity.
**Why:** CC3's "easiest measurement win." Gives AD-019/020 audit pipelines a historical trend — does `seldon verify` catch real violations over time, or has it been always-pass since inception? Without this, the gate is operating unmeasured.
**Size:** One CC task. Hours, not days. 5 LOC + one new event type.
**Dashboard impact:** CC4 Q-b (gate activity) gains a new series.
**Verification:** Run `seldon verify` on a known-dirty artifact, confirm JSONL entry written. Run on clean artifact, confirm no entry. Query event log for `verify.violation` entries and render in dashboard.

### Commit 2 — Dual-model audit loop (AD-019/020 SPOF break)

**What:** Add `AUDIT_MODEL` environment variable + LiteLLM-compatible endpoint configuration, routing the AD-019 auditor subagent through a second model family (Gemini Flash or Claude Sonnet — not whichever model the authoring session uses). Reference: CC1 pattern #8 + #9 (k-dense-byok).
**Why:** Breaks the single-model audit SPOF flagged in the parent handoff as one of three current SPOFs in the system. Audit credibility improves immediately once authoring and audit run on different model families. Closes the "single-model audit-revise closed loop" problem userMemories flagged as open.
**Size:** One, possibly two CC tasks. LiteLLM config + subagent definition update + one round of testing on a real SFV audit pass.
**Dashboard impact:** Requires no new metrics — existing AD-019 telemetry works.
**Verification:** Run an SFV audit with the current model, then with `AUDIT_MODEL` set to a different provider, compare findings. Expect non-zero divergence (different models catch different things; that's the point).

### Commit 3 — Phase C infrastructure retirement executed

**What:** Execute the 4-item Tier 1 retirement list (`phase_c_retirement_list.md`): LightRAG, claude-mem thedotmack v10.5.2, Hermes Agent install, `seldon-test` + `seldon-test-project` databases.
**Why:** Subtraction before addition. Visceral, verifiable "the burst shipped something." The operator's repo and `.venv` get smaller; `~/.hermes/` and dead installs stop showing up in audits; two test DBs disappear from the 18-database Neo4j listing.
**Size:** One CC task. Script-driven cleanup with verification commands.
**Verification:** After execution, CC2's infrastructure inventory should show 4 fewer items. `ls ~/.wintermute/` and `ls ~/.hermes/` should match the expected post-retirement state. Neo4j database count drops from 18 to 16.

**Explicitly NOT in the commit point:** AD-022, AD-023, AD-024 promotions. These are doc work, they ship as part of normal synthesis output this session, and they don't count toward the commit-point cap. See § AD Promotions below.

---

## 75% Bucket — Highest-ROI Near-Term Wins

Shippable within 1–3 CC tasks each. Measurement wins dominate. These are the things that, once done, make every subsequent burst cheaper.

| # | Item | Source | Est. size |
|---|---|---|---|
| 75.1 | `seldon verify` violation logging (**Commit 1** — ships this burst) | CC3 | XS |
| 75.2 | Dual-model audit loop (**Commit 2** — ships this burst) | CC1 pattern #8/#9 | S |
| 75.3 | `updated_at` property added to node schema (Seldon + Wintermute) | CC4 limitation #5 | S |
| 75.4 | `REMEDIATED_BY` edge type added to Seldon graph schema | CC4 limitation #4 | XS |
| 75.5 | LabNotebookEntry creation rate tracked per-session (briefing/closeout usage) | CC3 | S |
| 75.6 | `seldon paper audit` Tier 1 build history via event log | CC3 | S |
| 75.7 | Perplexity query execution tracking (Issue → Perplexity session ID linkage) | CC3 | S |
| 75.8 | Ontology sync `synced_epoch` tracking completion (partially implemented, finish it) | CC3 | S |
| 75.9 | Dashboard daemonization — launchd plist for `observability_dashboard.py` | CC4 limitation #8 | XS |
| 75.10 | `seldon docs check` status investigation — real, stub, or aspirational? | CC3 Q5 | XS (investigation only) |
| 75.11 | Dual-model audit: add third provider to ensemble once two-model loop proves stable | follows 75.2 | M |
| 75.12 | k-dense-byok pattern #15 — formalize SKILL.md YAML frontmatter + markdown body convention in Seldon | CC1 pattern #15 | S |
| 75.13 | Agentic-data-scientist pattern #4 — dual-agent confirmation gate for AD-019/020 iterate/proceed decisions | CC1 pattern #4 | S |

**Principle:** Everything in this bucket has either (a) obvious measurement value once it ships, or (b) cheap infrastructure cost for clear operational benefit. Nothing in this bucket is speculative.

---

## 15% Bucket — Long-Lead Solid-Value

Multi-burst or multi-week work where value is clear but implementation is non-trivial. These are commitments, not experiments.

| # | Item | Source | Notes |
|---|---|---|---|
| 15.1 | **claude-mem adoption (Option A)** — install fresh, configure 5-hook lifecycle, bridge PostToolUse observations to Wintermute entity nodes | CC1 Q4 | AGPL accepted (operator decision). First step: confirm supported version post-v10.5.2. |
| 15.2 | **Wintermute Sleep Function A (Collapse/Dedup)** — three-layer pattern from CC5 — deterministic SemHash pre-dedup, LLM-proposed merges at 0.90/0.50 thresholds, human YAML review | CC5 AD-023 | Requires: ClaudeClaw entity-quality sample first (CC5 Q2); `wintermute arbitrate` CLI; Wintermute MCP server re-registered (see retirement R4 conditional). |
| 15.3 | Seldon skill discovery — sentence-transformers + cosine indexing over Seldon artifact corpus, 4-level progressive disclosure | CC1 patterns #1, #2 | High leverage: every `seldon go` session gains better context injection. |
| 15.4 | Agentic-data-scientist pattern #5 — persistent success-criteria tracking with file-level evidence for CC task enforcement | CC1 pattern #5 | Fills known gap where CC success contracts are prose-level, not tracked. |
| 15.5 | Wintermute ingestion schema audit + timestamp backfill | CC4 limitation + CC5 honest unknown #2 | Prerequisite for sleep functions to be meaningful. |

**Claude-mem path (15.1) detail:** Operator chose Option A. Work items:
  (a) Retire v10.5.2 orphaned install (Retirement R2, ships in Commit 3).
  (b) Install current supported version.
  (c) Configure hooks (`PostToolUse`, `SessionStart`, `SessionEnd`, `UserPromptSubmit`, `PreCompact`).
  (d) Build bridge: claude-mem observation → Wintermute Entity/Claim node (CC1 Q4 specifies the CLAIM-CONFIRM queue pattern).
  (e) Monitor for adopt-vs-extract regret over 30 days. If AGPL becomes inconvenient for external reasons, extract path is still open (not ideal, but reversible).

---

## 10% Innovation Bets

**Rule:** Each bet has a kill criterion written BEFORE work starts. No exceptions. If the kill criterion fires, the bet ends — no grace period, no "just one more iteration."

### Bet 10.1 — Wintermute Sleep Function C (LLM-Proposed Edge Inference) at v1

**Thesis:** Cross-domain edge discovery via LLM-scored candidate pairs will reveal non-obvious connections in the Wintermute graph that the operator actually finds useful (not just "interesting"). This validates Sleep Function C's claim to be worth the compute cost.

**Kill criterion (ANY triggers termination):**
- 30 days after first operation: **rejection rate > 50%** → the LLM is producing mostly wrong edges, not a worthwhile signal.
- **auto-accept rate outside 0.20–0.60** after threshold calibration window → threshold miscalibration unfixable with current signals.
- **Zero edges surfaced via "cross-domain" lens** that the operator flags as genuinely novel in the first 60 days → the function isn't finding what it claims to find.

**If killed:** Double down on Sleep A+B. Edge inference becomes a v2/v3 concern, not a 2026 concern.

**Explicitly deferred until Sleep A is operational:** Sleep C depends on the entity space having been cleaned by Collapse/Dedup first. Don't start this bet until 15.2 has been running for ≥ 2 weeks.

### Bet 10.2 — Claude-mem + Wintermute bidirectional context injection

**Thesis:** claude-mem's session observations feed Wintermute; Wintermute's sleep-function insights feed back into claude-mem's `SessionStart` hook. A feedback loop where each session is informed by the cross-session graph cognition the previous sessions contributed to. This is the "living system" vision for Wintermute v2.

**Kill criterion:**
- After 60 days: operator cannot point to a specific instance where Wintermute-sourced context in a session improved the work (vs. just adding tokens) → the feedback loop isn't producing value, close it.
- SessionStart hook latency > 3 seconds due to Wintermute queries → operational friction exceeds value.

**If killed:** claude-mem adoption remains (it's the 15% commitment). The feedback loop is what's abandoned. Wintermute becomes read-side only for human queries, not session-injection.

**Prerequisites:** 15.1 (claude-mem adopted) + 15.2 (Sleep A operational) — both must be running before this bet starts.

---

## What Phase C Does NOT Commit To

- **ALMA meta-learning (PL-006).** Hard defer. Research-scale ambition, no operational data yet. Revisit when sleep functions have produced ≥ 6 months of data.
- **AD-001 through AD-021 dead-weight audit.** Noted as post-burst work, not in any bucket. CC1 patterns didn't surface specific supersession evidence.
- **Full-graph sleep function runs.** CC5 explicitly scoped Sleep A to neighborhood (24h + 1-hop). Full-graph is a v2 question.
- **Multi-provider ensemble for sleep functions.** CC5 spec names this as v2. Single-provider (Gemini Flash via LiteLLM) is v1.
- **Seldon engineering domain configuration.** Still blocked on "when a non-research project needs it." No trigger fired this burst.

---

## AD Promotions (Ship Alongside Commit Point, Not Counted Toward It)

Three ADs promote as normal doc work this burst. Each is a short file in `docs/design/`. They don't count toward the three-item commit point because they're already drafted — the work is formalization, not creation.

- **AD-022 (CLI-default, MCP-exception)** — promote. Short AD pointing at the governing principle in the 2026-04-18 parent handoff.
- **AD-023 (Wintermute sleep functions as architectural center)** — promote with one edit: surface the claude-mem Option A commitment explicitly in the Decision section, not only as an open question. (Operator decision 2026-04-18 chose Option A.)
- **AD-024 (Observability as substrate)** — promote as a short formalization pointing at the running CC4 dashboard + SQLite metrics store.

Drafts of each are in the three AD files alongside this roadmap.

---

## Risk Notes for Execution

1. **The commit point is three items. Not four.** If Commit 2 (dual-model audit) turns out to be two CC tasks instead of one, that's still one commit item. Don't split it into two and call it four items.

2. **Commit 3 (retirement execution) has the lowest technical complexity and the highest psychological payoff.** Do it first if momentum is lagging. Seeing 4 items actually removed from the inventory is motivating.

3. **Commit 2 (dual-model audit) has a hidden cost: testing it requires running a real audit.** Budget time for one SFV section audit pass using the new dual-model config. If this balloons, split off the "test on real audit" as a follow-on task and ship the infrastructure change alone.

4. **The 15% bucket has a sequencing risk.** Claude-mem adoption (15.1) and Sleep Function A (15.2) both depend on decisions that need operational data. If 15.1 is started before the supported claude-mem version is confirmed, the work gets thrown away. Verify supported version first.

5. **Opus 4.7 elaboration risk on this roadmap.** This document should be a working reference, not an essay. If it needs expanding, a section gets deleted to make room. Total length stays roughly what it is now.

---

## Scope Verification Pass

- ✅ No project slugs appear as retirement or deprioritization targets.
- ✅ "Retire" is applied only to infrastructure (R1–R5 in retirement list).
- ✅ "Dormant" not used in this document (not needed — no projects discussed in deprioritization framing).
- ✅ "Collapse" appears only in sleep-function context (graph deduplication), which is its correct use.
- ✅ Three-item commit point is three items, not four.
- ✅ Each 10% bet has a written kill criterion before the work starts.
- ✅ 75%/15%/10% allocation is by effort and priority, not by item count (75% has more items because individual items are cheap).

---

*End of roadmap. Ship the three committed items. The rest is backlog.*
