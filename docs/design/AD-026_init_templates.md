# AD-026: `seldon init` Project Templates

**Date:** 2026-04-21
**Status:** Accepted
**Supersedes:** Hardcoded `_BOOTSTRAP_TASKS` in `seldon/commands/init.py` (removed in this AD).
**Related:** AD-004 (per-project database isolation).

## Context

Prior to this AD, `seldon init` unconditionally seeded five paper-specific `ResearchTask` artifacts (`SETUP-01` through `SETUP-05`) into every new project's graph, regardless of project type. The strings lived in a Python module-level constant.

An investigation triggered by an apparent cross-project contamination report (usai-harness showing tasks that looked like they belonged to a paper project) found:

1. Per-project database isolation per AD-004 was intact — the tasks were not leaking between graphs.
2. The tasks were being re-seeded into every project's graph at init time, byte-identical because they came from the same hardcoded list.
3. For non-paper projects (code, research notebooks, tooling), the tasks were irrelevant noise that polluted `seldon task list`, `seldon go`, and the MCP tools.

Full diagnosis: `notes/2026-04-21_cross_project_contamination_diagnosis.md`.

## Decision

Project-init bootstrap state is now data, not code. Templates are YAML files under `seldon/templates/` loaded by `seldon.templates.loader`.

Template schema (minimum required keys, extensible):

```yaml
name: <str>                # must match filename stem
description: <str>         # human-readable one-liner
bootstrap_tasks:           # list, may be empty
  - description: <str>
    name: <str>            # optional
```

Unrecognized top-level keys are preserved in the loaded dict so that future extensions (directory scaffolding, `seldon.yaml` overrides, template composition) can be added without breaking the loader contract.

`seldon init <project_name>` accepts:

- `--template <name>` (default `blank`) — selects which template to apply.
- `--list-templates` — enumerate available templates and exit.
- `--force` — proceed even if the target Neo4j database already contains artifacts.

The selected template name is recorded at `project.template` in the generated `seldon.yaml` so the init decision is auditable and reproducible.

Two templates ship:

- **`blank`** — empty. The default. Appropriate for any project where the user wants to write their own tasks.
- **`paper`** — the five `SETUP-01..05` manuscript tasks from the prior hardcoded list. Preserves onboarding for paper projects; opt-in via `--template paper`.

A secondary `init` hardening change is bundled with this AD: `init` now verifies the target Neo4j database contains no Artifact nodes before proceeding, and fails loudly if it does. `--force` overrides for explicit re-init. This closes the silent-attach gap where two directories with colliding slugs could unknowingly write to the same database.

## Consequences

**Positive:**

- New non-paper projects start with a clean task graph. No ghost tasks in `seldon task list`, `seldon go`, or MCP tool output.
- Adding a new project type is a new YAML file, not a Python change. Supports growth without code churn.
- Template choice is auditable (recorded in `seldon.yaml`).
- Silent database attachment is eliminated; init either creates fresh or refuses and explains why.

**Negative / migration:**

- Existing `seldon.yaml` files predating this AD have no `project.template` field. This is tolerated — the field is informational, not load-bearing. Old projects continue to work; future re-inits will record the chosen template.
- Existing project graphs that have the five `SETUP-01..05` artifacts from prior `init` runs still contain them. Retroactive cleanup is a separate follow-up task; out of scope here.

**Defense in depth:**

- The emptiness check catches the slug-collision case where two `seldon init` runs with the same project name write to the same database. It does NOT prevent a user from editing `seldon.yaml` by hand to point at a shared database, but `seldon verify` and `seldon go` both read project-specific paths (`source_file` values under `project_dir`) and would surface anomalies in practice.

## Alternatives considered

1. **Remove `_BOOTSTRAP_TASKS` entirely, no replacement.** Simpler, but loses a useful onboarding cue for paper projects and provides no extension path for other project types.
2. **Separate `seldon template apply <name>` subcommand.** More flexible but higher surface area; premature at current scale. Template selection at init time is sufficient for now.
3. **Make bootstrap tasks a field of `domain/*.yaml`.** Conflates domain (state machine, property schemas) with project-type onboarding. Domain is a coarser axis than template.

Chosen approach (data-driven templates as a new concept) is orthogonal to domain and scales to arbitrary project types without touching code.

## Affected code

- `seldon/templates/` — new: loader, `blank.yaml`, `paper.yaml`.
- `seldon/commands/init.py` — rewritten: template flags, emptiness check, `project.template` recorded.
- `tests/test_templates.py` — new.
- `tests/test_init.py` — new.
- `tests/test_session_commands.py::TestInitBootstrapTasks` — rewritten to exercise the template loader path.

## Retroactive cleanup (separate task)

Delete the orphan `SETUP-01..05` ResearchTask artifacts from project graphs initialized before this AD (`seldon-arnold`, `seldon-icsp-notebook`, `seldon-sfv-paper`, `seldon-usai-harness`, likely others). Filed as a follow-up task; out of scope here.
