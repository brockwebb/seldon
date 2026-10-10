# AD-036 ADDENDUM 02: the commit point of R4 is a git hook

**Date:** 2026-10-09. **Task:** HOOK-001 (`2ebfb15e`). **Amends:** nothing in AD-036's rulings. R4 says
`seldon verify` (pre-commit) refuses a design note without a passing verdict. PA-001 found that no
pre-commit hook ran anywhere, so R4's commit point was a prose rule. This addendum records why, and
how the commit point is now built. The mechanism is `seldon/core/hooks.py`.

## 1. The cause (receipts)

- `core.hooksPath` was set in each repository's own `.git/config`, never in global or system config
  (`git config --show-origin --show-scope --get-all core.hooksPath` from a neutral directory
  returns nothing).
- It was set in two repositories, both to an absolute path under `~/Documents/GitHub`:
  - seldon: `/Users/brock/Documents/GitHub/seldon/.git/hooks`. The seldon-sel004 worktree shares
    this config.
  - arnold: `/Users/brock/Documents/GitHub/arnold/.git/hooks`.
- The repositories moved to `~/GitHub` on 2026-06-19; the symlinks left in `~/Documents/GitHub`
  are dated that day.
  - Seldon's old path still resolves through its symlink, but `seldon/.git/hooks` no longer exists.
  - Arnold's old path resolves to nothing, and `arnold/.git/hooks` is gone too.
  - Every other repository with a `seldon.yaml` has its stock `.git/hooks` of samples and no
    `core.hooksPath`.
- So in no repository did any hook run, including arnold's ADR-012 closure hooks
  (`post-commit`, `post-merge`). `scripts/seldon/install_hooks.sh` had copied those into
  `.git/hooks`, which git does not track, and they were lost in the move.
- Which tool wrote the absolute `core.hooksPath` is not recoverable. Git does not version config.
  An internal search for `hooksPath` over the declared corpus returns nothing (receipts below), and
  no handoff records the move.
- AD-030-R3 assumed a hook: "`seldon verify --fix` (already pre-commit)". Nothing on disk backed
  that.

## 2. What was built

1. **`seldon hooks install`** sets `core.hooksPath` to the relative path `.githooks`, in the
   repository's own config only (`--local`), and records the interpreter as `seldon.python` in
   the same config. It writes `.githooks/pre-commit` when the file is absent. That file is
   tracked, and the caller commits it. Install refuses to overwrite a different `pre-commit`.
   - git resolves a relative hooks path against the directory where hooks run, the top of the
     working tree, so each checkout and each worktree runs the hook it carries. A clone or move
     cannot leave a dead absolute path again.
   - The interpreter lives in local config, because it is machine state and a launchd-started
     session may not have `seldon` on PATH.
2. **The hook judges the staged bytes.** `.githooks/pre-commit` runs `seldon hooks pre-commit`,
   which reads everything from git's index: the staged copy of each file, the staged
   `seldon.yaml`, the staged governed ledger (where verdicts live) and the staged register. An
   unstaged edit can neither pass nor fail a commit.
   - So a note's verdict has to be staged with the note. The commit then carries its own receipt.
   - pre-commit.com gets the same property by stashing unstaged changes. Reading the index
     directly leaves the working tree untouched.
3. **What the hook checks.** It runs the Tier A checks whose subject is a staged governed file and
   which the index alone can decide:
   - **Prior art (R4).** Every staged gated note outside the baseline needs a passing verdict for
     its staged bytes.
   - **Decision register.** Three checks, on staged notes added after the register's baseline and
     on the staged register:
     - `ruling_label_unparsed` (section 6.1);
     - every label has a record in the staged register (AD-033-R2);
     - when register files are staged, the staged register's chain verifies.
4. **What the hook does not check.** These stay with `seldon verify --strict`, because each is
   graph-wide, needs Neo4j, or runs another repository's pipeline (AD-030-R10):
   - File hashes, Ontology, References, Unregistered files, Binding constraints;
   - Glossary, which checks paper sections, not governed files;
   - Governed docs.
   - Governed-doc ingest is excluded for one more reason. It is blocked by the stale governed pin
     (Issue `25da4d06`). Gating commits on it would refuse every `cc_tasks/` commit in seldon,
     including the dispatcher's own registration commits.
5. **A judgment that cannot be made refuses.** An unreadable index, a malformed config or a
   missing interpreter refuses the commit and names the cause. `git commit --no-verify` is the one
   way past (githooks(5)).
6. **The bypass audit.** `seldon verify` gains a "Commit hook" check. It has two findings:
   - **Not installed.** git will not run the tracked hook in this checkout. `--fix` installs it.
   - **`hook_bypassed`.** A non-merge commit, at or after the commit that added
     `.githooks/pre-commit`, carried gated design-note bytes with no passing verdict in the
     ledger at `HEAD`.
     - A bypass whose note passes now is reported as a healed warning.
     - Merge commits are not walked, because their commits were judged on their branch.
   - The check is not Tier A. Both findings describe the checkout or its history, not the change
     in hand. Tier A is held to that line in `seldon/commands/verify.py`.
7. **The dispatcher.** `seldon dispatch once` calls `ensure_installed` before taking the lease.
   It points git at the tracked hook when the checkout's config does not. If the checkout lacks
   `.githooks/pre-commit`, it launches nothing. It never writes the hook file, because that would
   dirty the tree a dispatched session must open clean.
8. **Arnold's ADR-012 hooks** move to `.githooks/post-commit` and `.githooks/post-merge` as
   wrappers. Each wrapper runs its tracked source under `scripts/seldon/hooks/` by path, and
   `install_hooks.sh` defers to `seldon hooks install`.

## 3. Prior art

### External

- Runtime enforcement holds where instruction alone does not (bears on section 2's premise; with
  AD-036 section 2's instruction-decay rows):
- library receipt: query "hard enforcement outside the agent versus prompt instructions compliance guardrail" | release library_graph_20260930_m002_2026-09-30.json sha256:fc7f31737a682d1832e26ac72ebe5da75d054bd4e8564524ba1ed239a2576543 | rows lesson:2026-05-09_arXiv_2602_22302#p52:792:2373-2610
- The library holds no source on git hooks themselves. The query "git pre-commit hook enforcement
  continuous integration gate developers bypass" returned 48 rows, none of them about hooks; it is
  logged in `state/prior_art_queries.jsonl`. The hook semantics are cited from git's own manual:
  - a relative `core.hooksPath` is "taken as relative to the directory where the hooks are run"
    (git-config(1), git 2.50.1);
  - pre-commit "can be bypassed with the `--no-verify` option" (githooks(5)).
- web receipt: url https://git-scm.com/docs/git-config | retrieved 2026-10-09
- web receipt: url https://git-scm.com/docs/githooks | retrieved 2026-10-09
- The pre-commit framework's rule: it "only runs on the staged contents of files by temporarily
  stashing the unstaged changes", because running on unstaged changes "can lead to both
  false-positives and false-negatives". Adopted as the property. Its mechanism (stash and
  restore) was not adopted: reading the index directly leaves the working tree untouched, and it
  avoids a dependency (constitution section 8).
- web receipt: url https://pre-commit.com/ | retrieved 2026-10-09

### Internal

Arnold's ADR-012 closure hooks: version-controlled sources, copied into `.git/hooks` by an
installer. That is the copy that was lost.
- internal receipt: query "closure hooks installer" | repo arnold@220ccde29831f22f8e38fb2197a922e00a1f7d15 | hits handoffs/2026-06-10-adr-012-effect-verified-writes-and-closure-hook.md:21

AD-030-R3 and Seldon's CLAUDE.md put ingest "on the commit". AD-013 names pre-commit hooks as the
enforcement mechanism:
- internal receipt: query "ingest runs on commit" | repo seldon@b705f22c13b45ad2665ea98499b942ea1812b9ea | hits CLAUDE.md:123, docs/design/AD-030_governed_documents_as_graph_content.md:39
- internal receipt: query "pre-commit hook" | repo seldon@b705f22c13b45ad2665ea98499b942ea1812b9ea | hits docs/design/AD-013_documentation_as_traceability.md:459, docs/design/AD-030_governed_documents_as_graph_content.md:39

The setting itself is in no searched document:
- internal receipt: query "hooksPath" | repo seldon@b705f22c13b45ad2665ea98499b942ea1812b9ea | hits none
- internal receipt: query "hooksPath" | repo arnold@220ccde29831f22f8e38fb2197a922e00a1f7d15 | hits none
- internal receipt: query "hooksPath" | repo squiddy@e06f9ea179e6f29c53a9fafe36109c50925861c7 | hits none
