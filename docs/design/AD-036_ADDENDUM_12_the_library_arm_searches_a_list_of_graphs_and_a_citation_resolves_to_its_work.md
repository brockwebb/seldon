# AD-036 ADDENDUM 12: the library arm searches a list of graphs, a receipt names its graph, and a governed citation resolves to the work it names

**Date:** 2026-11-09. **Status:** Accepted. Implemented by SEL-036
(`cc_tasks/2026-11-09_SEL-036_seldon_gets_a_bibliographic_graph_every_cited_source_is_a_resolved_work_with_its_metadata_and_text.md`,
Part E), on the operator's order the task records: "All those sources that we are quoting must have a citation and
added to the Seldon knowledge graph". **Amends:** AD-036-R3 (the library arm was "the squiddy library graph"; it is
now every graph `prior_art.library.graph` lists) and the receipt grammar of AD-036 section 4 (an optional
`graph <name> |`). Every receipt written before this addendum names no graph and verifies as it did. Two new rulings.
**Code:** `seldon/core/prior_art.py` (`library_graphs_of`, `Settings.library_graphs`, `Library(s, graph, name)`,
`Libraries`, `_verify_library` routing to `_verify_library_one`, the `graph` group of the receipt grammar),
`seldon/commands/prior_art.py` and `seldon/mcp_server.py` (one receipt per graph), `seldon/core/governing_commit.py`;
`seldon/core/biblio_bridge.py`; `seldon/domain/research.yaml` (`ExternalReference`, `resolves_to`).
**Tests:** `tests/test_sel036_library_graphs.py`, `tests/test_sel036_biblio_bridge.py`.

## 1. Evidence

1. **The library arm had nothing on requirements engineering.** SEL-033's two library receipts returned
   model-training rows, so AD-013 ADDENDUM 01 section 2 cited ISO/IEC/IEEE 29148, ReqIF, SysML v2, DOORS, Gotel and
   Finkelstein, Cleland-Huang and Cog by name only. squiddy's library graph holds the works cited in the operator's
   Claude conversation export; Seldon's own design notes cite works it never held.
2. **Seldon's governed graph held 72 `Citation` artifacts on 2026-11-09, none resolved** (AD-030-R6 captures a
   citation as a string in state `proposed`). SEL-036 built `graphs/seldon-biblio`, a squiddy graph of the works,
   standards and software those notes and tasks cite, each resolved to its identifier (SEL-036 RESULT).
3. **A receipt verifies against one release** (AD-036-R2, ADDENDUM 06): the rows it lists must be returned by the
   release it names. Two graphs are two releases, so a search over both cannot produce one receipt.

## 2. Prior art

### External

Federated search over several collections either merges the ranked lists into one (result merging; Reciprocal Rank
Fusion is the textbook merge, and the library holds a system that merges four parallel lists that way) or keeps each
collection's list apart. This ruling keeps them apart: a merged list has no single release a receipt can name, so it
could not be re-run (AD-036-R2). squiddy biblio's `ExternalReference` class ("the pointer a citation makes outside the
graph", squiddy DI-046) is the model for R21, and squiddy OD-4 section 3.3 is its rule: a bridge between graphs holds
identifiers and mappings, never content.

- library receipt: query "federated search across multiple collections result merging" | release library_graph_20261106_sq125_c_2026-11-06.json sha256:bbd841d3b5ab8822258c824656a1b80365d3a4707f0456ddb4f73d508a120cd3 | rows lesson:2026-03-22_arXiv_2512_12818#p11:181:64-350

### Internal

- internal receipt: query "ExternalReference pointer outside the graph" | repo squiddy@aa2feb38753e8bceb8ea0cbac8e7df82804e002a | hits docs/OD-4_identity_spine.md:193
- internal receipt: query "library receipt names the release" | repo squiddy@aa2feb38753e8bceb8ea0cbac8e7df82804e002a | hits docs/KIT_BOUNDARY.md:87
- internal receipt: query "library receipt names the release" | repo seldon@79069129e3c4ba9a059ec8199e8c2d1023739c1f | hits docs/design/AD-035_ADDENDUM_02_pinned_roles.md:42

## 3. Rulings

- **AD-036-R21. The library arm searches every graph `prior_art.library.graph` lists, each separately, and a library receipt names the graph its rows came from.**
  `library.graph` is one graph directory or a list of them; each is named by its directory's name, and two with one
  name are refused. `search --library` prints one receipt per graph that answered, each with `graph <name> |`; a
  graph that cannot answer (no served index yet) is reported beside the others and fails nothing. Verification sends
  each receipt to the graph it names; a receipt naming none goes to the first graph listed, which stays squiddy's
  library, so every receipt written before R21 verifies unchanged. A receipt naming a graph the list does not hold is
  `release_unavailable`.
- **AD-036-R22. A governed Citation resolves to the bibliographic entry its text names as a pointer: an `ExternalReference` artifact named `<graph>:<entry id>`, reached by a `resolves_to` link, carrying the entry's identifier and title and none of its content.**
  The pairs come from the map the resolver used (`graphs/seldon-biblio/intake/seeds.yaml`, `governed:`), made by
  reading each Citation's text; nothing is inferred. One Citation may resolve to several entries (a reference list on
  one line). The writer is `seldon.core.biblio_bridge.bridge`, idempotent, through the event store. `resolves_to` and
  `ExternalReference` were ADDED to the research domain because no relationship had `Citation` as its source and none
  reached outside the graph.

## 4. What this does not do

- It does not merge rows across graphs into one ranking. A reader who wants one list reads each graph's in turn.
- A `graph seldon-biblio` receipt verifies only where that graph's index is built. The index is gitignored (squiddy's
  `work`), so a checkout where the graph was never released cannot verify one; such a receipt fails
  `release_unavailable` there, naming the graph. No note carries one until the primary checkout holds a release.
- It does not verify a Citation (AD-030-R6's `proposed` to `verified` transition). A `resolves_to` link records which
  work a citation names; whether the note uses the work correctly is a reading, not a lookup.
