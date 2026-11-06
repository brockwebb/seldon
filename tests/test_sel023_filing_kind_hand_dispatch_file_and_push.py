"""SEL-023: a consumer filing is a kind the registrar accepts, a hand task is refused by the dispatcher, a filing is
written and registered in one call, and a Desktop commit reaches origin on the next pass.

`cc_tasks/2026-11-03_SEL-023_a_consumer_filing_is_a_kind_the_registrar_accepts_and_a_desktop_commit_reaches_origin.md`,
answering squiddy's filing of 2026-11-03 (observations 1 to 6) and the SQ11 work-order addendum's W7 and W8.

A. `**Kind:** filing` registers without candidacy headers, is never a candidate (`filing`), and closes with its return.
B. `**Dispatch:** hand` is recorded; the dispatcher never launches it (`dispatch_hand`) and says who does.
C. `seldon cc file` writes, commits and registers under the filing lock the pass also takes; `commit_governed`
   registers an unregistered task file in the same call.
D. Every pass pushes what the branch is ahead by: the lease-held exit, the holder's tick, and the pass's end.
E. The consumer rule is in what `seldon go` sends a Desktop; a return can answer a filing in the producer's graph.
"""
from __future__ import annotations

import fcntl
import subprocess
from pathlib import Path

import pytest
import yaml

from seldon.commands import dispatch as S
from seldon.commands.cc import register_task_file
from seldon.commands.dispatch import dispatch_group
from seldon.commands.task import task_group
from seldon.core import desktop_commit as DC
from seldon.core import dispatch as D
from seldon.core import filing as F
from seldon.core import returns as RT
from tests.dispatch_scaffold import NEO4J_DB, git, make_project, register, run_cli
from tests.test_sel008_cross_project_waits_and_block_reason import (  # noqa: F401  (fixtures)
    OTHER_DB, domain_config, other_db,
)
from tests.test_sel013r_answers_files_its_return import _config, _invoke, _repo, _today
from tests.testdb import TEST_DATABASE

neo4j_tests = pytest.mark.usefixtures("neo4j_available", "clean_test_db")

FULL = {"candidacy_headers": D.REQUIRED_HEADERS}

FILING = """# Consumer filing from consumer: something we experienced

**Kind:** filing
**Filed by:** consumer
**Date:** 2026-11-06. A report of what the consumer observed; no candidacy headers.

## What the consumer observed

1. The thing failed on the second call. This filing proposes no fix.

## What the consumer wants to know back

(a) Whether it changes.
"""

HAND_TASK = """# CC Task — {stem}

**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Spend:** zero model calls.
**Network:** none.
**Dispatch:** hand (the operator, from the primary checkout; it fast-forwards main)
**Parts:** A 1.00.

## 1. Do the thing.
"""


def _write(p: Path, rel: str, text: str) -> Path:
    f = p / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text, encoding="utf-8")
    return f


def _cfg(p: Path) -> dict:
    return yaml.safe_load((p / "seldon.yaml").read_text(encoding="utf-8"))


def _reg(p: Path, driver, dc, f: Path, actor: str = "cc") -> dict:
    return register_task_file(project_dir=p, config=_cfg(p), driver=driver, database=NEO4J_DB, domain_config=dc,
                              session_id=None, task_path=f, actor=actor, allow_untracked=True)


def _prop(driver, task_id: str, key: str, database: str = NEO4J_DB):
    with driver.session(database=database) as s:
        return s.run(f"MATCH (t:ResearchTask {{artifact_id: $id}}) RETURN t.{key} AS v", id=task_id).single()["v"]


# ══════════════════════════════════════════════════════════════════════════════
# Part A: the kind (no Neo4j)
# ══════════════════════════════════════════════════════════════════════════════

def test_a_filing_is_never_a_candidate_and_no_other_header_it_sets_is_read(tmp_path):
    f = _write(tmp_path, "f.md", FILING.replace("**Date:**", "**Spend:** lots and lots.\n**Model:** gpt-9\n**Date:**"))
    out = D.static_checks(f, FULL)
    assert out["candidate"] is False and out["reason"] == D.FILING_REASON
    assert out["failures"] == [], "a header a filing sets is ignored, not refused"
    assert "never a candidate" in out["message"]


def test_the_same_file_without_the_kind_line_is_refused_as_today(tmp_path):
    f = _write(tmp_path, "f.md", FILING.replace("**Kind:** filing\n", ""))
    codes = [x["code"] for x in D.static_checks(f, FULL)["failures"]]
    assert codes[0].startswith("no_header:")


@pytest.mark.parametrize("value, kind", [(None, "task"), ("filing", "filing"), ("`filing`.", "filing"),
                                         ("task", "task"), ("report", None), ("", None)])
def test_the_kind_grammar(value, kind):
    assert D.parse_kind(value)["kind"] == kind


def test_an_unparsable_kind_is_a_static_failure(tmp_path):
    f = _write(tmp_path, "f.md", FILING.replace("**Kind:** filing", "**Kind:** a report"))
    assert D.KIND_UNPARSABLE in [x["code"] for x in D.static_checks(f, None)["failures"]]


def test_a_filing_that_drafts_the_producers_fix_is_refused_and_a_report_is_not(tmp_path):
    assert F.designs_fix_refusal(_write(tmp_path, "ok.md", FILING), {}) is None
    for heading in ("## Proposed fix", "## Candidate fixes", "### The fix", "**Suggested design:** x"):
        bad = _write(tmp_path, "bad.md", FILING + f"\n{heading}\n\nChange `foo()` to retry.\n")
        refusal = F.designs_fix_refusal(bad, {})
        assert refusal and refusal.startswith(F.FILING_DESIGNS_FIX), heading
    fenced = _write(tmp_path, "fenced.md", FILING + "\n```\n## Proposed fix\n```\n")
    assert F.designs_fix_refusal(fenced, {}) is None, "a fenced block is quoted text, not the filing's structure"


def test_the_real_squiddy_filing_reads_as_a_report():
    """The measurement this task answers: squiddy's own filing carries no fix, so the lint must pass it."""
    repo = Path(__file__).resolve().parents[1]
    real = repo / ("cc_tasks/2026-11-03_consumer_filing_from_squiddy_a_consumer_filing_cannot_be_registered_and_"
                   "consumer_threads_have_no_rule_against_designing_fixes.md")
    assert F.designs_fix_refusal(real, yaml.safe_load((repo / "seldon.yaml").read_text())) is None


def test_the_fix_heading_patterns_are_configured_not_hardcoded(tmp_path):
    f = _write(tmp_path, "f.md", FILING + "\n## Workaround\n\nx\n")
    assert F.designs_fix_refusal(f, {}) is None
    assert F.designs_fix_refusal(f, {"filings": {"fix_headings": ["^workaround"]}})


# ══════════════════════════════════════════════════════════════════════════════
# Part B: who launches it (no Neo4j)
# ══════════════════════════════════════════════════════════════════════════════

def test_a_hand_task_passes_every_static_check_and_is_never_a_candidate(tmp_path):
    f = _write(tmp_path, "t.md", HAND_TASK.format(stem="t"))
    out = D.static_checks(f, FULL)
    assert out["failures"] == [], "registration accepts it"
    assert out["candidate"] is False and out["reason"] == D.DISPATCH_HAND_REASON
    assert "the operator, from the primary checkout" in out["message"], "the reason line says who launches it"


@pytest.mark.parametrize("value, mode", [(None, "dispatcher"), ("hand", "hand"), ("dispatcher", "dispatcher"),
                                         ("by hand", None), ("manual", None)])
def test_the_dispatch_grammar(value, mode):
    assert D.parse_dispatch(value)["mode"] == mode


def test_an_unparsable_dispatch_header_refuses(tmp_path):
    f = _write(tmp_path, "t.md", HAND_TASK.format(stem="t").replace("**Dispatch:** hand", "**Dispatch:** manual"))
    assert D.DISPATCH_UNPARSABLE in [x["code"] for x in D.static_checks(f, FULL)["failures"]]


# ══════════════════════════════════════════════════════════════════════════════
# A, B and C in a dispatched project (Neo4j)
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def proj(tmp_path, monkeypatch, neo4j_available, clean_test_db):
    for var in D.API_KEY_VARS:
        monkeypatch.setenv(var, "x")
        monkeypatch.delenv(var)
    return make_project(tmp_path)


def _once(p: Path):
    out = run_cli(p, dispatch_group, ["once"])
    assert out.exit_code == 0, out.output
    return out.output


@neo4j_tests
def test_fixture_a_headerless_filing_registers_and_every_pass_lists_it_as_a_filing(proj, neo4j_driver,
                                                                                domain_config):
    p = proj
    f = _write(p, "cc_tasks/2026-11-06_consumer_filing_from_consumer.md", FILING)
    out = _reg(p, neo4j_driver, domain_config, f, actor="desktop")
    assert _prop(neo4j_driver, out["artifact_id"], "task_kind") == "filing"
    assert _prop(neo4j_driver, out["artifact_id"], "filed_by") == "consumer"
    assert git(p, "status", "--porcelain").stdout == "", "registration committed it"
    text = _once(p)
    assert "0 candidate(s)" in text
    assert f"{out['artifact_id'][:8]} not_a_candidate: filing" in text and "no_source_file" not in text


@neo4j_tests
def test_without_the_kind_line_the_filing_is_refused_as_today(proj, neo4j_driver, domain_config):
    p = proj
    f = _write(p, "cc_tasks/2026-11-06_consumer_filing_from_consumer.md", FILING.replace("**Kind:** filing\n", ""))
    with pytest.raises(ValueError, match="no_header"):
        _reg(p, neo4j_driver, domain_config, f, actor="cc")
    with pytest.raises(ValueError, match="AD-030-R9"):          # and a Desktop's task owes its design note, as today
        _reg(p, neo4j_driver, domain_config, f, actor="desktop")


@neo4j_tests
def test_a_filing_registered_before_the_header_is_retagged_by_one_task_update(proj, neo4j_driver, domain_config):
    """squiddy 6ffde0f7 and 18001e38: header-less filings registered before R11, `no_source_file` on every pass."""
    p = proj
    tid = register(p, neo4j_driver, domain_config, "2026-10-20_hazbrief_findings", "2026-10-20T00:00:00Z")
    before = _once(p)
    assert f"{tid[:8]} not_a_candidate: source_file_missing" in before   # its file was never there
    assert "not_a_candidate: filing" not in before
    retag = run_cli(p, task_group, ["update", tid[:8], "--kind", "filing"])
    assert retag.exit_code == 0, retag.output
    assert f"{tid[:8]} not_a_candidate: filing" in _once(p)


@neo4j_tests
def test_a_hand_task_is_recorded_and_never_launched(proj, neo4j_driver, domain_config):
    p = proj
    f = _write(p, "cc_tasks/2026-11-06_hand_task.md", HAND_TASK.format(stem="hand"))
    out = _reg(p, neo4j_driver, domain_config, f)
    assert _prop(neo4j_driver, out["artifact_id"], "dispatch_mode") == "hand"
    text = _once(p)
    assert f"{out['artifact_id'][:8]} not_a_candidate: dispatch_hand" in text
    assert "the operator, from the primary checkout" in text
    assert "launching" not in text
    assert _prop(neo4j_driver, out["artifact_id"], "state") == "proposed"


@neo4j_tests
def test_cc_file_writes_commits_and_registers_under_the_lock_a_pass_cannot_enter(proj, neo4j_driver, monkeypatch):
    """Part C's fixture: a pass that runs between the write and the registration evaluates nothing, so it cannot
    observe the untracked file; after the call the tree is clean and the task is registered."""
    p = proj
    import seldon.commands.cc as CC
    real = CC.register_task_file
    seen = {}

    def probing(**kw):
        cfg = {**_cfg(p), "filings": {"lock_wait_s": 0}}
        seen["untracked"] = git(p, "status", "--porcelain", "--untracked-files=all").stdout
        with S._filing_guard(p, cfg, dry_run=False) as guard:
            seen["guard"] = guard
        return real(**kw)
    monkeypatch.setattr(CC, "register_task_file", probing)
    out = F.file_task(p, HAND_TASK.format(stem="filed"), name="2026-11-06_filed.md")
    assert "?? cc_tasks/2026-11-06_filed.md" in seen["untracked"], "the probe ran inside the window"
    assert "skipped" in seen["guard"], "a pass in the window waits on the lock and evaluates nothing"
    assert git(p, "status", "--porcelain").stdout == ""
    assert git(p, "log", "-1", "--format=%s", "--", "cc_tasks/2026-11-06_filed.md").stdout.strip()
    assert _prop(neo4j_driver, out["artifact_id"], "source_file") == "cc_tasks/2026-11-06_filed.md"


@neo4j_tests
def test_a_refused_cc_file_leaves_the_tree_as_it_was(proj):
    p = proj
    with pytest.raises(F.FilingError, match="no_header"):
        F.file_task(p, "# A task with no headers\n\n## 1. x\n", name="2026-11-06_bare.md")
    assert not (p / "cc_tasks/2026-11-06_bare.md").exists()
    assert git(p, "status", "--porcelain").stdout == ""


@neo4j_tests
def test_cc_file_refuses_to_overwrite(proj):
    p = proj
    _write(p, "cc_tasks/2026-11-06_there.md", "x\n")
    with pytest.raises(F.FilingError, match=F.FILE_EXISTS):
        F.file_task(p, HAND_TASK.format(stem="there"), name="2026-11-06_there.md")
    assert (p / "cc_tasks/2026-11-06_there.md").read_text() == "x\n"


@neo4j_tests
def test_a_pass_that_finds_the_filing_lock_held_evaluates_nothing(proj):
    p = proj
    cfg = _cfg(p)
    cfg["filings"] = {"lock_wait_s": 0}
    (p / "seldon.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    git(p, "commit", "-q", "-am", "filings wait 0")
    _write(p, "cc_tasks/2026-11-06_mid_write.md", "half a file\n")
    with F.filing_lock(p, cfg, holder="a filer mid-write"):
        text = _once(p)
    assert "filing lock:" in text and "evaluated nothing" in text
    assert "dirty_tree" not in text


@neo4j_tests
def test_commit_governed_registers_an_unregistered_task_file_in_the_same_call(proj, neo4j_driver):
    p = proj
    _write(p, "cc_tasks/2026-11-06_desktop_task.md", HAND_TASK.format(stem="d"))
    _write(p, "cc_tasks/2026-11-06_desktop_task_ADDENDUM_01.md", "# addendum\n")
    out = DC.commit_governed(p, ["cc_tasks/2026-11-06_desktop_task.md", "cc_tasks/2026-11-06_desktop_task_ADDENDUM_01.md"],
                             register_tasks=True, actor="cc")
    assert out.committed, out.detail
    assert [r["path"] for r in out.registered] == ["cc_tasks/2026-11-06_desktop_task.md"], "never an addendum"
    assert _prop(neo4j_driver, out.registered[0]["artifact_id"], "dispatch_mode") == "hand"
    assert "registered: cc_tasks/2026-11-06_desktop_task.md" in DC.render(out)
    assert git(p, "status", "--porcelain").stdout == ""


@neo4j_tests
def test_commit_governed_keeps_the_commit_when_registration_refuses(proj):
    p = proj
    _write(p, "cc_tasks/2026-11-06_bare.md", "# no headers\n")
    out = DC.commit_governed(p, ["cc_tasks/2026-11-06_bare.md"], register_tasks=True, actor="cc")
    assert out.committed and out.unregistered and "no_header" in out.unregistered[0]["refusal"]
    assert "NOT registered" in DC.render(out)
    assert git(p, "status", "--porcelain").stdout == "", "committed: the queue is not stalled on c7"


# ══════════════════════════════════════════════════════════════════════════════
# Part D: the pass pushes
# ══════════════════════════════════════════════════════════════════════════════

def _desktop_commit(p: Path, name: str = "handoffs/2026-11-06_h.md") -> str:
    _write(p, name, "a handoff\n")
    git(p, "add", "--", name)
    git(p, "commit", "-q", "-m", f"desktop: {name}", "--", name)
    return git(p, "rev-parse", "HEAD").stdout.strip()


def _origin_head(p: Path) -> str:
    return git(p, "rev-parse", "origin/main").stdout.strip() if git(p, "fetch", "-q").returncode == 0 else ""


@neo4j_tests
def test_a_pass_that_finds_the_lease_held_pushes_the_desktop_commit(proj):
    """Observation 6: a holder can run a session for an hour; the Desktop's commit does not wait for its merge."""
    p = proj
    head = _desktop_commit(p)
    lock = p / ".seldon" / "dispatch.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a+") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        text = _once(p)
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    assert "lease held" in text and "push: pushed 1 commit(s)" in text
    assert _origin_head(p) == head


@neo4j_tests
def test_an_idle_pass_pushes_once_and_says_so_once(proj):
    p = proj
    head = _desktop_commit(p)
    text = _once(p)
    assert text.count("push: pushed 1 commit(s)") == 1, text
    assert _origin_head(p) == head
    assert "push:" not in _once(p), "level with origin: nothing to say"


@neo4j_tests
def test_the_holders_tick_pushes_a_commit_made_while_its_session_runs(proj):
    p = proj
    cfg = D.load_dispatch_config(p)
    S._push_reset(p)
    S._push(p, cfg)                                     # the launch's own push, before the session
    head = _desktop_commit(p)
    tick = S._pushing(lambda: {"reap": None}, p, cfg)
    assert tick() == {"reap": None}, "the inspector's answer is passed through"
    assert _origin_head(p) == head
    tick()                                              # same HEAD: nothing tried twice


# ══════════════════════════════════════════════════════════════════════════════
# Part E: the consumer rule, and a return to a filing in the producer's graph
# ══════════════════════════════════════════════════════════════════════════════

def test_the_desktop_section_seldon_go_sends_carries_the_consumer_rule():
    from seldon.commands.go import _ROLE_SECTION
    desktop = _ROLE_SECTION.split("### If You Are a CC Session")[0]
    assert "does not design, draft or implement the producer's fix" in desktop
    assert "seldon_cc_file" in desktop and "**Kind:** filing" in desktop


RESULT = """# RESULT: SEL-901

Landed.

## For consumer

**Title:** apply what the producer landed

1. Retag the two filings.
"""


@pytest.fixture
def pair(tmp_path, monkeypatch, other_db, clean_test_db):
    producer = _repo(tmp_path / "producer", "producer", TEST_DATABASE)
    consumer = _repo(tmp_path / "consumer", "consumer", other_db, origin=True)
    monkeypatch.chdir(producer)
    return producer, consumer


def _numbered_consumer_task(consumer: Path, driver, dc) -> None:
    f = _write(consumer, "cc_tasks/2026-11-01_SQ-041_something.md",
               "# SQ-041: something\n\n**Spend:** zero.\n**Network:** none.\n**After:** none\n\n## 1. x\n")
    register_task_file(project_dir=consumer, config=_config(consumer), driver=driver, database=OTHER_DB,
                       domain_config=dc, session_id=None, task_path=f, actor="cc", allow_untracked=True)


@neo4j_tests
@pytest.mark.parametrize("by_header", [True, False])
def test_fixture_a_return_answers_a_filing_in_the_producers_graph_and_closes_it(pair, neo4j_driver, domain_config,
                                                                             by_header):
    producer, consumer = pair
    _numbered_consumer_task(consumer, neo4j_driver, domain_config)
    filing_rel = "cc_tasks/2026-11-06_consumer_filing_from_consumer.md"
    filing = register_task_file(project_dir=producer, config=_config(producer), driver=neo4j_driver,
                                database=TEST_DATABASE, domain_config=domain_config, session_id=None,
                                task_path=_write(producer, filing_rel, FILING), actor="desktop",
                                allow_untracked=True)["artifact_id"]
    answers = f"producer:{Path(filing_rel).stem}"
    task = ("# SEL-901: answer the filing\n\n**Spend:** zero.\n**Network:** none.\n**After:** none\n"
            + (f"**Answers:** {answers}\n" if by_header else "") + "\n## 1. x\n")
    task_rel = "cc_tasks/2026-11-06_SEL-901_answer_the_filing.md"
    out = register_task_file(project_dir=producer, config=_config(producer), driver=neo4j_driver,
                             database=TEST_DATABASE, domain_config=domain_config, session_id=None,
                             task_path=_write(producer, task_rel, task), actor="cc", allow_untracked=True)
    _write(producer, "cc_tasks/2026-11-06_SEL-901_answer_the_filing_RESULT.md", RESULT)
    args = ["return", task_rel] + ([] if by_header else ["--answers", answers])
    filed = _invoke(*args)
    assert filed.exit_code == 0, filed.output
    ret_rel = f"cc_tasks/{_today()}_SQ-042_apply_what_the_producer_landed.md"
    assert f"return filed: {consumer}/{ret_rel}" in filed.output, "numbered by the consumer's own prefix"
    text = (consumer / ret_rel).read_text(encoding="utf-8")
    assert f"**Returns:** producer:{out['artifact_id']} (SEL-901)" in text
    assert subprocess.run(["git", "status", "--porcelain"], cwd=consumer, capture_output=True,
                          text=True).stdout == ""
    assert _prop(neo4j_driver, filing, "state", TEST_DATABASE) == "completed", "the filing closes with its return"
    again = _invoke(*args)
    assert again.exit_code == 0 and "already filed" in again.output


@neo4j_tests
def test_answers_naming_a_task_of_the_producers_own_that_is_not_a_filing_is_refused(pair, neo4j_driver,
                                                                                  domain_config):
    producer, _consumer = pair
    rel = "cc_tasks/2026-11-06_SEL-902_a_task.md"
    register_task_file(project_dir=producer, config=_config(producer), driver=neo4j_driver, database=TEST_DATABASE,
                       domain_config=domain_config, session_id=None, actor="cc", allow_untracked=True,
                       task_path=_write(producer, rel, "# SEL-902: a task\n\n**Spend:** zero.\n**Network:** none.\n"
                                                       "**After:** none\n\n## 1. x\n"))
    with pytest.raises(ValueError, match="not a filing"):
        RT.resolve_answers("", producer, _config(producer), value="producer:SEL-902")
