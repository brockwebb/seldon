"""The dispatcher reconciles machine-written governed state before it judges the tree (AD-038-R1).

**Why this exists.** Between 10 and 17 October 2026 the two standing dispatchers refused 797 passes on c7, the
clean-tree criterion, and every one of those refusals was caused by a file the system itself had written and not
committed (`docs/design/AD-038_the_machine_reconciles_its_own_state.md` §1). Each writer had been taught, one task at a
time, to commit its own lines (AD-036-R11, DESK-001), and each fix exposed the next writer. The dispatcher committed
only lines whose actor was `dispatcher` or `desktop` (the retired `COMMITTABLE_ACTORS`), so a `governed_sync` or a
`cc` line counted as dirt and refused the whole queue.

**Prior art.** OpenGitOps principle 4: "software agents continuously observe actual system state and attempt to apply
the desired state". A reconciler that finds drift repairs it rather than stopping the world for a person. The duty that
R11 put on each writer moves to the one process that can always discharge it: the pass holding the lease, before it
reads the tree.

**What qualifies a path is its class and the shape of its change, never who wrote it** (AD-038-R1):

========================  ==============================================================  ==========================
class                     paths                                                           admitted change
========================  ==============================================================  ==========================
``event_store``           the tracked event store (``event_store.path``)                  append-only, every line parses
``prior_art``             the prior-art query log and the verdict ledger (AD-036-R3, R4)  append-only, every line parses
``decision_register``     a NEW record under the register dir; the rendered REGISTER.md   a new record file; any render
``cadence``               ``seldon.yaml``                                                 only ``last_instance:`` lines
``task_files``            an untracked registered task file, its untracked addendum, or   registration output
                          its untracked ``_OODA.md`` record (AD-038-R10); an untracked
                          addendum is admitted whether or not its base is tracked
``hooks``                 ``.githooks/pre-commit`` and ``.githooks/commit-msg``           bytes exactly seldon's text
                          (AD-038-R15)
========================  ==============================================================  ==========================

Anything else (a source file, a ledger edited in place, a deleted file, a hook refusal) is left for c7, which names
the path and the reason. One commit per class, path-scoped, hooks on (R11's gate is kept).

The caller holds the lease and has no claim in flight: a `git commit` beside a working dispatched session is DD-019's
class and an `index.lock` collision besides. This module checks neither; `seldon.commands.dispatch._reconcile` does.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

#: The classes, in the order their commits are made. The event store first: every other class's writer also appended
#: to it, and a reader of `git log` finds each record before the files it records.
CLASSES = ("event_store", "prior_art", "decision_register", "cadence", "task_files", "hooks")

#: The one seldon.yaml line the cadence writes back (`seldon.core.cadence.write_last_instance`).
_LAST_INSTANCE_RE = re.compile(r"^\s*last_instance\s*:")

#: Addenda beside a task file (`seldon.core.dispatch.addenda_for` uses the same glob).
_ADDENDUM_RE = re.compile(r"^(?P<stem>.+)_ADDENDUM[^/]*\.md$")

#: The Desktop OODA's file record beside a task file (`seldon.core.dispatch.OODA_FILE_SUFFIX`, AD-038-R10). A Desktop
#: session writes it as it writes an addendum, so it is reconciled as one: c18 counts it only once it is committed.
_OODA_RE = re.compile(r"^(?P<stem>.+)_OODA\.md$")


def _git(project_dir: Path, *args: str, text: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=project_dir, capture_output=True, text=text)


def dirty_entries(project_dir: Path) -> list:
    """Every dirty path as `{path, status, tracked}` from `git status --porcelain -z --untracked-files=all`.

    `-z` so a path with a space or a quote is read as git wrote it; `--untracked-files=all` so a new file in a new
    directory is named, not its directory. `--no-optional-locks` for the reason `tree_state` gives.

    Raises:
        RuntimeError: When git status fails. An unreadable tree is not a clean one, and c7 reports it.
    """
    r = _git(project_dir, "--no-optional-locks", "status", "--porcelain", "-z", "--untracked-files=all")
    if r.returncode != 0:
        raise RuntimeError(f"git status exited {r.returncode}: {(r.stderr or '').strip()[:200]}")
    out, parts, i = [], r.stdout.split("\0"), 0
    while i < len(parts):
        entry = parts[i]
        i += 1
        if not entry:
            continue
        xy, path = entry[:2], entry[3:]
        if xy[0] in "RC":
            # A rename or copy carries its source as the next NUL field; neither is a machine write.
            out.append({"path": path, "status": xy, "tracked": True, "from": parts[i]})
            i += 1
            continue
        out.append({"path": path, "status": xy, "tracked": xy != "??"})
    return out


def _head_bytes(project_dir: Path, rel: str) -> bytes | None:
    r = _git(project_dir, "show", f"HEAD:{rel}", text=False)
    return r.stdout if r.returncode == 0 else None


def appended_rows(project_dir: Path, rel: str) -> dict:
    """`{ok, why, rows}` for a JSONL file: its change against HEAD must be an append of lines that each parse.

    An untracked file is all appended (HEAD holds no bytes of it). `why` is the reason c7 is given when not ok.
    """
    path = Path(project_dir) / rel
    if not path.is_file():
        return {"ok": False, "why": "deleted", "rows": []}
    base = _head_bytes(project_dir, rel) or b""
    work = path.read_bytes()
    if not work.startswith(base):
        return {"ok": False, "why": "not append-only against HEAD (edited in place)", "rows": []}
    rows = []
    for raw in work[len(base):].decode("utf-8", errors="replace").splitlines():
        if not raw.strip():
            continue
        try:
            rows.append(json.loads(raw))
        except json.JSONDecodeError:
            return {"ok": False, "why": "an appended line does not parse as JSON", "rows": rows}
    return {"ok": True, "why": None, "rows": rows}


def writer_of(row: dict) -> str:
    """Who wrote a JSONL line: the event store's `actor`, a squiddy ledger line's `stage`, a query-log line's
    `tool`, or the provenance block's tool. Named in the commit message; never a condition on committing."""
    if not isinstance(row, dict):
        return "unknown"
    for key in ("actor", "stage", "tool"):
        if row.get(key):
            return str(row[key])
    prov = row.get("provenance")
    if isinstance(prov, dict) and prov.get("tool"):
        return str(prov["tool"])
    return "unknown"


def cadence_only(project_dir: Path, rel: str) -> bool:
    """Does `rel` differ from HEAD only in `last_instance:` lines, line for line? The cadence's write-back
    (`write_last_instance`) edits that one line in place, and nothing else in seldon.yaml is machine-written."""
    path = Path(project_dir) / rel
    base = _head_bytes(project_dir, rel)
    if base is None or not path.is_file():
        return False
    old = base.decode("utf-8", errors="replace").splitlines()
    new = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(old) != len(new):
        return False
    changed = [(a, b) for a, b in zip(old, new) if a != b]
    return bool(changed) and all(_LAST_INSTANCE_RE.match(a) and _LAST_INSTANCE_RE.match(b) for a, b in changed)


def governed_paths(project_dir: Path, config: dict) -> dict:
    """The path of each single-file class, relative to the project: `{event_store, query_log, verdict_ledger,
    register_dir, rendered}`. A project without a `prior_art:` block has neither prior-art path (None)."""
    from seldon.core import decisions as DEC

    project_dir = Path(project_dir)
    out = {"event_store": (config or {}).get("event_store", {}).get("path", "seldon_events.jsonl"),
           "query_log": None, "verdict_ledger": None,
           "register_dir": ((config or {}).get("decisions") or {}).get("register_dir", DEC.DEFAULT_REGISTER_DIR),
           "rendered": ((config or {}).get("decisions") or {}).get("rendered", DEC.DEFAULT_RENDERED)}
    if isinstance((config or {}).get("prior_art"), dict):
        from seldon.core import prior_art as pa
        try:
            s = pa.settings(project_dir, config)
            out["query_log"] = pa._rel_to(project_dir, s.log)
            out["verdict_ledger"] = pa._rel_to(project_dir, pa.verdict_ledger(project_dir, config))
        except pa.PriorArtError:
            # A misconfigured block is reported where it is used (search, verify); here its files are simply not a
            # class, so a dirty one is named by c7 like any other path.
            pass
    return out


def classify(project_dir: Path, config: dict, registered: set, entries: list | None = None) -> dict:
    """Sort every dirty path into a class, or into `unreconciled` with the reason.

    Args:
        project_dir: The checkout.
        config: The parsed seldon.yaml.
        registered: The `source_file` of every registered ResearchTask (relative paths).
        entries: `dirty_entries(project_dir)`, when the caller already has it.

    Returns:
        `{"classes": {class: {"paths": [...], "writers": [...], "rows": [...]}}, "unreconciled": [{path, why}]}`.
    """
    project_dir = Path(project_dir)
    entries = dirty_entries(project_dir) if entries is None else entries
    gp = governed_paths(project_dir, config)
    jsonl = {gp["event_store"]: "event_store"}
    for key in ("query_log", "verdict_ledger"):
        if gp[key]:
            jsonl[gp[key]] = "prior_art"
    reg_dir = gp["register_dir"].rstrip("/") + "/"
    classes = {c: {"paths": [], "writers": [], "rows": []} for c in CLASSES}
    unreconciled = []
    from seldon.core.hooks import seldon_hook_scripts
    hook_scripts = seldon_hook_scripts()

    def admit(cls, path, writers, rows=()):
        classes[cls]["paths"].append(path)
        classes[cls]["writers"].extend(w for w in writers if w not in classes[cls]["writers"])
        classes[cls]["rows"].extend(rows)

    for e in entries:
        path, status = e["path"], e["status"]
        if status[0] in "RC":
            unreconciled.append({"path": path, "why": f"renamed or copied from {e.get('from')}"})
            continue
        if "D" in status:
            unreconciled.append({"path": path, "why": "deleted"})
            continue
        if path in jsonl:
            got = appended_rows(project_dir, path)
            if got["ok"]:
                admit(jsonl[path], path, [writer_of(r) for r in got["rows"]], got["rows"])
            else:
                unreconciled.append({"path": path, "why": got["why"]})
            continue
        if path == gp["rendered"]:
            admit("decision_register", path, ["seldon decision (render)"])
            continue
        if path.startswith(reg_dir):
            if e["tracked"]:
                unreconciled.append({"path": path, "why": "a register record edited in place (one file per record "
                                                          "event, never edited: AD-033-R2)"})
            else:
                admit("decision_register", path, ["seldon decision"])
            continue
        if path == "seldon.yaml":
            if cadence_only(project_dir, path):
                admit("cadence", path, ["cadence"])
            else:
                unreconciled.append({"path": path, "why": "configuration edited beyond the cadence's last_instance"})
            continue
        if not e["tracked"] and path in registered:
            admit("task_files", path, ["cc register"])
            continue
        m = _ADDENDUM_RE.match(path)
        if not e["tracked"] and m and f"{m.group('stem')}.md" in registered:
            admit("task_files", path, ["addendum to a registered task"])
            continue
        m = _OODA_RE.match(path)
        if not e["tracked"] and m and f"{m.group('stem')}.md" in registered:
            admit("task_files", path, ["OODA record on a registered task"])
            continue
        if e["tracked"] and path in registered:
            unreconciled.append({"path": path, "why": "a registered task file edited after registration"})
            continue
        if path in hook_scripts:
            # AD-038-R15: `ensure_installed` writes commit-msg before the lease and may not commit it; an older
            # `seldon hooks install` wrote and left it. Seldon's exact text only: other bytes are someone's hook.
            f = project_dir / path
            if f.is_file() and f.read_text(encoding="utf-8", errors="replace") == hook_scripts[path]:
                admit("hooks", path, ["seldon hooks install"])
            else:
                unreconciled.append({"path": path, "why": "a hook file that is not seldon's text"})
            continue
        unreconciled.append({"path": path, "why": "not machine-written governed state"
                                                  + (" (untracked)" if not e["tracked"] else "")})
    return {"classes": {c: v for c, v in classes.items() if v["paths"]}, "unreconciled": unreconciled}


def _event_store_message(rows: list, writers: list) -> str:
    """The event store's commit subject: the types and ids first, so `git log` stays the log's own index."""
    types = list(dict.fromkeys(r.get("event_type") for r in rows if isinstance(r, dict)))
    ids = list(dict.fromkeys(
        str(p.get("task_id") or p.get("artifact_id"))[:8]
        for p in ((r.get("payload") or {}) for r in rows if isinstance(r, dict))
        if p.get("task_id") or p.get("artifact_id")))
    return (f"record: {', '.join(t for t in types if t)} {', '.join(ids) or '-'} — {len(rows)} line(s) written by "
            f"{', '.join(writers) or 'unknown'}; reconciled by the standing dispatcher (event_store, AD-038-R1)")


def message_for(cls: str, entry: dict) -> str:
    """One commit subject per class, naming the class and the writers found (FRICTION-001 Part A step 1)."""
    if cls == "event_store":
        return _event_store_message(entry["rows"], entry["writers"])
    what = {"prior_art": f"{len(entry['rows'])} prior-art line(s)",
            "decision_register": f"{len(entry['paths'])} decision-register file(s)",
            "cadence": "the cadence's last_instance",
            "task_files": f"{len(entry['paths'])} registered task file(s): {', '.join(entry['paths'])}",
            "hooks": f"seldon's hook file(s): {', '.join(entry['paths'])}"}[cls]
    rule = "AD-038-R15" if cls == "hooks" else "AD-038-R1"
    return (f"reconcile: {what} written by {', '.join(entry['writers']) or 'unknown'}; committed by the standing "
            f"dispatcher ({cls}, {rule})")


def reconcile(project_dir: Path, config: dict, registered: set, classes=CLASSES, commit=None) -> dict:
    """Commit every dirty path in the governed classes, one commit per class; report the rest.

    Args:
        project_dir: The checkout. The caller holds the lease with no claim in flight.
        config: The parsed seldon.yaml.
        registered: Every registered ResearchTask's `source_file`.
        classes: Which classes to commit (all by default). A path of another class is left as it is and is not
            reported as unreconciled: the caller asked about these classes only.
        commit: `commit_paths(project_dir, paths, message)`; `seldon.core.dispatch.commit_paths` by default.

    Returns:
        `{"commits": [{class, paths, writers, committed, commit?, reason?, stderr?}], "unreconciled": [{path, why}]}`.
        A class whose commit fails (a hook refusal) contributes its paths to `unreconciled` with git's reason.
    """
    if commit is None:
        from seldon.core.dispatch import commit_paths as commit
    project_dir = Path(project_dir)
    found = classify(project_dir, config, registered)
    commits, unreconciled = [], list(found["unreconciled"]) if set(classes) == set(CLASSES) else []
    for cls in CLASSES:
        if cls not in classes or cls not in found["classes"]:
            continue
        entry = found["classes"][cls]
        outcome = commit(project_dir, entry["paths"], message_for(cls, entry))
        commits.append({"class": cls, "paths": entry["paths"], "writers": entry["writers"],
                        "message": message_for(cls, entry), **outcome})
        if not outcome.get("committed"):
            stderr = (outcome.get("stderr") or "").strip().splitlines()
            why = f"commit refused ({outcome.get('reason')})" + (f": {stderr[-1][:200]}" if stderr else "")
            unreconciled.extend({"path": p, "why": why} for p in entry["paths"])
    return {"commits": commits, "unreconciled": unreconciled}
