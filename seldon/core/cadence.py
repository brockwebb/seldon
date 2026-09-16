"""Cadence: a schedule that PRODUCES a task, and never bypasses the queue.

`ai-readiness-kg/docs/design/2026-09-15_DN-006_standing_dispatcher.md` decision 8 is the spec:

> `seldon.yaml dispatch.cadence` lists named schedules, each with a calendar rule, a template
> under `cc_tasks/templates/`, and the name of the last instance created. When a schedule is
> due and no instance for that period exists, the pass renders the template, registers it, and
> lets it flow through decisions 2 to 5 like any other task.

**The whole design is in that last clause.** A scheduler that ran a cycle directly would have
its own criteria, its own claim and its own log; this one has none of those, because what it
produces is a task file, and a task file already has an evaluator. The cadence adds exactly one
thing to the system — a file appearing on a calendar — and everything downstream of it is the
path a hand-written task already takes.

**The rule vocabulary is closed and small.** `monthly_first_weekday` is the only rule DD-060
asks for ("monthly, from cycle 3, first Monday UTC") and therefore the only one implemented. A
second rule type is a code change with a test, not a string somebody types into a config file:
an open-ended cron expression in a YAML key is an interpreter nobody wrote, and its failure mode
is a cycle that silently never runs.

Prior art, read before designing (the same survey DN-006 §2 records): cron and systemd timers
express *when*, and each of them hands the decision of *what may run now* to the thing being
run; Airflow separates the schedule (a DAG's `schedule_interval`) from the run's own gating, and
its `catchup` flag exists precisely because "the schedule was due while nothing was watching" is
a question every scheduler has to answer. This one answers it with `catchup=False` by
construction: the period is a calendar month, the instance check is a file on disk, and a pass
that wakes up late in the period creates that period's one instance and no earlier period's.
"""
from __future__ import annotations

import calendar
import re
from datetime import datetime, timezone
from pathlib import Path

#: The weekday vocabulary, lower case, Monday first — `calendar.MONDAY == 0`.
WEEKDAYS = {name.lower(): i for i, name in enumerate(calendar.day_name)}

#: The one implemented rule type. See the module docstring for why the list is short.
RULE_MONTHLY_FIRST_WEEKDAY = "monthly_first_weekday"
RULE_TYPES = (RULE_MONTHLY_FIRST_WEEKDAY,)

#: Keys every cadence entry must carry. DN-006 decision 8 names four of them
#: (`name`, `rule`, `template`, `last_instance`); `instances_dir` and `cycle_name_format` are
#: the two the implementation needed and the note did not have — see ADDENDUM_02 to that note.
#: `cycle_name_format` exists so the string `scan_` is not compiled into this module: the
#: cadence is generic, the cycle-naming convention is the project's, and `~/GitHub/CLAUDE.md`
#: §2 puts a project's convention in its config file.
ENTRY_KEYS = ("name", "rule", "template", "instances_dir", "cycle_name_format", "start_period",
              "last_instance")

#: `start_period` is the first period a schedule may serve, and it is **required**. Prior art:
#: Airflow's `start_date`, which exists for exactly this condition — a schedule switched on
#: part-way through a period that something else has already served. Without it, installing a
#: monthly cadence on the 16th finds the current period due and no instance on disk, and
#: creates a second measurement of a month that already has one. `catchup=False` does not help:
#: the offending period is not an earlier one, it is the current one.
#:
#: It is required rather than defaulted to "the period the config was written in", because that
#: default is invisible: it would depend on a file's mtime, and a schedule whose start nobody
#: can read off the config is a schedule nobody can check.

#: `{date}` is the only substitution `cycle_name_format` takes: a cycle is named for the UTC day
#: it runs on (`params.cycle.name: scan_2026-09-10`), which is the convention every payload
#: path, Result suffix and `refuse_clobber` key in ai-readiness-kg already follows.
_CYCLE_NAME_FIELDS = ("date",)

#: What `render` substitutes into a template. A closed set, so a template that names something
#: else fails loudly at render time rather than shipping a task file with `{typo}` in its body.
#:
#: `instance_stem` is the fifth, and it is not decoration: the dispatcher's finish check looks
#: for `cc_tasks/<stem>_RESULT.md` where `<stem>` is the instance file's own stem, so a template
#: that named its RESULT any other way would produce a task whose RESULT the dispatcher cannot
#: find — every cycle `blocked` on a filename. Recorded in DN-006 ADDENDUM_02.
TEMPLATE_FIELDS = ("cycle_name", "period", "cadence_name", "created_at", "instance_stem")

#: `{...}` as a template placeholder. Deliberately narrow — a task file is markdown full of
#: braces in code blocks and Cypher, and a formatter that treated every brace as a placeholder
#: would mangle the body it is supposed to be copying verbatim.
_PLACEHOLDER_RE = re.compile(r"\{(" + "|".join(TEMPLATE_FIELDS) + r")\}")

#: A period identifier for the monthly rule. `YYYY-MM`, and quoted in YAML so it is a string.
_PERIOD_RE = re.compile(r"\d{4}-\d{2}")

#: Any other `{word}` in a template is a typo for one of the four, and it is reported rather
#: than passed through: a template is authored once and rendered unattended forever, so the
#: first render is the only chance anybody has to notice.
_ANY_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


class CadenceConfigError(ValueError):
    """A `dispatch.cadence` entry is malformed, or names a rule type nobody implemented."""


class CadenceRenderError(ValueError):
    """The template could not be rendered — a missing file, or a placeholder nobody defined."""


# --------------------------------------------------------------------------- configuration

def validate_cadence(entries) -> list:
    """Validate the `dispatch.cadence` list, raising on anything this cannot execute.

    Called from `load_dispatch_config`, so an unknown rule type refuses **at config load** and
    not on the first pass that happens to be due. A schedule that fails the day it fires is a
    schedule that fails unattended and at the only moment it mattered.
    """
    if entries is None:
        return []
    if not isinstance(entries, list):
        raise CadenceConfigError(
            f"dispatch.cadence must be a list of entries, got {type(entries).__name__}")
    seen = set()
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise CadenceConfigError(f"dispatch.cadence[{i}] is not a mapping")
        missing = [k for k in ENTRY_KEYS if k not in entry]
        if missing:
            raise CadenceConfigError(
                f"dispatch.cadence[{i}] missing {', '.join(missing)}")
        name = entry["name"]
        if not isinstance(name, str) or not name:
            raise CadenceConfigError(f"dispatch.cadence[{i}].name must be a non-empty string")
        if name in seen:
            raise CadenceConfigError(
                f"dispatch.cadence has two entries named {name!r}; the name is what the "
                f"instance file and the `cadence_created` event key on")
        seen.add(name)
        validate_rule(entry["rule"], where=f"dispatch.cadence[{i}] ({name})")
        fmt = entry["cycle_name_format"]
        if not isinstance(fmt, str) or not fmt:
            raise CadenceConfigError(
                f"dispatch.cadence[{i}] ({name}).cycle_name_format must be a non-empty string")
        unknown = [f for f in _ANY_PLACEHOLDER_RE.findall(fmt) if f not in _CYCLE_NAME_FIELDS]
        if unknown:
            raise CadenceConfigError(
                f"dispatch.cadence[{i}] ({name}).cycle_name_format names "
                f"{', '.join(sorted(set(unknown)))}; the only field is "
                f"{{{_CYCLE_NAME_FIELDS[0]}}}")
        start = entry["start_period"]
        if not isinstance(start, str) or not _PERIOD_RE.fullmatch(start):
            raise CadenceConfigError(
                f"dispatch.cadence[{i}] ({name}).start_period is {start!r}; expected a period "
                f"identifier the rule produces, e.g. \"2026-10\" for a monthly rule. It is the "
                f"first period this schedule may serve and it has no default")
    return entries


def validate_rule(rule, where: str = "rule") -> dict:
    """One calendar rule. The vocabulary is closed; an unknown key is a refusal, not a default.

    A rule this cannot read must never fall through to "not due": that is the failure that
    looks exactly like a healthy quiet month.
    """
    if not isinstance(rule, dict) or not rule:
        raise CadenceConfigError(f"{where}.rule must be a mapping naming one rule type")
    types = [k for k in rule if k in RULE_TYPES]
    unknown = [k for k in rule if k not in RULE_TYPES and k != "at_utc"]
    if unknown:
        raise CadenceConfigError(
            f"{where}.rule has unknown key(s) {', '.join(sorted(unknown))}; the implemented "
            f"vocabulary is {', '.join(RULE_TYPES)} plus at_utc. A new rule type is a code "
            f"change with a test, not a string in a config file")
    if len(types) != 1:
        raise CadenceConfigError(
            f"{where}.rule must name exactly one of {', '.join(RULE_TYPES)}, found {len(types)}")
    rtype = types[0]
    weekday = str(rule[rtype]).lower()
    if weekday not in WEEKDAYS:
        raise CadenceConfigError(
            f"{where}.rule.{rtype} is {rule[rtype]!r}; expected one of "
            f"{', '.join(WEEKDAYS)}")
    at = rule.get("at_utc", "00:00")
    if not isinstance(at, str) or not re.fullmatch(r"\d{2}:\d{2}", at):
        raise CadenceConfigError(
            f"{where}.rule.at_utc is {at!r}; expected HH:MM, UTC, quoted so YAML does not read "
            f"it as a sexagesimal number")
    hh, mm = (int(p) for p in at.split(":"))
    if hh > 23 or mm > 59:
        raise CadenceConfigError(f"{where}.rule.at_utc is {at!r}, which is not a time of day")
    return rule


def rule_type(rule: dict) -> str:
    return next(k for k in rule if k in RULE_TYPES)


def _at_utc(rule: dict) -> tuple:
    hh, mm = (int(p) for p in str(rule.get("at_utc", "00:00")).split(":"))
    return hh, mm


# ------------------------------------------------------------------------------- the calendar

def period_of(rule: dict, when: datetime) -> str:
    """The period identifier `when` falls in. For the monthly rule, `YYYY-MM`.

    The period — not the due instant — is what the instance file is named for, so a pass that
    fires at 00:05 and a pass that fires on the 28th of the same month look for the same file.
    """
    rtype = rule_type(rule)
    if rtype == RULE_MONTHLY_FIRST_WEEKDAY:
        return f"{when.year:04d}-{when.month:02d}"
    raise CadenceConfigError(f"no period defined for rule type {rtype!r}")   # unreachable


def due_instant(rule: dict, period: str) -> datetime:
    """The UTC instant at which `period` becomes due. Tz-aware, always UTC.

    For `monthly_first_weekday: monday`, the first Monday of the month at `at_utc` — computed
    from the calendar rather than from an offset table, because "the first Monday" moves by
    three or four days a month and an arithmetic shortcut is how an off-by-one ships.
    """
    rtype = rule_type(rule)
    if rtype != RULE_MONTHLY_FIRST_WEEKDAY:
        raise CadenceConfigError(f"no due instant defined for rule type {rtype!r}")
    year, month = (int(p) for p in period.split("-"))
    target = WEEKDAYS[str(rule[rtype]).lower()]
    first = datetime(year, month, 1, tzinfo=timezone.utc)
    # `(target - first.weekday()) % 7` is the number of days from the 1st to the first
    # occurrence of the target weekday, and it is 0 when the 1st IS that weekday.
    day = 1 + (target - first.weekday()) % 7
    hh, mm = _at_utc(rule)
    return datetime(year, month, day, hh, mm, tzinfo=timezone.utc)


def is_due(rule: dict, now: datetime, start_period: str | None = None) -> bool:
    """Has this period's due instant passed, and is this period one the schedule may serve?

    Evaluated against the CURRENT period only, which is `catchup=False` by construction: a
    dispatcher that was off for two months creates this month's instance and does not
    back-fill two cycles nobody could have run. A back-filled cycle would measure today's
    hosts and be named for a month that has gone, which is the one thing a dated measurement
    may not be.

    `start_period` is the other half, and `catchup=False` does not cover it: a schedule
    switched on part-way through a period that something else already served would find the
    CURRENT period due with no instance on disk and create a duplicate. Period identifiers for
    the monthly rule sort lexicographically because they are zero-padded `YYYY-MM`.
    """
    now = _as_utc(now)
    period = period_of(rule, now)
    if start_period and period < start_period:
        return False
    return now >= due_instant(rule, period)


def next_due_instants(rule: dict, after: datetime, count: int = 3,
                      start_period: str | None = None) -> list:
    """The next `count` due instants strictly after `after`.

    Exists so the arithmetic is checked once against a calendar and then trusted — a schedule
    whose next firing nobody has ever printed is a schedule nobody has verified.
    """
    after = _as_utc(after)
    out = []
    year, month = after.year, after.month
    while len(out) < count:
        period = f"{year:04d}-{month:02d}"
        when = due_instant(rule, period)
        if when > after and not (start_period and period < start_period):
            out.append(when)
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return out


def _as_utc(when: datetime) -> datetime:
    """A naive datetime is read as UTC, not as local time.

    The rule is declared in UTC (`at_utc`) and the machine that runs it is on US Eastern, so
    "first Monday 00:00" is Sunday evening locally. Reading a naive timestamp as local would
    make the schedule fire on the wrong calendar day for five months of the year — the DST
    offset changes, the rule does not.
    """
    return when.replace(tzinfo=timezone.utc) if when.tzinfo is None else when.astimezone(
        timezone.utc)


# ------------------------------------------------------------------------------ the instance

def cycle_name_for(entry: dict, created_at: datetime) -> str:
    """`scan_2026-10-05` — the cycle identifier the rendered task will run under."""
    return entry["cycle_name_format"].format(date=_as_utc(created_at).strftime("%Y-%m-%d"))


def instance_stem(entry: dict, period: str, created_at: datetime) -> str:
    return f"{_as_utc(created_at).strftime('%Y-%m-%d')}_{entry['name']}_{period}"


def instance_path(project_dir: Path, entry: dict, period: str, created_at: datetime) -> Path:
    return (Path(project_dir) / entry["instances_dir"]
            / f"{instance_stem(entry, period, created_at)}.md")


def existing_instance(project_dir: Path, entry: dict, period: str) -> Path | None:
    """The instance file for this period, whatever day of the period it was written on.

    **The check is the file, never the config field.** DN-006 decision 8 records
    `last_instance` in `seldon.yaml` for a reader; if the guard were that field, a hand-cleared
    line — or a write-back that failed while the file itself was created — would create a
    second task for a month that already has one. The glob is over the period suffix, so the
    date prefix is free to be whatever day the pass first fired on.
    """
    d = Path(project_dir) / entry["instances_dir"]
    if not d.is_dir():
        return None
    found = sorted(d.glob(f"*_{entry['name']}_{period}.md"))
    return found[0] if found else None


def render(template_text: str, *, cycle_name: str, period: str, cadence_name: str,
           created_at: str, instance_stem: str) -> str:
    """Substitute the four fields. Anything else in braces is a typo and refuses.

    `str.format` is not used: a task file body is markdown with JSON, Cypher and shell in it,
    and `format` would raise or mangle on every one of those braces. The substitution is
    therefore a regex over exactly the four known names.
    """
    values = {"cycle_name": cycle_name, "period": period, "cadence_name": cadence_name,
              "created_at": created_at, "instance_stem": instance_stem}
    out = _PLACEHOLDER_RE.sub(lambda m: values[m.group(1)], template_text)
    return out


def unknown_placeholders(template_text: str) -> list:
    """`{word}` placeholders the renderer does not define, EXCLUDING the four it does.

    Reported by the config/template check rather than by `render`, because a false positive
    here is a brace in a code fence and the right response to one is a human reading it, not a
    pass that refuses at 00:00 on the first Monday.
    """
    return sorted({m for m in _ANY_PLACEHOLDER_RE.findall(template_text)
                   if m not in TEMPLATE_FIELDS})


def evaluate_entry(project_dir: Path, entry: dict, now: datetime) -> dict:
    """The cadence half of a pass's criteria vector, as VALUES — the same contract as DN-006
    decision 2's task criteria: never a boolean summary, because "not due" and "due but the
    instance exists" and "due and the tree was dirty" are three different things an operator
    needs to tell apart."""
    now = _as_utc(now)
    period = period_of(entry["rule"], now)
    when = due_instant(entry["rule"], period)
    existing = existing_instance(project_dir, entry, period)
    start = entry.get("start_period")
    return {
        "cadence": entry["name"],
        "period": period,
        "due_at": when.isoformat().replace("+00:00", "Z"),
        "start_period": start,
        "before_start": bool(start and period < start),
        "due": is_due(entry["rule"], now, start),
        "instance": str(existing.relative_to(Path(project_dir))) if existing else None,
        "last_instance": entry.get("last_instance") or None,
        "next_due": [d.isoformat().replace("+00:00", "Z")
                     for d in next_due_instants(entry["rule"], now, 3, start)],
        "template": entry["template"],
    }


# --------------------------------------------------- writing `last_instance` back, in place

_LAST_INSTANCE_RE = re.compile(r"^(?P<lead>\s*last_instance\s*:).*$")


def write_last_instance(seldon_yaml: Path, cadence_name: str, value: str) -> bool:
    """Record the instance just created, by editing the ONE line in place.

    Not `yaml.safe_dump` of the reparsed document: every key in this project's `dispatch:`
    block carries the comment that says what its value is based on — the standing band's
    reference, the poll interval's missing measured basis, the permission mode's derivation —
    and a round-trip through the loader would delete all of it. The dispatcher must not be the
    thing that strips a config file of its reasons.

    Returns False rather than raising when the line cannot be found: `last_instance` is a
    reader's record and `existing_instance` is the guard (see its docstring), so a failed
    write-back must not abort a pass that has already created and registered the instance. The
    caller puts the outcome on the `cadence_created` event, where it is visible.
    """
    lines = seldon_yaml.read_text(encoding="utf-8").splitlines(keepends=True)
    start = None
    for i, line in enumerate(lines):
        if re.fullmatch(rf"\s*-\s+name:\s*{re.escape(cadence_name)}\s*", line.rstrip("\n")):
            start = i
            break
    if start is None:
        return False
    indent = len(lines[start]) - len(lines[start].lstrip())
    for i in range(start + 1, len(lines)):
        stripped = lines[i].strip()
        if not stripped or stripped.startswith("#"):
            continue
        cur = len(lines[i]) - len(lines[i].lstrip())
        # A new list item at or above this entry's indent ends the entry.
        if cur <= indent and stripped.startswith("- "):
            break
        if cur < indent:
            break
        m = _LAST_INSTANCE_RE.match(lines[i].rstrip("\n"))
        if m and cur == indent + 2:
            nl = "\n" if lines[i].endswith("\n") else ""
            lines[i] = f'{m.group("lead")} "{value}"{nl}'
            seldon_yaml.write_text("".join(lines), encoding="utf-8")
            return True
    return False
