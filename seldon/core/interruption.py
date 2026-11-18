"""A session the network cut off is resumed, not blocked for a person (SEL-040 Part B, AD-034-R21..R23).

**Why this exists.** hazbrief HB-189 (2026-11-16) ran 4 h 41 min and committed its work on its branch. At 10:37:00Z
the laptop lid closed (`pmset -g log`: "Entering Sleep state due to 'Clamshell Sleep'", 16 s after the session's last
model record). In the dark-wake windows that followed, the CLI retried the API ten times (`api_retry`, attempt 10 of
10, no HTTP status) and ended on its own synthetic message "API Error: Can't reach the API server - check your internet
or DNS (ENOTFOUND)", exit 1. The session never reached its Stop hook, so the finish read "Parts declared and no stop
gate ran" and recorded `stop_gate_unpassed`: blocked, for a person. Desktop wrote a resume addendum and redrove it by
hand. Nothing in that sequence needed a person; the cause was the transport, not the session's work.

**Prior art.** Kubernetes Job pod failure policy (KEP-3329, stable in 1.31): a failed pod is CLASSED before it is
counted. A pod that ended on an infrastructure disruption (the `DisruptionTarget` condition) takes the action
`Ignore`: it is restarted and not counted toward `backoffLimit`; a listed exit code takes `FailJob`; everything else
counts. The KEP's stated problem is HB-189's: a single retry counter "regardless of the root cause of the failures".
Batch schedulers draw the same line (Slurm requeues a job whose node failed and not one that exited non-zero; named,
not fetched). Seldon's own: AD-038-R2 (a stop the dispatcher caused is redriven by the dispatcher), `seldon dispatch
redrive` (a kept worktree is resumable), SEL-034 (a terminal task stops its session).

**What the dispatcher can tell apart, and what it cannot.** It reads three things, each recorded on the finish:

* ``transport_error``: the CLI's own last message is its synthetic "API Error" naming a connection failure
  (``dispatch.interruption.transport_patterns``: ENOTFOUND, ECONNREFUSED, ECONNRESET, ETIMEDOUT, EAI_AGAIN, "Can't
  reach the API server", "Connection error", "fetch failed"). Decisive.
* ``retries_exhausted``: the CLI's ``api_retry`` records reached their ``max_retries`` after the session's last real
  model turn, with no client-error status (4xx other than 408 and 429). Decisive: the API did not answer.
* ``host_slept``: the host's power log (``dispatch.interruption.host_sleep_command``, macOS ``pmset -g log``) shows a
  Sleep between the session's last model record and its end. Corroboration only: it says WHY the transport failed
  (a closed lid) and is never needed when either decisive reading is present.

A closed lid and a dropped network look the same to the CLI (both are a transport failure) and are resumed alike; the
host log, when present, says which it was. A process killed from outside (a signal exit with no ``result`` record and
no dispatcher stop) is ambiguous: the operating system, an out-of-memory kill and an operator's kill all look so. With
``host_slept`` beside it, it is classed ``interrupted``; without, the dispatcher cannot tell, and the finish is
recorded as it always was (blocked for a person) with the ambiguity named in ``interruption.undecided``.

Never interrupted: a session whose RESULT is committed (its work is done; the regate answers it, AD-034-R10), a task
the graph shows terminal, a session the dispatcher or a station stopped, and a session its Stop gate let go
(``no_progress`` or ``ceiling``): it ran to its gate and failed it.
"""
from __future__ import annotations

import json
import re
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path

#: The finish outcomes this module adds (`dispatch_worktree.OUTCOMES`) and the stop reasons a finish carries in
#: `failure`, which `seldon.core.redrive.answered_stop` reads.
INTERRUPTED = "interrupted"
INTERRUPTED_THRICE = "interrupted_thrice"

#: AD-034-R22: an interrupted task is redriven at most this many times; the next interruption blocks it with
#: `interrupted_thrice`. A ruling, not a tunable: the outcome's name says three, and a task that loses its transport
#: three times is telling the operator something about the host that no automatic retry answers.
MAX_RESUMES = 2

#: The record a pass writes when an interrupted task waits because the API did not answer its probe.
EVENT_PROBE = "interruption_probe"

#: The config block under `dispatch:`.
CONFIG_KEY = "interruption"

#: Defaults for `dispatch.interruption`. Each is overridden by the project's seldon.yaml.
DEFAULTS = {
    # The CLI's own words for a connection that never reached the API (CLI 2.1.325, HB-189's tail; Node's
    # `getaddrinfo`/socket error codes, which the CLI quotes in parentheses).
    "transport_patterns": [r"\bENOTFOUND\b", r"\bECONNREFUSED\b", r"\bECONNRESET\b", r"\bETIMEDOUT\b",
                           r"\bEAI_AGAIN\b", r"\bEHOSTUNREACH\b", r"\bENETUNREACH\b",
                           r"Can't reach the API server", r"Connection error", r"fetch failed"],
    # The host's power log; an empty list turns the corroboration off (a host without `pmset`).
    "host_sleep_command": ["pmset", "-g", "log"],
    # How long the power log may take to read. Measured: 3.6 s for the whole log on the operator's laptop
    # (2026-11-17), so ten times that is generous and still bounded.
    "host_sleep_timeout_s": 30,
    # "Once the API answers" (SEL-040 Part A): a TCP connect to the API's host. No model call and no tokens: the
    # same reachability the CLI failed on (DNS resolution and a socket), not the API's health.
    "probe_host": "api.anthropic.com",
    "probe_port": 443,
    "probe_timeout_s": 5,
}

#: The power-log lines that mean the host went to sleep (`pmset -g log`'s event column).
_SLEEP_RE = re.compile(r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [+-]\d{4}) +Sleep +\t?(?P<what>.*)$")

#: Statuses that say the API answered and refused the request itself: not a transport failure.
_CLIENT_ERRORS_TRANSIENT = (408, 429)


class InterruptionConfigError(ValueError):
    """`dispatch.interruption` does not validate."""


def load_settings(block) -> dict:
    """`dispatch.interruption` with its defaults, validated. Raises InterruptionConfigError."""
    if block is None:
        block = {}
    if not isinstance(block, dict):
        raise InterruptionConfigError(f"dispatch.{CONFIG_KEY} must be a mapping, got {block!r}")
    unknown = sorted(set(block) - set(DEFAULTS))
    if unknown:
        raise InterruptionConfigError(f"dispatch.{CONFIG_KEY} has unknown keys {unknown}; known: {sorted(DEFAULTS)}")
    out = {**DEFAULTS, **block}
    pats = out["transport_patterns"]
    if not isinstance(pats, list) or not pats or not all(isinstance(p, str) and p for p in pats):
        raise InterruptionConfigError(f"dispatch.{CONFIG_KEY}.transport_patterns must be a non-empty list of "
                                      f"regular expressions, got {pats!r}")
    try:
        [re.compile(p) for p in pats]
    except re.error as exc:
        raise InterruptionConfigError(f"dispatch.{CONFIG_KEY}.transport_patterns: {exc}") from exc
    cmd = out["host_sleep_command"]
    if not isinstance(cmd, list) or not all(isinstance(c, str) and c for c in cmd):
        raise InterruptionConfigError(f"dispatch.{CONFIG_KEY}.host_sleep_command must be a list of strings "
                                      f"(empty turns it off), got {cmd!r}")
    for key in ("host_sleep_timeout_s", "probe_timeout_s", "probe_port"):
        v = out[key]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
            raise InterruptionConfigError(f"dispatch.{CONFIG_KEY}.{key} must be a positive number, got {v!r}")
    if not isinstance(out["probe_host"], str) or not out["probe_host"].strip():
        raise InterruptionConfigError(f"dispatch.{CONFIG_KEY}.probe_host must be a host name, got "
                                      f"{out['probe_host']!r}")
    return out


# ------------------------------------------------------------------------------------------- reading the tail

def _records(lines: list):
    for ln in lines:
        if ln.startswith("{"):
            try:
                obj = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                yield obj


def _text_of(obj: dict) -> str:
    msg = obj.get("message") or {}
    parts = msg.get("content") or []
    return " ".join(str(p.get("text") or "") for p in parts if isinstance(p, dict) and p.get("type") == "text")


def _parse_ts(value) -> datetime | None:
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def read_tail(lines: list, settings: dict) -> dict:
    """What the session's own stream says about how it ended. `lines` are the session's log lines (one segment).

    Returns ``{last_model_at, transport_error, retries, retries_exhausted, result_record, synthetic_text}``:
    ``last_model_at`` is the timestamp of the last record the API produced (an assistant record not marked
    ``<synthetic>``); a tool result after it is local work and does not move it. Everything else is read from the
    records after that assistant record.
    """
    recs = list(_records(lines))
    last_real = -1
    last_model_at = None
    for i, obj in enumerate(recs):
        if obj.get("type") == "assistant" and (obj.get("message") or {}).get("model") != "<synthetic>":
            last_real = i
            last_model_at = obj.get("timestamp") or last_model_at
    tail = recs[last_real + 1:]
    retries = [o for o in tail if o.get("type") == "system" and o.get("subtype") == "api_retry"]
    synthetic = [_text_of(o) for o in tail
                 if o.get("type") == "assistant" and (o.get("message") or {}).get("model") == "<synthetic>"]
    transport = None
    for text in synthetic:
        if text.startswith("API Error") and any(re.search(p, text) for p in settings["transport_patterns"]):
            transport = text[:300]
    exhausted = False
    if retries:
        last = retries[-1]
        status = last.get("error_status")
        client_refusal = isinstance(status, int) and 400 <= status < 500 and status not in _CLIENT_ERRORS_TRANSIENT
        max_r = last.get("max_retries")
        exhausted = (isinstance(max_r, int) and isinstance(last.get("attempt"), int) and last["attempt"] >= max_r
                     and not client_refusal)
    return {"last_model_at": last_model_at, "transport_error": transport,
            "retries": [{k: r.get(k) for k in ("attempt", "max_retries", "error_status", "error")} for r in retries],
            "retries_exhausted": exhausted, "result_record": any(o.get("type") == "result" for o in recs),
            "synthetic_text": synthetic[-1][:300] if synthetic else None}


def host_sleeps(settings: dict, start: datetime | None, end: datetime, run=subprocess.run) -> dict:
    """The host's Sleep entries between `start` and `end`, from its power log. `{read, sleeps, error}`.

    Never raises: the reading is corroboration, and a host whose log cannot be read is reported as such.
    """
    cmd = settings["host_sleep_command"]
    if not cmd:
        return {"read": False, "sleeps": [], "error": "host_sleep_command is empty (off)"}
    if start is None:
        return {"read": False, "sleeps": [], "error": "no model record to start the window from"}
    try:
        r = run(cmd, capture_output=True, text=True, timeout=settings["host_sleep_timeout_s"])
    except (OSError, subprocess.SubprocessError) as exc:
        return {"read": False, "sleeps": [], "error": f"{type(exc).__name__}: {exc}"[:300]}
    if r.returncode != 0:
        return {"read": False, "sleeps": [], "error": f"exit {r.returncode}: {(r.stderr or '').strip()[:300]}"}
    out = []
    for ln in r.stdout.splitlines():
        m = _SLEEP_RE.match(ln)
        if not m:
            continue
        ts = datetime.strptime(m.group("ts"), "%Y-%m-%d %H:%M:%S %z")
        if start <= ts <= end:
            out.append({"at": ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                        "what": " ".join(m.group("what").split())[:160]})
    return {"read": True, "sleeps": out, "error": None}


def classify(*, lines: list, exit_code, result_committed: bool, gate: dict, stopped: list, settings: dict,
             ended_at: datetime | None = None, sleeps=None) -> dict:
    """Was this session interrupted by its transport? ``{interrupted, evidence, undecided, tail, host}``.

    Args:
        lines: The session's log segment.
        exit_code: The CLI's exit code (negative for a signal, as `subprocess` reports it).
        result_committed: The task's RESULT is committed on its branch.
        gate: The finish's Stop-gate reading (`_gate_reading`).
        stopped: The `session_stop` payloads recorded for this launch (a station's or the dispatcher's stop).
        settings: `load_settings` output.
        ended_at: When the session ended (default: now).
        sleeps: `host_sleeps`-shaped callable `(start, end) -> dict`; default reads the host's log.
    """
    tail = read_tail(lines, settings)
    out = {"interrupted": False, "evidence": [], "undecided": None, "tail": tail, "host": None, "excluded": None}
    # The stream's own evidence is read first and kept on every exclusion, so a reader of the finish sees that the
    # transport failed even when that did not decide it.
    if tail["transport_error"]:
        out["evidence"].append("transport_error")
    if tail["retries_exhausted"]:
        out["evidence"].append("retries_exhausted")
    if result_committed:
        out["excluded"] = "result_committed"
    elif stopped:
        out["excluded"] = f"stopped: {', '.join(str(s.get('reason')) for s in stopped)}"
    elif gate.get("verdict") in ("no_progress", "ceiling"):
        out["excluded"] = f"stop_gate_{gate['verdict']}"
    if out["excluded"]:
        return out
    killed = isinstance(exit_code, int) and exit_code < 0 and not tail["result_record"]
    end = ended_at or datetime.now(timezone.utc)
    if out["evidence"] or killed:
        start = _parse_ts(tail["last_model_at"])
        host = (sleeps or (lambda s, e: host_sleeps(settings, s, e)))(start, end)
        out["host"] = host
        if host.get("sleeps"):
            out["evidence"].append("host_slept")
    if killed:
        if "host_slept" in out["evidence"]:
            out["evidence"].append("killed_no_result")
        elif not (tail["transport_error"] or tail["retries_exhausted"]):
            out["undecided"] = (f"the session was killed (exit {exit_code}) with no result record and no dispatcher "
                                f"stop, and the host log shows no sleep: an operating-system kill, an out-of-memory "
                                f"kill and an operator's kill look alike, so it is blocked for a person as before")
    out["interrupted"] = bool({"transport_error", "retries_exhausted", "killed_no_result"} & set(out["evidence"]))
    return out


def worth_recording(reading: dict) -> bool:
    """Does a reading say anything beyond "an ordinary failure"? Only then does the finish carry it, so an ordinary
    `session_failed` or `stop_gate_unpassed` record is what it was before SEL-040."""
    return bool(reading.get("interrupted") or reading.get("evidence") or reading.get("undecided"))


# ------------------------------------------------------------------------------------------- counting and probing

def prior_interruptions(events: list, task_id: str) -> list:
    """This task's earlier interrupted finishes (`interrupted` or `interrupted_thrice`), oldest first."""
    return [e for e in events if e.get("event_type") == "dispatch_finished"
            and (e.get("payload") or {}).get("task_id") == task_id
            and (e.get("payload") or {}).get("outcome") in (INTERRUPTED, INTERRUPTED_THRICE)]


def probe(settings: dict, connect=socket.create_connection) -> dict:
    """Does the API's host answer a TCP connect? `{ok, host, port, error}`. No model call; never raises."""
    host, port = settings["probe_host"], int(settings["probe_port"])
    try:
        conn = connect((host, port), timeout=settings["probe_timeout_s"])
    except OSError as exc:
        return {"ok": False, "host": host, "port": port, "error": f"{type(exc).__name__}: {exc}"[:300]}
    try:
        conn.close()
    except OSError:
        pass
    return {"ok": True, "host": host, "port": port, "error": None}


# ------------------------------------------------------------------------------------------- the resume

def resume_plan(project_dir: Path, events: list, task_id: str, git=None) -> dict | None:
    """The kept worktree a relaunch of this task resumes in, or None for a fresh launch.

    A plan exists when the task's newest finish is `interrupted`, a `dispatch_redrive` answered it, no launch came
    after that redrive, and the finish's worktree is still on disk on its branch. Returns ``{worktree, name,
    branch, base, last_commit, last_subject, interrupted_at, evidence, prior_tokens, resumes, answers}``.
    ``prior_tokens`` is every interrupted session's tokens so far (AD-034-R22: they count toward the task's cap).
    """
    from seldon.core import worktree as WT
    git = git or WT.git
    finishes = [e for e in events if e.get("event_type") == "dispatch_finished"
                and (e.get("payload") or {}).get("task_id") == task_id]
    if not finishes or (finishes[-1].get("payload") or {}).get("outcome") != INTERRUPTED:
        return None
    fin = finishes[-1]
    fp = fin["payload"]
    after = [e for e in events if str(e.get("timestamp") or "") >= str(fin.get("timestamp") or "")]
    redriven = any(e.get("event_type") == "dispatch_redrive" and (e.get("payload") or {}).get("task_id") == task_id
                   for e in after)
    relaunched = any(e.get("event_type") == "dispatch_launched" and (e.get("payload") or {}).get("task_id") == task_id
                     for e in after)
    if not redriven or relaunched:
        return None
    rel, branch = fp.get("worktree"), fp.get("branch")
    if not rel or not branch:
        return None
    wt = Path(project_dir) / rel
    if not wt.is_dir():
        return None
    on = git(wt, "rev-parse", "--abbrev-ref", "HEAD")
    if on.returncode != 0 or on.stdout.strip() != branch:
        return None
    head = git(wt, "log", "-1", "--format=%H%x00%s")
    sha, _, subject = head.stdout.strip().partition("\x00") if head.returncode == 0 else ("", "", "")
    inter = fp.get("interruption") or {}
    return {"worktree": rel, "name": Path(rel).name, "branch": branch, "base": fp.get("base"),
            "last_commit": sha or None, "last_subject": subject or None,
            "interrupted_at": inter.get("ended_at") or fin.get("timestamp"),
            "evidence": inter.get("evidence") or [], "prior_tokens": int(inter.get("carried_tokens") or 0),
            "resumes": len(prior_interruptions(events, task_id)), "answers": fin.get("event_id")}


#: Appended to the launch prompt of a resumed session. Protocol text, as `WORKTREE_CLAUSE` is.
RESUME_CLAUSE = (
    "RESUMED (AD-034-R21): this task's previous session was interrupted at {interrupted_at}: its transport failed "
    "({evidence}), not its work. This is resume {resumes} of at most " + str(MAX_RESUMES) + ". Its work is kept on "
    "branch `{branch}` in {worktree}; the last commit there is {last_commit} \"{last_subject}\". Continue from that "
    "commit: read `git log` and `git status` first, and do not redo committed work. Anything it left uncommitted is "
    "still in the tree. If your working directory is not {worktree}, merge `{branch}` into your branch before "
    "anything else. Tokens already spent ({prior_tokens}) count toward this task's ceiling."
)


def resume_clause(plan: dict) -> str:
    return RESUME_CLAUSE.format(**{**plan, "evidence": ", ".join(plan["evidence"]) or "unrecorded",
                                   "last_commit": (plan["last_commit"] or "none")[:12],
                                   "last_subject": plan["last_subject"] or ""})


def launch_prior_tokens(launch_payload: dict) -> int:
    """Tokens an earlier interrupted session of this launch's task spent (0 for a fresh launch)."""
    return int(((launch_payload or {}).get("resume") or {}).get("prior_tokens") or 0)
