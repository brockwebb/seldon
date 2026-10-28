"""SEL-014R Part D: last night's chain replayed through the OODA knowledge source (AD-038-R16, R17).

`cc_tasks/2026-10-28_SEL-014R_the_ooda_is_a_knowledge_source_the_dispatcher_launches.md` Part D.

1. **The overnight chain.** NUM-001R `bacacc4c` -> DESK-004R `f7a1d2f0` -> DISP-004R `2909ce0f` -> RECALL-002R
   `ff3a4189` ran 2026-10-27/28 with no OODA. Each of its three edges is replayed at the commit that brought the
   predecessor's RESULT to main (this repository's own history, in a `git clone --shared` and a detached worktree per
   edge), so the successor's premises are checked against the tree it would have launched from. Every edge ends in
   `ooda_ok` or `ooda_amended`, and no record is one a person must read (`ooda_blocked`) or one that ran on the timer
   (`ooda_expired`).
2. **A successor whose premise the predecessor broke** ends `ooda_amended`, with the addendum committed before the
   record.

The model is a stand-in (`STAND_IN`), a deterministic reader of the brief the dispatcher composed: it amends when the
dispatcher reported a premise false or unrunnable at HEAD, writing the successor's next addendum at the prefix the
brief names, and answers `ok` otherwise. So what is tested is the dispatcher's half (the brief, the launch, the check
of the verdict, the addendum's commit, the record), and the decision depends on what the brief carried, not on the
test. The same replay with the real model is the acceptance run recorded in the RESULT
(`scripts/sel014r_replay_with_the_model.py`).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from seldon.commands import dispatch_ooda as DO
from seldon.core import dispatch as D
from seldon.core import ooda as O
from seldon.core.events import read_events
from tests.models_fixture import use_stub_cli
from tests.test_dispatch import _commit, _seldon_yaml, _task_file, project  # noqa: F401  (fixture)

SELDON_REPO = Path(__file__).resolve().parents[1]

#: The overnight chain: (task id, file stem). Each consecutive pair is one `precedes` edge.
CHAIN = [
    ("bacacc4c-9ddc-45bb-b214-0747bd6d2c13", "2026-10-27_NUM-001R_task_numbers_allocated_and_headers_read_from_the_header_block"),
    ("f7a1d2f0-f69b-48d0-87c7-a2187d7d1d03", "2026-10-27_DESK-004R_every_file_the_machine_writes_is_committed_by_the_tool_that_wrote_it"),
    ("2909ce0f-ec55-4da7-8f9b-f2f393933264", "2026-10-27_DISP-004R_a_cross_repo_task_is_pushed_in_every_repository_it_names"),
    ("ff3a4189-1943-4405-a30f-8d3344bb97ad", "2026-10-27_RECALL-002R_recall_turned_on_in_squiddy_arnold_and_ai_readiness_kg"),
]

#: The stand-in model. Reads the prompt the dispatcher built, cuts and enters a worktree as `--worktree` does, and
#: decides from the brief alone.
STAND_IN = r'''#!{python}
import json, os, re, subprocess, sys
args = sys.argv[1:]
prompt = args[args.index("-p") + 1]
if args[-1] == "--worktree":
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True).stdout.strip()
    name = "ooda-" + str(os.getpid())
    wt = os.path.join(top, ".claude", "worktrees", name)
    subprocess.run(["git", "-C", top, "worktree", "add", "-q", "-b", "worktree-" + name, wt, "HEAD"], check=True)
    os.chdir(wt)
print(json.dumps({{"type": "system", "subtype": "init", "cwd": os.path.realpath(os.getcwd())}}))
print(json.dumps({{"type": "assistant", "message": {{"id": "m1", "role": "assistant", "content": [],
                                                    "usage": {{"input_tokens": 100, "output_tokens": 10}}}}}}))
broken = [ln.strip() for ln in prompt.splitlines() if re.match(r"\s*premise \((false|unrunnable)\)", ln)]
prefix = re.search(r"with these prefixes: (\S+?_)[.;]", prompt)
if broken and prefix:
    path = prefix.group(1) + "premise_the_predecessor_broke.md"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write("# ADDENDUM: a premise the predecessor broke\n\n**Author:** OODA knowledge source (AD-038-R16)\n\n"
                 + "\n".join("- " + b for b in broken) + "\n")
    verdict = {{"verdict": "amended", "note": f"{{len(broken)}} premise(s) false at HEAD", "addenda": [path]}}
else:
    verdict = {{"verdict": "ok", "note": "the RESULT changes nothing in the successor"}}
text = "Read the RESULT and the successor.\nOODA-VERDICT: " + json.dumps(verdict)
print(json.dumps({{"type": "result", "subtype": "success", "result": text, "usage": {{"output_tokens": 10}},
                  "modelUsage": {{"claude-opus-5-5": {{"outputTokens": 10, "inputTokens": 100}}}}}}))
'''


def _stand_in(tmp_path: Path) -> Path:
    stub = tmp_path / "bin" / "claude"
    stub.parent.mkdir(parents=True, exist_ok=True)
    stub.write_text(STAND_IN.format(python=sys.executable), encoding="utf-8")
    stub.chmod(0o755)
    use_stub_cli(tmp_path, stub)
    return stub


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def _run(tree: Path, config: dict, item: dict) -> dict:
    cfg = D.load_dispatch_config(tree, config)
    cfg["ooda_grace_s"] = 120
    cfg["ooda"] = {**cfg["ooda"], "enabled": True, "inspect_every_s": 0.2}
    return DO.run_one(tree, config, cfg, None, item)


@pytest.fixture
def clone(tmp_path):
    """This repository's history, cloned so the replay never touches the checkout under test."""
    dst = tmp_path / "seldon"
    subprocess.run(["git", "clone", "-q", "--shared", "--no-checkout", str(SELDON_REPO), str(dst)], check=True)
    for args in (["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        _git(dst, *args)
    return dst


def test_the_overnight_chain_needs_no_human_reading(clone, tmp_path):
    _stand_in(tmp_path)
    kinds = []
    for (pid, pstem), (sid, sstem) in zip(CHAIN, CHAIN[1:]):
        result = f"cc_tasks/{pstem}_RESULT.md"
        sha = _git(clone, "log", "--diff-filter=A", "--format=%H", "-1", "HEAD", "--", result)
        assert sha, f"{result} is not in this repository's history"
        tree = tmp_path / f"edge_{pid[:8]}"
        _git(clone, "worktree", "add", "-q", "--detach", str(tree), sha)
        assert (tree / f"cc_tasks/{sstem}.md").is_file(), f"{sstem} was not filed at {sha[:8]}"
        config = yaml.safe_load((tree / "seldon.yaml").read_text(encoding="utf-8"))
        config.pop("recall", None)          # the sibling corpora are not beside a /tmp clone; Recall is the model run's
        pred = {"artifact_id": pid, "state": "completed", "name": pstem, "source_file": f"cc_tasks/{pstem}.md"}
        succ = {"artifact_id": sid, "state": "proposed", "name": sstem, "source_file": f"cc_tasks/{sstem}.md",
                "predecessors": [pred]}
        out = _run(tree, config, {"predecessor": pred, "successors": [succ], "completed_at": None})
        kinds.append(out["kind"])
        [rec] = [e for e in read_events(tree) if e["event_type"] in O.RECORD_KINDS]
        assert rec["payload"]["task_id"] == pid and rec["payload"]["successors"][0]["task_id"] == sid
        assert rec["payload"]["result"] == result
        if out["kind"] == O.OODA_AMENDED:
            for rel in out["payload"]["addenda"]:
                assert D.is_tracked(tree, tree / rel)
    assert len(kinds) == len(CHAIN) - 1
    assert set(kinds) <= {O.OODA_OK, O.OODA_AMENDED}, kinds


def test_a_successor_whose_premise_the_predecessor_broke_is_amended(project, tmp_path):
    """n0 moved `a/` to `b/`; n1 still checks `a/`. The brief reports the premise false, the stand-in amends, and the
    dispatcher commits the addendum before it writes `ooda_amended`."""
    _stand_in(tmp_path)
    (project / "a").mkdir()
    (project / "a" / "keep").write_text("x\n", encoding="utf-8")
    _task_file(project, "n0")
    n1 = _task_file(project, "n1")
    n1.write_text(n1.read_text() + "\n**Premises:**\n- premise: the inputs are under a | check: test -d a\n",
                  encoding="utf-8")
    _commit(project, "chain")
    _git(project, "mv", "a", "b")
    (project / "cc_tasks" / "n0_RESULT.md").write_text("# RESULT n0\n\nMoved a/ to b/.\n", encoding="utf-8")
    _commit(project, "n0 done")
    config = yaml.safe_load((project / "seldon.yaml").read_text())
    pred = {"artifact_id": "p" * 8, "state": "completed", "name": "n0", "source_file": "cc_tasks/n0.md"}
    succ = {"artifact_id": "s" * 8, "state": "proposed", "name": "n1", "source_file": "cc_tasks/n1.md",
            "predecessors": [pred]}
    out = _run(project, config, {"predecessor": pred, "successors": [succ], "completed_at": None})
    assert out["kind"] == O.OODA_AMENDED, out["payload"]
    [rel] = out["payload"]["addenda"]
    assert rel == "cc_tasks/n1_ADDENDUM_01_premise_the_predecessor_broke.md"
    assert "premise (false): the inputs are under a | check: test -d a" in (project / rel).read_text()
    assert D.is_tracked(project, project / rel)
    # The addendum's commit is in history before the record is in the ledger: the record names it.
    assert _git(project, "log", "-1", "--format=%h", "--", rel).startswith(out["payload"]["commit"][:7])
