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

**SEL-062 (AD-038 ADDENDUM 17, REVIEW-001 F-05 and F-06).**

* A plant the harness could not run (an `OSError`, a hook call over `HOOK_TIMEOUT_S`) is *untried*, not failed. It
  refuses the pass it happens on (`limit_control_untried`: a limit not known to hold is not trusted), and the next
  pass tries again. Before, it latched every launch until `seldon.yaml` changed.
* The fingerprint also covers the code that enforces the limits (`enforcing_files`), so a change to the guard is tried.
* The guard resolves the spellings REVIEW-001's probe got past it: a `cd` then a relative path, a quote-split path,
  and a search rooted at a parent of the guarded directory. Each is a planted control (`PLANTED_SPELLINGS`).
* The guard is a denylist of spellings, not complete mediation (Saltzer and Schroeder 1975). A process that builds
  the path in a variable or an interpreter's string still reaches it. The OS-enforced form is PL-018.
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
#: SEL-062 (F-05): the refusal of a pass whose controls the harness could not run. Not latched: the next pass tries.
REFUSED_CONTROL_UNTRIED = "limit_control_untried"
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
#: SEL-062 (F-06): tools that search below their root, so a root that is a guarded directory or a parent of one
#: reaches into it. A search with no `path` searches the call's working directory.
_SEARCH_TOOLS = ("Grep", "Glob", "LS")
#: Characters that end a glob pattern's literal prefix.
_GLOB_CHARS = "*?[{"
#: SEL-062 (F-06): the planted spellings each guarded path is tried with. The first two are SEL-054's; the other
#: three are the spellings REVIEW-001's probe got past the guard.
PLANTED_SPELLINGS = ("canonical_read", "canonical_cat", "cd_relative", "quote_split", "search_parent")
#: SEL-062 (F-05): the modules whose code enforces the limits the controls try, relative to the `seldon` package.
#: A change to any of them changes the fingerprint, so the changed code is tried before a launch.
ENFORCING_MODULES = ("core/controls.py", "commands/dispatch_stations.py", "core/stations.py")


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


def _resolve(value: str, cwd: Path) -> str | None:
    """`value` as an absolute, resolved path against `cwd`, with `~` and environment variables expanded; None when it
    cannot be one (a NUL, a resolution loop)."""
    try:
        p = Path(os.path.expandvars(os.path.expanduser(value)))
        return str((p if p.is_absolute() else cwd / p).resolve())
    except (OSError, ValueError, RuntimeError):
        return None


def _hit(resolved: str | None, paths: list, *, parent_too: bool = False) -> str | None:
    """The guarded root `resolved` lies under, or (with `parent_too`, for a search's root) the root it is a parent of."""
    if resolved is None:
        return None
    for root in paths:
        if _under(resolved, root) or (parent_too and _under(root, resolved)):
            return root
    return None


#: Shell words that end one simple command and start the next, so a following `cd` is a command again.
_COMMAND_BREAKS = ("&&", "||", ";", "|", "&", "(", ")", ";;", "|&")


def command_paths(command: str, cwd: Path) -> list:
    """Every path a Bash command's words can name, resolved (SEL-062, F-06).

    The words are the shell's after quoting is removed (`shlex`, POSIX mode, so `sec""rets` is `secrets`), with
    redirections and command separators split off. A relative word resolves against the working directory as the
    command's own `cd`s change it, and the text after a `--flag=` is a word too. A command that does not parse (an
    unbalanced quote) yields nothing here; the raw-text spellings still read it."""
    lex = shlex.shlex(command, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    try:
        words = list(lex)
    except ValueError:
        return []
    here, out, start, cd_next = cwd, [], True, False
    for w in words:
        if w in _COMMAND_BREAKS or (w and all(c in "();<>|&" for c in w)):
            start = w in _COMMAND_BREAKS or not all(c in "<>" for c in w)
            cd_next = False
            continue
        candidates = [w] + ([w.split("=", 1)[1]] if w.startswith("-") and "=" in w else [])
        for c in candidates:
            r = _resolve(c, here)
            if r is not None:
                out.append(r)
        if cd_next:
            r = _resolve(w, here)
            if r is not None:
                here = Path(r)
            cd_next = False
        elif start and w == "cd":
            cd_next = True
        start = False
    return out


def _glob_root(pattern: str, cwd: Path) -> str | None:
    """An absolute glob pattern's literal prefix, as the directory a search starts from; None for a relative one."""
    expanded = os.path.expanduser(pattern)
    if not os.path.isabs(expanded):
        return None
    cut = min([i for i, ch in enumerate(expanded) if ch in _GLOB_CHARS] or [len(expanded)])
    return _resolve(expanded[:cut].rsplit("/", 1)[0] or "/", cwd)


def refusal(hook: dict, paths: list) -> str | None:
    """Why the guard refuses this PreToolUse call, or None. `hook` is the hook's JSON input.

    AD-038-R44 as amended by ADDENDUM 17: a file tool's path argument, a search's root (a guarded directory or a parent
    of one), an absolute Glob pattern's prefix, a Bash command's resolved words (`command_paths`), and the raw text in
    the `~`, `$HOME` and `/private` spellings. A denylist of spellings, not complete mediation."""
    if not paths:
        return None
    tool_input = hook.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return None
    tool = hook.get("tool_name")
    cwd = Path(hook.get("cwd") or os.getcwd())
    search = tool in _SEARCH_TOOLS
    named = False
    for key in _PATH_KEYS:
        value = tool_input.get(key)
        if not isinstance(value, str) or not value:
            continue
        named = True
        root = _hit(_resolve(value, cwd), paths, parent_too=search and key == "path")
        if root:
            return _reason(tool, root)
    if search:
        root = _hit(None if named else _resolve(".", cwd), paths, parent_too=True)
        pattern = tool_input.get("pattern") if tool == "Glob" else None
        if not root and isinstance(pattern, str) and pattern:
            root = _hit(_glob_root(pattern, cwd), paths, parent_too=True)
        if root:
            return _reason(tool, root)
    command = tool_input.get("command")
    if isinstance(command, str) and command:
        for resolved in command_paths(command, cwd):
            root = _hit(resolved, paths)
            if root:
                return _reason(tool, root)
    for key in _TEXT_KEYS:
        value = tool_input.get(key)
        if not isinstance(value, str) or not value:
            continue
        for root in paths:
            if any(s in value for s in _spellings(root)):
                return _reason(tool, root)
    return None


def _reason(tool: str | None, root: str) -> str:
    return (f"GUARD: this {tool or 'tool'} call names {root}, which the dispatcher's session guard refuses "
            f"(seldon.yaml dispatch.guard.deny_paths or dispatch.hive.secrets_dir; AD-038-R44). Nothing a dispatched "
            f"session needs is there: the dispatcher already gave this session what it may hold, in its environment.")


# ------------------------------------------------------------------------------------------------ the controls

def planted_requests(root: str) -> list:
    """`(spelling, tool, tool_input)` for every planted request a guarded path is tried with (`PLANTED_SPELLINGS`)."""
    plant = f"{root}/{PLANT_NAME}"
    parent, name = os.path.split(root.rstrip("/"))
    parent = parent or "/"
    split = f'{name[:1]}""{name[1:]}' if name else '""'
    out = {
        "canonical_read": ("Read", {"file_path": plant}),
        "canonical_cat": ("Bash", {"command": f"cat {shlex.quote(plant)}"}),
        "cd_relative": ("Bash", {"command": f"cd {shlex.quote(parent)} && cat {shlex.quote(name)}/{PLANT_NAME}"}),
        "quote_split": ("Bash", {"command": f"cat {shlex.quote(parent)}/{split}/{PLANT_NAME}"}),
        "search_parent": ("Grep", {"pattern": PLANT_NAME, "path": parent}),
    }
    return [(s, *out[s]) for s in PLANTED_SPELLINGS]


def guard_controls(hook_command: str, paths: list, cwd: Path, run=subprocess.run) -> list:
    """Feed every planted request (`planted_requests`) for each deny path to the installed hook command.

    A request the harness could not deliver (an `OSError`, a call over `HOOK_TIMEOUT_S`) is a row with `refused: None`,
    `tried: False` and `harness_error: True`: the limit was not tried, so it neither held nor let the plant through."""
    rows = []
    try:
        argv = shlex.split(hook_command)
    except ValueError as exc:
        return [{"limit": "guard", "request": hook_command, "refused": False, "error": f"does not parse: {exc}"}]
    env = {k: v for k, v in os.environ.items() if k != "SELDON_SESSION_ID"}
    for root in paths:
        for spelling, tool, tool_input in planted_requests(root):
            hook = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input, "cwd": str(cwd),
                    "session_id": "planted-control"}
            row = {"limit": "guard", "path": root, "spelling": spelling,
                   "request": {"tool_name": tool, "tool_input": tool_input}}
            try:
                proc = run(argv, input=json.dumps(hook), capture_output=True, text=True, timeout=HOOK_TIMEOUT_S,
                           cwd=str(cwd), env=env)
            except (OSError, subprocess.TimeoutExpired) as exc:
                rows.append({**row, "refused": None, "tried": False, "harness_error": True,
                             "error": f"{type(exc).__name__}: {exc}"})
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
        except Exception as exc:                                     # noqa: BLE001 - recorded on the row, untried
            # SEL-062 (F-05): the inspector over a planted session could not run, so the ceiling was not tried. The
            # row refuses this pass as untried and the next pass tries again; it is never read as "held".
            return {"limit": "spend_ceiling", "request": {"tokens": used}, "refused": None, "tried": False,
                    "harness_error": True, "error": f"{type(exc).__name__}: {exc}"}
    hit = [p for k, p in stops if k == S.EVENT_SESSION_STOP and p.get("reason") == "spend_ceiling"
           and p.get("kind") == "hard"]
    return {"limit": "spend_ceiling", "request": {"tokens": used, "ceiling": ceiling}, "refused": bool(hit),
            **({} if hit else {"error": f"no hard stop for {used} tokens over a {ceiling} ceiling: {out!r}"[:300]})}


def network_row() -> dict:
    return {"limit": "network", "tried": False, "refused": None,
            "why": "the Network line reaches a session only as SELDON_NETWORK_ALLOWLIST, read by a consumer's fetch "
                   "helper; seldon sets no host rule of its own, so there is nothing of seldon's to try"}


def enforcing_files() -> list:
    """The source files of the code that enforces the limits (`ENFORCING_MODULES`), in a stable order."""
    pkg = Path(__file__).resolve().parent.parent
    return [pkg / m for m in ENFORCING_MODULES]


def enforcing_code_digest() -> str:
    """A sha256 over the enforcing code's bytes (SEL-062, F-05): the guard that changed is a guard not yet tried. A file
    that cannot be read is hashed as its name and the error, so the digest still changes when it does."""
    h = hashlib.sha256()
    for f in enforcing_files():
        h.update(str(Path(f).name).encode("utf-8") + b"\0")
        try:
            h.update(Path(f).read_bytes())
        except OSError as exc:
            h.update(f"unreadable: {type(exc).__name__}".encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()[:16]


def limits_spec(hook_command: str, paths: list, scfg: dict) -> dict:
    """What the controls try. Its fingerprint decides when they run again: the launch line's hook command, the guarded
    paths, the spend factor, and (SEL-062) a digest of the code that enforces them."""
    return {"hook_command": hook_command, "deny_paths": list(paths),
            "spend_ceiling_factor": scfg.get("spend_ceiling_factor"), "code": enforcing_code_digest()}


def spec_fingerprint(spec: dict) -> str:
    return hashlib.sha256(json.dumps(spec, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def try_limits(spec: dict, scfg: dict, cwd: Path, run=subprocess.run) -> dict:
    """Run every control.

    `failed` is every limit that let its planted request through; `untried` every plant the harness could not run.
    `ok` is True only when neither holds. `retry` is True when nothing failed and something was untried: the next pass
    tries again rather than latching on a harness error (SEL-062, F-05)."""
    rows = guard_controls(spec["hook_command"], spec["deny_paths"], cwd, run=run)
    rows.append(spend_control(scfg))
    rows.append(network_row())
    failed = [r for r in rows if r.get("refused") is False]
    untried = [r for r in rows if r.get("harness_error")]
    return {"fingerprint": spec_fingerprint(spec), "rows": rows, "failed": failed, "untried": untried,
            "ok": not failed and not untried, "retry": bool(untried) and not failed}
