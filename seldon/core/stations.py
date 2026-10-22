"""AD-037-R6's four inspection stations for a dispatched session: premise review, first article, milestone with
earned value, and andon with huddle (QC-002). Pure or filesystem-local: no Neo4j, no launch.

**What each station reads and writes** (record names are the event types below; every record carries `task_id`):

* **(a) premise review**, before launch: the task's `**Premises:**` block, plus one premise the dispatcher adds to
  every task (`environment_in_flight`). A false `check:` premise refuses the launch as `dispatch_refused` with reason
  `premise_false`; `judgment:` premises are listed in `dispatch_launched` and not evaluated (QC-003 supplies the
  calibrated checker, AD-037-R3 and R5).
* **(b) first article**: the session appends `first_article` after the first unit of a loop the task declares in
  `**First article:**`; the station runs the declared check over that output and writes `first_article_pass` or a
  `session_stop`.
* **(c) milestone**: the session appends `part_complete` at each Part boundary; the station runs the Part's
  `check:` criteria, computes CPI (earned value over actual cost; PMI 2003, ANSI/EIA-748) and writes `milestone`. A
  failed check writes a `session_stop`; CPI below the configured line writes a `huddle` and does not stop.
* **(d) andon and huddle** (AD-032 FC-28, FC-29): any station, the session or the operator writes `session_stop`; the
  session halts at its next boundary and writes `andon_halted`. A hard stop (spend or disk ceiling, or an operator's
  `--hard` for FC-32's toxic tier) that is not answered by `andon_halted` within the reap interval is reaped by the
  lease holder, which writes `andon_reaped`. A `huddle` stays open until `huddle_closed` names its cause and gate.

The prior art each piece is taken from: SAE AS9102B (first article: objective evidence before production); earned
value management (CPI = EV / AC; PMI, "Earned value: the good, the bad, and the ugly", 2003); jidoka and the andon
cord (Ohno 1988) for "any station stops the line, the stop waits on nobody"; Wheeler's individuals (XmR) chart for
R8's chart, drawn only from `qc.chart_min_points` points on (FC-15). See
`docs/design/AD-037_in_process_quality_control_for_dispatched_sessions.md` section 2.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import statistics
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import yaml

from seldon.core import criteria

# ------------------------------------------------------------------------------------------- the records

EVENT_PART_COMPLETE = "part_complete"
EVENT_MILESTONE = "milestone"
EVENT_FIRST_ARTICLE = "first_article"
EVENT_FIRST_ARTICLE_PASS = "first_article_pass"
EVENT_SESSION_STOP = "session_stop"
EVENT_ANDON_HALTED = "andon_halted"
EVENT_ANDON_REAPED = "andon_reaped"
EVENT_HUDDLE = "huddle"
EVENT_HUDDLE_CLOSED = "huddle_closed"
#: FRICTION-002 Part C: what the Stop hook found when the session tried to end (the milestone station reads it).
EVENT_STOP_GATE = "stop_gate"
#: FRICTION-002 Part D: one action the auto-mode classifier blocked, from the session's `PermissionDenied` hook.
EVENT_CLASSIFIER_BLOCK = "classifier_block"
#: How much of a blocked tool call's input `classifier_block` keeps: enough to judge a false positive by, bounded so a
#: blocked heredoc does not grow the tracked event store by its size.
CLASSIFIER_INPUT_CHARS = 500
#: The CLI's own text when its auto-mode breaker trips in a headless session (3 consecutive or 20 total blocks;
#: CLI 2.1.302: `Agent aborted: too many classifier denials in headless mode`). Read from the session's log.
CLASSIFIER_BREAKER_TEXT = "too many classifier denials in headless mode"
#: Station (a)'s refusal reasons, written on `dispatch_refused` (`seldon.core.dispatch.EVENT_REFUSED`).
REFUSED_PREMISE_FALSE = "premise_false"
REFUSED_ENVIRONMENT_IN_FLIGHT = "environment_in_flight"

#: The records that make each station live, by AD-037-R6 letter. AD-037-R9's opt-in precondition reads this
#: (`stations_live`), and `tests/test_dispatch_parallel_held.py` drives each through the code path.
STATION_RECORDS = {
    "a": ("dispatch_refused:" + REFUSED_PREMISE_FALSE, "dispatch_refused:" + REFUSED_ENVIRONMENT_IN_FLIGHT),
    "b": (EVENT_FIRST_ARTICLE, EVENT_FIRST_ARTICLE_PASS, EVENT_SESSION_STOP),
    "c": (EVENT_PART_COMPLETE, EVENT_MILESTONE),
    "d": (EVENT_SESSION_STOP, EVENT_ANDON_HALTED, EVENT_ANDON_REAPED, EVENT_HUDDLE, EVENT_HUDDLE_CLOSED),
}

#: The session-side exit code meaning "a stop is written: halt at this boundary". Distinct from 1 (error) and 2
#: (click usage), so a session's shell can tell a halt from a mistake.
HALT_EXIT = 3

#: Stop kinds. `line` is a station's or the session's stop; `andon` the operator's; `hard` the dispatcher's
#: enforced stop, the only kind that is ever reaped.
STOP_KINDS = ("line", "andon", "hard")

# ------------------------------------------------------------------------------------------- the config

#: `dispatch.stations` defaults. Each value's basis is stated, and each is overridable per project, so installing
#: this build changes no config file.
STATIONS_DEFAULTS = {
    # AD-037-R6 (c): "CPI below 0.8 opens a huddle without stopping." No measured basis; FC-15's chart replaces it
    # once 10 tasks exist.
    "cpi_huddle_below": 0.8,
    # AD-037-R7: inspection costs at most 10% of the task's estimate. No measured basis; the actual share is charted.
    "inspection_reserve_share": 0.10,
    # The judgment sampler's rate with a full reserve. ASSUMPTION, inert until QC-003 calibrates a checker: no
    # judgment output is read before then (AD-037-R3, R5). The rate falls linearly with the reserve (R7).
    "judgment_sample_rate": 0.25,
    # QC-002 Part C step 1: "nothing within three polls is a huddle". The task's number.
    "first_article_polls": 3,
    # QC-002 Part C step 2: a hard stop is reaped only when no `andon_halted` came within one poll interval.
    "reap_after_intervals": 1,
    # The spend ceiling of a hard stop, as a multiple of the task's declared estimate. INHERITED: every QC and SQ
    # task's stop condition is the estimate plus 20% (QC-002: 1.5M, stop at 1.8M; SQ-015 the same).
    "spend_ceiling_factor": 1.2,
    # DISP-001R Part B step 1: the spend ceiling's floor is the median token reading at the first inspection over
    # this many of the repository's most recent finished launches. The window is the task's number; the floor
    # itself is measured, never configured (`spend_floor`).
    "floor_launches": 10,
    # How long one `check:` command may run before it is a failure. ASSUMPTION: the longest single check in
    # this portfolio's tasks is a full seldon suite, about 15 minutes; twice that.
    "check_timeout_s": 1800,
    # FRICTION-002 Part C: how long the Stop hook may run all of a session's declared Parts' checks before the CLI
    # kills it (the hook's `timeout`, seconds). ASSUMPTION: two `check_timeout_s`, since a task's Parts rarely
    # carry more than two suite-sized checks; a killed hook lets the session end, and its milestones then wait
    # unanswered, which `seldon dispatch inspect` shows.
    "stop_gate_timeout_s": 3600,
    # LOOP-001 Part A (AD-034 ADDENDUM 04): what a Stop round's fingerprint masks before it is hashed, so two rounds
    # compare equal when only a volatile span differs. pytest prints its run time on its summary line ("1 failed in
    # 0.42s") on every run, so without the duration mask two identical pytest failures never match and the
    # no-progress rule could not fire on the commonest check; timestamps, addresses and temporary paths are the
    # same class. Each is a regular expression replaced by `<v>`. A pattern too broad hides real progress (the
    # session is let go a round early and is not merged); one too narrow leaves the CLI's own cap as the backstop.
    "no_progress_volatile": [
        r"\b\d+(?:\.\d+)?\s?(?:s|ms|sec|secs|seconds)\b",
        r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?",
        r"\b0x[0-9a-fA-F]+\b",
        r"pytest-\d+",
        r"\btmp[A-Za-z0-9_]{6,}\b",
    ],
    # Where the projects this task's environment includes are named (premise `environment_in_flight`): a
    # `path#key` reference to a list of sibling repository names (squiddy: `squiddy/kit.yaml#environment_packages`).
    # Unset means `decisions.repositories` in this project's seldon.yaml.
    "environment_ref": None,
    # STATION-001 (AD-037-R15): the python a check's `pytest`, `seldon` and `python` run as, and whose `bin` a check
    # and the dispatched session get first on PATH. A path relative to the project's primary checkout (squiddy:
    # `.venv/bin/python`, PEP 405), resolved and checked at load. Unset means the dispatcher's own interpreter
    # (`sys.executable`), which is right for a project whose environment IS the dispatcher's, as seldon's is.
    "interpreter": None,
}

#: Keys an earlier build read that are withdrawn, with why. The loader names the ruling, so a seldon.yaml that still
#: carries one is refused with its reason rather than as an unknown key.
WITHDRAWN_KEYS = {
    "stop_hook_block_cap": "withdrawn by LOOP-001 (AD-034 ADDENDUM 04): the Stop hook lets a session go when two "
                           "consecutive rounds make no progress, not at a count; the CLI's own cap is the backstop",
}

#: A `**Parts:**` header's shares must sum to 1 within this. Two-decimal shares of four Parts round to within 0.01.
PARTS_SUM_TOLERANCE = 0.011

#: Issue states in which a `premise_false` Issue still holds its task (seldon/domain/research.yaml, Issue).
ISSUE_OPEN_STATES = ("open", "in_progress", "blocked")


class StationsConfigError(ValueError):
    """A `dispatch.stations` value is malformed."""


def load_stations_config(cfg: dict, project_dir: Path | None = None) -> dict:
    """`dispatch.stations` over `STATIONS_DEFAULTS`, validated. Unknown keys refuse: a misspelt ceiling would
    otherwise be silently the default. A relative `interpreter` resolves against `project_dir` (`resolve_interpreter`);
    `load_dispatch_config` passes it and writes the absolute path back, so every later load sees the resolved one."""
    block = (cfg or {}).get("stations") or {}
    if not isinstance(block, dict):
        raise StationsConfigError(f"dispatch.stations must be a mapping, got {block!r}")
    withdrawn = sorted(set(block) & set(WITHDRAWN_KEYS))
    if withdrawn:
        raise StationsConfigError("; ".join(f"dispatch.stations.{k} is {WITHDRAWN_KEYS[k]}" for k in withdrawn))
    unknown = sorted(set(block) - set(STATIONS_DEFAULTS))
    if unknown:
        raise StationsConfigError(f"dispatch.stations has unknown key(s) {unknown}; known: {sorted(STATIONS_DEFAULTS)}")
    out = {**STATIONS_DEFAULTS, **block}
    for key in ("cpi_huddle_below", "inspection_reserve_share", "judgment_sample_rate", "spend_ceiling_factor",
                "check_timeout_s"):
        v = out[key]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
            raise StationsConfigError(f"dispatch.stations.{key} must be a positive number, got {v!r}")
    for key in ("first_article_polls", "reap_after_intervals", "stop_gate_timeout_s", "floor_launches"):
        v = out[key]
        if isinstance(v, bool) or not isinstance(v, int) or v < 1:
            raise StationsConfigError(f"dispatch.stations.{key} must be a whole number of at least 1, got {v!r}")
    vol = out["no_progress_volatile"]
    if not isinstance(vol, list) or not all(isinstance(x, str) for x in vol):
        raise StationsConfigError(f"dispatch.stations.no_progress_volatile must be a list of regular expressions, "
                                  f"got {vol!r}")
    for x in vol:
        try:
            re.compile(x)
        except re.error as exc:
            raise StationsConfigError(f"dispatch.stations.no_progress_volatile: {x!r} does not compile: {exc}") from exc
    out["interpreter"] = resolve_interpreter(out["interpreter"], project_dir)
    return out


def resolve_interpreter(value, project_dir: Path | None) -> str | None:
    """`dispatch.stations.interpreter` as an absolute path, or None when undeclared. A declared path that is not an
    executable file refuses here, never later as a silent fall back to the dispatcher's own python (AD-037-R15). The
    path is not resolved through symlinks: a venv's `bin/python` is a link, and its `bin` is what PATH needs."""
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise StationsConfigError(f"dispatch.stations.interpreter must be a non-empty path string, got {value!r}")
    path = Path(value).expanduser()
    if not path.is_absolute():
        if project_dir is None:
            raise StationsConfigError(f"dispatch.stations.interpreter {value!r} is relative and no project directory "
                                      f"was given to resolve it against")
        path = Path(project_dir).absolute() / path
    if not path.exists():
        raise StationsConfigError(f"dispatch.stations.interpreter {value!r} does not exist (looked for {path})")
    if not path.is_file() or not os.access(path, os.X_OK):
        raise StationsConfigError(f"dispatch.stations.interpreter {value!r} is not an executable file ({path})")
    return str(path)


def interpreter_kw(scfg: dict) -> dict:
    """`{"interpreter": <path>}` for a station's `run`, or `{}` when undeclared, so an undeclared project's call is
    today's call exactly."""
    return {"interpreter": scfg["interpreter"]} if scfg.get("interpreter") else {}


def interpreter_env(interpreter: str, env: dict) -> dict:
    """What a process under `interpreter` gets so that its children resolve the same python: the interpreter's `bin`
    first on `PATH`, and `VIRTUAL_ENV` its parent (what a venv's `activate` sets, PEP 405)."""
    bin_dir = Path(interpreter).parent
    rest = [x for x in (env.get("PATH") or "").split(os.pathsep) if x and x != str(bin_dir)]
    return {"PATH": os.pathsep.join([str(bin_dir), *rest]), "VIRTUAL_ENV": str(bin_dir.parent)}


# ------------------------------------------------------------------------------------------- the task file

_PARTS_RE = re.compile(r"^\s*\*\*Parts:\*\*\s*(?P<v>.+?)\s*$", re.MULTILINE)
_PART_ITEM_RE = re.compile(r"^(?:Part\s+)?(?P<name>[A-Za-z0-9][A-Za-z0-9_-]*)\s*[:=]?\s+(?P<share>\d*\.?\d+)$")
_PART_HEADING_RE = re.compile(r"^(?P<hashes>#{1,6})\s+Part\s+(?P<name>[A-Za-z0-9][A-Za-z0-9_-]*?)\s*[:.—-]", re.MULTILINE)
_ANY_HEADING_RE = re.compile(r"^(?P<hashes>#{1,6})\s", re.MULTILINE)
_PREMISES_HEADER_RE = re.compile(r"^\s*\*\*Premises:\*\*\s*(?P<rest>.*)$")
_PREMISE_RE = re.compile(r"^\s*(?:[-*]\s+)?premise:\s*(?P<statement>.+?)\s*\|\s*(?P<kind>check|judgment):\s*(?P<rest>.+?)\s*$")
_FIRST_ARTICLE_RE = re.compile(r"^\s*\*\*First article:\*\*\s*(?P<loop>[^,]+?)\s*,\s*(?P<rest>.+?)\s*$", re.MULTILINE)
_BACKTICK_RE = re.compile(r"`([^`]+)`")


def parse_parts(text: str) -> dict:
    """The `**Parts:**` header: `{declared, parts: [{name, share}], error}`. Shares must sum to 1.

    `A 0.35, B 0.25, C 0.25, D 0.15.` is the form; `Part A: 0.35` and `A=0.35` read the same."""
    m = _PARTS_RE.search(text)
    if not m:
        return {"declared": False, "parts": [], "error": None}
    raw = m.group("v").strip().rstrip(".").strip()
    parts, bad = [], []
    for item in (s.strip() for s in raw.split(",")):
        im = _PART_ITEM_RE.match(item)
        if not im:
            bad.append(item)
            continue
        parts.append({"name": im.group("name"), "share": float(im.group("share"))})
    if bad or not parts:
        return {"declared": True, "parts": [], "error": f"Parts entries do not parse as `<name> <share>`: {bad or raw!r}"}
    names = [p["name"] for p in parts]
    if len(set(names)) != len(names):
        return {"declared": True, "parts": [], "error": f"Parts names repeat: {names}"}
    total = sum(p["share"] for p in parts)
    if abs(total - 1.0) > PARTS_SUM_TOLERANCE:
        return {"declared": True, "parts": [], "error": f"Parts shares sum to {total:.3f}, not 1"}
    return {"declared": True, "parts": parts, "error": None}


def part_section(text: str, name: str) -> str | None:
    """The text of `## Part <name>: ...` up to the next heading of the same or a higher level."""
    for m in _PART_HEADING_RE.finditer(text):
        if m.group("name") != name:
            continue
        level = len(m.group("hashes"))
        end = len(text)
        for h in _ANY_HEADING_RE.finditer(text, m.end()):
            if len(h.group("hashes")) <= level:
                end = h.start()
                break
        return text[m.start():end]
    return None


def check_command(criterion: str) -> str | None:
    """The command of a criterion marked `check:` (AD-037-R1), or None for any other criterion.

    The forms in use: `` `check: CMD` rest ``, `` `check:` `CMD` rest ``, and a bare `check: CMD`. A backtick span is
    the command; with none, the rest of the line is."""
    c = criterion.strip()
    if c.startswith("`check:`"):
        m = _BACKTICK_RE.search(c[len("`check:`"):])
        return m.group(1).strip() if m else None
    if c.startswith("`check:"):
        end = c.find("`", 1)
        cmd = c[len("`check:"):end if end > 0 else None].strip()
        return cmd or None
    if c.startswith("check:"):
        rest = c[len("check:"):].strip()
        m = _BACKTICK_RE.match(rest)
        return (m.group(1).strip() if m else rest) or None
    return None


def judgment_criterion(criterion: str) -> str | None:
    c = criterion.strip()
    for lead in ("`judgment:`", "`judgment:", "judgment:"):
        if c.startswith(lead):
            return c[len(lead):].strip(" `") or None
    return None


def part_criteria(text: str, name: str) -> dict:
    """A Part's marked criteria: `{checks: [command], judgments: [why], section_found}`."""
    section = part_section(text, name)
    if section is None:
        return {"checks": [], "judgments": [], "section_found": False}
    found = [c for _, c in criteria.acceptance_criteria(section)]
    return {"checks": [cmd for cmd in (check_command(c) for c in found) if cmd],
            "judgments": [j for j in (judgment_criterion(c) for c in found) if j],
            "section_found": True}


def parse_premises(text: str) -> dict:
    """The `**Premises:**` block: `{declared, premises: [{line, statement, kind, command|why}], errors}`.

    Each line is `premise: <statement> | check: <command>` or `premise: <statement> | judgment: <why>`; the block
    runs from the header to the first blank line or heading. A line inside it that does not parse is an error, and
    station (a) refuses on it: a premise nobody can read is not a premise that holds."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not _PREMISES_HEADER_RE.match(line):
            continue
        out, errors = [], []
        rest = _PREMISES_HEADER_RE.match(line).group("rest").strip()
        body = ([(i + 1, rest)] if rest else []) + [(j + 1, lines[j]) for j in range(i + 1, len(lines))]
        for n, raw in body:
            if not raw.strip() or _ANY_HEADING_RE.match(raw):
                if n != i + 1:
                    break
                continue
            m = _PREMISE_RE.match(raw)
            if not m:
                errors.append({"line": n, "text": raw.strip()})
                continue
            value = m.group("rest").strip()
            span = _BACKTICK_RE.fullmatch(value)
            row = {"line": n, "statement": m.group("statement").strip(), "kind": m.group("kind")}
            row["command" if row["kind"] == "check" else "why"] = span.group(1).strip() if span else value
            out.append(row)
        return {"declared": True, "premises": out, "errors": errors}
    return {"declared": False, "premises": [], "errors": []}


def parse_first_articles(text: str) -> list:
    """`**First article:** <loop name>, <check command>` lines: `[{loop, command}]`. The command may be in backticks;
    `{output}` in it is replaced by the first unit's output path, which is also in `SELDON_FIRST_ARTICLE_OUTPUT`."""
    out = []
    for m in _FIRST_ARTICLE_RE.finditer(text):
        rest = m.group("rest").strip().rstrip(".")
        span = _BACKTICK_RE.search(rest)
        out.append({"loop": m.group("loop").strip(), "command": (span.group(1) if span else rest).strip()})
    return out


# ------------------------------------------------------------------------------------------- tokens

#: The header line `seldon.commands.dispatch._run` writes before each session's output in its log.
_LOG_HEADER_RE = re.compile(r"^=== \S+ \| dispatch \|")


def session_tokens(log_path: Path) -> dict:
    """Tokens the latest session in a dispatch log has used, from the CLI's stream-json `usage` (QC-002 Part A).

    `tokens` is input plus cache writes plus output, the measure every QC and SQ RESULT reports against its estimate
    (SQ-015 RESULT line 3); cache reads are reported separately and not counted. Each assistant message's usage is
    counted once, by message id (stream-json repeats a message's usage on each of its content blocks). Only the
    output after the log's last `=== ... | dispatch |` header is read: a relaunch appends to the same log."""
    if not log_path.is_file():
        return {"tokens": None, "cache_read": None, "messages": 0, "error": f"no log at {log_path}"}
    usage: dict[str, dict] = {}
    with log_path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if _LOG_HEADER_RE.match(line):
                usage = {}
                continue
            if not line.startswith("{"):
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = obj.get("message") if obj.get("type") == "assistant" else None
            if isinstance(msg, dict) and isinstance(msg.get("usage"), dict):
                usage[msg.get("id") or obj.get("uuid") or str(len(usage))] = msg["usage"]
    tokens = sum(int(u.get("input_tokens") or 0) + int(u.get("cache_creation_input_tokens") or 0)
                 + int(u.get("output_tokens") or 0) for u in usage.values())
    cache = sum(int(u.get("cache_read_input_tokens") or 0) for u in usage.values())
    return {"tokens": tokens, "cache_read": cache, "messages": len(usage), "error": None}


_LOG_HEADER_TS_RE = re.compile(r"^=== (?P<ts>\S+) \| dispatch \|")


def _usage_tokens(u: dict) -> int:
    return (int(u.get("input_tokens") or 0) + int(u.get("cache_creation_input_tokens") or 0)
            + int(u.get("output_tokens") or 0))


def tokens_at(log_path: Path, launched_at: str, within_s: float) -> int | None:
    """Tokens (as `session_tokens` counts them) the session launched at `launched_at` had used `within_s` seconds
    after its log header: the reading its first inspection saw (DISP-001R Part B step 1).

    The session is the log's first segment whose `=== <ts> | dispatch |` header is at or after `launched_at` (the
    header is written after `dispatch_launched`, and a relaunch appends a later segment). An assistant record is
    counted when its own `timestamp` is within the window. None when the log or the segment is absent.
    """
    if not Path(log_path).is_file():
        return None
    start = _parse_ts(launched_at)
    header, usage = None, {}
    with Path(log_path).open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = _LOG_HEADER_TS_RE.match(line)
            if m:
                if header is not None:
                    break
                ts = _parse_ts(m.group("ts"))
                if ts >= start:
                    header = ts
                continue
            if header is None or not line.startswith("{"):
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = obj.get("message") if obj.get("type") == "assistant" else None
            if not (isinstance(msg, dict) and isinstance(msg.get("usage"), dict) and obj.get("timestamp")):
                continue
            if (_parse_ts(obj["timestamp"]) - header).total_seconds() <= within_s:
                usage[msg.get("id") or obj.get("uuid") or str(len(usage))] = msg["usage"]
    if header is None:
        return None
    return sum(_usage_tokens(u) for u in usage.values())


def spend_floor(project_dir: Path, events: list, within_s: float, launches: int, until: str | None = None,
                exclude_session: str | None = None) -> dict:
    """The spend ceiling's floor, measured (DISP-001R Part B step 1): the median of the token reading at the first
    inspection (`within_s` after launch) over the repository's last `launches` finished launches.

    A launch counts once it has a `dispatch_finished` (any outcome: DISP-001's reaped session is a data point) and
    its log yields a positive reading; a launch that never reached the model reads zero and says nothing about the
    cost of loading a session. `until` cuts the history at a timestamp (the weekly chart). `exclude_session` leaves
    out the session being inspected. Returns `{value, n, window, within_s, launches: [...]}`; `value` is None
    with no data point, and the ceiling is then the estimate's alone.
    """
    finished = {(e.get("payload") or {}).get("child_session_id") for e in events
                if e.get("event_type") == "dispatch_finished" and (until is None or _ts(e) <= until)}
    candidates = [e for e in events if e.get("event_type") == "dispatch_launched"
                  and (e.get("payload") or {}).get("child_session_id") in finished
                  and (e.get("payload") or {}).get("child_session_id") != exclude_session
                  and (e.get("payload") or {}).get("log_path")]
    points = []
    for e in reversed(candidates):
        if len(points) >= launches:
            break
        p = e["payload"]
        tokens = tokens_at(Path(project_dir) / p["log_path"], p.get("launched_at") or _ts(e), within_s)
        if tokens:
            points.append({"task_id": p.get("task_id"), "source_file": p.get("source_file"),
                           "child_session_id": p.get("child_session_id"), "launched_at": p.get("launched_at"),
                           "tokens": tokens})
    points.reverse()
    value = int(statistics.median([pt["tokens"] for pt in points])) if points else None
    return {"value": value, "n": len(points), "window": launches, "within_s": within_s, "launches": points}


def spend_ceiling(estimate: int | None, factor: float, floor: dict | None) -> dict:
    """The token ceiling of a hard stop (DISP-001R Part B step 1): never below the cost of loading a session.

    `ceiling = max(estimate, floor) x factor`. The task wrote `max(estimate x factor, floor)`; a ceiling AT the
    median first-inspection reading would stop about half the sessions whose estimate is below it at their first
    inspection, which is DISP-001's defect again, so the factor's margin applies to whichever term binds. None
    when the task declares no estimate (no ceiling is invented for it).
    """
    if not estimate:
        return {"ceiling": None, "estimate": estimate, "factor": factor, "binding": None}
    value = (floor or {}).get("value")
    binding = "floor" if value and value > estimate else "estimate"
    out = {"ceiling": int(max(estimate, value or 0) * factor), "estimate": estimate, "factor": factor,
           "binding": binding}
    if binding == "floor":
        out["floor"] = {k: floor[k] for k in ("value", "n", "window", "within_s", "launches")}
    return out


def floor_by_week(project_dir: Path, events: list, within_s: float, launches: int) -> list:
    """`spend_floor` as it stood at the end of each ISO week with a finished launch (`seldon qc chart`, DISP-001R
    Part B step 1). `[{week, value, n}]`, oldest first."""
    weeks: dict[str, str] = {}
    for e in events:
        if e.get("event_type") == "dispatch_finished" and _ts(e):
            y, w, _ = _parse_ts(_ts(e)).isocalendar()
            key = f"{y}-W{w:02d}"
            weeks[key] = max(weeks.get(key, ""), _ts(e))
    out = []
    for week in sorted(weeks):
        f = spend_floor(project_dir, events, within_s, launches, until=weeks[week])
        out.append({"week": week, "value": f["value"], "n": f["n"]})
    return out


def cpi(parts: list, completed: list, tokens: int | None, estimate: int | None) -> dict:
    """Earned value over actual cost, both as shares of the task's estimate (AD-037-R6 c).

    Earned is the planned share of the completed Parts; actual is tokens used over the estimate. CPI above 1 is
    under budget. `None` when the estimate is zero or unknown, or no token has been counted: no ratio is invented."""
    shares = {p["name"]: p["share"] for p in parts}
    unknown = [c for c in completed if c not in shares]
    earned = round(sum(shares[c] for c in set(completed) if c in shares), 6)
    actual = (tokens / estimate) if (tokens and estimate) else None
    return {"earned": earned, "actual": None if actual is None else round(actual, 6),
            "cpi": None if not actual else round(earned / actual, 4), "unknown_parts": unknown}


# ------------------------------------------------------------------------------------------- running a check

#: A usage error is the command not running, not the command reporting a defect: POSIX utilities, argparse and
#: click exit 2 with a `usage:` line; pytest exits 4 with `ERROR: usage:`. 126 and 127 are the shell's "not
#: executable" and "not found". Such a check has produced no reading (an inspection-equipment failure, in MSA's
#: terms), so it is recorded `unrunnable` and opens a huddle; it never counts as a pass.
_USAGE_LINE_RE = re.compile(r"^(?:error:\s*)?usage:", re.IGNORECASE | re.MULTILINE)
UNRUNNABLE_EXITS = (126, 127)
_TAIL_CHARS = 1500


#: Commands a check names that run as `<this python> -m <module>` (AD-037 ADDENDUM 02). `pytest`, so a check runs
#: against the interpreter the dispatcher runs in, not whichever `pytest` is first on launchd's PATH; `seldon`, so a
#: check runs the code of the tree it runs in: the console script imports the primary checkout's code (seldon is
#: installed editable from it), and a branch that changed the code its check depends on could never pass its own
#: gate (PA-002's Part B, 2026-10-19). STATION-001 (AD-037-R15): `<this python>` is the project's declared
#: interpreter when it declares one.
MODULE_COMMANDS = ("pytest", "seldon")
#: First words that ARE the interpreter, replaced by a declared one (AD-037-R15). Undeclared, they are left to PATH,
#: as AD-037 ADDENDUM 02 left them.
PYTHON_COMMANDS = ("python", "python3")


def check_argv(command: str, interpreter: str | None = None) -> list:
    """The command as argv, with a `MODULE_COMMANDS` first word run as `<interpreter> -m <it>` (the dispatcher's own
    `sys.executable` when undeclared), and, when an interpreter is declared, a `PYTHON_COMMANDS` first word replaced
    by it."""
    argv = shlex.split(command)
    if argv and argv[0] in MODULE_COMMANDS:
        argv = [interpreter or sys.executable, "-m", argv[0], *argv[1:]]
    elif argv and interpreter and argv[0] in PYTHON_COMMANDS:
        argv = [interpreter, *argv[1:]]
    return argv


def tree_path(cwd: Path, env: dict) -> str:
    """`PYTHONPATH` for a check run in `cwd`: the tree first, then whatever the environment already carried. A child
    the check starts (a git hook, a test's subprocess) inherits it, so it imports the tree's code too; `python -m`
    alone puts the tree on the check's own path and on no child's (AD-037 ADDENDUM 02)."""
    rest = [x for x in (env.get("PYTHONPATH") or "").split(os.pathsep) if x and x != str(cwd)]
    return os.pathsep.join([str(cwd), *rest])


def output_fingerprint(exit_code, stdout: str, stderr: str, volatile: list | tuple = ()) -> str:
    """sha256 over a check's exit code, stdout and stderr, each with the `volatile` patterns replaced by `<v>`
    (LOOP-001 Part A). Two runs with the same fingerprint told the session nothing new."""
    def mask(text: str) -> str:
        for pat in volatile:
            text = re.sub(pat, "<v>", text)
        return text
    body = json.dumps([exit_code, mask(stdout or ""), mask(stderr or "")], ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def run_check(command: str, cwd: Path, timeout_s: float, env: dict | None = None,
              output: str | None = None, volatile: list | tuple | None = None, interpreter: str | None = None) -> dict:
    """Run one `check:` command in `cwd`, with `cwd` first on `PYTHONPATH` (`tree_path`). `outcome` is `pass`
    (exit 0), `fail`, or `unrunnable` (no reading). The row names the interpreter and the path it ran with, and
    carries `output_sha256` (`output_fingerprint`, masking `volatile`; the configured default when None).

    `interpreter` is the project's declared python (AD-037-R15): the check's `pytest`, `seldon` and `python` run as
    it, its `bin` is first on `PATH` and `VIRTUAL_ENV` is set (`interpreter_env`), and the row records it and the
    `pytest` that `PATH` now resolves. None is today's check: the dispatcher's interpreter, its PATH, today's row."""
    if volatile is None:
        volatile = STATIONS_DEFAULTS["no_progress_volatile"]
    started = time.monotonic()
    run_env = dict(os.environ if env is None else env)
    run_env["PYTHONPATH"] = tree_path(Path(cwd), run_env)
    row = {"command": command, "interpreter": interpreter or sys.executable, "pythonpath": run_env["PYTHONPATH"]}
    if interpreter:
        run_env.update(interpreter_env(interpreter, run_env))
        row["pytest"] = shutil.which("pytest", path=run_env["PATH"])
    try:
        argv = check_argv(command.replace("{output}", output) if output else command, interpreter)
    except ValueError as exc:
        return {**row, "outcome": "unrunnable", "exit": None, "seconds": 0.0, "tail": f"does not parse: {exc}"}
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        run_env.pop(var, None)
    if output:
        run_env["SELDON_FIRST_ARTICLE_OUTPUT"] = output
    try:
        proc = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout_s, env=run_env)
    except FileNotFoundError as exc:
        return {**row, "outcome": "unrunnable", "exit": 127, "seconds": round(time.monotonic() - started, 3),
                "tail": str(exc)}
    except subprocess.TimeoutExpired:
        return {**row, "outcome": "fail", "exit": None, "seconds": round(time.monotonic() - started, 3),
                "tail": f"timed out after {timeout_s}s"}
    text = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode == 0:
        outcome = "pass"
    elif proc.returncode in UNRUNNABLE_EXITS or (proc.returncode in (2, 4) and _USAGE_LINE_RE.search(text)):
        outcome = "unrunnable"
    else:
        outcome = "fail"
    return {**row, "outcome": outcome, "exit": proc.returncode, "seconds": round(time.monotonic() - started, 3),
            "tail": text[-_TAIL_CHARS:],
            "output_sha256": output_fingerprint(proc.returncode, proc.stdout, proc.stderr, volatile)}


#: A huddle's reason when a check names a file its tree lacks and the session's branch holds (AD-038-R4): the station
#: ran in the wrong tree, which is the dispatcher's defect, and `seldon.core.redrive` answers it without a person.
REASON_WRONG_TREE = "check_unrunnable_wrong_tree"
#: The same, when no branch holds the file either: the check names something that does not exist anywhere.
REASON_MISSING_FILE = "check_unrunnable_missing_file"
#: Commands whose purpose is to test for a file: a missing file is their reading, not an unrunnable check.
_EXISTENCE_TESTS = ("test", "[")
#: A token is a path when it has a directory part or one of these suffixes (after any pytest `::node` id).
_PATH_SUFFIXES = (".py", ".md", ".yaml", ".yml", ".json", ".jsonl", ".txt", ".toml", ".sh", ".csv")


def named_paths(command: str) -> list:
    """The file paths a check command names, in order: argv tokens that look like paths, with a pytest node id's
    `::...` removed. Options (`-k`, `--x=y`) and their values are not paths. Empty for an existence test."""
    try:
        argv = shlex.split(command)
    except ValueError:
        return []
    if not argv or Path(argv[0]).name in _EXISTENCE_TESTS:
        return []
    out = []
    for tok in argv[1:]:
        if tok.startswith("-") or "://" in tok or "{" in tok:
            continue
        path = tok.split("::", 1)[0]
        if "/" in path or path.endswith(_PATH_SUFFIXES):
            out.append(path)
    return out


def missing_file_reading(command: str, cwd: Path, branch: str | None) -> dict | None:
    """AD-038-R4: when a check names a file absent from the tree it ran in, the check could not be run as written.

    Returns None when every named file is present; otherwise `{missing, reason, branch}`, with `reason`
    `REASON_WRONG_TREE` when the session's `branch` holds every missing file (`git cat-file -e <branch>:<path>`),
    else `REASON_MISSING_FILE`.
    """
    missing = [p for p in named_paths(command) if not (Path(cwd) / p).exists()]
    if not missing:
        return None
    on_branch = bool(branch) and all(
        subprocess.run(["git", "-C", str(cwd), "cat-file", "-e", f"{branch}:{p}"], capture_output=True).returncode == 0
        for p in missing)
    return {"missing": missing, "reason": REASON_WRONG_TREE if on_branch else REASON_MISSING_FILE, "branch": branch}


def run_station_check(command: str, cwd: Path, timeout_s: float, branch: str | None = None,
                      run: Callable[..., dict] = run_check, **run_kw) -> dict:
    """`run_check`, then AD-038-R4: a check that did not pass and names a file its tree lacks is `unrunnable`
    (a huddle), never `fail` (a stop). A genuinely failing check, whose files are all present, still fails.
    `run_kw` (the Stop gate's `volatile`) is passed to `run` only when given."""
    r = run(command, cwd, timeout_s, **run_kw)
    if r.get("outcome") == "pass":
        return r
    miss = missing_file_reading(command, Path(cwd), branch)
    if miss is None:
        return r
    return {**r, "outcome": "unrunnable", "reason": miss["reason"], "missing": miss["missing"], "cwd": str(cwd)}


# ------------------------------------------------------------------------------------------- the event store

def _ts(event: dict) -> str:
    return event.get("timestamp") or ""


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def last_launch(events: list, task_id: str) -> dict | None:
    """The task's most recent `dispatch_launched` event."""
    hits = [e for e in events if e.get("event_type") == "dispatch_launched"
            and (e.get("payload") or {}).get("task_id") == task_id]
    return hits[-1] if hits else None


def launch_for_session(events: list, session_id: str | None) -> dict | None:
    """The `dispatch_launched` event whose `child_session_id` is this session's (`SELDON_SESSION_ID`)."""
    if not session_id:
        return None
    hits = [e for e in events if e.get("event_type") == "dispatch_launched"
            and (e.get("payload") or {}).get("child_session_id") == session_id]
    return hits[-1] if hits else None


def task_records(events: list, task_id: str, since: str = "") -> list:
    """This task's station records written at or after `since` (the launch's timestamp)."""
    return [e for e in events if (e.get("payload") or {}).get("task_id") == task_id and _ts(e) >= since]


def log_growth_s(log: Path | None, now: datetime) -> float | None:
    """Seconds since the session's log last grew (its mtime), or None with no log to read."""
    if log is None or not Path(log).is_file():
        return None
    return (now - datetime.fromtimestamp(Path(log).stat().st_mtime, timezone.utc)).total_seconds()


def pending_hard_stop(records: list) -> dict | None:
    """The first hard `session_stop` in `records` not yet answered by `andon_halted` or `andon_reaped`: what the
    PreToolUse gate delivers at the session's next tool call (DISP-001R Part B step 2)."""
    return pending_stop([e for e in records if e.get("event_type") != EVENT_SESSION_STOP
                         or (e.get("payload") or {}).get("kind") == "hard"])


def pending_stop(records: list) -> dict | None:
    """The first `session_stop` not yet answered by `andon_halted` or `andon_reaped`."""
    answered = {(e.get("payload") or {}).get("stop_event_id") for e in records
                if e.get("event_type") in (EVENT_ANDON_HALTED, EVENT_ANDON_REAPED)}
    for e in records:
        if e.get("event_type") == EVENT_SESSION_STOP and e.get("event_id") not in answered:
            return e
    return None


def open_huddles(events: list) -> list:
    """Huddles with no `huddle_closed` and a reading, cause or gate still missing (FC-29: a huddle names all
    three). Each row is the huddle's payload plus its timestamp."""
    closed = {(e.get("payload") or {}).get("huddle_id") for e in events if e.get("event_type") == EVENT_HUDDLE_CLOSED}
    out = []
    for e in events:
        if e.get("event_type") != EVENT_HUDDLE:
            continue
        p = e.get("payload") or {}
        if p.get("huddle_id") in closed or (p.get("reading") and p.get("cause") and p.get("gate")):
            continue
        out.append({**p, "opened_at": _ts(e)})
    return out


def huddle_payload(task_id: str | None, reading: str, opened_by: str, cause: str | None = None,
                   gate: str | None = None, **extra) -> dict:
    return {"task_id": task_id, "huddle_id": str(uuid.uuid4()), "opened_by": opened_by, "reading": reading,
            "cause": cause, "gate": gate, **extra}


# ------------------------------------------------------------------------------------------- the inspection pass

Emit = Callable[[str, dict], dict | None]


def judgment_plan(judgments: list, reserve_left_share: float, base_rate: float, judge: Callable[[], str]) -> dict:
    """R7's sampler: which `judgment:` outputs a reading judge would read at this boundary, and whether it may.

    The rate is `base_rate` scaled by the share of the inspection reserve still unspent, so it falls first when the
    reserve runs low; `check:` commands are never in its scope. `judge()` resolves the calibrated checker
    (`seldon.models.resolve_judge`); until QC-003 supplies a passing report it refuses, and the plan is recorded as
    deferred with zero calls."""
    rate = round(max(0.0, min(1.0, base_rate * max(0.0, reserve_left_share))), 4)
    k = min(len(judgments), int(round(rate * len(judgments) + 0.4999))) if judgments and rate > 0 else 0
    sampled = judgments[:k]
    try:
        judge_id = judge() if sampled else None
        status = "would_read" if sampled else "none_sampled"
    except Exception as exc:                                        # noqa: BLE001 - recorded, never swallowed
        judge_id, status = None, f"deferred: {type(exc).__name__}: {exc}"
    return {"rate": rate, "items": len(judgments), "sampled": len(sampled), "judge": judge_id, "status": status,
            "model_calls": 0}


def round_fingerprint(parts: list) -> str:
    """sha256 over every check a Stop round ran: part, command, outcome, exit and output (`output_sha256`; for a row
    without one, a check that never produced output or a stubbed runner, its exit and `tail`). Equal fingerprints
    in consecutive refused rounds are LOOP-001's no progress."""
    rows = sorted([part["part"] or "", r.get("command") or "", r.get("outcome"), r.get("exit"),
                   r.get("output_sha256") or hashlib.sha256(str(r.get("tail") or "").encode("utf-8")).hexdigest()]
                  for part in parts for r in part["checks"])
    return hashlib.sha256(json.dumps(rows).encode("utf-8")).hexdigest()


def stop_gate(project_dir: Path, launch: dict, events: list, scfg: dict, cwd: Path, branch: str | None, *,
              run: Callable[..., dict] = run_check, stop_hook_active: bool = False,
              floor: dict | None = None) -> dict:
    """FRICTION-002 Part C: the Stop hook's decision for a dispatched session that is trying to end.

    Runs the `check:` criteria of every Part the session has declared complete (`part_complete` since its launch)
    in the session's own tree (`cwd`, its worktree), and decides:

    * every check passes, or no Part is declared: the session may end (`verdict: pass`). The negative control
      (AD-038-R6): a correct session ends on its first Stop.
    * a check fails and the session is under its token ceiling (the `**Spend:**` estimate times
      `spend_ceiling_factor`): the end is refused (`verdict: block`) with the failing commands in `reason`, which
      the CLI hands back to the model as the next instruction.
    * a check fails at or over the ceiling: the session may end, and a hard stop (`session_stop`, kind `hard`,
      reason `spend_ceiling`) is written with the failures (`verdict: ceiling`).

    * a check fails, under the ceiling, and this round's checks produced exactly what the previous refused round's
      did (`round_fingerprint`): the session may end (`verdict: no_progress`, with `no_progress: {rounds: [n-1,
      n]}`). LOOP-001 Part A (AD-034 ADDENDUM 04): each refused Stop is a round, a round that repeats its
      predecessor carried no new information, and there is no count and no cap; the finish reads the verdict as
      `stop_gate_unpassed`, so the branch is not merged. The CLI's own refusal cap stays as the backstop.

    A check that could not run (`unrunnable`) never blocks: a defective command would hold the session forever.
    The milestone station opens its huddle from this record. Prior art: Claude Code's Stop hook as a completion
    gate ("give Claude a pass/fail check"), docs/research/2026-10-17_vendor_survey_codex_claude_code.html section 1;
    for the no-progress rule, the vendor's loop pattern (code.claude.com/docs/en/workflows: "keep fixing until a
    check passes ... or two rounds in a row make no progress") and Reflexion (Shinn et al. 2023).

    Returns ``{"record": <stop_gate payload>, "block": bool, "reason": str | None, "hard_stop": payload | None}``.
    """
    from seldon.core.dispatch import spend_tokens, parse_headers, HEADER_SPEND

    lp = launch["payload"]
    task_id = lp["task_id"]
    since = _ts(launch)
    records = task_records(events, task_id, since)
    task_file = Path(project_dir) / lp["source_file"]
    text = task_file.read_text(encoding="utf-8", errors="surrogateescape") if task_file.is_file() else ""
    declared: dict[str, list] = {}
    for e in records:
        if e.get("event_type") == EVENT_PART_COMPLETE:
            declared.setdefault((e.get("payload") or {}).get("part"), []).append(e["event_id"])
    parts, failed = [], []
    for name, answers in declared.items():
        crit = part_criteria(text, name)
        results = [run_station_check(cmd, cwd, scfg["check_timeout_s"], branch, run=run,
                                     volatile=scfg["no_progress_volatile"], **interpreter_kw(scfg))
                   for cmd in crit["checks"]]
        parts.append({"part": name, "answers": answers, "checks": results, "section_found": crit["section_found"]})
        failed += [{"part": name, **r} for r in results if r["outcome"] == "fail"]
    estimate = spend_tokens(parse_headers(text)[HEADER_SPEND]) if text else None
    log = Path(project_dir) / lp["log_path"] if lp.get("log_path") else None
    tokens = session_tokens(log)["tokens"] if log and log.is_file() else None
    # DISP-001R Part B step 1: `floor` is `spend_floor`'s measurement; the ceiling is never below it.
    limit = spend_ceiling(estimate, scfg["spend_ceiling_factor"], floor)
    ceiling = limit["ceiling"]
    over = ceiling is not None and tokens is not None and tokens >= ceiling
    verdict = "pass" if not failed else ("ceiling" if over else "block")
    # LOOP-001 Part A: this session's earlier rounds (its refused Stops since the launch), and whether this one
    # repeats the last of them.
    prior = [(e.get("payload") or {}) for e in records if e.get("event_type") == EVENT_STOP_GATE
             and (e.get("payload") or {}).get("child_session_id") == lp.get("child_session_id")]
    refused = [g for g in prior if g.get("verdict") == "block"]
    fingerprint = round_fingerprint(parts)
    rnd, no_progress = len(refused) + 1, None
    if verdict == "block" and prior and prior[-1].get("verdict") == "block" \
            and prior[-1].get("fingerprint") == fingerprint:
        verdict = "no_progress"
        no_progress = {"rounds": [prior[-1].get("round") or len(refused), rnd]}
    record = {"task_id": task_id, "child_session_id": lp.get("child_session_id"), "cwd": str(cwd), "branch": branch,
              # AD-037 ADDENDUM 02: what a check's `seldon` and `pytest` ran as, and the tree they imported; the
              # project's declared interpreter when it declares one (AD-037-R15).
              "interpreter": scfg.get("interpreter") or sys.executable, "path": tree_path(Path(cwd), dict(os.environ)),
              "parts": parts, "failed": [f["command"] for f in failed], "tokens": tokens, "ceiling": ceiling,
              "verdict": verdict, "stop_hook_active": bool(stop_hook_active),
              "round": rnd, "fingerprint": fingerprint}
    if no_progress:
        record["no_progress"] = no_progress
    reason, hard = None, None
    if verdict == "block":
        reason = ("FRICTION-002 stop gate: this session may not end while a declared Part's check fails. "
                  + " ".join(f"Part {f['part']}: `{f['command']}` exit {f['exit']}"
                             + (f" ({f['tail'][-300:].strip()})" if f.get("tail") else "") + "."
                             for f in failed)
                  + f" Fix the work so the check passes, then end the session again (round {rnd}; {tokens} of "
                    f"{ceiling} tokens used). If it cannot be made to pass, write the RESULT saying why and end: a "
                    f"round whose check output repeats this one's lets the session go (`no_progress`), and its "
                    f"branch is NOT merged.")
    elif verdict == "ceiling":
        hard = {"task_id": task_id, "station": "stop_gate", "kind": "hard", "reason": "spend_ceiling",
                "by": "dispatcher", "reading": {"tokens": tokens, **limit},
                "failed": record["failed"]}
    return {"record": record, "block": verdict == "block", "reason": reason, "hard_stop": hard}


def gate_reading(records: list, part_event_id: str) -> dict | None:
    """The newest `stop_gate` part entry that answers `part_event_id`, or None while no Stop has run its checks."""
    for e in reversed(records):
        if e.get("event_type") != EVENT_STOP_GATE:
            continue
        for part in (e.get("payload") or {}).get("parts") or []:
            if part_event_id in (part.get("answers") or []):
                return {**part, "stop_gate_event_id": e["event_id"]}
    return None


def inspect(project_dir: Path, task_id: str, events: list, scfg: dict, poll_interval_s: float, emit: Emit, *,
            run: Callable[..., dict] = run_check, judge: Callable[[], str] | None = None,
            disk: Callable[[], dict] | None = None, now: datetime | None = None) -> dict:
    """One inspection of an in-flight task: stations (b), (c) and (d). Idempotent: every record it answers is keyed
    by the answered record's event id, so two inspectors (the holder's loop and a later pass) never answer twice.

    Returns what it did, and `reap`: the hard stop due for reaping, or None. Only the lease holder acts on `reap`.
    """
    from seldon.core.dispatch import spend_tokens, parse_headers, HEADER_SPEND

    now = now or datetime.now(timezone.utc)
    launch = last_launch(events, task_id)
    if launch is None:
        return {"task_id": task_id, "error": "no dispatch_launched for this task", "reap": None}
    lp = launch["payload"]
    since = _ts(launch)
    records = task_records(events, task_id, since)
    task_file = Path(project_dir) / lp["source_file"]
    text = task_file.read_text(encoding="utf-8", errors="surrogateescape") if task_file.is_file() else ""
    estimate = spend_tokens(parse_headers(text)[HEADER_SPEND]) if text else None
    parts = parse_parts(text)
    answered = {(e.get("payload") or {}).get("answers") for e in records}
    reserve = int((estimate or 0) * scfg["inspection_reserve_share"])
    judge = judge or (lambda: (_ for _ in ()).throw(RuntimeError("no checker wired")))
    out = {"task_id": task_id, "milestones": [], "first_articles": [], "stops": [], "huddles": [], "reap": None}

    def stop(station: str, kind: str, reason: str, **extra) -> None:
        payload = {"task_id": task_id, "station": station, "kind": kind, "reason": reason, "by": "dispatcher",
                   **extra}
        emit(EVENT_SESSION_STOP, payload)
        out["stops"].append(payload)

    def huddle(reading: str, opened_by: str, **extra) -> None:
        payload = huddle_payload(task_id, reading, opened_by, **extra)
        emit(EVENT_HUDDLE, payload)
        out["huddles"].append(payload)

    # (c) milestones, in the order the session wrote them.
    completed: list[str] = []
    spent_inspection = 0
    for e in records:
        if e.get("event_type") != EVENT_PART_COMPLETE:
            continue
        p = e.get("payload") or {}
        completed.append(p.get("part"))
        if e["event_id"] in answered:
            continue
        crit = part_criteria(text, p.get("part"))
        # FRICTION-002 Part C: the station runs no check of its own. The session's Stop hook runs the Part's checks
        # in the session's tree when it tries to end and records `stop_gate`; the milestone is the reading of that
        # record, and waits, unanswered, until a Stop has run them. A failure there keeps the session working
        # (the hook refuses the end), so it is recorded here as a defect and is not a line stop.
        gate = gate_reading(records, e["event_id"])
        if gate is None:
            continue
        results = gate["checks"]
        value = cpi(parts["parts"], completed, p.get("tokens"), estimate)
        plan = judgment_plan(crit["judgments"], (reserve - spent_inspection) / reserve if reserve else 0.0,
                             scfg["judgment_sample_rate"], judge)
        defects = [r for r in results if r["outcome"] == "fail"]
        unrunnable = [r for r in results if r["outcome"] == "unrunnable"]
        milestone = {"task_id": task_id, "answers": e["event_id"], "part": p.get("part"),
                     "checks_source": "stop_gate", "stop_gate_event_id": gate["stop_gate_event_id"],
                     "planned_share": p.get("planned_share"), "tokens": p.get("tokens"), "estimate": estimate,
                     **value, "checks": results, "section_found": crit["section_found"], "defect": bool(defects),
                     "judgment": plan,
                     "inspection": {"check_seconds": round(sum(r["seconds"] for r in results), 3),
                                    "model_tokens": plan["model_calls"], "reserve_tokens": reserve,
                                    "share_of_estimate": 0.0 if estimate else None}}
        emit(EVENT_MILESTONE, milestone)
        out["milestones"].append(milestone)
        for r in unrunnable:
            extra = {"reason": r["reason"], "missing": r["missing"], "cwd": r["cwd"]} if r.get("reason") else {}
            huddle(f"check could not run at Part {p.get('part')}: `{r['command']}` exit {r['exit']}"
                   + (f" ({r['reason']}: {', '.join(r['missing'])} absent from {r['cwd']})" if extra else ""),
                   "check_unrunnable", part=p.get("part"), **extra)
        if value["cpi"] is not None and value["cpi"] < scfg["cpi_huddle_below"]:
            huddle(f"CPI {value['cpi']} below {scfg['cpi_huddle_below']} at Part {p.get('part')} "
                   f"(earned {value['earned']}, actual {value['actual']})", "cpi", part=p.get("part"))

    # (b) first articles.
    declared = {fa["loop"]: fa["command"] for fa in parse_first_articles(text)}
    for e in records:
        if e.get("event_type") != EVENT_FIRST_ARTICLE or e["event_id"] in answered:
            continue
        p = e.get("payload") or {}
        command = declared.get(p.get("loop"))
        if command is None:
            stop("first_article", "line", "first_article_undeclared", answers=e["event_id"], loop=p.get("loop"))
            continue
        where = Path(p["cwd"]) if p.get("cwd") and Path(p["cwd"]).is_dir() else Path(project_dir)
        r = run(command, where, scfg["check_timeout_s"], output=p.get("output"), **interpreter_kw(scfg))
        if r.get("outcome") != "pass":
            miss = missing_file_reading(command.replace("{output}", p.get("output") or ""), where, p.get("branch"))
            if miss is not None:
                r = {**r, "outcome": "unrunnable", "reason": miss["reason"], "missing": miss["missing"],
                     "cwd": str(where)}
        row = {"task_id": task_id, "answers": e["event_id"], "loop": p.get("loop"), "output": p.get("output"),
               "check": r}
        out["first_articles"].append(row)
        if r["outcome"] == "pass":
            emit(EVENT_FIRST_ARTICLE_PASS, row)
        elif r.get("reason") in (REASON_WRONG_TREE, REASON_MISSING_FILE):
            # AD-038-R4: a file absent from the tree is a huddle, never a stop.
            huddle(f"first-article check could not run for loop {p.get('loop')!r}: {r['reason']}: "
                   f"{', '.join(r['missing'])} absent from {r['cwd']}", "check_unrunnable", loop=p.get("loop"),
                   answers=e["event_id"], reason=r["reason"], missing=r["missing"], cwd=r["cwd"])
        else:
            stop("first_article", "line", f"first_article_{r['outcome']}", answers=e["event_id"], loop=p.get("loop"),
                 check=r)

    # (d) the dispatcher's hard stops: spend and disk ceilings. One per reason per launch.
    hard_reasons = {(e.get("payload") or {}).get("reason") for e in records
                    if e.get("event_type") == EVENT_SESSION_STOP and (e.get("payload") or {}).get("kind") == "hard"}
    log = Path(project_dir) / lp["log_path"] if lp.get("log_path") else None
    used = session_tokens(log)["tokens"] if log else None
    # DISP-001R Part B step 1: the ceiling is never below the measured cost of loading a session.
    limit = spend_ceiling(estimate, scfg["spend_ceiling_factor"],
                          spend_floor(project_dir, events, poll_interval_s, scfg["floor_launches"],
                                      exclude_session=lp.get("child_session_id")) if estimate else None)
    out["ceiling"] = limit
    if limit["ceiling"] is not None and used is not None and used > limit["ceiling"] \
            and "spend_ceiling" not in hard_reasons:
        stop("dispatcher", "hard", "spend_ceiling", reading={"tokens": used, **limit})
    if disk is not None and "disk_ceiling" not in hard_reasons:
        d = disk()
        if not d.get("ok", True):
            stop("dispatcher", "hard", "disk_ceiling", reading=d)

    # (d) the reap: a hard stop with no `andon_halted` within the reap interval, of a session whose log has not
    # grown for that interval either (DISP-001R Part B step 3). A session writing to its log is alive and is given
    # its tool boundary, where the PreToolUse gate delivers the stop (`tool_gate`); the reap is the backstop.
    # Read over the records as they stood when this inspection began: a stop written just now is not yet due.
    halted = {(e.get("payload") or {}).get("stop_event_id") for e in records
              if e.get("event_type") in (EVENT_ANDON_HALTED, EVENT_ANDON_REAPED)}
    wait_s = scfg["reap_after_intervals"] * poll_interval_s
    for e in records:
        p = e.get("payload") or {}
        if e.get("event_type") == EVENT_SESSION_STOP and p.get("kind") == "hard" and e.get("event_id") not in halted:
            age = (now - _parse_ts(_ts(e))).total_seconds()
            if age < wait_s:
                continue
            growth = log_growth_s(log, now)
            if growth is not None and growth < wait_s:
                out["reap_deferred"] = {"stop_event_id": e["event_id"], "age_s": round(age, 1), "wait_s": wait_s,
                                        "last_log_growth_s": round(growth, 1)}
                break
            out["reap"] = {"stop_event_id": e["event_id"], "reason": p.get("reason"), "age_s": round(age, 1),
                           "wait_s": wait_s, "last_log_growth_s": None if growth is None else round(growth, 1)}
            break
    return out


# ------------------------------------------------------------------------------------------- station (a)

def environment_repositories(project_dir: Path, config: dict, scfg: dict) -> dict:
    """`{name: path}` of the repositories this project's environment names (premise `environment_in_flight`).

    `dispatch.stations.environment_ref` (`path#key`, a list of sibling repository names, e.g. squiddy's
    `squiddy/kit.yaml#environment_packages`) when set; otherwise `decisions.repositories` (seldon's squiddy and
    arnold). A name resolves to the sibling directory of that name beside this project."""
    project_dir = Path(project_dir).resolve()      # `Path('.').parent` is `.`: resolve before taking the parent
    ref = scfg.get("environment_ref")
    if ref:
        path, _, key = str(ref).partition("#")
        data = yaml.safe_load((project_dir / path).read_text(encoding="utf-8")) or {}
        names = data
        for part in key.split("."):
            names = (names or {}).get(part) if isinstance(names, dict) else None
        if not isinstance(names, list):
            raise StationsConfigError(f"dispatch.stations.environment_ref {ref!r} does not name a list")
        return {str(n): str((project_dir.parent / str(n)).resolve()) for n in names}
    repos = ((config or {}).get("decisions") or {}).get("repositories") or {}
    return {str(n): str((project_dir / p).resolve()) for n, p in repos.items()}


def environment_premise(project_dir: Path, config: dict, scfg: dict, lease_held: Callable[[Path], dict | None]) -> dict:
    """The premise the dispatcher adds to every task (QC-002 Part B step 3, from SQ-015's kit pass): no other
    project's dispatcher holds its lease on a repository this task's environment names. `lease_held(repo)` returns
    the holding lease body or None."""
    held = {}
    for name, path in environment_repositories(project_dir, config, scfg).items():
        if Path(path).resolve() == Path(project_dir).resolve():
            continue
        body = lease_held(Path(path))
        if body:
            held[name] = {"path": path, "holder": body.get("holder"), "task": body.get("task"),
                          "acquired_at": body.get("acquired_at")}
    return {"statement": "no other project's dispatcher holds a lease on a repository this task's environment names",
            "kind": "check", "source": "dispatcher", "outcome": "false" if held else "true", "held": held}


def review_premises(project_dir: Path, text: str, scfg: dict, run: Callable[..., dict] = run_check) -> dict:
    """Station (a) over the task's own `**Premises:**` block. `check:` premises run; `judgment:` ones are listed for
    the R2 checker and not evaluated. `ok` is False on any false, unrunnable or unreadable premise."""
    parsed = parse_premises(text)
    rows = []
    for p in parsed["premises"]:
        if p["kind"] == "check":
            r = run(p["command"], Path(project_dir), scfg["check_timeout_s"], **interpreter_kw(scfg))
            rows.append({**p, "outcome": "true" if r["outcome"] == "pass" else
                         ("false" if r["outcome"] == "fail" else "unrunnable"), "check": r})
        else:
            rows.append({**p, "outcome": "not_evaluated", "evaluated_by": "R2 checker (QC-003)"})
    for err in parsed["errors"]:
        rows.append({"line": err["line"], "statement": err["text"], "kind": "unreadable", "outcome": "unreadable"})
    false = [r for r in rows if r["outcome"] in ("false", "unrunnable", "unreadable")]
    return {"declared": parsed["declared"], "premises": rows, "false": false,
            "judgment": [r for r in rows if r["kind"] == "judgment"], "ok": not false}


# ------------------------------------------------------------------------------------------- R8's chart

def xmr_limits(values: list) -> dict:
    """Wheeler's individuals chart: centre line the mean, natural process limits mean ± 2.66 × the mean moving
    range (2.66 = 3 / d2, d2 = 1.128 for subgroups of 2)."""
    mean = sum(values) / len(values)
    mr = [abs(b - a) for a, b in zip(values, values[1:])]
    mr_bar = sum(mr) / len(mr) if mr else 0.0
    return {"mean": round(mean, 4), "mr_bar": round(mr_bar, 4), "unpl": round(mean + 2.66 * mr_bar, 4),
            "lnpl": round(mean - 2.66 * mr_bar, 4)}


def chart(events: list, project: str, seed: list | None = None, min_points: int = 10) -> dict:
    """AD-037-R8's per-project reading: premise-false rate, first-article reject rate, milestone defect rate, CPI
    per task and huddles per task, from the event store, plus seed rows (tasks measured before the stations ran,
    CPI only). A first reading is reported, not gated."""
    def n(kind, pred=lambda p: True):
        return [e for e in events if e.get("event_type") == kind and pred(e.get("payload") or {})]

    reviews = n("dispatch_launched", lambda p: "premises" in p) + n(
        "dispatch_refused", lambda p: p.get("reason") in (REFUSED_PREMISE_FALSE, REFUSED_ENVIRONMENT_IN_FLIGHT))
    premise_false = n("dispatch_refused", lambda p: p.get("reason") == REFUSED_PREMISE_FALSE)
    articles = n(EVENT_FIRST_ARTICLE)
    rejects = n(EVENT_SESSION_STOP, lambda p: p.get("station") == "first_article")
    milestones = n(EVENT_MILESTONE)
    defects = [m for m in milestones if (m.get("payload") or {}).get("defect")]

    def rate(k, d):
        return {"k": len(k), "n": len(d), "rate": round(len(k) / len(d), 4) if d else None}

    by_task: dict[str, dict] = {}
    for m in milestones:
        p = m["payload"]
        row = by_task.setdefault(p["task_id"], {"task": p["task_id"][:8], "project": project, "source": "milestone"})
        row.update({"estimate": p.get("estimate"), "actual_tokens": p.get("tokens"), "cpi": p.get("cpi"),
                    "earned": p.get("earned"),
                    "inspection_share": (p.get("inspection") or {}).get("share_of_estimate")})
    for h in n(EVENT_HUDDLE):
        tid = (h.get("payload") or {}).get("task_id")
        if tid:
            by_task.setdefault(tid, {"task": tid[:8], "project": project, "source": "huddle"})
            by_task[tid]["huddles"] = by_task[tid].get("huddles", 0) + 1
    rows = list(seed or []) + list(by_task.values())
    cpis = [r["cpi"] for r in rows if isinstance(r.get("cpi"), (int, float))]
    individuals = ({"drawn": True, "n": len(cpis), **xmr_limits(cpis)} if len(cpis) >= min_points
                   else {"drawn": False, "n": len(cpis), "needs": min_points})
    return {"project": project, "premise_false_rate": rate(premise_false, reviews),
            "first_article_reject_rate": rate(rejects, articles), "milestone_defect_rate": rate(defects, milestones),
            "tasks": rows, "huddles": len(n(EVENT_HUDDLE)), "individuals_chart": individuals,
            "classifier": classifier_per_launch(events)}


def classifier_per_launch(events: list) -> list:
    """FRICTION-002 Part D step 2: per launch, its permission mode, how many actions the auto-mode classifier blocked
    (`classifier_block`) and whether its breaker stopped the session (`session_stop` from station `classifier`).
    A launch in another mode is listed with its mode, so a zero is never read as "auto mode blocked nothing"."""
    rows, by_child = [], {}
    for e in events:
        p = e.get("payload") or {}
        if e.get("event_type") == "dispatch_launched":
            row = {"task": (p.get("task_id") or "")[:8], "task_id": p.get("task_id"),
                   "child_session_id": p.get("child_session_id"), "launched_at": p.get("launched_at"),
                   "permission_mode": p.get("permission_mode"), "blocks": 0, "breaker": False}
            rows.append(row)
            if p.get("child_session_id"):
                by_child[p["child_session_id"]] = row
        elif e.get("event_type") == EVENT_CLASSIFIER_BLOCK and p.get("child_session_id") in by_child:
            by_child[p["child_session_id"]]["blocks"] += 1
        elif e.get("event_type") == EVENT_SESSION_STOP and p.get("station") == "classifier":
            for row in reversed(rows):
                if row["task_id"] == p.get("task_id"):
                    row["breaker"] = True
                    break
    return rows


def load_seed(path: Path) -> list:
    """The pre-station CPI rows (`qc.chart_seed`): each `{task, project, estimate, actual, basis}`; CPI is
    estimate over actual, the completed task's earned value (1.0) over its actual share."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    rows = []
    for r in data.get("tasks") or []:
        est, act = float(r["estimate"]), float(r["actual"])
        rows.append({"task": r["task"], "project": r["project"], "source": "seed", "estimate": est,
                     "actual_tokens": act, "ratio": round(act / est, 4), "cpi": round(est / act, 4),
                     "lower_bound": bool(r.get("lower_bound")), "basis": r.get("basis")})
    return rows


#: The registration refusal for a task with no readable `**Parts:**` header (QC-002 Part A step 4).
PARTS_REFUSAL = "parts_undeclared"


def parts_baseline(project_dir: Path, config: dict) -> set[str]:
    """Task paths registered before QC-002's merge (`qc.parts_baseline` in seldon.yaml), which are not re-checked,
    as `criterion_unmarked`'s baseline is (QC-001 Part E)."""
    rel = ((config or {}).get("qc") or {}).get("parts_baseline")
    if not rel:
        return set()
    path = Path(project_dir) / rel
    if not path.is_file():
        raise FileNotFoundError(f"seldon.yaml qc.parts_baseline names {path}, which does not exist")
    return {ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")}


def parts_registration_refusal(task_path: Path, project_dir: Path, config: dict) -> str | None:
    """`parts_undeclared` for a task with no `**Parts:**` header, or one that does not parse; None otherwise.

    Without the header station (c) has no planned shares and CPI cannot be computed (AD-037-R6 c).

    A project is held to the gate once it names its baseline (`qc.parts_baseline`), because absence is the refusal:
    a project whose registered tasks were never listed would have every one of them refused at once. Seldon names
    its baseline in QC-002; each other project opts in by writing its own from its own graph."""
    if not ((config or {}).get("qc") or {}).get("parts_baseline"):
        return None
    try:
        rel = str(Path(task_path).resolve().relative_to(Path(project_dir).resolve()))
    except ValueError:
        rel = str(task_path)
    if rel in parts_baseline(project_dir, config):
        return None
    parsed = parse_parts(Path(task_path).read_text(encoding="utf-8", errors="replace"))
    if parsed["declared"] and not parsed["error"]:
        return None
    why = parsed["error"] or "no `**Parts:**` header"
    return (f"{PARTS_REFUSAL}: {why}. A task lists each Part's share of its estimate, e.g. "
            f"`**Parts:** A 0.35, B 0.25, C 0.25, D 0.15.`, so station (c) can compute CPI (AD-037-R6 c, QC-002)")


#: AD-038-R5's refusal at registration: a `check:` premise that is false when the task is registered.
PREMISE_REGISTRATION_REFUSAL = "premise_false"


def premises_registration_refusal(task_path: Path, project_dir: Path, config: dict,
                                  run: Callable[..., dict] = run_check) -> str | None:
    """AD-038-R5: run the task's `check:` premises at registration; None when every one holds.

    A false, unrunnable or unreadable premise refuses with each command's exit and the tail of its output, so the
    author sees it in the same turn (SQ-016 waited 19 hours at the dispatcher for a one-line path error). Run in the
    registering project with station (a)'s timeout. Dispatch keeps its own review: the environment may change between.
    `judgment:` premises are not evaluated here either (station (a) lists them for the R2 checker).
    """
    text = Path(task_path).read_text(encoding="utf-8", errors="replace")
    if not parse_premises(text)["declared"]:
        return None
    try:
        scfg = load_stations_config((config or {}).get("dispatch") or {}, Path(project_dir))
    except StationsConfigError:
        scfg = dict(STATIONS_DEFAULTS)
    review = review_premises(Path(project_dir), text, scfg, run=run)
    if review["ok"]:
        return None
    lines = []
    for r in review["false"]:
        chk = r.get("check") or {}
        tail = " ".join((chk.get("tail") or "").split())[-300:]
        lines.append(f"`{r.get('command') or r.get('statement')}` is {r['outcome']}"
                     + (f" (exit {chk.get('exit')})" if chk else "") + (f": {tail}" if tail else "")
                     + f" [premise: {r.get('statement')}]")
    return (f"{PREMISE_REGISTRATION_REFUSAL}: {len(lines)} premise(s) do not hold at registration (AD-038-R5): "
            + "; ".join(lines))


def stations_live() -> dict:
    """AD-037-R9's first precondition, read from the code path: each station's records are written by a function
    that exists here. `tests/test_dispatch_parallel_held.py` drives each one."""
    import seldon.core.dispatch as D
    from seldon.commands import dispatch as cmd
    from seldon.commands import dispatch_stations as st
    live = {
        "a": (hasattr(cmd, "_premise_review") and REFUSED_PREMISE_FALSE in D.REFUSAL_REASONS
              and REFUSED_ENVIRONMENT_IN_FLIGHT in D.REFUSAL_REASONS),
        "b": hasattr(st, "first_article_command") and hasattr(st, "inspect_in_flight"),
        "c": hasattr(st, "part_complete_command") and hasattr(st, "holder_inspector"),
        "d": all(hasattr(st, n) for n in ("stop_command", "huddle_command", "boundary_command", "record_reap")),
        # The worktree supervisor (SEL-004) does not inspect its session yet: its session writes to the worktree's
        # event store, which the primary's inspector does not read. Parallel dispatch is what R9 gates, so the
        # stations are not live for it until this is True.
        "worktree": False,
    }
    return {**live, "all": all(live.values())}
