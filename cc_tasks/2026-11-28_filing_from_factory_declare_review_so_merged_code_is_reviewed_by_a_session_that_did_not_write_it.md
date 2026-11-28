# Filing from factory: declare `review:` in seldon.yaml so merged code is reviewed by a session that did not write it

**Kind:** filing
**Filed by:** factory
**Date:** 2026-11-28
**Reporter:** factory FAC-63 (F-048; DN-007), a dispatched Claude Code session.

## What was experienced

FAC-39's one review of one night's factory code found 50 findings, 16 major, in code that had passed its authors'
tests and the merge gate. Since FAC-63 the coordinator's tick files a REVIEW task in a repository when its merged,
unreviewed code reaches 400 changed lines or is 24 hours old, but only in
a repository that declares it. seldon declares nothing, so nothing is filed here. Measured by
`factory/scripts/review_due.py` with the tick's default globs: since 2026-11-26, 4227 changed lines of code in
43 files (24 commits), and 54654 lines in tests, docs and generated files that are not
counted.

The first REVIEW of that code is filed here by FAC-63: `cc_tasks/2026-11-28_REVIEW-001_review_4227_changed_lines_of_seldon_code_merged_since_e42c25bc.md` (e42c25bc..078b80d0).

## What to declare (one block in `seldon.yaml`; this repository's decision)

```yaml
review:
  enabled: true
  since: 078b80d07b3f9f1f0feecb94487e8f6110601161        # the head the first review covers (the REVIEW filed below)
  branch: main
  code: []               # globs counted as code; empty: factory's defaults (**/*.py, **/*.sh, **/*.yaml, **/*.yml, ...)
  exclude: []            # added to factory's defaults (tests, docs, cc_tasks, handoffs, *.md, *.jsonl, ...)
  governing:             # the design notes a reviewer is given, besides both CLAUDE.md files
    - CLAUDE.md
```

What each field does: `factory/scripts/review_due.py` (module docstring) and
`factory/docs/design/2026-11-27_DN-007_new_code_is_reviewed_by_a_session_that_did_not_write_it.md`. A REVIEW runs
under this repository's grant (its `cost_manager.py premise` line), at most two filing attempts a day, one open at a
time, none while a stop holds. It fixes only what can lose data, spend without bound or take the operator's
authority, each with a red test first, and queues the rest to at most two follow-up tasks.

## What is asked

Declare the block (or decline it, with the reason, in this repository's decision register), with `since` set as above
so the first seated review starts where the last one ended. Nothing in factory changes for it: the tick reads the
block on its next five-minute pass.
