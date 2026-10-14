# AD-035 ADDENDUM 02: a role names a family or a specific model; the catalog is each model's parameter profile

**Date:** 2026-10-14. **Status:** accepted (L4, decided by the Desktop session that wrote the task and its two addenda,
on the operator's ruling and correction of 2026-10-12 and his scope direction of 2026-10-13). **Task:** MODEL-003,
ResearchTask `019844b9` (files `cc_tasks/2026-10-12_MODEL-002_pinned_roles_author_opus_4_8*.md`; the label MODEL-002
was already held by `2026-10-09_MODEL-002_explicit_effort_hermetic_model_tests.md`). **Amends:** AD-035 by adding
R9 to R12. R1 to R8 are unchanged; R2's "newest in family" stays the default.

## 1. The gap, measured

At seldon `ed77e29` (2026-10-13):

- `seldon/models.py`: a role mapped to a family; the lock held one id per family, the newest the CLI's alias resolved;
  `check_task_models` accepted only those ids; `load_registry` validated a role only by family and effort. There was
  no way to say "this role runs Opus 4.8". A task header naming `claude-opus-4-8` was refused by AD-035-R5, correctly.
- `models/models.lock.yaml` (resolved 2026-10-14, CLI 2.1.296): opus resolves to `claude-opus-5-5`.
- Whether `--model claude-opus-4-8` is served on demand was unmeasured. Measured 2026-10-14 under CLI 2.1.296: it is
  served exactly (`docs/evidence/model003/opus_4_8_effort_probes.jsonl`; the refresh evidence named in the RESULT).
- The CLI does not validate `--effort` per model: `--effort bogus` on `claude-opus-4-8` exited 0 and was served.
  A CLI probe therefore cannot measure which parameter values a model supports; it measures only that the model is
  served. Each profile's values come from a documented source, recorded beside the entry
  (`docs/evidence/model003/effort_profiles_api_reference.md`).

## 2. The operator's ruling

ai-readiness-kg `docs/design/2026-10-12_DN-014_executive_summary_brief.md` section 9, verbatim:

> Opus 4.8 writes; Fable 5.1 reads as the reviewer in a fresh context. The operator's standing rule: he can name any
> model for a role; defaults are the most recent models unless there is a reason otherwise. Opus 4.8 is chosen for
> authoring on the operator's experience writing the two books with it.

His correction of the same day (MODEL-003 ADDENDUM 01): which model does a step is a parameter of the workflow. The
orchestrator calls whatever named model is most effective for that step. "Newest" is the right default and the wrong
only option. Different models accept different parameters, and that is configuration of what each model allows. The
defect is the registry's shape: it knew families, not models. His direction of 2026-10-13 (ADDENDUM 02): Anthropic
models only for the MVP.

## 3. Prior art

### External

- Lockfiles, as cited in AD-035 section 2 (recalled, as AD-035 erratum 01 records for that section). A manifest may
  name a range or an exact version, and the lock records what each resolved to: Cargo `=x.y.z`, an exact version
  string in `package.json`. R9 is that split: a role names a family (a range, resolved to its newest member) or an id
  (an exact pin), and the lock records what was served.
- MLflow Model Registry, as cited in AD-035 section 2: a name maps to a specific model version.
- OpenRouter's Models API carries a `supported_parameters` array on every model object, listing the request
  parameters that model accepts (openrouter.ai/docs/models; cited by MODEL-003 ADDENDUM 01, not re-fetched). R10 and
  R11 take its shape and nothing else: no OpenRouter code, client, key or endpoint (ADDENDUM 02 section 2).
- The Claude API reference bundled with Claude Code CLI 2.1.296 (`claude-api` skill, `shared/model-migration.md` and
  `shared/models.md`, quoted with sha256 in `docs/evidence/model003/effort_profiles_api_reference.md`): Opus 4.8 keeps
  "the `low`/`medium`/`high`/`xhigh`/`max` effort levels", and "`effort` defaults to `high` when not set (same as
  Sonnet 4.6 and Opus 4.8)".
- library receipt: query "lockfile exact version pin dependency resolution reproducibility" | release library_graph_20261012_sq013_01_2026-10-12.json sha256:0989759c402ca41472806bdf9ab47529ba2eb5a6b25d0e75c1a6e29e650d4275 | rows lesson:2026-05-09_10_1145_3805621_3807648#p5:111:3187-3229, lesson:2026-05-09_10_1145_3805621_3807648#p5:110:2865-3185, lesson:2026-05-09_10_1145_3805621_3807648#p6:144:922-939
  - The library holds no package-management literature. The rows returned are off-topic (poisoning, benchmarks), so
    this is a failed search, recorded as one, and the lockfile citation above stays recalled.

### Internal

Opus 4.8 is already in use on this machine as a named model, outside any registry (the adjudicator role's `uses` in
`models/registry.yaml` names icsp_notebook's conflict adjudication on `claude-opus-4-8`):

- internal receipt: query "claude-opus-4-8" | repo icsp_notebook@68723d09c29f5be602c7caf95b1f154935dae4e3 | hits docs/mentions_burn_validation.md:31, docs/mentions_resolution_characterization.md:91, docs/conflict_analysis_report.md:62, docs/mentions_burn_validation.md:67
- internal receipt: query "claude-opus-4-8" | repo ai-readiness-kg@a95ae2e1cf5c5bf2c30090a0f80740a093a3d4ed | hits docs/research/2026-08-23_tgbench2_decision.md:3, docs/research/2026-08-27_chunked_vs_wholedoc_verdict.md:130, docs/research/2026-08-27_chunked_vs_wholedoc_verdict.md:146, docs/research/2026-08-27_edge_suppression_judge_verdict.md:7, docs/research/2026-08-27_pilot_instrument_verdict.md:11

AD-035 itself (section 1): Opus 4.8 is a classifier fallback target, so it was known to be served.

## 4. Rulings

- **AD-035-R9. A role names either a family or one specific model id.**
  - A family resolves to the family's newest member, the default (R2 unchanged). A model id is used exactly.
  - Neither is privileged; both are lines of configuration in `models/registry.yaml`.
  - A role names exactly one of `family` or `model`; the registry refuses a role naming both or neither.
- **AD-035-R10. The registry carries a `models:` catalog keyed by Anthropic model id, one parameter profile each, and `refresh` probes every model a role names.**
  - Each entry declares its `family` and its `supported_params`, for example `effort: [low, medium, high, xhigh, max]`, or `effort: []` when the model takes none. Family heads have entries too.
  - The catalog holds `claude-<family>-*` ids only; `load_registry` refuses any other prefix, so a non-Anthropic id cannot enter before its own task decides how it should work.
  - `seldon models refresh` probes each model a role names with `--model <id>` and records, under the lock's `models:`, the served id, `available`, and the evidence file. Served must equal the id exactly; anything else is `available: false` with the reason.
  - A failed probe never fails the family probes and never blocks writing the lock. The day's cache does not cover a named model the lock has never probed.
- **AD-035-R11. A role's declared parameters are checked against its model's `supported_params` at registry load.**
  - A parameter the model does not support, or a value it does not take, is refused at load, naming the role, the parameter and the model. It is never silently dropped at launch.
  - The launcher passes exactly the declared, supported parameters. A model whose profile is `effort: []` launches with no `--effort` flag and no `CLAUDE_CODE_EFFORT_LEVEL`. AD-036-R8 holds for every model whose profile has effort levels: the role names one.
  - A family role is checked at load against the head the documented-default table was read for. It is checked again at resolution against the head the lock serves when the catalog has that head. A bump to a head with no profile is named `profile_missing` in the `models_lock_bumped` event.
- **AD-035-R12. A role whose named model is unavailable fails as `model_unavailable`, and R5 accepts any id the lock marks available.**
  - It never falls back to another model: that is the substitution R6 exists to stop.
  - R5 accepts the family heads plus every named model the lock marks available. A `**Model:** <role>` header naming an unavailable model is refused, quoting the lock.
  - The four `ANTHROPIC_DEFAULT_*_MODEL` variables still carry the family heads. `--model` carries the named id, and the R6 receipt compares the served id with it.

AD-037's checker over a role naming a model maps by that model's catalog family (an opus model is read by fable), and
a calibration report stays per judge id over generator id. AD-037 governs both and nothing in it changes, so the base
task's R13 is not a ruling here (ADDENDUM 01).

## 5. First use

Role `author`: model `claude-opus-4-8`, effort `high`. The uses are ai-readiness-kg DN-014 section 9 and the
operator's book work. `high` is the model's documented default (section 3). The book work ran before the 5.5 models
moved the default to `medium`. The level is a documented default, not a measured one: no pilot has compared levels on
this task. CLI 2.1.296's own `--help` lists the five levels and states no per-model default; the lock evidence states
none either.
