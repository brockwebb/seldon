"""AD-038-R16 (SEL-014R): the dispatcher launches the OODA knowledge source and records its verdict.

`docs/design/AD-038_ADDENDUM_07_the_ooda_as_a_knowledge_source.md`. The brief, the verdict and the records are
`seldon.core.ooda`'s; this module is the launch, under the pass lease: the same CLI, model lock, environment and
detached run (`seldon.commands.dispatch._run`) a task session gets, with `--worktree` for the CLI's hard isolation,
no Stop gate (an OODA has no Parts; its one gate is a verdict the dispatcher can check), and a holder-side bound on
wall clock (`dispatch.ooda_grace_s`) and tokens (`dispatch.ooda.token_cap`).

The session writes nothing to the primary. The dispatcher copies an addendum the session wrote in its worktree,
commits it through the hooks, and only then writes the record, so nothing can launch the successor without it.
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path

import click

from seldon import models
from seldon.core import dispatch as D
from seldon.core import ooda as O
from seldon.core import stations as QS
from seldon.core import worktree as WT
from seldon.core.events import read_events

#: The OODA session's log, beside the task logs under `dispatch.log_dir`: `<predecessor stem>.ooda.log`.
LOG_SUFFIX = ".ooda.log"

#: The settings an OODA session launches with: the worktree is cut from main's HEAD (FRICTION-002's reason), and no
#: hooks, because the Stop gate checks a task's Parts and an OODA has none.
SESSION_SETTINGS = {"worktree": {"baseRef": "head"}}


def fire(project_dir: Path, config: dict, cfg: dict, session_id, tasks: list, runner=None) -> list:
    """Run the OODAs due now, oldest completion first, at most `dispatch.ooda.max_per_pass`. Returns the records."""
    idx = D.ooda_index(read_events(project_dir))
    items = O.due(tasks, idx["latest"], idx["completed_at"],
                  lambda p: D._ooda_file_state(project_dir, p.get("source_file"))[2])
    out = []
    for item in items[: cfg["ooda"]["max_per_pass"]]:
        out.append(run_one(project_dir, config, cfg, session_id, item, runner=runner))
    if len(items) > len(out):
        click.echo(f"ooda: {len(items) - len(out)} more due; the next pass runs them")
    return out


def _review(cfg: dict):
    scfg = QS.load_stations_config(cfg)
    return lambda project_dir, text: QS.review_premises(Path(project_dir), text, scfg)


def _recall(project_dir: Path, config: dict):
    from seldon.core import recall as RC

    def hits(text: str, stem: str, task_id: str) -> tuple:
        try:
            if RC.settings(config) is None:
                return [], "recall is off in this project (no `recall:` block)"
            r = RC.recall(Path(project_dir), config, text, task_stem=stem, task_id=task_id)
        except RC.RecallError as exc:
            return [], f"recall unavailable: {exc}"
        return [h.line() for h in r.hits], ("; ".join(r.notes) or None)
    return hits


def cli_worktree_root(project_dir: Path) -> Path:
    """Where `claude --worktree` cuts its worktrees: `.claude/worktrees` under the repository's MAIN working tree,
    which is the project for a dispatcher in the primary checkout and the common git dir's parent for one run from a
    linked worktree (SEL-014R's replay found the second: a session's addendum was looked for under the linked tree)."""
    common = WT.git(Path(project_dir), "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()
    main = Path(common).parent if common else Path(project_dir)
    return (main / D.CLI_WORKTREE_DIR).resolve()


def _cleanup(project_dir: Path, wt: Path | None, base: str | None) -> dict:
    """Remove the session's worktree and branch when the session committed nothing on it; keep and say so otherwise."""
    if wt is None or not wt.is_dir():
        return {"worktree": None}
    rel = str(wt.relative_to(Path(project_dir).resolve())) if wt.is_relative_to(Path(project_dir).resolve()) else str(wt)
    branch = WT.git(wt, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    ahead = WT.git(Path(project_dir), "rev-list", "--count", f"{base}..{branch}") if base and branch else None
    commits = int(ahead.stdout.strip()) if ahead is not None and ahead.returncode == 0 else None
    if commits != 0:
        return {"worktree": rel, "branch": branch, "kept": True,
                "why": f"{commits} commit(s) on its branch" if commits else "its branch could not be measured"}
    out = WT.remove(Path(project_dir), wt)
    if not out["worktree_removed"]:
        return {"worktree": rel, "branch": branch, "kept": True, "why": out["stderr"]}
    gone = WT.git(Path(project_dir), "branch", "-d", branch)
    return {"worktree": rel, "branch": branch, "kept": False, "branch_deleted": gone.returncode == 0}


def run_one(project_dir: Path, config: dict, cfg: dict, session_id, item: dict, runner=None) -> dict:
    """One OODA: brief, launch, bound, read the verdict, apply an addendum, record. Returns `{kind, payload}`."""
    from seldon.commands import dispatch as S
    from seldon.commands import dispatch_worktree as W

    project_dir = Path(project_dir)
    ocfg = cfg["ooda"]
    b = O.brief(project_dir, config, item, _review(cfg), _recall(project_dir, config))
    pred = b["predecessor"]
    stem = Path(pred["file"] or pred["task_id"]).stem
    log_dir = D.config_path(project_dir, cfg["log_dir"])
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{stem}{LOG_SUFFIX}"
    spec = models.launch_spec_for(ocfg["model_role"])
    cmd = S._launch_cmd(cfg, O.prompt(b) + "\n\n" + S.HEADLESS_CLAUSE, spec, worktree=True,
                        settings=SESSION_SETTINGS)
    child_session_id = str(uuid.uuid4())
    base = WT.rev(project_dir, "HEAD")
    offset = S._log_offset(log_path)
    timeout_s, cap = float(cfg["ooda_grace_s"]), int(ocfg["token_cap"])
    started = time.monotonic()
    reaped: dict = {}
    init_box: dict = {}

    def inspector():
        if time.monotonic() - started > timeout_s:
            return {"reap": {"reason": "timeout", "limit": timeout_s}}
        used = QS.session_tokens(log_path).get("tokens") or 0
        if used > cap:
            return {"reap": {"reason": "token_cap", "limit": cap, "tokens": used}}
        return None

    def on_reap(reap, pid, sig):
        reaped.update({**reap, "pid": pid, "signal": sig})

    click.echo(f"ooda: {pred['task_id'][:8]} {pred['file']} -> {D.config_rel(project_dir, log_path)}")
    code = (runner or S._run)(cmd, project_dir, log_path, child_session_id,
                              extra_env=S._worktree_env(project_dir, spec, cfg), inspector=inspector,
                              inspect_every_s=float(ocfg["inspect_every_s"]), on_reap=on_reap,
                              on_init=lambda init: init_box.update(init=init))
    wall = round(time.monotonic() - started, 3)
    init = init_box.get("init") or W.cli_init(log_path, offset)
    wt = Path(init["cwd"]).resolve() if init and init.get("cwd") else None
    if wt is not None and (project_dir.resolve() == wt or not wt.is_relative_to(cli_worktree_root(project_dir))):
        wt = None
    toks = QS.session_tokens(log_path)
    session = {"log": D.config_rel(project_dir, log_path), "child_session_id": child_session_id, "exit": code,
               "seconds": wall, "tokens": toks.get("tokens"), "cache_read": toks.get("cache_read"),
               "model": spec["model"], "role": spec["role"], "timeout_s": timeout_s, "token_cap": cap}

    with log_path.open("r", encoding="utf-8", errors="replace") as fh:
        fh.seek(offset)
        segment = fh.read()
    envelope = models.last_result_envelope(segment) or {}
    kind, verdict, reason, detail, addenda, commit = O.OODA_EXPIRED, None, None, None, None, None
    if reaped:
        reason, detail = reaped["reason"], f"reaped by {reaped.get('signal')} past {reaped.get('limit')}"
    elif not W.reached_model(log_path, offset):
        reason, detail = "launch_failed", W.launch_stderr_line(log_path, offset)
    elif code != 0:
        reason, detail = "exit_nonzero", f"exit {code}"
    else:
        verdict = O.parse_verdict(envelope.get("result") if isinstance(envelope.get("result"), str) else None)
        if not verdict["ok"]:
            reason, detail = verdict["reason"], verdict["detail"]
        elif verdict["verdict"] == "amended":
            checked = O.check_addenda(b, verdict["addenda"], wt, project_dir)
            if not checked["ok"]:
                reason, detail = checked["reason"], checked["detail"]
            else:
                kind, addenda, commit, reason, detail = _land_addenda(project_dir, pred, checked["files"])
        else:
            kind = O.VERDICTS[verdict["verdict"]]
    session.update(_cleanup(project_dir, wt, base))
    payload = O.record_payload(b, kind, verdict=verdict, reason=reason, detail=detail, session=session,
                               addenda=addenda, commit=commit)
    S._emit(project_dir, session_id, kind, payload)
    click.echo(f"ooda: {pred['task_id'][:8]} {kind}" + (f" ({reason}: {detail})" if reason else "")
               + f", {session['tokens']} tokens, {wall}s")
    return {"kind": kind, "payload": payload}


def _land_addenda(project_dir: Path, pred: dict, files: list) -> tuple:
    """Copy the session's addenda into the primary and commit them through the hooks, BEFORE the record.

    `(kind, addenda, commit, reason, detail)`: `ooda_amended` on a commit; `ooda_expired`
    (`addendum_commit_refused`) with the files removed again when the hooks refuse, so no untracked file is left for
    c7 and the successor runs as written."""
    rels = [f["rel"] for f in files]
    for f in files:
        (project_dir / f["rel"]).write_bytes(f["data"])
    done = D.commit_paths(project_dir, rels, f"ooda: {', '.join(rels)} written by the OODA knowledge source on "
                                             f"{pred['task_id'][:8]} {pred['file']} (AD-038-R16)")
    if not done["committed"]:
        for rel in rels:
            (project_dir / rel).unlink(missing_ok=True)
        return O.OODA_EXPIRED, None, None, "addendum_commit_refused", done.get("stderr") or done.get("reason")
    return O.OODA_AMENDED, rels, done["commit"], None, None
