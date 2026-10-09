# PA-001: the prior-art receipts gate (AD-036), declared effort, hermetic tests, and the AD-035 records the register cannot see

**Repo:** seldon (primary). Cross-repo by absolute path: `/Users/brock/GitHub/squiddy`, `/Users/brock/GitHub/arnold`, `/Users/brock/GitHub/icsp_notebook`, plus every repo MODEL-001 touched for Part E. Each repo gets its own `feat/PA-001` branch. L4: commit, merge and push in every repo touched.
**Date:** 2026-10-09. **Authored by:** a Desktop session in squiddy.
**Governing:** `/Users/brock/GitHub/seldon/docs/design/AD-036_prior_art_receipts_gate.md` (R1 to R9, section 6). Read it in full. Also read:
- `/Users/brock/GitHub/seldon/docs/design/AD-035_config_driven_model_selection.md`
- `/Users/brock/GitHub/seldon/docs/design/AD-035_erratum_01_prior_art_overstated.md`
- `/Users/brock/GitHub/seldon/cc_tasks/2026-10-09_MODEL-001_config_driven_model_selection_RESULT.md`

Glob and read every sibling `*PA-001*ADDENDUM*.md` first.
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Model:** primary
**Spend:** est. 3M tokens for this session. Library and internal searches are local. Zero harness model calls.
**Network:** none beyond git push. `icsp_notebook` CI runs on its host after push.

## Step 0
Stop if this task is `in_progress` in the seldon graph.

## Part A: the tool (R1, R2, R3)

1. Build `seldon prior-art search --library|--internal "<query>"`.
   - The library arm calls squiddy-library `search` in-process, through squiddy's installed package.
   - The internal arm runs ripgrep over `prior_art.internal_roots`, a new `seldon.yaml` key, seeded per R3.
   - Both arms print R1 receipts and append to `state/prior_art_queries.jsonl`.
2. Build `seldon prior-art verify <note>`. It parses `## Prior art` / `### External` / `### Internal` and re-runs each receipt per R2. It reports per receipt: `pass`, `id_not_returned`, `release_unavailable` or `malformed`.
3. Expose both as the seldon MCP tool `seldon_prior_art_search`, plus `seldon_prior_art_verify`.
4. Pick a receipt syntax a note author can write by hand and the parser reads strictly. Document it in AD-036's addendum, not by editing AD-036.

## Part B: the gate (R4)

- `seldon verify` (pre-commit) refuses a commit adding a design note that lacks a passing verify. The verdict is written to the governed ledger beside the note's hash.
- `seldon cc register` refuses a task whose governing note has no passing verdict. The refusal quotes what is missing and names AD-036.
- The baseline is every note on main at this task's merge commit. Write the list to `docs/design/AD-036_baseline.txt`.
- Tests:
  - a planted note without the section is refused at commit and at registration;
  - a planted receipt whose row id the query does not return fails;
  - a "no prior art" sentence without a query receipt fails;
  - each gate is removed in turn to prove its test fails (kg_construction_methodology §7.9).

## Part C: the recall control (R5)

- Before any run, write the 18 positive locations and one fixed query per location to `docs/evidence/pa001/recall_control_prereg.yaml`.
  - The locations come from G5 problem 1's timeline and the four ai-readiness-kg lines AD-036 section 2 cites.
  - Write each query from the entry's topic, never copying its wording.
  - Commit the file.
- Then run the internal arm and report recall at top 20 with its Wilson-95 interval against the 0.70 bar.
- A miss list is the deliverable either way.
- A failure does not block Part B.

## Part D: library latency (AD-036 section 4)

- Measure p95 of squiddy-library `search` over the 24 frozen questions, cold and warm, against 10 s.
- Write `docs/evidence/pa001/library_latency.json`.

## Part E: declared effort and hermetic tests (R8, R9)

- **R8.** Refuse `effort: default` in `seldon.models`. Set every role per R8, rewrite the registry comment, and have every launcher pass `--effort`. Receipts record effort. `seldon models refresh` records each family's documented default effort in the `models_lock_bumped` event.
- **R9.**
  - Gate arnold's live seed-scan test and every test that can reach a launcher without a fake behind an opt-in variable.
  - Search for them in every repo MODEL-001 touched and list them in the RESULT.
  - Add a PATH-shim test proving zero `claude` invocations by default.
- **icsp_notebook CI:** install seldon from the pin the repo's `models` extra names, so the 18 skipped AD-035 gate tests run. The CI run URL is the evidence.

## Part F: the register cannot see AD-035 (AD-036 section 6.1)

- Write AD-035-R1 to R8 into the decision register through `seldon decision`, with AD-033-R8's statement and validator. Point each record's source at AD-035's heading lines.
- Add the `ruling_label_unparsed` check to `seldon verify`, with a planted note whose heading-form label is uncaptured.
- Run it over every repo whose `seldon.yaml` has a `decisions:` block. Report any other note it catches; do not fix them here.

## Part G: self-test (R7)

- Run `seldon prior-art verify` on AD-036 and on AD-035.
- Re-run AD-036's internal section as tool searches.
- Record both results in `/Users/brock/GitHub/seldon/docs/design/AD-036_ADDENDUM_01_self_test.md` and `/Users/brock/GitHub/seldon/docs/design/AD-035_ADDENDUM_01_prior_art_verified.md`.
- Never edit AD-035 or AD-036.

## Report

Write the RESULT, under 50 lines, to `/Users/brock/GitHub/seldon/cc_tasks/2026-10-09_PA-001_prior_art_receipts_gate_RESULT.md`. It covers:
- the tool's receipt syntax;
- the gate's tests;
- recall, with its interval and the misses;
- library p95;
- the effort column before and after;
- every test gated, by repo;
- the icsp CI URL;
- AD-035 register records written;
- other unparsed labels found;
- suite numbers per repo (passed, skipped, xfailed, deselected, failed);
- premises found wrong;
- tokens and model.

Then run `seldon verify` and `seldon cc complete`, merge, and push.
