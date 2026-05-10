# AD-025: DeerFlow as Build-Time Harness, Not Runtime Substrate

**Status:** Accepted
**Date:** 2026-05-02
**Reversibility review due:** 2026-08-02 (90 days)
**Supersedes / amends:** None. Compatible with AD-001 through AD-024.

---

## Decision

DeerFlow 2.0 (ByteDance, open source) is adopted as the **build-time harness** for designing and scaffolding new capabilities across the Seldon ecosystem (Seldon itself, runtime products like Arnold, future tools).

DeerFlow is **not** adopted as a runtime substrate. It is **not** a Seldon dependency. It does **not** replace Claude Code for bounded implementation work. It is invoked deliberately, on-demand, with bounded lifetime measured in hours per run.

Three-layer model:

| Layer | Tool | Lifetime |
|-------|------|----------|
| Build / design | DeerFlow on OpenRouter (Kimi K2 primary, DeepSeek v3.2 fallback) | Hours, on-demand |
| Implementation | Claude Code via `claude --print` headless | Bounded sessions |
| Runtime products | Seldon CLI, Arnold MCP servers, Wintermute, etc. | Light, always-on |

LeStat as a separate codebase is retired. Foraging behavior moves to DeerFlow skills targeting Wintermute's graph. The 2026-02-26 LeStat scope doc is marked Historical.

---

## Rationale

The original LeStat scope (2026-02-26) duplicates approximately 80% of what DeerFlow ships out of the box: sandboxed filesystem per task, subagent fan-out with isolated context, skills as progressive-load Markdown modules, persistent SQLite memory, IM gateway (Telegram/Slack/Feishu), MCP support, durable checkpointing across multi-hour runs.

Continuing to hand-build that substrate is level-3 anchor work that blocks level-4 progress. A larger team has solved the orchestration / sandboxing / multi-agent harness problem at scale. Adopting their solution where it fits is wisdom, not capitulation.

DeerFlow earns its overhead specifically when:
- The problem benefits from parallel subagent exploration (try N approaches in parallel, pick winner)
- The problem requires sustained execution across context-window boundaries that would otherwise need manual handoffs
- The problem has natural decomposition into role-isolated subtasks (specialist agents with distinct retrieval profiles per AD-005 / PL-003)

It does **not** earn its overhead for single-file edits, bounded refactors, or work that fits in one Claude Code session. **Default is Claude Code for bounded implementation work; reach for DeerFlow when the multi-agent shape is real.**

---

## TOS posture

DeerFlow's planner runs on OpenRouter (Kimi K2 primary, DeepSeek v3.2 fallback). Both are cheap (~$0.20/M input tokens range) and adequate for planning/research roles.

Claude Max (200/month plan) is invoked only via `claude --print` headless mode for bounded implementation tasks the orchestrator delegates. This matches Anthropic's stated mental model: Claude Code = interactive bounded sessions, API = automation. It avoids the OpenClaw failure mode (Claude as persistent backend for a third-party harness, which Anthropic enforced against ~3 weeks before this AD).

OpenRouter integration is built **before** the Anthropic line moves, not after. If `claude --print` orchestrated invocation patterns become enforcement-restricted, fallback is configured and tested.

Token economics target per build run:
- DeerFlow planner phase: < $5 on Kimi/DeepSeek
- Claude Code implementer phase: stays within one 5-hour rolling Max window
- Total cash cost: pennies per run

Off-peak scheduling preferred (10pm-6am ET) to align with cheaper Anthropic burn windows and to use weekly headroom (currently ~15% utilization).

---

## Provenance contract: BuildRun events

DeerFlow's internal trace lives in `~/.deerflow/state.db` and stays there. It is **not** mirrored into Seldon's graph. Mirroring would pollute the graph with orchestration noise that has no provenance value at the artifact level.

At run completion, DeerFlow emits a single structured `BuildRun` event into the JSONL log of the target Seldon project. The event captures:

- `run_id` — unique identifier
- `goal` — the prompt/spec that initiated the run
- `plan_hash` — content hash of DeerFlow's planning phase output
- `models_used` — planner model, implementer model(s), validator model(s) and their costs
- `token_counts` — per-model token usage
- `subagents` — list of subagents spawned with their roles
- `files_produced` — list of file paths with content hashes and resulting commit SHAs
- `validation_results` — test pass/fail, lint results, `seldon verify` output
- `internal_trace_ref` — path or hash referencing DeerFlow's own state.db record for deep audit

`BuildRun` becomes a first-class artifact type in the Seldon graph projection, with provenance edges:

```
Prompt → BuildRun → [GeneratedFile, GeneratedSkill, Test, ...] → Acceptance
```

The evidence chain extends through the build process, not just the runtime. This satisfies the construct-validity standard for transparency that distinguishes real provenance from chain-of-thought theater.

---

## Explicit non-decisions

The following architectural commitments are **unchanged** by adopting DeerFlow:

- Seldon remains CLI-default per AD-022. DeerFlow does not become a Seldon dependency.
- Sleep functions remain the architectural center per AD-023.
- JSONL events remain the source of truth, Neo4j remains the queryable projection per AD-001 and the event-sourced design.
- Per-project graph database isolation per AD-004 holds. DeerFlow build runs targeting different projects emit BuildRuns to those projects' respective graphs, not a shared store.
- The confabulation behavioral contract holds. DeerFlow output goes through the same "verify before asserting" rules as any other source.
- CC task immutability state machine holds. DeerFlow-generated CC tasks follow `proposed → accepted → in_progress → completed` like any other.
- `proposed` = on disk, not claimed; `accepted` = runner claims, lock begins. DeerFlow scaffolding tasks are no exception.
- AD-022 (CLI-default, MCP-exception) holds. DeerFlow build runs invoke Seldon via CLI like any other consumer.

---

## Pilot

Arnold Phase 1 morning brief is the pilot, scoped per the 2026-05-02 chatbot-exit handoff. Specifics in the pilot CC task spec; summary here:

- DeerFlow scaffolds Arnold's agentic coaching team architecture (seven agents: Sparky, Doc, PT, Strength, Conditioning, Endurance, Arnold)
- Sunday morning dry-run exercises only Sparky → Doc → PT → Arnold (Phase 1: mobility/calisthenics, no programming logic)
- Coaches (Strength/Conditioning/Endurance) are scaffolded with role definitions and persona prompts but do not produce content for the pilot brief
- Output: scaffolded agent definitions, retrieval contracts, integration glue for ClaudeClaw, dry-run brief for Sunday, BuildRun event in `seldon-arnold`

Pilot success criteria:
1. BuildRun event emitted to `seldon-arnold` with full provenance
2. Generated skill/agent files pass `seldon verify` and Arnold integration tests
3. Token cost on planner side < $5
4. Claude Max usage stays within one 5-hour rolling window
5. Subjective: dry-run brief output quality is at or above what a focused Claude Code session would produce in equivalent wall-clock time

If pilot succeeds, second migration is Wintermute foraging skills (replacing the retired LeStat scope).

DeerFlow build sessions do not displace SFV final-draft slow-read attention. Build work happens only after a paper-progress checkpoint in any given week.

---

## What kills this AD

The 90-day reversibility review at 2026-08-02 fails (AD reversed) if **any** of the following hold:

1. **TOS enforcement.** Anthropic enforcement action against `claude --print` orchestrated invocation patterns, with no acceptable workaround for the bounded-implementation use case.
2. **Architectural leakage.** DeerFlow's internal architecture proves too leaky to maintain a clean BuildRun boundary — e.g., its memory layer cannot be partitioned per project, or its sandbox model cannot be adapted to write only the BuildRun event without polluting the graph.
3. **Token economics fail.** OpenRouter costs for sustained DeerFlow use exceed reasonable thresholds (rough heuristic: more than $50/month for the build-time work being done), without producing output proportionate to the spend.
4. **Pilot output quality.** The Arnold pilot output requires more cleanup than it would have taken to build the same coaching team in Claude Code directly. This is a falsifiable claim — measure wall-clock and subjective quality, not just feature completeness.
5. **Substitution.** Anthropic ships agent-team capabilities (Claude Code agent teams, Cowork, or successor) that subsume DeerFlow's value at integration cost lower than DeerFlow's maintenance cost. In that case, migration to the Anthropic-native option is correct.

The bet is **DeerFlow + Anthropic ecosystem**. Not DeerFlow as escape from Anthropic. The first three conditions kill the integration; the fourth kills the pilot's premise; the fifth is a graceful exit, not a failure.

---

## References

- DeerFlow 2.0: https://github.com/bytedance/deer-flow
- SitePoint orchestration guide (Claude Code + DeerFlow + Ruflo): https://www.sitepoint.com/the-developers-guide-to-autonomous-coding-agents-orchestrating-claude-code-ruflo-and-deerflow/
- DeerFlow long-running tasks deep dive: https://www.sitepoint.com/deerflow-deep-dive-managing-longrunning-autonomous-tasks/
- OpenClaw enforcement (PYMNTS, ~3 weeks before this AD): context for TOS posture
- Arnold chatbot-exit handoff: `/Users/brock/Documents/GitHub/arnold/handoffs/2026-05-02_chatbot-exit-and-time-budgeting.md`
- AD-005: Standard Interface Contract (update/retrieve) — basis for specialist retrieval profiles
- AD-022: CLI-default, MCP-exception
- AD-023: Sleep functions as architectural center
- AD-024: Observability as substrate
- PL-003: Fractal Agent Team with Specialist Retrieval Profiles (parking lot, now activated by this AD)
