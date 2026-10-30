# AD-034 ADDENDUM 07: a session's link to gitignored data is clean, the worktree's hook resolves, and a task without Parts is one Part

**Date:** 2026-10-29. **Written by:** SEL-017 (`cc_tasks/2026-10-29_SEL-017_a_linked_gitignored_directory_is_clean_the_worktree_hook_resolves_and_parts_defaults_to_one.md`).
**Amends:** AD-034's merge round (the dirt check FRICTION-002 Part B gave `worktree_links`), the worktree record
(`dispatch_worktree_named`), and AD-037-R6's Parts reading on the session side. **Applies:** HOOK-001 (AD-036 ADDENDUM
02: `core.hooksPath` is the relative, tracked `.githooks`). Three new rulings, AD-034-R13 to R15.

## Evidence

- **A.** hazbrief HB-64 (`0448b253`, branch `worktree-rosy-sprouting-stroustrup`, ff38054) and HB-72 (`10aef6ce`,
  `worktree-floating-snuggling-waffle`, e86bc49) finished and ended `merge_blocked: uncommitted_changes` on
  `corpus/raw`, `graphs/hazbrief-corpus/corpus/parsed`, `graphs/hazbrief-corpus/texts` and
  `graphs/hazbrief-corpus/work`. Each session symlinked those from the primary so its tests could run (a worktree
  carries no gitignored file). hazbrief ignores each by a trailing-slash pattern (`corpus/raw/`, `graphs/*/work/`).
  git matches such a pattern only against a directory, and a symlink is not one, so `git status` lists all four.
  HB-63 merged because its one link, `.env`, is a file pattern. The round's `exclude=linked` covered only the
  dispatcher's own `worktree_links`. hazbrief declares none.
- **B.** In this worktree on 2026-10-29, `git config --show-scope --get core.hooksPath` printed
  `local /Users/brock/GitHub/seldon/.githooks`. That is the primary's absolute path, in the config every worktree
  shares, and `seldon hooks status` printed `core.hooksPath is '/Users/brock/GitHub/seldon/.githooks', not '.githooks'`.
  SEL-012's RESULT found seldon's and squiddy's shared value absolute on 2026-10-28 and set it relative. It was absolute
  again a day later, so a writer outside seldon re-points the shared value. A fix that only rewrites the shared value
  would be undone the same way.
- **C.** `seldon dispatch part-complete` refused a task with no `**Parts:**` header ("Part 'A' is not in the task's
  **Parts:** header"). Every hazbrief task registered before AD-037-R6's gate reached registration lacks the header,
  and the base file is immutable, so its session could not run the milestone station.

## Prior art

- **gitignore(5).** "If there is a separator at the end of the pattern then the pattern will only match directories,
  and paths underneath them." A symlink to a directory is a file to git, so `dir/` never matches it, and
  `git check-ignore dir/` refuses the path outright ("beyond a symbolic link"). Applied, not re-implemented. The
  question "would this path be ignored as a directory?" goes to git itself, run on a scratch work tree where the path
  is an empty directory. That tree holds the only `.gitignore` files that can bear on the path, its ancestors', and
  uses the repository's own git directory, so `info/exclude` and `core.excludesFile` are read as usual. seldon does
  no pattern matching of its own.
- **git-worktree(1), CONFIGURATION FILE; git-config(1) `--worktree`.** "By default, the repository config file is
  shared across all worktrees ... `extensions.worktreeConfig` ... each worktree has its own configuration file ...
  read after the shared one." This is the mechanism built for a setting that must differ per worktree. Adopted for B.
  The same page requires `core.worktree`, and `core.bare = true`, to be moved out of the shared config before the
  extension is turned on. When either is set, the dispatcher records a refusal and turns nothing on.
- **Earned value, the 100% rule** (PMI, *Practice Standard for Work Breakdown Structures*): the decomposition of a
  piece of work covers all of it. With no decomposition declared, the whole task is one work package carrying 100% of
  the planned value. Adopted for C. CPI is earned (1.00 at the one Part's end) over actual. Only an absent header
  defaults. A header that is present and fails to parse keeps its error, because it is the author's to fix.
- **HOOK-001 / AD-036 ADDENDUM 02** (internal, below): "a fresh worktree runs the hook its own checkout carries." This
  ruling restores that property. It was true only while the shared value was relative.

### Internal

- internal receipt: query "symlink to a gitignored directory counted dirty at merge" | repo seldon@9a535c43f22ab7272993527eeebc70c7071a014e | hits none
- internal receipt: query "symlink to a gitignored directory counted dirty at merge" | repo squiddy@87f2a1a5dd71059b8b923c2f5e4a1fba2553834e | hits none
- internal receipt: query "symlink to a gitignored directory counted dirty at merge" | repo ai-readiness-kg@d1b25c759775f3d0b978b5a7dfa938736671b00e | hits none
- internal receipt: query "symlink to a gitignored directory counted dirty at merge" | repo arnold@6114fe89226c455af64e3142bd6bee841769aeeb | hits none
- internal receipt: query "symlink to a gitignored directory counted dirty at merge" | repo icsp_notebook@97e7fb6d014acc38757928205984a30be1f131f2 | hits none
- internal receipt: query "symlink to a gitignored directory counted dirty at merge" | repo wintermute@2a78c392f4d998227d2433338ea45aee82c67f1e | hits none
- internal receipt: query "symlink to a gitignored directory counted dirty at merge" | repo workbench-audit@tree:c03bc86f0e4d7087c6f9cc417ee42ef66f7bc07268d5316448b4344c744b5412 | hits none
- internal receipt: query "worktree core.hooksPath relative" | repo seldon@9a535c43f22ab7272993527eeebc70c7071a014e | hits docs/design/AD-036_ADDENDUM_02_commit_hook.md:34
- internal receipt: query "worktree core.hooksPath relative" | repo squiddy@87f2a1a5dd71059b8b923c2f5e4a1fba2553834e | hits none
- internal receipt: query "worktree core.hooksPath relative" | repo ai-readiness-kg@d1b25c759775f3d0b978b5a7dfa938736671b00e | hits none
- internal receipt: query "worktree core.hooksPath relative" | repo arnold@6114fe89226c455af64e3142bd6bee841769aeeb | hits none
- internal receipt: query "worktree core.hooksPath relative" | repo icsp_notebook@97e7fb6d014acc38757928205984a30be1f131f2 | hits none
- internal receipt: query "worktree core.hooksPath relative" | repo wintermute@2a78c392f4d998227d2433338ea45aee82c67f1e | hits none
- internal receipt: query "worktree core.hooksPath relative" | repo workbench-audit@tree:c03bc86f0e4d7087c6f9cc417ee42ef66f7bc07268d5316448b4344c744b5412 | hits none
- internal receipt: query "task with no Parts header earned value one work package" | repo seldon@9a535c43f22ab7272993527eeebc70c7071a014e | hits none
- internal receipt: query "task with no Parts header earned value one work package" | repo squiddy@87f2a1a5dd71059b8b923c2f5e4a1fba2553834e | hits none
- internal receipt: query "task with no Parts header earned value one work package" | repo ai-readiness-kg@d1b25c759775f3d0b978b5a7dfa938736671b00e | hits none
- internal receipt: query "task with no Parts header earned value one work package" | repo arnold@6114fe89226c455af64e3142bd6bee841769aeeb | hits none
- internal receipt: query "task with no Parts header earned value one work package" | repo icsp_notebook@97e7fb6d014acc38757928205984a30be1f131f2 | hits none
- internal receipt: query "task with no Parts header earned value one work package" | repo wintermute@2a78c392f4d998227d2433338ea45aee82c67f1e | hits none
- internal receipt: query "task with no Parts header earned value one work package" | repo workbench-audit@tree:c03bc86f0e4d7087c6f9cc417ee42ef66f7bc07268d5316448b4344c744b5412 | hits none

The searches for A and C found no earlier ruling here: no repository records a symlink at an ignored path, or a
default Parts reading. The search for B returned HOOK-001's note, which is applied above.

### External

- library receipt: query "per-worktree git configuration hooks path" | release library_graph_20261017_sq018_02_2026-10-17.json sha256:99984ba3da90146a73ab4e9d8ddf15687551cb2cc2659be90d16e525253ecfb5 | rows lesson:2026-02-22_arXiv_2506_12508#p47:936:695-761, lesson:2026-02-22_arXiv_2506_12508#p47:942:965-1025, lesson:2026-02-22_arXiv_2506_12508#p5:87:1432-1463, lesson:2026-02-22_arXiv_2501_12948#p66:930:739-1001, lesson:2026-02-22_arXiv_2501_12948#p66:925:269-373, lesson:2026-02-22_arXiv_2501_12948#p66:929:541-737, lesson:2026-06-20_arXiv_2603_27277#p4:71:469-617, lesson:2026-06-20_arXiv_2603_27277#p4:88:4131-4161, lesson:2026-06-20_arXiv_2603_27277#p3:29:238-1906, lesson:2026-02-22_10_18653_v1_2025_naacl_long_36#p4:98:3163-3500, lesson:2026-02-22_10_18653_v1_2025_naacl_long_36#p3:58:2980-3048, lesson:2026-02-22_10_18653_v1_2025_naacl_long_36#p9:207:1837-3024, lesson:2026-02-22_arXiv_2505_02484#p162:2079:1238-1428, lesson:2026-02-22_arXiv_2505_02484#p162:2068:202-377, lesson:2026-02-22_arXiv_2505_02484#p162:2074:628-802, lesson:2025-07-10_github_com_get_started_getting_started_with_git#meta, lesson:2026-04-07_arXiv_2512_05411#p7:132:1350-1440, lesson:2026-04-07_arXiv_2512_05411#p7:138:2737-2830, lesson:2026-07-04_arXiv_2606_10209#p4:52:5357-5452, lesson:2026-07-04_arXiv_2606_10209#p9:124:39-63, lesson:2026-02-22_arXiv_2410_02958#p39:970:881-1266, lesson:2026-02-22_arXiv_2410_02958#p33:835:1829-1921, lesson:2026-02-22_arXiv_2410_02958#p42:1034:1318-1740, lesson:2026-02-21_arXiv_2602_07755#p1:2:1652-1656, lesson:2026-05-09_arXiv_2602_22302#p22:390:1571-1673, lesson:2026-05-09_arXiv_2602_22302#p20:363:3090-3325, lesson:2026-02-22_arXiv_2410_14684#p23:342:2894-2985, lesson:2026-02-22_arXiv_2410_14684#p2:33:666-696, lesson:2026-02-22_arXiv_2410_14684#p22:312:1391-1482, lesson:2026-04-01_arXiv_2507_09089#p19:207:627-1368, lesson:2026-04-01_arXiv_2507_09089#p48:565:1882-2041, lesson:2026-04-01_arXiv_2507_09089#p48:563:1713-1732, lesson:2026-02-22_arXiv_2403_07718#p8:113:2279-2310, lesson:2026-02-22_arXiv_2403_07718#p8:120:2891-2922, lesson:2026-02-22_arXiv_2403_07718#p8:132:3699-3730, lesson:2026-02-22_arXiv_2504_21024#p7:211:50-58, lesson:2026-03-17_arXiv_2305_17144#p13:263:538-907, lesson:2026-02-22_arXiv_2502_18449#p23:338:210-227, lesson:2026-04-07_arXiv_2601_18375#p6:82:406-498, lesson:2026-04-07_arXiv_2601_18375#p6:81:314-404, lesson:2026-04-07_arXiv_2601_18375#p6:80:225-312, lesson:2026-02-22_arXiv_2410_20285#p31:406:453-485, lesson:2026-02-22_arXiv_2410_20285#p24:321:1192-1481, lesson:2026-02-22_arXiv_2410_20285#p28:369:912-1451, lesson:2026-02-22_arXiv_2410_14052#p19:320:1173-1598, lesson:2026-02-22_arXiv_2410_14052#p4:86:3413-3663, lesson:2026-02-22_arXiv_2410_14052#p5:100:315-870

The library is a corpus of AI-research lessons. Its rows are about model training and evaluation, not git
configuration, and none bears on this note. The sources are the git manuals (`git help gitignore`,
`git help worktree`, `git help config`) and PMI's WBS practice standard.

## The rules

- **AD-034-R13. The merge round's dirt check, and every other caller of `dirty_paths`, shall count as clean an untracked symlink whose own path is ignored when its trailing slash is disregarded, or whose target is inside the primary checkout at a path the primary ignores. A directory the session made counts as clean only when it holds nothing but such links. A merged finish shall record these links as `merge.linked_by_session`. A symlink at a tracked path is a type change and still blocks.**
- **AD-034-R14. When the dispatcher names a worktree whose checkout carries `.githooks/pre-commit`, it shall turn on `extensions.worktreeConfig` and set that worktree's own `core.hooksPath` to the relative `.githooks` (`git config --worktree`). It shall never write the primary's value, and it shall record the reading on `dispatch_worktree_named.hooks_path`. The dispatcher shall refuse, and record the refusal, when the shared config sets `core.worktree` or `core.bare = true`.**
- **AD-034-R15. `seldon dispatch part-complete` and the stations shall read a task with no `**Parts:**` header as one Part, `A 1.00`, and mark `parts_defaulted` on the `part_complete` and `milestone` records. A header that is present and does not parse shall keep its error. Registration shall still refuse a new file without the header (SEL-011).**

## What this does not do

- It does not merge HB-64 or HB-72. Redriving them is hazbrief's job (HB-73 there).
- It does not rewrite the primary's shared `core.hooksPath`. `ensure_installed` still re-points it on every pass. The
  writer that makes it absolute is still unidentified. R14 makes worktrees independent of that writer, whoever it is.
- It does not point a worktree that the dispatcher did not name (an interactive `claude --worktree` session). In such
  a worktree, `seldon verify` reports the hook as before, and `seldon hooks install` there sets the shared value.
