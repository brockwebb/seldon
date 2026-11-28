"""SEL-060 Parts A and C (AD-031-R4, R7): recall's use counted from the sessions' logs, and replayed.

The first two counts of Part A were wrong in ways these tests pin: a glob like `./.git/*` counted as opening every
hit (91.6% "opened"), and a RESULT's own `Recall used:` line, written with Write, counted as reading the hits it
named. `seldon.core.recall_audit` does not exist on main before SEL-060, so every test here fails there.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
import yaml

from seldon.core import recall_audit as A

HIT_RESULT = "demo:2026-01-02_TASK-002_beta_RESULT"
HIT_OTHER = "demo:2026-01-03_TASK-003_gamma_RESULT"


def _line(obj: dict) -> str:
    return json.dumps(obj) + "\n"


def _tool(name: str, inp: dict) -> str:
    return _line({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": inp}]}})


def _log(path: Path, ts: str, hits: list, tools: list) -> None:
    head = (f"=== {ts} | dispatch | claude -p 'Recall (RECALL-001): registration searched the repositories' own "
            "history for this task.\n")
    body = "".join(f"  - result  {h}  2026-01-02  headline\n" for h in hits)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(head + body + "\nRead CLAUDE.md, then execute it.'\n" + "".join(tools), encoding="utf-8")


def _event(event_type: str, payload: dict, ts: str) -> str:
    return _line({"event_id": str(uuid.uuid4()), "event_type": event_type, "timestamp": ts, "actor": "t",
                  "authority": "accepted", "session_id": "s", "payload": payload})


def test_the_header_is_what_was_handed_and_writes_are_not_reads(tmp_path: Path):
    log = tmp_path / "x.log"
    _log(log, "2026-02-01T10:00:00Z", [HIT_RESULT, HIT_OTHER], [
        _tool("Write", {"file_path": "/w/cc_tasks/x_RESULT.md", "content": f"Recall used: {HIT_RESULT}"}),
        _tool("Bash", {"command": "find . -maxdepth 3 -not -path './.git/*' | head"}),
    ])
    s = A.parse_log(log)
    assert list(s.handed) == [HIT_RESULT, HIT_OTHER] and s.recall_block
    assert len(s.inputs) == 1  # the Write is not an input a read is looked for in
    assert A.opened({"id": HIT_RESULT, "kind": "result"}, s.inputs) == (False, False)


@pytest.mark.parametrize("command, universe, expect", [
    ("cat cc_tasks/2026-01-02_TASK-002_beta_RESULT.md", frozenset(), True),
    ("cat cc_tasks/2026-01-02_TASK-002_*", frozenset(), True),
    ("cat cc_tasks/*_RESULT*.md", frozenset(), False),  # too few literal characters
    ("cat cc_tasks/2026-01-0*", frozenset(f"2026-01-0{i}_TASK-00{i}_x.md" for i in range(1, 6))
     | {"2026-01-02_TASK-002_beta_RESULT.md"}, False),  # a sweep of six files
    ("ls cc_tasks | grep TASK-002", frozenset(), False),
])
def test_what_counts_as_opening_a_result(command, universe, expect):
    inputs = [json.dumps({"command": command})]
    assert A.opened({"id": HIT_RESULT, "kind": "result"}, inputs, universe)[0] is expect


def test_issues_and_decisions_open_by_id():
    inputs = [json.dumps({"command": "seldon issue show 1a2b3c4d"}), json.dumps({"pattern": "AD-031-R3"})]
    assert A.opened({"id": "demo:issue-1a2b3c4d", "kind": "issue"}, inputs)[0]
    assert A.opened({"id": "demo:AD-031-R3", "kind": "decision"}, inputs)[0]
    assert not A.opened({"id": "demo:AD-031-R30", "kind": "decision"}, inputs)[0]
    note = [json.dumps({"file_path": "/r/docs/design/AD-031_note.md"})]
    assert A.opened({"id": "demo:AD-031-R4", "kind": "decision", "path": "docs/design/AD-031_note.md"}, note) \
        == (False, True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "demo"
    (root / "cc_tasks").mkdir(parents=True)
    (root / "seldon.yaml").write_text(yaml.safe_dump({"project": {"name": "demo"},
                                                      "dispatch": {"log_dir": "logs/dispatch"}}))
    stem = "2026-02-01_TASK-010_frob"
    (root / "cc_tasks" / f"{stem}.md").write_text("# TASK-010\nFollows TASK-002.\n")
    (root / "cc_tasks" / f"{stem}_RESULT.md").write_text(f"# RESULT\nRecall used: {HIT_RESULT}\n")
    (root / "cc_tasks" / "2026-01-02_TASK-002_beta_RESULT.md").write_text("# RESULT: TASK-002\n")
    (root / "cc_tasks" / "2026-01-03_TASK-003_gamma_RESULT.md").write_text("# RESULT: TASK-003\n")
    hits = [{"id": HIT_RESULT, "kind": "result", "path": "cc_tasks/2026-01-02_TASK-002_beta_RESULT.md",
             "shared_terms": ["a"] * 5, "arms": ["lexical"]},
            {"id": HIT_OTHER, "kind": "result", "path": "cc_tasks/2026-01-03_TASK-003_gamma_RESULT.md",
             "shared_terms": ["a"] * 9, "arms": ["lexical", "served"]}]
    (root / "seldon_events.jsonl").write_text(
        _event("recall_listed", {"task_id": "t-10", "source_file": f"cc_tasks/{stem}.md", "hits": hits},
               "2026-02-01T09:00:00Z"))
    _log(root / "logs" / "dispatch" / f"{stem}.log", "2026-02-01T10:00:00Z", [HIT_RESULT, HIT_OTHER],
         [_tool("Read", {"file_path": f"/x/cc_tasks/2026-01-02_TASK-002_beta_RESULT.md"})])
    # A gate log beside it is not a session.
    (root / "logs" / "dispatch" / f"{stem}.gate.log").write_text("=== 2026-02-01T11:00:00Z | gate | pytest\n")
    return root


def test_one_repository_counted(repo: Path):
    out = A.audit_repository("demo", repo)
    assert len(out["sessions"]) == 1
    s = out["sessions"][0]
    assert s["result"] == "used"
    fates = {h["id"]: (h["opened"], h["used"], h["cited"]) for h in s["hits"]}
    assert fates == {HIT_RESULT: (True, True, True), HIT_OTHER: (False, False, False)}
    t = A.tables([out])
    assert (t["total"]["handed"], t["total"]["opened"], t["total"]["used"]) == (2, 1, 1)
    assert t["by_cited"]["cited result"]["opened"] == 1 and t["by_cited"]["not cited result"]["opened"] == 0
    assert set(t["by_arms"]) == {"lexical", "lexical+served"}
    assert "| **all** | 1 | 2 | 1 | 50.0% |" in A.render_markdown(t, [out])


def test_a_repository_without_recall_or_logs_is_named(tmp_path: Path):
    root = tmp_path / "bare"
    root.mkdir()
    (root / "seldon.yaml").write_text("project: {name: bare}\n")
    (root / "seldon_events.jsonl").write_text("")
    assert A.audit_repository("bare", root)["notes"] == ["no dispatch log directory"]


def test_repositories_come_from_the_one_list(tmp_path: Path):
    (tmp_path / "factory").mkdir()
    (tmp_path / "factory" / "seldon.yaml").write_text(yaml.safe_dump({"portfolio": {"repositories":
                                                                      {"demo": "../demo", "factory": "."}}}))
    got = A.resolve_ref_map("factory/seldon.yaml#portfolio.repositories", tmp_path)
    assert got == {"demo": (tmp_path / "demo").resolve(), "factory": (tmp_path / "factory").resolve()}
    with pytest.raises(A.AuditError, match="has no"):
        A.resolve_ref_map("factory/seldon.yaml#portfolio.nope", tmp_path)
    with pytest.raises(A.AuditError, match="not set"):
        A.registered_repositories(tmp_path, {"recall": {}})


# ------------------------------------------------------------------------------------------- Part C: the replay

BLOCK = {"top_n": 8, "min_shared_terms": 2, "max_file_bytes": 2000000, "headline_chars": 120,
         "result_globs": ["cc_tasks/*_RESULT*.md"], "failure_terms": ["fail"], "bm25": {"k1": 1.2, "b": 0.75},
         "served": {"enabled": False, "k": 20, "rrf_k": 60, "graphs": {}}}
SELECTION = {"mode": "touch", "noise_paths": ["cc_tasks/*"], "max_citing_share": 1.0, "max_tasks_per_file": 5,
             "max_file_hits": 1, "max_issue_hits": 0, "dead_end_days": 30,
             "lexical_min_shared_terms": {"result": None}}


def _replay_repo(tmp_path: Path, n: int, result_date: str = "2026-01-02T12:00:00Z") -> Path:
    """SEL-063 (REVIEW-001 F-25): the RESULT's landing is its commit's time, so the commit is dated."""
    root = tmp_path / "demo"
    (root / "cc_tasks").mkdir(parents=True)
    (root / "seldon.yaml").write_text(yaml.safe_dump({"project": {"name": "demo"},
                                                      "dispatch": {"log_dir": "logs/dispatch"}}))
    (root / "seldon_events.jsonl").write_text("")
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    (root / "cc_tasks" / "2026-01-02_TASK-002_beta_RESULT.md").write_text("# RESULT: TASK-002\n")
    os.utime(root / "cc_tasks" / "2026-01-02_TASK-002_beta_RESULT.md", (1, 1))
    for i in range(n):
        stem = f"2026-02-{i + 1:02d}_TASK-1{i:02d}_t"
        (root / "cc_tasks" / f"{stem}.md").write_text("# TASK\nFollows TASK-002.\n")
        _log(root / "logs" / "dispatch" / f"{stem}.log", f"2026-02-{i + 1:02d}T10:00:00Z", [],
             [_tool("Read", {"file_path": "/x/cc_tasks/2026-01-02_TASK-002_beta_RESULT.md"})])
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=root, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_DATE": result_date, "GIT_COMMITTER_DATE": result_date})
    return root


def test_replay_reports_both_selections(tmp_path: Path):
    root = _replay_repo(tmp_path, 2)
    rows = A.replay_repository("demo", root, BLOCK, SELECTION, 30, tmp_path / "ck.jsonl", progress=lambda m: None)
    assert [r["old_source"] for r in rows] == ["replayed", "replayed"]
    assert all(r["new"][0]["id"] == HIT_RESULT and r["new"][0]["opened"] for r in rows)
    assert all(r["consulted"] == ["2026-01-02_TASK-002_beta_RESULT.md"] for r in rows)
    s = A.replay_summary(rows)["demo"]
    assert (s["tasks"], s["new_opened"], s["consulted_in_new"]) == (2, 2, 2)


def test_a_result_that_landed_after_the_launch_is_not_found(tmp_path: Path):
    # Committed after the 2026-02 launch (SEL-063: the commit, not the mtime, says when it landed).
    root = _replay_repo(tmp_path, 1, result_date="2026-03-01T12:00:00Z")
    rows = A.replay_repository("demo", root, BLOCK, SELECTION, 30, tmp_path / "ck.jsonl", progress=lambda m: None)
    assert rows[0]["new"] == []


KILL_SCRIPT = """
import os, signal, sys
from pathlib import Path
sys.path.insert(0, {repo_root!r})
from seldon.core import recall_audit as A
from seldon.core import recall as RC
calls = Path({calls!r})
real = RC.recall
def counted(*a, **k):
    with calls.open("a") as fh:
        fh.write(k.get("task_stem", "") + "\\n")
    return real(*a, **k)
RC.recall = counted
n = [0]
def progress(_m):
    n[0] += 1
    if {kill} and n[0] == 2:
        os.kill(os.getpid(), signal.SIGKILL)
A.replay_repository("demo", Path({root!r}), {block!r}, {sel!r}, 30, Path({ck!r}), progress=progress)
"""


def test_a_killed_replay_resumes_without_redoing_a_unit(tmp_path: Path):
    """Constitution section 15 point 8: SIGKILL mid-loop, restart, same rows, no completed unit recomputed."""
    root = _replay_repo(tmp_path, 4)
    repo_root = str(Path(__file__).resolve().parents[1])

    def run(ck: Path, calls: Path, kill: bool) -> int:
        script = KILL_SCRIPT.format(repo_root=repo_root, calls=str(calls), kill=kill, root=str(root), block=BLOCK,
                                    sel=SELECTION, ck=str(ck))
        return subprocess.run([sys.executable, "-c", script], capture_output=True, text=True).returncode

    assert run(tmp_path / "ck.jsonl", tmp_path / "calls.txt", kill=True) == -signal.SIGKILL
    first = A.checkpoint_rows(tmp_path / "ck.jsonl")
    assert len(first) == 2
    assert run(tmp_path / "ck.jsonl", tmp_path / "calls.txt", kill=False) == 0
    resumed = A.checkpoint_rows(tmp_path / "ck.jsonl")
    assert run(tmp_path / "clean.jsonl", tmp_path / "calls_clean.txt", kill=False) == 0
    clean = A.checkpoint_rows(tmp_path / "clean.jsonl")
    strip = lambda rows: {k.rsplit(":", 1)[0]: {f: v for f, v in r.items() if f != "key"} for k, r in rows.items()}
    assert strip(resumed) == strip(clean)
    stems = (tmp_path / "calls.txt").read_text().split()
    assert len(stems) == 2 * 4 and len(set(stems)) == 4  # each task: one old and one new call, never a second pair
