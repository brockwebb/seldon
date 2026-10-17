# MCP-001: every seldon MCP tool runs the checkout's current code in a fresh process; the server never goes stale and never needs a restart

**Repo:** seldon. L4: commit and push. Work on your worktree branch; the dispatcher merges on green (AD-034 ADDENDUM 01). Do not touch the primary checkout.
**Date:** 2026-10-17. **Authored by:** a Desktop session in squiddy (SQ8).
**Governing:** AD-038-R3 (mutating MCP tools run HEAD in a subprocess). This task extends R3 to every tool, read tools included, so the `server_stale` refusal and the Desktop restart it demands disappear. Write the extension as AD-038 ADDENDUM 01 with the evidence below; no new ruling beyond "every tool," no new control (AD-038-R6).
**After:** none
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Model:** primary
**Spend:** est. 0.15M tokens. Basis: R3's subprocess path exists; this routes the remaining tools through it and removes the staleness guard's refusal branch.
**Parts:** A 0.7, B 0.3.
**Network:** none beyond git push.
**Exclusive:** yes
**Premises:**
- premise: R3's subprocess runner exists | check: `test -f seldon/commands/mcp_call.py`
- premise: the staleness guard still refuses reads | check: `grep -q "server_stale" seldon/core/loaded_state.py`

Glob and read every sibling `*MCP-001*ADDENDUM*.md`.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.25M.

## Evidence

Four Desktop restarts on 2026-10-17 alone, each because main moved under a running `seldon-mcp` process (FRICTION-001, DESK-003, FRICTION-002 merges, plus one during DESK-002R). The guard (`loaded_state.stale`) is correct to refuse rather than answer from old code; the cost is that every merge turns the operator into a restart step. A long-lived process over a repository that changes several times a day is the wrong shape; the known pattern is a thin server whose every call execs the current code (R3 already chose this for writes).

## Part A

1. Route every tool in `seldon/mcp_server.py` through `mcp_call` (fresh process, current checkout), reads included. The server process keeps only transport and argument marshalling; it imports nothing from `seldon.core` at tool-call time.
2. The staleness guard becomes a one-line note in the tool result (`code: <sha>`) instead of a refusal. Remove the refusal branch; keep the sha so a transcript shows which code answered.
3. Measure the latency cost on the three most-called read tools (`seldon_query`, `seldon_task_list`, `seldon_decision_show`) before and after, 10 calls each, and record it in `docs/evidence/mcp001/latency.jsonl`. If the median exceeds 2 s on any of them, say so in the RESULT; do not optimize here.
4. Tests, each failing on HEAD: a read tool answers from a checkout whose HEAD moved after the server started; no tool result ever carries `server_stale`.

Acceptance:
- `check: ! grep -rn "server_stale" seldon/ --include=*.py | grep -v tests/`
- `check: pytest tests/test_mcp001_fresh_process.py -q`

## Part B

1. AD-038 ADDENDUM 01: R3 extended to every tool, with the four-restart evidence and the latency table.
2. Remove the restart instruction from CLAUDE.md and from any handoff template that tells the operator to restart Desktop after a merge.

Acceptance:
- `check: test -f docs/design/AD-038_ADDENDUM_01_every_tool_runs_fresh.md`
- `check: ! grep -qi "restart desktop\|restart claude desktop" CLAUDE.md`

## Report

RESULT under 15 lines: tools routed, latency medians before and after, tests, tokens against 0.15M.
