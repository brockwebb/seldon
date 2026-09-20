# Seldon Issue: a cadence template can only be rendered by a schedule

**Date:** 2026-09-18
**Severity:** Minor (a workaround exists and works; it duplicates four config values into a shell line)
**Found during:** `ai-readiness-kg` `cc_tasks/2026-09-18_cadence_off.md`, where the operator turned the project's
monthly scan cadence off and made a scan cycle something a person asks for
**Component:** `seldon.core.cadence` / `seldon dispatch` — there is no CLI entry point to the renderer

---

## Problem

`seldon.core.cadence.render`, `instance_stem` and `cycle_name_for` are reachable only from
`seldon.commands.dispatch._create_instance`, which runs only when a `dispatch.cadence` entry's rule
says a period is due. A project that keeps the template but turns the schedule off
(`dispatch.cadence: []`) has no command that renders it. The render parameters the entry used to
carry (`name`, `template`, `instances_dir`, `cycle_name_format`) are no longer in any config, so the
workaround has to type them.

The workaround used in `ai-readiness-kg` (its `cc_tasks/2026-09-18_cadence_off_RESULT.md` §1) is a
`python -c` over `seldon.core.cadence`, then `git add`, `seldon cc register` and `git commit`. It
works, and it is four literal values in a shell line (`~/GitHub/CLAUDE.md` §2).

## Asked for

`seldon cadence render <name> [--period P]`:

1. Reads the entry from a `dispatch.templates:` list (or from `dispatch.cadence` with the `rule`
   optional). An entry with no rule never fires on a pass and can always be rendered on request.
   The four fields `validate_cadence` checks today stay required.
2. Renders through the same `render` / `instance_stem` / `cycle_name_for` the pass uses, so a
   template rendered by hand and one rendered on a schedule cannot differ.
3. Stages the file and registers it through `register_task_file`, as `_create_instance` does. It
   refuses when an instance with the same stem exists, and emits `cadence_created` with
   `"trigger": "request"`, which makes the event distinguishable from a scheduled one.
4. `--period` defaults to the UTC date, so two requested cycles in one month cannot collide on
   the instance glob.

## Also

A rendered instance's `**Network:**` header reads `hosts, under cadence <name>`. c5 (the network
criterion) admits it by regex and does not check that `<name>` is a configured cadence, so an
on-request instance is still eligible after the schedule is removed. That is the behaviour this
project wants today. It is recorded here because a later tightening of c5 to "a configured cadence"
would silently make every on-request cycle ineligible.

---

## Resolved 2026-09-20 — `seldon cadence list|check|render`

`ai-readiness-kg/cc_tasks/2026-09-19_seldon_hygiene_superseded_cadence_after.md` decision 2,
landed in `seldon/commands/cadence.py` (commit `33f70c6`).

    seldon cadence render (<cadence-name> | --template <path>) [--var k=v ...]
                          [--period P] [--cycle-name N] [--out-dir D] [--write] [--register]

Without `--write` it prints and touches nothing. `--write` refuses to overwrite; `--register`
implies it and goes through `register_task_file`, the same function `seldon cc register` and the
cadence pass already use. A hand render writes `cadence_rendered`, never `cadence_created`, so
the log still distinguishes a person asking from a schedule firing (DN-006 decision 8 keeps its
meaning). `tests/test_cadence_render_command.py` asserts the stdout render is **byte-identical**
to what `_create_instance` writes for the same entry and instant.

The four typed values this issue is about come from the entry when one is named. With
`--template` there is no rule and no `cycle_name_format`, so `--period` and `--cycle-name` are
**required** rather than defaulted: a dated measurement may not carry a date nobody chose.

The five `TEMPLATE_FIELDS` stay closed. A template that needs more declares them on one line in
its first ten — `<!-- seldon:vars target, network_hosts -->` — and an undeclared `--var`, a
declared var nobody supplied, and any other `{word}` outside a code fence each refuse by name.
That is the shape Helm's `values.schema.json`, Terraform `variable` blocks and a composite
action's `inputs:` all use: the template declares its interface and the engine checks both
directions.

**The "Also" above still stands**, unchanged: c5 admits `under cadence <name>` by regex without
checking that the name is configured, and that is what lets an on-request instance stay eligible
after the schedule is removed.
