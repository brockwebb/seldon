"""`seldon cadence render` — a template can be rendered because somebody asked.

`ai-readiness-kg/cc_tasks/2026-09-19_seldon_hygiene_superseded_cadence_after.md` decision 2,
from DN-007 ruling 3.

**The condition.** `seldon/cli.py` registered no `cadence` group, and `C.render` was reachable
only from the dispatcher's cadence pass. A project whose `dispatch.cadence` is empty — which
ai-readiness-kg's is, by operator ruling on 2026-09-18 — therefore could not render its own
template with the tool that owns the format. One of its task files documented
`seldon cadence render spot_scan --target bea` as if the command existed.

The byte-identity test is the point of the whole command: a hand render that differed from
what the schedule would have written would be a second renderer, which is the thing this
exists to remove.
"""
from __future__ import annotations

import json
import os
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from seldon.commands.cadence import cadence_group
from seldon.core import cadence as C
from tests.testdb import TEST_DATABASE

NEO4J_DB = TEST_DATABASE
STORE = "seldon_events.jsonl"

#: 2026-10-05 is the first Monday of October 2026, hand-checked against a calendar as
#: `tests/test_cadence_pass.py` does.
NOW = datetime(2026, 10, 5, 0, 30, tzinfo=timezone.utc)

TEMPLATE = textwrap.dedent("""\
    # CC Task — cycle {cycle_name}, created by cadence {cadence_name} for {period}

    **Date:** {created_at}
    **Implements:** DN-006 decision 8.
    **Framework layer served (DN-005 §5 rule 1):** §2.2 Tier M
    **Spend:** zero model calls.
    **Network:** none.

    ## 1. Run the cycle as `{cycle_name}`; the RESULT is `{instance_stem}_RESULT.md`.

    ```cypher
    MATCH (a:Artifact) WHERE a.name = {name} RETURN a
    ```
    """)

VAR_TEMPLATE = textwrap.dedent("""\
    # CC Task — spot of {target}
    <!-- seldon:vars target, network_hosts -->

    **Date:** {created_at}
    **Implements:** DN-006 decision 8.
    **Framework layer served (DN-005 §5 rule 1):** §2.2 Tier M
    **Spend:** zero model calls.
    **Network:** allowlist: {network_hosts}

    ## 1. Measure {target} as `{cycle_name}`.
    """)

ENTRY = {
    "name": "scan_cycle",
    "rule": {"monthly_first_weekday": "monday", "at_utc": "00:00"},
    "template": "cc_tasks/templates/scan_cycle.md",
    "instances_dir": "cc_tasks",
    "cycle_name_format": "scan_{date}",
    "start_period": "2026-10",
    "last_instance": "",
}


@pytest.fixture
def project(tmp_path):
    p = tmp_path / "proj"
    (p / "cc_tasks" / "templates").mkdir(parents=True)
    (p / "controls.yaml").write_text(
        yaml.safe_dump({"spend": {"daily_tokens": 55_000_000}}), encoding="utf-8")
    (p / STORE).write_text("", encoding="utf-8")
    (p / "cc_tasks" / "templates" / "scan_cycle.md").write_text(TEMPLATE, encoding="utf-8")
    (p / "cc_tasks" / "templates" / "spot.md").write_text(VAR_TEMPLATE, encoding="utf-8")
    (p / "seldon.yaml").write_text(yaml.safe_dump({
        "event_store": {"path": STORE},
        "neo4j": {"database": NEO4J_DB,
                  "uri": os.getenv("NEO4J_URI", "bolt://localhost:7687")},
        "project": {"domain": "research", "name": "t", "slug": "t"},
        "dispatch": {"enabled": True, "branch": "main",
                     "standing_band_ref": "controls.yaml#spend.daily_tokens",
                     "poll_interval_s": 300, "permission_mode": "bypassPermissions",
                     "stop_file": ".seldon/DISPATCH_STOP", "log_dir": "logs/dispatch",
                     "lease_file": ".seldon/dispatch.lock",
                     "cadence": [ENTRY]},
    }, sort_keys=False), encoding="utf-8")
    return p


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    import seldon.commands.cadence as mod
    monkeypatch.setattr(mod, "_utcnow", lambda: NOW)


def _run(project, argv):
    prev = Path.cwd()
    os.chdir(project)
    try:
        return CliRunner().invoke(cadence_group, argv, catch_exceptions=False)
    finally:
        os.chdir(prev)


def _events(project):
    return [json.loads(ln) for ln in
            (project / STORE).read_text(encoding="utf-8").splitlines() if ln.strip()]


# ------------------------------------------------------- byte-identity with the cadence pass

def test_render_to_stdout_is_what_the_pass_would_have_written(project):
    """The whole point. Same entry, same instant, same bytes as `_create_instance` writes."""
    period = C.period_of(ENTRY["rule"], NOW)
    expected = C.render(
        (project / ENTRY["template"]).read_text(encoding="utf-8"),
        cycle_name=C.cycle_name_for(ENTRY, NOW),
        period=period,
        cadence_name=ENTRY["name"],
        created_at=NOW.isoformat().replace("+00:00", "Z"),
        instance_stem=C.instance_stem(ENTRY, period, NOW),
    )
    out = _run(project, ["render", "scan_cycle"])
    assert out.exit_code == 0, out.output
    assert out.output == expected


def test_stdout_render_writes_nothing_at_all(project):
    before = sorted(pp.name for pp in (project / "cc_tasks").iterdir())
    out = _run(project, ["render", "scan_cycle"])
    assert out.exit_code == 0
    assert sorted(pp.name for pp in (project / "cc_tasks").iterdir()) == before
    assert _events(project) == []


def test_a_brace_inside_a_code_fence_is_left_alone(project):
    out = _run(project, ["render", "scan_cycle"])
    assert "MATCH (a:Artifact) WHERE a.name = {name} RETURN a" in out.output


# --------------------------------------------------------------------------- the refusals

def test_an_undeclared_var_is_refused_by_name(project):
    out = _run(project, ["render", "--template", "cc_tasks/templates/spot.md",
                         "--period", "bea", "--cycle-name", "spot_bea_2026-10-05",
                         "--var", "target=BEA", "--var", "network_hosts=a.gov",
                         "--var", "targte=BEA"])
    assert out.exit_code != 0
    assert "'targte'" in out.output
    assert "not declared" in out.output


def test_a_declared_var_nobody_supplied_is_refused_by_name(project):
    out = _run(project, ["render", "--template", "cc_tasks/templates/spot.md",
                         "--period", "bea", "--cycle-name", "spot_bea",
                         "--var", "target=BEA"])
    assert out.exit_code != 0
    assert "'network_hosts'" in out.output


def test_an_unknown_placeholder_is_refused_by_name(project):
    (project / "cc_tasks" / "templates" / "typo.md").write_text(
        "# {cycle_name} and {cycle_nmae}\n", encoding="utf-8")
    out = _run(project, ["render", "--template", "cc_tasks/templates/typo.md",
                         "--period", "p", "--cycle-name", "c"])
    assert out.exit_code != 0
    assert "'cycle_nmae'" in out.output


def test_write_refuses_to_overwrite(project):
    first = _run(project, ["render", "scan_cycle", "--write"])
    assert first.exit_code == 0, first.output
    rel = first.output.strip()
    assert (project / rel).is_file()
    second = _run(project, ["render", "scan_cycle", "--write"])
    assert second.exit_code != 0
    assert "refusing to overwrite" in second.output


def test_a_template_with_no_schedule_needs_a_period_and_a_cycle_name(project):
    out = _run(project, ["render", "--template", "cc_tasks/templates/spot.md",
                         "--var", "target=BEA", "--var", "network_hosts=a.gov"])
    assert out.exit_code != 0
    assert "--period" in out.output and "--cycle-name" in out.output


def test_exactly_one_of_name_or_template(project):
    assert _run(project, ["render"]).exit_code != 0
    assert _run(project, ["render", "scan_cycle", "--template", "x.md"]).exit_code != 0


def test_an_unknown_cadence_name_names_the_configured_ones(project):
    out = _run(project, ["render", "nope"])
    assert out.exit_code != 0
    assert "scan_cycle" in out.output


# ---------------------------------------------------------------------- declared variables

def test_a_declared_var_is_substituted(project):
    out = _run(project, ["render", "--template", "cc_tasks/templates/spot.md",
                         "--period", "bea", "--cycle-name", "spot_bea_2026-10-05",
                         "--var", "target=BEA", "--var", "network_hosts=apps.bea.gov, 127.0.0.1"])
    assert out.exit_code == 0, out.output
    assert "# CC Task — spot of BEA" in out.output
    assert "**Network:** allowlist: apps.bea.gov, 127.0.0.1" in out.output
    assert "Measure BEA as `spot_bea_2026-10-05`" in out.output


def test_a_declaration_may_not_name_one_of_the_five_fields(project):
    (project / "cc_tasks" / "templates" / "bad.md").write_text(
        "# t\n<!-- seldon:vars period -->\n{period}\n", encoding="utf-8")
    out = _run(project, ["render", "--template", "cc_tasks/templates/bad.md",
                         "--period", "p", "--cycle-name", "c", "--var", "period=x"])
    assert out.exit_code != 0
    assert "period" in out.output


# ---------------------------------------------------------------------------- the event

def test_a_hand_render_writes_cadence_rendered_and_never_cadence_created(project):
    out = _run(project, ["render", "scan_cycle", "--write"])
    assert out.exit_code == 0, out.output
    events = _events(project)
    assert [e["event_type"] for e in events] == [C.EVENT_CADENCE_RENDERED]
    payload = events[0]["payload"]
    assert payload["cadence"] == "scan_cycle"
    assert payload["template"] == ENTRY["template"]
    assert payload["instance_stem"] == C.instance_stem(ENTRY, "2026-10", NOW)
    assert payload["on_request"] is True
    assert events[0]["actor"] in ("human", "cc")


def test_the_event_records_the_vars(project):
    out = _run(project, ["render", "--template", "cc_tasks/templates/spot.md",
                         "--period", "bea", "--cycle-name", "spot_bea",
                         "--var", "target=BEA", "--var", "network_hosts=apps.bea.gov",
                         "--write"])
    assert out.exit_code == 0, out.output
    payload = _events(project)[0]["payload"]
    assert payload["vars"] == {"target": "BEA", "network_hosts": "apps.bea.gov"}


def test_no_event_when_nothing_was_written(project):
    _run(project, ["render", "scan_cycle"])
    assert _events(project) == []


# ------------------------------------------------------------------------- list and check

def test_list_evaluates_every_schedule_and_writes_nothing(project):
    out = _run(project, ["list"])
    assert out.exit_code == 0, out.output
    assert "scan_cycle" in out.output and "2026-10" in out.output
    assert _events(project) == []


def test_check_fails_on_a_template_with_an_unknown_placeholder(project):
    (project / ENTRY["template"]).write_text("# {cycle_nmae}\n", encoding="utf-8")
    out = _run(project, ["check"])
    assert out.exit_code == 1
    assert "cycle_nmae" in out.output


def test_check_passes_on_the_real_template(project):
    out = _run(project, ["check"])
    assert out.exit_code == 0, out.output
    assert out.output.startswith("ok   scan_cycle")


# ----------------------------------------------------------------------------- --register

@pytest.mark.usefixtures("neo4j_available", "clean_test_db")
def test_register_creates_one_task_and_a_second_run_warns(project, neo4j_driver):
    """`--register` implies `--write` and goes through `register_task_file`, so every gate
    `seldon cc register` applies applies here. A second run renders nothing and registers
    nothing new."""
    first = _run(project, ["render", "scan_cycle", "--register"])
    assert first.exit_code == 0, first.output
    stem = C.instance_stem(ENTRY, "2026-10", NOW)
    assert (project / "cc_tasks" / f"{stem}.md").is_file()
    with neo4j_driver.session(database=NEO4J_DB) as s:
        n = s.run("MATCH (t:Artifact:ResearchTask) RETURN count(t) AS n").single()["n"]
    assert n == 1
    events = [e["event_type"] for e in _events(project)]
    assert events.count(C.EVENT_CADENCE_RENDERED) == 1

    second = _run(project, ["render", "scan_cycle", "--register"])
    assert second.exit_code == 0, second.output
    assert "already exists" in second.output
    assert "already registered" in second.output
    with neo4j_driver.session(database=NEO4J_DB) as s:
        n = s.run("MATCH (t:Artifact:ResearchTask) RETURN count(t) AS n").single()["n"]
    assert n == 1, "a second run duplicated the task"
    events = [e["event_type"] for e in _events(project)]
    assert events.count(C.EVENT_CADENCE_RENDERED) == 1, "a second run rendered again"
