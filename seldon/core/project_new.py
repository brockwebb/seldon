"""`seldon project new`: a directory becomes a seldon project, with a dispatcher and a squiddy graph, in one
command (SEL-019).

**Why.** Three consumer projects were adopted by hand: squiddy, hazbrief-mcp (SEL-016, 2026-10-29) and
aacps-ai-policy (AP-02, 2026-11-01, aacps commit 8869c47), each by the same sequence typed again: `seldon init`,
`seldon hooks install`, the environment the dispatcher's premise reads, `seldon dispatch adopt`, the plist symlinked
and bootstrapped, `dispatch.enabled` set true, the lot committed, and, for the two with a graph, `squiddy init` from
a `graph.yaml`. aacps ran its first task and its corpus acquisition before any of that existed, which is the failure
this command removes: the next consumer repository starts under seldon, never beside it.

**Composition, not re-implementation.** Every step is an existing command's own function: `seldon init`
(`seldon.commands.init.initialize_project`), `seldon hooks install` (`hooks.install`, `hooks.declare_union`),
`seldon dispatch adopt` (`adopt.adoption`, `adopt.write_adoption`, unchanged) and `squiddy init` (squiddy's CLI, run
as a subprocess, never imported: squiddy is another repository with its own interpreter). What is new here is only
what the hand adoptions typed after those commands: the environment block, the stations' `environment_ref`, the
FC-02 secret scan, an optional declared interpreter, loading the plist, the enable flip and the commit.

**Prior art: idempotent convergence.** The step model is configuration management's (CFEngine's convergent
operators, Burgess 2004, "A tiny overview of cfengine: convergent maintenance agent"; Ansible's per-task `ok` /
`changed` result): each step reads the state it would produce, acts only on the difference, and reports which it
was, so a second run on a finished project changes nothing and says so. The scaffolding half (one seed file, every
other artifact generated) is cookiecutter's and the OBO ODK's, already adopted by `squiddy init` (K-001); this
command does not template anything squiddy or seldon already generate.

**Where each value comes from.** The kit's (the primary seldon checkout's) `seldon.yaml`: `project_new:` for the
environment packages, the squiddy command and the LaunchAgents directory; `desktop_commit.scan` for the secret scan;
`dispatch:` and `jobs.dispatch` through `adopt` as before. A key the project already has is never rewritten (adopt's
rule, kept for every block this module adds).
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from seldon.core import adopt as A

#: The kit `project new` reads its block from: the same primary checkout `adopt` reads (`adopt._kit_dir`).
KIT_DIR = A.KIT_DIR

#: The skeleton `graph.yaml` written when `--graph` names a graph with no spec yet. Its required fields are blank:
#: the scope is the operator's words (squiddy DN-028 R-129) and is never guessed here.
GRAPH_SPEC_TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "graph_spec" / "squiddy_graph.yaml"

#: Where a consumer's graphs live (hazbrief-mcp `graphs/hazbrief-corpus`, aacps `graphs/aacps-policy-dm`).
GRAPHS_DIR = "graphs"

#: The record `squiddy init` writes into a graph it initialized (squiddy/init.py `RECORD`); its presence is the
#: state the graph step converges to.
SQUIDDY_INIT_RECORD = ".squiddy_init.json"

#: The commit `project new` makes of everything it wrote.
COMMIT_MESSAGE = "project: `seldon project new` (SEL-019)\n\n{body}\n"
ENABLE_COMMIT_MESSAGE = "dispatch: enabled by `seldon project new --enable` once its plist is loaded (SEL-019)\n"


class ProjectNewError(ValueError):
    """A step cannot run; the message names the step and what to do."""


@dataclass
class Step:
    """One step's outcome: `changed` (it acted), `ok` (already in the state it produces), `skipped` (not asked
    for) or `refused` (it could not act; `detail` says why and what to do)."""
    name: str
    status: str
    detail: str = ""
    wrote: list = field(default_factory=list)


def project_new_config(kit_dir: Path = KIT_DIR) -> dict:
    """The kit's `project_new:` block, validated. Every key is required: the code has no defaults."""
    kit = A.kit_config(kit_dir)
    block = kit.get("project_new")
    if not isinstance(block, dict):
        raise ProjectNewError(f"{kit_dir / 'seldon.yaml'} has no `project_new:` block")
    need = ("environment_packages", "squiddy_command", "launch_agents_dir")
    missing = [k for k in need if k not in block]
    if missing:
        raise ProjectNewError(f"{kit_dir / 'seldon.yaml'} project_new lacks {missing}")
    if not (isinstance(block["environment_packages"], list) and block["environment_packages"]):
        raise ProjectNewError("project_new.environment_packages must be a non-empty list of sibling repository names")
    if not (isinstance(block["squiddy_command"], list) and block["squiddy_command"]):
        raise ProjectNewError("project_new.squiddy_command must be a non-empty list")
    return {**block, "_kit": kit}


def kit_relative(value: str, kit_dir: Path) -> str:
    """A path written relative to the kit, made absolute; anything not path-shaped (a bare program name) as is."""
    if "/" not in value or os.path.isabs(value):
        return value
    return str((Path(kit_dir) / value).resolve())


def squiddy_command(cfg: dict, kit_dir: Path) -> list:
    return [kit_relative(str(cfg["squiddy_command"][0]), kit_dir)] + [str(x) for x in cfg["squiddy_command"][1:]]


# ───────────────────────────────────────────────────────────────── git

def _git(project_dir: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    out = subprocess.run(["git", *args], cwd=project_dir, capture_output=True, text=True)
    if check and out.returncode != 0:
        raise ProjectNewError(f"git {' '.join(args)} failed in {project_dir}: {(out.stderr or out.stdout).strip()}")
    return out


def is_repo_top(project_dir: Path) -> bool:
    out = _git(project_dir, "rev-parse", "--show-toplevel", check=False)
    return out.returncode == 0 and Path(out.stdout.strip()).resolve() == Path(project_dir).resolve()


def ensure_repo(project_dir: Path, branch: str) -> Step:
    """A git repository whose top is `project_dir`, on `branch` when it is created here. A directory inside some
    other repository is refused: a project is a repository of its own (each system has its own record)."""
    project_dir.mkdir(parents=True, exist_ok=True)
    if is_repo_top(project_dir):
        return Step("git", "ok", "already a git repository")
    inside = _git(project_dir, "rev-parse", "--show-toplevel", check=False)
    if inside.returncode == 0:
        raise ProjectNewError(f"{project_dir} is inside the repository {inside.stdout.strip()}; a seldon project "
                              f"is a repository of its own. Choose a directory outside it.")
    _git(project_dir, "init", "-b", branch)
    return Step("git", "changed", f"git init -b {branch}")


def dirty_paths(project_dir: Path) -> set:
    """Every path git would commit now (modified, staged or untracked, ignores honoured), one per file."""
    out = _git(project_dir, "status", "--porcelain", "-uall", "-z")
    paths = set()
    entries = out.stdout.split("\0")
    i = 0
    while i < len(entries):
        e = entries[i]
        if not e:
            i += 1
            continue
        code, path = e[:2], e[3:]
        paths.add(path)
        if "R" in code or "C" in code:
            i += 1          # the rename's source follows as its own entry
        i += 1
    return paths


def commit_paths(project_dir: Path, paths: list, message: str) -> str | None:
    """Commit exactly `paths`, through the hooks (never `--no-verify`); returns the short sha, or None when there
    is nothing to commit."""
    if not paths:
        return None
    _git(project_dir, "add", "--", *paths)
    staged = _git(project_dir, "diff", "--cached", "--name-only").stdout.split()
    if not staged:
        return None
    done = _git(project_dir, "commit", "-q", "-m", message, "--", *paths, check=False)
    if done.returncode != 0:
        _git(project_dir, "reset", "-q", "--", *paths, check=False)
        raise ProjectNewError(f"the commit of {', '.join(sorted(paths))} was refused: "
                              f"{(done.stderr or done.stdout).strip()}")
    return _git(project_dir, "rev-parse", "--short", "HEAD").stdout.strip()


# ───────────────────────────────────────────────────────────────── the session-state ignore line

#: Seldon's per-machine session state (`seldon init` step 3 makes the directory; the dispatcher's lease, leases
#: directory and stuck streak, the hooks' and the MCP's runtime files live under it). Never a record.
SESSION_STATE_LINE = ".seldon/"
SESSION_STATE_COMMENT = ("# Seldon's per-machine session state (lease, stuck streak, runtime logs); never a record "
                         "(SEL-020).")


def _tracked_ignore_rule(project_dir: Path, probe: str) -> bool:
    """Whether a `.gitignore` inside the repository ignores `probe`. `.git/info/exclude` and the global excludes
    file do not count: no clone or dispatched worktree inherits them from the record (aacps carried `.seldon/` in
    its `info/exclude`, SEL-020)."""
    out = subprocess.run(["git", "check-ignore", "-v", "--no-index", probe], cwd=project_dir,
                         capture_output=True, text=True)
    if out.returncode != 0:
        return False
    source = out.stdout.split(":", 1)[0]
    return not os.path.isabs(source) and Path(source).name == ".gitignore"


def ignore_step(project_dir: Path) -> Step:
    """`.seldon/` ignored by the project's own `.gitignore`, appended when absent (SEL-020 Part A). Without it, the
    first dispatcher pass leaves `.seldon/` files untracked, and a dirty tree holds every task (c7)."""
    probe = SESSION_STATE_LINE + "x"
    if _tracked_ignore_rule(project_dir, probe):
        return Step("ignore", "ok", f"{SESSION_STATE_LINE} ignored")
    gi = project_dir / ".gitignore"
    old = gi.read_text(encoding="utf-8") if gi.is_file() else ""
    sep = "" if not old or old.endswith("\n") else "\n"
    gi.write_text(old + sep + ("\n" if old else "") + SESSION_STATE_COMMENT + "\n" + SESSION_STATE_LINE + "\n",
                  encoding="utf-8")
    return Step("ignore", "changed", f".gitignore + {SESSION_STATE_LINE}", [".gitignore"])


# ───────────────────────────────────────────────────────────────── seldon.yaml additions

def _load(project_dir: Path) -> tuple:
    text = (project_dir / "seldon.yaml").read_text(encoding="utf-8")
    return text, (yaml.safe_load(text) or {})


def _block_lines(values: dict, indent: str, comments: dict) -> list:
    lines = []
    for key, value in values.items():
        for c in comments.get(key, "").splitlines():
            lines.append(f"{indent}# {c}")
        dumped = yaml.safe_dump({key: value}, default_flow_style=False, sort_keys=False, width=10_000).rstrip("\n")
        lines.extend(indent + ln for ln in dumped.splitlines())
    return lines


ENVIRONMENT_COMMENT = (
    "The sibling repositories this project's runs depend on, read by `dispatch.stations.environment_ref`\n"
    "(hazbrief-mcp's and aacps-ai-policy's form, seldon SEL-016). Written by `seldon project new` (SEL-019) from\n"
    "the kit's `project_new.environment_packages`.")
SCAN_COMMENT = (
    "FC-02 (constitution 6.1): every handoff is run through the secret scanner before it is committed. Copied by\n"
    "`seldon project new` (SEL-019) from the kit's `desktop_commit.scan`, its program re-rooted at this project.")
ENV_REF_COMMENT = (
    "AD-037-R6 (a): the dispatcher's premise on every task, that no other project's dispatcher holds its lease on a\n"
    "repository this project's environment names (SEL-016's form; written by `seldon project new`, SEL-019).")
INTERPRETER_COMMENT = (
    "AD-037-R15: the interpreter this project's checks and dispatched sessions run under. Declared by `seldon\n"
    "project new --interpreter` (SEL-019) only after it imported seldon, since a check's `seldon` runs as\n"
    "`<interpreter> -m seldon`.")


def environment_text(project_dir: Path, cfg: dict, kit_dir: Path, dispatch: bool,
                     interpreter: str | None) -> tuple:
    """The `seldon.yaml` text with what the hand adoptions added after `adopt`, each only when absent:
    `environment.packages`, `desktop_commit.scan` and, with `dispatch`, `dispatch.stations.environment_ref` and the
    declared interpreter. Returns `(new_text or None, [added key paths])`."""
    text, config = _load(project_dir)
    added = []
    if "environment" not in config:
        text = A.insert_into_block(text, ("environment",),
                                   _block_lines({"packages": list(cfg["environment_packages"])}, "  ", {}))
        text = text.replace("\nenvironment:\n", "\n" + "\n".join(f"# {c}" for c in ENVIRONMENT_COMMENT.splitlines())
                            + "\nenvironment:\n", 1)
        added.append("environment.packages")
    scan = ((cfg["_kit"].get("desktop_commit") or {}).get("scan") or {})
    if scan and not ((config.get("desktop_commit") or {}).get("scan")):
        command = [str(c) for c in scan.get("command") or []]
        if command and "/" in command[0] and not os.path.isabs(command[0]):
            # Lexically, never resolve() on the program: a venv's `bin/python` is a symlink to a bare CPython that
            # runs outside the venv and cannot import the scanner (DESK-003; found again adopting factory, SEL-020).
            command[0] = os.path.relpath(os.path.normpath(Path(kit_dir).resolve() / command[0]),
                                         project_dir.resolve())
        text = A.insert_into_block(text, ("desktop_commit", "scan"),
                                   _block_lines({"roots": list(scan.get("roots") or []), "command": command},
                                                "    ", {"roots": SCAN_COMMENT}))
        added.append("desktop_commit.scan")
    if dispatch:
        stations = ((config.get("dispatch") or {}).get("stations") or {})
        values = {}
        if "environment_ref" not in stations:
            values["environment_ref"] = "seldon.yaml#environment.packages"
        if interpreter and "interpreter" not in stations:
            values["interpreter"] = interpreter
        if values:
            text = A.insert_into_block(text, ("dispatch", "stations"),
                                       _block_lines(values, "    ", {"environment_ref": ENV_REF_COMMENT,
                                                                     "interpreter": INTERPRETER_COMMENT}))
            added.extend(f"dispatch.stations.{k}" for k in values)
    if not added:
        return None, []
    try:
        yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ProjectNewError(f"the seldon.yaml `project new` would write does not parse; nothing written: {exc}")
    return text, added


def check_interpreter(interpreter: str) -> None:
    """AD-037-R15: a declared interpreter must import seldon, or every check's `seldon` fails under it (SEL-016
    left hazbrief's undeclared for exactly this reason)."""
    try:
        out = subprocess.run([interpreter, "-c", "import seldon"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProjectNewError(f"--interpreter {interpreter} cannot run: {exc}") from exc
    if out.returncode != 0:
        raise ProjectNewError(f"--interpreter {interpreter} cannot import seldon ({out.stderr.strip()[-200:]}); a "
                              f"check's `seldon` runs as `<interpreter> -m seldon` (AD-037-R15). Install seldon in "
                              f"it, or leave it undeclared as hazbrief does (SEL-016).")


def missing_siblings(project_dir: Path, packages: list) -> list:
    """Environment packages with no sibling directory: the premise would name a repository that is not there."""
    return [p for p in packages if not (Path(project_dir).resolve().parent / str(p)).is_dir()]


_ENABLED_RE = re.compile(r"^(  enabled:[ \t]*)false\b", re.MULTILINE)


def enabled_text(text: str) -> str | None:
    """`dispatch.enabled: false` flipped to true, the one line, comments kept; None when there is nothing to flip.
    Only the line inside the top-level `dispatch:` block is touched."""
    m = re.search(r"^dispatch:[ \t]*\n((?:[ \t]+.*\n|[ \t]*\n)*)", text, re.MULTILINE)
    if not m:
        return None
    body = m.group(1)
    flipped, n = _ENABLED_RE.subn(r"\1true", body, count=1)
    if not n:
        return None
    return text[:m.start(1)] + flipped + text[m.end(1):]


# ───────────────────────────────────────────────────────────────── the plist

def launchctl(*args: str) -> subprocess.CompletedProcess:
    """The one place `launchctl` runs (tests replace it)."""
    return subprocess.run(["launchctl", *args], capture_output=True, text=True)


def load_plist(plist_path: Path, label: str, launch_agents_dir: Path, uid: int | None = None) -> Step:
    """Install the job by SYMLINK (never a copy: the tracked plist stays the one the wrapper's interval check reads)
    and bootstrap it into the user's GUI domain, each only when not already so. A different file already at the
    link is refused, never overwritten."""
    uid = os.getuid() if uid is None else uid
    link = Path(launch_agents_dir).expanduser() / f"{label}.plist"
    acted = []
    if link.is_symlink() or link.exists():
        if not (link.is_symlink() and Path(os.readlink(link)).resolve() == Path(plist_path).resolve()):
            raise ProjectNewError(f"{link} exists and is not a symlink to {plist_path}; read it, remove it if it is "
                                  f"stale, and re-run")
    else:
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(Path(plist_path).resolve())
        acted.append(f"ln -s {plist_path} {link}")
    domain = f"gui/{uid}"
    if launchctl("print", f"{domain}/{label}").returncode != 0:
        out = launchctl("bootstrap", domain, str(link))
        if out.returncode != 0:
            raise ProjectNewError(f"launchctl bootstrap {domain} {link} exited {out.returncode}: "
                                  f"{(out.stderr or out.stdout).strip()}")
        acted.append(f"launchctl bootstrap {domain} {link}")
    if acted:
        return Step("plist", "changed", "; ".join(acted))
    return Step("plist", "ok", f"{label} already loaded from {link}")


# ───────────────────────────────────────────────────────────────── the graph

def graph_spec_name(graph: str) -> str:
    """squiddy's spec `name` (lowercase, digits, underscores) for a graph directory name: `aacps-policy-dm` ->
    `aacps_policy_dm`, as aacps wrote it."""
    name = re.sub(r"[^a-z0-9_]", "_", graph.lower())
    if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        raise ProjectNewError(f"--graph {graph!r} does not make a squiddy spec name (a letter, then letters, digits "
                              f"and underscores)")
    return name


def graph_step(project_dir: Path, graph: str, command: list) -> Step:
    """`graphs/<graph>/` initialized by `squiddy init` from its own `graph.yaml`. With no spec there, the skeleton
    is written and the step is refused until the operator fills it: the scope is his words, never guessed (squiddy
    DN-028 R-129). A graph squiddy already initialized is left alone."""
    gdir = project_dir / GRAPHS_DIR / graph
    spec = gdir / "graph.yaml"
    if (gdir / SQUIDDY_INIT_RECORD).is_file():
        return Step("graph", "ok", f"{gdir.relative_to(project_dir)} already initialized by squiddy")
    wrote = []
    if not spec.is_file():
        gdir.mkdir(parents=True, exist_ok=True)
        spec.write_text(GRAPH_SPEC_TEMPLATE.read_text(encoding="utf-8").replace("{name}", graph_spec_name(graph))
                        .replace("{graph}", graph), encoding="utf-8")
        wrote.append(str(spec.relative_to(project_dir)))
    rel = str(gdir.relative_to(project_dir))
    try:
        out = subprocess.run([*command, "init", rel, "--spec", str(spec.relative_to(project_dir))],
                             cwd=project_dir, capture_output=True, text=True)
    except OSError as exc:
        raise ProjectNewError(f"squiddy cannot run ({' '.join(command)}): {exc}; check the kit's "
                              f"project_new.squiddy_command") from exc
    if out.returncode != 0:
        why = (out.stderr or out.stdout).strip().splitlines()
        return Step("graph", "refused",
                    f"squiddy init refused: {why[-1].rstrip('.') if why else f'exit {out.returncode}'}. Fill "
                    f"{spec.relative_to(project_dir)} (title, description, scope.topic in the operator's words) and "
                    f"re-run `seldon project new`.", wrote)
    return Step("graph", "changed", f"squiddy init {rel} --spec {spec.relative_to(project_dir)}", wrote)
