"""AD-034-R41 as amended by ADDENDUM 15: the guard on a ResearchTask's move into `completed` (SEL-062).

**Why this exists.** SEL-058 (AD-034-R41) made `seldon cc complete` refuse a task the dispatcher blocked unless a
passing full gate of main's tree is on record; REVIEW-001 F-02 put the MCP tool's completion on the same function.
REVIEW-001 F-16 found the rest of the machine's ways to `completed`: `seldon task close` and the MCP
`seldon_task_close` walk a blocked task there through `artifacts.walk_to_completed`, and `seldon task update` steps it
`blocked -> in_progress -> completed`. None of them called R41. F-21 found that the evidence was a gate of main's tree
alone, so a blocked task whose branch never reached main completed on main's unrelated green.

**The rule.** A guard belongs to the transition, not to the commands that happen to take it (guard conditions on
state-machine transitions: OMG SysML v2 and KerML, UML statecharts). `artifacts.plan_task_transition`, the one
planner every ResearchTask move goes through, calls `guard` for every move into `completed`:

* A task is held when it is `blocked` now, or when its newest move into `blocked` comes after its newest
  `dispatch_launched` (REVIEW-001 F-04), in a project with a dispatch block.
* A held task passes on a passing, clean, full `gate_run` of the tree the dispatch branch holds now (F-03), AND when
  its own dispatch branch on record has every commit's patch on that branch (`git cherry`: a rebased or cherry-picked
  commit is recognised by its patch id, the way work reaches main by hand). The record's id is stored on the task as
  `completion_gate`.
* The dispatcher's own completion after a merge passes `completion={"by": "merge", ...}`: that merge was made on R26's
  evidence. The operator's `seldon cc complete --ungated "<reason>"` passes `{"by": "ungated", "reason": ...}`, and
  the reason is stored as `completed_ungated`.
* Otherwise the move is refused (`artifacts.R41Refused`) before anything is written: `blocked_ungated` with no
  evidence, `branch_not_on_main` naming the branch and its commits that main lacks.

This module is core, not a command: the CLI's and the MCP tool's completions keep calling `r41_completion` for their
early, friendly refusal (`seldon.commands.cc` re-exports it), and the guard repeats the check at the transition.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

#: The refusals (AD-034-R41 as amended).
REFUSED_UNGATED = "blocked_ungated"
REFUSED_BRANCH = "branch_not_on_main"
#: The records that name a dispatched task's branch, read in file order so the newest wins.
BRANCH_EVENTS = ("dispatch_worktree_named", "dispatch_finished", "worktree_kept")
#: How many of a branch's unmerged commits a refusal names.
UNMERGED_SHOWN = 5


def blocked_since_launch(events: list, artifact_id: str) -> bool:
    """REVIEW-001 F-04: whether the task's newest move INTO `blocked` comes after its newest `dispatch_launched`.

    R41 is about a task the dispatcher blocked and did not merge: whatever reached main did so by hand. Its state at
    completion is not the test, because `seldon task update --state in_progress` steps a task out of `blocked` and
    `cc complete` would then never see it. A redrive the dispatcher launched again is not held: that launch's own finish
    gates and merges it (AD-034-R26). The event store is append-only, so file order is the order of record."""
    blocked_at = launched_at = -1
    for i, e in enumerate(events):
        q = e.get("payload") or {}
        if e.get("event_type") == "artifact_state_changed" and q.get("artifact_id") == artifact_id \
                and q.get("to_state") == "blocked":
            blocked_at = i
        elif e.get("event_type") == "dispatch_launched" and q.get("task_id") == artifact_id:
            launched_at = i
    return blocked_at > launched_at


def task_branch(events: list, artifact_id: str) -> str | None:
    """The dispatch branch the newest launch, finish or kept-worktree record names for the task, or None."""
    branch = None
    for e in events:
        q = e.get("payload") or {}
        if e.get("event_type") in BRANCH_EVENTS and q.get("task_id") == artifact_id and q.get("branch"):
            branch = q["branch"]
    return branch


def branch_on_main(primary: Path, main: str, branch: str) -> tuple:
    """`(on_main, unmerged, why)`: whether every commit on `branch` has its patch on `main` (`git cherry`).

    `why` is set when the question cannot be answered: a branch that no longer resolves (deleted after a hand merge) is
    not shown to have reached main, so it is not on main here, and the operator's `--ungated` is the remedy."""
    ref = subprocess.run(["git", "-C", str(primary), "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"],
                         capture_output=True, text=True)
    if ref.returncode != 0:
        return False, [], f"the branch `{branch}` no longer resolves in {primary}"
    out = subprocess.run(["git", "-C", str(primary), "cherry", main, branch], capture_output=True, text=True)
    if out.returncode != 0:
        return False, [], f"`git cherry {main} {branch}` failed: {(out.stderr or '').strip()[-200:]}"
    unmerged = [ln[2:].strip() for ln in out.stdout.split("\n") if ln.startswith("+ ")]
    return not unmerged, unmerged, None


def blocked_completion(project_dir: Path, config: dict, artifact_id: str | None,
                       ungated: str | None) -> tuple[dict, str | None]:
    """AD-034-R41 for one held task: `(properties to record, refusal or None)`.

    Evidence is a passing, clean, full `gate_run` of the dispatch branch's tip tree in the primary checkout's store
    (`gate_plan.completion_evidence`), and the task's own branch on that branch (`branch_on_main`). A project that
    declares no dispatch block has no gate to require. The operator's `--ungated REASON` completes it anyway, and the
    reason is recorded on the task (AD-034-R26: a gate that ran nothing is not evidence, so the override says so on its
    face instead of passing for one)."""
    from seldon.core import gate_plan as GP
    from seldon.core import worktree as WT
    from seldon.core.dispatch import DispatchConfigError, load_dispatch_config
    from seldon.core.events import read_events

    if ungated is not None:
        if not ungated.strip():
            return {}, "--ungated needs a reason: it is recorded on the task as the override's grounding"
        return {"completed_ungated": ungated.strip()}, None
    if not config.get("dispatch"):
        return {}, None
    try:
        cfg = load_dispatch_config(project_dir, config)
    except DispatchConfigError as exc:
        return {}, f"{REFUSED_UNGATED}: the dispatch block does not load, so no gate evidence can be read: {exc}"
    primary = WT.anchor(Path(project_dir).resolve())
    events = read_events(primary)
    found = GP.completion_evidence(primary, cfg["branch"], events)
    if found is None:
        return {}, (f"{REFUSED_UNGATED}: this task is blocked, so the dispatcher did not merge it, and no passing full "
                    f"gate is recorded for the tree `{cfg['branch']}` holds now (AD-034-R41). Run `seldon gate main` "
                    f"(or `seldon gate run --full` on {cfg['branch']}) and complete it once that passes, or complete "
                    f"it with `seldon cc complete <file> --ungated \"<reason>\"`, which records the override on the "
                    f"task.")
    branch = task_branch(events, artifact_id) if artifact_id else None
    if branch:
        # REVIEW-001 F-21: main's green says nothing of a branch that never reached it.
        on_main, unmerged, why = branch_on_main(primary, cfg["branch"], branch)
        if not on_main:
            named = ", ".join(c[:12] for c in unmerged[:UNMERGED_SHOWN]) + (
                f" (+{len(unmerged) - UNMERGED_SHOWN} more)" if len(unmerged) > UNMERGED_SHOWN else "")
            detail = why or f"{len(unmerged)} commit(s) on `{branch}` have no patch on `{cfg['branch']}`: {named}"
            return {}, (f"{REFUSED_BRANCH}: this task is blocked and its dispatch branch `{branch}` is not on "
                        f"`{cfg['branch']}` ({detail}; AD-034-R41 as amended by ADDENDUM 15). Land the branch on "
                        f"{cfg['branch']} (merge, rebase or cherry-pick), let the scheduled gate or `seldon gate main` "
                        f"pass on the result, then complete it; or `seldon cc complete <file> --ungated \"<reason>\"`.")
    return {"completion_gate": found.get("event_id")}, None


def r41_completion(project_dir: Path, config: dict, artifact_id: str, current_state: str | None,
                   ungated: str | None) -> tuple[dict, str | None]:
    """AD-034-R41 for every completion: `(properties to record, refusal or None)`.

    Held when the task is `blocked` now, or was blocked after its newest launch (F-04). A project with no dispatch block
    has no dispatcher to have blocked anything, so nothing is read."""
    if not config.get("dispatch"):
        return {}, None
    held = current_state == "blocked"
    if not held and artifact_id:
        from seldon.core import worktree as WT
        from seldon.core.events import read_events
        held = blocked_since_launch(read_events(WT.anchor(Path(project_dir).resolve())), artifact_id)
    if not held:
        return {}, None
    return blocked_completion(project_dir, config, artifact_id, ungated)


def guard(project_dir: Path, artifact_id: str, current_state: str, completion: dict | None) -> dict:
    """The guard on a ResearchTask's move into `completed`: the properties to record with the move, or `R41Refused`.

    `completion` is how the caller completes: None (an ordinary completion, held to R41), `{"by": "merge", "evidence":
    ...}` (the dispatcher's own completion after a merge it made on R26's evidence), or `{"by": "ungated", "reason":
    ...}` (the operator's override, which `seldon cc complete --ungated` alone passes). A project directory with no
    seldon.yaml has no dispatch block and so no gate to require."""
    from seldon.config import load_project_config
    from seldon.core.artifacts import R41Refused

    by = (completion or {}).get("by")
    if by == "merge":
        return {}
    if by not in (None, "ungated"):
        raise R41Refused(f"{REFUSED_UNGATED}: unknown completion {completion!r} (expected `merge` or `ungated`)")
    try:
        config = load_project_config(project_dir) or {}
    except FileNotFoundError:
        return {}
    ungated = (completion or {}).get("reason") or "" if by == "ungated" else None
    props, refusal = r41_completion(project_dir, config, artifact_id, current_state, ungated)
    if refusal:
        raise R41Refused(refusal)
    return props
