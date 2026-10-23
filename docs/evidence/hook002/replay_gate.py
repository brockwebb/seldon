"""HOOK-002 Part C: replay the FIXED commit gate over every commit that landed since AD-036 ADDENDUM 06, from a worktree.

Every dispatched commit in a repository whose `prior_art:` block is a `ref` was refused by the hook from its worktree and
went in with `--no-verify` (SQ-019, SQ-029R, SQ-028R, SQ-022, SUITE-001 RESULTs). This measures what that bypass let
through: for each non-merge commit on `main` since ADDENDUM 06's commit, it runs `hooks.pre_commit` and then
`hooks.commit_msg` (with the commit's own message, so a `draft:` subject is honoured) as the hook would have run them
at that commit, from a LINKED WORKTREE, which is the path the defect broke.

Nothing is written to the repositories read. Each one is cloned with `git clone --shared` into a scratch directory laid
out as `~/GitHub` is (siblings), with `seldon` a symlink to the real seldon checkout so `ref: ../seldon/seldon.yaml`
names the real definition. Inside the clone a linked worktree is added under `.claude/worktrees/replay`. For each
commit the worktree's HEAD is detached at the commit's first parent and its index is set to the commit's tree
(`git read-tree`), so `git diff --cached` is exactly what the commit added or modified, as at the original commit.

    python -m docs.evidence.hook002.replay_gate <scratch dir> <since> <seldon primary checkout> <repo name>...

Each repo name is a sibling of the seldon primary checkout (`squiddy` is `<seldon>/../squiddy`). Run with `-m` from
this checkout so the code replayed is this checkout's seldon, not the pip-installed one.

Prints one JSON object per commit (sha, date, subject, staged count, findings) and a summary line; exits 0.

    python -m docs.evidence.hook002.replay_gate --control <scratch dir> <repo name>

runs the positive control on a repository already replayed; exits 0 when the gate refuses the planted note.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from seldon.core import hooks


def git(root: Path, *args: str) -> str:
    # GIT_* from an enclosing hook or session would aim these commands at another repository.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True,
                          env=env).stdout


def replay(scratch: Path, since: str, source: Path) -> list[dict]:
    clone = scratch / source.name
    if not clone.exists():
        git(scratch, "clone", "-q", "--shared", "--no-checkout", str(source), str(clone))
    wt = clone / ".claude" / "worktrees" / "replay"
    if not wt.exists():
        git(clone, "worktree", "add", "-q", "--detach", str(wt), "origin/main")
    rows = []
    shas = git(clone, "rev-list", "--no-merges", "--reverse", f"--since={since}", "origin/main").split()
    for sha in shas:
        parent = git(clone, "rev-parse", f"{sha}^").strip()
        git(wt, "checkout", "-q", "--detach", "--force", parent)
        git(wt, "read-tree", sha)
        message = git(clone, "log", "-1", "--format=%B", sha)
        try:
            pre, summary = hooks.pre_commit(wt)
            msg, drafts, _ = hooks.commit_msg(wt, message)
            findings, error = pre + [f for f in msg if f not in pre], None
        except hooks.HookError as exc:
            findings, drafts, summary, error = [], [], {}, str(exc)
        rows.append({"repo": source.name, "sha": sha[:10], "date": git(clone, "log", "-1", "--format=%as", sha).strip(),
                     "subject": message.splitlines()[0][:100], "staged": summary.get("staged"),
                     "findings": findings, "drafts_admitted": drafts, "error": error})
        print(json.dumps(rows[-1]), flush=True)
    git(wt, "checkout", "-q", "--detach", "--force", "origin/main")
    return rows


def control(scratch: Path, name: str) -> dict:
    """The positive control: the same replay worktree, a planted design note with no prior art staged on main's tip. A
    replay that cannot refuse this would report zero findings for any history, so its zero would mean nothing."""
    wt = scratch / name / ".claude" / "worktrees" / "replay"
    git(wt, "checkout", "-q", "--detach", "--force", "origin/main")
    planted = wt / "docs" / "design" / "DN-999_hook002_planted.md"
    planted.write_text("# DN-999 planted by HOOK-002's replay\n\nNo prior art section.\n")
    git(wt, "add", "--", str(planted.relative_to(wt)))
    try:
        findings, summary = hooks.pre_commit(wt)
    finally:
        git(wt, "reset", "-q", "--hard", "origin/main")
    row = {"control": name, "staged": summary.get("staged"), "checked": summary.get("checked"),
           "refused": bool(findings), "findings": findings}
    print(json.dumps(row), flush=True)
    return row


def main(argv: list[str]) -> int:
    if argv[1] == "--control":
        return 0 if control(Path(argv[2]), argv[3])["refused"] else 1
    scratch, since, seldon_dir = Path(argv[1]), argv[2], Path(argv[3]).resolve()
    repos = [seldon_dir.parent / name for name in argv[4:]]
    scratch.mkdir(parents=True, exist_ok=True)
    link = scratch / "seldon"
    if not link.exists():
        link.symlink_to(seldon_dir.resolve())
    rows = [r for repo in repos for r in replay(scratch, since, repo)]
    print(json.dumps({"summary": True, "commits": len(rows),
                      "with_findings": sum(1 for r in rows if r["findings"]),
                      "errors": sum(1 for r in rows if r["error"])}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
