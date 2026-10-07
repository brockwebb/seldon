"""SEL-004: `dispatch.max_parallel: 1` reproduces the pre-SEL-004 dispatcher byte for byte.

`cc_tasks/2026-10-07_SEL-004_worktree_per_task_dispatch.md` decision 2 and Tests: the default
must change nothing in any project until it opts in. "Nothing" is tested here against a
RECORDED transcript, not against a reading of the code: the scenario below was run with the
dispatcher as it stood at main 77464f1 (before SEL-004) and its normalized transcript written to
`tests/fixtures/dispatch_serial_transcript.txt`. The test runs the same scenario on the current
code, once with no `max_parallel` key and once with `max_parallel: 1`, and compares bytes.

The transcript is everything an operator or a replay can see: each pass's output (what the
launchd wrapper logs), every line of the event store, every per-task dispatch log, the commit
subjects on main, and the graph states. Only run-to-run noise is normalized (paths, host and
pid, uuids, timestamps, shas, wall clock); `dispatch_scaffold.normalize` numbers ids by first
appearance, so ids must also recur in the same places.

To re-record (only ever against a checkout of the pre-change dispatcher):
    SELDON_RECORD_SERIAL_TRANSCRIPT=1 python -m pytest tests/test_dispatch_serial_transcript.py
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from seldon.commands.dispatch import dispatch_group
from seldon.core import dispatch as D
from seldon.domain.loader import load_domain_config
from tests.dispatch_scaffold import (
    RESEARCH_YAML, add_task, events_dump, git, make_project, normalize, register, run_cli,
    task_states, write_stub,
)

pytestmark = pytest.mark.usefixtures("neo4j_available")

FIXTURE = Path(__file__).parent / "fixtures" / "dispatch_serial_transcript.txt"
RECORD_ENV = "SELDON_RECORD_SERIAL_TRANSCRIPT"


def _scenario(tmp_path, driver, dispatch_extra) -> str:
    """Four passes: a green launch, a failing launch, a dirty tree, a held lease."""
    domain_config = load_domain_config(RESEARCH_YAML)
    p = make_project(tmp_path, dispatch_extra=dispatch_extra)
    for stem in ("t1", "t2", "t3"):
        add_task(p, stem)
    write_stub(p, {"t1": {"complete": True, "write": {"out/t1.txt": "one\n"}},
                   "t2": {"exit": 1, "result": False}})
    register(p, driver, domain_config, "t1", "2026-09-15T00:00:01Z")
    register(p, driver, domain_config, "t2", "2026-09-15T00:00:02Z")
    out = []

    def once(label):
        res = run_cli(p, dispatch_group, ["once"])
        out.append(f"## pass: {label}\nexit={res.exit_code}\n{res.output}")

    once("t1 green")
    once("t2 fails")
    (p / "notes.txt").write_text("operator scratch\n", encoding="utf-8")
    register(p, driver, domain_config, "t3", "2026-09-15T00:00:03Z")
    once("dirty tree")
    lease = D.Lease(p / ".seldon" / "dispatch.lock").__enter__()
    try:
        once("lease held")
    finally:
        lease.__exit__(None, None, None)

    out.append("## events\n" + events_dump(p))
    for log in sorted((p / "logs" / "dispatch").glob("*.log")):
        out.append(f"## log {log.name}\n" + log.read_text(encoding="utf-8"))
    out.append("## git log main\n" + git(p, "log", "--format=%s", "main").stdout)
    out.append("## git status\n" + git(p, "status", "--porcelain").stdout)
    out.append("## graph\n" + "\n".join(f"{k} {v}" for k, v in
                                       sorted(task_states(driver).items())))
    return normalize("\n".join(out), p) + "\n"


@pytest.mark.parametrize("dispatch_extra", [{}, {"max_parallel": 1}],
                         ids=["no_key", "max_parallel_1"])
def test_max_parallel_1_reproduces_the_recorded_serial_transcript(
        tmp_path, neo4j_driver, clean_test_db, monkeypatch, dispatch_extra):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    transcript = _scenario(tmp_path, neo4j_driver, dispatch_extra)
    if os.getenv(RECORD_ENV) == "1":
        if dispatch_extra:
            pytest.skip("recording uses the no-key run only")
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(transcript, encoding="utf-8")
        pytest.skip(f"recorded {FIXTURE}")
    assert transcript == FIXTURE.read_text(encoding="utf-8")
