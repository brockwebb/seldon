"""SEL-042 Part C: which replayed commit of HB-189's branch restores the three reconciled event lines on a rebase.

Clones hazbrief-mcp (shared, read-only for the source) into /tmp, makes a main that moved by one appended event
line (what the round's journal commit does), then replays the branch's commits one at a time with `git cherry-pick`
(the rebase's own replay, with the repository's merge=union attribute) and counts each id after each commit.
"""
import json
import subprocess
import sys
from pathlib import Path

SRC = "/Users/brock/GitHub/hazbrief-mcp"
DST = Path("/tmp/sel042/hzclone")
BRANCH = "worktree-witty-finding-whisper"
IDS = ["30730309", "b1ab2033", "dfa7ae1e"]
STORE = "seldon_events.jsonl"


def git(*a, check=True):
    r = subprocess.run(["git", "-C", str(DST), *a], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f"git {' '.join(a)}: {r.stderr}")
    return r


def counts():
    out = []
    text = (DST / STORE).read_text(encoding="utf-8", errors="replace")
    for i in IDS:
        out.append(sum(1 for ln in text.splitlines() if f'"event_id": "{i}' in ln))
    return out


def main():
    if not DST.exists():
        subprocess.run(["git", "clone", "-q", "--shared", "--no-checkout", SRC, str(DST)], check=True)
        git("fetch", "-q", "origin", f"{BRANCH}:{BRANCH}")
    git("config", "user.email", "sel042@example.invalid")
    git("config", "user.name", "sel042 replay")
    base = git("merge-base", "origin/main", BRANCH).stdout.strip()
    revs = git("rev-list", "--reverse", f"{base}..{BRANCH}").stdout.split()
    print("base", base[:8], "commits", len(revs))
    git("checkout", "-q", "-f", "-B", "replay", base)
    # The round's journal commit: one new line appended to main's store.
    with (DST / STORE).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"event_id": "00000000-sel042-journal", "event_type": "stop_gate", "payload": {}}) + "\n")
    git("add", STORE)
    git("commit", "-q", "-m", "journal line (the round's record commit)")
    print("new main", counts())
    for r in revs:
        before = counts()
        subj = git("log", "-1", "--format=%s", r).stdout.strip()[:90]
        touches = STORE in git("show", "--name-only", "--format=", r).stdout.split()
        pick = git("cherry-pick", "--allow-empty", "--keep-redundant-commits", r, check=False)
        if pick.returncode != 0:
            print("CONFLICT at", r[:8], pick.stderr[-300:])
            git("cherry-pick", "--abort", check=False)
            return
        after = counts()
        flag = " <-- RESTORES" if sum(after) > sum(before) else (" <-- drops" if sum(after) < sum(before) else "")
        if touches or flag:
            print(r[:8], before, "->", after, "store" if touches else "", subj, flag)
    print("final", counts())


if __name__ == "__main__":
    sys.exit(main())
