"""The cadence: the calendar, the instance check, the render, and the config refusal.

`ai-readiness-kg/cc_tasks/2026-09-16_cadence_and_enable.md` §1 names the test set, against
`ai-readiness-kg/docs/design/2026-09-15_DN-006_standing_dispatcher.md` decision 8.

**Nothing here touches Neo4j, a host, or a model.** The calendar is arithmetic, the instance
check is a file on disk, and the render is a regex; the one thing that needs a graph — the
registration — is exercised in `test_cadence_pass.py` against the test database.

The date arithmetic is tested against a hand-checked calendar rather than against a
reimplementation of the same formula: an off-by-one in "the first Monday of the month" is
invisible to a test that computes the expected value the same way the code does.
"""
from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from seldon.core import cadence as C
from seldon.core import dispatch as D


def _entry(**over) -> dict:
    e = {"name": "scan_cycle",
         "rule": {"monthly_first_weekday": "monday", "at_utc": "00:00"},
         "template": "cc_tasks/templates/scan_cycle.md",
         "instances_dir": "cc_tasks",
         "cycle_name_format": "scan_{date}",
         "start_period": "2026-01",
         "last_instance": ""}
    e.update(over)
    return e


@pytest.fixture
def project(tmp_path) -> Path:
    p = tmp_path / "proj"
    (p / "cc_tasks" / "templates").mkdir(parents=True)
    return p


# ==================================================================== the calendar, by hand

#: Hand-checked against a calendar, one per month. 2026-10-05 is the due instant this task's
#: decision 6 states, and it is in the table so the RESULT's arithmetic and the code's agree.
FIRST_MONDAYS_2026 = {
    "2026-09": 7, "2026-10": 5, "2026-11": 2, "2026-12": 7,
}
FIRST_MONDAYS_2027 = {"2027-01": 4, "2027-02": 1, "2027-03": 1}


@pytest.mark.parametrize("period,day", {**FIRST_MONDAYS_2026, **FIRST_MONDAYS_2027}.items())
def test_the_due_instant_is_the_first_monday_of_the_month_at_midnight_utc(period, day):
    when = C.due_instant(_entry()["rule"], period)
    assert (when.year, when.month, when.day) == (*[int(x) for x in period.split("-")], day)
    assert (when.hour, when.minute, when.tzinfo) == (0, 0, timezone.utc)
    assert when.weekday() == 0


def test_a_month_that_starts_on_the_target_weekday_is_due_on_the_first():
    """`(target - weekday) % 7` must be 0, not 7, when the 1st IS the target weekday. 2027-02-01
    and 2027-03-01 are both Mondays; an implementation that always added a week would put the
    cycle on the 8th."""
    assert C.due_instant(_entry()["rule"], "2027-02").day == 1
    assert C.due_instant(_entry()["rule"], "2027-03").day == 1


def test_at_utc_moves_the_due_instant_and_nothing_else():
    rule = {"monthly_first_weekday": "monday", "at_utc": "13:45"}
    when = C.due_instant(rule, "2026-10")
    assert (when.day, when.hour, when.minute) == (5, 13, 45)


@pytest.mark.parametrize("weekday,day", [("tuesday", 6), ("friday", 2), ("sunday", 4)])
def test_every_weekday_in_the_vocabulary_resolves(weekday, day):
    """October 2026 begins on a Thursday: the first Friday is the 2nd, the first Sunday the
    4th, the first Tuesday the 6th."""
    assert C.due_instant({"monthly_first_weekday": weekday}, "2026-10").day == day


# ------------------------------------------------------------------ due, and the boundaries

@pytest.mark.parametrize("now,due", [
    ("2026-10-01T00:00:00Z", False),   # the month has begun, the first Monday has not
    ("2026-10-04T23:59:59Z", False),   # one second before
    ("2026-10-05T00:00:00Z", True),    # the instant itself
    ("2026-10-31T23:00:00Z", True),    # still the same period, still due, still one instance
])
def test_due_is_evaluated_against_this_period_only(now, due):
    assert C.is_due(_entry()["rule"], datetime.fromisoformat(now.replace("Z", "+00:00"))) is due


def test_the_month_boundary_starts_a_new_period_that_is_not_yet_due():
    """November's period begins on the 1st and is not due until the 2nd. A pass on
    2026-10-31 and a pass on 2026-11-01 are in different periods, and the second one creates
    nothing — which is the whole reason the period and the due instant are separate."""
    rule = _entry()["rule"]
    oct31 = datetime(2026, 10, 31, 23, 0, tzinfo=timezone.utc)
    nov1 = datetime(2026, 11, 1, 1, 0, tzinfo=timezone.utc)
    assert C.period_of(rule, oct31) == "2026-10" and C.is_due(rule, oct31) is True
    assert C.period_of(rule, nov1) == "2026-11" and C.is_due(rule, nov1) is False


def test_a_naive_timestamp_is_read_as_utc_and_never_as_local_time():
    """The rule is declared in UTC and the machine is on US Eastern, so `first Monday 00:00Z`
    is Sunday 20:00 local. A naive timestamp read as local would fire on the wrong calendar day
    for the five months of the year the offset differs — and the offset, not the rule, is what
    changes."""
    naive = datetime(2026, 10, 5, 0, 30)
    aware = datetime(2026, 10, 5, 0, 30, tzinfo=timezone.utc)
    assert C.is_due(_entry()["rule"], naive) == C.is_due(_entry()["rule"], aware) is True
    # 2026-10-04T21:00 US Eastern is 2026-10-05T01:00Z: due in UTC, and the day before locally.
    eastern_evening = datetime(2026, 10, 5, 1, 0, tzinfo=timezone.utc)
    assert C.is_due(_entry()["rule"], eastern_evening) is True
    assert C.period_of(_entry()["rule"], eastern_evening) == "2026-10"


def test_the_next_three_due_instants_are_strictly_after_the_given_time():
    nxt = C.next_due_instants(_entry()["rule"], datetime(2026, 10, 5, 0, 0, tzinfo=timezone.utc))
    assert [d.isoformat() for d in nxt] == ["2026-11-02T00:00:00+00:00",
                                            "2026-12-07T00:00:00+00:00",
                                            "2027-01-04T00:00:00+00:00"]


def test_next_due_instants_crosses_the_year_boundary():
    nxt = C.next_due_instants(_entry()["rule"],
                              datetime(2026, 12, 8, tzinfo=timezone.utc), count=2)
    assert [(d.year, d.month, d.day) for d in nxt] == [(2027, 1, 4), (2027, 2, 1)]


# ============================================================ the instance check is the FILE

def test_a_period_with_an_instance_on_disk_is_reported_as_served(project):
    e = _entry()
    assert C.existing_instance(project, e, "2026-10") is None
    (project / "cc_tasks" / "2026-10-05_scan_cycle_2026-10.md").write_text("x")
    found = C.existing_instance(project, e, "2026-10")
    assert found is not None and found.name == "2026-10-05_scan_cycle_2026-10.md"


def test_the_instance_is_found_whatever_day_of_the_period_it_was_written_on(project):
    """The glob is over the period suffix. A dispatcher that was down on the 5th and fired on
    the 19th must not create a second instance for October just because the date prefix in the
    name would differ."""
    (project / "cc_tasks" / "2026-10-19_scan_cycle_2026-10.md").write_text("x")
    assert C.existing_instance(project, _entry(), "2026-10") is not None


def test_a_hand_cleared_last_instance_does_not_make_the_period_unserved(project):
    """DN-006 decision 8 records `last_instance` in the config for a reader; the guard is the
    FILE. A guard that was the config field would create a second task for a month that already
    has one the moment somebody edited the line — or the moment a write-back failed after the
    file was created."""
    (project / "cc_tasks" / "2026-10-05_scan_cycle_2026-10.md").write_text("x")
    row = C.evaluate_entry(project, _entry(last_instance=""),
                           datetime(2026, 10, 6, tzinfo=timezone.utc))
    assert row["due"] is True
    assert row["last_instance"] is None
    assert row["instance"] == "cc_tasks/2026-10-05_scan_cycle_2026-10.md"


def test_another_cadences_instance_for_the_same_period_is_not_mistaken_for_this_ones(project):
    (project / "cc_tasks" / "2026-10-05_other_cadence_2026-10.md").write_text("x")
    assert C.existing_instance(project, _entry(), "2026-10") is None


def test_evaluate_entry_reports_values_and_not_a_boolean(project):
    row = C.evaluate_entry(project, _entry(), datetime(2026, 10, 6, tzinfo=timezone.utc))
    assert row["cadence"] == "scan_cycle" and row["period"] == "2026-10"
    assert row["due_at"] == "2026-10-05T00:00:00Z" and row["due"] is True
    assert row["instance"] is None
    assert row["next_due"][0] == "2026-11-02T00:00:00Z"
    assert row["template"] == "cc_tasks/templates/scan_cycle.md"


# ================================================================== the config refuses early

def _block(cadence) -> dict:
    return {"enabled": True, "branch": "main",
            "standing_band_ref": "controls.yaml#spend.daily_tokens",
            "poll_interval_s": 300, "permission_mode": "bypassPermissions",
            "stop_file": ".seldon/DISPATCH_STOP", "log_dir": "logs/dispatch",
            "lease_file": ".seldon/dispatch.lock", "cadence": cadence}


def _load(tmp_path, cadence):
    return D.load_dispatch_config(tmp_path, {"dispatch": _block(cadence)})


def test_an_unknown_rule_type_refuses_at_config_load(tmp_path):
    """The refusal has to happen when the config is READ, not when the schedule fires: a rule
    this cannot execute must never be indistinguishable from a quiet month, and 00:00 on the
    first Monday, unattended, is the worst possible moment to find out."""
    with pytest.raises(C.CadenceConfigError, match="unknown key"):
        _load(tmp_path, [_entry(rule={"every_fortnight": "monday"})])


def test_a_cron_expression_is_refused_with_its_reason(tmp_path):
    with pytest.raises(C.CadenceConfigError, match="not a string in a config file"):
        _load(tmp_path, [_entry(rule={"cron": "0 0 * * 1"})])


def test_a_rule_that_names_no_rule_type_refuses(tmp_path):
    """`at_utc` alone is a time with no schedule attached. It has to refuse rather than default
    to some cadence nobody wrote down."""
    with pytest.raises(C.CadenceConfigError, match="exactly one"):
        _load(tmp_path, [_entry(rule={"at_utc": "00:00"})])


def test_an_unknown_weekday_refuses(tmp_path):
    with pytest.raises(C.CadenceConfigError, match="expected one of"):
        _load(tmp_path, [_entry(rule={"monthly_first_weekday": "moonday"})])


@pytest.mark.parametrize("at", ["0:00", "24:00", "00:61", 0, "midnight"])
def test_an_at_utc_that_is_not_a_time_of_day_refuses(tmp_path, at):
    with pytest.raises(C.CadenceConfigError):
        _load(tmp_path, [_entry(rule={"monthly_first_weekday": "monday", "at_utc": at})])


@pytest.mark.parametrize("key", C.ENTRY_KEYS)
def test_every_entry_key_is_required(tmp_path, key):
    e = _entry()
    del e[key]
    with pytest.raises(C.CadenceConfigError, match="missing"):
        _load(tmp_path, [e])


def test_two_entries_with_one_name_refuse(tmp_path):
    with pytest.raises(C.CadenceConfigError, match="two entries named"):
        _load(tmp_path, [_entry(), _entry()])


def test_a_cycle_name_format_naming_an_unknown_field_refuses(tmp_path):
    with pytest.raises(C.CadenceConfigError, match="the only field is"):
        _load(tmp_path, [_entry(cycle_name_format="scan_{cycle}")])


def test_a_project_with_no_cadence_key_loads_and_gets_an_empty_list(tmp_path):
    """The cadence is opt-in exactly as the dispatcher is: a project that has never declared a
    schedule must not start failing config load because a schedule mechanism now exists."""
    block = _block(None)
    del block["cadence"]
    assert D.load_dispatch_config(tmp_path, {"dispatch": block})["cadence"] == []


# =========================================================================== the render

TEMPLATE = """# CC Task — {cadence_name} for {period}

**Date:** {created_at}
**Spend:** zero model calls. **Network:** hosts, under cadence {cadence_name}

Set `params.cycle.name: {cycle_name}`.

```cypher
MATCH (f:Finding) WHERE f.cycle = "{cycle_name}" RETURN count(f)
```

RESULT at `cc_tasks/{instance_stem}_RESULT.md`.

Shell: `${HOME}/bin/thing` and a dict literal `{"a": 1}`.
"""


def test_the_five_fields_are_substituted_and_nothing_else_is_touched():
    out = C.render(TEMPLATE, cycle_name="scan_2026-10-05", period="2026-10",
                   cadence_name="scan_cycle", created_at="2026-10-05T00:01:02Z",
                   instance_stem="2026-10-05_scan_cycle_2026-10")
    assert "# CC Task — scan_cycle for 2026-10" in out
    assert "**Date:** 2026-10-05T00:01:02Z" in out
    assert 'f.cycle = "scan_2026-10-05"' in out
    assert "under cadence scan_cycle" in out
    # The braces a markdown task file is full of survive verbatim — `str.format` would raise
    # on `${HOME}` and mangle `{"a": 1}`, and a template is a task file, not a format string.
    assert '${HOME}/bin/thing' in out and '{"a": 1}' in out
    # The fifth field is the RESULT filename the dispatcher's finish check looks for. A
    # template that named its RESULT any other way would produce a task that ran, wrote its
    # RESULT, and was marked `blocked` on a filename. DN-006 ADDENDUM_02 §2.
    assert "cc_tasks/2026-10-05_scan_cycle_2026-10_RESULT.md" in out


def test_a_placeholder_nobody_defines_is_reported_rather_than_shipped():
    assert C.unknown_placeholders("a {cycle_name} and a {cycle_nmae}") == ["cycle_nmae"]
    assert C.unknown_placeholders(
        "{cycle_name}{period}{cadence_name}{created_at}{instance_stem}") == []


def test_the_cycle_name_is_the_utc_day_the_instance_was_created():
    assert C.cycle_name_for(_entry(), datetime(2026, 10, 5, 0, 30, tzinfo=timezone.utc)) \
        == "scan_2026-10-05"


def test_the_instance_path_carries_the_date_the_name_and_the_period(project):
    p = C.instance_path(project, _entry(), "2026-10",
                        datetime(2026, 10, 5, tzinfo=timezone.utc))
    assert p.relative_to(project).as_posix() == "cc_tasks/2026-10-05_scan_cycle_2026-10.md"


# ============================================== last_instance is written WITHOUT reformatting

YAML_WITH_COMMENTS = """\
dispatch:

  # THE KILL SWITCH, and it ships false.
  enabled: false

  cadence:
    # Why this schedule exists, in the file an operator reads.
    - name: scan_cycle
      rule:
        monthly_first_weekday: monday
        at_utc: "00:00"
      template: cc_tasks/templates/scan_cycle.md
      instances_dir: cc_tasks
      cycle_name_format: "scan_{date}"
      start_period: "2026-10"
      # Written back by the dispatcher. The FILE is the guard.
      last_instance: ""
    - name: other
      rule:
        monthly_first_weekday: friday
      template: cc_tasks/templates/other.md
      instances_dir: cc_tasks
      cycle_name_format: "other_{date}"
      start_period: "2026-09"
      last_instance: "cc_tasks/2026-09-04_other_2026-09.md"
"""


def test_writing_last_instance_keeps_every_comment_in_the_file(tmp_path):
    """A round-trip through `yaml.safe_dump` would delete every line that says WHY a value is
    what it is — the band's reference, the poll interval's missing measured basis, the
    permission mode's derivation. The dispatcher must not be the thing that strips a config
    file of its reasons."""
    f = tmp_path / "seldon.yaml"
    f.write_text(YAML_WITH_COMMENTS, encoding="utf-8")
    assert C.write_last_instance(f, "scan_cycle", "cc_tasks/2026-10-05_scan_cycle_2026-10.md")
    text = f.read_text(encoding="utf-8")
    assert "# THE KILL SWITCH, and it ships false." in text
    assert "# Written back by the dispatcher. The FILE is the guard." in text
    doc = yaml.safe_load(text)
    entries = doc["dispatch"]["cadence"]
    assert entries[0]["last_instance"] == "cc_tasks/2026-10-05_scan_cycle_2026-10.md"
    # The OTHER entry's value is untouched: the write is scoped to the named entry.
    assert entries[1]["last_instance"] == "cc_tasks/2026-09-04_other_2026-09.md"


def test_writing_last_instance_for_a_name_that_is_not_there_reports_false(tmp_path):
    f = tmp_path / "seldon.yaml"
    f.write_text(YAML_WITH_COMMENTS, encoding="utf-8")
    assert C.write_last_instance(f, "no_such_cadence", "x") is False
    assert f.read_text(encoding="utf-8") == YAML_WITH_COMMENTS


def test_writing_last_instance_targets_the_second_entry_without_touching_the_first(tmp_path):
    f = tmp_path / "seldon.yaml"
    f.write_text(YAML_WITH_COMMENTS, encoding="utf-8")
    assert C.write_last_instance(f, "other", "cc_tasks/2026-10-02_other_2026-10.md")
    entries = yaml.safe_load(f.read_text())["dispatch"]["cadence"]
    assert entries[0]["last_instance"] == ""
    assert entries[1]["last_instance"] == "cc_tasks/2026-10-02_other_2026-10.md"


# ======================================================= the commit the cadence has to make

@pytest.fixture
def repo(tmp_path) -> Path:
    p = tmp_path / "repo"
    p.mkdir()
    for a in (["init", "-b", "main"], ["config", "user.email", "t@t"],
              ["config", "user.name", "t"]):
        subprocess.run(["git", *a], cwd=p, check=True, capture_output=True)
    (p / ".gitignore").write_text("ignored.jsonl\n", encoding="utf-8")
    (p / "kept.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=p, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=p, check=True, capture_output=True)
    return p


def test_the_commit_is_pathspec_limited_and_leaves_other_dirt_alone(repo):
    """The dispatcher commits what the cadence wrote and nothing else. `git add -A` would sweep
    up whatever else was in the checkout under a message saying a task file was created."""
    (repo / "new.md").write_text("task\n", encoding="utf-8")
    (repo / "kept.txt").write_text("two\n", encoding="utf-8")       # unrelated dirt
    out = D.commit_paths(repo, ["new.md"], "chore(cadence): x")
    assert out["committed"] and out["commit"]
    tree = D.tree_state(repo)
    assert tree["dirty_paths"] == ["kept.txt"]
    assert D.is_tracked(repo, repo / "new.md")


def test_an_ignored_path_is_skipped_rather_than_failing_the_commit(repo):
    """A project may ignore its event store (the test projects do) or track it (the real one
    does). `git add` on an ignored path is an error, and letting that abort the commit would
    leave a registered task file uncommitted for a reason that has nothing to do with it."""
    (repo / "new.md").write_text("task\n", encoding="utf-8")
    (repo / "ignored.jsonl").write_text("{}\n", encoding="utf-8")
    out = D.commit_paths(repo, ["new.md", "ignored.jsonl", "missing.yaml"],
                         "chore(cadence): x")
    assert out["committed"]
    assert out["committed_paths"] == ["new.md"]
    assert sorted(out["skipped"]) == ["ignored.jsonl", "missing.yaml"]


def test_a_commit_with_nothing_committable_reports_rather_than_raising(repo):
    out = D.commit_paths(repo, ["ignored.jsonl"], "chore(cadence): x")
    assert out["committed"] is False and out["reason"] == "nothing_to_commit"


# ------------------------------------------------------- start_period: Airflow's start_date

def test_a_period_before_start_period_is_never_due():
    """The condition this exists for, in one test. A monthly schedule switched on partway
    through a month finds the CURRENT period due with no instance on disk — and `catchup=False`
    does not help, because the offending period is not an earlier one. Without a start boundary,
    installing this cadence on 2026-09-16 would create a second September cycle for a month
    cycle 4 already measured."""
    rule = _entry()["rule"]
    mid_september = datetime(2026, 9, 16, 3, 25, tzinfo=timezone.utc)
    assert C.is_due(rule, mid_september) is True                    # the rule alone says yes
    assert C.is_due(rule, mid_september, start_period="2026-10") is False


def test_the_start_period_itself_is_served():
    """A boundary that excluded its own period would be off by one month, forever."""
    rule = _entry()["rule"]
    assert C.is_due(rule, datetime(2026, 10, 5, tzinfo=timezone.utc), "2026-10") is True
    assert C.is_due(rule, datetime(2026, 10, 4, tzinfo=timezone.utc), "2026-10") is False


def test_next_due_instants_skips_periods_before_the_start(project):
    nxt = C.next_due_instants(_entry()["rule"], datetime(2026, 9, 16, tzinfo=timezone.utc),
                              3, "2026-10")
    assert [(d.year, d.month, d.day) for d in nxt] == [(2026, 10, 5), (2026, 11, 2),
                                                       (2026, 12, 7)]


def test_evaluate_entry_reports_the_start_boundary_as_a_value(project):
    row = C.evaluate_entry(project, _entry(start_period="2026-10"),
                           datetime(2026, 9, 16, tzinfo=timezone.utc))
    assert row["period"] == "2026-09"
    assert row["start_period"] == "2026-10" and row["before_start"] is True
    assert row["due"] is False
    assert row["next_due"][0] == "2026-10-05T00:00:00Z"


@pytest.mark.parametrize("bad", ["2026", "October 2026", "2026-1", 202610, None])
def test_a_start_period_that_is_not_a_period_identifier_refuses(tmp_path, bad):
    with pytest.raises(C.CadenceConfigError, match="start_period"):
        _load(tmp_path, [_entry(start_period=bad)])
