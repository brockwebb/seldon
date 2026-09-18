"""`seldon dispatch` — the standing dispatcher.

Implements `ai-readiness-kg/docs/design/2026-09-15_DN-006_standing_dispatcher.md` decisions 1
to 10 (decision 8, the cadence, landed with `cc_tasks/2026-09-16_cadence_and_enable.md`), and
the rule that the dispatcher commits and pushes every line it writes to the tracked event store
(`cc_tasks/2026-09-16_dispatcher_commits_its_record.md`, DN-006 ADDENDUM_04).

    seldon dispatch once        one evaluation pass, at most one launch, exit
    seldon dispatch status      the live criteria vector for every candidate
    seldon dispatch lease reap  operator-only; refuses while the holder PID is alive

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
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import click

from seldon.config import (
    bind_process_session, get_current_session, get_neo4j_driver, load_project_config,
)
from seldon.core import cadence as C
from seldon.core import dispatch as D
from seldon.core.artifacts import transition_task
from seldon.core.events import append_event, make_event
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


def _tasks(driver, database) -> list:
    """Every open ResearchTask, with its `precedes` predecessors' states.

    The graph IS the queue (DN-006 decision 1): there is no separate table to keep in step,
    and a task becomes dispatchable by being registered, not by being enqueued.
    """
    q = ("MATCH (t:ResearchTask) WHERE t.state IN $states "
         "OPTIONAL MATCH (p:ResearchTask)-[:PRECEDES|precedes]->(t) "
         "RETURN t.artifact_id AS artifact_id, t.name AS name, t.state AS state, "
         "       t.source_file AS source_file, t.created_at AS created_at, "
         "       collect({artifact_id: p.artifact_id, state: p.state}) AS predecessors "
         "ORDER BY t.created_at")
    with driver.session(database=database) as s:
        rows = [dict(r) for r in s.run(q, states=list(D.DISPATCHABLE_STATES))]
    for r in rows:
        r["predecessors"] = [p for p in r["predecessors"] if p.get("artifact_id")]
    return rows


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


def _survey(project_dir, config, driver, database):
    """Everything a pass needs to decide, gathered once. Shared by `once` and `status` so the
    two can never disagree about what the criteria said."""
    cfg = D.load_dispatch_config(project_dir, config)
    band = D.resolve_standing_band(project_dir, cfg["standing_band_ref"])
    tree = D.tree_state(project_dir)
    lease_body = D.read_lease(project_dir / cfg["lease_file"])
    claim = _claim_in_flight(driver, database)
    rows = [D.evaluate(project_dir, t, cfg, band, tree, claim, lease_body)
            for t in _tasks(driver, database)]
    return cfg, band, tree, lease_body, claim, D.fifo(rows)


def _emit(project_dir, session_id, event_type, payload):
    append_event(project_dir, make_event(event_type=event_type, actor=ACTOR,
                                         authority="accepted", payload=payload,
                                         session_id=session_id))


def _store_rel(config) -> str:
    return config.get("event_store", {}).get("path", "seldon_events.jsonl")


def _record_own_lines(project_dir, config, cfg) -> dict:
    """Commit the lines the dispatcher appended to the tracked event store, and only those.

    `ai-readiness-kg/cc_tasks/2026-09-16_dispatcher_commits_its_record.md` decision 1, closing
    DN-006 ADDENDUM_03 §4: `dispatch_finished` is appended AFTER the dispatched session has
    committed and pushed, so before this every completed dispatch left the store modified by a
    line only the dispatcher wrote — and the cadence gates creation on a clean tree, so that one
    line could block cycle 5.

    **Callers hold the lease.** A held lease is how a pass knows no dispatched session is
    working in the checkout; a `git commit` beside a working session is DD-019's class and an
    `index.lock` collision besides. The three lines written WITHOUT the lease are therefore
    never committed where they are written, and the next pass that holds the lease commits them
    first (`_pass`):

    * `lease_held` — written while a session is in flight; that session's own commit, or the
      finish pass's, carries it.
    * `dispatch_observed_stop` — the operator has stopped the world, and a commit and a push
      are writes the STOP file exists to prevent.
    * `api_key_present` — the DD-007 refusal comes before the lease and touches nothing else
      (`test_an_api_key_refuses_before_any_claim`). The launchd wrapper unsets both variables,
      so this is reachable only from a hand-run pass.

    Pathspec-limited to the store (`D.commit_paths`), and only when every appended line is the
    dispatcher's (`D.own_appended_lines`). The message names each event type and task id, so
    `git log` reads as the log's own index. No event is written for the commit: git records it.
    """
    store = _store_rel(config)
    if D.tree_state(project_dir)["branch"] != cfg["branch"]:
        return {"committed": False, "reason": "wrong_branch"}
    own = D.own_appended_lines(project_dir, store, ACTOR)
    if not own["ok"]:
        if own["reason"] not in ("clean", "untracked"):
            detail = {"not_own_lines": "not dispatcher-only (also written by "
                                       f"{', '.join(own.get('foreign_actors', []))})",
                      "not_append_only": "not append-only against HEAD",
                      "unparseable": "an appended line does not parse"}[own["reason"]]
            click.echo(f"record: {store} NOT committed: {detail}", err=True)
        return {"committed": False, "reason": own["reason"]}
    types = list(dict.fromkeys(e.get("event_type") for e in own["events"]))
    ids = list(dict.fromkeys(
        str(p.get("task_id") or p.get("artifact_id"))[:8]
        for p in ((e.get("payload") or {}) for e in own["events"])
        if p.get("task_id") or p.get("artifact_id")))
    message = (f"record: {', '.join(types)} {', '.join(ids) or '-'} — "
               f"{len(own['events'])} line(s) written by the standing dispatcher")
    outcome = D.commit_paths(project_dir, [store], message)
    if outcome["committed"]:
        click.echo(f"record: {message} -> {outcome['commit']}")
    else:
        click.echo(f"record: {store} NOT committed ({outcome['reason']}): "
                   f"{outcome.get('stderr', '')}", err=True)
    return outcome


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
    payload = {"enabled": cfg["enabled"], "branch": tree["branch"],
               "configured_branch": cfg["branch"], "tree_dirty": tree["dirty"],
               "tree_dirty_count": tree["dirty_count"],
               "stop_file": str(cfg["stop_file"]),
               "stop_file_present": (project_dir / cfg["stop_file"]).exists(),
               "standing_band": band, "standing_band_ref": cfg["standing_band_ref"],
               "permission_mode": cfg["permission_mode"],
               "lease": lease_body or None, "claim_in_flight": claim,
               "open_tasks": len(rows),
               "candidates": sum(1 for r in rows if r["candidate"]),
               "eligible": [r["task_id"] for r in rows if r["eligible"]],
               "cadence": cadence_rows,
               "tasks": rows}
    if as_json:
        click.echo(json.dumps(payload, indent=1, default=str))
        return
    click.echo(f"dispatch: enabled={cfg['enabled']}  branch={tree['branch']}"
               f" (configured {cfg['branch']})  dirty={tree['dirty']}"
               f" ({tree['dirty_count']} path(s))")
    click.echo(f"  stop file   : {cfg['stop_file']} "
               f"{'PRESENT' if payload['stop_file_present'] else 'absent'}")
    click.echo(f"  standing band: {band:,} tokens  <- {cfg['standing_band_ref']}")
    held = (lease_body or {}).get("holder")
    click.echo(f"  lease        : {held or 'free'}"
               + (f" (released {lease_body['released_at']})"
                  if not held and (lease_body or {}).get("released_at") else ""))
    click.echo(f"  claim        : {claim['artifact_id'][:8] + ' by ' + claim['claimed_by'] if claim else 'none'}")
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
    """One evaluation pass: at most one launch, then exit.

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
            return
        try:
            _pass(project_dir, config, driver, database, domain_config, session_id, cfg,
                  lease, dry_run)
        finally:
            lease.__exit__(None, None, None)
    finally:
        driver.close()


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


def _commit_registered(project_dir, config, cfg, tasks, tree, claim, dry_run) -> list:
    """DN-006 ADDENDUM_03 §2: a registered task file is committed by the dispatcher, not by a
    person.

    **The wedge this removes.** `seldon cc register` leaves two things behind: an untracked
    task file, and an `artifact_created` line appended to the event store, which this project
    tracks. Decision 2's c1 wants the file git-tracked and c7 wants the tree clean, so a
    Desktop session that registers a task produces a task that can never be dispatched — and
    blocks every OTHER task in the queue at the same time, because c7 is a fact about the
    checkout and not about the task being evaluated. That is the wedge ADDENDUM_02 §1 found in
    the cadence, one step earlier in the life of a task, and the commit is entailed by
    decision 2 in exactly the way it was entailed by decision 8.

    **Both halves of the footprint go in one commit.** The task file, any untracked
    `<stem>_ADDENDUM*.md` beside it (c3's evidence: a dispatcher that committed a base task and
    left its supersession notice untracked would hand a session a task the notice forbids), and
    the event store, whose modified line is the record of the very registration being
    committed. Committing the file alone leaves c7 false on that line and makes this mechanism
    incapable of freeing a single task.

    **What it will not touch.** Anything else untracked or modified stays c7's business
    (`git add -A` is what the cadence already refuses); and it writes nothing into a checkout
    with a dispatcher claim in flight or on a branch that is not the configured one, for
    DD-019's reason.

    **No event.** The commit is recorded by git and the registration by `artifact_created`; a
    third record of one fact is what decision 1 spent this task removing. The pass names it on
    stdout, which is what the launchd wrapper's log carries.
    """
    if dry_run or claim is not None or tree["branch"] != cfg["branch"]:
        return []
    store = config.get("event_store", {}).get("path", "seldon_events.jsonl")
    done = []
    for task in tasks:
        rel = task.get("source_file")
        if not rel:
            continue
        path = project_dir / rel
        if not path.is_file() or D.is_tracked(project_dir, path):
            continue
        paths = [rel]
        paths += [str(a.relative_to(project_dir)) for a in D.addenda_for(path)
                  if not D.is_tracked(project_dir, a)]
        paths.append(store)
        outcome = D.commit_paths(project_dir, paths,
                                 f"register: {rel} — registered task file committed by the "
                                 f"standing dispatcher")
        if outcome["committed"]:
            click.echo(f"register: {rel} committed as {outcome['commit']} "
                       f"({len(outcome['committed_paths'])} path(s))")
        else:
            # Reported, never swallowed. A failure here leaves the file exactly as the
            # registration left it; the next pass tries again, and `status` still shows why
            # the task is ineligible.
            click.echo(f"register: {rel} NOT committed ({outcome['reason']}): "
                       f"{outcome.get('stderr', '')}", err=True)
        done.append({"source_file": rel, **outcome})
    record = _commit_registration_records(project_dir, store)
    if record is not None:
        done.append(record)
    return done


def _commit_registration_records(project_dir, store) -> dict | None:
    """Commit the store when it holds the uncommitted record of a registration that committed
    its own file (`ai-readiness-kg/cc_tasks/2026-09-18_registration_commits.md` decision 4).

    Registration now commits an untracked task file by path and writes `artifact_created`
    with `source_commit` AFTER that commit, so the line cannot be in it. The loop above keys on
    an untracked file and never sees such a task; without this, the one line keeps c7 false for
    the whole queue — decision 3's wedge, one commit later. The store is committed on the same
    terms the loop above has always committed it with a task file (whole file, pathspec to the
    store alone, only with no claim in flight — the caller's gate), and only when it is
    append-only against HEAD: an in-place edit is not a registration's footprint.

    Returns the commit outcome, or None when there is no such record to commit.
    """
    appended = D.appended_events(project_dir, store)
    if not appended["ok"]:
        return None
    records = [e for e in appended["events"]
               if e.get("event_type") == "artifact_created"
               and (e.get("payload") or {}).get("artifact_type") == "ResearchTask"
               and ((e.get("payload") or {}).get("properties") or {}).get("source_commit")]
    if not records:
        return None
    names = ", ".join(f"{e['payload']['properties'].get('source_file')} "
                      f"({str(e['payload'].get('artifact_id'))[:8]})" for e in records)
    outcome = D.commit_paths(project_dir, [store],
                             f"register: record of {names} — registration line committed by "
                             f"the standing dispatcher")
    if outcome["committed"]:
        click.echo(f"register: record of {names} committed as {outcome['commit']}")
    else:
        click.echo(f"register: record of {names} NOT committed ({outcome['reason']}): "
                   f"{outcome.get('stderr', '')}", err=True)
    return {"source_file": store, **outcome}


def _pass(project_dir, config, driver, database, domain_config, session_id, cfg, lease,
          dry_run):
    band = D.resolve_standing_band(project_dir, cfg["standing_band_ref"])
    claim = _claim_in_flight(driver, database)
    # The dispatcher's own leftovers FIRST, before anything reads the tree: lines an earlier
    # pass appended and did not commit — a pass that died between append and commit, or a
    # dispatcher process still running the code from before decision 1 existed. With no claim
    # in flight and the lease held, nothing else is working in the checkout.
    if claim is None and not dry_run:
        _record_own_lines(project_dir, config, cfg)
    tree = D.tree_state(project_dir)
    # Registered-but-uncommitted task files BEFORE the cadence and before candidacy: the
    # cadence gates creation on a clean tree, and an untracked task file is one of the things
    # making it dirty, so committing first is what lets a due period be served in the same pass.
    tasks = _tasks(driver, database)
    if _commit_registered(project_dir, config, cfg, tasks, tree, claim, dry_run):
        tree = D.tree_state(project_dir)
    # Cadence BEFORE candidacy (DN-006 decision 8): a task this pass creates is a task this
    # pass may then launch, so the queue it evaluates is the queue as it stands after the
    # calendar has had its say.
    if cfg.get("cadence"):
        _cadence(project_dir, config, driver, database, domain_config, session_id, cfg, tree,
                 claim, dry_run)
        tree = D.tree_state(project_dir)
    lease_body = D.read_lease(project_dir / cfg["lease_file"])
    rows = D.fifo([D.evaluate(project_dir, t, cfg, band, tree, claim, lease_body)
                   for t in _tasks(driver, database)])

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
        for r in rows:
            reason = D.first_refusal_reason(r) if r["candidate"] else None
            if reason:
                click.echo(f"  {(r['task_id'] or '?')[:8]} {reason}: "
                           f"{','.join(r['failed'])}  {r['source_file']}")
                if reason == "network_undeclared":
                    click.echo(f"      {r['criteria']['c5'].get('message', '')}")
        # Decision 2's retry: whatever this pass or an earlier one committed and could not
        # push is pushed now. A no-op when the branch is level with its upstream.
        if not dry_run and claim is None:
            _push(project_dir, cfg)
        return

    chosen = eligible[0]
    if dry_run:
        click.echo(json.dumps({"would_launch": chosen["task_id"],
                               "source_file": chosen["source_file"],
                               "criteria": chosen["criteria"]}, indent=1, default=str))
        return

    rel = chosen["source_file"]
    stem = Path(rel).stem
    log_dir = project_dir / cfg["log_dir"]
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{stem}.log"
    prompt = DISPATCH_LINE.format(rel=rel, stem=stem)

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
    cmd = _launch_cmd(cfg, prompt)
    # The child's root session id, minted here and handed down through the environment, so a
    # reader can join the session's `cc` events to this launch (decision 2).
    child_session_id = str(uuid.uuid4())
    _emit(project_dir, session_id, D.EVENT_LAUNCHED,
          {"task_id": chosen["task_id"], "source_file": rel,
           "child_session_id": child_session_id,
           "claimed_by": claimed["claimed_by"], "transitions": claimed["transitions"],
           "criteria": chosen["criteria"], "framework_layer": chosen["framework_layer"],
           "network_allowlist": chosen["criteria"]["c5"]["network_allowlist"],
           "log_path": str(log_path.relative_to(project_dir)),
           "command": " ".join(shlex.quote(p) for p in cmd),
           "permission_mode": cfg["permission_mode"], "launched_at": _now()})
    # The claim's transitions and `dispatch_launched` are committed and pushed BEFORE the
    # session starts, so it opens on a clean, level tree. Left for the session, they were the
    # dirt it found on opening and the lines its own final commit had to carry.
    _record_and_push(project_dir, config, cfg)
    click.echo(f"launching {chosen['task_id'][:8]} {rel} -> "
               f"{log_path.relative_to(project_dir)}")

    started = time.monotonic()
    code = _run(cmd, project_dir, log_path, child_session_id,
                network_allowlist=chosen["criteria"]["c5"]["network_allowlist"])
    wall = round(time.monotonic() - started, 3)

    result_path = project_dir / "cc_tasks" / f"{stem}_RESULT.md"
    graph_state = _state_of(driver, database, chosen["task_id"])
    ok = code == 0 and result_path.is_file() and graph_state == "completed"
    finish = {"task_id": chosen["task_id"], "child_session_id": child_session_id,
              "exit_code": code, "wall_clock_s": wall,
              "result_present": result_path.is_file(),
              "result_path": str(result_path.relative_to(project_dir)),
              "graph_state_observed": graph_state, "ok": ok,
              "log_path": str(log_path.relative_to(project_dir))}
    _emit(project_dir, session_id, D.EVENT_FINISHED, finish)
    if not ok:
        # Blocked, never retried. The next OODA reads the log and decides; a loop that cannot
        # see why the last attempt failed cannot decide anything and would spend on each guess.
        _block(project_dir, driver, database, domain_config, session_id, chosen["task_id"],
               graph_state, code, log_path.relative_to(project_dir))
        click.echo(f"finished exit={code} result={result_path.is_file()} "
                   f"graph={graph_state} -> blocked", err=True)
        # After the walk to `blocked`, so what the operator is told is already on the log;
        # before the commit, so a `dispatch_notify_failed` ships with it.
        _notify(project_dir, session_id, cfg, finish, chosen.get("name") or stem)
        _record_and_push(project_dir, config, cfg)
        return
    click.echo(f"finished exit=0 in {wall}s; {stem}_RESULT.md present; graph completed")
    _notify(project_dir, session_id, cfg, finish, chosen.get("name") or stem)
    _record_and_push(project_dir, config, cfg)


def _notify(project_dir, session_id, cfg, finish: dict, task_name: str) -> None:
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
    command = cfg.get("notify")
    if not command:
        return
    env = dict(os.environ)
    env.update({
        "SELDON_NOTIFY_TASK_ID": str(finish["task_id"]),
        "SELDON_NOTIFY_TASK_NAME": str(task_name),
        "SELDON_NOTIFY_OK": "true" if finish["ok"] else "false",
        # The word a notification body wants, so a template needs no shell conditional.
        "SELDON_NOTIFY_OUTCOME": "ok" if finish["ok"] else "blocked",
        "SELDON_NOTIFY_RESULT_PATH": finish["result_path"],
        "SELDON_NOTIFY_LOG_PATH": finish["log_path"],
        "SELDON_NOTIFY_WALL_SECONDS": str(finish["wall_clock_s"]),
    })
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
        click.echo(f"notify: sent ({finish['task_id'][:8]} "
                   f"{'ok' if finish['ok'] else 'blocked'})")
        return
    _emit(project_dir, session_id, D.EVENT_NOTIFY_FAILED,
          {"task_id": finish["task_id"], "command": command, **failure})
    click.echo(f"notify FAILED ({failure['reason']}) for {finish['task_id'][:8]}", err=True)


def _launch_cmd(cfg: dict, prompt: str) -> list:
    """`claude -p "<the dispatch line>"` with the non-interactive permission mode.

    The prompt is the protocol's own sentence. The permission mode comes from `seldon.yaml`
    with its reason beside it, never from the plist alone (DN-006 decision 5), so the one
    setting that decides what a dispatched session may do to the checkout is in the file an
    operator reads to answer that question.
    """
    cmd = [cfg.get("cli", "claude"), "-p", prompt]
    mode = cfg["permission_mode"]
    if mode:
        cmd += ["--permission-mode", mode]
    if cfg.get("model"):
        cmd += ["--model", cfg["model"]]
    return cmd


def _run(cmd: list, project_dir: Path, log_path: Path, child_session_id: str,
         network_allowlist: list | None = None) -> int:
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
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(f"=== {_now()} | dispatch | {' '.join(shlex.quote(p) for p in cmd)}\n")
        fh.flush()
        proc = subprocess.run(cmd, cwd=project_dir, stdout=fh, stderr=subprocess.STDOUT,
                              env=env)
        fh.write(f"\nEXIT={proc.returncode}\n")
    return proc.returncode


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


def _block(project_dir, driver, database, domain_config, session_id, task_id, state, code,
           log_rel):
    if state != "in_progress":
        return
    try:
        transition_task(project_dir=project_dir, driver=driver, database=database,
                        domain_config=domain_config, artifact_id=task_id,
                        current_state="in_progress", new_state="blocked", actor=ACTOR,
                        authority="accepted", session_id=session_id)
    except Exception as exc:                                        # noqa: BLE001
        click.echo(f"could not block {task_id[:8]}: {exc}", err=True)


@dispatch_group.group("lease")
def lease_group():
    """The single-instance lease."""


@lease_group.command("reap")
def lease_reap():
    """Release a lease whose holder is gone. **Refuses while the holder PID is alive.**

    Operator-only and PID-gated, never age-gated: DD-022's orphan-reap rule adopted unchanged.
    An age threshold releases a lease a healthy long-running holder still needs, and two
    dispatchers believing they are one is the defect the lease exists for.
    """
    project_dir, config, driver, database, _dc, _sid = _open_project()
    driver.close()
    cfg = D.load_dispatch_config(project_dir, config)
    out = D.reap_lease(project_dir / cfg["lease_file"])
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
