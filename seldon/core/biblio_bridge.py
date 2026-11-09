"""The governed graph's citations, bridged to the bibliographic graph they name (AD-036-R22, SEL-036 Part E).

A governed `Citation` (AD-030-R6) is a string cut from a note: `docs_design_ad_029_task_precedence@kelley_walker_1959`.
The bibliographic graph (`graphs/seldon-biblio`, a squiddy graph) holds the WORK that string names, resolved to its
identifier with its metadata, licence and text. This module writes the link between them, in Seldon's graph, as a
pointer and never a copy: one `ExternalReference` artifact per entry (`<graph>:<entry id>`, with the entry's
identifier and title at bridge time), and one `resolves_to` link from each Citation to each entry its text names.

**Prior art.** squiddy biblio's `ExternalReference` class ("the pointer a citation makes outside the graph", DI-046)
and squiddy OD-4 section 3.3 (bridges between graphs are identifiers and mappings, no content). The map from Citation
to entry is the one the resolver used (`graphs/seldon-biblio/intake/seeds.yaml`, `governed:`), made by reading each
Citation's text; nothing here infers a pair.

**Idempotent.** An ExternalReference is found by its name before one is made; a link already present is not made
again. Re-running after the seed map grows adds only what is new. Every write goes through the event store
(`seldon.core.artifacts`), so the bridge replays with everything else.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

#: The relationship and the artifact type this module writes (seldon/domain/research.yaml, AD-036-R22).
REL = "resolves_to"
EXTERNAL = "ExternalReference"


@dataclass
class BridgeReport:
    citations_mapped: int = 0
    citations_missing: list = field(default_factory=list)     # governed keys the graph does not hold
    entries_missing: list = field(default_factory=list)       # entry ids the catalog does not hold
    references_created: int = 0
    references_existing: int = 0
    links_created: int = 0
    links_existing: int = 0
    naming_no_work: list = field(default_factory=list)        # Citations whose text names no work

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def identifier_of(entry: dict) -> str | None:
    """The entry's persistent identifier, in the order a reader can follow it: DOI, arXiv, OpenAlex, a standard's
    number, a repository, an ISBN."""
    if entry.get("doi"):
        return f"doi:{entry['doi']}"
    if entry.get("arxiv_id"):
        return f"arxiv:{entry['arxiv_id']}"
    if entry.get("openalex_id"):
        return f"openalex:{entry['openalex_id']}"
    if entry.get("standard_number"):
        return f"standard:{entry['standard_number']}"
    if entry.get("repository"):
        return f"repo:{str(entry['repository']).removeprefix('https://github.com/')}"
    if entry.get("isbn"):
        isbn = entry["isbn"][0] if isinstance(entry["isbn"], list) else entry["isbn"]
        return f"isbn:{isbn}"
    return None


def _citation_ids(session, keys: list[str]) -> dict:
    rows = session.run("MATCH (c:Citation) WHERE c.name IN $keys RETURN c.name AS name, c.artifact_id AS id",
                       keys=keys)
    return {r["name"]: r["id"] for r in rows}


def _reference_id(session, name: str) -> str | None:
    r = session.run("MATCH (e:ExternalReference {name: $name}) RETURN e.artifact_id AS id", name=name).single()
    return r["id"] if r else None


def _linked(session, from_id: str, to_id: str) -> bool:
    q = ("MATCH (a {artifact_id: $f})-[r:RESOLVES_TO]->(b {artifact_id: $t}) RETURN count(r) AS n")
    return session.run(q, f=from_id, t=to_id).single()["n"] > 0


def bridge(project_dir: Path, driver, database: str, domain_config, governed: dict, entries: dict,
           graph_name: str, actor: str = "cc", authority: str = "accepted", session_id: str | None = None,
           dry_run: bool = False) -> BridgeReport:
    """Write every `resolves_to` the seed map names.

    Args:
        governed: `{citation name: {"seeds": [entry id, ...], ...}}` (seeds.yaml `governed:`).
        entries: `{entry id: catalog entry}` (the graph's candidates file).
        graph_name: the bibliographic graph's directory name (`seldon-biblio`).
        dry_run: count what would be written, write nothing.
    """
    from seldon.core.artifacts import create_artifact, create_link

    rep = BridgeReport()
    planned: set = set()                            # dry run: the pointers this run would make, so each counts once
    with driver.session(database=database) as s:
        cids = _citation_ids(s, list(governed))
    for key, g in governed.items():
        seeds = list(g.get("seeds") or [])
        if not seeds:
            rep.naming_no_work.append(key)
            continue
        cid = cids.get(key)
        if cid is None:
            rep.citations_missing.append(key)
            continue
        rep.citations_mapped += 1
        for eid in seeds:
            entry = entries.get(eid)
            if entry is None:
                rep.entries_missing.append(eid)
                continue
            name = f"{graph_name}:{eid}"
            if dry_run and name in planned:
                rep.references_existing += 1        # this run would already have made it
                rep.links_created += 1
                continue
            with driver.session(database=database) as s:
                rid = _reference_id(s, name)
            if rid is None:
                rep.references_created += 1
                if dry_run:
                    planned.add(name)
                    rep.links_created += 1          # a new pointer has no link yet, so its link would be written too
                    continue
                props = {"name": name, "graph": graph_name, "entry_id": eid,
                         "title": str(entry.get("title") or eid)}
                ident = identifier_of(entry)
                if ident:
                    props["identifier"] = ident
                rid = create_artifact(project_dir, driver, database, domain_config, EXTERNAL, props,
                                      actor=actor, authority=authority, session_id=session_id)
            else:
                rep.references_existing += 1
            with driver.session(database=database) as s:
                done = _linked(s, cid, rid)
            if done:
                rep.links_existing += 1
                continue
            rep.links_created += 1
            if dry_run:
                continue
            rel = {"method": "seed_map"}
            if entry.get("resolved_by"):
                rel["resolved_by"] = str(entry["resolved_by"])
            create_link(project_dir, driver, database, domain_config, from_id=cid, to_id=rid,
                        from_type="Citation", to_type=EXTERNAL, rel_type=REL, actor=actor, authority=authority,
                        session_id=session_id, rel_properties=rel)
    return rep


def works_for_ruling(session, source_document: str) -> list[dict]:
    """Which works a governed document rests on: its Citations' `resolves_to` targets. The question the bridge exists
    to answer (SEL-036 Part E: "so the governed graph answers which works a ruling rests on")."""
    q = ("MATCH (c:Citation {source_document: $doc})-[:RESOLVES_TO]->(e:ExternalReference) "
         "RETURN DISTINCT e.name AS name, e.identifier AS identifier, e.title AS title ORDER BY name")
    return [dict(r) for r in session.run(q, doc=source_document)]
