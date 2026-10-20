"""STD-001R Part B: make cc_tasks/ and handoffs/ tracked in every repository under ~/GitHub (AD-039).

    python scripts/std001/sweep.py --dry-run     # rewrite, list, scan, then restore every .gitignore
    python scripts/std001/sweep.py --apply       # rewrite, scan, commit by path; append the evidence

Per repository (the task's 29; the 5 already correct are not touched):

1. Rewrite `.gitignore`: delete the lines that ignore either directory (and a now-redundant
   `!handoffs/.gitkeep`), replace the stale comments listed in EDITS, and put the AD-039 stanza
   where the first deleted line was (else at the end). watermarks-remover's deny-by-default list
   gets the two directories allowed instead. Then `git check-ignore` must pass, or the repo stops.
2. Scan every file now untracked under the two directories with `squiddy.secret_scan`. A file over
   SIZE_LIMIT is not added (listed instead). On a pass, add exactly those files and the
   `.gitignore` (plus EXTRA files) and commit through the repo's hooks; on a flag, commit the
   `.gitignore` alone and record file and line, never the value.
3. Append one row per repository to docs/evidence/std001/sweep.jsonl.

Nothing is pushed: the dispatched session's instructions forbid a push; the RESULT lists the repos.

**Status 2026-10-19:** `--dry-run` ran in STD-001R's session (docs/evidence/std001/sweep_dryrun.jsonl);
`--apply` was refused twice by the session's auto-mode classifier ("Modify Shared Resources"), so it is
the operator's step: run `python scripts/std001/sweep.py --apply` from seldon's checkout. It appends
docs/evidence/std001/sweep.jsonl, which that commit then carries.
Paths are committed by name (`git commit -- <paths>` semantics via an explicit add list), so another
session's dirt in the same repository is never swept in.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

WT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WT))
from seldon.core import tracked_dirs as TD  # noqa: E402

GITHUB = Path("/Users/brock/GitHub")
SCANNER = [str(GITHUB / "squiddy/.venv/bin/python"), "-m", "squiddy.secret_scan"]
EVIDENCE = WT / "docs/evidence/std001/sweep.jsonl"
BACKUP = Path("/tmp/std001r/gitignore_backup")
#: GitHub warns on a file over 50 MiB and refuses one over 100 MiB ("About large files on
#: GitHub", docs.github.com). A record file that large is a blob, not a record: list it, add nothing.
SIZE_LIMIT = 50 * 1024 * 1024
#: Files passed to one scanner call (argv length).
SCAN_BATCH = 200
COMMIT_MSG = "std-001: track cc_tasks/ and handoffs/ (AD-039)"

#: The task's 29 (survey 2026-10-19), less none.
REPOS = ["ai-readiness-kg", "hazbrief-mcp", "icsp_notebook", "resume-redactor",
         "CoolSpot", "TickBiteRisk", "ai-workflow-design", "appraisal-agent", "book_responsible_ai",
         "census-mcp-server", "central_library", "federal-survey-concept-mapper",
         "ms-teams-attendance-reporter", "sas_graph_code_conversion", "usai-harness", "wintermute",
         "watermarks-remover",
         "brock_projects", "survey-dag-extractor", "usai-api-tester",
         "AI-Pulse", "ai-demos", "census-web-concept-inventory", "dixie", "measuring-ai-economy",
         "practical-ai-ml-labs", "trustgraph-fork", "webdesktop", "claude-skills"]

#: Lines that ignore a record directory, deleted wherever they appear.
DELETE = {"cc_tasks/", "handoffs/", "/cc_tasks/", "/handoffs/", "cc_tasks", "handoffs",
          "!handoffs/.gitkeep", "!cc_tasks/.gitkeep"}

#: Stale comments, by repository and exact text: replacement (None deletes the line).
EDITS = {
    "CoolSpot": {"# session-local project management": None},
    "TickBiteRisk": {
        "# Seldon — ephemeral session state and AI task/handoff specs.":
            "# Seldon — ephemeral session state.",
        "# seldon.yaml (project config) and seldon_events.jsonl (graph source-of-truth":
            "# seldon.yaml (project config) and seldon_events.jsonl (graph source-of-truth",
        "# event log) ARE tracked; only local session state and CC task/handoff docs":
            "# event log) ARE tracked; only local session state is ignored. cc_tasks/ and handoffs/",
        "# (per engineering-standards CLAUDE.md §6) are ignored.":
            "# are tracked (AD-039, which withdrew engineering-standards CLAUDE.md §6's rule).",
    },
    "ai-workflow-design": {"# Session artifacts (not for public repo)":
                           "# Audit artifacts (not for public repo)"},
    "book_responsible_ai": {"# Session artifacts (not for public repo)":
                            "# Audit artifacts (not for public repo)"},
    "resume-redactor": {"# Working notes, per engineering standards": None},
    "survey-dag-extractor": {"# handoff folder": None},
    "usai-harness": {"# Working directories": None},
}

#: Repositories whose `.gitignore` already satisfies AD-039 in the working tree (another session's
#: edit, uncommitted): commit it as it stands.
KEEP_GITIGNORE = {"hazbrief-mcp"}

#: Extra stale-text fixes committed with the repo's `.gitignore`: (path, old line, new line).
EXTRA = {
    "hazbrief-mcp": [
        ("CLAUDE.md", "- `cc_tasks/` — tracked. `handoffs/` and `logs/` — gitignored.",
         "- `cc_tasks/` and `handoffs/` — tracked (AD-039; a handoff is secret-scanned before it is "
         "committed). `logs/` — gitignored."),
        ("BOOTSTRAP.md", "4. Create the directories DN-001 names: `docs/stylebook/`, `packs/`, "
         "`fixtures/scenarios/`, `cc_tasks/`, `handoffs/`. Gitignore `handoffs/` and `logs/`; track `cc_tasks/`.",
         "4. Create the directories DN-001 names: `docs/stylebook/`, `packs/`, `fixtures/scenarios/`, "
         "`cc_tasks/`, `handoffs/`. Track `cc_tasks/` and `handoffs/` (AD-039; only `*.json`/`*.jsonl` under "
         "them are ignored); gitignore `logs/`."),
    ],
}


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    r = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} in {repo.name} exited {r.returncode}: {r.stderr.strip()}")
    return r


def rewrite(name: str, text: str) -> str:
    """The `.gitignore` text with AD-039 applied."""
    lines = text.splitlines()
    if name == "watermarks-remover":
        add = [TD.STANZA_COMMENT, "!/cc_tasks/", "!/handoffs/", *TD.BLOB_LINES]
        have = {ln.strip() for ln in lines}
        return "\n".join(lines + [ln for ln in add if ln not in have]) + "\n"
    edits = EDITS.get(name, {})
    out, at = [], None
    for ln in lines:
        s = ln.strip()
        if s in DELETE:
            if at is None:
                at = len(out)
            continue
        if ln in edits:
            if edits[ln] is not None:
                out.append(edits[ln])
            continue
        out.append(ln)
    have = {ln.strip() for ln in out}
    stanza = [ln for ln in TD.stanza().splitlines() if ln not in have]
    if all(b in have for b in TD.BLOB_LINES):
        stanza = []
    if at is None:
        if out and out[-1].strip():
            stanza = [""] + stanza if stanza else []
        out += stanza
    else:
        out[at:at] = stanza
    return "\n".join(out) + "\n"


def untracked(repo: Path) -> list[str]:
    dirs = [d for d in TD.TRACKED_DIRS if (repo / d).is_dir()]
    if not dirs:  # an empty pathspec would list the whole repository
        return []
    r = git(repo, "ls-files", "--others", "--exclude-standard", "-z", "--", *dirs)
    return sorted(p for p in r.stdout.split("\0") if p)


def scan(repo: Path, files: list[str]) -> tuple[str, list[str]]:
    """`(pass|flag|error, hit lines)`; a hit is `path:line pattern`, never a value."""
    hits, status = [], "pass"
    for i in range(0, len(files), SCAN_BATCH):
        r = subprocess.run(SCANNER + files[i:i + SCAN_BATCH], cwd=repo, capture_output=True, text=True)
        if r.returncode == 1:
            status = "flag"
            hits += [ln for ln in r.stdout.splitlines() if ln.strip()]
        elif r.returncode != 0:
            return "error", [f"scanner exit {r.returncode}: {r.stderr.strip()[:300]}"]
    return status, hits


def one(name: str, apply: bool) -> dict:
    repo = GITHUB / name
    row = {"repo": name, "ts": datetime.now(timezone.utc).isoformat(), "mode": "apply" if apply else "dry-run"}
    gi = repo / ".gitignore"
    has_dirs = any((repo / d).is_dir() for d in TD.TRACKED_DIRS)
    if not gi.exists() and not has_dirs:
        return {**row, "action": "none", "why": "no .gitignore and neither directory (task Part B step 1)"}
    branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if branch != "main":
        return {**row, "action": "skipped", "why": f"checked out on {branch}, not main; no branch switch"}
    dirty_gi = bool(git(repo, "status", "--porcelain", "--", ".gitignore").stdout.strip())
    if dirty_gi and name not in KEEP_GITIGNORE:
        return {**row, "action": "skipped", "why": ".gitignore has another writer's uncommitted edit"}
    before = gi.read_text() if gi.exists() else ""
    BACKUP.mkdir(parents=True, exist_ok=True)
    (BACKUP / f"{name}.gitignore").write_text(before)
    after = before if name in KEEP_GITIGNORE else rewrite(name, before)
    gi.write_text(after)
    try:
        still = TD.ignored(repo)
        if still:
            raise RuntimeError(f"still ignored after rewrite: {[TD.describe(f) for f in still]}")
        files = untracked(repo)
        sizes = {f: (repo / f).stat().st_size for f in files}
        big = [f for f in files if sizes[f] > SIZE_LIMIT]
        small = [f for f in files if f not in big]
        status, hits = scan(repo, small) if small else ("pass", [])
        row.update(gitignore_changed=after != before, untracked=len(files), oversize=big, scan=status,
                   scan_hits=hits)
        add_files = small if status == "pass" else []
        row.update(files_tracked=len(add_files), bytes=sum(sizes[f] for f in add_files))
        extra = []
        for rel, old, new in EXTRA.get(name, []):
            p = repo / rel
            t = p.read_text()
            if old in t:
                if apply:
                    p.write_text(t.replace(old, new, 1))
                extra.append(rel)
            elif new not in t:
                raise RuntimeError(f"{rel}: stale line not found and fix not present")
        row["extra"] = extra
        if not apply:
            row["files"] = add_files[:50]
            gi.write_text(before)
            return {**row, "action": "dry-run"}
        paths = [".gitignore", *add_files, *extra] if (after != before or dirty_gi) else [*add_files, *extra]
        if not paths:
            return {**row, "action": "none", "why": "already AD-039 and nothing untracked", "sha": None}
        git(repo, "add", "--", *paths)
        msg = COMMIT_MSG if status == "pass" else COMMIT_MSG + " (.gitignore only; scan flagged files left untracked)"
        c = git(repo, "commit", "-m", msg + "\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>", "--", *paths,
                check=False)
        if c.returncode != 0:
            git(repo, "reset", "-q", "--", *paths, check=False)
            return {**row, "action": "commit_refused", "why": (c.stdout + c.stderr).strip()[-800:]}
        row["sha"] = git(repo, "rev-parse", "HEAD").stdout.strip()
        row["committed_paths"] = len(paths)
        return {**row, "action": "committed"}
    except Exception:
        gi.write_text(before)
        raise


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    ap.add_argument("--only", nargs="*", default=None)
    a = ap.parse_args()
    if a.apply:
        EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    bad = 0
    for name in a.only or REPOS:
        try:
            row = one(name, a.apply)
        except Exception as exc:  # one repository's failure is a row, not a crash (standards §15.7)
            row = {"repo": name, "action": "error", "why": f"{type(exc).__name__}: {exc}"[:800]}
            bad += 1
        print(json.dumps(row), flush=True)
        if a.apply:
            with EVIDENCE.open("a") as f:
                f.write(json.dumps(row) + "\n")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
