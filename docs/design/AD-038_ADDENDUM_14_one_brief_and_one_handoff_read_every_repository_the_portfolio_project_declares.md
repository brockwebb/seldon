# AD-038 ADDENDUM 14: one brief and one handoff read every repository the portfolio project declares

**Date:** 2026-11-25. **Status:** Accepted. Implemented by SEL-044 and its ADDENDUM 01
(`cc_tasks/2026-11-21_SEL-044_one_brief_and_one_handoff_read_every_registered_repository_from_the_portfolio_project.md`),
from factory's filing `6087e4d1` (`cc_tasks/2026-11-13_filing_from_factory_the_operator_has_no_portfolio_entry_point.md`).
**Extends:** AD-038-R8 (a task may wait on a task in another project's graph, read where it lives and never written)
from one target to every repository a project lists; AD-030-R9's `seldon handoff` with a portfolio form. Reads what
AD-037-R17 (the lease's phase), R20 (a running gate's progress) and R21 (wall time) record. Four new rulings,
AD-038-R32 to R35.
**Code:** `seldon/core/portfolio.py`; `seldon/commands/go.py` (`--portfolio`); `seldon/commands/handoff.py`
(`--portfolio`); `seldon/mcp_server.py` (`seldon_go` and `seldon_handoff`, argument `portfolio`).
**Tests:** `tests/test_sel044_portfolio.py`.

## 1. Evidence

1. **The factory gathers by hand.** factory's coordinator read every other repository with one task-list call each and
   a read of each `.seldon/dispatch_last_pass.json`, on 2026-11-01, 11-02 and 11-13. On 11-13 that missed that seldon
   had built requirements as graph content four days earlier (AD-013-R1, SEL-033, SEL-035), and the factory designed
   around a gap that did not exist (filing `6087e4d1`). On 2026-11-21 the operator found a sixfold growth in seldon's
   gate time himself (seldon's filing to factory `71438cd8`).
2. **The hand-kept table is wrong in five rows and omits ten repositories.** SEL-044 Part A
   (`docs/evidence/sel044/part_a_measure.md`, measured 2026-11-25): twenty-one directories under `~/GitHub` hold a
   `seldon.yaml` (eighteen repositories; three are git worktrees of `slosh-pipe` naming its database). Every one has
   an online graph holding tasks; six dispatch. `factory/registry.md` lists nine rows, says factory and aacps-ai-policy
   have no dispatcher (both run one), says ai-readiness-kg's rescan is off (its whole dispatcher is stopped by
   `.seldon/DISPATCH_STOP`), and omits ten repositories with graphs, one with 27 open tasks.
3. **Every reading the brief needs already exists per repository.** `seldon task list` (open ResearchTasks by the
   domain's open states), `seldon dispatch status` (the pass lease with its `phase` and `gate_progress`, AD-037-R17 and
   R19), `.seldon/dispatch_last_pass.json` (the last pass's candidates and refusals), the event store (huddles,
   completions, `gate_run` and `gate_recorded` with `wall_seconds`, AD-037-R21), and the `blocked` state with its
   stored reason (AD-038-R7), which is where `ungated` and `interrupted_thrice` show. Nothing new is measured.

## 2. Prior art

### External

- **gita** ("Manage multiple git repos with sanity", pypi.org/project/gita) and **myrepos** (`mr`, myrepos.branchable.com):
  a declared list of repositories, one read run across all of them, one table with a row per repository. Found by
  search on 2026-11-21 and not read beyond their descriptions. Adopted only that shape: a declared list, a fan-out
  read, a table. Departed from: both run arbitrary commands in each repository, and this reads only.
- **Scatter-gather** (Hohpe and Woolf, *Enterprise Integration Patterns*, 2003, "Scatter-Gather"): one request sent to
  several recipients side by side, the replies aggregated into one message, a recipient that does not answer reported
  rather than waited on for ever. Named, not fetched. Adopted for the read: one reader per repository, run side by
  side, and an unreadable repository is a row with its reason.
- The library arm returned nothing on point for either query: tutorials and agent-benchmark papers.
  - library receipt: query "manage multiple git repositories status" | graph seldon-biblio | release seldon_biblio_graph_20261111_sel037_2026-11-11.json sha256:076422bb8382009ff8c0105c7ae07dd9b2f2a86b7ff7fd24b4674e219c6b7b4c | rows doc_sw_madr_1#b31:4097-4220, doc_sw_madr_1#b50:5625-5832, doc_sw_madr_1#b13:1509-1672, doc_sw_requiem_1#b62:4051-4078, arxiv_2406_14325#b67:38953-39217, arxiv_2406_14325#b123:67175-67413, doc_premis_3_0_1#b436:138804-138917, doc_premis_3_0_1#b803:371666-371734, doc_premis_3_0_1#b123:47905-48233, doc_sw_openfasttrace_ug_use_cases_tracing_the_whole_chain_in_the_same_file_system#b12:1349-1425, doc_nasa_swe_072_1#b516:90026-90157, doc_nasa_swe_072_1#b291:47119-47274, doc_nasa_swe_072_1#b561:97030-97198, nygard2011adr#b57:6448-6908, liang2026skillnet#b223:95648-95686, liang2026skillnet#b95:31683-32542, liang2026skillnet#b182:73067-73567, doc_sw_cog_1#b48:6232-6460, doc_sw_strictdoc_1#b105:2569-2575, doc_sw_sphinx_needs_2#b425:32214-32274, doc_sw_doorstop_2#b25:3492-3514, doc_sw_doorstop_2#b8:2618-2853, chen2023chatgpt#b16:7098-7936, chen2023chatgpt#b4:143-1692, chen2023chatgpt#b117:48623-49194, doc_rfc9162_1#b619:114672-114949, doc_rfc9162_1#b422:76311-76639, doc_rfc9162_1#b301:52280-52540, doc_sw_sphinx_needs_1#b711:12552-12620, doc_argondigital_verification_methods_1#b106:12725-12739, zhuge2024agentjudge#b204:56708-56868, zhuge2024agentjudge#b308:84545-85275, zhuge2024agentjudge#b66:14622-14849, browning2014doorstop#b9:548-1368, browning2014doorstop#b44:11151-12006, browning2014doorstop#b79:18742-19176, fuchss2025lissa#b181:72924-73257, fuchss2025lissa#b178:72211-72565, fuchss2025lissa#b196:77085-77327, doc_omg_sysml_v2_1#b2564:673753-673895, doc_omg_sysml_v2_1#b3976:873455-873577, doc_omg_sysml_v2_1#b3947:867766-867894

### Internal

- internal receipt: query "portfolio brief across repositories" | repo seldon@af3b7df06007e6e0c557d81c9ad65d36c4924b8d | hits handoffs/2026-11-24_desktop_sld2_final_gate_work_not_yet_on_main_and_what_the_thread_got_wrong.md:167, docs/decisions/REGISTER.md:9

What the record held: the hit is the 2026-11-24 handoff's open-task list naming the filing itself; nothing in any
repository reads more than one graph for a brief. AD-038-R8's resolver (`seldon/core/cross_project.py`) is the
nearest code: it opens another project's graph through that project's own `seldon.yaml` and writes nothing, and the
portfolio reader opens each repository the same way.

## 3. Rulings

- **AD-038-R32. A project may declare `portfolio.repositories` in its seldon.yaml, a mapping of name to path relative to its primary checkout; in such a project `seldon go --portfolio`, `seldon handoff --portfolio` and the MCP tools' `portfolio` argument read every listed repository and write nothing to any of them.**
  Each repository is opened through its own `seldon.yaml` (its graph, its domain, its dispatch block), as AD-038-R8
  opens a waits-on target. A portfolio command in a project that declares no `portfolio.repositories` refuses, naming
  the key; it does not fall back to the side-by-side directories. `go --portfolio --brief` prints the portfolio brief
  alone; `go --portfolio` puts it first in the project's own orientation. The only file written is the portfolio
  handoff, in the portfolio project.
- **AD-038-R33. A listed repository that cannot be read is listed with the reason and never dropped; a repository read in part shows what was read and names each reading that failed.**
  No path, no `seldon.yaml`, an unreadable config, a graph that refuses or a corrupt event store is each a reason in
  the repository's row, and the brief's header counts the unreadable ones. A failure in one repository's read never
  stops another's.
- **AD-038-R34. The brief's readings are each repository's own: open tasks are what its `seldon task list` shows at the same moment (the ResearchTasks in the open states of its own domain); the running task's phase is its pass lease's `phase` (AD-037-R17), `phase unknown` when the lease records none; the median gate time is over `wall_seconds` alone (AD-037-R21), printed with its n, and `no wall-clock gate records` where none carries it.**
  Per repository the brief carries open tasks by state, the running task (the pass lease's task and every held
  worktree lease) with its phase and, in `gate`, the gate's progress as `seldon dispatch status` prints it; the last
  pass with its candidates and refusals; the alarms; the tasks completed since the last portfolio handoff; the open
  filings in its graph (`task_kind: filing`); and the median gate time. The alarms are: a stop file present, a lease
  whose holder is gone, a stuck streak the dispatcher notified, a blocked task (with its stored reason, which is where
  `ungated` and `interrupted_thrice` show), an open huddle, a last pass that cannot be read, and a running gate whose
  log has not grown for `portfolio.gate_silent_after_s` (AD-037-R20: output that stopped growing is how a hung gate
  shows). One row per repository, then detail only for repositories with an alarm or a failed reading.
- **AD-038-R35. `seldon handoff --portfolio` writes one handoff in the portfolio project with a section per repository and one resume line, and the time it was generated is the start of the next brief's "completed since"; the read runs one reader per repository side by side, with no cache.**
  The handoff carries a `**Portfolio handoff:**` line with its time, and the next brief finds the newest such file.
  Before the first one, "completed since" reaches back `portfolio.first_window_days`. A cache would make the counts a
  past moment's, which R34 forbids; the read's cost is measured instead (SEL-044 Part D).

## 4. What this does not change

Each repository's own `seldon go`, `seldon handoff`, `seldon task list` and `seldon dispatch status` are unchanged. The
brief carries neither spend nor the bank: those are the factory's own (factory F-016). A repository is in the
portfolio only by being listed; `factory/registry.md` stays the factory's table, and its corrections are the
factory's to make.
