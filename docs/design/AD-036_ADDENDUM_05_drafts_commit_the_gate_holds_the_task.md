# AD-036 ADDENDUM 05: a draft note commits; the gate holds the task it governs

**Date:** 2026-10-15. **Task:** DESK-001 (`cc_tasks/2026-10-15_DESK-001_desktop_writes_are_committed.md`, task
`5558c652`). **Amends:** AD-036-R4. It moves R4's commit point and registration point; it adds R13. The task names this
"ADDENDUM 04"; that number was taken on 2026-10-14 by DISP-c7, so this is 05. The mechanism is
`seldon/core/hooks.py` (`commit_msg`, `is_draft`), `seldon/core/desktop_commit.py`, `seldon/core/governing_commit.py`,
`seldon/commands/cc.py` (`register_task_file`) and `seldon/core/dispatch.py` (criterion c14, `governing_unverified`).

## 1. The condition, measured

AD-036-R4 says the gate refuses at two points. At commit, it refuses a design note without a passing prior-art verdict.
At registration, it refuses a task whose governing note has no passing verdict. Both refusals leave nothing committed.
The note a Desktop session wrote stays untracked. The dispatcher's c7 (clean tree, DN-006 decision 2) then refuses
**every** task in the queue on every five-minute pass, not just the one the note governs. Nobody is told until someone
reads the log. Recorded stalls:

| Date | Untracked file | Stall | Record |
|---|---|---|---|
| 2026-09-22 | DN-008 (ai-readiness-kg, task 92421acb) | about 3 hours | ai-readiness-kg task 21af86f8 |
| 2026-10-12 | MODEL-003's note | about 36 hours | Issue 7e70aeb0 |
| 2026-10-14 | DN-014 ADDENDUM 01 (ai-readiness-kg, tasks ba40cb29, e2c4e125) | about 14 hours, 126 passes | DESK-001 |

So the commit-point refusal did not stop an unreceipted note reaching a task. Registration and dispatch stopped that.
What the commit-point refusal did was stop every other task.

## 2. Ruling

- **AD-036-R13. A design note without a passing prior-art verdict may be committed as a declared draft, and the gate holds every task the note governs until the note passes.**
  - **Commit.** A commit that carries such a note passes only if its subject line has the `draft:` token. The git
    `commit-msg` hook enforces this from the tracked `.githooks/commit-msg`. That hook reads the message and the same
    index pre-commit reads. A checkout without that hook keeps the check in pre-commit and refuses as before, so the
    gate fails closed. A merge is not judged: its commits were judged on their branch.
  - **Registration.** Registration verifies the note and records its verdict. A failing verdict no longer refuses the
    registration. Note, task file and verdict go in one `draft:` commit. The task is registered. The reply prints one
    `HOLD` line per note, with the command that clears it.
  - **Dispatch.** The dispatcher refuses a candidate whose governing note lacks a passing verdict for its current bytes,
    as `governing_unverified` (criterion c14). Only that task waits; the queue does not.
  - **Audit.** `bypassed()` does not report a `draft:` commit, because it was declared. `seldon verify` warns on a
    committed draft note instead of failing. A note whose current bytes are uncommitted still fails Tier A, because it
    is the change in hand.
  - R4's other clauses stand: baseline notes are grandfathered; every refusal and hold quotes what is missing and
    names AD-036.

## 3. Why not the alternatives

- **Keep the commit refusal and commit the note some other way** (with `--no-verify`, or by an operator). That is the
  bypass `hook_bypassed` exists to report. It also leaves the 3 to 36 hour latency in place.
- **Mark drafts in the note's own bytes** (a `Status: draft` header). Clearing the draft would then mean editing the
  note, which changes its hash and needs a new verdict for bytes nobody meant to change. It also puts gate state in a
  document.
- **Register nothing on a failing verdict** (SEL-006 as built). The refused task file stays untracked and stalls the
  queue in the same way. Committing it unregistered would fail `seldon verify`'s "Unregistered files" check (Tier A)
  for every later session.

## 4. Prior art

### External

- Git's own manual places message checks in `commit-msg`, because pre-commit cannot see the message. Pre-commit "takes
  no parameters, and is invoked before obtaining the proposed commit log message". `commit-msg` "is invoked by
  git-commit and git-merge, and can be bypassed with the `--no-verify` option. It takes a single parameter, the name of
  the file that holds the proposed commit log message. Exiting with a non-zero status causes the command to abort."
  That is why this ruling uses `commit-msg`, and why a merge is skipped explicitly.
- web receipt: url https://git-scm.com/docs/githooks | retrieved 2026-10-15
- The pattern of draft in the record, gate at integration, is GitHub's draft pull request: "Draft pull requests cannot
  be merged". Recording work in progress is allowed; integrating it is not. Here, committing is the record and
  dispatch is the integration.
- web receipt: url https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/about-pull-requests | retrieved 2026-10-15
- The library holds no source on git workflow gates. The query below returned 50 rows, none about commit gating. It is
  logged in `state/prior_art_queries.jsonl`, the same finding as ADDENDUM 02 section 3.
- library receipt: query "draft work in progress commit allowed gate at merge or integration instead of commit" | release library_graph_20261012_sq013_01_2026-10-12.json sha256:0989759c402ca41472806bdf9ab47529ba2eb5a6b25d0e75c1a6e29e650d4275 | rows lesson:2026-05-09_10_1145_3805621_3807648#p12:247:2585-2737

### Internal

- AD-036-R11 (ADDENDUM 04): "An automatic process that leaves a tracked file dirty is a defect." This ruling applies
  R11 to the writer that had no commit path, a Desktop session, and to the gate whose refusal left the dirt.
- DN-006 decision 2's c7 is the criterion every stall above tripped. ADDENDUM 01 decision 6b to
  `2026-09-19_seldon_hygiene_superseded_cadence_after.md` is the stuck alarm DESK-001 Part B moves to the first pass.
