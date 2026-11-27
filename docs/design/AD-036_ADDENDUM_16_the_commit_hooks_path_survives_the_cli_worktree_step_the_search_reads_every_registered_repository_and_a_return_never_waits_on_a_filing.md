# AD-036 ADDENDUM 16: the commit hook's path survives the CLI's worktree step, the prior-art search reads every registered repository, and a return never waits on a filing

**Date:** 2026-11-26. **Status:** Accepted. Implemented by SEL-052 Parts A and B
(`cc_tasks/2026-11-26_SEL-052_what_factory_reported_this_week_is_answered.md`), from factory's filings of 2026-11-26
(`..._spec_check_found_components_not_at_spec.md`, `..._the_prior_art_search_does_not_read_four_registered_repositories_...md`,
`..._a_return_task_waited_on_a_filing_that_never_runs_...md`) and the factory coordinator's CTAI-008 observation.
**Amends:** HOOK-001's installation (this note's ADDENDUM 02: the relative `.githooks` in the repository's own
config) by moving the relative value to each checkout's `config.worktree`. **Extends:** the internal arm's roots
(ADDENDUM 01's list) with the portfolio's; the return writer of ADDENDUM 09 and the filing kind of ADDENDUM 10.
Four new rulings, AD-036-R31 to R34.
**Code:** `seldon/core/hooks.py` (`install`, `_point_both`, `status`); `seldon/core/prior_art.py`
(`portfolio_roots`); `seldon.yaml` (`prior_art.internal_roots_from`, `internal.default_include`);
`seldon/core/returns.py` (`latest_open`, `render`, `_complete_at_filing`); `seldon/commands/cc.py`
(`resolve_after_refs`, `after_unrunnable`).
**Tests:** `tests/test_sel052_hook_path.py`, `tests/test_sel052_prior_art_reach.py`, `tests/test_sel052_returns.py`.

## 1. Evidence

1. **The writer of the absolute `core.hooksPath` is the Claude Code CLI.** Its post-create worktree step (function
   `xTt` in the 2.1.325 bundle at `/opt/homebrew/lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe`, read
   2026-11-26) reads `core.hooksPath` from the repository's common config, resolves a relative value against the
   main checkout, and runs `git config core.hooksPath <absolute>` in the new worktree, logging "Configured worktree to
   use hooks from main repository". A plain `git config` writes the shared config (git-config(1)), so the primary's
   value became absolute on every `claude --worktree` launch, and `seldon verify` there reported the commit hook not
   installed (factory FAC-18 and FAC-21, critical-thinking-ai, 2026-11-26; seldon's own primary at this writing).
   The dispatcher's `ensure_installed` set it back on its pass, and the next launch broke it again.
2. **Four registered repositories were never searched.** seldon's `prior_art.internal_roots` named six repositories;
   factory's `portfolio.repositories` names nine. A search for "requirements elicitation" returned no factory receipt
   though factory's `docs/se/strs.md` holds 56 stakeholder needs (factory FAC-17).
3. **A return waited on a filing.** `cc return` writes a return `After:` the consumer's latest open task; on
   2026-11-24 that was squiddy's consumer filing `750348cb`, which is never a candidate, and SQ-143 sat proposed two
   days until a person removed the edge. A survey of every registered repository on 2026-11-26 (22 return files) found
   one more open: seldon's SEL-051, after the prior-art filing this task answers.
4. **A green return was blocked `ungated`.** critical-thinking-ai CTAI-008 (2026-11-27T01:00:57Z to 02:05:11Z) ended
   `merge_blocked: ungated`: the return template declared `**Parts:** A 1.00.` with no `check:`, and the project
   declares no `dispatch.gate_command`, so the Stop gate ran nothing and the merge round had no evidence.

## 2. Prior art

### External

- **git's per-worktree configuration** (git-worktree(1), CONFIGURATION FILE; git-config(1), `--worktree`): with
  `extensions.worktreeConfig` on, `$GIT_DIR/config.worktree` is read after the shared config and wins. Measured on git
  2.50.1 (2026-11-26): `git worktree add` copies the main worktree's `config.worktree` into the new worktree, so a new
  worktree resolves `.githooks` against its own top before anyone points it. Adopted for R31; it is the mechanism
  AD-034-R14 already uses for dispatched worktrees.
- **One writer per configuration value** (from the task's prior-art line, unverified as a citation): a value two
  writers disagree on is rewritten by whichever ran last. R31 does not remove the second writer, which is not
  seldon's; it makes the value seldon writes the other writer's fixed point.
- **ISO/IEC/IEEE 29148** source attribute and **traceability**: a requirement's text belongs where a search finds it.
  Named, not fetched. Adopted for R32's inclusion of the requirement projections.
- The library arm returned nothing on point (template and agent papers):
  - library receipt: query "git hooks shared configuration per worktree" | graph seldon-biblio | release seldon_biblio_graph_20261111_sel037_2026-11-11.json sha256:076422bb8382009ff8c0105c7ae07dd9b2f2a86b7ff7fd24b4674e219c6b7b4c | rows doc_sw_madr_1#b19:3113-3247, doc_sw_madr_1#b13:1509-1672, doc_sw_requiem_1#b47:3126-3230, doc_sw_strictdoc_1#b38:1231-1258, doc_sw_openfasttrace_ug_use_cases_tracing_the_whole_chain_in_the_same_file_system#b12:1349-1425, doc_sw_doorstop_2#b25:3492-3514, liang2026skillnet#b182:73067-73567, liang2026skillnet#b154:66034-66323, liang2026skillnet#b187:80946-81783, arxiv_2104_03986#b96:37512-38020, arxiv_2104_03986#b57:23011-23412, arxiv_2104_03986#b84:32986-33395, fuchss2025lissa#b145:60245-60373, fuchss2025lissa#b106:31578-32663, fuchss2025lissa#b39:11473-11889, doc_rfc9162_1#b619:114672-114949, doc_rfc9162_1#b420:75705-75927, doc_rfc9162_1#b85:16939-17105, doc_sw_cog_1#b48:6232-6460, ilyas2022saga#b83:27605-27909, ilyas2022saga#b93:31061-32001, ilyas2022saga#b87:29259-30046, arxiv_2406_14325#b69:39240-39263, arxiv_2406_14325#b109:56110-57627, arxiv_2406_14325#b67:38953-39217, doc_sw_openfasttrace_ug_product_lifecycle_product_lifecycle#b16:3225-3380, doc_sw_sphinx_needs_1#b28:499-512, doc_who_trs1033_annex4_1#b2112:554683-556430, doc_who_trs1033_annex4_1#b1222:344923-344984, doc_who_trs1033_annex4_1#b988:304745-304833, doc_sw_sphinx_needs_2#b28:496-509, doc_premis_3_0_1#b226:76254-76271, doc_premis_3_0_1#b614:277073-277830, doc_premis_3_0_1#b122:47199-47903, doc_nasa_swe_072_1#b602:101341-101525, doc_nasa_swe_072_1#b45:1598-1635, doc_nasa_swe_072_1#b570:98622-98664, torresarias2019intoto#meta, zhang2026rlm#b286:138303-138355, zhang2026rlm#b145:67163-67673, zhang2026rlm#b264:130739-131024

### Internal

- internal receipt: query "hooksPath worktree" | repo seldon@3f84b3e2a9abe09a4e83342b8689b108ed60d009 | hits docs/decisions/register/00321_seldon-ad-034-r14_accept.yaml:1, docs/design/AD-034_ADDENDUM_07_session_links_worktree_hook_default_part.md:3, docs/design/AD-034_ADDENDUM_07_session_links_worktree_hook_default_part.md:51
- internal receipt: query "requirements elicitation" | repo factory@14d5ad7405b00fc7c35f3510da953100adcde822 | hits docs/design/2026-11-26_DN-002_what_the_operator_says_is_a_need_with_a_disposition.md:102, docs/design/2026-11-26_DN-002_what_the_operator_says_is_a_need_with_a_disposition.md:95, docs/design/2026-11-26_DN-002_what_the_operator_says_is_a_need_with_a_disposition.md:91

What the record held: AD-034-R14 (SEL-017 Part B) points a dispatched worktree's own `config.worktree` at `.githooks`
because the shared value had been found absolute "written by something outside seldon"; it left the primary's value
alone. The second receipt is the first factory hit the search returns once factory is a root (it was not before).

## 3. Rulings

- **AD-036-R31. `seldon hooks install` writes the shared `core.hooksPath` as the main worktree's `.githooks`, absolute, and the checkout's own `config.worktree` as the relative `.githooks`, with `extensions.worktreeConfig` on; a relative value left in the shared config is reported as not installed.**
  The absolute shared value is the one the Claude Code CLI writes over a relative one, so its worktree step finds
  nothing to change. Every checkout seldon installs or points reads its own `config.worktree`, which wins, so each runs
  the hook its own checkout carries; a worktree no one pointed reads the copy git made at `worktree add`, or on a git
  that makes none, the absolute fallback, which runs the primary's tracked hook rather than none. The installer
  refuses a shared `core.worktree` or `core.bare = true`, as AD-034-R14's pointing does. The dispatcher's
  `ensure_installed` moves an old relative install on its next pass.
- **AD-036-R32. The internal arm's roots are `internal_roots` and, when `internal_roots_from` names a `{name: path}` map in another seldon.yaml, every repository that map lists which no `internal_roots` row already names or points at; `internal.default_include` carries the requirement projections, `docs/se/**` and `docs/requirements/**`.**
  The portfolio list (factory's `portfolio.repositories`) is the one list of registered repositories; a second copy
  here would drift as this one did. A listed repository not on disk is a root, so its receipt fails loudly. Widening
  the include re-scores nothing an old receipt rests on: verification is membership in the hits at the receipt's
  commit.
- **AD-036-R33. A task file's `After:` may not name a filing: registration refuses it as `after_unrunnable`, and the return writer's `After:` is the consumer's latest open task that can run, never a filing or a FUTURE task.**
  A filing completes only when another task's return closes it (AD-036-R17), so a wait on it is a wait on an answer
  nobody scheduled. Name the task that answers it.
- **AD-036-R34. A return carries one check, that its RESULT exists, so a consumer with no gate command can merge it; and a `For <consumer>` section whose `**Nothing to build:**` header gives a reason makes the return completed at filing, with no session.**
  The return file is still written and registered: it is the record that the answer reached the consumer, and its
  header says why nothing was built. The walk to `completed` and its event lines are recorded in the consumer as
  registration records its own. A `Nothing to build` header with no reason is refused.

## 4. What this does not decide

- Whether a return that does have work should run the consumer's long job inside the return session. CTAI-008 spent
  64 minutes of wall clock and 5.7 minutes of API time: the rest was the extraction it resumed, a re-parse (the fresh
  worktree lacks the gitignored parse intermediates) and two release cuts. The consumer section said "resume"; the
  return's default `**Spend:**` said "no model calls of its own", which was not the case. A producer that knows the
  consumer's step is a long run sets `**Spend:**` and `**Network:**` in its section, as the writer already allows.
