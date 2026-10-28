"""`seldon dispatch` — the standing dispatcher.

Implements `ai-readiness-kg/docs/design/2026-09-15_DN-006_standing_dispatcher.md` decisions 1
to 10 (decision 8, the cadence, landed with `cc_tasks/2026-09-16_cadence_and_enable.md`), and
the rule that the dispatcher commits and pushes every line it writes to the tracked event store
(`cc_tasks/2026-09-16_dispatcher_commits_its_record.md`, DN-006 ADDENDUM_04).

    seldon dispatch once        one evaluation pass, at most one launch, exit
    seldon dispatch status      the live criteria vector for every candidate
    seldon dispatch lease reap  operator-only; refuses while the holder PID is alive

With `dispatch.max_parallel > 1` (SEL-004, AD-034; `seldon.commands.dispatch_worktree`) a pass
may launch several non-exclusive tasks, each in its own git worktree under a detached
supervisor (`seldon dispatch supervise`, hidden) that merges it on green. At the default of 1
nothing here changes, and `tests/test_dispatch_serial_transcript.py` holds that byte for byte.

**There is no daemon.** launchd is the loop and `once` is the pass, which is the pattern
`scripts/jobs/biblio_resume_job.py` already runs under in the project this was built for. A
daemon would add a process to supervise and would not make anything happen sooner than the
poll interval does.

**The pass writes at most one launch and never retries.** A retry is a decision — it belongs to
the OODA that reads the log, not to a loop that cannot see why the last attempt failed
(DN-006 decision 4).

Argument parsing and presentation only; the evaluation, the lease and the config live in
`seldon.core.dispatch` so each criterion is testable against a fixture that fails exactly it.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import click
import yaml

from seldon import models
from seldon.config import (
    bind_process_session, get_current_session, get_neo4j_driver, load_project_config,
)
from seldon.core import cadence as C
from seldon.core import qc
from seldon.core import dispatch as D
from seldon.core import instruction_context as IC
from seldon.core import stations as QS
from seldon.core import worktree as WT
from seldon.core.artifacts import transition_task
from seldon.core.events import append_event, make_event
from seldon.core.moving import is_future
from seldon.domain.loader import load_domain_config

#: Actor on every event this module writes. Not `human` and not `cc`: a dispatch is an
#: assertion the MACHINE made, and a log that attributed it to a person would misdescribe the
#: one thing the dispatcher exists to change.
ACTOR = "dispatcher"

#: The CC dispatch line `CLAUDE.md` prescribes, verbatim. The prompt is not composed here for
#: taste; it is the protocol's own sentence, and a dispatcher that paraphrased it would be
#: sending a session a different instruction from the one an operator sends.
#:
#: The one addition is `HEADLESS_CLAUSE`, which the operator's line does not carry because it
#: is false of an interactive session: under `claude -p` a turn end is the process end, and
#: the first session on `c609b1e1` (2026-09-16T14:44:47Z) backgrounded its suite, ended its
#: turn to be notified, and died with no RESULT. `ai-readiness-kg` `CLAUDE.md` states the same
#: sentence under "Headless sessions" and a test there asserts the two are byte-identical.
HEADLESS_CLAUSE = (
    "This session is headless: there is no next turn and ending it ends the process. "
    "Poll every detached command to its EXIT line inside this turn; never use "
    "background-task mode or wait to be notified."
)
DISPATCH_LINE = (
    "Read CLAUDE.md, then execute {rel}. Glob and read all sibling {stem}_ADDENDUM*.md files "
    "before starting; an addendum can amend or SUPERSEDE the base task. " + HEADLESS_CLAUSE
)

#: The mechanical guard under the clause. Claude Code documents
#: `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` as disabling "all background task functionality,
#: including the `run_in_background` parameter on Bash and subagent tools, auto-backgrounding,
#: and the Ctrl+B shortcut" (code.claude.com/docs/en/env-vars; checked against CLI 2.1.273).
#: Not a tunable: a dispatched session with background tasks enabled is the defect.
HEADLESS_ENV = {"CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1"}

#: `proposed` has no edge to `in_progress` on the ResearchTask state machine
#: (`seldon/domain/research.yaml`: proposed -> [accepted, rejected, superseded, withdrawn]).
#: DN-006 decision 4 calls the claim "the `in_progress` transition"; from `proposed` that is
#: two transitions, and the walk is the same shape `walk_to_completed` already uses for the
#: close path. Recorded in the DN-006 addendum rather than deviated from silently.
CLAIM_PATH = {"proposed": ["accepted", "in_progress"], "accepted": ["in_progress"]}


def _now() -> str:
    return _utcnow().isoformat().replace("+00:00", "Z")


def _utcnow() -> datetime:
    """The pass's clock, as one seam.

    Everything time-dependent in a pass — the cadence's "is this period due", the instance's
    date, the timestamps on the events — reads the clock through here, so a test can freeze it
    at a hand-checked instant and exercise the real calendar rather than whatever today
    happens to be. The scan harness has the same seam for the same reason (`scan/clock.py`):
    a schedule whose behaviour can only be tested during the first week of a month is a
    schedule that is untested for three weeks out of four.
    """
    return datetime.now(timezone.utc)


def _open_project():
    # The dispatcher's own events carry this process's id, never a session file another
    # process left (ai-readiness-kg/cc_tasks/2026-09-16_session_id_names_the_process.md
    # decisions 1(c) and 2). An id inherited from the environment still wins over it.
    bind_process_session()
    config = load_project_config()
    project_dir = Path.cwd()
    driver = get_neo4j_driver(config)
    domain_config = load_domain_config(
        Path(__file__).parent.parent / "domain"
        / f"{config['project'].get('domain', 'research')}.yaml")
    return (project_dir, config, driver, config["neo4j"]["database"], domain_config,
            get_current_session(project_dir))


def _tasks(driver, database, include_future: bool = False) -> list:
    """Every open ResearchTask, with its `precedes` predecessors' states.

    The graph IS the queue (DN-006 decision 1): there is no separate table to keep in step,
    and a task becomes dispatchable by being registered, not by being enqueued.

    A `FUTURE` task (TRIAGE-001 rule 4) is left out unless `include_future`: it is a parked
    idea, so it is neither a candidate nor a line in the pass's log, its counts or `status`.
    The reconciler (`_registered_files`) reads every registered task's file instead, because a
    registered FUTURE task file still has to be committed or it leaves the tree dirty.
    """
    q = ("MATCH (t:ResearchTask) WHERE t.state IN $states "
         "OPTIONAL MATCH (p:ResearchTask)-[:PRECEDES|precedes]->(t) "
         "RETURN t.artifact_id AS artifact_id, t.name AS name, t.state AS state, "
         "       t.source_file AS source_file, t.created_at AS created_at, "
         "       t.description AS description, t.waits_on_external AS waits_on_external, "
         "       collect({artifact_id: p.artifact_id, state: p.state, name: p.name, "
         "                source_file: p.source_file, updated_at: p.updated_at}) AS predecessors "
         "ORDER BY t.created_at")
    with driver.session(database=database) as s:
        rows = [dict(r) for r in s.run(q, states=list(D.DISPATCHABLE_STATES))]
    for r in rows:
        r["predecessors"] = [p for p in r["predecessors"] if p.get("artifact_id")]
    if not include_future:
        rows = [r for r in rows if not is_future(r.get("description"))]
    return rows


def _cross_waits(project_dir: Path, tasks: list) -> dict:
    """c17's input (AD-038-R8): each task's unsatisfied waits on tasks in other projects' graphs, read once per pass.

    A target whose graph cannot be read is unsatisfied, and each one is logged to stderr (the pass's log), so an
    outage in another project is visible where the held task is. The waiting project's config is read here; a
    config that cannot be read is raised, not defaulted, because a pass that guessed would read the wrong graphs.
    """
    from seldon.core import cross_project as X
    return X.unsatisfied_waits(project_dir, tasks, on_error=lambda line: click.echo(line, err=True))


def _ooda_waits(project_dir: Path, cfg: dict, tasks: list) -> dict:
    """c18's input (AD-038-R17): each chained task's OODA gate, from one read of the ledger per pass. Nothing is read
    when the project's knowledge source is off, so a project that has not opted in pays nothing for it."""
    if not cfg["ooda"]["enabled"]:
        return {}
    from seldon.core.events import read_events
    return D.ooda_waits(project_dir, tasks, cfg, D.ooda_index(read_events(project_dir)), _utcnow())


def _ooda_fire(project_dir, config, cfg, driver, database, session_id) -> list:
    """AD-038-R16: run the OODAs due now (at most `dispatch.ooda.max_per_pass`) and commit their records. Callers hold
    the pass lease with no session in flight. Nothing is read when the knowledge source is off."""
    if not cfg["ooda"]["enabled"]:
        return []
    from seldon.commands import dispatch_ooda as DO
    records = DO.fire(project_dir, config, cfg, session_id, _tasks(driver, database))
    if records:
        _record_own_lines(project_dir, config, cfg)
    return records


def _claim_in_flight(driver, database) -> dict | None:
    """Any task the dispatcher already holds `in_progress`. c6's graph half.

    Scoped to a dispatcher claim marker: a task a HUMAN took `in_progress` is decision 10's
    territory — the rule that the operator does not hand-dispatch while this is enabled — and
    the dispatcher reports it rather than pretending to guard it.
    """
    q = ("MATCH (t:ResearchTask {state: 'in_progress'}) "
         "RETURN t.artifact_id AS artifact_id, t.claimed_by AS claimed_by, "
         "       t.claimed_at AS claimed_at")
    with driver.session(database=database) as s:
        for r in s.run(q):
            if str(r["claimed_by"] or "").startswith("dispatcher:"):
                return dict(r)
    return None


def _claims_in_flight(driver, database) -> list:
    """Every task a dispatcher claim holds `in_progress`, with its source file. SEL-004: in
    parallel mode several are in flight at once, one per worktree."""
    q = ("MATCH (t:ResearchTask {state: 'in_progress'}) "
         "WHERE t.claimed_by STARTS WITH 'dispatcher:' "
         "RETURN t.artifact_id AS artifact_id, t.claimed_by AS claimed_by, "
         "       t.claimed_at AS claimed_at, t.source_file AS source_file, t.name AS name "
         "ORDER BY t.claimed_at")
    with driver.session(database=database) as s:
        return [dict(r) for r in s.run(q)]


def _survey(project_dir, config, driver, database):
    """Everything a pass needs to decide, gathered once. Shared by `once` and `status` so the
    two can never disagree about what the criteria said."""
    cfg = D.load_dispatch_config(project_dir, config)
    band = D.resolve_standing_band(project_dir, cfg["standing_band_ref"])
    lease_body = D.read_lease(project_dir / cfg["lease_file"])
    if cfg["max_parallel"] > 1:
        # SEL-004: the parallel pass's own survey, plan included, so `status` shows why a
        # task waits beside the running ones exactly as the next pass would decide it.
        from seldon.commands import dispatch_worktree as W
        survey = W.survey(project_dir, cfg, driver, database, band, lease_body)
        return cfg, band, survey["tree"], lease_body, survey["claim"], survey["rows"]
    tree = D.tree_state(project_dir)
    claim = _claim_in_flight(driver, database)
    holds = _premise_holds(project_dir, driver, database)
    launch_holds = _launch_holds(project_dir)
    union = D.union_state(project_dir)
    tasks = _tasks(driver, database)
    cross = _cross_waits(project_dir, tasks)
    ooda = _ooda_waits(project_dir, cfg, tasks)
    rows = [D.evaluate(project_dir, t, cfg, band, tree, claim, lease_body, premise_holds=holds,
                       launch_holds=launch_holds, union=union, cross_waits=cross, ooda=ooda)
            for t in tasks]
    return cfg, band, tree, lease_body, claim, D.fifo(rows)


def _emit(project_dir, session_id, event_type, payload):
    append_event(project_dir, make_event(event_type=event_type, actor=ACTOR,
                                         authority="accepted", payload=payload,
                                         session_id=session_id))


def _store_rel(config) -> str:
    return config.get("event_store", {}).get("path", "seldon_events.jsonl")


def _registered_files(driver, database) -> set:
    """The `source_file` of every registered ResearchTask, in any state: what qualifies an untracked task file or
    addendum as registration output for the reconciler (AD-038-R1)."""
    q = "MATCH (t:ResearchTask) WHERE t.source_file IS NOT NULL RETURN DISTINCT t.source_file AS f"
    with driver.session(database=database) as s:
        return {r["f"] for r in s.run(q)}


def _declare_union(project_dir, config) -> None:
    """AD-034 ADDENDUM 05, by AD-038-R1 (the machine reconciles its own state): declare the project's append-only
    logs `merge=union` when git does not merge them so, and commit `.gitattributes` alone, as `seldon hooks install`
    does. Without it every worktree task whose main gained a line meanwhile ends `rebase_conflict` (squiddy SQ-021).

    Called by `_reconcile`, so under the lease, with no claim in flight and on the configured branch. A
    `.gitattributes` with uncommitted edits is someone's work in progress and is left alone; so is any failure to
    write or commit, which is printed. In both cases c16 then refuses every launch and names the files."""
    from seldon.core import hooks as H
    if D.git(project_dir, "status", "--porcelain", "--", H.GITATTRIBUTES).stdout.strip():
        click.echo(f"union: {H.GITATTRIBUTES} has uncommitted edits; not declaring (c16 names what is missing)",
                   err=True)
        return
    try:
        out = H.declare_union(project_dir, config)
    except H.HookError as exc:
        click.echo(f"union: NOT declared: {exc}", err=True)
        return
    if out["committed"]:
        click.echo(f"union: {H.GITATTRIBUTES} declares {', '.join(out['added'])} merge=union -> {out['commit']} "
                   f"(AD-034 ADDENDUM 05)")


def _reconcile(project_dir, config, cfg, driver, database) -> dict:
    """AD-038-R1: commit every dirty path of machine-written governed state, one commit per class, before c7.

    Replaces the per-writer sweeps this pass used to run (`_record_own_lines` over `COMMITTABLE_ACTORS`, the
    prior-art leftovers, `_commit_registered` and its registration-record sweep): 797 refused passes in a week were
    all dirt the system wrote itself (`docs/design/AD-038_the_machine_reconciles_its_own_state.md` §1). What
    qualifies a path is its class and its change (`seldon.core.reconcile`), never its writer.

    **Callers hold the lease and have no claim in flight**, so nothing else is working in the checkout. Nothing is
    committed on a branch other than the configured one. Returns `{commits, unreconciled}`; each commit is printed,
    and `unreconciled` is what c7 names when it refuses.
    """
    from seldon.core import reconcile as R
    if D.tree_state(project_dir)["branch"] != cfg["branch"]:
        return {"commits": [], "unreconciled": [], "skipped": "wrong_branch"}
    _declare_union(project_dir, config)
    try:
        out = R.reconcile(project_dir, config, _registered_files(driver, database))
    except RuntimeError as exc:
        # git status failed: c7's own read reports it as tree_unreadable.
        click.echo(f"reconcile: NOT run: {exc}", err=True)
        return {"commits": [], "unreconciled": [], "skipped": "git_failed"}
    for c in out["commits"]:
        if c.get("committed"):
            click.echo(f"record: {c['message']} -> {c['commit']}")
        else:
            click.echo(f"record: {', '.join(c['paths'])} NOT committed ({c['class']}, {c.get('reason')}): "
                       f"{c.get('stderr', '')}", err=True)
    # A governed path the reconciler refused (a ledger edited in place, a register record rewritten) is
    # printed here as well as by c7: a pass with no candidate prints no refusal line, and this one must
    # not go unseen. Ordinary dirt (a source file) is c7's alone to name.
    for u in out["unreconciled"]:
        if not u["why"].startswith("not machine-written"):
            click.echo(f"record: {u['path']} NOT committed: {u['why']}", err=True)
    return out


def _unreconciled(project_dir, config, driver, database, done: dict | None) -> list:
    """What c7 names for a dirty tree: the reconciler's leftovers, or, when it did not run (a dry run, a claim in
    flight), the paths it would not commit."""
    from seldon.core import reconcile as R
    if done is not None and "skipped" not in done:
        return done["unreconciled"]
    try:
        return R.classify(project_dir, config, _registered_files(driver, database))["unreconciled"]
    except RuntimeError:
        return []


def _breaker_and_stale(project_dir, config, driver, database, domain_config, session_id, cfg) -> None:
    """DISP-002 (AD-034 ADDENDUM 02), run by a pass with no session in flight: merge each task blocked by the
    classifier breaker whose work was green (`remerge_breaker_green`), then remove each kept worktree that holds
    nothing (`sweep_stale_kept`). A failure of either is reported, not raised, as `_auto_redrive`'s is: the pass that
    launches the queue must not die on a housekeeping step, and the next pass tries again."""
    from seldon.commands import dispatch_worktree as W
    for step, call in (("remerge", lambda: W.remerge_breaker_green(project_dir, config, driver, database,
                                                                    domain_config, session_id, cfg)),
                       # DISP-003R (AD-034 ADDENDUM 03): kept work blocked `stop_gate_unpassed` is re-gated in place.
                       ("regate", lambda: W.regate(project_dir, config, driver, database, domain_config,
                                                   session_id, cfg)),
                       ("stale kept sweep", lambda: W.sweep_stale_kept(project_dir, driver, database, session_id))):
        try:
            call()
        except Exception as exc:                                        # noqa: BLE001
            click.echo(f"{step}: NOT done: {type(exc).__name__}: {exc}", err=True)


def _auto_redrive(project_dir, driver, database, domain_config, session_id) -> list:
    """Redrive the blocked tasks whose stop was the dispatcher's own defect (AD-038-R2;
    `seldon.core.redrive.AUTO_REDRIVE_REASONS`). Each is printed; a failure is reported, not raised, since
    the pass's other work does not depend on it and the next pass tries again."""
    from seldon.core import redrive as RD
    try:
        done = RD.auto_redrive(project_dir, driver, database, domain_config, session_id)
    except (RD.RedriveRefused, ValueError) as exc:
        click.echo(f"redrive: automatic redrive NOT done: {exc}", err=True)
        return []
    for r in done:
        click.echo(f"redrive: {r['task_id'][:8]} {r['source_file']} -> accepted "
                   f"(answers {r['stop_event_type']} {r['stop_reason']})")
    return done


def _record_own_lines(project_dir, config, cfg) -> dict:
    """Commit the lines appended to the tracked event store, whoever wrote them (AD-038-R1).

    `ai-readiness-kg/cc_tasks/2026-09-16_dispatcher_commits_its_record.md` decision 1, closing
    DN-006 ADDENDUM_03 §4: `dispatch_finished` is appended AFTER the dispatched session has
    committed and pushed, so before this every completed dispatch left the store modified by a
    line only the dispatcher wrote.

    **Callers hold the lease.** A held lease is how a pass knows no dispatched session is
    working in the checkout; a `git commit` beside a working session is DD-019's class and an
    `index.lock` collision besides. The three lines written WITHOUT the lease (`lease_held`,
    `dispatch_observed_stop`, `api_key_present`) are therefore never committed where they are
    written, and the next pass that holds the lease commits them first (`_pass`).

    **The actor allowlist is gone** (AD-038-R1, FRICTION-001 Part A). It admitted `dispatcher`
    and `desktop` lines and refused `cc`, `governed_sync` and every other writer, which turned the
    system's own writes into c7 dirt for the whole queue. The DD-019 guard it stood for is the
    lease: every caller holds it with no session working. What still refuses is a store that is not
    append-only against HEAD, or a line that does not parse; c7 names it.
    """
    from seldon.core import reconcile as R
    store = _store_rel(config)
    if D.tree_state(project_dir)["branch"] != cfg["branch"]:
        return {"committed": False, "reason": "wrong_branch"}
    try:
        out = R.reconcile(project_dir, config, set(), classes=("event_store",))
    except RuntimeError as exc:
        click.echo(f"record: {store} NOT committed: {exc}", err=True)
        return {"committed": False, "reason": "git_failed"}
    if not out["commits"]:
        why = R.appended_rows(project_dir, store)
        if not why["ok"] and why["why"] != "deleted" and _store_dirty(project_dir, store):
            click.echo(f"record: {store} NOT committed: {why['why']}", err=True)
            return {"committed": False, "reason": why["why"]}
        return {"committed": False, "reason": "clean"}
    c = out["commits"][0]
    if c.get("committed"):
        click.echo(f"record: {c['message']} -> {c['commit']}")
    else:
        click.echo(f"record: {store} NOT committed ({c.get('reason')}): {c.get('stderr', '')}", err=True)
    return c


def _store_dirty(project_dir, store) -> bool:
    return bool(D.git(project_dir, "status", "--porcelain", "--", store).stdout.strip())


def _push(project_dir, cfg) -> dict:
    """Decision 2: push whatever the branch is ahead by. A failure is reported on stdout, where
    the wrapper's log carries it, and is NOT a refusal and NOT an event — the next pass under
    the lease retries it because the branch is still ahead, and git records the beginning."""
    if D.tree_state(project_dir)["branch"] != cfg["branch"]:
        return {"pushed": False, "reason": "wrong_branch"}
    out = D.push_if_ahead(project_dir)
    if out["pushed"]:
        click.echo(f"push: pushed {out['ahead']} commit(s)")
    elif out["reason"] == "push_failed":
        click.echo(f"push FAILED ({out['ahead']} commit(s) ahead; retried next pass): "
                   f"{out.get('stderr', '')}")
    elif out["reason"] == "no_upstream":
        click.echo(f"push: branch {cfg['branch']} has no upstream; nothing pushed")
    return out


def _record_and_push(project_dir, config, cfg) -> None:
    _record_own_lines(project_dir, config, cfg)
    _push(project_dir, cfg)


@click.group("dispatch")
def dispatch_group():
    """The standing dispatcher: a registered task with a clean gate no longer waits."""


@dispatch_group.command("status")
@click.option("--json", "as_json", is_flag=True, help="machine-readable, the whole survey")
def dispatch_status(as_json):
    """The live criteria vector for every open task, the lease holder, launches in flight.

    Writes NO event. `status` is the operator's eye; the log records assertions the dispatcher
    made, and looking is not one (DN-006 decision 7).
    """
    project_dir, config, driver, database, _dc, _sid = _open_project()
    try:
        cfg, band, tree, lease_body, claim, rows = _survey(project_dir, config, driver, database)
    finally:
        driver.close()
    cadence_rows = _cadence_rows(project_dir, cfg)
    # AD-034 ADDENDUM 05: a fact about the checkout, reported once at the top as well as per task (c16).
    union = D.union_state(project_dir)
    payload = {"enabled": cfg["enabled"], "branch": tree["branch"],
               "union_attribute_missing": None if union["ok"] else (union["missing"] or union.get("read_error")),
               "configured_branch": cfg["branch"], "tree_dirty": tree["dirty"],
               "tree_dirty_count": tree["dirty_count"],
               "tree_read_error": tree.get("read_error"),
               "stuck_state_file": str(D.stuck_state_path(project_dir, cfg)),
               "stuck_due": _stuck_due(project_dir, cfg, rows, tree, claim),
               "stop_file": str(cfg["stop_file"]),
               "stop_file_present": (project_dir / cfg["stop_file"]).exists(),
               "standing_band": band, "standing_band_ref": cfg["standing_band_ref"],
               "permission_mode": cfg["permission_mode"],
               "lease": lease_body or None, "claim_in_flight": claim,
               "open_tasks": len(rows),
               "candidates": sum(1 for r in rows if r["candidate"]),
               "eligible": [r["task_id"] for r in rows if r["eligible"]],
               "cadence": cadence_rows,
               "max_parallel": cfg["max_parallel"],
               "worktree_leases": D.worktree_leases(project_dir, cfg),
               # QC-002: station (a)'s outcome on the last pass that reviewed premises, and open huddles (d).
               "last_premise_review": _stations_mod().last_premise_review(project_dir, cfg),
               "open_huddles": _open_huddles(project_dir),
               "tasks": rows}
    if as_json:
        click.echo(json.dumps(payload, indent=1, default=str))
        return
    click.echo(f"dispatch: enabled={cfg['enabled']}  branch={tree['branch']}"
               f" (configured {cfg['branch']})  dirty={tree['dirty']}"
               f" ({tree['dirty_count']} path(s))")
    if not union["ok"]:
        click.echo(f"  union_attribute_missing: "
                   f"{', '.join(union['missing']) or union.get('read_error')} "
                   f"(not merge=union; run `seldon hooks install`, AD-034 ADDENDUM 05)")
    click.echo(f"  stop file   : {cfg['stop_file']} "
               f"{'PRESENT' if payload['stop_file_present'] else 'absent'}")
    click.echo(f"  standing band: {band:,} tokens  <- {cfg['standing_band_ref']}")
    held = (lease_body or {}).get("holder")
    click.echo(f"  lease        : {held or 'free'}"
               + (f" (released {lease_body['released_at']})"
                  if not held and (lease_body or {}).get("released_at") else ""))
    click.echo(f"  claim        : {claim['artifact_id'][:8] + ' by ' + claim['claimed_by'] if claim else 'none'}")
    click.echo(f"  max_parallel : {cfg['max_parallel']}  (every task in a worktree under "
               f"{D.CLI_WORKTREE_DIR}/, gate: {cfg['gate_command']})")
    for wl in payload["worktree_leases"]:
        b = wl["body"]
        held = (f"{b.get('holder')} ({'alive' if wl['alive'] else 'GONE — `seldon dispatch '}"
                f"{'' if wl['alive'] else 'lease reap --task ' + wl['stem'] + '`'})"
                if wl["held"] else f"released {b.get('released_at')}")
        click.echo(f"  worktree     : {wl['stem']}  {b.get('worktree')} on {b.get('branch')}  "
                   f"lease {held}")
    click.echo(f"  open tasks   : {len(rows)}  candidates: {payload['candidates']}  "
               f"eligible: {len(payload['eligible'])}")
    for cr in cadence_rows:
        if cr["before_start"]:
            served = f"not due (before start_period {cr['start_period']})"
        else:
            served = cr["instance"] or ("DUE, no instance" if cr["due"] else "not due")
        click.echo(f"  cadence      : {cr['cadence']} {cr['period']} due {cr['due_at']} "
                   f"-> {served}")
        click.echo(f"                 next: {', '.join(cr['next_due'])}")
    click.echo("")
    for r in rows:
        head = f"  {(r['task_id'] or '?')[:8]}  {r['state']:9s}"
        if not r["candidate"]:
            click.echo(f"{head}  NOT A CANDIDATE ({r['not_a_candidate_reason']})  "
                       f"{r['source_file'] or ''}")
            if r.get("not_a_candidate_message"):
                click.echo(f"      {r['not_a_candidate_message']}")
            continue
        verdict = "ELIGIBLE" if r["eligible"] else f"ineligible on {','.join(r['failed'])}"
        click.echo(f"{head}  {verdict}  {r['source_file']}")
        for key in sorted(r["criteria"]):
            c = r["criteria"][key]
            mark = "ok " if c["ok"] else "NO "
            detail = {k: v for k, v in c.items() if k != "ok"}
            click.echo(f"      {mark}{key}: {json.dumps(detail, default=str)}")


@dispatch_group.command("once")
@click.option("--dry-run", is_flag=True,
              help="evaluate and report the chosen task; claim nothing and launch nothing")
def dispatch_once(dry_run):
    """One evaluation pass: at most one launch, then exit (up to max_parallel worktree
    launches when `dispatch.max_parallel > 1`).

    Exit code is 0 in every ordinary outcome, including "nothing eligible", "lease held",
    "disabled" and "STOP file present" — the same contract the burn's cap exhaustion has, so
    launchd does not learn to treat a healthy no-op as a failure.
    """
    project_dir, config, driver, database, domain_config, session_id = _open_project()
    try:
        cfg = D.load_dispatch_config(project_dir, config)
        stop = project_dir / cfg["stop_file"]

        # DD-007, BEFORE any claim and before the lease: an inherited API key means a
        # dispatched session would spend against a credential nobody declared. The refusal
        # carries no task id because no task was chosen.
        key = D.api_key_present()
        if key:
            _emit(project_dir, session_id, D.EVENT_REFUSED,
                  {"task_id": None, "reason": "api_key_present", "variable": key})
            click.echo(f"refused: {key} is set; dispatch is Max OAuth only (DD-007)", err=True)
            return

        if not cfg["enabled"] or stop.exists():
            # The kill switch, read on this pass and never cached. A STOP file gets its own
            # event ONCE per appearance so the log shows when the operator stopped the world,
            # without a line every five minutes for as long as it stays stopped.
            reason = "stop_file" if stop.exists() else "disabled"
            if reason == "stop_file" and not _stop_already_observed(project_dir, stop):
                _emit(project_dir, session_id, D.EVENT_OBSERVED_STOP,
                      {"stop_file": str(stop), "observed_at": _now(),
                       "stop_mtime": stop.stat().st_mtime})
            click.echo(f"dispatch is {reason}; nothing evaluated")
            return

        # HOOK-001: a dispatched session commits through the same gate as everyone else. The
        # hook is tracked, so every checkout and worktree carries it; this points git at it when
        # the repository's config does not (a fresh clone, a moved checkout). A checkout without
        # the hook launches nothing: a standing condition, so it is printed, not logged.
        from seldon.core import hooks as H
        gate = H.ensure_installed(project_dir)
        if not gate["ok"]:
            click.echo(f"refused: the commit gate is not installed: {gate['error']} "
                       f"(run `seldon hooks install`)", err=True)
            return

        try:
            lease = D.Lease(project_dir / cfg["lease_file"]).__enter__()
        except D.LeaseHeld as held:
            # ONE event per lease ACQUISITION, and never one per pass — the STOP file's
            # treatment three lines above, for the STOP file's reason. A held lease is a
            # STANDING CONDITION: it lasts for as long as the dispatched session it belongs to
            # runs, and a five-minute poll wrote THREE identical refusals for one acquisition
            # inside the first session this dispatcher ever launched
            # (`ai-readiness-kg/cc_tasks/2026-09-16_publication_guards_RESULT.md` §0; the
            # three are still on that project's log, at 04:27:49Z, 04:36:55Z and 04:38:55Z,
            # all naming holder `dispatcher:HexagonMBP.local:71841`).
            #
            # It earns its ONE event rather than the silence `dirty_tree` and `disabled` get,
            # and the difference is the rule DN-006 ADDENDUM_03 states: a standing condition is
            # recorded here only when its beginning is recorded NOWHERE ELSE a reader can
            # reach. `.seldon/dispatch.lock` is gitignored runtime state that the next
            # acquisition overwrites, so an acquisition leaves no other trace unless the pass
            # that took it went on to launch something. A dirty tree, a disabled flag and an
            # over-band header are all facts about tracked files, and git already says when
            # each began.
            if not _lease_acquisition_already_refused(project_dir, held.body):
                _emit(project_dir, session_id, D.EVENT_REFUSED,
                      {"task_id": None, "reason": "lease_held",
                       "holder": held.body.get("holder"),
                       "acquired_at": held.body.get("acquired_at"),
                       "task_in_flight": held.body.get("task")})
            click.echo(f"lease held by {held.body.get('holder')}; exiting")
            # QC-002: a holder from before the stations does not inspect the session it waits on, so this pass
            # does, and reaps nothing (the session and the lease are the holder's, DN-006 decision 6).
            from seldon.commands import dispatch_stations as ST
            inspected = ST.inspect_for_held_lease(project_dir, cfg, held.body)
            if inspected is not None:
                click.echo(f"inspected {str(held.body.get('task'))[:8]} for its holder: "
                           f"{len(inspected.get('milestones') or [])} milestone(s), "
                           f"{len(inspected.get('first_articles') or [])} first article(s), "
                           f"{len(inspected.get('stops') or [])} stop(s), "
                           f"{len(inspected.get('huddles') or [])} huddle(s)"
                           + (f" ({inspected['skipped']})" if inspected.get("skipped") else ""))
            return
        try:
            _pass(project_dir, config, driver, database, domain_config, session_id, cfg,
                  lease, dry_run)
        except DATABASE_UNAVAILABLE as exc:
            _database_unavailable(project_dir, session_id, cfg, exc, dry_run)
        else:
            if not dry_run:
                _database_back(project_dir, cfg)
        finally:
            lease.__exit__(None, None, None)
    finally:
        driver.close()


@dispatch_group.command("redrive")
@click.argument("task")
@click.option("--actor", default="human", show_default=True,
              help="who redrives: human, cc or desktop (`seldon qc chart` counts each as an operator intervention)")
def dispatch_redrive(task, actor):
    """Put a blocked task back on the queue: blocked -> accepted, claim cleared (AD-038-R2).

    TASK is an artifact id, a unique id prefix, or the task file's stem. The task keeps its file, id
    and history; `dispatch_redrive` records the stop it answers. Refuses a task that is not blocked
    (exit 1). Like the dead-letter redrive of a message queue, this is the one way back; a new task
    file for the same work is what it replaces.
    """
    from seldon.core import redrive as RD
    project_dir, config, driver, database, domain_config, session_id = _open_project()
    try:
        task_id = _resolve_task(driver, database, task)
        if task_id is None:
            raise click.ClickException(f"no ResearchTask matches {task!r}")
        try:
            out = RD.redrive(project_dir, driver, database, domain_config, task_id, actor, session_id)
        except RD.RedriveRefused as exc:
            raise click.ClickException(f"redrive refused: {exc}")
    finally:
        driver.close()
    click.echo(f"redriven: {task_id[:8]} {out['source_file']} blocked -> accepted; answers "
               f"{out['stop_event_type'] or 'no recorded stop'} {out['stop_reason'] or ''}".rstrip())
    # The redrive's own lines, committed the way an MCP tool commits its append (deferred while a
    # lease is held; the next pass reconciles them, AD-038-R1).
    committed = D.commit_journal_append(project_dir, config, by="seldon dispatch redrive", actor=actor)
    if committed.get("committed"):
        click.echo(f"committed {committed['commit']}")


@dispatch_group.command("adopt")
@click.option("--project", "project", type=click.Path(file_okay=False, path_type=Path), default=".",
              show_default=True, help="the project to adopt the dispatcher in")
@click.option("--standing-band-ref", default=None, help="<file>#<key path> of the machine's token cap")
@click.option("--branch", default=None, help="the branch a pass may dispatch on")
@click.option("--label", "launchd_label", default=None, help="the launchd label")
@click.option("--gate-command", default=None, help="the re-gate command (the project's test suite); optional")
@click.option("--ooda-grace-s", type=float, default=None, help="c18's grace in seconds (0, the default, never waits)")
@click.option("--yes", is_flag=True, help="take every default without asking (headless)")
@click.option("--dry-run", is_flag=True, help="print what would be written and write nothing")
def dispatch_adopt(project, standing_band_ref, branch, launchd_label, gate_command, ooda_grace_s, yes, dry_run):
    """Opt a project into the standing dispatcher in one step (AD-038-R11).

    Adds the `dispatch:` block's missing keys (from the project's own config where it has them, the kit's block for
    the machine-wide ones, and the answers for the rest), the wrapper's `jobs.dispatch` log caps, the gitignore lines
    for the dispatcher's runtime state, and the launchd plist, at a path it prints. Written `enabled: false`; a key
    the project already has is never rewritten. Needs no database.
    """
    from seldon.core import adopt as A
    project_dir = project.resolve()
    try:
        config = yaml.safe_load((project_dir / "seldon.yaml").read_text(encoding="utf-8")) or {}
        kit = A.kit_config()
    except (OSError, yaml.YAMLError, A.AdoptError) as exc:
        raise click.ClickException(str(exc))
    given = {"standing_band_ref": standing_band_ref, "branch": branch, "launchd_label": launchd_label}
    answers = {}
    for key, prompt, default in A.questions(project_dir, config, kit):
        if given.get(key):
            answers[key] = given[key]
        elif yes:
            answers[key] = default
        else:
            answers[key] = click.prompt(prompt, default=default)
    if gate_command:
        answers["gate_command"] = gate_command
    if ooda_grace_s is not None:
        answers["ooda_grace_s"] = int(ooda_grace_s) if float(ooda_grace_s).is_integer() else ooda_grace_s
    try:
        out = A.adoption(project_dir, answers)
    except A.AdoptError as exc:
        raise click.ClickException(str(exc))
    added = out["added"]
    if not (out["seldon_yaml"] or out["plist"] or out["gitignore_add"]):
        click.echo(f"adopt: {project_dir} already carries the dispatch block, the log caps, the ignores and its plist")
        return
    click.echo(f"adopt: {project_dir}" + (" (dry run: nothing written)" if dry_run else ""))
    if added["dispatch"]:
        click.echo(f"  seldon.yaml dispatch: + {', '.join(added['dispatch'])}")
    if added["jobs_dispatch"]:
        click.echo(f"  seldon.yaml jobs.dispatch: + {', '.join(added['jobs_dispatch'])}")
    if out["gitignore_add"]:
        click.echo(f"  .gitignore: + {', '.join(out['gitignore_add'])}")
    if out["plist"]:
        click.echo(f"  plist: {out['plist_path']}")
    if dry_run:
        if out["seldon_yaml"]:
            click.echo("--- seldon.yaml as it would be written ---")
            click.echo(out["seldon_yaml"], nl=False)
        if out["plist"]:
            click.echo(f"--- {out['plist_path']} ---")
            click.echo(out["plist"], nl=False)
        return
    written = A.write_adoption(project_dir, out)
    click.echo(f"wrote: {', '.join(written)}")
    label = out["block"].get("launchd_label")
    click.echo("next, in a shell, in this order:")
    click.echo(f"  1. cd {project_dir} && git add {' '.join(written)} && git commit -m 'dispatch: adopt (AD-038-R11)'")
    click.echo("  2. seldon hooks install")
    if label:
        click.echo(f"  3. ln -s {out['plist_path']} ~/Library/LaunchAgents/{label}.plist && "
                   f"launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/{label}.plist")
    click.echo("  4. set dispatch.enabled to true in seldon.yaml and commit it, when the first task file is ready")


@dispatch_group.group("ooda")
def ooda_group():
    """The OODA between chained tasks (AD-038-R16, R17, criterion c18): the blocks a person answers, and the record
    that answers one."""


@ooda_group.command("pending")
@click.option("--json", "as_json", is_flag=True, help="print the rows as JSON")
def ooda_pending(as_json):
    """Every open task an `ooda_blocked` record holds (AD-038-R17): the question, the note that would answer it, the
    RESULT and the successor. The knowledge source (R16) reads every other RESULT; this is the only OODA a person
    reads (docs/conventions/desktop_ooda.md). Empty output means nothing is blocked."""
    project_dir, config, driver, database, _dc, _sid = _open_project()
    try:
        cfg = D.load_dispatch_config(project_dir, config)
        tasks = _tasks(driver, database)
    finally:
        driver.close()
    from seldon.core.events import read_events
    rows = D.ooda_pending(project_dir, tasks, cfg, D.ooda_index(read_events(project_dir)), _utcnow())
    if as_json:
        click.echo(json.dumps(rows, indent=1, default=str))
        return
    for line in D.ooda_pending_lines(rows):
        click.echo(line)


@ooda_group.command("record")
@click.argument("task")
@click.option("--note", default=None, help="one line: what the OODA found (the file form carries the full reading)")
@click.option("--actor", default="desktop", show_default=True, help="who oriented: desktop, human or cc")
def ooda_record(task, note, actor):
    """Record that the OODA on completed TASK is done: one `ooda_recorded` event, which releases every successor c18
    holds on it, and answers an `ooda_blocked` record on it (AD-038-R17). TASK is an id, a unique prefix or a task file stem. Refuses a task that is not completed or verified
    (exit 1): there is no RESULT to have read."""
    project_dir, config, driver, database, _dc, session_id = _open_project()
    try:
        task_id = _resolve_task(driver, database, task)
        if task_id is None:
            raise click.ClickException(f"no ResearchTask matches {task!r}")
        with driver.session(database=database) as s:
            state = s.run("MATCH (t:ResearchTask {artifact_id: $id}) RETURN t.state AS state",
                          id=task_id).single()["state"]
    finally:
        driver.close()
    try:
        payload = D.ooda_record_event(task_id, state, actor, note)
    except ValueError as exc:
        raise click.ClickException(str(exc))
    append_event(project_dir, make_event(event_type=D.EVENT_OODA_RECORDED, actor=actor, authority="accepted",
                                         payload=payload, session_id=session_id))
    click.echo(f"ooda recorded: {task_id[:8]} ({actor})")
    # Committed the way `redrive` commits its line (deferred while a lease is held; the next pass reconciles it).
    committed = D.commit_journal_append(project_dir, config, by="seldon dispatch ooda record", actor=actor)
    if committed.get("committed"):
        click.echo(f"committed {committed['commit']}")


@dispatch_group.command("regate")
@click.argument("task")
def dispatch_regate(task):
    """Re-gate a task blocked `stop_gate_unpassed` in its kept worktree, and merge it on pass (AD-034 ADDENDUM 03).

    TASK is an artifact id, a unique id prefix, or the task file's stem. The task must be blocked, its last finish
    `stop_gate_unpassed`, its worktree kept and its RESULT committed on its branch. The branch is rebased onto main,
    every `check:` line of the task runs in the worktree with the tree's own code (AD-037-R14), and on pass the
    branch goes to the merge path (merge on green, complete, sweep). On fail the task stays blocked and the failing
    checks are printed (exit 1). Takes the pass lease; the dispatcher runs the same step on every pass.
    """
    from seldon.commands import dispatch_worktree as W
    project_dir, config, driver, database, domain_config, session_id = _open_project()
    cfg = D.load_dispatch_config(project_dir)
    try:
        task_id = _resolve_task(driver, database, task)
        if task_id is None:
            raise click.ClickException(f"no ResearchTask matches {task!r}")
        try:
            with W._pass_lease(project_dir, cfg):
                out = W.regate(project_dir, config, driver, database, domain_config, session_id, cfg,
                               task_id=task_id)
                _record_and_push(project_dir, config, cfg)
        except W.RegateRefused as exc:
            raise click.ClickException(f"regate refused: {exc}")
        except D.LeaseHeld as held:
            raise click.ClickException(f"the pass lease is held by {held.body.get('holder')}; the dispatcher's "
                                       f"next pass regates {task_id[:8]} itself")
    finally:
        driver.close()
    (rec,) = out
    if rec["outcome"] != "pass":
        raise click.ClickException(f"{task_id[:8]} stays blocked ({rec['reason']}): "
                                   + ("; ".join(f"`{f['command']}` {f['outcome']} exit {f['exit']}"
                                                for f in rec["failed"]) or ", ".join(rec.get("files") or [])))
    click.echo(f"regated {task_id[:8]}: {len(rec['checks'])} check(s) pass; handed to the merge path")


def _resolve_task(driver, database, ref: str) -> str | None:
    """A full id, a unique prefix, or a task file stem (`cc_tasks/<stem>.md`)."""
    q = ("MATCH (t:ResearchTask) WHERE t.artifact_id STARTS WITH $ref "
         "OR t.source_file = $rel OR t.source_file = $ref RETURN DISTINCT t.artifact_id AS id")
    stem = Path(ref).stem if ref.endswith(".md") else ref
    with driver.session(database=database) as s:
        ids = [r["id"] for r in s.run(q, ref=ref, rel=f"cc_tasks/{stem}.md")]
    if len(ids) > 1:
        raise click.ClickException(f"{ref!r} is ambiguous: {', '.join(i[:8] for i in ids)}")
    return ids[0] if ids else None


#: What "the database is unavailable" means to a pass (Issue 59b2db84): Neo4j refusing the database
#: (`DatabaseUnavailable`, the 2026-10-15 lock-file outage) or the server unreachable
#: (`ServiceUnavailable`, the connection-refused tracebacks in the same log).
from neo4j.exceptions import DatabaseUnavailable as _DatabaseUnavailable  # noqa: E402
from neo4j.exceptions import ServiceUnavailable as _ServiceUnavailable  # noqa: E402

DATABASE_UNAVAILABLE = (_DatabaseUnavailable, _ServiceUnavailable)


def _outage_path(project_dir, cfg) -> Path:
    return Path(project_dir) / Path(cfg["lease_file"]).parent / D.OUTAGE_STATE_FILE


def _database_unavailable(project_dir, session_id, cfg, exc, dry_run) -> None:
    """AD-038-R6 for Issue 59b2db84: a pass that cannot reach Neo4j is a handled refusal, exit 0.

    From 16:11Z on 2026-10-15 every pass crashed with a `DatabaseUnavailable` traceback (rc=1) and no
    alert reached the operator for five hours. Now the FIRST pass of an outage writes one
    `dispatch_refused` (reason `database_unavailable`) and raises the notifier once, as a stuck alarm;
    later passes of the same outage only print a line (DN-006 decision 7: a standing condition is not
    re-logged per pass). The pass that reaches the database again removes the outage file.
    """
    error = f"{type(exc).__name__}: {str(exc).splitlines()[0][:300] if str(exc) else ''}"
    path = _outage_path(project_dir, cfg)
    state = {}
    if path.is_file():
        try:
            state = json.loads(path.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError:
            state = {}          # a corrupt file re-arms the alarm: "tell them again", never "stay quiet"
    first = not state
    state = {"first_seen": state.get("first_seen") or _now(), "passes": int(state.get("passes", 0)) + 1,
             "error": error}
    click.echo(f"refused: database_unavailable ({error}); pass {state['passes']} of this outage since "
               f"{state['first_seen']}", err=True)
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=1) + "\n", encoding="utf-8")
    if not first:
        return
    _emit(project_dir, session_id, D.EVENT_REFUSED,
          {"task_id": None, "reason": "database_unavailable", "error": error, "first_seen": state["first_seen"]})
    click.echo(f"STUCK: database_unavailable since {state['first_seen']}: {error}", err=True)
    _run_notifier(project_dir, session_id, cfg, {
        "SELDON_NOTIFY_TASK_ID": "", "SELDON_NOTIFY_TASK_NAME": "dispatcher",
        "SELDON_NOTIFY_OK": "false", "SELDON_NOTIFY_OUTCOME": "stuck",
        "SELDON_NOTIFY_CRITERION": "database_unavailable", "SELDON_NOTIFY_PASSES": "1",
        "SELDON_NOTIFY_DIRTY_PATHS": "",
        "SELDON_NOTIFY_MESSAGE": f"stuck: database_unavailable: {error}",
        "SELDON_NOTIFY_RESULT_PATH": "", "SELDON_NOTIFY_LOG_PATH": "", "SELDON_NOTIFY_WALL_SECONDS": "0",
    }, task_id="-", label="stuck")


def _database_back(project_dir, cfg) -> None:
    """The first pass that reached the database ends the outage: the next one alarms afresh."""
    path = _outage_path(project_dir, cfg)
    if path.is_file():
        try:
            passes = json.loads(path.read_text(encoding="utf-8") or "{}").get("passes")
        except json.JSONDecodeError:
            passes = None
        path.unlink()
        click.echo(f"database available again after {passes} refused pass(es)")


def _last_payload(project_dir: Path, event_type: str, where=None) -> dict | None:
    """The payload of the most recent event of this type, or None.

    The single read behind both once-per-appearance suppressions below. LAST rather than ANY,
    because the question each of them asks is "is the condition on the log the one in front of
    me now" — a condition that ended and began again is a new assertion and gets a new line.
    """
    from seldon.core.events import read_events
    last = None
    for ev in read_events(project_dir):
        if ev.get("event_type") != event_type:
            continue
        payload = ev.get("payload") or {}
        if where is not None and not where(payload):
            continue
        last = payload
    return last


def _stop_already_observed(project_dir: Path, stop: Path) -> bool:
    """Has this STOP-file appearance already been recorded? Compares the file's mtime with the
    last `dispatch_observed_stop`, so removing and re-creating the file is a new appearance and
    a file left in place for a week is one."""
    last = _last_payload(project_dir, D.EVENT_OBSERVED_STOP)
    mtime = stop.stat().st_mtime
    return (last is not None and last.get("stop_mtime") is not None
            and abs(float(last["stop_mtime"]) - mtime) < 1e-6)


def _lease_acquisition_already_refused(project_dir: Path, body: dict) -> bool:
    """Has THIS lease acquisition already been refused once? The STOP file's mtime comparison,
    against the acquisition's identity instead.

    `acquired_at` and not the holder alone: `dispatcher:<host>:<pid>` recycles, and a suppression
    keyed on it would swallow a genuinely new collision taken by a reused PID — silence about
    the one event in this whole branch that is worth a line.
    """
    holder, acquired = body.get("holder"), body.get("acquired_at")
    if holder is None and acquired is None:
        # A lease file with no body at all. Nothing to key on, so nothing is suppressed: an
        # unreadable lease that blocks a pass is exactly the state an operator must see.
        return False
    last = _last_payload(project_dir, D.EVENT_REFUSED,
                         where=lambda p: p.get("reason") == "lease_held")
    if last is None:
        return False
    return (last.get("holder"), last.get("acquired_at")) == (holder, acquired)


def _cadence_rows(project_dir, cfg, now=None) -> list:
    """Every cadence entry evaluated, whether or not anything is due. Writes nothing."""
    now = now or _utcnow()
    return [C.evaluate_entry(project_dir, e, now) for e in (cfg.get("cadence") or [])]


def _cadence(project_dir, config, driver, database, domain_config, session_id, cfg, tree,
             claim, dry_run) -> list:
    """DN-006 decision 8, evaluated BEFORE candidacy: a due period with no instance on disk
    gets one, and the instance then flows through decision 2 like any other task.

    The gate on creating anything is deliberately the same shape as c6, c7 and c8 — enabled
    (already checked by the caller), no claim in flight, clean tree on the configured branch.
    The dispatcher writes a file and a commit here, and it must not do that to a checkout
    somebody or something else is editing: that is the batch-identity class (DD-019) in the one
    place this design can still reach it.

    A cadence that creates nothing writes **no event**, for decision 7's reason. `status` and
    `seldon go` compute the same rows live, so a due-but-blocked schedule is visible to an
    operator without a line in the log every five minutes for as long as it stays that way.
    """
    rows = _cadence_rows(project_dir, cfg)
    for row in rows:
        row["created"] = None
        if not row["due"] or row["instance"]:
            continue
        blocked = None
        if claim is not None:
            blocked = "claim_in_flight"
        elif tree.get("read_error"):
            blocked = "tree_unreadable"
        elif tree["branch"] != cfg["branch"]:
            blocked = "wrong_branch"
        elif tree["dirty"]:
            blocked = "dirty_tree"
        if blocked:
            row["created"] = False
            row["blocked_on"] = blocked
            # The reason AND its evidence, so a blocked tick is readable from the wrapper's
            # log alone (decision 3 of the dispatcher-commits-its-record task): after the
            # dispatcher commits its own lines, the paths are the operator's or a session's.
            evidence = {"dirty_tree": f": {', '.join(tree['dirty_paths'])}"
                                      + (f" (+{tree['dirty_count'] - len(tree['dirty_paths'])}"
                                         f" more)" if tree["dirty_count"]
                                         > len(tree["dirty_paths"]) else ""),
                        "wrong_branch": f": on {tree['branch']}, configured {cfg['branch']}",
                        "tree_unreadable": f": {tree.get('read_error')}",
                        "claim_in_flight": f": {claim['artifact_id'][:8]} by "
                                           f"{claim['claimed_by']}" if claim else ""}
            row["blocked_evidence"] = evidence[blocked].lstrip(": ")
            click.echo(f"cadence {row['cadence']} {row['period']} is due and NOT created "
                       f"({blocked}){evidence[blocked]}", err=True)
            continue
        if dry_run:
            row["created"] = False
            row["blocked_on"] = "dry_run"
            continue
        entry = next(e for e in cfg["cadence"] if e["name"] == row["cadence"])
        row.update(_create_instance(project_dir, config, driver, database, domain_config,
                                    session_id, cfg, entry, row["period"]))
    return rows


def _create_instance(project_dir, config, driver, database, domain_config, session_id, cfg,
                     entry, period) -> dict:
    """Render the template, register it through `seldon cc register`'s own code path, record
    `last_instance`, commit, and put the whole thing on the log as one `cadence_created`.

    Order matters and is not arbitrary: the file is **staged before registration** because
    `register_task_file` refuses a task file git cannot recover, and the index is what makes it
    recoverable; the commit comes **after** the event so the commit contains the event line
    too, and a reader of the log finds the commit that carries its own record.

    Any failure removes the file it wrote and leaves nothing half-created: the next pass
    re-renders. Nothing is retried inside one pass (DN-006 decision 4's rule, applied one level
    down).
    """
    from seldon.commands.cc import register_task_file

    now = _utcnow()
    created_at = _now()
    template = project_dir / entry["template"]
    if not template.is_file():
        click.echo(f"cadence {entry['name']}: template {entry['template']} does not exist; "
                   f"nothing created", err=True)
        return {"created": False, "blocked_on": "template_missing"}
    text = template.read_text(encoding="utf-8")
    unknown = C.unknown_placeholders(text)
    cycle_name = C.cycle_name_for(entry, now)
    path = C.instance_path(project_dir, entry, period, now)
    path.parent.mkdir(parents=True, exist_ok=True)
    rel = str(path.relative_to(project_dir))
    path.write_text(C.render(text, cycle_name=cycle_name, period=period,
                             cadence_name=entry["name"], created_at=created_at,
                             instance_stem=C.instance_stem(entry, period, now)),
                    encoding="utf-8")
    staged = D.stage(project_dir, [rel])
    if staged.returncode != 0:
        path.unlink(missing_ok=True)
        click.echo(f"cadence {entry['name']}: git add failed: {staged.stderr.strip()}",
                   err=True)
        return {"created": False, "blocked_on": "git_add_failed"}
    try:
        outcome = register_task_file(
            project_dir=project_dir, config=config, driver=driver, database=database,
            domain_config=domain_config, session_id=session_id, task_path=path,
            actor=ACTOR, emit=lambda m: click.echo(f"  {m}") if m else None)
    except Exception as exc:                                        # noqa: BLE001
        # Reported, never swallowed, and the file goes with it: a rendered task file that is
        # not in the graph is a task nothing will ever run and a file the next pass would see
        # as "this period is already served".
        D.git(project_dir, "rm", "--cached", "-q", "--", rel)
        path.unlink(missing_ok=True)
        click.echo(f"cadence {entry['name']}: registration failed, instance removed: "
                   f"{type(exc).__name__}: {exc}", err=True)
        return {"created": False, "blocked_on": "register_failed",
                "error": f"{type(exc).__name__}: {exc}"}

    wrote_back = C.write_last_instance(project_dir / "seldon.yaml", entry["name"], rel)
    if not wrote_back:
        click.echo(f"cadence {entry['name']}: could not record last_instance in seldon.yaml; "
                   f"the instance file is the guard and it exists", err=True)
    payload = {"cadence": entry["name"], "period": period, "rule": entry["rule"],
               "task_id": outcome["artifact_id"], "task_file": rel,
               "cycle_name": cycle_name, "template": entry["template"],
               "already_registered": outcome["existing"],
               "last_instance_written": wrote_back,
               "unknown_placeholders": unknown, "created_at": created_at,
               "next_due": C.next_due_instants(entry["rule"], now, 3)[0]
                           .isoformat().replace("+00:00", "Z")}
    _emit(project_dir, session_id, D.EVENT_CADENCE_CREATED, payload)
    paths = [rel, config.get("event_store", {}).get("path", "seldon_events.jsonl"),
             "seldon.yaml"]
    commit = D.commit_paths(project_dir, paths,
                            f"chore(cadence): {entry['name']} {period} — "
                            f"{rel} created by the standing dispatcher")
    if not commit["committed"]:
        click.echo(f"cadence {entry['name']}: commit failed ({commit['reason']}): "
                   f"{commit.get('stderr', '')}", err=True)
    click.echo(f"cadence {entry['name']} {period}: created {rel} "
               f"({outcome['artifact_id'][:8]}), commit {commit.get('commit', 'NONE')}")
    return {"created": True, "task_id": outcome["artifact_id"], "instance": rel,
            "cycle_name": cycle_name, "commit": commit.get("commit"),
            "last_instance_written": wrote_back}


def _pass(project_dir, config, driver, database, domain_config, session_id, cfg, lease,
          dry_run):
    if cfg["max_parallel"] > 1 and not qc.parallel_opted_in(project_dir, config):
        # AD-037-R9: parallel dispatch stays at 1 until R6's stations and the disk preflight are live; a project
        # opts in only by an accepted record anchored at AD-037-R9 naming it. The dispatcher refuses the pass (no
        # launch), the way it refuses an inherited API key: exit 0, a refusal event, and the reason on stderr.
        _emit(project_dir, session_id, D.EVENT_REFUSED,
              {"task_id": None, "reason": "parallel_not_opted_in", "max_parallel": cfg["max_parallel"]})
        click.echo(f"refused: dispatch.max_parallel is {cfg['max_parallel']} and no accepted record anchored at "
                   f"AD-037-R9 names {Path(project_dir).resolve().name!r} (AD-037-R9: parallel dispatch stays at 1)",
                   err=True)
        return
    if cfg["max_parallel"] > 1:
        # SEL-004 (AD-034): worktree per task. Opt-in; at the default of 1 the code below is
        # the pass, unchanged, and `tests/test_dispatch_serial_transcript.py` holds it to the
        # recorded transcript of the pre-SEL-004 dispatcher.
        from seldon.commands import dispatch_worktree as W
        return W.pass_parallel(project_dir, config, driver, database, domain_config,
                               session_id, cfg, lease, dry_run)
    band = D.resolve_standing_band(project_dir, cfg["standing_band_ref"])
    claim = _claim_in_flight(driver, database)
    # AD-038-R1: reconcile FIRST, before anything reads the tree. Every dirty path of machine-written
    # governed state (the event store, the prior-art logs, the decision register, the cadence's
    # write-back, registered task files and their addenda) is committed, one commit per class,
    # whoever wrote it. With no claim in flight and the lease held, nothing else is working in the
    # checkout. Before the cadence too: it gates creation on a clean tree.
    done = None
    if claim is None and not dry_run:
        # FRICTION-002 Part B: a merged task's worktree is removed (its branch kept), before the reconcile so
        # the `worktree_removed` lines are committed in this pass.
        from seldon.commands import dispatch_worktree as W
        W.sweep(project_dir, session_id)
        # DISP-002 (AD-034 ADDENDUM 02): green work a breaker trip blocked is merged, and a kept tree that holds
        # nothing is removed with its branch, before the reconcile so their lines are committed in this pass.
        _breaker_and_stale(project_dir, config, driver, database, domain_config, session_id, cfg)
        # AD-038-R2: a task blocked by one of the dispatcher's own recorded defects goes back on the
        # queue by itself, before the reconcile so its lines are committed in this pass.
        _auto_redrive(project_dir, driver, database, domain_config, session_id)
        done = _reconcile(project_dir, config, cfg, driver, database)
        # AD-038-R16 (SEL-014R): the OODA knowledge source fires on the board's state, under this pass's lease and
        # before candidacy, so no successor is evaluated ahead of its predecessor's OODA; its records and any
        # addendum are committed before the tree is read.
        _ooda_fire(project_dir, config, cfg, driver, database, session_id)
    tree = D.tree_state(project_dir)
    # Cadence BEFORE candidacy (DN-006 decision 8): a task this pass creates is a task this
    # pass may then launch, so the queue it evaluates is the queue as it stands after the
    # calendar has had its say.
    if cfg.get("cadence"):
        _cadence(project_dir, config, driver, database, domain_config, session_id, cfg, tree,
                 claim, dry_run)
        tree = D.tree_state(project_dir)
    if tree["dirty"]:
        # c7 names what the reconciler could not or may not commit, and why (FRICTION-001 Part A step 3).
        tree["unreconciled"] = _unreconciled(project_dir, config, driver, database, done)
    lease_body = D.read_lease(project_dir / cfg["lease_file"])
    holds = _premise_holds(project_dir, driver, database)
    launch_holds = _launch_holds(project_dir)
    union = D.union_state(project_dir)
    tasks = _tasks(driver, database)
    cross = _cross_waits(project_dir, tasks)
    ooda = _ooda_waits(project_dir, cfg, tasks)
    rows = D.fifo([D.evaluate(project_dir, t, cfg, band, tree, claim, lease_body, premise_holds=holds,
                              launch_holds=launch_holds, union=union, cross_waits=cross, ooda=ooda)
                   for t in tasks])
    # The staleness alarm, before the eligible/ineligible split so a candidate that has been
    # refused for hours is heard about whether or not some OTHER task launched this pass.
    _record_last_pass(project_dir, cfg, rows, tree, claim, dry_run)
    _stuck(project_dir, session_id, cfg, rows, tree, claim, dry_run)

    eligible = [r for r in rows if r["eligible"]]
    if not eligible:
        # DN-006 decision 7, taken literally: **a pass in which nothing is eligible writes NO
        # event.** The log records assertions, and "nothing to do" is not one.
        #
        # This branch used to emit one `dispatch_refused` per blocked candidate, and it was
        # wrong in the way only a path that has never run can be wrong. Every reason reachable
        # from here — `dirty_tree`, `above_band`, `network_undeclared`, `disabled`,
        # `stop_file` — is a STANDING CONDITION, re-evaluated every five minutes and unchanged
        # until somebody edits a file. A working tree is dirty for as long as a session is
        # working in it, so the first enabled pass over a two-candidate queue would have
        # written two events, and the next 5-minute pass two more, for hours: the poll logging
        # its own silence, which is the exact thing the comment above it forbade. Worse, the
        # event store is a TRACKED file here, so writing to it keeps the tree dirty, which
        # keeps the refusal true — a loop that feeds itself.
        #
        # Nothing is lost. Every one of those reasons is a live property of a task file or of
        # the checkout, and `seldon dispatch status` computes all of them on demand with their
        # values. The refusals that DO reach the log are the ones that are occurrences rather
        # than states: `lease_held`, `api_key_present` and `claim_failed`, each emitted at its
        # own site above.
        click.echo(f"nothing eligible ({len(rows)} open, "
                   f"{sum(1 for r in rows if r['candidate'])} candidate(s))")
        _echo_refusals(rows, tree)
        # Decision 2's retry: whatever this pass or an earlier one committed and could not
        # push is pushed now. A no-op when the branch is level with its upstream.
        if not dry_run and claim is None:
            _push(project_dir, cfg)
        return

    # AD-037-R6 (a): premise review, BEFORE the claim, over the eligible tasks in FIFO order. A false premise
    # refuses that task (an Issue names it) and the next eligible task is reviewed; a sibling's lease on this
    # project's environment refuses the pass, since it holds for every task here alike.
    chosen = None
    for row in eligible:
        review = _premise_review(project_dir, config, driver, database, domain_config, session_id, cfg, row,
                                 dry_run)
        if review["ok"]:
            chosen = row
            chosen["premises"] = review
            break
        if not review["environment"]["outcome"] == "true":
            if not dry_run:
                _push(project_dir, cfg)
            return
    if chosen is None:
        click.echo("nothing launched: every eligible task has a false premise")
        if not dry_run:
            _record_and_push(project_dir, config, cfg)
        return
    if dry_run:
        click.echo(json.dumps({"would_launch": chosen["task_id"],
                               "source_file": chosen["source_file"],
                               "criteria": chosen["criteria"],
                               "premises": chosen["premises"]}, indent=1, default=str))
        return
    _launch_inplace(project_dir, config, driver, database, domain_config, session_id, cfg,
                    lease, chosen)


def _launch_inplace(project_dir, config, driver, database, domain_config, session_id, cfg,
                    lease, chosen):
    """Claim, cut the task's worktree, launch the CLI into it, wait, merge on green: DN-006 decisions 4 and 5
    with AD-034-R5/R6's finish, under the pass lease held for the whole run.

    FRICTION-002 Part B (AD-034 ADDENDUM 01): every task runs in its own worktree, which turns on the CLI's hard
    isolation: Edit/Write and git aimed at the primary checkout are refused. DISP-001R Part A: the CLI names and
    cuts it (`--worktree` with no name: `.claude/worktrees/<generated>` on `worktree-<generated>`, from main's HEAD
    after the claim's records are committed); the dispatcher reads the path from the session's `init` record,
    links `dispatch.worktree_links` in and records `dispatch_worktree_named`. A session that ends before its first
    model turn is `launch_failed` (`dispatch_worktree.finish_session`). The primary is then
    touched only by the dispatcher's own commits, merges on green and Desktop's governed commits. The name says
    where the session's LEASE is held (in place, by this pass, for the whole run), not where it works; the
    parallel mode's exclusive tasks use it too.

    The finish is the worktree supervisor's (`dispatch_worktree.finish_session`): a session that exited 0 with its
    RESULT committed on its branch, on the requested model, is rebased, checked and fast-forwarded into main and
    then completed by the dispatcher; anything else is blocked and its worktree and branch are kept, with a
    `worktree_kept` record. This pass already holds the pass lease, so the finish takes no second one.
    """
    from contextlib import nullcontext
    from seldon.commands import dispatch_worktree as W
    rel = chosen["source_file"]
    stem = Path(rel).stem
    log_dir = project_dir / cfg["log_dir"]
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{stem}.log"
    log_rel = str(log_path.relative_to(project_dir))
    held = nullcontext

    # THE CLAIM, and it is the compare-and-set: a transition that fails launches nothing.
    claimed = _claim(project_dir, driver, database, domain_config, session_id, chosen)
    if not claimed["ok"]:
        _emit(project_dir, session_id, D.EVENT_REFUSED,
              {"task_id": chosen["task_id"], "reason": "claim_failed",
               "error": claimed["error"], "from_state": chosen["state"]})
        click.echo(f"claim failed for {chosen['task_id'][:8]}: {claimed['error']}", err=True)
        _record_and_push(project_dir, config, cfg)
        return

    lease.heartbeat(task=chosen["task_id"])
    # QC-002: this holder inspects the session while it waits (`_run`), so a later pass need not.
    from seldon.commands import dispatch_stations as ST
    lease.write({**D.read_lease(lease.path), ST.LEASE_STATIONS_FIELD: ST.LEASE_STATIONS_VERSION})
    # AD-035 R2 and R7: the lock is refreshed (cached for the day) BEFORE the run, and this
    # run keeps the spec it starts with to the end.
    refresh_note = models.ensure_fresh("dispatch")
    spec = _session_spec(project_dir, rel)
    cmd = _launch_cmd(cfg, W.worktree_prompt(rel, project_dir, chosen["task_id"]), spec, worktree=True,
                      settings=_session_settings(project_dir, cfg))
    # The child's root session id, minted here and handed down through the environment, so a
    # reader can join the session's `cc` events to this launch (decision 2).
    child_session_id = str(uuid.uuid4())
    # DISP-004R (AD-034-R12): the other repositories the Repo line says to push, with their HEADs before the session.
    push_repos = D.cross_repo_launch(project_dir, cfg, (project_dir / rel).read_text(encoding="utf-8",
                                                                                     errors="surrogateescape"))
    _emit(project_dir, session_id, D.EVENT_LAUNCHED,
          {"task_id": chosen["task_id"], "source_file": rel,
           "child_session_id": child_session_id,
           "claimed_by": claimed["claimed_by"], "transitions": claimed["transitions"],
           "criteria": chosen["criteria"], "framework_layer": chosen["framework_layer"],
           "network_allowlist": chosen["criteria"]["c5"]["network_allowlist"],
           "log_path": log_rel,
           "command": " ".join(shlex.quote(p) for p in cmd),
           "permission_mode": cfg["permission_mode"], "launched_at": _now(),
           "mode": "worktree", "worktree": None, "branch": None, "worktree_named_by": "cli", "stem": stem,
           **({"push_repos": push_repos} if push_repos else {}),
           **_station_fields(cfg, chosen),
           **_model_fields(spec, refresh_note),
           # PRUNE-002 Part B: the instruction context this session receives, for `qc chart`'s toil reading.
           IC.PAYLOAD_KEY: IC.measure(project_dir)})
    # The claim's transitions and `dispatch_launched` are committed and pushed BEFORE the CLI
    # cuts the worktree, so the task's branch starts from a main that already carries its own claim.
    _record_and_push(project_dir, config, cfg)
    base = WT.rev(project_dir, "HEAD")
    # `worktree`, `branch` and `linked` are filled by `name_worktree` at the session's `init` record.
    extra = {"worktree_task": chosen["task_id"], "stem": stem, "source_file": rel, "worktree": None,
             "branch": None, "base": base, "child_session_id": child_session_id, "linked": [],
             "model_spec": spec, "push_repos": push_repos}
    click.echo(f"launching {chosen['task_id'][:8]} {rel} in a worktree the CLI names -> {log_rel}")

    started = time.monotonic()
    offset = _log_offset(log_path)
    # The CLI is started in the PRIMARY checkout: `--worktree <stem>` resolves `.claude/worktrees/<stem>` against
    # the repository it starts in, and enters it.
    code = _run(cmd, project_dir, log_path, child_session_id,
                network_allowlist=chosen["criteria"]["c5"]["network_allowlist"],
                extra_env=_worktree_env(project_dir, spec, cfg),
                inspector=ST.holder_inspector(project_dir, cfg, chosen["task_id"]),
                inspect_every_s=cfg["poll_interval_s"],
                on_reap=lambda reap, pid, sig: ST.record_reap(project_dir, chosen["task_id"], reap, pid, sig),
                on_init=lambda init: W.name_worktree(project_dir, session_id, extra, init, cfg["worktree_links"]))
    wall = round(time.monotonic() - started, 3)
    W.finish_session(project_dir, config, driver, database, domain_config, session_id, cfg,
                     chosen["task_id"], extra, code, wall, log_path, offset, spec,
                     name=chosen.get("name") or stem, lease_cm=held)


def _worktree_env(project_dir: Path, spec: dict, cfg: dict) -> dict:
    """What a worktree session's environment adds: the model lock's ids (AD-035 R3), where the primary checkout
    is (AD-034-R8) and, when the project declares one, its interpreter's `bin` first on `PATH` with `VIRTUAL_ENV`
    (AD-037-R15), so a bare `pytest` or `python` the session types is the project's and not the launchd job's. No
    Stop-hook block cap: LOOP-001 (AD-034 ADDENDUM 04) withdrew FRICTION-002's, so the gate's no-progress rule lets
    a stuck session go and the CLI's own default cap is only the backstop."""
    env = {**spec["env"], WT.PRIMARY_CHECKOUT_ENV: str(project_dir)}
    interpreter = QS.load_stations_config(cfg)["interpreter"]
    if interpreter:
        env.update(QS.interpreter_env(interpreter, dict(os.environ)))
    return env


def _classifier_reading(project_dir: Path, child_session_id: str, log_path: Path, offset: int) -> dict:
    """FRICTION-002 Part D: how many actions the auto-mode classifier blocked in this launch (its
    `classifier_block` records), the last block's reason, and whether the CLI's breaker ended the session (its own
    text in the session's log, from `offset`)."""
    from seldon.core.events import read_events
    blocks = [e for e in read_events(project_dir)
              if e.get("event_type") == QS.EVENT_CLASSIFIER_BLOCK
              and (e.get("payload") or {}).get("child_session_id") == child_session_id]
    text = ""
    if log_path.is_file():
        with log_path.open("r", encoding="utf-8", errors="replace") as fh:
            fh.seek(offset)
            text = fh.read()
    reasons = [(b.get("payload") or {}).get("reason") for b in blocks]
    return {"blocks": len(blocks), "reasons": reasons,
            "last_reason": reasons[-1] if reasons else None,
            "breaker": QS.CLASSIFIER_BREAKER_TEXT in text}


def _gate_reading(project_dir: Path, task_id: str, child_session_id: str) -> dict:
    """FRICTION-002 Part C at the finish: did the session's Stop gate pass when it ended?

    `passed` is True when the last `stop_gate` record of this launch says `pass`, or when the session declared no
    Part and no gate record exists (nothing to gate). It is False when the last verdict is `no_progress` (two
    consecutive refused rounds with the same check output, LOOP-001), `block` (the CLI's own block cap ended the
    session over the hook, observed at 9 consecutive refusals on CLI 2.1.302; now only the backstop) or `ceiling`, and
    when the session declared a Part but no gate ran (a hook that never ran is not a pass)."""
    from seldon.core.events import read_events
    gates, declared = [], False
    for e in read_events(project_dir):
        p = e.get("payload") or {}
        if e.get("event_type") == QS.EVENT_STOP_GATE and p.get("child_session_id") == child_session_id:
            gates.append(p)
        elif e.get("event_type") == QS.EVENT_PART_COMPLETE and p.get("task_id") == task_id:
            declared = True
    if gates:
        last = gates[-1]
        return {"passed": last["verdict"] == "pass", "verdict": last["verdict"], "runs": len(gates),
                "why": None if last["verdict"] == "pass" else f"{last['verdict']}: {', '.join(last['failed'])}"}
    if declared:
        return {"passed": False, "verdict": None, "runs": 0, "why": "Parts declared and no stop gate ran"}
    return {"passed": True, "verdict": None, "runs": 0, "why": None}


def _classifier_stop(project_dir: Path, session_id, task_id: str, reading: dict) -> None:
    """FRICTION-002 Part D: the CLI's breaker (3 consecutive or 20 total blocks) aborted a headless session. That is a
    `line` stop with the classifier's reason, answered by a redrive from the operator or Desktop (AD-038-R2), never
    by the dispatcher's automatic redrive."""
    _emit(project_dir, session_id, QS.EVENT_SESSION_STOP,
          {"task_id": task_id, "station": "classifier", "kind": "line", "reason": "classifier_breaker",
           "classifier_reason": reading["last_reason"], "blocks": reading["blocks"], "by": "dispatcher"})


#: How many dirty paths a refusal line and a stuck alarm name. Ten is ADDENDUM_01's own
#: number ("the dirty paths (`git status --short`, first ten)"); `tree_state` already caps its
#: list at twenty and reports the true count beside it, so nothing is hidden by either.
STUCK_DIRTY_PATHS_SHOWN = 10


def _refusal_lines(rows: list, tree: dict) -> list:
    """One line per refused candidate and per non-candidate (SEL-011 Part B), with the evidence an
    operator acts on (indented detail lines after it). The text `_echo_refusals` prints and `seldon go` shows from the last pass
    (DESK-001 Part B step 5), so the log and the orientation read the same."""
    out = []
    for r in rows:
        if not r.get("candidate"):
            # SEL-011 Part B (Issue 9965fbed): a non-candidate gets its line too. A pass that printed only
            # "0 candidates" left squiddy SQ-088 and SQ-091 `proposed` for two days with no reason anywhere.
            out.append(f"  {(r.get('task_id') or '?')[:8]} not_a_candidate: {r.get('not_a_candidate_reason')}  "
                       f"{r.get('source_file') or ''}")
            if r.get("not_a_candidate_message"):
                out.append(f"      {r['not_a_candidate_message']}")
            continue
        reason = D.first_refusal_reason(r)
        if reason:
            out.append(f"  {(r['task_id'] or '?')[:8]} {reason}: "
                       f"{','.join(r['failed'])}  {r['source_file']}")
            if reason == "spend_unreadable":
                out.append(f"      {r['criteria']['c4'].get('message', '')}")
            if reason == "network_undeclared":
                out.append(f"      {r['criteria']['c5'].get('message', '')}")
            if reason == "concurrency_undeclared":
                out.append(f"      {r['criteria']['c10'].get('message', '')}")
            if reason == "worktree_unavailable":
                out.append(f"      {json.dumps(r['criteria']['c11'])}")
            if reason == "dirty_tree":
                # ADDENDUM_01 decision 6b: name the DIRT, not only the task. The task file
                # is not why c7 failed and printing only it sent seven hours of log lines
                # pointing at the wrong file.
                out.append(f"      dirty: {', '.join(_dirty_paths(tree))}")
                # AD-038-R1: each path the reconciler could not or may not commit, with its reason.
                for u in (tree.get("unreconciled") or [])[:STUCK_DIRTY_PATHS_SHOWN]:
                    out.append(f"      unreconciled: {u['path']}: {u['why']}")
            if reason == "union_attribute_missing":
                # AD-034 ADDENDUM 05: name the files and the command that declares them.
                u = r["criteria"]["c16"]
                if u.get("read_error"):
                    out.append(f"      append-only logs unreadable: {u['read_error']}")
                else:
                    out.append(f"      not merge=union: {', '.join(u['missing'])} "
                               f"(run `seldon hooks install`)")
            if reason == "wrong_branch":
                out.append(f"      branch: {tree.get('branch') or '(none)'}, configured "
                           f"{r['criteria']['c7'].get('configured_branch')}")
            if reason == "tree_unreadable":
                out.append(f"      git: {tree.get('read_error')}")
            if reason == "disk_short":
                # SQ-010 ADDENDUM 02 D3.4: the need, the free space and where, so the operator knows what to free
                d = r["criteria"]["c12"]
                out.append(f"      disk: need {d['need_bytes']:,} bytes ({d['factor']} x the {d['launch']} "
                           f"launch's {d['footprint_bytes']:,}-byte tree at {d['ref']}), free "
                           f"{d['free_bytes']:,} bytes at {d['path']} ({d['probe']})")
            if reason == "disk_unmeasured":
                out.append(f"      disk: the launch's footprint could not be measured: "
                           f"{r['criteria']['c12'].get('read_error')}")
            if reason in ("ooda_pending", "ooda_blocked"):
                # AD-038-R17: which predecessor's OODA is due (the knowledge source runs on it) or blocked (its
                # question, and the line that answers it).
                for w in r["criteria"]["c18"]["predecessors"]:
                    if w["released_by"]:
                        continue
                    who = f"{(w['predecessor'] or '?')[:8]} {w['name'] or ''}"
                    if w.get("held") == "blocked":
                        out.append(f"      OODA on {who} blocked: {w.get('question')} (answer in "
                                   f"{w.get('answering_note')}); then `seldon dispatch ooda record "
                                   f"{(w['predecessor'] or '?')[:8]}`")
                    else:
                        out.append(f"      OODA on {who} due: the knowledge source runs it at a pass "
                                   f"(dispatch.ooda.max_per_pass per pass, oldest completion first)")
            if reason == "governing_unverified":
                # DESK-001: the note and the command that clears the hold.
                for u in r["criteria"]["c14"]["unverified"]:
                    out.append(f"      unverified: {u['note'] or '(gate)'}: {u['why']}")
    return out


def _echo_refusals(rows: list, tree: dict) -> None:
    """One line per refused candidate. Shared by the serial pass and the parallel one (SEL-004),
    so both logs read the same."""
    for line in _refusal_lines(rows, tree):
        click.echo(line)


def _record_last_pass(project_dir, cfg, rows, tree, claim, dry_run) -> None:
    """Write what this pass refused, for `seldon go`'s Dispatcher section (DESK-001 Part B step 5).

    A file, not an event: the refusals are standing conditions, and DN-006 decision 7 forbids
    logging them per pass. A file overwritten each pass is the dead man's switch's display, not a
    record. Nothing on a dry run, which observes on another's behalf."""
    if dry_run:
        return
    refused = []
    for r in rows:
        reason = D.first_refusal_reason(r) if r.get("candidate") else None
        if reason:
            refused.append({"task_id": r.get("task_id"), "criterion": reason,
                            "failed": r.get("failed"), "source_file": r.get("source_file")})
    D.write_last_pass(project_dir, cfg, {
        "at": _now(), "open": len(rows),
        "candidates": sum(1 for r in rows if r.get("candidate")),
        "claim_in_flight": claim is not None, "refused": refused,
        "dirty_paths": _dirty_paths(tree) if tree.get("dirty") else [],
        "lines": _refusal_lines(rows, tree)})


def _dirty_paths(tree: dict) -> list:
    paths = list(tree.get("dirty_paths") or [])[:STUCK_DIRTY_PATHS_SHOWN]
    extra = tree.get("dirty_count", len(paths)) - len(paths)
    return paths + ([f"(+{extra} more)"] if extra > 0 else [])


def _stuck(project_dir, session_id, cfg, rows, tree, claim, dry_run) -> list:
    """ADDENDUM_01 decision 6b: a candidate refused on the same criterion for N consecutive
    passes raises the notifier ONCE, writes one `dispatch_stuck`, and re-arms when the
    criterion changes or clears.

    **Why this is not the per-pass refusal logging decision 7 forbids.** Decision 7's argument
    is that a standing condition re-logged every five minutes buries the assertions in the
    log — and it is right. This writes one event per STREAK, not one per pass: 84 passes over
    seven hours produce exactly one `dispatch_stuck`, and a 85th produces none. The thing
    decision 7 removed was a record of silence; this is a record of a queue that has stopped,
    which is the opposite fact.

    Writes nothing on a dry run, and nothing while a claim is in flight — a session working in
    the checkout makes the tree dirty by design, and alarming on that would train the operator
    to ignore the alarm, which is the only way a staleness alarm can fail.
    """
    if dry_run or claim is not None:
        return []
    if tree.get("read_error"):
        # A pass that could not read the tree has not observed the queue, so it neither
        # advances a streak nor clears one: the streak file is not read or written
        # (ai-readiness-kg/cc_tasks/2026-10-09_main_green_dispatch_stuck_without_a_path.md
        # decision 3). The line is the trace; the next pass that can read decides.
        click.echo(f"stuck: not counted; the tree could not be read ({tree['read_error']})")
        return []
    refusals = _stuck_refusals(rows)
    previous = D.read_stuck_state(project_dir, cfg)
    state, alarms = D.advance_stuck(
        previous, {k: {"criterion": v["criterion"]} for k, v in refusals.items()},
        lambda criterion: D.stuck_threshold(cfg, criterion), _now())
    D.write_stuck_state(project_dir, cfg, state)
    for task_id in alarms:
        row = refusals[task_id]["row"]
        entry = state[task_id]
        dirty = _dirty_paths(tree)
        payload = {"task_id": task_id, "name": row.get("name"),
                   "source_file": row.get("source_file"),
                   "criterion": entry["criterion"], "failed": row.get("failed"),
                   "passes": entry["passes"],
                   "threshold": D.stuck_threshold(cfg, entry["criterion"]),
                   "first_seen": entry["first_seen"], "dirty_paths": dirty,
                   "dirty_count": tree.get("dirty_count"),
                   "branch": tree.get("branch"), "configured_branch": cfg["branch"],
                   "poll_interval_s": cfg.get("poll_interval_s")}
        _emit(project_dir, session_id, D.EVENT_STUCK, payload)
        evidence = (f"branch: {tree.get('branch') or '(none)'}, configured {cfg['branch']}"
                    if entry["criterion"] == "wrong_branch"
                    else f"dirty: {', '.join(dirty) or '(none)'}")
        click.echo(f"STUCK: {str(task_id)[:8]} refused as {entry['criterion']} for "
                   f"{entry['passes']} consecutive passes since {entry['first_seen']}; "
                   f"{evidence}", err=True)
        _run_notifier(project_dir, session_id, cfg, {
            "SELDON_NOTIFY_TASK_ID": str(task_id),
            "SELDON_NOTIFY_TASK_NAME": str(row.get("name") or row.get("source_file") or "?"),
            "SELDON_NOTIFY_OK": "false",
            "SELDON_NOTIFY_OUTCOME": "stuck",
            "SELDON_NOTIFY_CRITERION": entry["criterion"],
            "SELDON_NOTIFY_PASSES": str(entry["passes"]),
            "SELDON_NOTIFY_DIRTY_PATHS": ", ".join(dirty),
            # DESK-001 Part B step 6: the body names the evidence, so the banner alone says what
            # to commit. `notify` templates that predate it keep working on the other variables.
            "SELDON_NOTIFY_MESSAGE": (f"stuck: {entry['criterion']} for {entry['passes']} pass(es); "
                                      f"{evidence}"),
            "SELDON_NOTIFY_RESULT_PATH": "",
            "SELDON_NOTIFY_LOG_PATH": "",
            "SELDON_NOTIFY_WALL_SECONDS": "0",
        }, task_id=task_id, label="stuck")
    return alarms


def _stuck_refusals(rows: list) -> dict:
    """`{task_id: {"criterion", "row"}}` for every refused candidate: what a pass counts, and
    what `status` reads to say which candidates the next pass would alarm on."""
    refusals = {}
    for row in rows:
        if not row.get("candidate"):
            continue
        reason = D.first_refusal_reason(row)
        if reason:
            refusals[row["task_id"]] = {"criterion": reason, "row": row}
    return refusals


def _stuck_due(project_dir, cfg, rows, tree, claim) -> list:
    """The candidates the NEXT pass would raise `dispatch_stuck` for, computed without writing:
    the same refusals `_stuck` would count, advanced against the same streak file with the pure
    `advance_stuck`. Empty whenever `_stuck` would count nothing (claim in flight, unreadable
    tree). A pass that writes an event is a pass with something to assert, and this is how a
    reader of `status` knows one is coming (decision 4 of the task above)."""
    if claim is not None or tree.get("read_error"):
        return []
    refusals = _stuck_refusals(rows)
    _state, alarms = D.advance_stuck(
        D.read_stuck_state(project_dir, cfg),
        {k: {"criterion": v["criterion"]} for k, v in refusals.items()},
        lambda criterion: D.stuck_threshold(cfg, criterion), _now())
    return alarms


def _notify(project_dir, session_id, cfg, finish: dict, task_name: str,
            outcome: str | None = None, message: str | None = None) -> None:
    """Run `dispatch.notify`, the operator's finish signal, once per finished task.

    `ai-readiness-kg/cc_tasks/2026-09-17_dispatcher_notifies.md` decision 1. Prior art: cron's
    `MAILTO`, systemd's `OnSuccess=`/`OnFailure=`, a CI runner's status post — the runner owns
    the notification and configuration names the channel, so a desktop banner and a phone push
    are the same code path with a different string in `seldon.yaml`.

    The outcome reaches the command through `SELDON_NOTIFY_*` ENVIRONMENT variables and never by
    substitution into the command text, which is how git hooks and systemd units hand a command
    its context: a task name is data, and data interpolated into a shell line is an injection.

    Run through `/bin/sh -c` in its own process group with stdin closed, and killed as a group
    at `notify_timeout_s`. **Nothing here may alter the dispatch record or raise**: a missing,
    failing or hanging notifier is one `dispatch_notify_failed` event and the pass goes on.
    """
    _run_notifier(project_dir, session_id, cfg, {
        "SELDON_NOTIFY_TASK_ID": str(finish["task_id"]),
        "SELDON_NOTIFY_TASK_NAME": str(task_name),
        "SELDON_NOTIFY_OK": "true" if finish["ok"] else "false",
        # The word a notification body wants, so a template needs no shell conditional.
        "SELDON_NOTIFY_OUTCOME": outcome or ("ok" if finish["ok"] else "blocked"),
        # DESK-001: the body text, set on every notification so one template serves both kinds.
        # DISP-001R: `message` carries a launch failure's stderr line.
        "SELDON_NOTIFY_MESSAGE": message or outcome or ("ok" if finish["ok"] else "blocked"),
        "SELDON_NOTIFY_RESULT_PATH": finish["result_path"],
        "SELDON_NOTIFY_LOG_PATH": finish["log_path"],
        "SELDON_NOTIFY_WALL_SECONDS": str(finish["wall_clock_s"]),
    }, task_id=finish["task_id"],
        label=outcome or ("ok" if finish["ok"] else "blocked"))


def _run_notifier(project_dir, session_id, cfg, env_updates: dict, task_id: str,
                  label: str) -> None:
    """The notify channel itself, shared by the finish signal and the stuck alarm.

    One code path, because a stuck alarm that went out by a second mechanism would be a second
    thing to configure, a second thing to time out, and a second thing that can silently not
    exist.
    """
    command = cfg.get("notify")
    if not command:
        return
    env = dict(os.environ)
    env.update(env_updates)
    timeout = cfg["notify_timeout_s"]
    failure = None
    try:
        proc = subprocess.Popen(["/bin/sh", "-c", command], cwd=project_dir, env=env,
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, start_new_session=True, text=True)
        try:
            output, _ = proc.communicate(timeout=timeout)
            if proc.returncode != 0:
                failure = {"reason": "nonzero_exit", "exit_code": proc.returncode,
                           "output_tail": (output or "")[-500:]}
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, 9)
            output, _ = proc.communicate()
            failure = {"reason": "timeout", "timeout_s": timeout,
                       "output_tail": (output or "")[-500:]}
    except Exception as exc:                                        # noqa: BLE001
        # Reported on the log, never swallowed and never raised: the finish is recorded and the
        # lease must still be released by the caller.
        failure = {"reason": "error", "error": f"{type(exc).__name__}: {exc}"}
    if failure is None:
        click.echo(f"notify: sent ({str(task_id)[:8]} {label})")
        return
    _emit(project_dir, session_id, D.EVENT_NOTIFY_FAILED,
          {"task_id": task_id, "command": command, "label": label, **failure})
    click.echo(f"notify FAILED ({failure['reason']}) for {str(task_id)[:8]}", err=True)


#: AD-035 R6: the session's output is the CLI's event stream, one JSON object per line, ending
#: in the `result` object whose `modelUsage` is the served-model receipt. `--verbose` is what
#: `-p` requires for `stream-json`. The log keeps every message the session wrote.
SESSION_OUTPUT_ARGS = ["--output-format", "stream-json", "--verbose"]


def _session_spec(project_dir: Path, rel: str) -> dict:
    """The launch block for a task (AD-035 R3): its `**Model:**` role or id, else `primary`.

    Candidacy has already refused a header that names an id outside the lock (R5), so what is
    read here is a role or a current id.
    """
    text = (project_dir / rel).read_text(encoding="utf-8", errors="surrogateescape")
    check = models.check_task_models(text)
    return models.launch_spec_for(check["role"] or check["model"] or MODEL_ROLE_DEFAULT)


#: The role a task with no `**Model:**` header runs as.
MODEL_ROLE_DEFAULT = "primary"


def _session_settings(project_dir: Path, cfg: dict) -> dict:
    """The per-launch `--settings` every dispatched session gets (FRICTION-002), merged under the model lock's.

    * `worktree.baseRef: head`: the CLI enters the worktree the dispatcher cut from main's HEAD (which carries the
      task's own claim) and never branches from `origin/<default>` instead (the CLI's default, `fresh`).
    * a `Stop` hook, `seldon dispatch stop-gate` (Part C): the completion gate.
    * a `PermissionDenied` hook, `seldon dispatch classifier-denied` (Part D): one record per classifier block.

    Each hook runs `python -P -m seldon`: `-P` keeps the session's worktree (the hook's cwd) off `sys.path`, so the
    gate is the dispatcher's installed code and never the branch the session is editing.
    """
    scfg = QS.load_stations_config(cfg)

    def hook(sub: str, timeout: int | None = None) -> dict:
        h = {"type": "command", "command": " ".join(shlex.quote(a) for a in (
            sys.executable, "-P", "-m", "seldon", "dispatch", sub, "--project", str(Path(project_dir).resolve())))}
        if timeout:
            h["timeout"] = timeout
        return h
    return {"worktree": {"baseRef": "head"},
            "hooks": {"Stop": [{"hooks": [hook("stop-gate", int(scfg["stop_gate_timeout_s"]))]}],
                      "PermissionDenied": [{"hooks": [hook("classifier-denied")]}],
                      # DISP-001R Part B step 2: a hard stop is delivered at the session's next tool boundary.
                      "PreToolUse": [{"matcher": "*", "hooks": [hook("tool-gate")]}]}}


def _launch_cmd(cfg: dict, prompt: str, spec: dict, worktree: bool = False,
                settings: dict | None = None) -> list:
    """The lock's CLI, `-p "<the dispatch line>"`, the permission mode, and the model block.

    The prompt is the protocol's own sentence. The permission mode comes from `seldon.yaml`
    with its reason beside it, never from the plist alone (DN-006 decision 5), so the one
    setting that decides what a dispatched session may do to the checkout is in the file an
    operator reads to answer that question. The executable, `--model <id>` and the
    `switchModelsOnFlag: false` settings come from the model lock (AD-035 R3, R6), never from
    this project's config: `dispatch.cli` and `dispatch.model` are refused at load.
    """
    cmd = [spec["cli_path"], "-p", prompt, *SESSION_OUTPUT_ARGS]
    mode = cfg["permission_mode"]
    if mode:
        cmd += ["--permission-mode", mode]
    args = list(spec["args"])
    if settings and cfg.get("allow"):
        # DISP-002 Part B (AD-034 ADDENDUM 02): the command shapes a task may legitimately run, each with the task-file
        # instruction that needs it beside it in seldon.yaml (`dispatch.allow`). Everything else, secrets writes
        # included, stays with the auto-mode classifier.
        settings = {**settings, "permissions": {"allow": [a["rule"] for a in cfg["allow"]]}}
    if settings:
        # One `--settings`: the lock's own keys (AD-035 R6) merged over this launch's.
        i = args.index("--settings")
        args[i + 1] = models.settings_json({**settings, **json.loads(args[i + 1])})
    if worktree:
        # DISP-001R Part A (AD-034 ADDENDUM 01): `--worktree` with NO name, so the CLI names the worktree ("If you
        # omit the name, Claude generates one such as `bright-running-fox`", code.claude.com/docs/en/worktrees),
        # cuts `.claude/worktrees/<name>` on `worktree-<name>` from HEAD (`worktree.baseRef: head`), enters it and
        # turns on its hard isolation. A name the dispatcher made up hit the CLI's 64-character limit twice
        # (RECALL-001, MCP-001). Last on the line because the flag's value is optional: nothing may follow it
        # that the CLI could read as the name.
        args = args + ["--worktree"]
    return cmd + args


def _model_receipt(log_path: Path, offset: int, spec: dict) -> dict:
    """R6: requested and served model for the session whose output starts at `offset` in the log.

    `ok` is False when the stream carried no result object or its answering model is not the
    requested one; either way the task is not counted as done (`model_substituted`).
    """
    with log_path.open("r", encoding="utf-8", errors="replace") as fh:
        fh.seek(offset)
        text = fh.read()
    envelope = models.last_result_envelope(text) or {}
    r = models.receipt(spec["model"], envelope, effort=spec["effort"])
    r.update({"role": spec["role"], "cli_version": spec["cli_version"],
              "lock_resolved_on": spec["resolved_on"]})
    return r


def _model_fields(spec: dict, refresh_note: str | None) -> dict:
    """What `dispatch_launched` records about the model, so a reader need not open the lock."""
    out = {"model": {"role": spec["role"], "family": spec["family"], "requested": spec["model"],
                     "effort": spec["effort"], "cli_path": spec["cli_path"],
                     "cli_version": spec["cli_version"],
                     "lock_resolved_on": spec["resolved_on"], "lock_evidence": spec["evidence"]}}
    if refresh_note:
        out["model"]["refresh"] = refresh_note
    return out


#: How long a reaped session's process group has, after SIGTERM, before SIGKILL. ASSUMPTION: the CLI flushes its
#: transcript and exits well inside this; a session still running after it is not going to halt.
REAP_GRACE_S = 30


#: DISP-001R Part A: how long `_run` watches a new session's log for the CLI's `init` record (the worktree it named)
#: before it stops watching and leaves the name to the finish. ASSUMPTION: the probe of CLI 2.1.303 wrote `init`
#: within two seconds of start (docs/evidence/disp001r/), after the operator's SessionStart hooks, which can run
#: for tens of seconds; two minutes bounds both. A session past it is named from its log when it ends.
INIT_WAIT_S = 120
#: The watch's read interval. Small, because the worktree's links (`dispatch.worktree_links`) are made at `init`
#: and the session's first tool call can follow its first model turn by a few seconds.
INIT_POLL_S = 0.2


def _run(cmd: list, project_dir: Path, log_path: Path, child_session_id: str,
         network_allowlist: list | None = None, extra_env: dict | None = None,
         inspector=None, inspect_every_s: float | None = None, on_reap=None, on_init=None) -> int:
    """Detached, logged, `EXIT=$?` appended.

    Working directory is the PROJECT ROOT, so `CLAUDE.md` loads — the exact inverse of
    `kg/extraction/model_stub.py`'s hermetic cwd, which exists to stop a JSON-only call
    narrating. Here the narration is the point.

    `ANTHROPIC_API_KEY` is stripped from the child's environment as well as refused in the
    parent's: the pass could have started before a shell exported one. `HEADLESS_ENV` is laid
    over the result so an inherited value cannot re-enable background tasks.

    `SELDON_SESSION_ID` is set to `child_session_id`, overriding anything inherited: it is the
    first entry of the session resolution order, so every event the child writes carries it.

    `SELDON_NETWORK_ALLOWLIST` carries the task's parsed allowlist, comma-separated
    (ai-readiness-kg/cc_tasks/2026-09-18_network_allowlist.md decision 2). It is stripped
    whenever the task declared no allowlist, so an inherited list can never license a `none`
    task's fetches: the helper that reads it refuses to run when it is unset.
    """
    env = {k: v for k, v in os.environ.items()
           if k not in D.API_KEY_VARS and k != D.NETWORK_ALLOWLIST_ENV}
    env.update(HEADLESS_ENV)
    env["SELDON_SESSION_ID"] = child_session_id
    if network_allowlist:
        env[D.NETWORK_ALLOWLIST_ENV] = ",".join(network_allowlist)
    # SEL-004: a worktree session is run with `project_dir` = its worktree and is told where
    # the primary checkout is (`seldon.core.worktree.PRIMARY_CHECKOUT_ENV`). AD-035 R3: the
    # caller's extra env carries the lock's four `ANTHROPIC_DEFAULT_*_MODEL` ids.
    env.update(extra_env or {})
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(f"=== {_now()} | dispatch | {' '.join(shlex.quote(p) for p in cmd)}\n")
        fh.flush()
        # QC-002 (AD-037-R6): the holder waits in slices of `inspect_every_s` and inspects the session between them.
        # An inspected session gets its own process group, so a reap (a hard stop the session did not answer within
        # the reap interval) ends its children too; the holder is the only process that reaps (DN-006 decision 6).
        # An uninspected one (the worktree supervisor's) stays in its caller's group, which
        # `dispatch_worktree._terminate_orphaned_session` relies on.
        start = fh.tell()
        proc = subprocess.Popen(cmd, cwd=project_dir, stdout=fh, stderr=subprocess.STDOUT, env=env,
                                start_new_session=inspector is not None)
        if on_init is not None:
            # DISP-001R Part A: the CLI names the worktree, so the dispatcher learns it from the session's `init`
            # record and hands it to `on_init` (link, record) while the session runs.
            from seldon.commands import dispatch_worktree as W
            deadline = time.monotonic() + INIT_WAIT_S
            while True:
                init = W.cli_init(log_path, start)
                if init is not None:
                    on_init(init)
                    break
                if proc.poll() is not None or time.monotonic() >= deadline:
                    break
                time.sleep(INIT_POLL_S)
        while True:
            try:
                returncode = proc.wait(timeout=inspect_every_s if inspector else None)
                break
            except subprocess.TimeoutExpired:
                reap = (inspector() or {}).get("reap")
                if reap:
                    sig = _reap_group(proc)
                    if on_reap:
                        on_reap(reap, proc.pid, sig)
        fh.write(f"\nEXIT={returncode}\n")
    return returncode


def _reap_group(proc) -> str:
    """SIGTERM the session's process group, SIGKILL after `REAP_GRACE_S`. Returns the signal that ended it."""
    import signal
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return "none (already exited)"
    try:
        proc.wait(timeout=REAP_GRACE_S)
        return "SIGTERM"
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
        return "SIGKILL"


def _log_offset(log_path: Path) -> int:
    """Where the next session's output will start in its (appended) log."""
    return log_path.stat().st_size if log_path.exists() else 0


def _claim(project_dir, driver, database, domain_config, session_id, row) -> dict:
    """Walk the chosen task to `in_progress`, recording `claimed_by = dispatcher:<host>:<pid>`.

    `proposed -> in_progress` is not an edge on the ResearchTask state machine, so from
    `proposed` the claim is `proposed -> accepted -> in_progress`; the claim marker lands on
    the second transition, which is where the machine puts it.
    """
    who = D.holder_id()
    state = row["state"]
    done = []
    try:
        for target in CLAIM_PATH[state]:
            transition_task(project_dir=project_dir, driver=driver, database=database,
                            domain_config=domain_config, artifact_id=row["task_id"],
                            current_state=state, new_state=target, actor=ACTOR,
                            authority="accepted", session_id=session_id,
                            claimed_by=who if target == "in_progress" else None)
            done.append(f"{state} -> {target}")
            state = target
    except Exception as exc:                                        # noqa: BLE001
        # Reported, never swallowed. `transition_task` validates every precondition before its
        # first write, so a failure on the first hop left the graph untouched; a failure on the
        # second leaves the task `accepted`, which is an open state the next pass re-evaluates.
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "transitions": done,
                "claimed_by": who}
    return {"ok": True, "error": None, "transitions": done, "claimed_by": who}


def _state_of(driver, database, task_id) -> str | None:
    with driver.session(database=database) as s:
        r = s.run("MATCH (t:ResearchTask {artifact_id: $id}) RETURN t.state AS state",
                  id=task_id).single()
    return r["state"] if r else None


def block_reason(outcome: str, code, log_rel) -> str:
    """The reason a dispatcher block stores (AD-038-R7): the finish's outcome, its exit code and its log, so the
    task says why it stopped without a reader opening the event store."""
    return f"dispatcher: {outcome} (exit {code}; log {log_rel})"


def _block(project_dir, driver, database, domain_config, session_id, task_id, state, code,
           log_rel, *, reason: str):
    if state != "in_progress":
        return
    try:
        transition_task(project_dir=project_dir, driver=driver, database=database,
                        domain_config=domain_config, artifact_id=task_id,
                        current_state="in_progress", new_state="blocked", actor=ACTOR,
                        authority="accepted", session_id=session_id, block_reason=reason)
    except Exception as exc:                                        # noqa: BLE001
        click.echo(f"could not block {task_id[:8]}: {exc}", err=True)


def _stations_mod():
    from seldon.commands import dispatch_stations as ST
    return ST


def _open_huddles(project_dir: Path) -> list:
    from seldon.core import stations as S
    from seldon.core.events import read_events
    return S.open_huddles(read_events(project_dir))


def _station_fields(cfg: dict, chosen: dict) -> dict:
    """What `dispatch_launched` records for the stations: the premise review (a), and R7's inspection reserve."""
    from seldon.core import stations as S
    scfg = S.load_stations_config(cfg)
    tokens = (chosen.get("criteria") or {}).get("c4", {}).get("declared_tokens")
    return {"premises": chosen.get("premises"),
            "inspection_reserve": {"share": scfg["inspection_reserve_share"],
                                   "tokens": int((tokens or 0) * scfg["inspection_reserve_share"])}}


def _premise_holds(project_dir: Path, driver, database) -> dict:
    """Tasks held by an open `premise_false` Issue (c13), read from the event store and the Issue's graph state."""
    from seldon.core.events import read_events

    def issue_state(issue_id):
        with driver.session(database=database) as s:
            r = s.run("MATCH (i:Issue {artifact_id: $id}) RETURN i.state AS state", id=issue_id).single()
        return r["state"] if r else None
    return _stations_mod().premise_holds(read_events(project_dir), issue_state)


def launcher_fingerprint(project_dir: Path, rel: str) -> dict:
    """What a launch failure's stderr line can depend on (DISP-001R Part A step 2): the CLI the lock names, the
    dispatcher's own code (the last commit touching the installed `seldon/` package) and the task file's bytes.

    A `launch_failed` task is held while all three are unchanged, because the same launcher given the same task
    writes the same stderr line; any change can make the line differ, so the task is launched again.
    """
    import hashlib

    pkg_root = Path(__file__).resolve().parent.parent.parent
    code = D.git(pkg_root, "log", "-1", "--format=%H", "--", "seldon")
    path = Path(project_dir) / rel
    return {"cli_version": _session_spec(project_dir, rel)["cli_version"],
            "dispatcher_code": code.stdout.strip() if code.returncode == 0 else None,
            "task_file_sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None}


def _launch_holds(project_dir: Path) -> dict:
    """Tasks whose newest finish is `launch_failed` with the launcher unchanged since (c15, DISP-001R Part A).

    `{task_id: {stderr_line, finished_at, fingerprint}}`. The hold clears by itself when `launcher_fingerprint`
    differs from the one the failure recorded, so a repeating launcher defect is noticed once and does not loop.
    """
    from seldon.core.events import read_events

    newest: dict[str, dict] = {}
    for e in read_events(project_dir):
        if e.get("event_type") == D.EVENT_FINISHED:
            newest[(e.get("payload") or {}).get("task_id")] = e
    holds = {}
    for task_id, e in newest.items():
        p = e.get("payload") or {}
        if p.get("outcome") != "launch_failed" or not p.get("source_file"):
            continue
        now = launcher_fingerprint(project_dir, p["source_file"])
        if now == p.get("fingerprint"):
            holds[task_id] = {"stderr_line": p.get("stderr_line"), "finished_at": e.get("timestamp"),
                              "fingerprint": now}
    return holds


def _premise_review(project_dir, config, driver, database, domain_config, session_id, cfg, row, dry_run) -> dict:
    """Station (a) for one eligible task, with its refusal: `environment_in_flight` once per sibling lease
    acquisition (a standing condition, recorded where it begins), `premise_false` with an Issue naming the
    premise. A dry run reviews and records nothing."""
    from seldon.core import stations as S
    review = _stations_mod().premise_review(project_dir, config, cfg, row)
    if review["ok"] or dry_run:
        if not review["ok"]:
            click.echo(f"dry run: {row['task_id'][:8]} would be refused on its premises", err=True)
        return review
    env = review["environment"]
    if env["outcome"] != "true":
        acquisitions = {n: h.get("acquired_at") for n, h in env["held"].items()}
        seen = _last_payload(project_dir, D.EVENT_REFUSED,
                             where=lambda p: p.get("reason") == S.REFUSED_ENVIRONMENT_IN_FLIGHT
                             and p.get("acquisitions") == acquisitions)
        if seen is None:
            _emit(project_dir, session_id, D.EVENT_REFUSED,
                  {"task_id": row["task_id"], "reason": S.REFUSED_ENVIRONMENT_IN_FLIGHT, "held": env["held"],
                   "acquisitions": acquisitions})
            _record_and_push(project_dir, config, cfg)
        click.echo(f"refused: {S.REFUSED_ENVIRONMENT_IN_FLIGHT}: a dispatcher holds a lease on "
                   f"{', '.join(sorted(env['held']))}, which this project's environment names", err=True)
        return review
    false = review["false"]
    names = "; ".join(f"line {f.get('line')}: {f.get('statement')} ({f.get('outcome')})" for f in false)
    issue_id = _file_premise_issue(project_dir, driver, database, domain_config, session_id, row, names)
    _emit(project_dir, session_id, D.EVENT_REFUSED,
          {"task_id": row["task_id"], "reason": S.REFUSED_PREMISE_FALSE, "issue_id": issue_id,
           "false": [{k: f.get(k) for k in ("line", "statement", "kind", "command", "outcome")} for f in false],
           "source_file": row["source_file"]})
    click.echo(f"refused {row['task_id'][:8]}: {S.REFUSED_PREMISE_FALSE}: {names} (Issue {str(issue_id)[:8]})",
               err=True)
    return review


def _file_premise_issue(project_dir, driver, database, domain_config, session_id, row, names) -> str | None:
    """The Issue AD-037-R6 (a) requires: it names the false premise, and while it is open the task waits (c13)."""
    from seldon.core.artifacts import create_artifact
    return create_artifact(
        project_dir=project_dir, driver=driver, database=database, domain_config=domain_config,
        artifact_type="Issue",
        properties={"name": f"premise_false: {Path(row['source_file']).stem}"[:200],
                    "description": (f"Station (a) refused {row['source_file']} ({row['task_id']}) before launch: "
                                    f"{names}. Correct the premise (or the task) and resolve this Issue; the task "
                                    f"waits while it is open (AD-037-R6 a, QC-002)."),
                    "issue_type": "factual_error", "importance": "high", "urgency": "high",
                    "detection_method": "automated_check", "target": "data"},
        actor=ACTOR, authority="accepted", session_id=session_id)


@dispatch_group.group("lease")
def lease_group():
    """The single-instance lease."""


@lease_group.command("reap")
@click.option("--task", "task_stem", default=None,
              help="reap a worktree task's lease (`<lease_dir>/<stem>.lock`, SEL-004) instead "
                   "of the pass lease")
def lease_reap(task_stem):
    """Release a lease whose holder is gone. **Refuses while the holder PID is alive.**

    Operator-only and PID-gated, never age-gated: DD-022's orphan-reap rule adopted unchanged.
    An age threshold releases a lease a healthy long-running holder still needs, and two
    dispatchers believing they are one is the defect the lease exists for.
    """
    project_dir, config, driver, database, _dc, _sid = _open_project()
    driver.close()
    cfg = D.load_dispatch_config(project_dir, config)
    path = (D.worktree_lease_path(project_dir, cfg, task_stem) if task_stem
            else project_dir / cfg["lease_file"])
    out = D.reap_lease(path)
    click.echo(json.dumps(out, indent=1))
    if not out["reaped"] and out["reason"] == "holder_alive":
        raise SystemExit(1)


@lease_group.command("show")
def lease_show():
    """The lease body, as it stands. Takes no lock."""
    project_dir, config, driver, database, _dc, _sid = _open_project()
    driver.close()
    cfg = D.load_dispatch_config(project_dir, config)
    click.echo(json.dumps(D.read_lease(project_dir / cfg["lease_file"]) or
                          {"lease": "free"}, indent=1))


# The worktree supervisor (`seldon dispatch supervise`, SEL-004) registers itself on
# `dispatch_group` when its module is imported; imported last because it imports this module.
from seldon.commands import dispatch_worktree as _dispatch_worktree  # noqa: E402,F401
# The stations' commands (QC-002, AD-037-R6), for the same reason.
from seldon.commands import dispatch_stations as _dispatch_stations  # noqa: E402,F401
