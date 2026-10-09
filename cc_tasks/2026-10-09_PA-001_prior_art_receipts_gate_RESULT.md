# RESULT: PA-001, the prior-art receipts gate (AD-036), declared effort, hermetic tests, AD-035 records
**Date:** 2026-10-09. **Task:** `459f463e`. **Model:** `claude-opus-5-5` (primary). **Addenda:** none existed.
**Receipt syntax (Part A).** `seldon prior-art search --internal|--library`, `verify`, MCP `seldon_prior_art_search`/`_verify` (`seldon/core/prior_art.py`).
- `- library receipt: query "<q>" | release <file> sha256:<64> | rows <id>, ...`
- `- internal receipt: query "<q>" | repo <name>@<40-hex> | hits <path>:<line>[#sha256=<12>], ...`
- `- web receipt: url <u> | retrieved <date>`
- `rows none`/`hits none` is the only form "no prior art" takes. Grammar and two departures from R3 (files read from git objects so receipts re-run at the named commit; top-level `docs/*.md` added to the corpus) are in `AD-036_ADDENDUM_01_self_test.md`.
**Gate (Part B).** `seldon verify` check "Prior art" (Tier A, `--fix` verifies) and `cc register` refuse a non-baseline note without a passing verdict for its bytes. Verdicts are `provenance` events in `governed/ledger/events.jsonl` via `squiddy.ledger.append`. Baseline: 56 notes, `docs/design/AD-036_baseline.txt`. Tests `tests/test_prior_art.py` (28):
- planted note refused at commit and at registration; wrong row id and wrong line both fail `id_not_returned`;
- bare "no prior art" fails; web-only External fails; malformed fails;
- each gate removed in turn lets the planted note through (§7.9).
**Recall (Part C).** Pre-registered `3c29394` before any run. 8/18 at top 20, recall 0.444, Wilson-95 [0.246, 0.663]: **FAIL** vs 0.70.
- Misses: G5-01, 03, 07, 10, 11, 13 (no all-terms match); G5-06 (rank 47), 12 (46), 14 (24), M-03 (79).
- Design task `ace164ee` (governed-graph arm). Does not block Part B.
**Library p95 (Part D)**, 24 frozen DQ questions, k=10, checkpointed harness with SIGKILL test: warm **0.32 s PASS**; cold (first search of a process) **21.1 s FAIL** vs 10 s. Design task `f4b2ffb4`.
**Effort (R8).** Before: every role `default` except `document_extractor`/`demand_judge` `high`. After: opus/sonnet/haiku roles `medium`, fable roles (`judge`) `high`, those two `high`; new roles `register_statement` (sonnet, low) and `auditor` (opus, medium).
- `default` is refused. Every launch passes `--effort` and `CLAUDE_CODE_EFFORT_LEVEL` (the docs rank the env var equal to the flag). Receipts carry `effort`. `refresh` records documented defaults (code.claude.com model-config, read today) and flags `unverified` families.
**Tests gated (R9), `LIVE_MODEL_CALLS=1`, each repo with a PATH-shim zero-call test and a planted positive control:**
- arnold `tests/cli/test_seed_scan.py::test_seed_scan_observations_dry_run_runs_and_prints_stats`.
- ai-readiness-kg `tests/test_dispatch_config.py` (2 tests: `env -i` drops the fixture lock).
- seldon, squiddy, icsp_notebook, dixie, measuring-ai-economy: none needed.
- Merges: seldon (this branch), squiddy `244668c`, ai-readiness-kg `59a667af`, arnold `220ccde`, icsp `8e2feac`, dixie `3c04150`, measuring-ai-economy `04269ac`.
**icsp CI:** https://github.com/brockwebb/icsp-notebook/actions/runs/37980327901 green; seldon installed from the new `models` extra pin, 642 passed, 0 skipped (was 618 + 18 skipped).
**AD-035 register (Part F).** AD-035-R1..R8 and AD-036-R1..R9 (also unregistered) written via `scripts/pa001/register_rulings.py`.
- AD-033-R8 pass via SEL-002's prompts on the lock client: 17/17 validator pass, about 65.5k weighted tokens. 14 landed; AD-035-R8 and AD-036-R4, R7 refused by the AD-033-R3 deictic check ("this decision", "the note"), kept verbatim, flagged failed.
- `ruling_label_unparsed` added to the decision check, with a planted test; the heading pattern was added to `seldon.yaml`.
**Other unparsed labels (reported, not fixed):** seldon `docs/design/evolution_burst_2026-04/phase_c_retirement_list.md` (5); arnold `docs/adr/013-canonical-training-vocabulary.md` (3). Squiddy has none.
**Self-test (G).** AD-036 and AD-035 as written: both FAIL (prose, no receipts). With addenda carrying the tool's receipts, AD-036 passes 14/14 receipts (event `768cf043`) and AD-035 passes (`cd4e5e9c`). Every library row AD-036 cites reproduced.
**Suites** (passed/skipped/xfailed/deselected/failed):
- seldon 2282/0/0/0/0.
- squiddy 1938/0/0/0/1 (pre-existing item 15 harvest walk).
- ai-readiness-kg 3203/4/41/0/0.
- arnold root 1002/5/0/0/1, MCP 383/0/1/0/1, dashboard 460/0/0/0/8 (all pre-existing).
- icsp 782/0/0/0/0. dixie 104/0/0/0/0. measuring-ai-economy 261/0/0/0/0.
**Premises found wrong.**
- No git pre-commit hook exists (`core.hooksPath` names a removed `Documents/` path), so "commit gate" is `seldon verify` by protocol, as for the other Tier A checks.
- squiddy was not importable from seldon's interpreter; installed editable `--no-deps`.
- AD-036 itself had no register records.
- seldon's paper-audit launcher ran bare `claude` from PATH (missed by MODEL-001); now role `auditor` from the lock.
- The header's "zero harness model calls" conflicts with Part F's R8 statement pass; Part F was followed (under cap).
- icsp had no `models` extra; one was created.
- `governed/squiddy.pin` stale (Issue `25da4d06`): 19 governed docs uncataloged, the one `seldon verify` issue.
**Tokens:** main session about 0.42M (budget counter); Part E agents 0.98M; statement pass about 65.5k weighted. Total about 1.47M against 3M estimated.
