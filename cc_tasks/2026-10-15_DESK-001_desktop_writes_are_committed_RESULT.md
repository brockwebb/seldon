# RESULT: DESK-001, desktop writes are committed (task 5558c652)

**Merged:** f4f5214 (fast-forward from branch `feat/desk001-desktop-writes-committed`). **Suite:** 2522 passed, 0 failed,
0 skipped (22 min 08 s, `PYTHONPATH` set to the worktree, run detached and polled; log `/tmp/desk001/full2.txt`).

**Tool.** `seldon commit-governed <path>... [--project DIR] [--json]` and the MCP tool
`seldon_commit_governed(paths: list[str], project_dir=".") -> str` (`seldon/core/desktop_commit.py`).
- It commits exactly the named paths, through the hooks, as `desktop: <kind>: <basename>`, and returns
  `committed <sha> <message>`.
- It refuses, with nothing staged: paths outside `desktop_commit.roots`, outside the project, missing, gitignored or
  unchanged. Under `scan.roots` it also refuses a file `squiddy.secret_scan` flags.
- A hook refusal comes back verbatim as `hook_refused`, and the paths are unstaged.

**Registration.**
- It now commits the notes named in `**Implements:**`, `**Amended by:**` and `**Resolves:**`, as well as
  `**Governing:**`. The task file goes in the same single commit.
- A governing note with a FAIL verdict no longer refuses the registration. The verdict is recorded and staged. Note and
  task go in one `register: draft: ...` commit. The reply prints `HOLD: <note> ...`.
- Every refusal that is left (hook, `ruling_unrecorded`, AD-030-R9, `**After:**`) prints one line: the dispatcher
  refuses every task on c7 until the files are committed.

**AD-036 decision.** AD-036-R4 rules that the commit itself is gated. The change is therefore an addendum, AD-036
ADDENDUM 05, with new ruling AD-036-R13.
- Register: accept `seldon:AD-036-R13` (00284) and amend `seldon:AD-036-R4` (00285, `--by` R13). The three stalls are
  the evidence.
- The hook changed. The new tracked `.githooks/commit-msg` admits an unverified note only when the subject carries
  `draft:`. A merge is not judged. A checkout without `commit-msg` keeps refusing the note in pre-commit (fail closed).
- `bypassed()` skips `draft:` commits, and `seldon verify` warns, not fails, on a committed draft.
- The new dispatch criterion c14 (`governing_unverified`) holds only the task the draft governs.

**Part B.**
- `seldon_handoff` commits the session's touched, uncommitted `docs/design/*.md` and `handoffs/*.md`, then writes the
  handoff and commits it.
- Each pass writes `.seldon/dispatch_last_pass.json`, and `seldon go` prints its refusal lines under **Last pass**.
- `dispatch.stuck_after_passes_by_criterion: {dirty_tree: 1}`: the first refused pass alarms.
- `SELDON_NOTIFY_MESSAGE` carries `stuck: dirty_tree for 1 pass(es); dirty: <paths>`, and seldon's `notify` shows it.

**Checks.**
- New tests are in `tests/test_desk001_desktop_commit.py` (15), plus one each in `test_cc_register_commits_note.py`,
  `test_handoff.py` and `test_dispatch_stuck_and_journal.py` (2).
- FC-27 mutation check: changing `stage` to `git add -A` and the commit to no pathspec fails
  `test_only_the_named_paths_are_committed`. The code was then restored.

**Supersede edge (Part D).** ai-readiness-kg 21af86f8 is now `proposed → superseded`, with the task's reason plus
"superseded by seldon task 5558c652".
- It was written as actor `desktop`, so ai-readiness-kg's dispatcher commits the line. I made no commit there.
- No `superseded_by` edge: 5558c652 is in seldon's graph, not ai-readiness-kg's.

**Premises found wrong.**
1. "AD-036 ADDENDUM 04" was taken on 2026-10-14 by DISP-c7, so the addendum is 05.
2. "Registration still registers the task ... as today" was wrong. SEL-006 refused the registration on a FAIL and
   committed nothing. R13 makes it register with a hold.
3. `--superseded-by` cannot cross graphs.
4. Step 5 reads a last-pass file the pass writes, not the free-text launchd log. The log path is a per-project wrapper
   detail, and parsing it would be fragile.
5. The tests changed by intent: SEL-006's failing-receipt test, PA-001's registration-refusal test, two
   decision-7/6b dispatch tests (now criterion-aware), and the serial-transcript and stuck fixtures, which are pinned
   to the uniform threshold they were recorded under.
