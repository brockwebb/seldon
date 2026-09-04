# Result units vocabulary and the `name` / `units` split (AD-028)

**Status:** active
**Applies to:** every project graph with `Result` artifacts
**Authoritative list:** `seldon/domain/result_units_vocabulary.yaml` — **not this file**

---

## 1. The defect this convention closes

`{{result:NAME:value}}` tokens in paper prose resolve against the graph by looking
up `"result:<name>"`. Before AD-028, `seldon result register` had no `--name`
flag, so nothing ever set the `name` property on a `Result`. Authors reached for
the only free-text slot the command exposed — `units` — and put the token key
there. In `seldon-ai-readiness-kg` that produced 3592 `Result` nodes, none with a
`name`, all carrying something in `units`: some genuine (`count`, `ratio`), most
token keys (`admitted_yield_ratio`).

Two properties were carrying one meaning between them, decided by convention
nobody wrote down. AD-028 splits them:

| Property | Meaning | Example |
|----------|---------|---------|
| `name`   | Stable token key. What `{{result:NAME:field}}` looks up. | `admitted_yield_ratio` |
| `units`  | A real unit of measurement. Never a token key. | `ratio` |

`name` is case-sensitive, at most 128 characters, and unique per project graph.
It must start with an ASCII letter or digit, then any of letters, digits,
underscore, dot or hyphen (AD-028 §1 as amended by Amendment 01, which admitted
uppercase). **The regex itself is written in exactly one place —
`RESULT_NAME_PATTERN` in `seldon/commands/result.py` — and is deliberately not
reproduced here**, because a second copy is a second definition and the two
drift; `seldon result register --help` prints the live pattern.
`seldon result register --name` enforces grammar, length and uniqueness at the
CLI, and `seldon result migrate-names` applies the identical check on both its
dry-run and its live path. The domain config deliberately does **not** mark
`name` as required, so Results registered before AD-028 stay schema-valid.

## 2. What the vocabulary is for

The vocabulary is the machine's answer to "is this string a unit or a name?".
It has exactly two consumers:

1. **`seldon result migrate-names`** — classifies every `Result` that has no
   `name`. A `units` value in the vocabulary is a real unit and is left alone;
   anything else is promoted to `name`.
2. **The transitional units fallback in `seldon/paper/build.py`** — when a
   `{{result:NAME:...}}` token matches no `name`, the resolver may fall back to
   matching a Result by `units`, but only when that `units` string is **not** in
   the vocabulary. A token that happens to equal `count` is a coincidence, not a
   reference.

Adding an entry makes `migrate-names` stop promoting that string. Removing one
makes it start. Change the list only alongside a `--dry-run` against every
affected project.

## 3. Where the list lives, and why not here

The authoritative list is **`seldon/domain/result_units_vocabulary.yaml`**, loaded
by `seldon/domain/units_vocabulary.py`.

It lives inside the package because `pyproject.toml` ships
`[tool.setuptools.package-data] "seldon.domain" = ["*.yaml"]` and `include = ["seldon*"]`.
`docs/` is not part of the installed distribution. A loader reading this
directory would work in an editable checkout and fail with a config-not-found on
any real install — the exact silent-environment-dependence Section 2 of the
engineering standards forbids. Nothing resolves the vocabulary relative to the
current working directory or a guessed repository root; the path comes from the
loader module's own `__file__`.

This document explains the vocabulary. The YAML *is* the vocabulary.

## 4. The seeded vocabulary

Two groups, unioned at load time.

**Seed units** — named directly by the AD-028 task specification:

`%`, `rate`, `ratio`, `count`, `tokens`, `chars`, `seconds`, `minutes`, `docs`,
`chunks`, `items`, `facts`, `USD`, `kappa`

**Codebase units** — every distinct string the Seldon repository itself already
puts in a `units` slot, found by sweeping all `units=` / `units:` literals across
source, tests, fixtures, and domain-config help text:

| Unit | Where the codebase uses it |
|------|----------------------------|
| `accuracy` | `--units` help text in `seldon/commands/result.py`; test fixtures |
| `acc` | `tests/test_paper_build.py` fixture |
| `ms` | `--units` help text in `seldon/commands/result.py` |
| `score` | the most common `units` literal across the test suite |
| `fraction` | `tests/test_verify.py` fixtures |
| `bits` | `tests/test_impact.py` fixture |
| `bits_per_decade` | `tests/test_impact.py` fixture |

`accuracy`, `acc`, `score`, and `fraction` are metric names rather than
dimensional units. They are in the vocabulary anyway, because the codebase
already uses them in the `units` slot and omitting them would make
`migrate-names` promote them to `name` and rewrite existing Results. The
vocabulary records what the system treats as a unit, not what a metrologist
would.

## 5. The three migration classes

`seldon result migrate-names [--dry-run]` puts every `Result` with no `name` into
exactly one class.

| Class | Condition | Action |
|-------|-----------|--------|
| `units_is_real_unit` | `units` is in the vocabulary and is not in use as a token key | Leave `name` unset. Report only. |
| `ambiguous` | `units` is in the vocabulary **and** that same string is in use as a token key — cited by a `{{result:...}}` token in the project's paper sources, or already claimed as another Result's `name` | Do not assign. List in full in the report. A human decides. |
| `migrated` | Anything else with a non-empty `units` | Promote: `name := units`, then clear `units`. |

A fourth bucket, `no_units`, catches Results with neither a `name` nor a `units`
to promote. Nothing can be inferred for them; they are reported so they are not
silently invisible.

**Migration is by event, never by mutation.** Each promotion emits one
`artifact_updated` event through `seldon.core.artifacts.update_artifact`, setting
`name` and clearing `units` together. One event, not two: `seldon/core/sync.py`
projects events onto the graph by dispatching on `event_type`, and an
unrecognised type is logged and *skipped*. Inventing `result_name_assigned` /
`result_units_cleared` would make every migration vanish on a full replay unless
the sync dispatcher — a module outside this change's ownership — learned them
first. `artifact_updated` already replays correctly, and setting a property to
`null` in Neo4j removes it, so the clear survives replay too.

After migration a migrated Result has no `units`. `units` is `required: true` in
`research.yaml`, so `seldon docs check` will count it as a missing required
property. That is correct reporting, not a regression: those Results never had a
real unit, and now the graph says so out loud instead of hiding a token key in
the slot.

## 6. The transitional fallback

`resolve_references` in `seldon/paper/build.py` may resolve a token by `units`
when no `name` matches. Every fallback hit emits an `SI-09` warning line naming
the token and the Result it matched, so the fallback set is visible in build
output rather than silently load-bearing. If more than one Result carries the
same `units` token, the fallback refuses to guess and raises a fatal `SI-09`
naming every candidate.

The fallback is **transitional**. It is marked `# TRANSITIONAL (AD-028)` in
`seldon/paper/build.py` with its removal condition on its face: delete
`build_units_fallback_index`, its call site, and the `units_fallback` parameter
once `seldon result migrate-names` has been run live on every project graph and
no build emits `SI-09`.
