# RESULT: AD-030 governed documents ingest, Squiddy recipe plus Seldon import, with backfill

**Date:** 2026-09-12
**Task file:** `cc_tasks/2026-09-12_ad030_governed_docs_ingest.md`
**Seldon task:** dbe3d2dd
**Governing doc:** `docs/design/AD-030_governed_documents_as_graph_content.md`
**Addenda read:** none exist. `find . -iname "*ADDENDUM*"` over both repos returned nothing.

**Commits**
- squiddy: `18637f1` (kit v0.2.0, merged as `819a290`), `07e3510` (catalog and sweep fixes, merged as `f230237`)
- seldon: see the commit that carries this file.

---

## 1. The design assumption, restated as instructed

`squiddy/config.py` refuses any projection backend whose database starts with `seldon-` (DI-005).
AD-030-R10 says Squiddy returns ledger events and Seldon consumes them. Therefore Squiddy never
projects into `seldon-seldon-self`. The governed-docs graph is a Squiddy graph living inside the
Seldon repo with its own ledger and a NetworkX-only projection; Seldon imports that ledger through
its own event store and projects into its own database. Two ledgers, one write path each. **DI-005
stays exactly as it is** — and now has a test (`squiddy/tests/test_protected_targets.py`), which it
did not before.

`seldon/core/governed.py` imports nothing from Squiddy. The coupling is a JSONL file format.

## 2. Success contract, verified

| Contract clause | Measured | Verdict |
|---|---|---|
| `MATCH (d {artifact_type:'Document', name:'AD-030'})-[:CONTAINS]->(r {artifact_type:'Ruling'}) RETURN count(r)` ≥ 10 | **13** | PASS |
| Every `.md` under the four governed directories has a Document node whose `content_hash` equals its on-disk sha256 | **97 of 97**, 0 missing, 0 mismatched | PASS |
| Edge count in `seldon-seldon-self` excluding OntologyTerm/AgentRole/Workflow edges > 0, registered as a Result | **2298**, registered as `seldon_self_graph_edges_substantive` | PASS |
| `seldon_cc_register` on a fixture task mentioning "per-set RPE" against a fixture Ruling forbidding it returns that Ruling | `test_mcp_cc_register_returns_the_matched_ruling` | PASS |
| Squiddy DI-005 guard unchanged and its test passes | Guard unchanged in what it refuses; test written (see §5, F1) | PASS |

`seldon verify --strict` exits 0. Seldon suite: **1628 passed** (1574 at start, +54). Squiddy suite:
**107 passed** (50 at start, +57).

AD-030 section 1 measured this graph on the morning of 2026-09-12: "61 relationships total, all
OntologyTerm, AgentRole, or Workflow scaffolding. Zero edges among tasks, decisions, notes, or
requirements." It now holds 2347 relationships, 2298 of them substantive.

## 3. Registered Results

All thirteen registered via `seldon result register`, names per the AD-028 grammar.

| Name | Value | Units |
|---|---|---|
| `governed_files_admitted` | 97 | files |
| `governed_document_nodes` | 97 | nodes |
| `governed_section_nodes` | 1391 | nodes |
| `governed_ruling_nodes` | 168 | nodes |
| `governed_citation_nodes` | 37 | nodes |
| `governed_passage_nodes` | 389 | nodes |
| `governed_edges_contains` | 1948 | edges |
| `governed_edges_mentions` | 284 | edges |
| `governed_edges_cites` | 37 | edges |
| `governed_edges_extends` | 7 | edges |
| `governed_edges_depends_on` | 9 | edges |
| `governed_edges_suspect` | 0 | edges |
| `seldon_self_graph_edges_substantive` | 2298 | edges |

Suspect edges are 0 on the first run, as the task predicted.

## 4. What shipped

**Part A — squiddy (kit, generic).**
`squiddy/parse_markdown.py`: markdown into the kit's `(plain_text, blocks)` intermediate, stdlib
only. `plain_text` is the file verbatim, so `plain_text[start:end] == block["text"]` for every
block and a stored span is re-derivable from the file's own bytes. `squiddy/parse.py` gained
`choose_parser`, which routes on `engine.parse.markdown_kinds` / `markdown_suffixes` **before** any
reader runs; the block is optional, so no existing graph changed. Kit version 0.1.0 → 0.2.0.

Two further kit additions the task did not name but the graph could not exist without, both
generic and both recorded here rather than smuggled: the `local_file_present` assess criterion (a
repository-owned corpus has no wider world to vouch for it) and the `local_document` acquire kind
(no network, but the same three checks in their local form: the bytes moving under the record, the
file vanishing, a file holding no document).

**Part B — `governed/`, a Squiddy graph in the Seldon repo.**
`config.yaml` (engine block complete, `projection.backends` NetworkX only, `policy.provenance:
local_authored`), `schema/governed.yaml` (LinkML: Document, Section, Ruling, Citation, Passage plus
the closed edge set and CiTO-typed citation edges), `emit.py`, `catalog_governed.py`, `Makefile`,
`reset.sh`, `corpus/manifest.yaml`. Every classification rule — ruling patterns, identifier
patterns, header fields, CiTO markers — lives in `config.yaml` under `domain:`, and **every Ruling
records which pattern matched it**, so a wrong classification is a pattern to fix rather than a
judgement to relitigate.

`make -C governed admit ID=<doc_id>` runs all 18 stages in 10.6 seconds, preview included.

**Part C — Seldon.**
`research.yaml` 0.3 → 0.4: artifact types Document, Section, Ruling, Passage; Citation gained the
verification properties `method`, `date`, `by` and `raw`; relationship types `constrained_by`,
`satisfies`, `extends`, `mentions`, with `cites` widened and given `cito_type`, `supersedes` and
`contains` widened, `depends_on` given Document → Document. State machines for the four new types.

`seldon/core/governed.py` and `seldon/commands/governed.py`: `governed sync` (idempotent by content
hash; a changed hash updates and marks every touching edge suspect), `governed search` (Neo4j
full-text index over Section, Ruling, Passage, Citation), `governed status`. `seldon verify` gained
a Tier A "Governed docs" check whose `--fix` runs the sync. `seldon cc register` and
`seldon_cc_register` return the rulings a task is constrained by, write the edges, and refuse a
task citing no `AD-`/`DN-` identifier. `seldon go`'s R9 check now takes the node form.

## 5. Findings

**F1. DI-005's guard ran below an optional import, and had no test.**
`squiddy.project.write_neo4j` checked for the neo4j driver before checking the protected-target
list, so in an environment without the `neo4j` extra a forbidden target was reported as a missing
driver — and a reader following that message would install the driver and try again. The guard now
runs first. It is unchanged in *what* it refuses. It also had no test at all; the invariant this
whole task turns on was a comment. `tests/test_protected_targets.py` now pins both checkpoints
across four protected names. Fixed, not merely reported, because the task's own success contract
asserts "its test still passes".

**F2. `squiddy catalog` dropped every candidate field outside a fixed whitelist.**
A new graph's own fields could never reach the manifest. The governed graph's `local_path` and
`doc_kind` vanished and the assess stage then correctly reported an entry that named nothing —
a failure two layers from its cause. Fixed generically (`07e3510`).

**F3. `squiddy sweep --layer` was hardcoded to `kind == "work"`.**
A graph whose only kind is `local_document` ran the layer over zero entries and reported success.
Fixed generically, with `--kinds` to narrow (`07e3510`).

**F4. AD-030-R5's four document states do not map onto the kit's stage axis one-to-one, and the
naive mapping makes the reconcile gate lie.**
`admitting` is `in_graph` in the middle of becoming true, and the kit flips the stage on the *far*
side of the append. A projection reading `admitting` as `held` is therefore compared, one stage
later, against a manifest that has already flipped, and the gate reports the ledger as lagging a
manifest it is exactly in step with. `emit.manifest_state_for` maps `admitting` and `in_graph` both
to `admitted`, and any `excluded:` disposition to `declined`. Recorded as a finding because AD-030
section 4 states the states without saying how they meet a pipeline that has an in-flight stage.

**F5. AD-030 section 4 says `mentions` is recovered "for every `AD-\d+`, `DN-`, `S-\d+`, `T\d-\d+`,
8-hex task prefix", but most of those identifiers name nothing in the governed graph.**
`DI-005` and `OD-4` are Squiddy's; an eight-hex prefix is a ResearchTask in *Seldon's* graph. Emitting
an edge for each would have produced dangling pointers and failed the kit's own dangling gate. The
resolution splits the work along the line AD-030-R10 already draws: Squiddy emits `Mentions` only
where the target resolves inside its own graph, carries every other identifier on the node as
`identifiers`, and Seldon's import resolves the rest against its own artifacts. 284 `mentions`
edges landed; 61 identifiers were abstained on and reported rather than guessed at. **This is a
departure from the letter of section 4 and is stated here rather than patched into the AD.**

**F6. "Register each governed file's ArchitecturalDecision or DesignNote node as the same Document
… do not double-mint" cannot be done literally without destroying one of the two identities.**
A Seldon artifact has a single-valued `artifact_type`. Making one node be both an
ArchitecturalDecision and a Document means overwriting that property on 27 existing nodes, which
breaks `seldon docs check`, every `artifact_type = 'ArchitecturalDecision'` query, and the
documentation-completeness accounting those nodes carry. What shipped instead: the Document node
carries `seldon_artifact_id` pointing at the existing decision record, and nothing existing is
mutated. 27 of 97 documents matched an existing node this way. No second *decision* record is
created, which is the sense of "do not double-mint" that matters; a Document is a different kind of
node (the file's structure) from a decision record (the ruling's identity).

**F7. The Result-name grammar lint scanned the governed graph's own caches.**
`tests/test_result_grammar.py` greps the repo for a second copy of the grammar string. The parse
cache and the ledger hold *verbatim copies* of `cc_tasks/` files that are already exempt, so the
lint found the same statement reproduced and called it a second authored one. The derived
directories are now exempt; the originals are still scanned under their own rules.

**F8. Citation extraction is shallower than AD-030-R6 implies, deliberately.**
37 Citation nodes over 97 documents. `looks_like_reference` admits a bullet only when it carries a
parenthesised year, a DOI, or an `et al.` — so AD-030's own prior-art entries that are bare names
("INCOSE / OMG SysML v2 …") are not citations here. A full reference parser is a project; R6 says
capture is free and verification is separate, and what is captured is what a verification step
needs to look the reference up. Reported so the number is not read as a coverage claim.

**F9. Three prose rulings in AD-030 are pattern artefacts.**
Of 13 rulings found in AD-030, ten are `AD-030-R1`…`R10`. The other three matched `never` in
ordinary prose and `BINDING` where section 4 uses the word as vocabulary rather than as a banner.
This is the designed behaviour — a Ruling records `matched_pattern`, so the fix is a pattern edit,
not a judgement — but the ruling counts in §3 include them and should be read as "text the
configured patterns classified as deontic", not as "rulings a human would recognise".

**F10. A governed file that has never been cataloged was invisible to every check.**
The hash comparison asks whether the ledger and the graph agree about a document. A file written
and never put through the ingest is in neither, so nothing disagreed about it — and AD-030-R1's
"every governed document is graph content" quietly meant "every document the ledger already knows
about". Found immediately: this RESULT file was the first one. `governed.uncataloged` enumerates
the four directories (reading the list from `governed/config.yaml`, never restating it) and the
verify check now reports files with no ledger entry. It is deliberately NOT `--fix`-able: cataloging
runs Squiddy's pipeline, and a Seldon `--fix` that silently invoked another repository's toolchain
would erase the boundary AD-030-R10 draws. The check says what to run.

**F11. AD-030-R10 says the Squiddy dependency is "pinned in `pyproject.toml`", and it is not.**
Seldon's import reads a JSONL file and imports no Squiddy module, so a hard runtime dependency
would be one Seldon never uses — and it would make Seldon un-installable wherever Squiddy is
absent, which is currently every environment Seldon's own suite runs in. The dependency is real but
it is a *build-time* one for the `governed/` graph, not a runtime one for the `seldon` package. Not
added; stated here for the AD to settle.

## 6. Scope boundaries observed

- AD-030 not edited. Every finding is in this file.
- No Neo4j projection backend targeting any `seldon-*` database; DI-005 not relaxed.
- Zero model calls in any stage.
- No governed file moved, renamed or archived.
- No chat export parsed.
- Neither repo left on an unmerged branch.
