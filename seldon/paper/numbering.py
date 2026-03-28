"""
Figure and table numbering for the paper build pipeline.

Computes display numbers (e.g., "2.3" or "5") from graph position via
APPEARS_IN and CONTAINS_SECTION edges. Numbers are computed on the fly —
the figure_number/table_number properties on artifacts are for caching only.

Public API:
    compute_figure_numbers(session, database) -> dict[artifact_id, display_str]
    compute_table_numbers(session, database) -> dict[artifact_id, display_str]
    compute_section_display(session, database) -> dict[artifact_id, display_str]
    build_name_lookup(session, fig_numbers, tbl_numbers, sec_display) -> (fig_by_name, tbl_by_name, sec_by_name)
    resolve_xref_tokens(text, figure_by_name, table_by_name, section_by_name) -> str
"""
from __future__ import annotations

import re
import warnings

from neo4j import Session

# Pattern for cross-reference tokens: {{figure:NAME}}, {{table:NAME}}, {{section:NAME}}
# Distinct from REFERENCE_PATTERN (which handles {{type:name:field}} with a field part)
XREF_PATTERN = re.compile(r'\{\{(figure|table|section):([^:}]+)\}\}')


def _assign_numbers(records: list[dict]) -> dict[str, str]:
    """
    Assign display numbers from ordered records.

    Each record must have: artifact_id, chapter_seq (int or None).
    Records are assumed pre-sorted by (chapter_seq, section_seq, name).

    Returns:
        dict mapping artifact_id → display string:
        - "1", "2", "3" for flat papers (no chapters)
        - "2.1", "2.2", "3.1" for chaptered documents
    """
    has_chapters = any(r["chapter_seq"] is not None for r in records)

    result: dict[str, str] = {}
    if has_chapters:
        chapter_counters: dict[int, int] = {}
        for r in records:
            ch = r["chapter_seq"]
            if ch is None:
                warnings.warn(
                    f"Artifact {r['artifact_id']} has no chapter ancestor in a chaptered document;"
                    " skipping numbering.",
                    UserWarning,
                    stacklevel=2,
                )
                continue
            chapter_counters[ch] = chapter_counters.get(ch, 0) + 1
            result[r["artifact_id"]] = f"{ch}.{chapter_counters[ch]}"
    else:
        for i, r in enumerate(records, start=1):
            result[r["artifact_id"]] = str(i)

    return result


def compute_figure_numbers(session: Session, database: str) -> dict[str, str]:
    """
    Compute display numbers for all Figures based on graph position.

    Queries Figures with APPEARS_IN edges. Finds depth-0 ancestor (chapter)
    via CONTAINS_SECTION* edges. Flat paper → sequential 1, 2, 3.
    Chaptered → {chapter_seq}.{n}: 2.1, 2.2, 3.1.

    Args:
        session: Active Neo4j session.
        database: Neo4j database name (unused in query but kept for API consistency).

    Returns:
        dict mapping artifact_id to display string (e.g., "2.1" or "1").
    """
    records = session.run("""
        MATCH (f:Artifact:Figure)-[:APPEARS_IN]->(s:Artifact:PaperSection)
        OPTIONAL MATCH (chapter:Artifact:PaperSection {depth: 0})-[:CONTAINS_SECTION*0..]->(s)
        RETURN f.artifact_id AS artifact_id,
               chapter.sequence AS chapter_seq,
               coalesce(s.sequence, 0) AS section_seq,
               f.name AS fig_name
        ORDER BY coalesce(chapter.sequence, 0), coalesce(s.sequence, 0), f.name
    """).data()

    return _assign_numbers(records)


def compute_table_numbers(session: Session, database: str) -> dict[str, str]:
    """
    Compute display numbers for all Tables based on graph position.

    Same logic as compute_figure_numbers but queries Table nodes.

    Args:
        session: Active Neo4j session.
        database: Neo4j database name (unused in query but kept for API consistency).

    Returns:
        dict mapping artifact_id to display string (e.g., "3.1" or "1").
    """
    records = session.run("""
        MATCH (t:Artifact:Table)-[:APPEARS_IN]->(s:Artifact:PaperSection)
        OPTIONAL MATCH (chapter:Artifact:PaperSection {depth: 0})-[:CONTAINS_SECTION*0..]->(s)
        RETURN t.artifact_id AS artifact_id,
               chapter.sequence AS chapter_seq,
               coalesce(s.sequence, 0) AS section_seq,
               t.name AS tbl_name
        ORDER BY coalesce(chapter.sequence, 0), coalesce(s.sequence, 0), t.name
    """).data()

    return _assign_numbers(records)


def compute_section_display(session: Session, database: str) -> dict[str, str]:
    """
    Compute display strings for PaperSections based on depth and sequence.

    depth=0 → "Chapter N"
    depth=1 → "Section P.N" (parent.own)
    depth=2 → "Section P.Q.N" (grandparent.parent.own)
    No depth → "Section N" (flat)

    Args:
        session: Active Neo4j session.
        database: Neo4j database name (unused in query but kept for API consistency).

    Returns:
        dict mapping artifact_id to display string (e.g., "Chapter 2" or "Section 2.1").
    """
    records = session.run("""
        MATCH (s:Artifact:PaperSection)
        OPTIONAL MATCH (parent:Artifact:PaperSection)-[:CONTAINS_SECTION]->(s)
        OPTIONAL MATCH (grandparent:Artifact:PaperSection)-[:CONTAINS_SECTION]->(parent)
        RETURN s.artifact_id AS artifact_id, s.depth AS depth,
               s.sequence AS seq,
               parent.sequence AS parent_seq,
               grandparent.sequence AS gp_seq
    """).data()

    # Deduplicate: a section with multiple CONTAINS_SECTION parents produces multiple rows.
    # Warn and keep only the first occurrence of each artifact_id.
    seen_ids: set[str] = set()
    deduped: list[dict] = []
    for r in records:
        aid = r["artifact_id"]
        if aid in seen_ids:
            warnings.warn(
                f"Section {aid} has multiple parent sections; using first match.",
                UserWarning,
                stacklevel=2,
            )
        else:
            seen_ids.add(aid)
            deduped.append(r)
    records = deduped

    result: dict[str, str] = {}
    for r in records:
        depth = r["depth"]
        seq = r["seq"] or 0
        if depth == 0:
            result[r["artifact_id"]] = f"Chapter {seq}"
        elif depth == 1:
            p = r["parent_seq"] or 0
            result[r["artifact_id"]] = f"Section {p}.{seq}"
        elif depth == 2:
            gp = r["gp_seq"] or 0
            p = r["parent_seq"] or 0
            result[r["artifact_id"]] = f"Section {gp}.{p}.{seq}"
        else:
            result[r["artifact_id"]] = f"Section {seq}"

    return result


def build_name_lookup(
    session: Session,
    figure_numbers: dict[str, str],
    table_numbers: dict[str, str],
    section_display: dict[str, str],
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """
    Convert {artifact_id: display} dicts to {name: display} dicts.

    Queries artifact names for all IDs and returns name-keyed lookups for
    use in resolve_xref_tokens.

    Args:
        session: Active Neo4j session.
        figure_numbers: {artifact_id: display} for Figure nodes.
        table_numbers: {artifact_id: display} for Table nodes.
        section_display: {artifact_id: display} for PaperSection nodes.

    Returns:
        Tuple of (figure_by_name, table_by_name, section_by_name), each
        mapping artifact name → display string.
    """
    all_ids = list(figure_numbers) + list(table_numbers) + list(section_display)
    if not all_ids:
        return {}, {}, {}

    records = session.run(
        "MATCH (a:Artifact) WHERE a.artifact_id IN $ids AND a.name IS NOT NULL "
        "RETURN a.artifact_id AS artifact_id, a.name AS name",
        ids=all_ids,
    ).data()
    id_to_name = {r["artifact_id"]: r["name"] for r in records}

    figure_by_name = {id_to_name[k]: v for k, v in figure_numbers.items() if k in id_to_name}
    table_by_name = {id_to_name[k]: v for k, v in table_numbers.items() if k in id_to_name}
    section_by_name = {id_to_name[k]: v for k, v in section_display.items() if k in id_to_name}

    return figure_by_name, table_by_name, section_by_name


def resolve_xref_tokens(
    text: str,
    figure_by_name: dict[str, str],
    table_by_name: dict[str, str],
    section_by_name: dict[str, str],
) -> str:
    """
    Replace {{figure:NAME}}, {{table:NAME}}, {{section:NAME}} tokens with display strings.

    Unknown names are left as-is (missing xrefs caught by seldon verify).

    Args:
        text: Input prose containing XREF tokens.
        figure_by_name: {name: display_number} for figures (e.g., {"fig_setup": "2.1"}).
        table_by_name: {name: display_number} for tables (e.g., {"tbl_summary": "3.1"}).
        section_by_name: {name: display_string} for sections (e.g., {"chapter_03": "Chapter 3"}).

    Returns:
        Text with all recognized tokens replaced. Unrecognized tokens are left unchanged.
    """
    def _replace(match: re.Match) -> str:
        token_type = match.group(1)
        name = match.group(2)
        if token_type == "figure":
            display = figure_by_name.get(name)
            return f"Figure {display}" if display else match.group(0)
        elif token_type == "table":
            display = table_by_name.get(name)
            return f"Table {display}" if display else match.group(0)
        elif token_type == "section":
            display = section_by_name.get(name)
            return display if display else match.group(0)
        return match.group(0)

    return XREF_PATTERN.sub(_replace, text)
