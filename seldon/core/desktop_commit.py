"""The tool that writes a governed file commits it (DESK-001).

    seldon commit-governed <path> [<path> ...] [--project DIR]   # CLI
    seldon_commit_governed(project_dir, paths)                     # MCP, for Desktop

**The condition.** A Desktop session writes design notes, addenda and task files through the
Filesystem MCP. It has no shell and so no commit path. `seldon cc register` commits the task file
and its governing note (d6a1f467, SEL-006) and nothing else, so every other note Desktop wrote left
the tree dirty, the dispatcher refused every candidate on c7 every five minutes, and the operator
found out hours later: 2026-09-22 (DN-008, 3 hours), 2026-10-12 (MODEL-003, 36 hours, Issue
7e70aeb0), 2026-10-14 (DN-014 ADDENDUM 01, 14 hours). AD-036-R11 already rules that "an automatic
writer commits what it writes"; this is the commit path for the writer that had none.

**What it does.** Commits exactly the named paths, through the hooks (never `--no-verify`), with a
message `desktop: <kind>: <basename>`. It refuses, before staging anything:
  - a path outside the configured roots (`desktop_commit.roots`; default `DEFAULT_ROOTS`);
  - a path that escapes the project, does not exist, is gitignored, or has nothing to commit;
  - a file under a scanned root (`desktop_commit.scan`) the secret scanner flags (FC-02: each
    handoff is scanned before it is committed; seldon's `.gitignore`).
A hook refusal is returned with the hook's text verbatim, and everything this call staged is
unstaged again. It never runs `git add -A` and never commits a path it was not given: the commit
is pathspec-limited (`dispatch.commit_paths`), so another session's staged or dirty files stay
exactly as they were.

**A ruling's record commits with its note, and only with it (DESK-002).** The register files
(`decisions.register_dir`, `*.yaml`) and the rendered `REGISTER.md` are outside the roots: AD-033-R2
makes `seldon decision` their one writer. But the commit gate refuses a design note whose label has
no record in the staged register, and a Desktop session writes that record itself
(`seldon_decision_accept`) while writing the note. So a register file is accepted in the SAME call as
a design note one of whose labels it carries an event about, and `REGISTER.md` with such a file;
alone, or beside a note that does not label it, each still refuses as `outside_roots` (Issue 5c689098).

**Drafts.** A gated design note with no passing prior-art verdict for its bytes is committed with
`draft:` in the subject (`desktop: draft: design: <name>`), which the commit-msg hook admits
(AD-036 ADDENDUM 05). Verification is not run here: it costs library searches, and registration
runs it for the notes a task names (SEL-006). The return says which notes went in as drafts and the
command that clears each.
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from seldon.core import dispatch as D

#: The roots a Desktop write may be committed from, and the kind each names in the message. The
#: task's list (DESK-001 Part A step 1): what Desktop writes, and nothing a session's code lives in.
DEFAULT_ROOTS = {
    "docs/design/": "design",
    "cc_tasks/": "task",
    "handoffs/": "handoff",
    "issues/": "issue",
    "ontology/": "ontology",
}

# Refusal reasons: the first token of a refusal, so callers and tests branch on one vocabulary.
OUTSIDE_ROOTS = "outside_roots"
OUTSIDE_PROJECT = "outside_project"
NOT_FOUND = "not_found"
IGNORED = "ignored"
UNCHANGED = "unchanged"
SECRET_FOUND = "secret_found"
SCAN_FAILED = "scan_failed"
HOOK_REFUSED = "hook_refused"
NO_PATHS = "no_paths"

#: The kind a register file or REGISTER.md is named by in the commit message (DESK-002).
REGISTER_KIND = "register"

#: The trailer `squiddy.secret_scan` prints as its last line (`scanned N file(s); exit 1`). Exit 1
#: is a finding only with it: a scanner that never started (an import error, a missing module)
#: also exits 1, and that is SCAN_FAILED, not SECRET_FOUND (DESK-003, Issue cf57b8e5).
SCAN_FOUND_TRAILER = re.compile(r"^scanned \d+ file\(s\); exit 1$", re.MULTILINE)


class CommitConfigError(ValueError):
    """`desktop_commit:` in seldon.yaml does not parse."""


@dataclass
class Settings:
    roots: dict                                   # {"docs/design/": "design", ...}
    scan_roots: list = field(default_factory=list)
    scan_command: list = field(default_factory=list)


def settings(project_dir: Path, config: dict) -> Settings:
    """The `desktop_commit:` block, with defaults. Raises CommitConfigError on a malformed one."""
    block = (config or {}).get("desktop_commit") or {}
    if not isinstance(block, dict):
        raise CommitConfigError("desktop_commit must be a mapping")
    roots = block.get("roots", DEFAULT_ROOTS)
    if not isinstance(roots, dict) or not roots or not all(
            isinstance(k, str) and isinstance(v, str) and v for k, v in roots.items()):
        raise CommitConfigError("desktop_commit.roots must map a directory to a kind name")
    roots = {k.rstrip("/") + "/": v for k, v in roots.items()}
    scan = block.get("scan") or {}
    if not isinstance(scan, dict):
        raise CommitConfigError("desktop_commit.scan must be a mapping {roots, command}")
    scan_roots = [r.rstrip("/") + "/" for r in scan.get("roots") or []]
    command = scan.get("command") or []
    if scan_roots and (not isinstance(command, list) or not command):
        raise CommitConfigError("desktop_commit.scan.command must be a non-empty list when "
                                "scan.roots is set")
    # A relative program path is relative to the project (seldon.yaml's own convention for
    # sibling repositories, e.g. `../squiddy/...`); a bare name is looked up on PATH. Absolutized
    # lexically, never with resolve(): a venv's `bin/python` is a symlink, and following it lands
    # on the bare interpreter, which runs outside the venv (DESK-003).
    if command and ("/" in command[0]) and not Path(command[0]).is_absolute():
        command = [os.path.normpath(Path(project_dir) / command[0])] + list(command[1:])
    return Settings(roots=roots, scan_roots=scan_roots, scan_command=[str(c) for c in command])


@dataclass
class Outcome:
    committed: bool
    sha: Optional[str] = None
    message: Optional[str] = None
    paths: list = field(default_factory=list)
    drafts: list = field(default_factory=list)      # [{"note", "why"}]
    refusal: Optional[str] = None                   # reason token
    detail: str = ""                                # human text; the hook's verbatim on HOOK_REFUSED

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def _refuse(reason: str, detail: str, paths=()) -> Outcome:
    return Outcome(committed=False, refusal=reason, detail=f"{reason}: {detail}", paths=list(paths))


def _normalize(project_dir: Path, raw: str) -> Optional[str]:
    """The project-relative posix path, or None when it escapes the project."""
    p = Path(raw).expanduser()
    full = p if p.is_absolute() else project_dir / p
    try:
        return full.resolve().relative_to(project_dir).as_posix()
    except ValueError:
        return None


def kind_of(rel: str, s: Settings) -> Optional[str]:
    """The kind name of the root `rel` is under, longest root first; None outside every root."""
    for root in sorted(s.roots, key=len, reverse=True):
        if rel.startswith(root):
            return s.roots[root]
    return None


def message_for(rels: list, s: Settings, draft: bool) -> str:
    """`desktop: <kind>: <basename>[, <basename>]; <kind>: ...`, `draft: ` after `desktop: `."""
    groups: dict = {}
    for rel in rels:
        groups.setdefault(kind_of(rel, s) or REGISTER_KIND, []).append(Path(rel).name)
    body = "; ".join(f"{k}: {', '.join(names)}" for k, names in groups.items())
    return f"desktop: {'draft: ' if draft else ''}{body}"


def unverified_notes(project_dir: Path, config: dict, rels: list) -> list[dict]:
    """The gated design notes among `rels` with no passing prior-art verdict for their bytes."""
    from seldon.core import prior_art as pa

    if not isinstance(config.get("prior_art"), dict):
        return []
    s = pa.settings(project_dir, config)
    notes = [r for r in rels if pa.is_gated(s, r)]
    return [{"note": r["note"], "why": r["why"]}
            for r in pa.gate_status(project_dir, config, notes) if not r["ok"]]


def _scan(project_dir: Path, s: Settings, rels: list) -> Optional[Outcome]:
    targets = [r for r in rels if any(r.startswith(root) for root in s.scan_roots)]
    if not targets:
        return None
    try:
        r = subprocess.run([*s.scan_command, *targets], cwd=project_dir, capture_output=True,
                           text=True)
    except OSError as exc:
        return _refuse(SCAN_FAILED, f"the secret scan could not run ({' '.join(s.scan_command)}): "
                                    f"{exc}", targets)
    if r.returncode == 1 and SCAN_FOUND_TRAILER.search(r.stdout or ""):
        return _refuse(SECRET_FOUND, f"the secret scan flagged {', '.join(targets)}; nothing was "
                                     f"staged: {(r.stdout or r.stderr).strip()}", targets)
    if r.returncode != 0:
        return _refuse(SCAN_FAILED, f"the secret scan exited {r.returncode} without a finding: "
                                    f"{(r.stderr or r.stdout).strip()}", targets)
    return None


def _register_refusal(project_dir: Path, config: dict, rels: list, register_rels: list) -> Optional[Outcome]:
    """None when every register path in the call answers a label of a design note in the call."""
    from seldon.core import decisions as dr

    def refuse(rel: str, why: str) -> Outcome:
        return _refuse(OUTSIDE_ROOTS, f"{rel}: {why}; a register file or REGISTER.md commits through this "
                                      f"tool only with the design note whose label it answers, in the same "
                                      f"call (DESK-002, AD-033-R2)", [rel])
    try:
        ds = dr.settings(project_dir, config)
    except dr.RegisterError as exc:
        return _refuse("config_invalid", str(exc))
    labels: dict = {}
    for rel in rels:
        if ds is not None and dr.is_design_note(ds, rel):
            for qid in dr.labeled_ids_in(ds, rel, (project_dir / rel).read_text(encoding="utf-8")):
                labels.setdefault(qid, rel)
    records = [r for r in register_rels if r.endswith(".yaml")]
    for rel in records:
        try:
            qid = (yaml.safe_load((project_dir / rel).read_text(encoding="utf-8")) or {}).get("id")
        except yaml.YAMLError as exc:
            return refuse(rel, f"not YAML ({exc})")
        if qid not in labels:
            return refuse(rel, f"it is about {qid}, which no design note in this call labels"
                               + (f" (they label {', '.join(sorted(labels))})" if labels else ""))
    for rel in register_rels:
        if rel not in records and not records:
            return refuse(rel, "no register record in this call")
    return None


def _register_path(project_dir: Path, config: dict, rel: str) -> bool:
    """`rel` is a file of this project's register, or its rendered REGISTER.md."""
    from seldon.core import decisions as dr

    try:
        ds = dr.settings(project_dir, config)
    except dr.RegisterError:
        return False
    if ds is None:
        return False
    prefix = ds.register_dir.rstrip("/") + "/"
    return rel == ds.rendered or (rel.startswith(prefix) and rel.endswith(".yaml")
                                  and "/" not in rel[len(prefix):])


def _unstage(project_dir: Path, rels: list) -> None:
    """Put the index back for exactly these paths after a refused commit."""
    if D.git(project_dir, "rev-parse", "--verify", "-q", "HEAD").returncode == 0:
        D.git(project_dir, "reset", "-q", "--", *rels)
    else:
        D.git(project_dir, "rm", "--cached", "-q", "--ignore-unmatch", "--", *rels)


def commit_governed(project_dir: Path, paths: list, config: Optional[dict] = None) -> Outcome:
    """Commit exactly `paths` through the hooks. See the module docstring for every refusal.

    Args:
        project_dir: The project (repository top level) the paths belong to.
        paths: Project-relative or absolute paths of files under the configured roots.
        config: Parsed seldon.yaml; read from `project_dir` when None.

    Returns:
        An `Outcome`. `sha` is the full commit sha when `committed`.
    """
    project_dir = Path(project_dir).expanduser().resolve()
    if config is None:
        from seldon.config import load_project_config
        config = load_project_config(project_dir)
    try:
        s = settings(project_dir, config)
    except CommitConfigError as exc:
        return _refuse("config_invalid", str(exc))
    if not paths:
        return _refuse(NO_PATHS, "name at least one path")
    rels, register_rels = [], []
    for raw in paths:
        rel = _normalize(project_dir, str(raw))
        if rel is None:
            return _refuse(OUTSIDE_PROJECT, f"{raw} is not inside {project_dir}", [raw])
        if kind_of(rel, s) is None and _register_path(project_dir, config, rel):
            register_rels.append(rel)      # judged below, against the notes of this call
        elif kind_of(rel, s) is None:
            return _refuse(OUTSIDE_ROOTS, f"{rel} is under none of {', '.join(s.roots)}; this tool "
                                          f"commits only what a Desktop session writes", [rel])
        if not (project_dir / rel).is_file():
            return _refuse(NOT_FOUND, f"{rel} is not a file", [rel])
        if D.git(project_dir, "check-ignore", "-q", "--", rel).returncode == 0:
            return _refuse(IGNORED, f"{rel} is gitignored; the project has said it does not track it",
                           [rel])
        if not D.git(project_dir, "status", "--porcelain", "--untracked-files=all", "--",
                     rel).stdout.strip():
            return _refuse(UNCHANGED, f"{rel} has nothing to commit (git holds these bytes)", [rel])
        rels.append(rel)
    rels = list(dict.fromkeys(rels))
    if register_rels:
        refused = _register_refusal(project_dir, config, rels, register_rels)
        if refused is not None:
            return refused
    scanned = _scan(project_dir, s, rels)
    if scanned is not None:
        return scanned
    drafts = unverified_notes(project_dir, config, rels)
    message = message_for(rels, s, draft=bool(drafts))
    out = D.commit_paths(project_dir, rels, message)
    if not out.get("committed"):
        _unstage(project_dir, rels)
        return Outcome(committed=False, refusal=HOOK_REFUSED, paths=rels, drafts=drafts,
                       message=message,
                       detail=f"{HOOK_REFUSED}: {out.get('reason')}: {out.get('stderr', '')}".rstrip())
    sha = D.git(project_dir, "rev-parse", "HEAD").stdout.strip()
    return Outcome(committed=True, sha=sha, message=message, paths=rels, drafts=drafts)


def render(outcome: Outcome) -> str:
    """The text the CLI prints and the MCP tool returns."""
    if not outcome.committed:
        return f"REFUSED {outcome.detail}"
    lines = [f"committed {outcome.sha[:12]} {outcome.message}"]
    for d in outcome.drafts:
        lines.append(f"  draft: {d['note']}: {d['why']}. A task governed by it is held at "
                     f"registration and dispatch until it passes (AD-036 ADDENDUM 05).")
    return "\n".join(lines)
