# Filing from factory: a declared worktree link to a tracked directory is skipped without a word

**Kind:** filing
**Filed by:** factory
**Author:** Desktop session (factory coordinator, FCT-4), 2026-11-25.
**Waits behind:** SEL-047 and the gate-time work (factory F-027 items 1 and 3). Nothing in factory is blocked on it today.

## What factory experienced

Factory's `seldon.yaml` declares `dispatch.worktree_links: [.env, corpus/inbox]`. Twice, a dispatched session found `corpus/inbox/` in its worktree as an empty real directory, not the link:

- FAC-06 (`b62cd550`), RESULT line 29: "this worktree's `corpus/inbox/` was an empty directory, not the link `dispatch.worktree_links` describes". The session put its held copies into the primary by `cp -n` by hand (RESULT line 159).
- FAC-06R (`92f90769`), RESULT line 9: "`corpus/inbox/` at launch: an empty real directory (only `.gitkeep`), not a link."

## The evidence, read from the code and the trees

- `factory` tracks `corpus/inbox/.gitkeep` (`git ls-files corpus/inbox`), so every checkout, a worktree included, creates the directory.
- `seldon/core/worktree.py` `link()` skips a `rel` whose destination exists (`if not src.exists() or dst.exists() ...: continue`) and returns only the paths it linked. Nothing is recorded for the skip.
- seldon's own `seldon.yaml` comment on `worktree_links` (SEL-037 Part A) states the same property for `graphs/seldon-biblio/exports/`: a checkout creates it and `worktree.link` skips it. So seldon knows the case; a consumer declaring such a path is not told.

## What factory wants to know back

1. Whether a `worktree_links` entry the checkout itself creates is a configuration seldon refuses or warns about at load, or something the consumer must find by reading `worktree.py`.
2. If the answer is the consumer's side, which form factory should use for a local, gitignored inbox that must be shared with every worktree (its CLAUDE.md, "`corpus/inbox/` is local and never published").
