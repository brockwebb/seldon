# AD-025 Amendment 01: Narrow Scope to Research-Synthesis Harness

**Status:** Accepted
**Date:** 2026-05-03
**Amends:** AD-025 (DeerFlow as Build-Time Harness, Not Runtime Substrate)
**Original AD reversibility review:** 2026-08-02 (unchanged)
**Evidence base:** `/Users/brock/Documents/GitHub/arnold/cc_tasks/2026-05-02_deerflow-pilot_closeout.md`; 6 BuildRun artifacts in `seldon-arnold` (3 smoke tests + 2 DeerFlow attempts + 1 Claude Code fallback).

---

## What this amendment changes

AD-025 §Decision claimed DeerFlow as the build-time harness for designing and scaffolding new capabilities across the Seldon ecosystem. The Arnold pilot empirically falsified the scaffolding claim. This amendment narrows AD-025's scope.

**Original claim (now superseded):**

> DeerFlow 2.0 is adopted as the build-time harness for designing and scaffolding new capabilities across the Seldon ecosystem.

**Amended claim:**

> DeerFlow 2.0 is retained as a research-and-deliberation harness for multi-source synthesis tasks where a plan-approve-execute interactive loop is the right shape. It is NOT adopted for code scaffolding, file generation, or any task where Claude Code's bounded-implementation pattern fits. Each DeerFlow invocation requires an explicit use-case justification documented as a CC task or research note before the run.

The three-layer model in AD-025 is corrected as follows:

| Layer | Tool | Use case | Lifetime |
|-------|------|----------|----------|
| Research / synthesis / deliberation | DeerFlow on OpenRouter (Kimi K2) | Multi-source exploration, design-space mapping, literature synthesis. Anywhere a human-in-the-loop research conversation is the right shape. | Hours, interactive |
| Build / scaffolding / implementation | Claude Code | Code generation, file scaffolding, refactoring, anything with concrete file outputs. | Bounded sessions |
| Runtime products | Seldon CLI, Arnold MCP servers, etc. | Light, always-on. Provenance via JSONL events. | Persistent |

The change from original AD-025 is the first row's use case. Deliberative research goes to DeerFlow; implementation goes to Claude Code.

---

## Why the original claim was wrong

Two distinct findings from the pilot:

**Finding 1 — Mental model mismatch.** AD-025 assumed DeerFlow exposes a headless build CLI: point at goal file, run autonomously for hours, produce artifacts, exit. DeerFlow's actual shape is a LangGraph-based interactive research-and-deliberation harness. The lead_agent is designed around a plan-approve-execute loop with a human-in-the-loop via message gateway (Telegram/Discord/CLI chat). When invoked headlessly via the wrapper script, lead_agent ran 28 turns and produced zero scaffold files because the planning middleware gates execution on a human-approve signal that never came.

A second attempt with `is_plan_mode=False` and `subagent_enabled=False` ran 33 more turns, also produced zero files. Two configurations across 61 turns / $0.438 / 412s of wallclock confirmed the architectural mismatch is not config-tunable.

**Finding 2 — Article-interpretation error.** Re-reading the SitePoint, dev.to, and AIToolly pieces with fresh eyes, the language consistently described an interactive harness ("SuperAgent harness," "message gateway," "channels," QR-flow auth, WeCom/DingTalk integration). The phrase "long-running autonomous tasks" was ambiguous and we read it as "headless unattended execution." The articles meant "agent maintains state across hours of human-collaborative work."

The misread was reasonable but identifiable in retrospect. The "wanted to believe" component was real — the dopamine of finding a level-4 substrate suppressed the corrective evidence visible in the message-gateway emphasis. Feynman principle applied: easiest person to fool is yourself, and the signal was missed for ~12 hours despite being there in the source material.

---

## What is retained from AD-025

The following structural commitments from AD-025 survive the amendment unchanged:

1. **TOS posture.** DeerFlow planner runs on OpenRouter (Kimi K2 primary, DeepSeek v3.2 fallback). Claude Max is invoked only via `claude --print` headless for bounded implementation tasks. The OpenClaw failure mode is avoided.
2. **Provenance contract: BuildRun events.** This pattern worked perfectly. BuildRun is a first-class artifact type in `seldon-arnold` with full provenance edges. The contract applies to ALL build work — including failures, including Claude Code work, including future research-synthesis runs. Provenance for failure is as valuable as provenance for success.
3. **Per-project graph database isolation** per AD-004.
4. **Confabulation contract** holds for DeerFlow output as for any other source.
5. **CC task immutability** state machine holds for DeerFlow-generated tasks.
6. **AD-022 (CLI-default, MCP-exception)** holds.
7. **The retirement of LeStat as a separate codebase.** This decision was correct independent of the harness debate. LeStat's foraging behavior, when implemented, will be Claude Code skills + ClaudeClaw scheduling, not a hand-rolled harness.

---

## What this amendment unblocks

The pilot also validated a different architecture that was always implicit in Seldon AD-005 and PL-003 but had never been instantiated in working code:

**Finding A from the closeout — the agentic coaching team architecture is real and validated.** Claude Code scaffolded:
- 7 agents in `arnold/agents/<name>/` with role definitions, personas, retrieval contracts, system prompts
- `arnold/scripts/morning_brief.py` orchestrator
- `arnold/config/morning_brief.yaml` for ClaudeClaw scheduling
- `arnold/tests/test_morning_brief_dryrun.py` (16/16 passing)
- Sparky-only data access verified across all 6 non-Sparky agents

This is the level-4 jump. The DeerFlow conversation forced the architecture to become real, but the architecture itself — specialist agents with role-isolated retrieval profiles, structurally enforced confabulation contract via single data-tier agent — is reusable beyond Arnold. The same pattern instantiates Seldon's PL-003 fractal agent team for research workflows when that work surfaces.

---

## Reversibility status

The original AD-025 §"What Kills This AD" listed five conditions. Post-pilot status:

| Condition | Status |
|-----------|--------|
| #1 TOS enforcement | Not triggered. `claude --print` orchestrated invocation worked cleanly. |
| #2 Architectural leakage | Not triggered. Wrapper bridged the CLI gap; BuildRun boundary stayed clean. |
| #3 Token economics fail | Not triggered. Total pilot cost <$5 across all attempts. |
| #4 Pilot output quality | **One strong signal.** Two DeerFlow attempts produced zero files; Claude Code produced 31 working files in less time. |
| #5 Substitution | Not triggered. |

The amendment scope-narrows AD-025 rather than reversing it because the §4 signal applies specifically to scaffolding work, not to all DeerFlow use. The narrowed claim (research-synthesis only) is not yet falsified — it has not yet been tested.

The 90-day formal review at 2026-08-02 remains in effect. If between now and then no DeerFlow research-synthesis pilot succeeds, OR if `~/deer-flow` install + maintenance overhead exceeds value delivered, the AD becomes a candidate for full reversal at that review.

---

## Operational implications

1. **No DeerFlow invocations without a documented use case.** Each future DeerFlow run requires a CC task or research note specifying the goal, why DeerFlow's plan-approve-execute shape fits the goal, and the success criteria. This prevents speculative re-pilots that would burn cost without informing the AD.

2. **Candidate research-synthesis pilots, when ready** (none committed):
   - SFV manuscript synthesis against literature corpus (post slow-read)
   - Wintermute edge-inference design-space exploration
   - Cross-paper synthesis when multiple research threads need integration

3. **Default for design and build work is now Claude Code + optional adversarial review.** Future AD will sketch the Opus 4.7 + GPT-5.5 dual-model review pattern for high-stakes diffs, building on Seldon's existing audit-dispatch infrastructure (κ=0.839 validated). That AD is not yet drafted; it should follow live evidence from the Arnold deployment.

4. **DeerFlow install at `~/deer-flow` is retained.** Cost of keeping is near zero when idle. Cost of reinstalling if needed later is hours. Ratchet stays.

---

## References

- AD-025 original: `/Users/brock/Documents/GitHub/seldon/docs/decisions/AD-025_deerflow_build_harness.md`
- Pilot CC task: `/Users/brock/Documents/GitHub/arnold/cc_tasks/2026-05-02_deerflow-pilot-arnold-coaching-team.md`
- Pilot closeout: `/Users/brock/Documents/GitHub/arnold/cc_tasks/2026-05-02_deerflow-pilot_closeout.md`
- BuildRun artifacts in `seldon-arnold` (Cypher-queryable): 6 total, same goal_hash for the three pilot data points
- Seldon AD-005 (Standard Interface Contract — basis for specialist retrieval profiles)
- Seldon PL-003 (Fractal Agent Team with Specialist Retrieval Profiles — now instantiated in Arnold)
