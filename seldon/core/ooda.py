"""AD-038-R16, R17 and R18 (SEL-014R): the OODA between chained tasks as a knowledge source, and the mechanical retry.

`docs/design/AD-038_ADDENDUM_07_the_ooda_as_a_knowledge_source.md`.

**The shape is a blackboard** (Hearsay-II, Erman et al. 1980; Hayes-Roth 1985). The graph, the task files and the
ledger are the board. A knowledge source fires on a condition of the board's state and writes back; a control
component chooses what fires and records the result. Here there are two knowledge sources and one control:

* the OODA (R16) fires on "a completed task with an open successor and no OODA record". It is a headless Claude Code
  session, because orienting on a RESULT is judgment. This module composes its brief, reads its verdict and turns it
  into exactly one of four records; `seldon.commands.dispatch_ooda` launches it under the pass lease.
* the registration retry (R18) fires on "a registration refused for a mechanical cause". Each cause has one known
  repair, so it is a rule table and makes no model call.
* the dispatcher is the control. It alone writes a record, after checking what the session claims (AD-037: a
  session's claim is not a fact until checked).

c18 reads the records through :func:`record_index`; R17 makes the OODA advisory: only a predecessor whose OODA is
still due, or whose latest record is `ooda_blocked`, holds its successor.
"""
from __future__ import annotations

import json
import os
import re
import shlex
from datetime import date
from pathlib import Path
from typing import Callable

# ================================================================================================ records (R16)

OODA_OK = "ooda_ok"
OODA_AMENDED = "ooda_amended"
OODA_BLOCKED = "ooda_blocked"
OODA_EXPIRED = "ooda_expired"
#: The knowledge source's four records, one per OODA run.
RECORD_KINDS = (OODA_OK, OODA_AMENDED, OODA_BLOCKED, OODA_EXPIRED)
#: A Desktop's record (AD-038-R10's event, `seldon dispatch ooda record`). Under R17 it releases, and it is how a
#: Desktop answers a block.
DESKTOP_RECORDED = "ooda_recorded"
#: The verdict a session returns, and the record each becomes.
VERDICTS = {"ok": OODA_OK, "amended": OODA_AMENDED, "blocked": OODA_BLOCKED}
#: Why a run is `ooda_expired`. A closed set, so the record and the RESULT speak one vocabulary.
EXPIRED_REASONS = ("timeout", "token_cap", "launch_failed", "exit_nonzero", "no_verdict", "verdict_unreadable",
                   "addendum_missing", "addendum_misnamed", "addendum_commit_refused")

#: The line a session's last message carries. Protocol text, not a tunable.
VERDICT_PREFIX = "OODA-VERDICT:"

#: The predecessor states that left a RESULT to read (AD-038-R10's set, unchanged).
PREDECESSOR_STATES = ("completed", "verified")
#: The successor states an OODA serves: the ones the dispatcher could still launch.
SUCCESSOR_STATES = ("proposed", "accepted")

#: An addendum's name: `<successor stem>_ADDENDUM_<NN>_<slug>.md`, the convention's form
#: (`docs/conventions/desktop_ooda.md` section 3). `ADDENDUM-NN` is squiddy's spelling and is read for numbering too.
_ADDENDUM_NN_RE = re.compile(r"_ADDENDUM[_-](\d+)")
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_]*$")

#: `dispatch.ooda` when absent: off, so installing this build changes no project's queue. The cap and the role are
#: the task's (SEL-014R Spend: "cap at 0.3M per OODA run"); `inspect_every_s` is how often the holder reads the
#: session's tokens and clock, small against the timeout so a reap lands close to the bound.
OODA_DEFAULTS = {"enabled": False, "max_per_pass": 1, "token_cap": 300_000, "model_role": "primary",
                 "inspect_every_s": 15}


class OodaConfigError(ValueError):
    """`dispatch.ooda` (or `ooda_grace_s` under it) does not validate."""


def load_config(block: dict) -> dict:
    """`dispatch.ooda`, validated, with its defaults; `ooda_grace_s` must be above 0 when it is enabled (R17)."""
    raw = block.get("ooda")
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise OodaConfigError(f"dispatch.ooda must be a mapping, got {raw!r}")
    unknown = sorted(set(raw) - set(OODA_DEFAULTS))
    if unknown:
        raise OodaConfigError(f"dispatch.ooda has unknown key(s) {unknown}; known: {sorted(OODA_DEFAULTS)}")
    out = {**OODA_DEFAULTS, **raw}
    if not isinstance(out["enabled"], bool):
        raise OodaConfigError(f"dispatch.ooda.enabled must be a bool, got {out['enabled']!r}")
    for key in ("max_per_pass", "token_cap"):
        v = out[key]
        if isinstance(v, bool) or not isinstance(v, int) or v < 1:
            raise OodaConfigError(f"dispatch.ooda.{key} must be a positive whole number, got {v!r}")
    v = out["inspect_every_s"]
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
        raise OodaConfigError(f"dispatch.ooda.inspect_every_s must be a positive number of seconds, got {v!r}")
    if not isinstance(out["model_role"], str) or not out["model_role"].strip():
        raise OodaConfigError(f"dispatch.ooda.model_role must be a role name, got {out['model_role']!r}")
    if out["enabled"] and not block.get("ooda_grace_s"):
        raise OodaConfigError(
            "dispatch.ooda.enabled is true but dispatch.ooda_grace_s is 0 or absent: under AD-038-R17 it is the OODA "
            "session's wall-clock timeout, and a session with no bound is the one the timeout exists to stop")
    return out


def record_index(events: list) -> dict:
    """`{predecessor id: {kind, at, payload}}`, the latest OODA record per predecessor, whoever wrote it."""
    out = {}
    for e in events:
        kind = e.get("event_type")
        if kind not in RECORD_KINDS and kind != DESKTOP_RECORDED:
            continue
        p = e.get("payload") or {}
        if p.get("task_id"):
            out[p["task_id"]] = {"kind": kind, "at": e.get("timestamp"), "payload": p}
    return out


def released_by(kind: str | None) -> str | None:
    """c18's `released_by` for a predecessor's latest record: the record's kind, `ooda_event` for a Desktop's (the
    name AD-038-R10 gave it), None for a block or no record."""
    if kind is None or kind == OODA_BLOCKED:
        return None
    return "ooda_event" if kind == DESKTOP_RECORDED else kind


def due(tasks: list, latest: dict, completed_at: dict, has_file: Callable[[dict], bool]) -> list:
    """The OODAs due now, oldest completion first: `[{predecessor, successors, completed_at}]`.

    One per predecessor with a `proposed` or `accepted` successor in `tasks` (the pass's open tasks) and no record:
    no knowledge-source or Desktop record in `latest`, and no committed `<stem>_OODA.md` (`has_file`)."""
    by_pred: dict = {}
    for t in tasks:
        if t.get("state") not in SUCCESSOR_STATES:
            continue
        for p in t.get("predecessors") or []:
            pid = p.get("artifact_id")
            if not pid or p.get("state") not in PREDECESSOR_STATES or pid in latest:
                continue
            row = by_pred.setdefault(pid, {"predecessor": p, "successors": [],
                                           "completed_at": completed_at.get(pid) or p.get("updated_at")})
            row["successors"].append(t)
    rows = [r for r in by_pred.values() if not has_file(r["predecessor"])]
    return sorted(rows, key=lambda r: (str(r["completed_at"] or ""), r["predecessor"]["artifact_id"]))


# ================================================================================================ the brief

def result_path(source_file: str) -> str:
    p = Path(source_file)
    return str(p.with_name(p.stem + "_RESULT.md"))


def next_addendum_prefix(project_dir: Path, source_file: str) -> str:
    """`cc_tasks/<stem>_ADDENDUM_<NN>_`: one more than the highest addendum number the successor has, else 01."""
    p = Path(project_dir) / source_file
    nums = [int(m.group(1)) for a in p.parent.glob(f"{p.stem}_ADDENDUM*.md")
            if (m := _ADDENDUM_NN_RE.search(a.name[len(p.stem):]))]
    nn = max(nums, default=0) + 1
    return str(Path(source_file).with_name(f"{p.stem}_ADDENDUM_{nn:02d}_"))


def brief(project_dir: Path, config: dict, item: dict, review: Callable[[Path, str], dict],
          recall_hits: Callable[[str, str, str], tuple]) -> dict:
    """What the dispatcher hands the session (R16 "What it reads").

    `review(project_dir, text)` is station (a)'s premise run (`stations.review_premises`); `recall_hits(text, stem,
    task_id)` returns `(hit lines, note or None)`. Both are seams so a test can supply them."""
    from seldon.core import dispatch as D

    project_dir = Path(project_dir)
    pred = item["predecessor"]
    pred_rel = pred.get("source_file") or ""
    res_rel = result_path(pred_rel) if pred_rel else None
    pred_text = ""
    if pred_rel and (project_dir / pred_rel).is_file():
        pred_text = (project_dir / pred_rel).read_text(encoding="utf-8", errors="replace")
    hits, recall_note = recall_hits(pred_text, Path(pred_rel).stem, pred["artifact_id"]) if pred_text else (
        [], "the predecessor's task file is not on disk; no Recall")
    successors = []
    for t in item["successors"]:
        rel = t.get("source_file") or ""
        path = project_dir / rel
        text = path.read_text(encoding="utf-8", errors="replace") if rel and path.is_file() else ""
        premises = review(project_dir, text) if text else {"premises": []}
        successors.append({
            "task_id": t.get("artifact_id"), "name": t.get("name"), "file": rel,
            "addenda": [str(a.relative_to(project_dir)) for a in D.addenda_for(path)] if text else [],
            "addendum_prefix": next_addendum_prefix(project_dir, rel) if rel else None,
            "governing": (D._header_value(text, "Governing") or "").strip() or None,
            "premises": [{"statement": r.get("statement"), "kind": r.get("kind"), "outcome": r.get("outcome"),
                          "command": r.get("command"),
                          "tail": " ".join(((r.get("check") or {}).get("tail") or "").split())[-300:] or None}
                         for r in premises.get("premises") or []]})
    return {"predecessor": {"task_id": pred["artifact_id"], "name": pred.get("name"), "file": pred_rel,
                            "state": pred.get("state")},
            "result": res_rel, "result_exists": bool(res_rel and (project_dir / res_rel).is_file()),
            "recall": hits, "recall_note": recall_note, "successors": successors}


def prompt(b: dict) -> str:
    """The session's instruction: the brief, the three decisions, and the verdict line it must end on."""
    pred = b["predecessor"]
    out = [f"OODA (AD-038-R16, docs/design/AD-038_ADDENDUM_07_the_ooda_as_a_knowledge_source.md) on completed task "
           f"{pred['task_id'][:8]} {pred['file']}. You are a knowledge source, not a task session: observe, orient, "
           f"decide, and write at most one addendum file per successor in this worktree. Do not commit, merge, push, "
           f"register, or run any `seldon` command that writes; the dispatcher records your verdict.",
           "", "1. Run `seldon go --brief`.",
           f"2. Read the predecessor's RESULT in full: {b['result']}"
           + ("" if b["result_exists"] else " (NOT on disk: say so in your note)") + ". Then read each successor's "
           "task file and every addendum it already has, below."]
    for s in b["successors"]:
        out.append(f"   - successor {(s['task_id'] or '?')[:8]} {s['file']}"
                   + (f"; addenda: {', '.join(s['addenda'])}" if s["addenda"] else "; no addenda")
                   + (f"; governing: {s['governing']}" if s["governing"] else ""))
        for pr in s["premises"]:
            line = f"       premise ({pr['outcome']}): {pr['statement']}"
            if pr["command"]:
                line += f" | check: {pr['command']}"
            if pr["tail"] and pr["outcome"] != "true":
                line += f" -> {pr['tail']}"
            out.append(line)
    out.append("3. The dispatcher ran each successor's `check:` premises against HEAD; the outcomes are above. "
               "Recall for the predecessor (the repositories' own history nearest to it):")
    if b["recall"]:
        out.extend(f"   {h}" for h in b["recall"])
    else:
        out.append("   none")
    if b["recall_note"]:
        out.append(f"   (note: {b['recall_note']})")
    out.extend([
        "4. Orient: for each premise and Part of each successor, did the RESULT make it false or out of date (a moved "
        "path, a premise the predecessor made true or false, a number, a check that needs `sh -c`)? Read the "
        "governing notes named above where the RESULT touches them.",
        "5. Decide exactly one:",
        "   - ok: the RESULT changes nothing in any successor.",
        "   - amended: write the successor's next addendum in THIS worktree at exactly `<prefix><slug>.md`, slug "
        "lowercase letters, digits and underscores, with these prefixes: "
        + "; ".join(f"{s['addendum_prefix']}" for s in b["successors"] if s["addendum_prefix"]) + ". Begin it "
        "`# ADDENDUM <NN> to <successor stem>: <title>` and a line `**Author:** OODA knowledge source on "
        f"{pred['task_id'][:8]} (AD-038-R16)`. An addendum amends what the task does; it cannot supply a missing "
        "candidacy header, Parts or Premises (AD-038-R11). Do not commit it.",
        "   - blocked: the RESULT raises a question no ruling answers (a part the governing note did not decide, a "
        "finding that wants a new rule, a value call). Name the question and the design note that would answer it.",
        "6. End your final message with exactly one line, the JSON on one line:",
        f'{VERDICT_PREFIX} {{"verdict": "ok|amended|blocked", "note": "<one line>", "addenda": ["<path>", ...], '
        f'"question": "<blocked only>", "answering_note": "<blocked only: docs/design/...>"}}'])
    return "\n".join(out)


# ================================================================================================ the verdict

def parse_verdict(text: str | None) -> dict:
    """The session's last `OODA-VERDICT:` line: `{ok, verdict, note, addenda, question, answering_note}` or
    `{ok: False, reason, detail}` with `reason` `no_verdict` or `verdict_unreadable`."""
    lines = [ln.strip().strip("`").strip() for ln in (text or "").splitlines()]
    found = [ln for ln in lines if ln.startswith(VERDICT_PREFIX)]
    if not found:
        return {"ok": False, "reason": "no_verdict", "detail": f"no `{VERDICT_PREFIX}` line in the final message"}
    raw = found[-1][len(VERDICT_PREFIX):].strip()
    try:
        v = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {"ok": False, "reason": "verdict_unreadable", "detail": f"not JSON ({exc}): {raw[:200]}"}
    if not isinstance(v, dict) or v.get("verdict") not in VERDICTS:
        return {"ok": False, "reason": "verdict_unreadable",
                "detail": f"`verdict` must be one of {sorted(VERDICTS)}: {raw[:200]}"}
    note = v.get("note")
    addenda = v.get("addenda") or []
    if isinstance(addenda, str):
        addenda = [addenda]
    out = {"ok": True, "verdict": v["verdict"], "note": note if isinstance(note, str) else None,
           "addenda": addenda, "question": v.get("question"), "answering_note": v.get("answering_note")}
    if not isinstance(addenda, list) or not all(isinstance(a, str) and a for a in addenda):
        return {"ok": False, "reason": "verdict_unreadable", "detail": f"`addenda` must be a list of paths: {raw[:200]}"}
    if v["verdict"] == "amended" and not addenda:
        return {"ok": False, "reason": "addendum_missing", "detail": "verdict `amended` names no addendum"}
    if v["verdict"] == "blocked" and not all(isinstance(out[k], str) and out[k].strip()
                                             for k in ("question", "answering_note")):
        return {"ok": False, "reason": "verdict_unreadable",
                "detail": "verdict `blocked` must name its `question` and the `answering_note` that would answer it"}
    return out


def check_addenda(b: dict, addenda: list, worktree: Path | None, project_dir: Path) -> dict:
    """Each named addendum is a successor's next addendum, exists in the session's worktree and not yet in the
    primary: `{ok, files: [{rel, data}]}` or `{ok: False, reason, detail}`."""
    prefixes = [s["addendum_prefix"] for s in b["successors"] if s["addendum_prefix"]]
    files = []
    for rel in addenda:
        pre = next((p for p in prefixes if rel.startswith(p)), None)
        slug = rel[len(pre):-3] if pre and rel.endswith(".md") else None
        if pre is None or not slug or not _SLUG_RE.match(slug):
            return {"ok": False, "reason": "addendum_misnamed",
                    "detail": f"{rel} is not `<prefix><slug>.md` for any of {prefixes}"}
        if (Path(project_dir) / rel).exists():
            return {"ok": False, "reason": "addendum_misnamed", "detail": f"{rel} already exists in the primary"}
        src = Path(worktree) / rel if worktree else None
        if src is None or not src.is_file():
            return {"ok": False, "reason": "addendum_missing",
                    "detail": f"{rel} is not in the session's worktree {worktree}"}
        files.append({"rel": rel, "data": src.read_bytes()})
    return {"ok": True, "files": files}


def record_payload(b: dict, kind: str, *, verdict: dict | None = None, reason: str | None = None,
                   detail: str | None = None, session: dict | None = None, addenda: list | None = None,
                   commit: str | None = None) -> dict:
    """One record's payload. Every record names the predecessor (`task_id`, which c18 reads), the successors it
    read, the session's tokens and log, and, for `ooda_expired`, why."""
    if kind == OODA_EXPIRED and reason not in EXPIRED_REASONS:
        raise ValueError(f"ooda_expired needs a reason in {EXPIRED_REASONS}, got {reason!r}")
    pred = b["predecessor"]
    out = {"task_id": pred["task_id"], "name": pred.get("name"), "result": b["result"],
           "successors": [{"task_id": s["task_id"], "file": s["file"]} for s in b["successors"]],
           "by": "knowledge_source"}
    if verdict and verdict.get("ok"):
        out["note"] = verdict.get("note")
    if kind == OODA_BLOCKED:
        out.update({"question": verdict["question"], "answering_note": verdict["answering_note"]})
    if kind == OODA_AMENDED:
        out.update({"addenda": addenda or [], "commit": commit})
    if kind == OODA_EXPIRED:
        out.update({"reason": reason, "detail": detail})
    out["session"] = session or {}
    return out


# ================================================================================================ R18: the retry

#: The refusal codes R18 retries. Each is the prefix the refusing gate writes (AD-038-R13, AD-038-R5).
NUMBER_TAKEN = "number_taken"
PREMISE_FALSE = "premise_false"
MECHANICAL_CODES = (NUMBER_TAKEN, PREMISE_FALSE)

#: The event a retry writes, on the task when it registered.
EVENT_REGISTRATION_RETRIED = "registration_retried"

RULE_NEXT_NUMBER = "next_number"
RULE_SH_C = "sh_c"
RULE_STALE_EVIDENCE = "stale_evidence"

#: Shell syntax the premise runner passes to argv literally (it execs, it runs no shell; AD-038-R5), so a check that
#: uses any of it means what it says only under `sh -c`.
_SHELL_SYNTAX_RE = re.compile(r"&&|\|\||;|\||\$\(|`|>|<|\$[A-Za-z_{]")
#: The path-existence forms the stale-evidence rule narrows. Anything else that names a missing path (a `grep` on
#: it, a `cat`) is not mechanical: narrowing it would change what the premise claims.
_PATH_TESTS = ("-e", "-f", "-d", "-s")


def mechanical_code(refusal: str) -> str | None:
    """The mechanical code a refusal starts with, else None."""
    head = (refusal or "").lstrip()
    return next((c for c in MECHANICAL_CODES if head.startswith(c + ":")), None)


def _checked_path(command: str) -> str | None:
    try:
        argv = shlex.split(command)
    except ValueError:
        return None
    if len(argv) == 3 and argv[0] == "test" and argv[1] in _PATH_TESTS:
        return argv[2]
    if len(argv) == 2 and argv[0] == "ls" and not argv[1].startswith("-"):
        return argv[1]
    return None


def _toplevel(path: Path) -> Path | None:
    import subprocess
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=path, capture_output=True, text=True)
    return Path(r.stdout.strip()).resolve() if r.returncode == 0 else None


def stale_evidence_narrowing(project_dir: Path, task_text: str, command: str) -> dict | None:
    """R18's third rule for one false check: `{path, ancestor, command}` or None when it does not apply.

    Applies to `test -e|-f|-d|-s <path>` and `ls <path>` whose path is absent and lies in a repository the task
    names: this project's, or a sibling checkout `../<name>` whose name the task text carries."""
    project_dir = Path(project_dir).resolve()
    rel = _checked_path(command)
    if rel is None:
        return None
    target = Path(os.path.normpath(project_dir / os.path.expanduser(rel)))
    if target.exists():
        return None
    ancestor = target.parent
    while not ancestor.exists() and ancestor != ancestor.parent:
        ancestor = ancestor.parent
    top = _toplevel(ancestor)
    if top is None:
        return None
    own = _toplevel(project_dir)
    if top != own and top.name not in task_text:
        return None
    if top != ancestor.resolve() and top not in ancestor.resolve().parents:
        return None
    narrowed = os.path.relpath(ancestor, project_dir)
    return {"path": rel, "ancestor": narrowed, "command": f"test -d {shlex.quote(narrowed)}"}


def _replace_command(line: str, old: str, new: str) -> str:
    """`line` with its check's command `old` replaced by `new`, inside backticks when it was."""
    head, sep, rest = line.partition("check:")
    if not sep:
        raise ValueError(f"no `check:` on premise line {line!r}")
    if f"`{old}`" in rest:
        return head + sep + rest.replace(f"`{old}`", f"`{new}`", 1)
    if old not in rest:
        raise ValueError(f"the check {old!r} is not on premise line {line!r}")
    return head + sep + rest.replace(old, new, 1)


def repair_premises(project_dir: Path, text: str, false_rows: list, today: str) -> dict | None:
    """R18's premise rules over every false premise: `{text, changes}`, or None unless EVERY false premise has a
    rule (a premise that is simply false is reported as today, not half-repaired)."""
    lines = text.splitlines(keepends=True)
    changes = []
    for r in false_rows:
        cmd, n = r.get("command"), r.get("line")
        if r.get("kind") != "check" or not cmd or not n:
            return None
        before = lines[n - 1]
        if _SHELL_SYNTAX_RE.search(cmd) and not cmd.startswith("sh -c "):
            after = _replace_command(before, cmd, f"sh -c {shlex.quote(cmd)}")
            rule = RULE_SH_C
        else:
            nar = stale_evidence_narrowing(project_dir, text, cmd)
            if nar is None:
                return None
            after = _replace_command(before, cmd, nar["command"])
            stmt = r.get("statement") or ""
            mark = f"{stmt} [stale_evidence: {nar['path']} absent at registration {today}]"
            if stmt and stmt in after:
                after = after.replace(stmt, mark, 1)
            rule = RULE_STALE_EVIDENCE
        lines[n - 1] = after
        changes.append({"rule": rule, "line": n, "before": before.rstrip("\n"), "after": after.rstrip("\n")})
    return {"text": "".join(lines), "changes": changes} if changes else None


def renumbered_name(name: str, new_token: str) -> str:
    """`<date>_<TOKEN><rest>` with its token (and any `R<n>` re-filing mark) replaced by `new_token`."""
    from seldon.core import numbering as N
    tok = N.file_token(name)
    if tok is None:
        raise ValueError(f"{name} carries no task number")
    head = name[:11]                                  # `YYYY-MM-DD_`
    return head + new_token + name[len(head) + len(str(tok)):]


def retitled(text: str, old_token: str, new_token: str) -> tuple:
    """The text with the first occurrence of `old_token` in its title line replaced: `(text, change or None)`."""
    lines = text.splitlines(keepends=True)
    for i, ln in enumerate(lines):
        if ln.startswith("# "):
            if old_token not in ln:
                return text, None
            new = ln.replace(old_token, new_token, 1)
            lines[i] = new
            return "".join(lines), {"rule": RULE_NEXT_NUMBER, "line": i + 1, "before": ln.rstrip("\n"),
                                    "after": new.rstrip("\n")}
    return text, None


def today_iso() -> str:
    return date.today().isoformat()


def _tracked(project_dir: Path, rel: str) -> bool:
    from seldon.core import dispatch as D
    return D.git(project_dir, "ls-files", "--error-unmatch", "--", rel).returncode == 0


def _commit_repair(project_dir: Path, paths: list, message: str) -> None:
    """Commit a tracked task file's repair, path-scoped, through the hooks; a refusal raises (nothing is retried)."""
    from seldon.core import dispatch as D
    done = D.git(project_dir, "commit", "-m", message, "--", *paths)
    if done.returncode != 0:
        raise ValueError(f"the AD-038-R18 repair could not be committed: {(done.stderr or done.stdout).strip()}")


def repair(project_dir: Path, task_path: Path, *, holders: Callable[[], list], allocate: Callable[[str], str],
           review: Callable[[Path, str], dict], today: str | None = None) -> dict | None:
    """R18's rules over a refused task file, applied: `{path, rel, original, rules, changes, tracked}`, or None when
    no rule applies or a false premise has none (the refusal is then reported as today and the file is untouched).

    Every mechanical cause is looked for, not only the one the refusal named: registration stops at its first
    refusal, so a file with a shell check AND a taken number would otherwise need two retries."""
    from seldon.core import dispatch as D
    from seldon.core import numbering as N

    project_dir = Path(project_dir)
    rel = str(Path(task_path).relative_to(project_dir))
    text = Path(task_path).read_text(encoding="utf-8", errors="surrogateescape")
    changes, new_rel = [], rel
    bad = review(project_dir, text).get("false") or []
    if any(r.get("outcome") == "unreadable" for r in bad):
        return None
    if bad:
        fixed = repair_premises(project_dir, text, bad, today or today_iso())
        if fixed is None:
            return None
        text, changes = fixed["text"], list(fixed["changes"])
    tok = N.file_token(rel)
    if tok is not None:
        taken, _open = N.registration_refusal(rel, holders())
        if taken:
            new_token = allocate(tok.prefix)
            new_rel = str(Path(rel).with_name(renumbered_name(Path(rel).name, new_token)))
            text, title = retitled(text, str(tok), new_token)
            changes.append({"rule": RULE_NEXT_NUMBER, "line": None, "before": rel, "after": new_rel})
            if title:
                changes.append(title)
    if not changes:
        return None
    tracked = _tracked(project_dir, rel)
    if new_rel != rel:
        if (project_dir / new_rel).exists():
            raise ValueError(f"the AD-038-R18 renumbering target {new_rel} already exists")
        if tracked:
            mv = D.git(project_dir, "mv", "--", rel, new_rel)
            if mv.returncode != 0:
                raise ValueError(f"the AD-038-R18 renumbering could not move {rel}: {mv.stderr.strip()}")
        else:
            (project_dir / rel).rename(project_dir / new_rel)
    (project_dir / new_rel).write_text(text, encoding="utf-8", errors="surrogateescape")
    rules = sorted({c["rule"] for c in changes})
    if tracked:
        D.git(project_dir, "add", "--", new_rel)
        _commit_repair(project_dir, list(dict.fromkeys([rel, new_rel])),
                       f"register: {new_rel} repaired for one retry ({', '.join(rules)}) (AD-038-R18)")
    return {"path": project_dir / new_rel, "rel": new_rel, "original": rel, "rules": rules, "changes": changes,
            "tracked": tracked}


def retry_registration(project_dir: Path, task_path: Path, first_refusal: str, *,
                       register: Callable[[Path], dict], holders: Callable[[], list],
                       allocate: Callable[[str], str], review: Callable[[Path, str], dict],
                       record: Callable[[dict], None], today: str | None = None) -> dict | None:
    """R18: None when the refusal has no mechanical cause or no rule applies (the caller reports it as today).
    Otherwise one retry: the registration's outcome with `retried` (the record) added; a second refusal raises
    `ValueError` naming the retry. Either way `record` receives the one `registration_retried` payload."""
    code = mechanical_code(first_refusal)
    if code is None:
        return None
    fix = repair(project_dir, task_path, holders=holders, allocate=allocate, review=review, today=today)
    if fix is None:
        return None
    payload = {"file": fix["rel"], "original_file": fix["original"], "first_refusal_code": code,
               "first_refusal": first_refusal[:2000], "rules": fix["rules"], "changes": fix["changes"],
               "rule_of": "AD-038-R18"}
    try:
        out = register(fix["path"])
    except ValueError as exc:
        record({**payload, "outcome": "refused_again", "second_refusal": str(exc)[:2000], "task_id": None})
        raise ValueError(f"{exc} (after one mechanical retry under AD-038-R18, rules {', '.join(fix['rules'])}; "
                         f"the first refusal was: {first_refusal[:300]})") from exc
    payload = {**payload, "outcome": "registered", "task_id": out.get("artifact_id")}
    record(payload)
    return {**out, "retried": payload}
