"""SEL-014R Part D acceptance: last night's seldon chain replayed through the OODA knowledge source, real model.

    python scripts/sel014r_replay_with_the_model.py --root /tmp/sel014r/replay

`tests/test_sel014r_replay_overnight_chain.py` replays the chain with a deterministic stand-in for the model; this
script makes the same three OODA runs with the model the lock names for `dispatch.ooda.model_role`, so the RESULT can
say what the knowledge source decides on real RESULTs and what each run costs. It is paid work (three sessions of up
to `--token-cap` tokens each), so it is checkpointed (CLAUDE.md section 15):

- **Unit of work:** one OODA run on one `precedes` edge of the overnight chain (NUM-001R -> DESK-004R -> DISP-004R ->
  RECALL-002R), in a detached worktree at the commit that brought the predecessor's RESULT to main, beside symlinks
  to the sibling repositories so Recall reads them.
- **Key:** sha256 of (predecessor id, successor id, replay commit, model id, sha256 of `seldon/core/ooda.py`), so a
  changed prompt or model is never served a stale row.
- **Checkpoint:** one JSON line per finished unit, flushed and fsynced, in `--checkpoint`. Re-running the command is
  the resume: completed keys are skipped.
- **Progress:** every `--progress-s` seconds (default 60) and at each unit boundary, to stdout and `--log`: unit n of
  N, elapsed, the running session's tokens, tokens spent so far.
- **Pilot:** the first unit of a fresh checkpoint. Its measured tokens times the units left is printed as the
  projection, and the run aborts (exit 4) when the projection crosses `--total-token-ceiling`.
- **Ceilings:** per run, `--token-cap` and `--timeout-s` are the knowledge source's own bounds (the holder reaps the
  session); in total, `--total-token-ceiling` and `--wall-ceiling-s` stop new units (exit 3, naming the ceiling).
- **Failures are rows:** an exception in a unit is recorded with its error and the next unit runs.

`--fake-sleep-s` replaces the OODA run with a fake that records each call in `<root>/calls.txt` and sleeps; it exists
for `tests/test_sel014r_replay_script_checkpoint.py`, which SIGKILLs a run mid-unit and resumes it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

SELDON_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SELDON_REPO))

#: The overnight chain (task id, file stem), in order; each consecutive pair is one unit.
CHAIN = [
    ("bacacc4c-9ddc-45bb-b214-0747bd6d2c13", "2026-10-27_NUM-001R_task_numbers_allocated_and_headers_read_from_the_header_block"),
    ("f7a1d2f0-f69b-48d0-87c7-a2187d7d1d03", "2026-10-27_DESK-004R_every_file_the_machine_writes_is_committed_by_the_tool_that_wrote_it"),
    ("2909ce0f-ec55-4da7-8f9b-f2f393933264", "2026-10-27_DISP-004R_a_cross_repo_task_is_pushed_in_every_repository_it_names"),
    ("ff3a4189-1943-4405-a30f-8d3344bb97ad", "2026-10-27_RECALL-002R_recall_turned_on_in_squiddy_arnold_and_ai_readiness_kg"),
]
#: The sibling repositories Recall and the premise checks read, linked beside the replay trees.
SIBLINGS = ("squiddy", "arnold", "ai-readiness-kg", "icsp_notebook")


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def units(model: str) -> list:
    """The three edges, each with its replay commit and key."""
    code = hashlib.sha256((SELDON_REPO / "seldon/core/ooda.py").read_bytes()).hexdigest()
    out = []
    for (pid, pstem), (sid, sstem) in zip(CHAIN, CHAIN[1:]):
        sha = _git(SELDON_REPO, "log", "--diff-filter=A", "--format=%H", "-1", "HEAD", "--",
                   f"cc_tasks/{pstem}_RESULT.md")
        key = hashlib.sha256(json.dumps([pid, sid, sha, model, code]).encode()).hexdigest()
        out.append({"key": key, "pid": pid, "pstem": pstem, "sid": sid, "sstem": sstem, "commit": sha})
    return out


def load_done(path: Path) -> dict:
    if not path.is_file():
        return {}
    return {r["key"]: r for r in (json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln)}


def append(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


class Log:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def __call__(self, msg: str) -> None:
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}"
        print(line, flush=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def _tree(root: Path, clone: Path, u: dict) -> Path:
    tree = root / f"edge_{u['pid'][:8]}"
    if not tree.is_dir():
        _git(clone, "worktree", "add", "-q", "--detach", str(tree), u["commit"])
    return tree


def run_real(root: Path, u: dict, args) -> dict:
    """One OODA run through `seldon.commands.dispatch_ooda.run_one`, the dispatcher's own code."""
    import yaml

    from seldon.commands import dispatch_ooda as DO
    from seldon.core import dispatch as D

    clone = root / "seldon"
    if not clone.is_dir():
        subprocess.run(["git", "clone", "-q", "--shared", "--no-checkout", str(SELDON_REPO), str(clone)], check=True)
    # The siblings are beside the PRIMARY checkout; from a linked worktree, that is the common git dir's parent.
    primary = Path(_git(SELDON_REPO, "rev-parse", "--path-format=absolute", "--git-common-dir")).parent
    for name in SIBLINGS:
        link, real = root / name, primary.parent / name
        if not link.exists() and real.exists():
            link.symlink_to(real)
    tree = _tree(root, clone, u)
    config = yaml.safe_load((tree / "seldon.yaml").read_text(encoding="utf-8"))
    # Served Recall reads each repository's governed export, which a fresh worktree does not carry; the lexical arm
    # reads the same repositories' files and is what this replay uses.
    if isinstance(config.get("recall"), dict):
        config["recall"].setdefault("served", {})["enabled"] = False
    cfg = D.load_dispatch_config(tree, config)
    cfg["ooda_grace_s"] = args.timeout_s
    cfg["ooda"] = {**cfg["ooda"], "enabled": True, "token_cap": args.token_cap}
    pred = {"artifact_id": u["pid"], "state": "completed", "name": u["pstem"],
            "source_file": f"cc_tasks/{u['pstem']}.md"}
    succ = {"artifact_id": u["sid"], "state": "proposed", "name": u["sstem"],
            "source_file": f"cc_tasks/{u['sstem']}.md", "predecessors": [pred]}
    out = DO.run_one(tree, config, cfg, None, {"predecessor": pred, "successors": [succ], "completed_at": None})
    p = out["payload"]
    addenda = {rel: (tree / rel).read_text(encoding="utf-8") for rel in p.get("addenda") or []}
    return {"kind": out["kind"], "note": p.get("note"), "reason": p.get("reason"), "detail": p.get("detail"),
            "question": p.get("question"), "answering_note": p.get("answering_note"), "addenda": addenda,
            "tokens": p["session"].get("tokens"), "cache_read": p["session"].get("cache_read"),
            "seconds": p["session"].get("seconds"), "model": p["session"].get("model"),
            "log": str(tree / p["session"]["log"])}


def run_fake(root: Path, u: dict, args) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    with (root / "calls.txt").open("a", encoding="utf-8") as fh:
        fh.write(u["key"] + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    time.sleep(args.fake_sleep_s)
    return {"kind": "ooda_ok", "note": "fake", "tokens": 1000, "seconds": 0.0, "model": "fake"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--checkpoint", type=Path, default=None)
    ap.add_argument("--log", type=Path, default=None)
    ap.add_argument("--token-cap", type=int, default=300_000)
    ap.add_argument("--timeout-s", type=float, default=1800)
    ap.add_argument("--total-token-ceiling", type=int, default=900_000)
    ap.add_argument("--wall-ceiling-s", type=float, default=5400)
    ap.add_argument("--progress-s", type=float, default=60)
    ap.add_argument("--fake-sleep-s", type=float, default=None)
    args = ap.parse_args(argv)
    ckpt = args.checkpoint or args.root / "checkpoint.jsonl"
    log = Log(args.log or args.root / "progress.txt")
    if args.fake_sleep_s is None:
        from seldon import models
        model = models.launch_spec_for("primary")["model"]
        run = run_real
    else:
        model, run = "fake", run_fake
    todo = units(model)
    done = load_done(ckpt)
    spent = sum(int(r.get("tokens") or 0) for r in done.values())
    fresh = not done
    started = time.monotonic()
    log(f"replay: {len(todo)} unit(s), {sum(u['key'] in done for u in todo)} done, {spent} tokens spent, model {model}")
    for n, u in enumerate(todo, 1):
        if u["key"] in done:
            log(f"unit {n}/{len(todo)} {u['pid'][:8]}: done, skipped (resume)")
            continue
        if spent >= args.total_token_ceiling:
            log(f"ABORT: total token ceiling {args.total_token_ceiling} reached ({spent})")
            return 3
        if time.monotonic() - started >= args.wall_ceiling_s:
            log(f"ABORT: wall-clock ceiling {args.wall_ceiling_s}s reached")
            return 3
        log(f"unit {n}/{len(todo)} {u['pid'][:8]} -> {u['sid'][:8]} at {u['commit'][:8]}: start")
        stop = threading.Event()
        session_log = args.root / f"edge_{u['pid'][:8]}" / "logs" / "dispatch" / f"{u['pstem']}.ooda.log"

        def progress():
            from seldon.core.stations import session_tokens
            while not stop.wait(args.progress_s):
                now = session_tokens(session_log).get("tokens") if session_log.is_file() else None
                log(f"  unit {n}/{len(todo)} running {round(time.monotonic() - started)}s elapsed, session tokens "
                    f"{now}, spent before it {spent}")
        t = threading.Thread(target=progress, daemon=True)
        t.start()
        unit_start = time.monotonic()
        try:
            row = run(args.root, u, args)
        except Exception as exc:              # a failed unit is a row, never the end of the run (section 15.7)
            row = {"kind": "error", "error": f"{type(exc).__name__}: {exc}"}
        finally:
            stop.set()
        row = {**{k: u[k] for k in ("key", "pid", "sid", "commit")}, **row,
               "wall_s": round(time.monotonic() - unit_start, 1)}
        append(ckpt, row)
        spent += int(row.get("tokens") or 0)
        log(f"unit {n}/{len(todo)} {u['pid'][:8]}: {row['kind']}"
            + (f" ({row.get('reason')}: {row.get('detail')})" if row.get("reason") else "")
            + f", {row.get('tokens')} tokens, {row['wall_s']}s; spent {spent}")
        if fresh and n == 1:
            left = len(todo) - 1
            projected = spent + int(row.get("tokens") or 0) * left
            log(f"pilot: {row.get('tokens')} tokens and {row['wall_s']}s per unit (measured); projected total "
                f"{projected} tokens for {len(todo)} units, about {round(row['wall_s'] * len(todo))}s")
            if projected > args.total_token_ceiling:
                log(f"ABORT: the pilot projects {projected} > total token ceiling {args.total_token_ceiling}")
                return 4
    rows = load_done(ckpt)
    kinds = [rows[u["key"]]["kind"] for u in todo if u["key"] in rows]
    log(f"replay done: n={len(kinds)} {kinds}, {sum(int(r.get('tokens') or 0) for r in rows.values())} tokens")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
