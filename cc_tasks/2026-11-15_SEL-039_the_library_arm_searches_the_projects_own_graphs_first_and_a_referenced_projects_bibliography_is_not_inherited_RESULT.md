# SEL-039 RESULT: the library arm searches the project's own graphs first, and a consumer by reference no longer searches seldon's bibliography

**Task:** `65889134`. **Executed:** Claude Code, dispatched, worktree `fluffy-chasing-pond` (branch
`worktree-fluffy-chasing-pond`), 2026-11-15 to 16. Not merged, pushed or completed here: the dispatcher does that.
**Answers:** hazbrief-mcp's filing `bbfd478f`
(`cc_tasks/2026-11-15_filing_from_hazbrief_prior_art_search_library_arm_does_not_search_the_projects_own_corpus.md`).
**Ruling:** `docs/design/AD-036_ADDENDUM_14_the_library_arm_searches_the_projects_own_graphs_first_and_a_referenced_projects_bibliography_is_not_inherited.md`
(AD-036-R25, R26, R27; R21's statement amended).

Recall used: seldon:AD-036-R21, seldon:2026-11-11_SEL-038_a_system_written_journal_never_blocks_a_merge_and_a_held_library_release_is_read_through_squiddys_accessor_RESULT

(R21 is the rule amended: its "a receipt naming no graph is verified in the first graph listed" is why the unnamed
default stays the first LISTED graph, not the first searched. SEL-038's RESULT is what answers the filing's item 4, and
its memory notes on addendum receipts (`### Internal` subheadings, no bold rule ids in prose) shaped the addendum.)

## In plain terms

A project's library search now starts with the project's own graphs. hazbrief's three queries from the filing now
return hazbrief's own dispersion sources first (SCICHEM/SCIPUFF documentation, Hanna, Strimaitis and Chang, the Jack
Rabbit II comparisons), then the general library. seldon's bibliography is no longer searched for any project that takes
seldon's prior-art block by reference, unless the call names it. Every receipt already written still verifies,
including the 29 in hazbrief's notes and the 5 in squiddy's that name `seldon-biblio`. Nothing changes in any consumer's
`seldon.yaml`.

## Premises (checked 2026-11-15)

- the filing is on main: yes.
- hazbrief takes its prior-art settings by reference: yes (`ref: ../seldon/seldon.yaml#prior_art`).
- seldon's list names its own bibliography: yes (kept; see B).
- hazbrief has a graph of its own: yes, with a served export and a served index.

## Commits (oldest first; prior-art log and verdict record commits between them)

1. `7193207` docs: AD-036 ADDENDUM 14 and the register records (R25, R26, R27 accepted; R21 amended), pending
   numbering on main.
2. `e9aa14e` record: the addendum's prior-art verdict (PASS).
3. `c9cdc5b` feat: the code and tests (Part B).
4. This RESULT, the evidence under `docs/evidence/sel039/`.

## A. The ruling

AD-036 ADDENDUM 14 rules, in order: (1) **own** graphs, `prior_art.own_graphs` when declared (a referencing block may
set it), otherwise every `graphs/*/graph.yaml` in the project's repository whose served export is on disk; a listed
graph inside the project's own repository is an own graph; (2) **shared**: the `library.graph` list less every graph
inside the referenced project's repository; (3) another project's graph only when the call names it. A receipt's graph
resolves whether or not it is searched by default (R26), so no receipt is re-recorded. Another project's graph is
receipted `<repository>/<graph>`. `seldon verify` and `seldon go` warn on a project with a graph directory and no own
graph the arm can read (R27).

Prior art: resource selection in distributed IR (Callan 2000; Shokouhi and Si 2011), whose framing is adopted
(selection is its own step, and what it chose is stated) and whose methods (estimated per query) are not, because the
choice here is by provenance; and tsconfig `extends`, ADDENDUM 03's basis. The library arm holds nothing on resource
selection, and its receipt says so. Verify PASS (verdict `507f4d3385ab449f8292cfd08397bae8`), receipts read under
`### External` and `### Internal`; three internal receipts cite AD-036's own family and read `self_citation`, and one
(AD-013 ADDENDUM 02 line 36) cites outside it and passes.

## B. Code and tests

- `seldon/core/prior_art.py`: `Settings.own_graphs`, `own_repo`, `referenced_repo`; `OWN_GRAPHS_KEY` admitted in a
  referencing block, the definer's never inherited (`resolve_block`); `served_export_reason` and `index_reason` (through
  squiddy's own loader: `<exports_dir>/<artifact_stem>.json`, the index manifest); `library_plan` (R25's order,
  `not_searched` with each reason, `reachable` for R26); `Libraries(s, graphs=None)` (search order, `origin` own, shared
  or named, `for_graph` resolving bare and `<repository>/<graph>` names); `own_graph_notice` (R27). The receipt grammar's
  `graph` takes one optional `/`.
- `seldon/commands/prior_art.py`: `--graph` (repeatable), `origin` on each graph, `not_searched` in the output and the
  print-out. MCP `seldon_prior_art_search` gains `graphs` and prints the same. The MCP "not committed" line now says
  "the dispatcher's next pass commits them (AD-038-R1)" for `lease_held` and `dirty_before_this_run` (the filing's
  item 4).
- `seldon/commands/verify.py`: check "Prior-art own graphs" (22 checks now; `tests/test_verify_event_log.py`
  updated). `seldon/commands/go.py`: section 5.2.
- `seldon.yaml`: comment only. **`graphs/seldon-biblio` stays on the list on purpose**: a consumer's receipt naming
  `graph seldon-biblio` resolves through it (R26). Removing it would break those 34 receipts.
- `TOOL_VERSION` not bumped: matching, ranking and verdict rules are unchanged, and the grammar change only widens
  (every old receipt parses as before), as R21's own `graph` field did without a bump.

`tests/test_sel039_own_graphs_first.py`, 23 tests on a four-repository fixture (seldon the definer, squiddy's library,
hazbrief a consumer by reference with its own served graph, a third project): the consumer's search returns its own
graph's rows first, the shared library second, none from the referenced project's bibliography, and logs in its own
log; seldon's own search still returns seldon-biblio (own) and the library; receipts name their graph; receipts naming
`seldon-biblio`, `library`, none, and the own graph all verify from the consumer; naming another project's graph on the
call searches it and its receipt (`other/othergraph`) parses back and verifies; malformed and unknown names are refused;
own_graphs pins the choice and is never inherited; a name collision is refused; a listed graph in the project's own
repository is searched once as its own (squiddy's case); the R27 warning in verify and go.

Suite (full, `-n 6`, this branch's code on PYTHONPATH, 2026-11-16): **3411 passed, 7 skipped, 4 failed** in 34 min.
None of the four is this task's, and none touches the prior-art code:
- `test_pa002_release_resolve::test_rebuilding_the_served_release_reproduces_the_served_index`: the known squiddy
  library index drift (Issue dbe38fac), failing on main since SEL-009.
- `test_dispatch_parallel::test_a_killed_supervisor_...` and `::test_two_disjoint_non_exclusive_...`: timing flakes
  under load; both **pass alone** (re-run, 2 passed).
- `test_sel024_gate_record::test_fixture_a_regate_whose_gate_outlasts_lock_wait_...`: a timing assertion ("the filing
  landed mid-gate"; `gate_running_at_end` False) that also failed alone at load average 8 to 16. SEL-029 recorded it
  failing identically on main's code under load; it reads no prior-art code.

The neighbouring suites alone (prior_art, prior_art_caller, prior_art_ref, sel029, sel036, sel038, pa002, hook002,
cc_register_commits_note, disp003, go, mcp_tools, verify_event_log, sel033, sel039): 249 passed, 1 failed (pa002, as
above).

## C. Proof on the real repositories (read only)

With `project_dir` hazbrief-mcp's primary and **no write there**: the proof calls `Libraries.search`, which logs
nothing, and verification ran with its query log pointed at /tmp. hazbrief's HEAD was `8069d56e` and its tree clean
before and after. Script and full output: `docs/evidence/sel039/proof_c.py`, `proof_c.json`.

Searched: `hazbrief-corpus` (own), `library` (shared). Not searched: `seldon-biblio` ("lives in the referenced project's
repository /Users/brock/GitHub/seldon ... name it on the call to search it").

"dense gas shallow layer time dependent" (own 48 rows, release `hazbrief_corpus_graph_hb01b_61_2026-11-12.json`;
library 41):
1. [hazbrief-corpus] noaa-aloha-technical-documentation: "The steady-plumes generated by the Heavy Gas model are combined to create a time-dependent cloud ..."
2. [hazbrief-corpus] hanna-strimaitis-chang-1993-hazard-response-modeling-uncertainty-vol2: "PERFORMANCE MEASURES FOR CONCENTRATIONS FOR CONTINUOUS DENSE GAS RELEASES (BURRO, COYOTE, DESERT TORTOISE ..."
3. [hazbrief-corpus] epa-slab-users-guide-1990: "SLAB: A Time-Dependent Computer Model for the Dispersion of Heavy Gas ..."
4. [hazbrief-corpus] erg2016-anl-technical-report: "Like the passive gas dispersion model used in CASRAM, the dense gas algorithm is integral in nature ..."
5. [hazbrief-corpus] epa-rmp-oca-guidance-2009: "Dense Gas Distances to Lower Flammability Limit"

"SCIPUFF vertical resolution puff split dense" (own 49; library 43):
1. [hazbrief-corpus] epa-scipuff-overview-2000: "SCIPUFF is a time-dependent Gaussian puff model that employs second-order closure ..."
2. [hazbrief-corpus] nws-10-518: "The dispersion of a pollutant is calculated by assuming either a Gaussian or Top-Hat horizontal distribution within a puff ..."
3. [hazbrief-corpus] epa-slab-users-guide-1990: "The average puff volume concentration C(t) ..."
4. [hazbrief-corpus] scichem-scipuff-fi: "SCICHEM source/src/lib/SCIPUFFlib/SCIPUFF/inc/scipuff_fi.f90 at commit 156625ef"
5. [hazbrief-corpus] hanna-strimaitis-chang-1993-hazard-response-modeling-uncertainty-vol2: "With a transport speed greater than 1.5 m/s, a puff would pass by all receptors ..."

"Jack Rabbit chlorine model comparison" (own 47; library 41):
1. [hazbrief-corpus] mazzola-2020-jack-rabbit-ii-17-dense-gas-models-manuscript: "Results of comparisons of the predictions of 17 dense gas d[ispersion models] ..."
2. [hazbrief-corpus] hanna-2016-ae-jack-rabbit-lyme-bay: "Observed chlorine concentrations during Jack Rabbit I and Lyme Bay field experiment[s]"
3. [hazbrief-corpus] ams-2011-186566-hanna-dense-gas-poster: "Comparing results of two chlorine release field experiments - Wild Stallions an[d Jack Rabbit]"
4. [hazbrief-corpus] atsdr-tp-fluorides-hf-fluorine-2003: "Kinetic model of fluoride metabolism in the rabbit."
5. [hazbrief-corpus] atsdr-tp-chlorine-2010: "A computational fluid dynamics-physiologically based pharmacokinetic model is being developed for chlorine ..."

Nothing was missing: hazbrief-corpus has a served export and a served index the arm reads.

R26 on real receipts, same read-only form (`docs/evidence/sel039/proof_r26.py`, output `proof_r26.txt`): hazbrief's
DN-029 (2026-11-12) verifies PASS from hazbrief's own settings, its `graph library` receipt (line 216) and its `graph
seldon-biblio` receipt (line 217) both `pass`, though seldon-biblio is no longer searched for hazbrief; squiddy's DN-062
(2026-11-15) likewise PASS, `graph library` line 81 and `graph seldon-biblio` line 82 both `pass`. hazbrief's and
squiddy's trees were clean afterwards; no verdict was recorded.

Every other repository, with the branch's code (`docs/evidence/sel039/plans.txt`): seldon searches seldon-biblio (own)
then library; squiddy searches library as its own and nothing else (biblio and registry serve no export); arnold and
ai-readiness-kg search their own graph first, and both get the R27 warning, because neither own graph can answer
(arnold-evidence: squiddy refuses to load it, "the graph declares `domain.extract` and no `index.text_of_record`";
ai-readiness: "the graph declares no index"). Their searches still answer from the library, with their own graph
reported unavailable beside it. Those two are each project's own act (build or declare the index); nothing in seldon
works around them.

## D. The return, and the filing's item 4

Filed with `seldon cc return --answers hazbrief-mcp:bbfd478f` (RETURN_LINE). Item 4, what happens to query-log lines a
Desktop search leaves while another session holds the lease: they stay modified in hazbrief's primary until the next
pass that takes the lease, which commits them as the `prior_art` class (`reconcile: N prior-art line(s) ... (prior_art,
AD-038-R1)`); a merge round commits them before its fast-forward (AD-034-R19). Pinned by
`tests/test_prior_art_caller.py::test_a_held_lease_defers_the_commit_to_the_next_pass` and
`tests/test_sel038_journals_and_held_releases.py::test_a_journal_dirty_in_main_during_the_run_does_not_block_the_merge`
(query_log). Observed in hazbrief: commit `6edc2e6a` (2026-11-15 23:32), "reconcile: 2 prior-art line(s) written by
prior-art/1; committed by the standing dispatcher (prior_art, AD-038-R1)". hazbrief needs no tool for it.

## Out of scope, recorded

The library arm still returns 40 to 50 rows per graph for a query no row is about (Issue f42b75b2 part b); seen again
in C (the library's rows for these three queries are not about dispersion). Its own design.

## For hazbrief-mcp

**Title:** seldon SEL-039 landed: your library searches now start with hazbrief-corpus, and seldon's bibliography is no longer searched for you

Nothing here is urgent and nothing in it is needed for the 2026-11-20 submission.

Answers your filing `bbfd478f`. The cause was seldon's, not squiddy's and not your configuration: your `prior_art.ref`
made seldon's library list yours, and SEL-036 had put seldon's own bibliography on that list. Since SEL-039 (AD-036-R25,
R26, R27):

- A library search for hazbrief searches `hazbrief-corpus` first (it is found because it has a served export; no change
  to your seldon.yaml), then squiddy's library. `seldon-biblio` is no longer searched for you unless a call names it
  (`--graph seldon-biblio`, or the MCP tool's `graphs`). The output labels each graph `own` or `shared` and lists what
  was not searched and why.
- Every receipt already in your notes still verifies as before, including the 29 that name `graph seldon-biblio`.
  Re-record nothing.
- New receipts from `hazbrief-corpus` read `| graph hazbrief-corpus |`.
- Item 4: a Desktop search during a running task leaves its lines in `state/prior_art_queries.jsonl` modified in your
  primary. Your dispatcher's next pass that takes the lease commits them (`reconcile: ... (prior_art, AD-038-R1)`), as it
  did at `6edc2e6a` on 2026-11-15, and a merge round commits them before its fast-forward. You need no tool for it. The
  MCP reply now says so on its "not committed" line.

Steps:

1. Confirm seldon main carries SEL-039: `grep -n "def library_plan" /Users/brock/GitHub/seldon/seldon/core/prior_art.py`
   prints a line. If it prints nothing, stop and say so in your RESULT.
2. Run one library search from hazbrief, for example `seldon prior-art search --library "dense gas dispersion"`. The
   first graph printed is `graph hazbrief-corpus (own)`, the second `graph library (shared)`, and a `not searched:
   seldon-biblio` line follows. Record the first graph line in your RESULT.
3. Optional: to pin the choice instead of relying on discovery, add `own_graphs: [graphs/hazbrief-corpus]` under
   `prior_art:` in your seldon.yaml, beside `ref` and `gate.baseline` (a referencing block may set it). Only worth it if
   you add a second graph you do not want searched.
4. Run `seldon verify`. The "Prior-art own graphs" check passes. A warning there means hazbrief-corpus has lost its
   served export or index.
