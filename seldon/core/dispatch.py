"""The standing dispatcher's pure logic: candidacy, eligibility, the lease, the config.

`docs/design/2026-09-15_standing_dispatcher.md` in this repo describes the command group;
`ai-readiness-kg/docs/design/2026-09-15_DN-006_standing_dispatcher.md` is the design note this
implements, and its §3 decisions are the spec.

**The condition this closes.** A registered ResearchTask whose gate is clean waited in
`proposed` until a person relayed a dispatch line into Claude Code. Nothing about *which* task
to run was missing — only the act of starting it. That is a latency defect, and it is the only
one this module addresses (DN-006 §4 is explicit that post-completion decision latency is not
touched).

**Everything here is pure or filesystem-local.** No Neo4j, no subprocess, no launch. The command
module composes these against the graph; keeping the evaluation separable is what lets each
criterion be tested against a fixture task file that fails exactly that one.

Prior art the shape is taken from, read before designing (DN-006 §2): Airflow's scheduler claim
as a database row transition rather than a message; the Kubernetes `Lease` object's separation
of holder identity from the thing acted on; Chubby (Burrows, OSDI 2006) for advisory locks whose
holder is identified and whose release is never inferred from age alone.
"""
from __future__ import annotations

import fcntl
import fnmatch
import json
import os
import re
import shutil
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from seldon import models
from seldon.core import cadence as C
from seldon.core import worktree as WT
from seldon.core.moving import is_future

#: DN-006 decision 3, as corrected by this build's ADDENDUM_01 to that note. The marker survey
#: over 34 addenda in `ai-readiness-kg/cc_tasks/` found a `**Status:**` field in the first ten
#: lines to be an existing habit (5 files) with an upper-case verb vocabulary — `AMENDS` in
#: four, `SUPERSEDED` in one — but only ONE file has ever expressed base-task supersession, and
#: it spells it `**Status of base task: SUPERSEDED — DO NOT EXECUTE.**`
#: (`2026-09-01_harness_reconciliation_ADDENDUM-01.md`). One instance in 34 is not a convention,
#: so decision 3's `**Status:** SUPERSEDED` is what gets written from here on; the matcher also
#: accepts the one historical spelling, because the alternative is a dispatcher that reads the
#: single genuinely superseded task in the repository as executable.
#:
#: Case-sensitive on `SUPERSEDED` deliberately: `**Status:** AMENDS the base task. Does not
#: supersede it.` is four of the five Status lines, and lower-case `supersede` inside a sentence
#: saying the opposite is exactly what a case-insensitive match would read as a supersession.
SUPERSEDED_MARKER = "**Status:** SUPERSEDED"
SUPERSEDED_RE = re.compile(r"\*\*Status(?:\s+of\s+base\s+task)?\s*:?\*?\*?:?\s*[^*\n]*"
                           r"\bSUPERSEDED\b")
#: How far into an addendum the marker must appear. DN-006 decision 3.
MARKER_WINDOW_LINES = 10

#: The three headers a dispatchable task file must carry. The first two are DN-006 decision 2;
#: the third is ADDENDUM_01 to the implementing task, which binds DN-005 §5 rule 1 — every task
#: names the framework layer it advances, or says it is hygiene — to something other than a
#: reader's attention.
#:
#: The dispatcher does not judge whether the named layer is the RIGHT one. It asserts that a
#: layer was named, which is what the rule requires.
HEADER_SPEND = "Spend"
HEADER_NETWORK = "Network"
HEADER_LAYER = "Framework layer served"
REQUIRED_HEADERS = (HEADER_SPEND, HEADER_NETWORK, HEADER_LAYER)

#: SEL-010R2 Part B (AD-038-R11): the headers are a per-project list, `dispatch.candidacy_headers`, and these two are
#: the kit-wide minimum no project may drop: without `Spend` c4 has no number to hold against the band, and without
#: `Network` c5 has no declaration to refuse. `Framework layer served` is DN-005 §5 rule 1, ai-readiness-kg's
#: framework rule, which every project that adopted the dispatcher inherited by copying the constant. A project with
#: no `candidacy_headers` key keeps `REQUIRED_HEADERS`, so installing this build changes no project's candidates;
#: `seldon dispatch adopt` writes the minimum for a new project, which adds what its own rules require.
MINIMUM_HEADERS = (HEADER_SPEND, HEADER_NETWORK)

#: `**Spend:** zero model calls.` / `**Network:** none.` / `**Framework layer served (DN-005 §5
#: rule 1):** §2.2 Tier M.` — the same bolded-header shape `seldon cc register` already parses.
#: The header name may carry a parenthetical, which the third one does. One field; where it may
#: stand is the header block's business (:func:`header_block`, AD-038-R14).
_HEADER_RE_CACHE: dict[str, re.Pattern] = {}


def _header_re(name: str) -> re.Pattern:
    if name not in _HEADER_RE_CACHE:
        _HEADER_RE_CACHE[name] = re.compile(
            # The value starts at the closing `**`, not after its spaces: the reader matches on a line whose code
            # spans are blanked, and a value that opens with one (`**After:** \`<stem>\``) must not be skipped.
            r"\*\*" + re.escape(name) + r"(?:[ \t]*\([^)\n]*\))?[ \t]*:\*\*(?P<value>[^\n]*)"
            r"|\*\*" + re.escape(name) + r"(?:[ \t]*\([^)\n]*\))?[ \t]*:(?P<v2>[^*\n]*)\*\*"
            r"(?P<rest>[^\n]*)")
    return _HEADER_RE_CACHE[name]


#: AD-038-R14 (NUM-001R Part B): headers are read from the header block, never from prose. Before it the
#: first match ANYWHERE in the file won, so a header quoted in prose was read as the header: 2f5d4492 recorded
#: network_kind=cadence from a Supersedes sentence, and registration refused twice on 2026-09-22 for a prose
#: `**After:**`. The block is the file's preamble: the lines after the `# ` title up to the first `##` heading or
#: thematic break, fenced code excluded (RFC 5322 §2.1's header section, which ends where the body begins; the
#: Pandoc and MultiMarkdown metadata blocks are the Markdown form). Not "the contiguous header lines": over the 1,623
#: task files in ~/GitHub on 2026-10-27, authors separate header groups with blank lines and a sentence, so a
#: contiguity rule would have dropped 106 real Network headers; the preamble rule changed 10 reads, every one a prose
#: match or a legacy file.
#:
#: A header line STARTS with a bold label carrying a colon (`**Spend:** ...`, `- **Exclusive:** no`); a field later
#: on such a line is read too (`**Spend:** zero model calls. **Network:** none.`, a shape 79 files use), except
#: inside a backtick code span, which is how a header is quoted (`its \`**Network:**\` header opened with ...`).
_HEADER_LINE_RE = re.compile(r"^[ \t]*(?:[-*+][ \t]+)?\*\*[A-Za-z][^*\n]*:")
#: A colon-less label alone on its line, its value in the list under it (arnold KG-006's `**Spend**`); the reader
#: before AD-038-R14 accepted it, so the block reader does too.
_BARE_LABEL_RE = re.compile(r"^[ \t]*\*\*(?P<name>[A-Za-z][^*\n]*?)(?:[ \t]*\([^)\n]*\))?\*\*[ \t]*$")
_BLOCK_END_RE = re.compile(r"^(?:#{2,}[ \t]|[ \t]*(?:-[ \t]*){3,}$|[ \t]*(?:\*[ \t]*){3,}$|[ \t]*(?:_[ \t]*){3,}$)")
_FENCE_RE = re.compile(r"^[ \t]*(?:```|~~~)")
#: A list item or indented line under a header whose own line carries no value (`**Spend:**` then `- est. 6M ...`).
_CONTINUATION_RE = re.compile(r"^(?:[ \t]*(?:[-*+]|\d+[.)])[ \t]|[ \t]+\S)")
_CODE_SPAN_RE = re.compile(r"`+[^`\n]*`+")
#: The refusal code for a header the block carries twice.
HEADER_REPEATED = "header_repeated"


def header_block(text: str) -> list[tuple[int, str]]:
    """The header block as `(1-based line number, line)` pairs: after the title, before the first section."""
    lines = text.split("\n")
    start = next((i + 1 for i, line in enumerate(lines) if line.startswith("# ")), 0)
    out, fenced = [], False
    for i in range(start, len(lines)):
        line = lines[i]
        if _FENCE_RE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        if _BLOCK_END_RE.match(line):
            break
        out.append((i + 1, line))
    return out


def header_hits(text: str, name: str) -> list[tuple[int, str]]:
    """Every `**<name>:**` field in the header block, in order, as `(line number, raw value)`."""
    block = header_block(text)
    rx = _header_re(name)
    hits = []
    for k, (no, line) in enumerate(block):
        bare = _BARE_LABEL_RE.match(line)
        if bare and bare.group("name").strip() == name:
            values = [""]
        elif _HEADER_LINE_RE.match(line):
            # Masked to the same length, so a match's offsets index the original line.
            masked = _CODE_SPAN_RE.sub(lambda m: " " * len(m.group()), line)
            values = [line[m.start("value"):m.end("value")].strip() if m.group("value") is not None
                      else (line[m.start("v2"):m.end("v2")] + line[m.start("rest"):m.end("rest")]).strip()
                      for m in rx.finditer(masked)]
        else:
            continue
        for value in values:
            if not value:
                cont = []
                for _no, nxt in block[k + 1:]:
                    if not nxt.strip() or _HEADER_LINE_RE.match(nxt) or not _CONTINUATION_RE.match(nxt):
                        break
                    cont.append(nxt.strip())
                value = " ".join(cont)
            hits.append((no, value))
    return hits


def repeated_headers(text: str, names) -> list[dict]:
    """`{code, message}` for each of `names` the header block carries more than once (AD-038-R14)."""
    out = []
    for name in dict.fromkeys(names):
        hits = header_hits(text, name)
        if len(hits) > 1:
            out.append({"code": f"{HEADER_REPEATED}:{name}",
                        "message": (f"`**{name}:**` appears {len(hits)} times in the header block (lines "
                                    f"{', '.join(str(no) for no, _ in hits)}); the block carries each header once, "
                                    f"so keep one")})
    return out

#: A framework-layer value that satisfies ADDENDUM_01: a DN-005 §2 layer reference, a capability
#: tier, or the word `none` for a hygiene task.
_LAYER_VALUE_RE = re.compile(r"§\s?2\.[1-5]\b|\bTier\s+[MOD]\b|\bnone\b", re.IGNORECASE)
#: The same rule as text, quoted by every refusal that reads it (SEL-011; Issue 9965fbed asked for it beside
#: `NETWORK_GRAMMAR`).
LAYER_GRAMMAR = ("`**Framework layer served (DN-005 §5 rule 1):** <value>` where the value names a DN-005 §2 "
                 "reference (§2.1 to §2.5), a capability tier (Tier M, O or D), or `none` for a hygiene task")

#: `zero` in a Spend header means zero model calls. Anything else must name a token count that
#: the standing band can be compared against; `M`/`K` suffixes are the spelling the task files
#: and `--ceiling-tokens` already use.
_ZERO_RE = re.compile(r"\bzero\b", re.IGNORECASE)
_STRICT_TOKENS_RE = re.compile(r"(?P<n>\d[\d,_]*(?:\.\d+)?)\s*(?:(?P<suffix>[MmKk])\b(?:\s*tokens?\b)?|tokens?\b)")
_TOKENS_RE = re.compile(r"(?P<n>\d[\d,_]*(?:\.\d+)?)\s*(?P<suffix>[MmKk])?\s*(?:tokens?|$|[ .,;)])")

#: The Network header's grammar (ai-readiness-kg/cc_tasks/2026-09-18_network_allowlist.md
#: decision 1, amending DN-006 decision 2). Network is a declared budget, like Spend, and not a
#: binary: a task either contacts no host, or names the exact hosts it may contact, or carries
#: the cadence provenance decision 8 writes. `beyond git push` is implied by all three.
#:
#: The shape is an egress allowlist, the way CI runners and build sandboxes declare network
#: (Nix and Bazel deny by default and allow named fetches). It is DECLARATIVE: macOS offers no
#: cheap per-process egress filter, so the dispatcher enforces nothing at the socket. The
#: session-side fetch helper refuses off-list hosts and logs every request, and the RESULT
#: quotes that log — the same standing as the Spend header, a declared budget audited after.
NETWORK_GRAMMAR = ("`**Network:** none` (optionally followed by prose, e.g. `none beyond "
                   "git push`), or `**Network:** allowlist: host1, host2, ...` with exact "
                   "hostnames (no wildcards, no schemes, no paths, no ports), or "
                   "`**Network:** <hosts>, under cadence <name>`")

#: `none` must LEAD the value. It used to match anywhere, so `the hosts in §2, none else`
#: passed as if it declared no network; every surveyed task file that meant none says so
#: first (`none.`, `none beyond git push`, `NONE — ...`, a backticked `none`).
_NETWORK_NONE_RE = re.compile(r"^[\s`*_]*none\b", re.IGNORECASE)
#: The child's copy of a launched task's allowlist, comma-separated. The session-side fetch
#: helper refuses any host not on it and refuses to run at all when it is unset; the dispatcher
#: strips any inherited value, so a `none` task never runs with a stale list.
NETWORK_ALLOWLIST_ENV = "SELDON_NETWORK_ALLOWLIST"
_NETWORK_CADENCE_RE = re.compile(r"under\s+cadence\s+\S+", re.IGNORECASE)
_NETWORK_ALLOWLIST_RE = re.compile(r"^[\s`*_]*allowlist\s*:(?P<hosts>.*)$", re.IGNORECASE)
#: RFC 1123 host names: dot-separated labels of letters, digits and inner hyphens, each at most
#: 63 characters, the whole at most 253. Compared case-insensitively (RFC 4343) and stored
#: lower-case, so the child's list and the helper's comparison speak one spelling.
_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*$")

#: The OPTIONAL fourth header, read by `seldon cc register` and not by candidacy
#: (ai-readiness-kg/cc_tasks/2026-09-19_seldon_hygiene_superseded_cadence_after.md decision 3).
#:
#: **What it closes.** DN-007 records that SEQUENCING lines are "read into `precedes` edges
#: inconsistently". They are not read at all: a repo-wide `grep -rn -i sequencing seldon/` on
#: 2026-09-19 returned zero hits. `cc register` wrote no edge, dispatcher readiness reads
#: `precedes` edges only, and every such edge in ai-readiness-kg's graph was written by a
#: Desktop session calling `seldon_task_chain` by hand, when it remembered to. The sentence at
#: the end of a SEQUENCING line — "Not launched before `X.md` is `completed` on the graph" — is
#: prose the dispatcher cannot see, the same class as a supersession stated only in prose
#: (DN-006 ADDENDUM_01).
#:
#: Prior art, and the reason this is a separate header rather than a parser for the prose:
#: systemd's `After=` is an ORDERING-only declaration, deliberately separate from `Requires=`
#: (systemd.unit(5)) — which is exactly what `precedes` is, order and not requirement; Make
#: declares prerequisites where the scheduler reads them; Airflow's `set_upstream` is a call,
#: not a docstring. Every one of them puts the ordering in the machine-read place and leaves
#: the comment as a comment. The name is taken from systemd for that reason.
HEADER_AFTER = "After"
AFTER_GRAMMAR = ("`**After:** none`, or `**After:** <ref>[, <ref> ...]` where each ref is a "
                 "cc_tasks file stem (with or without `.md`) or an artifact id prefix of 8 or "
                 "more hex characters, optionally qualified `<project>:<ref>` for a task in "
                 "another project's graph (a cross-project wait, AD-038-R8)")
#: `none` must LEAD the value, for the reason `_NETWORK_NONE_RE` gives: a `none` matched
#: anywhere would read "after the scan, none of the report tasks" as declaring no predecessor.
_AFTER_NONE_RE = re.compile(r"^[\s`*_]*none\b", re.IGNORECASE)
#: A ref: a path-free stem, optionally `.md`, optionally backticked, optionally with a
#: `cc_tasks/` prefix that is stripped. No globs and no directories, so a ref names one file.
_AFTER_REF_RE = re.compile(r"^(?:cc_tasks/)?(?P<stem>[A-Za-z0-9][A-Za-z0-9._-]*?)(?:\.md)?$")
#: An artifact id prefix. Eight hex characters is what `short()` prints and what every task
#: file and commit message in these projects quotes.
AFTER_ID_MIN_HEX = 8
_AFTER_ID_RE = re.compile(r"^[0-9a-f]{%d,}$" % AFTER_ID_MIN_HEX)
#: SEL-008 (AD-038-R8): `<project>:<ref>`, a ref in another project's graph. `cc register` records it as a
#: cross-project wait on the created task (the other graph is read, never written); the ref is resolved there by the
#: same rule a local ref is. The project is a directory-style name, so no `:` or `/` inside it.
_AFTER_XREF_RE = re.compile(r"^(?P<project>[A-Za-z0-9][A-Za-z0-9._-]*):(?P<ref>.+)$")


def parse_after(value: str | None) -> dict:
    """The After header against :data:`AFTER_GRAMMAR`: `{kind, refs, error}`.

    `kind` is `none` or `refs` when the value parses, and `None` when it does not — in which
    case `error` says which part failed and quotes the grammar. The header is OPTIONAL: a
    `value` of None is `{"kind": "absent"}`, which means no edges, as before this existed.
    """
    if value is None:
        return {"kind": "absent", "refs": [], "error": None}
    stripped = value.strip()
    if not stripped:
        return {"kind": None, "refs": [],
                "error": f"After header is empty; expected {AFTER_GRAMMAR}"}
    if _AFTER_NONE_RE.match(stripped):
        return {"kind": "none", "refs": [], "error": None}
    # A trailing sentence period is prose, the way it is in the Network header's allowlist.
    stripped = stripped[:-1] if stripped.endswith(".") else stripped
    items = [r.strip().strip("`").strip() for r in stripped.split(",")]
    refs, bad = [], []
    for item in items:
        x = _AFTER_XREF_RE.match(item)
        m = _AFTER_REF_RE.match(x.group("ref") if x else item)
        if not item or not m:
            bad.append(item)
            continue
        stem = f"{x.group('project')}:{m.group('stem')}" if x else m.group("stem")
        if stem not in refs:
            refs.append(stem)
    if bad:
        return {"kind": None, "refs": [],
                "error": (f"After header entries are not refs: "
                          f"{', '.join(repr(b) for b in bad)}; expected {AFTER_GRAMMAR}")}
    return {"kind": "refs", "refs": refs, "error": None}


def after_ref_is_id(ref: str) -> bool:
    """True when a ref may also be read as an artifact id prefix."""
    return bool(_AFTER_ID_RE.match(ref))


#: SEL-013R (AD-036-R16): the OPTIONAL header of a task that answers a filing from another repository. Its one value
#: names the filing, qualified by the repository it came from, and that repository is where the answer's return task
#: is filed (`seldon.core.returns`). The grammar is read here, with the other static checks; whether the filing
#: exists in that repository's graph is read by registration, which may open another graph.
HEADER_ANSWERS = "Answers"
ANSWERS_UNRESOLVED = "answers_unresolved"
ANSWERS_GRAMMAR = ("`**Answers:** <repo>:<ref>`, one filing: the consumer repository's name (its directory, or "
                   "seldon.yaml `tasks.projects`) and the filing's task number (`HB-37`), cc_tasks file stem or "
                   "artifact id prefix")


def parse_answers(value: str | None) -> dict:
    """The Answers header against :data:`ANSWERS_GRAMMAR`: `{kind, project, ref, error}`.

    `kind` is `absent` (no header), `ref` (parses) or None (does not, and `error` says why). One filing per task: a
    task that answers two filings files two returns, and a list would leave which RESULT section feeds which return
    to an ordering rule nobody can see.
    """
    if value is None:
        return {"kind": "absent", "project": None, "ref": None, "error": None}
    item = value.strip()
    item = item[:-1] if item.endswith(".") else item
    item = item.strip().strip("`").strip()
    x = _AFTER_XREF_RE.match(item)
    m = _AFTER_REF_RE.match(x.group("ref")) if x else None
    if not x or not m:
        return {"kind": None, "project": None, "ref": None,
                "error": f"Answers header {value.strip()!r} is not one qualified ref; expected {ANSWERS_GRAMMAR}"}
    return {"kind": "ref", "project": x.group("project"), "ref": m.group("stem"), "error": None}


# ------------------------------------------------------- concurrency: Exclusive and Touches

#: The two OPTIONAL concurrency headers (seldon `cc_tasks/2026-10-07_SEL-004_worktree_per_task
#: _dispatch.md` decision 1, AD-034).
#:
#: **What it closes.** ai-readiness-kg DN-013-R3 said "the precedes graph already says which
#: tasks are independent". It does not: a `precedes` edge records an ordering a Desktop wrote
#: down, and its absence says nothing about whether two tasks write the same files or the same
#: database. Independence is therefore DECLARED per task, by resource, and the scheduler never
#: infers it. Prior art: GitHub Actions `concurrency` groups (the author names the lock key)
#: and the declared outputs of Make and Bazel (the author names what a step writes).
#:
#: `Exclusive` defaults to `yes`: a task with neither header runs alone, exactly as every task
#: did before this existed.
HEADER_EXCLUSIVE = "Exclusive"
HEADER_TOUCHES = "Touches"
CONCURRENCY_HEADERS = (HEADER_EXCLUSIVE, HEADER_TOUCHES)
CONCURRENCY_GRAMMAR = (
    "`**Exclusive:** yes` or `**Exclusive:** no` (absent means yes), and "
    "`**Touches:** none` or `**Touches:** <item>, <item>, ...` where each item is a resource "
    "named under `dispatch.resources` in seldon.yaml or a repository-relative path glob "
    "(fnmatch syntax; a trailing `/` means the whole directory; `./name` for a root file "
    "whose name has no dot; no absolute paths, no `..`, no whitespace). A task with "
    "`Exclusive: no` must carry `Touches`")
_EXCLUSIVE_RE = re.compile(r"^[\s`*_]*(?P<v>yes|no)\b", re.IGNORECASE)
_TOUCHES_NONE_RE = re.compile(r"^[\s`*_]*none\b", re.IGNORECASE)
#: A bare word is a resource NAME and must be configured: a typo such as `neo4J` that fell
#: through to a path glob would silently overlap nothing, which is the one failure a lock
#: declaration may not have.
_RESOURCE_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
_GLOB_CHARS = "*?["


#: The concurrency headers are read from the header block like every other (AD-038-R14), which is what their own
#: line anchor was for: they are read from every candidate in serial mode as well, and a task file that quotes the
#: grammar in prose (the SEL-004 task does, inside a list item and backticks) would otherwise be read as a malformed
#: declaration and refused.
def parse_concurrency_headers(text: str) -> dict:
    """The two optional headers as raw values; `None` where absent."""
    return {name: _header_value(text, name) for name in CONCURRENCY_HEADERS}


def _touch_item(item: str, resources: dict) -> tuple:
    """`("resource", name)`, `("path", glob)`, or `("error", message)` for one Touches item."""
    if not item:
        return ("error", "empty item")
    if _RESOURCE_NAME_RE.match(item):
        if item in resources:
            return ("resource", item)
        known = ", ".join(sorted(resources)) or "none configured"
        return ("error", f"unknown resource {item!r} (configured: {known}; write "
                         f"`./{item}` for a root path)")
    path = item[2:] if item.startswith("./") else item
    parts = path.split("/")
    if (not path or path.startswith("/") or "\\" in path or any(c.isspace() for c in path)
            or ".." in parts):
        return ("error", f"{item!r} is not a repository-relative path glob")
    return ("path", path)


def parse_concurrency(exclusive: str | None, touches: str | None, resources: dict) -> dict:
    """The concurrency declaration against :data:`CONCURRENCY_GRAMMAR`.

    Returns `{declared, exclusive, resources, paths, error}`. `declared` is False when the
    task carries neither header, which is the pre-SEL-004 task: exclusive, touching
    everything. `error` names what failed and quotes the grammar, as the Network header's
    refusal does.
    """
    out = {"declared": exclusive is not None or touches is not None, "exclusive": True,
           "resources": [], "paths": [], "error": None}

    def fail(msg):
        return {**out, "error": f"{msg}; expected {CONCURRENCY_GRAMMAR}"}

    if exclusive is not None:
        m = _EXCLUSIVE_RE.match(exclusive)
        if not m:
            return fail(f"Exclusive header {exclusive!r} is not yes or no")
        out["exclusive"] = m.group("v").lower() == "yes"
    if touches is None:
        if not out["exclusive"]:
            return fail("a non-exclusive task must declare Touches")
        return out
    raw = touches.strip()
    if not raw:
        return fail("Touches header is empty")
    if _TOUCHES_NONE_RE.match(raw):
        return out
    # A sentence-ending period is prose, as in the Network allowlist and the After header.
    raw = raw[:-1] if raw.endswith(".") else raw
    for item in (i.strip().strip("`").strip() for i in raw.split(",")):
        kind, value = _touch_item(item, resources)
        if kind == "error":
            return fail(f"Touches item: {value}")
        bucket = out["resources"] if kind == "resource" else out["paths"]
        if value not in bucket:
            bucket.append(value)
    return out


def _literal_bounds(glob: str) -> tuple:
    """The literal text before the first wildcard and after the last, and whether any exists."""
    first = min((glob.index(c) for c in _GLOB_CHARS if c in glob), default=None)
    if first is None:
        return glob, glob, False
    ends = [glob.rindex(c) for c in "*?" if c in glob]
    if "[" in glob and "]" in glob[glob.index("["):]:
        ends.append(glob.rindex("]"))
    return glob[:first], glob[max(ends) + 1:], True


def _expand_dir(glob: str) -> list:
    """A trailing `/` is the whole directory; a literal path may be a file or a directory."""
    if glob.endswith("/"):
        return [glob + "**"]
    if not any(c in glob for c in _GLOB_CHARS):
        return [glob, glob + "/**"]
    return [glob]


def _pair_may_overlap(a: str, b: str) -> bool:
    pa, sa, wild_a = _literal_bounds(a)
    pb, sb, wild_b = _literal_bounds(b)
    if not wild_a and not wild_b:
        return a == b
    # One literal side is decided exactly: the only path it names is itself. fnmatch's `*`
    # crosses `/`, which is broader than a shell glob, so exact here is still conservative.
    if not wild_a or not wild_b:
        literal, wild = (a, b) if not wild_a else (b, a)
        return fnmatch.fnmatchcase(literal, wild)
    return ((pa.startswith(pb) or pb.startswith(pa))
            and (sa.endswith(sb) or sb.endswith(sa)))


def globs_may_overlap(a: str, b: str) -> bool:
    """Can some path match both globs? Sound, deliberately not exact.

    Any path matching an fnmatch glob begins with the glob's literal prefix (the text before
    its first wildcard) and ends with its literal suffix (the text after its last). A path
    matching both globs therefore begins with both prefixes, so one is a prefix of the other,
    and the same holds for the suffixes. When either pair is unrelated the globs are disjoint;
    otherwise they are treated as overlapping. The error is one-sided: an unnecessary wait,
    never two writers on one file.
    """
    a, b = _normalize_glob(a), _normalize_glob(b)
    return any(_pair_may_overlap(x, y) for x in _expand_dir(a) for y in _expand_dir(b))


def _normalize_glob(glob: str) -> str:
    """One spelling per path: `//` and `.` segments collapsed, and lower-cased because the
    default macOS file system is case-insensitive, so `Docs/x` and `docs/x` are one file.
    Lower-casing can only add overlaps, which is the safe direction. A trailing `/` is kept:
    it means "the whole directory"."""
    trailing = glob.endswith("/")
    parts = [p for p in glob.split("/") if p not in ("", ".")]
    out = "/".join(parts).lower()
    return out + "/" if trailing and out else out


def _all_paths(conc: dict, resources: dict) -> list:
    paths = list(conc.get("paths") or [])
    for name in conc.get("resources") or []:
        paths += list((resources.get(name) or {}).get("paths") or [])
    return paths


def touches_overlap(a: dict, b: dict, resources: dict) -> list:
    """What two non-exclusive declarations share: resource names, then `glob ~ glob` pairs.

    A named resource's configured paths take part in the path comparison, so `views` and a
    raw `site/app.js` collide when `views` names `site/`.
    """
    shared = [r for r in a.get("resources") or [] if r in (b.get("resources") or [])]
    for x in _all_paths(a, resources):
        for y in _all_paths(b, resources):
            if globs_may_overlap(x, y):
                pair = f"{x + '**' if x.endswith('/') else x} ~ {y}"
                if pair not in shared:
                    shared.append(pair)
    return shared


def plan_launches(candidates: list, running: list, max_parallel: int, resources: dict) -> dict:
    """Which of the otherwise-eligible candidates launch this pass, and why the rest wait.

    Args:
        candidates: `{task_id, concurrency}` rows in FIFO order (decision 9), each eligible
            on every criterion except concurrency.
        running: `{task_id, concurrency}` for every task a dispatcher claim holds.
        max_parallel: `dispatch.max_parallel`.
        resources: `dispatch.resources`.

    Returns:
        `{"launch": [task_id, ...], "deferred": {task_id: {reason, with, overlap}}}`.
        `reason` is `exclusive_waits` (an exclusive task waiting for others to finish),
        `exclusive` (something exclusive holds or is waiting for everything), `overlap`
        (shared Touches) or `max_parallel`.

    **Waiting tasks hold their resources.** A candidate deferred for any reason reserves what
    it declared, so a later candidate that overlaps it cannot overtake it when a slot frees:
    FIFO per resource, the way GitHub Actions queues a concurrency group. A waiting EXCLUSIVE
    candidate reserves everything, so later candidates wait behind it rather than starve it:
    writer preference, the second readers-writers problem (Courtois, Heymans and Parnas,
    CACM 1971).
    """
    held = [{"task_id": r["task_id"], "concurrency": r["concurrency"]} for r in running]
    slots = max_parallel - len(running)
    launch, deferred = [], {}
    for cand in candidates:
        c = cand["concurrency"]
        if c["exclusive"]:
            if held:
                deferred[cand["task_id"]] = {"reason": "exclusive_waits",
                                             "with": [h["task_id"] for h in held],
                                             "overlap": []}
            elif slots > 0:
                launch.append(cand["task_id"])
                slots -= 1
            held.append(cand)
            continue
        excl = [h["task_id"] for h in held if h["concurrency"]["exclusive"]]
        if excl:
            deferred[cand["task_id"]] = {"reason": "exclusive", "with": excl, "overlap": []}
        else:
            hits = [(h["task_id"], touches_overlap(h["concurrency"], c, resources))
                    for h in held]
            hits = [(tid, ov) for tid, ov in hits if ov]
            if hits:
                deferred[cand["task_id"]] = {
                    "reason": "overlap", "with": [tid for tid, _ in hits],
                    "overlap": list(dict.fromkeys(o for _, ov in hits for o in ov))}
            elif slots <= 0:
                deferred[cand["task_id"]] = {"reason": "max_parallel",
                                             "with": [r["task_id"] for r in running]
                                             + launch, "overlap": []}
            else:
                launch.append(cand["task_id"])
                slots -= 1
        held.append(cand)
    return {"launch": launch, "deferred": deferred}


#: Predecessor states that let a successor run (DN-006 decision 2, c2). `blocked` and `rejected`
#: are deliberately absent: a successor whose predecessor is blocked is a successor whose
#: premise nobody has checked.
PREDECESSOR_SATISFIED = ("completed", "verified", "superseded", "withdrawn")

#: The states a task may be dispatched from (c1).
DISPATCHABLE_STATES = ("proposed", "accepted")

#: DN-006 decision 7's event names.
EVENT_LAUNCHED = "dispatch_launched"
EVENT_FINISHED = "dispatch_finished"
EVENT_REFUSED = "dispatch_refused"
EVENT_OBSERVED_STOP = "dispatch_observed_stop"
#: DN-006 decision 8's. A cadence that created a task asserted that a period was due and that
#: nothing had served it yet; that is a judgement and it goes on the log. A cadence that created
#: NOTHING writes no event, for decision 7's reason — a five-minute poll that logged its own
#: silence would bury the assertions in it.
EVENT_CADENCE_CREATED = "cadence_created"
#: A candidate refused on the same criterion for `dispatch.stuck_after_passes` consecutive
#: passes (ADDENDUM_01 to ai-readiness-kg/cc_tasks/2026-09-19_seldon_hygiene_superseded_cadence
#: _after.md, decision 6b). The incident: 84 consecutive passes over seven hours printed
#: `65e5da0e dirty_tree: c7`, exit 0, no event, no notification, while one untracked task file
#: sat in `cc_tasks/`. Every refusal reason reachable from the quiet branch is a STANDING
#: condition, so decision 7 rightly forbids logging each pass — but a queue that can stop needs
#: a staleness alarm SEPARATE from its failure alarm. Prior art: the dead man's switch; Nagios
#: freshness checks; Prometheus `absent()` with a `for:` duration. A healthy exit code on a
#: pass that has refused the same candidate 84 times is the case those exist for.
EVENT_STUCK = "dispatch_stuck"
#: Passes on one criterion before the alarm. `seldon.yaml dispatch.stuck_after_passes`; at the
#: standing `poll_interval_s: 300` the default is fifteen minutes. **No measured basis**, like
#: `poll_interval_s` itself, and it says so in the config file.
STUCK_AFTER_PASSES_DEFAULT = 3
#: Per-criterion overrides of `stuck_after_passes` (`dispatch.stuck_after_passes_by_criterion`).
#: DESK-001 Part B step 6: `dirty_tree` alarms on the FIRST refused pass. A dirty tree refuses the
#: whole queue, not one task, and the three recorded stalls (2026-09-22, 3 hours; 2026-10-12, 36
#: hours; 2026-10-14, 14 hours) were each a Desktop write nobody committed, found by reading the log.
#: Fifteen minutes of grace bought nothing there: the condition never clears by itself.
STUCK_AFTER_PASSES_BY_CRITERION_DEFAULT = {"dirty_tree": 1}
#: The last pass's refusals, for `seldon go` (DESK-001 Part B step 5). Beside the streak file,
#: under the gitignored lease directory: what the last pass saw is local state, not a record.
LAST_PASS_FILE = "dispatch_last_pass.json"
#: Test override of the last-pass file's path, as `STUCK_STATE_ENV` is for the streak file.
LAST_PASS_ENV = "SELDON_DISPATCH_LAST_PASS"
#: Where the streak is kept. Under `.seldon/`, which is gitignored: a count of passes is local
#: state and not a project record. The EVENT is the record.
STUCK_STATE_FILE = "dispatch_stuck.json"

#: The finish notification's failure (ai-readiness-kg/cc_tasks/2026-09-17_dispatcher_notifies.md
#: decision 1). A notifier that ran is not an event: the finish it reports is already on the log.
#: A notifier that did not run, failed or hung is one, because it is the only trace that the
#: operator was never told.
EVENT_NOTIFY_FAILED = "dispatch_notify_failed"

#: FRICTION-002 Part B: a task that ended unmerged keeps its worktree and branch, and says so with the branch
#: name and the reason; a merged task's worktree is removed by the sweep, which records each removal.
EVENT_WORKTREE_KEPT = "worktree_kept"
EVENT_WORKTREE_REMOVED = "worktree_removed"

#: How long the finish notifier may run before it is killed. Decision 1 of the task above: a
#: desktop or push notifier returns in well under a second, and a notifier that is still running
#: after thirty has hung — it must not hold the lease, and with it every later pass, hostage.
#: Overridable per project as `dispatch.notify_timeout_s`.
NOTIFY_TIMEOUT_S_DEFAULT = 30

#: Refusal reasons. A closed set, so `status` and the log speak one vocabulary.
REFUSAL_REASONS = ("lease_held", "stop_file", "disabled", "dirty_tree", "above_band",
                   "network_undeclared", "api_key_present", "claim_failed",
                   # SEL-004: a Exclusive/Touches declaration that does not parse (c10), and a
                   # task whose worktree path or branch is already taken (c11).
                   "concurrency_undeclared", "worktree_unavailable",
                   # c7's other two halves, which were reported as `dirty_tree` until
                   # ai-readiness-kg/cc_tasks/2026-10-09_main_green_dispatch_stuck_without_a_path
                   # .md decision 3: a checkout on another branch (or a detached HEAD) with no
                   # dirty path, and a git read that failed. `dirty_tree` now always names a path.
                   "wrong_branch", "tree_unreadable",
                   # QC-002 (AD-037-R6 a): a false premise, and a sibling dispatcher's lease on this project's
                   # environment.
                   "premise_false", "environment_in_flight",
                   # DESK-001 (AD-036 ADDENDUM 05): a governing design note without a passing
                   # prior-art verdict, committed as a draft. R4's gate moved here from the commit.
                   "governing_unverified",
                   # FRICTION-001 Part E (AD-038-R6, Issue 59b2db84): Neo4j unreachable. Written once
                   # per outage, with one STUCK notification, instead of a traceback every pass.
                   "database_unavailable",
                   # SEL-008 (AD-038-R8, c17): a wait on a task in another project's graph that is not yet
                   # satisfied, and one whose other graph could not be read (not ready, never ready by default).
                   "waits_on_unsatisfied", "waits_on_unreachable",
                   # SEL-010R2 (AD-038-R10, c18): a chained task whose completed predecessor has no OODA record yet
                   # and whose grace has not run out.
                   "ooda_pending",
                   # SEL-011 (AD-038-R12): a Spend header that names neither `zero` nor a token count. c4 used to
                   # report it as `above_band`, which sent its reader to the band for a header that does not parse.
                   "spend_unreadable")

#: The outage file, beside the lease: `{first_seen, passes, error}` while the database is unreachable,
#: removed by the first pass that reaches it. Runtime state, gitignored with the lease.
OUTAGE_STATE_FILE = "dispatch_outage.json"

#: Points the stuck-streak file somewhere other than `<lease dir>/dispatch_stuck.json`. Unset in
#: production. A test that runs a REAL pass sets it to its own copy, so passes in two tests (or a
#: test and the launchd dispatcher in the same checkout) never advance each other's streaks: the
#: daily suite's three passes in four seconds counted as three polls and raised `dispatch_stuck`
#: on 2026-10-08 and 2026-10-09 (decision 4 of the task above). The `AIRKG_DISPATCH_LOG`
#: precedent: one variable, read at the one place the path is computed.
STUCK_STATE_ENV = "SELDON_DISPATCH_STUCK_STATE"

#: DD-007. The subscription-OAuth gate, the same one `kg/extraction/model_stub.py` enforces at
#: its own choke point: an inherited API key means a dispatched session would spend against a
#: credential nobody declared. Checked BEFORE any claim, so a refusal leaves no state change.
API_KEY_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")


class DispatchConfigError(ValueError):
    """The `dispatch:` block is missing, malformed, or names a reference that does not resolve."""


# --------------------------------------------------------------------------- configuration

#: Dispatch keys AD-035 retired: the lock names the CLI and the model.
FORBIDDEN_DISPATCH_KEYS = ("cli", "model")


def load_dispatch_config(project_dir: Path, config: dict | None = None) -> dict:
    """The project's `dispatch:` block, validated. Read at call time, never cached.

    DN-006 decision 2's c8 requires `enabled` and the STOP file to be read on *every* pass; a
    cached config would make the kill switch advisory, which is the one thing a kill switch may
    not be (DD-004).
    """
    if config is None:
        config = yaml.safe_load((project_dir / "seldon.yaml").read_text(encoding="utf-8"))
    block = (config or {}).get("dispatch")
    if block is None:
        raise DispatchConfigError(
            f"{project_dir}/seldon.yaml has no `dispatch:` block; the dispatcher is opt-in per "
            f"project and refuses to guess one")
    for key in ("enabled", "branch", "standing_band_ref", "poll_interval_s", "permission_mode",
                "stop_file", "log_dir", "lease_file"):
        if key not in block:
            raise DispatchConfigError(f"seldon.yaml dispatch block missing {key!r}")
    # AD-035 R3 and R4: the dispatcher execs the lock's CLI with the lock's id for the task's
    # role. A `cli` or `model` key here would be a second, unlocked source of both, so it is
    # refused rather than ignored: an operator who set one must learn it no longer applies.
    for key in FORBIDDEN_DISPATCH_KEYS:
        if key in block:
            raise DispatchConfigError(
                f"seldon.yaml dispatch.{key} is no longer read: sessions launch the CLI and model "
                f"in seldon's models/models.lock.yaml, for the task's `**Model:**` role or "
                f"`primary` (AD-035 R3, R4). Remove the key.")
    if not isinstance(block["enabled"], bool):
        raise DispatchConfigError(
            f"dispatch.enabled must be a bool, got {block['enabled']!r}: a kill switch that "
            f"can be a truthy string is a kill switch nobody can read")
    # DN-006 decision 8. Optional — a project with no schedule has no `cadence:` key — but an
    # entry that IS there is validated here, so an unreadable rule refuses at config load and
    # not at 00:00 on the first Monday, unattended, at the only moment it mattered.
    block["cadence"] = C.validate_cadence(block.get("cadence"))
    # The finish notifier. Optional; a value that IS there must be a non-empty command string,
    # checked here so an unusable notifier refuses at load and not after an hour-long task has
    # finished with nobody to tell.
    notify = block.get("notify")
    if notify is not None and (not isinstance(notify, str) or not notify.strip()):
        raise DispatchConfigError(
            f"dispatch.notify must be a non-empty shell command string, got {notify!r}")
    block["notify"] = notify
    # SEL-005: the launchd job that runs this project's passes. Optional; when given, `seldon go`
    # reports `dispatch: on` only while that job is loaded, because a config that says enabled with
    # no job running launches nothing and a Desktop session that believed otherwise would wait.
    label = block.get("launchd_label")
    if label is not None and (not isinstance(label, str) or not label.strip()):
        raise DispatchConfigError(f"dispatch.launchd_label must be a non-empty string, got {label!r}")
    block["launchd_label"] = label
    timeout = block.get("notify_timeout_s", NOTIFY_TIMEOUT_S_DEFAULT)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise DispatchConfigError(
            f"dispatch.notify_timeout_s must be a positive number of seconds, got {timeout!r}")
    block["notify_timeout_s"] = timeout
    # Decision 6b. Optional with a default, so installing this build changes no config file;
    # a value that IS there is validated at load for `notify_timeout_s`'s reason.
    stuck = block.get("stuck_after_passes", STUCK_AFTER_PASSES_DEFAULT)
    if isinstance(stuck, bool) or not isinstance(stuck, int) or stuck < 1:
        raise DispatchConfigError(
            f"dispatch.stuck_after_passes must be a positive whole number of passes, got "
            f"{stuck!r}")
    block["stuck_after_passes"] = stuck
    by = block.get("stuck_after_passes_by_criterion", STUCK_AFTER_PASSES_BY_CRITERION_DEFAULT)
    if not isinstance(by, dict) or any(
            k not in REFUSAL_REASONS + ("disk_short", "disk_unmeasured")
            or isinstance(v, bool) or not isinstance(v, int) or v < 1 for k, v in by.items()):
        raise DispatchConfigError(
            f"dispatch.stuck_after_passes_by_criterion must map refusal reasons to positive whole "
            f"numbers of passes, got {by!r}")
    block["stuck_after_passes_by_criterion"] = dict(by)
    # SQ-010 ADDENDUM 02 D3.4. Optional with a default, so installing this build changes no config file.
    factor = block.get("disk_need_factor", DISK_NEED_FACTOR_DEFAULT)
    if isinstance(factor, bool) or not isinstance(factor, (int, float)) or factor < 1:
        raise DispatchConfigError(
            f"dispatch.disk_need_factor must be a number of at least 1 (the launch's measured footprint is "
            f"multiplied by it), got {factor!r}")
    block["disk_need_factor"] = factor
    # SEL-010R2 (AD-038-R10): c18's grace. Optional with a default of 0, which never waits, so installing this build
    # changes no project's queue; a project opts in by naming how long a chain waits for its Desktop OODA.
    grace = block.get("ooda_grace_s", OODA_GRACE_S_DEFAULT)
    if isinstance(grace, bool) or not isinstance(grace, (int, float)) or grace < 0:
        raise DispatchConfigError(
            f"dispatch.ooda_grace_s must be a number of seconds, 0 or more (0 never waits), got {grace!r}")
    block["ooda_grace_s"] = grace
    # DISP-004R (AD-034-R12). Optional with defaults, so installing this build changes no config file.
    root = block.get("cross_repo_root", CROSS_REPO_ROOT_DEFAULT)
    if not isinstance(root, str) or not root.strip():
        raise DispatchConfigError(
            f"dispatch.cross_repo_root must be a directory path (relative to the project), got {root!r}")
    block["cross_repo_root"] = root
    xbranch = block.get("cross_repo_branch", CROSS_REPO_BRANCH_DEFAULT)
    if not isinstance(xbranch, str) or not xbranch.strip():
        raise DispatchConfigError(f"dispatch.cross_repo_branch must be a branch name, got {xbranch!r}")
    block["cross_repo_branch"] = xbranch
    block["candidacy_headers"] = load_candidacy_headers(block.get("candidacy_headers"))
    block["allow"] = _load_allow(block.get("allow"))
    _load_parallel_config(block)
    # QC-002: the stations' block, validated at load like every other key, so a misspelt ceiling refuses here.
    from seldon.core import stations as S
    try:
        scfg = S.load_stations_config(block, project_dir)
    except S.StationsConfigError as exc:
        raise DispatchConfigError(str(exc)) from exc
    # STATION-001 (AD-037-R15): the declared interpreter, resolved against this project, so every later
    # `load_stations_config(cfg)` reads the absolute path whatever its working directory.
    if scfg["interpreter"]:
        block["stations"] = {**block["stations"], "interpreter": scfg["interpreter"]}
    return block


def load_candidacy_headers(value) -> tuple:
    """`dispatch.candidacy_headers` (AD-038-R11): the headers a task file must carry to be a candidate.

    Absent: `REQUIRED_HEADERS`, the list every project read before this key existed. Present: a list of header names
    that contains `MINIMUM_HEADERS`, refused at load otherwise, so a project can add a header of its own and never
    drop the two c4 and c5 cannot run without."""
    if value is None:
        return REQUIRED_HEADERS
    # A tuple is this loader's own output: `seldon cc register`, called from a pass's cadence with the block the
    # pass already loaded, loads it again (SEL-011), and a loader that refuses what it returned refuses that.
    if not isinstance(value, (list, tuple)) or not value or not all(isinstance(v, str) and v.strip() for v in value):
        raise DispatchConfigError(
            f"dispatch.candidacy_headers must be a list of header names, got {value!r}")
    names = tuple(dict.fromkeys(v.strip() for v in value))
    missing = [h for h in MINIMUM_HEADERS if h not in names]
    if missing:
        raise DispatchConfigError(
            f"dispatch.candidacy_headers must include the kit-wide minimum {list(MINIMUM_HEADERS)}; missing "
            f"{missing} (c4 holds Spend against the band and c5 refuses an undeclared Network: AD-038-R11)")
    return names


#: The shape of one `dispatch.allow` rule: a Claude Code permission rule for the Bash tool with a non-empty pattern.
_ALLOW_RULE_RE = re.compile(r"^Bash\([^()]+\)$")


def _load_allow(value) -> list:
    """`dispatch.allow` (DISP-002 Part B, AD-034 ADDENDUM 02): the `permissions.allow` rules a dispatched session is
    launched with. Optional, default none. Each entry is `{rule, instruction}`: a Bash permission rule and the
    task-file instruction that needs it, quoted, so the reason a session may run a command without the classifier is
    in the file an operator reads. An entry without its instruction refuses at load."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise DispatchConfigError(f"dispatch.allow must be a list of {{rule, instruction}} entries, got {value!r}")
    out = []
    for entry in value:
        rule = entry.get("rule") if isinstance(entry, dict) else None
        why = entry.get("instruction") if isinstance(entry, dict) else None
        if not isinstance(rule, str) or not _ALLOW_RULE_RE.match(rule):
            raise DispatchConfigError(f"dispatch.allow rule must look like `Bash(<pattern>)`, got {entry!r}")
        if not isinstance(why, str) or not why.strip():
            raise DispatchConfigError(f"dispatch.allow rule {rule!r} must quote the task instruction that needs it")
        out.append({"rule": rule, "instruction": why})
    return out


#: `dispatch.max_parallel` when absent: one task at a time, the pre-SEL-004 dispatcher, which
#: `tests/test_dispatch_serial_transcript.py` holds byte for byte. Nothing changes in any
#: project until it opts in.
MAX_PARALLEL_DEFAULT = 1

#: Where every task's worktree lives and the branch it is cut on: the Claude Code CLI's own
#: convention for `claude --worktree <name>` (`<repo>/.claude/worktrees/<name>`, branch
#: `worktree-<name>`, observed on CLI 2.1.302 in `docs/evidence/friction002/`). FRICTION-002 Part
#: B (AD-034 ADDENDUM 01): the dispatcher cuts the worktree there and the CLI enters it, which
#: turns on the CLI's hard isolation. Fixed by the vendor, so not configuration: a
#: `dispatch.worktree_dir` or `dispatch.branch_prefix` key is refused at load.
CLI_WORKTREE_DIR = ".claude/worktrees"
CLI_BRANCH_PREFIX = "worktree-"
RETIRED_WORKTREE_KEYS = ("worktree_dir", "branch_prefix")

#: The worktree keys and their defaults (SEL-004, AD-034). Since FRICTION-002 every task runs in
#: a worktree, so they are filled in at every `max_parallel` and `status` shows the values in
#: force; only `gate_command` stays required for `max_parallel > 1` alone.
PARALLEL_DEFAULTS = {
    # One lease per worktree (decision 2): `<lease_dir>/<stem>.lock`, holder = supervisor.
    "lease_dir": ".seldon/leases",
    # Named resources a Touches header may use: name -> {paths: [globs], description}.
    "resources": {},
    # Files a worktree session writes in the PRIMARY checkout (decision 5): the pass commits
    # their appended lines under the file's own flock and c7 does not count them as dirt.
    "shared_paths": [],
    # Gitignored files a session needs, symlinked from the primary checkout into each
    # worktree (a worktree carries no gitignored file). FRICTION-002: `.env` by default, because
    # every task now runs in a worktree and every project here keeps its credentials there; a
    # path absent from the primary is skipped (`worktree.link`), so the default costs nothing.
    "worktree_links": [".env"],
    # Rebase-gate-merge rounds before a task whose main keeps moving is merge_blocked.
    # **No measured basis**: three is the declared starting value.
    "merge_attempts": 3,
    # How long a finishing supervisor waits for the pass lease before it gives up and leaves
    # the task for the stale-lease path. **No measured basis**; a pass is seconds long.
    "merge_lock_timeout_s": 600,
    # The re-gate's wall-clock ceiling. **No measured basis**: ai-readiness-kg's full suite
    # took 42 minutes on 2026-10-06 (DN-013 §2), and an hour leaves room for it.
    "gate_timeout_s": 3600,
    # The field that must be unique across every line of a `merge=union` file (decision 4).
    "union_unique_key": "event_id",
}


def _relative_glob_list(block: dict, key: str) -> list:
    value = block.get(key, PARALLEL_DEFAULTS[key])
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise DispatchConfigError(f"dispatch.{key} must be a list of non-empty strings, got "
                                  f"{value!r}")
    for v in value:
        if v.startswith("/") or ".." in v.split("/"):
            raise DispatchConfigError(f"dispatch.{key} entry {v!r} is not repository-relative")
    return value


def _load_parallel_config(block: dict) -> None:
    """Validate `max_parallel` always, and the parallel keys when it is above one.

    A parallel config that cannot be honoured refuses at load, never at the first merge: the
    re-gate needs a `gate_command` (decision 3), and a resource with no readable paths would
    be a lock that collides with nothing.
    """
    n = block.get("max_parallel", MAX_PARALLEL_DEFAULT)
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise DispatchConfigError(f"dispatch.max_parallel must be a positive whole number, got "
                                  f"{n!r}")
    block["max_parallel"] = n
    resources = block.get("resources", PARALLEL_DEFAULTS["resources"])
    if not isinstance(resources, dict):
        raise DispatchConfigError(f"dispatch.resources must be a mapping, got {resources!r}")
    for name, spec in resources.items():
        if not isinstance(name, str) or not _RESOURCE_NAME_RE.match(name):
            raise DispatchConfigError(f"dispatch.resources name {name!r} must be a bare word "
                                      f"({_RESOURCE_NAME_RE.pattern})")
        paths = (spec or {}).get("paths", []) if isinstance(spec, dict) else None
        if not isinstance(paths, list) or not all(isinstance(p, str) and p for p in paths):
            raise DispatchConfigError(f"dispatch.resources.{name} must be a mapping with a "
                                      f"`paths` list of globs, got {spec!r}")
    block["resources"] = resources
    for key in RETIRED_WORKTREE_KEYS:
        if key in block:
            raise DispatchConfigError(
                f"seldon.yaml dispatch.{key} is no longer read: every task runs in the Claude Code "
                f"CLI's worktree, {CLI_WORKTREE_DIR}/<stem> on branch {CLI_BRANCH_PREFIX}<stem> "
                f"(FRICTION-002, AD-034 ADDENDUM 01). Remove the key.")
    gate = block.get("gate_command")
    if gate is not None and (not isinstance(gate, str) or not gate.strip()):
        raise DispatchConfigError(f"dispatch.gate_command must be a non-empty shell command, got {gate!r}")
    block["gate_command"] = gate
    if n > 1 and gate is None:
        raise DispatchConfigError(
            "dispatch.max_parallel > 1 requires dispatch.gate_command: the re-gate after a "
            "rebase (SEL-004 decision 3) has nothing to run otherwise, and a merge that cannot "
            "be re-gated would be a merge on faith")
    for key, default in PARALLEL_DEFAULTS.items():
        if key in ("shared_paths", "worktree_links"):
            block[key] = _relative_glob_list(block, key)
        elif key == "resources":
            continue
        elif isinstance(default, int):
            v = block.get(key, default)
            if isinstance(v, bool) or not isinstance(v, int) or v < 1:
                raise DispatchConfigError(f"dispatch.{key} must be a positive whole number, "
                                          f"got {v!r}")
            block[key] = v
        else:
            v = block.get(key, default)
            if not isinstance(v, str) or not v:
                raise DispatchConfigError(f"dispatch.{key} must be a non-empty string, got "
                                          f"{v!r}")
            block[key] = v


def launchd_loaded(label: str) -> bool:
    """Whether the per-user launchd job `label` is loaded (`launchctl print gui/<uid>/<label>`)."""
    import os
    import subprocess
    r = subprocess.run(["launchctl", "print", f"gui/{os.getuid()}/{label}"],
                       capture_output=True, text=True, check=False)
    return r.returncode == 0


def dispatch_state(project_dir: Path, config: dict | None = None, loaded=None) -> dict:
    """`{"on": bool, "why": str}`: will a registered task here launch without a pasted line?

    SEL-005 (AD-036 section 6.2): on 2026-10-09 a Desktop session twice said the dispatcher
    "may pick up" a task in a project that had no dispatcher at all. The answer is read from state
    every time: a `dispatch:` block that loads, `enabled: true`, no STOP file, and (when the block
    names its `launchd_label`) that job loaded. Anything else is `off` with the reason.
    """
    project_dir = Path(project_dir)
    if config is None:
        path = project_dir / "seldon.yaml"
        config = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else {}
    if not (config or {}).get("dispatch"):
        return {"on": False, "why": "no `dispatch:` block; every task needs a pasted line"}
    try:
        cfg = load_dispatch_config(project_dir, config)
    except DispatchConfigError as exc:
        return {"on": False, "why": f"the dispatch block does not load: {exc}"}
    if not cfg["enabled"]:
        return {"on": False, "why": "dispatch.enabled is false"}
    if (project_dir / cfg["stop_file"]).exists():
        return {"on": False, "why": f"STOP file {cfg['stop_file']} present"}
    label = cfg.get("launchd_label")
    loaded = loaded or launchd_loaded
    if label and not loaded(label):
        return {"on": False, "why": f"launchd job {label} is not loaded"}
    return {"on": True, "why": (f"enabled, launchd job {label} loaded" if label
                                 else "enabled (no launchd_label declared to confirm a job)")}


def resolve_standing_band(project_dir: Path, ref: str) -> int:
    """`controls.yaml#spend.daily_tokens` -> the int that file holds, today.

    A REFERENCE and never a copied number (DN-006 §5): the standing band is the same value the
    spend guard enforces, and a second copy of it in `seldon.yaml` would be a number that drifts
    silently the first time the operator moves the cap.
    """
    if "#" not in ref:
        raise DispatchConfigError(
            f"standing_band_ref {ref!r} is not a reference: expected `<file>#<dotted.path>`")
    rel, dotted = ref.split("#", 1)
    path = project_dir / rel
    if not path.is_file():
        raise DispatchConfigError(f"standing_band_ref {ref!r} names {rel}, which does not exist")
    node: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            raise DispatchConfigError(f"standing_band_ref {ref!r}: {rel} has no {dotted!r}")
        node = node[part]
    if not isinstance(node, int):
        raise DispatchConfigError(
            f"standing_band_ref {ref!r} resolves to {node!r}, which is not an integer token count")
    return node


# ------------------------------------------------------------------ the task file's headers

def _header_value(text: str, name: str) -> str | None:
    """The header's value from the header block (AD-038-R14), the first where it repeats; None where absent.

    A repeat is refused by :func:`static_checks` (`header_repeated`), so the first is only ever read on a file that
    registration refused or that was registered before the rule.
    """
    hits = header_hits(text, name)
    return hits[0][1] if hits else None


def parse_headers(text: str, names=REQUIRED_HEADERS) -> dict:
    """The candidacy headers, as raw values. `None` where the header is absent.

    Reads the same bolded-header lines `seldon cc register` already reads, from the header block
    only (:func:`header_block`, AD-038-R14), and adds nothing to
    the task file format — the opt-in is that a task file carries them, not that it adopts a
    new syntax (DN-006 decision 2). The three `REQUIRED_HEADERS` are always read, required or not,
    because c4, c5 and c9 record their values; `names` adds a project's own (AD-038-R11).
    """
    return {name: _header_value(text, name) for name in dict.fromkeys(REQUIRED_HEADERS + tuple(names))}


def spend_tokens(value: str | None) -> int | None:
    """The Spend header as a token count: 0 for `zero`, the declared ceiling otherwise.

    `None` means the header says something this cannot read, which is a refusal and never a
    zero — a Spend line nobody can parse is the one case where guessing costs money.
    """
    if value is None:
        return None
    # QC-002: an explicit token count wins over the word `zero`. QC-002's own header reads "est. 1.5M tokens ...
    # Zero model calls beyond the session", and zero-first read it as 0 tokens: c4 passed it against the band at
    # 0 and station (c) had no estimate to compute CPI from. Only an unambiguous count (`<n> tokens`, `<n>M`,
    # `<n>K`) outranks `zero`, so an incidental number in a zero header ("DN-005 §5") is not read as a count.
    strict = _STRICT_TOKENS_RE.search(value)
    if strict:
        n = float(strict.group("n").replace(",", "").replace("_", ""))
        return int(n * {"m": 1_000_000, "k": 1_000}.get((strict.group("suffix") or "").lower(), 1))
    if _ZERO_RE.search(value):
        return 0
    m = _TOKENS_RE.search(value)
    if not m:
        return None
    n = float(m.group("n").replace(",", "").replace("_", ""))
    mult = {"m": 1_000_000, "k": 1_000}.get((m.group("suffix") or "").lower(), 1)
    return int(n * mult)


def parse_network(value: str | None) -> dict:
    """The Network header against `NETWORK_GRAMMAR`: `{kind, hosts, error}`.

    `kind` is `none`, `allowlist` or `cadence` when the value parses and `None` when it does
    not, in which case `error` says which part failed and quotes the grammar. `hosts` is the
    parsed allowlist, lower-cased and de-duplicated in order, and empty for the other kinds.
    """
    if value is None:
        return {"kind": None, "hosts": [], "error": f"no Network header; expected {NETWORK_GRAMMAR}"}
    m = _NETWORK_ALLOWLIST_RE.match(value)
    if m:
        raw = m.group("hosts").strip()
        # A sentence-ending period after the last host is prose, not a trailing-dot FQDN.
        raw = raw[:-1] if raw.endswith(".") else raw
        items = [h.strip().strip("`").strip() for h in raw.split(",")]
        if not raw or not any(items):
            return {"kind": None, "hosts": [],
                    "error": f"allowlist names no host; expected {NETWORK_GRAMMAR}"}
        bad = [h for h in items if not _HOSTNAME_RE.match(h.lower())]
        if bad:
            return {"kind": None, "hosts": [],
                    "error": (f"allowlist entries are not exact hostnames: "
                              f"{', '.join(repr(b) for b in bad)}; expected {NETWORK_GRAMMAR}")}
        hosts = list(dict.fromkeys(h.lower() for h in items))
        return {"kind": "allowlist", "hosts": hosts, "error": None}
    if _NETWORK_NONE_RE.search(value):
        return {"kind": "none", "hosts": [], "error": None}
    if _NETWORK_CADENCE_RE.search(value):
        return {"kind": "cadence", "hosts": [], "error": None}
    return {"kind": None, "hosts": [],
            "error": f"Network header {value!r} does not parse; expected {NETWORK_GRAMMAR}"}


def network_declared_none(value: str | None) -> bool:
    """True for the two forms that name no host of their own: `none` and the cadence
    provenance. An allowlist is declared, and passes c5, but is not `none`."""
    return parse_network(value)["kind"] in ("none", "cadence")


def layer_named(value: str | None) -> bool:
    """ADDENDUM_01: the header is present AND names a layer, a tier, or `none`."""
    return value is not None and bool(_LAYER_VALUE_RE.search(value))


def candidacy(task_file: Path, required=REQUIRED_HEADERS) -> dict:
    """Is this task file dispatchable at all, and if not, which header failed.

    A task whose file lacks the headers is **not a candidate** — not "ineligible". The
    distinction is the whole opt-in (DN-006 decision 2): nothing already queued changes
    behaviour when the job is installed, and `status` can say so in one word.

    `required` is the project's `dispatch.candidacy_headers` (AD-038-R11). The headers are read from
    the BASE file only, never from an addendum: an addendum amends what a task does, and a
    candidacy read across several files would need a precedence rule every other reader of the
    headers (registration, the stations' Parts and Premises, the Stop gate) would then have to
    share. A committed file's missing header is repaired by a new task file (`<id>R`).

    SEL-011 (AD-038-R12): the not-a-candidate half of :func:`static_checks`, which is where the checks live, so this
    and registration cannot drift. Kept for its callers that ask only "is it a candidate, and why not".
    """
    s = static_checks(task_file, {"candidacy_headers": tuple(required)})
    return {"candidate": s["candidate"], "reason": s["reason"], "message": s["message"],
            "headers": s["headers"], "model": s["model"]}


# ------------------------------------------------------- SEL-011: the static checks, one function

#: SEL-011 (AD-038-R12): the reason codes of a task file whose `**Parts:**` header is absent or does not parse, and
#: whose `**After:**` header does not parse. Both are registration's own words (`stations.PARTS_REFUSAL`, and the
#: `after_unresolved` registration has refused an unparseable or unresolvable After header with since 2026-09-19);
#: the dispatcher now reads both, so a file registered by any road is held to them.
PARTS_UNDECLARED = "parts_undeclared"
AFTER_UNRESOLVED = "after_unresolved"
SPEND_GRAMMAR = ("`**Spend:** zero` (no model calls) or a token count, e.g. `**Spend:** est. 0.4M tokens` "
                 "(`<n> tokens`, `<n>M`, `<n>K`)")


def _no_header_message(missing: list, required) -> str:
    return (f"the task file carries no {', '.join(f'`**{n}:**`' for n in missing)} header; a dispatchable task "
            f"carries each of {', '.join(required)} (DN-006 decision 2, AD-038-R11: `dispatch.candidacy_headers`). "
            f"The headers are read from this file only: an addendum cannot supply one, so a committed file that "
            f"lacks one is re-filed as a new task file")


def static_checks(task_file: Path, cfg: dict | None, project_dir: Path | None = None,
                  config: dict | None = None) -> dict:
    """Every candidacy check that reads only the task file and the project's configuration (SEL-011, AD-038-R12).

    The ONE function `evaluate` and `seldon cc register` both call, so a file registration accepts is a file the
    dispatcher can run, refused on the same reason code with the same grammar. Before it, registration applied Parts,
    the Model lock and the After grammar while the dispatcher applied the headers, Spend, Network and Exclusive/Touches,
    and a file could pass the first and sit unlaunched at the second with nothing said (SEL-010, SEL-010R, squiddy
    SQ-088 and SQ-091, Issue 9965fbed). What depends on live state stays at the dispatcher: the band (c4's comparison),
    the tree (c7), the lease and claims (c6), worktrees (c11), disk (c12), premises (c13), waits (c2, c17, c18).

    Args:
        task_file: The task's base file. Addenda are never read (AD-038-R11).
        cfg: The project's validated `dispatch:` block, or None for a project with no dispatcher, in which case the
            dispatcher's own checks (headers, Framework layer, Spend, Network, Exclusive/Touches) do not apply and
            only those registration has always applied do (Model lock, Parts, After).
        project_dir: The project root, for the Parts gate's baseline. Without it the Parts check is skipped.
        config: The project's parsed seldon.yaml, for the Parts gate (`qc.parts_baseline`). Read from
            `project_dir` when omitted.

    Returns:
        `{candidate, reason, message, headers, model, tokens, network, concurrency, failures}`. `failures` is every
        failed check, in the dispatcher's order, as `{code, message}`; registration refuses on any. `candidate` and
        `reason` are the dispatcher's not-a-candidate verdict, the first failure that is not one of c4, c5 or c10:
        Spend, Network and Exclusive/Touches stay criteria at the dispatcher, so a candidate refused on one of them
        keeps its refusal line and its `dispatch_stuck` alarm. `tokens`, `network` and `concurrency` are the parsed
        values c4, c5 and c10 record.
    """
    out = {"candidate": True, "reason": None, "message": None, "headers": {}, "model": None,
           "tokens": None, "network": None, "concurrency": None, "failures": []}
    if not task_file.is_file():
        msg = f"the task file {task_file} does not exist"
        return {**out, "candidate": False, "reason": "source_file_missing", "message": msg,
                "failures": [{"code": "source_file_missing", "message": msg}]}
    text = task_file.read_text(encoding="utf-8", errors="surrogateescape")
    criteria_codes = set()
    # AD-038-R14: every header these checks read is read from the header block, once. A header the block carries
    # twice is refused rather than resolved by order: which one the author meant is not the reader's to guess.
    read = ((tuple(cfg.get("candidacy_headers", REQUIRED_HEADERS)) + REQUIRED_HEADERS + CONCURRENCY_HEADERS
             if cfg is not None else ()) + (HEADER_AFTER, HEADER_ANSWERS))
    failures = repeated_headers(text, read)
    if cfg is not None:
        required = cfg.get("candidacy_headers", REQUIRED_HEADERS)
        headers = parse_headers(text, required)
        out["headers"] = headers
        missing = [n for n in required if headers[n] is None]
        if missing:
            failures.append({"code": f"no_header:{','.join(missing)}",
                             "message": _no_header_message(missing, required)})
        if HEADER_LAYER in required and headers[HEADER_LAYER] is not None and not layer_named(headers[HEADER_LAYER]):
            failures.append({"code": "framework_layer_names_no_layer",
                             "message": (f"`**{HEADER_LAYER}:**` {headers[HEADER_LAYER]!r} names no layer; "
                                         f"expected {LAYER_GRAMMAR}")})
        if headers[HEADER_SPEND] is not None:
            out["tokens"] = spend_tokens(headers[HEADER_SPEND])
            if out["tokens"] is None:
                failures.append({"code": "spend_unreadable",
                                 "message": (f"Spend header {headers[HEADER_SPEND]!r} names neither `zero` nor a "
                                             f"token count; expected {SPEND_GRAMMAR}")})
                criteria_codes.add("spend_unreadable")
        if headers[HEADER_NETWORK] is not None:
            out["network"] = parse_network(headers[HEADER_NETWORK])
            if out["network"]["error"]:
                failures.append({"code": "network_undeclared", "message": out["network"]["error"]})
                criteria_codes.add("network_undeclared")
        raw = parse_concurrency_headers(text)
        out["concurrency"] = parse_concurrency(raw[HEADER_EXCLUSIVE], raw[HEADER_TOUCHES],
                                               cfg.get("resources") or {})
        if out["concurrency"]["error"]:
            failures.append({"code": "concurrency_undeclared", "message": out["concurrency"]["error"]})
            criteria_codes.add("concurrency_undeclared")
    # AD-035 R5: a `**Model:**` header or a code-block `--model` naming an id the lock does not hold.
    try:
        out["model"] = models.check_task_models(text)
    except models.ModelsError as exc:
        out["model"] = {"errors": [str(exc)]}
        failures.append({"code": "model_lock_unreadable", "message": f"the model lock cannot be read ({exc})"})
    else:
        if not out["model"]["ok"]:
            failures.append({"code": "model_not_in_lock", "message": "; ".join(out["model"]["errors"])})
    # AD-037-R6 (c): the Parts gate, under the project's baseline exactly as registration has applied it since QC-002.
    if project_dir is not None:
        from seldon.core import stations as S
        try:
            if config is None:
                path = Path(project_dir) / "seldon.yaml"
                config = (yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else {}) or {}
            refusal = S.parts_registration_refusal(task_file, Path(project_dir), config)
        except (OSError, yaml.YAMLError) as exc:
            # Fail closed, like c14: a gate that cannot be evaluated does not pass the file.
            refusal = f"{S.PARTS_REFUSAL}: the Parts gate cannot be evaluated ({exc})"
        if refusal:
            failures.append({"code": PARTS_UNDECLARED,
                             "message": refusal.removeprefix(f"{S.PARTS_REFUSAL}: ")})
    after = parse_after(_header_value(text, HEADER_AFTER))
    if after["kind"] is None:
        failures.append({"code": AFTER_UNRESOLVED, "message": after["error"]})
    answers = parse_answers(_header_value(text, HEADER_ANSWERS))
    if answers["kind"] is None:
        failures.append({"code": ANSWERS_UNRESOLVED, "message": answers["error"]})
    out["failures"] = failures
    blocking = [f for f in failures if f["code"] not in criteria_codes]
    if blocking:
        out.update(candidate=False, reason=blocking[0]["code"], message=blocking[0]["message"])
    return out


def static_refusal(failures: list) -> str | None:
    """The registration refusal text for :func:`static_checks`'s failures: one `<code>: <message>` per failure, so an
    author with three wrong headers learns all three in one turn (SEL-010 had three). None when there are none."""
    if not failures:
        return None
    return "; ".join(f"{f['code']}: {f['message']}" for f in failures) + "."


# ------------------------------------------------------------------------- the addendum scan

def addenda_for(task_file: Path) -> list[Path]:
    return sorted(task_file.parent.glob(f"{task_file.stem}_ADDENDUM*.md"))


def superseding_addendum(task_file: Path) -> Path | None:
    """The first sibling addendum carrying the supersession marker in its first ten lines."""
    for path in addenda_for(task_file):
        head = path.read_text(encoding="utf-8", errors="surrogateescape").splitlines()
        for line in head[:MARKER_WINDOW_LINES]:
            # SEARCH, not match: every Status line in the surveyed repository sits after a
            # `**Date:** ...` on the same line, so an anchored pattern reads none of them.
            if SUPERSEDED_RE.search(line):
                return path
    return None


# --------------------------------------------------------------------------------- git state

def git(project_dir: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=project_dir, capture_output=True, text=True)


def tree_state(project_dir: Path, exclude=()) -> dict:
    """`{branch, dirty, dirty_paths}` — c7's raw material, recorded as values.

    DN-006 decision 2 asks every criterion to be recorded as a value rather than a boolean
    summary, and this is the criterion where the value matters most: "the tree was dirty" is
    not actionable and "the tree was dirty on these three paths" is.
    """
    rev = git(project_dir, "rev-parse", "--abbrev-ref", "HEAD")
    branch = rev.stdout.strip()
    # `--no-optional-locks`: git(1) documents it for exactly this caller, a process that runs
    # `git status` in the background of a checkout someone else is working in. Without it the
    # status takes `index.lock` to refresh the index, and a session's own `git commit` in the
    # same instant fails on the lock.
    #
    # NOT `.strip()` on the porcelain output. Every line is `XY PATH` with X and Y each
    # possibly a space, so an unstaged modification is `" M path"` — and stripping the whole
    # blob removes the leading space of the FIRST line only, after which `ln[3:]` eats the
    # first character of that one path and no other. Found by running the dry pass and reading
    # `LAUDE.md` in the criteria vector; a defect that corrupts exactly one entry of a
    # diagnostic list is one no amount of staring at the code finds.
    status = git(project_dir, "--no-optional-locks", "status", "--porcelain")
    # A git call that FAILED is a failed read, not a clean tree and not a dirty one. Before
    # ai-readiness-kg/cc_tasks/2026-10-09_main_green_dispatch_stuck_without_a_path.md decision 3
    # the return codes were not looked at, so a failed status read as "no paths" and a failed
    # rev-parse as a wrong branch, and c7 reported either as `dirty_tree`.
    failed = [(name, r) for name, r in (("rev-parse", rev), ("status", status))
              if r.returncode != 0]
    if failed:
        name, r = failed[0]
        return {"branch": branch, "dirty": False, "dirty_paths": [], "dirty_count": 0,
                "read_error": f"git {name} exited {r.returncode}: "
                              f"{(r.stderr or '').strip()[:200]}"}
    porcelain = status.stdout
    paths = [ln[3:] for ln in porcelain.split("\n") if ln.strip()]
    # SEL-004 decision 5: a shared append-only file (a spend ledger) that worktree sessions
    # append to in the PRIMARY checkout is not dirt the pass waits on; the pass commits it.
    if exclude:
        paths = [p for p in paths if p not in set(exclude)]
    return {"branch": branch, "dirty": bool(paths), "dirty_paths": paths[:20],
            "dirty_count": len(paths)}


def stage(project_dir: Path, paths: list) -> subprocess.CompletedProcess:
    """`git add` exactly these paths. Never `-A`.

    A dispatcher that staged the whole tree would commit whatever else happened to be lying in
    the checkout, under a message saying it created a task file.
    """
    return git(project_dir, "add", "--", *[str(p) for p in paths])


def commit_paths(project_dir: Path, paths: list, message: str) -> dict:
    """Commit exactly these paths, and report what happened as values.

    **Why the dispatcher commits at all.** DN-006 decision 8 says the rendered task "flows
    through decisions 2 to 5 like any other task" — and decision 2's c1 requires the task file
    to be git-tracked while c7 requires the working tree to be clean. A rendered file that is
    never committed fails both, forever, for every task in the queue: the cadence would create
    January's cycle and then wedge the dispatcher until a person came and committed it, which
    is the exact latency this whole mechanism exists to remove. The commit is entailed by
    decision 8, not added to it; DN-006 ADDENDUM_02 records that the note does not say so.

    Pathspec-limited (`git commit -- <paths>`), so a tree that is dirty for some other reason
    keeps its other changes and this commit contains only what the cadence wrote. This function
    does not push; the pass pushes separately (`push_if_ahead`), after every commit it makes
    and on every pass that finds the branch still ahead
    (`ai-readiness-kg/cc_tasks/2026-09-16_dispatcher_commits_its_record.md` decision 2).
    """
    # A path the project ignores is dropped rather than staged: `git add` on an ignored path
    # is an error, and it would abort a commit for a file the project has deliberately said it
    # does not track (a test project ignores its event store; the real one tracks it). What is
    # skipped is reported, so the difference is visible rather than assumed.
    wanted = [str(p) for p in paths]
    keep = [p for p in wanted
            if (Path(project_dir) / p).exists()
            and git(project_dir, "check-ignore", "-q", "--", p).returncode != 0]
    skipped = [p for p in wanted if p not in keep]
    if not keep:
        return {"committed": False, "reason": "nothing_to_commit", "skipped": skipped}
    added = stage(project_dir, keep)
    if added.returncode != 0:
        return {"committed": False, "reason": "git_add_failed", "stderr": added.stderr.strip(),
                "skipped": skipped}
    done = git(project_dir, "commit", "-m", message, "--", *keep)
    if done.returncode != 0:
        # Unstage what this call staged: a refused commit (a hook) must leave the index as it found
        # it, or the next commit anyone makes carries these paths under its own message.
        git(project_dir, "reset", "-q", "--", *keep)
        return {"committed": False, "reason": "git_commit_failed",
                "stderr": (done.stderr or done.stdout).strip(), "skipped": skipped}
    head = git(project_dir, "rev-parse", "--short", "HEAD").stdout.strip()
    return {"committed": True, "reason": None, "commit": head, "message": message,
            "committed_paths": keep, "skipped": skipped}


def appended_events(project_dir: Path, store_rel: str) -> dict:
    """The events appended to the tracked store since HEAD, whoever wrote them.

    The store's commit precondition since AD-038-R1 retired the actor allowlist (FRICTION-001
    Part A): what qualifies a line is that the change is an append, never who wrote it. Checked against
    HEAD's blob: the working copy must begin with HEAD's bytes, and every appended line must
    parse. Returns `{ok, reason, events}` with `reason` one of `None`, `clean`, `untracked`,
    `not_append_only`, `unparseable`; never raises on a state.
    """
    path = Path(project_dir) / store_rel
    if not path.is_file() or not is_tracked(Path(project_dir), path):
        return {"ok": False, "reason": "untracked", "events": []}
    head = subprocess.run(["git", "show", f"HEAD:{store_rel}"], cwd=project_dir,
                          capture_output=True)
    if head.returncode != 0:
        return {"ok": False, "reason": "untracked", "events": []}
    work = path.read_bytes()
    if work == head.stdout:
        return {"ok": False, "reason": "clean", "events": []}
    if not work.startswith(head.stdout):
        return {"ok": False, "reason": "not_append_only", "events": []}
    events = []
    for raw in work[len(head.stdout):].decode("utf-8").splitlines():
        if not raw.strip():
            continue
        try:
            events.append(json.loads(raw))
        except json.JSONDecodeError:
            return {"ok": False, "reason": "unparseable", "events": events}
    return {"ok": True, "reason": None, "events": events}


def push_if_ahead(project_dir: Path) -> dict:
    """Push the current branch when it is ahead of its upstream; otherwise do nothing.

    Decision 2 of the same task: the dispatcher pushes what it commits, and a failed push is
    retried by the next pass whenever the branch is still ahead. "Ahead" is read from git
    (`rev-list --count @{u}..HEAD`), never remembered, so the retry needs no state of its own.
    Returns `{pushed, reason, ahead, stderr?}`; `reason` is `None`, `up_to_date`,
    `no_upstream` or `push_failed`. Never raises: an offline machine is an ordinary state.
    """
    count = git(project_dir, "rev-list", "--count", "@{u}..HEAD")
    if count.returncode != 0:
        return {"pushed": False, "reason": "no_upstream", "ahead": None,
                "stderr": count.stderr.strip()}
    ahead = int(count.stdout.strip() or 0)
    if ahead == 0:
        return {"pushed": False, "reason": "up_to_date", "ahead": 0}
    # `GIT_TERMINAL_PROMPT=0`: a launchd pass has no terminal, and a credential prompt would
    # hang the pass until the next one collided with its lease.
    done = subprocess.run(["git", "push", "--quiet"], cwd=project_dir, capture_output=True,
                          text=True, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    if done.returncode != 0:
        return {"pushed": False, "reason": "push_failed", "ahead": ahead,
                "stderr": (done.stderr or done.stdout).strip()}
    return {"pushed": True, "reason": None, "ahead": ahead}


# ------------------------------------------------------- a cross-repo task's other repositories (DISP-004R)

#: The header that names the repositories a task works in, and its L4 clause (commit, merge, push) where they are.
HEADER_REPO = "Repo"

#: Where a bare repository name in the Repo line is looked for: `dispatch.cross_repo_root`, relative to the project.
#: Every governed repository is a sibling checkout of seldon's (`seldon.yaml prior_art.internal_roots` reads them
#: the same way), so the default is the project's parent directory.
CROSS_REPO_ROOT_DEFAULT = ".."

#: The branch a named repository must be on for its push (`dispatch.cross_repo_branch`). Sessions commit on a
#: sibling's main by path (AD-036-R12); a sibling on another branch is someone's work in progress, never pushed.
CROSS_REPO_BRANCH_DEFAULT = "main"

#: The L4 clause: from `L4:` to the end of its sentence (a period followed by whitespace or the end of the value).
_L4_RE = re.compile(r"\bL4\s*:(?P<clause>.*?)(?:\.(?=\s)|\.?$)", re.S)
#: A clause segment that quantifies over every repository the line names ("in all three", "in every repo touched").
_EVERY_RE = re.compile(r"\b(?:every|all|each|both)\b", re.I)
_PUSH_RE = re.compile(r"\bpush", re.I)
#: A bare word that may be a sibling checkout's directory name.
_REPO_WORD_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")
#: An absolute path, as the Repo lines write cross-repo targets (`/Users/brock/GitHub/arnold`).
_ABS_PATH_RE = re.compile(r"(?<![\w.])/[^\s`'\"(),;]+")


def _is_checkout(path: Path) -> bool:
    return (path / ".git").exists()


def _named_repos(text: str, root: Path) -> list:
    """The git checkouts `text` names, in order of first mention: absolute paths, and bare words that are the
    directory name of a checkout under `root`. A word that names no checkout is prose and is ignored."""
    hits = []
    for m in _ABS_PATH_RE.finditer(text):
        path = Path(m.group(0).rstrip(".:"))
        if _is_checkout(path):
            hits.append((m.start(), path.resolve()))
    for m in _REPO_WORD_RE.finditer(text):
        word = m.group(0).rstrip(".")
        if word and _is_checkout(root / word):
            hits.append((m.start(), (root / word).resolve()))
    out = []
    for _, path in sorted(hits, key=lambda h: h[0]):
        if path not in out:
            out.append(path)
    return out


def repo_push_targets(value: str | None, project_dir: Path, root: Path) -> list:
    """The OTHER repositories whose main a task's `**Repo:**` line says to push (AD-034-R12), as resolved paths.

    The line is prose (`seldon (primary); squiddy and ai-readiness-kg (...). L4: commit, merge, push in all three.`),
    so the reading is deliberately narrow, and what it cannot read pushes nothing:

    * only the `L4:` clause decides, up to the end of its sentence, and within it only the `;`-separated segments
      that say `push` (`push in squiddy; the hazbrief graph release commits in hazbrief-mcp` pushes squiddy alone);
    * a push segment that names repositories pushes those;
    * a push segment that names none pushes every repository the line names up to the end of the L4 clause, and only
      when it quantifies (`all`, `every`, `each`, `both`); a bare `L4: commit, merge, push.` is the primary's alone,
      so a repository the line names as evidence ("read only") is never pushed by it, and neither is one named in
      a sentence after the clause;
    * "every repo touched" is read at the finish, where a named repository whose HEAD did not move is not pushed;
    * the project itself is left out: its own main is pushed by the dispatcher as before.
    """
    if not value:
        return []
    m = _L4_RE.search(value)
    if m is None:
        return []
    segments = [s for s in m.group("clause").split(";") if _PUSH_RE.search(s)]
    named = []
    for seg in segments:
        named += _named_repos(seg, root)
    if not named and any(_EVERY_RE.search(seg) for seg in segments):
        named = _named_repos(value[:m.end()], root)
    own = Path(project_dir).resolve()
    out = []
    for path in named:
        if path != own and path not in out:
            out.append(path)
    return out


def cross_repo_launch(project_dir: Path, cfg: dict, task_text: str) -> list:
    """At launch: each repository the task's Repo line says to push, with its HEAD now, for the finish to compare.
    `[{"repo": <path>, "head_at_launch": <sha or None>}]`; empty for a task that names no other repository."""
    root = (Path(project_dir) / cfg["cross_repo_root"]).resolve()
    return [{"repo": str(path), "head_at_launch": WT.rev(path, "HEAD")}
            for path in repo_push_targets(_header_value(task_text, HEADER_REPO), project_dir, root)]


#: A cross-repo push reading's `push` values that are not a success and not "nothing to do": each one alarms.
CROSS_REPO_REFUSALS = ("missing", "read_error", "wrong_branch", "dirty_tree", "no_upstream", "push_failed")


def push_cross_repo(entry: dict, branch: str) -> dict:
    """At a merged finish: push one named repository's main when its HEAD moved since launch and its tree is clean.

    Returns the entry with `head_at_finish` and `push`: `unmoved` (nothing this session did there), `pushed`,
    `up_to_date`, or one of `CROSS_REPO_REFUSALS`. A dirty tree refuses the push, as c7 refuses a dispatch: what is
    uncommitted there is someone's work in progress, and pushing past it would publish a main nobody has looked at
    whole. Never raises (an offline machine is an ordinary state, as in `push_if_ahead`)."""
    repo = Path(entry["repo"])
    out = {"repo": entry["repo"], "head_at_launch": entry.get("head_at_launch")}
    if not _is_checkout(repo):
        return {**out, "head_at_finish": None, "push": "missing"}
    head = WT.rev(repo, "HEAD")
    out["head_at_finish"] = head
    if head == entry.get("head_at_launch"):
        return {**out, "push": "unmoved"}
    state = tree_state(repo)
    if state.get("read_error"):
        return {**out, "push": "read_error", "error": state["read_error"]}
    if state["branch"] != branch:
        return {**out, "push": "wrong_branch", "branch": state["branch"]}
    if state["dirty"]:
        return {**out, "push": "dirty_tree", "dirty_paths": state["dirty_paths"][:10],
                "dirty_count": state["dirty_count"]}
    pushed = push_if_ahead(repo)
    if pushed["pushed"]:
        return {**out, "push": "pushed", "ahead": pushed["ahead"]}
    res = {**out, "push": pushed["reason"], "ahead": pushed["ahead"]}
    if pushed.get("stderr"):
        res["stderr"] = pushed["stderr"][:500]
    return res


def lease_is_held(project_dir: Path, cfg: dict) -> bool:
    """Is a dispatcher pass — and therefore possibly a dispatched session — working here?

    Read from the lease's RECORD plus PID liveness, never from age: the DD-022 orphan rule,
    which `reap_lease` already follows. A stale body naming a dead PID is not a held lease.
    """
    body = read_lease(Path(project_dir) / cfg["lease_file"])
    if not body or body.get("holder") is None:
        return False
    pid = body.get("pid")
    return not isinstance(pid, int) or pid_alive(pid)


def commit_journal_append(project_dir: Path, config: dict, by: str, actor: str = "desktop") -> dict:
    """Commit the lines `by` just appended to the tracked event store, path-scoped.

    ADDENDUM_01 decision 6a to
    `ai-readiness-kg/cc_tasks/2026-09-19_seldon_hygiene_superseded_cadence_after.md`.

    **What it closes.** `seldon cc register` has committed its own footprint since
    `2026-09-18_registration_commits`, for a reason that is not special to registration: the
    event store is a TRACKED file in this project, and a write to it that nobody commits keeps
    c7 false for the WHOLE queue — not for the task that was touched, for every task behind it.
    Every other MCP write tool appends to the same file and committed nothing. `_record_own_lines`
    then refuses the file, by name, as "not dispatcher-only (also written by desktop)".

    **Deferred, never forced.** Nothing is committed while a lease is held: a `git commit`
    beside a working dispatched session is DD-019's class and an `index.lock` collision
    besides. The next pass that holds the lease reconciles what it finds (AD-038-R1). Nothing is
    committed either when the project has no `dispatch:` block (the dispatcher is opt-in per
    project and this is its hygiene), or when the store is untracked or not append-only. The
    lines may be anyone's: with no lease held no session is working here, which is the DD-019
    guard the retired actor allowlist stood for.

    Returns:
        `{committed, reason, ...}` — `reason` one of `None`, `no_dispatch_block`,
        `lease_held`, `wrong_branch`, or whatever `appended_events` / `commit_paths`
        reported. **Never raises**: a tool that did its work must not fail on its bookkeeping.
    """
    try:
        cfg = load_dispatch_config(Path(project_dir), config)
    except (DispatchConfigError, OSError):
        return {"committed": False, "reason": "no_dispatch_block"}
    store = (config or {}).get("event_store", {}).get("path", "seldon_events.jsonl")
    if lease_is_held(project_dir, cfg):
        return {"committed": False, "reason": "lease_held"}
    if tree_state(project_dir)["branch"] != cfg["branch"]:
        return {"committed": False, "reason": "wrong_branch"}
    own = appended_events(Path(project_dir), store)
    if not own["ok"]:
        return {"committed": False, "reason": own["reason"]}
    types = list(dict.fromkeys(e.get("event_type") for e in own["events"]))
    ids = list(dict.fromkeys(
        str(pl.get("task_id") or pl.get("artifact_id") or pl.get("id"))[:8]
        for pl in ((e.get("payload") or {}) for e in own["events"])
        if pl.get("task_id") or pl.get("artifact_id") or pl.get("id")))
    message = (f"{actor}: {', '.join(types)} {', '.join(ids) or '-'} — "
               f"{len(own['events'])} line(s) written by {by}")
    return commit_paths(Path(project_dir), [store], message)


# ------------------------------------------------------------------- the stuck-queue alarm

def stuck_state_path(project_dir: Path, cfg: dict) -> Path:
    """Where the streaks are kept: `$SELDON_DISPATCH_STUCK_STATE` when set, else beside the
    lease. The one place the path is computed, so a reader and a writer cannot disagree."""
    override = os.environ.get(STUCK_STATE_ENV)
    if override:
        return Path(override).expanduser()
    return Path(project_dir) / Path(cfg["lease_file"]).parent / STUCK_STATE_FILE


def read_stuck_state(project_dir: Path, cfg: dict) -> dict:
    path = stuck_state_path(project_dir, cfg)
    if not path.is_file():
        return {}
    try:
        body = json.loads(path.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError:
        # A corrupt streak file re-arms the alarm rather than silencing it: the failure
        # direction of a staleness alarm must be "tell them again", never "stay quiet".
        return {}
    return body if isinstance(body, dict) else {}


def write_stuck_state(project_dir: Path, cfg: dict, state: dict) -> None:
    path = stuck_state_path(project_dir, cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def stuck_threshold(cfg: dict, criterion: str) -> int:
    """Passes before the alarm for this criterion: its override, else `stuck_after_passes`."""
    return (cfg.get("stuck_after_passes_by_criterion") or {}).get(criterion,
                                                                  cfg["stuck_after_passes"])


def last_pass_path(project_dir: Path, cfg: dict) -> Path:
    override = os.environ.get(LAST_PASS_ENV)
    if override:
        return Path(override).expanduser()
    return Path(project_dir) / Path(cfg["lease_file"]).parent / LAST_PASS_FILE


def write_last_pass(project_dir: Path, cfg: dict, body: dict) -> None:
    path = last_pass_path(project_dir, cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(body, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def read_last_pass(project_dir: Path, cfg: dict) -> dict | None:
    """The last pass's record, or None when no pass has written one. Raises on a corrupt file:
    `seldon go` reports that rather than showing an empty queue."""
    path = last_pass_path(project_dir, cfg)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def advance_stuck(previous: dict, refusals: dict, threshold, now: str) -> tuple:
    """One pass's refusals against the previous streaks: `(state, alarms)`.

    Pure, so the whole re-arm rule is testable without a clock, a graph or a notifier.

    Args:
        previous: The state file's contents.
        refusals: `{task_id: {"criterion": str, "detail": ...}}` for this pass.
        threshold: `dispatch.stuck_after_passes`, or a callable `criterion -> passes`
            (`stuck_threshold`, so a dirty tree can alarm on its first pass).
        now: Timestamp stamped on a new streak and on the alarm.

    Returns:
        The state to persist, and the task ids to raise the alarm for in this pass.

    A streak re-arms when the criterion CHANGES or CLEARS — a task that stops being refused
    drops out of the state entirely, so the same criterion recurring later alarms again. The
    alarm fires exactly once per streak: that is the difference between a staleness alarm and
    the per-pass refusal logging DN-006 decision 7 forbids.
    """
    state, alarms = {}, []
    for task_id, row in refusals.items():
        prior = previous.get(task_id) or {}
        same = prior.get("criterion") == row["criterion"]
        passes = (prior.get("passes", 0) + 1) if same else 1
        notified = bool(prior.get("notified")) if same else False
        entry = {"criterion": row["criterion"], "passes": passes, "notified": notified,
                 "first_seen": prior.get("first_seen", now) if same else now}
        need = threshold(row["criterion"]) if callable(threshold) else threshold
        if passes >= need and not notified:
            entry["notified"] = True
            entry["notified_at"] = now
            alarms.append(task_id)
        elif same and prior.get("notified_at"):
            entry["notified_at"] = prior["notified_at"]
        state[task_id] = entry
    return state, alarms


def is_tracked(project_dir: Path, path: Path) -> bool:
    try:
        rel = path.relative_to(project_dir)
    except ValueError:
        return False
    r = git(project_dir, "ls-files", "--error-unmatch", str(rel))
    return r.returncode == 0


# ------------------------------------------------------------------------------- the lease

def holder_id(pid: int | None = None) -> str:
    return f"dispatcher:{socket.gethostname()}:{pid or os.getpid()}"


def pid_alive(pid: int) -> bool:
    """PID liveness, the DD-022 orphan-reap rule adopted unchanged (DN-006 §5).

    Never age. A reservation — or here a lease — is orphaned when its holder is gone, and a
    long-running holder is not an orphan however long it runs.
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class LeaseHeld(RuntimeError):
    """Another dispatcher holds the flock. Not an error condition: a second pass exits 0."""

    def __init__(self, body: dict):
        self.body = body
        super().__init__(f"lease held by {body.get('holder')!r}")


class Lease:
    """`fcntl.flock` on `<project>/.seldon/dispatch.lock`, with an identified holder.

    The flock is the guard; the JSON body is the *record* of who holds it and what is in
    flight, so `status` and `lease reap` can answer without taking the lock. DD-019 is why the
    guard is hard rather than advisory: two runners on one queue is the batch-identity defect
    at runner grain, and that one cost 22.0M tokens against a 12M ceiling.
    """

    def __init__(self, path: Path, extra: dict | None = None):
        self.path = path
        self._fh = None
        #: Fields every body this lease writes carries, including the release record. A
        #: per-worktree lease (SEL-004 decision 2) keeps its task, worktree and branch here so
        #: a released or orphaned lease still says which task it was; the global lease has
        #: none, and its bodies are byte-for-byte what they were before.
        self.extra = dict(extra or {})

    def __enter__(self) -> "Lease":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self._fh.close()
            self._fh = None
            raise LeaseHeld(read_lease(self.path)) from exc
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self.write({"holder": holder_id(), "pid": os.getpid(), "acquired_at": now,
                    "heartbeat_at": now, "task": None, **self.extra})
        return self

    def write(self, body: dict) -> None:
        self._fh.seek(0)
        self._fh.truncate()
        self._fh.write(json.dumps(body, indent=1) + "\n")
        self._fh.flush()
        os.fsync(self._fh.fileno())

    def heartbeat(self, task: str | None = None) -> None:
        body = read_lease(self.path)
        body["heartbeat_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        if task is not None:
            body["task"] = task
        self.write(body)

    def __exit__(self, *exc) -> bool:
        if self._fh is not None:
            # RECORD THE RELEASE, do not just drop the flock. The file is the lease's *record*
            # and the flock is its *guard*; leaving the body naming a holder whose process has
            # since exited makes every reader — `status`, `seldon go` — report a lease held by
            # a dead PID and tell the operator to run `lease reap`. That is a false alarm after
            # every ordinary pass, and an operator who is told to reap a healthy lease twelve
            # times an hour will reap a real one without looking.
            #
            # The file is kept rather than unlinked so the flock has a stable inode: two passes
            # racing on a path that is deleted between them can each open a different file and
            # each take "the" lock.
            body = read_lease(self.path)
            self.write({"holder": None, "pid": None, "task": None,
                        "last_holder": body.get("holder"),
                        "acquired_at": body.get("acquired_at"),
                        "released_at": datetime.now(timezone.utc).isoformat()
                        .replace("+00:00", "Z"), **self.extra})
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
            self._fh.close()
            self._fh = None
        return False


def acquire_waiting(path: Path, timeout_s: float, poll_s: float = 0.5,
                    extra: dict | None = None) -> "Lease":
    """Take a lease, waiting up to `timeout_s` for its holder to release it.

    For the worktree supervisor's finish (SEL-004 decision 3): the merge into main, the events
    and the commits must not interleave with a pass's, and a pass lasts seconds, so the
    supervisor waits for the pass rather than refusing. A pass never waits; it still exits on
    `LeaseHeld`, as decision 6 has it.

    Raises:
        LeaseHeld: the lease was still held when `timeout_s` ran out.
    """
    import time
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            return Lease(path, extra=extra).__enter__()
        except LeaseHeld:
            if time.monotonic() >= deadline:
                raise
            time.sleep(poll_s)


def worktree_lease_path(project_dir: Path, cfg: dict, stem: str) -> Path:
    """`<lease_dir>/<stem>.lock`: one lease per worktree (SEL-004 decision 2)."""
    return Path(project_dir) / cfg.get("lease_dir", ".seldon/leases") / f"{stem}.lock"


def flock_held(path: Path) -> bool:
    """Does some process hold the flock on `path`? Probed with LOCK_NB and released at once.

    The kernel drops a flock when its holder dies, so for a holder known to have taken it this
    is an exact liveness test, immune to the PID reuse a `kill(pid, 0)` probe is not.
    """
    if not Path(path).is_file():
        return False
    with Path(path).open("a+", encoding="utf-8") as fh:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        return False


def worktree_holder_alive(path: Path, body: dict) -> bool:
    """A worktree lease's holder is alive (SEL-004, AD-034-R9).

    Once the supervisor has recorded `supervising: true` it holds the flock for its whole
    life, so the flock decides. Before that (the moment between the pass starting it and its
    taking the flock) the PID recorded by the pass is all there is; DD-022's rule applies.
    """
    if body.get("holder") is None:
        return False
    if body.get("supervising"):
        return flock_held(path)
    pid = body.get("pid")
    return isinstance(pid, int) and pid_alive(pid)


def worktree_leases(project_dir: Path, cfg: dict) -> list:
    """Every per-worktree lease body on disk, with its path, for `status`, `go` and reap."""
    d = Path(project_dir) / cfg.get("lease_dir", ".seldon/leases")
    out = []
    for path in sorted(d.glob("*.lock")) if d.is_dir() else []:
        body = read_lease(path)
        out.append({"path": str(path.relative_to(project_dir)), "stem": path.stem,
                    "body": body, "held": body.get("holder") is not None,
                    "alive": worktree_holder_alive(path, body)})
    return out


def worktree_state(project_dir: Path, cfg: dict) -> dict:
    """c11's raw material: is the CLI's worktree directory ignored, so a worktree inside the checkout is not c7's
    dirt.

    DISP-001R Part A: the CLI names each worktree (`--worktree` with no name), so there is no path or branch to
    find taken before the launch; the name is learned from the session's `init` record. A probe path under the
    directory stands for every name the CLI could choose.
    """
    probe = f"{CLI_WORKTREE_DIR}/{CLI_NAME_PROBE}"
    ignored = git(project_dir, "check-ignore", "-q", "--", probe).returncode == 0
    return {"worktree_dir": CLI_WORKTREE_DIR, "named_by": "cli", "ignored": ignored, "ok": ignored}


#: The name `worktree_state` asks `git check-ignore` about: any name stands for all of them, since the CLI's names
#: are one path segment under `CLI_WORKTREE_DIR`.
CLI_NAME_PROBE = "cli-named"


def read_lease(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError:
        return {"unparseable": True}


def reap_lease(path: Path) -> dict:
    """The only release path other than process exit, and it refuses a live holder.

    No age-based auto-reap, for the reason DD-022 gives: an age threshold releases a lease a
    healthy long-running holder still needs, and the whole class of defect that guards against
    is two writers believing they are one.
    """
    body = read_lease(path)
    if not body:
        return {"reaped": False, "reason": "no_lease_file", "holder": None}
    if body.get("holder") is None and not body.get("unparseable"):
        # Released cleanly by its holder on exit. There is nothing to reap, and saying so is
        # not the same as saying there is no lease file — an operator who asked to reap wants
        # to know which of the two they are looking at.
        return {"reaped": False, "reason": "not_held", "holder": None,
                "last_holder": body.get("last_holder"),
                "released_at": body.get("released_at")}
    pid = body.get("pid")
    if isinstance(pid, int) and pid_alive(pid):
        return {"reaped": False, "reason": "holder_alive", "holder": body.get("holder"),
                "pid": pid}
    path.unlink()
    return {"reaped": True, "reason": "holder_gone", "holder": body.get("holder"), "pid": pid}


# ------------------------------------------------------------------------------- free space (c12)

#: `dispatch.disk_need_factor` when absent. SQ-010 ADDENDUM 02 D3.4: a launch needs its measured peak footprint
#: "times 2", not the machine-wide 25 GB floor. The factor is the addendum's margin, not a measurement.
DISK_NEED_FACTOR_DEFAULT = 2

#: The free-space probe's fake. When set (to a whole number of bytes) the probe reports it for every volume and
#: never reads the disk: DN-043 R-184 says no test reads the machine's state, and conftest sets it for every test,
#: in-process and in every child the test starts. The probe's name for itself is recorded in c12, so a production
#: pass that ever ran under it says so in its own record.
DISK_FREE_ENV = "SELDON_DISK_FREE_BYTES"


def free_bytes(path: Path) -> tuple[int, str]:
    """`(free bytes, what measured them)` on the volume holding `path`; a path not made yet is measured on its
    nearest existing parent's volume. The one place the dispatcher reads free space."""
    fake = os.environ.get(DISK_FREE_ENV)
    if fake is not None:
        if not fake.strip().isdigit():
            raise DispatchConfigError(f"{DISK_FREE_ENV}={fake!r} is not a whole number of bytes")
        return int(fake), f"env {DISK_FREE_ENV}"
    q = Path(path)
    while not q.exists() and q != q.parent:
        q = q.parent
    return shutil.disk_usage(q).free, "statvfs"


def tree_bytes(project_dir: Path, ref: str) -> int:
    """The bytes a checkout of `ref` writes: the sum of its blobs' sizes (`git ls-tree -r -l`). Submodule
    entries carry no size and count 0. Raises `RuntimeError` when git cannot read the ref."""
    r = git(project_dir, "ls-tree", "-r", "-l", "-z", ref)
    if r.returncode != 0:
        raise RuntimeError(f"git ls-tree {ref}: {r.stderr.strip()[:200]}")
    total = 0
    for entry in r.stdout.split("\0"):
        if not entry:
            continue
        meta = entry.split("\t", 1)[0].split()
        if len(meta) == 4 and meta[1] == "blob" and meta[3].isdigit():
            total += int(meta[3])
    return total


def disk_state(project_dir: Path, cfg: dict, worktree: bool) -> dict:
    """Criterion c12: is there room for this launch? SQ-010 ADDENDUM 02 D3.4.

    **What a launch writes, measured at launch time.** A worktree launch (SEL-004; every launch since
    FRICTION-002) checks out the configured branch into `.claude/worktrees/`: its footprint is that tree, measured
    exactly from git, and the volume is the worktree directory's. `worktree=False` (a task whose declaration does
    not parse, which c10 refuses anyway) measures the project's own volume. What a session will write beyond its
    tree cannot be measured before it runs, and the decision taken here, on the grounding below, is that its
    footprint is the same measured tree:

    * The tree is the unit a session's disk use is made of. The incident this answers
      (squiddy/docs/evidence/sq010/disk_incident.md, 2026-10-11) was one in-place session that made two
      worktrees and a clean-run clone of its repository, about 4.4 GB on a 1.1 GB tree: copies of the tree.
    * It is measured, from the commit, every pass, so it follows the repository as it grows; a constant would
      be a guess and the machine-wide 25 GB floor would refuse a 2 MB repository's launch for a reason that is
      not that launch's.
    * It is a lower bound, not the session's peak: a session that copies the tree more than `factor` times
      can still exhaust the disk. That is why each tool that writes copies checks its own need before it runs
      (D3.4: squiddy's record-pass and governed repin), rather than the dispatcher pretending to know the
      session's.

    A tree git cannot measure refuses (`disk_unmeasured`) rather than assuming a need of zero."""
    factor = cfg.get("disk_need_factor", DISK_NEED_FACTOR_DEFAULT)
    ref = cfg["branch"]
    where = Path(project_dir) / CLI_WORKTREE_DIR if worktree \
        else Path(project_dir)
    out = {"launch": "worktree" if worktree else "in_place", "ref": ref, "path": str(where),
           "factor": factor}
    try:
        footprint = tree_bytes(Path(project_dir), ref)
    except RuntimeError as exc:
        return {**out, "read_error": str(exc), "ok": False}
    free, probe = free_bytes(where)
    need = int(footprint * factor)
    return {**out, "footprint_bytes": footprint, "need_bytes": need, "free_bytes": free, "probe": probe,
            "ok": free >= need}


# ------------------------------------------------------------- the OODA between chained tasks (c18)
#
# SEL-010R2 Part A (AD-038-R10). The dispatcher closes the latency between a clean gate and a launch; it did not close
# the step between task N's RESULT and task N+1's launch, in which someone reads the RESULT, names the premises it
# found wrong and amends N+1 (`docs/design/2026-09-15_standing_dispatcher.md`: "still a Desktop OODA and is not
# automated here", DN-006 §4). c18 holds N+1 until that step has left a record, or until the project's grace runs out.
#
# Prior art: a manual-approval gate between pipeline stages that resumes on approval OR on a timeout. Argo Workflows'
# `suspend` template with `duration` (resumes by `argo resume` or when the duration elapses); Jenkins Pipeline's
# `input` step inside `timeout`; GitHub Actions environments' required reviewers and wait timer. Decided here: the
# record releases the successor at once, the grace releases it without one, and a grace of 0 is no gate at all.

#: `dispatch.ooda_grace_s` when absent: never wait (the pre-SEL-010R2 dispatcher, unchanged in every project).
OODA_GRACE_S_DEFAULT = 0

#: The event a Desktop OODA writes for task N (`seldon dispatch ooda record`), payload `{task_id, by, note}`.
EVENT_OODA_RECORDED = "ooda_recorded"

#: The file form of the record: `<N's stem>_OODA.md` beside N's task file (and its RESULT), committed. A file that is
#: not tracked does not count: the successor's worktree is cut from main's HEAD and would not see it.
OODA_FILE_SUFFIX = "_OODA.md"

#: The predecessor states that produce a RESULT to read. A superseded, withdrawn or rejected predecessor satisfies c2
#: (AD-029 section 3) but left nothing to orient on, so it does not hold its successor here.
OODA_PREDECESSOR_STATES = ("completed", "verified")


def ooda_file(source_file: str | None) -> str | None:
    """The OODA record's path for a task whose file is `source_file` (relative to the project)."""
    if not source_file:
        return None
    p = Path(source_file)
    return str(p.with_name(p.stem + OODA_FILE_SUFFIX))


def _parse_ts(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def ooda_index(events: list) -> dict:
    """c18's raw material from the ledger, read once per pass: `{recorded: {task_id: event}, completed_at:
    {task_id: timestamp}}`. `completed_at` is the LAST move into `completed`, because a task redriven and completed
    again has a newer RESULT, and the grace runs from the RESULT a reader would read."""
    recorded, completed = {}, {}
    for e in events:
        kind, p = e.get("event_type"), e.get("payload") or {}
        if kind == EVENT_OODA_RECORDED and p.get("task_id"):
            recorded[p["task_id"]] = {"at": e.get("timestamp"), "by": p.get("by"), "note": p.get("note")}
        elif (kind == "artifact_state_changed" and p.get("to_state") == "completed"
              and p.get("artifact_id")):
            completed[p["artifact_id"]] = e.get("timestamp")
    return {"recorded": recorded, "completed_at": completed}


def ooda_waits(project_dir: Path, tasks: list, cfg: dict, index: dict, now: datetime) -> dict:
    """c18 for every task it applies to: `{task_id: criterion}`. Empty when the grace is 0 (the project has not opted
    in). A task applies when at least one `precedes` predecessor is `completed` or `verified`; its criterion is
    present whether it passes or not, so `dispatch_launched` records which record, or the grace, released it.

    Per predecessor: `released_by` is `ooda_event`, `ooda_file`, `grace` or None (still waiting). A predecessor whose
    completion time is in neither the ledger nor the graph's `updated_at` cannot have its grace measured and waits
    (fail closed, like c14 and c17); `seldon dispatch ooda record <N>` releases it."""
    grace = cfg.get("ooda_grace_s", OODA_GRACE_S_DEFAULT)
    if not grace:
        return {}
    out = {}
    for t in tasks:
        preds = [p for p in (t.get("predecessors") or []) if p.get("state") in OODA_PREDECESSOR_STATES]
        if not preds:
            continue
        rows = []
        for p in preds:
            pid = p.get("artifact_id")
            rel = ooda_file(p.get("source_file"))
            path = Path(project_dir) / rel if rel else None
            exists = bool(path and path.is_file())
            tracked = bool(exists and is_tracked(project_dir, path))
            event = index["recorded"].get(pid)
            done_at = index["completed_at"].get(pid)
            source = "ledger" if done_at else None
            if not done_at and p.get("updated_at"):
                # An upper bound on the completion time: measured from it, the grace is never shorter than declared.
                done_at, source = p["updated_at"], "graph_updated_at"
            ts = _parse_ts(done_at)
            elapsed = (now - ts).total_seconds() if ts else None
            released = ("ooda_event" if event else "ooda_file" if tracked
                        else "grace" if elapsed is not None and elapsed >= grace else None)
            row = {"predecessor": pid, "name": p.get("name"), "state": p.get("state"),
                   "ooda_file": rel, "ooda_file_exists": exists, "ooda_file_tracked": tracked,
                   "ooda_event": event, "completed_at": str(done_at) if done_at else None,
                   "completed_at_source": source,
                   "elapsed_s": round(elapsed) if elapsed is not None else None,
                   "released_by": released}
            if released is None and ts is None:
                row["message"] = "completion time unknown; the grace cannot be measured"
            rows.append(row)
        out[t.get("artifact_id")] = {"grace_s": grace, "predecessors": rows,
                                     "ok": all(r["released_by"] for r in rows)}
    return out


def ooda_pending(project_dir: Path, tasks: list, cfg: dict, index: dict, now: datetime) -> list:
    """`seldon dispatch ooda pending` / `seldon_ooda_pending`: one row per (completed predecessor without a record,
    open successor), with the RESULT to read, the successor to amend, the record's path and the grace left.

    Listed whatever the grace: with no grace a record is still what the chain's author wants written. An infinite
    grace here releases only on a record, so every predecessor that lacks one is listed."""
    grace = cfg.get("ooda_grace_s", OODA_GRACE_S_DEFAULT)
    gates = ooda_waits(project_dir, tasks, {**cfg, "ooda_grace_s": float("inf")}, index, now)
    by_id = {t.get("artifact_id"): t for t in tasks}
    rows = []
    for tid, g in gates.items():
        for w in g["predecessors"]:
            if w["released_by"]:
                continue
            src = next((p.get("source_file") for p in by_id[tid].get("predecessors") or []
                        if p.get("artifact_id") == w["predecessor"]), None)
            rows.append({"predecessor": w["predecessor"], "predecessor_name": w["name"],
                         "result": str(Path(src).with_name(Path(src).stem + "_RESULT.md")) if src else None,
                         "ooda_file": w["ooda_file"], "successor": tid,
                         "successor_file": by_id[tid].get("source_file"), "grace_s": grace,
                         "grace_left_s": (max(0, grace - w["elapsed_s"])
                                          if grace and w["elapsed_s"] is not None else None),
                         "completed_at": w["completed_at"]})
    return rows


def ooda_pending_lines(rows: list) -> list:
    """The text both surfaces print for `ooda_pending`'s rows."""
    if not rows:
        return ["ooda: nothing pending"]
    out = []
    for r in rows:
        held = ("not held (dispatch.ooda_grace_s is 0)" if not r["grace_s"]
                else f"held {r['grace_left_s']} s more" if r["grace_left_s"] is not None
                else "held until a record (completion time unknown)")
        out.append(f"{r['predecessor'][:8]} {r['predecessor_name'] or ''} completed {r['completed_at'] or '?'}")
        out.append(f"  read:    {r['result']}")
        out.append(f"  amend:   {r['successor_file']} ({r['successor'][:8]}), {held}")
        out.append(f"  release: commit {r['ooda_file']}, or `seldon dispatch ooda record {r['predecessor'][:8]}`")
    return out


def ooda_record_event(task_id: str, state: str | None, by: str, note: str | None) -> dict:
    """The `ooda_recorded` payload for completed `task_id`; ValueError for a task with no RESULT to have read."""
    if state not in OODA_PREDECESSOR_STATES:
        raise ValueError(f"{task_id[:8]} is {state}; an OODA record answers a completed task's RESULT "
                         f"({', '.join(OODA_PREDECESSOR_STATES)})")
    return {"task_id": task_id, "by": by, "note": note}


# ------------------------------------------------------------------------------- evaluation

def union_state(project_dir: Path) -> dict:
    """Criterion c16's raw material (AD-034 ADDENDUM 05): the project's append-only logs and those git does not merge
    by union. `{required, missing, ok}`, plus `read_error` when the list cannot be made (fail closed: a launch whose
    rebase may conflict on every log is the launch this criterion exists to stop). Read once per pass, like c7's tree.
    """
    from seldon.core import hooks as H

    try:
        path = Path(project_dir) / "seldon.yaml"
        config = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else {}
        required = H.append_only_paths(project_dir, config or {})
        missing = H.union_missing(project_dir, config or {})
    except (H.HookError, OSError, yaml.YAMLError) as exc:
        return {"required": [], "missing": [], "ok": False, "read_error": str(exc)}
    return {"required": required, "missing": missing, "ok": not missing}


def evaluate(project_dir: Path, task: dict, cfg: dict, band: int, tree: dict,
             claim_in_flight: dict | None, lease_body: dict, running=None,
             premise_holds: dict | None = None, launch_holds: dict | None = None,
             union: dict | None = None, cross_waits: dict | None = None,
             ooda: dict | None = None) -> dict:
    """The eight criteria of DN-006 decision 2, each evaluated to a recorded VALUE.

    Never a boolean summary: a pass that says "ineligible" and nothing else is a pass a
    stranger cannot replay, and DD-065 is that every assertion the project makes carries the
    grounds it was made on.
    """
    source = task.get("source_file")
    task_file = project_dir / source if source else None
    if is_future(task.get("description")):
        # TRIAGE-001 Part B: a parked idea (rule 4's `FUTURE` prefix) is never a candidate, even
        # with a task file. `_tasks` already leaves these out of a pass; this holds for any caller.
        cand = {"candidate": False, "reason": "future", "message": None, "headers": {}}
    else:
        # SEL-011 (AD-038-R12): the static checks are the ones `seldon cc register` refuses on, by the same function.
        cand = (static_checks(task_file, cfg, project_dir) if task_file
                else {"candidate": False, "reason": "no_source_file", "message": None, "headers": {}})
    # `created_at` is carried through because `fifo` sorts on it (decision 9). It was dropped
    # here until SEL-004, so every pass sorted by `("", task_id)`: a random uuid order.
    out = {"task_id": task.get("artifact_id"), "name": task.get("name"),
           "state": task.get("state"), "source_file": source,
           "created_at": task.get("created_at"),
           "candidate": cand["candidate"], "not_a_candidate_reason": cand["reason"],
           # SEL-011 Part B: the grammar or rule the reason stands for, printed under the reason line.
           "not_a_candidate_message": cand.get("message"),
           "framework_layer": cand["headers"].get(HEADER_LAYER),
           # AD-035: what the header asked for (a role, an id) and, when refused, why.
           "model": cand.get("model")}
    if not cand["candidate"]:
        out["criteria"] = {}
        out["eligible"] = False
        return out

    headers = cand["headers"]
    sup = superseding_addendum(task_file)
    tokens = cand["tokens"]
    stop = project_dir / cfg["stop_file"]

    c = {}
    c["c1"] = {"state": task["state"], "source_file": source,
               "file_exists": task_file.is_file(),
               "git_tracked": is_tracked(project_dir, task_file),
               "ok": (task["state"] in DISPATCHABLE_STATES and task_file.is_file()
                      and is_tracked(project_dir, task_file))}
    preds = task.get("predecessors") or []
    unsatisfied = [p for p in preds if p.get("state") not in PREDECESSOR_SATISFIED]
    c["c2"] = {"predecessors": len(preds),
               "unsatisfied": [{"id": p.get("artifact_id"), "state": p.get("state")}
                               for p in unsatisfied],
               "ok": not unsatisfied}
    c["c3"] = {"addenda": [p.name for p in addenda_for(task_file)],
               "superseding": sup.name if sup else None, "ok": sup is None}
    c["c4"] = {"spend_header": headers[HEADER_SPEND], "declared_tokens": tokens,
               "standing_band": band, "band_ref": cfg["standing_band_ref"],
               "ok": tokens is not None and tokens <= band}
    if tokens is None:
        c["c4"]["message"] = (f"Spend header {headers[HEADER_SPEND]!r} names neither `zero` nor a token count; "
                              f"expected {SPEND_GRAMMAR}")
    net = cand["network"]
    c["c5"] = {"network_header": headers[HEADER_NETWORK], "network_kind": net["kind"],
               "network_allowlist": net["hosts"], "ok": net["kind"] is not None}
    if net["error"]:
        c["c5"]["message"] = net["error"]
    c["c6"] = {"in_progress_claim": claim_in_flight,
               "lease_task": lease_body.get("task"),
               "lease_holder": lease_body.get("holder"),
               "ok": claim_in_flight is None}
    c["c7"] = {"branch": tree["branch"], "configured_branch": cfg["branch"],
               "dirty": tree["dirty"], "dirty_count": tree["dirty_count"],
               "dirty_paths": tree["dirty_paths"],
               "ok": (tree["branch"] == cfg["branch"] and not tree["dirty"]
                      and not tree.get("read_error"))}
    if tree.get("read_error"):
        c["c7"]["read_error"] = tree["read_error"]
    if tree.get("dirty") and tree.get("unreconciled"):
        # AD-038-R1: the paths the reconciler could not or may not commit, and why. Absent on a clean
        # tree, so the criteria vector the serial transcript holds for a launch is unchanged.
        c["c7"]["unreconciled"] = tree["unreconciled"]
    c["c8"] = {"enabled": cfg["enabled"], "stop_file": str(cfg["stop_file"]),
               "stop_file_present": stop.exists(),
               "ok": bool(cfg["enabled"]) and not stop.exists()}
    #: ADDENDUM_01's criterion, numbered beyond DN-006's table rather than renumbering it: the
    #: note's decision 2 is cited by id elsewhere and a c-number that means two things in two
    #: documents is worse than a table with a ninth row.
    c["c9"] = {"framework_layer": headers[HEADER_LAYER], "ok": True}

    # SEL-004 (AD-034). For a serial pass and a task with neither header c6 keeps its meaning and c10
    # is absent; c11 is present for every task since FRICTION-002 (below).
    parallel = cfg.get("max_parallel", MAX_PARALLEL_DEFAULT) > 1
    conc = cand["concurrency"]
    out["concurrency"] = conc
    if parallel:
        # c6 in parallel mode: no claim in flight IN THIS CHECKOUT (an exclusive task runs
        # here); claims in worktrees are the running set, and whether this task may run beside
        # them is decided by `plan_launches`, which updates this criterion.
        c["c6"] = {"in_place_claim": claim_in_flight, "running": list(running or []),
                   "max_parallel": cfg["max_parallel"],
                   "lease_holder": lease_body.get("holder"), "ok": claim_in_flight is None}
    if conc["declared"] or parallel:
        c["c10"] = {"declared": conc["declared"], "exclusive": conc["exclusive"],
                    "resources": conc["resources"], "paths": conc["paths"],
                    "ok": conc["error"] is None}
        if conc["error"]:
            c["c10"]["message"] = conc["error"]
    # FRICTION-002 Part B (AD-034 ADDENDUM 01): every task runs in its own worktree, exclusive or not and at any
    # `max_parallel`, so c11 (the worktree path and branch are free and ignored) is every task's criterion.
    # `Exclusive:` decides only whether a task may run beside others, never where it runs.
    if conc["error"] is None:
        c["c11"] = worktree_state(project_dir, cfg)
    # SQ-010 ADDENDUM 02 D3.4: free space against this launch's own measured need, before any claim. Every
    # launch checks a tree out into a worktree.
    c["c12"] = disk_state(project_dir, cfg, worktree=conc["error"] is None)

    # QC-002 (AD-037-R6 a): a task whose last premise review filed an Issue that is still open waits on it. Absent
    # for every other task, so the criteria vector the serial transcript holds is unchanged.
    hold = (premise_holds or {}).get(task.get("artifact_id"))
    if hold:
        c["c13"] = {**hold, "ok": False}
    # DESK-001 (AD-036 ADDENDUM 05): R4's dispatch point. A draft note may be committed, so the gate
    # that used to refuse its commit refuses the launch of a task it governs instead. Absent unless it
    # fails, like c13, so the criteria vector the serial transcript holds is unchanged.
    unverified = governing_unverified(project_dir, task_file)
    if unverified:
        c["c14"] = {"unverified": unverified, "ok": False}
    # DISP-001R Part A step 2: a task whose last launch ended before any model turn waits until the launcher or
    # the task changes (`seldon.commands.dispatch._launch_holds`). Absent otherwise, like c13.
    failed_launch = (launch_holds or {}).get(task.get("artifact_id"))
    if failed_launch:
        c["c15"] = {**failed_launch, "ok": False}
    # ATTR-001 (AD-034 ADDENDUM 05): every task merges back through a rebase, and an append-only log git does not
    # merge by union conflicts on that rebase whenever main gained a line meanwhile (squiddy SQ-021, 2026-10-23). The
    # pass reads `union_state` once and passes it; absent unless it fails, like c13, so the criteria vector is unchanged.
    if union is not None and not union["ok"]:
        c["c16"] = {**union, "ok": False}
    # SEL-008 (AD-038-R8): a task that waits on a task in ANOTHER project's graph is not ready until that task reaches
    # terminal success, and a wait whose graph could not be read is not ready either (fail closed, like c14). The
    # caller reads the other graphs once per pass (`seldon.core.cross_project.unsatisfied_waits`) and passes only the
    # unsatisfied waits; absent unless it fails, like c13, so the criteria vector is unchanged for every other task.
    waits = (cross_waits or {}).get(task.get("artifact_id"))
    if waits:
        c["c17"] = {"waits_on": waits, "ok": False}
    # SEL-010R2 (AD-038-R10): a chained task waits for the Desktop OODA on its completed predecessor, or the project's
    # grace. The caller reads the ledger once per pass (`ooda_waits`); present only for a task with a completed
    # predecessor in a project whose grace is above 0, so every other vector, and the serial transcript, are unchanged.
    gate = (ooda or {}).get(task.get("artifact_id"))
    if gate:
        c["c18"] = gate

    out["criteria"] = c
    out["eligible"] = all(v["ok"] for v in c.values())
    out["failed"] = [k for k, v in c.items() if not v["ok"]]
    return out


def first_refusal_reason(row: dict) -> str | None:
    """The refusal reason DN-006 decision 7 names, for a row that failed. Ordered so the
    SYSTEM-wide conditions are reported ahead of the task-specific ones: `disabled` and
    `stop_file` are facts about the pass, and reporting a per-task reason instead would put a
    task's name on a refusal that had nothing to do with it."""
    c = row.get("criteria") or {}
    if not c.get("c8", {}).get("ok", True):
        return "stop_file" if c["c8"]["stop_file_present"] else "disabled"
    # Free space is a fact about the machine, not the task: reported ahead of the task-specific reasons.
    if not c.get("c12", {}).get("ok", True):
        return "disk_unmeasured" if c["c12"].get("read_error") else "disk_short"
    if not c.get("c7", {}).get("ok", True):
        return c7_reason(c["c7"])
    # A fact about the checkout, like c7, so reported ahead of the task-specific reasons.
    if not c.get("c16", {}).get("ok", True):
        return "union_attribute_missing"
    if not c.get("c4", {}).get("ok", True):
        return "spend_unreadable" if c["c4"].get("declared_tokens") is None else "above_band"
    if not c.get("c5", {}).get("ok", True):
        return "network_undeclared"
    if not c.get("c10", {}).get("ok", True):
        return "concurrency_undeclared"
    if not c.get("c11", {}).get("ok", True):
        return "worktree_unavailable"
    if not c.get("c13", {}).get("ok", True):
        return "premise_false"
    if not c.get("c14", {}).get("ok", True):
        return "governing_unverified"
    if not c.get("c15", {}).get("ok", True):
        return "launch_failed"
    if not c.get("c17", {}).get("ok", True):
        return ("waits_on_unreachable" if any(w.get("error") and w.get("state") is None
                                              and w.get("error") != "no longer resolves"
                                              for w in c["c17"]["waits_on"])
                else "waits_on_unsatisfied")
    if not c.get("c18", {}).get("ok", True):
        return "ooda_pending"
    return None


def governing_unverified(project_dir: Path, task_file: Path) -> list:
    """Criterion c14: the task's governing notes with no passing prior-art verdict (DESK-001).

    `[{"note", "why"}]`, empty when every one passes or the project declares no `prior_art:`
    block. A gate that cannot be evaluated fails closed with one row naming why: a launch on an
    unknown verdict is the launch this criterion exists to stop.
    """
    from seldon.core import prior_art as pa

    try:
        path = Path(project_dir) / "seldon.yaml"
        config = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else {}
        rows = pa.registration_holds(task_file, Path(project_dir), config or {})
    except (pa.PriorArtError, OSError, yaml.YAMLError) as exc:
        return [{"note": None, "why": f"the prior-art gate cannot be evaluated: {exc}"}]
    return [{"note": r["note"], "why": r["why"]} for r in rows]


def c7_reason(c7: dict) -> str:
    """Which half of c7 failed. **`dirty_tree` only when there is a path to name**
    (ai-readiness-kg/cc_tasks/2026-10-09_main_green_dispatch_stuck_without_a_path.md decision 3).

    The incident: the daily suite's worktree is a detached HEAD, so c7 failed on its branch half
    with a clean tree, and the pass reported `dirty_tree`, printed `dirty: (branch)`, and after
    three passes wrote a `dispatch_stuck` whose `dirty_paths` was `[]`. A refusal that names no
    dirt sends the reader looking for dirt. A dirty tree on the wrong branch is reported as dirty,
    because the paths are the more specific evidence."""
    if c7.get("read_error"):
        return "tree_unreadable"
    if c7.get("dirty"):
        return "dirty_tree"
    return "wrong_branch"


def fifo(rows: list) -> list:
    """DN-006 decision 9: FIFO by `created_at` among eligible tasks, and nothing else. The
    Desktop orders work with `precedes` edges; a priority field would be a value nobody
    measured."""
    return sorted(rows, key=lambda r: (r.get("created_at") or "", r.get("task_id") or ""))


def api_key_present(env: dict | None = None) -> str | None:
    """The name of the first API-key variable set, or None. DD-007."""
    env = os.environ if env is None else env
    for var in API_KEY_VARS:
        if env.get(var):
            return var
    return None
