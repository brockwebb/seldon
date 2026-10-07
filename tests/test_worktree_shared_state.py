"""SEL-004 decisions 5 and 6: state that must stay ONE across worktrees.

`cc_tasks/2026-10-07_SEL-004_worktree_per_task_dispatch.md`:

* **Decision 5, one spend ledger.** Every worktree resolves the ledger to the primary
  checkout's path (`seldon.core.worktree.primary_checkout`) and appends under an exclusive
  flock on the file (`seldon.core.worktree.locked`, the discipline ai-readiness-kg's
  `kg/spend.py` uses), so parallel runs share one daily cap. Tested with two processes in two
  worktrees reserving against one cap. The pass then commits the appended lines
  (`dispatch.shared_paths`), and the file is not c7's dirt.
* **Decision 6, Seldon's own graph writes.** Two worktrees run `seldon cc register` and
  `seldon cc complete` at the same time against one scratch database; the graph is consistent
  and, after both branches merge, both sets of events are in `seldon_events.jsonl`.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from seldon.commands.dispatch import dispatch_group
from seldon.core import worktree as WT
from seldon.domain.loader import load_domain_config
from tests.dispatch_scaffold import (
    NEO4J_DB, RESEARCH_YAML, SELDON_REPO, add_task, git, make_project, register, run_cli,
)

CAP = 300
STEP = 10
TRIES = 40

RESERVER = r'''
import json, os, sys, time
from pathlib import Path
sys.path.insert(0, {repo!r})
from seldon.core.worktree import locked, primary_checkout
ledger = primary_checkout(Path.cwd()) / "state" / "spend_ledger.jsonl"
while not Path({go!r}).exists():
    time.sleep(0.01)
granted = 0
for i in range({tries}):
    with locked(ledger) as fh:
        fh.seek(0)
        used = sum(json.loads(l)["tokens"] for l in fh if l.strip())
        if used + {step} <= {cap}:
            time.sleep(0.002)   # widen the read-to-append window a race would need
            fh.write(json.dumps({{"who": sys.argv[1], "i": i, "tokens": {step}}}) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
            granted += 1
print(granted)
'''


def _ledger_repo(tmp_path):
    p = make_project(tmp_path)
    (p / "state").mkdir()
    (p / "state" / "spend_ledger.jsonl").write_text("")
    git(p, "add", "state/spend_ledger.jsonl")
    git(p, "commit", "-q", "-m", "ledger")
    for name in ("wa", "wb"):
        assert WT.add(p, p / ".worktrees" / name, f"task/{name}", "HEAD")["ok"]
    return p


def test_primary_checkout_resolves_the_same_path_from_every_worktree(tmp_path):
    p = _ledger_repo(tmp_path)
    assert WT.primary_checkout(p) == p.resolve()
    assert WT.primary_checkout(p / ".worktrees" / "wa") == p.resolve()
    assert WT.primary_checkout(p / ".worktrees" / "wb" / "state") == p.resolve()
    with pytest.raises(WT.WorktreeError):
        WT.primary_checkout(tmp_path)


def test_the_ledger_lock_holds_under_two_processes_in_two_worktrees(tmp_path):
    """Two processes, one per worktree, each try 40 reservations of 10 against a cap of 300.
    Exactly 30 are granted in total, every one in the primary's ledger, none in either
    worktree's own copy: one cap, not one per worktree (DD-019 at worktree grain)."""
    p = _ledger_repo(tmp_path)
    go = tmp_path / "go"
    script = tmp_path / "reserve.py"
    script.write_text(RESERVER.format(repo=str(SELDON_REPO), go=str(go), tries=TRIES,
                                      step=STEP, cap=CAP))
    procs = [subprocess.Popen([sys.executable, str(script), name],
                              cwd=p / ".worktrees" / name, stdout=subprocess.PIPE, text=True)
             for name in ("wa", "wb")]
    time.sleep(0.5)
    go.write_text("go")
    granted = [int(proc.communicate(timeout=60)[0].strip()) for proc in procs]

    lines = [json.loads(ln) for ln in
             (p / "state" / "spend_ledger.jsonl").read_text().splitlines() if ln.strip()]
    assert sum(granted) == CAP // STEP == len(lines)
    assert sum(ln["tokens"] for ln in lines) == CAP
    assert all(g > 0 for g in granted), granted
    for name in ("wa", "wb"):
        assert (p / ".worktrees" / name / "state" / "spend_ledger.jsonl").read_text() == ""


@pytest.mark.usefixtures("neo4j_available")
def test_the_pass_commits_shared_ledger_appends_and_does_not_wait_on_them(
        tmp_path, neo4j_driver, clean_test_db, monkeypatch):
    """`dispatch.shared_paths`: lines a worktree session appended in the primary are committed
    by the next pass under the file's flock, and are not the dirt c7 waits on."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p = make_project(tmp_path, dispatch_extra={
        "max_parallel": 2, "gate_command": "true",
        "shared_paths": ["state/spend_ledger.jsonl"]})
    (p / "state").mkdir()
    (p / "state" / "spend_ledger.jsonl").write_text('{"tokens": 1}\n')
    git(p, "add", "state/spend_ledger.jsonl")
    git(p, "commit", "-q", "-m", "ledger")
    with WT.locked(p / "state" / "spend_ledger.jsonl") as fh:
        fh.write('{"tokens": 2}\n')
    out = run_cli(p, dispatch_group, ["once"]).output
    assert "shared: state/spend_ledger.jsonl 1 line(s) ->" in out, out
    assert git(p, "status", "--porcelain").stdout == ""
    assert git(p, "show", "HEAD:state/spend_ledger.jsonl").stdout == (
        '{"tokens": 1}\n{"tokens": 2}\n')

    # An in-place edit is reported and left, never committed under the dispatcher's name.
    (p / "state" / "spend_ledger.jsonl").write_text('{"tokens": 9}\n')
    out = run_cli(p, dispatch_group, ["once"]).output
    assert "NOT committed: not append-only against HEAD" in out


# ====================================================================== decision 6

def _seldon(cwd: Path, *argv) -> subprocess.Popen:
    env = {**os.environ, "PYTHONPATH": str(SELDON_REPO)}
    return subprocess.Popen([sys.executable, "-m", "seldon", *argv], cwd=cwd, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def _run_all(procs):
    outs = [proc.communicate(timeout=120)[0] for proc in procs]
    for proc, out in zip(procs, outs):
        assert proc.returncode == 0, out
    return outs


@pytest.mark.usefixtures("neo4j_available")
def test_two_worktrees_register_and_complete_concurrently(tmp_path, neo4j_driver,
                                                          clean_test_db):
    """Worktree A registers three new task files while worktree B completes three registered
    tasks, at the same time, against one database. The graph holds each new task once and each
    completed task completed; after both branches rebase and fast-forward, main's event store
    is valid JSONL with unique ids and carries every one of those events."""
    dc = load_domain_config(RESEARCH_YAML)
    p = make_project(tmp_path)
    done = []
    for i in range(3):
        add_task(p, f"done{i}", "Implements AD-001.\n")
        done.append(register(p, neo4j_driver, dc, f"done{i}", f"2026-10-07T00:00:0{i}Z"))
    git(p, "commit", "-q", "-m", "registrations", "--", "seldon_events.jsonl")
    wa, wb = p / ".worktrees" / "wa", p / ".worktrees" / "wb"
    assert WT.add(p, wa, "task/wa", "HEAD")["ok"] and WT.add(p, wb, "task/wb", "HEAD")["ok"]
    for i in range(3):
        add_task(wa, f"new{i}", "Implements AD-001.\n", commit=False)
        git(wa, "add", f"cc_tasks/new{i}.md")   # `cc register` refuses a file git cannot recover

    script_a = " && ".join(f"{sys.executable} -m seldon cc register cc_tasks/new{i}.md"
                           for i in range(3))
    script_b = " && ".join(f"{sys.executable} -m seldon cc complete cc_tasks/done{i}.md"
                           for i in range(3))
    env = {**os.environ, "PYTHONPATH": str(SELDON_REPO)}
    procs = [subprocess.Popen(["/bin/sh", "-c", script], cwd=cwd, env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
             for script, cwd in ((script_a, wa), (script_b, wb))]
    _run_all(procs)

    with neo4j_driver.session(database=NEO4J_DB) as s:
        rows = {r["src"]: (r["n"], r["states"]) for r in s.run(
            "MATCH (t:ResearchTask) RETURN t.source_file AS src, count(*) AS n, "
            "collect(t.state) AS states")}
    for i in range(3):
        assert rows[f"cc_tasks/done{i}.md"] == (1, ["completed"])
        assert rows[f"cc_tasks/new{i}.md"] == (1, ["proposed"])

    # Each session commits its own store, as a session does at the end of its task.
    for wt in (wa, wb):
        git(wt, "add", "-A")
        git(wt, "commit", "-q", "-m", f"{wt.name}: session end")
    for wt, branch in ((wa, "task/wa"), (wb, "task/wb")):
        assert WT.rebase(wt, WT.rev(p, "main"))["ok"]
        git(p, "merge", "--ff-only", "-q", branch)
    store = git(p, "show", "main:seldon_events.jsonl").stdout.encode()
    assert WT.check_union_text(store, "event_id")["ok"]
    events = [json.loads(ln) for ln in store.decode().splitlines() if ln.strip()]
    created = {e["payload"]["properties"]["source_file"] for e in events
               if e["event_type"] == "artifact_created"
               and e["payload"].get("artifact_type") == "ResearchTask"}
    completed = {e["payload"]["artifact_id"] for e in events
                 if e["event_type"] == "artifact_state_changed"
                 and e["payload"]["to_state"] == "completed"}
    assert {f"cc_tasks/new{i}.md" for i in range(3)} <= created
    assert set(done) <= completed


def test_check_union_text_names_malformed_lines_and_duplicate_ids():
    data = b'{"event_id": "a"}\n{"event_id": "b"}{"event_id": "c"}\n\n{"event_id": "a"}\n[1]\n'
    assert WT.check_union_text(data, "event_id") == {"ok": False, "malformed": [2, 5],
                                                     "duplicates": ["a"]}
    assert WT.check_union_text(b'{"x": 1}\n{"x": 1}\n', "event_id")["ok"] is True


def test_check_union_text_against_a_base_reports_only_what_the_branch_added():
    """Review finding: a duplicate or malformed line already on main must not block every
    task that appends to the store; only lines the merge added are the task's."""
    base = b'{"event_id": "a"}\n{"event_id": "a"}\nnot json\n'
    merged = base + b'{"event_id": "b"}\n'
    assert WT.check_union_text(merged, "event_id", base=base)["ok"] is True
    bad = base + b'{"event_id": "b"}\n{"event_id": "b"}\n{"event_id": "a"}\nbroken{\n'
    assert WT.check_union_text(bad, "event_id", base=base) == {
        "ok": False, "malformed": [7], "duplicates": ["b", "a"]}
