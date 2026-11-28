# Filing from factory: commit-governed cannot commit a tracked deletion, so an operator's move leaves the primary dirty

**Kind:** filing
**Filed by:** factory
**Date:** 2026-11-28
**Reporter:** factory FAC-61 ADDENDUM 01, a dispatched Claude Code session.

## What was experienced

At 19:28 EST on 2026-11-27 the operator answered a `for_operator` item the way the item tells him to: he edited it and
moved it to `for_operator/done/`. The copy under `done/` was committed (`2b47df2`), but the deletion at the old path
stayed uncommitted: `seldon commit-governed` refused it, because the path is no longer a file. A tracked deletion
leaves the primary checkout dirty, which stops every dispatcher pass (c7 `dirty_tree`). To keep the tree clean the
coordinator restored the old copy from HEAD, so the item then existed twice, answered and unanswered.

## What the evidence shows

`seldon/core/desktop_commit.py` `commit_governed`, the check on each path:
`if not (project_dir / rel).is_file(): return _refuse(NOT_FOUND, f"{rel} is not a file", [rel])`. `D.commit_paths`
(`seldon/core/dispatch.py`) also keeps only paths that exist. So no governed commit can carry a deletion, even of a
file under a configured root that git tracks.

## What factory asks

Could `commit-governed` accept a path that git tracks and the working tree has deleted (`git status` ` D`), under the
same roots and refusals, staging it with `git rm --cached` and committing it in the same pathspec-limited commit as
the other paths, so a move (one deletion and one new file) is one governed commit?

## What factory does meanwhile

The tick commits an operator's move itself: when a tracked `for_operator/<name>.md` is gone from a registered
repository's checkout and `for_operator/done/<name>.md` is there, it commits exactly those two paths with a plain
pathspec-limited `git commit` through the repository's hooks (`factory/scripts/coordinator_tick.py`
`operator_moves_step`, marked `KLUDGE` with this file as its teardown: once the governed commit takes a deletion, the
tick calls it instead).
