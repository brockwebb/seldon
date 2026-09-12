# CC Task: AD-030 governed documents ingest, Squiddy recipe plus Seldon import, with backfill

**Date:** 2026-09-12
**Project:** seldon (`/Users/brock/GitHub/seldon`), with kit changes in squiddy (`/Users/brock/GitHub/squiddy`)
**Seldon task:** dbe3d2dd
**Governing doc:** `docs/design/AD-030_governed_documents_as_graph_content.md` (the spec; this file is the execution plan)
**Mode:** L4. Each repo commits, merges to main, pushes its own changes. Close dbe3d2dd citing both hashes.
**Run after:** `cc_tasks/2026-09-12_seldon_handoff_tool.md`

## Goal

Every governed markdown file in the Seldon repo (`docs/design/`, `docs/requirements/`, `cc_tasks/`, `handoffs/`) exists in `seldon-seldon-self` as a Document node with Section, Ruling, Citation and Passage children and lexically recovered edges, ingested through a Squiddy recipe and imported through Seldon's own write path, re-run by `seldon verify --fix` on every commit. AD-030 itself is the first document registered, and the backfill counts are registered Results.

## Prerequisites

- Read both repos' `CLAUDE.md`, then AD-030 in full, then `squiddy/squiddy/{config,parse,write,ledger,project,manifest}.py` and `graphs/biblio/config.yaml` and `graphs/biblio/emit.py` as the worked example of a graph.
- Glob and read any `cc_tasks/2026-09-12_ad030_governed_docs_ingest*ADDENDUM*.md` before starting.
- Both suites green at start.

## Design assumption (decided; state it in the RESULT, do not reopen)

`squiddy/config.py` refuses any projection backend whose database starts with `seldon-` (DI-005). AD-030-R10 says Squiddy returns ledger events and Seldon consumes them. Therefore Squiddy never projects into `seldon-seldon-self`. The governed-docs graph is a Squiddy graph living inside the Seldon repo with its own ledger and NO Neo4j projection backend; Seldon imports that ledger through its own event store and projects into its own database. Two ledgers, one write path each. DI-005 stays as is.

## Part A, Squiddy repo: markdown parser (kit, generic)

A1. Add `squiddy/parse_markdown.py` producing the same intermediate as `parse.py` (plain_text, blocks with idx, kind, level, section_path, char_span; page = None): ATX headings set level and section_path; paragraphs, list items, fenced code, tables and blockquotes are blocks with kind set accordingly; YAML frontmatter becomes one block kind `frontmatter` with parsed keys carried in a `meta` field. Spans are real character offsets into plain_text. Route by manifest entry `kind` or file suffix in `parse.py` (config key under `engine.parse`, e.g. `markdown_suffixes`), never by hardcoded check inside the docling path.
A2. Tests: headings nesting, frontmatter, code fences not mis-parsed as headings, spans verified by slicing plain_text.
A3. Commit, push in squiddy. Bump the kit version in `pyproject.toml`.

## Part B, Seldon repo: the governed-docs graph

B1. Create `governed/` in the Seldon repo as a Squiddy graph: `config.yaml` (engine block complete per `_REQUIRED`; `projection.backends` empty or a NetworkX-only backend if the kit requires one entry; `policy.provenance` set for local authored documents), `schema/governed.yaml` (LinkML: Document, Section, Ruling, Citation, Passage; slots per AD-030 section 4; edge classes for the closed edge set plus CiTO-typed citation edges with a `cito_type` slot), `emit.py`, `corpus/manifest.yaml` (rendered, see B4), `ledger/events.jsonl`.
B2. `emit.py`: from the parsed blocks emit one Document (id = repo-relative path slug, `content_hash` sha256 of the file, `doc_kind` from directory), one Section per heading with stable id `<doc>#<slug-of-section-path>` and the verbatim span, one Ruling per Section or paragraph block whose text matches the deontic pattern (config list under `domain.ruling_patterns`: `^\*\*AD-\d+-R\d+\.\*\*`, `BINDING`, `\bMUST\b`, `\bnever\b`, numbered requirement forms), Citation nodes for reference-list lines and inline author-year patterns (state `proposed`), Passage nodes when a quoted span is present. Edges recovered lexically from the text: `mentions` for every `AD-\d+`, `DN-`, `S-\d+`, `T\d-\d+`, 8-hex task prefix; `extends` and `depends_on` from the header fields `Extends:` / `Depends on:`; CiTO edges from the prior-art list format used in AD-030 section 6 (`cites_as_evidence`, `uses_method_in`, `disagrees_with`, `refutes`, with `reason` when present).
B3. Manifest in the graph (AD-030-R5): governed files are cataloged as Document nodes with `manifest_state`; `corpus/manifest.yaml` is written by `manifest_projection()` from the ledger, never hand-edited. Add a gate: no content edge without an `admitted` Document.
B4. One command admits one file: `make admit ID=<doc_id>` from `governed/`, minutes end to end, extraction preview shown before append (Squiddy acceptance bar).

## Part C, Seldon repo: import, hook, registration, backfill

C1. Extend `seldon/domain/research.yaml`: artifact types Document, Section, Ruling, Citation (verification state machine `proposed -> verified`, properties `method`, `date`, `by`), Passage; relationship types `constrained_by`, `satisfies`, `supersedes`, `extends`, `depends_on`, `mentions`, `cites` with `cito_type`; bump schema version.
C2. `seldon governed sync [--all|<path>]`: reads `governed/ledger/events.jsonl`, maps Squiddy node and edge events to Seldon artifact and link events, idempotent by `content_hash` (unchanged hash = no-op; changed hash = update event, mark every edge touching the Document `suspect`, reuse the existing stale propagation). Register each governed file's ArchitecturalDecision or DesignNote node (existing types) as the same Document where one already exists: match on `path`, do not double-mint; AD-025 through AD-029 have no node today and get one.
C3. Hook: `seldon verify --fix` runs `governed sync` for governed files whose hash differs from the graph; `seldon verify --strict` fails on an unsynced governed file.
C4. `cc_register` (CLI and MCP): after registration, return Rulings matched by identifier reference or by concept overlap with the task text (config key for the overlap threshold in `seldon.yaml`), write `constrained_by` edges for them, and print them in the tool response. R9: refuse a cc_task file that references no `AD-` or `DN-` identifier when `handoff.require_design_note` is true; warn otherwise.
C5. Full-text index on Section and Passage text in Neo4j; `seldon governed search <terms>` returns doc, section id, and span.
C6. Backfill: admit AD-030 first, then every file in the four governed directories. Register Results (via `seldon result register`, names per AD-028 grammar) for: governed files admitted, Document nodes, Section nodes, Ruling nodes, Citation nodes, edges by type, suspect edges (expect 0 on first run). Include them in the RESULT file.
C7. `seldon go`: replace the file-mtime R9 check from the handoff task with the DesignNote/Document node check.
C8. Tests in Seldon: emitter over a fixture governed file (AD-030 copy) producing >= 10 Rulings and the expected `extends` edges; import idempotency; hash-change marks edges suspect; cc_register returns matched rulings; R9 refuse and warn.
C9. `seldon verify --strict`, both suites green, commit, push, `seldon cc complete cc_tasks/2026-09-12_ad030_governed_docs_ingest.md`, close dbe3d2dd with both hashes. Write `cc_tasks/2026-09-12_ad030_governed_docs_ingest_RESULT.md` with the registered Result names and values, and any AD-030 ruling that proved wrong in implementation, stated as a finding, not fixed in the AD.

## Success contract

- `seldon_query`: `MATCH (d {artifact_type:'Document', name:'AD-030'})-[:contains]->(r {artifact_type:'Ruling'}) RETURN count(r)` returns >= 10.
- Every `.md` under the four governed directories has a Document node whose `content_hash` equals its on-disk sha256.
- Edge count in `seldon-seldon-self` excluding OntologyTerm, AgentRole and Workflow edges is > 0 and registered as a Result.
- `seldon_cc_register` on a fixture task mentioning "per-set RPE" against a fixture Ruling forbidding it returns that Ruling.
- Squiddy DI-005 guard unchanged and its test still passes.

## What NOT to do

- Do not edit AD-030. Findings go in the RESULT file and as Issues.
- Do not add a Neo4j projection backend targeting any `seldon-*` database, and do not relax DI-005.
- Do not call a model in any stage. Zero model calls.
- Do not move, rename, or archive any governed file.
- Do not parse chat exports; they are a later source class.
- Do not stop on an unmerged branch in either repo.
