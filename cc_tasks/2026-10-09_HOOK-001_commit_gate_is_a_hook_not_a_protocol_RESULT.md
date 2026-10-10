# RESULT: HOOK-001, the commit gate is a git hook; the three refused register statements
**Date:** 2026-10-09. **Task:** `2ebfb15e`. **Model:** `claude-opus-5-5` (primary). **Addenda:** none existed. **Design:** `docs/design/AD-036_ADDENDUM_02_commit_hook.md` (AD-036 + addenda verify pass, ledger event `1e0dd463`).
**hooksPath cause (receipts in ADDENDUM 02 section 1):**
- Set in LOCAL config only (never global or system, so step 3 removed nothing above repository level): seldon `/Users/brock/Documents/GitHub/seldon/.git/hooks` (seldon-sel004 shares it) and arnold `/Users/brock/Documents/GitHub/arnold/.git/hooks`. Both moved to `~/GitHub` on 2026-06-19; both `.git/hooks` directories are gone. No hook ran anywhere.
- Arnold's ADR-012 post-commit and post-merge hooks, copied into `.git/hooks` by `install_hooks.sh`, were lost with them.
- What wrote the absolute path is not recoverable: `seldon prior-art search --internal "hooksPath"` returns `hits none` in all 7 roots, and "pre-commit hook" hits only AD-013 and AD-030-R3, which assumed a hook ("already pre-commit").
**Built (seldon `feat/HOOK-001`):**
- `seldon hooks install|status|pre-commit` (`seldon/core/hooks.py`): local `core.hooksPath=.githooks` (tracked); interpreter in local `seldon.python`.
- The pre-commit hook judges the index only: Prior art against the staged ledger (the verdict is staged with the note); `ruling_label_unparsed` and labels without a staged record; the staged register's chain.
- Graph-wide Tier A checks (including Governed docs, blocked by Issue `25da4d06`) stay with `verify --strict`. The reason is in ADDENDUM 02.
- `seldon verify` gains "Commit hook" (not installed, `--fix`; or `hook_bypassed`). `seldon dispatch once` points git at the tracked hook and launches nothing without it.
**Installed (merged and pushed, local `core.hooksPath` before -> `.githooks`):**
- seldon (old: the dead seldon path above); arnold `0eddb10` (old: the dead arnold path), with ADR-012 hooks rewired as by-path wrappers and `install_hooks.sh` deferring to seldon.
- Unset before: ai-readiness-kg `015a4f1c`, ai-workflow-design `a54ce41`, book_responsible_ai `72184b4`, brock_projects `16a989e`, census-web-concept-inventory `18d815c`, federal-survey-concept-mapper `1a12347`, icsp_notebook `78ec84b`, regs-comment-pipeline `5dad99f`, sas_graph_code_conversion `e44dcbb`, squiddy `1d714db`, TickBiteRisk `8c2ac8c`, usai-harness `542f52d`.
- Not installed:
  - seldon-sel004 shares seldon's config, but its `feat/SEL-004` checkout has no `.githooks`, so it runs no hook until it merges main.
  - webdesktop and ai-demos hold a `seldon.yaml` only in a subdirectory (`services/`, `leibniz-pi/`). The hook reads the repository root's config, so it would judge nothing there; it is not installed. brock_projects/nsf_aiday2026 is inside brock_projects, which is covered.
**Hook p95:** 1.03 s (median 0.90 s, max 1.03 s) over 10 design-note commits on seldon, the heaviest config (7.5 MB staged ledger). Bound 5 s. `docs/evidence/hook001/hook_timing.json`.
**Planted refusal and bypass:**
- Live, in a throwaway seldon worktree: `git commit` of a note without prior art was refused by the hook (exit 1, quotes AD-036-R4). `--no-verify` committed it, and the verify check reported `hook_bypassed: c5ed1a237b74 docs/design/AD-099_planted.md`.
- Tests: `tests/test_hooks.py` (18). They cover the planted refusal, the staged-only rule both ways, the label and register refusals, bypass (open and healed), install by path (git runs the tracked file; worktree), and §7.9 (unsetting `core.hooksPath` or deleting the hook lets the note through, and the refusal test then fails).
**The three records (AD-033-R8 re-run with the note's id, title and path in context; `scripts/hook001/`; about 12.4k weighted tokens):**
- AD-036-R7: passed; landed as amend `00248`.
- AD-036-R4: passed the validator; refused again by the AD-033-R3 deictic check. Text: "The prior-art gate shall refuse at two points: ... write the verdict to the governed ledger beside the note's hash; ...". Reason: `'the note'` (an anaphor of "a design note" earlier in the same sentence). It stays flagged.
- AD-035-R8: validator failed it, complete=false. Text: "Seldon shall not deploy managed settings (an `availableModels` allowlist or a denial of superseded models) for model selection, and shall enforce model order at the call sites under R3 to R6 with the receipt as proof; this shall be revisited if a call site is found that R3 cannot reach." Reason: it drops the two reasons (allowlist binds interactive sessions; denial disables fallback targets). It stays flagged.
**Suites (passed/skipped/xfailed/deselected/failed):** seldon 2304/0/0/0/0. squiddy 1938/0/0/0/1 (`test_x001_conformance` harvest_walk_complete, pre-existing, as in PA-001). Other repositories: only `.githooks/` (and arnold's installer script) changed, no test references either, and their suites were not re-run.
**Tokens:** main session about 0.33M (context counter; estimate was 0.6M); statement pass about 12.4k weighted (sonnet, `register_statement`, effort low).
