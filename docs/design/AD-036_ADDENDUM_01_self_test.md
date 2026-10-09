# AD-036 ADDENDUM 01: the receipt grammar, two departures, and the self-test (R7)

**Date:** 2026-10-09. **Task:** PA-001 (`459f463e`). **Amends:** nothing in AD-036's rulings. It
records what PA-001 Part A step 4 and Part G require: the receipt syntax (documented here, not
by editing AD-036), the two places the build departed from R3's wording, and R7's self-test,
whose internal searches re-run with the tool are the receipts below. `seldon prior-art verify`
reads a note together with its `AD-036_ADDENDUM_*` files, so this addendum completes AD-036's
prior-art section without editing it.

## 1. The receipt grammar (Part A step 4)

One bullet per receipt, under `### External` or `### Internal` beneath a `## Prior art` heading
(a numbered heading such as `## 2. Prior art` is accepted). Prose around the bullets is allowed and
ignored. Every bullet that says `receipt:` is parsed strictly; one that does not parse is
`malformed`.

    - library receipt: query "<q>" | release <export file> sha256:<64 hex> | rows <row id>, <row id>
    - internal receipt: query "<q>" | repo <name>@<40-hex commit> | hits <path>:<line>, <path>:<line>
    - web receipt: url <https://...> | retrieved <YYYY-MM-DD>

- `rows none` and `hits none` are the receipt of a search that found nothing. That is the only
  accepted form of "no prior art"; a sentence saying so with no such receipt fails.
- A hit in a file the repository does not track (a gitignored handoff) is cited
  `<path>:<line>#sha256=<first 12 hex of the file>`, because a commit does not pin it.
- A root that is not a git repository is named `<name>@tree:<64 hex>`, the digest of every path
  and content hash searched.
- A query may not contain a double quote.
- `seldon prior-art search --internal|--library "<q>"` prints receipts in exactly this form; an
  author pastes them and may trim the cited hits to the ones the note relies on.

Statuses per receipt: `pass`, `id_not_returned` (a cited row or line is not in the re-run result),
`release_unavailable` (the named release, commit or tree cannot be loaded, or an untracked file
changed), `malformed`.

## 2. Two departures from R3's wording, decided before the recall control ran

1. **Files are read from git's object store, not by ripgrep.** R2 requires each receipt to be
   re-run against the commit it names; ripgrep reads only a working tree. The matching semantics
   are ripgrep's as R3 states them (case-insensitive, every term within one paragraph), with
   terms matched at a word start so `pin` finds `pinned`. Search and verification run the same
   function over the same bytes, so a receipt the tool printed always re-verifies at its commit.
2. **The declared corpus adds each repository's top-level `docs/*.md`.** R3's list misses the
   files where two repositories keep their governing specification and decision log: squiddy
   `docs/EXTRACTION_DESIGN_SPEC.md` and `docs/DECISIONS_INHERITED.md`, ai-readiness-kg
   `docs/design_decisions.md`. Two of the 18 recall-control locations are in them. The addition is
   in `seldon.yaml` with its reason and is in the pre-registration's tool description.

## 3. The recall control (R5)

Pre-registered in `docs/evidence/pa001/recall_control_prereg.yaml` (commit `3c29394`) before any
run. Result, `docs/evidence/pa001/recall_control_result.json`: 8 of 18 at top 20, recall 0.444,
Wilson-95 [0.246, 0.663]. **FAIL** against the 0.70 bar. As R5 states, this does not block the
gate. The misses and what the tool does not do are in the PA-001 RESULT; the governed-graph arm is
filed as a design task.

## 4. Self-test (R7)

**AD-036 verified as written** (`seldon prior-art verify`, 2026-10-09, AD-036 sha256 `1e88beac53c6`,
governed-ledger event `6f906ce4`): **FAIL**. Both subsections exist; neither carries a receipt in the
grammar, because the note was written before the tool and states its searches in prose. That is the
bootstrap R7 describes, not a defect of the note.

**Converted.** Every library query AD-036 section 2 quotes was re-run verbatim against the release
it names, and every row it cites came back (`docs/evidence/pa001/selftest_searches.json`). Its
internal section, "searched by reading", was re-run as nine tool searches; each target it names was
returned. The receipts are in section 5. With them, AD-036 plus this addendum verifies **PASS**
(event recorded in the governed ledger; the RESULT names it). Two cited sources stay outside the
library, as AD-036 already said: PRISMA-S (Rethlefsen et al. 2021) and reproducible-builds.org.
The vendor page R8 rests on is carried as a web receipt.

AD-035's own check is in `AD-035_ADDENDUM_01_prior_art_verified.md`.

## 5. Prior art

### External

- library receipt: query "checklist compliance enforced gate pre-registration systematic review protocol reduces errors" | release library_graph_20260930_m002_2026-09-30.json sha256:fc7f31737a682d1832e26ac72ebe5da75d054bd4e8564524ba1ed239a2576543 | rows lesson:2026-04-13_arXiv_2406_14325#p21:138:1384-1675, lesson:2026-04-13_arXiv_2406_14325#p16:104:1865-2521, lesson:2026-02-22_arXiv_2502_12110#p22:436:25-451
- library receipt: query "LLM agents fail to follow instructions in long context, constraints ignored, instruction adherence degrades" | release library_graph_20260930_m002_2026-09-30.json sha256:fc7f31737a682d1832e26ac72ebe5da75d054bd4e8564524ba1ed239a2576543 | rows lesson:2026-02-22_arXiv_2401_07128#p8:229:96-130, lesson:2026-02-22_arXiv_2410_15553#p10:200:2341-3477
- library receipt: query "PRISMA-S reporting literature search strategy databases search strings dates reproducible search" | release library_graph_20260930_m002_2026-09-30.json sha256:fc7f31737a682d1832e26ac72ebe5da75d054bd4e8564524ba1ed239a2576543 | rows lesson:2026-05-09_arXiv_2604_23338#p4:54:1802-2716, lesson:2026-02-02_arXiv_2501_05435#p4:36:519-1392
- library receipt: query "LLM behavior drift over time model version changes reproducibility of results" | release library_graph_20260930_m002_2026-09-30.json sha256:fc7f31737a682d1832e26ac72ebe5da75d054bd4e8564524ba1ed239a2576543 | rows lesson:2026-03-29_arXiv_2411_15594#p44:613:2025-3138, lesson:2026-03-29_arXiv_2411_15594#p22:329:2228-3056, lesson:2026-04-07_arXiv_2307_09009#p2:40:494-2812, lesson:2026-04-07_arXiv_2307_09009#p1:8:1723-2355
- web receipt: url https://code.claude.com/docs/en/model-config | retrieved 2026-10-09

### Internal

G5 problem 1, its timeline and best answer (rank 1 of 19):
- internal receipt: query "internal prior art searched" | repo workbench-audit@tree:c03bc86f0e4d7087c6f9cc417ee42ef66f7bc07268d5316448b4344c744b5412 | hits cross_project/synthesis/G5_governance.md:38#sha256=30a923e2b1ff, cross_project/synthesis/G5_governance.md:548#sha256=30a923e2b1ff, cross_project/synthesis/G5_governance.md:11#sha256=30a923e2b1ff

methodology section 1 (model identity is a gate) (rank 7 of 48):
- internal receipt: query "model identity gate" | repo ai-readiness-kg@7e62f24e23b7ea8a61f9c68de906be3db6b8a162 | hits docs/research/kg_construction_methodology.md:8

methodology section 7 rules 1 to 5 (rule 5: verify product facts before pinning) (rank 4 of 5):
- internal receipt: query "product facts pinning" | repo ai-readiness-kg@7e62f24e23b7ea8a61f9c68de906be3db6b8a162 | hits docs/research/kg_construction_methodology.md:68

methodology section 7.6 (rank 5 of 31):
- internal receipt: query "positive-controlled instrument verdict" | repo ai-readiness-kg@7e62f24e23b7ea8a61f9c68de906be3db6b8a162 | hits docs/research/kg_construction_methodology.md:55

squiddy DN-009 R-40 (rank 1 of 32):
- internal receipt: query "internal search gate" | repo squiddy@1cc6fc2d4e7b289737c1bccc210a6166707480ad | hits docs/design/2026-09-20_internal_prior_art_packs_anchors.md:37, docs/design/2026-09-20_internal_prior_art_packs_anchors.md:30, docs/design/2026-09-20_internal_prior_art_packs_anchors.md:13

plan action E's exit check (rank 3 of 3):
- internal receipt: query "frozen questions p95" | repo workbench-audit@tree:c03bc86f0e4d7087c6f9cc417ee42ef66f7bc07268d5316448b4344c744b5412 | hits 2026-10-04_next_actions_plan.md:16#sha256=29e02311ed48

AD-030-R9 (rank 1 of 5):
- internal receipt: query "design note citation register refuses" | repo seldon@7ef721140a094309ad60b86c69661eb7ebfca9df | hits docs/design/AD-030_governed_documents_as_graph_content.md:51

AD-033's design-note label patterns (rank 4 of 17):
- internal receipt: query "label pattern decisions" | repo seldon@7ef721140a094309ad60b86c69661eb7ebfca9df | hits docs/design/AD-033_decision_register.md:78

the stale governed pin (Issue 25da4d06) (rank 1 of 5):
- internal receipt: query "governed pin stale" | repo seldon@7ef721140a094309ad60b86c69661eb7ebfca9df | hits handoffs/2026-10-04_SEL-002_decision_register_db1.md:19
