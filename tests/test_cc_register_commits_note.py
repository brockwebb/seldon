"""SEL-006 Part A: registration verifies and commits the governing design note with the task.

A Desktop session has no git, so its design note stayed untracked until the executing session's
Step 0 committed it: the dispatcher's c7 refused the launch and the operator pasted a launch line
(Issue 231c255c), and a Desktop session edited a note after a running session had committed it
(Issue 1fed4254). `register_task_file` now verifies such a note (AD-036-R4), records its labelled
rulings from the note's bytes (AD-033-R3, decided_by desktop), and commits note, records, verdict
and task file in one commit through the hook.

Real git, the real commit hook (`seldon hooks install`) and real Neo4j: what is under test is what
git and the hook do with the commit registration makes. Only the library arm is a stub, as in
`tests/test_hooks.py`, so no test loads the library index.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from seldon.commands.cc import cc_group
from seldon.core import hooks as H
from seldon.core import prior_art as pa
from seldon.mcp_server import seldon_cc_register
from tests.testdb import TEST_DATABASE

pytestmark = pytest.mark.usefixtures("neo4j_available", "clean_test_db")

LIB_SHA = "a" * 64
SRC = Path(H.__file__).resolve().parents[2]
TASK = "cc_tasks/2026-10-15_SEL-T_probe.md"
NOTE = "docs/design/AD-099_probe.md"
LEDGER = "governed/ledger/events.jsonl"


class StubLibrary:
    def __init__(self, s=None):
        self.rows, self.sha = ["lesson:x#p1:1:0-9"], LIB_SHA

    def search(self, query, k=None):
        return {"query": query, "release": "lib.json", "sha256": self.sha, "rows": self.rows, "hits": []}


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["PYTHONPATH"] = os.pathsep.join(x for x in (str(SRC), env.get("PYTHONPATH")) if x)
    return subprocess.run(["git", "-C", str(root), *args], check=check, capture_output=True, text=True, env=env)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """`tests/test_hooks.py`'s project (prior-art gate, decision register, tracked governed ledger,
    the hook installed), with a Neo4j database and an event store so a task can be registered."""
    # The hook git runs imports seldon: the code under test, not the installed checkout.
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(x for x in (str(SRC), os.environ.get("PYTHONPATH")) if x))
    monkeypatch.setattr(pa, "Library", StubLibrary)
    sib = tmp_path / "sib"
    (sib / "docs" / "design").mkdir(parents=True)
    _git(sib, "init", "-q")
    _git(sib, "config", "user.email", "t@t")
    _git(sib, "config", "user.name", "t")
    (sib / "docs" / "design" / "DN-001_unit.md").write_text(
        "# DN-001\n\nIntro line.\n\nThe unit of extraction is the\nparagraph, measured.\n")
    _git(sib, "add", "-A")
    _git(sib, "commit", "-qm", "init")
    sib_sha = _git(sib, "rev-parse", "HEAD").stdout.strip()

    proj = tmp_path / "proj"
    proj.mkdir()
    _git(proj, "init", "-q", "-b", "main")
    _git(proj, "config", "user.email", "t@t")
    _git(proj, "config", "user.name", "t")
    (proj / "governed" / "ledger").mkdir(parents=True)
    (proj / LEDGER).write_text("")
    (proj / "docs" / "design").mkdir(parents=True)
    (proj / "docs" / "decisions" / "register").mkdir(parents=True)
    (proj / "docs" / "design" / "AD-036_baseline.txt").write_text("docs/design/OLD.md\n")
    (proj / "docs" / "design" / "OLD.md").write_text("# an old note, no prior art\n")
    (proj / "cc_tasks").mkdir()
    (proj / "README.md").write_text("x\n")
    config = {
        "project": {"name": "t", "domain": "research"},
        "neo4j": {"database": TEST_DATABASE, "uri": os.getenv("NEO4J_URI", "bolt://localhost:7687")},
        "event_store": {"path": "seldon_events.jsonl"},
        "governed": {"graph_dir": "governed"},
        "prior_art": {
            "log": "state/q.jsonl",
            "internal_roots": [{"name": "sib", "path": str(sib)}],
            "internal": {"default_include": ["docs/design/**"], "suffixes": [".md"],
                         "top_n": 20, "max_file_bytes": 100000, "bm25": {"k1": 1.2, "b": 0.75}},
            "library": {"graph": str(tmp_path / "nolib"), "k": 20},
            "gate": {"design_dir": "docs/design", "baseline": "docs/design/AD-036_baseline.txt",
                     "exempt_globs": ["*_ADDENDUM_*.md", "*_erratum_*.md"],
                     "verdict_ledger_without_governed": "state/verdicts.jsonl"},
        },
    }
    (proj / "seldon.yaml").write_text(yaml.safe_dump(config))
    (proj / ".gitignore").write_text("state/\nseldon_events.jsonl\ndocs/decisions/.register.lock\n")
    _git(proj, "add", "-A")
    _git(proj, "commit", "-qm", "init")
    config["decisions"] = {
        "repository": "t", "baseline": {"name": "B", "commit": _git(proj, "rev-parse", "HEAD").stdout.strip()},
        "design_notes": [{"glob": "docs/design/AD-*.md",
                          "pattern": r"^(?:\s*[-*]\s*)?\*\*(AD-\d{3}-R\d+)[.:)\s]", "id": "{repo}:{label}"}]}
    (proj / "seldon.yaml").write_text(yaml.safe_dump(config))
    assert H.install(proj, python=sys.executable).wrote_hook
    _git(proj, "add", "-A")
    _git(proj, "commit", "-qm", "install the commit gate")
    return {"dir": proj, "config": config, "sib_sha": sib_sha}


def _good(repo, rulings: str = "") -> str:
    return (f"# AD-099 a probe note\n\n## 2. Prior art\n\n### External\n\n"
            f'- library receipt: query "unit of extraction" | release lib.json sha256:{LIB_SHA} '
            f"| rows lesson:x#p1:1:0-9\n\n### Internal\n\n"
            f'- internal receipt: query "unit of extraction" | repo sib@{repo["sib_sha"]} '
            f"| hits docs/design/DN-001_unit.md:5\n\n## 3. Decisions\n\n{rulings}")


BAD = "# AD-099 a probe note\n\nNo prior art section at all.\n"
RULING = ("- **AD-099-R1. A probe ruling binds the probe.**\n"
          "  - It is recorded by registration, from these bytes.\n\n"
          "Closing prose that is not the ruling.\n")


def _write(repo, rel: str, text: str) -> None:
    (repo["dir"] / rel).write_text(text, encoding="utf-8")


def _task(repo) -> None:
    _write(repo, TASK, "# CC Task: probe\n\n**Governing:** AD-099 (the probe note).\n**Model:** primary\n\n"
                       "A task governed by a note Desktop wrote.\n")


def _head(repo) -> str:
    return _git(repo["dir"], "rev-parse", "HEAD").stdout.strip()


def _files_in(repo, rev: str = "HEAD") -> list[str]:
    return sorted(_git(repo["dir"], "show", "--name-only", "--pretty=", rev).stdout.split())


def _status(repo, *paths: str) -> str:
    return _git(repo["dir"], "status", "--porcelain", "--untracked-files=all", "--", *paths).stdout


def _registered(repo) -> list[dict]:
    store = repo["dir"] / "seldon_events.jsonl"
    if not store.is_file():
        return []
    ev = [json.loads(x) for x in store.read_text().splitlines() if x.strip()]
    return [e for e in ev if e["event_type"] == "artifact_created"
            and e["payload"]["properties"].get("source_file") == TASK]


def test_an_untracked_note_with_passing_receipts_is_committed_with_the_task_in_one_commit(repo):
    _write(repo, NOTE, _good(repo))
    _task(repo)
    before = _head(repo)

    out = seldon_cc_register(TASK, project_dir=str(repo["dir"]), allow_untracked=True)

    assert out.startswith("Registered:"), out
    assert _git(repo["dir"], "rev-parse", "HEAD~1").stdout.strip() == before     # exactly one commit
    assert _files_in(repo) == sorted([NOTE, TASK, LEDGER])
    # The verdict the hook judged is in that commit, for the note's committed bytes.
    have = pa.verdicts(repo["dir"], repo["config"])
    sha = pa._sha((repo["dir"] / NOTE).read_bytes())
    assert have[NOTE][sha]["verdict"] == "pass"
    # Nothing registration read is left uncommitted: the dispatcher's c7 passes on these paths.
    assert _status(repo, "docs/design", "cc_tasks", "governed") == ""
    reg = _registered(repo)
    assert len(reg) == 1 and reg[0]["payload"]["properties"]["source_commit"] == _head(repo)


def test_a_failing_receipt_refuses_and_commits_nothing(repo):
    _write(repo, NOTE, BAD)
    _task(repo)
    before = _head(repo)

    out = seldon_cc_register(TASK, project_dir=str(repo["dir"]), allow_untracked=True)

    assert out.startswith("Error: governing_note_unverified"), out
    assert "missing: no `## Prior art` section" in out
    assert _head(repo) == before
    assert _status(repo, NOTE).startswith("??") and _status(repo, TASK).startswith("??")
    assert _registered(repo) == []
    # The fail verdict is recorded (AD-036-R4) and left for the dispatcher's sweep, not committed.
    have = pa.verdicts(repo["dir"], repo["config"])
    assert [v["verdict"] for v in have[NOTE].values()] == ["fail"]


def test_a_labelled_ruling_without_a_record_is_recorded_by_registration(repo):
    _write(repo, NOTE, _good(repo, RULING))
    _task(repo)

    out = seldon_cc_register(TASK, project_dir=str(repo["dir"]), allow_untracked=True)

    assert out.startswith("Registered:"), out
    files = _files_in(repo)
    recs = [f for f in files if f.startswith("docs/decisions/register/")]
    assert len(recs) == 1 and NOTE in files and TASK in files
    rec = yaml.safe_load((repo["dir"] / recs[0]).read_text())
    assert rec["id"] == "t:AD-099-R1" and rec["event"] == "accept" and rec["status"] == "accepted"
    assert rec["decided_by"] == "desktop" and rec["operator_stated"] is False
    lines = (repo["dir"] / NOTE).read_text().splitlines()
    a, b = rec["source"]["lines"]
    assert lines[a - 1].startswith("- **AD-099-R1.") and lines[b - 1].endswith("these bytes.")
    assert rec["source"]["text"] == "\n".join(lines[a - 1:b])
    assert rec["receipts"] == [TASK]
    assert _status(repo, "docs") == ""


def test_a_note_edited_after_an_earlier_commit_is_committed_as_a_new_commit_never_amended(repo):
    # The note was committed earlier (verdict staged with it, as the hook requires) ...
    _write(repo, NOTE, _good(repo))
    s = pa.settings(repo["dir"], repo["config"])
    pa.record_verdict(pa.verify_note(repo["dir"] / NOTE, s, library=StubLibrary()), repo["dir"], repo["config"])
    _git(repo["dir"], "add", NOTE, LEDGER)
    _git(repo["dir"], "commit", "-qm", "the first commit of the note")
    first = _head(repo)
    first_tree = _git(repo["dir"], "rev-parse", f"{first}^{{tree}}").stdout.strip()
    # ... then Desktop edited it.
    _write(repo, NOTE, _good(repo) + "A later paragraph Desktop added.\n")
    _task(repo)

    out = seldon_cc_register(TASK, project_dir=str(repo["dir"]), allow_untracked=True)

    assert out.startswith("Registered:"), out
    assert _git(repo["dir"], "rev-parse", "HEAD~1").stdout.strip() == first     # a child, not a rewrite
    assert _git(repo["dir"], "rev-parse", f"{first}^{{tree}}").stdout.strip() == first_tree
    assert NOTE in _files_in(repo) and TASK in _files_in(repo)
    assert "A later paragraph" in _git(repo["dir"], "show", f"HEAD:{NOTE}").stdout
    assert _status(repo, "docs/design", "cc_tasks") == ""


def test_without_the_flag_an_uncommitted_note_refuses_rather_than_staying_untracked(repo):
    """`--allow-untracked` now means "commit what registration verified"; without it, a note git
    does not hold refuses, so no registration ever leaves a file it read untracked."""
    _write(repo, NOTE, _good(repo))
    _task(repo)
    _git(repo["dir"], "add", TASK)
    _git(repo["dir"], "commit", "-qm", "the task, committed by its author")
    before = _head(repo)
    prev = Path.cwd()
    os.chdir(repo["dir"])
    try:
        res = CliRunner().invoke(cc_group, ["register", TASK], catch_exceptions=False)
    finally:
        os.chdir(prev)
    assert res.exit_code == 1, res.output
    assert "governing_note_uncommitted" in res.output and NOTE in res.output
    assert _head(repo) == before and _registered(repo) == []


def test_a_commit_the_hook_refuses_puts_the_tree_back_and_registers_nothing(repo, tmp_path_factory):
    hooks = tmp_path_factory.mktemp("hooks")
    (hooks / "pre-commit").write_text("#!/bin/sh\necho refused by hook >&2\nexit 1\n")
    (hooks / "pre-commit").chmod(0o755)
    _git(repo["dir"], "config", "core.hooksPath", str(hooks))
    _write(repo, NOTE, _good(repo, RULING))
    _task(repo)
    before = _head(repo)

    out = seldon_cc_register(TASK, project_dir=str(repo["dir"]), allow_untracked=True)

    assert out.startswith("Error: governing_note_uncommitted"), out
    assert "refused by hook" in out
    assert _head(repo) == before and _registered(repo) == []
    assert not list((repo["dir"] / "docs" / "decisions" / "register").glob("*.yaml"))
    assert _status(repo, NOTE).startswith("??") and _status(repo, TASK).startswith("??")
    assert _git(repo["dir"], "diff", "--cached", "--name-only").stdout == ""
