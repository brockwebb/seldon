# RESULT: SEL-012, the pass-ledger hook lands and installs in seldon; the four siblings follow as SEL-015

**Executed:** Claude Code (Opus 5.5), dispatched headless in worktree `flickering-prancing-stream`, 2026-10-28, on
main `7dbced4`. **Addenda:** none (globbed `cc_tasks/2026-10-28_SEL-012_*ADDENDUM*.md`: no files).
**Spend:** zero model calls. **Network:** none (no push: the launch instruction forbids it here).
Recall used: squiddy:2026-10-27_SQ-096_a_pass_reaches_main_only_on_main_and_seldon_verify_refuses_a_forked_pass_ledger_RESULT, seldon:2026-10-09_HOOK-001_commit_gate_is_a_hook_not_a_protocol_RESULT

| Part | State |
|---|---|
| Premises | All three hold. |
| A, land the branch | **Done on this branch.** `e2d0fd8` was cherry-picked cleanly as `b5b3faf`, because DESK-004R's `e60123f` was already in the branch's base `f797f31`, so there was nothing to resolve. Full suite: 2,996 passed, 7 skipped, 1 failed. The failure was already known before this change. The dispatcher merges this branch (launch instruction); I did not. |
| B, install everywhere | **seldon: done** (`a35c0c5`, which tracks `.githooks/prepare-commit-msg`). **The four siblings: not installed here, on purpose.** Each was rehearsed in a scratch clone, and all four came out clean. The live installs are filed as **SEL-015** (`70d17196`, `**After:**` this task), so the dispatcher runs them once this branch is on main. **squiddy `core.hooksPath`:** was absolute, now relative (values below). |
| C, prove the refusal | **Done.** In a scratch clone of squiddy, a rebase whose ledger conflict was resolved to the branch's side was refused at `git rebase --continue`, with `pass_ledger_forked` and R-237's text. Taking main's side and recording the pass again went through. |

## Premises

| premise | check | result |
|---|---|---|
| the SQ-096 seldon branch exists and is unmerged | `git rev-parse --verify feat/sq096-pass-ledger-fork` | holds: `e2d0fd8`, one commit beyond main's ancestor `f797f31` |
| the installer exists | `test -f seldon/commands/hooks.py` | holds |
| the squiddy SQ-096 RESULT exists | `ls .../2026-10-27_SQ-096_*_RESULT.md` | holds; read in full before Part A |

## Part A: the branch lands

- `git cherry-pick e2d0fd8` gave `b5b3faf`, with no conflicts. Since `f797f31`, main has changed none of the seven
  files the commit touches (`git log f797f31..main -- <files>` is empty). `git merge-base --is-ancestor e60123f f797f31`
  is true, so DESK-004R's installer changes were already under the SQ-096 commit, and there was nothing to resolve
  against them.
- **Full suite** (branch on PYTHONPATH, `-n 8`, 18 min 54 s): **2,996 passed, 7 skipped, 1 failed.** The failure is
  `test_pa002_release_resolve::test_rebuilding_the_served_release_reproduces_the_served_index`
  (`release_unavailable`: squiddy's `graphs/library/extract/control.yaml` `index:` block differs from the one in the
  release commit). SQ-096 recorded the same failure on main `f797f31`, and so did SEL-008/009 (library index drift,
  Issue dbe38fac). It reads squiddy's library and touches nothing this change does. I did not re-run it on main in
  this session.
- The third hook is tracked under `.githooks/` (Part B, `a35c0c5`). `seldon hooks install` writes all three, which
  the rehearsal (Part B) and Part C both show.
- The commits after `a35c0c5` on this branch went through all three hooks, the new `prepare-commit-msg` included.
  When git runs the hook, its cwd is the worktree, so `python -m seldon` imports the branch's code.

## Part B: the installs

### seldon (this branch)

`python -m seldon hooks install --repo .` printed:
`core.hooksPath /Users/brock/GitHub/seldon/.githooks -> .githooks; seldon.python /opt/anaconda3/bin/python; committed .githooks/prepare-commit-msg as a35c0c5`.
After it, `hooks status` gives `installed: true, sequenced: true` and the tree is clean.

**Finding: seldon's own `core.hooksPath` was absolute too**, not only squiddy's. The local config is shared by every
worktree, so this run also moved seldon's primary checkout to the relative `.githooks`. The primary's main has no
`prepare-commit-msg` file yet, so its commits still run the same two hooks as before. Every seldon worktree tracks
`pre-commit` and `commit-msg`, so relative changes nothing for those worktrees either.

### The four siblings: rehearsed, and filed as SEL-015

**Why not installed here.** A sibling's hooks run the *installed* seldon, which is the editable install at
`/Users/brock/GitHub/seldon`, on main. Until this branch merges, main has no `seldon hooks prepare-commit-msg`. A
tracked `prepare-commit-msg` in a sibling would therefore refuse every commit there, the dispatcher's record commits
included. SQ-096's RESULT ("Not done here", item 2) found the same and deferred it for the same reason. This session
cannot merge (launch instruction), so the live installs wait on the merge.

**SEL-015**
(`cc_tasks/2026-10-28_SEL-015_the_prepare_commit_msg_hook_installs_in_the_four_siblings_once_main_carries_it.md`,
`70d17196`) is registered with `**After:** 2026-10-28_SEL-012_...`. The dispatcher holds it until this task
completes, which happens at the merge, and then launches it. No operator step is needed. Its step 0 re-checks, at
launch, that main carries the subcommand and the hook file.
- I first filed it as SEL-012R. Registration refused that name (`number_taken`: a re-filing over an in-progress
  holder), and `seldon task number SEL` gave SEL-015.
- Its two launch-time facts were first written as `**Premises:**`. Registration evaluates premises at once
  (AD-038-R5), and both are false until the merge, so they became step 0.

**Rehearsal** (`docs/evidence/sel012/rehearse_b.py`, transcript `rehearse_b_transcript.txt`). For each sibling:
- a `git clone` under `/tmp`, with the siblings symlinked beside it so relative refs resolve;
- the primary's untracked `.githooks/*` copied in;
- `seldon hooks install` run with this branch's code.

All four exited 0 with `installed: true, sequenced: true` and a clean clone:

| repo | the install committed |
|---|---|
| squiddy | `.githooks/prepare-commit-msg` |
| arnold | `.gitattributes` (`governed/ledger/events.jsonl merge=union`), then `.githooks/commit-msg` and `.githooks/prepare-commit-msg` |
| ai-readiness-kg | `.githooks/commit-msg` (untracked in the primary, seldon's exact text) and `.githooks/prepare-commit-msg` |
| hazbrief-mcp | `.gitattributes` (`seldon_events.jsonl`, `state/prior_art_queries.jsonl` merge=union), then `.githooks/prepare-commit-msg` |

- Every hook file on disk in the four primaries is seldon's exact text (compared against `seldon_hook_scripts()`), so
  `_write_hook` refuses none of them.
- The installer's commits are pathspec-limited (`git commit -- <paths>`, `seldon/core/hooks.py:283`). The unrelated
  uncommitted files in arnold (2) and hazbrief-mcp (8) stay out of them.

### squiddy `core.hooksPath`

| when | value |
|---|---|
| SEL-012's survey, ~09:35 EDT (`docs/evidence/sel012/survey.py`) | `local  /Users/brock/GitHub/squiddy/.githooks` (absolute, against HOOK-001) |
| read just before setting it, 09:51 EDT | `.githooks` |
| after `git -C squiddy config --local core.hooksPath .githooks` | `local  .githooks`; `seldon hooks status` gives `installed: true` |

**Something else changed it between the two reads.** No squiddy commit landed in that window. The most likely writer
is squiddy's standing dispatcher pass: `seldon/commands/dispatch.py:567` runs `hooks.ensure_installed` before every
pass. `status` counts an absolute path as a problem, so `ensure_installed` re-points it. That attribution is an
inference from the code, and no event recorded it. My `config` write set the value it already had. Before I set it,
I checked that both squiddy worktrees track `pre-commit` and `commit-msg`, so the relative path changes no hook that
runs.

## Part C: the refusal, in a scratch clone of squiddy

Script: `docs/evidence/sel012/partc.py`. Full transcript: `docs/evidence/sel012/partc_transcript.txt`.
- The clone is of squiddy main `ff64a7a4`, whose ledger has 25 lines. This branch's seldon was installed there.
- The branch `sel012-fork` recorded one pass through `kitpass.record` (the kit's own write path), chained onto line
  25. Main then recorded another pass on the same line 25.
- `git rebase main` conflicted on `kit/ledger/passes.jsonl`. I resolved it with `checkout --theirs`, the branch's
  side, which is SQ-021M2's mistake, and ran `git rebase --continue`:

```
$ git rebase --continue
  seldon commit gate: 1 finding(s) in the staged files:
    - kit/ledger/passes.jsonl (staged): .../staged.jsonl against main: pass_ledger_forked: line 26 is kit_suite_pass
      for commit d3f3f6396005 (tree 000000000000, recorded 2026-10-28T13:48:47.660292+00:00, prev d54421a2b436);
      main's line 26 is kit_suite_pass for commit d3f3f6396005 (tree 000000000000, recorded
      2026-10-28T13:48:53.649418+00:00, prev d54421a2b436). main's pass ledger has one sequencer, main (DN-052 R-237):
      a pass a branch recorded is never merged into it; take main's ledger in the conflict and record the merging
      tip's pass again on main's last line
  Refused by the commit gate (AD-036-R4; HOOK-001). ...
  error: could not commit staged changes.
  [exit 1]
```

Then I did what R-237 says: `git checkout HEAD -- kit/ledger/passes.jsonl` (main's side; HEAD is the onto commit
during a rebase), recorded the pass again onto main's line 26, and ran `rebase --continue`. It gave
`Successfully rebased and updated refs/heads/sel012-fork`, exit 0. The script exits 0 only when both halves hold.

- Both scratch passes name the same commit, because each recorded `HEAD` (the hooks commit) at the time. The two
  lines differ by timestamp, which is what makes them a fork.
- **My first run of the second half was wrong.** After the first `add`, `checkout --ours` had no unmerged entry left
  and re-read the index, so the branch's line stayed staged and the hook refused it again, correctly. The script now
  uses `checkout HEAD --`.

## Not done here

- **The merge and push of this branch:** done by the dispatcher (launch instruction).
- **The four sibling installs and their pushes:** SEL-015, which the dispatcher launches after the merge.
- **The SQ-096 branch and worktree:** `feat/sq096-pass-ledger-fork` and `.claude/worktrees/sq096-pass-ledger-fork`
  are left as they are. This session may not remove other worktrees. Once this branch is on main, its content is
  there (as `b5b3faf`, a cherry-pick, so `git branch -d` will report it unmerged). To clean up, from a shell in
  `/Users/brock/GitHub/seldon`, after the merge:
  ```
  git worktree remove .claude/worktrees/sq096-pass-ledger-fork
  git branch -D feat/sq096-pass-ledger-fork
  ```

## Session usage

- Zero model calls, zero network.
- Tokens: 127,991 at the Part A boundary (`seldon dispatch part-complete`), against an estimate of 0.4M and a stop
  at 0.5M. Parts B and C are recorded at their own boundaries.
- Most of the wall clock was the full suite (19 min, detached, polled).
