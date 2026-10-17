"""Shared scaffolding for QC-002's station tests (AD-037-R6): a scratch project with a dispatch block, a task file
carrying `**Parts:**`, a `dispatch_launched` record and a dispatch log with stream-json usage. No Neo4j, no model call.
"""
from __future__ import annotations

import json
import sys
import textwrap
from datetime import datetime, timedelta, timezone  # noqa: F401 (timedelta re-exported for tests)
from pathlib import Path

import yaml

from seldon.core.events import append_event, make_event, read_events

TASK_ID = "11111111-2222-3333-4444-555555555555"
STEM = "2026-10-14_T-001_planted"
PASS = f"{sys.executable} -c pass"
FAIL = f"{sys.executable} -c \"import sys; sys.exit(1)\""

TASK = textwrap.dedent("""\
    # T-001: a planted task

    **Framework layer served (DN-005 §5 rule 1):** none
    **Spend:** est. 1M tokens. **Network:** none.
    {extra}

    ## Part A: the first part

    Acceptance:
    - `check: {check_a}` passes.

    ## Part B: the second part

    Acceptance:
    - `check: {check_b}` passes.
    - `judgment:` the prose reads as the operator's.
    """)


def make_project(tmp_path: Path, *, check_a: str = PASS, check_b: str = PASS, extra: str = "**Parts:** A 0.5, B 0.5.",
                 stations: dict | None = None, decisions: dict | None = None) -> Path:
    p = tmp_path / "proj"
    (p / "cc_tasks").mkdir(parents=True)
    (p / "logs" / "dispatch").mkdir(parents=True)
    block = {"enabled": True, "branch": "main", "standing_band_ref": "x#y", "poll_interval_s": 300,
             "permission_mode": "bypassPermissions", "stop_file": ".seldon/DISPATCH_STOP", "log_dir": "logs/dispatch",
             "lease_file": ".seldon/dispatch.lock"}
    if stations:
        block["stations"] = stations
    cfg = {"project": {"name": "proj"}, "dispatch": block}
    if decisions:
        cfg["decisions"] = decisions
    (p / "seldon.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    (p / "seldon_events.jsonl").write_text("", encoding="utf-8")
    (p / "cc_tasks" / f"{STEM}.md").write_text(TASK.format(extra=extra, check_a=check_a, check_b=check_b),
                                               encoding="utf-8")
    return p


def config(p: Path) -> dict:
    return yaml.safe_load((p / "seldon.yaml").read_text(encoding="utf-8"))


def launch(p: Path, session_id: str = "child-1", at: datetime | None = None) -> dict:
    ev = make_event("dispatch_launched", "dispatcher", "accepted",
                    {"task_id": TASK_ID, "source_file": f"cc_tasks/{STEM}.md", "child_session_id": session_id,
                     "log_path": f"logs/dispatch/{STEM}.log", "launched_at": _iso(at or _now()),
                     "model": {"role": "primary"}})
    if at:
        ev["timestamp"] = _iso(at)
    append_event(p, ev)
    return ev


def write_log(p: Path, tokens: int) -> None:
    """A dispatch log whose one session used `tokens` (input + cache writes + output), in two messages."""
    half = tokens // 2
    lines = [f"=== {_iso(_now())} | dispatch | claude -p ...",
             json.dumps({"type": "assistant", "message": {"id": "m1", "usage": {
                 "input_tokens": half, "cache_creation_input_tokens": 0, "output_tokens": 0,
                 "cache_read_input_tokens": 999}}}),
             # stream-json repeats a message's usage on each content block; counted once.
             json.dumps({"type": "assistant", "message": {"id": "m1", "usage": {
                 "input_tokens": half, "cache_creation_input_tokens": 0, "output_tokens": 0,
                 "cache_read_input_tokens": 999}}}),
             json.dumps({"type": "assistant", "message": {"id": "m2", "usage": {
                 "input_tokens": 0, "cache_creation_input_tokens": tokens - half - 10, "output_tokens": 10,
                 "cache_read_input_tokens": 1}}})]
    (p / "logs" / "dispatch" / f"{STEM}.log").write_text("\n".join(lines) + "\n", encoding="utf-8")


def record(p: Path, kind: str, payload: dict, actor: str = "cc", at: datetime | None = None) -> dict:
    ev = make_event(kind, actor, "accepted", {"task_id": TASK_ID, **payload})
    if at:
        ev["timestamp"] = _iso(at)
    append_event(p, ev)
    return ev


def events(p: Path, kind: str | None = None) -> list:
    return [e for e in read_events(p) if kind is None or e["event_type"] == kind]


def emitter(p: Path):
    def emit(kind, payload):
        ev = make_event(kind, "dispatcher", "accepted", payload)
        append_event(p, ev)
        return ev
    return emit


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(t: datetime) -> str:
    return t.isoformat().replace("+00:00", "Z")


def ago(seconds: float) -> datetime:
    return _now() - timedelta(seconds=seconds)


def gate(p: Path, cwd: Path | None = None, branch: str | None = None, run=None, task_id: str | None = None) -> dict:
    """What the session's Stop hook records (FRICTION-002 Part C): the declared Parts' checks, run in `cwd` (the
    session's tree; the project by default), as one `stop_gate` record. Returns `stations.stop_gate`'s result."""
    from seldon.core import stations as S
    from seldon.core.dispatch import load_dispatch_config
    evs = events(p)
    tid = task_id or TASK_ID
    kw = {"run": run} if run else {}
    out = S.stop_gate(p, S.last_launch(evs, tid), evs, S.load_stations_config(load_dispatch_config(p)),
                      Path(cwd or p), branch, **kw)
    append_event(p, make_event(S.EVENT_STOP_GATE, "cc", "accepted", out["record"]))
    return out
