# AD-030 Implementation Findings 002: Names, Supersession, Incremental Re-ingest

**Name:** AD-030-F002
**Date:** 2026-09-12
**Status:** Active (Desktop reconciliation of `cc_tasks/2026-09-12_ad030_findings_reconcile_RESULT.md` against the live graph)
**Extends:** AD-030 (governed documents as graph content)
**Depends on:** `docs/design/AD-030_implementation_findings_001.md`, `cc_tasks/2026-09-12_ad030_findings_reconcile_RESULT.md`
**Seldon task closed by this reconciliation:** eb359760 (`completed` by CC under L4; graph verified 2026-09-12)

---

## 1. Context

The reconcile task met its contract. Graph state verified from Desktop: 102 governed Documents, 19 active Rulings (10 in AD-030, 9 in Findings 001), 166 retired, 14 Results verified, both gate fixtures withdrawn, the R17 to R10 `SUPERSEDES` edge present, 13 `CONSTRAINED_BY` edges on eb359760.

The RESULT raises four findings the implementer correctly left unsettled. Two are AD-030 changes (a document's canonical name, the supersession syntax), one is a requirement on the Squiddy stream (incremental re-ingest), one is a reading of R16 to ratify.

Errata: RESULT section 5 states `governed_edges_contains` as 1825 in prose while the verified token resolves to 1844. The prose figure is from a pre-final sweep. R18 already forbids the practice; no ruling change.

## 2. Rulings

**AD-030-R20.** A governed document declares its canonical name in a `Name:` header field. The name is the graph identity used by `name`-keyed queries, `EXTENDS` recovery and the ruling ID prefix. When the field is absent, the derivation is the leading identifier of the file stem, with sorted-path-first-claim as the collision tiebreak; a derived name is never authoritative over a declared one. Every design note written from this ruling forward carries the field. Settles reconcile RESULT G2.

**AD-030-R21.** Supersession is declared, not inferred. A ruling that replaces another carries the declaration as its final sentence in the form `Supersedes AD-NNN-Rn.` (hyphenated ruling ID, sentence-final). Recovery is a single pattern over ruling text: `Supersedes` followed by one or more ruling IDs. Whole-document supersession uses a `Supersedes:` header field with document names. Nothing else is read as supersession. Settles reconcile RESULT G6.

**AD-030-R22.** An admitted governed document whose content hash has moved is re-ingested at the cost of that one document. The requirement is on the stream Seldon consumes (AD-030-R10): the kit's assess stage compares the manifest's recorded hash against the file, treats `admitted but changed` as admissible, and the write stage appends updated node events that the projection merges last-write-wins. A full ledger rewrite is a reset path, never the edit path. Until this lands, no corpus larger than the Seldon repo is admitted. Settles reconcile RESULT G9.

**AD-030-R23.** R16 governs classification only. A block admitted as a Ruling has its force (`binding`, `prohibition`, `recommendation`) read from its own text by a separate force pattern list. A ruling identifier classifies a block only when used as a label: sentence-initial and terminated by `.` or `:`, or bolded, or opening a heading. An identifier mentioned inside a sentence, or cited in a heading that discusses it, is a `mentions` target. Ratifies reconcile RESULT G7 and G8.

**AD-030-R24.** Retired Rulings keep their nodes and edges and bind nothing. `read_rulings` excludes `retired` and `superseded` by default. Ratifies reconcile RESULT G1 and the retire-not-delete decision in RESULT section 1.

## 3. Accepted without a new ruling

- G3 (re-write on name change as well as hash change), G4 (suspect follows content hash only), G5 (header-field edges resolve paths as well as identifiers). Fixed generically.
- `seldon cc constrain <task|--all>` for backfilling `CONSTRAINED_BY` on tasks that predate the gate. 58 tasks predate it; backfill is part of the next task.

## 4. Not tasked

- Arnold rulings as the second corpus. Blocked on R22 by that ruling's own terms.
- The 154 `never` retirements are correct for this corpus but the pattern set has been tuned on one repository. A second corpus is the test.

## 5. Prior art

- Cleland-Huang, J., Gotel, O., Huffman Hayes, J., Mäder, P., Zisman, A. (2014). Software traceability: trends and future directions. FOSE 2014. `cites_as_evidence` for R21 (explicit trace links over inferred ones where inference precision is low).
- Object Management Group (2023). OMG Systems Modeling Language (SysML) v2 Beta specification, KerML. `uses_method_in` for R20 (declared element names, derived names as fallback).
- Groth, P., Gibson, A., Velterop, J. (2010). The anatomy of a nanopublication. Information Services and Use 30(1-2). `uses_method_in` for R23 (assertion versus mention).
- Kleppmann, M. (2017). Designing Data-Intensive Applications. O'Reilly, ch. 11 (log-based incremental processing, last-write-wins merge). `uses_method_in` for R22.

## 6. Next step

One CC task, `cc_tasks/2026-09-12_ad030_names_supersession_reingest.md`: `Name:` field and supersession pattern on the Seldon and governed side, incremental re-ingest on the Squiddy side, `seldon cc constrain --all` backfill, counts re-verified.
