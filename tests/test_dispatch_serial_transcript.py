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

**Erratum, MODEL-001 (AD-035, 2026-10-09).** The launch deliberately changed: the session is the
lock's CLI with `--output-format stream-json --verbose` and `--model <id> --settings
{"switchModelsOnFlag":false}`, its stream ends in a result line, `dispatch_launched` carries a
`model` block, `dispatch_finished` a `model_receipt`, and the blocked line names the served model.
The fixture was re-recorded on the MODEL-001 code, and the re-recording was checked to equal the
pre-change fixture byte for byte once exactly those additions are removed (the strip script and
its `True` are in `cc_tasks/2026-10-09_MODEL-001_config_driven_model_selection_RESULT.md`). Every
other line, and so the serial behaviour this test exists to hold, is unchanged.

**Erratum, PA-001 (AD-036-R8, 2026-10-09).** Effort is now a declared input: the launch command
ends `--effort medium` (the `primary` role's level), `dispatch_launched`'s `model.effort` reads
`medium` where it read `default`, and `dispatch_finished`'s `model_receipt` carries `effort`.
Re-recorded on the PA-001 code; a per-line diff against the MODEL-001 fixture showed eight changed
lines, every change one of exactly those three insertions or that one substitution.

**Erratum, SQ-010 ADDENDUM 02 D3.4 (2026-10-11).** Every candidate now carries criterion c12, free space
against the launch's measured need, so each `dispatch_launched` criteria vector gains one `"c12": {...}` block
(two in this scenario). Its `free_bytes` is the conftest fake (10**15), which `normalize` numbers as a HEX token,
so every later HEX token's number shifts by one. Re-recorded twice on the D3.4 code (byte-identical), and checked
to equal the pre-change fixture once the two c12 blocks are removed and HEX tokens renumbered by first
appearance in both. Every other line is unchanged. c12's `footprint_bytes` and `need_bytes` are masked as
`<BYTES>`: they measure the committed tree, which differs between the two parametrizations by the
`max_parallel: 1` line in seldon.yaml.

**Erratum, QC-002 (AD-037-R6, 2026-10-14).** Each `dispatch_launched` now records station (a)'s premise review
(`premises`: the dispatcher's environment premise and the task's own, none in this scenario) and R7's
`inspection_reserve`. Re-recorded on the QC-002 code; the diff is the two launch lines, and the re-recording equals
the pre-change fixture once exactly those two keys are removed from both (checked with a regex strip, `True`).
Every other line is unchanged: the stations write nothing for a session that appends no station record.

**Erratum, FRICTION-001 (AD-038-R1, 2026-10-17).** The dispatcher reconciles before c7, whoever wrote a line, and
its event-store commit subject names the writers it found and the class: `... written by desktop; reconciled by the
standing dispatcher (event_store, AD-038-R1)` where it read `... written by the standing dispatcher`. The dirty-tree
pass's refusal gains one line naming the path the reconciler would not commit (`unreconciled: notes.txt: not
machine-written governed state (untracked)`). Re-recorded on the FRICTION-001 code; `diff` against the pre-change
fixture shows exactly twelve reworded subjects (six on the passes' output, six in the `git log` section) and the one
added refusal line, nothing else.

**Erratum, FRICTION-002 (AD-034 ADDENDUM 01, 2026-10-17).** The serial pass deliberately changed where its session
runs: every task runs in `.claude/worktrees/<stem>` on branch `worktree-<stem>`, launched with `--worktree <stem>`
and per-launch `--settings` hooks, and finishes through AD-034-R5/R6's merge. Each launch's criteria vector gains
c11; `dispatch_launched` gains `mode`, `worktree`, `branch` and its command those flags; the finish lines are the
worktree finish's (`session exit=...`, `merged ...`, `sweep: removed ...`, `undeclared writes ...`), and
`dispatch_finished` carries `outcome`, `classifier_blocks`, `stop_gate` and the worktree fields; a merged task adds
`worktree_removed` and a failed one `worktree_kept`; main's log gains the merged session commit. HEX tokens renumber
accordingly. Re-recorded twice on the FRICTION-002 code (byte-identical). The four scenarios and their outcomes (one
green launch completed, one failing launch blocked, the dirty-tree refusal, the held-lease refusal) are unchanged.
"""
from __future__ import annotations

import os
import re
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
    # DESK-001 made `dirty_tree` alarm on its first pass. The recorded transcript is the serial
    # dispatcher's launch path, not its alarm thresholds, so the scenario keeps the uniform
    # threshold it was recorded under; the new default has its own tests.
    p = make_project(tmp_path, dispatch_extra={"stuck_after_passes_by_criterion": {},
                                               **dispatch_extra})
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
    # c12's byte counts are the size of the committed tree, and the two parametrizations commit different
    # seldon.yaml files (one has `max_parallel: 1`), so the counts differ by exactly that line. They are the
    # measurement's inputs, not the serial behaviour this test holds; masked the way wall clock is.
    text = re.sub(r'"(footprint_bytes|need_bytes)": \d+', r'"\1": <BYTES>', "\n".join(out))
    return normalize(text, p) + "\n"


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
