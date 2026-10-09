# MODEL-002: effort is explicit per role, tests never call a model unasked, icsp CI runs the model gates

**Repo:** seldon (primary), with `/Users/brock/GitHub/arnold` and `/Users/brock/GitHub/icsp_notebook` by absolute path, each on its own `feat/MODEL-002` branch. L4: commit, merge, push in every repo touched.
**Date:** 2026-10-09. **Authored by:** a Desktop session in squiddy (OODA on MODEL-001's RESULT).
**Governing:** `/Users/brock/GitHub/seldon/docs/design/AD-035_config_driven_model_selection.md` (R1, R3, R6). Read `/Users/brock/GitHub/seldon/cc_tasks/2026-10-09_MODEL-001_config_driven_model_selection_RESULT.md` first. Glob and read sibling `*MODEL-002*ADDENDUM*.md`.
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Model:** primary
**Spend:** est. 1M tokens for this session. No harness model call.
**Network:** none beyond git push.

## Step 0
If this task is already `in_progress` in the seldon graph, or a dispatcher lease names this file, stop.

## Part A: the defect, with its premise wrong in MODEL-001

`models/registry.yaml` gives 20 of 22 roles `effort: default`. Its comment says this "keeps today's behavior". It does not.

`default` passes no `--effort`, so the effort level is whatever the CLI's default is for the model the lock serves. That default moved with the bump:
- Opus 5 and Sonnet 5 default to `high`.
- Opus 5.5, Sonnet 5.5 and Haiku 5.5 default to `medium`.

Source: code.claude.com/docs/en/model-config, "Adjust effort level", read 2026-10-09.

So MODEL-001 lowered effort on every opus and sonnet role, invisibly, by the same mechanism AD-035 exists to stop. The model was made explicit; effort, the second half of the instrument, was left implicit.

## Part B: ruling to implement (AD-035-R1 extended)

1. **`effort: default` is refused.** `seldon.models` fails loudly on it, the same way it fails on an unknown role. Every role names a level.
2. **Values.** Set each role to the documented default of the model its family now resolves to. That makes today's actual behavior explicit and leaves it unchanged:
   - `medium` on the opus, sonnet and haiku roles. Anthropic's migration guidance is to start Opus 5.5 at `medium` rather than carry over Opus 5's `high`.
   - `high` on the fable roles.
   - Roles that already name a level keep it: `document_extractor` and `demand_judge` stay `high`.
   - Rewrite the file's comment to say this. Remove the "keeps today's behavior" sentence.
3. **Every launcher passes `--effort <level>` from the registry.** Every receipt records the requested effort beside requested and served model.
4. **Lock bumps check effort too.** `seldon models refresh` records each family's default effort from the CLI it installed, if the CLI exposes it; if not, from the version note in the docs, cited. A bump that changes a family's default effort is written into the `models_lock_bumped` event, so the next move is visible even though registry values no longer depend on it.

## Part C: tests never call a model unasked (arnold)

MODEL-001 found arnold's live seed-scan test makes a real model call whenever `claude` is on PATH. That is undeclared spend and a non-hermetic suite.
- Gate it behind an explicit opt-in environment variable. Name the variable in the test's skip reason.
- Default is skip.
- Inventory the other arnold tests for the same pattern, and every repo MODEL-001 touched. Search for a subprocess or launcher call reachable from a test without a fake. Gate every hit the same way, and list them in the RESULT.

## Part D: icsp CI

icsp_notebook's CI does not install seldon, so 18 tests that hold the AD-035 gates skip there.
- Install seldon in CI from the same pin the repo's `models` extra names.
- Make those 18 run.
- Green is done: the run URL is the evidence.

## Tests
Each must fail before the change:
- `effort: default` is refused;
- every registry role resolves to a named level;
- a launcher's argv carries `--effort` equal to its role's level;
- the receipt records effort;
- arnold's suite with `claude` on PATH and the opt-in unset makes zero subprocess calls to it. Use a PATH shim that records invocations.

## Report
RESULT under 40 lines at `/Users/brock/GitHub/seldon/cc_tasks/2026-10-09_MODEL-002_explicit_effort_hermetic_model_tests_RESULT.md`. It covers:
- the registry's effort column before and after;
- every launcher changed;
- every test gated, by repo;
- the icsp CI run URL;
- suite numbers per repo (passed, skipped, xfailed, deselected, failed);
- premises found wrong;
- tokens and model.

Close out with `seldon verify`, `seldon cc complete`, then merge and push.
