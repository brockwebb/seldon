"""Model selection: the registry, the lock, the accessor, the launch block and the receipt (AD-035).

    seldon models show                  # the registry's roles and the lock's ids
    seldon models resolve <role> [--json]
    seldon models refresh [--force] [--version V] [--no-commit]

**Why this exists.** Before AD-035 a model was named three ways on this machine: an alias in a
config, an id typed into a task file from a Desktop session's memory, and whatever the CLI binary
resolved at launch. The binary pin silently pinned the model generation (alias resolution lives in
the binary), and the CLI can substitute a model without any record this machine keeps. This module
is the one place a model id comes from.

**The shape is a lockfile** (npm `package-lock.json`, Cargo `Cargo.lock`, Poetry `poetry.lock`):

- `models/registry.yaml` is intent: role to family and effort (R1).
- `models/models.lock.yaml` is resolution: family to model id, plus the CLI that resolved it, the
  date and the evidence file. Only :func:`refresh` writes it (R2), by asking Anthropic's own
  resolver, the newest CLI, one probe per family alias.
- :func:`resolve` is the only way code on this machine gets a model id (R1).
- :func:`launch_spec` is what a launcher needs to obey R3 and R6: the lock's CLI, `--model <id>`,
  the four `ANTHROPIC_DEFAULT_*_MODEL` variables, and `switchModelsOnFlag: false`.
- :func:`check_receipt` compares the served model against the requested one and raises
  :class:`ModelSubstituted` (`model_substituted`) on a mismatch (R6).

**Where the files are.** `$SELDON_MODELS_HOME` when set; otherwise the `models/` directory beside
this package in the seldon checkout. A non-editable install has no such directory and fails loudly
naming the variable, so no process ever reads a stale copy packaged with an old install.

**Dependencies.** Standard library and PyYAML only, so `import seldon.models` costs nothing in a
repository that otherwise has no use for Seldon's graph.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml

#: Overrides where the registry and lock are read from. Tests point it at a fixture directory.
MODELS_HOME_ENV = "SELDON_MODELS_HOME"
REGISTRY_FILE = "registry.yaml"
LOCK_FILE = "models.lock.yaml"
#: The event `refresh` appends to the seldon event store when an id or the CLI version changes.
EVENT_LOCK_BUMPED = "models_lock_bumped"
#: The named failure R6 requires when the served model is not the requested one.
SUBSTITUTED = "model_substituted"

#: R3: one variable per family, so CLI background work and any alias the CLI resolves internally
#: follow the lock too (code.claude.com/docs/en/model-config, read 2026-10-09).
FAMILY_ENV = {
    "opus": "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "sonnet": "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "haiku": "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "fable": "ANTHROPIC_DEFAULT_FABLE_MODEL",
}
#: R6: a safety-classifier flag becomes a visible refusal instead of a silent re-run on another
#: model. Passed through `--settings`, which takes inline JSON.
LAUNCH_SETTINGS = {"switchModelsOnFlag": False}
EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")
#: `effort: default` passes no `--effort` flag.
EFFORT_DEFAULT = "default"
#: Variables a probe child must not inherit: credentials (subscription OAuth only, DD-007), the
#: session identity of a parent Claude Code session, and any family pin, which would make the probe
#: read back the old lock instead of the binary's own alias table.
_PROBE_SCRUB_EXACT = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_MODEL",
                      "ANTHROPIC_SMALL_FAST_MODEL", "CLAUDECODE", "CLAUDE_PID", "CLAUDE_EFFORT",
                      *FAMILY_ENV.values())
_PROBE_SCRUB_PREFIX = ("CLAUDE_CODE_",)
#: The literal model ids this machine uses: `claude-<family>-<digits>...`.
MODEL_ID_RE = re.compile(r"\bclaude-(?:opus|sonnet|haiku|fable)-\d[\w.\-\[\]]*")
#: CLI family aliases, which R4 forbids as configuration values.
ALIASES = tuple(FAMILY_ENV)
REGISTRY_REQUIRED_REFRESH = ("npm_package", "install_root", "bin_relpath", "families",
                             "probe_prompt", "probe_timeout_s", "npm_timeout_s", "cache",
                             "evidence_dir", "commit_branch", "auto_on_register",
                             "auto_on_dispatch")


class ModelsError(Exception):
    """The registry or the lock is missing, malformed or does not answer. Fatal: no call is made."""


class UnknownRole(ModelsError):
    """A launcher asked for a role the registry does not hold."""


class ModelSubstituted(Exception):
    """R6: the served model is not the requested one. The unit stops; its output is not used.

    `reason` is always ``model_substituted``; `receipt` carries requested, served and side models.
    """

    reason = SUBSTITUTED

    def __init__(self, receipt: dict):
        self.receipt = dict(receipt)
        served = receipt.get("served")
        detail = ("the envelope names no served model" if served is None
                  else f"served {served!r}")
        super().__init__(f"{SUBSTITUTED}: requested {receipt.get('requested')!r}, {detail} "
                         f"(AD-035 R6)")


# ------------------------------------------------------------------------------ the files

def models_home() -> Path:
    """The directory holding `registry.yaml` and `models.lock.yaml`."""
    env = os.environ.get(MODELS_HOME_ENV)
    if env:
        home = Path(env).expanduser()
        if not (home / REGISTRY_FILE).is_file():
            raise ModelsError(f"{MODELS_HOME_ENV}={env} holds no {REGISTRY_FILE}")
        return home
    home = Path(__file__).resolve().parent.parent / "models"
    if not (home / REGISTRY_FILE).is_file():
        raise ModelsError(
            f"no model registry at {home}: this seldon is not a source checkout. Set "
            f"{MODELS_HOME_ENV} to the seldon repository's models/ directory (AD-035 R1).")
    return home


def _home(home: Path | None) -> Path:
    return Path(home) if home is not None else models_home()


def load_registry(home: Path | None = None) -> dict:
    """The registry, validated. Every role names a known family and a known effort."""
    path = _home(home) / REGISTRY_FILE
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    roles = data.get("roles")
    if not isinstance(roles, dict) or not roles:
        raise ModelsError(f"{path}: no `roles:` mapping")
    for name, row in roles.items():
        if not isinstance(row, dict):
            raise ModelsError(f"{path}: role {name!r} is not a mapping")
        if row.get("family") not in FAMILY_ENV:
            raise ModelsError(f"{path}: role {name!r} family {row.get('family')!r} is not one "
                              f"of {sorted(FAMILY_ENV)}")
        effort = row.get("effort")
        if effort != EFFORT_DEFAULT and effort not in EFFORT_LEVELS:
            raise ModelsError(f"{path}: role {name!r} effort {effort!r} is not "
                              f"{EFFORT_DEFAULT!r} or one of {EFFORT_LEVELS}")
    refresh_cfg = data.get("refresh")
    if not isinstance(refresh_cfg, dict):
        raise ModelsError(f"{path}: no `refresh:` block")
    missing = [k for k in REGISTRY_REQUIRED_REFRESH if k not in refresh_cfg]
    if missing:
        raise ModelsError(f"{path}: refresh block missing {missing}")
    return data


def load_lock(home: Path | None = None) -> dict:
    """The lock, validated: every family the registry uses has an id, and the CLI is named."""
    home = _home(home)
    path = home / LOCK_FILE
    if not path.is_file():
        raise ModelsError(f"no {LOCK_FILE} at {home}; run `seldon models refresh` (AD-035 R2)")
    lock = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    fams = lock.get("families")
    if not isinstance(fams, dict) or not fams:
        raise ModelsError(f"{path}: no `families:` mapping")
    for fam, row in fams.items():
        if not isinstance(row, dict) or not isinstance(row.get("model"), str) or not row["model"]:
            raise ModelsError(f"{path}: family {fam!r} names no model id")
    cli = lock.get("cli") or {}
    if not cli.get("version") or not cli.get("path"):
        raise ModelsError(f"{path}: `cli.version` and `cli.path` are required")
    return lock


def lock_ids(home: Path | None = None) -> dict:
    """`{family: model id}` from the lock."""
    return {fam: row["model"] for fam, row in load_lock(home)["families"].items()}


def role_names(home: Path | None = None) -> list:
    return sorted(load_registry(home)["roles"])


# --------------------------------------------------------------------------- the accessor

@dataclass(frozen=True)
class Resolution:
    """What a role resolves to today."""

    role: str
    family: str
    effort: str
    model: str
    cli_path: str
    cli_version: str
    resolved_on: str
    evidence: str | None = None


def resolve_role(role: str, home: Path | None = None) -> Resolution:
    """The role's family, effort, model id and the CLI that resolved it."""
    home = _home(home)
    roles = load_registry(home)["roles"]
    if role not in roles:
        raise UnknownRole(f"role {role!r} is not in {home / REGISTRY_FILE}; the roles are "
                          f"{sorted(roles)} (AD-035 R1)")
    lock = load_lock(home)
    fam = roles[role]["family"]
    if fam not in lock["families"]:
        raise ModelsError(f"role {role!r} is family {fam!r}, which {home / LOCK_FILE} does not "
                          f"resolve; run `seldon models refresh`")
    return Resolution(role=role, family=fam, effort=roles[role]["effort"],
                      model=lock["families"][fam]["model"],
                      cli_path=str(Path(lock["cli"]["path"]).expanduser()),
                      cli_version=str(lock["cli"]["version"]),
                      resolved_on=str(lock.get("resolved_on")),
                      evidence=lock.get("evidence"))


def resolve(role: str, home: Path | None = None) -> str:
    """The model id for a role. AD-035 R1: the only way code on this machine gets one."""
    return resolve_role(role, home).model


def launch_env(home: Path | None = None) -> dict:
    """R3: `ANTHROPIC_DEFAULT_{OPUS,SONNET,HAIKU,FABLE}_MODEL` from the lock, all four."""
    ids = lock_ids(home)
    missing = [f for f in FAMILY_ENV if f not in ids]
    if missing:
        raise ModelsError(f"the lock resolves no id for {missing}; run `seldon models refresh`")
    return {FAMILY_ENV[f]: ids[f] for f in FAMILY_ENV}


def settings_json(extra: dict | None = None) -> str:
    """The `--settings` value: R6's `switchModelsOnFlag: false`, merged over any caller settings."""
    merged = dict(extra or {})
    merged.update(LAUNCH_SETTINGS)
    return json.dumps(merged, separators=(",", ":"), sort_keys=True)


def launch_spec(role: str, home: Path | None = None) -> dict:
    """Everything a launcher needs to start a CLI call for `role` under R3 and R6.

    Returns ``{role, family, effort, model, cli_path, cli_version, resolved_on, evidence, env,
    args, settings}``. `args` is ``["--model", id, "--settings", json]`` plus ``["--effort", e]``
    when the role's effort is not ``default``. A launcher execs ``cli_path`` with its own flags
    and `args`, with `env` laid over the child's environment, and records :func:`receipt`.
    """
    r = resolve_role(role, home)
    args = ["--model", r.model, "--settings", settings_json()]
    if r.effort != EFFORT_DEFAULT:
        args += ["--effort", r.effort]
    return {"role": r.role, "family": r.family, "effort": r.effort, "model": r.model,
            "cli_path": r.cli_path, "cli_version": r.cli_version,
            "resolved_on": r.resolved_on, "evidence": r.evidence,
            "env": launch_env(home), "args": args, "settings": dict(LAUNCH_SETTINGS)}


def launch_spec_for(target: str, home: Path | None = None) -> dict:
    """The launch block for a task's `**Model:**` value: a role, or an id equal to the lock's.

    An id is launched as its family with effort `default` and `role` None; anything else fails
    loudly, because a header that names neither is refused at registration (R5).
    """
    home = _home(home)
    if target in load_registry(home)["roles"]:
        return launch_spec(target, home)
    ids = lock_ids(home)
    fams = [f for f, m in ids.items() if m == target]
    if not fams:
        raise ModelsError(f"{target!r} is neither a role nor an id in the lock: {lock_quote(home)}")
    lock = load_lock(home)
    return {"role": None, "family": fams[0], "effort": EFFORT_DEFAULT, "model": target,
            "cli_path": str(Path(lock["cli"]["path"]).expanduser()),
            "cli_version": str(lock["cli"]["version"]), "resolved_on": str(lock.get("resolved_on")),
            "evidence": lock.get("evidence"), "env": launch_env(home),
            "args": ["--model", target, "--settings", settings_json()],
            "settings": dict(LAUNCH_SETTINGS)}


# ---------------------------------------------------------------------------- the receipt

def served_model(envelope: dict) -> str | None:
    """The model that ANSWERED: the `modelUsage` entry whose output tokens equal the envelope's
    top-level `usage`, else the one with the most output.

    Harvested from squiddy `model_client._answering_model` (S-007's positive control on CLI
    2.1.270): every `claude -p` invocation may also make a small side call to a Haiku model and
    list it first in `modelUsage`, so "the first key" stamps the wrong model.
    """
    if not isinstance(envelope, dict):
        return None
    mu = envelope.get("modelUsage")
    if not isinstance(mu, dict):
        return None
    entries = [(k, v) for k, v in mu.items() if isinstance(v, dict)]
    if not entries:
        return None
    usage = envelope.get("usage") if isinstance(envelope.get("usage"), dict) else {}
    out = usage.get("output_tokens")
    if isinstance(out, (int, float)):
        match = [k for k, v in entries if int(v.get("outputTokens") or 0) == int(out)]
        if len(match) == 1:
            return match[0]
    return max(entries, key=lambda kv: (int(kv[1].get("outputTokens") or 0),
                                        int(kv[1].get("inputTokens") or 0)))[0]


def receipt(requested: str, envelope: dict) -> dict:
    """R6's record for one call: `{requested, served, side_models, ok}`."""
    served = served_model(envelope)
    mu = envelope.get("modelUsage") if isinstance(envelope, dict) else None
    side = sorted(k for k in (mu or {}) if k != served) if isinstance(mu, dict) else []
    return {"requested": requested, "served": served, "side_models": side,
            "ok": served is not None and served == requested}


def check_receipt(requested: str, envelope: dict) -> dict:
    """The receipt, or :class:`ModelSubstituted` when the served model is not the requested one."""
    r = receipt(requested, envelope)
    if not r["ok"]:
        raise ModelSubstituted(r)
    return r


def last_result_envelope(text: str) -> dict | None:
    """The final `{"type": "result", ...}` object of a CLI transcript.

    `--output-format json` prints one envelope; `--output-format stream-json` prints one JSON
    object per line and ends with the result. Either way the last parseable result object wins.
    """
    found = None
    for line in (text or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and (obj.get("type") == "result" or "modelUsage" in obj):
            found = obj
    if found is None:
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                found = obj
        except (json.JSONDecodeError, TypeError):
            pass
    return found


# -------------------------------------------------------------------- the task-file gates (R5)

#: `**Model:** <value>`: the same bolded-header shape `seldon cc register` reads for Spend and
#: Network. The value is a role name or a model id equal to one of the lock's.
MODEL_HEADER_RE = re.compile(r"^\s*(?:[-*]\s+)?\*\*Model(?:\s*\([^)]*\))?\s*:\*\*[ \t]*(?P<v>[^\n]*)",
                             re.MULTILINE)
MODEL_GRAMMAR = ("`**Model:** <role>` naming a role in models/registry.yaml, or "
                 "`**Model:** <id>` equal to an id in models/models.lock.yaml")
_FENCE_RE = re.compile(r"^(?P<fence>```|~~~)[^\n]*\n(?P<body>.*?)^(?P=fence)[ \t]*$",
                       re.MULTILINE | re.DOTALL)
_CODE_MODEL_RE = re.compile(r"--model(?:\s+|=)(?P<v>[^\s\\`'\"]+|'[^']*'|\"[^\"]*\")")
#: A `--model` argument that is a placeholder, not a literal: `<id>`, `$MODEL`, `${X}`, `{model}`.
_PLACEHOLDER_RE = re.compile(r"^[<$({]|[>})]$")


def _clean(v: str) -> str:
    return v.strip().strip("`'\"*_").rstrip(".,;:").strip("`'\"")


def model_header(text: str) -> str | None:
    """The raw `**Model:**` header value, or None when the task has none (the header is optional)."""
    m = MODEL_HEADER_RE.search(text or "")
    return m.group("v").strip() if m else None


def code_block_models(text: str) -> list:
    """Every literal `--model` argument inside a fenced code block."""
    out = []
    for block in _FENCE_RE.finditer(text or ""):
        for m in _CODE_MODEL_RE.finditer(block.group("body")):
            v = _clean(m.group("v"))
            if v and not _PLACEHOLDER_RE.search(v):
                out.append(v)
    return out


def lock_quote(home: Path | None = None) -> str:
    """The lock, quoted for a refusal: `fable=claude-fable-5-1, ... (CLI 2.1.295, 2026-10-09)`."""
    lock = load_lock(home)
    ids = ", ".join(f"{f}={r['model']}" for f, r in sorted(lock["families"].items()))
    return f"{ids} (CLI {lock['cli']['version']}, resolved {lock.get('resolved_on')})"


def check_task_models(text: str, home: Path | None = None) -> dict:
    """R5 and the Model header grammar against the current lock.

    Returns ``{ok, header, role, model, code_models, errors}``. `role` is the header's role when
    it names one; `model` is the id the header resolves to (the role's, or the id it names). Prose
    that cites history is not checked: only the header and fenced code blocks are read.
    """
    header = model_header(text)
    code = code_block_models(text)
    if header is None and not code:
        # Nothing to check, so nothing is read: a task that names no model never depends on the
        # lock being readable.
        return {"ok": True, "header": None, "role": None, "model": None, "code_models": [],
                "errors": []}
    home = _home(home)
    roles = load_registry(home)["roles"]
    ids = set(lock_ids(home).values())
    errors = []
    role = model = None
    if header is not None:
        value = _clean(header.split()[0]) if header.split() else ""
        if value in roles:
            role, model = value, resolve(value, home)
        elif value in ids:
            model = value
        elif value in ALIASES:
            errors.append(f"Model header names the alias {value!r}; a task names a role "
                          f"(AD-035 R4); expected {MODEL_GRAMMAR}")
        else:
            errors.append(f"Model header {header!r} does not parse; expected {MODEL_GRAMMAR}")
        stale = sorted({m.group(0).rstrip(".,;:)`") for m in MODEL_ID_RE.finditer(header)} - ids)
        if stale:
            errors.append(f"Model header names {stale}, not in the lock (AD-035 R5)")
    bad = [v for v in code if v not in ids]
    if bad:
        errors.append(f"code-block --model names {sorted(set(bad))}, not in the lock (AD-035 R5)")
    if errors:
        errors.append(f"the lock: {lock_quote(home)}")
    return {"ok": not errors, "header": header, "role": role, "model": model,
            "code_models": code, "errors": errors}


# ------------------------------------------------------------------------------- refresh (R2)

def _today() -> str:
    return _dt.datetime.now(_dt.timezone.utc).date().isoformat()


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")


def probe_env(base: dict | None = None) -> dict:
    """A probe child's environment: no credentials, no parent session, no family pin."""
    env = dict(os.environ if base is None else base)
    for k in list(env):
        if k in _PROBE_SCRUB_EXACT or k.startswith(_PROBE_SCRUB_PREFIX):
            env.pop(k)
    return env


def probe_command(cli_path: str, alias: str, prompt: str) -> list:
    """One minimal call: no tools, one turn, no session, no user settings, no MCP, R6's setting."""
    return [cli_path, "-p", prompt, "--model", alias, "--output-format", "json",
            "--tools", "", "--max-turns", "1", "--no-session-persistence",
            "--setting-sources", "", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
            "--settings", settings_json()]


def _default_runner(cmd: list, *, cwd: str | None, env: dict, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)


@dataclass
class RefreshOutcome:
    """What a refresh did, as values."""

    status: str                      # cached | unchanged | bumped | written
    lock: dict
    evidence: str | None = None
    event: dict | None = None
    committed: str | None = None
    messages: list = field(default_factory=list)


def _repo_root(home: Path) -> Path:
    return home.parent


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def refresh(*, home: Path | None = None, force: bool = False, version: str | None = None,
            commit: bool = True, runner: Callable | None = None,
            npm: Callable | None = None, today: str | None = None) -> RefreshOutcome:
    """R2: install the newest CLI into a versioned prefix, probe each family alias, write the lock.

    `runner(cmd, cwd=, env=, timeout=)` runs a command (default `subprocess.run`); tests pass a
    fake. `npm` is the same seam for the two npm commands. Nothing is written when every probe
    agrees with the current lock and the day is the same: re-running is idempotent. When an id or
    the CLI version changes, a `models_lock_bumped` event naming old and new is appended to the
    seldon event store. The lock, the evidence and the event are committed only on the configured
    branch.
    """
    home = _home(home)
    reg = load_registry(home)
    cfg = reg["refresh"]
    runner = runner or _default_runner
    npm = npm or runner
    today = today or _today()
    old = None
    if (home / LOCK_FILE).is_file():
        old = load_lock(home)
    if (old and not force and cfg["cache"] == "day" and str(old.get("resolved_on")) == today
            and Path(old["cli"]["path"]).expanduser().exists()):
        return RefreshOutcome(status="cached", lock=old,
                              messages=[f"lock resolved today ({today}); cached for the day"])

    pkg = cfg["npm_package"]
    if version is None:
        res = npm(["npm", "view", pkg, "version"], cwd=None, env=dict(os.environ),
                  timeout=int(cfg["npm_timeout_s"]))
        if res.returncode != 0 or not res.stdout.strip():
            raise ModelsError(f"`npm view {pkg} version` failed: {(res.stderr or '').strip()[:300]}")
        version = res.stdout.strip().splitlines()[-1].strip()
    prefix = Path(cfg["install_root"]).expanduser() / version
    cli_path = prefix / cfg["bin_relpath"]
    installed = False
    if not cli_path.exists():
        prefix.mkdir(parents=True, exist_ok=True)
        res = npm(["npm", "install", "--prefix", str(prefix), "--no-fund", "--no-audit",
                   f"{pkg}@{version}"], cwd=str(prefix), env=dict(os.environ),
                  timeout=int(cfg["npm_timeout_s"]))
        if res.returncode != 0 or not cli_path.exists():
            raise ModelsError(f"npm install of {pkg}@{version} into {prefix} failed: "
                              f"{(res.stderr or res.stdout or '').strip()[-500:]}")
        installed = True
    env = probe_env()
    got = runner([str(cli_path), "--version"], cwd=None, env=env, timeout=60)
    reported = (got.stdout or "").strip().split()[0] if (got.stdout or "").strip() else ""
    if got.returncode != 0 or reported != version:
        raise ModelsError(f"{cli_path} reports {reported!r}, expected {version!r}")

    probes = {}
    families = {}
    cwd = tempfile.mkdtemp(prefix="seldon-models-probe-")
    for fam in cfg["families"]:
        cmd = probe_command(str(cli_path), fam, cfg["probe_prompt"])
        started = _dt.datetime.now(_dt.timezone.utc)
        res = runner(cmd, cwd=cwd, env=env, timeout=int(cfg["probe_timeout_s"]))
        secs = round((_dt.datetime.now(_dt.timezone.utc) - started).total_seconds(), 3)
        envelope = None
        try:
            envelope = json.loads(res.stdout) if res.stdout else None
        except json.JSONDecodeError:
            envelope = last_result_envelope(res.stdout)
        served = served_model(envelope or {})
        probes[fam] = {"alias": fam, "argv": cmd, "exit_code": res.returncode, "seconds": secs,
                       "served": served,
                       "model_usage_keys": sorted((envelope or {}).get("modelUsage") or {}),
                       "envelope": envelope, "stderr_tail": (res.stderr or "")[-500:]}
        if res.returncode != 0 or served is None:
            raise ModelsError(f"probe {fam!r} failed (exit {res.returncode}): "
                              f"{(res.stderr or res.stdout or '').strip()[:300]}")
        if not served.startswith(f"claude-{fam}-"):
            raise ModelsError(f"probe {fam!r} was served {served!r}, not a {fam} model")
        families[fam] = {"alias": fam, "model": served}

    old_ids = {f: r["model"] for f, r in (old or {}).get("families", {}).items()}
    old_cli = str((old or {}).get("cli", {}).get("version") or "")
    new_ids = {f: r["model"] for f, r in families.items()}
    changed = old is None or old_ids != new_ids or old_cli != version
    root = _repo_root(home)
    evidence_rel = f"{cfg['evidence_dir']}/refresh_{today}.json"
    if (root / evidence_rel).exists():
        # A second refresh on one day (forced) never overwrites the first one's evidence.
        evidence_rel = f"{cfg['evidence_dir']}/refresh_{today}_{_now()[11:19].replace(':', '')}.json"
    evidence_path = root / evidence_rel
    lock = {"schema": 1, "resolved_on": today, "resolved_at": _now(),
            "cli": {"version": version, "path": str(cli_path), "npm_package": pkg},
            "families": families, "evidence": evidence_rel}
    same_day_same = (old is not None and not changed and str(old.get("resolved_on")) == today)
    if same_day_same:
        return RefreshOutcome(status="unchanged", lock=old,
                              messages=["every probe agrees with the lock; nothing written"])

    evidence = {"refreshed_at": lock["resolved_at"], "date": today, "npm_package": pkg,
                "cli_version": version, "cli_path": str(cli_path), "installed_now": installed,
                "cli_version_reported": reported, "probe_cwd": cwd,
                "previous_lock": old, "probes": probes, "lock": lock}
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(evidence, indent=1, sort_keys=True) + "\n",
                             encoding="utf-8")
    _write_lock(home, lock)
    event = None
    touched = [str((home / LOCK_FILE).relative_to(root)), evidence_rel]
    if changed:
        from seldon.core.events import append_event, make_event
        event = make_event(EVENT_LOCK_BUMPED, actor="seldon-models", authority="AD-035-R2",
                           payload={"old": {"families": old_ids, "cli_version": old_cli or None},
                                    "new": {"families": new_ids, "cli_version": version},
                                    "evidence": evidence_rel, "lock": LOCK_FILE})
        append_event(root, event)
        touched.append("seldon_events.jsonl")
    committed = None
    msgs = []
    if commit:
        committed, why = _commit(root, touched, cfg["commit_branch"],
                                 f"models: lock {'bumped' if changed else 'rechecked'} "
                                 f"{today} (CLI {version}; AD-035 R2)")
        if why:
            msgs.append(f"not committed: {why}")
    return RefreshOutcome(status="bumped" if changed else "written", lock=lock,
                          evidence=evidence_rel, event=event, committed=committed,
                          messages=msgs)


def _write_lock(home: Path, lock: dict) -> None:
    header = ("# The model lock: RESOLUTION, written only by `seldon models refresh` (AD-035 R1, R2).\n"
              "# Never edit by hand. Intent is in registry.yaml; this file is what the newest CLI's\n"
              "# own alias resolver served, one probe per family, with the evidence file named below.\n")
    tmp = home / f".{LOCK_FILE}.{uuid.uuid4().hex}.tmp"
    tmp.write_text(header + yaml.safe_dump(lock, sort_keys=False), encoding="utf-8")
    os.replace(tmp, home / LOCK_FILE)


def _commit(root: Path, paths: list, branch: str, message: str) -> tuple:
    """Path-scoped commit on `branch` only. Returns `(sha, None)` or `(None, why)`."""
    inside = _git(root, "rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0:
        return None, f"{root} is not a git work tree"
    current = _git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if current != branch:
        return None, f"checkout is on {current!r}, refresh commits only on {branch!r}"
    add = _git(root, "add", "--", *paths)
    if add.returncode != 0:
        return None, f"git add failed: {add.stderr.strip()[:200]}"
    done = _git(root, "commit", "-m", message, "--", *paths)
    if done.returncode != 0:
        return None, f"git commit failed: {(done.stderr or done.stdout).strip()[:200]}"
    return _git(root, "rev-parse", "--short", "HEAD").stdout.strip(), None


def ensure_fresh(trigger: str, home: Path | None = None, **kw) -> str | None:
    """R2's "runs when a task is authored and when a run starts", cached for the day.

    `trigger` is `register` or `dispatch`; the registry's `auto_on_<trigger>` switches it. Returns
    None when the lock is current (or the switch is off), or a warning when the refresh failed: the
    current lock still stands, and an offline registration is not refused for it.
    """
    try:
        home = _home(home)
        if not load_registry(home)["refresh"].get(f"auto_on_{trigger}"):
            return None
        out = refresh(home=home, **kw)
        return "; ".join(out.messages) or None
    except (ModelsError, OSError, subprocess.SubprocessError) as exc:
        return f"WARNING: model lock not refreshed ({type(exc).__name__}: {exc}); using the current lock"


def which_cli() -> str | None:
    """The interactive `claude` on PATH, for `show` to report beside the lock's. Never launched."""
    return shutil.which("claude")


def show(home: Path | None = None) -> dict:
    """The registry's roles with what each resolves to, and the lock."""
    home = _home(home)
    reg = load_registry(home)
    try:
        lock = load_lock(home)
    except ModelsError as exc:
        lock = {"error": str(exc)}
    rows = []
    for name, row in sorted(reg["roles"].items()):
        model = (lock.get("families") or {}).get(row["family"], {}).get("model")
        rows.append({"role": name, "family": row["family"], "effort": row["effort"],
                     "model": model})
    return {"home": str(home), "roles": rows, "lock": lock, "path_cli": which_cli()}


def as_json(obj: Any) -> str:
    return json.dumps(obj, indent=1, sort_keys=True, default=str)
