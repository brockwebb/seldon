"""The commit point of AD-036-R4 as a git hook (HOOK-001; AD-036 ADDENDUM 02).

    seldon hooks install       # per repository: core.hooksPath -> the tracked .githooks/
    seldon hooks status        # is it installed here, and what did it replace
    seldon hooks pre-commit    # what .githooks/pre-commit runs; never typed by hand

**Why this exists.** AD-036-R4 says `seldon verify` (pre-commit) refuses a design note without
receipts. PA-001 found that no pre-commit hook ran in any repository: `core.hooksPath` named a
`~/Documents/GitHub/...` path that the June 2026 move to `~/GitHub` left dead, and arnold's
ADR-012 hooks, copied into `.git/hooks`, were lost with it. So the "commit gate" was a prose rule
an agent might follow, which is the failure AD-036 exists to end (its section 2: instructions
decay inside an agent's session; enforcement is refusal, not reminder).

**Installed by path, never copied.** The hook lives in a TRACKED `.githooks/` directory and
`core.hooksPath` is set to that relative path in the repository's own config (never `--global`,
never `--system`). Git resolves a relative hooks path against the top of the working tree, so a
fresh worktree runs the hook its own checkout carries, and a moved clone keeps a working hook.
The interpreter is recorded in the same local config (`seldon.python`), because a hook run by a
launchd-started session may not have seldon on PATH; it is machine state, so it never enters a
tracked file.

**The staged bytes decide.** The hook judges the index, not the working tree: the staged copy of
each governed file, the staged `seldon.yaml`, the staged governed ledger (where verdicts live)
and the staged decision register. An unstaged edit can neither pass nor fail a commit. This is
the property the pre-commit framework (pre-commit.com) buys by stashing unstaged changes; here
the blobs are read from the index directly, so the working tree is never touched.

**What it checks.** The Tier A checks whose subject is a staged governed file and which the
index alone can decide:
- `Prior art` (AD-036-R4): each staged gated design note outside the baseline has a passing
  verdict for its staged bytes in the staged governed ledger.
- `Decision register` (AD-033-R2, AD-036 section 6.1): no `ruling_label_unparsed` label in a
  staged note added after the register's baseline; every label it carries has a record in the
  staged register; and, when register files are staged, the staged register's chain verifies.
The graph-wide Tier A checks (file hashes, ontology, references, binding constraints,
unregistered files, governed-doc ingest) are not properties of one staged file, need Neo4j or
another repository's pipeline, and stay with `seldon verify --strict`.

**The one way past** is `git commit --no-verify`. `bypassed()` finds what it let through: a
non-merge commit, at or after the one that added `.githooks/pre-commit`, that carried gated
design-note bytes with no passing verdict in the ledger. `seldon verify` reports each as
`hook_bypassed`.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import yaml

#: The tracked hooks directory, relative to the top of the working tree.
HOOKS_DIR = ".githooks"
#: The hook this module installs.
PRE_COMMIT = "pre-commit"
#: Local git config key holding the interpreter the hook runs seldon with.
PYTHON_KEY = "seldon.python"
#: The bypass finding's name in `seldon verify`.
BYPASSED = "hook_bypassed"
#: A register record's top-level id line, as `seldon decision` writes it.
_ID_LINE = re.compile(rb"^id: ['\"]?([^'\"\n]+?)['\"]?\s*$", re.M)

#: What `.githooks/pre-commit` contains. Tracked in every repository; `install` writes it when it
#: is absent and refuses to overwrite a different one.
HOOK_SCRIPT = """#!/bin/sh
# Seldon's commit gate (AD-036-R4; HOOK-001, AD-036 ADDENDUM 02). Tracked and run in place:
# `seldon hooks install` points core.hooksPath at this directory; nothing is copied into .git/.
# It judges the STAGED governed files only. `git commit --no-verify` is the one way past it, and
# `seldon verify` reports a design note committed that way as hook_bypassed.
py="$(git config --get seldon.python)"
if [ -n "$py" ] && [ -x "$py" ]; then
  exec "$py" -m seldon hooks pre-commit
fi
if command -v seldon >/dev/null 2>&1; then
  exec seldon hooks pre-commit
fi
echo "seldon commit gate: no interpreter: git config seldon.python is unset or not executable" >&2
echo "and seldon is not on PATH. Run \\`seldon hooks install\\` in this repository." >&2
exit 1
"""


class HookError(RuntimeError):
    """A git or configuration problem the hook cannot judge around. Fatal; it refuses."""


def _git(repo: Path, *args: str, check: bool = True, input_bytes: bytes | None = None,
         text: bool = True) -> subprocess.CompletedProcess:
    """Run git in `repo`. The environment is inherited on purpose: inside a hook git sets
    GIT_INDEX_FILE (a `git commit -a` or `git commit <path>` stages into a temporary index), and
    the hook must read THAT index."""
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, input=input_bytes,
                       text=text if input_bytes is None else False)
    if check and r.returncode != 0:
        err = r.stderr if isinstance(r.stderr, str) else r.stderr.decode("utf-8", "replace")
        raise HookError(f"git {' '.join(args)} failed in {repo}: {err.strip()}")
    return r


def toplevel(path: Path) -> Path:
    """The top of the working tree containing `path`."""
    return Path(_git(Path(path), "rev-parse", "--show-toplevel").stdout.strip())


# ---------------------------------------------------------------------------------- install

@dataclass
class InstallResult:
    repo: str
    old_hooks_path: Optional[str]
    hooks_path: str
    python: str
    wrote_hook: bool
    changed: bool


def hook_file(repo: Path) -> Path:
    return Path(repo) / HOOKS_DIR / PRE_COMMIT


def install(repo: Path, python: str | None = None) -> InstallResult:
    """Point this repository's own `core.hooksPath` at the tracked `.githooks/`.

    Writes `.githooks/pre-commit` when it is absent (the caller commits it; it is tracked).
    Refuses when a different file is there: someone's hook is never overwritten silently.
    Records the interpreter in local config. Idempotent.

    Raises:
        HookError: Not a git repository, a different pre-commit already tracked, or a git
            command failing.
    """
    repo = toplevel(Path(repo))
    python = python or sys.executable
    hf = hook_file(repo)
    wrote = False
    if hf.exists():
        if hf.read_text(encoding="utf-8") != HOOK_SCRIPT:
            raise HookError(f"{hf} exists and is not seldon's hook; merge it by hand (seldon's "
                            f"text is seldon.core.hooks.HOOK_SCRIPT) and re-run")
    else:
        hf.parent.mkdir(parents=True, exist_ok=True)
        hf.write_text(HOOK_SCRIPT, encoding="utf-8")
        wrote = True
    if not os.access(hf, os.X_OK):
        hf.chmod(hf.stat().st_mode | 0o111)
    old = _git(repo, "config", "--local", "--get", "core.hooksPath", check=False).stdout.strip()
    old_py = _git(repo, "config", "--local", "--get", PYTHON_KEY, check=False).stdout.strip()
    if old != HOOKS_DIR:
        _git(repo, "config", "--local", "core.hooksPath", HOOKS_DIR)
    if old_py != python:
        _git(repo, "config", "--local", PYTHON_KEY, python)
    return InstallResult(repo=str(repo), old_hooks_path=old or None, hooks_path=HOOKS_DIR,
                         python=python, wrote_hook=wrote,
                         changed=wrote or old != HOOKS_DIR or old_py != python)


def status(repo: Path) -> dict:
    """{installed, problems, hooks_path, effective, python}. `installed` is True only when git
    will run the tracked seldon hook in this checkout, with an interpreter that exists."""
    repo = toplevel(Path(repo))
    hp = _git(repo, "config", "--get", "core.hooksPath", check=False).stdout.strip()
    scope = _git(repo, "config", "--show-scope", "--get", "core.hooksPath",
                 check=False).stdout.split("\t")[0].strip()
    py = _git(repo, "config", "--get", PYTHON_KEY, check=False).stdout.strip()
    effective = _git(repo, "rev-parse", "--git-path", "hooks").stdout.strip()
    problems = []
    if hp != HOOKS_DIR:
        problems.append(f"core.hooksPath is {hp or 'unset'!r}, not {HOOKS_DIR!r}")
    elif scope and scope not in ("local", "worktree"):
        problems.append(f"core.hooksPath is set in {scope} config; it belongs to the repository")
    hf = hook_file(repo)
    if not hf.is_file():
        problems.append(f"{HOOKS_DIR}/{PRE_COMMIT} is missing from this checkout")
    else:
        if hf.read_text(encoding="utf-8") != HOOK_SCRIPT:
            problems.append(f"{HOOKS_DIR}/{PRE_COMMIT} is not seldon's hook")
        if not os.access(hf, os.X_OK):
            problems.append(f"{HOOKS_DIR}/{PRE_COMMIT} is not executable")
        tracked = _git(repo, "ls-files", "--error-unmatch", f"{HOOKS_DIR}/{PRE_COMMIT}",
                       check=False).returncode == 0
        if not tracked:
            problems.append(f"{HOOKS_DIR}/{PRE_COMMIT} is not tracked (commit it)")
    if not py:
        if shutil.which("seldon") is None:
            problems.append(f"no interpreter: {PYTHON_KEY} unset and seldon not on PATH")
    elif not os.access(py, os.X_OK):
        problems.append(f"{PYTHON_KEY} {py!r} is not executable")
    return {"installed": not problems, "problems": problems, "hooks_path": hp or None,
            "scope": scope or None, "effective": effective, "python": py or None}


def ensure_installed(repo: Path) -> dict:
    """The dispatcher's launch-path call: install when the tracked hook is present but git is
    not pointed at it. {ok, changed, error}. Never writes a tracked file: a checkout without
    `.githooks/pre-commit` is reported, not repaired, because writing it would dirty the tree a
    dispatched session must open clean."""
    try:
        repo = toplevel(Path(repo))
        if not hook_file(repo).is_file():
            return {"ok": False, "changed": False,
                    "error": f"{HOOKS_DIR}/{PRE_COMMIT} is not in this checkout; a dispatched "
                             f"session would commit without the gate (HOOK-001)"}
        st = status(repo)
        if st["installed"]:
            return {"ok": True, "changed": False, "error": None}
        res = install(repo)
        st = status(repo)
        return {"ok": st["installed"], "changed": res.changed,
                "error": "; ".join(st["problems"]) or None}
    except HookError as exc:
        return {"ok": False, "changed": False, "error": str(exc)}


# ------------------------------------------------------------------------------- the index

class Index:
    """Blobs from git's index (`:path`) or from a commit (`<rev>:path`), read through one
    `git cat-file --batch` per lookup set."""

    def __init__(self, repo: Path, rev: str = ""):
        self.repo = Path(repo)
        self.rev = rev            # "" is the index
        self._cache: dict[str, Optional[bytes]] = {}

    def spec(self, rel: str) -> str:
        return f"{self.rev}:{rel}"

    def blobs(self, rels: Iterable[str]) -> dict[str, Optional[bytes]]:
        want = [r for r in dict.fromkeys(rels) if r not in self._cache]
        if want:
            r = _git(self.repo, "cat-file", "--batch",
                     input_bytes=("\n".join(self.spec(x) for x in want) + "\n").encode())
            out, pos = r.stdout, 0
            for rel in want:
                nl = out.index(b"\n", pos)
                header = out[pos:nl].decode("utf-8", "replace")
                pos = nl + 1
                if header.endswith(" missing") or header.endswith(" ambiguous"):
                    self._cache[rel] = None
                    continue
                size = int(header.rsplit(" ", 1)[1])
                self._cache[rel] = out[pos:pos + size]
                pos += size + 1
        return {r: self._cache[r] for r in rels}

    def blob(self, rel: str) -> Optional[bytes]:
        return self.blobs([rel])[rel]

    def text(self, rel: str) -> Optional[str]:
        b = self.blob(rel)
        return None if b is None else b.decode("utf-8", "replace")

    def files_under(self, prefix: str) -> list[str]:
        """Paths in the index (or the commit) under a directory."""
        prefix = prefix.rstrip("/") + "/"
        if self.rev:
            out = _git(self.repo, "ls-tree", "-r", "--name-only", "-z", self.rev, "--",
                       prefix).stdout
        else:
            out = _git(self.repo, "ls-files", "-z", "--", prefix).stdout
        return sorted(p for p in out.split("\0") if p)


def staged_paths(repo: Path) -> list[str]:
    """Paths the commit adds or modifies (renames read as a delete plus an add)."""
    out = _git(repo, "diff", "--cached", "--name-only", "-z", "--no-renames",
               "--diff-filter=ACM").stdout
    return sorted(p for p in out.split("\0") if p)


def _tracked(repo: Path, rel: str) -> bool:
    return _git(repo, "ls-files", "--error-unmatch", "--", rel, check=False).returncode == 0


def text_of(repo: Path, idx: Index, rel: str) -> Optional[str]:
    """A file as the commit will hold it: the staged blob when the path is tracked; the working
    tree's copy when it is not tracked at all (an untracked file is never part of any commit, so
    it is configuration of the checkout, like the environment); None when neither exists."""
    if _tracked(repo, rel) or idx.rev:
        return idx.text(rel)
    p = Path(repo) / rel
    return p.read_text(encoding="utf-8") if p.is_file() else None


def staged_config(repo: Path, idx: Index) -> dict:
    """seldon.yaml as the commit will hold it. {} when the repository has none."""
    raw = text_of(repo, idx, "seldon.yaml")
    if raw is None:
        return {}
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise HookError("seldon.yaml (staged) is not a mapping")
    return data


# ---------------------------------------------------------------------------------- checks

def _rel_to(repo: Path, p: Path) -> str:
    return Path(p).resolve().relative_to(Path(repo).resolve()).as_posix()


def prior_art_findings(repo: Path, config: dict, staged: list[str], idx: Index) -> list[str]:
    """AD-036-R4 over the staged gated notes, judged against the staged ledger."""
    from seldon.core import prior_art as pa

    if not isinstance(config.get("prior_art"), dict):
        return []
    try:
        s = pa.settings(repo, config)
    except pa.PriorArtError as exc:
        return [f"Prior art: {exc}"]
    gated = [p for p in staged if pa.is_gated(s, p)]
    if not gated:
        return []
    base_text = text_of(repo, idx, _rel_to(repo, s.baseline))
    if base_text is None:
        return [f"Prior art: the AD-036 baseline list {s.baseline} is not in the commit"]
    base = pa.baseline_from_text(base_text)
    gated = [p for p in gated if p not in base]
    if not gated:
        return []
    ledger = pa.governed_ledger(repo, config)
    have: dict = {}
    if ledger is not None:
        raw = text_of(repo, idx, _rel_to(repo, ledger))
        if raw is not None:
            have = pa.verdicts_from_lines(raw.splitlines(), f"{_rel_to(repo, ledger)} (staged)")
    blobs = idx.blobs(gated)
    out = []
    for rel in gated:
        row = pa.judge(rel, pa._sha(blobs[rel]), have)
        if not row["ok"]:
            why = row["why"]
            if why.startswith("no prior-art verdict"):
                why += "; then stage the governed ledger with the note"
            out.append(f"Prior art: {rel}: {why}")
    return out


def decision_findings(repo: Path, config: dict, staged: list[str], idx: Index) -> list[str]:
    """AD-033-R2 and AD-036 section 6.1 over the staged design notes and register files."""
    from seldon.core import decisions as dr

    try:
        s = dr.settings(repo, config)
    except dr.RegisterError as exc:
        return [f"Decision register: {exc}"]
    if s is None:
        return []
    out = []
    reg_prefix = s.register_dir.rstrip("/") + "/"
    notes = [p for p in staged if dr.is_design_note(s, p)]
    if s.baseline_commit:
        notes = [p for p in notes if not dr._in_tree(s.root, s.baseline_commit, p)]
    labels: dict[str, str] = {}
    for rel in notes:
        text = idx.text(rel) or ""
        for _, line, label in dr.unparsed_labels_in(s, rel, text):
            out.append(f"Decision register: {dr.UNPARSED}: {rel}:{line} {label} is in a heading "
                       f"or bold position and no `decisions.design_notes` pattern captures it "
                       f"(AD-036 section 6.1)")
        if s.baseline_commit:
            for qid in dr.labeled_ids_in(s, rel, text):
                labels.setdefault(qid, rel)
    reg_files = [p for p in idx.files_under(s.register_dir) if p.endswith(".yaml")]
    if labels:
        # The `id:` line of each record file, read by pattern rather than parsed: the command
        # writes canonical YAML with `id` at the top level, and squiddy's register is ~900 files.
        ids = {m.group(1).decode() for raw in idx.blobs(reg_files).values()
               if raw and (m := _ID_LINE.search(raw))}
        for qid, rel in sorted(labels.items()):
            if qid not in ids:
                out.append(f"Decision register: {rel} labels {qid}, which has no record in the "
                           f"staged register; write it with `seldon decision` and stage it "
                           f"(AD-033-R2)")
    if any(p.startswith(reg_prefix) for p in staged):
        out.extend(f"Decision register: {x}" for x in _staged_register_verify(repo, s, idx,
                                                                              reg_files))
    return out


def _staged_register_verify(repo: Path, s, idx: Index, reg_files: list[str]) -> list[str]:
    """The register's chain check (`Register.verify`) over the STAGED register files."""
    from seldon.core import decisions as dr

    with tempfile.TemporaryDirectory(prefix="seldon-hook-") as tmp:
        root = Path(tmp)
        for rel, raw in idx.blobs(reg_files).items():
            dest = root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw or b"")
        return dr.Register(s.repository, root, s.register_dir).verify()


def pre_commit(repo: Path) -> tuple[list[str], dict]:
    """Every finding that refuses this commit, and a summary of what was judged.

    Raises:
        HookError: When the index or the configuration cannot be read. The hook refuses then too.
    """
    started = time.monotonic()
    repo = toplevel(Path(repo))
    staged = staged_paths(repo)
    idx = Index(repo)
    summary = {"staged": len(staged), "checked": [], "seconds": None}
    findings: list[str] = []
    if staged:
        config = staged_config(repo, idx)
        if config:
            findings += prior_art_findings(repo, config, staged, idx)
            findings += decision_findings(repo, config, staged, idx)
            summary["checked"] = [k for k in ("prior_art", "decisions") if config.get(k)]
    summary["seconds"] = round(time.monotonic() - started, 3)
    return findings, summary


REFUSAL_FOOTER = ("Refused by the commit gate (AD-036-R4; HOOK-001). The staged files decide; "
                  "fix them and stage again. `git commit --no-verify` bypasses the gate, and "
                  "`seldon verify` reports a design note committed that way as hook_bypassed.")


# ----------------------------------------------------------------------------- the bypass

def anchor(repo: Path, rev: str = "HEAD") -> Optional[str]:
    """The first commit reachable from `rev` that added `.githooks/pre-commit`: the moment the
    gate existed in this history. None when it never did."""
    out = _git(repo, "log", "--diff-filter=A", "--format=%H", "--reverse", rev, "--",
               f"{HOOKS_DIR}/{PRE_COMMIT}", check=False).stdout.split()
    return out[0] if out else None


def bypassed(repo: Path, config: dict, rev: str = "HEAD") -> Optional[list[dict]]:
    """Commits the gate should have refused. None when the gate is not configured (no
    `prior_art:` block) or never existed in this history.

    A row per (commit, note): a non-merge commit at or after the anchor that added or modified a
    gated design note outside the baseline whose bytes in that commit have no passing verdict in
    the governed ledger as `rev` holds it. `healed` says whether the note as `rev` holds it now
    passes. Merge commits are not walked: the commits they bring were judged on their branch.
    """
    from seldon.core import prior_art as pa

    repo = toplevel(Path(repo))
    if not isinstance(config.get("prior_art"), dict):
        return None
    a = anchor(repo, rev)
    if a is None:
        return None
    s = pa.settings(repo, config)
    at = Index(repo, rev)
    base_text = at.text(_rel_to(repo, s.baseline))
    base = pa.baseline_from_text(base_text) if base_text is not None else set()
    ledger = pa.governed_ledger(repo, config)
    have: dict = {}
    if ledger is not None:
        lrel = _rel_to(repo, ledger)
        raw = at.text(lrel)
        if raw is None and not _tracked(repo, lrel) and ledger.is_file():
            raw = ledger.read_text(encoding="utf-8")      # an untracked ledger is never in git
        if raw is not None:
            have = pa.verdicts_from_lines(raw.splitlines(), f"{_rel_to(repo, ledger)}@{rev}")
    parents = _git(repo, "rev-list", "--parents", "-n", "1", a).stdout.split()
    walk = [rev, "--not", parents[1]] if len(parents) > 1 else [rev]
    log = _git(repo, "log", "--no-merges", "--format=%x00%H", "--name-only",
               "--diff-filter=AM", "--no-renames", *walk, "--", s.design_dir).stdout
    rows = []
    for chunk in log.split("\0"):
        lines = [x for x in chunk.strip().splitlines() if x]
        if not lines:
            continue
        commit, files = lines[0], lines[1:]
        for rel in files:
            if not pa.is_gated(s, rel) or rel in base:
                continue
            blob = Index(repo, commit).blob(rel)
            if blob is None:
                continue
            row = pa.judge(rel, pa._sha(blob), have)
            if row["ok"]:
                continue
            now = at.blob(rel)
            healed = now is not None and pa.judge(rel, pa._sha(now), have)["ok"]
            rows.append({"commit": commit, "note": rel, "sha256": row["sha256"],
                         "why": row["why"], "healed": healed})
    return rows
