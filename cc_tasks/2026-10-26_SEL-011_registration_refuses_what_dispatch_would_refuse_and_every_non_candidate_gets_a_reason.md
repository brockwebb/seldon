# SEL-011: registration refuses what dispatch would refuse, and every non-candidate gets a reason line

**Status:** proposed
**Author:** Desktop session (seldon), 2026-10-26, from findings reported by the squiddy (SQ10) and hazbrief Desktop sessions.
**Repo:** seldon (primary). L4: commit, merge, push in seldon. squiddy and hazbrief are read by path for the evidence below, never written.
**Governing:** AD-038 (the criteria vector; R5, registration runs the task's premises, is the precedent this extends); AD-037-R6 (the stations, whose Parts check already runs at registration); DN-006 decision 2 (the candidacy headers). Number any new ruling under AD-038 and say so in the RESULT.
**Model:** primary
**Spend:** est. 0.4M tokens. Basis: factor the candidacy checks into one function both paths call, one reason line per non-candidate in the pass output, fixture tests. Zero model calls.
**Network:** none beyond git push.
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes (edits seldon/core/dispatch.py and seldon/commands/dispatch.py)
**Parts:** A 0.55, B 0.30, C 0.15.
**Premises:**
- premise: the dispatcher's three candidacy headers are a constant in core | check: grep -q "REQUIRED_HEADERS = (HEADER_SPEND, HEADER_NETWORK, HEADER_LAYER)" seldon/core/dispatch.py
- premise: the Parts check already runs at registration, in the stations module | check: grep -q parts_undeclared seldon/core/stations.py
- premise: a pass prints a one-line summary when nothing is eligible | check: grep -q "nothing eligible" seldon/commands/dispatch.py

Checks are single commands with no shell.

## The condition

A task file can pass `seldon cc register` and then never run, with no signal to its author. Measured this week:

- SEL-010 (hazbrief filing, 2026-10-25): committed with no Parts, a non-numeric Spend and no framework-layer header. Registration refused on Parts only; the other two would have refused it at dispatch.
- SEL-010R (2026-10-26): registered clean, then refused at every pass on c10 `concurrency_undeclared` (`Exclusive: no` with no `Touches`). Withdrawn; re-filed as SEL-010R2.
- squiddy SQ-088 and SQ-091: sat two days as `proposed` with the pass reporting "0 candidates" and no reason, because the filings carried none of Spend / Network / Framework layer served.
- Issue 9965fbed (seldon, pre-October): a not-candidate task gets no reason line. Still open, and undispatchable itself.

The criteria are applied at two points by two code paths. The cost of the gap is a lost day per filing and a person reading logs to find out why.

## What to build

**A. One candidacy function, run at registration.** Factor the dispatcher's static candidacy checks (the required headers, Spend as `zero` or a token count, the Network grammar, Exclusive/Touches (c10), Parts, the Model lock, a parseable After header) into one function that `dispatch.evaluate` and `seldon cc register` both call. Registration refuses on any failure with the dispatcher's own reason code and grammar text, so the author sees it in the same turn. Checks that depend on live state (dirty tree, leases, waits, worktree availability) stay dispatch-only. A test registers a fixture file that fails each static check and asserts the refusal names it.

**B. A reason line for every non-candidate.** Every pass prints one line per open task that is not a candidate: id, reason code, source file. A pass that today prints "nothing eligible (N open, 0 candidates)" lists N lines. Same in `seldon dispatch status`. Resolves 9965fbed; mark it resolved in the RESULT's closing commit.

**C. The record.** State in the RESULT that a committed task file's headers can only be repaired by a new file (the registrar and the dispatcher read the base file only), and correct TRIAGE-001's advice that SEL-003 "needs those headers added in an addendum". Also record, for SPEC-001, that a `check:` line runs without a shell, so a pipe, `&&` or `!` needs `sh -c "..."` (five squiddy checks failed that way the weekend of 2026-10-24).

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.5M.

## Deliverables

Parts A and B with tests; issue 9965fbed resolved; `cc_tasks/2026-10-26_SEL-011_registration_refuses_what_dispatch_would_refuse_and_every_non_candidate_gets_a_reason_RESULT.md`.
