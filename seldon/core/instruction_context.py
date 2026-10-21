"""The bytes of instruction context a launched session receives (PRUNE-002 Part B step 3, AD-038-R6's toil measure).

**Why this exists.** Before PRUNE-002, a session got `~/GitHub/CLAUDE.md` and the project's `CLAUDE.md` from the CLI,
then the same two files again inside `seldon go`, plus go's own hand-written command list. That is about 135 KB of
instruction context, most of it read twice and most of it describing gates that already state their own rule when
they refuse. AD-038-R6 says a control ships with a toil measure. This module is that measure for the cut: the
dispatcher records a reading on every `dispatch_launched` (`measure`), and `seldon qc chart` reports it per ISO week
(`by_week`). A growing number means the bootloader is growing back.

A launched session runs inside Claude Code, so its go output is measured on go's Claude Code path
(`in_claude_code=True`), which does not embed either CLAUDE.md file.
"""
from __future__ import annotations

from pathlib import Path
from statistics import median

from seldon.core.toil import week_of

#: The `dispatch_launched` payload key the reading is stored under.
PAYLOAD_KEY = "instruction_context"


def _bytes(path: Path | None) -> int | None:
    return path.stat().st_size if path is not None and path.is_file() else None


def measure(project_dir: Path) -> dict:
    """One reading for a session launched in `project_dir`.

    Returns `{"standards", "standards_path", "project_claude_md", "go", "go_error", "total"}`, sizes in bytes. A file
    that is absent counts as 0 in `total` and is None in its own key. When go's output cannot be assembled the
    failure is recorded as `go_error`, `go` is None and `total` is None: a reading missing a part is not a smaller
    reading, and the chart leaves it out rather than counting it low. The launch goes ahead either way.
    """
    from seldon.commands.go import assemble_go_context
    from seldon.paths import resolve_system_standards

    project_dir = Path(project_dir)
    standards_path = resolve_system_standards()
    standards = _bytes(standards_path)
    project_md = _bytes(project_dir / "CLAUDE.md")
    go_bytes, go_error = None, None
    try:
        go_bytes = len(assemble_go_context(project_dir=str(project_dir), in_claude_code=True).encode("utf-8"))
    except Exception as exc:                                            # noqa: BLE001 -- recorded, not swallowed
        go_error = f"{type(exc).__name__}: {exc}"
    total = None if go_bytes is None else (standards or 0) + (project_md or 0) + go_bytes
    return {"standards": standards, "standards_path": str(standards_path) if standards_path else None,
            "project_claude_md": project_md, "go": go_bytes, "go_error": go_error, "total": total}


def by_week(events: list) -> list:
    """`[{week, n, median_total, max_total, unmeasured}]` over `dispatch_launched` events, weeks in order.

    `n` counts launches with a complete reading; `unmeasured` counts launches with no reading (launched before
    PRUNE-002) or a reading without a total (go could not be assembled).
    """
    weeks: dict = {}
    for e in events:
        if e.get("event_type") != "dispatch_launched" or not e.get("timestamp"):
            continue
        reading = (e.get("payload") or {}).get(PAYLOAD_KEY) or {}
        row = weeks.setdefault(week_of(e["timestamp"]), {"totals": [], "unmeasured": 0})
        if isinstance(reading.get("total"), int):
            row["totals"].append(reading["total"])
        else:
            row["unmeasured"] += 1
    out = []
    for w in sorted(weeks):
        totals = weeks[w]["totals"]
        out.append({"week": w, "n": len(totals), "median_total": int(median(totals)) if totals else None,
                    "max_total": max(totals) if totals else None, "unmeasured": weeks[w]["unmeasured"]})
    return out
