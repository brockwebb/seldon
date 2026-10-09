"""Shared scaffolding for the dispatcher tests that run real passes against a scratch repository.

A scratch project is a git repository with a `dispatch:` block, a tracked event store, a bare
`origin` so pushes are real, and a stub `claude` on disk. The stub is a Python script driven by
`bin/stub_spec.json`: for each task stem it names what the "session" does (write files, append
an event, commit, complete the task in the graph, sleep, exit code). No model call, no network.

Used by `test_dispatch_serial_transcript.py` (SEL-004's `max_parallel: 1` byte-for-byte test)
and `test_dispatch_parallel.py` (the worktree-per-task tests). The fixture transcript was
recorded with this module against the dispatcher as it stood at main 77464f1, before SEL-004.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import yaml
from click.testing import CliRunner

from seldon.core.artifacts import create_artifact
from tests.testdb import TEST_DATABASE

NEO4J_DB = TEST_DATABASE
SELDON_REPO = Path(__file__).resolve().parents[1]
RESEARCH_YAML = SELDON_REPO / "seldon" / "domain" / "research.yaml"

TASK_BODY = textwrap.dedent("""\
    # CC Task — {stem}

    **Date:** 2026-09-15
    **Framework layer served (DN-005 §5 rule 1):** §2.2 Tier M
    **Spend:** zero model calls. **Network:** none.
    {extra}
    ## 1. Do the thing.
    """)


def git(p: Path, *a, check=True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *a], cwd=p, check=check, capture_output=True, text=True)


def make_project(tmp_path: Path, *, dispatch_extra: dict | None = None,
                 track_store: bool = True, union_store: bool = True) -> Path:
    """A git project with a dispatch block, a tracked event store and a bare origin."""
    p = tmp_path / "proj"
    (p / "cc_tasks").mkdir(parents=True)
    (p / "bin").mkdir()
    git(p, "init", "-q", "-b", "main")
    git(p, "config", "user.email", "t@t")
    git(p, "config", "user.name", "t")
    ignore = [".seldon/", "logs/", "bin/", ".worktrees/"]
    if not track_store:
        ignore.append("seldon_events.jsonl")
    (p / ".gitignore").write_text("\n".join(ignore) + "\n", encoding="utf-8")
    if union_store:
        (p / ".gitattributes").write_text("seldon_events.jsonl merge=union\n",
                                          encoding="utf-8")
    (p / "controls.yaml").write_text(
        yaml.safe_dump({"spend": {"daily_tokens": 55_000_000}}), encoding="utf-8")
    dispatch = {"enabled": True, "branch": "main",
                "standing_band_ref": "controls.yaml#spend.daily_tokens",
                "poll_interval_s": 300, "permission_mode": "bypassPermissions",
                "stop_file": ".seldon/DISPATCH_STOP", "log_dir": "logs/dispatch",
                "lease_file": ".seldon/dispatch.lock"}
    dispatch.update(dispatch_extra or {})
    # AD-035 R3: the dispatcher execs the lock's CLI, so the stub is named by a fixture lock,
    # not by a `dispatch.cli` key (which is now refused). Undone after the test by conftest's
    # monkeypatched SELDON_MODELS_HOME.
    use_stub_lock(tmp_path, p)
    (p / "seldon.yaml").write_text(yaml.safe_dump({
        "event_store": {"path": "seldon_events.jsonl"},
        "neo4j": {"database": NEO4J_DB, "uri": os.getenv("NEO4J_URI",
                                                         "bolt://localhost:7687")},
        "project": {"domain": "research", "name": "t", "slug": "t"},
        "dispatch": dispatch,
    }), encoding="utf-8")
    (p / "seldon_events.jsonl").write_text("", encoding="utf-8")
    git(p, "add", "-A")
    git(p, "commit", "-q", "-m", "init")
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True,
                   capture_output=True)
    git(p, "remote", "add", "origin", str(origin))
    git(p, "push", "-q", "-u", "origin", "main")
    write_stub(p, {})
    return p


def use_stub_lock(tmp_path: Path, p: Path) -> Path:
    """Point SELDON_MODELS_HOME at a fixture lock whose CLI is the project's stub `claude`."""
    from tests.models_fixture import write_models_home
    home = write_models_home(tmp_path / "models_home", cli_path=p / "bin" / "claude")
    os.environ["SELDON_MODELS_HOME"] = str(home)
    return home


def add_task(p: Path, stem: str, extra: str = "", commit: bool = True) -> str:
    rel = f"cc_tasks/{stem}.md"
    (p / rel).write_text(TASK_BODY.format(stem=stem, extra=extra), encoding="utf-8")
    if commit:
        git(p, "add", "--", rel)
        git(p, "commit", "-q", "-m", f"task {stem}", "--", rel)
        git(p, "push", "-q")
    return rel


def register(p: Path, driver, domain_config, stem: str, created_at: str) -> str:
    return create_artifact(
        project_dir=p, driver=driver, database=NEO4J_DB, domain_config=domain_config,
        artifact_type="ResearchTask",
        properties={"description": f"stub task {stem}", "name": stem,
                    "source_file": f"cc_tasks/{stem}.md", "created_at": created_at},
        actor="desktop", authority="accepted")


STUB = '''#!{python}
"""Stub `claude -p`: does what bin/stub_spec.json says for the task named in the prompt."""
import json, os, re, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, {repo!r})
sys.stdout.reconfigure(line_buffering=True)  # a test may wait on a line of this log
prompt = sys.argv[sys.argv.index("-p") + 1]
stem = re.search(r"cc_tasks/([A-Za-z0-9_.-]+)\\.md", prompt).group(1)
spec = json.loads(Path({spec!r}).read_text()).get(stem, {{}})
cwd = Path.cwd()
print("stub cc:", " ".join(sys.argv[1:]))
print("stub cwd:", "worktree" if ".worktrees" in str(cwd) else "primary")
def mark(what):
    if spec.get("mark"):
        with open(spec["mark"], "a") as fh:
            fh.write(f"{{stem}} {{what}} {{time.time()}}\\n")
mark("start")
if spec.get("dump_env"):
    Path(spec["dump_env"]).write_text(json.dumps(
        {{k: v for k, v in os.environ.items() if k.startswith("ANTHROPIC_DEFAULT_")}}))
if spec.get("pidfile"):
    Path(spec["pidfile"]).write_text(str(os.getpid()))
for rel, text in (spec.get("write") or {{}}).items():
    (cwd / rel).parent.mkdir(parents=True, exist_ok=True)
    with open(cwd / rel, "a") as fh:
        fh.write(text)
for rel, (old, new) in (spec.get("replace") or {{}}).items():
    path = cwd / rel
    path.write_text(path.read_text().replace(old, new))
for rel, text in (spec.get("primary_append") or {{}}).items():
    from seldon.core.worktree import locked
    with locked(Path(os.environ["SELDON_PRIMARY_CHECKOUT"]) / rel) as fh:
        fh.write(text)
if spec.get("sleep"):
    time.sleep(spec["sleep"])
if spec.get("append_event"):
    from seldon.core.events import append_event, make_event
    append_event(cwd, make_event("note_recorded", "cc", "accepted", {{"stem": stem}}))
if spec.get("result", True):
    (cwd / "cc_tasks" / f"{{stem}}_RESULT.md").write_text("# RESULT\\n")
if spec.get("complete"):
    from seldon.core.artifacts import walk_to_completed
    from seldon.domain.loader import load_domain_config
    from seldon.config import get_neo4j_driver
    d = get_neo4j_driver({{"neo4j": {{"uri": {uri!r}, "database": {db!r}}}}})
    tid = d.session(database={db!r}).run(
        "MATCH (t:ResearchTask {{source_file: $s}}) RETURN t.artifact_id AS i",
        s=f"cc_tasks/{{stem}}.md").single()["i"]
    walk_to_completed(project_dir=cwd, driver=d, database={db!r},
                      domain_config=load_domain_config(Path({research!r})),
                      artifact_id=tid, current_state="in_progress", actor="cc")
    d.close()
if spec.get("commit", True) and spec.get("result", True):
    paths = ([f"cc_tasks/{{stem}}_RESULT.md"] + list((spec.get("write") or {{}}).keys())
             + list((spec.get("replace") or {{}}).keys()))
    if spec.get("append_event") or spec.get("complete"):
        paths.append("seldon_events.jsonl")
    subprocess.run(["git", "add", "--", *paths], check=True)
    subprocess.run(["git", "commit", "-q", "-m", f"{{stem}}: result", "--", *paths],
                   check=True)
mark("end")
# AD-035 R6: the CLI's stream ends in a result object whose `modelUsage` names the served model.
# The stub serves what `--model` asked for, unless the spec plants a substitution.
served = spec.get("served") or sys.argv[sys.argv.index("--model") + 1]
print(json.dumps({{"type": "result", "subtype": "success", "usage": {{"output_tokens": 1}},
                  "modelUsage": {{served: {{"outputTokens": 1, "inputTokens": 1}}}}}}))
sys.exit(spec.get("exit", 0))
'''


def write_stub(p: Path, spec: dict) -> None:
    spec_path = p / "bin" / "stub_spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    stub = p / "bin" / "claude"
    stub.write_text(STUB.format(python=sys.executable, repo=str(SELDON_REPO),
                                spec=str(spec_path), research=str(RESEARCH_YAML),
                                uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
                                db=NEO4J_DB), encoding="utf-8")
    stub.chmod(0o755)


def run_cli(p: Path, group, argv):
    """Invoke a click group with cwd at the project, as launchd would."""
    prev = Path.cwd()
    os.chdir(p)
    try:
        return CliRunner().invoke(group, argv, catch_exceptions=False)
    finally:
        os.chdir(prev)


def task_states(driver) -> dict:
    with driver.session(database=NEO4J_DB) as s:
        return {r["n"]: r["s"] for r in s.run(
            "MATCH (t:ResearchTask) RETURN t.name AS n, t.state AS s")}


# ----------------------------------------------------------------------- normalization

_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?")
_HEX_RE = re.compile(r"\b[0-9a-f]{7,40}\b")
_WALL_RE = re.compile(r"(\"wall_clock_s\": |in )\d+(?:\.\d+)?(s?)")


def normalize(text: str, project: Path) -> str:
    """Replace what differs between two runs of one scenario and nothing else.

    Paths, the host and pid in a holder id, uuids, timestamps, commit shas and wall clock.
    Ids are numbered by first appearance, so two transcripts are equal only when every id
    recurs in the same places.
    """
    import socket
    for form in {str(project.resolve()), str(project)}:
        text = text.replace(form, "<PROJ>")
    text = text.replace(str(Path(sys.executable)), "<PY>")
    text = re.sub(re.escape(socket.gethostname()) + r":\d+", "<HOST>:<PID>", text)
    for pattern, tag in ((_UUID_RE, "UUID"), (_HEX_RE, "HEX")):
        seen: dict[str, str] = {}
        text = pattern.sub(lambda m: seen.setdefault(m.group(0), f"<{tag}-{len(seen) + 1}>"),
                           text)
    text = _TS_RE.sub("<TS>", text)
    text = _WALL_RE.sub(lambda m: f"{m.group(1)}<WALL>{m.group(2)}", text)
    return text


def events_dump(p: Path) -> str:
    lines = []
    for raw in (p / "seldon_events.jsonl").read_text(encoding="utf-8").splitlines():
        if raw.strip():
            lines.append(json.dumps(json.loads(raw), sort_keys=True))
    return "\n".join(lines)
