# AD-036 ADDENDUM 09: a task that answers a consumer's filing files its own return in the consumer's repository

**Date:** 2026-10-28. **Written by:** SEL-013R (`cc_tasks/2026-10-28_SEL-013R_a_consumer_filings_answer_files_its_own_return.md`).
**Amends:** nothing. **Extends:** AD-036-R12 (a filing into another repository's `cc_tasks/` registers there and the
registration commits it), which until now ran in one direction only: consumer to producer. One new ruling. The
mechanism is `seldon/core/returns.py`, `seldon cc return`, the refusal in `seldon cc complete`, and
`file_return_at_merge` in the dispatcher's merged finish. Tests: `tests/test_sel013r_answers_files_its_return.py`.

## Evidence

Four hazbrief filings into squiddy were answered by squiddy tasks whose RESULTs ended with "For hazbrief: paste these
steps". The return went through the operator's clipboard. A Desktop then wrote hazbrief HB-63 and HB-64, and
ai-readiness-kg's `2026-10-28_repin_squiddy_to_b16ebb05_after_sq021s_rebase.md`, by hand (squiddy SQ11 work order,
`handoffs/2026-10-28_desktop_sq11_the_factory_runs_without_the_desktop_work_order.md`, item W3). HB-63's own text
says what it is: "The exact lines are in squiddy's ... RESULT, section 'For hazbrief'; read it in full first and run
them in the order it gives." The dispatcher already crossed repositories (AD-034-R12 pushes there). Nothing required
the answering task to file its answer back.

## Prior art

- **Request-Reply, Return Address and Correlation Identifier** (Hohpe and Woolf, *Enterprise Integration Patterns*,
  2003). A requester that wants a reply says where the reply goes (the return address). The reply carries the
  identifier of the request it answers (the correlation identifier), so the requester can match the two. Adopted:
  the answering task's `**Answers:** <repo>:<ref>` is the correlation identifier, and its qualifier is the return
  address. The return's `**Returns:** <producer>:<task id>` is the reply's correlation identifier, pointing back. The
  departure: the reply is not a message on a channel. It is a task file in the requester's own queue, held to the
  requester's own admission checks (its candidacy headers, its numbering, its `After:` order), because the
  requester's dispatcher is what acts on it.
- **Cross-project waits** (AD-038-R8, `seldon/core/cross_project.py`). A `<project>:<ref>` is resolved in the other
  graph through that project's own `seldon.yaml`, read and never written. Applied unchanged to resolve the Answers
  ref.
- **The allocator** (AD-038-R13). The return's number is the consumer's own next number, read from its graph and every
  worktree's `cc_tasks/`. The same optimistic-concurrency rule applies: a collision is refused at registration.

### Internal

- internal receipt: query "return path for a consumer filing answered in another repository" | repo seldon@73b9db8220aa95b930f6190092881e5948f610f5 | hits handoffs/2026-10-28_desktop_sq11_the_factory_runs_without_the_desktop_work_order.md:7
- internal receipt: query "return path for a consumer filing answered in another repository" | repo squiddy@ff64a7a4897fb4c240269fde0b4c8302d164a1c6 | hits none

The seldon hit is the work order that filed this task. squiddy, the repository whose RESULTs carried the "paste"
sections, holds no rule for the return.

### External

- library receipt: query "request reply return address correlation identifier messaging" | release library_graph_20261017_sq018_02_2026-10-17.json sha256:99984ba3da90146a73ab4e9d8ddf15687551cb2cc2659be90d16e525253ecfb5 | rows lesson:2026-04-05_arXiv_2602_20021#p17:111:127-904, lesson:2026-04-05_arXiv_2602_20021#p16:108:1291-1726, lesson:2026-04-05_arXiv_2602_20021#p15:96:241-1196

The library is a corpus of AI-research lessons. Its rows for this query cover agent messaging formats, not the
integration patterns. The source for this addendum is the book named above, cited from the patterns' published
names. Network was out of scope for this task, so nothing was fetched.

## The rule

- **AD-036-R16. A task that answers a filing from another repository carries `**Answers:** <repo>:<ref>`, and
  registration refuses one that does not resolve to exactly one task in that repository's graph
  (`answers_unresolved`). `seldon cc complete` refuses the task (`return_unfiled`) until a return task exists in
  the consumer's `cc_tasks/`. The return names the answering task in its `**Returns:**` header, is registered in
  the consumer's graph and is committed in the consumer's repository. `seldon cc return` writes the return from the
  RESULT's `For <repo>` section, numbers it with the consumer's allocator, sets its `After:` to the consumer's latest
  open task, and registers it there (AD-036-R12). The dispatcher's merged finish runs the same writer when the
  session did not, and pushes the consumer. A finish that cannot file the return blocks the task with the refusal as
  its reason and does not complete it. A RESULT's "for <consumer>: paste" section is retired.**

## Details

1. **The grammar is static, the resolution is not.** `seldon.core.dispatch.parse_answers` is in
   `static_checks` (AD-038-R12), so the dispatcher and registration refuse the same malformed header with the same
   code. Resolving the ref needs the other graph, so that happens at registration only, as cross-project `After`
   refs do. The resolved filing is recorded as `answers_external` on the task.
2. **One filing per task.** A task that answers two filings files two returns. With a list, which RESULT section
   feeds which return would depend on an ordering rule no reader can see.
3. **The return's headers.** The writer owns `Status`, `Author`, `Returns` and `After`, and a section that sets one
   is refused. `Spend`, `Network`, `Framework layer served` and `Parts` come from the section if it sets them, else
   from `returns.headers` in the producer's `seldon.yaml`, else from `seldon.core.returns.DEFAULT_HEADERS`. The
   consumer's registration then applies its own candidacy checks. A return it refuses is deleted from disk, so a
   refusal leaves the consumer's tree as it was.
4. **"Latest open"** is the consumer's most recently registered task in `proposed`, `accepted`, `in_progress` or
   `blocked`. A blocked task counts as open: a return that waits behind a held task keeps the consumer's own order.
5. **Blocked, not completed, on a failed finish.** The merge stands. What is missing is the consumer's half.
   `completed` would tell the consumer nothing and would hide the gap from `seldon go`. The fix is
   `seldon cc return <task>`, then `seldon cc complete <task>`. `blocked` walks to `completed`.
6. **A consumer whose dispatcher is off, or that has none** (hazbrief-mcp has no `dispatch:` block), holds the
   return until someone launches it by hand. That is the consumer's own choice and not this rule's concern.

## Why not the alternatives

- **A cross-project `waits_on` from the consumer's task to the producer's task.** That records that the consumer
  waits. It does not record what the consumer must do, which is the part that went through the clipboard.
- **Have the consumer's dispatcher read the producer's RESULT.** Every consumer would then parse every producer's
  RESULT format. The return task puts the reading in one writer, in the producer, which knows what it landed.
- **Leave the return to the session and make it a criterion.** A criterion is checked by the Stop gate in the
  session's own tree. The return lives in another repository, and only the finish step sees both trees after the
  merge.
