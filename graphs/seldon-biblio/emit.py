"""A graph's emitter: one manifest entry plus its resolver record, in; typed instances of the
generated classes, out. This is the graph's half of the write path (Koza's layer in the Monarch
stack, S-003 section 3 bucket C): deterministic, zero model calls, and the kit projects what it
emits into every backend.

The kit calls `emit(entry, resolved, graph, classes)` and `manifest_projection(entry, graph)`.

SEEDED, NOT GENERATED. `squiddy init` copies this file into a new graph once and never rewrites
it, and `squiddy init --check` does not report drift against it, because editing it is the point:
the emitter is where a graph says what its own kinds mean. It is seeded rather than imported
because `graphs/biblio/emit.py` and `graphs/library/emit.py` were byte-identical (K-001 Part A),
which means the copy never needed a per-graph emitter and a new graph should not start by writing
one. What arrives here handles the three kinds every graph in the kit has had so far (work,
standard, software) and the local-document kind S-008 added; a graph with a kind of its own adds
it here.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from squiddy.acquire import normalize_doi

_SLUG_KEEP = re.compile(r"[^a-z0-9]+")


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return _SLUG_KEEP.sub("_", s.lower()).strip("_")


def person_id(name: str, orcid: str | None) -> str:
    """Readable, source-scoped, minted once (OD-4 §3.1). ORCID is a property, not the key."""
    return f"person:{slug(name)}"


def split_citations(cited_in: str) -> list[str]:
    """Split a `cited_in` string on the semicolons that separate citations, never on one inside
    parentheses. S-005 Part 0: eight spurious Decision nodes (`cited:status`, `cited:undo_documented`)
    were minted from the notes in "(...; ...)" before this rule existed."""
    out, buf, depth = [], [], 0
    for ch in cited_in or "":
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == ";" and depth == 0:
            out.append("".join(buf)); buf = []
        else:
            buf.append(ch)
    out.append("".join(buf))
    return [s.strip() for s in out if s.strip()]


def decision_ids(cited_in: str, domain: dict) -> list[dict]:
    """Parse a `cited_in` string into the decisions it names, by the graph's declared patterns."""
    out, seen = [], set()
    for piece in split_citations(cited_in):
        piece = piece.strip()
        if not piece:
            continue
        matched = False
        for rule in domain.get("decision_id_patterns") or []:
            for m in re.finditer(rule["pattern"], piece):
                did = rule["id_format"].format(m.group(0), *m.groups()) if rule.get("id_format") else m.group(0)
                matched = True
                if did in seen:
                    continue
                seen.add(did)
                out.append({"id": did, "kind": rule["kind"], "source_document": rule["source_document"],
                            "title": piece})
        if not matched:
            did = f"cited:{slug(piece)}"
            if did not in seen:
                seen.add(did)
                out.append({"id": did, "kind": "TASK", "source_document": None, "title": piece})
    return out


def internal_headings(entry: dict) -> list[str]:
    """Every heading of an internal document, in reading order, read from the file the entry names.

    Returns an empty list when the file is gone or is not UTF-8: the assessment stage is what
    decides an entry whose file has moved, and an emitter that raised here would turn a decision
    into a crash.
    """
    from squiddy.repodocs import headings
    path = Path(entry.get("local_path") or "")
    if not path.is_absolute() or not path.is_file():
        return []
    try:
        return headings(path.read_bytes().decode("utf-8"))
    except UnicodeDecodeError:
        return []


def manifest_projection(entry: dict, graph) -> dict:
    """The properties of the entry's primary node that come from the manifest verbatim. The
    manifest-to-ledger gate compares exactly these (squiddy.gates.manifest_leg)."""
    kind = entry.get("kind")
    common = {"id": entry["id"], "title": entry.get("title"), "source_url": entry.get("source_url"),
              "disposition": entry.get("disposition")}
    if kind == "work":
        common.update({"doi": (entry.get("doi") or None), "openalex_id": entry.get("openalex_id"),
                       "year": entry.get("year"), "publication_date": entry.get("publication_date"),
                       "venue": entry.get("venue"), "work_type": entry.get("work_type"),
                       "oa_status": entry.get("oa_status"), "oa_url": entry.get("oa_url"),
                       "licence": entry.get("licence"), "abstract": entry.get("abstract"),
                       "local_path": entry.get("local_path"), "sha256": entry.get("sha256")})
    elif kind == "local_document":
        # S-008 Part A. A document this repository wrote, admitted as a Work whose `work_type` says
        # so. What the node carries is the entry: the path, the hashes, the sort, the date and the
        # repository it came from. The prose stays in the file (docs/S-008_rules.md §2).
        common.update({"work_type": "internal_document", "doc_kind": entry.get("doc_kind"),
                       "repo": entry.get("repo"), "commit": entry.get("commit"),
                       "file_type": entry.get("file_type"), "first_heading": entry.get("first_heading"),
                       "doc_date": entry.get("doc_date"), "local_path": entry.get("local_path"),
                       "sha256": entry.get("sha256")})
    elif kind == "standard":
        common.update({"version": entry.get("version"), "version_date": entry.get("version_date"),
                       "verification_status": entry.get("verification_status")})
    elif kind == "software":
        common.update({"repository": entry.get("source_url"), "licence": entry.get("licence"),
                       "version": entry.get("version"), "version_date": entry.get("version_date"),
                       "last_push": entry.get("last_push"),
                       "verification_status": entry.get("verification_status")})
    return {k: v for k, v in common.items() if v is not None}


def emit(entry: dict, resolved: dict | None, graph, classes: dict) -> list:
    """Instances for one admitted entry. `classes` maps class name to the generated Pydantic class."""
    kind = entry.get("kind")
    prim = graph.engine["write"]["primary_class_by_kind"].get(kind)
    if prim is None:
        raise SystemExit(f"FATAL: no primary class for manifest kind {kind!r} "
                         f"(engine.write.primary_class_by_kind)")
    Cls = classes[prim]
    props = manifest_projection(entry, graph)
    props["cited_in"] = split_citations(str(entry.get("cited_in") or ""))
    props["method"] = "manifest"
    out = []
    oa = ((resolved or {}).get("resolved") or {}).get("openalex") or {}
    cr = ((resolved or {}).get("resolved") or {}).get("crossref") or {}
    if kind == "work":
        props["arxiv_id"] = _arxiv_id(entry, oa)
        authorships = [a for a in (oa.get("authorships") or []) if a.get("display_name")]
        if not authorships:
            authorships = [{"position": i, "display_name": n, "orcid": None,
                            "openalex_author_id": None, "institutions": []}
                           for i, n in enumerate(entry.get("authors") or [])]
        props["authors_raw"] = [a.get("raw_author_name") or a["display_name"] for a in authorships]
        out.append(Cls(**props))
        seen_org = set()
        for a in authorships:
            pid = person_id(a["display_name"], a.get("orcid"))
            out.append(classes["Person"](id=pid, name=a["display_name"], name_normalized=slug(a["display_name"]),
                                         orcid=_orcid(a.get("orcid")),
                                         openalex_author_id=a.get("openalex_author_id"),
                                         method="openalex" if oa else "manifest"))
            out.append(classes["AuthoredBy"](subject=entry["id"], object=pid,
                                             author_position=int(a.get("position", 0)),
                                             raw_name=a.get("raw_author_name") or a["display_name"],
                                             method="openalex" if oa else "manifest"))
            for inst in a.get("institutions") or []:
                if not inst.get("display_name"):
                    continue
                oid = f"org:{slug(inst['display_name'])}"
                if oid not in seen_org:
                    seen_org.add(oid)
                    out.append(classes["Organization"](id=oid, name=inst["display_name"], ror=inst.get("ror"),
                                                       openalex_institution_id=inst.get("openalex_institution_id"),
                                                       country_code=inst.get("country_code"),
                                                       method="openalex"))
                out.append(classes["AffiliatedWith"](subject=pid, object=oid, as_of_work=entry["id"],
                                                     method="openalex"))
    elif kind == "local_document":
        # The headings are read from the file at emit time rather than carried in the manifest: a
        # manifest entry is an inventory row and a table of contents is not one. The file's hash is
        # in the entry, so a heading list that no longer matches is a re-ingest, not a silent drift.
        props["headings"] = internal_headings(entry)
        out.append(Cls(**props))
    else:
        out.append(Cls(**props))
    # THE DECISION HALF IS CONDITIONAL ON THE GRAPH DECLARING THOSE CLASSES (K-001 defect).
    # This file is what `squiddy init` seeds every new graph with, and a graph's spec names the
    # classes it wants. A graph that does not declare `Decision` -- graphs/library holds its
    # citations as `CitationEvent`, and a graph whose only kind is a local document has no use for
    # either -- got a `KeyError: 'Decision'` from here the moment one of its entries carried a
    # `cited_in` value, two frames below anything that named the spec. The seed must not assume a
    # class the spec may not declare. `cited_in` is already a property of the primary node
    # (`props` above), so nothing is lost when the edge is not emitted: the citation is still in
    # the graph, as a field rather than as an edge, and adding the classes to the spec turns it
    # into edges on the next run.
    if {"Decision", "SupportsDecision"} <= set(classes):
        for d in decision_ids(str(entry.get("cited_in") or ""), graph.domain):
            out.append(classes["Decision"](id=d["id"], title=d["title"], decision_kind=d["kind"],
                                           source_document=d["source_document"], method="manifest"))
            out.append(classes["SupportsDecision"](subject=entry["id"], object=d["id"],
                                                   cited_in_text=d["title"], method="manifest"))
    return out


def _orcid(o: str | None) -> str | None:
    if not o:
        return None
    return re.sub(r"^https?://orcid\.org/", "", o)


def _arxiv_id(entry: dict, oa: dict) -> str | None:
    doi = str(entry.get("doi") or "")
    m = re.match(r"10\.48550/arxiv\.(.+)$", doi, re.I)
    if m:
        return m.group(1)
    for k, v in (oa.get("ids") or {}).items():
        if k == "arxiv" and v:
            return str(v).rsplit("/", 1)[-1]
    return None


# --------------------------------------------------------------------------------------
# Edge layers for an ALREADY ADMITTED entry (S-006 Part 1)
# --------------------------------------------------------------------------------------

def emit_layer(entry: dict, resolved: dict | None, graph, classes: dict, layer: str, context: dict) -> list:
    """`cites`: Cites and ExpressionOf edges from public, deterministic sources only. A reference
    whose DOI names a work in the manifest AND in the graph becomes a Cites edge to that Work; any
    other DOI becomes an ExternalReference keyed by DOI (fss-policy-kg practice, DI-046), so a
    pointer outside the graph is a node with a key and never a string. A reference with no DOI
    cannot be keyed; it is COUNTED on the Work (`references_total` against `references_keyed`),
    which is the logged abstention. ExpressionOf comes from Crossref `relation` (is-preprint-of,
    has-preprint, is-version-of) and DataCite related identifiers (IsPreprintOf, HasPreprint,
    IsVersionOf). No expansion: nothing here mints a Work.

    `context`: {"doi_index": {normalized doi: manifest id}, "in_graph": {ids with a node}}."""
    if layer != "cites":
        raise SystemExit(f"FATAL: unknown layer {layer!r}; this emitter knows: cites")
    if entry.get("kind") != "work":
        return []
    res = (resolved or {}).get("resolved") or {}
    cr, dc = res.get("crossref") or {}, res.get("datacite") or {}
    by_doi, in_graph = context["doi_index"], context["in_graph"]
    out, seen_ext = [], set()

    def target_for(doi: str, method: str) -> str:
        tid = by_doi.get(doi)
        if tid and tid in in_graph and tid != entry["id"]:
            return tid
        xid = f"doi:{doi}"
        if xid not in seen_ext:
            seen_ext.add(xid)
            out.append(classes["ExternalReference"](id=xid, ref_kind="doi", doi=doi, method=method))
        return xid

    refs = cr.get("references") or []
    keyed, seen_targets = 0, set()
    for ref in refs:
        doi = normalize_doi(ref.get("doi"))
        if not doi:
            continue
        keyed += 1
        t = target_for(doi, "crossref")
        if t in seen_targets:
            continue
        seen_targets.add(t)
        out.append(classes["Cites"](subject=entry["id"], object=t, raw_reference=ref.get("unstructured") or None,
                                    cito_intent="citesForInformation", method="crossref"))
    for rtype, items in (cr.get("relation") or {}).items():
        for it in items or []:
            if str(it.get("id-type", "")).lower() != "doi":
                continue
            other = normalize_doi(it.get("id"))
            if rtype == "is-preprint-of":
                out.append(classes["ExpressionOf"](subject=entry["id"], object=target_for(other, "crossref"),
                                                   relation="is_preprint_of", method="crossref"))
            elif rtype == "has-preprint":
                out.append(classes["ExpressionOf"](subject=target_for(other, "crossref"), object=entry["id"],
                                                   relation="is_preprint_of", method="crossref"))
            elif rtype == "is-version-of":
                out.append(classes["ExpressionOf"](subject=entry["id"], object=target_for(other, "crossref"),
                                                   relation="is_version_of", method="crossref"))
    for ri in dc.get("related_identifiers") or []:
        if str(ri.get("relatedIdentifierType", "")).lower() != "doi":
            continue
        other, rt = normalize_doi(ri.get("relatedIdentifier")), ri.get("relationType")
        if rt == "IsPreprintOf":
            out.append(classes["ExpressionOf"](subject=entry["id"], object=target_for(other, "datacite"),
                                               relation="is_preprint_of", method="datacite"))
        elif rt == "HasPreprint":
            out.append(classes["ExpressionOf"](subject=target_for(other, "datacite"), object=entry["id"],
                                               relation="is_preprint_of", method="datacite"))
        elif rt == "IsVersionOf":
            out.append(classes["ExpressionOf"](subject=entry["id"], object=target_for(other, "datacite"),
                                               relation="is_version_of", method="datacite"))
    if refs or out:
        props = manifest_projection(entry, graph)
        props["cited_in"] = split_citations(str(entry.get("cited_in") or ""))
        props["method"] = "manifest"
        props["references_total"], props["references_keyed"] = len(refs), keyed
        out.insert(0, classes[graph.engine["write"]["primary_class_by_kind"]["work"]](**props))
    return out


# --------------------------------------------------------------------------------------
# The extraction stage's half of the write path (S-007): grounded proposals to instances
# --------------------------------------------------------------------------------------

def claim_id(doc_id: str, text: str) -> str:
    """`claim:<work>:<sha256 of the located text, first 12>`: the same sentence located twice is
    one node, which is what makes a re-extraction an edit rather than a duplicate."""
    import hashlib
    return f"claim:{doc_id}:{hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]}"


def emit_extraction(entry: dict, proposals: list[dict], graph, classes: dict) -> list:
    """Claim and Asserts instances from the extract stage's evidence file. ONLY `grounded`
    proposals are emitted: a span the harness could not locate is a failed extraction, never a
    stored claim (R-14). Every instance carries the extractor stamp with the RESOLVED model id
    (DI-023), the run id, the prompt hash, the located span, and `status: proposed` (OD-5: shown
    before commit; acceptance is a later ruling)."""
    xcfg = graph.domain.get("extract") or {}
    Claim = classes[xcfg.get("output_class", "Claim")]
    Asserts = classes[xcfg.get("edge_class", "Asserts")]
    out, seen = [], set()
    for p in proposals:
        if p.get("status") != "grounded":
            continue
        text = p["text"]
        cid = claim_id(entry["id"], text)
        if cid in seen:
            continue
        seen.add(cid)
        x = p.get("extractor") or {}
        stamp = {"prov_extractor": f"{x.get('provider')}:{x.get('model_role') or x.get('alias')}",
                 "prov_extractor_version": x.get("model"),
                 "prov_prompt_sha256": x.get("prompt_sha256"),
                 "prov_run_id": p.get("run_id"),
                 "method": "extraction", "status": "proposed"}
        seg = p.get("segment") or {}
        out.append(Claim(id=cid, text=text, claim_kind=p["claim"]["claim_kind"],
                         grounding_span=dict(p["span"]), segment_idx=seg.get("idx"),
                         section=seg.get("section"), section_path=seg.get("section_path"), **stamp))
        out.append(Asserts(subject=entry["id"], object=cid, grounding_span=dict(p["span"]), **stamp))
    return out


def emit_rulings(ratings: list[dict], graph, classes: dict) -> list:
    """Ruling and RulesOn instances from the pilot gate's rater and adjudicator records. The
    verdict is `yes` iff both rubric questions were answered yes. `final` on the edge marks the
    ruling that stands: the adjudicator's when there is one, else the rater's."""
    import hashlib
    xcfg = graph.domain.get("extract") or {}
    Ruling = classes[xcfg.get("ruling_class", "Ruling")]
    RulesOn = classes[xcfg.get("ruling_edge_class", "RulesOn")]
    out = []
    for r in ratings:
        both = bool(r.get("claim_made")) and bool(r.get("span_is_evidence"))
        key = hashlib.sha256(f"{r['claim_id']}|{r['role']}|{r.get('run_id')}".encode("utf-8")).hexdigest()[:8]
        rid = f"ruling:{r['role']}:{r['claim_id'].split(':', 1)[1]}:{key}"
        stamp = {"prov_extractor": f"claude_cli_max_oauth:{r.get('model_role') or r.get('alias')}",
                 "prov_extractor_version": r.get("model"), "prov_run_id": r.get("run_id"),
                 "method": "model_rating", "status": "accepted"}
        out.append(Ruling(id=rid, role=r["role"], claim_made=bool(r.get("claim_made")),
                          span_is_evidence=bool(r.get("span_is_evidence")), verdict="yes" if both else "no",
                          rationale=r.get("rationale"), rubric_version=r["rubric_version"], **stamp))
        out.append(RulesOn(subject=rid, object=r["claim_id"], final=bool(r.get("final")), **stamp))
    return out


# --------------------------------------------------------------------------------------
# The decision registers (S-008 Part B): rows and rulings as nodes, with their sources
# --------------------------------------------------------------------------------------

def emit_decisions(records: list[dict], graph, classes: dict, context: dict) -> list:
    """Decision nodes and their edges, from the registers `squiddy.decisions` read.

    Three edge kinds, each only where its target exists (an edge to a node nobody minted is the
    dangling pointer the gate exists to catch):

    - `DerivedFrom` to the manifest entry a row names as its source. A source outside the cataloged
      frame is a recorded miss and no edge.
    - `Cites` to the decisions a ruling's text names, which is how DN-001's R-01 reaches DI-004.
    - `SupportsDecision` from the works a ruling names to the ruling, in the direction the graph
      already uses for `cited_in` (the task's "supports edges to the Works it names"; the existing
      edge class is the one the served verbs already walk).

    A Decision the `cited_in` layer already minted is NOT re-minted: the same id is asserted again
    with the register's fields, which the ledger merges (last write wins) and the write path admits
    as an edit rather than a duplicate.
    """
    from squiddy.decisions import cited_decisions, named_works
    Decision, Cites = classes["Decision"], classes["Cites"]
    DerivedFrom, Supports = classes["DerivedFrom"], classes["SupportsDecision"]
    patterns = context["cited_id_patterns"]
    work_keys, in_graph = context["work_keys"], context["in_graph"]
    known = set(context["existing_decisions"]) | {r["id"] for r in records}
    out, misses = [], []
    for r in records:
        out.append(Decision(id=r["id"], title=r["title"] or r["id"], decision_kind=r["kind"],
                            source_document=r["source_document"], decision_register=r["register"],
                            disposition=r["disposition"], statement=r["statement"] or None,
                            method="register"))
        for s in r["sources"]:
            if not s.get("entry_id") or s["entry_id"] not in in_graph:
                continue                       # recorded as a miss by the reader; never an edge
            out.append(DerivedFrom(subject=r["id"], object=s["entry_id"], source_text=s.get("text"),
                                   locator=s.get("locator"), located_heading=s.get("located_heading"),
                                   locator_status=s["status"], method="register"))
        for did in cited_decisions(r, patterns, r["id"]):
            if did in known:
                out.append(Cites(subject=r["id"], object=did, cito_intent="citesAsAuthority",
                                 method="register"))
            else:
                misses.append({"decision": r["id"], "cites": did, "why": "no node for the cited id"})
        for wid in named_works(r, work_keys):
            if wid in in_graph:
                out.append(Supports(subject=wid, object=r["id"],
                                    cited_in_text=f"named in {r['register']} {r['id']}", method="register"))
    context["cite_misses"] = misses
    return out


# --------------------------------------------------------------------------------------
# The imported vocabularies (S-008 Part D): terms as Concepts, alt labels as Atoms
# --------------------------------------------------------------------------------------

def emit_vocabulary(spec: dict, terms: list[dict], entry: dict, graph, classes: dict,
                    *, new_entry: bool = True) -> list:
    """One vocabulary: its Standard node, a Concept per term, an Atom per alternate label.

    The Standard node is the manifest entry's projection plus what the import measured, so the
    drift gate compares the hash of the file that was read. Every Concept is keyed by the IRI the
    standard published (R-03: referenced, never copied), and carries `DefinedIn` to the Standard so
    a consumer can ask which specification a term came from without parsing its IRI.
    """
    Standard, Concept = classes["Standard"], classes["Concept"]
    Atom, SurfaceOf, DefinedIn = classes["Atom"], classes["SurfaceOf"], classes["DefinedIn"]
    out = []
    props = manifest_projection(entry, graph)
    props["cited_in"] = split_citations(str(entry.get("cited_in") or ""))
    props["method"] = "manifest"
    out.append(Standard(**props))
    # THE DECISION STUBS BELONG TO THE ADMISSION THAT MINTED THEM. Re-emitting them for a standard
    # this graph already holds rewrote `Decision.title` with whichever entry cited it last, and two
    # entries citing OD-4 in different words made the node oscillate: two events appended on every
    # run, forever. A vocabulary import imports a vocabulary.
    # THE EDGE BELONGS TO THE STANDARD, so it is emitted on every import (SQ-090R). The write is a
    # re-ingest, which retires what a run does not emit: skipping the edge with the stub retracted
    # the citation a first import wrote, on every re-import of a held vocabulary (hazbrief HB-20),
    # and retracted the stub too where this entry was the only one asserting it. So a re-import
    # names the stub BY ITS ID ALONE: no title to rewrite, so the re-ingest's payload comparison
    # drops it as unchanged (no event), and it is in the slice, so it is not retired. A decision
    # the entry no longer cites is named by neither, and leaves with its edge.
    for d in decision_ids(str(entry.get("cited_in") or ""), graph.domain):
        if new_entry:
            out.append(classes["Decision"](id=d["id"], title=d["title"], decision_kind=d["kind"],
                                           source_document=d["source_document"], method="manifest"))
        else:
            out.append(classes["Decision"](id=d["id"]))
        out.append(classes["SupportsDecision"](subject=entry["id"], object=d["id"],
                                               cited_in_text=d["title"], method="manifest"))
    # AN ATOM IS A SURFACE FORM FOR A CASE-INSENSITIVE MATCHER, so two labels that differ only in
    # case are ONE atom. Collecting them first and keeping the lexicographically smallest variant
    # makes the id's text deterministic: emitting them inline let `Datasamling` and `datasamling`
    # take turns owning `atom:dcat:datasamling`, and each run appended the other one as an edit
    # forever (found by running the import twice and watching four events appear every time).

    # SQ-005 (DN-040 R-173): a hierarchical vocabulary's positions (MeSH's tree numbers) ride on the Concept. A
    # graph whose Concept declares no `tree_numbers` slot cannot hold them, and is told so rather than losing them.
    def _tree(t: dict) -> dict:
        tn = t.get("tree_numbers")
        if not tn:
            return {}
        if "tree_numbers" not in (getattr(Concept, "model_fields", None) or {}):
            raise SystemExit(f"FATAL: the vocabulary {t['vocabulary']!r} carries tree numbers and this graph's "
                             f"Concept declares no `tree_numbers` slot; add `tree_numbers: {{multivalued: true}}` "
                             f"to Concept in the spec and re-render (SQ-005)")
        return {"tree_numbers": list(tn)}

    atoms: dict[str, str] = {}
    for t in terms:
        out.append(Concept(id=t["iri"], pref_label=t["pref_label"], definition=t.get("definition"),
                           definition_source=t.get("definition_source"), label_source=t.get("label_source"),
                           vocabulary=t["vocabulary"], tier=t["vocabulary"], term_type=t.get("term_type"),
                           group=t.get("group"), **_tree(t), method="vocabulary_import"))
        out.append(DefinedIn(subject=t["iri"], object=entry["id"], method="vocabulary_import"))
        for alt in t.get("alt_labels") or []:
            aid = atom_id(t["vocabulary"], alt)
            atoms[aid] = min(atoms.get(aid, alt), alt)
            out.append(SurfaceOf(subject=aid, object=t["iri"], method="vocabulary_import"))
    for aid, text in sorted(atoms.items()):
        out.append(Atom(id=aid, text=text, source=terms[0]["vocabulary"], atom_kind="alt_label",
                        method="vocabulary_import"))
    if spec.get("derived_from_work"):
        # A hand-entered list read out of a paper says so with an edge, not with a comment.
        for t in terms:
            out.append(classes["DerivedFrom"](subject=t["iri"], object=spec["derived_from_work"],
                                              source_text=f"{spec['title']} ({spec['prefix']})",
                                              locator_status="path_only", method="vocabulary_import"))
    return out


def atom_id(source: str, text: str) -> str:
    """`atom:<source>:<slug>`: the same string from the same source is one atom, which is what makes
    a second import of a vocabulary an edit rather than a duplicate."""
    import hashlib
    s = slug(text)
    if not s:                                    # a label that slugs to nothing is still an atom
        s = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    return f"atom:{source}:{s[:80]}"


def emit_mappings(rows: list[dict], graph, classes: dict, context: dict) -> list:
    """An Atom for each kit term, a Mapping node per SSSOM row, and the edges to both ends.

    A coinage has a subject end and no object end, which is what keeps it in the graph as a
    recorded search rather than as an orphan nobody can find (docs/S-008_rules.md §6).
    """
    Atom, Mapping = classes["Atom"], classes["Mapping"]
    MapsTo, MapsFrom = classes["MapsTo"], classes["MapsFrom"]
    out = []
    for r in rows:
        aid = atom_id("squiddy", r["subject_label"])
        mid = f"mapping:{slug(r['subject_label'])}:{slug(r['predicate_id'])}"
        out.append(Atom(id=aid, text=r["subject_label"], source="squiddy", atom_kind="kit_term",
                        method="term_map"))
        out.append(Mapping(id=mid, subject_id=aid, subject_label=r["subject_label"],
                           predicate_id=r["predicate_id"], object_id=r.get("object_id"),
                           object_label=r.get("object_label"),
                           mapping_justification=r["mapping_justification"],
                           vocabularies_searched=list(r["vocabularies_searched"]),
                           mapping_tool=context["mapping_tool"], mapping_date=context["mapping_date"],
                           method="term_map"))
        out.append(MapsFrom(subject=mid, object=aid, method="term_map"))
        if r.get("object_id"):
            out.append(MapsTo(subject=mid, object=r["object_id"], method="term_map"))
    return out


def emit_mentions(rows: list[dict], graph, classes: dict) -> list:
    """(Concept)-[:MENTIONS]->(Claim | Decision | Work) with the span it was located at.

    A stopword label is FLAGGED and never omitted (docs/S-008_rules.md §4): the flag governs
    traversal, and a count that dropped its most common term would be a different measurement.
    """
    Mentions = classes["Mentions"]
    return [Mentions(subject=r["concept"], object=r["target"], span_start=r["span_start"],
                     span_end=r["span_end"], matched_label=r["matched_label"],
                     scanned_field=r["field"], normalization=r["normalization"],
                     stopword=bool(r.get("stopword")), stopword_reason=r.get("stopword_reason"),
                     method="mention_layer")
            for r in rows]


def emit_gate_ruling(res: dict, graph, classes: dict) -> list:
    """The density gate's verdict as a Ruling on a Release (S-008 Part F).

    Every line is written out with its rule and its measured value, so the record says what was
    checked and not only whether it passed. A fail is recorded exactly as a pass is.
    """
    Ruling, Release, RulesOn = classes["Ruling"], classes["Release"], classes["RulesOn"]
    version = res["release"]
    rid = f"ruling:gate:density:{version}"
    lines = [f"{r['line']} | {r['rule']} | measured {r['measured']} | {'pass' if r['pass'] else 'FAIL'}"
             for r in res["lines"]]
    return [
        Release(id=f"release:{version}", title=version, released_on=res.get("released_on"),
                gate_verdict=res["verdict"], method="release"),
        Ruling(id=rid, role="gate", verdict="yes" if res["verdict"] == "pass" else "no",
               gate_name=res["gate"], gate_lines=lines, pre_registered_in=res["pre_registered_in"],
               rationale=f"{res['measured']['nodes']} nodes, {res['measured']['edges']} edges, "
                         f"{res['measured']['relationship_types']} relationship types; thresholds "
                         f"derived from {res.get('derived_from')}",
               method="gate", status="accepted"),
        RulesOn(subject=rid, object=f"release:{version}", final=True, method="gate"),
    ]
