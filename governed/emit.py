"""The governed-documents emitter: one manifest entry and its parsed markdown in; typed instances
of Document, Section, Ruling, Citation, Passage and the closed edge set out (AD-030).

This is the graph's half of the write path. The kit parses, hashes, scopes and appends; everything
here is deterministic, reads no network and calls no model. Every rule that decides *what* a piece
of text is lives in `config.yaml` under `domain:` — the ruling patterns, the identifier patterns,
the header fields, the CiTO markers — and every node this module mints records which configured
rule produced it. A wrong classification is then a pattern to fix, not a judgement to relitigate.

THE EDGES ARE SPLIT ACROSS TWO PASSES, and that is the point rather than an accident. `emit` writes
only what is inside one document, so every endpoint it names already exists and an admission can
never leave a dangling pointer. Cross-document edges — `Extends`, `DependsOn`, the `Mentions` that
resolve to another governed document — are `emit_layer`'s, run after every Document is in the
ledger. An identifier that resolves in no document of THIS graph is not dropped: it is carried on
the node as `identifiers`, because a task id resolves in Seldon's graph and Seldon is what can see
it (AD-030-R10).

The kit calls `emit(entry, resolved, graph, classes)`, `emit_layer(entry, resolved, graph, classes,
layer, context)` and `manifest_projection(entry, graph)`.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path

_SLUG_KEEP = re.compile(r"[^a-z0-9]+")

#: Header fields are read from the block above the first `---` rule or the first `##` heading,
#: whichever comes first. Below that a document is prose, and `Extends:` inside prose is a
#: sentence rather than a declaration.
_HEADER_FIELD_RE_TEMPLATE = r"^\s*\*{{0,2}}{field}:\*{{0,2}}\s*(.+?)\s*$"

#: A reference-list line: a bullet whose text is a citation. The prior-art lists AD-030 section 6
#: and every design note in this repository use this shape.
_REFERENCE_LINE_RE = re.compile(r"^\s*[-*+]\s+(.*\S)\s*$")

#: A backticked CiTO token inside a reference line, optionally followed by a target and a reason.
_CITO_RE_TEMPLATE = r"`{token}`(?:\s+(?:for|on)\s+(?P<target>[^,.;]+?))?(?:\s*,\s*reason:\s*(?P<reason>[^.]+))?(?=[.;,]|$)"

#: A quoted span: a markdown blockquote, or a double-quoted run of at least this many characters.
#: Shorter runs are ordinary emphasis, not quotation (AD-030-R6: a Passage exists when a span was
#: quoted, and a two-word phrase in quotes is a term, not a span).
MIN_QUOTE_CHARS = 40
_DOUBLE_QUOTE_RE = re.compile(r"[“\"]([^“”\"]{%d,})[”\"]" % MIN_QUOTE_CHARS)

#: Block kinds the emitter reads as prose that can carry a ruling, an identifier or a citation.
_PROSE_KINDS = ("paragraph", "list_item", "blockquote", "table")


def slug(s: str) -> str:
    """Lowercase, ASCII-folded, non-alphanumerics collapsed to `_`.

    Args:
        s: Any string.

    Returns:
        A key-safe slug. Empty input yields an empty string.
    """
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return _SLUG_KEEP.sub("_", s.lower()).strip("_")


def doc_id_for(rel_path: str) -> str:
    """The Document key for a repo-relative governed path.

    The key is derived from the path because that is what a reader has in hand; identity still
    rests on `content_hash` (AD-030-R4), and a governed document does not move.

    Args:
        rel_path: Repo-relative path, e.g. `docs/design/AD-030_governed.md`.

    Returns:
        A stable slug, e.g. `docs_design_ad_030_governed`.
    """
    return slug(rel_path.rsplit(".", 1)[0])


def section_id_for(doc_id: str, section_path: str | None, ordinal: int) -> str:
    """The Section key: `<doc>#<slug of the section path>`.

    Stable across every edit that leaves the heading alone, which is what lets a task cite a
    ruling in March and still be citing it in September. A section with no heading (prose before
    the first heading) falls back to its ordinal, because it has no name to be stable about.

    Args:
        doc_id: The Document key.
        section_path: The heading stack, joined, or None.
        ordinal: Reading-order position, used only for the unnamed case.

    Returns:
        The section key.
    """
    return f"{doc_id}#{slug(section_path)}" if section_path else f"{doc_id}#preamble_{ordinal}"


def sha256_text(text: str) -> str:
    """sha256 of a string's UTF-8 bytes.

    Args:
        text: The text to hash.

    Returns:
        Hex digest.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Reading the parsed intermediate
# ---------------------------------------------------------------------------

def parsed_path(graph, doc_id: str) -> Path:
    """Where `squiddy.parse` cached this document's blocks.

    Args:
        graph: The loaded graph.
        doc_id: The manifest id.

    Returns:
        Path to the cached intermediate.
    """
    return graph.path("parsed_dir") / f"{doc_id}.json"


def load_parsed(graph, doc_id: str) -> dict:
    """Read the parsed intermediate for one document.

    Args:
        graph: The loaded graph.
        doc_id: The manifest id.

    Returns:
        The cached `{plain_text, blocks, ...}` mapping.

    Raises:
        SystemExit: If the parse stage has not run. An emitter that invented an empty document
            here would admit a node with a title and no content, which is the failure the kit's
            own read stage exists to refuse.
    """
    path = parsed_path(graph, doc_id)
    if not path.is_file():
        raise SystemExit(
            f"FATAL: no parsed intermediate for {doc_id} at {path}; the parse stage must run "
            f"before the read stage"
        )
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Classification, all of it driven by config
# ---------------------------------------------------------------------------

def compiled_rules(domain: dict, key: str, pattern_field: str = "pattern") -> list[tuple[dict, re.Pattern]]:
    """Compile a configured rule list once.

    Args:
        domain: The graph's `domain:` block.
        key: Which rule list to compile.
        pattern_field: Field holding the regular expression.

    Returns:
        `(rule, compiled)` pairs in declaration order, which is precedence order.

    Raises:
        SystemExit: If a configured pattern does not compile. A broken pattern must be named at
            load, not silently match nothing for a year.
    """
    out = []
    for rule in domain.get(key) or []:
        try:
            out.append((rule, re.compile(rule[pattern_field], re.MULTILINE)))
        except re.error as exc:
            raise SystemExit(f"FATAL: domain.{key} pattern {rule.get('name') or rule[pattern_field]!r} "
                             f"does not compile: {exc}")
    return out


def classify_ruling(
    text: str,
    rules: list[tuple[dict, re.Pattern]],
    force_rules: list[tuple[dict, re.Pattern]] | None = None,
    default_force: str = "binding",
) -> dict | None:
    """Return the configured ruling pattern this text matches, and the force it carries.

    TWO QUESTIONS, ANSWERED SEPARATELY (AD-030-R16). *Is this a Ruling?* is decided by position —
    a ruling identifier or the BINDING banner in the heading or the first token — because deciding
    it by vocabulary made every paragraph containing "must" a ruling and left the corpus with no
    rulings in it. *What force does it carry?* is then read from the text of a block already known
    to be a ruling, which R16 does not forbid and which is the only thing that distinguishes a
    prohibition from a recommendation.

    Precedence is declaration order in both lists.

    Args:
        text: The block's verbatim text.
        rules: Compiled ruling-classification rules.
        force_rules: Compiled force rules, or None to use `default_force` for everything.
        default_force: Force for a ruling that states its force no more precisely than by being one.

    Returns:
        `{"name", "force"}` for the matching rule, or None when the block is not a ruling.
    """
    for rule, pattern in rules:
        if pattern.search(text):
            return {"name": rule["name"], "force": deontic_force(text, force_rules, default_force)}
    return None


def deontic_force(
    text: str,
    force_rules: list[tuple[dict, re.Pattern]] | None,
    default_force: str = "binding",
) -> str:
    """Read the force of a block already classified as a Ruling.

    Args:
        text: The ruling's verbatim text.
        force_rules: Compiled force rules, in precedence order.
        default_force: Returned when no rule matches.

    Returns:
        One of the DeonticForce values.
    """
    for rule, pattern in force_rules or ():
        if pattern.search(text):
            return rule["force"]
    return default_force


#: A document's own label for a ruling: `AD-030-R9`, or the `Addendum 029-A` form this repository
#: also uses for an amendment to a decision. Both are stable across every edit of the ruling's
#: text, which is the whole point of taking the id from the label rather than from the ordinal.
_RULING_IDENTIFIER_RE = re.compile(r"\b([A-Z]{2,4}-\d+-R\d+|Addendum\s+\d+-[A-Za-z0-9]+)\b")


def ruling_identifier(text: str) -> str | None:
    """Extract the document's own label for a ruling, when it writes one.

    Args:
        text: The block's verbatim text.

    Returns:
        The identifier, or None.
    """
    match = _RULING_IDENTIFIER_RE.search(text)
    return " ".join(match.group(1).split()) if match else None


def ruling_blocks(doc_id: str, blocks: list[dict], domain: dict) -> list[dict]:
    """Every block of a document that is a Ruling, with the id it will carry.

    ONE READING, TWO CALLERS. `emit` mints the Ruling nodes and `emit_layer` recovers the
    supersession edges between them; if the two disagreed about which blocks are rulings or about
    what a ruling's id is, the edges would point at nodes that do not exist. Sharing the pass is
    what makes that impossible rather than merely unlikely.

    Args:
        doc_id: The Document key.
        blocks: The parsed blocks, in reading order.
        domain: The graph's `domain:` block.

    Returns:
        `{"id", "identifier", "force", "matched_pattern", "block"}` per ruling, in reading order.
        A ruling with no label of its own falls back to its ordinal, which is stable only while
        the document's other rulings are.
    """
    rules = compiled_rules(domain, "ruling_patterns")
    force_rules = compiled_rules(domain, "force_patterns")
    default_force = domain.get("default_force", "binding")
    out: list[dict] = []
    for block in blocks:
        if block["kind"] not in ("heading", *_PROSE_KINDS):
            continue
        match = classify_ruling(block["text"], rules, force_rules, default_force)
        if not match:
            continue
        identifier = ruling_identifier(block["text"])
        ruling_id = (f"{doc_id}!{slug(identifier)}" if identifier
                     else f"{doc_id}!r{len(out):03d}")
        out.append({"id": ruling_id, "identifier": identifier, "force": match["force"],
                    "matched_pattern": match["name"], "block": block})
    return out


def supersedes_references(text: str, pattern: re.Pattern | None) -> list[str]:
    """The ruling identifiers a ruling declares it supersedes (AD-030-R21).

    Args:
        text: The ruling's verbatim text.
        pattern: The compiled supersession pattern, or None to recover nothing.

    Returns:
        Hyphenated ruling identifiers, in order, deduplicated. Empty when the text declares none —
        which includes text that merely discusses a supersession, because R21 makes supersession
        declared rather than inferred.
    """
    if pattern is None:
        return []
    out: list[str] = []
    for match in pattern.finditer(text or ""):
        for ident in re.findall(r"[A-Z]{2,4}-\d+-R\d+", match.group(1)):
            if ident not in out:
                out.append(ident)
    return out


def identifier_references(text: str, rules: list[tuple[dict, re.Pattern]]) -> list[dict]:
    """Every identifier the text names, by the graph's declared patterns.

    Args:
        text: Text to scan.
        rules: Compiled identifier rules.

    Returns:
        `{"identifier", "kind", "occurrences"}` per distinct identifier, in first-appearance order.
    """
    found: dict[str, dict] = {}
    for rule, pattern in rules:
        for match in pattern.finditer(text):
            ident = match.group(0)
            if ident in found:
                found[ident]["occurrences"] += 1
            else:
                found[ident] = {"identifier": ident, "kind": rule["kind"], "occurrences": 1}
    return list(found.values())


def header_fields(plain_text: str, fields: list[str]) -> dict[str, str]:
    """Read the declaration block at the top of a governed document.

    Only the header is read. `Extends:` below the first `---` rule or the first `##` heading is a
    sentence in prose, not a declaration, and treating it as one would mint edges out of examples.

    Args:
        plain_text: The whole document.
        fields: Field names to look for, e.g. `["Extends", "Depends on"]`.

    Returns:
        Mapping of field name to its raw value, for the fields present.
    """
    lines = plain_text.splitlines()
    end = len(lines)
    for i, line in enumerate(lines):
        if re.match(r"^ {0,3}-{3,}\s*$", line) and i > 0:
            end = i
            break
        if re.match(r"^ {0,3}#{2,6}\s+\S", line):
            end = i
            break
    header = "\n".join(lines[:end])
    out = {}
    for field in fields:
        pattern = re.compile(
            _HEADER_FIELD_RE_TEMPLATE.format(field=re.escape(field)), re.MULTILINE | re.IGNORECASE
        )
        match = pattern.search(header)
        if match:
            out[field] = match.group(1).strip()
    return out


def cito_in_line(line: str, markers: list[dict]) -> dict | None:
    """Find a CiTO type declared in a reference line.

    The form AD-030 section 6 uses: a bullet ending in a backticked type, optionally `for <target>`
    and `, reason: <why>`. The reason matters most on `disagrees_with` and `refutes`, where
    AD-030-R7 requires the constraint to be named.

    Args:
        line: The reference line's text.
        markers: The `domain.cito_markers` list.

    Returns:
        `{"cito_type", "target", "reason"}`, or None when no marker appears.
    """
    for marker in markers:
        pattern = re.compile(_CITO_RE_TEMPLATE.format(token=re.escape(marker["token"])))
        match = pattern.search(line)
        if match:
            return {
                "cito_type": marker["cito_type"],
                "target": (match.group("target") or "").strip() or None,
                "reason": (match.group("reason") or "").strip() or None,
            }
    return None


def looks_like_reference(text: str) -> bool:
    """Return True when a bullet reads as a citation rather than as ordinary prose.

    The test is the shape a reference has and a sentence does not: a year in parentheses, a `doi:`
    or `https://doi.org/`, or an `et al.` A bullet with none of these is a list item.

    Args:
        text: The bullet's text.

    Returns:
        True when it reads as a citation.
    """
    return bool(
        re.search(r"\(\d{4}[a-z]?\)", text)
        or re.search(r"\b(?:doi:|https?://(?:dx\.)?doi\.org/)", text, re.IGNORECASE)
        or re.search(r"\bet al\.", text)
    )


_DOI_RE = re.compile(r"\b(?:doi:\s*|https?://(?:dx\.)?doi\.org/)(10\.\d{4,9}/\S+?)(?=[\s.,;)]|$)",
                     re.IGNORECASE)
_YEAR_RE = re.compile(r"\((\d{4})[a-z]?\)")


def citation_fields(raw: str) -> dict:
    """Pull the structured fields a reference line states plainly.

    Deliberately shallow: a full reference parser is a project, and AD-030-R6 says capture is free
    and verification is separate. What is extracted here is what a later verification step needs
    to look the reference up.

    Args:
        raw: The reference line.

    Returns:
        Mapping with any of `authors`, `year`, `doi`, `title`.
    """
    out: dict[str, str] = {}
    doi = _DOI_RE.search(raw)
    if doi:
        out["doi"] = doi.group(1).rstrip(".")
    year = _YEAR_RE.search(raw)
    if year:
        out["year"] = year.group(1)
        authors = raw[: year.start()].strip().strip(".,;")
        if authors:
            out["authors"] = authors
        rest = raw[year.end():].strip().lstrip(".").strip()
        title = re.split(r"(?<=[a-z0-9])\.\s", rest, maxsplit=1)[0].strip()
        if title:
            out["title"] = title[:300]
    return out


def quoted_spans(text: str) -> list[str]:
    """Every quoted span in a block, long enough to be a quotation.

    Args:
        text: The block's verbatim text.

    Returns:
        The quoted strings, in order.
    """
    return [m.group(1).strip() for m in _DOUBLE_QUOTE_RE.finditer(text)]


# ---------------------------------------------------------------------------
# The kit's two entry points
# ---------------------------------------------------------------------------

def doc_kind_for(rel_path: str, domain: dict) -> str | None:
    """Which governed directory a path belongs to.

    Args:
        rel_path: Repo-relative path.
        domain: The graph's `domain:` block.

    Returns:
        The configured `doc_kind`, or None when the path is not under a governed directory.
    """
    for entry in domain.get("governed_directories") or []:
        prefix = entry["path"].rstrip("/") + "/"
        if rel_path.startswith(prefix):
            return entry["doc_kind"]
    return None


#: The kit's stage axis mapped onto the four document states AD-030-R5 names. `admitting` maps to
#: `admitted` because that is when the Document node is written: the kit flips the stage to
#: `in_graph` on the FAR side of the append, so a projection that read `admitting` as `held` would
#: be compared, one stage later, against a manifest that had already flipped — the ledger would
#: report as lagging a manifest it is exactly in step with.
_STATE_BY_STAGE = {
    "cataloged": "cataloged",
    "acquired": "held",
    "admitting": "admitted",
    "in_graph": "admitted",
    "assess_queue": "held",
}


def manifest_state_for(entry: dict) -> str:
    """The AD-030-R5 state of one manifest entry.

    Args:
        entry: The manifest entry.

    Returns:
        `cataloged`, `held`, `admitted` or `declined`. A disposition in the `excluded:` family is
        `declined` whatever the stage says, because a declined document never receives a content
        edge and the stage axis does not carry that fact.
    """
    if str(entry.get("disposition") or "").startswith("excluded:"):
        return "declined"
    return _STATE_BY_STAGE.get(entry.get("stage"), "cataloged")


def manifest_projection(entry: dict, graph) -> dict:
    """The Document properties that come from the manifest verbatim.

    The manifest-to-ledger gate compares exactly these, so anything the emitter derives from the
    document's text must stay out: a derived count changing when the file changes is the hash's
    job to notice, not this gate's.

    Args:
        entry: The manifest entry.
        graph: The loaded graph.

    Returns:
        The gated properties, with None values dropped.
    """
    rel = (entry.get("source_url") or "").strip()
    props = {
        "id": entry["id"],
        "title": entry.get("title"),
        "path": rel or None,
        "doc_kind": entry.get("doc_kind") or doc_kind_for(rel, graph.domain),
        "manifest_state": manifest_state_for(entry),
        "content_hash": entry.get("sha256"),
        "sha256": entry.get("sha256"),
        "local_path": entry.get("local_path"),
        "byte_length": entry.get("bytes"),
        "disposition": entry.get("disposition"),
        "seldon_artifact_id": entry.get("seldon_artifact_id"),
        "reason": entry.get("decline_reason"),
        "decided_by": entry.get("decided_by"),
        "decided_date": entry.get("decided_date"),
    }
    return {k: v for k, v in props.items() if v is not None}


def declared_name(plain_text: str, domain: dict) -> str | None:
    """The name a document declares for itself in its header (AD-030-R20).

    Args:
        plain_text: The whole document.
        domain: The graph's `domain:` block; `name_field` names the header field.

    Returns:
        The declared name, or None when the document declares none and a derivation must stand in.
    """
    field = domain.get("name_field")
    if not field:
        return None
    value = header_fields(plain_text, [field]).get(field)
    value = " ".join((value or "").split()).strip("`*")
    return value or None


def _document_instance(entry, graph, classes, parsed, sections, rulings):
    """Build the Document instance for one admitted entry."""
    props = manifest_projection(entry, graph)
    props["method"] = "governed_markdown_ingest"
    props["content_hash"] = props.get("content_hash") or sha256_text(parsed["plain_text"])
    props["section_count"] = len(sections)
    props["ruling_count"] = len(rulings)
    # NOT in manifest_projection: the drift gate compares exactly those fields against the
    # manifest, and this one is read from the document's text, which the manifest never holds.
    name = declared_name(parsed["plain_text"], graph.domain)
    if name:
        props["declared_name"] = name
    return classes["Document"](**props)


def emit(entry: dict, resolved: dict | None, graph, classes: dict) -> list:
    """Instances for one admitted governed document.

    Args:
        entry: The manifest entry.
        resolved: The acquisition record, or None.
        graph: The loaded graph.
        classes: Class name to generated Pydantic class.

    Returns:
        Node instances followed by edge instances. Nodes first so the projection's endpoint index
        is populated before any edge is replayed.

    Raises:
        SystemExit: If the parse stage has not run for this entry.
    """
    domain = graph.domain
    doc_id = entry["id"]
    parsed = load_parsed(graph, doc_id)
    plain = parsed["plain_text"]
    blocks = parsed["blocks"]
    doc_hash = entry.get("sha256") or sha256_text(plain)

    ident_rules = compiled_rules(domain, "identifier_patterns")
    rulings_by_block = {r["block"]["idx"]: r for r in ruling_blocks(doc_id, blocks, domain)}
    cito_markers = domain.get("cito_markers") or []
    inline_pattern = re.compile(domain["inline_citation_pattern"]) if domain.get("inline_citation_pattern") else None

    nodes: list = []
    edges: list = []
    sections: list[dict] = []
    rulings: list[dict] = []
    seen_section_ids: set[str] = set()
    seen_citations: set[str] = set()
    # Identifier references per node id. Carried onto the node rather than turned into edges here:
    # most of them resolve in Seldon's graph, not in this one (see the module docstring).
    node_identifiers: dict[str, list[str]] = {}

    def note_identifiers(node_id: str, text: str) -> None:
        """Record every identifier reference a block names, against the node that carries it."""
        bucket = node_identifiers.setdefault(node_id, [])
        for ref in identifier_references(text, ident_rules):
            if ref["identifier"] not in bucket:
                bucket.append(ref["identifier"])

    # ---- sections ------------------------------------------------------
    current_section_id: str | None = None
    for block in blocks:
        if block["kind"] != "heading":
            continue
        ordinal = len(sections)
        section_id = section_id_for(doc_id, block["section_path"], ordinal)
        if section_id in seen_section_ids:
            # Two headings with identical text at the same nesting produce the same key. The
            # ordinal disambiguates and is recorded, rather than one section silently replacing
            # the other.
            section_id = f"{section_id}~{ordinal}"
        seen_section_ids.add(section_id)
        start, end = block["char_span"]
        # The section's span runs to the next heading of the same or shallower level, so a
        # Section is its content and not just its title line.
        body_end = _section_body_end(blocks, block, len(plain))
        text = plain[start:body_end]
        sections.append({"id": section_id, "block": block, "text": text})
        nodes.append(classes["Section"](
            id=section_id, doc_id=doc_id, heading=block["text"].lstrip("# ").strip(),
            level=block["level"], ordinal=ordinal, section_path=block["section_path"],
            text=text, span_start=start, span_end=body_end,
            content_hash=sha256_text(text), method="governed_markdown_ingest",
        ))
        edges.append(classes["Contains"](subject=doc_id, object=section_id,
                                         method="governed_markdown_ingest"))

    section_by_block_idx = _section_index(blocks, sections)

    # ---- rulings, citations, passages, mentions -------------------------
    for block in blocks:
        kind = block["kind"]
        text = block["text"]
        start, end = block["char_span"]
        section_id = section_by_block_idx.get(block["idx"])

        ruling = rulings_by_block.get(block["idx"])
        if ruling:
            rulings.append(ruling["id"])
            nodes.append(classes["Ruling"](
                id=ruling["id"], doc_id=doc_id, ruling_identifier=ruling["identifier"],
                force=ruling["force"], matched_pattern=ruling["matched_pattern"],
                section_id=section_id, section_path=block["section_path"],
                text=text, span_start=start, span_end=end,
                content_hash=sha256_text(text), method="governed_markdown_ingest",
            ))
            edges.append(classes["Contains"](subject=doc_id, object=ruling["id"],
                                             method="governed_markdown_ingest"))
            note_identifiers(ruling["id"], text)

        if kind in _PROSE_KINDS or kind == "heading":
            note_identifiers(section_id or doc_id, text)

        # ---- citations --------------------------------------------------
        if kind == "list_item":
            reference = _REFERENCE_LINE_RE.match(text.splitlines()[0] or "")
            body = " ".join(line.strip() for line in text.splitlines()).strip()
            body = _REFERENCE_LINE_RE.sub(r"\1", body, count=1) if reference else body
            if looks_like_reference(body):
                citation_id = f"{doc_id}@{slug(body)[:80]}"
                if citation_id not in seen_citations:
                    seen_citations.add(citation_id)
                    fields = citation_fields(body)
                    nodes.append(classes["Citation"](
                        id=citation_id, doc_id=doc_id, citation_state="proposed", raw=body,
                        title=fields.get("title"), authors=fields.get("authors"),
                        year=fields.get("year"), doi=fields.get("doi"),
                        method="governed_markdown_ingest",
                    ))
                    cito = cito_in_line(body, cito_markers)
                    edges.append(classes["Cites"](
                        subject=section_id or doc_id, object=citation_id,
                        cito_type=(cito or {}).get("cito_type") or domain.get("cito_default", "cites_for_information"),
                        reason=(cito or {}).get("reason"), raw_reference=body[:400],
                        method="lexical_reference_list",
                    ))

        if inline_pattern and kind in _PROSE_KINDS:
            for match in inline_pattern.finditer(text):
                raw = f"{match.group(1)} ({match.group(2)})"
                citation_id = f"{doc_id}@{slug(raw)}"
                if citation_id in seen_citations:
                    continue
                seen_citations.add(citation_id)
                nodes.append(classes["Citation"](
                    id=citation_id, doc_id=doc_id, citation_state="proposed", raw=raw,
                    authors=match.group(1), year=match.group(2),
                    method="governed_markdown_ingest",
                ))
                edges.append(classes["Cites"](
                    subject=section_id or doc_id, object=citation_id,
                    cito_type=domain.get("cito_default", "cites_for_information"),
                    raw_reference=raw, method="lexical_inline_citation",
                ))

        # ---- passages ---------------------------------------------------
        spans = [text.lstrip("> ").strip()] if kind == "blockquote" else quoted_spans(text)
        for i, span in enumerate(spans):
            if len(span) < MIN_QUOTE_CHARS:
                continue
            passage_id = f"{doc_id}~{sha256_text(span)[:16]}"
            nodes.append(classes["Passage"](
                id=passage_id, doc_id=doc_id, text=span, span_start=start, span_end=end,
                quoted_in_section=section_id, content_hash=sha256_text(span),
                method="governed_markdown_ingest",
            ))
            edges.append(classes["Contains"](subject=doc_id, object=passage_id,
                                             method="governed_markdown_ingest"))

    # Attach the recovered identifiers to the nodes that named them. Rebuilding the instance is
    # how a Pydantic model gains a field it was constructed without, and the round trip validates
    # the result a second time.
    nodes = [
        type(node)(**{**node.model_dump(exclude_none=True), "identifiers": node_identifiers[node.id]})
        if node_identifiers.get(node.id) else node
        for node in nodes
    ]

    document = _document_instance(entry, graph, classes, parsed, sections, rulings)
    doc_identifiers = sorted({i for ids in node_identifiers.values() for i in ids})
    if doc_identifiers:
        document = classes["Document"](
            **{**document.model_dump(exclude_none=True), "identifiers": doc_identifiers}
        )
    return [document, *nodes, *edges]


# ---------------------------------------------------------------------------
# The cross-document layer
# ---------------------------------------------------------------------------

#: Identifier kinds that can name a governed document of this graph. The rest (`DI-`, `OD-`, a
#: task id) name something in another repository or in Seldon's own graph, and an edge to one of
#: them from here would be a pointer that lands nowhere.
_RESOLVABLE_KINDS = ("AD", "DN")


def document_index(graph) -> tuple[dict[str, str], dict[str, str]]:
    """Map the two things a header field can name to the Documents that are them.

    A governed design document names itself in its filename — `docs/design/AD-030_*.md` is AD-030 —
    which is the only claim the identifier half makes. The path half exists because a header field
    does not always use an identifier: the findings note's `Depends on:` names two RESULT files by
    repo-relative path, and resolving only identifiers dropped both edges silently.

    Args:
        graph: The loaded graph.

    Returns:
        `(by_identifier, by_path)` — e.g. `{"AD-030": "docs_design_ad_030_..."}` and
        `{"cc_tasks/x_RESULT.md": "cc_tasks_x_result"}`.
    """
    from squiddy import manifest as mf

    _s, _m, docs = mf.load_manifest(graph.manifest_path)
    by_identifier: dict[str, str] = {}
    by_path: dict[str, str] = {}
    # A DECLARED NAME CLAIMS FIRST (AD-030-R20). It is a statement of intent; the derivation from a
    # filename is a guess, and a guess must never take a name from a document that asked for it.
    for entry in sorted(docs, key=lambda e: str(e.get("source_url") or e["id"])):
        rel = entry.get("source_url") or ""
        if rel:
            by_path[rel] = entry["id"]
        name = _declared_name_of(graph, entry["id"])
        if name:
            by_identifier.setdefault(name, entry["id"])
    # ... then the filename derivation, in sorted path order so the tiebreak between two documents
    # sharing a leading identifier is the same one Seldon's importer applies.
    for entry in sorted(docs, key=lambda e: str(e.get("source_url") or e["id"])):
        rel = entry.get("source_url") or ""
        match = re.match(r"^((?:AD|DN)-\d+)", rel.rsplit("/", 1)[-1])
        if match:
            by_identifier.setdefault(match.group(1), entry["id"])
    return by_identifier, by_path


#: A cache that survives the emitter being re-executed. The kit loads this file by path for every
#: call, which builds a fresh module each time, so a module-level dict here would be a cache of
#: one. `document_index` runs once per document and a layer pass runs it once per document, so
#: without this the declared-name index would cost a hundred parsed-file reads a hundred times.
_CACHE_MODULE = "_governed_emit_process_cache"


def _process_cache(bucket: str) -> dict:
    """One named dict per process, whoever re-executes this module."""
    import sys
    import types

    module = sys.modules.get(_CACHE_MODULE)
    if module is None:
        module = types.ModuleType(_CACHE_MODULE)
        sys.modules[_CACHE_MODULE] = module
    if not hasattr(module, bucket):
        setattr(module, bucket, {})
    return getattr(module, bucket)


def _declared_name_of(graph, doc_id: str) -> str | None:
    """The `Name:` a document declares, or None. Cached; a missing parse is not an error here."""
    cache = _process_cache("declared_names")
    if doc_id not in cache:
        try:
            parsed = load_parsed(graph, doc_id)
        except SystemExit:
            cache[doc_id] = None
        else:
            cache[doc_id] = declared_name(parsed["plain_text"], graph.domain)
    return cache[doc_id]


#: A repo-relative markdown path as a header field writes one, backticked or bare.
_PATH_REF_RE = re.compile(r"`?([A-Za-z0-9_./-]+\.md)`?")


def path_references(text: str) -> list[str]:
    """Every repo-relative markdown path a header field names.

    Args:
        text: The header field's value.

    Returns:
        Paths in order of first appearance, deduplicated.
    """
    out: list[str] = []
    for match in _PATH_REF_RE.finditer(text or ""):
        path = match.group(1)
        if path not in out:
            out.append(path)
    return out


def _ruling_index(in_graph: set) -> dict[str, list[str]]:
    """Ruling node ids in the ledger, grouped by the slug of the identifier they carry.

    A Ruling's key is `<doc>!<slug of its identifier>` when it has one, so the ledger's own id set
    is the index and no extra context is needed. Grouping rather than mapping is deliberate: two
    documents can state a ruling under the same identifier, and the caller must abstain on that
    rather than pick one.

    Args:
        in_graph: Every node id the ledger holds.

    Returns:
        Slugged identifier to the node ids carrying it.
    """
    out: dict[str, list[str]] = {}
    for node_id in sorted(in_graph):
        _, sep, suffix = str(node_id).partition("!")
        if sep and suffix and not re.fullmatch(r"r\d{3}", suffix):
            out.setdefault(suffix, []).append(node_id)
    return out


def emit_layer(entry: dict, resolved: dict | None, graph, classes: dict, layer: str,
               context: dict) -> list:
    """Cross-document edges for one already-admitted document.

    Run after every Document is in the ledger, so an edge is emitted only when both ends exist.
    An identifier that resolves to no Document here is abstained from and reported, never emitted
    as a pointer into nothing (DI-046's logged abstention).

    Args:
        entry: The manifest entry.
        resolved: The acquisition record, or None.
        graph: The loaded graph.
        classes: Class name to generated Pydantic class.
        layer: The layer name; this graph declares one, `references`.
        context: The kit's ledger view, carrying `in_graph`.

    Returns:
        Edge instances.

    Raises:
        SystemExit: If an unknown layer is requested. Silently emitting nothing for a typo would
            report a layer as having run.
    """
    if layer != "references":
        raise SystemExit(f"FATAL: the governed graph declares one layer, `references`; got {layer!r}")

    domain = graph.domain
    doc_id = entry["id"]
    parsed = load_parsed(graph, doc_id)
    plain = parsed["plain_text"]
    ident_rules = compiled_rules(domain, "identifier_patterns")
    index, by_path = document_index(graph)
    in_graph = context.get("in_graph") or set()

    edges: list = []
    seen: set[tuple[str, str, str]] = set()
    abstained: dict[str, int] = {}

    def _admitted(target: str | None) -> str | None:
        """Keep a target only when it is another admitted Document of this graph."""
        return target if target and target != doc_id and target in in_graph else None

    def resolve(identifier: str) -> str | None:
        """The Document id an identifier names, when this graph holds one."""
        return _admitted(index.get(identifier))

    def resolve_path(path: str) -> str | None:
        """The Document id a repo-relative path names, when this graph holds one."""
        return _admitted(by_path.get(path))

    # ---- header fields: Extends, Depends on ------------------------------
    header_edge_rules = domain.get("header_edges") or []
    fields = header_fields(plain, [rule["field"] for rule in header_edge_rules])
    for rule in header_edge_rules:
        raw = fields.get(rule["field"])
        if not raw:
            continue
        # A header field names its targets by identifier OR by path, and a document is free to mix
        # the two in one field. Both are resolved; each target yields at most one edge.
        candidates = [
            (ref["identifier"], resolve(ref["identifier"]))
            for ref in identifier_references(raw, ident_rules)
        ] + [(path, resolve_path(path)) for path in path_references(raw)]
        for label, target in candidates:
            if target is None:
                abstained[label] = abstained.get(label, 0) + 1
                continue
            key = (rule["edge"], doc_id, target)
            if key in seen:
                continue
            seen.add(key)
            edges.append(classes[rule["edge"]](
                subject=doc_id, object=target, raw_field=raw[:300], method="header_field",
            ))

    # ---- ruling-level supersession (AD-030-R21) --------------------------
    # A ruling that replaces another SAYS SO, as the last sentence of its own text. The target is
    # another Ruling node, so this is a cross-document edge and belongs here rather than in `emit`:
    # at admission time the ruling it supersedes may not be in the ledger yet.
    pattern = graph.domain.get("supersession_pattern")
    supersedes_re = re.compile(pattern) if pattern else None
    ruling_ids = _ruling_index(in_graph)
    for ruling in ruling_blocks(doc_id, parsed["blocks"], domain):
        for identifier in supersedes_references(ruling["block"]["text"], supersedes_re):
            targets = [t for t in ruling_ids.get(slug(identifier), []) if t != ruling["id"]]
            if len(targets) != 1:
                # Nothing, or more than one document stating a ruling by that identifier. Either
                # way the declaration names something this graph cannot resolve to ONE node, and
                # a guess would be a supersession nobody declared.
                abstained[identifier] = abstained.get(identifier, 0) + 1
                continue
            key = ("Supersedes", ruling["id"], targets[0])
            if key in seen:
                continue
            seen.add(key)
            edges.append(classes["Supersedes"](
                subject=ruling["id"], object=targets[0],
                reason=f"declared in {ruling['identifier'] or ruling['id']}: "
                       f"`Supersedes {identifier}.`",
            ))

    # ---- mentions: every identifier reference anywhere in the document ----
    for ref in identifier_references(plain, ident_rules):
        if ref["kind"] not in _RESOLVABLE_KINDS:
            abstained[ref["identifier"]] = abstained.get(ref["identifier"], 0) + ref["occurrences"]
            continue
        target = resolve(ref["identifier"])
        if target is None:
            abstained[ref["identifier"]] = abstained.get(ref["identifier"], 0) + ref["occurrences"]
            continue
        key = ("Mentions", doc_id, target)
        if key in seen:
            continue
        seen.add(key)
        edges.append(classes["Mentions"](
            subject=doc_id, object=target, identifier=ref["identifier"],
            identifier_kind=ref["kind"], occurrences=ref["occurrences"],
            method="lexical_identifier_reference",
        ))

    if abstained:
        shown = ", ".join(f"{k} x{v}" for k, v in sorted(abstained.items())[:12])
        print(f"  {doc_id}: abstained on {len(abstained)} identifier(s) that name nothing in this "
              f"graph ({shown}{' ...' if len(abstained) > 12 else ''}); they are carried on the "
              f"nodes as `identifiers` and resolve in Seldon's graph")
    return edges


def _section_body_end(blocks: list[dict], heading: dict, doc_len: int) -> int:
    """Where a section's content ends: at the next heading of the same or shallower level.

    Args:
        blocks: All blocks in reading order.
        heading: The heading block opening the section.
        doc_len: Length of the document, for the last section.

    Returns:
        The end offset of the section's verbatim span.
    """
    level = heading["level"] or 1
    for block in blocks[heading["idx"] + 1:]:
        if block["kind"] == "heading" and (block["level"] or 1) <= level:
            return block["char_span"][0]
    return doc_len


def _section_index(blocks: list[dict], sections: list[dict]) -> dict[int, str]:
    """Map every block's index to the id of the section it sits in.

    Args:
        blocks: All blocks in reading order.
        sections: The sections emitted, in order.

    Returns:
        Block index to section id. Blocks before the first heading map to nothing.
    """
    out: dict[int, str] = {}
    current: str | None = None
    by_block = {section["block"]["idx"]: section["id"] for section in sections}
    for block in blocks:
        if block["idx"] in by_block:
            current = by_block[block["idx"]]
        if current:
            out[block["idx"]] = current
    return out
