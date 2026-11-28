# AD-036 ADDENDUM 17: a portfolio list not on this machine narrows the search and says so, and a checkout's hooks are judged by its own configuration

**Date:** 2026-11-28. **Status:** Accepted. Implemented by SEL-063 Part B
(`cc_tasks/2026-11-28_SEL-063_recalls_selection_and_audit_configuration_that_names_one_machine_and_the_smaller_review_findings.md`),
from REVIEW-001's findings F-28 and F-32
(`docs/reviews/2026-11-28_REVIEW-001_review_4227_changed_lines_of_seldon_code_merged_since_e42c25bc/review.md`).
**Amends:** AD-036-R32 (ADDENDUM 16: the portfolio's roots) and AD-036-R31 (ADDENDUM 16: what `status` calls
installed).
**Code:** `seldon/core/prior_art.py` (`portfolio_roots`, `Settings.notes`); `seldon/commands/prior_art.py`
(`run_search`, `search_command`); `seldon/core/hooks.py` (`status`).
**Tests:** `tests/test_sel063_part_b.py`; `tests/test_sel052_prior_art_reach.py` (its missing-file case now expects the
degraded search).

## 1. Evidence

Read at this branch's base (`1c8d372`):

1. **F-28. One sibling checkout decided whether a commit could be judged.** seldon's `prior_art.internal_roots_from`
   is `../factory/seldon.yaml#portfolio.repositories`. `portfolio_roots` raised `PriorArtError` when that file was not
   on disk, and `prior_art.settings` sits on the commit-msg hook, `seldon verify` and `cc register` paths, for seldon
   and for every consumer whose block is a reference to seldon's. A clone with no `factory` beside it could not commit a
   design note. Reproduced in `tests/test_sel063_part_b.py`.
2. **F-32. R31's "installed" read the merged value.** `status` took `git config --get core.hooksPath` and its scope,
   so whether a checkout read installed rested on which scope git's precedence happened to return, and on the shared
   value being the one the Claude Code CLI rewrites to (ADDENDUM 16 §1.1), an undocumented behaviour of another tool.

## 2. Prior art

### External

- **Graceful degradation with a warning.** A configuration reader that warns on a missing optional input and carries
  on is common practice; sphinx-needs, in the library's top row below, "will emit a warning" on a missing key rather
  than stop. Adopted for R32: the portfolio list adds roots, and without it the search is the explicit roots, said so.
  A malformed reference is still refused: that is a defect in the file, not an absence on this machine.
  - library receipt: query "graceful degradation when an optional input is missing, reported not fatal" | graph seldon-biblio | release seldon_biblio_graph_20261111_sel037_2026-11-11.json sha256:076422bb8382009ff8c0105c7ae07dd9b2f2a86b7ff7fd24b4674e219c6b7b4c | rows doc_sw_sphinx_needs_2#b565:51156-51249, doc_omg_sysml_v2_1#b2819:693677-693747, doc_omg_sysml_v2_1#b3985:875493-875695, doc_omg_sysml_v2_1#b1030:391384-391720, liu2024lostmiddle#b15:2109-2589, liu2024lostmiddle#b26:7846-8015, liu2024lostmiddle#b90:30429-31273, han2017checklists#b44:17252-19839, han2017checklists#b58:22768-23011, han2017checklists#b79:33964-34500, doc_omg_kerml_1#b2676:536294-536527, doc_omg_kerml_1#b6263:915753-916303, doc_omg_kerml_1#b694:260286-260595, doc_sw_openfasttrace_ug_use_cases_understanding_and_fixing_broken_requirement_branches#b13:2445-3049, zhuge2024agentjudge#b320:87434-87685, zhuge2024agentjudge#b342:88916-89155, zhuge2024agentjudge#b84:22855-23272, arxiv_2406_14325#b179:78876-78974, arxiv_2406_14325#b22:11912-12141, arxiv_2406_14325#b107:54720-54996, zhang2026rlm#b30:11130-11454, zhang2026rlm#b31:11456-11642, zhang2026rlm#b152:69622-70172, doc_sw_openfasttrace_ug_use_cases_partial_tracing_by_responsibility#b11:1955-2061, doc_sw_openfasttrace_ug_reference_input_format_support#b15:1767-1790, li2024selfroute#b46:16000-16332, li2024selfroute#b29:9289-9925, li2024selfroute#b82:28083-28590, doc_sw_sphinx_needs_1#b1253:22966-22990, doc_who_trs1033_annex4_1#b1353:372608-373783, doc_who_trs1033_annex4_1#b1299:359972-360744, doc_who_trs1033_annex4_1#b1097:320938-321025, amodei2016concrete#b15:7075-7815, amodei2016concrete#b301:110564-110728, amodei2016concrete#b112:62379-63682, ilyas2023growing#b58:19385-19931, ilyas2023growing#b60:20707-21328, ilyas2023growing#b56:18776-19032, doc_rfc8493_1#b92:15595-15618, doc_rfc8493_1#b58:11209-11250, doc_rfc8493_1#b56:11043-11109, doc_sw_madr_1#b12:1443-1508, doc_sw_madr_1#b6:555-752, doc_sw_madr_1#b8:864-1057, ilyas2022saga#b255:88142-88349, doc_w3c_prov_o_1#b2536:181895-181998
  - library receipt: query "graceful degradation when an optional input is missing, reported not fatal" | graph library | release library_graph_20261110_sq133r_b.r1_2026-11-13.json sha256:c38db2b4106bbc762c984d545e044a60ac0a91923254ba2e4de8cf8a3964d784 | rows lesson:2026-02-22_arXiv_2404_09491#p20:369:1515-2479, lesson:2026-03-21_arXiv_2510_05381#p7:93:1097-1726, lesson:2026-03-21_arXiv_2510_05381#p6:88:1907-1960, lesson:2026-01-28_10_1007_s11135_017_0533_4#p31:475:2199-2324, lesson:2026-01-28_10_1007_s11135_017_0533_4#p33:522:473-663, lesson:2026-02-22_10_18653_v1_2023_emnlp_main_187#p12:158:1262-1596, lesson:2026-02-22_arXiv_2305_16504#p3:38:2339-2361, lesson:2026-02-22_arXiv_2305_16504#p16:289:265-1009, lesson:2026-02-22_arXiv_2601_03192#p28:688:1351-1674, lesson:2026-02-22_arXiv_2601_03192#p28:687:1019-1349, lesson:2026-02-22_arXiv_2409_12917#p5:101:197-238, lesson:2026-02-22_arXiv_2409_12917#p8:225:734-1061, lesson:2026-05-09_arXiv_2605_06161#p26:502:0-544, lesson:2026-05-09_arXiv_2605_06161#p8:151:1742-2255, lesson:2026-05-09_arXiv_2605_06161#p24:465:805-1232, lesson:2026-03-17_10_18653_v1_2025_acl_short_33#p12:200:164-495, lesson:2026-04-13_arXiv_2507_15330#p8:134:1994-2419, lesson:2026-04-13_arXiv_2507_15330#p3:49:4344-4694, lesson:2026-04-13_arXiv_2507_15330#p3:40:1177-1349, lesson:2026-02-22_arXiv_2310_15127#p5:25:444-1742, lesson:2026-02-22_arXiv_2508_02621#p27:575:1309-1417, lesson:2026-02-22_arXiv_2508_02621#p27:576:1419-1546, lesson:2026-02-22_arXiv_2508_02621#p26:558:2894-3049, dynsteer2026#p6:114:706-727, dynsteer2026#p6:109:224-269, dynsteer2026#p20:413:1906-2511, lesson:2026-02-22_arXiv_2508_15144#p22:473:3075-3792, lesson:2026-02-22_arXiv_2508_15144#p14:338:2967-3913, lesson:2026-02-22_arXiv_2507_21035#p47:758:1070-1682, lesson:2026-02-22_arXiv_2507_21035#p48:781:2831-3099, lesson:2026-02-22_arXiv_2507_21035#p34:545:0-47, lesson:2026-02-22_arXiv_2510_04618#p20:299:667-1276, lesson:2026-05-09_arXiv_2604_01707#p23:746:6037-6223, lesson:2026-02-22_arXiv_2407_01476#p19:297:2485-3381, lesson:2026-03-22_arXiv_2512_12818#p27:453:1207-1523, lesson:2026-04-07_arXiv_2502_04134#p8:81:18-235
- **git's per-worktree configuration** (git-worktree(1), CONFIGURATION FILE; git-config(1) `--worktree`), as ADDENDUM
  16 cites it: with `extensions.worktreeConfig` on, `config.worktree` is read after the shared config and wins. R31 as
  amended judges a checkout by that file alone, so another tool's write to the shared value cannot make a pointed
  checkout read not installed.

### Internal

- internal receipt: query "internal_roots_from portfolio repositories" | repo seldon@f8eb569dc148027761a8d6658e32a0d280bfca3c | hits docs/decisions/register/00394_seldon-ad-036-r32_accept.yaml:1, docs/design/AD-036_ADDENDUM_16_the_commit_hooks_path_survives_the_cli_worktree_step_the_search_reads_every_registered_repository_and_a_return_never_waits_on_a_filing.md:66, docs/decisions/REGISTER.md:9
- internal receipt: query "internal_roots_from portfolio repositories" | repo squiddy@c8b6b5e0de7337063791aeb6f7bed7fc78c71c16 | hits none
- internal receipt: query "internal_roots_from portfolio repositories" | repo ai-readiness-kg@f3ef4a311c8b10d6c4f7c28ced718302ae2cf6c1 | hits none
- internal receipt: query "internal_roots_from portfolio repositories" | repo arnold@8c491f6c98586894787f5727560bf37a9d08c2fc | hits none
- internal receipt: query "internal_roots_from portfolio repositories" | repo icsp_notebook@619179538d53afa65a6390b3feda17d7c30061aa | hits none
- internal receipt: query "internal_roots_from portfolio repositories" | repo wintermute@2a78c392f4d998227d2433338ea45aee82c67f1e | hits none
- internal receipt: query "internal_roots_from portfolio repositories" | repo workbench-audit@tree:c03bc86f0e4d7087c6f9cc417ee42ef66f7bc07268d5316448b4344c744b5412 | hits none
- internal receipt: query "internal_roots_from portfolio repositories" | repo hazbrief-mcp@67694d89f564002ecd8a3d6b27f68b0b5ec330d8 | hits none
- internal receipt: query "internal_roots_from portfolio repositories" | repo aacps-ai-policy@1370530ba3433d24f15fa214505f77fc719504c5 | hits none
- internal receipt: query "internal_roots_from portfolio repositories" | repo critical-thinking-ai@0723ead6e21d3e0c66796aef90855ac1be63124c | hits none
- internal receipt: query "internal_roots_from portfolio repositories" | repo factory@9a4f9929fc8c999562445330e1b3f7155594a4cd | hits none

What the record held: R32 and R31 (ADDENDUM 16); the per-checkout pointing of AD-034-R14. The other repositories'
receipts are `hits none`.

## 3. Rulings

- **Amends AD-036-R32: The internal arm's roots are `internal_roots` and, when `internal_roots_from` names a `{name: path}` map in another seldon.yaml, every repository that map lists which no `internal_roots` row already names or points at; `internal.default_include` carries the requirement projections, `docs/se/**` and `docs/requirements/**`. When the file `internal_roots_from` names is not on this machine, the roots are `internal_roots` alone and every search says so in its output and its log line; a reference that is malformed, or names a key the file does not hold, is refused.**
  F-28. The portfolio file is one machine's sibling checkout; its absence narrows what a search reads and does not
  make the configuration wrong. A receipt that names a repository only the portfolio adds then fails to verify as a
  root it does not know, which is the loud failure R32 already wanted for a listed repository not on disk.
- **Amends AD-036-R31: `seldon hooks install` writes the shared `core.hooksPath` as the main worktree's `.githooks`, absolute, and the checkout's own `config.worktree` as the relative `.githooks`, with `extensions.worktreeConfig` on; `seldon hooks status` calls a checkout installed by its own `config.worktree` alone, and reports a shared value other than the one install writes as an advisory, never as not installed; a checkout whose own `config.worktree` does not name `.githooks` is reported as not installed.**
  F-32. The shared value is the fallback for a worktree nobody pointed, and install still writes the CLI's fixed point
  there so the CLI's step has nothing to change. `tests/test_sel052_hook_path.py` stays the tripwire for the CLI's
  behaviour.

## 4. What this does not change

- `recall.audit.repositories_from` (the same reference, SEL-060) still refuses when the file is missing. `seldon qc
  recall-audit` is an operator's measurement across the portfolio, on no commit, verify or registration path, and its
  population is that list: without it the audit could not state its n.
- Which repositories the portfolio lists, and where (factory's file, read and never written here).
