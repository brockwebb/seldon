# Filing from factory: a project needs a premise the dispatcher evaluates for every task, so a spent grant stops new launches

**Kind:** filing
**Filed by:** factory
**Date:** 2026-11-26
**Reporter:** factory FAC-30 Part B item 3 (task `factory/cc_tasks/2026-11-26_FAC-30_the_bank_issues_grants_and_one_standard_cost_manager_enforces_them_in_each_project.md`; design `factory/docs/design/2026-11-26_DN-004_the_bank_issues_grants_and_one_cost_manager_enforces_them_locally.md` decision 4 item 2; decision F-045). That task's ground for this filing: "For seldon's dispatcher, a candidacy or premise mechanism that already exists (a premise `check:` is one); if none fits without changing seldon, file to seldon what is missing."

## What the operator asked for

F-015 as amended (the operator, 2026-11-13): the bank grants a unit operation a budget for a project, and the unit operation "spends inside its grant under its own governor and stops itself when the grant is spent; it does not ask the bank per job." Dispatched Claude Code sessions are the largest unit operation (24.9M of 29.1M tokens counted in the allowance week to 2026-11-28).

## What factory built, and what it found in seldon

- factory now issues weekly grants (`factory/bank/grants/<reset date>.yaml`) and has one cost manager, `factory/scripts/cost_manager.py`, zero tokens. `cost_manager.py status --project P --unit seldon_sessions --stop-only` exits 0 while P's grant has room, and exits 4 when it is spent, naming the grant id. Unreadable records exit 2, failing closed.
- seldon's station (a) already runs a task's own `**Premises:**` `check:` lines before launch, and `| at: launch` keeps one out of registration (AD-038-R27). So a task that carries the line `cost_manager.py premise --project P --unit seldon_sessions` prints is refused `premise_false` while the grant is spent. factory's test runs seldon's own `review_premises` to show it (`factory/tests/test_cost_manager.py`).
- What is missing: the premise reaches only the tasks whose files carry it. Station (a) adds exactly one premise of its own to every task (`environment_in_flight`, `stations.environment_premise`), and a project cannot declare another. The STOP file is no substitute. It makes the pass print "nothing evaluated", which also stops merges of finished work, redrives and the stuck alarm. It is the operator's andon (FC-28), and a spent grant should stop only new launches.

## What is asked of seldon

1. A project-level list of `check:` premises in `seldon.yaml`, e.g. `dispatch.premises: [{statement, check}]`, that station (a) evaluates for every candidate before launch, beside `environment_in_flight`.
2. A false one refuses the launch and names the premise and its check's output. The output carries the grant id.
3. It is a standing condition, not a defect of the task, so it is treated as `environment_in_flight` is:
   - recorded once per episode;
   - with no `premise_false` Issue per task;
   - clearing itself when the check passes. A top-up or a new week makes the check pass again.
4. It never touches a running session, and the merge round and redrives go on.

## What follows in each project once it lands

Each project with a dispatcher adds one line to its own `seldon.yaml`, filed into that project then. The line is `cost_manager.py premise --project <name> --unit seldon_sessions` without the leading `- premise:`. The projects are seldon, squiddy, hazbrief-mcp, ai-readiness-kg, aacps-ai-policy, critical-thinking-ai and factory (factory `scripts/bank.yaml` `grants.seats`). Not filed now: a key seldon does not read enforces nothing. Until then factory's coordinator tick shows a spent grant on the home page and files the operator a top-up item.

## What is not asked

No change to seldon's per-task band (c4) or the session's stop ceiling (Spend × 1.2); both stay. seldon is not asked to read grants or know what a grant is. The check is an opaque command, as every premise is. This is a consumer's report (AD-036-R17), not a design: seldon decides whether and how.
