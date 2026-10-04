# AD-033: One decision register. Decisions are records with a lifecycle, kept in each repository, projected into Seldon, and measured before they are consumed at dispatch

**Date:** 2026-10-04
**Status:** Draft. Desktop design session. Implemented by SEL-002 (the register and the baseline, plan action C).
Section 6 is the pre-registration for SEL-003 (AD-031 Phase 1b, plan action D) and is frozen once this file is
committed.
**Extends:** AD-030 (governed documents as graph content), AD-031 (rulings reach the task by retrieval).
**Answers:** handoff 2026-10-04 open questions 1 (where the register lives) and 2 (AD-032's FC labels).
**Implements:** AD-032 (factory control design) FC-16, FC-18, FC-19; prepares FC-17.
**Location until filed:** `/Users/brock/GitHub/workbench/2026-10-04_decision_layer/`. SEL-002 step 0 files it as
`seldon/docs/design/AD-033_decision_register.md`, unchanged, and records its sha256.

## 1. The failure, measured

- The probe over 485 decision units found 45 conflicts: 10 contradictions, 23 silent supersessions, 3 stale
  premises, 3 duplicates, 6 cross-repository. 26 touch active work. No supersession is recorded in any machine-readable
  form; Seldon's parser cannot read Squiddy's ids (probe `conflicts.md`, F05).
- SEL-001 measured retrieval of the decisions a task should have seen: recall@10 0.259 (overlap) and 0.164 (hybrid)
  against a bar of 0.80; 0 and 1 of 5 known misses. Causes: 50.4 percent of Ruling nodes are a heading line only;
  Section rows crowd decisions out; the overlap score favors short text; one decision was unlabeled prose.
- Live example, 2026-10-04 08:40 ET: registering SQ-009 bound 8 decisions by word overlap. One of them, R-29 (the
  cost control chart), was withdrawn by R-32 on 2026-09-20 (probe F32). Registration binds withdrawn decisions as
  binding, because nothing records that they were withdrawn.
- A sample Ruling node in the Squiddy governed graph is the H1 heading of S-001's task file
  (`matched_pattern: numbered_requirement_heading`, `force: binding`). Positional parsing promotes headings to
  decisions.
- Cost of the gap: about 2.42M tokens and two repair rounds when Arnold tasks planned extraction against DN-025
  R-112 and R-113 (Arnold testing handoff, section 2). The operator was the continuity layer and caught it from
  memory.

The defect is not retrieval alone. A decision has no record: no stand-alone statement, no status, no declared
supersession, no consumer. Retrieval over prose cannot recover what was never written down as a record.

## 2. Prior art

### External

Searched 2026-10-04 (web): MADR 4.0, architectural knowledge vaporization, architecture fitness functions, long
context against retrieval. The remaining items are carried from the operator's audit and AD-031, where they were
checked; they were not re-fetched here.

- **Decisions as first-class records.** Jansen and Bosch 2005 (WICSA, doi:10.1109/WICSA.2005.61): design decisions
  should be first-class entities; when they are not, the knowledge vaporizes into the artifacts. Lee 1997 (IEEE
  Expert): rationale systems fail at retrieval at the point of decision, not at capture. Kruchten 2004 (ontology of
  architectural design decisions): decisions carry status and typed relations to each other (constrains, conflicts
  with, overrides, subsumes, is bound to).
- **The record form.** Nygard 2011 (Documenting Architecture Decisions): one short record per decision, in the
  repository, never rewritten; a changed decision is a new record and the old one reads "Superseded by".
  MADR 4.0.0 (released 2024-09-17): YAML front matter with status (proposed, accepted, rejected, deprecated,
  superseded by ADR-NNNN), date, decision-makers, consulted, informed. Practice tooling refuses a forked
  supersession chain and refuses edits to an accepted record (adr health checkers; dx-harness issue 315).
- **Statements.** Mavin et al. 2009 (EARS): five sentence templates (ubiquitous, event-driven, state-driven,
  unwanted behavior, optional feature) for requirements. EARS fits decisions that state behavior; it does not fit
  choices (a store, a name, a scope). Those get one declarative sentence.
- **Decisions as executable checks.** Ford, Parsons and Kua 2017, 2nd ed. 2023 (Building Evolutionary
  Architectures): an architectural fitness function is any mechanism that gives an objective integrity assessment
  of an architectural characteristic; Richards and Ford add a compliance section to each ADR naming whether and how
  it is checked. This is FC-01 (a decision exists only when something consumes it) in published form.
- **Baselines and change control.** EIA-649C: configuration identification, change control, status accounting,
  audit. A baseline is an identified, approved state from which changes are controlled. The register is a
  configuration baseline of decisions.
- **Whole register or retrieval.** Li et al. 2024 (EMNLP, arXiv:2407.16833): long-context prompting outperforms
  retrieval when the material fits the window, at higher token cost; Self-Route routes between them. Liu et al.
  2024 (TACL, Lost in the Middle): position in a long prompt affects use. ExpeL (Zhao et al. 2024, AAAI) hands the
  whole insight list to the agent. A full register of about 450 active records at about 80 tokens each is about
  36k tokens, which fits.
- **Traceability recovery.** Antoniol et al. 2002; Cleland-Huang, Gotel and Zisman 2012; LiSSA (ICSE 2025): the
  validator is limited by retrieval recall (AD-031 section 2).
- **Clustered data.** Pairs from one task are not independent. Cluster bootstrap over tasks (Field and Welsh 2007,
  JRSS-B; not re-fetched).

### Internal precedent

Searched: Seldon `docs/design`, `docs/decisions`, `seldon/core/governed.py`, the Squiddy graph's artifact types
(Cypher), the probe and its `inventory.py`, the FC draft, SEL-001, the Arnold testing handoff, Seldon's
architectural decisions document (AD-006, AD-007).

- **Seldon AD-006 and AD-007** made Results and ResearchTasks first-class artifacts with state machines because
  prose in handoffs drifted. Decisions are the third thing that drifts and the one still in prose. This note applies
  the same move.
- **AD-030** (R5: the manifest lives in the graph, the YAML is rendered and never hand-edited; R14: the Document
  plus its Rulings is the decision record, legacy decision nodes frozen; R16: positional patterns; R21: supersession
  declared, sentence-final; R22: recipe change path). R14 is superseded by AD-033-R10. **AD-029 Addendum 029-A**:
  every node pattern label-bound, `:Artifact` on every traversal; the new label must join its lint set. R5's pattern is reused for the
  rendered register. R16 and R21 are kept for prose and stop being the binding source (section 3, R7).
- **AD-031** and **SEL-001**: measured the failure; gold sets A, B and C are reused unchanged in section 6.
- **Squiddy DN-041 R-174** (`decision_log.jsonl`, append-only, hash-chained; the restore found 46 damaged entries
  the gate had not seen). The hash chain is reused for register records. DN-041's log holds admission decisions
  inside a graph; it is a different object and is not the register.
- **The Seldon graph already has a `Ruling` type** (181 in Squiddy's project graph, from governed sync, carrying
  `force: binding` and `authority: accepted` with no lifecycle). The register does not reuse it as the binding
  source: its population is the positional parse SEL-001 measured.
- **The probe's `inventory.py`** parsed 485 units with full bodies (R units are not heading-only there). SEL-002
  reuses it for the seed.
- **Arnold `docs/adr/`** uses Nygard status lines ("Accepted (Brock, 2026-06-27)") with no supersession field
  (probe F42).
- **Squiddy `DECISIONS_INHERITED.md`**: 71 DI rows mirror an R; 12 drifted from it (probe mirror summary).
- **Found empty:** no repository holds a decision record with a machine-readable status or supersession; `seldon/docs/decisions/` holds three
  documents (AD-025, its amendment, PL-011) and no record format.

## 3. Decisions

- **AD-033-R1. The register lives in each repository as files, and Seldon holds the projection.** Each
  repository that registers tasks (squiddy, seldon, arnold) keeps its decisions under
  `docs/decisions/register/`, one YAML file per record event, never edited. The files in git are the record of
  truth. Seldon projects them into `Decision` nodes in that repository's project graph and renders
  `docs/decisions/REGISTER.md` (generated, never hand-edited). A project reads other repositories' registers by an
  import list in `seldon.yaml` (`decisions.import: [squiddy]` for arnold); records stay in their home repository and
  the importing graph holds pointers.
  - Why files and not Seldon's event store: git is the one store that has not lost records (C6: 451 documents lost
    in Wintermute; Arnold's `.gitignore` drops Seldon's `*.jsonl`); Nygard and MADR keep records in the repository;
    the operator's pattern is small specialized stores with a hub of pointers. Why not one central register
    repository: R-01 and DI-004 (the monolith drift). Why not Squiddy's decision log: process decisions are Seldon's
    domain, and Squiddy has no knowledge of Seldon (AD-030-R10).
  - This answers open question 1: both, with the repository files as truth and the Seldon graph as projection.

- **AD-033-R2. One write path, control-type at the source.** Records are written only by `seldon decision`
  (CLI and MCP): `propose`, `accept`, `reject`, `supersede`, `amend`, `deprecate`, `show`, `list`, `check`. The
  command validates before writing and refuses: a missing required field; an id already used; a `supersedes` or
  `amends` target that does not exist or is not active; a second supersession of an already superseded record
  (forked chain; the refusal names the live head). Each file carries `prev_hash` (the previous record in that
  repository) and `record_hash`. `seldon verify` fails a file the command did not write (broken chain, hash
  mismatch) and a labeled decision in a new design note that has no record. Desktop calls the MCP form, so
  registering a decision is part of writing the note, not a later step.

- **AD-033-R3. The record.** Required fields: `id` (repository-qualified, the repository's native scheme:
  `squiddy:R-112`, `squiddy:DI-020`, `squiddy:EX-REQ-02`, `seldon:AD-030-R21`, `seldon:AD-032-FC-04`,
  `arnold:ADR-017`); `kind` (decision, requirement, mirror); `statement` (stand-alone; EARS when it states behavior,
  one declarative sentence otherwise; it names no other record by "this", "above" or "the note"); `source` (path,
  line range, sha256 of the source file, verbatim text); `status`; `scope` (repositories and graphs it binds);
  `rationale` (path and anchor of the note that argues it); `consumer` (R6); `decided_by` (operator, desktop,
  cc-task id, or inherited from a named repository) and `operator_stated` (true when the operator stated it in his
  own words, with the receipt); `date`. Relations, all optional: `supersedes`, `amends` (with the clause),
  `mirrors` (a DI row points to the record it mirrors and carries no statement of its own, FC-16), `constrains`.
  Control records add `control_type` (control or warning, FC-08) and `pattern` (FC-07). The relation names are
  Kruchten's (2004), cut to the ones the probe needed.

- **AD-033-R4. Status is a lifecycle, and it is derived.** Statuses are MADR's: proposed, accepted, rejected,
  deprecated, superseded. A record never changes after it is written. A status change is a new transition record;
  a superseded status is derived from the later record that names it. Only accepted records bind. Desktop
  decisions under L4 are accepted when registered (decided_by desktop); the operator overrides by a superseding
  record, never by an edit. `proposed` is for a decision that waits on a named measurement, and names it.

- **AD-033-R5. Baseline DB-1 (plan action C).** One baseline is established from the three repositories' main
  HEADs at SEL-002's start, recorded by commit. It holds: the probe's 485 units; DN-037's decisions, given ids
  `squiddy:DN-037-R1` onward at baseline; AD-032's FC labels (FC-01 to FC-07 accepted, operator-stated; FC-08 to
  FC-33 proposed); Arnold `docs/adr/` records; and the unlabeled prose decisions SEL-001 named (Arnold
  intensity-constructs per-set RPE, the five Arnold ontology documents), given ids `arnold:<doc>-B<n>` with their
  verbatim span. Seed status: the source's stated status where it has one; a decision a dispatched task has
  executed under is accepted, with that task as the receipt; otherwise accepted. Then the 45 probe findings and the
  12 drifted mirrors are applied as transition and superseding records, each citing its finding id and quotes,
  under L4. The probe's dispositions apply as written, except those that offer a choice; section 5 makes those
  choices. Every disposition that touches an operator-stated record goes on an override list in the delivery report.
  He is not asked.
  - This answers open question 2: AD-032's FC labels enter as records at the baseline; the positional parser is not
    extended for them.

- **AD-033-R6. Every accepted record names its consumer (FC-01), and the gap is counted, not blocked.** At the
  baseline `consumer` is filled mechanically: the conformance items, tests and code that cite the id. A record with
  none carries `review_only` with one reason from a closed list: `rationale` (explains, binds nothing);
  `pre_registration` (consumed by the task that ran it); `dispatch` (to be consumed at dispatch once FC-17 exists);
  `none` (no consumer yet). `none` is allowed at DB-1 and reported as a coverage figure at every release. The
  FC-01 gate that refuses `none` is turned on with FC-17, not before, so the baseline is not a blockade.

- **AD-033-R7. Positional Rulings stop binding.** Once a repository's register exists, `seldon cc register` binds
  `Decision` records only; positional `Ruling` nodes stay as searchable content and lose `force: binding`. Until
  SEL-003 picks an arm, registration's binding is labeled advisory in its output. AD-030-R16 and R21 stay in force
  for prose readers. Supersedes the binding role of AD-030-R16.

- **AD-033-R8. Statements are written by one call and checked by another.** For each active record a model writes
  the stand-alone statement from the verbatim source; a separate validator call checks that the source entails the
  statement and that nothing in the source's decision is dropped. A record that fails keeps the verbatim text as its
  statement, flagged. The pass runs through the Squiddy call layer under the DN-042 spend governor (SQ-009), with a
  10-record pilot, a measured estimate and a ceiling.

- **AD-033-R9. The conflicts probe stands (FC-18).** The probe is re-run on the register at the end of SEL-002 and
  at every Squiddy, Seldon and Arnold release. DB-1 exits with zero open contradictions and zero silent
  supersessions among active records. A governing document may not cite an id the register records as nonexistent.

- **AD-033-R10. The register record is the decision record.** AD-030-R14 made the Document node plus its Ruling
  nodes the decision record; SEL-001 measured that population as half headings, and a task file's H1 heading sits
  in it as a binding Ruling (section 1). From DB-1 forward the decision record is the register record, projected as
  a `Decision` node. Legacy `ArchitecturalDecision` and `DesignNote` nodes (30) stay unmutated, as R14 says; a
  `Decision` node is one per decision, never one per file, so R14's ban on new per-file decision nodes is kept. The
  `Decision` label joins Addendum 029-A's label set, and every read that traverses a relationship from it binds
  `:Artifact`. Supersedes AD-030-R14.

- **AD-033-R11. The log is the record of truth; Neo4j is the live working store; files are rendered views.**
  For every graph Squiddy builds, every Seldon project and this register: the authoritative record is the
  append-only, hash-chained event ledger kept with the repository. Neo4j is the live working store: every read and
  query goes to it, and the only write into it is a replay of the ledger, proven by the parity gate (S-009, H-001).
  The manifest is the stream of catalog, assess, admit, decline and supersede events in that ledger; the manifest
  YAML and `REGISTER.md` are rendered and never hand-edited. AD-030-R5's "the manifest lives in the graph" means
  the graph's ledger. Grounding: Helland 2015 (CIDR; CACM 2016), the truth is the log and the database is a cache of
  a subset of it, which is how every database including Neo4j already works (its transaction log); Kleppmann 2017
  (Designing Data-Intensive Applications, ch. 11 and 12: the log as system of record, databases as derived views);
  Kreps 2013 (The Log); 21 CFR 11.10(e) and ALCOA+ (an audit trail that never obscures what was recorded); the
  operator's own requirement that the manifest prove every past decline, which a store updated in place cannot do.
  Operator decision 2026-10-04, ending the question. Supersedes squiddy:R-04.

## 4. What changes for each session

- **Desktop:** a design note's decisions are registered in the same session through the MCP command; the note
  carries the ids and argues them. Desktop never edits a record.
- **CC:** a task that changes a decision lands a superseding record through the command and names it in its
  report.
- **Registration:** binds accepted `Decision` records only (R7), advisory until SEL-003.
- **Dispatch (FC-17):** designed after SEL-003, on its numbers (AD-031-R3).

## 5. Choices the probe left open

| Finding | Decision | Grounding |
|---|---|---|
| F06 manifest primacy | Settled by AD-033-R11. The manifest is a stream of events in the graph's ledger; Neo4j and the YAML are projections of it. R-08 and DI-070 wording and DI-242's direction are amended to R11; R-15's table gains the manifest. | AD-033-R11 (operator decision, 2026-10-04). |
| F16 DN-037 | DN-037 gets numbered decisions at the baseline. R-147 to R-166 are marked "under review per DN-037, binding until the review". | DN-037's text; FC-16. |
| F21 Arnold ADR-017 | ADR-017 is scoped to Arnold's served components at runtime; Squiddy's build-time model nodes are outside it. | Arnold's build runs these nodes now; ADR-017 is operator-accepted, so override list. |
| F23 Squiddy reads a Seldon Result | The demand-gate verdict moves into the graph's own register (R-126) and the valve reads that. AD-030-R10 stands. The code change is a Squiddy task, recorded with `consumer: none` until built. | AD-030-R10; operator: Seldon leverages Squiddy, never a merge. |
| F43 maintenance admission | The pick rule is an operator input set once in the spec; admit-one under that rule needs no pause. R-127 is amended. | Operator 2026-10-02: admission by written rule, stops only for disasters; Issue `45ca92d2`. Override list. |
| F28, F44 Wintermute ADs | AD-023 is deprecated (Wintermute mothballed 2026-09-10). AD-024 is scoped to Seldon and Wintermute. | Probe F28, F44. |
| F04 store of truth | Settled by AD-033-R11. R-15 stands; R-04's per-graph choice and the CLAUDE.md sentence saying the kit does not mandate which store is truth are superseded. Not on the override list. | AD-033-R11 (operator decision, 2026-10-04). |

## 6. Pre-registration: AD-031 Phase 1b on the register (SEL-003)

Frozen when this file is committed. Nothing here is tuned after a run.

- **Units.** Active accepted `Decision` records of DB-1 after SEL-002, scope including the task's repository and its
  imports. Text per record: id, statement, verbatim source. No Section rows in any arm.
- **Gold sets.** A, B and C exactly as SEL-001 drew them (same tasks, same seed, same stripping). Gold identifiers
  are re-resolved through the register (so DN-037 and Arnold ADR ids now resolve). Reported twice: the 733 pairs as
  SEL-001 resolved them, and the re-resolved set. The bar is judged on the re-resolved set.
- **Arms.**
  - **O:** Seldon's concept-overlap score over record text, unchanged code.
  - **H:** Squiddy's hybrid `search` over an index whose rows are records only, frozen `index:` block as SEL-001.
  - **F (full register):** one validator call per task with the whole active register in its scope, record order
    shuffled per call with a fixed seed (Liu et al. 2024); the call returns at most 10 record ids, ranked, that
    constrain or conflict with the task. Two replicates; agreement between them reported (Cohen's kappa and Gwet's
    AC1, R-52). The validator is a separate call from any author.
- **Positive control.** One planted record per B task that contradicts that task's text in its own words. An arm
  whose plant is not retrieved at k = 10 is reported as not working and its verdict is not cited (methodology 7.6).
- **Measures.** recall@5, recall@10 and MRR on A (arm F: recall over its returned set, which is at most 10), Wilson
  intervals, and a cluster bootstrap over tasks (10,000 resamples, seed 20261004) reported beside Wilson; B hits at
  k = 10; C candidate counts. Split by gold form (document identifier against the record's own identifier) as
  SEL-001 did.
- **Bar (AD-031 section 4, unchanged):** recall@10 on A at or above 0.80, and 5 of 5 B pairs at k = 10.
- **Outcome rule.** An arm that meets the bar is the binding mechanism for registration and for FC-17's design. If
  more than one meets it, the cheaper by measured tokens per task. If none meets it, the report names the misses by
  record and Phase 2 is not designed.
- **Spend.** O and H: zero model calls. F: about 106 tasks times 2 replicates times about 40k input tokens, about
  8.5M input tokens (notional; measured by a 5-task pilot under the DN-042 governor before the run). The
  2026-10-04 plan's "zero model calls for 1b" is corrected here: arm F calls a model.

## 7. Checks

- A planted hand-edited record file fails `seldon verify` (hash chain).
- A planted forked supersession is refused by `seldon decision supersede`, naming the live head.
- A planted labeled decision in a new note with no record fails `seldon verify`.
- Round-trip: every one of the 485 probe units resolves to a record with a status.
- Seldon resolves `squiddy:R-112` from an Arnold registration (SEL-001 F8, F9).
- The probe re-run on the register reports zero open contradictions and zero silent supersessions among active
  records.
- Registration of SQ-009's text against the register binds no superseded record (the R-29 case in section 1).

## 8. Open

- Whether `review_only: dispatch` records should be pasted into every task prompt or only those bound by SEL-003's
  arm. Decided with FC-17, on SEL-003's numbers.
- The third graph (handoff question 3) is out of scope here.
