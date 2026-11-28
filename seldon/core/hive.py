"""One board identity per dispatched session, minted by the dispatcher at launch (SEL-054 Part B; AD-038-R43).

factory's filing of 2026-11-27 ("the dispatcher mints one Hive identity per session at launch"): the Hive's client
minted a session's identity itself, from a minter token every session could read, so the identity was attested by the
client and a session could mint a second one. Here the DISPATCHER, a process outside the session, runs the board's
mint command once per launch and hands the session only the token it minted, in the session's environment:

* never in its prompt, `seldon.yaml`, `.env`, the launch line or any event (an event records the identity's name and a
  12-character sha256 prefix of the token, enough to match a post to its launch and useless to post with);
* and the session guard refuses tool calls that name the board's secrets directory (`controls.guard_paths`), so the
  minter's token is not one tool call away. The session runs as the operator's Unix user, so the guard stops a
  session's ordinary reach, not a determined process; the board's mint ledger stays factory's second check.

The board is factory's (DN-005): seldon knows no board protocol. `dispatch.hive.mint_command` is an opaque command, as
every premise `check:` is; it is run with `HIVE_PROJECT`, `HIVE_TASK`, `HIVE_TASK_NAME` and `SELDON_SESSION_ID` set and
prints the token, either alone or as JSON `{"token": ..., "identity": ...}`.

A failed mint never refuses the launch: a post is context and never read by a gate (factory DN-005 decision 3), so a
board that is down must not stop the line. It is recorded (`session_identity`, `minted: false`, the exit and the
stderr's length and fingerprint, never its text: SEL-062, F-22) and the
session launches without `HIVE_TOKEN`, which the client's notices hook reads as "no identity" and stays silent.
Prior art: workload identity attested by the platform at launch, never by the workload (SPIFFE/SPIRE: the agent
attests the workload and issues its SVID; Kubernetes projected service-account tokens, mounted by the kubelet).
"""
from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

HIVE_KEY = "hive"
#: The session's environment variables (factory DN-005 decision 2; `scripts/hive.py` `session_token`).
ENV_TOKEN = "HIVE_TOKEN"
ENV_PROJECT = "HIVE_PROJECT"
ENV_TASK = "HIVE_TASK"
#: Never inherited by a session: a token in the dispatcher's own environment is no session's identity.
INHERITED_STRIP = (ENV_TOKEN,)
#: The event that records a launch's identity (name and token fingerprint only).
EVENT_SESSION_IDENTITY = "session_identity"
#: Seconds the mint command may take. **No measured basis**: the board is local (127.0.0.1) and an invite lives 120 s
#: (DN-005), so a mint slower than 30 s has hung.
MINT_TIMEOUT_S_DEFAULT = 30
#: Characters of the token's sha256 an event keeps.
FINGERPRINT_CHARS = 12


class HiveConfigError(ValueError):
    """`dispatch.hive` is malformed."""


#: SEL-063 (REVIEW-001 F-29): a command word that means the interpreter running seldon, so a tracked `seldon.yaml`
#: names no one machine's Python.
PYTHON_WORD = "{python}"


def resolve_command(command: str, base: Path | None) -> str:
    """A `mint_command` or `notices_hook` as it runs on this machine: `{python}` is `sys.executable`, `~` is expanded,
    and a relative path-shaped word (one with a `/` and no leading `-`) is made absolute against `base`, the project's
    primary checkout, as `project_new.kit_relative` does for the kit's commands. Without `base` a relative word is kept.

    Raises:
        HiveConfigError: The command does not split as shell words.
    """
    try:
        words = shlex.split(command)
    except ValueError as exc:
        raise HiveConfigError(f"dispatch.{HIVE_KEY} command {command!r} does not split: {exc}") from exc
    out = []
    for w in words:
        if w == PYTHON_WORD:
            w = sys.executable
        elif w.startswith("~"):
            w = os.path.expanduser(w)
        elif base is not None and "/" in w and not w.startswith("-") and not os.path.isabs(w):
            w = str((Path(base) / w).resolve())
        out.append(w)
    return shlex.join(out)


def load_hive(value, base: Path | None = None) -> dict | None:
    """`dispatch.hive`, validated, its commands resolved against `base` (`resolve_command`); None when absent
    (nothing changes)."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise HiveConfigError(f"dispatch.{HIVE_KEY} must be a mapping, got {value!r}")
    unknown = sorted(set(value) - {"mint_command", "notices_hook", "secrets_dir", "mint_timeout_s"})
    if unknown:
        raise HiveConfigError(f"dispatch.{HIVE_KEY} has unknown key(s) {unknown}: expected mint_command, "
                              f"notices_hook, secrets_dir, mint_timeout_s")
    out = {}
    for key in ("mint_command", "notices_hook", "secrets_dir"):
        v = value.get(key)
        if v is not None and (not isinstance(v, str) or not v.strip()):
            raise HiveConfigError(f"dispatch.{HIVE_KEY}.{key} must be a non-empty string, got {v!r}")
        out[key] = v.strip() if v else None
    for key in ("mint_command", "notices_hook"):
        if out[key]:
            out[key] = resolve_command(out[key], base)
    if out["secrets_dir"] and not os.path.isabs(os.path.expanduser(out["secrets_dir"])):
        raise HiveConfigError(f"dispatch.{HIVE_KEY}.secrets_dir must be an absolute path (or start with ~), got "
                              f"{out['secrets_dir']!r}")
    timeout = value.get("mint_timeout_s", MINT_TIMEOUT_S_DEFAULT)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise HiveConfigError(f"dispatch.{HIVE_KEY}.mint_timeout_s must be a positive number, got {timeout!r}")
    out["mint_timeout_s"] = timeout
    return out


def fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:FINGERPRINT_CHARS]


def mint(hive: dict | None, *, project: str, task_id: str, task_name: str | None, session_id: str,
         cwd: Path) -> dict | None:
    """Run the mint command for one session. None when no mint is configured.

    Returns `{ok, token, identity, error}`; `token` is for the session's environment only and must never be written.
    """
    if not hive or not hive.get("mint_command"):
        return None
    env = {k: v for k, v in os.environ.items() if k not in INHERITED_STRIP}
    env.update({ENV_PROJECT: project, ENV_TASK: task_id, "HIVE_TASK_NAME": task_name or "",
                "SELDON_SESSION_ID": session_id})
    try:
        argv = shlex.split(hive["mint_command"])
        proc = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True,
                              timeout=hive["mint_timeout_s"], stdin=subprocess.DEVNULL)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "token": None, "identity": None, "error": f"{type(exc).__name__}: {exc}"}
    if proc.returncode != 0:
        # stderr only, and its tail: a mint command's stdout is where a token would be. The tail is for the dispatcher's
        # own stderr; `record` keeps only its length and fingerprint (SEL-062, REVIEW-001 F-22).
        stderr = (proc.stderr or "").strip()
        return {"ok": False, "token": None, "identity": None, "exit": proc.returncode, "stderr": stderr,
                "error": f"exit {proc.returncode}: {stderr[-300:]}"}
    token, identity = _parse(proc.stdout)
    if not token:
        return {"ok": False, "token": None, "identity": None, "error": "the mint command printed no token"}
    return {"ok": True, "token": token, "identity": identity, "error": None}


def _parse(stdout: str) -> tuple:
    text = (stdout or "").strip()
    if text.startswith("{"):
        try:
            body = json.loads(text)
        except json.JSONDecodeError:
            return None, None
        token = body.get("token") if isinstance(body, dict) else None
        return (str(token).strip() or None if token else None), (body.get("identity") if isinstance(body, dict)
                                                                  else None)
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    # One line, and one word: anything else is a command that printed more than a token, which is refused rather than
    # guessed at.
    if len(lines) == 1 and len(lines[0].split()) == 1:
        return lines[0], None
    return None, None


def session_env(minted: dict | None, *, project: str, task_id: str) -> dict:
    """What the session's environment gains: the token and its two labels when minted; nothing otherwise."""
    if not minted or not minted.get("ok"):
        return {}
    return {ENV_TOKEN: minted["token"], ENV_PROJECT: project, ENV_TASK: task_id}


def record(minted: dict, *, task_id: str, child_session_id: str) -> dict:
    """The `session_identity` payload: never the token, and never a failed mint's stderr text.

    AD-038-R43 as amended by ADDENDUM 17 (REVIEW-001 F-22): the event is in the event store, which travels with the
    repository, and a mint command that echoes its minter token on failure would publish it. The stderr is dropped
    rather than scanned, because the token format is factory's and a pattern misses some format. Its length and
    12-character sha256 prefix match a failure to the dispatcher's own log line, which carries the text."""
    stderr = minted.get("stderr")
    error = f"exit {minted.get('exit')}" if stderr is not None else minted.get("error")
    return {"task_id": task_id, "child_session_id": child_session_id, "minted": bool(minted.get("ok")),
            "identity": minted.get("identity"),
            "token_sha256": fingerprint(minted["token"]) if minted.get("token") else None,
            "error": error,
            "stderr_chars": len(stderr) if stderr is not None else None,
            "stderr_sha256": fingerprint(stderr) if stderr else None}
