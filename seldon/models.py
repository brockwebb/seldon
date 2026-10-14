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

- `models/registry.yaml` is intent: role to a family or to a named model, plus the parameters the
  role runs with (R1; AD-035-R9). Its `models:` catalog is each model's parameter profile: which
  parameters it takes and which values (AD-035-R10, R11).
- `models/models.lock.yaml` is resolution: family to model id, plus the CLI that resolved it, the
  date and the evidence file. Only :func:`refresh` writes it (R2), by asking Anthropic's own
  resolver, the newest CLI, one probe per family alias, plus one probe per model a role names,
  recorded under `models:` with whether it was served exactly (AD-035-R10).
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
#: AD-035-R12: a role naming a model the lock does not mark available. Never a fallback.
UNAVAILABLE = "model_unavailable"
#: AD-035-R10 and MODEL-003 ADDENDUM 02 section 2: the catalog holds Anthropic model ids only.
ANTHROPIC_PREFIX = "claude-"
#: Keys of a `roles:` row that are not launch parameters. Every other key is a parameter, and must
#: be one the role's model supports, with a value it supports (AD-035-R11).
ROLE_NON_PARAM_KEYS = ("family", "model", "uses")

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
#: The registry value AD-035 allowed and AD-036-R8 refuses: it passed no `--effort` flag, so the
#: level was whatever the served model's own default was. Kept as a name only for the refusal.
EFFORT_DEFAULT = "default"
#: The CLI reads this variable as an explicit effort choice of the same rank as `--effort`
#: (code.claude.com/docs/en/model-config, read 2026-10-09). A launch sets it to the declared level
#: so an inherited value cannot disagree with the flag.
EFFORT_ENV = "CLAUDE_CODE_EFFORT_LEVEL"
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
                             "auto_on_dispatch", "documented_default_effort")


class ModelsError(Exception):
    """The registry or the lock is missing, malformed or does not answer. Fatal: no call is made."""


class JudgeUncalibrated(ModelsError):
    """`judge_uncalibrated`: a judge with no passing calibration report on its current lock entry (AD-037-R5)."""


class UnknownRole(ModelsError):
    """A launcher asked for a role the registry does not hold."""


class ModelUnavailable(ModelsError):
    """`model_unavailable`: a role names a model the lock does not mark available (AD-035-R12).

    The role is not resolved to anything else: falling back to the family head would be the silent
    substitution R6 exists to stop.
    """

    reason = UNAVAILABLE

    def __init__(self, role: str, model: str, entry: dict | None, lock_path: Path):
        self.role, self.model, self.entry = role, model, dict(entry or {})
        if not entry:
            why = (f"{lock_path} has no `models:` entry for it; run `seldon models refresh --force`, "
                   f"which probes every model a role names")
        else:
            why = (f"the lock's last probe was served {entry.get('served')!r} "
                   f"(evidence {entry.get('evidence')}){': ' + entry['error'] if entry.get('error') else ''}")
        super().__init__(f"{UNAVAILABLE}: role {role!r} names {model!r}, which the lock does not mark "
                         f"available: {why}. It is not resolved to another model (AD-035-R12)")


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
    """The registry, validated.

    Every role names a known family or a model in the `models:` catalog (AD-035-R9), and every
    parameter it declares is one its model's profile supports, with a supported value (AD-035-R11).
    A role whose model takes effort levels names one (AD-036-R8).
    """
    path = _home(home) / REGISTRY_FILE
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    roles = data.get("roles")
    if not isinstance(roles, dict) or not roles:
        raise ModelsError(f"{path}: no `roles:` mapping")
    refresh_cfg = data.get("refresh")
    if not isinstance(refresh_cfg, dict):
        raise ModelsError(f"{path}: no `refresh:` block")
    missing = [k for k in REGISTRY_REQUIRED_REFRESH if k not in refresh_cfg]
    if missing:
        raise ModelsError(f"{path}: refresh block missing {missing}")
    _check_documented_defaults(path, refresh_cfg["documented_default_effort"],
                               refresh_cfg["families"])
    heads = {f: r["model"] for f, r in refresh_cfg["documented_default_effort"]["families"].items()}
    catalog = _check_catalog(path, data.get("models"), heads)
    for name, row in roles.items():
        _check_role(path, name, row, catalog, heads)
    _check_checker(path, data.get(CHECKER_ROLE), roles)
    _check_calibration(path, data.get("calibration"))
    return data


def _check_catalog(path: Path, catalog, heads: dict) -> dict:
    """AD-035-R10: the `models:` catalog, keyed by Anthropic model id, one parameter profile each.

    Each entry names its family (the id must start `claude-<family>-`, so a non-Anthropic id cannot
    enter, MODEL-003 ADDENDUM 02 section 2) and `supported_params`, a mapping of parameter name to
    the values the model accepts (`effort: []` when it takes none). `default_effort`, when given,
    is the model's documented default, used only when a task names the id instead of a role. The
    family heads the documented-default table was read for have entries too.
    """
    if not isinstance(catalog, dict) or not catalog:
        raise ModelsError(f"{path}: no `models:` catalog (AD-035-R10)")
    for mid, entry in catalog.items():
        if not isinstance(entry, dict):
            raise ModelsError(f"{path}: models.{mid} is not a mapping")
        fam = entry.get("family")
        if fam not in FAMILY_ENV:
            raise ModelsError(f"{path}: models.{mid} family {fam!r} is not one of {sorted(FAMILY_ENV)}")
        if not str(mid).startswith(f"{ANTHROPIC_PREFIX}{fam}-"):
            raise ModelsError(f"{path}: models.{mid} does not start with {ANTHROPIC_PREFIX}{fam}-: the "
                              f"catalog holds Anthropic model ids of the family it names (AD-035-R10)")
        params = entry.get("supported_params")
        if not isinstance(params, dict) or not all(isinstance(v, list) for v in params.values()):
            raise ModelsError(f"{path}: models.{mid} needs `supported_params`, a mapping of parameter "
                              f"to the list of values the model accepts (AD-035-R10)")
        bad = [v for v in params.get("effort", []) if v not in EFFORT_LEVELS]
        if bad:
            raise ModelsError(f"{path}: models.{mid} effort values {bad} are not CLI levels {EFFORT_LEVELS}")
        default = entry.get("default_effort")
        if default is not None and default not in params.get("effort", []):
            raise ModelsError(f"{path}: models.{mid} default_effort {default!r} is not in its "
                              f"supported effort {params.get('effort', [])}")
    absent = sorted(m for m in heads.values() if m not in catalog)
    if absent:
        raise ModelsError(f"{path}: the family heads {absent} have no `models:` entry (AD-035-R10)")
    return catalog


def _role_model(name: str, row: dict, heads: dict) -> tuple:
    """`(family, catalog id, named)`: the model whose profile a role is checked against.

    A role naming a model is checked against that model. A role naming a family is checked at load
    against the head the documented-default table was read for; `resolve_role` checks it again
    against whatever head the lock serves, when the catalog has that head.
    """
    if "model" in row:
        return None, row["model"], True
    return row["family"], heads[row["family"]], False


def _check_role(path: Path, name: str, row, catalog: dict, heads: dict) -> None:
    """AD-035-R9 (family xor model), R11 (declared parameters against the profile), AD-036-R8."""
    if not isinstance(row, dict):
        raise ModelsError(f"{path}: role {name!r} is not a mapping")
    if ("family" in row) == ("model" in row):
        raise ModelsError(f"{path}: role {name!r} must name exactly one of `family` or `model` "
                          f"(AD-035-R9)")
    if "family" in row and row["family"] not in FAMILY_ENV:
        raise ModelsError(f"{path}: role {name!r} family {row.get('family')!r} is not one "
                          f"of {sorted(FAMILY_ENV)}")
    if "model" in row and row["model"] not in catalog:
        raise ModelsError(f"{path}: role {name!r} names model {row['model']!r}, which has no entry "
                          f"in the `models:` catalog; add its measured profile first (AD-035-R10)")
    _fam, mid, _named = _role_model(name, row, heads)
    _check_params(f"{path}: role {name!r}", row, mid, catalog[mid])


def _check_params(where: str, row: dict, mid: str, entry: dict) -> None:
    """Every declared parameter is supported by `mid`'s profile; effort is named when it has levels."""
    supported = entry["supported_params"]
    effort = row.get("effort")
    if effort == EFFORT_DEFAULT:
        raise ModelsError(f"{where} effort 'default' is refused (AD-036-R8): name one of "
                          f"{supported.get('effort') or EFFORT_LEVELS}, the level the role is to run at")
    if supported.get("effort") and effort is None:
        raise ModelsError(f"{where} names no effort; {mid} takes {supported['effort']}, so the role "
                          f"names the level it runs at (AD-036-R8)")
    for key, value in row.items():
        if key in ROLE_NON_PARAM_KEYS:
            continue
        if key not in supported:
            raise ModelsError(f"{where} declares parameter {key!r}, which model {mid} does not "
                              f"support (its profile: {sorted(supported)}) (AD-035-R11)")
        if value not in supported[key]:
            raise ModelsError(f"{where} {key} {value!r} is not supported by model {mid}, which "
                              f"takes {supported[key]} (AD-035-R11; AD-036-R8)")


def role_family(reg: dict, role: str) -> str:
    """A role's family: the one it names, or its named model's catalog family (AD-035-R9)."""
    row = reg["roles"][role]
    return reg["models"][row["model"]]["family"] if "model" in row else row["family"]


def named_models(home: Path | None = None, reg: dict | None = None) -> list:
    """Every model id a role names directly (AD-035-R9), sorted: what `refresh` probes beyond the families."""
    reg = reg if reg is not None else load_registry(home)
    return sorted({row["model"] for row in reg["roles"].values() if "model" in row})


#: AD-037-R2: the role resolved relative to a generator role, the next tier above it.
CHECKER_ROLE = "checker"
CALIBRATION_REQUIRED = ("report_dir", "set", "z", "defect_label", "bar")


def _check_checker(path: Path, block, roles: dict) -> None:
    """The `checker:` block names an effort and one tier per family, each a known family."""
    if CHECKER_ROLE in roles:
        raise ModelsError(f"{path}: `{CHECKER_ROLE}` is the `{CHECKER_ROLE}:` block, not a row of `roles:` (AD-037-R2)")
    if not isinstance(block, dict):
        raise ModelsError(f"{path}: no `{CHECKER_ROLE}:` block (AD-037-R2)")
    if block.get("effort") not in EFFORT_LEVELS:
        raise ModelsError(f"{path}: `{CHECKER_ROLE}.effort` must be one of {EFFORT_LEVELS}")
    tiers = block.get("tiers")
    if not isinstance(tiers, dict) or sorted(tiers) != sorted(FAMILY_ENV):
        raise ModelsError(f"{path}: `{CHECKER_ROLE}.tiers` must name exactly {sorted(FAMILY_ENV)}")
    for fam, row in tiers.items():
        if not isinstance(row, dict) or row.get("family") not in FAMILY_ENV:
            raise ModelsError(f"{path}: `{CHECKER_ROLE}.tiers.{fam}` needs a `family` in {sorted(FAMILY_ENV)}")


def _check_calibration(path: Path, block) -> None:
    """The `calibration:` block (AD-037-R3, R5): where reports live, the set, and the bar."""
    if not isinstance(block, dict):
        raise ModelsError(f"{path}: no `calibration:` block (AD-037-R5)")
    missing = [k for k in CALIBRATION_REQUIRED if k not in block]
    bar = block.get("bar") or {}
    missing += [f"bar.{k}" for k in ("generator_catch_lower", "n_min") if k not in bar]
    if missing:
        raise ModelsError(f"{path}: `calibration:` lacks {missing}")


def _check_documented_defaults(path: Path, table, families: list) -> None:
    """AD-036-R8: the documented default effort table names its source and date and one row per
    family the lock resolves, each with the model it was read for and a known level."""
    if not isinstance(table, dict) or not table.get("source") or not table.get("retrieved"):
        raise ModelsError(f"{path}: refresh.documented_default_effort needs `source` and "
                          f"`retrieved` (AD-036-R8)")
    rows = table.get("families")
    if not isinstance(rows, dict) or sorted(rows) != sorted(families):
        raise ModelsError(f"{path}: refresh.documented_default_effort.families must name exactly "
                          f"{sorted(families)}")
    for fam, row in rows.items():
        if (not isinstance(row, dict) or row.get("effort") not in EFFORT_LEVELS
                or not str(row.get("model") or "").startswith(f"claude-{fam}-")):
            raise ModelsError(f"{path}: documented_default_effort row {fam!r} needs a "
                              f"claude-{fam}-* `model` and an `effort` in {EFFORT_LEVELS}")


def documented_default_effort(family: str, home: Path | None = None) -> str:
    """The family's documented default effort (registry `refresh.documented_default_effort`)."""
    return load_registry(home)["refresh"]["documented_default_effort"]["families"][family]["effort"]


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
    # AD-035-R10: `models:` is optional (a lock written before it, or a registry naming no model).
    named = lock.get("models")
    if named is not None:
        if not isinstance(named, dict):
            raise ModelsError(f"{path}: `models:` is not a mapping")
        for mid, row in named.items():
            if not isinstance(row, dict) or not isinstance(row.get("available"), bool):
                raise ModelsError(f"{path}: models.{mid} needs `available: true|false`")
    return lock


def available_models(home: Path | None = None, lock: dict | None = None) -> dict:
    """`{model id: entry}` for every named model the lock marks available (AD-035-R12)."""
    lock = lock if lock is not None else load_lock(home)
    return {m: r for m, r in (lock.get("models") or {}).items() if r.get("available") is True}


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
    effort: str | None
    model: str
    cli_path: str
    cli_version: str
    resolved_on: str
    evidence: str | None = None
    #: AD-037-R2: a Fable checker reads an authorship-obfuscated text, since nothing sits above Fable.
    obfuscate: bool = False
    #: AD-035-R9: the role names this model id rather than following its family's head.
    named: bool = False


def resolve_role(role: str, home: Path | None = None, *, generator: str | None = None) -> Resolution:
    """The role's family, effort, model id and the CLI that resolved it.

    `checker` (AD-037-R2) resolves relative to the generator role whose work it reads: the next tier above that
    role's family, from the registry's `checker.tiers`. It needs `generator`; no other role takes one."""
    home = _home(home)
    reg = load_registry(home)
    roles = reg["roles"]
    obfuscate = False
    if role == CHECKER_ROLE:
        if not generator:
            raise ModelsError(f"role {CHECKER_ROLE!r} resolves relative to a generator role: pass generator=<role> "
                              f"(AD-037-R2)")
        if generator not in roles:
            raise UnknownRole(f"generator role {generator!r} is not in {home / REGISTRY_FILE}; the roles are "
                              f"{sorted(roles)} (AD-035 R1)")
        # AD-037-R2 maps by family. A role naming a model is read by its catalog family (an opus model by
        # fable), and that needs no lock: the checker is defined whether or not the generator is served.
        gen_fam = role_family(reg, generator)
        tier = reg[CHECKER_ROLE]["tiers"][gen_fam]
        fam, effort, obfuscate = tier["family"], reg[CHECKER_ROLE]["effort"], bool(tier.get("obfuscate", False))
        params = {"effort": effort}
    else:
        if generator is not None:
            raise ModelsError(f"only role {CHECKER_ROLE!r} resolves relative to a generator; {role!r} was given "
                              f"generator={generator!r}")
        if role not in roles:
            raise UnknownRole(f"role {role!r} is not in {home / REGISTRY_FILE}; the roles are "
                              f"{sorted(roles)} (AD-035 R1)")
        row = roles[role]
        effort = row.get("effort")
        if "model" in row:
            # AD-035-R9, R12: a named model resolves to itself while the lock marks it available,
            # and otherwise fails. It never falls back to the family head.
            lock = load_lock(home)
            model = row["model"]
            entry = (lock.get("models") or {}).get(model)
            if not entry or entry.get("available") is not True:
                raise ModelUnavailable(role, model, entry, home / LOCK_FILE)
            return Resolution(role=role, family=reg["models"][model]["family"], effort=effort,
                              model=model, cli_path=str(Path(lock["cli"]["path"]).expanduser()),
                              cli_version=str(lock["cli"]["version"]),
                              resolved_on=str(lock.get("resolved_on")),
                              evidence=entry.get("evidence") or lock.get("evidence"), named=True)
        fam, params = row["family"], row
    lock = load_lock(home)
    if fam not in lock["families"]:
        raise ModelsError(f"role {role!r} is family {fam!r}, which {home / LOCK_FILE} does not "
                          f"resolve; run `seldon models refresh`")
    model = lock["families"][fam]["model"]
    if model in reg["models"]:
        # AD-035-R11 again, against the head the lock serves today: an unsupported parameter fails
        # here rather than being dropped at launch. A head the catalog has no profile for yet is
        # named by `refresh` in the bump event (`profile_missing`).
        _check_params(f"role {role!r} (family {fam} -> {model})", params, model, reg["models"][model])
    return Resolution(role=role, family=fam, effort=effort, model=model,
                      cli_path=str(Path(lock["cli"]["path"]).expanduser()),
                      cli_version=str(lock["cli"]["version"]),
                      resolved_on=str(lock.get("resolved_on")),
                      evidence=lock.get("evidence"), obfuscate=obfuscate)


def resolve(role: str, home: Path | None = None, *, generator: str | None = None) -> str:
    """The model id for a role. AD-035 R1: the only way code on this machine gets one."""
    return resolve_role(role, home, generator=generator).model


def _require_calibration(home: Path, judge_model: str, generator_model: str) -> None:
    """Refuse a judge with no complete, passing calibration report for this judge id over this generator id."""
    from seldon.core import qc
    path = qc.report_path(home, judge_model, generator_model)
    if not path.is_file():
        raise JudgeUncalibrated(f"judge_uncalibrated: no calibration report for judge {judge_model} over generator "
                                f"{generator_model} at {path}; run `seldon qc calibrate-judge` (AD-037-R5; a lock "
                                f"bump voids a report, AD-035-R7)")
    report = json.loads(path.read_text(encoding="utf-8"))
    cfg = load_registry(home)["calibration"]
    try:
        ok = qc.passes(report, cfg)
    except qc.CalibrationIncomplete as exc:
        raise JudgeUncalibrated(f"judge_uncalibrated: {exc} ({path})") from exc
    if not ok:
        g = report["self_preference"]["generator"]
        raise JudgeUncalibrated(f"judge_uncalibrated: {path} is under the bar: generator-style catch rate Wilson-95 "
                                f"lower bound {float(g['ci95'][0]):.3f} with n {g['n']}; the bar is "
                                f"{cfg['bar']['generator_catch_lower']} with n >= {cfg['bar']['n_min']} (AD-037-R3)")


def resolve_judge(role: str, generator: str, home: Path | None = None) -> str:
    """The model id for `role` used as a reading judge of `generator`'s work, only with a passing calibration report
    for that judge id over that generator id (AD-037-R5). `role` may be `checker`, resolved over `generator`."""
    home = _home(home)
    judge = resolve(role, home, generator=generator if role == CHECKER_ROLE else None)
    _require_calibration(home, judge, resolve(generator, home))
    return judge


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
    args, settings}``. `args` is ``["--model", id, "--settings", json, "--effort", level]``:
    effort is always passed when the model takes one (AD-036-R8), and `env` carries the same level
    in ``CLAUDE_CODE_EFFORT_LEVEL`` beside the four family ids. A model whose profile is
    `effort: []` launches with neither, and `effort` None (AD-035-R11). A launcher execs
    ``cli_path`` with its own flags and `args`, with `env` laid over the child's environment, and
    records :func:`receipt` with ``effort=spec["effort"]``.

    The four `ANTHROPIC_DEFAULT_*_MODEL` variables always carry the family heads; for a role that
    names a model, `--model` carries that id and the R6 receipt compares the served id with it.
    """
    r = resolve_role(role, home)
    return _spec(role=r.role, family=r.family, effort=r.effort, model=r.model,
                 cli_path=r.cli_path, cli_version=r.cli_version, resolved_on=r.resolved_on,
                 evidence=r.evidence, home=home)


def _spec(*, role, family, effort, model, cli_path, cli_version, resolved_on, evidence,
          home) -> dict:
    env = launch_env(home)
    args = ["--model", model, "--settings", settings_json()]
    if effort is not None:
        env[EFFORT_ENV] = effort
        args += ["--effort", effort]
    return {"role": role, "family": family, "effort": effort, "model": model,
            "cli_path": cli_path, "cli_version": cli_version, "resolved_on": resolved_on,
            "evidence": evidence, "env": env, "args": args,
            "settings": dict(LAUNCH_SETTINGS)}


def launch_spec_for(target: str, home: Path | None = None) -> dict:
    """The launch block for a task's `**Model:**` value: a role, or an id equal to the lock's.

    A family head's id is launched as its family, at the family's documented default effort
    (AD-036-R8), with `role` None. An available named model's id (AD-035-R12) is launched at its
    catalog `default_effort`, and refused when its profile has effort levels but no documented
    default. Anything else fails loudly, because a header that names neither is refused at
    registration (R5).
    """
    home = _home(home)
    reg = load_registry(home)
    if target in reg["roles"]:
        return launch_spec(target, home)
    lock = load_lock(home)
    ids = lock_ids(home)
    fams = [f for f, m in ids.items() if m == target]
    if fams:
        fam, effort, evidence = fams[0], documented_default_effort(fams[0], home), lock.get("evidence")
    elif target in available_models(lock=lock) and target in reg["models"]:
        entry = reg["models"][target]
        fam, effort = entry["family"], entry.get("default_effort")
        if effort is None and entry["supported_params"].get("effort"):
            raise ModelsError(f"{target!r} has no documented `default_effort` in the catalog; name a "
                              f"role that declares its effort (AD-036-R8)")
        evidence = lock["models"][target].get("evidence")
    else:
        raise ModelsError(f"{target!r} is neither a role nor an id in the lock: {lock_quote(home)}")
    return _spec(role=None, family=fam, effort=effort,
                 model=target, cli_path=str(Path(lock["cli"]["path"]).expanduser()),
                 cli_version=str(lock["cli"]["version"]),
                 resolved_on=str(lock.get("resolved_on")), evidence=evidence,
                 home=home)


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


def receipt(requested: str, envelope: dict, effort: str | None = None) -> dict:
    """R6's record for one call: `{requested, served, side_models, ok, effort}`.

    `effort` is the level the launch passed (`launch_spec(...)["effort"]`, AD-036-R8). None records
    that the caller did not say, which a reader can see; it is never filled in by guessing.
    """
    served = served_model(envelope)
    mu = envelope.get("modelUsage") if isinstance(envelope, dict) else None
    side = sorted(k for k in (mu or {}) if k != served) if isinstance(mu, dict) else []
    return {"requested": requested, "served": served, "side_models": side,
            "ok": served is not None and served == requested, "effort": effort}


def check_receipt(requested: str, envelope: dict, effort: str | None = None) -> dict:
    """The receipt, or :class:`ModelSubstituted` when the served model is not the requested one."""
    r = receipt(requested, envelope, effort)
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
    named = "; ".join(f"{m} available={r.get('available')} served={r.get('served')}"
                      for m, r in sorted((lock.get("models") or {}).items()))
    return (f"{ids}{'; named: ' + named if named else ''} "
            f"(CLI {lock['cli']['version']}, resolved {lock.get('resolved_on')})")


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
    # AD-035-R12: the family heads plus every named model the lock marks available.
    ids = set(lock_ids(home).values()) | set(available_models(home))
    errors = []
    role = model = None
    if header is not None:
        value = _clean(header.split()[0]) if header.split() else ""
        if value in roles:
            role = value
            try:
                model = resolve(value, home)
            except ModelUnavailable as exc:
                errors.append(f"Model header names role {value!r}: {exc}")
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
    named = named_models(reg=reg)
    # A role added today names a model the lock has never probed: the day's cache does not cover it.
    unprobed = [m for m in named if m not in ((old or {}).get("models") or {})]
    if (old and not force and cfg["cache"] == "day" and str(old.get("resolved_on")) == today
            and Path(old["cli"]["path"]).expanduser().exists() and not unprobed):
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

    model_probes, named_lock = _probe_named(named, str(cli_path), cfg, runner, env, cwd)

    old_ids = {f: r["model"] for f, r in (old or {}).get("families", {}).items()}
    old_cli = str((old or {}).get("cli", {}).get("version") or "")
    new_ids = {f: r["model"] for f, r in families.items()}
    documented = _documented_in_lock(cfg["documented_default_effort"], new_ids)
    old_documented = (old or {}).get("documented_default_effort")
    old_named = _named_state((old or {}).get("models"))
    new_named = _named_state(named_lock)
    changed = (old is None or old_ids != new_ids or old_cli != version
               or old_documented != documented or old_named != new_named)
    root = _repo_root(home)
    evidence_rel = f"{cfg['evidence_dir']}/refresh_{today}.json"
    if (root / evidence_rel).exists():
        # A second refresh on one day (forced) never overwrites the first one's evidence.
        evidence_rel = f"{cfg['evidence_dir']}/refresh_{today}_{_now()[11:19].replace(':', '')}.json"
    evidence_path = root / evidence_rel
    for row in named_lock.values():
        row["evidence"] = evidence_rel
    lock = {"schema": 1, "resolved_on": today, "resolved_at": _now(),
            "cli": {"version": version, "path": str(cli_path), "npm_package": pkg},
            "families": families, "documented_default_effort": documented,
            "evidence": evidence_rel}
    if named_lock:
        lock["models"] = named_lock
    same_day_same = (old is not None and not changed and str(old.get("resolved_on")) == today)
    if same_day_same:
        return RefreshOutcome(status="unchanged", lock=old,
                              messages=["every probe agrees with the lock; nothing written"])

    evidence = {"refreshed_at": lock["resolved_at"], "date": today, "npm_package": pkg,
                "cli_version": version, "cli_path": str(cli_path), "installed_now": installed,
                "cli_version_reported": reported, "probe_cwd": cwd,
                "previous_lock": old, "probes": probes, "model_probes": model_probes,
                "lock": lock}
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(evidence, indent=1, sort_keys=True) + "\n",
                             encoding="utf-8")
    _write_lock(home, lock)
    event = None
    touched = [str((home / LOCK_FILE).relative_to(root)), evidence_rel]
    if changed:
        from seldon.core.events import append_event, make_event
        event = make_event(EVENT_LOCK_BUMPED, actor="seldon-models", authority="AD-035-R2",
                           payload={"old": {"families": old_ids, "cli_version": old_cli or None,
                                            "documented_default_effort": old_documented},
                                    "new": {"families": new_ids, "cli_version": version,
                                            "documented_default_effort": documented},
                                    "old_models": old_named, "new_models": new_named,
                                    "documented_default_effort_unverified": sorted(
                                        f for f, r in documented["families"].items()
                                        if not r["current"]),
                                    # AD-035-R11: a head the catalog has no parameter profile for.
                                    "profile_missing": sorted(
                                        m for m in new_ids.values() if m not in reg["models"]),
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


def _probe_named(named: list, cli_path: str, cfg: dict, runner: Callable, env: dict,
                 cwd: str) -> tuple:
    """AD-035-R10: one probe per model a role names, `--model <id>`. `(probes, lock entries)`.

    Served must equal the id exactly; anything else, a non-zero exit, a timeout or an unreadable
    envelope is `available: false` with the reason. A failed probe never raises: the family probes
    and the lock stand without it, and the role naming it fails as `model_unavailable` (R12).
    """
    probes, entries = {}, {}
    for mid in named:
        cmd = probe_command(cli_path, mid, cfg["probe_prompt"])
        started = _dt.datetime.now(_dt.timezone.utc)
        envelope, served, error, code, stderr = None, None, None, None, ""
        try:
            res = runner(cmd, cwd=cwd, env=env, timeout=int(cfg["probe_timeout_s"]))
            code, stderr = res.returncode, (res.stderr or "")
            try:
                envelope = json.loads(res.stdout) if res.stdout else None
            except json.JSONDecodeError:
                envelope = last_result_envelope(res.stdout)
            served = served_model(envelope or {})
            if code != 0 or served is None:
                error = f"exit {code}: {(res.stderr or res.stdout or '').strip()[:300]}"
        except (subprocess.SubprocessError, OSError) as exc:
            error = f"{type(exc).__name__}: {exc}"
        secs = round((_dt.datetime.now(_dt.timezone.utc) - started).total_seconds(), 3)
        available = error is None and served == mid
        if error is None and not available:
            error = f"served {served!r}, not {mid!r}"
        probes[mid] = {"model": mid, "argv": cmd, "exit_code": code, "seconds": secs,
                       "served": served, "available": available, "error": error,
                       "model_usage_keys": sorted((envelope or {}).get("modelUsage") or {}),
                       "envelope": envelope, "stderr_tail": stderr[-500:]}
        entries[mid] = {"served": served, "available": available}
        if error:
            entries[mid]["error"] = error
    return probes, entries


def _named_state(models_block) -> dict:
    """What a lock's `models:` says, without its evidence path: the part a re-probe can change."""
    return {m: {"served": r.get("served"), "available": r.get("available")}
            for m, r in sorted((models_block or {}).items())}


def _documented_in_lock(table: dict, new_ids: dict) -> dict:
    """The registry's documented-default table as the lock records it (AD-036-R8): per family the
    level, the model it was documented for, and `current`, false when the lock now serves a model
    the table was not read for. A refresh cannot measure a documented default; it can only say
    whether the one on file is about the model being served."""
    return {"source": table["source"], "retrieved": str(table["retrieved"]),
            "families": {f: {"effort": r["effort"], "documented_for": r["model"],
                             "current": new_ids.get(f) == r["model"]}
                         for f, r in sorted(table["families"].items())}}


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
        if "model" in row:
            entry = (lock.get("models") or {}).get(row["model"]) or {}
            rows.append({"role": name, "family": reg["models"][row["model"]]["family"],
                         "effort": row.get("effort"), "model": row["model"], "named": True,
                         "available": entry.get("available") is True})
            continue
        model = (lock.get("families") or {}).get(row["family"], {}).get("model")
        rows.append({"role": name, "family": row["family"], "effort": row.get("effort"),
                     "model": model, "named": False, "available": model is not None})
    return {"home": str(home), "roles": rows, "lock": lock, "path_cli": which_cli()}


def as_json(obj: Any) -> str:
    return json.dumps(obj, indent=1, sort_keys=True, default=str)
