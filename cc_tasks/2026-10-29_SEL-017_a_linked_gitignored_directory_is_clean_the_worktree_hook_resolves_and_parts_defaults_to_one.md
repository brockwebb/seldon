# SEL-017: a symlink at a gitignored path is clean at merge, the worktree's hook resolves, and a task without Parts counts as one Part

**Status:** proposed
**Author:** Desktop session (seldon), 2026-10-29, from the hazbrief Desktop thread's three defect reports (HB-64 and HB-72 `merge_blocked`, `seldon verify` in a worktree, `dispatch part-complete`).
**Repo:** seldon (primary). L4: commit, merge, push in seldon. hazbrief-mcp is read by path for the evidence, never written.
**After:** none
**Governing:** AD-034 (worktree dispatch; its merge round and `worktree_links`, FRICTION-002 Part B); HOOK-001 (`core.hooksPath` relative, tracked `.githooks/`); AD-037-R6 (stations; Parts is the CPI input, QC-002). Number new rulings under AD-034.
**Model:** primary
**Spend:** est. 0.4M tokens. Basis: one predicate in `dirty_paths`, one `git config` line at worktree creation, one default in the Parts reader, three fixtures. Zero model calls.
**Network:** none beyond git push.
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes (edits `dispatch_worktree.py`, the worktree creation path and the Parts reader)
**Parts:** A 0.45, B 0.25, C 0.30.
**Premises:**
- premise: the merge round excludes only configured links from the dirt check | check: grep -q "exclude=linked" seldon/commands/dispatch_worktree.py
- premise: dirty_paths lives in the worktree module | check: grep -q "def dirty_paths" seldon/core/worktree.py
- premise: hazbrief ignores the four directories by trailing-slash patterns | check: grep -q "^graphs/\*/work/" /Users/brock/GitHub/hazbrief-mcp/.gitignore
- premise: hazbrief has no worktree_links of its own | check: sh -c "! grep -q worktree_links /Users/brock/GitHub/hazbrief-mcp/seldon.yaml"

Checks are single commands with no shell.

## The condition

A. hazbrief HB-64 (0448b253, `worktree-rosy-sprouting-stroustrup`, ff38054) and HB-72 (10aef6ce, `worktree-floating-snuggling-waffle`, e86bc49) finished their work and are `merge_blocked: uncommitted_changes` on `corpus/raw`, `graphs/hazbrief-corpus/corpus/parsed`, `graphs/hazbrief-corpus/texts` and `graphs/hazbrief-corpus/work`. The sessions symlinked those from the primary checkout so the tests could run (a worktree carries no gitignored file); each is ignored by a trailing-slash pattern, which git does not match against a symlink, so `dirty_paths` reports four untracked paths. HB-63 merged only because its one link, `.env`, is a file pattern. The round's `exclude=linked` covers `dispatch.worktree_links` and nothing a session links itself.

B. `seldon verify` run inside a worktree prints "Commit hook: not installed": the worktree inherits `core.hooksPath` as the primary checkout's absolute path, or none, so the relative `.githooks` HOOK-001 requires does not resolve there.

C. `seldon dispatch part-complete` refuses a task that has no `**Parts:**` header, which is every hazbrief task registered before AD-037-R6's Parts gate reached registration; the milestone station then cannot run and the session is blocked on a header it cannot add (the base file is immutable).

## What to build

**A. Clean means git-clean.** `dirty_paths` treats a path as clean when it is a symlink whose own path matches an ignore pattern once the trailing slash is disregarded, or whose target is inside the primary checkout at an ignored path; a session's own links are therefore as clean as configured ones. Record each such link in the merge record (`linked_by_session`). Fixture: a worktree with a symlink to an ignored directory merges; a symlink to a tracked path still blocks. Then redrive HB-64 and HB-72 is hazbrief's to do (HB-73 there); do not merge them from this task.

**B. The worktree's hook.** At worktree creation the dispatcher sets `core.hooksPath` to the relative `.githooks` in the worktree's own config (never the primary's absolute path), and `seldon verify` reports it found. Fixture: verify in a fresh worktree reports the hook installed.

**C. Parts defaults to one.** A task with no `**Parts:**` header is read as `A 1.00` by `part-complete` and the stations, with a `parts_defaulted` note on the record, so CPI is computed over one Part; registration keeps refusing a new file without the header (SEL-011). Fixture: part-complete on a header-less fixture task succeeds and notes the default.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.5M.

## Deliverables

A, B, C with tests; rulings under AD-034; `cc_tasks/2026-10-29_SEL-017_a_linked_gitignored_directory_is_clean_the_worktree_hook_resolves_and_parts_defaults_to_one_RESULT.md`.
