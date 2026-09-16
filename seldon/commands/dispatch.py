"""`seldon dispatch` — the standing dispatcher.

Implements `ai-readiness-kg/docs/design/2026-09-15_DN-006_standing_dispatcher.md` decisions 1
to 7, 9 and 10. Decision 8 (cadence) is a later task and is deliberately absent.

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
from datetime import datetime, timezone
from pathlib import Path

import click

from seldon.config import get_current_session, get_neo4j_driver, load_project_config
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
DISPATCH_LINE = (
    "Read CLAUDE.md, then execute {rel}. Glob and read all sibling {stem}_ADDENDUM*.md files "
    "before starting; an addendum can amend or SUPERSEDE the base task."
)

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
    click.echo(f"  lease        : {lease_body.get('holder') if lease_body else 'free'}")
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
            _emit(project_dir, session_id, D.EVENT_REFUSED,
                  {"task_id": None, "reason": "lease_held", "holder": held.body.get("holder"),
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


def _stop_already_observed(project_dir: Path, stop: Path) -> bool:
    """Has this STOP-file appearance already been recorded? Compares the file's mtime with the
    last `dispatch_observed_stop`, so removing and re-creating the file is a new appearance and
    a file left in place for a week is one."""
    from seldon.core.events import read_events
    mtime = stop.stat().st_mtime
    last = None
    for ev in read_events(project_dir):
        if ev.get("event_type") == D.EVENT_OBSERVED_STOP:
            last = ev["payload"].get("stop_mtime")
    return last is not None and abs(float(last) - mtime) < 1e-6


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
            click.echo(f"cadence {row['cadence']} {row['period']} is due and NOT created "
                       f"({blocked})", err=True)
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
    band = D.resolve_standing_band(project_dir, cfg["standing_band_ref"])
    tree = D.tree_state(project_dir)
    claim = _claim_in_flight(driver, database)
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
        return

    lease.heartbeat(task=chosen["task_id"])
    cmd = _launch_cmd(cfg, prompt)
    _emit(project_dir, session_id, D.EVENT_LAUNCHED,
          {"task_id": chosen["task_id"], "source_file": rel,
           "claimed_by": claimed["claimed_by"], "transitions": claimed["transitions"],
           "criteria": chosen["criteria"], "framework_layer": chosen["framework_layer"],
           "log_path": str(log_path.relative_to(project_dir)),
           "command": " ".join(shlex.quote(p) for p in cmd),
           "permission_mode": cfg["permission_mode"], "launched_at": _now()})
    click.echo(f"launching {chosen['task_id'][:8]} {rel} -> "
               f"{log_path.relative_to(project_dir)}")

    started = time.monotonic()
    code = _run(cmd, project_dir, log_path)
    wall = round(time.monotonic() - started, 3)

    result_path = project_dir / "cc_tasks" / f"{stem}_RESULT.md"
    graph_state = _state_of(driver, database, chosen["task_id"])
    ok = code == 0 and result_path.is_file() and graph_state == "completed"
    _emit(project_dir, session_id, D.EVENT_FINISHED,
          {"task_id": chosen["task_id"], "exit_code": code, "wall_clock_s": wall,
           "result_present": result_path.is_file(),
           "result_path": str(result_path.relative_to(project_dir)),
           "graph_state_observed": graph_state, "ok": ok,
           "log_path": str(log_path.relative_to(project_dir))})
    if not ok:
        # Blocked, never retried. The next OODA reads the log and decides; a loop that cannot
        # see why the last attempt failed cannot decide anything and would spend on each guess.
        _block(project_dir, driver, database, domain_config, session_id, chosen["task_id"],
               graph_state, code, log_path.relative_to(project_dir))
        click.echo(f"finished exit={code} result={result_path.is_file()} "
                   f"graph={graph_state} -> blocked", err=True)
        return
    click.echo(f"finished exit=0 in {wall}s; {stem}_RESULT.md present; graph completed")


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


def _run(cmd: list, project_dir: Path, log_path: Path) -> int:
    """Detached, logged, `EXIT=$?` appended.

    Working directory is the PROJECT ROOT, so `CLAUDE.md` loads — the exact inverse of
    `kg/extraction/model_stub.py`'s hermetic cwd, which exists to stop a JSON-only call
    narrating. Here the narration is the point.

    `ANTHROPIC_API_KEY` is stripped from the child's environment as well as refused in the
    parent's: the pass could have started before a shell exported one.
    """
    env = {k: v for k, v in os.environ.items() if k not in D.API_KEY_VARS}
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
