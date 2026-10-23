# AD-036 ADDENDUM 08: a `prior_art.ref` resolves at the primary checkout, as the corpus does

**Date:** 2026-10-22. **Task:** HOOK-002 (`cc_tasks/2026-10-22_HOOK-002_prior_art_ref_anchors_at_the_primary_checkout.md`).
**Amends:** nothing. No new ruling. ADDENDUM 06 section 2 rule 6 anchored a block's corpus paths at the primary checkout
(`corpus_anchor`); this applies the same rule to the one repository-level path it missed, the `ref` of ADDENDUM 03.
The mechanism is `seldon/core/prior_art.py` (`resolve_block`). Tests: `tests/test_hook002_ref_anchor.py`.

## 1. The defect, measured

squiddy, ai-readiness-kg and arnold define no `prior_art:` block of their own. Each holds
`ref: ../seldon/seldon.yaml#prior_art` (ADDENDUM 03). `resolve_block` read that path relative to the project directory.
A dispatched session's project directory is a linked worktree, `<primary>/.claude/worktrees/<name>`, so the ref named
`<primary>/.claude/worktrees/seldon/seldon.yaml`, which does not exist. `hooks.prior_art_findings` turns that
`PriorArtError` into a finding, and the pre-commit hook refused every commit from a worktree, note or not, before it
judged a file. SQ-019 (2026-10-21), SQ-029R, SQ-028R, SQ-022 and SUITE-001 (2026-10-22) each record the refusal, and
each committed with `--no-verify`. The bypassed commits reached main through the dispatcher's merge, which runs at
the primary checkout. The gate was not run on them.

## 2. The rule

1. **A relative `ref` resolves against `corpus_anchor(project_dir)`.** That is the project directory itself, or the
   same directory in the primary checkout when the project is a linked worktree. One function decides what "this
   repository" means for every repository-level path: the ref, the corpus roots and the library graph.
2. **The project's own state stays in the checkout.** The query log, the baseline, the design directory and the
   verdict ledger still resolve against the project directory, as ADDENDUM 03 and 06 rule 6 say. A worktree's
   verdicts and baseline are the branch's.
3. **An absolute or `~` ref is unchanged.**
4. **A ref that does not resolve at the primary is a refusal.** From a worktree, the message names both the anchored
   path and the path the ref names when read from the worktree.
5. **There is one resolver.** `hooks.pre_commit`, `hooks.commit_msg`, `hooks.bypassed`, `seldon prior-art` and
   `seldon verify` all reach the ref through `prior_art.settings`, then `resolve_block`. No caller was changed.

A consequence of rule 1: a ref that names a file in the project's own repository (for example `seldon.yaml#x`) is
read at the primary checkout from a worktree, not from the branch. The corpus already behaves this way. The three
refs in use name another repository, so this never arises today.

## 3. Why not the alternatives

- **Read the worktree path first and fall back to the primary.** That would be two resolvers and an order between
  them. A ref that happened to exist beside the worktree would silently win. The test the task set fails under it
  too: `settings` from a worktree must equal `settings` from the primary.
- **Make the commit hook read the primary's config.** That fixes the hook and leaves `seldon prior-art search` and
  `verify` broken in the same worktree. SQ-022 recorded the same defect for `seldon prior-art`.
- **Absolute refs in the three referencing repositories.** That bakes one machine's layout into three committed
  files, and ADDENDUM 03 chose relative refs so that the siblings move together.

## 4. Measured after the fix

`docs/evidence/hook002/replay_gate.py` replays the fixed gate (`pre_commit`, then `commit_msg` with the commit's own
message) over every non-merge commit on main since ADDENDUM 06's commit (`f3e31e1`, 2026-10-20 11:38 -0400). It runs
in squiddy, ai-readiness-kg and arnold, each a `--shared` scratch clone, from a linked worktree inside the clone, with
HEAD at the commit's parent and the index at the commit's tree. Result: 130 commits (squiddy 99, ai-readiness-kg 27,
arnold 4), **0 findings, 0 errors**. The positive control is a design note planted in the same replay worktree with no
prior-art section. The gate refuses it with `no prior-art verdict for its current bytes`, so the replay can find a
violation. Per-commit rows: `docs/evidence/hook002/replay_2026-10-22.jsonl`. The commits the bypass let through held
nothing the gate refuses. That came down to luck, not to a control.

## 5. Prior art

### External

- `git-worktree(1)`: "Manage multiple working trees attached to the same repository"; a repository has "one main
  worktree ... and zero or more linked worktrees"; "all refs starting with refs/ are shared" and "the repository
  config file is shared across all worktrees". The repository is one thing. A path that names another repository
  beside it belongs to the repository, not to one of its working trees. ADDENDUM 06 rule 6 already applies this
  to corpus paths.
- The rest of the reference rule is TypeScript's tsconfig `extends` (paths resolve relative to the file they
  originated in), which ADDENDUM 03 adopted. This addendum does not depart from it. It fixes where "the file the
  reference originated in" sits when that file is in a worktree. The library holds ML papers and returned nothing on
  version-control working trees. Its rows for the query are unrelated (an evaluation harness and a multi-agent
  configuration). Network was out of scope, so the man page is cited from the installed git rather than fetched.
- library receipt: query "linked working trees share one repository configuration" | release library_graph_20261017_sq018_02_2026-10-17.json sha256:99984ba3da90146a73ab4e9d8ddf15687551cb2cc2659be90d16e525253ecfb5 | rows lesson:2026-02-22_arXiv_2504_09037#p35:424:4034-4181, lesson:2026-02-22_arXiv_2407_21358#p5:139:70-902

### Internal

- ADDENDUM 03 (the ref) and ADDENDUM 06 rule 6 (`corpus_anchor`) are the two rules joined here. The register line
  for AD-036 is the internal hit. squiddy's SQ-019 RESULT named the fix first: "anchor the ref as the corpus is
  anchored". `seldon/core/worktree.py` (`primary_checkout`) resolves the primary checkout the same way for the spend
  ledger (AD-034 decision 5).
- internal receipt: query "prior_art ref by reference" | repo seldon@bf75e3e9bfc0e3652a9fc18355287ccf705a521c | hits docs/decisions/REGISTER.md:9
- internal receipt: query "prior_art ref by reference" | repo squiddy@2489c7f40b67982a4b32c38349d3de3ba0f619c5 | hits none
- internal receipt: query "prior_art ref by reference" | repo ai-readiness-kg@a75400e500afb987ad89050d745c11ba9654363e | hits none
