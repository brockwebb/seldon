# AD-034 ADDENDUM 01: worktree is the only mode; the CLI's `--worktree` enforces the boundary

**Date:** 2026-10-17
**Status:** Accepted. Implemented by FRICTION-002 Part B (`cc_tasks/2026-10-17_FRICTION-002_vendor_isolation_replaces_hand_built_plumbing.md`).
**Amends:** AD-034-R3 (removes the in-place carve-out for exclusive tasks and for `max_parallel: 1`), AD-034-R6 (applies to every task), AD-034 section 5 (`worktree_dir`, `branch_prefix`). No new ruling.
**Serves:** AD-038-R1 (one tree per session means the primary is written only by its three writers), AD-038-R4 (the stations inspect the session's tree; there is now exactly one per task).
**Code:** `seldon/commands/dispatch.py` (`_launch_inplace`, `_launch_cmd`, `_session_settings`), `seldon/commands/dispatch_worktree.py` (`finish_session`, `sweep`, `_record_kept`), `seldon/core/dispatch.py` (`CLI_WORKTREE_DIR`, `CLI_BRANCH_PREFIX`, c11 for every task), `seldon/core/worktree.py` (`remove` keeps the branch).

## 1. Why the carve-outs go

AD-034-R3 ran an exclusive task, and every task at `max_parallel: 1`, in the primary checkout. That made the primary checkout the session's working tree, the dispatcher's commit target and Desktop's commit target at once. Three stalls on seldon's own queue came from that sharing. A write left uncommitted in the primary refused every launch on c7, and nothing cleared it by itself: 3, 36 and 14 hours (recorded beside `dispatch.stuck_after_passes_by_criterion.dirty_tree` in `seldon.yaml`, DESK-001; the 36-hour one is the 12 to 14 October stall in `docs/research/2026-10-17_where_things_stand.md` section 2). The station that checked "the" tree halted a correct session in DESK-002 because the work sat on a worktree branch while the checks ran in main (Issue 02d52bc4). FRICTION-001 fixed both symptoms writer by writer and station by station. This addendum removes the shared tree that caused them.

## 2. Prior art

- **Claude Code `--worktree`** (the vendor survey, `docs/research/2026-10-17_vendor_survey_codex_claude_code.html` section 1, from code.claude.com's worktree and headless pages, fetched 2026-10-17): one worktree per session, at `<repo>/.claude/worktrees/<name>` on branch `worktree-<name>`, with hard isolation that refuses edits and git aimed at the main checkout. Codex reaches the same end with one VM workspace per task. This addendum adopts the vendor feature, as the survey recommends ("replace, do not re-fix").
- **Observed on the locked CLI (2.1.302), 2026-10-17** (`docs/evidence/friction002/isolation_probe_*.jsonl`, run under `bypassPermissions`, the most permissive mode):
  - A Write to the primary is refused: "This session is isolated in the worktree /private/tmp/f002probe/.claude/worktrees/f002probe. Edit the worktree copy of this file instead of the shared-checkout path."
  - `git -C <primary> commit` is refused: "this command redirects git to the shared checkout via -C. Refusing to run it — a worktree-isolated session's git operations must target its own worktree."
  - A compound git command is refused as "too complex to verify that it stays inside the worktree".
  - A worktree the dispatcher cut beforehand at that path is entered and isolated the same way (`precut`, `precut2`).
  - The CLI locks the worktree it enters, and leaves it in place when the session ends.
- AD-034's own prior art (merge queue, leases, union merge) stands unchanged.

## 3. What changes

1. **Every task runs in a worktree, at every `max_parallel`.** The dispatcher cuts `.claude/worktrees/<stem>` on branch `worktree-<stem>` from main's HEAD after the claim's records are committed. It links `dispatch.worktree_links` (default `[".env"]`; a path absent from the primary is skipped). It starts the CLI in the primary checkout with `--worktree <stem>`, so the CLI enters the cut tree and isolates it, plus `worktree.baseRef: head`, so the CLI never cuts its own tree from `origin`. The path and branch are the vendor's convention, so they are constants. A configured `dispatch.worktree_dir` or `dispatch.branch_prefix` is refused at load. `Exclusive:` remains. It decides whether a task may run beside others (AD-034-R2) and no longer decides where it runs. `max_parallel` stays 1.
2. **c11 is every task's criterion.** The task's worktree path and branch must be free and the path ignored. Every served repository already ignores `.claude/` (seldon, squiddy, ai-readiness-kg and arnold, checked 2026-10-17).
3. **The finish is AD-034-R5/R6's, for every task.** A serial pass holds the pass lease for the whole run, so it runs the supervisor's finish (`finish_session`) without taking the lease again. On green, the finish rebases, runs the union and spec checks, fast-forwards main, and then the dispatcher completes the task. With no `gate_command` declared, a task whose files main changed under it is `merge_blocked: regate_unavailable`, never merged on faith. The session is told not to merge, push or run `seldon cc complete`. The isolation now enforces the merge prohibition for git. Before, only the prompt carried it.
4. **Nothing deletes a branch.** A task that ends unmerged keeps its worktree and branch. `worktree_kept` records the branch, the outcome, the reason, and the RESULT's first line of prose when the branch carries one. A merged task's worktree is removed by `sweep`, run by every pass with no session in flight and after each merge. The sweep removes a worktree only when its task is recorded `merged`, its branch is contained in main, and nothing tracked in it is modified. Each removal is a `worktree_removed` record. The branch stays.
5. **The primary checkout is written by three things only:** the dispatcher's own commits, merges on green, and Desktop's governed commits.

## 4. What the isolation does not cover

The probe found one gap. A plain shell redirect into the primary (`echo y > <primary>/file` through the Bash tool) was **not** refused (`isolation_probe_bash.jsonl`: the file was written). The isolation inspects Edit/Write and git, not arbitrary shell writes. Machine writers that resolve the primary on purpose stay possible: `seldon dispatch part-complete`, the hooks' records, and AD-034-R8's shared ledgers. A stray shell write is still c7's to catch at the next pass, and AD-038-R1's reconciler names it as `unreconciled`. No control is added for it here (AD-038-R6: no new control without a reading that it is needed).

## 5. Parameters

| parameter | value | basis |
|---|---|---|
| worktree path, branch | `.claude/worktrees/<stem>`, `worktree-<stem>` | the CLI's convention, observed on 2.1.302 |
| `worktree.baseRef` | `head` | the branch must start at the main that carries the task's own claim |
| `worktree_links` | `[".env"]` | every served repository keeps its credentials there; absent sources are skipped |
| `gate_command` | optional at `max_parallel: 1` | a serial pass re-gates only when main changed the task's own files; with none, that case blocks |
