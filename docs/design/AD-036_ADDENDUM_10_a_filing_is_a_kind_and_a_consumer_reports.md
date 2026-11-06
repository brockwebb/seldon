# AD-036 ADDENDUM 10: a consumer filing is a kind the registrar accepts, a consumer reports and does not fix, and a return can answer a filing in the producer's own graph

**Date:** 2026-11-06. **Status:** Accepted. Implemented by SEL-023
(`cc_tasks/2026-11-03_SEL-023_a_consumer_filing_is_a_kind_the_registrar_accepts_and_a_desktop_commit_reaches_origin.md`),
answering squiddy's filing of 2026-11-03
(`cc_tasks/2026-11-03_consumer_filing_from_squiddy_a_consumer_filing_cannot_be_registered_and_consumer_threads_have_no_rule_against_designing_fixes.md`,
observations 1 to 5). **Amends:** AD-036-R12 (what a filing is when it registers); AD-036-R16 (what an `Answers:`
header may name). AD-038-R11 and R12 are unchanged for every file that is not a filing. Two new rulings.
**Code:** `seldon/core/dispatch.py` (`HEADER_KIND`, `parse_kind`, the filing branch of `static_checks` and
`evaluate`); `seldon/core/filing.py` (new: `designs_fix_refusal`, `registration_properties`); `seldon/commands/cc.py`
(`register_task_file`: a filing skips the gates a task to be executed owes; `cc return --answers`);
`seldon/core/returns.py` (`resolve_answers` for a filing in this graph, `close_filing`); `seldon/commands/task.py`
(`task update --kind`); `seldon/commands/go.py` (the Desktop section's consumer rule); `seldon/domain/research.yaml`
(`task_kind`, `filed_by`). **Tests:** `tests/test_sel023_filing_kind_hand_dispatch_file_and_push.py`.

## 1. Evidence

1. **A filing that follows R12 cannot register under AD-038-R11.** ai-readiness-kg AR-7 filed into squiddy on
   2026-11-03, headed "No headers, not a dispatcher candidate", and `seldon_cc_register` refused it
   `no_header:Spend,Network,Framework layer served` and `parts_undeclared`. Both rulings were in force, so under both a
   consumer filing was unregisterable (the filing, observation 1).
2. **Two header-less filings registered before R11 have had no route since.** squiddy `6ffde0f7` and `18001e38`
   show as `no_source_file` or `no_header` on every pass (observation 2). The same state was in seldon's own pass log
   on 2026-11-03: five tasks `not_a_candidate: no_source_file`, one `no_header:Spend,Framework layer served`
   (`logs/dispatch/seldon_dispatch.rotated_20261104T021957Z.log`, the 13:11:50Z pass).
3. **A consumer thread drafted the producer's fix, and nothing it read said it may not.** AR-7's Issue `2b5a296d`
   carried candidate fixes for a kit-side defect before the operator stopped it. The operator, 2026-11-03, verbatim:
   "We are consumers of the tools. We can file bug reports or issue reports with Squiddy. And then the Squiddy thread
   can work on that from a holistic Squiddy solution." (observation 4).
4. **R16's return addresses a filing in the consumer's graph only.** squiddy's filing is registered nowhere but the
   producer it was filed into, so the task answering it (SEL-023, whose file names its filing in prose and carries no
   `Answers:` header) had no return path under R16 as written.

## 2. Prior art

- **Bug-tracker separation of report and fix.** A bug report states observed behaviour, expected behaviour and
  reproduction; the fix belongs to the maintainers' change process (the Mozilla bug-writing guidelines and the
  Debian reportbug convention separate "what happened" from patches, which arrive through review). Adopted: a filing
  carries observation, evidence and the question back; a fix in it is refused. Departure: the refusal reads the
  filing's structure (headings, line-leading labels), not its prose, because the operator's rule is about what the
  consumer designs, not what it may mention.
- **Request-Reply with a Return Address** (Hohpe and Woolf, *Enterprise Integration Patterns*, 2003), as R16 already
  applies it. R18 widens where the request may be registered: in the replier's own queue, with the return address
  carried on the request (`**Filed by:**`) rather than implied by the repository the request lives in.
- **Internal:** AD-038-R11 and R12 (the candidacy headers, registration runs the dispatcher's static checks);
  TRIAGE-001's `FUTURE` prefix, the precedent for a registered task the dispatcher never evaluates.

The external sources are cited by their published names and were not fetched: the task's Network header allows
nothing beyond git. The internal search was this repository's record (the recall hits SEL-013R, SEL-011, AD-036-R12
and R16, DESK-001) and the filing's own evidence.

## 3. Rulings

- **AD-036-R17. A task file headed `**Kind:** filing` is a consumer filing: it registers without candidacy headers,
  is never a dispatcher candidate, and closes with its return; a consumer reports and does not fix.** Registration
  records `task_kind: filing` (and `filed_by` from `**Filed by:** <repo>`), applies none of the gates a task to be
  executed owes (the candidacy headers, a design-note reference, acceptance criteria, premises, a governing note's
  verdict, recall, constraining rulings), and ignores any other header the filing sets. It refuses a filing whose
  headings or line-leading bold labels carry a fix for the producer (`filing_designs_fix`; the patterns are
  `filings.fix_headings` in seldon.yaml). The dispatcher and `seldon dispatch status` list a filing under its own
  reason, `filing`, read from the graph before the file, so a filing registered before this ruling is retagged by
  `seldon task update --kind filing`. A filing closes when the task answering it files its return (R18) or by
  `seldon task withdraw`. `**Kind:** task` is the default. What `seldon go` sends a Desktop says: a thread working in
  a consumer repository reports what it experienced to the producer by filing, and does not design, draft or
  implement the producer's fix.
- **AD-036-R18. An `**Answers:**` header may name a filing registered in the answering repository's own graph; the
  return then goes to the filing's `**Filed by:**` repository and closes the filing.** `<repo>` in
  `**Answers:** <repo>:<ref>` naming this repository resolves the ref here, and refuses (`answers_unresolved`) a ref
  that is not a filing or a filing with no consumer (`**Filed by:**`, or `seldon cc return --to`). The return is
  numbered by the consumer's allocator under the prefix most of the consumer's numbered tasks carry, unless
  `--prefix` names one. Once the return is registered and committed in the consumer, the filing is walked to
  `completed`. `seldon cc return --answers <repo>:<ref>` supplies the value for an answering task whose file carries
  no header (one written before its filing could be registered); a header naming another filing is refused, not
  overridden.

## 4. Details

1. **Why the graph is read before the file.** The two squiddy filings have no `Kind:` line and must not be edited
   (a registered task file is immutable). One `artifact_updated` line retags each; the dispatcher reads `task_kind`
   from `_tasks` and never reaches the file.
2. **Issues.** An Issue names no producer: the type has no field for one. The consumer rule therefore reaches an
   Issue through what `seldon go` sends a Desktop, and reaches a filing through registration as well.
3. **What a filing still meets.** Git recoverability (registration commits it), the number check (a numbered filing
   cannot take a number another task holds), and a repeated `Kind:` header (AD-038-R14).
