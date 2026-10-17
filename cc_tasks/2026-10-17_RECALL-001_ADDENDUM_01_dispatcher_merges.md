# RECALL-001 ADDENDUM 01: the dispatcher merges; the session does not

Written 2026-10-17 by a Desktop session in squiddy (SQ8), after FRICTION-002 landed AD-034 ADDENDUM 01 (worktree is the only mode).

- Strike "Work on a branch; merge before each `part-complete`" from the header. You run in a worktree. Commit on your worktree branch and push it. The dispatcher merges on green and completes the task. A `git -C <primary>` or any write to the primary checkout is refused by the CLI's isolation; do not attempt one.
- `part-complete` records are still written per Part; the milestone station inspects your worktree.
- Everything else in the task stands.
