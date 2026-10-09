# RESULT: MODEL-001, model selection config-driven, locked and receipted (AD-035)
**Date:** 2026-10-09. **Task:** `6efdd767`. **Session model:** `claude-opus-5-5`, matching the lock's opus. **Addenda:** none existed.
**Inventory (Part A).** `docs/evidence/model001/inventory.md`, plus its classifier `classify_inventory.py`. It covers 36 repositories and 100,008 hits:
- launcher 68, config 228, task_header 5, fixture 361, history 99,163, false_positive 183.
- `fixture` and `false_positive` are classes added because the four given classes do not cover them.
- The Part C agents reclassified rows; the details are in their commit messages. Script `--model` defaults are config, not launchers. Launchers the regex missed: dixie `run_hermetic`, measuring-ai-economy `mcp_base.py`, arnold `morning_brief.py`, `critic.py` and `map_custom_to_canonical.py`, icsp `reg_battery/runner.py`, squiddy `extract.py:854` and three tools.
**Lock and probes (Part B).** `models/models.lock.yaml`, written by `seldon models refresh` with CLI 2.1.295 (`npm install --prefix ~/.local/share/seldon/claude-cli/2.1.295`):
- `fable=claude-fable-5-1`, `opus=claude-opus-5-5`, `sonnet=claude-sonnet-5-5`, `haiku=claude-haiku-5-5`.
- All four agree with the expected heads. Each probe's `modelUsage` held exactly one key and no side models.
- 13,589 tokens, $0.11 imputed. Evidence: `docs/evidence/model001/refresh_2026-10-09.json`. Event: `models_lock_bumped` `ccc85275`.
- The registry has 7 required roles plus 15 by use, taken from the inventory and the agents' ROLES_NEEDED lists.
**Launchers changed (Part C), one agent per repository except seldon, which I did.** Every launcher execs the lock's CLI with `--model <id>`, the four `ANTHROPIC_DEFAULT_*_MODEL` ids and `switchModelsOnFlag:false`, and records a receipt. A mismatch stops the unit as `model_substituted`.
- **seldon** `a11e041` (+`20f8a48`, `a37766e` roles): dispatcher in-place and worktree paths. Changes:
  - It launches with the role named in the `**Model:**` header, or `primary`.
  - It runs with `stream-json`, and the receipt goes in `dispatch_finished`.
  - A mismatch blocks the task, or refuses the merge.
  - The `dispatch.cli` and `dispatch.model` keys are now refused.
- **squiddy** `c1fa445`, `39cc642`: `model_client` (role, receipt, `ModelSubstitutedError`), `calls.py`, the daemon (`cli_not_piloted`), `extract`/`factory`/`downstream`/`teacher`/`quality` and 10 tools. Configs: control.yaml moved to 2.1.295 with a dated note that the next run is a new pilot, valve closed; `teacher.role`; `init_defaults` roles. Spec 0.21.0, sections 3, 4.2, 8.1, 13. The `models` extra is pinned to seldon.
- **ai-readiness-kg** `6de1e337`, `9720d796`: `model_stub.py` is the only exec site; consumers; scripts take `--role`. The primary probe judge moved opus-4-8 → `judge` (fable) to stay independent of the extractor. The G1 consumer and control re-pilot (R7). The seldon pin moved to `a11e041` and the brief pack was regenerated.
- **arnold** `d3b5d82`: critic, reply ingest, morning brief, parse_exercises and two mappers. Configs name roles; the arnold-evidence transport moved to 2.1.295 (new pilot).
- **icsp_notebook** `34cefe6`: `kg/claude_launch.py`, conflict adjudication, the A3 panel, the mentions passes, the E3 client and the REG runner. The E3 checkpoint key now includes the lock id.
- **dixie** `6b49fa5`: `run_hermetic` uses `document_extractor`.
- **measuring-ai-economy** `3059783`: triage and the MCP fetcher. Postgres migration 012 adds `model_receipt` columns; it was applied to the live local `wintermute` DB because that DB is what the suite runs against.
- **Not migrated, logged:**
  - census-mcp-server and federal-survey-concept-mapper: Messages-API instruments of finished studies (R7).
  - usai-*: a different provider and catalog.
  - trustgraph-fork `claude_cli`: the sealed 2026-08-23 benchmark fork.
  - seldon `scripts/sel002` and seldon-sel004: completed SEL-002, and a stale clone.
**Gates (Part D).** `cc register` (after `ensure_fresh`) and dispatch candidacy refuse a `**Model:**` header or code-block `--model` naming an id not in the lock, quoting the lock. The header takes a role or a lock id. Squiddy conformance item 36 `configs_name_roles` (AD-035 R4) has a planted control, and the control is caught.
**Suites** (passed / skipped / xfailed / deselected / failed):
- seldon 2244/0/0/0/0.
- squiddy 1923/0/0/0/1. The failure is item 15 harvest walk: ai-readiness-kg subtrees added 2026-10-06 with no disposition; it failed on main before this task.
- ai-readiness-kg 3200/3/41/0/1. The failure was the adopter runbook, generated from the pin I bumped; it was regenerated and the file reran 74 passed.
- arnold: root 1000/4/0/1/1; training-MCP 383/0/1/0/1; dashboard 460/0/0/0/8. The failure set is identical to the baseline.
- icsp_notebook 776/0/0/0/0. dixie 100/0/0/0/0. measuring-ai-economy 256/0/0/0/0.
- Serial dispatch transcript: re-recorded. It equals the old fixture byte for byte once exactly the MODEL-001 additions are stripped; the strip check printed `True`.
**Premises found wrong.**
- The inventory over-counts ai-readiness-kg launchers (13 → 1 exec site) and misses about 9 launchers elsewhere.
- ai-readiness-kg's `effort: high` was never passed to the CLI; it is now.
- icsp `kg/models.yaml` is not all USAi.
- arnold's conda env and squiddy's `.venv` could not import seldon until an editable `--no-deps` install.
- arnold's live seed-scan test makes a real model call when `claude` is on PATH.
- A judge's Q-005 effort is `high`, hence `demand_judge`.
**Open.**
- icsp CI does not install seldon, so 18 tests skip there.
- The `--settings` and `--setting-sources ""` combination is verified only by probe acceptance, not by forcing a classifier flag.
- link/homograph judge reruns and the squiddy library extraction are new pilots before use.
- `seldon verify`: 1 issue. 12 governed docs are uncataloged because `governed/squiddy.pin` (4ac50a5) is stale; this predates the task and is tracked as Issue `25da4d06`.
**Tokens:** main session about 0.37M, read from this session's budget counter; Part C agents 1.63M (squiddy 442k, ai-readiness-kg 331k, icsp 293k, arnold 275k, measuring-ai-economy 179k, dixie 115k); probes 13.6k. Total about 2.0M, against an estimate of 4M.
