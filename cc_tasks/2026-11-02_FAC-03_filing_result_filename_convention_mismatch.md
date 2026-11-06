# FAC-03 filing: the dispatcher looks for `<full stem>_RESULT.md`, sessions write `<date>_<code>_RESULT.md`, and nothing tells them which

**Status:** proposed (consumer filing; no dispatch headers. Seldon's Desktop turns it into a SEL task or declines it.)
**Filed by:** factory, FAC-03 (task 7a9a839d), 2026-11-02, from a dispatched session.
**Repo affected:** seldon (`seldon/commands/dispatch.py`, `seldon/core/ooda.py`). Consumers seen: factory, aacps-ai-policy.

## The defect

`seldon/core/ooda.py:143` `result_path(source_file)` returns `<dir>/<task stem>_RESULT.md`, and the dispatcher's
finish check reports `result_present` against that path (seldon at b4eba78). The launch prompt
(`seldon/commands/dispatch.py:78`, `DISPATCH_LINE`) names the task file and its addenda but never names the RESULT
path. A session that reads a task saying "RESULT: ..." picks its own filename. Sessions in two repositories picked
the short form `<date>_<code>_RESULT.md`, and the dispatcher recorded the run as `session_failed` even though the work
was complete and the stop gate passed.

## Instances

1. **factory FAC-01** (885f3f0a). `dispatch_finished` 2026-11-01T22:21:26Z, event 08bd2274-4fd4-4a57-98b1-dafccd7960dc:
   `exit_code: 0`, `stop_gate: {passed: true, verdict: pass}`, `result_present: false`,
   `result_path: cc_tasks/2026-11-01_FAC-01_hold_every_cited_source_and_check_every_claim_against_it_RESULT.md`,
   `outcome: session_failed`. The session wrote `cc_tasks/2026-11-01_FAC-01_RESULT.md` (branch
   worktree-temporal-imagining-heron, tip 70ad342).
2. **factory FAC-02** (8723d207). `dispatch_finished` 2026-11-02T03:26:19Z, event 04fe9a62-f0a2-4d43-b701-b678111314b6:
   `exit_code: 0`, stop gate passed, `result_present: false`,
   `result_path: cc_tasks/2026-11-01_FAC-02_merge_fac01_and_hold_its_copies_in_the_primary_RESULT.md`,
   `outcome: session_failed`. The session wrote `cc_tasks/2026-11-01_FAC-02_RESULT.md` (branch
   worktree-recursive-stargazing-honey, tip bfd0e7d).
3. **aacps-ai-policy AP-01 and AP-02**: both RESULTs carry the short name (`cc_tasks/2026-10-31_AP-01_RESULT.md`,
   `cc_tasks/2026-11-01_AP-02_RESULT.md`). **Correction to the FAC-03 task text:** aacps-ai-policy's
   `seldon_events.jsonl` (12 lines, read 2026-11-02) holds no `dispatch_finished` event. Its only dispatcher event is a
   `dispatch_observed_stop` (2026-11-01T04:36:39Z). So AP-01 and AP-02 show that sessions choose the short name; they
   are not dispatcher misses with payloads to cite.

The cost so far is one recovery task (FAC-03) and two worktrees kept so their work could be landed by hand.

## Asked

Either of these, or both:

- **(a) The launch prompt names the exact RESULT path.** `DISPATCH_LINE` already interpolates `{rel}` and `{stem}`.
  Add a clause such as "Write the RESULT to `{result}`," where `result = ooda.result_path(rel)`. This is the root fix,
  because the session then has nothing to guess.
- **(b) The finish check accepts the short form as a fallback.** If `<stem>_RESULT.md` is missing, look for
  `<date>_<code>_RESULT.md` for the same date and code, record which one it found, and keep `result_present` true.
  This repairs runs launched before (a) ships.

The consumer side is being handled: factory now has a CLAUDE.md that states the full-stem convention (FAC-03 Part C).
That only covers one repository, which is why the fix belongs in seldon.
