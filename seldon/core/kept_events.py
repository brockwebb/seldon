"""SEL-034 Part B (AD-038-R25): the events a kept worktree's session wrote reach main's log, or are discarded on record.

A dispatched session in a worktree writes its graph events through the live graph and into the WORKTREE's event
store. When its branch merges, `merge=union` carries those lines into main's store and the log agrees with the graph.
When the branch is kept (`session_failed`, `merge_blocked` and every other unmerged outcome) the lines stayed in the
kept tree while their effect stayed in the live graph, so a rebuild from main's log and the live graph disagreed:
hazbrief HB-140 (SEL-030) resolved Issue 8b992307 and created Issue 5b737052 that way.

The prior art is event sourcing's own rule for a write that should not stand: the log is never edited, and an
unwanted effect is undone by a COMPENSATING event, not by deleting the record (Fowler, "Event Sourcing" and
"Retroactive Event", 2005; Garcia-Molina and Salem, "Sagas", SIGMOD 1987, for compensation as the undo of a committed
step; the Compensating Transaction pattern of the Azure Architecture Center). Two branches:

* **Union (the default).** The live graph already holds the lines' effect, so the log must too: the lines main lacks
  (by `event_id`) are appended to main's store byte for byte, as the union merge would have, and
  `kept_events_reconciled` names them. A later merge of the same branch drops those exact lines from the branch's
  store first (`drop_reconciled`), so main never holds an id twice (`read_events` refuses that).
* **Discard (the task is terminal: withdrawn, superseded, rejected).** The session's work was not wanted. Its lines
  go to `docs/evidence/<task stem>/discarded_events.jsonl`, not into main's log, and every effect they left in the
  live graph is compensated through the ordinary evented writers, so a rebuild and the live graph agree:
  a state change is walked back to the state main's log holds, a property update is set back to the log's value, a
  link the session made is removed. An effect another hand has since changed (HB-140R re-opened 8b992307) is left as
  that hand set it. Artifacts the session CREATED are the one exception: a node cannot be removed from the graph by
  an event, so their creation, and the lines that touch them, are carried into main's log, and each created Issue is
  closed `wont_fix` with `resolution_notes` beginning `premise_false:` and naming the task. `events_discarded` records
  the count, the ids, what was carried, every compensation and anything that could not be compensated.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from seldon.core import worktree as WT

EVENT_RECONCILED = "kept_events_reconciled"
EVENT_DISCARDED = "events_discarded"
#: The task states in which a kept session's events are discarded rather than merged: the task ended without its
#: work being wanted. `completed`/`verified` are not here: their work is done, and their lines belong in the log.
DISCARD_STATES = ("withdrawn", "superseded", "rejected")
EVIDENCE_DIR = "docs/evidence"
DISCARDED_FILE = "discarded_events.jsonl"
#: The prefix of a created Issue's `resolution_notes` when the discard closes it (SEL-034 Part B).
PREMISE_FALSE = "premise_false"
#: The Issue states a discard leaves alone: already closed.
ISSUE_CLOSED_STATES = ("resolved", "verified", "wont_fix")
#: How an open Issue reaches `wont_fix` (seldon/domain/research.yaml, Issue): only `open` has the edge.
ISSUE_TO_OPEN = {"in_progress": ["open"], "blocked": ["open"]}


def _parse(raw: str) -> dict | None:
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _lines(data: str) -> list:
    return [ln.rstrip("\n") for ln in data.splitlines() if ln.strip()]


def worktree_lines(project_dir: Path, worktree_rel: str | None, branch: str | None, store_rel: str) -> list:
    """The kept session's store as raw lines: the tree's file on disk (the superset: a line the session never
    committed is still the session's), then any line only the branch tip holds (a tree removed since)."""
    out, seen = [], set()

    def take(lines):
        for raw in lines:
            ev = _parse(raw)
            key = (ev or {}).get("event_id") or raw
            if key not in seen:
                seen.add(key)
                out.append(raw)

    if worktree_rel:
        path = Path(project_dir) / worktree_rel / store_rel
        if path.is_file():
            take(_lines(path.read_text(encoding="utf-8", errors="replace")))
    if branch:
        data = WT.show(Path(project_dir), branch, store_rel)
        if data is not None:
            take(_lines(data.decode("utf-8", errors="replace")))
    return out


def _main_index(project_dir: Path, store_rel: str) -> tuple:
    """`(ids, raws, discarded_ids)` of main's store: every event id, every raw line (for id-less legacy lines), and the
    ids an earlier `events_discarded` already took out (they are absent from the log on purpose)."""
    ids, raws, discarded = set(), set(), set()
    path = Path(project_dir) / store_rel
    if not path.is_file():
        return ids, raws, discarded
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            raw = line.rstrip("\n")
            if not raw.strip():
                continue
            raws.add(raw)
            ev = _parse(raw)
            if ev is None:
                continue
            if ev.get("event_id"):
                ids.add(ev["event_id"])
            if ev.get("event_type") == EVENT_DISCARDED:
                discarded.update((ev.get("payload") or {}).get("event_ids") or [])
    return ids, raws, discarded


def missing_from_main(project_dir: Path, lines: list, store_rel: str) -> list:
    """`[(raw, event)]`: the kept lines main's store lacks, in the session's order. A line whose id an earlier
    discard named is not missing; a malformed line is returned with `event` None so it is reported, never dropped."""
    ids, raws, discarded = _main_index(project_dir, store_rel)
    out = []
    for raw in lines:
        ev = _parse(raw)
        eid = (ev or {}).get("event_id")
        if eid:
            if eid not in ids and eid not in discarded:
                out.append((raw, ev))
        elif raw not in raws:
            out.append((raw, ev))
    return out


def append_raw(project_dir: Path, store_rel: str, raws: list) -> None:
    """Append lines to main's store byte for byte (one write, one fsync, as `events.append_events`), so a later merge
    of the same branch can recognise them exactly."""
    if not raws:
        return
    path = Path(project_dir) / store_rel
    with path.open("a", encoding="utf-8") as fh:
        fh.write("".join(r + "\n" for r in raws))
        fh.flush()
        os.fsync(fh.fileno())


def touched(ev: dict) -> set:
    """The artifact ids a line acts on: its `artifact_id`, or a link's two ends."""
    p = (ev or {}).get("payload") or {}
    return {x for x in (p.get("artifact_id"), p.get("from_id"), p.get("to_id"), (ev or {}).get("artifact_id")) if x}


def split(missing: list) -> dict:
    """The discard's split: `created` (ids the session created), `carried` (lines touching a created artifact, kept in
    the log because a node cannot be removed by an event) and `discarded` (the rest)."""
    created = {((ev or {}).get("payload") or {}).get("artifact_id") for _, ev in missing
               if (ev or {}).get("event_type") == "artifact_created"} - {None}
    carried, discarded = [], []
    for raw, ev in missing:
        (carried if ev is not None and touched(ev) & created else discarded).append((raw, ev))
    return {"created": sorted(created), "carried": carried, "discarded": discarded}


def write_evidence(project_dir: Path, stem: str, discarded: list) -> str:
    """Append the discarded lines to `docs/evidence/<stem>/discarded_events.jsonl` (lines already there are not
    written twice). Returns the file's repository-relative path."""
    rel = f"{EVIDENCE_DIR}/{stem}/{DISCARDED_FILE}"
    path = Path(project_dir) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    have = set(_lines(path.read_text(encoding="utf-8"))) if path.is_file() else set()
    new = [raw for raw, _ in discarded if raw not in have]
    if new:
        with path.open("a", encoding="utf-8") as fh:
            fh.write("".join(r + "\n" for r in new))
            fh.flush()
            os.fsync(fh.fileno())
    return rel


def log_state(events: list) -> dict:
    """`{artifact_id: {"state", "type", "props", "links"}}` as main's log alone would project it (`sync._apply_event`'s
    rules: a created artifact starts at its `to_state` or `proposed`; a state change sets `to_state`; an update sets
    its properties; a link exists from `link_created` until `link_removed`)."""
    out: dict = {}

    def node(aid):
        return out.setdefault(aid, {"state": None, "type": None, "props": {}, "links": set()})

    for e in events:
        t, p = e.get("event_type"), e.get("payload") or {}
        if t == "artifact_created" and p.get("artifact_id"):
            n = node(p["artifact_id"])
            n["state"], n["type"] = p.get("to_state", "proposed"), p.get("artifact_type")
            n["props"].update(p.get("properties") or {})
        elif t == "artifact_state_changed" and p.get("artifact_id"):
            n = node(p["artifact_id"])
            n["state"] = p.get("to_state")
            n["type"] = n["type"] or p.get("artifact_type")
        elif t == "artifact_updated" and p.get("artifact_id"):
            node(p["artifact_id"])["props"].update(p.get("properties") or {})
        elif t in ("link_created", "link_removed") and p.get("from_id"):
            key = (p["from_id"], str(p.get("rel_type") or "").upper(), p.get("to_id"))
            (node(p["from_id"])["links"].add if t == "link_created" else node(p["from_id"])["links"].discard)(key)
    return out


def plan_compensations(discarded: list, logged: dict, live: dict) -> dict:
    """What undoes each discarded line's effect that still stands in the live graph.

    `logged` is `log_state` over main's store; `live` maps an artifact id to `{"state", "type", "props", "links"}` as
    the live graph holds it now (None when the node is absent). Per artifact, only the session's LAST change of each
    kind is compensated, and only when the live graph still shows it (another hand's later change stands).

    Returns `{"transitions": [...], "updates": [...], "unlinks": [...], "unreconciled": [...]}`.
    """
    last_state, last_props, links = {}, {}, {}
    for _, ev in discarded:
        if ev is None:
            continue
        t, p = ev.get("event_type"), ev.get("payload") or {}
        if t == "artifact_state_changed" and p.get("artifact_id"):
            last_state[p["artifact_id"]] = (p.get("to_state"), p.get("artifact_type"), ev.get("event_id"))
        elif t == "artifact_updated" and p.get("artifact_id"):
            for k, v in (p.get("properties") or {}).items():
                last_props[(p["artifact_id"], k)] = (v, ev.get("event_id"))
        elif t in ("link_created", "link_removed") and p.get("from_id"):
            key = (p["from_id"], str(p.get("rel_type") or "").upper(), p.get("to_id"))
            links[key] = (t, ev.get("event_id"))
    plan = {"transitions": [], "updates": [], "unlinks": [], "unreconciled": []}
    for aid, (to_state, atype, eid) in last_state.items():
        now, was = (live.get(aid) or {}), (logged.get(aid) or {})
        if not now:
            plan["unreconciled"].append({"event_id": eid, "artifact_id": aid, "why": "absent from the live graph"})
        elif now.get("state") != to_state:
            continue                        # another hand moved it since; its state stands
        elif was.get("state") is None:
            plan["unreconciled"].append({"event_id": eid, "artifact_id": aid,
                                         "why": "main's log holds no state for this artifact"})
        elif was["state"] != to_state:
            plan["transitions"].append({"event_id": eid, "artifact_id": aid,
                                        "artifact_type": now.get("type") or atype or was.get("type"),
                                        "from_state": to_state, "to_state": was["state"]})
    props: dict = {}
    for (aid, k), (v, eid) in last_props.items():
        now, was = (live.get(aid) or {}), (logged.get(aid) or {})
        if not now or (now.get("props") or {}).get(k) != v or (was.get("props") or {}).get(k) == v:
            continue
        props.setdefault(aid, {"artifact_id": aid, "properties": {}, "event_ids": []})
        props[aid]["properties"][k] = (was.get("props") or {}).get(k)
        if eid not in props[aid]["event_ids"]:
            props[aid]["event_ids"].append(eid)
    plan["updates"] = list(props.values())
    for key, (t, eid) in links.items():
        frm, rel, to = key
        now = (live.get(frm) or {}).get("links") or set()
        was = (logged.get(frm) or {}).get("links") or set()
        row = {"event_id": eid, "from_id": frm, "rel_type": rel, "to_id": to}
        if t == "link_created" and key in now and key not in was:
            plan["unlinks"].append(row)
        elif t == "link_removed" and key not in now and key in was:
            plan["unreconciled"].append({**row, "why": "the session removed a link main's log holds; re-creating it "
                                                        "needs its endpoint types and properties, left to the operator"})
    return plan


def bridging_links(carried: list, created: list, live: dict) -> list:
    """The carried `link_created` lines that join a created artifact to an OLDER one and still stand in the live graph:
    carried so the log names the link, then removed, so the older artifact keeps no edge to unwanted work (HB-140's
    `8b992307 -verified_by-> <a test that never reached main>`)."""
    made = set(created)
    out = []
    for _, ev in carried:
        p = (ev or {}).get("payload") or {}
        if (ev or {}).get("event_type") != "link_created" or not p.get("from_id"):
            continue
        if {p["from_id"], p.get("to_id")} <= made:
            continue
        key = (p["from_id"], str(p.get("rel_type") or "").upper(), p.get("to_id"))
        if key in ((live.get(p["from_id"]) or {}).get("links") or set()):
            out.append({"event_id": ev.get("event_id"), "from_id": key[0], "rel_type": key[1], "to_id": key[2]})
    return out


def reconciled_ids(project_dir: Path, store_rel: str, task_id: str) -> set:
    """The event ids `kept_events_reconciled` already appended to main's store for `task_id`."""
    path = Path(project_dir) / store_rel
    out: set = set()
    if not path.is_file():
        return out
    mark = f'"{EVENT_RECONCILED}"'
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if mark in line and task_id in line:
                ev = _parse(line)
                p = (ev or {}).get("payload") or {}
                if (ev or {}).get("event_type") == EVENT_RECONCILED and p.get("task_id") == task_id:
                    out.update(p.get("event_ids") or [])
    return out


def drop_reconciled(wt: Path, store_rel: str, ids: set, task_label: str) -> dict:
    """Before a kept branch whose lines were reconciled merges: after its rebase the store holds main's copy of each
    reconciled line and the branch's own, and main may never hold an id twice. Drops the LATER copy of a reconciled
    id when it is byte-identical to the first, commits that on the branch, and returns `{dropped, commit, stderr}`.
    A copy that differs is left for the union check to name: two different records under one id are a defect, not a
    duplicate."""
    path = Path(wt) / store_rel
    if not ids or not path.is_file():
        return {"dropped": [], "commit": None, "stderr": ""}
    first: dict = {}
    keep, dropped = [], []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        ev = _parse(raw) if raw.strip() else None
        eid = (ev or {}).get("event_id")
        if eid in ids:
            if eid in first and first[eid] == raw:
                dropped.append(eid)
                continue
            first.setdefault(eid, raw)
        keep.append(raw)
    if not dropped:
        return {"dropped": [], "commit": None, "stderr": ""}
    path.write_text("".join(r + "\n" for r in keep), encoding="utf-8")
    add = WT.git(Path(wt), "add", "--", store_rel)
    msg = (f"dispatch: drop {len(dropped)} event line(s) of {task_label} already reconciled into main (SEL-034, "
           f"AD-038-R25)\n\nkept_events_reconciled appended them to main's store when the branch was kept; the "
           f"rebase brought the branch's copies beside main's.")
    c = WT.git(Path(wt), "commit", "-q", "-m", msg, "--", store_rel) if add.returncode == 0 else add
    if c.returncode != 0:
        return {"dropped": dropped, "commit": None, "stderr": (c.stderr or c.stdout).strip()[-500:]}
    return {"dropped": dropped, "commit": WT.rev(Path(wt), "HEAD"), "stderr": ""}
