# AD-038 ADDENDUM 07: the OODA between chained tasks is a knowledge source the dispatcher launches, the chain waits only on a block, and a mechanical registration refusal is retried under a rule

**Date:** 2026-10-28. **Status:** Accepted. Implemented by SEL-014R
(`cc_tasks/2026-10-28_SEL-014R_the_ooda_is_a_knowledge_source_the_dispatcher_launches.md`; statement of record
`cc_tasks/2026-10-28_SEL-014_the_ooda_is_a_knowledge_source_the_dispatcher_launches.md`, refused `premise_false` at
registration). From the squiddy SQ11 work order
(`handoffs/2026-10-28_desktop_sq11_the_factory_runs_without_the_desktop_work_order.md`, items W1, W2 and W4).
**Amends:** AD-038-R10 (c18: what holds a chained task, and what `dispatch.ooda_grace_s` means);
`docs/conventions/desktop_ooda.md` (the Desktop reads only blocks). AD-038-R5 and R13 are unchanged; R18 adds one
retry in front of the refusals they produce. Three new rulings, numbered from the register.
**Code:** `seldon/core/ooda.py` (new: the knowledge source, its brief and verdict, the four records, the registration
retry); `seldon/core/dispatch.py` (`ooda_waits`, `ooda_index`, `ooda_pending`, `load_dispatch_config`);
`seldon/commands/dispatch.py` (the pass fires the knowledge source before candidacy; `dispatch ooda pending|record`);
`seldon/commands/dispatch_worktree.py` (`pass_parallel`, the same); `seldon/commands/cc.py` (`cc register` retries);
`seldon/mcp_server.py` (`seldon_cc_register` retries; `seldon_ooda_pending` lists blocks).
**Tests:** `tests/test_sel014r_ooda_knowledge_source.py`, `tests/test_sel014r_registration_retry.py`,
`tests/test_sel014r_replay_overnight_chain.py`.

## 1. Evidence

1. **The step as designed needs a human surface, and the factory runs without one.** On 2026-10-27/28 four seldon
   tasks (NUM-001R `bacacc4c` → DESK-004R `f7a1d2f0` → DISP-004R `2909ce0f` → RECALL-002R `ff3a4189`) and four squiddy
   tasks (SQ-052R → SQ-086R → SQ-089R → SQ-096) ran unattended and completed. No OODA was performed. seldon's
   `ooda_grace_s` is absent, so c18 was absent from every vector (AD-038-R10: a grace of 0 never waits), and the
   event store holds two `ooda_recorded` lines in all, neither for that chain. Nothing was worse for it, and nothing
   read any of the RESULTs before the next task launched either.
2. **A grace-released chain cannot be told from a checked one.** Under R10 the only signal that nobody read a RESULT
   is `released_by: grace`. With no grace there is not even that.
3. **Three registrations in one morning were refused for mechanical causes a human then fixed by hand** (the work
   order, item 2): a premise `check:` with `&&` or `$(...)` not under `sh -c` (the runner splits a check into argv
   and runs no shell, so `test` reports "unexpected operator" or "bad number"); a number already taken
   (`number_taken`, AD-038-R13, because the Desktop globbed instead of calling `seldon task number`); and a premise
   naming an evidence file that does not exist. Each fix is one line with a rule behind it.

## 2. Rulings

- **AD-038-R16. The OODA between chained tasks is a knowledge source the dispatcher launches, and it ends in exactly
  one of four records.**
  - *When it fires.* With `dispatch.ooda.enabled`, every pass, after the reconcile and before candidacy, finds each
    completed or verified task with an open successor (a `precedes` successor in `proposed` or `accepted`) that has no
    OODA record yet, and runs the OODA on at most `dispatch.ooda.max_per_pass` of them, oldest completion first. The
    knowledge source fires on the board's state, not on a message: a pass that missed the completion, a holder that
    died, or a project that has just enabled it, all find the same due work on the next pass. Disabled, nothing fires
    and nothing waits (R17).
  - *What it reads.* The dispatcher composes the brief, so the session spends its tokens on orienting, not on
    finding files: the predecessor's RESULT path, the successor's task file and every addendum it already has, the
    successor's `check:` premises run now against the primary's HEAD (station (a)'s runner, with each outcome and
    output tail), the Recall hits for the predecessor's task text (RECALL-001's retrieval, the spreading-activation
    step) and the governing notes the successor names. The session is told to run `seldon go --brief` first.
  - *How it runs.* One headless Claude Code session, `claude -p` with `--worktree` (the CLI's hard isolation: no
    write reaches the primary), on the model role `dispatch.ooda.model_role`, in a log under `dispatch.log_dir`. It
    is bounded by `dispatch.ooda_grace_s` seconds of wall clock and `dispatch.ooda.token_cap` tokens (input plus
    cache writes plus output, as `stations.session_tokens` counts them); the holder reaps a session past either.
  - *What it returns.* Its last message carries one line `OODA-VERDICT: {json}`, with `verdict` one of `ok`,
    `amended` or `blocked`. The dispatcher, not the session, writes the record to the primary's ledger:
    `ooda_ok` (the RESULT changes nothing in the successor; the chain proceeds);
    `ooda_amended` (the session wrote the successor's next addendum, `<successor stem>_ADDENDUM_<NN>_<slug>.md` at the
    `NN` the brief names, in its worktree; the dispatcher copies it to the primary and commits it through the hooks,
    path-scoped, **before** the record, so nothing can launch the successor without it; the chain proceeds);
    `ooda_blocked` (a question no ruling answers; the record names the question and the note that would answer it;
    the chain halts, R17);
    `ooda_expired` (the session timed out, crossed its token cap, exited non-zero, never reached the model, or
    returned no verdict, an unreadable one, or an addendum that is missing or misnamed; the reason is in the record;
    the chain proceeds). Every record carries the session's tokens, its log and the successors it read, so a chain
    that was checked is distinguishable from one that ran on the timer.
  - *What an addendum may do.* The convention's limits hold (`docs/conventions/desktop_ooda.md` section 3): an
    addendum amends what the successor does (a moved path, a premise the predecessor made true or false, a number, a
    check that needs `sh -c`); it cannot supply a missing candidacy header (AD-038-R11). The session does not commit,
    merge or push; its worktree is removed after the record, and kept, with the record saying so, only if the session
    committed on its branch.
- **AD-038-R17. The OODA is advisory: c18 holds a chained task only while its predecessor's OODA is due or blocked;
  `ooda_grace_s` is retired as a gate and kept as the OODA session's timeout.**
  W4 is ruled advisory. c18 is present for a task with a completed or verified predecessor whenever
  `dispatch.ooda.enabled` is true, and fails (`ooda_pending`) for a predecessor that has no record yet, which is the
  short wait for the machine's own session in this pass or the next (bounded by `max_per_pass` and the session's
  timeout, never by a person), and (`ooda_blocked`) for a predecessor whose latest record is `ooda_blocked`. Every
  other record releases: `ooda_ok`, `ooda_amended`, `ooda_expired`, a Desktop's `ooda_recorded` event and a committed
  `<stem>_OODA.md` file. A block is answered by a later `ooda_recorded` event (`seldon dispatch ooda record <N>`,
  MCP `seldon_ooda_record`) after the Desktop has amended, blocked or superseded the successor, as the convention's
  section 3 orders. `seldon dispatch ooda pending` and `seldon_ooda_pending` list only blocks, each with its question
  and the note that would answer it: the only OODA a person reads. With `enabled` false c18 is absent and nothing
  waits, whatever `ooda_grace_s` says; R10's grace, which released a chain on a timer with nobody reading, no longer
  releases or holds anything. `dispatch.ooda_grace_s` is the OODA session's wall-clock timeout, required above 0 when
  `enabled` is true. `dispatch_launched` records c18's per-predecessor `released_by` as the record's kind.
- **AD-038-R18. A registration refused for a mechanical cause is retried once under a named rule, and the retry is
  logged on the task.** `seldon cc register` and `seldon_cc_register` read a refusal, and for each mechanical cause
  apply its rule to the task file, then register once more:
  - `number_taken` (AD-038-R13): the file is renamed to the number `seldon task number <PREFIX>` allocates (keeping
    the slug, and dropping an `R<n>` re-filing mark, since a new number is a new identity), and the number in its
    title line is replaced; a tracked file is moved with `git mv`.
  - `premise_false` on a `check:` whose command uses shell syntax (`&&`, `||`, `;`, `|`, `$(`, a backtick, a
    redirect or a `$` expansion) and is not already `sh -c`: the command is wrapped as `sh -c '<command>'`, which is
    what its author meant (the runner execs argv, AD-038-R5).
  - `premise_false` on a `check:` of the form `test -e|-f|-d|-s <path>` or `ls <path>` whose path is absent and lies
    in a sibling repository the task file names outside its premises (a git checkout other than this project's, named
    in a header or the body): the premise is marked `[stale_evidence: <path> absent at registration <date>]` and its
    check narrowed to the nearest ancestor directory of the path that exists in that repository. A path in this
    project's own repository is never narrowed: a premise false here is AD-038-R5's case and reaches its author.
  A refusal with no mechanical cause, or with one whose rule does not apply to the line, is reported as today. A
  refusal after the retry is reported as today, with the retry named. Each retry is one `registration_retried`
  record: the rules applied, every line changed (before and after), the first refusal, the outcome and, when it
  registered, the task's id. The repair is a rule table; it makes no model call, because each cause has one known
  repair (R16's session is for what has none).

## 3. Negative control

- `test_disabled_knowledge_source_fires_nothing_and_c18_is_absent`: with `ooda.enabled` false, no session is launched,
  c18 is absent from every vector and `ooda_grace_s` holds nothing.
- `test_a_blocked_record_holds_and_a_later_desktop_record_releases`: only `ooda_blocked` holds once a record exists.
- `test_an_expired_session_proceeds_and_says_why`: a timeout is a record (`ooda_expired`), not a hold.
- `test_an_amended_verdict_without_its_addendum_is_expired`: the dispatcher does not trust a verdict it cannot check.
- `test_a_refusal_with_no_mechanical_cause_is_not_retried`: a premise that is simply false is refused once, as today.
- `test_a_second_refusal_reaches_the_operator`: one retry, never two.
- `test_a_missing_path_in_this_projects_own_repository_is_not_narrowed`, and R5's own
  `tests/test_friction001_registration_premises.py::test_a_false_premise_refuses_registration_with_its_output`, which
  the first form of R18 (that narrowed the project's own paths too) failed in SEL-014R's full suite.
- `tests/test_dispatch_serial_transcript.py` is unchanged: its project does not enable the knowledge source.

## 4. What this does not change

- `precedes` (AD-029) and c2: c18 adds a wait after c2 is satisfied, never before.
- Cross-project waits (c17, AD-038-R8): a task waiting on another graph's task is not held by c18, and the knowledge
  source fires only on this project's chains, writing only this project's ledger.
- AD-038-R11: an addendum still cannot supply a candidacy header; the OODA session is told so.
- The Desktop convention's section 3 order (addendum first, record last) holds for a Desktop answering a block.
- R5 and R13 refuse exactly what they refused; R18 retries in front of them and never widens what registers.

## 5. Prior art

### External

The blackboard architecture is the shape adopted. In Hearsay-II (Erman, Hayes-Roth, Lesser and Reddy 1980, ACM
Computing Surveys 12(2)) independent knowledge sources watch a shared board, fire when its state matches their
condition, and write their partial results back; Hayes-Roth, "A blackboard architecture for control" (Artificial
Intelligence 26, 1985) makes the choice of the next knowledge source a control component of its own. None of them
holds a conversation. *Adopted:* the graph plus the task files and the ledger are the board; the OODA is a knowledge
source whose condition is "a completed task with an open successor and no record"; the dispatcher is the control
component, and it alone writes the record. *Departed from:* a Hearsay-II knowledge source writes the board directly;
here the session writes nothing to the primary and the control component validates its verdict before recording it,
because a session's claim is not a fact until checked (AD-037). Linda's tuple spaces (Gelernter 1985, ACM TOPLAS
7(1)) are the coordination form: the knowledge source and the dispatcher never address each other; they read and
write the ledger. Spreading activation (Collins and Loftus 1975, Psychological Review 82(6)) names "the nearest
nodes for context"; RECALL-001's retrieval is the thin instance the brief reuses. Program-repair agents (Self-debug,
Reflexion, RepairAgent) use a model to find a fix that is not known in advance. *Departed from, for R18:* each
mechanical refusal has one known fix, so a rule table repairs it and no model is called. DeerFlow 2.0 (ByteDance, 2026)
is a point of comparison, not a template: a lead agent decomposes one goal into sub-agents in isolated contexts and
joins them; there is one goal per run and no governance between runs, which is the gap this knowledge source fills.

- library receipt: query "blackboard multi-agent shared memory" | release library_graph_20261017_sq018_02_2026-10-17.json sha256:99984ba3da90146a73ab4e9d8ddf15687551cb2cc2659be90d16e525253ecfb5 | rows lesson:2026-02-27_arXiv_2510_26493#p15:216:44-1993, lesson:2026-02-27_arXiv_2510_26493#p9:157:1545-1855
- library receipt: query "spreading activation memory retrieval" | release library_graph_20261017_sq018_02_2026-10-17.json sha256:99984ba3da90146a73ab4e9d8ddf15687551cb2cc2659be90d16e525253ecfb5 | rows lesson:2026-03-17_arXiv_2601_04748#p16:354:3713-3840
- library receipt: query "agent self-correction retry repair" | release library_graph_20261017_sq018_02_2026-10-17.json sha256:99984ba3da90146a73ab4e9d8ddf15687551cb2cc2659be90d16e525253ecfb5 | rows lesson:2026-02-22_arXiv_2411_04329#p2:25:417-525, lesson:2026-02-22_arXiv_2503_01935#p9:244:2921-3080
The library holds no copy of Hearsay-II, Hayes-Roth 1985, Gelernter 1985 or Collins and Loftus 1975; its rows above
are the later literature that builds on them (arXiv 2510.26493 on agents' indirect communication through a shared
memory, the blackboard's LLM form; arXiv 2601.04748 citing Anderson's spreading-activation theory; arXiv 2411.04329
and 2503.01935 on model-driven repair). The four originals are cited by bibliographic reference
(10.1145/356810.356816, 10.1016/0004-3702(85)90063-3, 10.1145/2363.2433, 10.1037/0033-295X.82.6.407), not as web
receipts: the task ran with no network, so no page was retrieved.

### Internal

- AD-032 section 6 already adopts the blackboard for the cross-project message board (Erman et al. 1980; Nii 1986):
  "the board informs; it never dispatches". *Departed from, deliberately:* the OODA knowledge source is dispatched by
  the control component, because its output gates a launch; the board's entries do not.
- The SQ11 work order names the gap and its prior art, from squiddy's log; these receipts re-run it in seldon's.
- AD-038-R10 (ADDENDUM 03) is what R17 amends: its grace released chains on a timer, and seldon left it at 0.
- AD-038-R5 (premises at registration) and R13 (`seldon task number`) produce the refusals R18 retries.

- internal receipt: query "blackboard knowledge source" | repo seldon@34975aef39098ecab2752efa7822470562477668 | hits docs/design/AD-032_factory_control_design.md:225, handoffs/2026-10-28_desktop_sq11_the_factory_runs_without_the_desktop_work_order.md:14
- internal receipt: query "blackboard knowledge source" | repo workbench-audit@tree:c03bc86f0e4d7087c6f9cc417ee42ef66f7bc07268d5316448b4344c744b5412 | hits design/2026-10-03_factory_control_design_DRAFT.md:224#sha256=6e77a0631484
- internal receipt: query "ooda chain proceeded on grace" | repo seldon@34975aef39098ecab2752efa7822470562477668 | hits handoffs/2026-10-28_desktop_sq11_the_factory_runs_without_the_desktop_work_order.md:7
- internal receipt: query "ooda chain proceeded on grace" | repo squiddy@ff64a7a4897fb4c240269fde0b4c8302d164a1c6 | hits none
- internal receipt: query "number_taken retry" | repo seldon@34975aef39098ecab2752efa7822470562477668 | hits handoffs/2026-10-28_desktop_sq11_the_factory_runs_without_the_desktop_work_order.md:32, docs/decisions/REGISTER.md:9
- internal receipt: query "sh -c premise check unexpected operator" | repo squiddy@ff64a7a4897fb4c240269fde0b4c8302d164a1c6 | hits handoffs/2026-10-28_sq11_dn052_r234_r237_four_tasks_chained_sq088_superseded_dn050_r_tasks_next.md:15
