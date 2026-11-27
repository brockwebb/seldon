"""Every limit the dispatcher sets on a session is tried by a planted request (SEL-054 Part B; AD-038-R44, R45).

factory's filing of 2026-11-27 ("every limit the dispatcher sets is tried by a planted control"): FAC-31 wrote a deny
rule as `Write(/private/tmp/.../check/**)`. In Claude Code's permission-rule syntax a single leading slash is relative
to the settings file and `//` is the filesystem root, so the rule matched nothing, said nothing, and a control
session's write went through; with `//` the same write was refused. A limit nobody has tried is not known to work.

This is AD-032 FC-27 ("every gate registers a planted defect it must catch") applied to the dispatcher's own limits,
and it is negative testing of an access control: the control is a request the limit must refuse. Prior art: NIST SP
800-53 CA-2/CA-8 (controls are assessed by trying them, not by reading their configuration); fault injection.

**The guard (R44).** `dispatch.guard.deny_paths` plus `dispatch.hive.secrets_dir`: the session's PreToolUse hook
(`seldon dispatch tool-gate`, already on every launch line) refuses a tool call that names a path under one of them,
for file tools by their path argument and for Bash by its command text. The paths ride on the hook's own command line
(`--deny-path`), so the launch line says what it guards and the control tries exactly that command.

The path-syntax failure FAC-31 met cannot occur in a rule seldon's launch line writes: its only permission rules are
`dispatch.allow`, which refuses at load anything but `Bash(<pattern>)` (AD-034 ADDENDUM 02), so the guard below is its
one path limit, and the guard is tried by plants rather than read for syntax.

**The controls (R45).** Run before a launch whenever the limits' fingerprint differs from the last one tried, and by
`seldon dispatch controls`:

* `guard`: for each deny path, a planted `Read` of a file under it and a planted `Bash cat` of it are fed to the
  installed hook command; each must come back `permissionDecision: deny`.
* `spend_ceiling`: the inspector (`stations.inspect`) is run over a planted session whose reading is twice the ceiling
  the project's stations set for a 1M estimate; it must write the `spend_ceiling` hard stop.
* `network`: recorded as untried, with why. The Network line reaches a session only as `SELDON_NETWORK_ALLOWLIST`, which
  a consumer's fetch helper reads; seldon enforces no host rule of its own, so there is nothing of seldon's to try.

A control that goes through refuses every launch (`limit_control_failed`) until the limits change and their controls
hold: a launch that depends on a limit known not to hold is the launch the limit exists to stop.
"""
from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
import tempfile
from pathlib import Path

GUARD_KEY = "guard"
#: The refusal reason a failed control gives every launch.
REFUSED_CONTROL_FAILED = "limit_control_failed"
#: The event a tried set of limits writes, once per fingerprint.
EVENT_LIMITS_TRIED = "limits_tried"
#: Beside the lease, as the other standing-condition files are.
STATE_FILE = "dispatch_controls.json"
#: The planted file name under a guarded directory. It need not exist: the guard refuses the request, not the read.
PLANT_NAME = "planted-control"
#: Seconds one planted hook call may take. **No measured basis**: the hook is `python -m seldon` reading the event
#: store, about a second here; thirty is the notifier's own ceiling.
HOOK_TIMEOUT_S = 30
#: Tool-input keys that carry a path.
_PATH_KEYS = ("file_path", "path", "notebook_path")
#: Tool-input keys whose text may name a path anywhere in it.
_TEXT_KEYS = ("command", "pattern", "glob")


class GuardConfigError(ValueError):
    """`dispatch.guard` is malformed."""


def load_guard(value) -> dict:
    """`dispatch.guard`, validated: `{deny_paths: [absolute paths]}`. Absent is no deny path."""
    if value is None:
        return {"deny_paths": []}
    if not isinstance(value, dict) or set(value) - {"deny_paths"}:
        raise GuardConfigError(f"dispatch.{GUARD_KEY} must be a mapping with `deny_paths`, got {value!r}")
    paths = value.get("deny_paths") or []
    if not isinstance(paths, list) or not all(isinstance(x, str) and x.strip() for x in paths):
        raise GuardConfigError(f"dispatch.{GUARD_KEY}.deny_paths must be a list of paths, got {paths!r}")
    for x in paths:
        if not os.path.isabs(os.path.expanduser(x)):
            raise GuardConfigError(f"dispatch.{GUARD_KEY}.deny_paths entry {x!r} must be absolute (or start with ~)")
    return {"deny_paths": list(paths)}


def guard_paths(cfg: dict) -> list:
    """Every directory the session guard refuses, absolute and resolved, in a stable order."""
    raw = list((cfg.get(GUARD_KEY) or {}).get("deny_paths") or [])
    secrets = (cfg.get("hive") or {}).get("secrets_dir")
    if secrets:
        raw.append(secrets)
    out = []
    for x in raw:
        p = str(Path(os.path.expanduser(x)).resolve())
        if p not in out:
            out.append(p)
    return out


def _spellings(path: str) -> list:
    """The ways a command can name `path`: resolved, as `~/`, as `$HOME/` and `${HOME}/`, and macOS's `/private`
    aliases (`/tmp` and `/private/tmp` are one directory)."""
    out = {path}
    home = str(Path.home().resolve())
    if path == home or path.startswith(home + "/"):
        rest = path[len(home):]
        out |= {"~" + rest, "$HOME" + rest, "${HOME}" + rest}
    if path.startswith("/private/"):
        out.add(path[len("/private"):])
    return sorted(out, key=len, reverse=True)


def _under(candidate: str, root: str) -> bool:
    return candidate == root or candidate.startswith(root.rstrip("/") + "/")


def refusal(hook: dict, paths: list) -> str | None:
    """Why the guard refuses this PreToolUse call, or None. `hook` is the hook's JSON input."""
    if not paths:
        return None
    tool_input = hook.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return None
    cwd = Path(hook.get("cwd") or os.getcwd())
    for key in _PATH_KEYS:
        value = tool_input.get(key)
        if not isinstance(value, str) or not value:
            continue
        p = Path(os.path.expanduser(value))
        resolved = str((p if p.is_absolute() else cwd / p).resolve())
        for root in paths:
            if _under(resolved, root):
                return _reason(hook.get("tool_name"), root)
    for key in _TEXT_KEYS:
        value = tool_input.get(key)
        if not isinstance(value, str) or not value:
            continue
        for root in paths:
            if any(s in value for s in _spellings(root)):
                return _reason(hook.get("tool_name"), root)
    return None


def _reason(tool: str | None, root: str) -> str:
    return (f"GUARD: this {tool or 'tool'} call names {root}, which the dispatcher's session guard refuses "
            f"(seldon.yaml dispatch.guard.deny_paths or dispatch.hive.secrets_dir; AD-038-R44). Nothing a dispatched "
            f"session needs is there: the dispatcher already gave this session what it may hold, in its environment.")


# ------------------------------------------------------------------------------------------------ the controls

def guard_controls(hook_command: str, paths: list, cwd: Path, run=subprocess.run) -> list:
    """Feed a planted `Read` and a planted `Bash cat` for each deny path to the installed hook command."""
    rows = []
    try:
        argv = shlex.split(hook_command)
    except ValueError as exc:
        return [{"limit": "guard", "request": hook_command, "refused": False, "error": f"does not parse: {exc}"}]
    env = {k: v for k, v in os.environ.items() if k != "SELDON_SESSION_ID"}
    for root in paths:
        plant = f"{root}/{PLANT_NAME}"
        for tool, tool_input in (("Read", {"file_path": plant}), ("Bash", {"command": f"cat {shlex.quote(plant)}"})):
            hook = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input, "cwd": str(cwd),
                    "session_id": "planted-control"}
            row = {"limit": "guard", "path": root, "request": {"tool_name": tool, "tool_input": tool_input}}
            try:
                proc = run(argv, input=json.dumps(hook), capture_output=True, text=True, timeout=HOOK_TIMEOUT_S,
                           cwd=str(cwd), env=env)
            except (OSError, subprocess.TimeoutExpired) as exc:
                rows.append({**row, "refused": False, "error": f"{type(exc).__name__}: {exc}"})
                continue
            rows.append({**row, "refused": _denied(proc.stdout), "exit": proc.returncode,
                         "output": (proc.stdout or proc.stderr or "").strip()[-300:]})
    return rows


def _denied(stdout: str) -> bool:
    for line in (stdout or "").splitlines():
        try:
            body = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ((body.get("hookSpecificOutput") or {}).get("permissionDecision")) == "deny":
            return True
    return False


def spend_control(scfg: dict) -> dict:
    """The inspector over a planted session at twice the ceiling it would set for a 1M estimate: it must stop it."""
    from seldon.core import stations as S
    from seldon.core.events import make_event

    estimate = 1_000_000
    with tempfile.TemporaryDirectory(prefix="seldon-spend-control-") as tmp:
        root = Path(tmp)
        (root / "cc_tasks").mkdir()
        (root / "logs").mkdir()
        (root / "cc_tasks" / "planted.md").write_text(
            "# planted\n\n**Spend:** est. 1M tokens. **Network:** none.\n", encoding="utf-8")
        ceiling = S.spend_ceiling(estimate, scfg["spend_ceiling_factor"], None)["ceiling"]
        used = 2 * ceiling
        (root / "logs" / "planted.log").write_text(
            "=== planted | dispatch | claude -p\n" + json.dumps({"type": "assistant", "message": {"id": "m1", "usage": {
                "input_tokens": used, "cache_creation_input_tokens": 0, "output_tokens": 0}}}) + "\n",
            encoding="utf-8")
        launch = make_event("dispatch_launched", "dispatcher", "accepted",
                            {"task_id": "planted-control", "source_file": "cc_tasks/planted.md",
                             "child_session_id": "planted-control", "log_path": "logs/planted.log",
                             "launched_at": "1970-01-01T00:00:00Z"})
        launch["timestamp"] = "1970-01-01T00:00:00Z"
        stops = []
        try:
            out = S.inspect(root, "planted-control", [launch], scfg, 300,
                            lambda kind, payload: stops.append((kind, payload)) or {"event_id": "planted"})
        except Exception as exc:                                     # noqa: BLE001 - a control that cannot run fails
            return {"limit": "spend_ceiling", "request": {"tokens": used}, "refused": False,
                    "error": f"{type(exc).__name__}: {exc}"}
    hit = [p for k, p in stops if k == S.EVENT_SESSION_STOP and p.get("reason") == "spend_ceiling"
           and p.get("kind") == "hard"]
    return {"limit": "spend_ceiling", "request": {"tokens": used, "ceiling": ceiling}, "refused": bool(hit),
            **({} if hit else {"error": f"no hard stop for {used} tokens over a {ceiling} ceiling: {out!r}"[:300]})}


def network_row() -> dict:
    return {"limit": "network", "tried": False, "refused": None,
            "why": "the Network line reaches a session only as SELDON_NETWORK_ALLOWLIST, read by a consumer's fetch "
                   "helper; seldon sets no host rule of its own, so there is nothing of seldon's to try"}


def limits_spec(hook_command: str, paths: list, scfg: dict) -> dict:
    """What the controls try. Its fingerprint decides when they run again."""
    return {"hook_command": hook_command, "deny_paths": list(paths),
            "spend_ceiling_factor": scfg.get("spend_ceiling_factor")}


def spec_fingerprint(spec: dict) -> str:
    return hashlib.sha256(json.dumps(spec, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def try_limits(spec: dict, scfg: dict, cwd: Path, run=subprocess.run) -> dict:
    """Run every control. `ok` is False when any limit let its planted request through."""
    rows = guard_controls(spec["hook_command"], spec["deny_paths"], cwd, run=run)
    rows.append(spend_control(scfg))
    rows.append(network_row())
    failed = [r for r in rows if r.get("refused") is False]
    return {"fingerprint": spec_fingerprint(spec), "rows": rows, "failed": failed, "ok": not failed}
