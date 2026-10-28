# RESULT: SEL-013R (task 9d4a865e), a task that answers a consumer's filing files its own return in the consumer's repository

**Date:** 2026-10-28. **Branch:** `worktree-squishy-wondering-pascal`. **Ruling:** AD-036-R16
(`docs/design/AD-036_ADDENDUM_09_an_answer_files_its_own_return.md`; register record written pending,
`docs/decisions/register/pending/00001_2a52bf4721a0360b_seldon-ad-036-r16_accept.yaml`, numbered at merge).

Recall used: seldon:AD-036-R12, seldon:AD-038-R13

AD-036-R12 set how the return is filed. The writer registers the file in the consumer through the one registrar
(`register_task_file` with `allow_untracked`), which commits it there, rather than writing and committing by its
own road. AD-038-R13 set how it is numbered: the consumer's `numbering.allocate`, whose `number_taken` check at
registration makes it safe without a lock. The other hits did not change the approach.

No addenda existed for this task (glob `2026-10-28_SEL-013R_*_ADDENDUM*.md`: none).

## What landed

**A. The header.** `**Answers:** <repo>:<ref>`, one filing. The ref is a task number (`HB-37`, an exact token first,
then its identity), a cc_tasks stem, or an id prefix.
- Grammar: `seldon.core.dispatch.parse_answers`, called from `static_checks` (AD-038-R12). A malformed header refuses
  at registration and at the dispatcher as `answers_unresolved`. A repeated header refuses as
  `header_repeated:Answers`.
- Resolution: `seldon.core.returns.resolve_answers`, called by `register_task_file` before anything is created. It
  reads the consumer's graph through its own `seldon.yaml` (`cross_project._open`) and never writes there. The
  resolved filing goes on the task as `answers_external` (`<project>:<artifact_id>`, declared in
  `seldon/domain/research.yaml`). A ref that does not resolve refuses with nothing written, and `cc register` prints
  a fix line for it.

**B. The refusal and the writer.**
- `seldon cc complete` refuses a task with `Answers:` (`return_unfiled`) unless the consumer's `cc_tasks/` holds a
  task whose `**Returns:** <producer>:<task id>` header names it, registered in the consumer's graph and committed
  there (in git's log, nothing uncommitted). The refusal names what is missing and the one command to run. The check
  covers both paths: an unregistered task is refused too, because a return has no id to name.
- `seldon cc return <task file | id> [--to <repo>] [--prefix P] [--dry-run]` writes the return from the RESULT's
  `## For <repo>` section. The heading may be at any level and may run on (`## For hazbrief: paste these steps`
  still reads). It matches the consumer's directory, project name or slug. The header lines at the top of the section
  (`**Title:**`, `**Spend:**`, `**Network:**`, `**Parts:**`, ...) set the return's headers. The rest is the body,
  verbatim.
  - Number: `numbering.allocate` in the consumer. The prefix comes from the answered filing's own token, or from
    `--prefix`.
  - `After:` the consumer's most recently registered open task (proposed, accepted, in_progress, blocked), or `none`.
  - Headers: the writer owns Status, Author, Returns and After, and a section that sets one is refused. Spend,
    Network, Framework layer and Parts come from the section if set, else from `returns.headers` in the producer's
    seldon.yaml, else from `returns.DEFAULT_HEADERS`.
  - Body: what landed (the answering task, its RESULT, the commit and its branch) and what the consumer does with it.
  - Registration: `register_task_file` in the consumer (AD-036-R12) commits the file and applies the consumer's
    gates. If the consumer refuses, the file is deleted, so the consumer's tree is left as it was.
  - Re-running reports the return already filed and writes nothing.
- The dispatcher's merged finish (`dispatch_worktree.file_return_at_merge`, called first in `_finish_merged`, under
  the lease, after the fast-forward):
  - If the session filed the return, the finish records `filed_by_session`.
  - Otherwise the finish runs the same writer from the merged RESULT.
  - In both cases it pushes the consumer through `push_named_repos` (AD-034-R12's reading and refusals).
  - If the return cannot be filed, or the consumer cannot be read, the task is blocked with the refusal as its
    `block_reason` and `dispatch_merge: merged`. The outcome is `return_unfiled`, which goes through notify, and the
    task is never completed. The fix is `seldon cc return`, then `seldon cc complete` (blocked walks to completed).
- `seldon_cc_complete` (MCP) applies the same refusal, through the same `returns.completion_refusal`. Before this, it
  walked a task to completed by its own road, which would have let Desktop bypass the gate.
- The "for <consumer>: paste" section is retired. `docs/conventions/dispatched_session_protocol.md` has a new section
  saying so, and covers the header, the `## For <repo>` section and the command.

**C. The fixture.** `test_fixture_an_answering_task_is_refused_then_returned_then_completed`:
1. A fixture consumer (its own git repository, origin, seldon.yaml and database) registers HB-37.
2. The producer registers SEL-900 with `**Answers:** consumer:HB-37`.
3. `cc complete` refuses SEL-900 with `return_unfiled` and names `seldon cc return`.
4. `cc return` files `HB-38` in the consumer. The file is committed there, registered `proposed`, and has a
   `precedes` edge from HB-37.
5. `cc complete` then completes SEL-900.

Two more tests run the same thing through `seldon dispatch once` with the stub CLI. In one the finish files the
return and pushes the consumer, so its origin is level with it. In the other the RESULT has no section, and the task
ends blocked with `return_unfiled` while the consumer's tree stays clean.

Tests: `tests/test_sel013r_answers_files_its_return.py`, 28 passed (91 s). The scaffold change is one line:
`tests/dispatch_scaffold.py`'s stub may write a given `result_text`.

## Part C's record: ai-readiness-kg's dispatcher is not off

The task asked me to note that "ai-readiness-kg's dispatcher is off by its own DN-006 decision 10, so a return filed
there still waits for a hand launch". On the machine today, that is not true:
- `ai-readiness-kg/seldon.yaml` has `dispatch.enabled: true`.
- `launchctl list` shows `com.brock.airkg-dispatch` loaded (last exit 0).
- DN-006 decision 10 (`ai-readiness-kg/docs/design/2026-09-15_DN-006_standing_dispatcher.md:54`) says the
  opposite of "off": "While `dispatch.enabled` is true, the operator does not hand-dispatch."

So a return filed in ai-readiness-kg is picked up by its own dispatcher like any other task, and must not be launched
by hand while that dispatcher is on. The repository that does hold a return for a hand launch is **hazbrief-mcp**,
whose `seldon.yaml` has no `dispatch:` block. The convention doc names hazbrief-mcp for that reason and does not
repeat the premise. The task spec is unchanged (it is immutable). This paragraph is the correction.

## Gates

- New tests: 29 passed, the MCP parity test included. `tests/test_mcp_tools.py`, `tests/test_mcp_cc_git_guard.py` and
  this file together: 49 passed.
- Full suite (`python -m dotenv -f .env run -- python -m pytest tests/`): **3024 passed, 1 failed, 7 skipped** in
  57 minutes. The failure is `tests/test_pa002_release_resolve.py::test_rebuilding_the_served_release_reproduces_the_served_index`,
  which raised `release_unavailable` because the `index:` block of squiddy's
  `graphs/library/extract/control.yaml` at edd5d5d66bf2 differs from today's. That is the pa002 drift: it depends on
  squiddy's working tree, not on this change. This run started before the MCP fix (932c9a0), so the files that fix
  touches were re-run afterwards (the 49 above).
- Prior art: `seldon prior-art verify docs/design/AD-036_ADDENDUM_09_...`. ADDENDUM 09's three receipts (two internal,
  one library) pass. The note family's verdict is FAIL, on `release_unavailable` rows in ADDENDA 01, 02, 03 and 05.
  Those library releases can no longer be rebuilt because squiddy's `index:` block changed. That failure predates
  this task and is not in its receipts. The commit gate accepted the addendum once its register record was staged
  with it (AD-033-R2).

## Token readings

- Part A boundary: 156,526 tokens, wall 459 s.
- Part B boundary: 183,115 tokens, wall 761 s.
- Part C boundary: 222,827 tokens, wall 5,595 s. Most of that wall time was the full suite.
- Stop condition: 0.5M.

## Not done, and why

- No real return was filed into hazbrief-mcp, squiddy or ai-readiness-kg. No task in any of them carries `Answers:`
  yet, and filing a fixture into a live repository would be a live filing. The writer is exercised on the fixture
  consumer only.
- A consumer with its own `dispatch:` block (squiddy, ai-readiness-kg) holds a return to its own candidacy headers.
  The fixture consumer has none. `register_task_file` applies the same `static_checks` either way, so a section that
  lacks a required header is refused there with the consumer's own code. No test covers a dispatch-configured
  consumer.
