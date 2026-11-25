"""The portfolio brief and handoff: one read of every repository a project declares (AD-038-R32 to R35, SEL-044).

**Why this exists.** The operator starts at the factory, and a `seldon go` or a handoff there read the factory's graph
only. The factory's coordinator gathered every other repository by hand, one task list and one
`.seldon/dispatch_last_pass.json` at a time, and on 2026-11-13 that hand gathering missed work seldon had finished four
days earlier (factory's filing `6087e4d1`). Every reading the brief needs already exists per repository; this module
gathers them, it measures nothing new.

**The shape.** A project declares ``portfolio.repositories`` (name to path, relative to its primary checkout). Each
listed repository is opened through its OWN ``seldon.yaml``, as :mod:`seldon.core.cross_project` opens a waits-on
target (AD-038-R8), and read with the readers its own commands use:

- open tasks: the ResearchTasks in its domain's open states, the query and the set `seldon task list` uses, so the
  counts are that command's at the same moment (R34);
- the running task and its phase: the pass lease's ``phase`` (AD-037-R17) and, in ``gate``, its ``gate_progress``
  (AD-037-R20), read with `seldon dispatch status`'s readers (``read_lease``, ``lease_is_held``, ``worktree_leases``,
  ``stations.gate_progress``); a lease with no phase is ``phase unknown``, never a guess;
- the last pass (``read_last_pass``), open huddles (``stations.open_huddles``), the stuck streaks the dispatcher
  notified, and the blocked tasks with their stored reason (AD-038-R7), where ``ungated`` and ``interrupted_thrice``
  show;
- the median gate time over ``wall_seconds`` only (AD-037-R21), with its n.

Nothing is written to any listed repository. The only file this module writes is the portfolio handoff, in the
portfolio project (:func:`write_handoff`).

**Failure.** A repository that cannot be read is a row with its reason, never dropped (R33): every reading is taken
separately and a failed one is recorded by name with its exception, so one bad graph does not hide a repository's
lease, and one bad repository does not stop another's read.

**Prior art.** gita and myrepos (a declared list of repositories, one read across them, one table; found, not read
beyond their descriptions) and scatter-gather (Hohpe and Woolf, *Enterprise Integration Patterns*: one request to many
recipients side by side, a non-answer reported). See AD-038 ADDENDUM 14 section 2.
"""
from __future__ import annotations

import re
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

#: The seldon.yaml block (AD-038-R32).
CONFIG_KEY = "portfolio"

#: `portfolio` defaults besides `repositories`, which has none. Each value's basis is stated; each is overridable.
PORTFOLIO_DEFAULTS = {
    # AD-038-R34 / SEL-044 ADDENDUM 01 item 1: a running gate whose log has not grown for this long is an alarm (a hung
    # gate shows as output that stopped growing, AD-037-R20). ASSUMPTION, no measured basis: half of the stations'
    # `check_timeout_s` (1800 s, the longest one check may run), so a gate silent for half the time a whole check may
    # take is shown, not yet killed.
    "gate_silent_after_s": 900,
    # AD-038-R35: how far "completed since" reaches before the first portfolio handoff exists. ASSUMPTION: one week,
    # the span of the factory's own hand gatherings (2026-11-01, 11-02, 11-13).
    "first_window_days": 7,
    # AD-038-R35: readers run side by side, at most this many at once. The bound itself is an ASSUMPTION (a few more
    # than the six dispatching repositories). SEL-044 Part D measured the read of the real nine at 1.8 s with 8 and
    # 2.1 s with 1: parsing the event stores holds the GIL, so threads overlap only the graph queries and file reads
    # (docs/evidence/sel044/part_d_timing.md).
    "max_workers": 8,
}

#: The line a portfolio handoff carries, with the time it was generated (R35); the next brief reads it back.
HANDOFF_MARKER = "**Portfolio handoff:**"
_MARKER_RE = re.compile(r"^\*\*Portfolio handoff:\*\*\s+(\S+)")

HANDOFFS_DIR = "handoffs"

#: Task states that count as "completed" for "completed since" (terminal success, as AD-038-R8's waits read it).
DONE_STATES = ("completed", "verified")

#: The ResearchTask label `seldon task list` reads.
TASK_LABEL = "ResearchTask"

#: Shown where the lease records no phase (SEL-044 ADDENDUM 01 item 1: do not guess it).
PHASE_UNKNOWN = "phase unknown"

#: Shown where no gate record carries wall time (SEL-044 ADDENDUM 01 item 2).
NO_WALL_GATES = "no wall-clock gate records"


class PortfolioConfigError(ValueError):
    """The project declares no usable `portfolio` block."""


# ------------------------------------------------------------------------------------------------ configuration

def settings(config: Optional[dict]) -> dict:
    """`portfolio` over `PORTFOLIO_DEFAULTS`, validated. Unknown keys refuse, as `dispatch.stations` does: a misspelt
    threshold would otherwise be silently the default.

    Raises:
        PortfolioConfigError: no `portfolio.repositories`, a malformed entry, an unknown key or a bad number.
    """
    block = (config or {}).get(CONFIG_KEY)
    if not block:
        raise PortfolioConfigError(
            "this project declares no portfolio: add `portfolio: {repositories: {<name>: <path>}}` to its seldon.yaml, "
            "paths relative to its primary checkout (AD-038-R32)")
    if not isinstance(block, dict):
        raise PortfolioConfigError(f"portfolio must be a mapping, got {block!r}")
    unknown = sorted(set(block) - set(PORTFOLIO_DEFAULTS) - {"repositories"})
    if unknown:
        raise PortfolioConfigError(f"portfolio has unknown key(s) {unknown}; known: "
                                   f"{sorted(set(PORTFOLIO_DEFAULTS) | {'repositories'})}")
    repos = block.get("repositories")
    if not isinstance(repos, dict) or not repos:
        raise PortfolioConfigError("portfolio.repositories must be a non-empty mapping of name to path "
                                   f"(AD-038-R32), got {repos!r}")
    for name, path in repos.items():
        if not isinstance(name, str) or not name or not isinstance(path, str) or not path:
            raise PortfolioConfigError(f"portfolio.repositories entry {name!r}: {path!r} must be a name and a path")
    out = {**PORTFOLIO_DEFAULTS, **{k: v for k, v in block.items() if k != "repositories"}, "repositories": repos}
    for key in ("gate_silent_after_s", "first_window_days"):
        v = out[key]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
            raise PortfolioConfigError(f"portfolio.{key} must be a positive number, got {v!r}")
    v = out["max_workers"]
    if isinstance(v, bool) or not isinstance(v, int) or v < 1:
        raise PortfolioConfigError(f"portfolio.max_workers must be a whole number of at least 1, got {v!r}")
    return out


def repositories(project_dir: Path, scfg: dict) -> dict:
    """`{name: absolute path}` in declared order, relative paths resolved against the PRIMARY checkout (a worktree's
    `../x` would point inside `.claude/worktrees/`, STD-001R), as `cross_project` resolves them."""
    from seldon.core.cross_project import _anchor

    anchor = _anchor(Path(project_dir))
    return {name: (anchor / path).resolve() for name, path in scfg["repositories"].items()}


# ------------------------------------------------------------------------------------------------ time

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    """UTC ISO time with microseconds: the handoff marker is the next window's start, and one cut to whole seconds
    counts a completion in the same second as the handoff twice (found by the handoff test)."""
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def last_portfolio_handoff(project_dir: Path) -> Optional[tuple]:
    """`(path, generated_at)` of the newest handoff in the portfolio project carrying `HANDOFF_MARKER`, or None."""
    d = Path(project_dir) / HANDOFFS_DIR
    best = None
    for path in d.glob("*.md") if d.is_dir() else []:
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                m = _MARKER_RE.match(line.strip())
                if m:
                    at = _parse(m.group(1))
                    if at is not None and (best is None or at > best[1]):
                        best = (path, at)
                    break
    return best


def since_for(project_dir: Path, scfg: dict, now: datetime) -> tuple:
    """`(since, source)` for "completed since" (R35): the last portfolio handoff's time, else the first window."""
    last = last_portfolio_handoff(project_dir)
    if last:
        return last[1], f"the last portfolio handoff, {Path(last[0]).name}"
    days = scfg["first_window_days"]
    return now - timedelta(days=days), f"no portfolio handoff yet; the last {days:g} day(s) (portfolio.first_window_days)"


# ------------------------------------------------------------------------------------------------ one repository

def _error(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


def _domain(config: dict):
    from seldon.domain.loader import load_domain_config

    name = (config.get("project") or {}).get("domain", "research")
    return load_domain_config(Path(__file__).resolve().parent.parent / "domain" / f"{name}.yaml")


def _graph(root: Path, config: dict, done_ids: list) -> dict:
    """The repository's open tasks (as `seldon task list` reads them) and the named done ones, in ONE query."""
    from seldon.config import get_neo4j_driver
    from seldon.core.artifacts import BLOCK_REASON_PROPERTY, open_states

    database = (config.get("neo4j") or {}).get("database")
    if not database:
        raise ValueError(f"{root}/seldon.yaml names no neo4j.database")
    open_set = list(open_states(_domain(config), TASK_LABEL))
    driver = get_neo4j_driver(config)
    try:
        with driver.session(database=database) as s:
            records = s.run(
                f"MATCH (t:{TASK_LABEL}) WHERE t.state IN $open OR t.artifact_id IN $done "
                "RETURN t.artifact_id AS id, t.state AS state, t.description AS description, t.name AS name, "
                f"t.{BLOCK_REASON_PROPERTY} AS block_reason, t.task_kind AS kind ORDER BY t.created_at",
                open=open_set, done=list(done_ids)).data()
    finally:
        driver.close()
    open_rows = [r for r in records if r["state"] in open_set]
    by_state: dict = {}
    for r in open_rows:
        by_state[r["state"]] = by_state.get(r["state"], 0) + 1
    return {"database": database, "open_states": open_set, "open": open_rows, "open_count": len(open_rows),
            "by_state": by_state, "done": [r for r in records if r["id"] in set(done_ids)
                                           and r["state"] in DONE_STATES]}


def _from_events(events: list, since: datetime) -> dict:
    """Completions since `since`, open huddles and the wall-clock gate median, from one read of the event store."""
    from seldon.core import gate_plan as GP
    from seldon.core import gate_record as GR
    from seldon.core import stations as S

    done, walls, without = {}, [], 0
    for e in events:
        t = e.get("event_type")
        p = e.get("payload") or {}
        if t == "artifact_state_changed" and p.get("to_state") in DONE_STATES:
            at = _parse(e.get("timestamp"))
            if at is not None and at > since and p.get("artifact_id"):
                done[p["artifact_id"]] = _iso(at)
        elif t == GP.EVENT_GATE_RUN or t == GR.EVENT_RECORDED:
            # ADDENDUM 01 item 2: wall seconds only; a record from before SEL-043 is left out, never filled in from
            # monotonic `seconds` (two clocks in one number).
            w = p.get("wall_seconds") if t == GP.EVENT_GATE_RUN else (p.get("gate") or {}).get("wall_seconds")
            if isinstance(w, (int, float)) and not isinstance(w, bool):
                walls.append(float(w))
            else:
                without += 1
    return {"completed_at": done, "huddles": S.open_huddles(events),
            "gate": {"median_wall_s": round(statistics.median(walls), 1) if walls else None, "n": len(walls),
                     "without_wall": without}}


def _dispatcher(root: Path, config: dict) -> Optional[dict]:
    """The dispatcher's readings, as `seldon dispatch status` takes them; None for a repository with no dispatch block.
    Reads only: `mark_phase` is never called (ADDENDUM 01 item 1)."""
    from seldon.core import dispatch as D
    from seldon.core import stations as S

    if not config.get("dispatch"):
        return None
    cfg = D.load_dispatch_config(root, config)
    out: dict = {"enabled": cfg["enabled"], "errors": {}}
    out["stop_file"] = D.config_path(root, cfg["stop_file"]).exists()
    lease_path = D.config_path(root, cfg["lease_file"])
    body = D.read_lease(lease_path)
    held = D.lease_is_held(root, cfg)
    out["lease"] = {"held": held, "holder": body.get("holder"), "task": body.get("task"),
                    "phase": body.get("phase"), "phase_since": body.get("phase_since"),
                    "gate": S.gate_progress(body.get("gate")) if held and body.get("gate") else None,
                    "holder_gone": bool(body.get("holder")) and not held,
                    "unparseable": bool(body.get("unparseable"))}
    out["worktrees"] = [{"stem": wl["stem"], "task": (wl["body"] or {}).get("task"),
                         "alive": wl["alive"], "branch": (wl["body"] or {}).get("branch")}
                        for wl in D.worktree_leases(root, cfg) if wl["held"]]
    try:
        last = D.read_last_pass(root, cfg)
        out["last_pass"] = None if last is None else {
            "at": last.get("at"), "candidates": last.get("candidates", 0),
            "refused": len(last.get("refused") or []), "lines": list(last.get("lines") or [])}
    except (OSError, ValueError) as exc:
        out["errors"]["last_pass"] = _error(exc)
    # The streak file beside THIS repository's lease. `stuck_state_path` honours SELDON_DISPATCH_STUCK_STATE, which
    # names the calling process's own project; another repository's file is always beside its own lease.
    stuck_path = lease_path.parent / D.STUCK_STATE_FILE
    try:
        import json
        streaks = json.loads(stuck_path.read_text(encoding="utf-8") or "{}") if stuck_path.is_file() else {}
        out["stuck"] = {tid: s for tid, s in (streaks or {}).items() if isinstance(s, dict) and s.get("notified")}
    except (OSError, ValueError) as exc:
        out["errors"]["stuck"] = _error(exc)
    return out


def read_repository(name: str, root: Path, since: datetime, scfg: dict) -> dict:
    """Every reading of one repository. Never raises: a reading that fails is recorded under `errors` by name, and a
    repository that cannot be opened at all is `readable: False` with its `reason` (R33)."""
    from seldon.config import load_project_config
    from seldon.core.events import read_events

    started = time.monotonic()
    row: dict = {"name": name, "path": str(root), "readable": True, "reason": None, "errors": {}}

    def done() -> dict:
        row["read_s"] = round(time.monotonic() - started, 2)
        return row

    if not Path(root).is_dir():
        row.update(readable=False, reason=f"no directory at {root}")
        return done()
    if not (Path(root) / "seldon.yaml").is_file():
        row.update(readable=False, reason=f"no seldon.yaml at {root}")
        return done()
    try:
        config = load_project_config(Path(root))
    except Exception as exc:                                        # noqa: BLE001 - shown in the row (R33)
        row.update(readable=False, reason=f"seldon.yaml unreadable: {_error(exc)}")
        return done()

    ev: dict = {"completed_at": {}, "huddles": [], "gate": None}
    try:
        ev = _from_events(read_events(Path(root)), since)
    except Exception as exc:                                        # noqa: BLE001 - shown in the row (R33)
        row["errors"]["events"] = _error(exc)
    row["huddles"] = ev["huddles"]
    row["gate"] = ev["gate"]
    try:
        g = _graph(Path(root), config, list(ev["completed_at"]))
        row["tasks"] = {k: g[k] for k in ("database", "open_states", "open", "open_count", "by_state")}
        row["completed"] = [{**r, "at": ev["completed_at"].get(r["id"])} for r in g["done"]]
    except Exception as exc:                                        # noqa: BLE001 - shown in the row (R33)
        row["errors"]["graph"] = _error(exc)
        row["tasks"], row["completed"] = None, None
    try:
        row["dispatch"] = _dispatcher(Path(root), config)
        if row["dispatch"]:
            for k, v in row["dispatch"].pop("errors").items():
                row["errors"][f"dispatch.{k}"] = v
    except Exception as exc:                                        # noqa: BLE001 - shown in the row (R33)
        row["errors"]["dispatch"] = _error(exc)
        row["dispatch"] = None
    # Neither the graph nor the event store answered: nothing a person needs was read, so the repository is unreadable
    # with every reason. One of the two failing is a partial read, shown as an alarm per failed reading.
    if "graph" in row["errors"] and "events" in row["errors"]:
        row.update(readable=False, reason="; ".join(f"{k}: {v}" for k, v in row["errors"].items()))
    return done()


# ------------------------------------------------------------------------------------------------ the portfolio

def read_portfolio(project_dir: Path, config: dict, now: Optional[datetime] = None,
                   reader: Callable[..., dict] = read_repository) -> dict:
    """Read every declared repository side by side (R35), rows in declared order.

    Raises:
        PortfolioConfigError: the project declares no usable portfolio (R32).
    """
    scfg = settings(config)
    now = now or _now()
    since, source = since_for(Path(project_dir), scfg, now)
    repos = repositories(Path(project_dir), scfg)
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=min(scfg["max_workers"], len(repos))) as pool:
        futures = {name: pool.submit(reader, name, path, since, scfg) for name, path in repos.items()}
        rows = []
        for name, fut in futures.items():
            try:
                rows.append(fut.result())
            except Exception as exc:                                # noqa: BLE001 - a reader that raised is a row
                rows.append({"name": name, "path": str(repos[name]), "readable": False,
                             "reason": f"reader failed: {_error(exc)}", "errors": {}})
    for row in rows:
        row["alarms"] = alarms(row, scfg)
    project = ((config.get("project") or {}).get("name")) or Path(project_dir).name
    return {"project": project, "project_dir": str(project_dir), "generated_at": _iso(now), "since": _iso(since),
            "since_source": source, "settings": {k: v for k, v in scfg.items() if k != "repositories"},
            "seconds": round(time.monotonic() - started, 2), "repositories": rows}


def alarms(row: dict, scfg: dict) -> list:
    """What is wrong in one repository (R34), each a short sentence. A failed reading is one too."""
    out = []
    if not row.get("readable"):
        return [f"unreadable: {row.get('reason')}"]
    for k, v in (row.get("errors") or {}).items():
        out.append(f"reading {k} failed: {v}")
    d = row.get("dispatch") or {}
    if d.get("stop_file"):
        out.append("stop file present: the dispatcher launches nothing")
    lease = d.get("lease") or {}
    if lease.get("unparseable"):
        out.append("pass lease unparseable")
    if lease.get("holder_gone"):
        out.append(f"pass lease holder gone ({lease.get('holder')}): `seldon dispatch lease reap`")
    g = lease.get("gate")
    if g and not g.get("finished"):
        age = g.get("last_output_age_s")
        if age is None or age >= scfg["gate_silent_after_s"]:
            out.append(f"gate output silent {'(no log)' if age is None else f'{age:.0f} s'} "
                       f"(>= portfolio.gate_silent_after_s {scfg['gate_silent_after_s']:g}): a hung gate? "
                       f"{g.get('log')}")
    for wl in d.get("worktrees") or []:
        if not wl.get("alive"):
            out.append(f"worktree lease {wl['stem']} holder gone: `seldon dispatch lease reap --task {wl['stem']}`")
    for tid, s in (d.get("stuck") or {}).items():
        out.append(f"stuck: {tid[:8]} refused {s.get('passes')} pass(es) on {s.get('criterion')} "
                   f"since {s.get('first_seen')}")
    for t in (row.get("tasks") or {}).get("open") or []:
        if t["state"] == "blocked":
            out.append(f"blocked: {t['id'][:8]} {t.get('block_reason') or 'no reason recorded'}")
    for h in row.get("huddles") or []:
        out.append(f"open huddle {str(h.get('huddle_id'))[:8]} on {str(h.get('task_id'))[:8]}: {h.get('reading')}")
    return out


# ------------------------------------------------------------------------------------------------ rendering

def _cell(text) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def running(row: dict) -> list:
    """`[(label, phase text)]` for the pass lease's task and every held worktree lease."""
    d = row.get("dispatch") or {}
    lease = d.get("lease") or {}
    out = []
    if lease.get("held"):
        phase = lease.get("phase") or PHASE_UNKNOWN
        out.append((str(lease.get("task") or "no task")[:8], phase))
    for wl in d.get("worktrees") or []:
        out.append((str(wl.get("task") or wl["stem"])[:8], f"worktree {wl['stem']}"))
    return out


def _open_text(row: dict) -> str:
    t = row.get("tasks")
    if not t:
        return "?"
    parts = ", ".join(f"{s} {n}" for s, n in sorted(t["by_state"].items()))
    return f"{t['open_count']}" + (f" ({parts})" if parts else "")


def _pass_text(row: dict) -> str:
    d = row.get("dispatch")
    if d is None:
        return "no dispatcher"
    lp = d.get("last_pass")
    if not lp:
        return "no pass recorded" if "dispatch.last_pass" not in (row.get("errors") or {}) else "unreadable"
    return f"{str(lp['at'])[:16]}Z {lp['candidates']} cand, {lp['refused']} refused"


def _gate_text(row: dict) -> str:
    g = row.get("gate")
    if not g:
        return "?"
    if not g["n"]:
        return NO_WALL_GATES
    return f"{g['median_wall_s']:.0f} s wall (n={g['n']})"


def _filings(row: dict) -> list:
    return [t for t in ((row.get("tasks") or {}).get("open") or []) if t.get("kind") == "filing"]


def gate_line(g: dict) -> str:
    """The running gate's progress, as `seldon dispatch status` prints it (`environment_lines`)."""
    wall, age = g.get("elapsed_wall_s"), g.get("last_output_age_s")
    ran = "?" if wall is None else f"{wall / 60:.0f} min"
    last = "never" if age is None else f"{age:.0f} s ago"
    state = "finished" if g.get("finished") else "running"
    return (f"gate {g.get('call_site')} {state} {ran} (wall), {g.get('lines')} line(s) in {g.get('log')}, "
            f"last output {last}" + (f": {g['last_line']}" if g.get("last_line") else ""))


def render_table(p: dict) -> list:
    lines = ["| repository | open | running (phase) | last pass | alarms | done since | filings | gate median |",
             "|---|---|---|---|---|---|---|---|"]
    for r in p["repositories"]:
        if not r.get("readable"):
            lines.append(f"| {r['name']} | UNREADABLE | | | 1 | | | |")
            continue
        run = ", ".join(f"{t} {ph}" for t, ph in running(r)) or "-"
        done = "?" if r.get("completed") is None else str(len(r["completed"]))
        lines.append("| " + " | ".join(_cell(x) for x in (
            r["name"], _open_text(r), run, _pass_text(r), len(r["alarms"]) or "-", done,
            len(_filings(r)) if r.get("tasks") else "?", _gate_text(r))) + " |")
    return lines


def render_detail(r: dict) -> list:
    """Detail for a repository with something wrong (R34): its path, its reason or its alarms, its gate's progress."""
    out = [f"### {r['name']}", "", f"`{r['path']}`"]
    if not r.get("readable"):
        out += ["", f"- UNREADABLE: {r.get('reason')}"]
        return out
    out.append("")
    out += [f"- {a}" for a in r["alarms"]]
    lease = ((r.get("dispatch") or {}).get("lease") or {})
    if lease.get("held"):
        out.append(f"- pass lease: {lease.get('holder')}, task {str(lease.get('task') or 'none')[:8]}, "
                   f"{lease.get('phase') or PHASE_UNKNOWN} since {lease.get('phase_since') or '?'}")
        if lease.get("gate"):
            out.append(f"  - {gate_line(lease['gate'])}")
    return out


def render_brief(p: dict) -> str:
    """The one-screen brief: a header, one row per repository, then detail only where something is wrong."""
    rows = p["repositories"]
    bad = [r for r in rows if r.get("alarms")]
    unreadable = sum(1 for r in rows if not r.get("readable"))
    lines = [f"## Portfolio: {p['project']}, {len(rows)} repositories",
             "",
             f"Read {p['generated_at']} in {p['seconds']:.1f} s; {unreadable} unreadable; "
             f"{len(bad)} with something wrong. Done since {p['since']} ({p['since_source']}). "
             "Spend and the bank are not here; they are the factory's own.",
             ""]
    lines += render_table(p)
    if bad:
        lines += ["", "### Something wrong", ""]
        for r in bad:
            lines += render_detail(r)
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# ------------------------------------------------------------------------------------------------ the handoff

def handoff_path(project_dir: Path, slug: str, now: datetime) -> Path:
    return Path(project_dir) / HANDOFFS_DIR / f"{now.astimezone(timezone.utc).strftime('%Y-%m-%d')}_{slug}.md"


def resume_line(project_dir: Path, path: Path, next_action: str) -> str:
    """The one resume line (R35)."""
    return (f"In {Path(project_dir).resolve()}: `seldon go --portfolio --brief`, then read {Path(path).resolve()}. "
            f"First action: {next_action}")


def render_section(r: dict) -> list:
    out = [f"## {r['name']}", "", f"`{r['path']}`", ""]
    if not r.get("readable"):
        return out + [f"UNREADABLE: {r.get('reason')}", ""]
    for a in r["alarms"]:
        out.append(f"- ALARM: {a}")
    if r["alarms"]:
        out.append("")
    run = running(r)
    out.append("**Running:** " + (", ".join(f"`{t}` {ph}" for t, ph in run) if run else "nothing"))
    lease = ((r.get("dispatch") or {}).get("lease") or {})
    if lease.get("gate"):
        out.append(f"  - {gate_line(lease['gate'])}")
    out.append(f"**Last pass:** {_pass_text(r)}")
    out.append(f"**Gate median:** {_gate_text(r)}")
    t = r.get("tasks")
    if t is None:
        out.append("**Open tasks:** unreadable")
    else:
        out.append(f"**Open tasks ({t['open_count']}):**" + ("" if t["open"] else " none"))
        for x in t["open"]:
            why = f" [blocked: {x.get('block_reason') or 'no reason recorded'}]" if x["state"] == "blocked" else ""
            kind = " (filing)" if x.get("kind") == "filing" else ""
            out.append(f"- `{x['id'][:8]}` [{x['state']}]{kind} {(x.get('description') or '')[:110]}{why}")
    done = r.get("completed")
    if done is None:
        out.append("**Completed since:** unreadable")
    else:
        out.append(f"**Completed since ({len(done)}):**" + ("" if done else " none"))
        for x in done:
            out.append(f"- `{x['id'][:8]}` {x['state']} {x.get('at') or ''} {(x.get('description') or '')[:100]}")
    return out + [""]


def render_handoff(p: dict, path: Path, summary: str, next_action: str) -> tuple:
    """`(text, resume)`: the portfolio handoff, one section per repository and one resume line (R35)."""
    resume = resume_line(Path(p["project_dir"]), path, next_action)
    lines = [f"# Portfolio handoff: {p['project']}", "",
             f"{HANDOFF_MARKER} {p['generated_at']}", "",
             f"**Summary:** {summary}", "",
             "Generated by `seldon handoff --portfolio` (AD-038-R35). Each section is read from that repository's own "
             "graph, event store and dispatcher files, and nothing was written to any of them.", ""]
    lines += render_brief(p).splitlines()
    lines.append("")
    for r in p["repositories"]:
        lines += render_section(r)
    lines += ["## Resume", "", resume, ""]
    return "\n".join(lines), resume


def write_handoff(path: Path, text: str, force: bool = False) -> Path:
    """Write the portfolio handoff in the portfolio project; an existing one is refused unless `force`."""
    path = Path(path)
    if path.exists() and not force:
        raise FileExistsError(f"{path} already exists. Choose another --slug, or pass --force to replace it.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
