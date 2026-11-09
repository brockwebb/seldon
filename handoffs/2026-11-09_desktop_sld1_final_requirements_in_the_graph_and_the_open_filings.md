# Handoff: seldon Desktop thread SLD-1, final (2026-11-09)

**From:** SLD-1, closing for good; the 2026-11-03 handoff (`2026-11-03_desktop_sld1_close_sel008_to_sel024_the_factory_runs.md`) stands for everything before 11-03. **To:** the next seldon Desktop thread. Read at `seldon go`.

## The operator's question, answered

He asked on 2026-11-09 why hazbrief's requirements had to be reconstructed from chat threads when the design says systems-engineering documents are generated from the graph. Answer, measured: the design has said so since AD-002, AD-006, AD-012 and AD-013, and `seldon/domain/research.yaml` carries `SRS_Requirement` with a state machine and the edges `implements`, `validates`, `satisfies`, `verified_by`, `derived_from`. Nothing loads requirements into it but `seldon artifact create` by hand, nothing renders them out, `seldon verify` does not count them. seldon's graph has 37 events on the type; hazbrief's has one. The work layer (tasks, issues, scripts, results) was wired; the governance layer (requirements, decisions, tests, traces) was declared and never wired, and `seldon init`/`go`/`verify` never said a project had no decision register (hazbrief: twenty days, 143 tasks, none). ANTS v0.4 had `export_rtm` and it did not carry forward. The hazbrief Desktop thread measured both halves this morning as filings SEL-031 and SEL-032. So: not vibe requirements on the operator's side; a half-built layer on the kit's side, and the monolithic markdown files in hazbrief are the symptom.

## Registered 2026-11-09 by this thread

- **SEL-033** (0a8a6776): requirements and decisions live in the graph; `seldon req import` from a markdown table (hazbrief's 148 VRs first), `seldon docs generate requirements|rtm` as committed projections (retires HB-134R2's four-place ratchet), `verify`/`docs check` count unverified requirements, init/go/verify/project-new report a missing `decisions:` block; design note AD-013 ADDENDUM 01 with the prior-art pass (29148, ReqIF, SysML v2, DOORS, Gotel and Finkelstein, Cleland-Huang); return to hazbrief answers SEL-031 and SEL-032 together. Est. 1.4M, cap 1.7M. Answers the operator's question in code.
- **SEL-034** (e6a20ced): a task that goes terminal stops its running session at the next tool boundary (`task_terminal` on the PreToolUse hook), and a kept worktree's session events reach main's log or are discarded on record; reconciles hazbrief's `worktree-sunny-shimmying-pebble` case. Answers SEL-030.

Both After: none, both Exclusive, both registered by `commit-governed` in one call (AD-038-R20, SEL-023's rule, now live).

## Landed since 11-03 (by the dispatcher, no hand launch)

SEL-023 (filings register as `Kind: filing`, AD-036-R17; `Dispatch: hand`; write+commit+register in one call; the pass pushes), SEL-024 (merge requires the declared pass record; unrunnable is a refusal), SEL-025 (rotated log ignored; untracked filing committed by the pass), SEL-029 (three squiddy filings answered: superseded library release verifies, verdict ledger commits beside its note, an addendum cannot carry Spend; SEL-026 to 028 closed by it; return HB-138 filed).

## Open filings, not yet answered by a task

- 5b76278b, squiddy, 2026-11-06: `seldon verify` KeyError `record_hash` on pending register records. SEL-029's RESULT mentions `record_hash`; check whether it fixed it and file the return, or register the fix.
- The squiddy lease-versus-snapshot filing (2026-11-06) and its ADDENDUM-01: the seldon/squiddy environment lease serialises every squiddy launch behind any seldon session. A design question (snapshot isolation of the served graph versus one lease), not a one-liner. Needs a design note before a task; the prior art is database isolation levels and git's own snapshot model.
- The "twelve docs/evidence subtrees, 34 documents, no harvest disposition" filing (2026-11-06): check SEL-029's RESULT before filing anything; it may be covered.

## Residue, deferred on purpose

SEL-003 (operator's spend decision, then an R file), SPEC-001, the secrets standard, three ai-readiness-kg CLI defects, 1581c3ec blocked. AD-038 base note still fails `prior-art verify` (dbe38fac); SEL-029 Part A may have changed that, check.

## Rules added since 11-03

- A filing is `Kind: filing` and registers header-less; a filing's answer carries its own return (`cc return`). Never give a consumer thread a launch line or a design; take their measurement, file the task, send the ids.
- `commit-governed` on an unregistered `cc_tasks/` file registers it in the same call; the pass commits an untracked filing instead of refusing the queue.
- Check premises against `$HOME/mnt/<repo>` in the device shell, not `/Users/brock/...`, before committing; a grep that fails to open a file passes a `!` check and lies.
