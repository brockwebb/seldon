# SEL-035: a requirement is authored once, every other cell is computed, a generated block is never a second source, and a test declares what it verifies

**Status:** proposed
**Author:** Desktop session (seldon, SLD-2), 2026-11-09, from the OODA on SEL-033 (review findings 83b09573 and 1cc32488; part (a) of f42b75b2).
**Repo:** seldon (primary). hazbrief-mcp is read and copied to scratch, never written; Part F files its return. L4: commit, merge, push in seldon.
**After:** none
**Governing:** AD-013 and AD-013 ADDENDUM 01 (R1 to R3, which this task amends); AD-012 (files are projections); AD-036 (prior art; the external arm was fetched by this Desktop thread on 2026-11-09 and is carried below, because the task runs without network); AD-038-R15 (a command commits what it writes); SEL-021 (a test node is a `Script` with `test_node`). Number new rulings under AD-013.
**Model:** primary
**Spend:** est. 1.1M tokens. Basis: one addendum, one measurement on a scratch copy, a renderer change with a one-time node migration, one refusal in two commands, one AST scanner, the return. Zero model calls.
**Network:** none beyond git push.
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes (edits `seldon/core/requirements.py`, `seldon/commands/req.py`, `seldon/commands/docs.py`, `seldon/commands/verify.py`, the domain config)
**Parts:** A 0.15, B 0.15, C 0.25, D 0.15, E 0.20, F 0.10.
**Premises:**
- premise: SEL-033's requirement code is on main | check: test -f seldon/core/requirements.py
- premise: ADDENDUM 01 keeps the load source's verbatim cells on the node | check: grep -q "status_text" docs/design/AD-013_ADDENDUM_01_requirements_as_graph_content.md
- premise: ADDENDUM 01 says its external sources were not fetched | check: grep -q "were not fetched" docs/design/AD-013_ADDENDUM_01_requirements_as_graph_content.md
- premise: hazbrief's requirements file is the measurement's dataset | check: test -f /Users/brock/GitHub/hazbrief-mcp/docs/VIEW_REQUIREMENTS.md

Read the SEL-033 RESULT and AD-013 ADDENDUM 01 before Part A.

## The condition (measured 2026-11-09, hazbrief-mcp graph, after SEL-033)

1. **One fact, two places, inside the graph.** 226 `SRS_Requirement` nodes; 226 carry `status_text`, 226 carry `verified_by_text`, 161 `validated_by`, 65 `satisfied_by_text`. The same facts are also the node's `state` and its `verified_by` / `satisfies` edges. VR-001: state `verified`, `status_text` "satisfied", `verified_by_text` a test node id that is also an edge. The projection renders the text, so SEL-033's "214 rows byte-identical" shows a storage round trip, not a render from edges. Any route that moves an edge or a state without the text (a task closing, `req add`, a SEL-021 link) leaves the rendered cell stale.
2. **Two sources for one table.** AD-013-R2 says a markdown table is never the truth; the return to hazbrief (HB-146 step 1) offers "or edit the table and re-run `seldon req import`" inside the marker blocks the renderer replaces. What `seldon docs generate requirements` does to a block edited by hand before any import is not stated anywhere.
3. **The verification column is typed, then parsed.** `verified_by` edges exist because a table cell named a test in one of three text forms. 21 RTM rows name a harness, "inspection", "judged, not tested" or a bare function name, and count as unverified.
4. **Size.** `seldon/core/requirements.py` is 53 KB for "read a table, render a table". This task must end with less of it, not more.

## Prior art, fetched 2026-11-09 by the Desktop thread (cite these in Part A's `### External` as fetched, with their URLs)

All four open-source requirement tools agree on three rules, and Seldon broke each one in SEL-033:

- **Doorstop** (https://doorstop-dev.github.io/doorstop/ ; Browning and Adams, "Doorstop: Text-Based Requirements Management Using Version Control"). One item, one YAML file; the published document is generated and never edited; each item stores a `reviewed` fingerprint, a changed parent makes child links suspect, and `doorstop clear` accepts them after review. Lesson: one authored record per requirement; a view is output only.
- **OpenFastTrace** (https://github.com/itsallcode/openfasttrace/blob/main/doc/user_guide.md). The specification item is authored in Markdown; coverage is declared by a tag in the covering artifact (source or test), and the tracer computes each item's status (covered, uncovered, covered outdated, orphaned). Nobody types "covered" or a test name into the requirement. Lesson: the covering artifact declares the link; status is computed.
- **StrictDoc** (https://strictdoc.readthedocs.io/en/stable/). Plain-text source; HTML, ReqIF, the traceability matrix and coverage screens are exports; source and test files link to requirements by markers in the code or by forward relations when the code cannot be touched; language-aware parsing binds a marker to its function. Lesson: same as OFT, plus a matrix is an export.
- **sphinx-needs** (https://sphinx-needs.readthedocs.io/en/latest/directives/needtable.html ; dynamic functions). A need is defined once; `needtable` is a filter over needs rendered at build; fields that depend on other needs are computed at build time by dynamic functions. Lesson: a table is a query, and a derived field is a function, not a stored value.
- **Cog** (https://cog.readthedocs.io/en/latest/running.html). `-c` writes a checksum beside each generated block; if the generated output was edited, the next run stops instead of overwriting; `--check` fails CI when a rerun would change the file. Lesson: the exact behaviour Part D needs, already specified.
- **Verification methods** (ISO/IEC/IEEE 15288 and 29148; INCOSE: inspection, analysis, demonstration, test; a verification cross-reference matrix carries the method per requirement). Lesson: "inspection" and "judged, not tested" are methods, not missing tests.

Not adopted as the store: each of the four keeps its truth in files and Seldon keeps it in the event log, which is the same thing one level down (AD-001). What is adopted is their shape.

## Rulings to write (Part A)

`docs/design/AD-013_ADDENDUM_02_authored_once_computed_everywhere_else.md`, with internal receipts from `seldon prior-art search` and the external list above marked fetched by Desktop with its date. `prior-art verify` passes before B to F.

- **Amend AD-013-R1.** A requirement's authored fields are: `requirement_id`, `description`, `set_by`, `document`, `section`, `verification_method` (test, inspection, analysis, demonstration; default test), `note` (free text, optional). Nothing else is stored as text. The verbatim columns (`status_text`, `verified_by_text`, `satisfied_by_text`, `validated_by`) are removed.
- **New ruling: every other cell is computed at render.** Status is the state's label (`requirements.state_labels` in seldon.yaml, default the state name) followed by the note when there is one. Verified-by is the list of `verified_by` targets. Satisfied-by is the list of `satisfies` sources. Decision is the list of `derived_from` register records. A column the graph cannot compute is not a projection column.
- **Amend AD-013-R2: one direction.** A table inside projection markers is output. `seldon req import` refuses a file that carries projection markers and names `seldon req add` / `seldon req update`; import is the onboarding route for an unmarked table and nothing else. `seldon docs generate` refuses, as Cog `-c` does, a file whose marker blocks do not hash to the revision stamped on line 1, prints the differing rows, and writes nothing; `--discard-edits` is the only override.
- **New ruling: a test declares what it verifies.** `@pytest.mark.verifies("VR-012", "VR-013")` on a test function or class. `seldon req trace` reads the project's test files with the standard library `ast` (no import, no collection), and makes `verified_by` edges to the SEL-021 test `Script` for each node id; an edge whose marker is gone is removed; a marker naming an unknown requirement is listed. `seldon verify` runs it. Edges SEL-033 imported from table cells stay until a marker replaces them; no new text grammar for test references is added, ever.
- **Verification counts follow the method.** `verify` and `docs check` report "method test, no test" separately from requirements whose method is inspection, analysis or demonstration; those reach `verified` on a `verified_by` edge to the Document, Result or Issue that records the evidence, and are listed when they have none.

## What to build

**B. Measure first, on a scratch copy** (hazbrief-mcp's repository copied to /tmp and a scratch database, as SEL-033 Part D did; dropped after). Record in the RESULT: (1) after one `seldon req add` that changes a status and one task close that adds a `satisfies` edge, how many rendered cells disagree with the graph; (2) what `seldon docs generate requirements` does to a marker block edited by hand: overwrite, refuse or merge, with the bytes; (3) the line count of `seldon/core/requirements.py` before this task. These are the before numbers; a finding that one of them is already fine narrows the Part, it does not cancel the ruling.

**C. Computed cells.** Change the renderer to the ruling; delete the verbatim-column path. One-time `seldon req migrate` (idempotent, events through the log): the remainder of `status_text` after its status word becomes `note`; a `verified_by_text` or `validated_by` that names inspection, analysis, demonstration or a judgment sets `verification_method` and keeps its words in `note`; text an edge already carries is dropped; text no edge carries and no rule places is listed per row and kept in `note`, never dropped. Then remove the four properties.

**D. One direction.** The two refusals above, `seldon req update <id>` for the authored fields, tests first: a hand-edited block is refused with its rows and survives byte for byte; `--discard-edits` regenerates; a marked file refuses import; an unmarked one still imports.

**E. Declared coverage.** `seldon req trace` and its `verify` hook as ruled; the marker is registered for the consumer by `seldon project new` and documented for an existing one (a `markers` line in its pytest config). Tests: function and class markers, a parametrized test, a removed marker, an unknown id, a file that does not parse (listed, not fatal).

**F. Proof and return.** On the scratch copy: migrate, trace, generate. Record every cell that differs from hazbrief's committed files, classed as (a) a cell now computed that said the same thing, (b) a cell that was stale or wrong, (c) wording lost. Class (c) must be empty or the migration is not done. Record the Part B numbers again as the after numbers, and the line count of `requirements.py`; if it grew, say why. Then `seldon cc return --to hazbrief-mcp`: what changed in how a requirement is edited (graph, never the table), the three commands in order (`seldon req migrate`, `seldon req trace`, `seldon docs generate requirements` then `rtm`), `state_labels` for its own vocabulary, the marker, and that its `tests/test_view_requirements.py` and its `rtm.md` export are hazbrief's to adjust. Do not write to hazbrief's repository or graph.

Update Issues 83b09573 and 1cc32488 with `remediated_by` this task and `verified_by` the tests that hold each fix (SEL-021). Leave f42b75b2 open: this file answers its part (a) by carrying fetched sources; its part (b), the gate passing on receipts no ruling cites, is its own task.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 1.4M.

## Deliverables

A to F with tests; the amended and new rulings; before and after numbers; the return filed in hazbrief-mcp; `cc_tasks/2026-11-09_SEL-035_a_requirement_is_authored_once_every_other_cell_is_computed_and_a_generated_block_is_never_a_second_source_RESULT.md`.
