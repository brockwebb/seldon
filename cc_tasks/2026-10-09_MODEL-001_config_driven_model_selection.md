# MODEL-001: model selection is config-driven, locked and receipted, on every launcher on this machine

**Repo:** seldon (primary). Branch `feat/MODEL-001` from main. Cross-repo edits by absolute path in `/Users/brock/GitHub/squiddy`, `/Users/brock/GitHub/ai-readiness-kg`, `/Users/brock/GitHub/arnold` and any other repo the inventory finds, each on its own `feat/MODEL-001` branch. L4: commit, merge, push in every repo touched.
**Date:** 2026-10-09. **Authored by:** a Desktop session in squiddy. **Seldon task:** `6efdd767`.
**Governing:** `/Users/brock/GitHub/seldon/docs/design/AD-035_config_driven_model_selection.md`. Read it in full first. Glob and read sibling `*MODEL-001*ADDENDUM*.md` before starting.
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Model:** this session's own. Confirm it is `claude-opus-5-5` or `claude-fable-5-1` and state it in the RESULT. This task builds the lock that later tasks name roles from.
**Spend:** est. 4M tokens for this session, plus R2's four probe calls (under 20k). Print session usage at the end.
**Network:** allowlist: registry.npmjs.org, api.anthropic.com (the R2 probes through the CLI). Plus git push.

## Step 0
If `6efdd767` is already `in_progress` in the seldon graph, or a dispatcher lease names this file, stop. It is already running.

## Part A: inventory
Search every repo under `/Users/brock/GitHub` (exclude `.venv`, `node_modules`, `.git`, `.worktrees`, `build`) for every model call site and model reference. Look for:
- `--model`, `claude -p`, `model_client`, `alias:`, `roles:`
- `ANTHROPIC_DEFAULT_`, `ANTHROPIC_SMALL_FAST_MODEL`, `cli_path`, `cli_version`
- and the regex `claude-(opus|sonnet|haiku|fable)-[0-9]`

Classify each hit:
- `launcher`: makes a call;
- `config`: names a model;
- `task_header`;
- `history`: a sealed record or Result. Never edit these.

Write the table to `/Users/brock/GitHub/seldon/docs/evidence/model001/inventory.md` with file:line for every row.

## Part B: registry, lock, refresh (AD-035 R1, R2)
- Build `models/registry.yaml` with roles `primary`, `extractor`, `rater`, `adjudicator`, `teacher`, `judge`, `background`.
- Map each role to a family and effort, taking today's intent from the inventory: what each role is used for now, moved to the newest member of its family. `judge` is `fable`. `background` is `haiku`.
- Build `models/models.lock.yaml`, the accessor `seldon.models.resolve(role)`, `seldon models show`, and `seldon models refresh`, exactly as R2 says:
  - install the CLI into `~/.local/share/seldon/claude-cli/<version>` by `npm install --prefix`, never global;
  - make one probe per family alias and read `modelUsage`;
  - write the lock and append the `models_lock_bumped` event;
  - write evidence to `docs/evidence/model001/refresh_<date>.json`.
- Run it.
- Expected heads, verify do not assume: `claude-fable-5-1`, `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5`. If a probe disagrees, the probe wins and the RESULT says so.

## Part C: launchers (R3, R6)
Every `launcher` row:
- resolves its role through the accessor;
- passes `--model <id>`;
- sets `ANTHROPIC_DEFAULT_{OPUS,SONNET,HAIKU,FABLE}_MODEL` from the lock;
- execs the lock's CLI;
- sets `switchModelsOnFlag: false` through `--settings`;
- records requested and served model per call.

A served id that differs from the requested id stops the unit with `model_substituted`.

Squiddy specifics:
- `squiddy/model_client.py` and the extraction daemon use the accessor.
- `graphs/library/extract/control.yaml` `transport.cli_path` and `cli_version` move to the lock's CLI. Edit by a new dated comment line, keeping history, as that file's convention requires.
- `teacher.alias` becomes `teacher.role: teacher`.
- `init_defaults.yaml` `engine.extract.roles` names registry roles.
- Note in the control file that the next extraction run is a new pilot (H-006 R-30). The extract valve stays closed.

The seldon dispatcher launches CC sessions with the `primary` role's id and the env block.

Use one agent per repo, in parallel.

## Part D: gates (R4, R5)
- `seldon cc register` and dispatcher candidacy refuse a task whose `**Model:**` header or code-block `--model` names an id not in the lock. Quote the lock in the refusal.
- Add a `**Model:**` header to the dispatcher's recognized grammar. It takes a role name, or an id equal to the lock's.
- Squiddy conformance gains an item: a config value that is a model alias or id fails, citing AD-035 R4. Seed its planted control.

## Tests
Each must be a test that fails before the change:
- a planted stale id in a task header is refused;
- a planted alias in a squiddy config fails conformance;
- a fake CLI that reports a different served model raises `model_substituted`;
- `resolve` on a missing role fails loudly;
- `refresh` against a fake CLI writes the lock and event once and is idempotent on rerun;
- the launcher env block carries all four lock ids.

## Report
RESULT under 50 lines at `/Users/brock/GitHub/seldon/cc_tasks/2026-10-09_MODEL-001_config_driven_model_selection_RESULT.md`. It covers:
- the inventory counts by class;
- the lock as written and the probe evidence;
- every launcher changed, by repo;
- each suite's numbers (passed, skipped, xfailed, deselected);
- premises found wrong;
- this session's model and tokens.

Close out with `seldon verify`, `seldon cc complete`, then merge and push in every repo touched.
