# PL-011: AST-Based Code Graph Analysis

**Status:** Parked  
**Date:** 2026-02-26  
**Trigger:** After Tier 2 result registry proves the file-level traceability pattern works

---

## What

Tree-sitter AST parsing of project source files into function/class/module-level artifacts within Seldon's graph. Enables function-level provenance chains instead of stopping at file-level.

## Why

Current Seldon design tracks Scripts as opaque artifacts: "this script generated this result." It doesn't look inside. With AST parsing, Seldon knows that `compute_similarity()` calls `load_embeddings()` which depends on `data/vectors.pkl`. Staleness propagation follows the actual call chain, not just file-level relationships.

This is AD-006 (Result Registry) done properly — provenance goes all the way down to function granularity.

## Four-Pass Ingestion Pattern

From GitNexus (https://github.com/abhigyanpatwari/GitNexus):

1. **Structure** → file/directory artifacts with CONTAINS relationships (Seldon already has this from ANTS)
2. **Parsing** → function/class/module artifacts extracted via Tree-sitter AST
3. **Import resolution** → IMPORTS/DEPENDS_ON relationships between code artifacts
4. **Call graph** → CALLS relationships with confidence scoring, line-number provenance

## Reference Implementation

**GitNexus** — client-side knowledge graph creator for codebases. MIT licensed, 123 stars.
- Repo: https://github.com/abhigyanpatwari/GitNexus
- Tech: Tree-sitter WASM parsers, KuzuDB, D3.js visualization, LangChain ReAct agents
- Languages supported: TypeScript, JavaScript, Python
- Relevant patterns: four-pass pipeline, LRU AST cache, parallel Web Worker processing, Cypher query generation for graph RAG
- **Not directly reusable** — browser-only architecture. The parsing pattern and Tree-sitter usage are what matter, not the wrapper.

## What to Adopt

- **Tree-sitter** for AST parsing (already supports Python, TS, JS — the languages in play)
- **Four-pass pipeline pattern** adapted to Seldon's CLI and event-sourced architecture
- **Confidence scoring on CALLS relationships** (exact match vs fuzzy match vs heuristic)

## What NOT to Do

- Don't adopt the browser/WASM architecture — Seldon is CLI + event-sourced JSONL
- Don't build this before file-level traceability is proven
- Don't speculate on languages beyond what's actually in use (Python first, others when needed)

## Seldon Integration Sketch

New artifact types for research domain config:
- `Function`, `Class`, `Module` (children of `Script`)
- New relationships: `CALLS`, `IMPORTS`, `DEFINES`
- `Script` CONTAINS `Function[]` — existing Script artifacts gain internal structure
- `Result` generated_by `Function` (not just `Script`) — tighter provenance

---

*Parked. Paper first. File-level traceability first. This is the refinement layer.*
