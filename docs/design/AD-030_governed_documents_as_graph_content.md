# AD-030: Governed Documents as Graph Content

**Date:** 2026-09-12
**Status:** Draft (Desktop design session; not yet ingested, not yet implemented)
**Extends:** AD-002 (domain-agnostic engine), AD-004 (per-project database), AD-013 (documentation as projection), AD-018 (document structure graph), AD-029 (task precedence)
**Depends on:** Squiddy (`/Users/brock/GitHub/squiddy`) as the ingest kit; identity registry (Squiddy OD-4)
**Seldon task:** dbe3d2dd
**Source thread:** Desktop design session 2026-09-12 ("Seldon New Design session"), to be cataloged as a source document when thread exports are admitted.

---

## 1. Context

AD-013 section 1 ruled on 2026-03-15 that documentation is a projection and the graph is the source. `seldon go` prints "the graph is the source of truth, files are projections of graph state" on every orient. The ruling was implemented for the paper stack (PaperSection, Result, Figure, Table, Script, DataFile) and never for the engineering artifacts that govern the system itself.

Measured state of `seldon-seldon-self` on 2026-09-12:

- 13 of approximately 28 ArchitecturalDecisions registered; AD-025 through AD-029 never registered.
- Each ArchitecturalDecision and DesignNote node carries a path and a 60 to 208 character description. No content, no sections, no rulings.
- 2 SRS_Requirement nodes for the entire system. 100 ResearchTask nodes.
- 61 relationships total, all OntologyTerm, AgentRole, or Workflow scaffolding. Zero edges among tasks, decisions, notes, or requirements.

The Arnold project graph has the same shape (180 ResearchTasks, zero edges). On 2026-09-01 a per-set RPE field, retired by a recorded ruling in `docs/ontology/intensity-constructs.md`, was reintroduced by a new task because no mechanism made the ruling addressable at task registration. Nothing was lost; nothing was bound.

Squiddy, one day old, already has `cc_tasks/`, `handoffs/`, `docs/`, and a ledger with the same shape. The pattern reproduces on day one of every repository.

## 2. Mechanism of decay

The authoring surface for the operator and for Claude Code is markdown. Every graph write was a second deliberate act (`seldon artifact create`, `seldon cc register`, `seldon link create`). Whenever writing to the graph costs more than writing to a file, the file wins and the graph decays. This is the documented failure mode of manual requirements traceability (DOORS in industrial practice): engineers author in documents, linking is a separate chore, links decay.

The field that addressed it is model-based systems engineering: the model is the single source, documents are generated views, the link set is the digital thread.

## 3. Decision

**AD-030-R1.** Every governed document is graph content. The markdown file is the serialization of a Document node; parsing it is the single write path. Governed directories: `docs/design/`, `docs/requirements/`, `cc_tasks/`, `handoffs/`, lab notebook entries.

**AD-030-R2.** Prose is authored on disk. Structure, identity, hashes, and links live in the graph. Argued prose (rationale, steps, lab entries) is never authored inside node fields; derived artifacts (RTM, impact reports, results registry, task lists, briefing context, the YAML manifest) are never authored by hand.

**AD-030-R3.** Ingest runs on commit, not on cron. `seldon verify --fix` (already pre-commit) parses governed files through the Squiddy recipe. A periodic currency sweep is the backstop for anything that bypassed the hook, never the primary path. Rationale: the defect window is the gap between a ruling being written and the next task being registered; a daily sweep leaves that window open.

**AD-030-R4.** Identity is the content hash, never the path. Governed authored documents stay in place (the path is the edit surface; relocation breaks re-sync). Source documents (PDFs, harvested pages, thread exports) are immutable, may live anywhere, and are resolved by hash. Git holds governed markdown; it does not hold source blobs. Source blobs go to a content-addressed store outside the repository (evaluate DVC and git-annex before writing a mover; both use a plain folder as a remote).

**AD-030-R5.** The manifest lives in the graph. Every document ever considered is a Document node from the moment it is cataloged, with states `cataloged -> held -> admitted | declined`. Declined nodes carry `reason`, `date`, `decided_by` and never receive content edges. The YAML manifest is rendered from these nodes and is never hand-edited. Reopening a declined document requires a new decision node with a `supersedes` edge citing new evidence. The admission invariant becomes one query: no content edge without an `admitted` Document node.

**AD-030-R6.** Citations are captured free and verified separately. Any citation appearing in a governed document becomes a Citation node at ingest in state `proposed`, with a Passage node (section or paragraph identifier, verbatim span, hash of source text) when a span was quoted. Verification is a state transition `proposed -> verified` carrying `method`, `date`, `by`. `seldon verify` reports unverified citations as it reports unregistered numbers. Gate intensity follows document type: design notes ship with `proposed` citations; `seldon paper build` refuses them at Tier 1.

**AD-030-R7.** Citation edges use the CiTO vocabulary, not an invented one. Fundamentals: `cites_as_evidence`, `uses_method_in`, `extends`. Constraint-driven prescriptions the operator rejects because the constraint no longer holds under current tooling: `disagrees_with` or `refutes`, with a `reason` property naming the constraint. Rejected science stays in the graph as a rejected prescription; reinstatement requires supersession with evidence. This is the queryable form of the artifact engineering standards section 7.5 already requires.

**AD-030-R8.** Cross-graph citation discovery goes through the Squiddy identity registry keyed by DOI and OpenAlex ID. No master bibliography. The verification record stays in the graph that performed it; the registry holds pointers.

**AD-030-R9.** A Desktop design session closes with a design note, not a task. Rulings are `##` sections carrying IDs (this document's `AD-030-Rn` pattern); citations are inline. Every CC task produced by a design session references a `DN-` or `AD-` identifier; `seldon_cc_register` checks this lexically and refuses otherwise. `seldon go` prints the obligation in the Desktop contract and, at the next orient, reports a Desktop session that registered no DesignNote.

**AD-030-R10.** Seldon depends on Squiddy; Squiddy has no knowledge of Seldon. The coupling is a stream specification, not awareness: Seldon supplies a domain schema (LinkML) and a manifest entry pointing at a file; Squiddy returns ledger events and store nodes conforming to that schema, each event stamped with the schema version. The dependency is pinned in `pyproject.toml`; CLAUDE.md names it in one line and carries no contract. The dependency graph stays acyclic. Rationale: Wintermute's ingest became a monolith when it knew its callers.

## 4. Schema (research domain extension; final form in the LinkML schema, not here)

Node types: `Document` (governed or source; manifest state), `Section` (addressable child, stable ID, verbatim span, hash), `Ruling` (a Section whose text is deontic: BINDING, MUST, never, or a numbered requirement), `Citation` (verification state), `Passage` (span in a source with hash).

Edge set (closed): `constrained_by` (task -> Ruling), `satisfies` (task or Script -> Requirement), `supersedes` (Ruling -> Ruling; decision -> decision), `extends` (AD -> AD), `mentions` (any -> any by identifier reference), CiTO-typed citation edges (Section -> Passage or Citation).

Link recovery is lexical by default: identifier references (`AD-NNN`, `S-NNN`, `T2-1`, task UUID prefixes), the `Extends:` / `Depends on:` / `Prior art:` header fields, and concept match between task text and Ruling text returned in the `cc_register` tool response. Human-authored links are the exception.

Suspect links: a hash change on either end of an edge flags the edge for review. This reuses the existing stale propagation for Results.

Full-text index on Section and Passage nodes.

## 5. What this does not do

- Does not require anyone to author in the graph.
- Does not add a rules engine. The graph is descriptive; the only gates are hash mismatch (existing), the `admitted` invariant (R5), and the design-note reference on task registration (R9).
- Does not merge Squiddy into Seldon or Seldon into Squiddy.
- Does not reorder Squiddy's consumers. The bibliographic evidence graph remains first; this recipe is its first client, and this document's citations are the first passages it admits.

## 6. Prior art (all citations in state `proposed`; verification per R6 before any publication)

- Gotel, O. and Finkelstein, A. (1994). An analysis of the requirements traceability problem. RE 1994. `cites_as_evidence` for section 2.
- Cleland-Huang, J., Gotel, O., Huffman Hayes, J., Mäder, P., Zisman, A. (2014). Software traceability: trends and future directions. FOSE 2014. `cites_as_evidence` for section 2 (trace decay and recovery).
- INCOSE / OMG SysML v2 (model as single source, generated views, digital thread). `cites_as_evidence` for R1, R2.
- DOORS and ReqIF (requirements as objects with stable IDs, typed links, suspect links). `uses_method_in` for section 4; `disagrees_with` on manual linking as the primary link source, reason: link authoring cost is no longer the binding constraint.
- Groth, P., Gibson, A., Velterop, J. (2010). The anatomy of a nanopublication. Information Services and Use. `uses_method_in` for Ruling and Passage nodes.
- Clark, T., Ciccarese, P., Goble, C. (2014). Micropublications: a semantic model for claims, evidence, arguments and annotations in biomedical communications. J. Biomedical Semantics. `uses_method_in` for R6.
- Shotton, D. (2010). CiTO, the Citation Typing Ontology. J. Biomedical Semantics. `uses_method_in` for R7.
- W3C PROV-O; OpenCitations; OBO Foundry ODK and ROBOT (already cited by Squiddy). `cites_as_evidence` for R8, R10.
- Seldon `2026-03-10_fractal_document_graph.md`, AD-013, AD-018: internal prior art this decision completes.

## 7. Next step

One CC task, filed against Seldon task dbe3d2dd: the LinkML domain schema for governed documents (Seldon side), the Squiddy ingest recipe that parses a governed markdown file into Document, Section, Ruling, Citation, and Passage nodes with lexical link recovery (Squiddy side), and a backfill run over `docs/design/`, `docs/requirements/`, `cc_tasks/`, `handoffs/` in the Seldon repository with the resulting node and edge counts registered as Results. Arnold rulings follow as the second corpus.
