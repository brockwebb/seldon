"""`seldon dispatch adopt`: a project opts into the standing dispatcher in one step (SEL-010R2 Part B, AD-038-R11).

Before this, adopting meant hand-writing the `dispatch:` block, a controls band reference, the wrapper's log caps, the
gitignore lines and a launchd plist (`docs/design/2026-09-15_standing_dispatcher.md`, "Adopting it in another
project"); hazbrief, the first project to try after seldon and squiddy, had none of them (SEL-010, 2026-10-25).

**Where each value comes from, first match wins:** the project's own `dispatch:` block (a key already there is never
rewritten); the answer given (an option, or a prompt); the kit's own block in seldon's `seldon.yaml` for the
machine-wide keys whose reasons are not the project's (poll interval, permission mode, lease, stop file, log dir, the
notifier, the stuck alarm), as SEL-005 copied them from ai-readiness-kg. What is the project's alone is asked: the
standing band reference (default: the kit's, re-rooted at the project), the launchd label and the branch.

**Text, not a YAML round trip.** Every `seldon.yaml` here is commented, and a `safe_dump` would drop every comment.
A missing block is appended as text; a partial one has its missing keys inserted at its end. The result is parsed
and validated by `load_dispatch_config` before anything is written, so a block that would refuse at the first pass
refuses here instead.

Pure except `write_adoption`, which writes exactly the paths it returns.
"""
from __future__ import annotations

import getpass
import os
import re
import subprocess
from pathlib import Path

import yaml

from seldon.core import dispatch as D

def _kit_dir() -> Path:
    """The kit: the PRIMARY checkout of the seldon tree this module runs from, whose `seldon.yaml` holds the block the
    machine-wide values are copied from and whose `scripts/jobs/seldon_dispatch.sh` is the wrapper every plist runs.
    The primary, not a worktree: the kit's relative references (`../squiddy/...`) resolve from it, and a plist must
    not name a wrapper inside a worktree the sweep will remove (`seldon.core.worktree.primary_checkout`)."""
    from seldon.core import worktree as WT
    here = Path(__file__).resolve().parents[2]
    try:
        return WT.primary_checkout(here)
    except WT.WorktreeError:
        return here


KIT_DIR = _kit_dir()
KIT_WRAPPER = "scripts/jobs/seldon_dispatch.sh"

#: Keys copied from the kit's block when the project has none of its own: their reasons are about the machine and
#: the CLI, not the project, and each is restated beside its value in the kit's `seldon.yaml`.
KIT_KEYS = ("poll_interval_s", "permission_mode", "stop_file", "lease_file", "log_dir", "notify",
            "notify_timeout_s", "stuck_after_passes", "stuck_after_passes_by_criterion")

#: The wrapper's log caps (`jobs.dispatch`), which it refuses to run without.
JOB_KEYS = ("log_max_line_chars", "log_max_run_bytes", "log_retention_days")

#: Where the plist is written in the project, as seldon's own is: tracked, and installed by symlink.
PLIST_DIR = "scripts/jobs"

#: The wrapper's own log, relative to the project (`seldon_dispatch.sh`: `$REPO/logs/seldon_dispatch.log`).
WRAPPER_LOG = "logs/seldon_dispatch.log"


class AdoptError(ValueError):
    """The adoption cannot be computed or would not validate."""


def kit_config(kit_dir: Path = KIT_DIR) -> dict:
    path = kit_dir / "seldon.yaml"
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise AdoptError(f"the kit's {path} cannot be read: {exc}") from exc


def rerooted_ref(ref: str, from_dir: Path, to_dir: Path) -> str:
    """A `<file>#<key path>` reference written relative to `from_dir`, rewritten relative to `to_dir`."""
    file, _, frag = ref.partition("#")
    target = (Path(from_dir) / file).resolve()
    return f"{os.path.relpath(target, Path(to_dir).resolve())}#{frag}"


def current_branch(project_dir: Path) -> str | None:
    out = subprocess.run(["git", "symbolic-ref", "--short", "HEAD"], cwd=project_dir, capture_output=True,
                         text=True)
    return out.stdout.strip() or None if out.returncode == 0 else None


def default_label(project_config: dict, project_dir: Path) -> str:
    """`com.<user>.<project slug>-dispatch`, the shape of seldon's and ai-readiness-kg's labels."""
    slug = ((project_config.get("project") or {}).get("slug") or Path(project_dir).resolve().name)
    return f"com.{getpass.getuser()}.{re.sub(r'[^A-Za-z0-9.-]', '-', slug)}-dispatch"


def questions(project_dir: Path, project_config: dict, kit: dict, kit_dir: Path = KIT_DIR) -> list:
    """What `adopt` asks, each with its default: `[(key, prompt, default)]`. A key the project already has is not
    asked."""
    have = (project_config.get("dispatch") or {})
    kit_block = kit.get("dispatch") or {}
    qs = []
    if "standing_band_ref" not in have:
        default = (rerooted_ref(kit_block["standing_band_ref"], kit_dir, project_dir)
                   if kit_block.get("standing_band_ref") else None)
        qs.append(("standing_band_ref", "standing band reference (<file>#<key path>, the machine's token cap)",
                   default))
    if "branch" not in have:
        qs.append(("branch", "branch a pass may dispatch on", current_branch(project_dir) or "main"))
    if "launchd_label" not in have:
        qs.append(("launchd_label", "launchd label", default_label(project_config, project_dir)))
    return qs


def plan(project_dir: Path, project_config: dict, answers: dict, kit: dict) -> dict:
    """The keys to add: `{dispatch: {...}, jobs_dispatch: {...}}`, each only what the project lacks."""
    have = project_config.get("dispatch") or {}
    kit_block = kit.get("dispatch") or {}
    add = {}
    if "enabled" not in have:
        # The adoption doc's rule: a new block starts off, so nothing already queued launches on the first load.
        add["enabled"] = False
    for key in ("branch", "standing_band_ref"):
        if key not in have:
            if not answers.get(key):
                raise AdoptError(f"dispatch.{key} has no value: give it as an option or at the prompt")
            add[key] = answers[key]
    for key in KIT_KEYS:
        if key not in have and key in kit_block:
            add[key] = kit_block[key]
    if "launchd_label" not in have and answers.get("launchd_label"):
        add["launchd_label"] = answers["launchd_label"]
    if "max_parallel" not in have:
        add["max_parallel"] = D.MAX_PARALLEL_DEFAULT
    if "candidacy_headers" not in have:
        add["candidacy_headers"] = list(D.MINIMUM_HEADERS)
    if "ooda_grace_s" not in have:
        add["ooda_grace_s"] = answers.get("ooda_grace_s", D.OODA_GRACE_S_DEFAULT)
    if "gate_command" not in have and answers.get("gate_command"):
        add["gate_command"] = answers["gate_command"]
    have_jobs = ((project_config.get("jobs") or {}).get("dispatch") or {})
    kit_jobs = ((kit.get("jobs") or {}).get("dispatch") or {})
    jobs = {k: kit_jobs[k] for k in JOB_KEYS if k not in have_jobs and k in kit_jobs}
    return {"dispatch": add, "jobs_dispatch": jobs}


#: One comment per key the block is written with, so the file an operator reads carries each reason (the rule every
#: `dispatch:` block here keeps). Keys copied from the kit point at the kit's block, where their full reasons are.
_COMMENTS = {
    "enabled": "THE KILL SWITCH, read every pass. Written false: set true once the plist is loaded.",
    "branch": "The branch a pass may dispatch on; any other branch fails c7.",
    "standing_band_ref": "The machine's token cap, by reference (DN-006 section 5); c4 holds a task's Spend to it.",
    "launchd_label": "The launchd job; `seldon go` reports `dispatch: on` only while it is loaded.",
    "max_parallel": "One task at a time (AD-037-R9 holds every project at 1 until it opts in by a register record).",
    "candidacy_headers": "AD-038-R11: the headers a task file must carry; Spend and Network are the kit-wide minimum.",
    "ooda_grace_s": "AD-038-R17: the OODA knowledge source's session timeout in seconds (it holds nothing); 0 is off.",
    "gate_command": "The re-gate run in the task's worktree when main changed a file it changed (AD-034 decision 3).",
}


def render_lines(values: dict, indent: str) -> list:
    """`key: value` lines (block-style YAML), each after its comment."""
    lines = []
    for key, value in values.items():
        why = _COMMENTS.get(key, "Copied from the kit's dispatch block (seldon/seldon.yaml), where its reason is.")
        lines.append(f"{indent}# {why}")
        dumped = yaml.safe_dump({key: value}, default_flow_style=False, sort_keys=False, width=10_000).rstrip("\n")
        lines.extend(indent + ln for ln in dumped.splitlines())
    return lines


_TOP_KEY_RE = re.compile(r"^(?P<key>[A-Za-z_][\w-]*)\s*:")


def insert_into_block(text: str, path: tuple, lines: list) -> str:
    """`lines` appended to the block at `path` (one or two keys deep), created at the end of the file or of its
    parent when absent. Block-style YAML only: a block ends at the next line indented no deeper than its key."""
    if not lines:
        return text
    src = text.splitlines()
    depth = len(path) - 1

    def find(key, start, stop, level):
        pat = re.compile(r"^" + " " * (2 * level) + re.escape(key) + r"\s*:")
        deeper = " " * (2 * level + 1)
        for i in range(start, stop):
            if pat.match(src[i]):
                end = i + 1
                while end < stop and (not src[end].strip() or src[end].startswith(deeper)
                                      or src[end].lstrip().startswith("#")):
                    end += 1
                # Trailing blank lines, and comments no deeper than the key, belong to whatever follows.
                while end > i + 1 and (not src[end - 1].strip() or not src[end - 1].startswith(deeper)):
                    end -= 1
                return i, end
        return None

    top = find(path[0], 0, len(src), 0)
    if top is None:
        head = [f"{path[0]}:"] + ([f"  {path[1]}:"] if depth else [])
        tail = ([""] if src and src[-1].strip() else [])
        return "\n".join(src + tail + head + lines) + "\n"
    if depth == 0:
        _, end = top
        return "\n".join(src[:end] + lines + src[end:]) + "\n"
    inner = find(path[1], top[0] + 1, top[1], 1)
    if inner is None:
        return "\n".join(src[:top[1]] + [f"  {path[1]}:"] + lines + src[top[1]:]) + "\n"
    return "\n".join(src[:inner[1]] + lines + src[inner[1]:]) + "\n"


def render_plist(label: str, project_dir: Path, plist_path: Path, interval: int, kit_dir: Path = KIT_DIR) -> str:
    """The launchd job, seldon's own shape (`scripts/jobs/com.brock.seldon-dispatch.plist`): the kit's wrapper with
    the project and this plist as arguments, so the wrapper's StartInterval check reads this file."""
    project = Path(project_dir).resolve()
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!--
  {label}: launchd job for the standing dispatcher in {project}.
  Written by `seldon dispatch adopt` (SEL-010R2, AD-038-R11); the shape and every reason are seldon's own job,
  {kit_dir}/scripts/jobs/com.brock.seldon-dispatch.plist.

  StartInterval is seldon.yaml `dispatch.poll_interval_s`; the wrapper refuses when the two differ.
  RunAtLoad false: loading the job must not fire a pass. AbandonProcessGroup true: a dispatched session outlives
  the pass that launched it (AD-034 premise 5).

  Install by SYMLINK, never a copy:
    ln -s {plist_path} ~/Library/LaunchAgents/{label}.plist
    launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/{label}.plist
-->
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>{kit_dir / KIT_WRAPPER}</string>
        <string>{project}</string>
        <string>{plist_path}</string>
    </array>
    <key>StartInterval</key>
    <integer>{interval}</integer>
    <key>RunAtLoad</key>
    <false/>
    <key>AbandonProcessGroup</key>
    <true/>
    <key>WorkingDirectory</key>
    <string>{project}</string>
</dict>
</plist>
"""


def ignore_lines(project_dir: Path, block: dict) -> list:
    """The runtime paths the dispatcher writes that git must ignore and does not yet: the lease, the STOP file, the
    log directory, the wrapper's log and the CLI's worktrees (c11 refuses every launch while those are not ignored)."""
    want = [block["lease_file"], block["stop_file"], block["log_dir"].rstrip("/") + "/", WRAPPER_LOG,
            D.CLI_WORKTREE_DIR + "/"]
    missing = []
    for rel in want:
        probe = rel.rstrip("/") + ("/x" if rel.endswith("/") else "")
        out = subprocess.run(["git", "check-ignore", "-q", "--no-index", probe], cwd=project_dir,
                             capture_output=True)
        if out.returncode != 0:
            missing.append(rel)
    return missing


def adoption(project_dir: Path, answers: dict, kit_dir: Path = KIT_DIR) -> dict:
    """Everything `adopt` would write, computed and validated, writing nothing:
    `{seldon_yaml, plist_path, plist, gitignore_add, added, block}`."""
    project_dir = Path(project_dir).resolve()
    path = project_dir / "seldon.yaml"
    if not path.is_file():
        raise AdoptError(f"{path} does not exist: run `seldon init` in the project first")
    text = path.read_text(encoding="utf-8")
    config = yaml.safe_load(text) or {}
    kit = kit_config(kit_dir)
    added = plan(project_dir, config, answers, kit)
    new_text = insert_into_block(text, ("dispatch",), render_lines(added["dispatch"], "  "))
    new_text = insert_into_block(new_text, ("jobs", "dispatch"), render_lines(added["jobs_dispatch"], "    "))
    try:
        new_config = yaml.safe_load(new_text) or {}
    except yaml.YAMLError as exc:
        raise AdoptError(f"the seldon.yaml adopt would write does not parse; nothing written: {exc}") from exc
    try:
        block = D.load_dispatch_config(project_dir, new_config)
        D.resolve_standing_band(project_dir, block["standing_band_ref"])
    except (D.DispatchConfigError, OSError, KeyError, ValueError) as exc:
        raise AdoptError(f"the block adopt would write does not validate: {exc}") from exc
    lacking = sorted(set(JOB_KEYS) - set(((new_config.get("jobs") or {}).get("dispatch") or {})))
    if lacking:
        raise AdoptError(f"jobs.dispatch would lack {lacking}; the wrapper refuses to run without them")
    label = block.get("launchd_label")
    plist_path = project_dir / PLIST_DIR / f"{label}.plist" if label else None
    return {"seldon_yaml": new_text if new_text != text else None, "added": added, "block": block,
            "plist_path": plist_path,
            "plist": (render_plist(label, project_dir, plist_path, block["poll_interval_s"], kit_dir)
                      if plist_path and not plist_path.exists() else None),
            "gitignore_add": ignore_lines(project_dir, block)}


def write_adoption(project_dir: Path, plan_: dict) -> list:
    """Write what `adoption` computed; returns the paths written, relative to the project."""
    project_dir = Path(project_dir).resolve()
    written = []
    if plan_["seldon_yaml"] is not None:
        (project_dir / "seldon.yaml").write_text(plan_["seldon_yaml"], encoding="utf-8")
        written.append("seldon.yaml")
    if plan_["plist"] is not None:
        plan_["plist_path"].parent.mkdir(parents=True, exist_ok=True)
        plan_["plist_path"].write_text(plan_["plist"], encoding="utf-8")
        written.append(str(plan_["plist_path"].relative_to(project_dir)))
    if plan_["gitignore_add"]:
        gi = project_dir / ".gitignore"
        old = gi.read_text(encoding="utf-8") if gi.is_file() else ""
        lines = ["", "# The standing dispatcher's runtime state (seldon dispatch adopt, AD-038-R11)."] + plan_[
            "gitignore_add"]
        gi.write_text(old.rstrip("\n") + "\n" + "\n".join(lines) + "\n" if old else "\n".join(lines[1:]) + "\n",
                      encoding="utf-8")
        written.append(".gitignore")
    return written
