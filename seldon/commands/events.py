"""`seldon events` — event-log maintenance and recoverability auditing.

Three commands, all built around one invariant: **the event log is append-only
and immutable.** Nothing here ever rewrites a line.

- ``migrate-legacy-ids`` — append a ``legacy_event_id_assigned`` record for each
  pre-envelope record that has no ``event_id``, freezing its deterministic
  derived id in the log.
- ``audit`` — read-only survey of one or many projects' logs for the same
  defect.
- ``replay-check`` — replay each log into a throwaway database and diff the
  result against the live graph. This is the measurement behind the
  Recoverability guarantee.
"""
from __future__ import annotations

from pathlib import Path
from typing import List

import click

from seldon.config import get_neo4j_driver, load_project_config
from seldon.core.events import append_event, event_count, make_event, read_events
from seldon.core.legacy_events import (
    LEGACY_ASSIGNMENT_EVENT_TYPE,
    assignment_records,
    is_legacy_record,
    make_assignment_payload,
    raw_records,
    scan_legacy_records,
    verify_assignments,
)
from seldon.core.projects import (
    DEFAULT_SCAN_DEPTH,
    PROJECT_ROOTS_ENV_VAR,
    ProjectRef,
    load_project_ref,
    resolve_projects,
)


@click.group("events")
def events_group():
    """Inspect and repair the JSONL event log."""


# ---------------------------------------------------------------------------
# Shared option sets
# ---------------------------------------------------------------------------

def _scope_options(f):
    """Attach the project-scope options shared by `audit` and `replay-check`."""
    f = click.option(
        "--project-dir", "project_dirs", multiple=True,
        type=click.Path(exists=True, file_okay=False),
        help="Audit this project. Repeatable. Suppresses root scanning.",
    )(f)
    f = click.option(
        "--roots", "roots", multiple=True,
        type=click.Path(exists=True, file_okay=False),
        help="Directory to scan for projects. Repeatable. Defaults to "
             f"${PROJECT_ROOTS_ENV_VAR}, then to the current project alone.",
    )(f)
    f = click.option(
        "--depth", default=DEFAULT_SCAN_DEPTH, show_default=True, type=int,
        help="Maximum directory levels below each root to scan.",
    )(f)
    return f


def _log_status(ref: ProjectRef) -> dict:
    """Read one project's log and classify its legacy-id health.

    Args:
        ref: The project to inspect.

    Returns:
        A dict with keys ``events``, ``legacy``, ``assigned``, ``unassigned``,
        ``tamper`` and ``error``. ``error`` is populated instead of raising when
        the log is unreadable, so a fleet audit reports every project.
    """
    status = {
        "events": 0, "legacy": 0, "assigned": 0, "unassigned": 0,
        "tamper": [], "error": None,
    }
    if ref.not_a_project:
        status["error"] = ref.not_a_project
        return status
    if ref.config_error:
        status["error"] = f"seldon.yaml unreadable — {ref.config_error}"
        return status
    if not ref.event_log.exists():
        status["error"] = "no seldon_events.jsonl"
        return status
    try:
        events = read_events(ref.path)
    except Exception as exc:
        status["error"] = f"{type(exc).__name__}: {exc}"
        return status

    legacy_rows = scan_legacy_records(events)
    assigned = assignment_records(events)
    status["events"] = len(events)
    status["legacy"] = len(legacy_rows)
    status["assigned"] = len([r for r in legacy_rows if r["ordinal"] in assigned])
    status["unassigned"] = len([r for r in legacy_rows if r["ordinal"] not in assigned])
    status["tamper"] = verify_assignments(events)
    return status


# ---------------------------------------------------------------------------
# migrate-legacy-ids
# ---------------------------------------------------------------------------

@events_group.command("migrate-legacy-ids")
@click.option("--dry-run", is_flag=True, default=False,
              help="Report the plan without appending anything. The dry run "
                   "derives exactly the ids the live run would append, so its "
                   "report predicts the live outcome exactly.")
@click.option("--project-dir", "project_dir_opt", default=None,
              type=click.Path(exists=True, file_okay=False),
              help="Project root to migrate. Defaults to the current directory.")
@click.option("--actor", default="human", show_default=True)
@click.option("--authority", default="accepted", show_default=True)
def migrate_legacy_ids(dry_run, project_dir_opt, actor, authority):
    """Assign deterministic ids to pre-envelope event-log records.

    Early Seldon wrote flat records with no ``event_id``. `read_events`
    de-duplicates on that field, so two such records looked like a collision and
    the whole log became unreadable — full replay was impossible and
    Recoverability, a declared guaranteed property, was broken.

    This command **appends** one ``legacy_event_id_assigned`` record per legacy
    line, carrying that line's ordinal, its full sha256 content digest, and the
    id derived from them. It never edits a line. The id recipe and the argument
    that a derived id cannot collide with a real uuid4 are in
    `seldon.core.legacy_events`.

    The appended records are **not** a lookup table `read_events` depends on:
    the reader re-derives every id from the line's own content on every read, so
    the log is readable whether or not this command has run. What the records
    add is *tamper evidence* — `seldon verify` re-derives each id and reports a
    mismatch, which can only mean an append-only line was edited.

    Idempotent. A record that already has an assignment is skipped, so a re-run
    appends nothing.
    """
    project_dir = Path(project_dir_opt) if project_dir_opt else Path.cwd()
    log_path = project_dir / "seldon_events.jsonl"

    if not log_path.exists():
        click.echo(f"No event log at {log_path}. Nothing to migrate.")
        return

    records = raw_records(log_path)
    events = read_events(project_dir)
    already = assignment_records(events)

    plan = []
    for ordinal, record in enumerate(records, start=1):
        if not is_legacy_record(record):
            continue
        payload = make_assignment_payload(ordinal, record)
        plan.append((ordinal, payload, ordinal in already))

    total_legacy = len(plan)
    pending = [p for p in plan if not p[2]]

    click.echo(f"Event log: {log_path}")
    click.echo(f"  records parsed        {len(records)}")
    click.echo(f"  legacy (no event_id)  {total_legacy}")
    click.echo(f"  already assigned      {total_legacy - len(pending)}")
    click.echo(f"  to assign             {len(pending)}")

    if total_legacy == 0:
        click.echo("\nNo legacy records. Nothing to do.")
        return

    click.echo()
    for ordinal, payload, done in plan:
        mark = "=" if done else "+"
        click.echo(
            f"  {mark} ordinal {ordinal:>6}  {payload['legacy_event_type']:<24} "
            f"{payload['assigned_event_id']}"
        )

    if not pending:
        click.echo("\nEvery legacy record already has an assignment record. No-op.")
        return

    if dry_run:
        click.echo(f"\nDry run — {len(pending)} record(s) would be appended. Nothing written.")
        return

    for ordinal, payload, _done in pending:
        append_event(
            project_dir,
            make_event(
                event_type=LEGACY_ASSIGNMENT_EVENT_TYPE,
                actor=actor,
                authority=authority,
                payload=payload,
            ),
        )

    click.echo(f"\nAppended {len(pending)} {LEGACY_ASSIGNMENT_EVENT_TYPE} record(s).")

    # Prove the repair on the way out: re-read and re-verify.
    events = read_events(project_dir)
    problems = verify_assignments(events)
    click.echo(f"Log now reads back cleanly: {len(events)} events "
               f"({event_count(project_dir)} lines).")
    if problems:
        click.echo("\nAssignment verification FAILED:", err=True)
        for p in problems:
            click.echo(f"  {p}", err=True)
        raise SystemExit(2)
    click.echo("Assignment verification passed.")


# ---------------------------------------------------------------------------
# audit
# ---------------------------------------------------------------------------

@events_group.command("audit")
@_scope_options
def events_audit(project_dirs, roots, depth):
    """Survey event logs for missing ``event_id`` values. Read-only.

    Reports, per project: total events, how many are legacy records, how many
    already carry an assignment record, and any tamper finding. Nothing is
    written to any project — a defect in someone else's project is theirs to
    migrate, not this command's to fix.
    """
    projects, notes = resolve_projects(project_dirs, roots, depth=depth)
    for note in notes:
        click.echo(f"  {note}")
    click.echo()

    if not projects:
        click.echo("No projects to audit.")
        return

    width = max(len(p.name) for p in projects)
    click.echo(f"  {'project'.ljust(width)}  {'database':<38} "
               f"{'events':>7} {'legacy':>7} {'assigned':>9} {'unassigned':>11}")
    click.echo(f"  {'-' * width}  {'-' * 38} {'-' * 7} {'-' * 7} {'-' * 9} {'-' * 11}")

    defective: List[str] = []
    broken: List[str] = []
    for ref in projects:
        st = _log_status(ref)
        db = ref.database or "(unset)"
        if st["error"]:
            click.echo(f"  {ref.name.ljust(width)}  {db:<38} {st['error']}")
            broken.append(ref.name)
            continue
        click.echo(
            f"  {ref.name.ljust(width)}  {db:<38} "
            f"{st['events']:>7} {st['legacy']:>7} {st['assigned']:>9} {st['unassigned']:>11}"
        )
        if st["unassigned"]:
            defective.append(ref.name)
        for problem in st["tamper"]:
            click.echo(f"      TAMPER: {problem}")

    click.echo()
    if defective:
        click.echo(
            f"  {len(defective)} project(s) hold legacy records with no assignment "
            f"record: {', '.join(defective)}"
        )
        click.echo("  Run `seldon events migrate-legacy-ids` inside each one.")
    else:
        click.echo("  No unassigned legacy records found.")
    if broken:
        click.echo(f"  {len(broken)} project(s) could not be read: {', '.join(broken)}")


# ---------------------------------------------------------------------------
# replay-check
# ---------------------------------------------------------------------------

@events_group.command("replay-check")
@_scope_options
@click.option("--verbose", is_flag=True, default=False,
              help="List every differing artifact and relationship, not just counts.")
def events_replay_check(project_dirs, roots, depth, verbose):
    """Replay each project's event log and diff it against its live graph.

    This is the measurement behind the Recoverability guarantee: if the graph is
    a projection of the log, replaying the log must reproduce the graph.

    The replay runs into a throwaway database that is created for the run and
    dropped afterwards. **No project database is ever written to** — each live
    graph is read only, to fingerprint it.

    A mismatch is usually not a replay bug. It means something wrote to the
    graph without writing an event, so that state cannot be rebuilt. Diagnose
    the un-evented write; do not reconcile by editing either side.
    """
    projects, notes = resolve_projects(project_dirs, roots, depth=depth)
    for note in notes:
        click.echo(f"  {note}")
    click.echo()

    if not projects:
        click.echo("No projects to check.")
        return

    from seldon.core.replay_check import replay_check

    failures = 0
    for ref in projects:
        click.echo(f"  {ref.name}  [{ref.database or '(unset)'}]")
        if ref.not_a_project:
            click.echo(f"      SKIP — {ref.not_a_project}")
            continue
        if ref.config_error:
            click.echo(f"      SKIP — seldon.yaml unreadable: {ref.config_error}")
            failures += 1
            continue
        if not ref.database:
            click.echo("      SKIP — seldon.yaml names no neo4j.database")
            failures += 1
            continue
        if not ref.event_log.exists():
            click.echo("      SKIP — no seldon_events.jsonl")
            continue
        try:
            config = load_project_config(ref.path)
            driver = get_neo4j_driver(config)
        except Exception as exc:
            click.echo(f"      SKIP — cannot connect: {type(exc).__name__}: {exc}")
            failures += 1
            continue
        try:
            cmp = replay_check(ref.path, driver, ref.database)
        finally:
            driver.close()

        if cmp.matches:
            # Artifact-scoped, matching what `matches` actually compared — a
            # raw node total would over-report on a database that also holds
            # non-Seldon content.
            ok_nodes, ok_edges = cmp._artifact_counts(cmp.live)
            click.echo(
                f"      OK — {cmp.events_replayed} events replayed; "
                f"{ok_nodes} artifacts / {ok_edges} "
                f"relationships reproduced exactly"
            )
            continue

        failures += 1
        for line in cmp.summary_lines():
            # `note:` lines are context, not findings — labelling them MISMATCH
            # is the same cry-wolf problem the artifact-scoped counts fixed.
            prefix = "  " if line.startswith("note:") else "MISMATCH: "
            click.echo(f"      {prefix}{line}")
        if verbose:
            for aid in cmp.missing_artifacts:
                click.echo(f"        live-only artifact {aid} "
                           f"({cmp.live.types.get(aid)}, state={cmp.live.states.get(aid)})")
            for aid in cmp.extra_artifacts:
                click.echo(f"        replay-only artifact {aid} "
                           f"({cmp.replayed.types.get(aid)})")
            for aid, live_state, replay_state in cmp.state_mismatches:
                click.echo(f"        state {aid} ({cmp.live.types.get(aid)}): "
                           f"live={live_state!r} replayed={replay_state!r}")
            for f, r, t, n in cmp.missing_edges:
                click.echo(f"        live-only edge {f} -[{r}]-> {t} x{n}")
            for f, r, t, n in cmp.extra_edges:
                click.echo(f"        replay-only edge {f} -[{r}]-> {t} x{n}")

    click.echo()
    if failures:
        click.echo(f"  {failures} project(s) did not reproduce cleanly.")
        raise SystemExit(2)
    click.echo("  All checked projects reproduce from their event log.")
