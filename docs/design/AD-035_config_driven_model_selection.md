# AD-035: Model selection is config-driven, locked, and receipted

**Date:** 2026-10-09. **Status:** accepted (operator defect, L4 self-executing). **Task:** ResearchTask `6efdd767` (MODEL-001).
**Author:** Desktop session (squiddy thread SQ6).

## 1. The defect

The operator orders which models run. Today nothing carries that order; agents and stale memory do.

Measured 2026-10-09:

- No model registry exists anywhere in `~/GitHub`. Models are named three ways:
  - by alias in configs: squiddy `squiddy/init_defaults.yaml` `engine.extract.roles` (extractor and rater `sonnet`, adjudicator `opus`), and `graphs/library/extract/control.yaml` `teacher.alias: opus`;
  - by ids typed into task files and Results from Desktop memory: `claude-opus-5`, `claude-sonnet-5`, `claude-fable-5-1`;
  - by whatever the interactive CLI resolves at launch.
- **The binary pin silently pins the model generation.** Squiddy's extraction daemon execs Claude Code 2.1.278 (H-006 R-30). Alias resolution lives in the binary: `opus` became Opus 5.5 at v2.1.280, `sonnet` became Sonnet 5.5 at v2.1.284, `haiku` became Haiku 5.5 at v2.1.293. Under 2.1.278, `opus`, `sonnet` and `haiku` mean Opus 5, Sonnet 5 and Haiku 4.5, and the 5.5 models cannot be requested at all. H-006 pinned the binary for reproducibility; the model pin came with it unrecorded.
- **Desktop memory carried a stale primary model** ("Opus 5 is the primary model"). That is the path by which superseded ids enter task files.
- **Silent substitution paths exist inside the CLI.** A safety-classifier flag re-runs a request on another model: from Fable 5.1, Fable 5 or Opus 5.5, biology flags go to Opus 5 and cybersecurity flags to Opus 4.8. An allowlist can substitute a family alias with another version. Neither change appears in any record this machine keeps.

Current family heads (2026-10-09): `claude-fable-5-1`, `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5` (Haiku 5.5 released 2026-10-07).

## 2. Prior art

**External** (searched 2026-10-09):

- Dependency lockfiles: npm `package-lock.json`, Cargo `Cargo.lock`, Poetry `poetry.lock`. Intent ("compatible with the latest 5.x") lives in the manifest; the resolved version lives in the lock; builds read the lock, never the manifest. This separates currency from reproducibility.
- Renovate and Dependabot: a bot detects an upstream release and proposes a lock bump as a recorded, reviewable change. Currency is automatic; the moment of change is explicit.
- MLflow Model Registry: named stages map a role to a concrete model version; consumers ask for the role.
- Claude Code model configuration (code.claude.com/docs/en/model-config, read 2026-10-09):
  - the alias version table, quoted above;
  - `ANTHROPIC_DEFAULT_{OPUS,SONNET,HAIKU,FABLE}_MODEL` fix what each alias, and background functionality, resolves to;
  - `--output-format json` returns the served model in `modelUsage`;
  - `switchModelsOnFlag: false` turns the classifier's silent switch into a visible refusal;
  - managed `availableModels` with `availableModelsMatch: exact` and `deniedModels` restrict selection machine-wide.

**Internal precedent** (searched: seldon, squiddy, ai-readiness-kg, arnold, icsp_notebook design notes and configs):

- Squiddy DN-042 R-176 (one machine-wide spend ledger): the pattern for one machine-wide registry.
- H-006 R-30 ("a new version is a config edit here and a new pilot"): the rule for what a bump costs a gated instrument.
- DN-006 and the 2026-09-18 Network header grammar: the pattern for a declared, machine-read task header checked at registration.
- DN-031 / INC-001: undeclared, invisible behavior is an incident class. A silent model change is the same class.
- Found no registry, no lock and no served-model check in any repository.

## 3. Rulings

## AD-035-R1. One registry, one lock, machine-wide, in this repo

  - `models/registry.yaml` holds intent: role to family, plus effort. Roles are named by use, for example `primary`, `extractor`, `rater`, `adjudicator`, `teacher`, `judge`, `background`.
  - `models/models.lock.yaml` holds the resolved model id per family, the CLI version that resolved it, the date and the evidence file.
  - `seldon models show` prints both. A Python accessor `seldon.models.resolve(role)` is the only way any code on this machine gets a model id.
## AD-035-R2. "Latest in family" is resolved by Anthropic's own resolver, the newest CLI

  - `seldon models refresh` installs the newest Claude Code into a versioned prefix (`npm install --prefix`, never the global install).
  - It runs one minimal `-p --model <alias> --output-format json` per family and records the `modelUsage` model id.
  - It writes the lock, appends a `models_lock_bumped` event naming old and new ids, and commits.
  - Cost is four short calls. It runs when a task is authored and when a run starts; the result is cached for the day.
## AD-035-R3. Launch from the lock, never from an alias

Every launcher sets the lock's ids into `ANTHROPIC_DEFAULT_{OPUS,SONNET,HAIKU,FABLE}_MODEL`, so CLI background work follows the lock too. It passes `--model <id>` for its role and execs the CLI version the lock names. Launchers: the seldon dispatcher, squiddy `model_client` and extraction daemon, ai-readiness-kg and arnold harnesses, and any other model call site the inventory finds.
## AD-035-R4. Configs name roles, not models

A config value that is a model alias or a model id fails conformance; it names a registry role instead. Desktop sessions and memory carry no model ids; a task file's `**Model:**` header names a role.
## AD-035-R5. Registration refuses a stale model

`seldon cc register` and dispatcher candidacy refuse a task whose `**Model:**` header, or whose `--model` argument in a code block, names an id not in the current lock. The refusal quotes the lock. Prose that cites history ("rated by claude-sonnet-5 in S-007") is not checked: it records what happened.
## AD-035-R6. Every call carries a served-model receipt

Each launched call records the requested id and `modelUsage`'s served id. A mismatch stops the unit with a named failure (`model_substituted`). Launched processes set `switchModelsOnFlag: false`, so a classifier flag becomes a recorded refusal and never a silent switch.
## AD-035-R7. Change only at a boundary

A run in flight keeps its lock entry to the end. A gated or sealed instrument re-pilots on a bump, per H-006 R-30. Sealed records keep the ids they were made with. Those are history, not staleness.
## AD-035-R8. Managed settings: evaluated, not deployed

An `availableModels` allowlist would also bind the operator's interactive sessions. Denying superseded models would also disable classifier fallback targets. R3 to R6 enforce the order where calls are made, and the receipt proves it. Revisit if a call site is found that R3 cannot reach.

## 4. Consequences

- Squiddy's extraction daemon moves its CLI pin to the lock's version. The next extraction run is a new pilot. The extract valve is closed, so nothing runs before then.
- Tasks authored after this lands state a role. The model appears only in the lock and in receipts.
