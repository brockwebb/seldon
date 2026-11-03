# SEL-023: a consumer filing is a kind the registrar accepts, a hand-dispatched task is refused by the dispatcher, a filing is written and registered in one call, and a Desktop commit reaches origin on the next pass

**Status:** proposed
**Author:** Desktop session (seldon), 2026-11-03, answering the squiddy consumer filing of 2026-11-03 (`cc_tasks/2026-11-03_consumer_filing_from_squiddy_a_consumer_filing_cannot_be_registered_and_consumer_threads_have_no_rule_against_designing_fixes.md`, observations 1 to 6) and the SQ11 work-order addendum of 2026-10-30 (`handoffs/2026-10-30_desktop_sq11_work_order_addendum_01_merge_gate_hand_dispatch_register_race.md`, W7 and W8).
**Repo:** seldon (primary); squiddy (Part E's return task is written and registered there under AD-036-R12 and R16). L4: commit, merge, push in both.
**After:** none
**Governing:** AD-036-R12 and R16 (the filing and the return); AD-038-R11 and R12 (candidacy headers, registration runs the static checks); AD-034 decision 2 (the pass pushes what the branch is ahead by); SEL-004 decision 3 (a hand-dispatched task fast-forwards main). Number new rulings under AD-036 (filings, the consumer rule) and AD-038 (the dispatch header, the push).
**Model:** primary
**Spend:** est. 0.6M tokens. Basis: two headers in the registrar and dispatcher, one combined write-register command, one push on every pass, one paragraph in the system CLAUDE.md, one return task, fixtures. Zero model calls.
**Network:** none beyond git push.
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes (edits `seldon/commands/cc.py`, `seldon/core/dispatch.py`, the pass, the system CLAUDE.md)
**Parts:** A 0.25, B 0.15, C 0.20, D 0.15, E 0.25.
**Premises:**
- premise: the pass pushes through push_if_ahead | check: grep -q "def push_if_ahead" seldon/core/dispatch.py
- premise: registration is register_task_file | check: grep -q "def register_task_file" seldon/commands/cc.py
- premise: the system CLAUDE.md carries no consumer-thread rule | check: sh -c "! grep -qi 'consumer thread' CLAUDE.md"
- premise: the squiddy filing is in seldon's tree, unregistered | check: test -f cc_tasks/2026-11-03_consumer_filing_from_squiddy_a_consumer_filing_cannot_be_registered_and_consumer_threads_have_no_rule_against_designing_fixes.md
- premise: no dispatch-mode header exists | check: sh -c "! grep -q HEADER_DISPATCH seldon/core/dispatch.py"

Checks are single commands with no shell.

Read the squiddy filing and its ADDENDUM-01 in full before Part A; they are the measurement.

## The condition

1. AD-036-R12 says a consumer filing registers in the producer's graph; AD-038-R11 refuses a file without candidacy headers. A filing that follows R12 cannot register (ai-readiness-kg AR-7 into squiddy, 2026-11-03), and two header-less filings registered before R11 (squiddy 6ffde0f7, 18001e38) show as `no_source_file` or `no_header` on every pass.
2. Between a Desktop's write and its register, the untracked file fails c7 for the producer's whole queue (twice in squiddy on 2026-10-30, once on 2026-11-03). SQ-050R's `spec_modified` is the same race reversed.
3. squiddy SQ-050RM was registered as hand-dispatched and launched by the dispatcher before its `blocked` state landed; the session noticed, the protection was luck.
4. The operator's rule for consumer threads (2026-11-03, verbatim in the filing's observation 4): consumers report what they experienced and never design or implement the producer's fix. Nothing `seldon go` embeds says so.
5. A Desktop commit through `seldon_commit_governed` is pushed only when a merge happens to run; in an idle repository it never leaves the machine (observation 6). The operator pushes nothing by hand.

## What to build

**A. `**Kind:** filing`.** A task file with this header registers without candidacy headers as a `ConsumerFiling` kind of ResearchTask: never a candidate, listed by `dispatch status` and the pass as `filing` (its own reason line, not `no_source_file`), closed by the return task that answers it (`cc return`, SEL-013R) or by `task withdraw`. `**Kind:** task` is the default. Any other header set on a filing is ignored, not refused. Fixture: a header-less filing with `Kind: filing` registers; without the line it is refused as today.

**B. `**Dispatch:** hand`.** Registration records it; the dispatcher refuses the task on a new criterion (`dispatch_hand`) and the reason line says who launches it. Fixture: a hand task is never a candidate.

**C. One call writes, commits and registers.** `seldon cc file --project <repo> --content-file <path>` (and the MCP tool) writes the task file into that repository's `cc_tasks/`, commits it through the hooks and registers it, in one step under the project's flock, so no pass can see an untracked task file. `seldon_commit_governed` on a `cc_tasks/` path that is not yet registered registers it in the same call. Fixture: a pass between write and register cannot observe dirt.

**D. The pass pushes.** Every pass that ends with the branch ahead of its upstream and a clean tree pushes (`push_if_ahead` after the sweep, not only at a merged finish); a Desktop commit therefore reaches origin within one poll interval in any repository with a dispatcher. Record `push:` on the pass line as today.

**E. The consumer rule and the return.** Add to the system CLAUDE.md that `seldon go` embeds, under the Desktop section: a thread working in a consumer repository reports what it experienced to the producer by filing (Part A) and does not design, draft or implement the producer's fix; a draft fix in a consumer Issue or filing is refused at registration when the filing names a producer. Then write the return to squiddy per AD-036-R16 with `seldon cc return`, answering the filing's (a), (b), (c) and observation 6 with what landed and what squiddy does: retag 6ffde0f7 and 18001e38 as filings (one `task update` each), and nothing else.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.8M.

## Deliverables

A to E with tests; rulings under AD-036 and AD-038; the squiddy return registered; `cc_tasks/2026-11-03_SEL-023_a_consumer_filing_is_a_kind_the_registrar_accepts_and_a_desktop_commit_reaches_origin_RESULT.md`.
