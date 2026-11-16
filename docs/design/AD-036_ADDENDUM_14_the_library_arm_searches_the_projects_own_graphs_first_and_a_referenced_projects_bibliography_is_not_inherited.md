# AD-036 ADDENDUM 14: the library arm searches the project's own graphs first, and a project that takes its prior-art settings by reference does not inherit the referenced project's bibliography

**Date:** 2026-11-15. **Status:** Accepted. Implemented by SEL-039
(`cc_tasks/2026-11-15_SEL-039_the_library_arm_searches_the_projects_own_graphs_first_and_a_referenced_projects_bibliography_is_not_inherited.md`),
answering hazbrief-mcp's filing
`cc_tasks/2026-11-15_filing_from_hazbrief_prior_art_search_library_arm_does_not_search_the_projects_own_corpus.md`
(task `bbfd478f`), on the operator's ruling of 2026-11-15: "Projects may search each other's repos, but the main
knowledge a project should start with is its own."
**Amends:** AD-036-R21 (which graphs the library arm searches, and in what order) and ADDENDUM 03 (what a project that
takes the block by reference inherits). Three new rulings, AD-036-R25, R26 and R27.
**Code:** `seldon/core/prior_art.py` (`Settings.own_graphs`, `library_plan`, `Libraries`, `own_graph_notice`);
`seldon/commands/prior_art.py` and the `seldon_prior_art_search` MCP tool (`--graph`, the plan printed);
`seldon/commands/verify.py` (`check_own_graphs`); `seldon/commands/go.py` (the notice).
**Tests:** `tests/test_sel039_own_graphs_first.py`.

## 1. Evidence

1. **hazbrief's library searches never reached hazbrief's own corpus.** On 2026-11-15, three library searches run for
   hazbrief-mcp ("dense gas shallow layer time dependent", "SCIPUFF vertical resolution puff split dense", "Jack Rabbit
   chlorine model comparison") returned 41 to 43 rows from squiddy's general library and 50 to 57 from seldon's
   bibliography, and none from `graphs/hazbrief-corpus`, which holds the SCICHEM documentation and the dispersion
   evaluations hazbrief's tasks cite (the filing, items 1 and 2). Re-measured by SEL-039 at code 8bc3f89 with "dense gas
   dispersion": 41 rows from `library`, 53 from `seldon-biblio`, none from hazbrief's graph.
2. **The cause is seldon's, in two steps.** hazbrief's block is `ref: ../seldon/seldon.yaml#prior_art`, the form
   ADDENDUM 03 told consumers to use, under which "the corpus paths resolve from seldon's file": the library list a
   consumer searches is seldon's list, and a consumer's own graph is never in it. SEL-036 then put
   `graphs/seldon-biblio` on seldon's list (AD-036-R21), so every consumer that takes the block by reference began
   searching seldon's bibliography. Nobody ruled that; it followed from the two rules together.
3. **Who is affected** (survey of every `seldon.yaml` beside seldon's, 2026-11-15, squiddy's own loader naming each
   graph's served export). Seventeen repositories take the block by reference. Five have a graph of their own with a
   served export: hazbrief-mcp (`hazbrief-corpus`), arnold (`arnold-evidence`), ai-readiness-kg (`ai-readiness`), squiddy
   (`library`; `biblio` and `registry` serve nothing) and seldon itself (`seldon-biblio`). aacps-ai-policy has a served
   graph and no `prior_art:` block.
4. **Receipts already written name both graphs.** Design notes in hazbrief-mcp carry 29 library receipts naming
   `graph seldon-biblio` and 45 naming `graph library`; squiddy's carry 5 and 7; seldon's own 3 naming `library` and 41
   naming none. A receipt naming no graph is verified in the first graph `library.graph` lists (AD-036-R21). Each of
   them must verify after this change exactly as before (AD-036-R19: no receipt is re-recorded).

## 2. Prior art

### External

- **Resource selection in distributed information retrieval.** Callan, "Distributed Information Retrieval" (2000, in
  Croft, ed., *Advances in Information Retrieval*), and Shokouhi and Si, "Federated Search" (*Foundations and Trends in
  Information Retrieval* 5(1), 2011), name the problem: given several collections, choose which to search for a query
  before searching. The field's selection methods (CORI, ReDDE) rank collections by their estimated relevance to the
  query. That is not what is needed here: the choice here is by provenance (whose corpus it is), declared in advance, not
  estimated per query, so the rule adopts the field's framing (selection is a step separate from search, and its result
  is stated) and departs from its methods. Cited by their published names; not fetched (Network: none).
- **Configuration inheritance resolves paths by origin.** TypeScript's `tsconfig.json` `extends` ("relative paths found
  in the configuration file will be resolved relative to the configuration file they originated in"), already the
  basis of ADDENDUM 03's path rule. What a referencing project inherits is the definer's RULES; a path that names the
  definer's own data still names the definer's data. That is why a graph inside the referenced repository is not the
  referencing project's.
- **The library arm's own answer** for the field's name, kept as the receipt that it holds nothing on resource selection
  (its rows are on agentic search and on retrieval in general):
- library receipt: query "distributed information retrieval resource selection federated search" | graph library | release library_graph_20261110_sq133r_b.r1_2026-11-13.json sha256:c38db2b4106bbc762c984d545e044a60ac0a91923254ba2e4de8cf8a3964d784 | rows lesson:2026-02-22_arXiv_2505_05428#p1:1:38-54, lesson:2026-02-22_arXiv_2506_18959#p3:83:525-1119
- library receipt: query "distributed information retrieval resource selection federated search" | graph seldon-biblio | release seldon_biblio_graph_20261111_sel037_2026-11-11.json sha256:076422bb8382009ff8c0105c7ae07dd9b2f2a86b7ff7fd24b4674e219c6b7b4c | rows li2024selfroute#b8:1287-1694, liu2024lostmiddle#b20:4292-5027

### Internal

- internal receipt: query "corpus paths resolve from seldon" | repo seldon@f0a970111fce9b8a1aa0aa9a0c8d5672c0a6e8f0 | hits docs/design/AD-036_ADDENDUM_03_prior_art_by_reference.md:41
- internal receipt: query "library graph list seldon-biblio" | repo seldon@f0a970111fce9b8a1aa0aa9a0c8d5672c0a6e8f0 | hits docs/design/AD-036_ADDENDUM_12_the_library_arm_searches_a_list_of_graphs_and_a_citation_resolves_to_its_work.md:48, docs/design/AD-036_ADDENDUM_12_the_library_arm_searches_a_list_of_graphs_and_a_citation_resolves_to_its_work.md:17
- internal receipt: query "own corpus first" | repo seldon@f0a970111fce9b8a1aa0aa9a0c8d5672c0a6e8f0 | hits docs/design/AD-036_ADDENDUM_03_prior_art_by_reference.md:41
- internal receipt: query "seldon-biblio" | repo seldon@f0a970111fce9b8a1aa0aa9a0c8d5672c0a6e8f0 | hits docs/design/AD-013_ADDENDUM_02_authored_once_computed_everywhere_else.md:36

ADDENDUM 03 line 41 is the rule this amends ("the corpus paths resolve from seldon's file"); ADDENDUM 12 lines 17 and 48
are AD-036-R21's list and its order. Neither considered a consumer's own graph: when ADDENDUM 03 was written no consumer
had one. These three cite this note's own family and read `self_citation` (AD-036-R14). AD-013 ADDENDUM 02 line 36 is
the receipt outside it: seldon-biblio is where seldon's own citations are entered ("Each source is an entry in
`graphs/seldon-biblio`"), which is why it is seldon's own graph and no other project's.

## 3. Rulings

- **AD-036-R25. The library arm searches a project's own graphs first, then the shared list, and never another
  project's graph by default.** For a project, the graphs are, in this order:
  1. **Own:** the graphs in the project's own repository. Declared as `prior_art.own_graphs` (a list of graph
     directories, relative to the project) when present, and a referencing block may set it, as it sets its baseline;
     otherwise every `graphs/*/graph.yaml` in the repository whose served export is on disk (squiddy's own name for
     it, `<exports_dir>/<artifact_stem>.json`), in directory-name order. A graph the shared list names that lies in
     the project's own repository is an own graph. Own graphs resolve at the primary checkout, as corpus paths do
     (ADDENDUM 06).
  2. **Shared:** the list the project declares or takes by reference (`library.graph`), with every graph that lies
     inside the referenced project's repository removed. seldon-biblio is seldon's own graph; it is not hazbrief's. A
     project's `own_graphs` is never inherited by a project that takes its block by reference.
  3. **Another project's graph:** only when the call names it (`--graph`).

  A search prints which graphs it searched, in this order, labelled own or shared, and which it did not and why (a graph
  directory with no served export; a graph the referenced project owns). An own graph and a shared graph with one
  directory name and two paths are refused as a configuration error, because a receipt names its graph by that name.
- **AD-036-R26. A receipt's graph resolves whether or not the graph is searched by default.** A receipt naming no
  graph is verified, as before, in the first graph `library.graph` lists. A receipt naming a graph is verified in that
  graph when it is any of the project's own graphs, the shared list's graphs, or a graph R25 removed from the shared
  list. So every receipt written before R25 verifies as it did, including hazbrief's and squiddy's receipts naming
  `seldon-biblio`. Another project's graph, named on a call, is named in its receipt as `<repository>/<graph>`, which
  resolves to `graphs/<graph>` in the repository of that name beside the project's primary checkout, the way the
  internal roots name siblings. The `graph` field of a receipt therefore takes one optional `/`.
- **AD-036-R27. A project with a graph directory and no own graph the arm can read is reported, never failed.** `seldon
  verify` (check "Prior-art own graphs") and `seldon go` warn when the project has a `prior_art:` block and at least
  one `graphs/*/graph.yaml`, and none of its own graphs has both a served export and a served index, naming each graph
  and what it lacks. A warning, as a missing decision register is (AD-033-R13): building a graph's index is the
  project's own act, and a failure would hold every task of a project that has not built one.

## 4. What this does not change

Receipt grammar (beyond R26's optional repository prefix), verification outcomes, the superseded-release window
(AD-036-R19), the held-release reader (AD-036-R24) and the internal arm. Item 4 of the filing, a query-log line left
uncommitted while another session holds the lease, is AD-038-R1's and AD-034-R19's: the next pass that takes the lease
commits it as the `prior_art` class (`reconcile: N prior-art line(s) ... (prior_art, AD-038-R1)`), and a merge round
commits it before its fast-forward. Pinned by `tests/test_prior_art_caller.py::test_a_held_lease_defers_the_commit_to_the_next_pass`
and `tests/test_sel038_journals_and_held_releases.py::test_a_journal_dirty_in_main_during_the_run_does_not_block_the_merge`.
The library arm returning 40 to 50 rows per graph for a query no row is about (Issue f42b75b2 part b) is out of scope.
