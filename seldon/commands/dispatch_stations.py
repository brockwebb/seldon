"""AD-037-R6's stations at the dispatcher and the session's side of them (QC-002).

    seldon dispatch part-complete --part A     the session, at each Part boundary (station c)
    seldon dispatch boundary                   the session, at each loop boundary: halt if a stop is written
    seldon dispatch first-article --loop L --output P [--wait]     the session, after a loop's first unit (b)
    seldon dispatch stop <task> [--hard] --reason R                the operator's andon (d)
    seldon dispatch huddle <task> --reading R --cause C --gate G   FC-29's record; `--id` fills an open one (d)
    seldon dispatch inspect [<task>]           one inspection now, as the dispatcher's pass runs it
    seldon dispatch stop-gate --project P      the session's Stop hook: run declared Parts' checks (FRICTION-002 C)
    seldon dispatch classifier-denied --project P   the session's PermissionDenied hook (FRICTION-002 D)

The session's commands exit `HALT_EXIT` (3) when a stop is written for its task; they write `andon_halted` first,
so the dispatcher sees the halt before the process ends. The protocol a session follows is
`docs/conventions/dispatched_session_protocol.md`; `seldon go` prints its three lines in a Claude Code session.

Who runs the inspection: the lease holder (the pass that launched the session) inspects every `poll_interval_s`
while it waits, and is the only process that reaps. A pass that finds the lease held by a holder that does not
inspect (one started before this build) inspects in its place and reaps nothing (DN-006: the lease and its
session belong to the holder).
"""
from __future__ import annotations

import fcntl
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import click

from seldon import models
from seldon.config import get_current_session, load_project_config, resolve_cli_actor
from seldon.core import dispatch as D
from seldon.core import stations as S
from seldon.core.events import append_event, make_event, read_events
from seldon.commands.dispatch import ACTOR, dispatch_group, _now

#: The lease body's field naming a holder that inspects while it waits. Absent on a holder from before QC-002.
LEASE_STATIONS_FIELD = "stations"
LEASE_STATIONS_VERSION = 1
#: The inspection guard, beside the lease: two inspectors (the holder's loop and a pass) never interleave.
STATIONS_LOCK = "stations.lock"
#: Where a pass leaves its last premise review, for `seldon dispatch status --json`. Local state, gitignored
#: with the lease: the record is the `dispatch_launched` or `dispatch_refused` event.
PREMISE_REVIEW_FILE = "premise_review.json"
EVENT_STATION_ERROR = "station_error"


def _emit(project_dir: Path, event_type: str, payload: dict, actor: str = ACTOR, session_id=None) -> dict:
    ev = make_event(event_type=event_type, actor=actor, authority="accepted", payload=payload,
                    session_id=session_id)
    append_event(project_dir, ev)
    return ev


def _scfg(cfg: dict) -> dict:
    return S.load_stations_config(cfg)


def _lease_dir(project_dir: Path, cfg: dict) -> Path:
    return (Path(project_dir) / cfg["lease_file"]).parent


# ----------------------------------------------------------------------------------------- dispatcher side

def inspect_in_flight(project_dir: Path, cfg: dict, task_id: str, holder: bool, now: datetime | None = None,
                      run=S.run_check) -> dict:
    """One inspection of `task_id` under the stations lock. Returns `stations.inspect`'s result, or
    `{"skipped": ...}` when another inspector holds the lock. Every record the inspection writes is appended to
    `events` as well as the store, so the reap reads what was just written."""
    lock_path = _lease_dir(project_dir, cfg) / STATIONS_LOCK
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as fh:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"task_id": task_id, "skipped": "another inspector holds the stations lock", "reap": None}
        try:
            events = read_events(project_dir)
            launch = S.last_launch(events, task_id)
            role = (((launch or {}).get("payload") or {}).get("model") or {}).get("role") or "primary"
            out = S.inspect(
                project_dir, task_id, events, _scfg(cfg), cfg["poll_interval_s"],
                emit=lambda kind, payload: _emit(project_dir, kind, payload),
                run=run, judge=lambda: models.resolve_judge(models.CHECKER_ROLE, role),
                disk=lambda: D.disk_state(project_dir, cfg, worktree=False), now=now)
            out["holder"] = holder
            return out
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def holder_inspector(project_dir: Path, cfg: dict, task_id: str):
    """The callback `_run` calls every `poll_interval_s` while it waits on the session it launched."""
    def inspect_once() -> dict:
        try:
            return inspect_in_flight(project_dir, cfg, task_id, holder=True)
        except Exception as exc:                                    # noqa: BLE001 - recorded, the wait goes on
            _emit(project_dir, EVENT_STATION_ERROR, {"task_id": task_id, "error": f"{type(exc).__name__}: {exc}"})
            return {"task_id": task_id, "error": str(exc), "reap": None}
    return inspect_once


def record_reap(project_dir: Path, task_id: str, reap: dict, pid: int, signal_name: str) -> None:
    _emit(project_dir, S.EVENT_ANDON_REAPED, {"task_id": task_id, "stop_event_id": reap["stop_event_id"],
                                             "reason": reap["reason"], "pid": pid, "signal": signal_name,
                                             "waited_s": reap["age_s"], "reap_after_s": reap["wait_s"],
                                             # DISP-001R Part B step 3: the liveness reading the reap acted on.
                                             "last_log_growth_s": reap.get("last_log_growth_s")})


def inspect_for_held_lease(project_dir: Path, cfg: dict, body: dict) -> dict | None:
    """A pass that found the lease held: inspect the task in flight when its holder does not (QC-002 dogfood: the
    session that built the stations was launched by a dispatcher process that predates them)."""
    task_id = (body or {}).get("task")
    if not task_id or (body or {}).get(LEASE_STATIONS_FIELD):
        return None
    return inspect_in_flight(project_dir, cfg, task_id, holder=False)


def premise_review(project_dir: Path, config: dict, cfg: dict, row: dict, run=S.run_check,
                   lease_held=None) -> dict:
    """Station (a) for one chosen task: the dispatcher's environment premise, then the task's own premises."""
    scfg = _scfg(cfg)
    lease_held = lease_held or _sibling_lease
    env = S.environment_premise(project_dir, config, scfg, lease_held)
    text = (Path(project_dir) / row["source_file"]).read_text(encoding="utf-8", errors="surrogateescape")
    own = S.review_premises(project_dir, text, scfg, run=run) if env["outcome"] == "true" else \
        {"declared": None, "premises": [], "false": [], "judgment": [], "ok": True, "skipped": "environment_in_flight"}
    review = {"task_id": row["task_id"], "source_file": row["source_file"], "at": _now(), "environment": env,
              **own, "ok": env["outcome"] == "true" and own["ok"]}
    path = _lease_dir(project_dir, cfg) / PREMISE_REVIEW_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(review, indent=1, default=str) + "\n", encoding="utf-8")
    return review


def last_premise_review(project_dir: Path, cfg: dict) -> dict | None:
    path = _lease_dir(project_dir, cfg) / PREMISE_REVIEW_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def _sibling_lease(repo: Path) -> dict | None:
    """The lease body of `repo`'s dispatcher when its holder is alive, else None. A repository with no dispatch
    block has no dispatcher and holds nothing."""
    try:
        cfg = D.load_dispatch_config(repo)
    except (FileNotFoundError, D.DispatchConfigError):
        return None
    if not D.lease_is_held(repo, cfg):
        return None
    return D.read_lease(repo / cfg["lease_file"])


def premise_holds(events: list, issue_state) -> dict:
    """`{task_id: {issue_id, issue_state, premises}}` for tasks whose last `premise_false` refusal filed an Issue that
    is still open: c13 refuses them until the Issue is resolved (AD-037-R6 a: "a false premise blocks the task
    with an Issue naming it"). `issue_state(id)` reads the Issue's state from the graph."""
    last = {}
    for e in events:
        p = e.get("payload") or {}
        if e.get("event_type") == D.EVENT_REFUSED and p.get("reason") == S.REFUSED_PREMISE_FALSE and p.get("task_id"):
            last[p["task_id"]] = p
        elif e.get("event_type") == D.EVENT_LAUNCHED and p.get("task_id"):
            last.pop(p["task_id"], None)
    out = {}
    for tid, p in last.items():
        state = issue_state(p.get("issue_id")) if p.get("issue_id") else None
        if state in S.ISSUE_OPEN_STATES:
            out[tid] = {"issue_id": p.get("issue_id"), "issue_state": state,
                        "premises": [f.get("statement") for f in p.get("false") or []]}
    return out


# ----------------------------------------------------------------------------------------- the session's side

def _session_task(project_dir: Path, events: list, task: str | None) -> dict:
    """This session's launch: by `--task` (an id, an id prefix of at least 8, or the task file's stem), else by
    `SELDON_SESSION_ID`, which the dispatcher sets to the child session id it records on `dispatch_launched`."""
    launches = [e for e in events if e.get("event_type") == D.EVENT_LAUNCHED]
    if task:
        hits = [e for e in launches if (e["payload"].get("task_id") or "").startswith(task) and len(task) >= 8
                or Path(e["payload"].get("source_file") or "").stem == task]
    else:
        sid = os.environ.get("SELDON_SESSION_ID") or get_current_session(project_dir)
        hits = [e for e in launches if e["payload"].get("child_session_id") == sid]
    if not hits:
        raise click.ClickException(
            f"no dispatch_launched names {'task ' + task if task else 'this session (SELDON_SESSION_ID)'}; "
            f"pass --task <id or stem>")
    return hits[-1]


def _halt_if_stopped(project_dir: Path, events: list, task_id: str, since: str, where: str) -> None:
    stop = S.pending_stop(S.task_records(events, task_id, since))
    if stop is None:
        return
    p = stop.get("payload") or {}
    _emit(project_dir, S.EVENT_ANDON_HALTED, {"task_id": task_id, "stop_event_id": stop["event_id"],
                                             "at": where, "stop_reason": p.get("reason"), "stop_kind": p.get("kind")},
          actor=resolve_cli_actor())
    click.echo(f"HALT: a {p.get('kind')} stop is written for {task_id[:8]} by {p.get('station') or p.get('by')} "
               f"({p.get('reason')}). `andon_halted` recorded at {where}. Write the RESULT with what stands and end "
               f"the session.", err=True)
    raise SystemExit(S.HALT_EXIT)


def _session_tree(cwd: Path) -> dict:
    """`{primary, cwd, branch}` for a session standing in `cwd` (AD-038-R4).

    `cwd` is the top of the checkout the session works in; `primary` is the checkout whose event store the
    dispatcher reads: the parent of git's common directory, which is `cwd` itself unless `cwd` is a linked
    worktree. Outside a git checkout all three fall back to `cwd` and no branch.
    """
    top = D.git(cwd, "rev-parse", "--show-toplevel")
    if top.returncode != 0:
        return {"primary": cwd, "cwd": cwd, "branch": None}
    tree = Path(top.stdout.strip())
    common = D.git(tree, "rev-parse", "--path-format=absolute", "--git-common-dir")
    primary = Path(common.stdout.strip()).parent if common.returncode == 0 else tree
    branch = D.git(tree, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() or None
    return {"primary": primary, "cwd": tree, "branch": branch}


@dispatch_group.command("part-complete")
@click.option("--part", required=True, help="the Part just finished, as named in the task's **Parts:** header")
@click.option("--task", default=None, help="task id or stem; default: this session's launch")
def part_complete_command(part, task):
    """Station (c), the session's side: record a Part boundary, then halt if a stop is written.

    Appends `part_complete` with the Part's planned share, tokens used so far (from the dispatch log's stream-json
    usage: input plus cache writes plus output) and wall time since launch, and prints the tokens.

    AD-038-R4: the record carries the session's checkout (`cwd`) and `branch`, and the station runs the Part's
    checks there. Run from a linked worktree, the record is written to the PRIMARY checkout's event store, where
    the dispatcher reads it (Issue 02d52bc4: checks ran in main while the work sat on a worktree branch)."""
    here = _session_tree(Path.cwd())
    project_dir = here["primary"]
    events = read_events(project_dir)
    launch = _session_task(project_dir, events, task)
    lp = launch["payload"]
    task_id = lp["task_id"]
    text = (project_dir / lp["source_file"]).read_text(encoding="utf-8", errors="surrogateescape")
    parts = S.parse_parts(text)
    shares = {p["name"]: p["share"] for p in parts["parts"]}
    if part not in shares:
        raise click.ClickException(f"Part {part!r} is not in the task's **Parts:** header "
                                   f"({parts['error'] or sorted(shares)})")
    used = S.session_tokens(project_dir / lp["log_path"]) if lp.get("log_path") else {"tokens": None}
    launched = datetime.fromisoformat(lp.get("launched_at", launch["timestamp"]).replace("Z", "+00:00"))
    wall = round((datetime.now(timezone.utc) - launched).total_seconds(), 1)
    _emit(project_dir, S.EVENT_PART_COMPLETE,
          {"task_id": task_id, "part": part, "planned_share": shares[part], "tokens": used.get("tokens"),
           "cache_read": used.get("cache_read"), "token_source": lp.get("log_path"), "wall_clock_s": wall,
           "cwd": str(here["cwd"]), "branch": here["branch"]},
          actor=resolve_cli_actor())
    click.echo(f"part_complete {task_id[:8]} Part {part}: planned share {shares[part]}, tokens so far "
               f"{used.get('tokens')}, wall {wall}s; checks run in {here['cwd']} ({here['branch']})")
    _halt_if_stopped(project_dir, read_events(project_dir), task_id, launch["timestamp"], f"Part {part}")


@dispatch_group.command("boundary")
@click.option("--task", default=None, help="task id or stem; default: this session's launch")
@click.option("--at", "where", default="loop boundary", help="where the session is, for the halt record")
def boundary_command(task, where):
    """Station (d), the session's side: exit 0 to continue, or write `andon_halted` and exit 3 if a stop is written.
    From a linked worktree the stops are read from the primary checkout's store (AD-038-R4)."""
    project_dir = _session_tree(Path.cwd())["primary"]
    events = read_events(project_dir)
    launch = _session_task(project_dir, events, task)
    _halt_if_stopped(project_dir, events, launch["payload"]["task_id"], launch["timestamp"], where)
    click.echo("continue: no stop written")


@dispatch_group.command("first-article")
@click.option("--loop", "loop", required=True, help="the loop's name as the task's **First article:** line gives it")
@click.option("--output", required=True, help="path of the first unit's output")
@click.option("--task", default=None, help="task id or stem; default: this session's launch")
@click.option("--wait/--no-wait", default=True, help="wait on the dispatcher's verdict (default) or only record")
@click.option("--poll-s", type=float, default=None, help="seconds between reads; default dispatch.poll_interval_s")
def first_article_command(loop, output, task, wait, poll_s):
    """Station (b), the session's side: record the first unit, then wait on the record, not on a person.

    A `first_article_pass` continues the loop (exit 0); a stop ends it (exit 3, `andon_halted` written); nothing
    within `first_article_polls` polls opens a huddle with its reading and halts (exit 3)."""
    here = _session_tree(Path.cwd())
    project_dir = here["primary"]
    cfg = D.load_dispatch_config(project_dir)
    scfg = _scfg(cfg)
    events = read_events(project_dir)
    launch = _session_task(project_dir, events, task)
    task_id = launch["payload"]["task_id"]
    ev = _emit(project_dir, S.EVENT_FIRST_ARTICLE, {"task_id": task_id, "loop": loop, "output": output,
                                                    "cwd": str(here["cwd"]), "branch": here["branch"]},
               actor=resolve_cli_actor())
    click.echo(f"first_article {task_id[:8]} loop {loop!r}: {output}")
    if not wait:
        return
    poll = poll_s if poll_s is not None else cfg["poll_interval_s"]
    for _ in range(scfg["first_article_polls"]):
        time.sleep(poll)
        events = read_events(project_dir)
        recs = S.task_records(events, task_id, launch["timestamp"])
        if any(e.get("event_type") == S.EVENT_FIRST_ARTICLE_PASS and e["payload"].get("answers") == ev["event_id"]
               for e in recs):
            click.echo("first_article_pass: continue the loop")
            return
        _halt_if_stopped(project_dir, events, task_id, launch["timestamp"], f"first article of {loop}")
    h = S.huddle_payload(task_id, f"no first-article verdict within {scfg['first_article_polls']} polls of {poll}s "
                                  f"for loop {loop!r}", "first_article_wait", loop=loop, answers=ev["event_id"])
    _emit(project_dir, S.EVENT_HUDDLE, h, actor=resolve_cli_actor())
    _emit(project_dir, S.EVENT_SESSION_STOP, {"task_id": task_id, "station": "first_article", "kind": "line",
                                                     "reason": "first_article_unanswered", "by": "session",
                                                     "huddle_id": h["huddle_id"]}, actor=resolve_cli_actor())
    _halt_if_stopped(project_dir, read_events(project_dir), task_id, launch["timestamp"], f"first article of {loop}")


@dispatch_group.command("stop")
@click.argument("task")
@click.option("--reason", required=True, help="the out-of-spec reading, in words")
@click.option("--hard", is_flag=True,
              help="a hard stop (FC-32's toxic tier): reaped by the lease holder if the session has not halted "
                   "within the reap interval")
def stop_command(task, reason, hard):
    """The andon (FC-28): write a stop for TASK (id, 8+ character prefix, or stem). The session halts at its next
    Part or loop boundary; nothing is killed by hand."""
    project_dir = Path.cwd()
    events = read_events(project_dir)
    launch = _session_task(project_dir, events, task)
    task_id = launch["payload"]["task_id"]
    ev = _emit(project_dir, S.EVENT_SESSION_STOP,
               {"task_id": task_id, "station": "operator", "kind": "hard" if hard else "andon", "reason": reason,
                "by": resolve_cli_actor()}, actor=resolve_cli_actor())
    click.echo(f"session_stop {ev['event_id'][:8]} for {task_id[:8]} ({'hard' if hard else 'andon'}): {reason}")


@dispatch_group.command("huddle")
@click.argument("task")
@click.option("--reading", default=None, help="the out-of-spec reading")
@click.option("--cause", default=None, help="the cause, one level down")
@click.option("--gate", default=None, help="the gate that now prevents it")
@click.option("--id", "huddle_id", default=None, help="fill and close an open huddle (8+ character prefix)")
def huddle_command(task, reading, cause, gate, huddle_id):
    """FC-29's huddle record for TASK: the reading, the cause one level down, the gate. With `--id`, an open
    huddle (one a station opened with its reading) is closed by naming its cause and gate."""
    project_dir = Path.cwd()
    events = read_events(project_dir)
    actor = resolve_cli_actor()
    if huddle_id:
        if not (cause and gate):
            raise click.ClickException("closing a huddle names both --cause and --gate (FC-29)")
        hits = [h for h in S.open_huddles(events) if h["huddle_id"].startswith(huddle_id)]
        if len(hits) != 1:
            raise click.ClickException(f"{len(hits)} open huddle(s) match {huddle_id!r}")
        _emit(project_dir, S.EVENT_HUDDLE_CLOSED, {"task_id": hits[0].get("task_id"), "huddle_id": hits[0]["huddle_id"],
                                                  "cause": cause, "gate": gate, "by": actor}, actor=actor)
        click.echo(f"huddle {hits[0]['huddle_id'][:8]} closed")
        return
    if not reading:
        raise click.ClickException("a new huddle names its --reading")
    try:
        task_id = _session_task(project_dir, events, task)["payload"]["task_id"]
    except click.ClickException:
        task_id = task
    h = S.huddle_payload(task_id, reading, actor, cause=cause, gate=gate)
    _emit(project_dir, S.EVENT_HUDDLE, h, actor=actor)
    state = "closed" if (cause and gate) else "open: close with --id and --cause/--gate"
    click.echo(f"huddle {h['huddle_id'][:8]} for {str(task_id)[:8]} ({state})")


@dispatch_group.command("inspect")
@click.argument("task", required=False)
def inspect_command(task):
    """Run one inspection of TASK (default: the task the lease names) now, as the dispatcher's pass does. Writes
    the records it finds due; reaps nothing."""
    project_dir = Path.cwd()
    config = load_project_config()
    cfg = D.load_dispatch_config(project_dir, config)
    if task:
        task_id = _session_task(project_dir, read_events(project_dir), task)["payload"]["task_id"]
    else:
        task_id = (D.read_lease(project_dir / cfg["lease_file"]) or {}).get("task")
        if not task_id:
            raise click.ClickException("no task in flight; name one")
    out = inspect_in_flight(project_dir, cfg, task_id, holder=False)
    click.echo(json.dumps(out, indent=1, default=str))


# ------------------------------------------------------------------------------------ the session's hooks

def _hook_input() -> dict:
    """The hook's JSON on stdin (Claude Code hooks: `session_id`, `cwd`, `hook_event_name`, ...). An unreadable
    input is an error, never an empty dict: a gate that read nothing would wave the session through."""
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"hook input is not JSON: {exc}") from exc


def _hook_launch(project_dir: Path, events: list) -> dict | None:
    """The `dispatch_launched` whose child session id is this process's `SELDON_SESSION_ID`, which the dispatcher
    set for the session and the CLI passes to its hooks; None for a session the dispatcher did not launch."""
    return S.launch_for_session(events, os.environ.get("SELDON_SESSION_ID"))


@dispatch_group.command("stop-gate", hidden=True)
@click.option("--project", "project", required=True, type=click.Path(exists=True, file_okay=False),
              help="the primary checkout, whose event store the dispatcher reads")
def stop_gate_command(project):
    """FRICTION-002 Part C: the Stop hook each dispatched session is launched with. Not for operators.

    Runs the `check:` criteria of every Part the session declared complete, in the session's tree, and records
    `stop_gate`. While a check fails and the session is under its token ceiling it prints the CLI's block decision
    (`{"decision": "block", "reason": ...}`), so the session keeps working; at the ceiling it lets the session end
    and writes a hard stop. A session the dispatcher did not launch ends untouched."""
    hook = _hook_input()
    project_dir = Path(project).resolve()
    events = read_events(project_dir)
    launch = _hook_launch(project_dir, events)
    if launch is None:
        return
    cwd = Path(hook.get("cwd") or os.getcwd())
    tree = _session_tree(cwd)
    cfg = D.load_dispatch_config(project_dir)
    scfg = _scfg(cfg)
    floor = S.spend_floor(project_dir, events, cfg["poll_interval_s"], scfg["floor_launches"],
                          exclude_session=launch["payload"].get("child_session_id"))
    out = S.stop_gate(project_dir, launch, events, scfg, tree["cwd"], tree["branch"],
                      stop_hook_active=bool(hook.get("stop_hook_active")), floor=floor)
    gate = _emit(project_dir, S.EVENT_STOP_GATE, out["record"], actor=resolve_cli_actor())
    if out["hard_stop"]:
        stop = _emit(project_dir, S.EVENT_SESSION_STOP, {**out["hard_stop"], "stop_gate_event_id": gate["event_id"]})
        # The session is about to end at the gate's word, which is the halt the stop asks for; recorded so the
        # holder does not reap a process that is already ending.
        _emit(project_dir, S.EVENT_ANDON_HALTED, {"task_id": out["record"]["task_id"],
                                                 "stop_event_id": stop["event_id"], "at": "stop gate",
                                                 "stop_reason": "spend_ceiling", "stop_kind": "hard"},
              actor=resolve_cli_actor())
    if out["block"]:
        click.echo(json.dumps({"decision": "block", "reason": out["reason"]}))


#: The event types the PreToolUse gate reads. It runs before EVERY tool call of every dispatched session, so it
#: parses only the lines that can carry one of these rather than the whole event store (16 MB in seldon today).
TOOL_GATE_EVENTS = (D.EVENT_LAUNCHED, S.EVENT_SESSION_STOP, S.EVENT_ANDON_HALTED, S.EVENT_ANDON_REAPED)


def _tool_gate_events(project_dir: Path) -> list:
    from seldon.core.events import _events_path

    path = _events_path(project_dir)
    if not path.is_file():
        return []
    marks = tuple(f'"{t}"' for t in TOOL_GATE_EVENTS)
    out = []
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if any(m in line for m in marks):
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if e.get("event_type") in TOOL_GATE_EVENTS:
                    out.append(e)
    return out


@dispatch_group.command("tool-gate", hidden=True)
@click.option("--project", "project", required=True, type=click.Path(exists=True, file_okay=False),
              help="the primary checkout, whose event store the dispatcher reads")
def tool_gate_command(project):
    """DISP-001R Part B step 2: the PreToolUse hook each dispatched session is launched with. Not for operators.

    A hard stop on the ledger for this session's task, not yet answered, is delivered here: the tool call is
    refused with the stop's reason (the CLI's `permissionDecision: deny`, whose reason the model reads), and the
    session records `andon_halted` itself, so it halts at a tool boundary instead of being killed inside a call.
    Every other call, and every call of a session the dispatcher did not launch, proceeds untouched."""
    hook = _hook_input()
    project_dir = Path(project).resolve()
    events = _tool_gate_events(project_dir)
    launch = _hook_launch(project_dir, events)
    if launch is None:
        return
    task_id = launch["payload"]["task_id"]
    stop = S.pending_hard_stop(S.task_records(events, task_id, S._ts(launch)))
    if stop is None:
        return
    p = stop.get("payload") or {}
    _emit(project_dir, S.EVENT_ANDON_HALTED, {"task_id": task_id, "stop_event_id": stop["event_id"],
                                             "at": "tool boundary", "tool_name": hook.get("tool_name"),
                                             "stop_reason": p.get("reason"), "stop_kind": p.get("kind")},
          actor=resolve_cli_actor())
    reason = (f"HALT: a hard stop is written for task {task_id[:8]} by {p.get('station') or p.get('by')} "
              f"({p.get('reason')}; reading {json.dumps(p.get('reading'), default=str)[:400]}). This tool call is "
              f"refused and `andon_halted` is recorded. Write the RESULT with what stands, commit it on this "
              f"branch, and end the session.")
    click.echo(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                  "permissionDecisionReason": reason}}))


@dispatch_group.command("classifier-denied", hidden=True)
@click.option("--project", "project", required=True, type=click.Path(exists=True, file_okay=False),
              help="the primary checkout, whose event store the dispatcher reads")
def classifier_denied_command(project):
    """FRICTION-002 Part D: the PermissionDenied hook each dispatched session is launched with. Not for operators.

    The CLI runs it after its auto-mode classifier denies a tool call, with `tool_name`, `tool_input`,
    `tool_use_id` and `reason`. It records one `classifier_block` for the launch and prints nothing, so the
    denial stands (the hook may not overrule the classifier)."""
    hook = _hook_input()
    project_dir = Path(project).resolve()
    launch = _hook_launch(project_dir, read_events(project_dir))
    if launch is None:
        return
    lp = launch["payload"]
    _emit(project_dir, S.EVENT_CLASSIFIER_BLOCK,
          {"task_id": lp["task_id"], "child_session_id": lp.get("child_session_id"),
           "tool_name": hook.get("tool_name"), "tool_use_id": hook.get("tool_use_id"),
           "reason": hook.get("reason"),
           "tool_input": json.dumps(hook.get("tool_input"), sort_keys=True, default=str)[:S.CLASSIFIER_INPUT_CHARS]},
          actor=resolve_cli_actor())
