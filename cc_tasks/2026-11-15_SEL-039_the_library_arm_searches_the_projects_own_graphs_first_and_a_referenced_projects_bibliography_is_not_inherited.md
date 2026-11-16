# SEL-039: the prior-art library arm searches the project's own graphs first, and a project that takes its prior-art settings by reference does not inherit the referenced project's bibliography

**Status:** proposed
**Author:** Desktop session (seldon, SLD-2), 2026-11-15. Answers hazbrief-mcp's filing `bbfd478f` (`cc_tasks/2026-11-15_filing_from_hazbrief_prior_art_search_library_arm_does_not_search_the_projects_own_corpus.md`), on the operator's ruling of 2026-11-15: "Projects may search each other's repos, but the main knowledge a project should start with is its own."
**Repo:** seldon (primary). hazbrief-mcp is read, never written; Part D files its return. L4: commit, merge, push in seldon.
**After:** none
**Governing:** AD-036 and its addenda: ADDENDUM 03 (a consumer takes the gate by reference, `prior_art.ref`), ADDENDUM 12 R21 (the library arm searches a list of graphs, each receipt naming its graph), R19 (superseded releases), R17 (filings); AD-038-R1 (the dispatcher commits system-written lines). Number the new ruling under AD-036.
**Model:** primary
**Spend:** est. 0.45M tokens. Basis: one resolution rule in `seldon/core/prior_art.py`, its tests with a two-repository fixture, one addendum, one return. Zero model calls.
**Network:** none
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes (edits `seldon/core/prior_art.py`, seldon.yaml's `prior_art` block)
**Parts:** A 0.15, B 0.45, C 0.20, D 0.20.
**Premises:**
- premise: the filing is on main | check: test -f cc_tasks/2026-11-15_filing_from_hazbrief_prior_art_search_library_arm_does_not_search_the_projects_own_corpus.md
- premise: hazbrief takes its prior-art settings by reference to seldon's | check: grep -q "ref: ../seldon/seldon.yaml#prior_art" /Users/brock/GitHub/hazbrief-mcp/seldon.yaml
- premise: seldon's list names its own bibliography | check: grep -q "graphs/seldon-biblio" seldon.yaml
- premise: hazbrief has a graph of its own | check: test -f /Users/brock/GitHub/hazbrief-mcp/graphs/hazbrief-corpus/graph.yaml

## The condition (re-measured 2026-11-15 19:40 EST, code 8bc3f89)

`seldon prior-art search "dense gas dispersion" --arm library` with `project_dir` hazbrief-mcp returned 41 rows from `graph library` and 53 from `graph seldon-biblio`: language-model papers matching "dense", the SysML fuel-tank example, a WHO dispersible-tablet test. Nothing from `graphs/hazbrief-corpus`, which holds the SCICHEM documentation and the dispersion evaluations hazbrief's tasks cite.

The cause is seldon's, in two steps:

1. hazbrief's seldon.yaml carries `prior_art.ref: ../seldon/seldon.yaml#prior_art` (ADDENDUM 03: "the corpus paths resolve from seldon's file"). So the library list a consumer searches is seldon's list. A consumer's own graph is never in it.
2. SEL-036 (this thread's task) put `graphs/seldon-biblio` on seldon's list (ADDENDUM 12 R21). By step 1 every consumer that takes the gate by reference began searching seldon's bibliography. That was not intended and nobody ruled it.

It is not squiddy's: the library arm read each graph it was pointed at correctly. It is not a hazbrief misconfiguration: hazbrief's block is the form seldon told consumers to use.

The filing's item 4 (query-log lines left uncommitted while the lease is held): SEL-038 answered the merge-round half on 2026-11-12. This task states, with a test or the existing one named, what the next pass does with such lines in a consumer, and says so in the return.

## What to build

**A. Ruling** (AD-036 addendum, receipts from `seldon prior-art search`, verify passing before the code). The library arm's graphs for a project are, in this order:
1. **Own:** the graphs in the project's own repository. Declared as `prior_art.own_graphs` in the project's seldon.yaml when present; otherwise every `graphs/*/graph.yaml` in that repository that has a served export. Searched and listed first.
2. **Shared:** the list the project declares or takes by reference, with any graph that lives inside the referenced project's repository removed (seldon-biblio is seldon's own; it is not hazbrief's).
3. **Another project's graph:** only when the call names it. No project searches another's graph by default.

A project that has a graph directory and no own graph the arm can read is reported by `seldon verify` and `seldon go` (warn, never fail), the way a missing decision register is.

**B. Code and tests.** Tests first, with a fixture of two repositories (a consumer by reference with its own served graph; the referenced project with a bibliography): the consumer's search returns its own graph's rows first, the shared library second, none from the referenced project's bibliography; seldon's own search still returns seldon-biblio (it is seldon's own) and the squiddy library; a receipt names its graph as now; every receipt already in a design note still verifies (R19, no re-recording). Naming another project's graph on the call searches it and the receipt says which.

**C. Proof on the real repositories, read only.** From a scratch copy of hazbrief-mcp (or with `project_dir` and no write: say which, and do not leave a line in hazbrief's query log), the three queries of the filing. Record the first five rows of each and which graph they came from. If hazbrief-corpus cannot be read by the arm (no served export, a held release, an older export schema), say exactly what is missing; do not work around it.

**D. Return.** `seldon cc return --to hazbrief-mcp`: what changed (its own corpus is searched first with no change to its seldon.yaml; seldon's bibliography is gone from its results), what a Desktop search during a running task leaves behind and what commits it, and the one optional step (declaring `prior_art.own_graphs` to pin the choice). Nothing in it is urgent for hazbrief's 2026-11-20 submission; say so in the return's first line.

## Out of scope, recorded

The same measurement shows the library arm returning about 40 to 50 rows per graph for a query no row is about, so a library search can never come back `hits none`. That is Issue f42b75b2 part (b) and gets its own design.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.55M.

## Deliverables

A to D with tests; the ruling; the filing answered; `cc_tasks/2026-11-15_SEL-039_the_library_arm_searches_the_projects_own_graphs_first_and_a_referenced_projects_bibliography_is_not_inherited_RESULT.md`.
