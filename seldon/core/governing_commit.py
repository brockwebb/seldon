"""Registration verifies and commits the governing design note with the task (SEL-006 Part A).

**The condition.** A Desktop session has no git: everything it writes is untracked until a tool
commits it. `seldon cc register` already commits the task file (DN-006 ADDENDUM_03 §2;
`ai-readiness-kg/cc_tasks/2026-09-18_registration_commits.md`). The design note the task names
was committed by nothing until the executing session's Step 0, so the dispatcher's c7 (dirty tree)
refused the launch, the operator pasted a launch line, and twice in one week a Desktop session
edited a note after a running session had committed it (Issues 231c255c, 1fed4254).

**What registration now does**, for each note under the design directory that the task's
`**Governing:**`, `**Implements:**`, `**Amended by:**` or `**Resolves:**` block names (DESK-001) (a path, or an AD-/DN- identifier) and that git does not track or
that has uncommitted changes, counting its addenda:

1. `verify` (before anything is created): re-run the note's prior-art receipts and record the
   verdict (AD-036-R4), in a project that declares a `prior_art:` block and for a gated note
   outside the baseline. Until DESK-001 a FAIL refused the registration and committed nothing,
   which left the note untracked and stalled the whole queue on c7. Under AD-036 ADDENDUM 05 (R13)
   a FAIL is a HOLD: the note commits as a `draft:` with the task, the verdict ledger is staged
   with it, and the dispatcher refuses this task as `governing_unverified` until the note passes.
2. `plan` (before anything is created): find each labelled ruling in the note that the register
   has no record for, and build its record from the note's bytes (AD-033-R3: verbatim source,
   `decided_by: desktop`; AD-033-R4: a Desktop decision under L4 is accepted when registered). A
   label the register cannot parse, a label another note's accepted record holds, or a record the
   schema refuses, refuses the registration as `ruling_unrecorded`. AD-033-R8's statement pass is
   a model call and stays with the executing session; the verbatim body is the statement until it
   runs, as at every earlier registration of rulings (PA-001, QC-001).
3. `commit` (after every other refusal, before the task's node is created): write the records,
   stage the notes, their pending addenda, the task file when untracked, the register files, the
   rendered register and the verdict ledger, and make ONE path-scoped commit through the hooks
   (never `--no-verify`). A refused commit unstages what it staged, removes the register files it
   wrote, restores the rendered register and refuses as `governing_note_uncommitted`.

**Order: records before commit.** The task left two orders open. Records-before-commit is taken
because `decisions.create` is the register's one write path (AD-033-R2), takes no model call, and
removes the executing session's Step 0 entirely; the alternative (refuse until a person records
them) keeps the paste this exists to remove.

**A note edited after an earlier commit is a new commit**, never an amend: history is the record
(AD-033-R11), and an amend would rewrite a commit a running session may hold.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from seldon.core import dispatch as D

#: Refusal reasons, the first token of the refusal text.
UNVERIFIED = "governing_note_unverified"
UNRECORDED = "ruling_unrecorded"
UNCOMMITTED = "governing_note_uncommitted"

#: The design directory when the project declares no `prior_art:` gate.
DEFAULT_DESIGN_DIR = "docs/design"
#: Addenda and errata: never a governing note of their own, always staged with their base note.
DEFAULT_EXEMPT = ("*_ADDENDUM_*.md", "*_erratum_*.md")

#: The task-header blocks whose design notes registration commits with the task. SEL-006 read
#: `**Governing:**` alone; DESK-001 Part A step 2 adds the other three a Desktop task names notes in,
#: because a note named there and left untracked stalled the queue on c7 just the same.
GOVERNING_HEADERS = ("Governing", "Implements", "Amended by", "Resolves")
_GOVERNING_BLOCK_RE = re.compile(
    r"^\*\*(?:" + "|".join(re.escape(h) for h in GOVERNING_HEADERS)
    + r"):\*\*(.*?)(?=^\*\*[A-Z][^*]*:\*\*|^#|\Z)", re.MULTILINE | re.DOTALL)
_ID_RE = re.compile(r"\b((?:AD|DN)-\d{3})\b")
_NOTE_ID_RE = re.compile(r"^(?:\d{4}-\d{2}-\d{2}_)?((?:AD|DN)-\d{3})(?=_|\.md$)")


@dataclass
class Pending:
    """One governing note registration must commit: the note and every path of it git lacks."""
    note: str                                   # the base note, project-relative
    paths: list = field(default_factory=list)   # the note and/or addenda that are untracked or dirty


@dataclass
class Plan:
    """What `commit` writes and stages, computed before anything is created."""
    pending: list = field(default_factory=list)       # [Pending]
    records: list = field(default_factory=list)       # [dict] register records to accept
    ledger_paths: list = field(default_factory=list)  # verdict ledger / query log to stage
    verdicts: list = field(default_factory=list)      # [(note, verdict)] recorded by `verify`


def remedy(refusal: str) -> str:
    """The fix line for a refusal of this module, by its reason."""
    if refusal.startswith(UNVERIFIED):
        return ("`seldon prior-art verify <note>` until it passes; a note's prior-art section is completed by an "
                "addendum, never by editing it (AD-036-R4)")
    if refusal.startswith(UNRECORDED):
        return ("label each ruling in a form `decisions.design_notes` captures, numbered from the register "
                "(`seldon decision list`); then register again. " + DIRTY_LINE)
    return ("re-run with --allow-untracked so registration commits what it verified, or clear what refused the "
            "commit (the hook's findings above) and register again. " + DIRTY_LINE)


#: DESK-001 Part A step 2: a refused registration commits nothing, so what Desktop wrote is still
#: untracked, and that stalls the whole queue, not this task. Said in one line on every such refusal.
DIRTY_LINE = ("Until the files above are committed (`seldon commit-governed <path>`, or the "
              "`seldon_commit_governed` MCP tool) or removed, the dispatcher refuses EVERY task on c7 "
              "(dirty_tree).")


def hold_line(note: str, why: str) -> str:
    """The one line registration prints for a governing note without a passing verdict (DESK-001)."""
    return (f"HOLD: {note}: {why}. Registered and committed as a draft; the dispatcher refuses this task "
            f"as governing_unverified until `seldon prior-art verify {note}` passes (AD-036 ADDENDUM 05).")


def _design_settings(project_dir: Path, config: dict) -> tuple[str, tuple]:
    pa_block = config.get("prior_art")
    if isinstance(pa_block, dict):
        from seldon.core import prior_art as pa
        s = pa.settings(project_dir, config)
        return s.design_dir, tuple(s.exempt_globs)
    return DEFAULT_DESIGN_DIR, DEFAULT_EXEMPT


def _fnmatch(pattern: str, name: str) -> bool:
    from fnmatch import fnmatchcase
    return fnmatchcase(name, pattern)


def _base_of(project_dir: Path, rel: str, design_dir: str, exempt: tuple) -> Optional[str]:
    """The base note an addendum or erratum belongs to, or `rel` itself for a base note."""
    name = Path(rel).name
    if not any(_fnmatch(g, name) for g in exempt):
        return rel
    m = _NOTE_ID_RE.match(name)
    if not m:
        return None
    for p in sorted((project_dir / design_dir).glob(f"*{m.group(1)}_*.md")):
        own = _NOTE_ID_RE.match(p.name)
        if own and own.group(1) == m.group(1) and not any(_fnmatch(g, p.name) for g in exempt):
            return p.relative_to(project_dir).as_posix()
    return None


def governing_notes(task_text: str, project_dir: Path, config: dict) -> list[str]:
    """The base design notes of THIS project the task's `GOVERNING_HEADERS` blocks name.

    A `docs/design/...md` path in the block counts (an addendum path counts as its base note), and
    so does each AD-/DN- identifier, resolved to `<design_dir>/[date_]<id>_*.md`. A name that does
    not resolve here (another repository's note) is not this registration's to commit.
    """
    project_dir = Path(project_dir).resolve()
    design_dir, exempt = _design_settings(project_dir, config)
    path_re = re.compile(r"(?:^|[\s`(/])((?:[\w.\-]+/)*" + re.escape(design_dir) + r"/[\w.\-/]+\.md)")
    found = set()
    for block in _GOVERNING_BLOCK_RE.findall(task_text):
        for m in path_re.finditer(block):
            raw = m.group(1)
            rel = raw[raw.find(design_dir + "/"):]
            if (project_dir / rel).is_file():
                base = _base_of(project_dir, rel, design_dir, exempt)
                if base:
                    found.add(base)
        for ident in _ID_RE.findall(block):
            for p in sorted((project_dir / design_dir).glob(f"*{ident}_*.md")):
                own = _NOTE_ID_RE.match(p.name)
                if own and own.group(1) == ident and not any(_fnmatch(g, p.name) for g in exempt):
                    found.add(p.relative_to(project_dir).as_posix())
    return sorted(found)


def _addenda(project_dir: Path, note: str, exempt: tuple) -> list[str]:
    p = project_dir / note
    m = _NOTE_ID_RE.match(p.name)
    if not m:
        return []
    out = []
    for q in sorted(p.parent.glob(f"*{m.group(1)}_*.md")):
        own = _NOTE_ID_RE.match(q.name)
        if q != p and own and own.group(1) == m.group(1) and any(_fnmatch(g, q.name) for g in exempt):
            out.append(q.relative_to(project_dir).as_posix())
    return out


def uncommitted(project_dir: Path, rel: str) -> bool:
    """True when git does not track `rel`, or its working copy or index differs from HEAD."""
    r = D.git(project_dir, "status", "--porcelain", "--untracked-files=all", "--", rel)
    if r.returncode != 0:
        return True
    return bool(r.stdout.strip())


def pending_notes(task_text: str, project_dir: Path, config: dict) -> list[Pending]:
    """Each governing note with something git does not hold: the note, or one of its addenda."""
    project_dir = Path(project_dir).resolve()
    _design, exempt = _design_settings(project_dir, config)
    out = []
    for note in governing_notes(task_text, project_dir, config):
        paths = [r for r in [note] + _addenda(project_dir, note, exempt) if uncommitted(project_dir, r)]
        if paths:
            out.append(Pending(note=note, paths=paths))
    return out


# --------------------------------------------------------------------------------------- verify

def verify(project_dir: Path, config: dict, pending: list[Pending], library=None) -> tuple[list, list[str]]:
    """Run and record the prior-art verdict for each pending gated note (AD-036-R4).

    Returns ``([(note, verdict payload)], [refusal text])``. A project with no `prior_art:` block,
    a note outside the gate, and a baseline note are not verified (the gate is per project, and
    the baseline is grandfathered). ``library`` replaces the library arm (tests).
    """
    from seldon.core import prior_art as pa

    if not isinstance(config.get("prior_art"), dict) or not pending:
        return [], []
    s = pa.settings(project_dir, config)
    base = pa.baseline(s)
    internal = pa.Internal(s)
    library = library or pa.Library(s)
    done, refusals = [], []
    for pn in pending:
        if not pa.is_gated(s, pn.note) or pn.note in base:
            continue
        v = pa.verify_note(Path(project_dir) / pn.note, s, internal=internal, library=library)
        pa.record_verdict(v, project_dir, config)
        done.append((pn.note, v.as_payload()))
        if v.verdict != pa.PASS:
            refusals.append(f"{UNVERIFIED}: {pn.note}: prior-art verdict is fail (recorded): "
                            + "; ".join(v.problems))
    return done, refusals


# ----------------------------------------------------------------------------------------- plan

def plan_records(project_dir: Path, config: dict, pending: list[Pending], task_rel: str,
                 date: Optional[str] = None) -> tuple[list[dict], list[str]]:
    """The register records registration writes, and any refusal, before anything is written.

    Only notes absent from the register's baseline tree are read (the same notes `seldon verify`
    and the commit hook require records for), and only labels with no record yet.
    """
    from seldon.core import decisions as dr
    from seldon.core.hooks import LABEL_TAKEN

    s = dr.settings(project_dir, config)
    if s is None:
        return [], []
    u = dr.Universe(s)
    records, refusals = [], []
    for pn in pending:
        for rel in pn.paths:
            if not dr.is_design_note(s, rel):
                continue
            if s.baseline_commit and dr._in_tree(s.root, s.baseline_commit, rel):
                continue
            path = Path(project_dir) / rel
            text = path.read_text(encoding="utf-8")
            for _rel, line, label in dr.unparsed_labels_in(s, rel, text):
                refusals.append(f"{UNRECORDED}: {rel}:{line} {label} is in a heading or bold position and no "
                                f"`decisions.design_notes` pattern captures it ({dr.UNPARSED}, AD-036 section 6.1)")
            sha = dr.sha256_file(path)
            lines = text.splitlines()
            seen = set()
            for qid, label, start, end in dr.labeled_spans_in(s, rel, text):
                if qid in seen:
                    continue                    # the first span of an id is its ruling
                seen.add(qid)
                have = u.get(qid)
                if have is not None:
                    holder = (have.get("source") or {}).get("path")
                    if holder and holder != rel and have.status == dr.BINDING:
                        refusals.append(f"{UNRECORDED}: {rel}:{start} declares {qid}, which the accepted record "
                                        f"already holds for {holder} ({LABEL_TAKEN}); "
                                        f"number the ruling from the register (`seldon decision list`)")
                    continue
                body = "\n".join(lines[start - 1:end]).strip()
                local = qid.split(":", 1)[1]
                rec = {"id": qid, "kind": "decision", "statement": body,
                       "source": {"path": rel, "lines": [start, end], "sha256": sha, "text": body},
                       "scope": [s.repository], "rationale": {"path": rel, "anchor": label}}
                cons = dr.cited_by(local, s.root, s.consumer_roots)
                if cons:
                    rec["consumer"] = cons
                else:
                    rec["review_only"] = "none"
                event = dict(rec, event="accept", date=date or dr.today(), decided_by="desktop",
                             operator_stated=False, receipts=[task_rel], reason=_reason(task_rel))
                event["status"] = "accepted"
                try:
                    dr._check_shape_or_refuse(event)
                except dr.RegisterError as exc:
                    refusals.append(f"{UNRECORDED}: {rel}:{start} {qid}: {exc}")
                    continue
                records.append(rec)
    return records, refusals


def _reason(task_rel: str) -> str:
    return (f"recorded by `seldon cc register` of {task_rel} from the governing note's bytes (SEL-006 Part A; "
            f"AD-033-R3, R4: a Desktop decision under L4 is accepted when registered); the AD-033-R8 statement "
            f"pass stays with the executing session")


# --------------------------------------------------------------------------------------- commit

def commit(project_dir: Path, config: dict, plan: Plan, task_rel: str, task_untracked: bool,
           message: str, date: Optional[str] = None) -> tuple[Optional[str], Optional[str]]:
    """Write the planned records and make ONE commit of everything registration verified.

    Returns ``(full sha, None)`` or ``(None, refusal text)``. On a refusal the working tree is
    as it was before this call, save the verdict ledger's recorded lines.
    """
    from seldon.core import decisions as dr

    project_dir = Path(project_dir).resolve()
    written: list[Path] = []
    rendered_rel, rendered_before = None, None
    s = dr.settings(project_dir, config)
    if plan.records and s is not None:
        u = dr.Universe(s)
        rendered = project_dir / s.rendered
        rendered_rel = s.rendered
        rendered_before = rendered.read_bytes() if rendered.is_file() else None
        try:
            for rec in plan.records:
                written += dr.create(u, "accept", rec, date=date or dr.today(), decided_by="desktop",
                                     operator_stated=False, receipts=[task_rel], reason=_reason(task_rel))
            if u.register(s.repository).exists():
                dr.write_rendered(dr.universe(project_dir, config))
        except dr.RegisterError as exc:
            _undo(project_dir, [], written, rendered_rel, rendered_before)
            return None, f"{UNRECORDED}: {exc}"
    paths = []
    for pn in plan.pending:
        paths += pn.paths
    if task_untracked:
        paths.append(task_rel)
    paths += [p.relative_to(project_dir).as_posix() for p in written]
    if rendered_rel and (project_dir / rendered_rel).is_file():
        paths.append(rendered_rel)
    paths += plan.ledger_paths
    paths = list(dict.fromkeys(paths))
    out = D.commit_paths(project_dir, paths, message)
    if not out.get("committed"):
        _undo(project_dir, [x for x in paths if (project_dir / x).exists()], written, rendered_rel,
              rendered_before)
        return None, (f"{UNCOMMITTED}: the commit of {', '.join(paths)} was refused "
                      f"({out.get('reason')}): {out.get('stderr', '')}".rstrip(": "))
    head = D.git(project_dir, "rev-parse", "HEAD").stdout.strip()
    return head, None


def _undo(project_dir: Path, staged: list, written: list, rendered_rel: Optional[str],
          rendered_before: Optional[bytes]) -> None:
    """Put the tree back as `commit` found it: unstage, remove the register files it wrote, restore
    the rendered register. The register's chain is intact again because only its tail was written."""
    if staged:
        if D.git(project_dir, "rev-parse", "--verify", "-q", "HEAD").returncode == 0:
            D.git(project_dir, "reset", "-q", "--", *staged)
        else:
            D.git(project_dir, "rm", "--cached", "-q", "--ignore-unmatch", "--", *staged)
    for p in written:
        p.unlink(missing_ok=True)
    if rendered_rel:
        target = Path(project_dir) / rendered_rel
        if rendered_before is None:
            target.unlink(missing_ok=True)
        else:
            target.write_bytes(rendered_before)


def ledger_paths(project_dir: Path, config: dict, verdicts: list) -> tuple[list[str], Optional[str]]:
    """The prior-art files `verify` appended to, to stage with the note so the hook judges the
    staged verdict (HOOK-001), and a refusal when one carries lines that are not prior-art lines
    (someone else's appends, which this commit must not sweep up)."""
    from seldon.core import prior_art as pa

    if not verdicts:
        return [], None
    out = []
    accepts = {pa.settings(project_dir, config).log: pa._is_log_line,
               pa.verdict_ledger(project_dir, config): pa._is_verdict_line}
    for p, accept in accepts.items():
        rel = pa._rel_to(project_dir, p)
        if rel is None or not p.is_file():
            continue
        if D.git(project_dir, "check-ignore", "-q", "--", rel).returncode == 0:
            continue
        if not uncommitted(project_dir, rel):
            continue
        why = pa._appended_lines_ok(project_dir, rel, accept)
        if why:
            return [], (f"{UNCOMMITTED}: {rel} carries uncommitted lines that are not prior-art lines "
                        f"({why}); registration will not commit them with the note")
        out.append(rel)
    return out, None
