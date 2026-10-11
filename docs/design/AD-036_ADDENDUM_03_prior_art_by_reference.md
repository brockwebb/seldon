# AD-036 ADDENDUM 03: one prior-art definition, referenced by every repository; a verdict ledger for a project with no governed graph

**Date:** 2026-10-11. **Task:** SQ-010 Part 0 (squiddy `cc_tasks/2026-10-10_SQ-010_governed_admission_dn043.md`,
task `00682405`). **Amends:** nothing in AD-036's rulings. It records how the configuration of
AD-036-R3 and R4 reaches the other repositories, and where a verdict goes when a repository keeps no
governed graph. The mechanism is `seldon/core/prior_art.py` (`resolve_block`, `settings`,
`verdict_ledger`) and `seldon/core/hooks.py` (`verdict_text`).

## 1. The condition

PA-001 configured the gate in seldon only. `seldon prior-art verify` on squiddy's DN-043 failed
because squiddy's `seldon.yaml` had no `prior_art:` block, so no design note outside seldon was
gated, although HOOK-001 had installed the hook in every repository. A rule enforced in one
repository did not travel: the audit's pattern again.

Two things stood in the way of giving every repository the gate:

1. **Copying the block would make fourteen definitions.** The block names the machine's internal
   corpus (seven roots), the library release and the matching parameters. Fourteen copies are
   fourteen chances to disagree the first time one changes. That is the drift squiddy DI-113
   records for a vendored copy ("a VENDORED COPY, not a symlink, and it drifts"), and the reason
   the dispatcher's standing band is "a REFERENCE and never a copied number"
   (`docs/design/2026-09-15_standing_dispatcher.md`).
2. **A verdict had nowhere to go.** AD-036-R4 writes the verdict to the governed ledger. Eleven of
   the fifteen repositories with a `seldon.yaml` keep no governed graph. There `record_verdict`
   raised and the gate saw no verdicts, so once the gate reached them every new design note would
   have been refused with no way to pass.

## 2. What was built

1. **A block may be a reference.** `prior_art: {ref: <file>#<dotted.key>, gate: {baseline: ...}}`.
   It uses the `<file>#<dotted.path>` form of `dispatch.standing_band_ref`
   (`seldon.core.dispatch.resolve_standing_band`). The file is relative to the referencing
   `seldon.yaml`'s directory, and `~` is expanded. Every other repository uses:

       prior_art:
         ref: ../seldon/seldon.yaml#prior_art
         gate:
           baseline: docs/design/AD-036_baseline.txt

2. **One definition, never a copy.** A referencing block may set only `ref` and `gate.baseline`.
   - The baseline is required and is the project's own: it lists that project's grandfathered
     notes, as seldon's lists seldon's (AD-036-R4).
   - Any other key is refused, naming the key and the defining file.
   - The target must be the definition itself. A ref to a ref is refused, so the definition is
     never two hops away.
   - A malformed ref, a missing file and a missing key are each refused by name.
3. **Paths resolve by origin.** The rule is TypeScript's for tsconfig `extends`: "All relative paths
   found in the configuration file will be resolved relative to the configuration file they
   originated in." It is split by what a path names:
   - The **corpus** is the machine's, so it resolves against the defining file's directory:
     `internal_roots[].path` and `library.graph`.
   - The **project's own state** resolves against the project using the block: `log`,
     `gate.design_dir`, `gate.baseline` and `gate.verdict_ledger_without_governed`. A search run
     in squiddy logs to squiddy's `state/prior_art_queries.jsonl`, never to seldon's, so it does
     not dirty another repository's tree.
   - For a block a project defines itself (seldon) the two directories are the same, and nothing
     changes.
4. **The verdict ledger.**
   - A project with a governed graph records verdicts in its governed ledger, as before.
   - A project without one records them in `gate.verdict_ledger_without_governed`. Seldon's
     definition sets it to `state/prior_art_verdicts.jsonl`, project-relative.
   - The write path is the same either way: `squiddy.ledger.append`, hash-chained.
5. **The hook.**
   - It still judges the staged `seldon.yaml`, baseline and verdict ledger.
   - The one file it reads from disk is the defining `seldon.yaml` a ref names. That file belongs
     to another repository, whose index this commit cannot stage.
   - A verdict ledger that is untracked and not gitignored now counts only once it is staged, so
     the commit carries its own receipt (ADDENDUM 02 section 2.2). A project's fallback ledger
     starts out that way. Without this rule its first verdict passed the note unstaged and was
     never committed (a test planted exactly that, and it failed before the rule).
   - A gitignored ledger can never be committed, so its working-tree copy is read, as before.
6. **Tests:** `tests/test_prior_art_ref.py`.
   - SQ-010 Part 0 step 2 is
     `test_part0_2_a_repo_without_its_own_internal_roots_resolves_seldons`.
   - The other tests cover resolution by origin, the refused overrides, refs and chains, the
     fallback ledger, and the hook in a referencing repository (refused without a verdict, passed
     with the staged fallback verdict, read from disk when gitignored).

## 3. Prior art

### External

TypeScript's `extends` is the adopted resolution rule, quoted in section 2. Its other half, "the
configuration from the base file are loaded first, then overridden by those in the inheriting
config file", is deliberately not adopted: a referencing block may override only its baseline,
because the gate's corpus and parameters are one rule for the machine, not a default.
- web receipt: url https://www.typescriptlang.org/tsconfig/extends.html | retrieved 2026-10-11

The library holds no software-engineering source on configuration inheritance or duplication, as
DN-043 also found for its own topics. This query returned 50 rows, none of them on configuration
(the first is an LLM-evaluation paper). The receipt keeps the gap on the record:
- library receipt: query "configuration duplicated across repositories drift single source of truth" | release library_graph_20260930_m002_2026-09-30.json sha256:fc7f31737a682d1832e26ac72ebe5da75d054bd4e8564524ba1ed239a2576543 | rows lesson:2026-04-16_arXiv_2601_19934#p3:14:0-713

### Internal

The reference form, and its reason, as the dispatcher already uses them for the standing band:
- internal receipt: query "reference never a copied number" | repo seldon@d34f2e518679bb6107e638c168bd38ec4f7f0844 | hits docs/design/2026-09-15_standing_dispatcher.md:47
- internal receipt: query "reference never a copied number" | repo ai-readiness-kg@02ba7b3471291f3f3f255fcf8bd987f2d95c4821 | hits docs/design/2026-09-15_DN-006_standing_dispatcher.md:27

A copy drifts where a link does not (squiddy DI-113):
- internal receipt: query "symlink" | repo squiddy@9eb862b690b0383a3538663409a2da9bb9e80f8b | hits docs/decisions/register/00284_squiddy-di-113_accept.yaml:1

Where AD-036-R4 puts the verdict. Only seldon's register and the AD itself mention it, and no
repository records a verdict place for a project without a governed graph:
- internal receipt: query "verdict governed ledger beside the note" | repo seldon@d34f2e518679bb6107e638c168bd38ec4f7f0844 | hits docs/design/AD-036_prior_art_receipts_gate.md:95
- internal receipt: query "verdict governed ledger beside the note" | repo arnold@0eddb102a81f156593e5cee77162ac62c840c97d | hits none
- internal receipt: query "verdict governed ledger beside the note" | repo ai-readiness-kg@02ba7b3471291f3f3f255fcf8bd987f2d95c4821 | hits none
