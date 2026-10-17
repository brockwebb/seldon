"""A long-lived process records what it loaded and re-checks it before acting (SEL-006 Part B).

squiddy DN-046 R-202 ("a process records what it loaded and re-checks it") applied to the MCP
servers. Claude Desktop starts `seldon-mcp` once and keeps it for days, while the checkout under it
moves: on 2026-10-14 MODEL-003 merged a new `models/registry.yaml` format, and the running server,
holding the code from before the merge, answered `seldon_cc_register` with a registry parse error
that named nothing about its cause (Issue fed23c36). The same holds for `squiddy serve`, which
imports squiddy.

**What is recorded at start:** the checkout's HEAD, the tree id at HEAD of each code directory the
process imported (`seldon/` for seldon-mcp), and the sha256 of each configuration file it reads
(`models/registry.yaml`, `seldon.yaml`). **Before every tool call** they are read again; on any
difference the call is refused with `server_stale`, and the message says to restart the server.

**Why the code tree and not HEAD itself.** The MCP tools commit their own event-store lines
(`_commit_append`) and registration commits its task file, so HEAD moves on nearly every write a
Desktop session makes. A HEAD comparison would refuse the second call of every session, which is a
gate that teaches its user to ignore it. The tree id of the imported package changes exactly when
the code the process would run has changed, which is what R-202 is about. The message still names
both HEADs, so the operator sees what moved.

This is the stale-code check every hot-reloading server makes by file identity (gunicorn's
`--reload`, Django's autoreloader, watchfiles), except that a refusal replaces the reload: an MCP
server cannot restart itself under Claude Desktop, so it says so instead of answering from old code.
"""
from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

#: The refusal's reason, the first token of its message.
STALE = "server_stale"


@dataclass(frozen=True)
class Loaded:
    """What a process loaded: a checkout's HEAD, its code trees and its configuration files."""
    name: str
    repo: Path
    head: str
    trees: dict = field(default_factory=dict)      # {code dir relative to repo: tree id at HEAD}
    files: dict = field(default_factory=dict)      # {absolute path: sha256 or None when absent}
    at: str = ""


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def _sha(path: Path) -> Optional[str]:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def _read(repo: Path, code_dirs: Iterable[str]) -> tuple[Optional[str], dict]:
    dirs = list(code_dirs)
    r = _git(repo, "rev-parse", "HEAD", *[f"HEAD:{d}" for d in dirs])
    if r.returncode != 0:
        return None, {}
    ids = r.stdout.split()
    return ids[0], dict(zip(dirs, ids[1:]))


def capture(name: str, repo: Path, code_dirs: Iterable[str], files: Iterable[Path]) -> Optional[Loaded]:
    """Record what the process loads now. None when `repo` is not a git checkout (an installed,
    non-editable package has no checkout to move under it, so there is nothing to re-check)."""
    repo = Path(repo).resolve()
    head, trees = _read(repo, code_dirs)
    if head is None:
        return None
    return Loaded(name=name, repo=repo, head=head, trees=trees,
                  files={str(Path(f).resolve()): _sha(Path(f)) for f in files},
                  at=datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z"))


#: The advice the message ends with when the caller names none.
RESTART_ADVICE = "Restart the MCP server (restart Claude Desktop)."


def stale(loaded: Optional[Loaded], advice: str = RESTART_ADVICE) -> Optional[str]:
    """None when the checkout still holds what was loaded; otherwise the `server_stale` message.

    `advice` ends the message. seldon-mcp passes its own since AD-038-R3: its mutating tools run the
    checkout's code in a fresh process, so only its read-only tools are guarded and none asks for a restart."""
    if loaded is None:
        return None
    head, trees = _read(loaded.repo, loaded.trees)
    moved = [d for d, t in loaded.trees.items() if trees.get(d) != t]
    changed = [Path(f).name for f, sha in loaded.files.items() if _sha(Path(f)) != sha]
    if head is not None and not moved and not changed:
        return None
    now = (head or "unknown")[:7]
    what = ", ".join([f"{d}/" for d in moved] + changed) or "the checkout"
    return (f"{STALE}: {loaded.name} loaded {loaded.head[:7]} on {loaded.at}; the checkout is at {now} "
            f"({what} changed since). {advice}")
