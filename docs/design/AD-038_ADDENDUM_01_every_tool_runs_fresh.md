# AD-038 ADDENDUM 01: every seldon-mcp tool runs the checkout's current code in a fresh process; the stale guard is gone

**Date:** 2026-10-20
**Status:** Accepted. Implemented by MCP-001 (`cc_tasks/2026-10-17_MCP-001_every_mcp_tool_runs_the_checkout_in_a_fresh_process.md`).
**Amends:** AD-038-R3 in place: "read-only tools may stay in process" and "`loaded_state.stale` then guards only the read-only tools" are withdrawn. No new ruling label and no new control (AD-038-R6): R3's own mechanism is extended to the six tools it left out, and one control (the stale guard) is removed.
**Retires:** SEL-006 Part B's refusal for seldon-mcp (`seldon/core/loaded_state.py`, deleted; `tests/test_mcp_server_stale.py`, deleted). squiddy's copy in `squiddy/serve.py` is not touched; it is squiddy's.
**Code:** `seldon/mcp_server.py` (`_tool`, `_runs_head`, `_run_in_head`), `seldon/commands/mcp_call.py` (`code_line`).
**Tests:** `tests/test_mcp001_fresh_process.py` (six tests, each failing on the code before MCP-001), `tests/test_friction001_mcp_head.py` (rewritten).
**Evidence:** `docs/evidence/mcp001/latency.jsonl` (harness `scripts/mcp001/latency.py`).

## 1. Evidence

Four Claude Desktop restarts on 2026-10-17 alone, each because main moved under a running `seldon-mcp` (the FRICTION-001, DESK-003 and FRICTION-002 merges, and one during DESK-002R). After R3 the mutating tools ran HEAD, but the six read-only tools (`seldon_go`, `seldon_task_list`, `seldon_query`, `seldon_decision_show`, `seldon_decision_list`, `seldon_decision_check`) still answered `server_stale` after every merge under `seldon/`. Orientation (`seldon_go`) and listing are the first calls of every Desktop thread, so a refusing read is a restart in practice even when its message asks for none. The guard was right to refuse rather than answer from old code; the shape that made refusal necessary was wrong: a process kept for days over a repository that changes several times a day.

## 2. The rule as amended

**The amendment.** R3 of AD-038 now reads "the MCP server runs HEAD, every tool": every seldon-mcp tool, read or write, runs as `<python> -P -m seldon mcp-call <tool>` in a fresh process on the checkout's current code, with its keyword arguments on stdin and its answer relayed. The server process keeps only transport and argument marshalling; it imports nothing from `seldon.core` to answer a call (`test_the_server_process_imports_nothing_from_seldon_core_to_answer_a_call`). There is no in-process path and so nothing to go stale and no staleness check. What SEL-006 recorded at load becomes a note: every string answer ends with `code: <sha>` (the HEAD short sha of the checkout the child imported, and `+ uncommitted changes under seldon/` when there are any), so a transcript shows which code answered. `_tool()` has no `read_only` parameter any more.

**What stays.** `mcp.stale_log` and `seldon qc chart`'s restart count are kept so the restarts inferred before this change stay on the toil chart (AD-038-R6); nothing appends to the log now, so the count is zero from here by construction. A server started before this merge keeps its old in-process read path until its next start; that start is the last one a merge forces.

## 3. The cost, measured

Ten calls each through the registered tool, against `seldon-seldon-self`, before (code `424969c`, in process behind the guard) and after (the fresh child):

| tool | median before | median after |
|---|---|---|
| `seldon_query` | 0.084 s | 2.349 s |
| `seldon_task_list` | 0.095 s | 2.324 s |
| `seldon_decision_show` | 0.982 s | 3.166 s |

Every median after exceeds the task's 2 s line. The added cost is a near-constant 2.2 s, the child's interpreter start and `seldon` import (the cost the mutating tools have paid since R3). It is reported, not optimized, as MCP-001 orders. Against it: a restart, which costs the operator's attention and the Desktop thread's context, four times on 2026-10-17.

## 4. Prior art

- **CGI** (RFC 3875, *The Common Gateway Interface Version 1.1*, 2004): the server forks a fresh process per request, which runs whatever program is on disk now. R3 as amended is this model; the long-lived MCP process is the web server, `seldon mcp-call` the script.
- **FastCGI and the cost of process start** (Open Market, FastCGI specification, 1996): process-per-request was replaced by persistent workers because start-up cost dominated short requests, at the price of workers that must be recycled when code changes (gunicorn's `--reload`, `max_requests`). This addendum knowingly takes the CGI side of that trade: here a request is a human-paced Desktop call and the code changes several times a day, so freshness is worth 2 s; a persistent worker pool with reload-on-tree-change is the recorded alternative if the latency ever matters.
- **`importlib.reload` caveats** (Python docs): names bound by `from ... import` and existing instances keep old objects. Why in-place reload was rejected in R3 and stays rejected.
- **squiddy DN-046 R-202** ("a process records what it loaded and re-checks it"): the rule SEL-006 implemented. It still holds in the limit: a process that loads per call re-checks per call by construction. The `code:` line is its record.
