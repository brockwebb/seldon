# SEL-001 delivery report: AD-031 Phase 1. Governed graphs for Squiddy and Arnold, and whether retrieval finds the rulings a task should have seen

**Date:** 2026-10-02. **Task:** `cc_tasks/2026-10-02_SEL-001_ad031_phase1_governed_graphs_retrieval_tevv.md`
(Seldon task ac0349a3). **Governing documents:** AD-031 (R1 to R3, section 4), AD-030 (R1, R3, R4, R9, R10),
Squiddy DN-025 R-110. **Addenda:** none exist (`*SEL-001*ADDENDUM*.md` matched nothing).
**Protocol:** `evidence/sel001/protocol.md`, committed before either arm ran (0bb69be; corrected three times, each
before any arm run: 975a2e7, 71991b4, 6bb7241; section 7). **Spend:** zero model calls. The only inference is Squiddy's pinned
local encoder (nomic-embed-text-v1.5 @ e9b67630), run under Squiddy's egress policy `none` with the sandbox applied.

## Verdict, first

**Both arms fail AD-031's bar, on both halves. Phase 2 is not designed (AD-031 section 4).**

| | Arm O (registration's concept overlap) | Arm H (Squiddy hybrid `search`) | Bar |
|---|---|---|---|
| Set A recall@10 (733 pairs) | **0.259** (Wilson 95% [0.229, 0.292]) | **0.164** ([0.139, 0.192]) | >= 0.80 |
| Set B pairs retrieved at k = 10 | **0 of 5** | **1 of 5** | 5 of 5 |

The measured causes are granularity first (half of all Rulings carry only their heading line as text; Section rows
crowd Ruling rows out of arm H's candidate pools) and the scorer second (arm O's overlap coefficient rewards the
shortest rulings). One B pair is a parse gap no retriever can close. Section 5.

## 1. Set B: the known misses (AD-031 section 1)

| Pair | Arm O | Arm H |
|---|---|---|
| KG-004 step 6 / DN-025 R-112 | miss, rank 78 | miss, beyond both sub-arms' 200 candidates (lexical rank 385 of 1,194 rows) |
| KG-004 step 6 / DN-025 R-113 | miss, rank 84 | miss, beyond both sub-arms (lexical rank 638 of 1,194) |
| KG-005 / DN-025 R-112 | miss, rank 43 | **hit, rank 3** |
| SQ-004 / DN-025 R-112 | miss, rank 132 | miss, beyond both sub-arms |
| RPE task (pb-03) / intensity-constructs per-set RPE ruling | miss: no Ruling node (parse gap) | miss: no Ruling node (parse gap) |

None of KG-004, KG-005 or SQ-004 cites DN-025, R-112 or R-113, as AD-031 section 1 says; both KG tasks use the
phrase "claims overlay", R-112's own vocabulary.

The intensity-constructs ruling is in a governed directory (`docs/ontology/`, AD-031-R1) and is not a Ruling: the
2026-08-16 paragraph ("`sets.rpe` is a CLOSED historical era. As of 2026-08-16 there is no capture surface for
per-set RPE anywhere in the system ...") carries no identifier and no banner, so no positional pattern admits it
(AD-030-R16). It was not hand-entered. Finding F6.

Outside B and outside the bar (protocol section 3): pb-04 and pb-01 against the same ruling miss the same way
(parse gap). Intensity-constructs section 12's R2 ("per-set effort is gone from PLANNING too", written 2026-09-12
in response to pb-03/pb-04) is found by arm O at rank 9 for pb-03 and missed by arm H.

## 2. Set A: explicit links, identifiers stripped

**Population.** 272 registered CC tasks (Squiddy 86, Arnold 186; 3 Arnold task files are no longer on disk, the
`ZZZ-throwaway` probes). 82 tasks cite at least one identifier that resolves to a Ruling in scope, giving **733
(task, ruling) pairs** (Squiddy 638 over 71 tasks, Arnold 95 over 11). `evidence/sel001/gold_a.jsonl`.

| Measure | Arm O | Arm H |
|---|---|---|
| recall@5 | 0.177 [0.151, 0.207] (130) | 0.134 [0.111, 0.160] (98) |
| recall@10 | **0.259 [0.229, 0.292]** (190) | **0.164 [0.139, 0.192]** (120) |
| MRR@10 | 0.113 | 0.076 |
| recall@10 over tasks (macro, information) | 0.316 | 0.199 |
| Squiddy tasks (638 pairs) | 0.271 [0.238, 0.307] | 0.171 [0.144, 0.202] |
| Arnold tasks (95 pairs) | 0.179 [0.115, 0.268] | 0.116 [0.066, 0.196] |

How the pairs arose, which the bar does not split but the reader should see:

| Gold reached by | Pairs | Arm O recall@10 | Arm H recall@10 |
|---|---|---|---|
| a document identifier only (`DN-025` -> every ruling it states) | 439 | 0.087 [0.064, 0.117] | 0.039 [0.024, 0.061] |
| the ruling's own identifier (`R-112`), with or without its document | 294 | 0.517 [0.460, 0.574] | 0.350 [0.298, 0.407] |

The document-identifier pairs are most of A and are a harder target than "the ruling the task relied on": a task
that cites DN-025 is credited with all five of its rulings. The protocol fixed that reading in advance (AD-031
section 4: "extract the DN-, AD- and R- identifiers it cites and resolve each to Ruling nodes"). The subset where a
task named the ruling itself also fails the bar, in both arms, so the verdict does not turn on it.

**Identifiers that resolved to no Ruling** (`evidence/sel001/gold_a_unresolved.jsonl`), 18:

- `AD-` with no document in scope: 16 (`AD-001`, `AD-002`, `AD-005`, `AD-012` x3, `AD-014`, `AD-016` x3,
  `AD-017` x2, `AD-025` x3, `AD-030`). Seldon's ADs are outside both scopes; Arnold's are in `docs/adr/`, which
  AD-031-R1 does not govern (F7).
- `DN-037`: Squiddy's DN-037 labels none of its decisions (plain bullets), so it states no Ruling.
- `R-17134`: no ruling carries it (a malformed token in the task text).

## 3. Set C: clean negatives, candidate counts

20 tasks, `random.Random(20261002)` over 149 completed tasks that no later addendum or erratum names
(`evidence/sel001/gold_c.jsonl`). Not a gate.

| | median | min | max |
|---|---|---|---|
| Arm O: rulings with score > 0 (of about 228) | 171.5 | 141 | 203 |
| Arm O: rulings at or above registration's threshold (0.18) | **76** | 28 | 176 |
| Arm O: what registration would bind (capped at its limit of 8) | 8 | 8 | 8 |
| Arm H: Ruling candidates in the top 10 | 3.5 | 0 | 8 |

Registration's threshold is not a filter: every clean task clears it for 28 to 176 rulings and registration binds
its cap of 8 every time, which is what SEL-001's own registration did (8 AD-030 rulings at 0.27 to 0.47, AD-031
section 1). Arm H returns fewer than 10 Ruling candidates for most tasks, because Ruling rows rarely reach either
sub-arm's 200-row pool (section 5).

## 4. Misses, per arm

Every A and B miss, with the task's top 3 candidates and the missed ruling's text, is in
`evidence/sel001/misses.md` (generated by `scripts/sel001/score.py`): 543 A misses and 5 B misses for arm O, 613
and 4 for arm H. Each carries mechanical cause signals (not exclusive):

| Signal | Arm O | Arm H |
|---|---|---|
| retrieval depth: the gold is in neither sub-arm's 200 candidates | n/a | 610 |
| granularity: a Section containing the gold ranked in the top 10 | n/a | 194 |
| granularity: a sibling ruling of the gold's own document is in the top 3 | 210 | 122 |
| vocabulary: the stripped task shares no content term with the ruling | 107 | 107 |
| outranked: shares terms, ranked below 10 | 285 | 1 |

## 5. What the evidence shows the causes are

**Cause 1, granularity of the Ruling unit (both arms).** A ruling written as a heading (`## R-15 Four things, one
truth`) becomes a Ruling node whose text is the heading line alone; its body is in the Section. Heading-form
Rulings are 115 of the 228 in scope (50.4 percent; 81 of Squiddy's 181 are `## R-nn` headings), median 72
characters, against 432 for a bold-label ruling, whose body is in the block. Arm H recall@10 by the gold's form: **0.008 for heading rulings (376 pairs), 0.328 for
bold-label rulings (357)**. Arm O: 0.223 and 0.297.

**Cause 2, Section rows crowd Ruling rows out of arm H's pools.** The index holds Sections (867 in Squiddy, 3,235
in Arnold; Squiddy's Sections average 1,525 characters, and an H1 Section spans its whole document) beside Rulings (181, 47).
A task file is long (KG-004's stripped text makes a 290-term OR query), and both BM25 over an OR query and dense
similarity to a long text favour long rows: KG-004's lexical top 200 is 200 Sections. Median Ruling rows among a
task's ~530 fused rows: 4. Checked by hand against the database for KG-004 with the kit's own `fts5_query`; the
harness is not the cause.

**Cause 3, arm O's scorer rewards the shortest rulings.** The overlap coefficient divides shared terms by the
smaller set (`seldon.core.governed.overlap_score`), so a two-term heading ruling that shares both terms scores 1.0:
`### R3 — the label` is arm O's rank 1 for KG-005 and pb-03. 71.6 percent of arm O's top-10 candidates are heading
rulings (median 73 characters). The same property makes the threshold pass 28 to 176 rulings on clean tasks.

**Cause 4, a parse gap.** The intensity-constructs per-set RPE ruling is unlabelled prose (F6).

**Vocabulary** accounts for 107 pairs in both arms (no shared content term after stripping): mostly
document-identifier pairs whose ruling the task never discusses.

No fix is applied (SEL-001 step 9). AD-031 section 4 names the candidates: section granularity (a heading ruling's
text is its section body; Sections and Rulings indexed or ranked separately), metadata documents, query
construction (a 290-term OR query is not a question).

## 6. The governed graphs (step 1 to 3)

| | Squiddy | Arnold |
|---|---|---|
| Governed files | 155 (design 40, cc_task 95, handoff 20) | 278 (design 2, ontology 7, requirements 9, cc_task 210, handoff 50) |
| Admitted | 155 / 155 | 278 / 278 |
| Sections | 867 | 3,235 |
| Rulings | 181 | 47 |
| by `matched_pattern` | bold_ruling_label 92, bare_ruling_heading 81, numbered_requirement_heading 8 | numbered_requirement_heading 20, bold_ruling_label 13, bare_ruling_label 8, bare_ruling_heading 6 |
| Documents with zero rulings | 108 (cc_task 87, handoff 20, design 1: DN-037) | 263 (cc_task 207, handoff 50, ontology 5, requirements 1) |
| Citations, Passages | 49, 133 | 27, 883 |
| Seldon graph after `seldon governed sync` | seldon-squiddy, agrees with the ledger | seldon-arnold, agrees with the ledger |
| Served index | 1,203 rows (1,048 Section/Ruling, 155 metadata), 155 shards | 3,560 rows (3,282 Section/Ruling, 278 metadata), 278 shards |
| Index parity | **PASS**, planted control fired (fingerprint db594a5c8142) | **PASS**, planted control fired (1f4d85d72775) |

Arnold's ontology documents with zero rulings: canonical-exercise-creation, progression-policy,
training-domain-vocabulary, week-template, workout-structure (their rulings are unlabelled prose, like F6's).
Zero-ruling lists: `evidence/sel001/governed_counts.json`.

Under the template's previous detector the same files gave Squiddy 8 rulings and Arnold 20 (F1).

**How each graph was built.** AD-030's template (Seldon `governed/`) copied unedited into `squiddy/governed/` and
`arnold/governed/` with a `TEMPLATE` file naming the Seldon commit and each file's sha256; pinned to the kit's
`squiddy/` tree at 4ac50a5; `make catalog`, `make sweep` (155 and 278 admissions, every one through all stages to
check-after, then the `references` layer); release; `seldon governed sync`. Each graph's first release stopped at
the kit's conformance stage on undeclared items (F13); the template now declares them and each graph's next
release passed every stage, its index and index-parity stages included. The index was then rebuilt (a resume:
nothing re-keyed) and parity re-run with the planted control under egress `none`
(`evidence/sel001/egress_index_*.json`, `parity_*.json`).

The index uses the library graph's frozen `index:` block verbatim (encoder, RRF k = 60, 200 candidates per sub-arm,
`tuned: false`, 10 documents, 3 rows each); only `units` (Section and Ruling ledger nodes), the pin's location and
the work directory differ, each stated in the graph's `extract/control.yaml`.

## 7. Decisions taken on the grounding, and corrections before any run

- **Arm H's ranking unit is the Ruling**, from the served verb's fused row ranking before it groups rows into
  documents; Sections compete in the sub-arms and are never candidates (protocol section 2). Phase 2 validates
  Rulings, so k counts Rulings.
- **Arnold tasks are scored over both graphs in both arms** (step 7). Registration today reads only its own
  database (F8), so arm O is the mechanism as AD-031-R1 says it should run, not as Arnold's registration runs now.
- **The task's own family is excluded** from its candidates (its own file, addenda, errata, RESULT).
- **"The RPE task" is pb-03** (F11).
- **Corrections, all committed before the first arm run:** identifier tokens end at their last digit (`R-112s`,
  975a2e7); Set C excludes a task a later addendum names in its text, as the protocol already said (the first draw
  held pb-03, 71991b4); a task's family is its `cc_tasks/` documents only (Squiddy's DN-031 file is named
  `INC-001_...`, 6bb7241).

## 8. Findings

**F1. The Ruling detector missed every label form Squiddy and Arnold write, and AD-031's own.** Fixed in the
template, a test per form (`tests/test_governed.py`, `SEL001_LABEL_FORMS`, verbatim examples):

| Form (pattern) | Three examples | Where |
|---|---|---|
| `bold_ruling_label` | `- **R-110 (the primary verb is hybrid retrieval with receipts).**`; `- **R-40.** ...`; `**DN-002-R1 A plan is optional; ...**` | Squiddy and Arnold DNs; Seldon AD-031 |
| `bare_ruling_heading` | `## R-01 A kit, not a system`; `## R-15 Four things, one truth`; `### R1 — nothing is required beyond what a set is` | Squiddy DN-001 to DN-003; Arnold docs/ontology |
| `bare_ruling_label` | `R1 **Nothing is required beyond what a set is.**`; `R2 **Per-set RPE is gone from planning too.**`; `- R1: block = within-workout grouping` | Arnold cc_tasks |

Sentences about a ruling (`R-26 ordered by ...`, `- R-112 makes claims an overlay ...`) stay prose; tested. A
ruling's label is read from its front (`ruling_label_pattern`) before the old search-anywhere fallback, which
would have labelled `- **R-112 (...).** ... AD-030-R5's path` as AD-030-R5. Over Seldon's 111 governed files no
existing ruling's id or pattern moves (checked; pinned for AD-030 by test).

**F2. AD-031's own three rulings were invisible to Seldon's governed graph** (`- **AD-031-R1. ...**`, a bold list
item with its title inside the bold). F1's `bold_ruling_label` admits them.

**F3. The pin check could never pass for a governed graph inside the kit's own repository.** It required Squiddy's
HEAD to equal the pinned commit; the commit that adds `squiddy/governed/` moves HEAD, and every docs-only Squiddy
commit broke every governed graph. The pin now binds the `squiddy/` package tree (the pinned commit's git tree
equal to HEAD's, nothing uncommitted in it); four tests. After Squiddy's governed-graph commit:
"HEAD b8b05e730e74 carries the pinned commit's squiddy/ tree 217dd296d320 unchanged".

**F4. Fourteen kit tests assume the working directory is Squiddy's root**, so the per-admission fast tier fails for
any graph run as `make -C <graph>`: `load_graph("graphs/library")` resolves against cwd
(`test_h009_quality_instrument.py` 5, `test_h011_decontext_instrument.py` 5, `test_h011a_repair_and_judge.py` 4).
Not fixed here. The sweeps ran with `--tests=`, and the fast tier ran once from the repo root on the pinned tree:
1,789 passed, 0 failed.

**F5. Arnold's root `.gitignore` ignores `*.jsonl`**, which would have left the governed ledger out of git without
a word. The template's `.gitignore` re-includes `ledger/events.jsonl` by name.

**F6. Domain rulings written as prose are not Rulings.** The intensity-constructs per-set RPE ruling, and every
ruling in five of Arnold's seven ontology documents, carry no label. No positional pattern can admit them without
admitting every bold sentence (AD-030-R16). Labelling them is an authoring act in Arnold, not a parser change.

**F7. Arnold tasks cite ADRs that are not governed.** `AD-016` is `docs/adr/016-exercise-id-convention.md`;
AD-031-R1 governs `docs/design`, `docs/requirements`, `cc_tasks`, `handoffs` and `docs/ontology`, not `docs/adr`.
`AD-025` (61 mentions in Arnold's task files) names no file in Arnold.

**F8. Registration reads one database.** `seldon cc register` calls `read_rulings` on the registering project's own
database, so an Arnold registration never sees a Squiddy ruling, though AD-031-R1 says Arnold's tasks search
Squiddy's graph.

**F9. Registration's identifier pass does not know Squiddy's ruling form.** `match_rulings` recognises
`[A-Z]{2,4}-\d+-R\d+` only; a task that names `R-112` gets no identifier match. Irrelevant here (the text is
stripped); relevant to Phase 2.

**F10. AD-031 section 1 says Seldon's governed graph was "built 2026-09-12 from 4 documents".** Its ledger held 106
Documents and 25 Rulings.

**F11. "The RPE task" is three tasks.** Arnold's addendum-02 R2 names pb-03 and pb-04 ("Desktop spec error"); pb-01
added the `RPE <n>` grammar token. B uses pb-03, which put the per-set field into a contract (AD-030 section 1's
description); pb-01 and pb-04 are reported beside it with the same result.

**F12. A document-local label repeated in one document collapses.** Arnold's plan-builder addendum-02 states R1 to
R3 twice (`R1 **...**`, then `**R1 — ...**`); both blocks key to `<doc>!r1`, so three Rulings are one node each,
last write winning. Seen in the ledger count (47) against the detector's block count (50).

**F13. The template predated kit 0.8's conformance contract.** Each graph's first release failed ten undeclared
items; `governed/conformance.yaml` now declares each for what the graph is, after the kit's own `registry` graph.
The control-record gate matches evidence files by the glob `*control*.json`, and a governed graph's evidence files
embed document ids, so Squiddy's DN-038 ("control own segment") was read as a control record; this graph's window
is declared never to open, with the reason.

**F15. The kit moved under the governed graphs before they merged.** SQ-005 (another session) merged kit changes
to Squiddy's main while SEL-001 ran (`factory.py`, `vocab.py`, `mesh_headings.py`, `text_routes.py`, the init
templates). None is on the governed pipeline's path (parse, assess, acquire, write, index), so the ledgers are what
main's kit would produce. The tree pin is strict by design, though: on Squiddy's main every governed graph's
`check-squiddy` now refuses until it is re-pinned and re-swept. The pin stays at 4ac50a5, the kit that built these
ledgers; re-pinning is the next governed build's first step. Whether a governed graph should pin only the modules
its pipeline imports is the open design question this exposes.

**F14. No scaffolder exists for a governed graph.** The template was copied, with provenance. A `seldon governed
init` would make the copy a command; not built.

## 9. Seldon's own governed graph

Not in SEL-001's measurement scope, and done anyway because the template changed under it. Seldon's governed graph
is the template's origin: its committed generated schema had to follow the `ontology` DocKind, its pin had to
follow the kit, and AD-031-R1 says every repository that registers CC tasks has a governed graph served with
Squiddy's `search`. Leaving it on the old recipe would have left a committed recipe that no ledger matched.

- Pin moved from 5611cf4 (kit 0.3.3) to 4ac50a5, the same as Squiddy's and Arnold's; schema regenerated; reset and
  full sweep, the recipe-change path (AD-030-R22). `extract/control.yaml` joined the template, so Seldon's graph
  builds the same index.
- Checked before the reset: under the new recipe the 106 previously admitted documents keep every Ruling and every
  Section id; nothing would retire.
- Sweep 20261002_sweep: 111/111 admitted, 111 layer runs, release passed every stage on the first try (index 1,639
  rows over 111 documents, 1,528 of them Section or Ruling; index parity pass).
- `seldon governed sync --dry-run`, then the sync: 105 documents unchanged, 1 updated, 5 created; 8 Rulings
  created, none retired. Rulings now 33 (25 before): AD-031-R1 to R3 (F2), and five `### R1.` to `### R5.`
  retirement decisions in `docs/design/evolution_burst_2026-04/phase_c_retirement_list.md` that the new
  `bare_ruling_heading` form admits. `seldon governed status`: every governed document in sync.

## 10. Commits

All three repositories on `feat/SEL-001`, merged to main and pushed.

- **Squiddy:** `4ac50a5` the index takes ledger nodes as units (kit; spec entry 0.17.0 after SQ-005's 0.16.0);
  `b8b05e7` the governed graph; merge `2ff1a07` (spec conflict with SQ-005 resolved by order); `489e358` the
  `seldon governed sync` events. Fast tier on the kit commit's tree: 1,789 passed.
- **Arnold:** `a893d36` the governed graph; merge `9cac708`. Arnold's root `.gitignore` keeps its Seldon event
  store (`*.jsonl`) out of git, so the sync's events are local to that checkout, as all of Arnold's are.
- **Seldon:** `0bb69be` template detector, pin, protocol and harness; `975a2e7`, `71991b4`, `6bb7241` corrections
  before any run; `0543c6f` template conformance; then the commit carrying this report, the evidence, Seldon's
  re-swept governed graph and the registered Results. Seldon suite: 2,115 passed.

Registered Results (seldon-seldon-self, `seldon result register`, input hash = `evidence/sel001/results.json`):
`sel001_arm_o_a_recall_at_10` 0.2592, `sel001_arm_o_a_recall_at_10_wilson_low` 0.2288,
`sel001_arm_o_a_recall_at_10_wilson_high` 0.2921, `sel001_arm_o_a_recall_at_5` 0.1774, `sel001_arm_o_a_mrr_at_10`
0.1134, `sel001_arm_o_b_hits_at_10` 0, `sel001_arm_o_bar_pass` 0; the same seven for arm H (0.1637, 0.1387, 0.1922,
0.1337, 0.076, 1, 0); `sel001_set_a_pairs` 733, `sel001_set_a_tasks` 82.

**`seldon cc complete` refused, and was left refused.** The task file was registered at `c6faeb5` (hash
2072527f...); the Desktop session then added arms O and H to steps 7 and 8 (AD-031 section 1: "registration
disproved it") and did not commit. This run executed that edited spec and committed it unaltered in `0bb69be`, so
its hash (8833d3f7...) no longer matches the registration and the immutability gate refuses completion. The gate
binds the machine; it was not bypassed, the registered hash was not touched, and the spec was not reverted. Task
ac0349a3 stays open until the operator settles it (an addendum or a superseding registration, per the gate's own
message).

## 11. Scope kept

- No retrieval fix applied; nothing tuned; the bar not moved.
- No ruling hand-entered.
- AD-030 and AD-031 not edited; every disagreement with them is a finding above.
- Zero model calls; the encoder ran offline under egress `none` with the sandbox applied
  (`evidence/sel001/egress_*.json`).
- `evidence/sel001/MANIFEST.json` records every evidence file's sha256 and what wrote it; the large regenerable
  ones (arm rows, queries, catalog) are kept out of git and are reproduced byte for byte by re-running
  `scripts/sel001/`.
