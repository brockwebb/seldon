# MODEL-002 ADDENDUM 01: any named model, with a per-model parameter profile

**Date:** 2026-10-12. **Authored by:** Desktop session, on the operator's correction of the same day.
**Amends:** Parts A, B and C of the base task. Part D is unchanged. Read this before any step.

## The correction

The operator: a workflow is a specification, and which model does a step is a parameter of it. The orchestrator calls whatever named model is most effective for that step; Opus 4.8 as first-pass author is one agent among others. Defaulting to the newest model is right as a default and wrong as the only option. Different models accept different parameters (effort levels, or none, or other settings); that is configuration of what each model allows, not a special case.

The base task treated the pin as an exception bolted onto a family-only registry. The defect is the registry's shape: it knows families, not models.

## Prior art

- OpenRouter's Models API carries a `supported_parameters` array on every model object, listing which request parameters that model accepts, and lets clients filter models by it (openrouter.ai/docs/models).
- The lockfile pattern already cited in AD-035 §2: a manifest may name a range or an exact version, and the lock records what each resolved to.

## Amended rulings (replace the base task's R9 to R13 in the addendum note)

- **AD-035-R9.** A role names either a family (resolved to the family's newest, the default) or a specific model id. Neither is privileged; both are lines of configuration.
- **AD-035-R10.** The registry carries a `models:` catalog keyed by model id, each entry declaring its `supported_params` (for example `effort: [low, medium, high, xhigh, max]`, or `effort: []` when the model takes none). Family heads get entries too. `refresh` probes every model a role names, records served id and availability in the lock, and never fails the lock because one named model is unavailable.
- **AD-035-R11.** A role's declared parameters are checked against its model's `supported_params` at registry load. A parameter the model does not support is refused at load, naming the role, the parameter and the model; it is never silently dropped at launch. The launcher passes exactly the declared, supported parameters.
- **AD-035-R12.** A role whose named model is unavailable fails as `model_unavailable`. It never falls back to another model; that is the substitution R6 exists to stop. R5 accepts any id the lock marks available.

The base task's R13 (checker and calibration) is dropped from the addendum note: AD-037 already governs it and nothing about it changes.

## Amended steps

- **Part B:** implement the catalog and R11's check in place of the base task's pin-only mechanism. The tests in the base task stand, re-read against the catalog, plus: a role declaring an effort its model's profile excludes is refused at load; a model with `effort: []` launches with no `--effort` flag and no `CLAUDE_CODE_EFFORT_LEVEL`. AD-036-R8 still holds for any model whose profile has effort levels: the role names one.
- **Part C:** role `author` names model `claude-opus-4-8`. Fill its `supported_params` by measurement, not assumption: probe it once with no effort flag and once per effort level, and record which the CLI accepts. Set `author`'s effort to `high` if accepted, otherwise to whatever the profile allows, and say which in the RESULT. If the model is not served, record that and skip Part D; there is nothing to escalate.
