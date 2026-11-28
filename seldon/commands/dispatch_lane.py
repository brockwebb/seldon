"""The coordination lane's launches (SEL-054 Part A; AD-038-R40, R41).

`seldon.core.lane` holds the rules; this module is where the passes and the exclusive task's holder apply them.

**Why the holder launches beside its own task.** An exclusive task runs with the pass lease held for its whole session
(`dispatch._launch_inplace`): every later pass finds the lease held and exits, so no pass can launch anything while a
build runs, at any `max_parallel`. The holder is the one process that is awake (it inspects its session every
`poll_interval_s`, QC-002) and that may write main (it holds the lease). So the lane's launch beside a build is a step
of the holder's inspection tick: one writer of main still, the same claim, record, push and supervisor a worktree
launch uses (`dispatch_worktree._launch_worktree`), and the lease's phase says `pass` while it writes (AD-037-R17).

A lane task always runs in its own worktree under its own supervisor, never in place, so a build may launch beside a
running lane task too. Its supervisor waits for the pass lease at its finish up to `coordination_lane.merge_wait_s`,
since a build's holder keeps the lease until the build's own finish.
"""
from __future__ import annotations

import click

from seldon.core import dispatch as D
from seldon.core import lane as L


def lane_of(cfg: dict) -> dict | None:
    return cfg.get(L.LANE_KEY)


def split_claims(project_dir, cfg: dict, claims: list) -> tuple:
    """`(lane_running, inplace)`: the lane tasks a worktree lease names, and the claims that are not lane tasks with a
    lease (an exclusive task in place, or a claim whose pass died before it wrote a lease). Lane rows carry `lane`."""
    from seldon.commands import dispatch_worktree as W
    lane = lane_of(cfg)
    running, inplace = W._classify(project_dir, cfg, claims)
    lanes = []
    for r in running:
        if L.is_lane(r.get("name"), lane):
            lanes.append({**r, "lane": True})
        else:
            # A non-lane worktree task in a serial project is not expected; it is a claim like any other.
            inplace.append({"artifact_id": r["task_id"], "name": r.get("name"), "source_file": r.get("source_file")})
    # A lane slot is held for as long as its supervisor lives, whatever the graph says meanwhile: a session may move
    # its own task (the stub completes itself), and its merge is still to come. A live lane lease no claim named is
    # counted too, so a second lane task cannot start under a first one's merge.
    return lanes + unclaimed_lane_leases(project_dir, cfg, {r["task_id"] for r in lanes}), inplace


def unclaimed_lane_leases(project_dir, cfg: dict, counted: set) -> list:
    """Live lane supervisors whose task no `in_progress` claim names (the session moved its own task): each still holds
    its lane slot until its merge. Rows in `_classify`'s shape, marked `lane` and `unclaimed`."""
    out = []
    for lease in D.worktree_leases(project_dir, cfg):
        body = lease["body"]
        if body.get("lane") and lease["alive"] and body.get("worktree_task") not in counted:
            out.append({"task_id": body.get("worktree_task"), "name": None, "stem": lease["stem"],
                        "source_file": body.get("source_file"), "lease": body, "lane": True, "unclaimed": True,
                        "concurrency": D.parse_concurrency(None, None, {})})
    return out


def mark_lane_rows(rows: list, lane_running: list, lane: dict | None) -> list:
    """Each lane row's c6 becomes its lane slot (`lane.apply_lane_c6`); other rows are unchanged."""
    if not lane:
        return rows
    ids = [r["task_id"] for r in lane_running]
    for row in rows:
        if L.is_lane(row.get("name"), lane):
            L.apply_lane_c6(row, ids, lane)
    return rows


def launch(project_dir, config, driver, database, domain_config, session_id, cfg, chosen) -> None:
    """A lane task's launch: always a worktree under its own supervisor, flagged `lane` for its finish."""
    from seldon.commands import dispatch_worktree as W
    chosen["lane"] = True
    W._launch_worktree(project_dir, config, driver, database, domain_config, session_id, cfg, chosen)


def launch_beside(project_dir, config, driver, database, domain_config, session_id, cfg, lease, holder_task) -> dict:
    """One look, from the exclusive task's holder, for a lane task to launch beside it. Returns what it did.

    Every criterion a pass applies is applied here, with the lane's c6 in place of the in-place claim's, and station
    (a) and the project's launch gates run before the claim, as in a pass."""
    from seldon.commands import dispatch as S
    lane = lane_of(cfg)
    if not lane:
        return {"launched": None, "why": "no lane"}
    lane_running, _ = split_claims(project_dir, cfg, S._claims_in_flight(driver, database))
    if len(lane_running) >= lane["slots"]:
        return {"launched": None, "why": L.DEFERRED_LANE_SLOTS}
    tasks = [t for t in S._tasks(driver, database) if L.is_lane(t.get("name"), lane)]
    if not tasks:
        return {"launched": None, "why": "no lane task"}
    D.mark_phase(lease.path, D.PHASE_PASS)
    try:
        # The inspection tick appends station records to the store; they are committed first, under this lease, so
        # c7 reads the tree a pass would.
        S._record_own_lines(project_dir, config, cfg)
        tree = D.tree_state(project_dir)
        lease_body = D.read_lease(D.config_path(project_dir, cfg["lease_file"]))
        # AD-038-R46 (SEL-062, REVIEW-001 F-15): the passes' evaluation stage over the lane's own tasks.
        _band, rows = S.evaluate_queue(project_dir, cfg, driver, database, tree, None, lease_body, view="lane",
                                       lane_running=lane_running, tasks=tasks)
        eligible = [r for r in rows if r["eligible"]]
        if not eligible:
            return {"launched": None, "why": "no eligible lane task",
                    "refused": {r["task_id"]: r.get("failed") for r in rows}}
        if not S._launch_gates(project_dir, config, session_id, cfg, dry_run=False):
            return {"launched": None, "why": "launch gates"}
        reviewed, stopped = S.review_launches(project_dir, config, driver, database, domain_config, session_id, cfg,
                                              eligible, False, want=1)
        if stopped:
            return {"launched": None, "why": "environment_in_flight"}
        if not reviewed:
            return {"launched": None, "why": "every eligible lane task has a false premise"}
        row = reviewed[0]
        click.echo(f"lane: launching {row['task_id'][:8]} beside {str(holder_task)[:8]} (AD-038-R40)")
        launch(project_dir, config, driver, database, domain_config, session_id, cfg, row)
        return {"launched": row["task_id"]}
    finally:
        D.mark_phase(lease.path, D.PHASE_SESSION)


def beside(inspector, project_dir, config, driver, database, domain_config, session_id, cfg, lease, holder_task):
    """The holder's inspection tick with the lane's look after it. A failure of the look is recorded and printed and
    never reaches the holder's wait: the build it holds for is not the lane's to stop."""
    from seldon.commands import dispatch as S

    def tick() -> dict:
        out = inspector()
        try:
            launch_beside(project_dir, config, driver, database, domain_config, session_id, cfg, lease, holder_task)
        except Exception as exc:                                    # noqa: BLE001 - recorded and printed below
            err = f"{type(exc).__name__}: {exc}"
            click.echo(f"lane: the look beside {str(holder_task)[:8]} failed: {err}", err=True)
            S._emit(project_dir, session_id, EVENT_LANE_ERROR, {"holder_task": holder_task, "error": err[:500]})
        return out
    return tick


#: A lane look that raised: recorded, never swallowed, never fatal to the build it ran beside.
EVENT_LANE_ERROR = "dispatch_lane_error"
