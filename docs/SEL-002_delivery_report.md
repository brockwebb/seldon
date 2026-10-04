# SEL-002 delivery report: AD-033 built. One decision register per repository, one write path, baseline DB-1, the 45 conflicts resolved as records, the probe re-run clean

**Date:** 2026-10-04. **Task:** `cc_tasks/2026-10-04_SEL-002_decision_register_baseline_db1.md` (Seldon task 0636b04a),
with ADDENDUM 01 (AD-033-R10 in Part A) and ADDENDUM 02 (AD-033-R11, the store-of-truth question closed).
**Governing:** AD-033 (filed as `docs/design/AD-033_decision_register.md`), AD-030, AD-031, AD-032, Squiddy DN-037,
DN-041, DN-042. **Prerequisites checked first:** SQ-008 (`3799de5`) and SQ-009 (`7076eae`) merged on Squiddy's main;
AD-032 present in Seldon's `docs/design`.
**Model spend:** Part E only, 3,058,891 weighted tokens over 1,249 calls (section 4). Everything else: zero model calls.

## 1. The override list

Every applied disposition that touches a record with `operator_stated: true`, plus the two that AD-033 section 5 puts
on the list by name (F21, F43). The task put F04 first; ADDENDUM 02 item 2 (written later) takes F04 and F06 off the
list, because the operator decided the store of truth himself on 2026-10-04 (AD-033-R11). They are not listed.
Nothing below edits a source document: each row is a register record (`evidence/sel002/part_c_events.json`,
`evidence/sel002/override_list.json`).

| Finding | Records | What changed | Receipt (why the record is operator-stated) |
|---|---|---|---|
| F21 (AD-033 s.5) | arnold:ADR-017 | Scoped to Arnold's served components at runtime; Squiddy's build-time model nodes are outside it (amendment + `scope_note`). | `docs/adr/017-local-first-models.md:5` "**Deciders:** Brock Webb" |
| F43 (AD-033 s.5) | squiddy:R-127 | The maintenance pick rule is an operator input set once; admit-one under it needs no pause (first builds still pause). | Not operator-stated by receipt; listed because AD-033 s.5 names it ("Operator 2026-10-02: admission by written rule"; Issue `45ca92d2`) |
| F09 | squiddy:R-152, R-153 | Amended by R-160 (the model may propose lookup labels, still chooses only returned descriptors) and R-161. | DN-033:12 "The operator's rule: do not invent what the science has..." |
| F16 | squiddy:R-152 to R-159 | Marked "under review per DN-037, binding until the review" (by DN-037-R7). R-147 to R-151 and R-160 to R-166 were marked the same and are not operator-stated. | DN-033:12 (R-152 to R-156); DN-034:5 "The operator's rule (2026-10-01 23:12, in session)" (R-157 to R-159) |
| F20 | squiddy:R-83 | Item 4's verb gate: the served contract is R-114's; question-driven verbs test it. | DN-018:5 "The operator's ruling, recorded" |
| F25 | squiddy:R-46, R-47 | Restated by R-125 (named exemption register; the extraction family keeps its daemon). | DN-011:3 "The operator's instruction, verbatim in substance..." |
| F28 | seldon:AD-023 | Deprecated (Wintermute mothballed 2026-09-10; AD-033 s.5). | AD-023:29 "Per operator decision 2026-04-18, ..." |
| F30 | squiddy:R-41 | The cited ChemRxiv DOI is recorded as nonexistent; the decision stands on Edge et al. 2024 and DI-177/H-009. | DN-009:3 "Written after the operator said, correctly, ..." |
| F34 | squiddy:R-43, R-44 | R-43's decontextualization dimension withdrawn (R-49); R-44's ranking clause closed (R-60: the judge ranks nothing). | DN-010:3 "The operator asked for a step back: ..." |
| F35 | squiddy:R-80, R-81 | Superseded for library only (R-97, R-107); R-81's cascade stays the template for a graph whose valve opens. | DN-018:5 "The operator's ruling, recorded" |
| F38 | squiddy:R-180 | Its check recorded as measured by SQ-009: 0 of 4 calls read the cache on a sub-1,024-token prefix. | DN-042:3 "Status: accepted (operator decisions of 2026-10-03 ...)" |
| F42 | arnold:ADR-013 | R2's "microcycle = ~1 wk" overridden by ADR-013 Addendum 01 (cycle duration is data). The amending record is itself the operator's. | `docs/adr/013-canonical-training-vocabulary.md:4` "Accepted (Brock, 2026-06-27)" |
| drifted mirror | squiddy:DI-242 | Made a decision of its own (it adds the acquire key without the kit version, which no R records; F19); it then amends R-116. | DECISIONS_INHERITED.md:511 "the operator's rule of 2026-09-12" |
| drifted mirror | squiddy:R-158 | Amended by DI-260 (an arXiv copy is an allowed public source at release). | DN-034:5 |

A caution on the receipts (finding G7): a note whose header names the operator gives every decision in that note
`operator_stated: true`. Where the operator prompted and Desktop decided (DN-009, DN-010, DN-011 are of that kind),
the list above is wider than "he stated it in his own words". Every receipt is in
`evidence/sel002/seed_manifest.json`.

## 2. Exit checks (AD-033 section 7, ADDENDUM 02 item 4)

All run by `scripts/sel002/exit_checks.py` on the final register; planted controls run on copies, never on the
registers. Output: `evidence/sel002/exit_checks.json`.

| # | Check | Result |
|---|---|---|
| 1 | A planted hand-edited record file fails verify (hash chain) | PASS: `00101_squiddy-r-107_accept.yaml` edited; "the data does not hash to its record_hash" |
| 2 | A planted forked supersession is refused, naming the live head | PASS: "supersedes target squiddy:R-29 is already superseded by squiddy:R-32; the live head of its chain is squiddy:R-32" |
| 3 | A planted labeled decision in a new note with no record fails verify | PASS: `R-990` in a new note in a clone of Squiddy; "labels squiddy:R-990, which has no record (AD-033-R2)" |
| 4 | Round trip: every one of the 485 probe units resolves to a record with a status | PASS: 485/485 (`evidence/sel002/roundtrip.json`; the three AD-020 calibration files resolve to `seldon:AD-020`, AALL-006 to `arnold:ADR-006`, each with the reason) |
| 5 | Seldon resolves `squiddy:R-112` from an Arnold registration | PASS: both `squiddy:R-112` and bare `R-112` in an Arnold task text bind `squiddy:R-112` by identifier, through Arnold's `decisions.import: [squiddy]` |
| 6 | The probe re-run on the register: zero open contradictions, zero silent supersessions among active records | PASS: 45/45 findings resolved; 0 open contradictions; 0 silent supersessions among 657 active records; 1 reviewed exclusion |
| 7 | Registration of SQ-009's text binds no superseded record (the R-29 case) | PASS: binds R-176 to R-181 by identifier and 8 accepted records by overlap; R-29 is `superseded` (by R-32) and is not bound |
| A02 | No agent-read file names a store other than the ledger as the record of truth | PASS, positive-controlled (the old CLAUDE.md sentence, "Neo4j is the live authoritative store", "the manifest is the record" are caught; "Authoritative list:" is not) |

The probe re-run (check 6) is `seldon decision check --probe` (`seldon.core.decisions.conflicts_probe`), a standing
command, so AD-033-R9's "at every release" has something to run. It does two things. First, it resolves each of the
probe's findings by a register event that cites it. Second, it scans for silent supersession afresh: any active record
whose own sentence uses one of the probe's amendment verbs about another active record must have that relation
recorded. Both halves are positive-controlled: a planted silent supersession and a planted open contradiction are
caught, and each control fails when its catching code is removed (`evidence/sel002/mutation_controls.txt`).

On its first run over the final register, the scan caught a real case. `seldon:AD-029-A`, registered late in this
task (G8), declares "Amends: AD-029", and that relation was unrecorded. It is now recorded (`00204_seldon-ad-029_amend`).
The one reviewed exclusion is `seldon:AD-029` naming AD-028's `withdrawn` task state, which is vocabulary, not a
withdrawal (`docs/decisions/probe_exclusions.yaml`). A new contradiction written in prose is not machine-detectable;
it reaches the register as a new probe finding, which half 1 then holds open.

## 3. Counts

**Records by status and repository** (after Parts B to E):

| | accepted | proposed | superseded | deprecated | total | register files |
|---|--:|--:|--:|--:|--:|--:|
| squiddy | 414 | 0 | 12 | 0 | 426 | 922 |
| seldon | 72 | 21 | 1 | 1 | 95 | 204 |
| arnold | 142 | 8 | 3 | 0 | 153 | 331 |

Seldon's 21 proposed records are AD-032 FC-08 to FC-33 less FC-11 to FC-15, waiting on "P1 to P6 per AD-032 section
8". FC-11 to FC-15 were accepted under F11: DN-042's status line records them as the operator's 2026-10-03
decisions, FC-04 (accepted, operator) names them as its check, and SQ-009 built them. Arnold's 8 proposed records are
the items its documents mark open (training-domain-vocabulary D5, D6, D9, D10, D11; the reversal record's D11;
canonical-exercise-creation B18), plus ADR-008, whose status line reads Proposed and which no task names.

**Consumers (Part D, AD-033-R6).** Filled mechanically when each record was written: the files under each
repository's configured roots (Squiddy `squiddy/conformance.yaml`, `tests`, `squiddy`; Seldon `tests`, `seldon`;
Arnold `tests`, `src`) that cite the id as a whole token. FC records are searched across all three repositories.
Records with no citing file got one review-only reason by rule: a pre-registration heading gives
`pre_registration`; an FC label or text naming dispatch or a hold gives `dispatch`; a rationale-only heading gives
`rationale`; anything else gives `none`. Coverage over accepted records at the end of Part C
(`evidence/sel002/part_d_coverage.json`):

| | accepted | with a consumer | coverage | review only: none / dispatch / rationale / pre-registration |
|---|--:|--:|--:|---|
| squiddy (own) | 196 | 133 | 0.679 | 50 / 8 / 4 / 1 |
| squiddy inherited DI rows | 218 | 91 | 0.417 | 122 / 5 / 0 / 0 |
| seldon | 66 | 45 | 0.682 | 8 / 12 / 1 / 0 |
| arnold | 134 | 19 | 0.142 | 109 / 1 / 5 / 0 |

`none` consumers on the final register: squiddy 172, seldon 14, arnold 117 (303 in all), with the 14 records added
under G8 counted. `none` is allowed at DB-1 (R6). The FC-01 gate that refuses it waits on FC-17.

**DB-1's contents** (`docs/decisions/BASELINE_DB-1.md`): 658 seeded records, plus AD-033-R10 and R11 written as
superseding records, plus the 14 labeled decisions registered under G8. That makes 674 records: 504 decision, 15
requirement, 71 mirror (62 still mirrors; 9 drifted mirrors became decisions).

**Part C:** 143 events: 117 amendments, 11 supersessions, 9 drifted mirrors made decisions, 5 acceptances
(FC-11 to FC-15), 1 deprecation (AD-023). The 12 drifted mirrors were dispositioned as follows:
- DI-240, DI-242, DI-246, DI-252, DI-178, DI-211, DI-263, DI-260 and DI-201 became decisions with their own
  statements. Each amends its R where it adds or reverses something; DI-211's R-90 citation is recorded as a
  probable mis-citation.
- DI-163 was amended at the seed by AD-033-R11.
- DI-258 (F03) and DI-204 (F12) were superseded.

## 4. Part E: statements (AD-033-R8)

**Pass rate.** 599 active, non-mirror records went through a writer call and a separate validator call. The validator
sees only the verbatim source and the statement. 495 passed (0.826), meaning entailed, complete and standalone.
471 landed as `statement_check: passed` with the new statement. The other 24 that the validator passed were refused by
the write path, because the statement points at other text ("this decision", "all of the following", "the note");
they keep the verbatim text. 128 records are `statement_check: failed` and keep their verbatim statement.

| | records | passed (landed) | failed | of which: not complete / not entailed / not standalone / no verdict / no statement / refused by the write path |
|---|--:|--:|--:|---|
| squiddy | 356 | 279 | 77 | 66 / 7 / 2 / 0 / 0 / 10 (overlaps the validator columns) |
| seldon | 93 | 72 | 21 | 11 / 0 / 0 / 1 / 0 / 10 |
| arnold | 150 | 120 | 30 | 15 / 5 / 0 / 6 / 2 / 6 |

Most `not complete` verdicts are DI rows. The validator holds that a row's tag column (its adaptation, or "does not
apply") is part of the decision; the writer's rule 5 says so too, and some statements still drop it.

**Estimate, actual and ratio**, in weighted tokens. The weights are the API price ratios recorded in `spend.yaml`, an
assumption: the Max plan's limit accounting is not published.

| Job | Estimate | Actual | Ratio |
|---|--:|--:|--:|
| Pilot 1 (first 10 rows, default effort), writer / validator | 19,637 / 18,125 (guesses) | 42,697 / 70,295 | 2.17 / 3.88 |
| Pilot 2 (stride sample, default effort) | 21,500 / 21,138 (guesses) | 47,710 / 97,179 | 2.22 / 4.60 |
| Pilot 3 (stride, `--effort low`) | 21,500 / 21,198 (guesses) | 47,929 / 45,627 | 2.23 / 2.15 |
| Pilot 4 (instructions as system prompt, serial) | 14,946 / 16,744 (guesses) | 23,199 / 19,034 | 1.55 / 1.14 |
| Bulk (575 records, measured on pilot 4) | 1,333,928 / 1,092,552 | 1,486,065 / 1,116,155 | 1.114 / 1.022 |
| Run 2 (2 retries + the 14 G8 records) | 36,835 / 25,187 | 41,467 / 21,533 | 1.126 / 0.855 |
| **All of Part E** | 3,000,000 (the task's notional, before any pilot) | **3,058,891** | **1.02** |

Before the bulk started, the projection from pilot 4 (2.82M including every pilot) was under the stop line I had
declared in config before the first pilot: 3M plus the +20% band. Three earlier pilots projected past that line (up to
8.5M). They were not run on; the prompt and transport were fixed instead:
- validator thinking cut with `--effort low` (G6);
- the instructions moved into the system prompt, so they are cached once rather than written every call (G5);
- the pilot drawn as a stride sample across the three registers instead of the first ten DI rows.

In run 2 the governor stopped both jobs at touchpoint 1. The writer hit its token cap after 13 of 15 units, and the
validator hit the +20% band, because the 14 added records are long sections. They were not resumed: under DN-042
R-178 that takes the operator's dated `spend_approval.yaml`. So 2 records have no statement and 7 have no verdict;
all 9 keep their verbatim text, flagged failed. One of them is plan-builder addendum-02 R2 (per-set RPE gone from
planning).

**Discipline.** The checkpoint plan (constitution sections 11 and 15) was committed before the first paid call
(`evidence/sel002/part_e_checkpoint_plan.md`). The SIGKILL test passed offline before then, and again after each
harness change (`evidence/sel002/statements_kill_test.txt`). Two calls timed out at 300 s in the bulk; they were
failure rows, and the next run retried them. Raw replies, usage and keys are in `evidence/sel002/statements/`.

## 5. What was built

- **Step 0.** AD-033 filed byte for byte as `docs/design/AD-033_decision_register.md`: sha256
  `5d57fe89ce8c035858ba696318cd02340ec329c2f1e7a40b579e0c411c6efbb3`, equal for the workbench file and the filed copy.
  It was committed alone, first, on main and pushed (`419c30e`), before any code. Seldon's governed sync parsed
  **0 decision units** from AD-033: the governed graph would not admit it (findings G1, G2).
- **Part A (AD-033-R2, R3, R4, R7, R10).**
  - The record is a LinkML schema, `seldon/domain/decision_register.yaml` (the governed template's language), read
    by a small validator, since linkml-runtime is not a Seldon dependency.
  - The write path is `seldon.core.decisions`. Each record event is one YAML file. `prev_hash` and `record_hash`
    follow DN-041's chain form, and a file's bytes must equal the canonical serialization of its data. The write path
    refuses a missing field, a used id, a missing or inactive target, and a forked supersession (naming the live
    head). Status is a fold of the record's events, never edited.
  - `seldon decision propose|accept|reject|supersede|amend|deprecate|show|list|check|project`, with matching
    `seldon_decision_*` MCP tools. Both call one entry point, so their refusals are identical (tested).
  - `Decision` nodes are projected into each project graph, with `supersedes`, `amends`, `mirrors` and `constrains`
    edges; imported records are pointers. REGISTER.md is rendered from the fold, and a hand edit fails the check.
  - `seldon verify` gains a Tier A "Decision register" check. It fails on a broken chain or hash, an unregistered
    label in a note added after DB-1, a rationale that resolves to no file, a hand-edited REGISTER.md, a stale
    projection, or a task bound to a non-accepted record.
  - `seldon cc register` in a repository with a register binds accepted `Decision` records only, its own and its
    imports', and prints "advisory until SEL-003". Positional Rulings become `force: searchable` (with
    `positional_force` kept).
  - `Decision` joined `SELDON_OWNED_LABELS` (Addendum 029-A); legacy ArchitecturalDecision and DesignNote nodes are
    untouched (tested).
  - Tests: `tests/test_decision_register.py`, 26. Each planted control is shown failing with its catching code
    removed (12 mutants).
- **Part B.** The DB-1 seed (`scripts/sel002/seed_db1.py`) went through the write path. It parses with the probe's
  own `inventory.py`, copied byte for byte, with its two truncation caps lifted in memory. It recorded the baseline
  commit set (`docs/decisions/BASELINE_DB-1.md`): seldon `a6422a0`, squiddy `c3de555`, arnold `f31a4c3`.
  - The re-run found 505 units, the 485 plus 20 added since the probe.
  - DN-037 became R1 to R7. AD-032 became FC-01 to FC-33.
  - Arnold's ADRs got their status from each ADR's status line.
  - The Arnold ontology decisions SEL-001 F6 named were located by a read-only reader and checked by script: 114.
  - Arnold DN-001 and DN-002 were added beyond R5's list (G8).
  - Truncated units (DI-170 to DI-178, and Arnold training-domain-vocabulary) carry full bodies.
- **Part C.** The dispositions are `scripts/sel002/part_c_dispositions.py`, a declarative table of 143 events, each
  citing its finding id and quotes. A mirror pass found no active mirror of a superseded record.
- **ADDENDUM 02 item 3.** One edit: Squiddy `CLAUDE.md` "The one invariant" now carries AD-033-R11's first two
  sentences (`876fc98`). I searched every `CLAUDE.md`, `AGENTS.md` and README, plus Seldon's `docs/conventions/`,
  in all three repositories for "authoritative", "source of truth", "graph-as-truth", "store of truth". The other
  hits are not about a store of record: Seldon's validity vocabulary README, the units-vocabulary
  "Authoritative list:", Arnold's CLAUDE.md "two versions of the truth" (task immutability), Arnold's kernel and
  local-routing READMEs. They are unchanged. Squiddy CLAUDE.md lines 95, 97 and 106 (F14, F01, F22) were not edited:
  Part C edits no source document, and the register carries the amendments.

## 6. Findings

**G1. Seldon's governed graph could not admit anything after SQ-008.** SQ-008 admitted AD-032 into the governed
ledger, and its release never re-cut the served export (served 111 documents, replay 112). Every later admission was
therefore refused at check-before. Release `20261004_sel002_export_repair` re-cut it, and every stage passed; the
ledger gained the four AD-032 `Mentions` edges the references layer had never written (`9ccd57c`). SQ-008 also left
two aborted-attempt directories in the gitignored `governed/evidence/`, which failed conformance item 5. I moved
them, not deleted them, to `governed/work/aborted_evidence_sq008/`.

**G2. AD-033 is not in Seldon's governed graph: the pinned kit (4ac50a5) refuses the admission.** With the export
repaired, the admission passes check-before and is refused at stage 07, reconcile. The `read` stage writes the
Document with `manifest_state: cataloged` while the manifest says `admitted`. I rolled the partial admission back to
the kit's own pre-write snapshot (a byte-identical prefix) and the manifest to its committed state; the drift gate
then reads manifest == ledger == export. Two more kit behaviours are on the record:
- An abandoned admission is itself a divergence that blocks the admission that would finish it.
- The per-document fast tier fails when run outside the kit's root (SEL-001 F4); the sweep ran with `--tests=`,
  as SEL-001's did.

AD-033's decisions are in the register, which is now Seldon's binding source (R7). `seldon verify` reports these 4
documents as never cataloged.

**G3. Squiddy's governed graph is nine documents behind** (SQ-006 to SQ-009, DN-041, DN-042, two handoffs). This
predates SEL-002 and was not touched; its pin no longer matches the kit's tree (SEL-001 F15). Arnold's governed graph
likewise has 4 never cataloged.

**G4. Arnold's `.gitignore` ignored `seldon.yaml`.** The register's import list and baseline commit live there, so
`seldon.yaml` is re-included by name. It holds no credentials.

**G5. DN-042's estimator overstates a small parallel pilot.** A call counts as warm when it shows any cache read.
Under the CLI every call reads its system prompt, so cold-start calls (about 6k tokens written on each worker's first
call) are priced as warm. Pilot 3 measured 4.79k per writer call by the governor's mean, against 3.13k for its seven
steady calls. Moving the instructions into the system prompt removed the effect here. A kit issue is worth filing:
price each worker's first call separately.

**G6. The CLI's default effort spends output tokens on thinking.** Pilot 2's validator returned a few lines of JSON
for up to 4,774 output tokens. `--effort low` cut its pilot cost from 97.2k to 45.6k with no loss visible in the
verdicts.

**G7. Receipts from a note's header apply to every decision in it** (see the caution in section 1). The first seed
scanned only each decision's own span and status line, so it missed ADR-017's "**Deciders:** Brock Webb". It was
redone before anything consumed it: the three Part B commits were reset on the unmerged branch and re-seeded, and
nothing else changed.

**G8. Positional rulings without a record.** Before R7 took effect, 42 positional Rulings had no record
(`evidence/sel002/positional_rulings_without_record.json`).
- 28 are not decisions: Squiddy's 8 task-file H1 headings (SEL-001's sample defect) and Arnold's 20
  `docs/requirements/FR-*` headings. They stop binding, correctly.
- The other 14 were registered through the command (`scripts/sel002/register_labeled_rulings.py`): Seldon Addendum
  029-A, the phase-C retirement rulings R1 to R5, and Arnold's eight labeled rulings in dispatched task addenda.

**G9. The probe's mirror list was a set of ranges.** DI-186, DI-187 and DI-189 cite no R. The task's rule, applied
literally, gives 71 mirrors, which is the probe's count.

**G10. The write path's first position-pointer pattern was too broad.** It refused "at or above 0.98" and "the layer
below the symptom". 30 validator-passed statements were recorded failed and then re-landed after the correction. Both
events are in the chain (`evidence/sel002/statements/reapply.json`); a test now holds both directions.

**G11. Suites.**
- **Seldon:** green (section 7).
- **Squiddy:** one failure, conformance item 15 (`harvest_walk_complete`): the new register directories in Seldon and
  Arnold, plus three subtrees ai-readiness-kg added after X-001's walk, had no disposition. Fixed (`e1e770c`).
- **Arnold:** 978 passed, 1 failed. `test_every_set_reference_resolves_to_a_node` fails on main too: live data, sets
  pointing at `CANONICAL:ARNOLD:MILKO_BENCH_PRESS`, which has no node. Not touched.
- Squiddy's `seldon verify --fix` could not fix CLAUDE.md's hash: the fixer only runs `seldon paper sync`. The hash
  was recorded with `seldon artifact update`.

## 7. Commits, suites, verify

<!-- filled at merge -->

## 8. Scope kept

- No source document edited, except ADDENDUM 02's Squiddy CLAUDE.md correction (its own commit).
- The operator was asked nothing. Two governor stops in Part E were left stopped, for his dated approval if he wants
  the 9 remaining records stated.
- AD-033 section 6 (SEL-003's pre-registration) was committed before anything was measured; nothing in it was tuned.
