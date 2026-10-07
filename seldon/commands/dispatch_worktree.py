"""The parallel dispatcher: each task in its own git worktree, merged on green.

`cc_tasks/2026-10-07_SEL-004_worktree_per_task_dispatch.md`, recorded as AD-034
(`docs/design/AD-034_worktree_per_task_dispatch.md`). Reached only when
`dispatch.max_parallel > 1`; at the default of 1 `seldon.commands.dispatch._pass` is the pass,
unchanged.

**Shape.** A pass (`seldon dispatch once`, under the pass lease, seconds long) evaluates the
queue, plans which tasks may run beside the ones already running (`D.plan_launches`, from the
declared `Exclusive`/`Touches` headers, never from `precedes`), and for each non-exclusive
launch claims the task, creates `<worktree_dir>/<stem>` on branch `<branch_prefix><stem>`
from main, and starts a detached SUPERVISOR. The supervisor (`seldon dispatch supervise`,
hidden) holds that worktree's own lease for the task's whole life, runs the session in the
worktree, and at the end merges on green: rebase onto main, re-gate if main changed a file the
task changed, check the union-merged append-only files, then take the pass lease, check main
has not moved, fast-forward, complete the task, record, push, and remove the worktree. A
conflict, a red re-gate or a malformed union file is `merge_blocked`: the task is blocked, an
Issue names the files, the worktree stays, the operator is notified, and nothing is resolved.

An EXCLUSIVE task (the default, and every task with neither header) runs as every task did
before: alone, in the primary checkout, with the pass lease held for its whole run
(`dispatch._launch_inplace`). It waits until no worktree task is running, and while it waits
no new task starts (writer preference, `D.plan_launches`).

**One pass lease, two holders.** Every write to main in the primary checkout (record commits,
registration commits, shared-ledger commits, a fast-forward) happens under the pass lease,
taken either by a pass or by a finishing supervisor that waits for it. A per-worktree lease
guards only its worktree. Prior art: the merge queue (bors, 2014; GitHub merge queue), for
"main only moves to a commit tested as it will land"; Kubernetes `Lease` and Chubby for a
lease with an identified holder qualified by liveness, never by age (DD-022).
"""
from __future__ import annotations

import json
import os
import shlex
import signal
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

import click

import seldon
from seldon.commands import dispatch as S
from seldon.core import dispatch as D
from seldon.core import worktree as WT
from seldon.core.artifacts import create_artifact, create_link, update_artifact, walk_to_completed

#: Appended to the CC dispatch line for a worktree session. The protocol's own sentence stays
#: verbatim (`S.DISPATCH_LINE`); this says what differs when the session is not alone. It is
#: protocol text, not a tunable, as `HEADLESS_CLAUSE` is.
WORKTREE_CLAUSE = (
    "This session runs in a git worktree at {worktree} on branch {branch}, not in the primary "
    "checkout at {primary}; other tasks run beside it in their own worktrees. Do all work and "
    "testing here and commit everything on this branch, including the RESULT. Do not merge, "
    "push, switch branches, or run `seldon cc complete` for this task: the dispatcher rebases "
    "onto main, re-runs the gate if main changed a file this task changed, merges on green "
    "and completes the task. Gitignored files are not in this worktree; the primary "
    "checkout's path is in $" + WT.PRIMARY_CHECKOUT_ENV + "."
)

#: The per-worktree lease's persistent fields (`D.Lease.extra`): what a released or orphaned
#: lease still has to say about which task, worktree and branch it guarded.
LEASE_EXTRA_KEYS = ("worktree_task", "stem", "source_file", "worktree", "branch", "base",
                    "child_session_id", "linked")

#: `dispatch_finished.outcome` values this module writes, beside the serial `ok` boolean.
OUTCOMES = ("merged", "session_failed", "merge_blocked", "worktree_add_failed",
            "launch_failed",
            "holder_gone", "released_unfinished")

#: The ResearchTask property that says what became of a worktree task's branch.
MERGE_PROPERTY = "dispatch_merge"


def worktree_prompt(rel: str, stem: str, worktree: Path, branch: str, primary: Path) -> str:
    return (S.DISPATCH_LINE.format(rel=rel, stem=stem) + " "
            + WORKTREE_CLAUSE.format(worktree=worktree, branch=branch, primary=primary))


# =============================================================================== the pass

def pass_parallel(project_dir, config, driver, database, domain_config, session_id, cfg,
                  lease, dry_run):
    """One pass under `max_parallel > 1`: reap, record, plan, launch. Holds the pass lease.

    The order is the serial pass's (own lines, registrations, cadence, then candidacy) with
    two steps added in front: a worktree task whose supervisor is gone is marked (decision 7),
    and a shared append-only file is committed (decision 5). The gates that ask "is a session
    working in this checkout" ask it of the in-place claim only, because worktree sessions do
    not work here.
    """
    band = D.resolve_standing_band(project_dir, cfg["standing_band_ref"])
    running, inplace = _classify(project_dir, cfg, S._claims_in_flight(driver, database))
    if not dry_run:
        running = _reap_stale(project_dir, driver, database, domain_config, session_id, cfg,
                              running)
    inplace_claim = inplace[0] if inplace else None
    if inplace_claim is None and not dry_run:
        S._record_own_lines(project_dir, config, cfg)
        _commit_shared(project_dir, cfg)
    exclude = cfg["shared_paths"]
    tree = D.tree_state(project_dir, exclude)
    tasks = S._tasks(driver, database)
    if S._commit_registered(project_dir, config, cfg, tasks, tree, inplace_claim, dry_run):
        tree = D.tree_state(project_dir, exclude)
    if cfg.get("cadence"):
        S._cadence(project_dir, config, driver, database, domain_config, session_id, cfg, tree,
                   inplace_claim, dry_run)
        tree = D.tree_state(project_dir, exclude)
    lease_body = D.read_lease(project_dir / cfg["lease_file"])
    ids = [r["task_id"] for r in running]
    rows = D.fifo([D.evaluate(project_dir, t, cfg, band, tree, inplace_claim, lease_body,
                              running=ids) for t in S._tasks(driver, database)])
    S._stuck(project_dir, session_id, cfg, rows, tree, inplace_claim, dry_run)

    ready = [r for r in rows if r["eligible"]]
    plan = D.plan_launches(
        [{"task_id": r["task_id"], "concurrency": r["concurrency"]} for r in ready],
        [{"task_id": r["task_id"], "concurrency": r["concurrency"]} for r in running],
        cfg["max_parallel"], cfg["resources"])
    _apply_plan(ready, plan)
    chosen = [r for r in ready if r["eligible"]]

    if not chosen:
        click.echo(f"nothing launched ({len(rows)} open, "
                   f"{sum(1 for r in rows if r['candidate'])} candidate(s), "
                   f"{len(running)} running)")
        S._echo_refusals(rows, tree)
    # A wait is not a refusal and writes no event (DN-006 decision 7: it is a standing
    # condition, and `status` computes it live); it is printed whether or not something else
    # launched, so the wrapper's log says why a task did not start beside the others.
    for r in ready:
        why = plan["deferred"].get(r["task_id"])
        if why:
            click.echo(f"  {r['task_id'][:8]} waits ({why['reason']}) on "
                       f"{', '.join(str(w)[:8] for w in why['with'])}"
                       + (f": {', '.join(why['overlap'])}" if why["overlap"] else "")
                       + f"  {r['source_file']}")
    if not chosen:
        if not dry_run and inplace_claim is None:
            S._push(project_dir, cfg)
        return
    if dry_run:
        click.echo(json.dumps({"would_launch": [r["task_id"] for r in chosen],
                               "running": ids, "deferred": plan["deferred"]},
                              indent=1, default=str))
        return
    for r in chosen:
        if r["concurrency"]["exclusive"]:
            # `plan_launches` launches an exclusive task only when nothing runs, and alone.
            S._launch_inplace(project_dir, config, driver, database, domain_config,
                              session_id, cfg, lease, r)
        else:
            _launch_worktree(project_dir, config, driver, database, domain_config, session_id,
                             cfg, r)


def survey(project_dir, cfg, driver, database, band, lease_body) -> dict:
    """What `status` shows under `max_parallel > 1`: the pass's evaluation and plan, with no
    write, no reap and no launch. A dead supervisor is shown, not marked; marking is a pass's."""
    running, inplace = _classify(project_dir, cfg, S._claims_in_flight(driver, database))
    claim = inplace[0] if inplace else None
    tree = D.tree_state(project_dir, cfg["shared_paths"])
    ids = [r["task_id"] for r in running]
    rows = D.fifo([D.evaluate(project_dir, t, cfg, band, tree, claim, lease_body, running=ids)
                   for t in S._tasks(driver, database)])
    ready = [r for r in rows if r["eligible"]]
    plan = D.plan_launches(
        [{"task_id": r["task_id"], "concurrency": r["concurrency"]} for r in ready],
        [{"task_id": r["task_id"], "concurrency": r["concurrency"]} for r in running],
        cfg["max_parallel"], cfg["resources"])
    _apply_plan(ready, plan)
    return {"tree": tree, "claim": claim, "rows": rows, "running": running, "plan": plan}


def _apply_plan(ready: list, plan: dict) -> None:
    """Write each deferral into its row's c6, so a wait is a recorded value (decision 2)."""
    for r in ready:
        why = plan["deferred"].get(r["task_id"])
        if why:
            r["criteria"]["c6"].update({"ok": False, "deferred": why})
            r["eligible"] = False
            r["failed"] = list(r["failed"]) + ["c6"]


def _declared(project_dir: Path, cfg: dict, source_file: str | None) -> dict:
    """A running task's declaration, re-read from its file on main. An unreadable one holds
    everything: the failure direction of a lock is waiting, never sharing."""
    path = project_dir / source_file if source_file else None
    if path is None or not path.is_file():
        return D.parse_concurrency(None, None, {})
    raw = D.parse_concurrency_headers(path.read_text(encoding="utf-8", errors="surrogateescape"))
    conc = D.parse_concurrency(raw[D.HEADER_EXCLUSIVE], raw[D.HEADER_TOUCHES],
                               cfg.get("resources") or {})
    return conc if conc["error"] is None else {**conc, "exclusive": True}


def _classify(project_dir: Path, cfg: dict, claims: list) -> tuple:
    """Split dispatcher claims into worktree tasks (a per-worktree lease names the task) and
    in-place ones (an exclusive task, or a claim whose pass died before it wrote a lease)."""
    running, inplace = [], []
    for c in claims:
        src = c.get("source_file")
        stem = Path(src).stem if src else None
        body = D.read_lease(D.worktree_lease_path(project_dir, cfg, stem)) if stem else {}
        if stem and body.get("worktree_task") == c["artifact_id"]:
            running.append({"task_id": c["artifact_id"], "name": c.get("name"), "stem": stem,
                            "source_file": src, "lease": body,
                            "concurrency": _declared(project_dir, cfg, src)})
        else:
            inplace.append(c)
    return running, inplace


def _reap_stale(project_dir, driver, database, domain_config, session_id, cfg,
                running) -> list:
    """Decision 7: a worktree task whose supervisor is gone is blocked; worktree and lease stay.

    Qualified by PID liveness and never by age (DD-022, DN-006 §5). A supervisor killed with
    its session leaves a lease naming a dead PID: the task moves to `blocked` the way any
    finish that was not ok does (DN-006 decision 4), one `dispatch_finished` says why, the
    operator is notified, and the worktree is kept for inspection. The lease FILE is kept too:
    releasing it is `seldon dispatch lease reap --task <stem>`, which refuses a live holder,
    so the one release path stays the operator's. A lease released without a finish (a
    supervisor that could not get the pass lease) is the same case.

    Returns the running tasks whose supervisors are alive.
    """
    live = []
    for r in running:
        body = r["lease"]
        path = D.worktree_lease_path(project_dir, cfg, r["stem"])
        if D.worktree_holder_alive(path, body):
            live.append(r)
            continue
        outcome = "holder_gone" if body.get("holder") is not None else "released_unfinished"
        killed = _terminate_orphaned_session(body)
        log_rel = f"{cfg['log_dir']}/{r['stem']}.log"
        finish = {"task_id": r["task_id"], "source_file": r["source_file"],
                  "child_session_id": body.get("child_session_id"),
                  "exit_code": None, "wall_clock_s": None, "result_present": False,
                  "result_path": f"cc_tasks/{r['stem']}_RESULT.md",
                  "graph_state_observed": "in_progress", "ok": False, "outcome": outcome,
                  "log_path": log_rel, "mode": "worktree", "worktree": body.get("worktree"),
                  "branch": body.get("branch"),
                  "lease_path": str(D.worktree_lease_path(project_dir, cfg, r["stem"])
                                    .relative_to(project_dir)),
                  "holder": body.get("holder") or body.get("last_holder"),
                  "orphaned_session_terminated": killed}
        S._emit(project_dir, session_id, D.EVENT_FINISHED, finish)
        S._block(project_dir, driver, database, domain_config, session_id, r["task_id"],
                 "in_progress", None, log_rel)
        click.echo(f"STALE: {r['task_id'][:8]} {r['stem']}: supervisor {finish['holder']} is "
                   f"gone ({outcome}); blocked; worktree {body.get('worktree')} and lease kept "
                   f"(`seldon dispatch lease reap --task {r['stem']}`)", err=True)
        S._notify(project_dir, session_id, cfg, {**finish, "wall_clock_s": 0},
                  r.get("name") or r["stem"], outcome=outcome)
    return live


def _terminate_orphaned_session(body: dict) -> bool:
    """SIGTERM the process group of a supervisor that died under its session.

    The session runs in the supervisor's group (the supervisor is started with `setsid` and
    runs `claude` without a new session), so a supervisor killed alone leaves a session that
    nothing will merge, still writing to the kept worktree and still spending. Only a group a
    supervisor recorded is signalled, only once its flock is gone, and never this process's
    own group. Returns whether a signal was delivered.
    """
    pgid = body.get("pgid")
    if not body.get("supervising") or not isinstance(pgid, int) or pgid == os.getpgrp():
        return False
    try:
        os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return False
    return True


def _commit_shared(project_dir: Path, cfg: dict) -> None:
    """Decision 5: commit the lines worktree sessions appended to a shared file in the primary.

    A spend ledger resolved to the primary checkout is ONE file across worktrees, appended
    under its own flock (`WT.locked`, the discipline the ledger's writer already uses). Its
    appended lines are committed here, under that same flock so no append lands half-staged,
    and only when the file is append-only against HEAD; an in-place edit is reported and left.
    """
    if D.tree_state(project_dir)["branch"] != cfg["branch"]:
        return
    for rel in cfg["shared_paths"]:
        path = project_dir / rel
        if not path.is_file() or not D.is_tracked(project_dir, path):
            continue
        with WT.locked(path):
            head = WT.show(project_dir, "HEAD", rel)
            work = path.read_bytes()
            if head is None or work == head:
                continue
            if not work.startswith(head):
                click.echo(f"shared: {rel} NOT committed: not append-only against HEAD",
                           err=True)
                continue
            n = sum(1 for ln in work[len(head):].decode("utf-8", "replace").splitlines()
                    if ln.strip())
            out = D.commit_paths(project_dir, [rel],
                                 f"record: {rel} — {n} line(s) appended by worktree sessions, "
                                 f"committed by the standing dispatcher")
        if out["committed"]:
            click.echo(f"shared: {rel} {n} line(s) -> {out['commit']}")
        else:
            click.echo(f"shared: {rel} NOT committed ({out['reason']}): "
                       f"{out.get('stderr', '')}", err=True)


# ============================================================================== the launch

def _launch_worktree(project_dir, config, driver, database, domain_config, session_id, cfg,
                     chosen) -> None:
    """Claim, record, create the worktree, start its supervisor. Returns at once."""
    rel, tid = chosen["source_file"], chosen["task_id"]
    stem = Path(rel).stem
    wt_rel, branch = chosen["criteria"]["c11"]["worktree"], chosen["criteria"]["c11"]["branch"]
    wt = project_dir / wt_rel
    log_dir = project_dir / cfg["log_dir"]
    log_dir.mkdir(parents=True, exist_ok=True)
    log_rel = str((log_dir / f"{stem}.log").relative_to(project_dir))

    claimed = S._claim(project_dir, driver, database, domain_config, session_id, chosen)
    if not claimed["ok"]:
        S._emit(project_dir, session_id, D.EVENT_REFUSED,
                {"task_id": tid, "reason": "claim_failed", "error": claimed["error"],
                 "from_state": chosen["state"]})
        click.echo(f"claim failed for {tid[:8]}: {claimed['error']}", err=True)
        S._record_and_push(project_dir, config, cfg)
        return
    child_session_id = str(uuid.uuid4())
    try:
        _start_claimed(project_dir, config, driver, database, domain_config, session_id, cfg,
                       chosen, claimed, child_session_id, wt, wt_rel, branch, log_dir, log_rel)
    except Exception as exc:                                        # noqa: BLE001
        # A claim with no lease record reads as an in-place claim, which holds every gate in
        # the primary checkout shut until someone intervenes. Any failure after the claim is
        # therefore finished as one: blocked, recorded, notified, never swallowed.
        error = f"{type(exc).__name__}: {exc}"
        click.echo(f"launch failed for {tid[:8]} after its claim: {error}", err=True)
        _finish_unmerged(project_dir, config, driver, database, domain_config, session_id,
                         cfg, {"task_id": tid, "source_file": rel,
                               "child_session_id": child_session_id, "exit_code": None,
                               "wall_clock_s": 0, "result_present": False,
                               "result_path": f"cc_tasks/{stem}_RESULT.md",
                               "graph_state_observed": "in_progress", "log_path": log_rel,
                               "mode": "worktree", "worktree": wt_rel, "branch": branch,
                               "error": error},
                         chosen.get("name") or stem, "launch_failed")


def _start_claimed(project_dir, config, driver, database, domain_config, session_id, cfg,
                   chosen, claimed, child_session_id, wt, wt_rel, branch, log_dir,
                   log_rel) -> None:
    """Everything after a successful claim: record, cut the worktree, start the supervisor."""
    rel, tid = chosen["source_file"], chosen["task_id"]
    stem = Path(rel).stem
    cmd = S._launch_cmd(cfg, worktree_prompt(rel, stem, wt, branch, project_dir))
    conc = chosen["concurrency"]
    S._emit(project_dir, session_id, D.EVENT_LAUNCHED,
            {"task_id": tid, "source_file": rel, "child_session_id": child_session_id,
             "claimed_by": claimed["claimed_by"], "transitions": claimed["transitions"],
             "criteria": chosen["criteria"], "framework_layer": chosen["framework_layer"],
             "network_allowlist": chosen["criteria"]["c5"]["network_allowlist"],
             "log_path": log_rel, "command": " ".join(shlex.quote(p) for p in cmd),
             "permission_mode": cfg["permission_mode"], "launched_at": S._now(),
             "mode": "worktree", "worktree": wt_rel, "branch": branch,
             "touches": {"resources": conc["resources"], "paths": conc["paths"]}})
    # Committed and pushed BEFORE the worktree is cut, so the task's branch starts from a main
    # that already carries its own claim.
    S._record_and_push(project_dir, config, cfg)
    base = WT.rev(project_dir, "HEAD")
    added = WT.add(project_dir, wt, branch, base)
    if not added["ok"]:
        finish = {"task_id": tid, "source_file": rel, "child_session_id": child_session_id,
                  "exit_code": None,
                  "wall_clock_s": 0, "result_present": False,
                  "result_path": f"cc_tasks/{stem}_RESULT.md",
                  "graph_state_observed": "in_progress", "log_path": log_rel,
                  "mode": "worktree", "worktree": wt_rel, "branch": branch, "base": base,
                  "error": added["stderr"]}
        click.echo(f"worktree add failed for {tid[:8]}: {added['stderr']}", err=True)
        _finish_unmerged(project_dir, config, driver, database, domain_config, session_id,
                         cfg, finish, chosen.get("name") or stem, "worktree_add_failed")
        return
    linked = WT.link(project_dir, wt, cfg["worktree_links"])
    extra = {"worktree_task": tid, "stem": stem, "source_file": rel, "worktree": wt_rel,
             "branch": branch, "base": base, "child_session_id": child_session_id,
             "linked": linked}
    lease_path = D.worktree_lease_path(project_dir, cfg, stem)
    lease_path.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "-m", "seldon", "dispatch", "supervise", tid,
            "--extra", json.dumps(extra)]
    # The supervisor runs THIS code: the package root goes first on its path, so an editable
    # install that points at another checkout cannot substitute different code mid-run.
    pkg_root = str(Path(seldon.__file__).resolve().parent.parent)
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(
        [pkg_root] + [p for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p])}
    with (log_dir / f"{stem}.supervisor.log").open("a", encoding="utf-8") as fh:
        proc = subprocess.Popen(argv, cwd=project_dir, stdin=subprocess.DEVNULL, stdout=fh,
                                stderr=subprocess.STDOUT, env=env, start_new_session=True)
    # The lease record names the supervisor BEFORE this pass releases the pass lease, so the
    # next pass sees a live holder and never a gap. Written in place (same inode), because the
    # supervisor's flock is on this file's inode.
    now = S._now()
    with lease_path.open("a+", encoding="utf-8") as fh:
        fh.seek(0)
        fh.truncate()
        fh.write(json.dumps({"holder": D.holder_id(proc.pid), "pid": proc.pid,
                             "acquired_at": now, "heartbeat_at": now, "task": tid, **extra},
                            indent=1) + "\n")
    click.echo(f"launching {tid[:8]} {rel} in {wt_rel} on {branch} -> {log_rel} "
               f"(supervisor pid {proc.pid})")


# ========================================================================= the supervisor

@S.dispatch_group.command("supervise", hidden=True)
@click.argument("task_id")
@click.option("--extra", "extra_json", required=True,
              help="the per-worktree lease's fields, as JSON, from the launching pass")
def dispatch_supervise(task_id, extra_json):
    """Run one worktree task to its end and merge it on green. Started by a pass; not for
    operators. Holds the worktree's lease for its whole life (SEL-004 decision 2)."""
    project_dir, config, driver, database, domain_config, session_id = S._open_project()
    try:
        cfg = D.load_dispatch_config(project_dir, config)
        extra = {k: v for k, v in json.loads(extra_json).items() if k in LEASE_EXTRA_KEYS}
        if extra.get("worktree_task") != task_id:
            raise click.ClickException(f"--extra names task {extra.get('worktree_task')!r}, "
                                       f"not {task_id!r}")
        lease_path = D.worktree_lease_path(project_dir, cfg, extra["stem"])
        try:
            lease = D.Lease(lease_path, extra=extra).__enter__()
        except D.LeaseHeld as held:
            # Two supervisors for one worktree is the defect the lease exists for.
            raise click.ClickException(f"worktree lease held by {held.body.get('holder')}")
        try:
            lease.heartbeat(task=task_id)
            # From here the flock is the liveness test (`D.worktree_holder_alive`), and the
            # process group is what a pass terminates if this supervisor dies under its session.
            lease.write({**D.read_lease(lease_path), "supervising": True,
                         "pgid": os.getpgrp()})
            _supervise(project_dir, config, driver, database, domain_config, session_id, cfg,
                       task_id, extra)
        finally:
            lease.__exit__(None, None, None)
    finally:
        driver.close()


@contextmanager
def _pass_lease(project_dir: Path, cfg: dict):
    lease = D.acquire_waiting(project_dir / cfg["lease_file"], cfg["merge_lock_timeout_s"])
    try:
        yield lease
    finally:
        lease.__exit__(None, None, None)


def _supervise(project_dir, config, driver, database, domain_config, session_id, cfg,
               task_id, extra) -> None:
    stem, rel, branch = extra["stem"], extra["source_file"], extra["branch"]
    wt = project_dir / extra["worktree"]
    log_path = project_dir / cfg["log_dir"] / f"{stem}.log"
    headers = D.parse_headers((project_dir / rel).read_text(encoding="utf-8",
                                                            errors="surrogateescape"))
    allow = D.parse_network(headers[D.HEADER_NETWORK])["hosts"]
    cmd = S._launch_cmd(cfg, worktree_prompt(rel, stem, wt, branch, project_dir))
    started = time.monotonic()
    code = S._run(cmd, wt, log_path, extra["child_session_id"], network_allowlist=allow,
                  extra_env={WT.PRIMARY_CHECKOUT_ENV: str(project_dir)})
    wall = round(time.monotonic() - started, 3)
    result_rel = f"cc_tasks/{stem}_RESULT.md"
    committed = WT.show(project_dir, branch, result_rel) is not None
    graph_state = S._state_of(driver, database, task_id)
    finish = {"task_id": task_id, "source_file": rel,
              "child_session_id": extra["child_session_id"],
              "exit_code": code, "wall_clock_s": wall, "result_present": committed,
              "result_path": result_rel, "graph_state_observed": graph_state,
              "log_path": str(log_path.relative_to(project_dir)), "mode": "worktree",
              "worktree": extra["worktree"], "branch": branch, "base": extra["base"]}
    name = _task_name(driver, database, task_id) or stem
    click.echo(f"session exit={code} result_committed={committed} graph={graph_state}")
    try:
        if code != 0 or not committed or graph_state not in ("in_progress", "completed"):
            with _pass_lease(project_dir, cfg):
                _finish_unmerged(project_dir, config, driver, database, domain_config,
                                 session_id, cfg, finish, name, "session_failed")
            return
        _merge(project_dir, config, driver, database, domain_config, session_id, cfg,
               finish, name, extra)
    except D.LeaseHeld as held:
        # Nothing is recorded without the pass lease. The worktree lease is released by the
        # caller with no finish, which the next pass reads as `released_unfinished`.
        click.echo(f"could not take the pass lease in {cfg['merge_lock_timeout_s']}s (held by "
                   f"{held.body.get('holder')}); left for the next pass", err=True)


def _task_name(driver, database, task_id):
    with driver.session(database=database) as s:
        r = s.run("MATCH (t:ResearchTask {artifact_id: $id}) RETURN t.name AS n",
                  id=task_id).single()
    return r["n"] if r else None


# ============================================================================== the merge

def _gate(project_dir: Path, cfg: dict, wt: Path, stem: str) -> dict:
    """Run `dispatch.gate_command` in the worktree. `{ok, exit_code, log_path, timed_out}`."""
    log = project_dir / cfg["log_dir"] / f"{stem}.gate.log"
    env = {**os.environ, WT.PRIMARY_CHECKOUT_ENV: str(project_dir)}
    with log.open("a", encoding="utf-8") as fh:
        fh.write(f"=== {S._now()} | gate | {cfg['gate_command']}\n")
        fh.flush()
        proc = subprocess.Popen(["/bin/sh", "-c", cfg["gate_command"]], cwd=wt, env=env,
                                stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT,
                                start_new_session=True)
        timed_out = False
        try:
            code = proc.wait(timeout=cfg["gate_timeout_s"])
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            code, timed_out = proc.wait(), True
        fh.write(f"\nEXIT={code}\n")
    return {"ok": code == 0 and not timed_out, "exit_code": code, "timed_out": timed_out,
            "log_path": str(log.relative_to(project_dir))}


def _spec_modified(driver, database, task_id: str, path: Path) -> bool:
    """The registered spec hash against the task file as it would land: `seldon cc complete`'s
    immutability check (cc_tasks findings may be appended below the spec, nothing above)."""
    from seldon.commands.cc import (HASH_SCOPE_SPEC, _file_hash, _get_artifact_file_hash,
                                    _spec_hash)
    registered, scope = _get_artifact_file_hash(driver, database, task_id)
    if registered is None or not path.is_file():
        return False
    if _spec_hash(path) == registered:
        return False
    return not (scope != HASH_SCOPE_SPEC and _file_hash(path) == registered)


def _merge(project_dir, config, driver, database, domain_config, session_id, cfg, finish,
           name, extra) -> None:
    """Decision 3: rebase onto main, re-gate if main changed the write set, check the union
    files, then fast-forward under the pass lease if main has not moved. Never resolves.

    Bounded by `merge_attempts`. A round ends early when main moved by a change outside the
    housekeeping set (the `merge=union` files and `shared_paths`), or when the fast-forward or
    the primary's branch refused; the last such reason is what a run of exhausted attempts is
    blocked on. A move made only of housekeeping commits, which the sweep under the lease
    itself makes whenever a ledger or the store has new lines, is rebased over inside the
    lease: it cannot conflict and is excluded from the re-gate, so it never costs a round.
    """
    stem, branch, rel = extra["stem"], extra["branch"], extra["source_file"]
    wt = project_dir / extra["worktree"]
    linked = extra.get("linked") or []
    regated, gate, last = False, None, ("main_kept_moving", [], {})

    def unmerged(reason, files, **detail):
        _finish_unmerged(project_dir, config, driver, database, domain_config, session_id,
                         cfg, finish, name, "merge_blocked",
                         merge={"reason": reason, "files": files, **detail})

    def blocked(reason, files, **detail):
        with _pass_lease(project_dir, cfg):
            unmerged(reason, files, **detail)

    def union_bad(tip, base_sha, writes):
        bad = {}
        for path in WT.union_files(wt, writes):
            check = WT.check_union_text(WT.show(wt, tip, path) or b"",
                                        cfg["union_unique_key"],
                                        base=WT.show(wt, base_sha, path))
            if not check["ok"]:
                bad[path] = {"malformed_lines": check["malformed"],
                             "duplicate_ids": check["duplicates"]}
        return bad

    for attempt in range(1, cfg["merge_attempts"] + 1):
        # Every round, not once: a gate that rewrote a tracked file would otherwise surface
        # as a rebase failure with no file named.
        dirt = WT.dirty_paths(wt, exclude=linked)
        if dirt:
            return blocked("uncommitted_changes", dirt, attempt=attempt)
        main_sha = WT.rev(project_dir, cfg["branch"])
        fork = WT.git(wt, "merge-base", "HEAD", main_sha).stdout.strip()
        writes = WT.changed_files(wt, fork, "HEAD")
        union = set(WT.union_files(wt, writes))
        if fork != main_sha:
            moved = WT.changed_files(wt, fork, main_sha)
            rb = WT.rebase(wt, main_sha)
            if not rb["ok"]:
                return blocked("rebase_conflict", rb["conflicts"], stderr=rb["stderr"][-500:],
                               attempt=attempt)
            # Append-only `merge=union` files are excluded: decision 4's check reads their
            # merged content below, and every merge moves the event store, so counting it
            # would re-gate every task whose main moved at all.
            overlap = sorted((set(moved) & set(writes)) - union)
            if overlap:
                regated, gate = True, _gate(project_dir, cfg, wt, stem)
                if not gate["ok"]:
                    return blocked("regate_red", overlap, gate=gate, attempt=attempt)
        tip = WT.rev(wt, "HEAD")
        bad = union_bad(tip, main_sha, writes)
        if bad:
            return blocked("union_invalid", sorted(bad), union=bad)
        if _spec_modified(driver, database, finish["task_id"], wt / rel):
            return blocked("spec_modified", [rel])
        with _pass_lease(project_dir, cfg):
            # What a pass would commit first, committed first here: a line a Desktop tool
            # appended while a pass held the lease would otherwise make the fast-forward
            # refuse to overwrite the store.
            S._record_own_lines(project_dir, config, cfg)
            _commit_shared(project_dir, cfg)
            now = WT.rev(project_dir, cfg["branch"])
            if now != main_sha:
                arrived = WT.changed_files(wt, main_sha, now)
                housekeeping = set(WT.union_files(wt, arrived)) | set(cfg["shared_paths"])
                if not set(arrived) <= housekeeping:
                    last = ("main_kept_moving", [], {"attempts": attempt})
                    continue   # real change landed while this was gated; rebase again
                rb = WT.rebase(wt, now)
                if not rb["ok"]:
                    return unmerged("rebase_conflict", rb["conflicts"],
                                    stderr=rb["stderr"][-500:], attempt=attempt)
                tip, main_sha = WT.rev(wt, "HEAD"), now
                bad = union_bad(tip, main_sha, writes)
                if bad:
                    return unmerged("union_invalid", sorted(bad), union=bad)
            if D.tree_state(project_dir)["branch"] != cfg["branch"]:
                last = ("primary_wrong_branch", [], {"attempts": attempt})
                continue
            ff = WT.git(project_dir, "merge", "--ff-only", "-q", branch)
            if ff.returncode != 0:
                last = ("ff_refused", [], {"attempts": attempt,
                                           "stderr": (ff.stderr or ff.stdout).strip()[-500:]})
                continue
            _finish_merged(project_dir, config, driver, database, domain_config, session_id,
                           cfg, finish, name, extra,
                           {"commit": tip, "attempts": attempt, "regated": regated,
                            "gate": gate, "writes": writes,
                            "undeclared_writes": _undeclared(project_dir, cfg, rel, writes)})
            return
    reason, files, detail = last
    return blocked(reason, files, **detail)


def _undeclared(project_dir: Path, cfg: dict, rel: str, writes: list) -> list:
    """Files the task wrote that its Touches did not declare: an audit, like the Network
    allowlist's (DN-006 ADDENDUM_05 §2), recorded on the finish and not a refusal. The task's
    own RESULT and every `merge=union` file are exempt; append-only files merge by design."""
    conc = _declared(project_dir, cfg, rel)
    globs = D._all_paths(conc, cfg.get("resources") or {})
    exempt = set(WT.union_files(project_dir, writes)) | {
        f"cc_tasks/{Path(rel).stem}_RESULT.md"}
    return [w for w in writes if w not in exempt
            and not any(D.globs_may_overlap(g, w) for g in globs)]


def _finish_merged(project_dir, config, driver, database, domain_config, session_id, cfg,
                   finish, name, extra, merge) -> None:
    """Under the pass lease, after the fast-forward: complete, record, push, remove."""
    task_id = finish["task_id"]
    state = S._state_of(driver, database, task_id)
    if state == "in_progress":
        update_artifact(project_dir=project_dir, driver=driver, database=database,
                        artifact_id=task_id,
                        properties={"completed_at": S._now(), MERGE_PROPERTY: "merged"},
                        actor=S.ACTOR, authority="accepted", session_id=session_id)
        walk_to_completed(project_dir=project_dir, driver=driver, database=database,
                          domain_config=domain_config, artifact_id=task_id,
                          current_state="in_progress", actor=S.ACTOR, session_id=session_id)
    # Named before `git worktree remove --force` discards them: committed work is safe (the
    # branch is merged and deleted with `-d`), gitignored output is not, and losing it
    # silently is the one thing the removal may not do.
    merge = {**merge, "discarded_ignored": WT.ignored_paths(
        project_dir / extra["worktree"], exclude=extra.get("linked") or [])}
    if merge["discarded_ignored"]:
        click.echo(f"removing {extra['worktree']} discards gitignored: "
                   f"{', '.join(merge['discarded_ignored'][:10])}", err=True)
    done = {**finish, "ok": True, "outcome": "merged",
            "graph_state_observed": S._state_of(driver, database, task_id),
            "merge": {k: v for k, v in merge.items() if k != "writes"}}
    S._emit(project_dir, session_id, D.EVENT_FINISHED, done)
    if merge["undeclared_writes"]:
        click.echo(f"undeclared writes by {task_id[:8]}: "
                   f"{', '.join(merge['undeclared_writes'])}", err=True)
    click.echo(f"merged {task_id[:8]} {extra['branch']} at {merge['commit'][:8]} "
               f"(attempt {merge['attempts']}, regated={merge['regated']})")
    S._notify(project_dir, session_id, cfg, done, name, outcome="merged")
    S._record_and_push(project_dir, config, cfg)
    removed = WT.remove(project_dir, project_dir / extra["worktree"], extra["branch"])
    if not (removed["worktree_removed"] and removed["branch_deleted"]):
        click.echo(f"cleanup of {extra['worktree']} incomplete: {removed['stderr']}", err=True)


def _finish_unmerged(project_dir, config, driver, database, domain_config, session_id, cfg,
                     finish, name, outcome, merge=None) -> None:
    """Under the pass lease: a worktree task that will not merge. Blocked, never retried
    (DN-006 decision 4), its worktree left where it is. `merge_blocked` also writes an Issue
    naming the files and sets the task's `dispatch_merge` (decision 3)."""
    task_id = finish["task_id"]
    record = {**finish, "ok": False, "outcome": outcome}
    if merge is not None:
        record["merge"] = merge
    state = S._state_of(driver, database, task_id)
    if state == "completed":
        # The session ran `seldon cc complete` against the worktree instruction, and
        # `completed` has no edge back to `blocked`: the graph says done for work that is not
        # on main. Recorded on the finish and in the Issue, never left implicit.
        record["graph_completed_unmerged"] = True
    S._emit(project_dir, session_id, D.EVENT_FINISHED, record)
    S._block(project_dir, driver, database, domain_config, session_id, task_id, state,
             finish.get("exit_code"), finish["log_path"])
    after = S._state_of(driver, database, task_id)
    if state == "in_progress" and after != "blocked":
        click.echo(f"BLOCK FAILED for {task_id[:8]}: the task is still {after}; the next "
                   f"pass will find its lease released and try again", err=True)
    if record.get("graph_completed_unmerged"):
        click.echo(f"GRAPH SAYS COMPLETED for {task_id[:8]}, whose branch did not merge",
                   err=True)
    kept = (project_dir / finish["worktree"]).exists()
    if outcome == "merge_blocked":
        update_artifact(project_dir=project_dir, driver=driver, database=database,
                        artifact_id=task_id, properties={MERGE_PROPERTY: "merge_blocked"},
                        actor=S.ACTOR, authority="accepted", session_id=session_id)
        issue = _merge_issue(project_dir, driver, database, domain_config, session_id,
                             task_id, name, finish,
                             {**merge, "graph_completed_unmerged":
                              bool(record.get("graph_completed_unmerged"))})
        click.echo(f"MERGE BLOCKED {task_id[:8]} ({merge['reason']}): "
                   f"{', '.join(merge['files']) or '-'}; worktree {finish['worktree']} "
                   f"{'kept' if kept else 'absent'}; "
                   f"issue {issue[:8]}", err=True)
    else:
        click.echo(f"finished {task_id[:8]} {outcome} exit={finish.get('exit_code')} "
                   f"result={finish.get('result_present')} -> blocked; worktree "
                   f"{finish['worktree']} {'kept' if kept else 'never created'}", err=True)
    S._notify(project_dir, session_id, cfg, {**record, "wall_clock_s": record["wall_clock_s"]
                                             or 0}, name, outcome=outcome)
    S._record_and_push(project_dir, config, cfg)


def _merge_issue(project_dir, driver, database, domain_config, session_id, task_id, name,
                 finish, merge) -> str:
    files = merge.get("files") or []
    description = (
        f"Worktree task {name} ({task_id[:8]}) did not merge: {merge['reason']}. "
        + ("The graph shows the task completed, because the session ran `seldon cc "
           "complete`; its work is NOT on main. " if merge.get("graph_completed_unmerged")
           else "") +
        f"Files: {', '.join(files) or 'none named'}. The branch {finish['branch']} and the "
        f"worktree {finish['worktree']} are kept as the session left them; the dispatcher "
        f"resolves nothing (SEL-004 decision 3). To finish by hand: resolve in the worktree, "
        f"run the gate, fast-forward main, `seldon cc complete {finish['source_file']}`, "
        f"then `git worktree remove` and `seldon dispatch lease reap --task "
        f"{Path(finish['worktree']).name}` if the lease is still recorded.")
    issue_id = create_artifact(
        project_dir=project_dir, driver=driver, database=database,
        domain_config=domain_config, artifact_type="Issue",
        properties={"name": f"merge_blocked: {name}", "description": description,
                    "issue_type": "merge_blocked", "importance": "high", "urgency": "high",
                    "detection_method": "automated_check", "target": "content",
                    "files": files, "merge_reason": merge["reason"],
                    "worktree": finish["worktree"], "branch": finish["branch"]},
        actor=S.ACTOR, authority="accepted", session_id=session_id)
    create_link(project_dir=project_dir, driver=driver, database=database,
                domain_config=domain_config, from_id=issue_id, to_id=task_id,
                from_type="Issue", to_type="ResearchTask", rel_type="remediated_by",
                actor=S.ACTOR, authority="accepted", session_id=session_id)
    return issue_id
