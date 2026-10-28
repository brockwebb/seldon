"""A project's hash-chained pass ledger has one sequencer, main (squiddy DN-052 R-237; squiddy SQ-096).

squiddy's `kit/ledger/passes.jsonl` chains each line to the one before (`prev_line_sha256`). On 2026-10-27 SQ-021's
branch and main had each appended after the same line 23, so every union of the two broke the chain, and nothing
refused the fork before a person met it in a rebase (squiddy SQ-021M2 RESULT, first execution). R-237 adopts RFC 6962's
rule (Certificate Transparency: one sequencer extends an append-only Merkle log; a second extension is a fork to refuse,
never to merge): a checkout's ledger must be main's lines followed by lines chained onto main's last.

**The rule lives in the project, seldon only runs it.** A project declares, in seldon.yaml:

    pass_ledger:
      path: kit/ledger/passes.jsonl          # the tracked ledger, relative to the repository
      check: [-m, squiddy.kitpass, check]    # arguments to seldon's interpreter

`seldon verify` runs `<interpreter> <check...> --checkout <project>` and the pre-commit hook runs the same with
`--ledger <file>` holding the STAGED blob, when the commit stages `path` (a rebase or merge conflict resolved to the
branch's side is exactly such a commit). PYTHONPATH is the checkout, so the checkout's own kit judges its own ledger
and a worktree, which has no virtual environment, can run it. Exit 0 passes, 1 is the refusal (its stderr names the
first forked line, `pass_ledger_forked`), anything else is a check that could not run, which fails too: a gate that
cannot judge does not pass.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

#: The seldon.yaml block.
CONFIG_KEY = "pass_ledger"
#: The refusal's name, as the project's check prints it (squiddy kitpass.FORKED).
FORKED = "pass_ledger_forked"
#: Seconds a check may run. The check is two `git` reads and a line comparison (under a second on squiddy's
#: 25-line ledger, measured 2026-10-28); a hung git is a failure, not a wait.
TIMEOUT_S = 60


class PassLedgerError(Exception):
    """The declaration is malformed, or the check could not be run."""


def declared(config: dict) -> Optional[dict]:
    """The validated `pass_ledger:` block, or None when the project declares none."""
    block = (config or {}).get(CONFIG_KEY)
    if block is None:
        return None
    if not isinstance(block, dict):
        raise PassLedgerError(f"seldon.yaml {CONFIG_KEY} must be a mapping, got {type(block).__name__}")
    extra = sorted(set(block) - {"path", "check"})
    if extra:
        raise PassLedgerError(f"seldon.yaml {CONFIG_KEY} has unknown key(s) {extra}; known: ['check', 'path']")
    path, check = block.get("path"), block.get("check")
    if not isinstance(path, str) or not path.strip():
        raise PassLedgerError(f"seldon.yaml {CONFIG_KEY}.path must name the tracked ledger, got {path!r}")
    if not (isinstance(check, list) and check and all(isinstance(a, str) for a in check)):
        raise PassLedgerError(f"seldon.yaml {CONFIG_KEY}.check must be a non-empty list of arguments to the "
                              f"interpreter, got {check!r}")
    return {"path": path, "check": list(check)}


def run(project_dir: Path, decl: dict, ledger: Optional[Path] = None) -> tuple[int, str]:
    """Run the project's check. `(returncode, output)`; raises PassLedgerError when it cannot start or times out."""
    project_dir = Path(project_dir).resolve()
    argv = [sys.executable, *decl["check"], "--checkout", str(project_dir)]
    if ledger is not None:
        argv += ["--ledger", str(ledger)]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(project_dir) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    try:
        r = subprocess.run(argv, cwd=str(project_dir), env=env, capture_output=True, text=True, timeout=TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PassLedgerError(f"{' '.join(argv)}: {type(exc).__name__}: {exc}") from exc
    return r.returncode, "\n".join(s.strip() for s in (r.stdout, r.stderr) if s.strip())


def staged_findings(repo: Path, config: dict, staged: list[str], blob) -> list[str]:
    """The pre-commit half: when the commit stages the declared ledger, judge the staged blob. `blob(rel)` returns
    the staged bytes (hooks.Index.blob)."""
    decl = declared(config)
    if decl is None or decl["path"] not in staged:
        return []
    data = blob(decl["path"])
    if data is None:
        return []
    with tempfile.TemporaryDirectory(prefix="seldon-pass-ledger-") as td:
        f = Path(td) / "staged.jsonl"
        f.write_bytes(data)
        try:
            rc, out = run(repo, decl, ledger=f)
        except PassLedgerError as exc:
            return [f"{decl['path']}: the pass-ledger check could not run: {exc}"]
    if rc == 0:
        return []
    # the check names the refusal itself; exit 1 without the name is an uncaught exception, not a fork
    head = "" if rc == 1 and FORKED in out else f"the pass-ledger check failed (exit {rc}): "
    return [f"{decl['path']} (staged): {head}{out}"[:2000]]
