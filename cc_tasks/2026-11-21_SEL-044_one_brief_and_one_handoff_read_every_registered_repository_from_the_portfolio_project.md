# SEL-044: one brief and one handoff read every registered repository from the portfolio project

**Status:** proposed
**Author:** Desktop session (seldon, SLD-2), 2026-11-21, the Saturday batch. Answers factory's filing `6087e4d1` (`cc_tasks/2026-11-13_filing_from_factory_the_operator_has_no_portfolio_entry_point.md`).
**Repo:** seldon (primary). factory and every other repository are read, never written; Part E files factory's return. L4: commit, merge, push in seldon.
**After:** none
**Governing:** AD-002 (domain-agnostic engine; domain configuration is schema); AD-038-R8 (a task may wait on a task in another project's graph, so cross-project reads already exist); AD-030-R9 (`seldon handoff`); factory F-011 and F-016 (the factory is Seldon at portfolio scope and builds no second engine). Number new rulings under AD-038.
**Model:** primary
**Spend:** est. 0.6M tokens. Basis: one read-only aggregation over reads each repository already answers, two command flags, one config block, one return. Zero model calls.
**Network:** none
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes (edits `seldon/commands/go.py`, the handoff command, seldon-mcp's tool list)
**Parts:** A 0.15, B 0.10, C 0.45, D 0.15, E 0.15.
**Premises:**
- premise: the filing is on main | check: test -f cc_tasks/2026-11-13_filing_from_factory_the_operator_has_no_portfolio_entry_point.md
- premise: factory keeps a registry of repositories | check: test -f /Users/brock/GitHub/factory/registry.md

## The condition

The operator starts at the factory and reads one repository at a time. A `seldon go` or a handoff in the factory reads the factory's graph only. The factory's coordinator gathers the rest by hand, one task-list call per repository and a read of each `.seldon/dispatch_last_pass.json`, as on 2026-11-01, 11-02 and 11-13. On 11-13 that hand gathering missed that seldon had built requirements as graph content four days earlier, and the factory designed around a gap that did not exist. On 2026-11-21 the operator found a sixfold growth in one project's gate time himself (seldon's filing to factory `71438cd8`). `factory/registry.md` lists nine repositories in a hand-kept table; twenty-one directories under `/Users/brock/GitHub` hold a seldon.yaml.

## Prior art

- Multi-repository status tools: gita ("Manage multiple git repos with sanity", https://pypi.org/project/gita/) and myrepos keep a registered list of repositories and run one read across all of them into one table. Found by search on 2026-11-21 and not read beyond the titles; the shape taken from them is only that: a declared list, one fan-out read, one table. Cite as found, not read.
- Seldon's own: `seldon_task_wait_on` and the recall arm already read sibling graphs by path through `decisions.repositories`; `seldon dispatch status`, `seldon task list` and `.seldon/dispatch_last_pass.json` already answer per repository everything the filing asks for. Nothing new is measured; it is gathered.

Run `seldon prior-art search` (internal and library arms) before the ruling.

## What to build

**A. Measure first.** For each of the twenty-one repositories: does it register tasks, does it dispatch, when was its last event. Compare against `factory/registry.md` and list every difference (a repository the table omits, a row whose dispatcher column is wrong). The table is the factory's to correct; the differences go in the return.

**B. Ruling** (AD-038 addendum; `prior-art verify` passing before C). A project may declare `portfolio.repositories` in its seldon.yaml (names and paths). In such a project `seldon go --portfolio` and `seldon handoff --portfolio` read every listed repository and write nothing to any of them. A repository that cannot be read is listed with the reason and never dropped. Counts in the portfolio brief equal each repository's own `seldon task list` at the same moment.

**C. The brief and the handoff.** `seldon go --portfolio [--brief]` and the `seldon_go` MCP tool's matching argument: per repository, open tasks by state, the running task and its phase, the last dispatcher pass and its outcome, open alarms (stuck, blocked, `ungated`, `interrupted_thrice`, open huddles), tasks completed since the last portfolio handoff, open filings addressed to it, and, where SEL-041's records exist, the median gate seconds. One screen, one row per repository, then detail only for repositories with something wrong. `seldon handoff --portfolio` writes one handoff in the portfolio project with a section per repository and one resume line. Tests first, on a fixture of three repositories: counts equal each repository's own list; an unreadable repository is shown with its reason; nothing is written outside the portfolio project.

**D. The cost of reading.** Time `go --portfolio --brief` over the real nine. If it takes more than thirty seconds, say what is slow and fix that (a graph read per repository can be one query each, run side by side); do not add a cache.

**E. Return.** `seldon cc return --to factory`: the config block to declare (with the nine from its registry as the worked example), the two commands, A's differences against `registry.md`, and what the brief does not carry (spend and the bank, which are the factory's own).

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.75M.

## Deliverables

A to E with tests; the ruling; A's table; the filing answered; `cc_tasks/2026-11-21_SEL-044_one_brief_and_one_handoff_read_every_registered_repository_from_the_portfolio_project_RESULT.md`.
