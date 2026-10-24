# AD-034 ADDENDUM 05: every governed repository declares its append-only logs merge=union

**Date:** 2026-10-23. **Written by:** ATTR-001 (`cc_tasks/2026-10-23_ATTR-001_every_governed_repo_merges_its_append_only_logs_by_union.md`).
**Applies:** AD-034-R7 (SEL-004 decision 4) to the repositories it was never installed in, by AD-038-R1 (the machine
reconciles its own state) and DESK-001 (the tool that writes a governed file commits it). No new ruling.

## Evidence

squiddy's dispatcher log, 2026-10-23: `MERGE BLOCKED 00203aed (rebase_conflict): seldon_events.jsonl; worktree
.claude/worktrees/compressed-shimmying-hearth kept; issue 295ad039`. SQ-021 finished its work. Its branch could not be
rebased because squiddy's main gained event lines while the session ran. R7 says `.gitattributes` is the only list of
append-only files. Before this addendum only seldon's `.gitattributes` existed. In squiddy, arnold, ai-readiness-kg
and hazbrief-mcp, `union_files` returned nothing, so every worktree task whose main moved ended `rebase_conflict`.
SQ-019, SQ-023, SQ-028R and SQ-029R merged only because nothing was appended to main while they ran.

Rehearsed in a `git clone --shared` of squiddy under /tmp (squiddy untouched). SQ-021's branch 6f4d784 was rebased onto
main e82e0a3 from merge base 0e77570:

| | lines in `seldon_events.jsonl` |
|---|---|
| merge base | 8956 |
| main side | 8989 (+33) |
| branch side | 8976 (+20) |
| after union rebase | 9009 |

Without the declaration, the rebase conflicts on `seldon_events.jsonl` alone. With it, the rebase is clean,
`check_union_text` passes (0 malformed, 0 duplicate `event_id`), and the whole merged file has 0 repeated ids.

## Prior art

- **gitattributes(5), `merge=union`.** Git's built-in union driver keeps both sides' lines. The manual names it for
  line-oriented files where order does not matter and warns that it does not check the result. AD-034 §2 already
  cites it. Adopted unchanged.
- **The attribute is tracked repository state.** Git reads `merge` from the `.gitattributes` in the tree being merged.
  A driver therefore applies on a rebase only when the attribute is committed on the branch being rebased onto. So
  this addendum commits it on each project's main and does not set it in `.git/info/attributes` or in global config.
- **SEL-004 decision 4 / AD-034-R7.** The merged result is checked (valid JSONL, unique `event_id`) because the driver
  alone cannot see a fused or duplicated line. Applied unchanged. This addendum only widens where the attribute exists.

### Internal

- internal receipt: query "union driver" | repo seldon@902a493af98b1726ef7d394cc47b093346251103 | hits docs/design/AD-034_worktree_per_task_dispatch.md:19
- internal receipt: query "gitattributes" | repo seldon@902a493af98b1726ef7d394cc47b093346251103 | hits docs/design/AD-034_ADDENDUM_03_kept_work_is_regated_in_place.md:39, docs/decisions/register/00211_seldon-ad-034-r7_accept.yaml:1, docs/design/AD-034_worktree_per_task_dispatch.md:41, docs/design/AD-034_worktree_per_task_dispatch.md:19, docs/decisions/REGISTER.md:9

### External

- library receipt: query "git merge driver union append-only log" | release library_graph_20261017_sq018_02_2026-10-17.json sha256:99984ba3da90146a73ab4e9d8ddf15687551cb2cc2659be90d16e525253ecfb5 | rows lesson:2026-05-09_10_1145_3805621_3807648#p12:248:2739-3071

The library arm returned nothing on git merge drivers. It is a corpus of AI-research lessons, and the receipt above
records that search. The source for the driver is the git manual, which AD-034 §2 names.

## What changed

- **The list is derived from the project, not copied.** `seldon.core.hooks.append_only_paths` lists:
  - the event store (`event_store.path`);
  - the governed ledger, where the governed graph directory exists;
  - the prior-art query log, where a `prior_art:` block is configured (its own, or the one its `ref` names).
  
  A path git ignores is left out because an untracked file is never merged (arnold ignores `*.jsonl`, so only its
  tracked ledger is listed). A `prior_art:` block that cannot be resolved raises an error naming the block; it is
  never skipped. `union_missing` asks git (`git check-attr`) and does not match text, so a wider pattern someone
  already wrote counts.
- **`seldon hooks install` writes and commits it.** In a seldon project, `declare_union` appends the comment and the
  missing `<path> merge=union` lines to `.gitattributes`, creating the file if needed and keeping what was there.
  It then commits that file alone, path-scoped, through the hooks. Running it again with nothing missing writes and
  commits nothing.
- **A pass declares it too (AD-038-R1).** `_reconcile` runs under the lease, with no claim in flight and on the
  configured branch, and it calls `declare_union` first. So each governed repository is fixed by its own dispatcher's
  next pass after this merges. Without that, they would wait on someone to run the installer. A `.gitattributes`
  with uncommitted edits is left alone and named on stderr, and so is a failure to write or commit.
- **c16 `union_attribute_missing`.** `union_state` is read once per pass and passed to `evaluate`. When anything is
  missing, c16 refuses every launch. Like c7, it is a fact about the checkout, so it is reported ahead of the
  task-specific reasons. The refusal line names the files and `seldon hooks install`. `seldon dispatch status`
  reports `union_attribute_missing` at the top. c16 is absent when the attribute is declared, as c13 to c15 are, so
  a healthy project's criteria vector does not change. An unreadable list fails closed with `read_error`.

Code: `seldon/core/hooks.py` (`append_only_paths`, `union_missing`, `declare_union`), `seldon/commands/hooks.py`,
`seldon/core/dispatch.py` (`union_state`, c16, `first_refusal_reason`), `seldon/commands/dispatch.py`
(`_declare_union`, the refusal line, `status`), `seldon/commands/dispatch_worktree.py`. Tests:
`tests/test_attr001_union_attribute.py`.

## Not covered

- **A `merge_blocked` task is not re-merged by the dispatcher.** AD-034-R10's regate covers only
  `stop_gate_unpassed`. Once squiddy's main carries the attribute, SQ-021 still needs a hand rebase and merge, or an
  amendment to R10 that extends regate to a `rebase_conflict` whose files are all now `merge=union`. This addendum
  makes neither.
- **Other append-only files.** squiddy's `kit/ledger/passes.jsonl` is appended by kit passes and appears in SQ-021's
  write set. It did not conflict in the rehearsal, and nothing declares it. A project can declare more files by hand.
  The installer covers only the three classes seldon itself writes.
