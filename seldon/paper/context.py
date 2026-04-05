"""
Paper context module — retrieves semantic anchor context for a named PaperSection.

Queries the graph and formats structured context for drafting or revision,
including the section's own anchor properties, assumes/assumed-by relationships,
explicit cross-references, and sibling sections.
"""
from __future__ import annotations

from typing import Any, Optional

import yaml
from neo4j import Driver


def get_section_context(
    driver: Driver,
    database: str,
    section_name: str,
) -> Optional[dict]:
    """
    Query graph for all context relevant to a named PaperSection.

    Returns a dict with keys:
        section: the artifact dict (None if not found)
        assumes: list of {artifact, rel_props} dicts — sections this one depends on
        assumed_by: list of {artifact, rel_props} dicts — sections that depend on this one
        cross_references_out: list of artifact dicts — explicit refs FROM this section
        cross_references_in: list of artifact dicts — explicit refs TO this section
        siblings: list of artifact dicts — PaperSections at same depth

    Returns None if no PaperSection with that name exists.
    """
    with driver.session(database=database) as session:
        # Target section
        result = session.run(
            "MATCH (s:PaperSection {name: $name}) RETURN s",
            name=section_name,
        ).single()
        if result is None:
            return None
        section = dict(result["s"])

        # Sections this section assumes (outgoing ASSUMES edges)
        assumes_records = session.run(
            "MATCH (s:PaperSection {name: $name})-[r:ASSUMES]->(t:PaperSection) "
            "RETURN t, properties(r) AS rel_props",
            name=section_name,
        ).data()
        assumes = [
            {"artifact": dict(rec["t"]), "rel_props": rec["rel_props"] or {}}
            for rec in assumes_records
        ]

        # Sections that assume this section (incoming ASSUMES edges)
        assumed_by_records = session.run(
            "MATCH (t:PaperSection)-[r:ASSUMES]->(s:PaperSection {name: $name}) "
            "RETURN t, properties(r) AS rel_props",
            name=section_name,
        ).data()
        assumed_by = [
            {"artifact": dict(rec["t"]), "rel_props": rec["rel_props"] or {}}
            for rec in assumed_by_records
        ]

        # Explicit cross-references outgoing
        xref_out_records = session.run(
            "MATCH (s:PaperSection {name: $name})-[:CROSS_REFERENCES]->(t:PaperSection) "
            "RETURN t",
            name=section_name,
        ).data()
        cross_references_out = [dict(rec["t"]) for rec in xref_out_records]

        # Explicit cross-references incoming
        xref_in_records = session.run(
            "MATCH (t:PaperSection)-[:CROSS_REFERENCES]->(s:PaperSection {name: $name}) "
            "RETURN t",
            name=section_name,
        ).data()
        cross_references_in = [dict(rec["t"]) for rec in xref_in_records]

        # Sibling sections — all PaperSections at the same depth
        depth = section.get("depth")
        if depth is not None:
            sib_records = session.run(
                "MATCH (sib:PaperSection) "
                "WHERE sib.depth = $depth AND sib.name <> $name "
                "RETURN sib ORDER BY sib.sequence",
                depth=depth,
                name=section_name,
            ).data()
            siblings = [dict(rec["sib"]) for rec in sib_records]
        else:
            siblings = []

    return {
        "section": section,
        "assumes": assumes,
        "assumed_by": assumed_by,
        "cross_references_out": cross_references_out,
        "cross_references_in": cross_references_in,
        "siblings": siblings,
    }


def _as_list(value) -> list:
    """Normalize a graph property to a list.

    Neo4j returns list properties as Python lists and string properties as
    strings.  The anchor population task stores pipe-separated strings
    (e.g. "claim1 | claim2") because the CLI update command cannot set list
    properties.  Accept both forms so the renderer works regardless of how
    the value was stored.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return value
    # Pipe-separated string
    return [item.strip() for item in str(value).split("|") if item.strip()]


def format_context_text(ctx: dict) -> str:
    """Format context dict as human-readable text for CC task context blocks."""
    section = ctx["section"]
    name = section.get("name", "?")
    title = section.get("title", "")
    lines = [f"=== Context for {name}: {title} ===", ""]

    # Anchor properties
    core_arg = section.get("core_argument")
    if core_arg:
        lines += ["CORE ARGUMENT:", f"  {core_arg}", ""]
    else:
        lines += ["CORE ARGUMENT:", "  (not set)", ""]

    claims = _as_list(section.get("claims"))
    lines.append("CLAIMS ESTABLISHED:")
    if claims:
        for c in claims:
            lines.append(f"  - {c}")
    else:
        lines.append("  (not set)")
    lines.append("")

    # Assumes (outgoing)
    assumes = ctx["assumes"]
    lines.append("THIS SECTION ASSUMES (revision in these may affect this one):")
    if assumes:
        for entry in assumes:
            a = entry["artifact"]
            rp = entry["rel_props"]
            a_name = a.get("name", "?")
            a_title = a.get("title", "")
            topic = rp.get("topic", "")
            strength = rp.get("strength", "")
            topic_str = f", {topic}" if topic else ""
            strength_str = f" [{strength}]" if strength else ""
            lines.append(f"  \u2190 {a_name}: {a_title}{topic_str}{strength_str}")
    else:
        lines.append("  (none)")
    lines.append("")

    # Assumed by (incoming)
    assumed_by = ctx["assumed_by"]
    lines.append("SECTIONS THAT ASSUME THIS ONE (revising this may break these):")
    if assumed_by:
        for entry in assumed_by:
            a = entry["artifact"]
            rp = entry["rel_props"]
            a_name = a.get("name", "?")
            a_title = a.get("title", "")
            topic = rp.get("topic", "")
            strength = rp.get("strength", "")
            topic_str = f", {topic}" if topic else ""
            strength_str = f" [{strength}]" if strength else ""
            lines.append(f"  \u2192 {a_name}: {a_title}{topic_str}{strength_str}")
    else:
        lines.append("  (none)")
    lines.append("")

    # Cross-references
    xref_out = ctx["cross_references_out"]
    xref_in = ctx["cross_references_in"]
    lines.append("CROSS-REFERENCES:")
    if xref_out or xref_in:
        for a in xref_in:
            lines.append(f"  \u2190 {a.get('name', '?')} (explicit)")
        for a in xref_out:
            lines.append(f"  \u2192 {a.get('name', '?')} (explicit)")
    else:
        lines.append("  (none)")
    lines.append("")

    # Terminology
    terms = _as_list(section.get("terminology_defined"))
    lines.append("TERMINOLOGY DEFINED HERE:")
    if terms:
        for t in terms:
            lines.append(f"  - {t}")
    else:
        lines.append("  (not set)")
    lines.append("")

    # Forward promises
    promises = _as_list(section.get("forward_promises"))
    lines.append("FORWARD PROMISES (not yet fulfilled):")
    if promises:
        for p in promises:
            lines.append(f"  \u2192 {p}")
    else:
        lines.append("  (none)")
    lines.append("")

    # Open threads
    threads = _as_list(section.get("open_threads"))
    lines.append("OPEN THREADS:")
    if threads:
        for t in threads:
            lines.append(f"  - {t}")
    else:
        lines.append("  (none)")
    lines.append("")

    # Siblings
    siblings = ctx["siblings"]
    lines.append("SIBLING SECTIONS:")
    if siblings:
        for sib in siblings:
            sib_name = sib.get("name", "?")
            sib_title = sib.get("title", "")
            sib_arg = sib.get("core_argument", "")
            arg_str = f" — {sib_arg}" if sib_arg else ""
            lines.append(f"  {sib_name}: {sib_title}{arg_str}")
    else:
        lines.append("  (none at same depth)")

    return "\n".join(lines)


def format_context_yaml(ctx: dict) -> str:
    """Format context dict as YAML for machine consumption."""
    section = ctx["section"]

    def _section_summary(a: dict) -> dict:
        return {
            "name": a.get("name"),
            "title": a.get("title"),
            "core_argument": a.get("core_argument"),
        }

    output: dict[str, Any] = {
        "section": {
            "name": section.get("name"),
            "title": section.get("title"),
            "core_argument": section.get("core_argument"),
            "claims": _as_list(section.get("claims")),
            "terminology_defined": _as_list(section.get("terminology_defined")),
            "forward_promises": _as_list(section.get("forward_promises")),
            "open_threads": _as_list(section.get("open_threads")),
            "anchor_date": section.get("anchor_date"),
            "anchor_source": section.get("anchor_source"),
        },
        "assumes": [
            {
                **_section_summary(e["artifact"]),
                "topic": e["rel_props"].get("topic"),
                "strength": e["rel_props"].get("strength"),
            }
            for e in ctx["assumes"]
        ],
        "assumed_by": [
            {
                **_section_summary(e["artifact"]),
                "topic": e["rel_props"].get("topic"),
                "strength": e["rel_props"].get("strength"),
            }
            for e in ctx["assumed_by"]
        ],
        "cross_references_out": [_section_summary(a) for a in ctx["cross_references_out"]],
        "cross_references_in": [_section_summary(a) for a in ctx["cross_references_in"]],
        "siblings": [_section_summary(a) for a in ctx["siblings"]],
    }
    return yaml.dump(output, default_flow_style=False, sort_keys=False, allow_unicode=True)
