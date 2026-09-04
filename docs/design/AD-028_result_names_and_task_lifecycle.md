# AD-028: Result Names, Transitional Units Fallback, and ResearchTask Terminal Semantics

**Date:** 2026-09-03
**Status:** Accepted
**Origin:** `cc_tasks/2026-09-03_seldon_defect_sweep_registry_lifecycle_ontology.md`, closing Seldon tasks `0bc41cfc`, `698d1d86`, `a3ba67a3`, `f951ed84`, `e3f751f6`, `1a23fd00`. Defects surfaced by ai-readiness-kg (`g1_freeze` RESULT §6.1–6.4, `g1_calibration` RESULT §3/§7.7).
**Related:** AD-006 (Result registry as first-class type); AD-013 (domain property schemas); AD-027 (`snapshot`, and the precedent for `category: system` on conditionally-set properties); AD-017 (central validity ontology).

## Context

Four defects, one root shape: the Result registry and the ResearchTask state machine each lacked a
property the downstream projects actually needed, so those projects encoded the missing information
in a property that already existed. The encoding then collided with that property's real meaning.

- **Results had no name.** `{{result:NAME:field}}` resolution in `seldon/paper/build.py` keys
  artifacts as `"result:<name>"` and always has. Nothing ever *set* a name, so projects stuffed the
  token key into `units`. In `seldon-ai-readiness-kg`, 3592 Results carry a token key in `units` and
  zero carry a name. 14 distinct `units` strings are shared by two or more Results, and some are
  simultaneously real units (`count`, `kappa`, `accuracy`).
- **Unknown provenance references were accepted silently.** `--data-name` / `--script-name` for a
  nonexistent artifact printed a warning and dropped the link, leaving a Result registered with no
  `computed_from` edge and no signal that one was intended.
- **`proposed` Results were unconditionally fatal at build time.** Internal and in-progress
  documents could not render at all, which pushed projects into bespoke resolver scripts.
- **A task whose premise turned out false had no honest terminal state.** `superseded` existed;
  `withdrawn` did not. A task that should never have been done could only sit in `proposed` forever
  or be falsely marked `completed`.

A fifth, structural issue sits under all of these: nothing recorded *which agent* was executing a
task, so two agents could and did execute the same task concurrently.

## Decision

### 1. `name` is the token key; `units` is a unit

`Result.name` is the stable key that `{{result:NAME:field}}` resolves against. Slug grammar
`^[a-z0-9][a-z0-9_.-]*$`, case-sensitive, ≤128 characters, **unique per project graph**. A collision
is a hard error naming the existing Result's `artifact_id`; no event is written.

`seldon result register --name` is **required for new registrations**, enforced at the CLI. The
property is deliberately **not** `required: true` in `research.yaml`, because Results registered
before this AD have no name and must stay valid. It is `category: system`: an identifier, not a
documentation gap for `seldon docs check` to report.

`units` means a real unit of measurement and nothing else. The authoritative vocabulary is
`seldon/domain/result_units_vocabulary.yaml`, inside the package so it survives a non-editable
install; `docs/conventions/result_units_vocabulary.md` explains it and points there. Configuration is
never loaded from `docs/`, which is not shipped.

### 2. The units fallback is transitional and must announce itself

When a `{{result:NAME:...}}` token matches no `name`, the resolver falls back to matching a Result by
`units` — but only when that `units` string is **not** in the vocabulary, so a real unit can never be
mistaken for a token key. Every fallback hit emits one warning line naming the token, so the fallback
set is visible in build output rather than silently load-bearing.

This is scaffolding for the migration window, marked `# TRANSITIONAL (AD-028)` at its single
definition site. It is removed in a later task, once the projects that depend on it have migrated.

### 3. Migration is by event, and classifies rather than guesses

`seldon result migrate-names [--dry-run] [--project-dir]` sorts every unnamed Result into exactly one
of four classes:

| Class | Meaning | Action |
|---|---|---|
| `migrated` | `units` is not a real unit and is unique | `name := units`, `units` cleared |
| `units_is_real_unit` | `units` is in the vocabulary | leave alone; the Result stays unreferenceable until a human names it |
| `ambiguous` | promoting would break name uniqueness, or the string is both a unit and a token key | **do not assign**; list in full for a human |
| `no_units` | no `units` at all | leave alone |

Migration writes **one combined `artifact_updated` event**, not bespoke event types:
`seldon/core/sync.py` silently skips event types it does not know, so a bespoke type would make every
migration vanish on replay. Nothing mutates the graph directly.

The `ambiguous` class is broader than the originating task file specified. That file defined it as
"units matches the vocabulary AND is used as a token key somewhere" — a definition that yields zero
in ai-readiness-kg, which has no `paper/` directory and therefore no token keys. The operative hazard
is a **name collision**, which would violate this AD's own uniqueness contract. Both conditions now
classify as ambiguous and each row reports which one applies.

### 4. Provenance references fail loud, and can be backfilled

An unknown `--data-name`, `--script-name`, `--script-id`, or `--script-path` is a hard error, exit
non-zero, **with no event written at all** — every reference is resolved and validated before
anything touches the graph. A Result whose provenance link was silently dropped is worse than no
Result.

`seldon result backfill-provenance --map FILE [--dry-run]` repairs existing graphs, emitting
`computed_from` / `generated_by` link events. An unknown name fails that row, continues the rest, and
reports at the end with a non-zero exit.

### 5. `--allow-proposed` renders state into the document

`seldon paper build --allow-proposed` makes SI-03 non-fatal and renders `<value> (proposed)` — the
resolved value, one space, the literal `(proposed)`. `verified` and `published` render unchanged, and
the default without the flag stays fatal exactly as before. The build summary prints the count of
proposed tokens rendered and the Result names.

The placement is safe because resolution ends in a bare `str(value)`: no number formatting, no
significant figures, no units suffix. That property is now pinned by a test, because the render form
depends on it.

### 6. `withdrawn` and `superseded` are distinct terminal states

`superseded` — the work was valid, something else overtook it. Already existed since 2026-06-18.
`withdrawn` — **the premise turned out false**; the work was never valid to do.

Both are reachable only from active states (`proposed`, `accepted`, `in_progress`, `blocked`) and
never from `completed` or `verified`: relabeling a finished task would corrupt the honest completion
record. Nothing is reachable out of either. Both require an operator-supplied `--reason`, stored as
`terminal_reason`, because the two are indistinguishable without one. `superseded` additionally takes
an optional `--superseded-by ARTIFACT_ID`, validated when present, writing a `superseded_by` edge.

`terminal_reason` is `category: system`, not `documentation`: absence is the normal case for every
task that ended another way, so counting it as a documentation gap would manufacture one false gap
per completed task. Same reasoning as AD-027's `snapshot`.

Rows already in `superseded` without a reason stay valid and are **not** backfilled. A reason
invented after the fact is not a reason.

### 7. Claims are recorded, and expiry is a report

The `accepted → in_progress` transition records `claimed_by` (`desktop`, `cc`, or a caller-supplied
agent id) and `claimed_at` (ISO-8601 UTC). Both are surfaced for `in_progress` tasks by
`seldon task list` and `seldon_task_list`.

`seldon task list --stale-claims HOURS` **reports** `in_progress` tasks claimed longer than HOURS
ago. It does not transition anything. Auto-release is deliberately out of scope: releasing a claim
that is merely slow, rather than dead, reintroduces the concurrent-execution failure this is meant to
prevent. HOURS is a caller argument, never a baked-in threshold.

### 8. Terminal states are excluded from task listings by default

`seldon task list` and `seldon_task_list` exclude terminal states by default; `--all` /
`state_filter='all'` includes them. This is a behavior change for existing callers of the CLI, which
previously listed everything.

## Consequences

- Every new Result needs a name. This is a breaking change to `seldon result register`, taken
  deliberately: the alternative is more Results whose identity lives in the wrong property.
- The units fallback is technical debt with a scheduled teardown, documented as such at its
  definition site. It is the one shortcut this AD accepts, and only because the migration cannot be
  atomic across projects.
- 23 Results in ai-readiness-kg (`count`, `kappa`, `accuracy`) stay unreferenceable by token until a
  human assigns names, and 40 more need human adjudication before that project's live migration.
  That is the correct outcome: the machine declines to guess which of three Results named `kappa` a
  citation meant.

## Notes on the originating task file

Recorded because the task file is immutable and these premises were contradicted by live state:

- **Relationship types do not live in the ontology.** The task directed adding edge types to the
  master `seldon-ontology` database. That database holds `OntologyTerm` vocabulary artifacts parsed
  from markdown, with five term-to-term edge types closed in `parser.py`. The validator that actually
  rejected `DataFile-[:GENERATED_BY]->Script` is `seldon/domain/loader.py::validate_relationship`,
  reading `relationship_types` from `research.yaml`. Executed literally, the task would have left the
  defect in place and added five pseudo-terms to the validity vocabulary. The edge types
  (`corrects`, `annotates`, `disputes`, `superseded_by`, and the widened `generated_by` /
  `computed_from`) were added to the domain config instead.
- **`superseded` already existed.** Task `a3ba67a3` asserted no such state existed. It has been in
  the `ResearchTask` state machine since 2026-06-18 with a comment citing its own CC task, and the 31
  superseded rows in ai-readiness-kg went through the legitimate state machine — no bypass path.
  Only `withdrawn` was genuinely missing.
- **`seldon init`'s ontology default was already derived** from the package location, not hardcoded.
  The stale `Documents/GitHub` strings survived in `seldon.yaml`, the shipped yaml template,
  `scripts/observability_collect.py`, and `go.py::_read_system_standards` — and the derivation was
  still wrong for a wheel install, because `ontology/` is not packaged and `seldon/ontology/` is the
  parser *code* package. Resolution now requires a marker vocabulary file.
