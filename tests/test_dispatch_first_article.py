"""QC-002 Part C (AD-037-R6 b): first-article inspection. A task marks a loop with `**First article:** <loop>,
<check over the first unit's output>`. The session stops after the first unit and appends `first_article` with the
output path; the dispatcher runs the check and writes `first_article_pass` (the loop continues) or a session stop (it
ends). The session waits on the record, not on a person: nothing within `first_article_polls` polls is a huddle.

The plants are the tests named `test_plant_*`; each fails on the HEAD before QC-002
(docs/evidence/qc002/plants_fail_on_head.txt).
"""
from __future__ import annotations

import sys
import threading
import time

from click.testing import CliRunner

from seldon.cli import main
from tests import stations_scaffold as F

CHECK = f"{sys.executable} -c \"import sys; sys.exit(0 if open(sys.argv[1]).read().startswith('ok') else 1)\" {{output}}"
FA = f"**Parts:** A 0.5, B 0.5.\n**First article:** documents, `{CHECK}`"


def _session(p, monkeypatch, argv, result):
    monkeypatch.chdir(p)
    monkeypatch.setenv("SELDON_SESSION_ID", "child-1")
    result["r"] = CliRunner().invoke(main, ["dispatch", *argv])


def _run_with_inspector(p, monkeypatch, argv, inspect_after_s=0.3):
    """The session's command in a thread; the dispatcher's inspection from this one, as the holder's loop would."""
    from seldon.core import stations as S
    result = {}
    t = threading.Thread(target=_session, args=(p, monkeypatch, argv, result))
    t.start()
    time.sleep(inspect_after_s)
    scfg = S.load_stations_config(F.config(p)["dispatch"])
    S.inspect(p, F.TASK_ID, F.events(p), scfg, 300, F.emitter(p))
    t.join(timeout=30)
    return result["r"]


def test_plant_a_first_article_pass_continues_the_loop(tmp_path, monkeypatch):
    p = F.make_project(tmp_path, extra=FA)
    F.launch(p, at=F.ago(60))
    (p / "out1.txt").write_text("ok: the first document\n", encoding="utf-8")
    r = _run_with_inspector(p, monkeypatch, ["first-article", "--loop", "documents", "--output", str(p / "out1.txt"),
                                             "--poll-s", "0.5"])
    assert r.exit_code == 0, r.output
    assert "continue the loop" in r.output
    from seldon.core import stations as S
    (fa,) = F.events(p, S.EVENT_FIRST_ARTICLE)
    (ok,) = F.events(p, S.EVENT_FIRST_ARTICLE_PASS)
    assert ok["payload"]["answers"] == fa["event_id"] and ok["payload"]["check"]["outcome"] == "pass"
    assert F.events(p, S.EVENT_SESSION_STOP) == []


def test_plant_a_first_article_fail_stops_the_loop(tmp_path, monkeypatch):
    p = F.make_project(tmp_path, extra=FA)
    F.launch(p, at=F.ago(60))
    (p / "out1.txt").write_text("garbage: a navigation page\n", encoding="utf-8")
    r = _run_with_inspector(p, monkeypatch, ["first-article", "--loop", "documents", "--output", str(p / "out1.txt"),
                                             "--poll-s", "0.5"])
    from seldon.core import stations as S
    assert r.exit_code == S.HALT_EXIT, r.output
    (stop,) = F.events(p, S.EVENT_SESSION_STOP)
    assert stop["payload"]["station"] == "first_article" and stop["payload"]["reason"] == "first_article_fail"
    (halted,) = F.events(p, S.EVENT_ANDON_HALTED)
    assert halted["payload"]["stop_event_id"] == stop["event_id"]
    assert F.events(p, S.EVENT_FIRST_ARTICLE_PASS) == []


def test_no_verdict_within_three_polls_is_a_huddle_and_a_halt(tmp_path, monkeypatch):
    from seldon.core import stations as S
    p = F.make_project(tmp_path, extra=FA)
    F.launch(p, at=F.ago(60))
    result = {}
    t0 = time.monotonic()
    _session(p, monkeypatch, ["first-article", "--loop", "documents", "--output", "x", "--poll-s", "0.1"], result)
    assert result["r"].exit_code == S.HALT_EXIT and time.monotonic() - t0 >= 0.3
    (h,) = F.events(p, S.EVENT_HUDDLE)
    assert h["payload"]["opened_by"] == "first_article_wait" and "3 polls" in h["payload"]["reading"]
    assert h["payload"]["cause"] is None and h["payload"]["gate"] is None, "cause and gate are left to fill"


def test_a_first_article_for_an_undeclared_loop_stops(tmp_path):
    from seldon.core import stations as S
    p = F.make_project(tmp_path, extra=FA)
    F.launch(p, at=F.ago(60))
    F.record(p, S.EVENT_FIRST_ARTICLE, {"loop": "records", "output": "x"})
    S.inspect(p, F.TASK_ID, F.events(p), S.load_stations_config({}), 300, F.emitter(p))
    (stop,) = F.events(p, S.EVENT_SESSION_STOP)
    assert stop["payload"]["reason"] == "first_article_undeclared"


def test_the_first_article_header_parses():
    from seldon.core import stations as S
    assert S.parse_first_articles(FA) == [{"loop": "documents", "command": CHECK}]
