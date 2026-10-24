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
from contextlib import contextmanager, nullcontext
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
    "This session runs in a git worktree the Claude Code CLI created and named under "
    "{primary}/" + D.CLI_WORKTREE_DIR + "/ (your working directory, on branch "
    "`" + D.CLI_BRANCH_PREFIX + "<its name>`), not in the primary "
    "checkout at {primary}; Claude Code refuses edits and git aimed at the primary. Do all work "
    "and testing here and commit everything on this branch, including the RESULT. Do not merge, "
    "push, switch branches, or run `seldon cc complete` for this task, whatever the task file "
    "says: the dispatcher rebases onto main, re-runs the gate if main changed a file this task "
    "changed, merges on green and completes the task. Run `seldon dispatch part-complete` from "
    "here. Gitignored files are not in this worktree unless linked; the primary checkout's path "
    "is in $" + WT.PRIMARY_CHECKOUT_ENV + "."
)

#: The per-worktree lease's persistent fields (`D.Lease.extra`): what a released or orphaned
#: lease still has to say about which task, worktree and branch it guarded.
LEASE_EXTRA_KEYS = ("worktree_task", "stem", "source_file", "worktree", "branch", "base",
                    "child_session_id", "linked", "model_spec")

#: `dispatch_finished.outcome` values this module writes, beside the serial `ok` boolean.
OUTCOMES = ("merged", "session_failed", "merge_blocked", "worktree_add_failed",
            "launch_failed", "model_substituted",
            "holder_gone", "released_unfinished",
            # FRICTION-002 Part D: the CLI's auto-mode breaker aborted the session.
            "classifier_breaker", "database_unavailable",
            # FRICTION-002 Part C: the session ended with its Stop gate not passed (the CLI's block cap or the token
            # ceiling ended it with a check failing, or it declared Parts and no gate ran).
            "stop_gate_unpassed")

#: The ResearchTask property that says what became of a worktree task's branch.
MERGE_PROPERTY = "dispatch_merge"


def worktree_prompt(rel: str, primary: Path, task_id: str | None = None) -> str:
    """The launch prompt: the task's Recall block (RECALL-001, read from its `recall_listed` record, so the session
    reads its history before CLAUDE.md), the protocol's dispatch line verbatim, then the worktree clause."""
    from seldon.core import recall as RC

    return (RC.task_prompt_block(primary, task_id)
            + S.DISPATCH_LINE.format(rel=rel, stem=Path(rel).stem) + " "
            + WORKTREE_CLAUSE.format(primary=primary))


# ================================================================ the CLI names the worktree (DISP-001R Part A)

#: The record that maps a launch to the worktree the CLI named: task id, stem, path, branch, base and the `init`
#: line it was read from. A record of its own, because `dispatch_launched` is committed before the CLI starts (so
#: the branch carries its own claim) and the name does not exist until the CLI has made it.
EVENT_WORKTREE_NAMED = "dispatch_worktree_named"

#: How much of the CLI's `init` line `dispatch_worktree_named` quotes (its tool and skill lists run to kilobytes).
INIT_FIELDS = ("type", "subtype", "cwd", "original_cwd", "session_id", "claude_code_version", "model")

#: How much of a launch failure's stderr line is recorded and notified.
STDERR_LINE_CHARS = 500


def _segment(log_path: Path, offset: int) -> list:
    """The session's lines: everything the CLI wrote after `offset`, without `_run`'s header and `EXIT=` lines."""
    if not Path(log_path).is_file():
        return []
    with Path(log_path).open("r", encoding="utf-8", errors="replace") as fh:
        fh.seek(offset)
        lines = fh.read().splitlines()
    return [ln for ln in lines if ln.strip() and not ln.startswith("=== ") and not ln.startswith("EXIT=")]


def _records(lines: list):
    for ln in lines:
        if ln.startswith("{"):
            try:
                obj = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                yield obj


def cli_init(log_path: Path, offset: int) -> dict | None:
    """The session's `system/init` stream-json record after `offset`, or None while there is none.

    Not the first record: the CLI writes its SessionStart hooks' `hook_started`/`hook_response` records ahead of
    `init` (CLI 2.1.303, docs/evidence/disp001r/cli_init_probe.txt). `init.cwd` is the worktree the CLI made.
    """
    for obj in _records(_segment(log_path, offset)):
        if obj.get("type") == "system" and obj.get("subtype") == "init" and obj.get("cwd"):
            return obj
    return None


def reached_model(log_path: Path, offset: int) -> bool:
    """Did the session get as far as its first `assistant` message? A CLI exit before it is `launch_failed`."""
    return any(obj.get("type") == "assistant" for obj in _records(_segment(log_path, offset)))


def launch_stderr_line(log_path: Path, offset: int) -> str | None:
    """The CLI's last line that is not stream-json: its error, for a session that never reached the model. The
    CLI's stderr is merged into the log (`_run`), and everything the CLI writes on stdout in this mode is JSON."""
    plain = [ln.strip() for ln in _segment(log_path, offset) if not ln.startswith("{")]
    return plain[-1][:STDERR_LINE_CHARS] if plain else None


def name_worktree(project_dir: Path, session_id, extra: dict, init: dict, links: list, emit: bool = True) -> dict:
    """Fill `extra` with the worktree the CLI named in `init`, link `links` into it, record it. Returns the record.

    The branch is read from the worktree, not composed from its name; `base` is the branch's commit now, before the
    session has committed, which is the commit the CLI cut it from. A path outside the checkout, or no branch, is
    recorded with its `error` and fills nothing: the finish then keeps whatever it finds and merges nothing.

    `emit=False` (the parallel supervisor) holds the record in `extra` for `finish_session` to write: mid-session the
    lease carries the mapping, and a record appended to the primary's event store then would leave the tree dirty
    for every read-only `status` until the next pass reconciles it.
    """
    project_dir = Path(project_dir)
    wt = Path(init["cwd"]).resolve()
    record = {"task_id": extra["worktree_task"], "stem": extra["stem"], "source_file": extra["source_file"],
              "child_session_id": extra["child_session_id"], "init": {k: init.get(k) for k in INIT_FIELDS}}
    try:
        rel = str(wt.relative_to(project_dir.resolve()))
    except ValueError:
        rel = None
    branch = WT.git(wt, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() if wt.is_dir() else ""
    if rel is None or not rel.startswith(D.CLI_WORKTREE_DIR + "/") or not branch or branch == "HEAD":
        record["error"] = f"init cwd {wt} is not a branch worktree under {project_dir}/{D.CLI_WORKTREE_DIR}"
    else:
        extra.update({"worktree": rel, "branch": branch, "base": WT.rev(wt, "HEAD") or extra.get("base"),
                      "linked": WT.link(project_dir, wt, links)})
        record.update({k: extra[k] for k in ("worktree", "branch", "base", "linked")})
    if emit:
        S._emit(project_dir, session_id, EVENT_WORKTREE_NAMED, record)
    else:
        extra[NAMED_PENDING] = record
    return record


#: The `extra` key under which a held `dispatch_worktree_named` record waits for the finish (never in the lease).
NAMED_PENDING = "_worktree_named_pending"


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
    done = None
    if inplace_claim is None and not dry_run:
        sweep(project_dir, session_id)
        S._breaker_and_stale(project_dir, config, driver, database, domain_config, session_id, cfg)
        # AD-038-R1: the serial pass's reconcile, before the shared files and before the tree is read.
        done = S._reconcile(project_dir, config, cfg, driver, database)
        _commit_shared(project_dir, cfg)
    exclude = cfg["shared_paths"]
    tree = D.tree_state(project_dir, exclude)
    if cfg.get("cadence"):
        S._cadence(project_dir, config, driver, database, domain_config, session_id, cfg, tree,
                   inplace_claim, dry_run)
        tree = D.tree_state(project_dir, exclude)
    if tree["dirty"]:
        tree["unreconciled"] = [u for u in S._unreconciled(project_dir, config, driver, database, done)
                                if u["path"] not in set(exclude)]
    lease_body = D.read_lease(project_dir / cfg["lease_file"])
    ids = [r["task_id"] for r in running]
    union = D.union_state(project_dir)
    tasks = S._tasks(driver, database)
    cross = S._cross_waits(project_dir, tasks)
    rows = D.fifo([D.evaluate(project_dir, t, cfg, band, tree, inplace_claim, lease_body,
                              running=ids, union=union, cross_waits=cross) for t in tasks])
    S._record_last_pass(project_dir, cfg, rows, tree, inplace_claim, dry_run)
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
    for n, r in enumerate(chosen):
        if r["concurrency"]["exclusive"]:
            # `plan_launches` launches an exclusive task only when nothing runs, and alone.
            S._launch_inplace(project_dir, config, driver, database, domain_config,
                              session_id, cfg, lease, r)
            continue
        if n:
            # SQ-010 ADDENDUM 02 D3.4: c12 was measured before this pass launched anything, and every worktree
            # launched since has written a tree. Measured again, so a pass that launches several cannot spend
            # the same free space on each. A shortfall here waits for a later pass, as c12 would make it.
            again = D.disk_state(project_dir, cfg, worktree=True)
            if not again["ok"]:
                r["criteria"]["c12"] = again
                r["eligible"], r["failed"] = False, list(r["failed"]) + ["c12"]
                click.echo("  not launched after the launches before it in this pass:")
                S._echo_refusals([r], tree)
                continue
        _launch_worktree(project_dir, config, driver, database, domain_config, session_id,
                         cfg, r)


def survey(project_dir, cfg, driver, database, band, lease_body) -> dict:
    """What `status` shows under `max_parallel > 1`: the pass's evaluation and plan, with no
    write, no reap and no launch. A dead supervisor is shown, not marked; marking is a pass's."""
    running, inplace = _classify(project_dir, cfg, S._claims_in_flight(driver, database))
    claim = inplace[0] if inplace else None
    tree = D.tree_state(project_dir, cfg["shared_paths"])
    ids = [r["task_id"] for r in running]
    union = D.union_state(project_dir)
    tasks = S._tasks(driver, database)
    cross = S._cross_waits(project_dir, tasks)
    rows = D.fifo([D.evaluate(project_dir, t, cfg, band, tree, claim, lease_body, running=ids,
                              union=union, cross_waits=cross) for t in tasks])
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
                 "in_progress", None, log_rel, reason=S.block_reason(outcome, None, log_rel))
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
    """Claim, record, start its supervisor, which launches the CLI into a worktree the CLI names. Returns at once."""
    rel, tid = chosen["source_file"], chosen["task_id"]
    stem = Path(rel).stem
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
                       chosen, claimed, child_session_id, log_dir, log_rel)
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
                               "mode": "worktree", "worktree": None, "branch": None,
                               "error": error},
                         chosen.get("name") or stem, "launch_failed")


def _start_claimed(project_dir, config, driver, database, domain_config, session_id, cfg,
                   chosen, claimed, child_session_id, log_dir, log_rel) -> None:
    """Everything after a successful claim: record, start the supervisor (the CLI cuts and names the worktree)."""
    rel, tid = chosen["source_file"], chosen["task_id"]
    stem = Path(rel).stem
    # AD-035 R2 and R7: refreshed (cached for the day) before the run; the supervisor launches
    # with THIS spec, carried in the lease, so a lock bump while it starts changes nothing.
    refresh_note = S.models.ensure_fresh("dispatch")
    spec = S._session_spec(project_dir, rel)
    cmd = S._launch_cmd(cfg, worktree_prompt(rel, project_dir, tid), spec, worktree=True,
                        settings=S._session_settings(project_dir, cfg))
    conc = chosen["concurrency"]
    S._emit(project_dir, session_id, D.EVENT_LAUNCHED,
            {"task_id": tid, "source_file": rel, "child_session_id": child_session_id,
             "claimed_by": claimed["claimed_by"], "transitions": claimed["transitions"],
             "criteria": chosen["criteria"], "framework_layer": chosen["framework_layer"],
             "network_allowlist": chosen["criteria"]["c5"]["network_allowlist"],
             "log_path": log_rel, "command": " ".join(shlex.quote(p) for p in cmd),
             "permission_mode": cfg["permission_mode"], "launched_at": S._now(),
             "mode": "worktree", "worktree": None, "branch": None, "worktree_named_by": "cli", "stem": stem,
             "touches": {"resources": conc["resources"], "paths": conc["paths"]},
             **S._model_fields(spec, refresh_note)})
    # Committed and pushed BEFORE the CLI cuts the worktree, so the task's branch starts from a
    # main that already carries its own claim.
    S._record_and_push(project_dir, config, cfg)
    base = WT.rev(project_dir, "HEAD")
    # `worktree`, `branch` and `linked` are filled by the supervisor at the session's `init` (`name_worktree`).
    extra = {"worktree_task": tid, "stem": stem, "source_file": rel, "worktree": None,
             "branch": None, "base": base, "child_session_id": child_session_id,
             "linked": [], "model_spec": spec}
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
    click.echo(f"launching {tid[:8]} {rel} in a worktree the CLI names -> {log_rel} "
               f"(supervisor pid {proc.pid})")
    # SQ-010 ADDENDUM 02 D3.4: the pass measures free space again before each further launch, and that reading
    # must include this launch's checkout. The CLI cuts the tree after the supervisor starts it, so the pass waits
    # until the supervisor has recorded the CLI's worktree in the lease (at `init`), the supervisor has exited, or
    # `INIT_WAIT_S` has passed.
    deadline = time.monotonic() + S.INIT_WAIT_S
    while proc.poll() is None and time.monotonic() < deadline and not D.read_lease(lease_path).get("worktree"):
        time.sleep(S.INIT_POLL_S)


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
    stem, rel = extra["stem"], extra["source_file"]
    log_path = project_dir / cfg["log_dir"] / f"{stem}.log"
    headers = D.parse_headers((project_dir / rel).read_text(encoding="utf-8",
                                                            errors="surrogateescape"))
    allow = D.parse_network(headers[D.HEADER_NETWORK])["hosts"]
    spec = extra["model_spec"]
    cmd = S._launch_cmd(cfg, worktree_prompt(rel, project_dir, task_id), spec, worktree=True,
                        settings=S._session_settings(project_dir, cfg))
    started = time.monotonic()
    offset = S._log_offset(log_path)
    lease_path = D.worktree_lease_path(project_dir, cfg, stem)

    def named(init: dict) -> None:
        # The lease says which worktree it guards once the CLI has named it (`_reap_stale`, `_classify` read it).
        # Rewritten in place: this process's flock is on the file's inode.
        name_worktree(project_dir, session_id, extra, init, cfg["worktree_links"], emit=False)
        with lease_path.open("r+", encoding="utf-8") as fh:
            body = {**json.loads(fh.read() or "{}"), **{k: extra[k] for k in ("worktree", "branch", "base", "linked")}}
            fh.seek(0)
            fh.truncate()
            fh.write(json.dumps(body, indent=1) + "\n")
    # Started in the PRIMARY checkout: the CLI cuts its worktree in the repository it starts in.
    code = S._run(cmd, project_dir, log_path, extra["child_session_id"], network_allowlist=allow,
                  extra_env=S._worktree_env(project_dir, spec, cfg), on_init=named)
    wall = round(time.monotonic() - started, 3)
    finish_session(project_dir, config, driver, database, domain_config, session_id, cfg, task_id, extra,
                   code, wall, log_path, offset, spec)


def finish_session(project_dir, config, driver, database, domain_config, session_id, cfg, task_id, extra,
                   code, wall, log_path, offset, spec, name=None, lease_cm=None) -> None:
    """A worktree session has exited: merge on green, or block and keep its worktree (AD-034-R5, R6).

    Shared by the parallel supervisor and, since FRICTION-002, the serial pass. `lease_cm` is a zero-argument
    context manager factory for the pass lease; the supervisor takes it (the default), while a serial pass already
    holds it and passes `contextlib.nullcontext`.
    """
    lease_cm = lease_cm or (lambda: _pass_lease(project_dir, cfg))
    pending = extra.pop(NAMED_PENDING, None)
    if pending is not None:
        S._emit(project_dir, session_id, EVENT_WORKTREE_NAMED, pending)
    if not extra.get("worktree"):
        # DISP-001R Part A: `_run` stopped watching before the CLI's `init`, or never watched (a supervisor started
        # by an older pass); the log still says which worktree the CLI made.
        init = cli_init(log_path, offset)
        if init is not None:
            name_worktree(project_dir, session_id, extra, init, cfg["worktree_links"])
    if not reached_model(log_path, offset):
        finish = {"task_id": task_id, "source_file": extra["source_file"],
                  "child_session_id": extra["child_session_id"], "exit_code": code, "wall_clock_s": wall,
                  "result_present": False, "result_path": f"cc_tasks/{extra['stem']}_RESULT.md",
                  "graph_state_observed": "in_progress", "log_path": str(log_path.relative_to(project_dir)),
                  "mode": "worktree", "worktree": extra.get("worktree"), "branch": extra.get("branch"),
                  "base": extra.get("base"), "linked": extra.get("linked") or []}
        try:
            with lease_cm():
                _finish_launch_failed(project_dir, config, driver, database, domain_config, session_id, cfg,
                                      finish, name or extra["stem"], launch_stderr_line(log_path, offset))
        except D.LeaseHeld as held:
            click.echo(f"could not take the pass lease in {cfg['merge_lock_timeout_s']}s (held by "
                       f"{held.body.get('holder')}); left for the next pass", err=True)
        return
    stem, rel, branch = extra["stem"], extra["source_file"], extra["branch"]
    receipt = S._model_receipt(log_path, offset, spec)
    result_rel = f"cc_tasks/{stem}_RESULT.md"
    committed = WT.show(project_dir, branch, result_rel) is not None
    classifier = S._classifier_reading(project_dir, extra["child_session_id"], log_path, offset)
    gate = S._gate_reading(project_dir, task_id, extra["child_session_id"])
    db_failure = None
    try:
        graph_state = S._state_of(driver, database, task_id)
    except S.DATABASE_UNAVAILABLE as exc:
        # AD-038-R2/R6: the session's outcome cannot be read, which is the dispatcher's own condition, not the
        # session's. Recorded as `database_unavailable`, the reason the automatic redrive answers.
        graph_state = None
        db_failure = f"{type(exc).__name__}: {str(exc).splitlines()[0][:200] if str(exc) else ''}"
    finish = {"task_id": task_id, "source_file": rel,
              "child_session_id": extra["child_session_id"],
              "exit_code": code, "wall_clock_s": wall, "result_present": committed,
              "result_path": result_rel, "graph_state_observed": graph_state,
              "log_path": str(log_path.relative_to(project_dir)), "mode": "worktree",
              "worktree": extra["worktree"], "branch": branch, "base": extra["base"],
              "linked": extra.get("linked") or [],
              "model_receipt": receipt, "classifier_blocks": classifier["blocks"], "stop_gate": gate}
    click.echo(f"session exit={code} result_committed={committed} graph={graph_state} "
               f"model={receipt['served']} (requested {receipt['requested']}) "
               f"classifier_blocks={classifier['blocks']}")
    # DISP-002 (AD-034 ADDENDUM 02): the breaker does not veto green work. A trip whose session exited 0 with its
    # RESULT committed and its Stop gate passed goes on to the merge, carrying the denials; only an unpassed one stops.
    breaker_green = classifier["breaker"] and is_green(code, committed, gate)
    if breaker_green:
        finish["breaker"] = breaker_record(classifier["blocks"], classifier["reasons"])
    elif classifier["breaker"]:
        S._classifier_stop(project_dir, session_id, task_id, classifier)
    if db_failure:
        with lease_cm():
            _finish_unreadable(project_dir, config, driver, database, domain_config, session_id, cfg,
                               {**finish, "failure": "database_unavailable", "database_error": db_failure},
                               name or stem)
        return
    name = name or _task_name(driver, database, task_id) or stem
    try:
        if classifier["breaker"] and not breaker_green:
            with lease_cm():
                _finish_unmerged(project_dir, config, driver, database, domain_config,
                                 session_id, cfg, finish, name, "classifier_breaker")
            return
        if not gate["passed"]:
            # Part C: a session the CLI let end with a declared Part's check failing (its block cap, or the token
            # ceiling) is not merged; the work stays on its branch with the failing commands named.
            with lease_cm():
                _finish_unmerged(project_dir, config, driver, database, domain_config, session_id, cfg,
                                 finish, name, "stop_gate_unpassed")
            return
        if code != 0 or not committed or graph_state not in ("in_progress", "completed"):
            with lease_cm():
                _finish_unmerged(project_dir, config, driver, database, domain_config,
                                 session_id, cfg, finish, name, "session_failed")
            return
        if not receipt["ok"]:
            # AD-035 R6: a branch written by an unverified model is never merged.
            with lease_cm():
                _finish_unmerged(project_dir, config, driver, database, domain_config,
                                 session_id, cfg, {**finish, "failure": S.models.SUBSTITUTED}, name,
                                 "model_substituted")
            return
        _merge(project_dir, config, driver, database, domain_config, session_id, cfg,
               finish, name, extra, lease_cm=lease_cm)
    except D.LeaseHeld as held:
        # Nothing is recorded without the pass lease. The worktree lease is released by the
        # caller with no finish, which the next pass reads as `released_unfinished`.
        click.echo(f"could not take the pass lease in {cfg['merge_lock_timeout_s']}s (held by "
                   f"{held.body.get('holder')}); left for the next pass", err=True)


def last_launch_failure(events: list, task_id: str) -> dict | None:
    """The payload of the task's newest `launch_failed` finish that recorded a stderr line, or None."""
    for e in reversed(events):
        p = e.get("payload") or {}
        if e.get("event_type") == D.EVENT_FINISHED and p.get("task_id") == task_id \
                and p.get("outcome") == "launch_failed" and "stderr_line" in p:
            return p
    return None


def _finish_launch_failed(project_dir, config, driver, database, domain_config, session_id, cfg, finish, name,
                          stderr_line: str | None) -> None:
    """Under the pass lease: the CLI exited before its first model turn (DISP-001R Part A step 2).

    The task never ran, so it is put back on the queue rather than blocked: `in_progress -> blocked -> accepted`,
    the redrive's own walk (AD-038-R2), because the ResearchTask machine has no edge back to `proposed`; `accepted`
    is the dispatchable state a claimed task returns to. c15 then holds it until the launcher or the task changes
    (`S._launch_holds`). The operator is notified with the CLI's line, once: a relaunch that fails with the same
    line is recorded `repeat` and not notified again.
    """
    from seldon.core import redrive as R
    from seldon.core.events import read_events

    task_id = finish["task_id"]
    line = stderr_line or f"the CLI exited {finish.get('exit_code')} before its first model turn and wrote no error"
    previous = last_launch_failure(read_events(project_dir), task_id)
    repeat = previous is not None and previous.get("stderr_line") == line
    record = {**finish, "ok": False, "outcome": "launch_failed", "stderr_line": line, "repeat": repeat,
              "fingerprint": S.launcher_fingerprint(project_dir, finish["source_file"])}
    S._emit(project_dir, session_id, D.EVENT_FINISHED, record)
    state = S._state_of(driver, database, task_id)
    S._block(project_dir, driver, database, domain_config, session_id, task_id, state,
             finish.get("exit_code"), finish["log_path"],
             reason=S.block_reason("launch_failed", finish.get("exit_code"), finish["log_path"]))
    if S._state_of(driver, database, task_id) == "blocked":
        R.redrive(project_dir, driver, database, domain_config, task_id, actor=S.ACTOR, session_id=session_id)
    after = S._state_of(driver, database, task_id)
    _record_kept(project_dir, session_id, finish, "launch_failed", line)
    click.echo(f"finished {task_id[:8]} launch_failed exit={finish.get('exit_code')} -> {after}"
               f"{' (repeat, not notified)' if repeat else ''}: {line}", err=True)
    if not repeat:
        S._notify(project_dir, session_id, cfg, {**record, "wall_clock_s": record["wall_clock_s"] or 0}, name,
                  outcome="launch_failed", message=f"launch_failed: {line}")
    S._record_and_push(project_dir, config, cfg)


def _finish_unreadable(project_dir, config, driver, database, domain_config, session_id, cfg, finish,
                       name) -> None:
    """The graph could not be read at the finish: blocked from the state the claim left, worktree kept."""
    record = {**finish, "ok": False, "outcome": "database_unavailable"}
    S._emit(project_dir, session_id, D.EVENT_FINISHED, record)
    S._block(project_dir, driver, database, domain_config, session_id, finish["task_id"], "in_progress",
             finish.get("exit_code"), finish["log_path"],
             reason=S.block_reason("database_unavailable", finish.get("exit_code"), finish["log_path"]))
    _record_kept(project_dir, session_id, finish, "database_unavailable", "database_unavailable")
    click.echo(f"finished {finish['task_id'][:8]} database_unavailable -> blocked; worktree "
               f"{finish['worktree']} kept", err=True)
    S._notify(project_dir, session_id, cfg, {**record, "wall_clock_s": record["wall_clock_s"] or 0}, name,
              outcome="database_unavailable")
    S._record_and_push(project_dir, config, cfg)


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
           name, extra, lease_cm=None) -> None:
    """Decision 3: rebase onto main, re-gate if main changed the write set, check the union
    files, then fast-forward under the pass lease if main has not moved. Never resolves.

    Bounded by `merge_attempts`. A round ends early when main moved by a change outside the
    housekeeping set (the `merge=union` files and `shared_paths`), or when the fast-forward or
    the primary's branch refused; the last such reason is what a run of exhausted attempts is
    blocked on. A move made only of housekeeping commits, which the sweep under the lease
    itself makes whenever a ledger or the store has new lines, is rebased over inside the
    lease: it cannot conflict and is excluded from the re-gate, so it never costs a round.
    """
    lease_cm = lease_cm or (lambda: _pass_lease(project_dir, cfg))
    stem, branch, rel = extra["stem"], extra["branch"], extra["source_file"]
    wt = project_dir / extra["worktree"]
    linked = extra.get("linked") or []
    regated, gate, last = False, None, ("main_kept_moving", [], {})

    def unmerged(reason, files, **detail):
        _finish_unmerged(project_dir, config, driver, database, domain_config, session_id,
                         cfg, finish, name, "merge_blocked",
                         merge={"reason": reason, "files": files, **detail})

    def blocked(reason, files, **detail):
        with lease_cm():
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
            if overlap and not cfg.get("gate_command"):
                # A serial project need not declare a gate (FRICTION-002): with none, a task whose files main
                # changed under it cannot be re-gated and is not merged on faith.
                return blocked("regate_unavailable", overlap, attempt=attempt)
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
        with lease_cm():
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
            # LOOP-001 Part B: the rebased branch's register, its pending records included, verifies before main
            # takes it, so the numbering after the fast-forward cannot refuse (two branches creating one id).
            reg_bad = _register_findings(wt, config)
            if reg_bad:
                return unmerged("register_invalid", sorted({x.split(":", 1)[0] for x in reg_bad}),
                                findings=reg_bad[:12], attempt=attempt)
            if D.tree_state(project_dir)["branch"] != cfg["branch"]:
                last = ("primary_wrong_branch", [], {"attempts": attempt})
                continue
            ff = WT.git(project_dir, "merge", "--ff-only", "-q", branch)
            if ff.returncode != 0:
                last = ("ff_refused", [], {"attempts": attempt,
                                           "stderr": (ff.stderr or ff.stdout).strip()[-500:]})
                continue
            merge = {"commit": tip, "attempts": attempt, "regated": regated, "gate": gate, "writes": writes,
                     "undeclared_writes": _undeclared(project_dir, cfg, rel, writes)}
            numbered = number_merged_register(project_dir, config, session_id, finish["task_id"], branch)
            if numbered:
                merge["register_numbered"] = numbered
            _finish_merged(project_dir, config, driver, database, domain_config, session_id,
                           cfg, finish, name, extra, merge)
            return
    reason, files, detail = last
    return blocked(reason, files, **detail)


#: LOOP-001 Part B: what the merge step records when it numbers a merged branch's pending register records.
EVENT_REGISTER_NUMBERED = "register_numbered"


def _register_findings(wt: Path, config: dict) -> list:
    """The decision register's findings in the worktree's tree (chain and pending), or [] with no register."""
    from seldon.core import decisions as dr
    s = dr.settings(wt, config)
    if s is None:
        return []
    return dr.Register(s.repository, Path(wt), s.register_dir).verify()


def number_merged_register(project_dir: Path, config: dict, session_id, task_id: str | None,
                           branch: str | None) -> dict | None:
    """LOOP-001 Part B (AD-033 ADDENDUM 01), after the fast-forward, under the pass lease, in the primary: give every
    unnumbered record the merge brought the next seq, render REGISTER.md, commit both, and record
    `register_numbered` with the mapping (provisional id -> seq). None when nothing was pending.

    A numbering that fails after the merge is recorded on the same event with its `error` and printed; the merge
    stands (main already holds it), and the pending files stay for `seldon decision number` to retry."""
    from seldon.core import decisions as dr
    s = dr.settings(project_dir, config)
    if s is None or not dr.Register(s.repository, Path(project_dir), s.register_dir).pending_files():
        return None
    payload = {"task_id": task_id, "branch": branch}
    try:
        out = dr.number_register(project_dir, config)
    except (dr.RegisterError, dr.BrokenRegister) as exc:
        payload["error"] = str(exc)[-1000:]
        S._emit(project_dir, session_id, EVENT_REGISTER_NUMBERED, payload)
        click.echo(f"REGISTER NOT NUMBERED after merging {branch}: {exc}", err=True)
        return payload
    payload["mapping"] = [{"provisional_id": r["provisional_id"], "id": r["id"], "event": r["event"],
                           "seq": r["seq"], "already": r["already"]} for r in out["numbered"] + out["already"]]
    paths = [s.register_dir, s.rendered]
    commit = commit_register(project_dir, paths,
                             f"register: numbered {len(out['numbered'])} record(s) merged from {branch} "
                             f"(LOOP-001, AD-033 ADDENDUM 01)")
    payload["commit"] = commit
    S._emit(project_dir, session_id, EVENT_REGISTER_NUMBERED, payload)
    done = ", ".join(f"{r['id']} {r['event']} -> {r['seq']}" for r in out["numbered"])
    click.echo(f"register: numbered {done or 'nothing'}"
               + (f"; {len(out['already'])} already numbered" if out["already"] else ""))
    return payload


def commit_register(project_dir: Path, paths: list, message: str) -> dict:
    """Commit the register directory and REGISTER.md as they stand, deletions included (`D.commit_paths` drops a
    path that no longer exists, and numbering removes the pending files)."""
    added = WT.git(project_dir, "add", "-A", "--", *paths)
    if added.returncode != 0:
        click.echo(f"register: NOT committed (git add): {added.stderr.strip()}", err=True)
        return {"committed": False, "reason": "git_add_failed", "stderr": added.stderr.strip()}
    done = WT.git(project_dir, "commit", "-q", "-m", message, "--", *paths)
    if done.returncode != 0:
        WT.git(project_dir, "reset", "-q", "--", *paths)
        err = (done.stderr or done.stdout).strip()
        click.echo(f"register: NOT committed: {err}", err=True)
        return {"committed": False, "reason": "git_commit_failed", "stderr": err[-500:]}
    return {"committed": True, "commit": WT.rev(project_dir, "HEAD")}


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
    # RECALL-001 Part B: the dispatcher completes a worktree task, so it reads the merged RESULT's `Recall used:`
    # line for the chart. Recorded, never a merge refusal: a missing or refused line is counted as such.
    from seldon.core import recall as RC
    used = RC.used_at_merge(project_dir, task_id, finish["result_path"])
    if used is not None:
        RC.record_used(project_dir, used, actor=S.ACTOR, session_id=session_id)
        if used["missing"] or used.get("refused"):
            click.echo(f"recall: {task_id[:8]}'s RESULT {'has no' if used['missing'] else 'has a refused'} "
                       f"`Recall used:` line{': ' + used['refused'] if used.get('refused') else ''}", err=True)
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
    S._notify(project_dir, session_id, cfg, done, name,
              outcome=BREAKER_MERGED if finish.get("breaker") else "merged")
    # FRICTION-002 Part B: the merged task's worktree is removed by the sweep, which keeps the branch.
    sweep(project_dir, session_id)
    S._record_and_push(project_dir, config, cfg)


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
             finish.get("exit_code"), finish["log_path"],
             reason=S.block_reason(outcome, finish.get("exit_code"), finish["log_path"]))
    reason = (merge or {}).get("reason") or outcome
    if outcome == "stop_gate_unpassed":
        reason = f"stop_gate_unpassed: {(finish.get('stop_gate') or {}).get('why')}"
    _record_kept(project_dir, session_id, finish, outcome, reason)
    after = S._state_of(driver, database, task_id)
    if state == "in_progress" and after != "blocked":
        click.echo(f"BLOCK FAILED for {task_id[:8]}: the task is still {after}; the next "
                   f"pass will find its lease released and try again", err=True)
    if record.get("graph_completed_unmerged"):
        click.echo(f"GRAPH SAYS COMPLETED for {task_id[:8]}, whose branch did not merge",
                   err=True)
    kept = bool(finish.get("worktree")) and (project_dir / finish["worktree"]).exists()
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


# ================================================================== kept and removed worktrees (FRICTION-002)

#: How much of a kept task's RESULT `worktree_kept` quotes as the session's own reason.
RESULT_REASON_CHARS = 300


def _result_reason(project_dir: Path, branch: str, result_rel: str) -> str | None:
    """The RESULT's first line of prose on the task's branch (headings and blank lines skipped), or None when the
    branch carries no RESULT: what the session itself said about how it ended."""
    data = WT.show(project_dir, branch, result_rel)
    if data is None:
        return None
    for line in data.decode("utf-8", "replace").splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            return s[:RESULT_REASON_CHARS]
    return None


def _record_kept(project_dir: Path, session_id, finish: dict, outcome: str, reason: str) -> None:
    """FRICTION-002 Part B step 3: a task that ends unmerged keeps its worktree and branch, and says so. Nothing
    deletes a branch; the worktree goes only when the task is merged (`sweep`)."""
    if not finish.get("worktree") or not (Path(project_dir) / finish["worktree"]).exists():
        return
    S._emit(project_dir, session_id, D.EVENT_WORKTREE_KEPT,
            {"task_id": finish["task_id"], "worktree": finish["worktree"], "branch": finish.get("branch"),
             "outcome": outcome, "reason": reason,
             "result_reason": _result_reason(project_dir, finish.get("branch") or "HEAD",
                                             finish.get("result_path") or "")})


def sweep(project_dir: Path, session_id=None) -> list:
    """Remove the worktree of every MERGED task that is still on disk; keep its branch. Returns what was removed.

    A worktree is removed only when the dispatcher recorded its task `merged` (`dispatch_finished.outcome`), its
    branch is contained in main (so nothing on it is lost), and nothing tracked in it is modified. Every other
    worktree, a kept one or one the operator made, is left alone. Each removal is a `worktree_removed` record.
    Run by every pass with no session in flight and after each merge (FRICTION-002 Part B step 4).
    """
    from seldon.core.events import read_events
    project_dir = Path(project_dir)
    merged = {}
    for e in read_events(project_dir):
        p = e.get("payload") or {}
        if e.get("event_type") == D.EVENT_FINISHED and p.get("outcome") == "merged" and p.get("worktree"):
            merged[p["worktree"]] = p
    main = D.load_dispatch_config(project_dir)["branch"]
    removed = []
    for rel, p in merged.items():
        wt = project_dir / rel
        if not wt.exists():
            continue
        branch = p.get("branch")
        contained = branch and WT.git(project_dir, "merge-base", "--is-ancestor", branch, main).returncode == 0
        dirt = WT.dirty_paths(wt, exclude=p.get("linked") or [])
        if not contained or dirt:
            click.echo(f"sweep: {rel} kept ({'branch not in ' + main if not contained else 'modified: ' + ', '.join(dirt[:5])})",
                       err=True)
            continue
        ignored = WT.ignored_paths(wt, exclude=p.get("linked") or [])
        out = WT.remove(project_dir, wt)
        if not out["worktree_removed"]:
            click.echo(f"sweep: {rel} NOT removed: {out['stderr']}", err=True)
            continue
        record = {"task_id": p.get("task_id"), "worktree": rel, "branch": branch, "branch_kept": True,
                  "discarded_ignored": ignored}
        S._emit(project_dir, session_id, D.EVENT_WORKTREE_REMOVED, record)
        click.echo(f"sweep: removed {rel} (branch {branch} kept)")
        removed.append(record)
    return removed


#: Task states in which a kept worktree no longer evidences an open stop (AD-034 ADDENDUM 02, DISP-002 Part B): the
#: task was redriven (it will run again in a new tree) or ended. `blocked` and `in_progress` keep their tree.
STALE_KEPT_STATES = ("proposed", "accepted", "superseded", "withdrawn", "completed")
#: Of those, the states in which the task will never run again, so an untracked file in its tree is the only copy of
#: something nothing will ask for; it is named in the record and removed with the tree. In a redriven task's tree an
#: untracked file keeps the tree.
TERMINAL_KEPT_STATES = ("superseded", "withdrawn", "completed")


def sweep_stale_kept(project_dir: Path, driver, database: str, session_id=None) -> list:
    """Remove a KEPT worktree that holds nothing, and delete its branch. Returns what was removed.

    DISP-002 Part B step 2 (AD-034 ADDENDUM 02). A task that ended unmerged keeps its tree and branch as evidence for
    the operator (`_record_kept`). Once the task is redriven or ended (`STALE_KEPT_STATES`) and its branch carries
    no commit beyond main and no modified tracked file, the tree is evidence of nothing and only blocks a relaunch
    on the same name. Such a tree is removed and its branch deleted with `git branch -d`, which refuses a branch main
    does not contain, so no commit can be lost. Untracked files are allowed only for a terminal task and are named
    in the `worktree_removed` record. Before this, three such trees (RECALL-001, MCP-001, DISP-001) waited on an
    operator because a dispatched session's classifier refuses `git worktree remove`.
    """
    from seldon.core.events import read_events
    project_dir = Path(project_dir)
    kept, merged = {}, set()
    for e in read_events(project_dir):
        p = e.get("payload") or {}
        if e.get("event_type") == D.EVENT_WORKTREE_KEPT and p.get("worktree"):
            kept[p["worktree"]] = p
        elif e.get("event_type") == D.EVENT_FINISHED and p.get("outcome") == "merged" and p.get("worktree"):
            merged.add(p["worktree"])
    main = D.load_dispatch_config(project_dir)["branch"]
    removed = []
    for rel, p in kept.items():
        wt, branch = project_dir / rel, p.get("branch")
        if rel in merged or not wt.exists() or not branch or not p.get("task_id"):
            continue
        state = S._state_of(driver, database, p["task_id"])
        if state not in STALE_KEPT_STATES:
            continue
        ahead = WT.git(project_dir, "rev-list", "--count", f"{main}..{branch}")
        if ahead.returncode != 0 or ahead.stdout.strip() != "0":
            click.echo(f"sweep: kept {rel} stays ({state}; branch {branch} "
                       f"{'unreadable' if ahead.returncode else ahead.stdout.strip() + ' commit(s) beyond ' + main})",
                       err=True)
            continue
        status = [ln for ln in WT.git(wt, "status", "--porcelain").stdout.split("\n") if ln.strip()]
        tracked = [ln[3:] for ln in status if not ln.startswith("??")]
        untracked = [ln[3:] for ln in status if ln.startswith("??")]
        if tracked or (untracked and state not in TERMINAL_KEPT_STATES):
            click.echo(f"sweep: kept {rel} stays ({state}; "
                       f"{'modified: ' + ', '.join(tracked[:5]) if tracked else 'untracked: ' + ', '.join(untracked[:5])})",
                       err=True)
            continue
        ignored = WT.ignored_paths(wt)
        out = WT.remove(project_dir, wt)
        if not out["worktree_removed"]:
            click.echo(f"sweep: kept {rel} NOT removed: {out['stderr']}", err=True)
            continue
        deleted = WT.git(project_dir, "branch", "-d", branch)
        record = {"task_id": p["task_id"], "worktree": rel, "branch": branch, "reason": "stale_kept",
                  "task_state": state, "branch_kept": deleted.returncode != 0,
                  "branch_delete_error": (deleted.stderr or deleted.stdout).strip()[-300:] if deleted.returncode else None,
                  "discarded_untracked": untracked, "discarded_ignored": ignored}
        S._emit(project_dir, session_id, D.EVENT_WORKTREE_REMOVED, record)
        click.echo(f"sweep: removed kept {rel} ({state}; branch {branch} "
                   f"{'kept: ' + record['branch_delete_error'] if record['branch_kept'] else 'deleted'})")
        removed.append(record)
    return removed


# ====================================================== the breaker does not veto green (DISP-002, AD-034 ADDENDUM 02)

#: The notification outcome, and `dispatch_finished.breaker.outcome`, of green work merged over a breaker trip.
BREAKER_MERGED = "breaker_tripped_merged"


def is_green(exit_code, result_committed, gate: dict) -> bool:
    """The session's own evidence that its work is done: exit 0, its RESULT committed on the branch, and a Stop gate
    that RAN and passed. A gate that never ran (no Part declared) is not evidence here, though it lets an ordinary
    finish through: the breaker's veto is lifted only by a pass on the record."""
    return exit_code == 0 and bool(result_committed) and (gate or {}).get("verdict") == "pass"


def breaker_record(blocks, reasons) -> dict:
    return {"outcome": BREAKER_MERGED, "blocks": blocks, "denials": list(reasons or [])}


def remerge_breaker_green(project_dir, config, driver, database, domain_config, session_id, cfg) -> list:
    """Apply the ruling to a finish recorded before it: merge a task blocked as `classifier_breaker` with green work.

    A task qualifies when it is `blocked`, its last `dispatch_finished` is a worktree finish with outcome
    `classifier_breaker` that `is_green`, and its worktree is still on disk. It is walked `blocked -> in_progress`
    and handed to `_merge`, which rebases, re-gates when main changed a file it changed, fast-forwards, completes and
    sweeps, or blocks it again with a `merge_blocked` Issue. Either way a new `dispatch_finished` is written, so a
    task is reconsidered once. A task redriven in the meantime (`accepted`) is left to its relaunch. Called by a pass
    with the pass lease held and no session in flight. Returns the task ids attempted.
    """
    from seldon.core.events import read_events
    events = read_events(project_dir)
    last = {}
    for e in events:
        p = e.get("payload") or {}
        if e.get("event_type") == D.EVENT_FINISHED and p.get("task_id"):
            last[p["task_id"]] = p
    tried = []
    for task_id, fin in last.items():
        if fin.get("outcome") != "classifier_breaker" or fin.get("mode") != "worktree" or not fin.get("worktree"):
            continue
        if not is_green(fin.get("exit_code"), fin.get("result_present"), fin.get("stop_gate")):
            continue
        wt = Path(project_dir) / fin["worktree"]
        if not wt.exists() or S._state_of(driver, database, task_id) != "blocked":
            continue
        reasons = [(e.get("payload") or {}).get("reason") for e in events
                   if e.get("event_type") == S.QS.EVENT_CLASSIFIER_BLOCK
                   and (e.get("payload") or {}).get("child_session_id") == fin.get("child_session_id")]
        S.transition_task(project_dir=project_dir, driver=driver, database=database, domain_config=domain_config,
                          artifact_id=task_id, current_state="blocked", new_state="in_progress", actor=S.ACTOR,
                          authority="accepted", session_id=session_id)
        finish = {**fin, "breaker": {**breaker_record(fin.get("classifier_blocks"), reasons), "remerged": True}}
        extra = {"stem": wt.name, "branch": fin["branch"], "source_file": fin["source_file"],
                 "worktree": fin["worktree"], "linked": fin.get("linked") or []}
        name = _task_name(driver, database, task_id) or wt.name
        click.echo(f"remerge: {task_id[:8]} blocked by the classifier breaker with green work; merging "
                   f"{fin['branch']} (AD-034 ADDENDUM 02)")
        _merge(project_dir, config, driver, database, domain_config, session_id, cfg, finish, name, extra,
               lease_cm=nullcontext)
        tried.append(task_id)
    return tried


# ================================================= a kept worktree is re-gated in place (DISP-003R, AD-034 ADDENDUM 03)

#: One regate attempt: the checks run, their outcome, and what the next pass compares to decide whether to try again.
EVENT_REGATED = "dispatch_regated"


class RegateRefused(Exception):
    """The task is not a regate candidate (not blocked `stop_gate_unpassed` with a kept tree and a committed RESULT)."""


def regate_candidates(project_dir: Path, driver, database: str) -> list:
    """The last `dispatch_finished` of every task that may be re-gated: a worktree finish of outcome
    `stop_gate_unpassed`, its worktree on disk, its RESULT committed on its branch, the task still `blocked`."""
    from seldon.core.events import read_events
    last = {}
    for e in read_events(project_dir):
        p = e.get("payload") or {}
        if e.get("event_type") == D.EVENT_FINISHED and p.get("task_id"):
            last[p["task_id"]] = p
    out = []
    for task_id, fin in last.items():
        if fin.get("outcome") != "stop_gate_unpassed" or fin.get("mode") != "worktree" or not fin.get("worktree"):
            continue
        if not (Path(project_dir) / fin["worktree"]).exists() or not fin.get("branch"):
            continue
        if WT.show(project_dir, fin["branch"], fin.get("result_path") or "") is None:
            continue
        if S._state_of(driver, database, task_id) != "blocked":
            continue
        out.append(fin)
    return out


def task_checks(text: str) -> list:
    """Every `check:` command of every Part the task declares, in order: what its Stop gate runs once all its Parts
    are complete, which a regate requires (a kept task's RESULT says the work is done)."""
    from seldon.core import stations as Q
    return [(part["name"], cmd) for part in Q.parse_parts(text)["parts"]
            for cmd in Q.part_criteria(text, part["name"])["checks"]]


def run_task_checks(project_dir: Path, cfg: dict, tree: Path, branch: str | None, text: str,
                    run=None) -> dict:
    """Run `task_checks(text)` in `tree` through the stations' own runner, so each check has AD-037-R14's path (the
    tree first on `PYTHONPATH`, `seldon` as `python -m seldon`) and AD-037-R15's interpreter (the project's, when it
    declares one). `{checks, failed, passed}`; a check that is not `pass` (fail or unrunnable) fails the regate:
    nothing unverified is merged."""
    from seldon.core import stations as Q
    scfg = Q.load_stations_config(cfg, project_dir)
    rows = [{"part": name, **Q.run_station_check(cmd, tree, scfg["check_timeout_s"], branch,
                                                 run=run or Q.run_check, **Q.interpreter_kw(scfg))}
            for name, cmd in task_checks(text)]
    failed = [r for r in rows if r["outcome"] != "pass"]
    return {"checks": rows, "failed": failed, "passed": bool(rows) and not failed}


def _branch_diff_key(wt: Path, main: str) -> str:
    """What the branch changed, independent of where it is based: a regate that failed is not re-run while this and
    main's non-housekeeping files stay the same (`_regate_unchanged`)."""
    import hashlib
    fork = WT.git(wt, "merge-base", "HEAD", main).stdout.strip()
    return hashlib.sha256(WT.git(wt, "diff", "--binary", fork, "HEAD").stdout.encode("utf-8", "surrogateescape")
                          ).hexdigest()


def _regate_unchanged(project_dir: Path, cfg: dict, wt: Path, last: dict | None, key: str) -> bool:
    """True when the task's last regate failed on this same branch diff and main has since changed only housekeeping
    (the `merge=union` files and `shared_paths`, as `_merge` counts it): running the checks again would read the same
    code. A changed branch or a real change on main is a new reading."""
    if not last or last.get("outcome") != "fail" or last.get("diff_key") != key or not last.get("main"):
        return False
    arrived = WT.changed_files(wt, last["main"], WT.rev(project_dir, cfg["branch"]))
    housekeeping = set(WT.union_files(wt, arrived)) | set(cfg["shared_paths"])
    return set(arrived) <= housekeeping


def regate(project_dir, config, driver, database, domain_config, session_id, cfg, task_id: str | None = None,
           run=None) -> list:
    """Re-gate kept work in place: DISP-003R Part C, AD-034 ADDENDUM 03 (AD-034-R10).

    For each `regate_candidates` task (or only `task_id`, which must be one, else `RegateRefused`): rebase the kept
    branch onto main in its worktree, run every `check:` line of the task in that tree with AD-037-R14's path, and
    record `dispatch_regated`. On pass, walk the task `blocked -> in_progress` and hand the branch to `_merge`, which
    re-gates when main changed a file it changed, fast-forwards, completes and sweeps, or blocks it again with a
    `merge_blocked` Issue. On fail the task stays blocked with the failing checks quoted, and the pass does not run
    the same reading again (`_regate_unchanged`); an explicit `task_id` always runs. Called with the pass lease held
    and no session in flight. Returns the `dispatch_regated` payloads.
    """
    from seldon.core.events import read_events
    project_dir = Path(project_dir)
    cands = regate_candidates(project_dir, driver, database)
    if task_id is not None:
        cands = [f for f in cands if f["task_id"] == task_id]
        if not cands:
            raise RegateRefused(f"{task_id[:8]} is not a regate candidate: it must be blocked, its last finish "
                                f"stop_gate_unpassed, its worktree kept and its RESULT committed on its branch")
    last_regate = {}
    for e in read_events(project_dir):
        if e.get("event_type") == EVENT_REGATED:
            last_regate[(e.get("payload") or {}).get("task_id")] = e["payload"]
    out = []
    for fin in cands:
        tid, wt, branch = fin["task_id"], project_dir / fin["worktree"], fin["branch"]
        main = cfg["branch"]
        record = {"task_id": tid, "regate_id": str(uuid.uuid4()), "worktree": fin["worktree"], "branch": branch,
                  "finish_answered": fin.get("child_session_id"), "by": "explicit" if task_id else "pass"}
        dirt = WT.dirty_paths(wt, exclude=fin.get("linked") or [])
        if dirt:
            record.update(outcome="fail", reason="uncommitted_changes", files=dirt[:20], checks=[], failed=[])
        else:
            key = _branch_diff_key(wt, main)
            if task_id is None and _regate_unchanged(project_dir, cfg, wt, last_regate.get(tid), key):
                continue
            main_sha = WT.rev(project_dir, main)
            rb = WT.rebase(wt, main_sha)
            record.update(diff_key=key, main=main_sha)
            if not rb["ok"]:
                record.update(outcome="fail", reason="rebase_conflict", files=rb["conflicts"],
                              stderr=rb["stderr"][-500:], checks=[], failed=[])
            else:
                text = (wt / fin["source_file"]).read_text(encoding="utf-8", errors="surrogateescape")
                res = run_task_checks(project_dir, cfg, wt, branch, text, run=run)
                record.update(outcome="pass" if res["passed"] else "fail", checks=res["checks"],
                              failed=[{"command": r["command"], "part": r["part"], "outcome": r["outcome"],
                                       "exit": r.get("exit"), "tail": (r.get("tail") or "")[-300:]}
                                      for r in res["failed"]],
                              reason=None if res["passed"] else ("no_checks" if not res["checks"] else "check_failed"))
        S._emit(project_dir, session_id, EVENT_REGATED, record)
        out.append(record)
        if record["outcome"] != "pass":
            click.echo(f"regate: {tid[:8]} stays blocked ({record['reason']}): "
                       + ("; ".join(f"`{f['command']}` {f['outcome']} exit {f['exit']}" for f in record["failed"])
                          or ", ".join(record.get("files") or []) or "-"), err=True)
            continue
        S.transition_task(project_dir=project_dir, driver=driver, database=database, domain_config=domain_config,
                          artifact_id=tid, current_state="blocked", new_state="in_progress", actor=S.ACTOR,
                          authority="accepted", session_id=session_id)
        finish = {**fin, "regate": {"regate_id": record["regate_id"],
                                    "checks": [r["command"] for r in record["checks"]]}}
        extra = {"stem": wt.name, "branch": branch, "source_file": fin["source_file"], "worktree": fin["worktree"],
                 "linked": fin.get("linked") or []}
        name = _task_name(driver, database, tid) or wt.name
        click.echo(f"regate: {tid[:8]} blocked stop_gate_unpassed; its {len(record['checks'])} check(s) pass in "
                   f"{fin['worktree']}; merging {branch} (AD-034 ADDENDUM 03)")
        _merge(project_dir, config, driver, database, domain_config, session_id, cfg, finish, name, extra,
               lease_cm=nullcontext)
    return out
