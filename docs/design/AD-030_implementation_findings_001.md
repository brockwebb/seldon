# AD-030 Implementation Findings 001: Rulings on the First Backfill

**Date:** 2026-09-12
**Status:** Active (Desktop reconciliation of the two 2026-09-12 CC RESULT files against the live graph)
**Extends:** AD-030 (governed documents as graph content), AD-028 (result names and task lifecycle), AD-029 (task precedence)
**Depends on:** `cc_tasks/2026-09-12_seldon_handoff_tool_RESULT.md`, `cc_tasks/2026-09-12_ad030_governed_docs_ingest_RESULT.md`
**Seldon tasks closed by this reconciliation:** dbe3d2dd, a5c372d1, 343cb6fe, d7fb603f (all `completed` by CC under L4; graph verified 2026-09-12)
**Source thread:** Desktop session 2026-09-12, second thread (resume from `handoffs/2026-09-12_ad030_governed_documents_design.md`)

---

## 1. Context

Both CC tasks ran and merged. Graph state verified from Desktop after completion:

- Four tasks `completed`. `343cb6fe PRECEDES d7fb603f` intact.
- 98 Document nodes, all `admitted`; the ingest RESULT file itself was cataloged after the counts were registered, so `governed_document_nodes` (97) is already one behind disk. This is the AD-030 F10 window closing on its own author.
- AD-030 Document contains 13 Ruling nodes (10 real, 3 pattern artefacts per F9).
- 2364 relationships excluding ontology, role and workflow scaffolding, up from 61 the same morning.
- Zero `CONSTRAINED_BY` edges. Expected: the gate writes them at registration and no task has been registered since it shipped. The CC task filed with this note is the first to pass through it.
- All 13 registered Results are `proposed`. None verified.
- AD-030 has no ArchitecturalDecision node. It exists as a Document with Rulings. See R14.

The RESULT files raise eleven findings that the implementer correctly refused to settle by editing AD-030. This note settles them. AD-030 is not edited; where a ruling below changes AD-030 text, this note supersedes that text and the `supersedes` edge is the record.

## 2. Rulings

**AD-030-R11.** The R9 design-note gate binds every actor except `cc`. Exemption is an allow-list of one, not a deny-list. A task created by any actor string other than `cc` (`desktop`, an autonomous agent, an unknown value) is gated. Settles handoff RESULT F1. Rationale: CC executes decisions; anything else that files a task is deciding, and unknown actors escaping a gate silently is the failure mode AD-030 section 2 describes.

**AD-030-R12.** Manifest state for a governed document is a projection of the kit's stage axis, not a fifth state machine. `cataloged` and `held` map one to one; `admitting` and `in_graph` both render as `admitted`; any `excluded:` disposition renders as `declined`. The kit's in-flight stage is never exposed. Settles ingest RESULT F4. AD-030 R5 stands; this ruling defines its mapping.

**AD-030-R13.** `mentions` edges are emitted only where the target resolves inside the emitting graph. Every other identifier a document references is carried on the node as `identifiers` and resolved by the consuming graph against its own artifacts. Identifiers that resolve nowhere are abstained on and reported by `seldon governed status`, never emitted as dangling edges. Settles ingest RESULT F5 and supersedes the "for every identifier" wording in AD-030 section 4. This is R10 applied to link recovery.

**AD-030-R14.** A Document node and a decision record are distinct node kinds joined by `seldon_artifact_id`. Existing ArchitecturalDecision and DesignNote nodes (30) are not mutated and not re-minted. From AD-030 forward, no new ArchitecturalDecision or DesignNote node is created for a governed file: the Document node plus its Ruling nodes is the decision record. `seldon docs check` counts Documents whose path is under `docs/design/` alongside legacy decision nodes. Settles ingest RESULT F6.

**AD-030-R15.** A citation is captured only when the reference carries a year, a DOI, or `et al.`; a bare name is a `mentions` candidate, not a Citation. Design notes therefore write every prior-art entry with at least a year. AD-030 section 6 entries lacking a year (INCOSE/SysML v2, DOORS/ReqIF, PROV-O, OpenCitations, ODK/ROBOT) are corrected in the next design note that cites them, not by editing AD-030. Settles ingest RESULT F8 and extends R9.

**AD-030-R16.** A Ruling is a section whose heading or first token carries a ruling identifier (`AD-NNN-Rn`, `DN-…-Rn`, a numbered requirement ID) or the `BINDING` banner as a heading token. Deontic words in body prose (`never`, `must`, `BINDING` used as vocabulary) do not classify. The pattern edit lives in `governed/config.yaml` under `domain:`; `matched_pattern` on each Ruling makes the reclassification auditable. Settles ingest RESULT F9. The 168 figure is a pattern count, not a ruling count, and is re-registered after the edit.

**AD-030-R17.** Squiddy is a build-time dependency of the `governed/` graph, pinned by commit in `governed/` (requirements file or Makefile variable), not a runtime dependency of the `seldon` package and not in `pyproject.toml`. Supersedes the `pyproject.toml` clause of AD-030 R10; the acyclicity and no-awareness clauses stand. Settles ingest RESULT F11.

**AD-030-R18.** Counts registered by a backfill are run outputs and enter the graph as `proposed`. Verification is a re-run of the sync followed by `seldon result verify`; a mismatch follows AD-028 stale handling. `governed_document_nodes` is already stale (97 registered, 98 on disk). No count from a governed backfill is quoted in a handoff or design note above `proposed` until verified.

**AD-030-R19.** An uncataloged governed file is a verify finding that names the command to run and is never `--fix`-able from Seldon. Ratifies ingest RESULT F10 as designed behaviour.

## 3. Accepted without a new ruling

- Handoff RESULT D1 through D5 (date-over-mtime boundary, `seldon go HANDOFF_PATH`, config constants written at `init`, two-case empty dispatch, no overwrite without `--force`). All consistent with existing standards; recorded here so they are addressable.
- Handoff RESULT F2 closed by ingest Part C (node form of the R9 check shipped).
- Ingest RESULT F1, F2, F3, F7: kit and lint defects fixed generically in Squiddy and Seldon. No ruling needed.

## 4. Not tasked

- Three of 30 legacy decision nodes have no Document pointing at them. Likely the consolidated `seldon_architectural_decisions.md` (AD-001 to AD-014 in one file). Inspect when a legacy node is next touched.
- Arnold rulings as the second corpus (AD-030 section 7). Separate task after the reconciliation below verifies clean.
- Cross-graph identity registry (R8). Not exercised by a single-corpus run.

## 5. Prior art

- Cleland-Huang, J., Gotel, O., Huffman Hayes, J., Mäder, P., Zisman, A. (2014). Software traceability: trends and future directions. FOSE 2014. `cites_as_evidence` for R13 (trace link recovery abstains rather than guesses).
- Shotton, D. (2010). CiTO, the Citation Typing Ontology. J. Biomedical Semantics 1(S6). `uses_method_in` for R15.
- Object Management Group (2023). OMG Systems Modeling Language (SysML) v2 Beta specification. `cites_as_evidence` for R14 (model element and its rendered view are distinct).
- Groth, P., Gibson, A., Velterop, J. (2010). The anatomy of a nanopublication. Information Services and Use 30(1-2). `uses_method_in` for R16 (assertion versus provenance versus supporting text).

## 6. Next step

One CC task, `cc_tasks/2026-09-12_ad030_findings_reconcile.md`, applying R16 and R17, cataloging and admitting this note, re-running the governed sync, and verifying all registered counts under R18.
