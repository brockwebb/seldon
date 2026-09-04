"""
Paper build module — resolves {{type:name:field}} references, runs Tier 1
structural integrity checks, optionally runs Tier 2+3 QC, assembles a .qmd
file, and optionally renders via Quarto.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from seldon.config import load_project_config, get_neo4j_driver
from seldon.paper.numbering import (
    compute_figure_numbers,
    compute_table_numbers,
    compute_section_display,
    build_name_lookup,
    resolve_xref_tokens,
)
from seldon.paper.qc import (
    run_tier2,
    run_tier3,
    load_qc_config,
    load_style_config,
    Violation,
    format_violations,
)
from seldon.paper.copyedit import load_copyedit_config, run_copyedit, parse_bib_keys
from seldon.domain.units_vocabulary import load_units_vocabulary
from seldon.core.naming import unanchored_name_grammar


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Reference token: ``{{result|figure|cite : NAME : FIELD}}``.
#:
#: The NAME capture uses the AD-028 Result name grammar (as amended 2026-09-04
#: to admit uppercase), not "any character but ':' and '}'". A string whose
#: name position is not a legal name is therefore not a token at all, which is
#: what lets a document print the placeholder ``{{result:<NAME>:value}}`` while
#: explaining the token syntax to a reader, without the resolver reporting
#: SI-01 on the explanation.
#:
#: All three token types share the grammar because all three names are Seldon
#: artifact names: a `cite` token names a Citation artifact, and that
#: artifact's BibTeX key lives in its own `bibtex_key` property (see the SI-07
#: check), so narrowing the token grammar constrains no BibTeX key.
#:
#: The grammar comes from `seldon.core.naming`, a leaf module, so this is a
#: plain eager compile. It was previously a lazy-compiling wrapper because the
#: grammar lived in `seldon.commands.result`, which imports this module — a
#: hard circular import. Hoisting the constant removed the need for it.
REFERENCE_PATTERN = re.compile(
    r'\{\{(result|figure|cite):(' + unanchored_name_grammar() + r'):([^}]+)\}\}'
)

# AD-028: marker appended to a resolved value when a `proposed` Result is
# rendered under --allow-proposed. Single space, then the literal.
PROPOSED_MARKER = "(proposed)"

# AD-028: check id for the transitional resolve-by-units fallback.
UNITS_FALLBACK_CHECK_ID = "SI-09"

TYPE_TO_REFTYPE = {
    "Result": "result",
    "Figure": "figure",
    "Citation": "cite",
}

REFTYPE_TO_TYPE = {v: k for k, v in TYPE_TO_REFTYPE.items()}


# ---------------------------------------------------------------------------
# Abstract extraction
# ---------------------------------------------------------------------------

def _extract_abstract_text(abstract_path: Path) -> str:
    """
    Read 00_abstract.md and return plain text with the heading stripped.

    Strips any leading line that is a markdown heading (starts with '#').
    Strips leading and trailing whitespace from the result.
    Returns empty string if file is empty after stripping.
    """
    raw = abstract_path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    # Drop lines that are purely a markdown heading at the start of the file
    while lines and lines[0].startswith("#"):
        lines.pop(0)
    return "\n".join(lines).strip()


def _inject_abstract_into_frontmatter(frontmatter_content: str, abstract_text: str) -> str:
    """
    Inject an abstract: block scalar into an existing YAML frontmatter string.

    frontmatter_content must be a string starting with '---' and ending with '---'.
    The abstract is inserted before the closing '---' delimiter.
    Lines of abstract_text are indented by 2 spaces for the YAML block scalar.
    """
    # Build YAML block scalar: "abstract: |\n  line1\n  line2"
    indented_lines = []
    for line in abstract_text.split("\n"):
        indented_lines.append(f"  {line}" if line.strip() else "")
    abstract_block = "abstract: |\n" + "\n".join(indented_lines).rstrip()

    content = frontmatter_content.rstrip()
    if content.endswith("---"):
        # Insert before closing ---
        body = content[:-3].rstrip()
        separator = "\n" if body else ""
        return f"---{separator}\n{abstract_block}\n---" if not body else f"{body}\n{abstract_block}\n---"
    else:
        # No closing --- found — append and close
        return f"{content}\n{abstract_block}\n---"


def _build_minimal_frontmatter(abstract_text: str) -> str:
    """
    Build a minimal YAML frontmatter block containing only the abstract.

    Used when no frontmatter.yml exists but 00_abstract.md does.
    Returns a complete '---...---' block.
    """
    return _inject_abstract_into_frontmatter("---", abstract_text)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class RefError:
    check_id: str   # SI-01, SI-02, SI-03, SI-07, SI-08, SI-09
    file: str
    line: int
    token: str      # the original {{...}} token
    message: str
    fatal: bool     # True = build aborts; False = warning only
    # AD-028: the artifact name this record is about, when one is known. Set on
    # non-fatal SI-03 records so the build summary can list which Results were
    # rendered as proposed without re-parsing tokens.
    artifact_name: Optional[str] = None


# ---------------------------------------------------------------------------
# Artifact loading
# ---------------------------------------------------------------------------

def load_named_artifacts(driver, database: str) -> dict:
    """
    Load all artifacts with a 'name' property from the graph.
    Returns dict keyed by "reftype:name" (e.g., "result:info_rate_3_32").
    reftype is lowercase: result, figure, cite (mapped from artifact_type).
    """
    artifacts = {}
    with driver.session(database=database) as session:
        records = session.run(
            "MATCH (a:Artifact) WHERE a.name IS NOT NULL RETURN a"
        ).data()

    for record in records:
        node = dict(record["a"])
        artifact_type = node.get("artifact_type", "")
        reftype = TYPE_TO_REFTYPE.get(artifact_type)
        if reftype is None:
            continue  # skip types we don't map (e.g. ResearchTask)
        name = node.get("name")
        if name:
            key = f"{reftype}:{name}"
            artifacts[key] = node

    return artifacts


# ---------------------------------------------------------------------------
# TRANSITIONAL (AD-028) — resolve {{result:NAME:...}} by the `units` property
#
# Before AD-028 `seldon result register` had no --name flag, so authors stashed
# the token key in `units`. This fallback keeps those projects building while
# `seldon result migrate-names` is rolled out.
#
# REMOVAL CONDITION: delete build_units_fallback_index, its call site in
# build_paper, and the `units_fallback` parameter of resolve_references once
# `seldon result migrate-names` has been run live against every project graph
# and no build emits an SI-09 line. Nothing else depends on this path.
#
# check_units_fallback (below) is the instrument that measures that condition,
# and `seldon paper check-units-fallback` is its CLI. Both go with the fallback
# when it goes: an instrument for a removed condition is dead weight.
# Last fleet measurement: cc_tasks/2026-09-04_si09_removal_condition_SUBRESULT.md
# ---------------------------------------------------------------------------

def build_units_fallback_index(
    driver,
    database: str,
    vocabulary: Optional[frozenset] = None,
) -> dict[str, list[dict]]:
    """Index unnamed Results by their ``units`` value for transitional lookup.

    Only Results that have no ``name`` and whose ``units`` is NOT a real unit of
    measurement are indexed: a Result whose units is ``count`` is measured in
    counts, and a ``{{result:count:value}}`` token matching it would be a
    coincidence rather than a reference.

    Args:
        driver: Open Neo4j driver.
        database: Database name to query.
        vocabulary: Optional pre-loaded units vocabulary. Defaults to the
            packaged one from ``seldon.domain.units_vocabulary``.

    Returns:
        Mapping of units string → list of Result nodes carrying it. A list with
        more than one entry is an ambiguity the resolver refuses to guess at.

    Raises:
        FileNotFoundError: If the packaged units vocabulary is missing.
        ValueError: If the packaged units vocabulary is malformed.
    """
    if vocabulary is None:
        vocabulary = load_units_vocabulary()

    index: dict[str, list[dict]] = {}
    with driver.session(database=database) as session:
        records = session.run(
            "MATCH (r:Result) "
            "WHERE r.name IS NULL AND r.units IS NOT NULL "
            "RETURN r"
        ).data()

    for record in records:
        node = dict(record["r"])
        units = node.get("units")
        if not isinstance(units, str) or not units.strip():
            continue
        if units in vocabulary:
            continue
        index.setdefault(units, []).append(node)

    return index


@dataclass
class UnitsFallbackFileCount:
    """Per-file SI-09 tally produced by :func:`check_units_fallback`.

    Attributes:
        path: File measured, as given by the caller.
        tokens: Result tokens the resolver recognised in the file. Reported so
            a zero can be distinguished from "this file has no tokens at all".
        resolutions: Tokens resolved by the transitional units fallback
            (non-fatal SI-09). This is the number the removal condition is
            stated in.
        ambiguities: Tokens the fallback refused to resolve because more than
            one unnamed Result carried the units string (fatal SI-09). These
            also block removal: the fallback is still load-bearing wherever it
            is being consulted at all.
        unresolved: Tokens that matched nothing at all (SI-01). Reported so a
            zero can be read honestly: a project whose graph is empty resolves
            nothing by the fallback either, and that is not the same evidence
            as a project whose tokens all resolve by name.
    """

    path: str
    tokens: int
    resolutions: int
    ambiguities: int
    unresolved: int = 0


@dataclass
class UnitsFallbackReport:
    """Whole-project SI-09 tally produced by :func:`check_units_fallback`.

    Attributes:
        project_dir: Project measured.
        database: Neo4j database read, or None when the config named none.
        files: Per-file tallies, in the order the caller supplied the files.
        index_keys: Number of distinct units strings in the fallback index —
            i.e. how many unnamed Results are still reachable *only* by the
            transitional path. Zero here means the fallback could not fire even
            if a document asked it to. A non-zero value in a project reporting
            zero resolutions is a latent dependency, not a live one: nothing
            cites those Results today, but the legacy rows are still there.
        named_artifacts: Number of name-bearing artifacts loaded from the
            graph. A zero-resolution report from a graph with zero named
            artifacts is vacuous — the tokens matched nothing at all — so this
            is what makes a reported zero auditable.
        error: Populated when the project could not be measured (no config, no
            database name, graph unreachable). A project with an error is NOT a
            project at zero and must never be counted as one.
    """

    project_dir: Path
    database: Optional[str]
    files: list[UnitsFallbackFileCount]
    index_keys: int
    named_artifacts: int = 0
    error: Optional[str] = None

    @property
    def measured(self) -> bool:
        """True when the tallies below are real measurements."""
        return self.error is None

    @property
    def resolutions(self) -> int:
        """Total non-fatal SI-09 resolutions across all files."""
        return sum(f.resolutions for f in self.files)

    @property
    def ambiguities(self) -> int:
        """Total fatal SI-09 ambiguities across all files."""
        return sum(f.ambiguities for f in self.files)

    @property
    def tokens(self) -> int:
        """Total result tokens seen across all files."""
        return sum(f.tokens for f in self.files)

    @property
    def unresolved(self) -> int:
        """Total SI-01 tokens (matched no artifact by any route)."""
        return sum(f.unresolved for f in self.files)


def check_units_fallback(
    project_dir: Path,
    files: Iterable[Path],
) -> UnitsFallbackReport:
    """Count SI-09 transitional-fallback resolutions without writing anything.

    This is the instrument for the SI-09 removal condition stated above: the
    fallback may be deleted once every project reports zero. `build_paper`
    cannot answer that question for a general project, because it only looks at
    `paper/sections/*.md` while token-bearing prose also lives in `docs/`,
    `cc_tasks/`, and elsewhere; and because it writes a `.qmd` and may invoke
    Quarto, which a fleet-wide read-only measurement must not do.

    Every graph query it issues is a read. Nothing is written to the project.

    Args:
        project_dir: Project root holding `seldon.yaml`.
        files: Files to resolve. The caller chooses the file set — for the
            removal-condition measurement that set is the project's *tracked*
            files containing result tokens, since untracked scratch is not the
            project's content.

    Returns:
        A :class:`UnitsFallbackReport`. When the project cannot be measured —
        unparseable config, no `neo4j.database`, unreachable or absent graph —
        the report carries `error` and empty tallies. That is deliberately not
        the same value as a measured zero: an unmeasurable project does not
        satisfy the removal condition, and collapsing the two would let the
        fallback be deleted on the strength of a project nobody could read.

    Raises:
        Nothing. Failure to reach a project's graph is a reportable outcome of a
        fleet-wide survey, not an error that should abort the survey. Anything
        that goes wrong is recorded in `error` with its exception type.
    """
    file_list = [Path(f) for f in files]

    try:
        config = load_project_config(project_dir)
        database = (config.get("neo4j") or {}).get("database")
        if not database:
            return UnitsFallbackReport(
                project_dir=Path(project_dir), database=None, files=[],
                index_keys=0,
                error="seldon.yaml names no neo4j.database",
            )
        driver = get_neo4j_driver(config)
        try:
            artifacts = load_named_artifacts(driver, database)
            index = build_units_fallback_index(driver, database)
        finally:
            driver.close()
    except Exception as exc:  # noqa: BLE001 — reported, never swallowed
        return UnitsFallbackReport(
            project_dir=Path(project_dir), database=None, files=[],
            index_keys=0,
            error=f"{type(exc).__name__}: {exc}",
        )

    counts: list[UnitsFallbackFileCount] = []
    for path in file_list:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            counts.append(UnitsFallbackFileCount(
                path=str(path), tokens=0, resolutions=0, ambiguities=0,
                unresolved=0,
            ))
            # A file named by the caller that cannot be read is a caller-side
            # problem, but silently scoring it zero would understate the tally.
            print(f"WARNING: {path}: {type(exc).__name__}: {exc}")
            continue

        tokens = sum(
            1 for m in REFERENCE_PATTERN.finditer(text) if m.group(1) == "result"
        )
        _resolved, errors = resolve_references(
            text=text,
            artifacts=artifacts,
            filename=str(path),
            units_fallback=index,
            # Proposed and stale Results are irrelevant to the SI-09 question;
            # admitting them keeps the tally about the fallback alone.
            allow_proposed=True,
            mark_proposed=False,
        )
        si09 = [e for e in errors if e.check_id == UNITS_FALLBACK_CHECK_ID]
        counts.append(UnitsFallbackFileCount(
            path=str(path),
            tokens=tokens,
            resolutions=sum(1 for e in si09 if not e.fatal),
            ambiguities=sum(1 for e in si09 if e.fatal),
            unresolved=sum(1 for e in errors if e.check_id == "SI-01"),
        ))

    return UnitsFallbackReport(
        project_dir=Path(project_dir),
        database=database,
        files=counts,
        index_keys=len(index),
        named_artifacts=len(artifacts),
    )


# ---------------------------------------------------------------------------
# Reference resolution
# ---------------------------------------------------------------------------

def resolve_references(
    text: str,
    artifacts: dict,
    filename: str,
    bib_path: Optional[Path] = None,
    paper_dir: Optional[Path] = None,
    units_fallback: Optional[dict] = None,
    allow_proposed: bool = False,
    mark_proposed: bool = True,
    value_formatter: Callable[[Any], str] = str,
) -> tuple[str, list[RefError]]:
    """
    Replace {{type:name:field}} tokens with artifact values.
    Returns (resolved_text, errors).

    Tier 1 checks during resolution:
    - SI-01: artifact not found → fatal
    - SI-02: artifact.state == "stale" → fatal
    - SI-03: Result artifact.state == "proposed" → fatal, unless allow_proposed
    - SI-07: cite token, bib_path provided, bibtex_key not in bib content → fatal
    - SI-08: figure token, paper_dir provided, figure path field not a real file → fatal
    - SI-09: result token resolved by the TRANSITIONAL units fallback → warning;
      fatal only when the fallback is ambiguous (AD-028)

    On error: leave original token in text, record error.

    Args:
        text: Section text containing {{type:name:field}} tokens.
        artifacts: Mapping of "reftype:name" → artifact node, from
            load_named_artifacts.
        filename: Name used in error records.
        bib_path: Optional path to references.bib, enabling SI-07.
        paper_dir: Optional paper directory, enabling SI-08.
        units_fallback: Optional TRANSITIONAL (AD-028) index from
            build_units_fallback_index, mapping a units string to the unnamed
            Results carrying it. When supplied, a result token that matches no
            `name` is retried against it. Pass None to disable the fallback.
        allow_proposed: When True, a Result in `proposed` state resolves and is
            rendered as "<value> (proposed)" with a non-fatal SI-03 record
            instead of aborting the build.
        mark_proposed: When True (the default) a value admitted by
            allow_proposed carries the PROPOSED_MARKER suffix. Pass False to
            render the bare value — appropriate for a working document whose
            every Result is proposed, where the marker on every number is noise
            rather than signal. The non-fatal SI-03 record is still emitted
            either way, so the information is never lost: the caller can count
            and name the proposed Results it rendered. Has no effect unless
            allow_proposed is True.
        value_formatter: Callable applied to the resolved field value to produce
            the rendered string. Defaults to `str`, i.e. exactly today's
            output. Supply a formatter to control rendering — for example to
            print an integral float as "26" rather than "26.0" when the graph
            stores every Result value as a float. Applied to the value in every
            case, including the proposed-marker case.

    Returns:
        Tuple of (resolved_text, errors).

    Raises:
        TypeError: If value_formatter returns a non-str. That is a caller bug,
            not a document problem, so it is raised rather than recorded as a
            RefError — a non-str substitution would otherwise fail deep inside
            `re.sub` with no reference to the token that caused it.
    """
    errors: list[RefError] = []

    # Read bib content once if needed
    bib_content: Optional[str] = None
    if bib_path is not None and bib_path.exists():
        bib_content = bib_path.read_text(encoding="utf-8")

    def _line_of(pos: int) -> int:
        return text.count("\n", 0, pos) + 1

    def _replace(match: re.Match) -> str:
        token = match.group(0)
        reftype = match.group(1)
        name = match.group(2)
        field = match.group(3)
        lineno = _line_of(match.start())

        key = f"{reftype}:{name}"
        artifact = artifacts.get(key)

        # TRANSITIONAL (AD-028): no Result carries this name — retry against the
        # units-as-name index. See build_units_fallback_index for the removal
        # condition.
        if artifact is None and reftype == "result" and units_fallback:
            candidates = units_fallback.get(name, [])
            if len(candidates) == 1:
                artifact = candidates[0]
                errors.append(RefError(
                    check_id=UNITS_FALLBACK_CHECK_ID,
                    file=filename,
                    line=lineno,
                    token=token,
                    message=(
                        f"TRANSITIONAL units fallback (AD-028): no Result has "
                        f"name='{name}'; matched artifact_id "
                        f"{candidates[0].get('artifact_id', '?')} whose units='{name}'. "
                        f"Run `seldon result migrate-names` to assign a real name."
                    ),
                    fatal=False,
                    artifact_name=name,
                ))
            elif len(candidates) > 1:
                ids = ", ".join(
                    str(c.get("artifact_id", "?")) for c in candidates
                )
                errors.append(RefError(
                    check_id=UNITS_FALLBACK_CHECK_ID,
                    file=filename,
                    line=lineno,
                    token=token,
                    message=(
                        f"TRANSITIONAL units fallback (AD-028) is ambiguous for "
                        f"'{name}': {len(candidates)} unnamed Results carry "
                        f"units='{name}' ({ids}). Run `seldon result migrate-names` "
                        f"and name them explicitly."
                    ),
                    fatal=True,
                    artifact_name=name,
                ))
                return token

        # SI-01: not found
        if artifact is None:
            errors.append(RefError(
                check_id="SI-01",
                file=filename,
                line=lineno,
                token=token,
                message=f"Artifact not found: {key}",
                fatal=True,
            ))
            return token

        state = artifact.get("state", "")

        # SI-02: stale
        if state == "stale":
            errors.append(RefError(
                check_id="SI-02",
                file=filename,
                line=lineno,
                token=token,
                message=f"Artifact '{key}' is stale",
                fatal=True,
            ))
            return token

        # SI-03: Result in proposed state
        render_proposed = False
        if reftype == "result" and state == "proposed":
            if not allow_proposed:
                errors.append(RefError(
                    check_id="SI-03",
                    file=filename,
                    line=lineno,
                    token=token,
                    message=f"Result '{key}' is proposed (not yet verified)",
                    fatal=True,
                    artifact_name=name,
                ))
                return token
            # AD-028: --allow-proposed downgrades SI-03 to a warning and, by
            # default, marks the rendered value so a reader can see it is not
            # yet verified. Under mark_proposed=False the value renders bare —
            # but this warning still records the token, so the proposed set
            # remains countable and nameable by the caller.
            render_proposed = True
            errors.append(RefError(
                check_id="SI-03",
                file=filename,
                line=lineno,
                token=token,
                message=(
                    f"Result '{key}' is proposed — rendered with the "
                    f"'{PROPOSED_MARKER}' marker (--allow-proposed)"
                    if mark_proposed else
                    f"Result '{key}' is proposed — rendered without a marker "
                    f"(--allow-proposed, mark_proposed=False)"
                ),
                fatal=False,
                artifact_name=name,
            ))

        # Resolve field value
        value = artifact.get(field)
        if value is None:
            errors.append(RefError(
                check_id="SI-01",
                file=filename,
                line=lineno,
                token=token,
                message=f"Field '{field}' not found on artifact '{key}'",
                fatal=True,
            ))
            return token

        # SI-07: cite token — verify bibtex_key exists in .bib file
        if reftype == "cite" and bib_path is not None:
            bibtex_key = str(artifact.get("bibtex_key", ""))
            if bib_content is not None and bibtex_key and bibtex_key not in bib_content:
                errors.append(RefError(
                    check_id="SI-07",
                    file=filename,
                    line=lineno,
                    token=token,
                    message=(
                        f"Citation '{key}' bibtex_key '{bibtex_key}' "
                        f"not found in {bib_path}"
                    ),
                    fatal=True,
                ))
                return token

        # SI-08: figure token — verify path file exists
        if reftype == "figure" and paper_dir is not None and field == "path":
            figure_path = str(value)
            if not (paper_dir / figure_path).exists():
                errors.append(RefError(
                    check_id="SI-08",
                    file=filename,
                    line=lineno,
                    token=token,
                    message=(
                        f"Figure '{key}' path '{figure_path}' "
                        f"does not exist under {paper_dir}"
                    ),
                    fatal=True,
                ))
                return token

        rendered = value_formatter(value)
        if not isinstance(rendered, str):
            raise TypeError(
                f"value_formatter must return str; got "
                f"{type(rendered).__name__} for token {token!r} in {filename}"
            )

        if render_proposed and mark_proposed:
            return f"{rendered} {PROPOSED_MARKER}"
        return rendered

    resolved = REFERENCE_PATTERN.sub(_replace, text)
    return resolved, errors


# ---------------------------------------------------------------------------
# XREF lookup helpers
# ---------------------------------------------------------------------------

def _compute_xref_lookups(
    session,
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """
    Compute name-keyed display-string lookups for figures, tables, and sections.

    Calls the numbering module to derive display strings from graph position, then
    converts artifact_id keys to name keys via build_name_lookup.

    The ``database`` parameter was removed: the three numbering functions document
    their own ``database`` argument as unused (queries run via the already-open
    session's database affinity), so forwarding it from the call site was dead
    plumbing.  An empty string is passed to satisfy their current signatures.

    Args:
        session: Active Neo4j session (already bound to the correct database).

    Returns:
        Tuple of (figure_by_name, table_by_name, section_by_name), each mapping
        artifact name → display string (e.g., {"fig_one": "1", "intro": "Section 1"}).
    """
    # The database argument is unused by these functions (see numbering.py docstrings).
    figure_numbers = compute_figure_numbers(session, "")
    table_numbers = compute_table_numbers(session, "")
    section_display = compute_section_display(session, "")
    return build_name_lookup(session, figure_numbers, table_numbers, section_display)


# ---------------------------------------------------------------------------
# Build pipeline
# ---------------------------------------------------------------------------

def build_paper(
    project_dir: Path,
    paper_dir: Optional[Path] = None,
    output_path: Optional[Path] = None,
    skip_qc: bool = False,
    strict: bool = False,
    no_render: bool = False,
    qc_config_path: Optional[Path] = None,
    style_config_path: Optional[Path] = None,
    allow_proposed: bool = False,
) -> int:
    """
    Full build pipeline. Returns exit code (0=success, 1=fatal errors).

    Args:
        allow_proposed: When True, a `proposed` Result no longer aborts the
            build (SI-03 becomes a warning) and renders as "<value> (proposed)".
            The summary reports how many proposed tokens were rendered and the
            Result names behind them. Default False preserves the fatal
            behaviour.

    Pipeline:
    1. Load config (load_project_config from project_dir)
    2. paper_dir defaults to project_dir / "paper"
    3. Discover sections: sorted(paper_dir / "sections" / "*.md")
    4. Load artifacts from graph
    5. bib_path = paper_dir / "references.bib" (None if doesn't exist)
    6. Resolve references in each section (collect all RefErrors)
    7. If any fatal RefError: print errors, return 1
    8. Unless skip_qc: run_tier2 + run_tier3 on each resolved section
    9. Assemble: frontmatter_path = paper_dir / "frontmatter.yml"
       - If frontmatter exists: prepend its content
       - Concatenate resolved sections
    10. Write to output_path (default: paper_dir / "paper.qmd")
    11. Unless no_render: subprocess.run(["quarto", "render", str(output_path)])
    12. Print summary report
    13. Return 0 if no fatal errors, 1 if strict=True and QC violations found
    """
    # 1. Load project config
    config = load_project_config(project_dir)
    database = config["neo4j"]["database"]

    # 2. paper_dir default
    if paper_dir is None:
        paper_dir = project_dir / "paper"

    # 3. Discover sections (00_abstract.md is excluded from the body)
    sections_dir = paper_dir / "sections"
    if sections_dir.exists():
        all_section_files = sorted(sections_dir.glob("*.md"))
        section_files = [f for f in all_section_files if f.name != "00_abstract.md"]
        abstract_path = sections_dir / "00_abstract.md"
        abstract_text: Optional[str] = _extract_abstract_text(abstract_path) if abstract_path.exists() else None
    else:
        section_files = []
        abstract_text = None

    # 4. Load artifacts from graph and compute XREF lookup tables
    driver = get_neo4j_driver(config)
    try:
        artifacts = load_named_artifacts(driver, database)
        # TRANSITIONAL (AD-028) — see build_units_fallback_index.
        units_fallback = build_units_fallback_index(driver, database)
        with driver.session(database=database) as session:
            figure_by_name, table_by_name, section_by_name = _compute_xref_lookups(
                session
            )
    finally:
        driver.close()

    # 5. bib_path
    bib_path_candidate = paper_dir / "references.bib"
    bib_path = bib_path_candidate if bib_path_candidate.exists() else None

    # 6. Resolve references in each section
    all_ref_errors: list[RefError] = []
    resolved_sections: list[tuple[str, str]] = []  # (filename, resolved_text)

    for section_file in section_files:
        text = section_file.read_text(encoding="utf-8")
        # XREF pre-pass: resolve {{figure:NAME}}, {{table:NAME}}, {{section:NAME}} tokens
        # before the result/figure/cite {{type:name:field}} pass below.
        # Unknown names are left as-is (no crash, no error recorded here).
        text = resolve_xref_tokens(text, figure_by_name, table_by_name, section_by_name)
        resolved, errors = resolve_references(
            text=text,
            artifacts=artifacts,
            filename=section_file.name,
            bib_path=bib_path,
            paper_dir=paper_dir,
            units_fallback=units_fallback,
            allow_proposed=allow_proposed,
        )
        all_ref_errors.extend(errors)
        resolved_sections.append((section_file.name, resolved))

    # 7. Abort if fatal errors
    fatal_errors = [e for e in all_ref_errors if e.fatal]
    if fatal_errors:
        print("=== BUILD REPORT ===\n")
        print("TIER 1: Structural Integrity")
        for e in fatal_errors:
            print(f"  [{e.check_id}] {e.file}:{e.line}: {e.message} (token: {e.token})")
        print(f"\nBuild: FAILED ({len(fatal_errors)} fatal error(s))")
        return 1

    # 8. QC checks
    # 8a. Tier 0: Copy Edit (always runs — not skipped by --skip-qc)
    copyedit_violations: list[Violation] = []
    try:
        ce_config = load_copyedit_config()
        bib_path = paper_dir / "references.bib"
        bib_keys = parse_bib_keys(bib_path) if bib_path.exists() else None
        for fname, resolved_text in resolved_sections:
            copyedit_violations.extend(
                run_copyedit(resolved_text, ce_config, fname, bib_keys=bib_keys)
            )
    except FileNotFoundError:
        pass  # No copyedit config — skip silently

    # 8b. Tier 2/3
    tier2_violations: list[Violation] = []
    tier3_violations: list[Violation] = []

    if not skip_qc:
        qc_config = load_qc_config(qc_config_path)
        style_config = load_style_config(style_config_path)

        for fname, resolved_text in resolved_sections:
            tier2_violations.extend(run_tier2(resolved_text, qc_config, fname))
            tier3_violations.extend(run_tier3(resolved_text, style_config, fname))

    # 9. Assemble document
    parts: list[str] = []

    frontmatter_path = paper_dir / "frontmatter.yml"
    if abstract_text:
        if frontmatter_path.exists():
            raw_frontmatter = frontmatter_path.read_text(encoding="utf-8").rstrip()
            parts.append(_inject_abstract_into_frontmatter(raw_frontmatter, abstract_text))
        else:
            parts.append(_build_minimal_frontmatter(abstract_text))
    elif frontmatter_path.exists():
        parts.append(frontmatter_path.read_text(encoding="utf-8").rstrip())

    for _fname, resolved_text in resolved_sections:
        parts.append(resolved_text.rstrip())

    assembled = "\n\n".join(parts)
    if assembled and not assembled.endswith("\n"):
        assembled += "\n"

    # 10. Write output
    if output_path is None:
        output_path = paper_dir / "paper.qmd"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(assembled, encoding="utf-8")

    # 11. Quarto render
    if not no_render:
        try:
            subprocess.run(
                ["quarto", "render", str(output_path)],
                check=True,
            )
        except FileNotFoundError:
            print("WARNING: quarto not found — skipping render step")
        except subprocess.CalledProcessError as e:
            print(f"WARNING: quarto render failed (exit code {e.returncode})")

    # 12. Print summary report
    if copyedit_violations:
        print(format_violations(copyedit_violations, "TIER 0: Copy Edit"))
    _print_report(
        ref_errors=all_ref_errors,
        tier2=tier2_violations,
        tier3=tier3_violations,
        output_path=output_path,
        paper_dir=paper_dir,
        strict=strict,
        allow_proposed=allow_proposed,
    )

    # 13. Return code — CE violations are always blocking
    if copyedit_violations:
        return 1
    if strict and (tier2_violations or tier3_violations):
        return 1
    return 0


def summarize_proposed(ref_errors: list[RefError]) -> tuple[int, list[str]]:
    """Summarise which Results were rendered as proposed (AD-028).

    Args:
        ref_errors: All Tier 1 records collected during resolution.

    Returns:
        Tuple of (token_count, names). token_count is how many individual
        {{result:...}} tokens were rendered with the "(proposed)" marker;
        names is the sorted list of distinct Result names behind them.

    Raises:
        Nothing.
    """
    rendered = [
        e for e in ref_errors
        if e.check_id == "SI-03" and not e.fatal
    ]
    names = sorted({e.artifact_name for e in rendered if e.artifact_name})
    return len(rendered), names


def _print_report(
    ref_errors: list[RefError],
    tier2: list[Violation],
    tier3: list[Violation],
    output_path: Path,
    paper_dir: Path,
    strict: bool,
    allow_proposed: bool = False,
) -> None:
    """Print the structured build summary report.

    Args:
        ref_errors: All Tier 1 records collected during resolution.
        tier2: Tier 2 prose-quality violations.
        tier3: Tier 3 style findings.
        output_path: Path the assembled .qmd was written to.
        paper_dir: Paper directory, used to shorten the reported output path.
        strict: Whether Tier 2/3 violations make the build fail.
        allow_proposed: When True, add the AD-028 section listing how many
            proposed Result tokens were rendered and which Results they name.

    Returns:
        None. Writes to stdout.

    Raises:
        Nothing.
    """
    print("=== BUILD REPORT ===\n")

    # Tier 1
    print("TIER 1: Structural Integrity")
    if ref_errors:
        for e in ref_errors:
            flag = "FATAL" if e.fatal else "WARN"
            print(f"  [{e.check_id}] [{flag}] {e.file}:{e.line}: {e.message}")
    else:
        print("  (none)")
    print()

    # AD-028: proposed-render summary. Only meaningful under --allow-proposed;
    # without the flag a proposed Result is fatal and the build never got here.
    if allow_proposed:
        token_count, proposed_names = summarize_proposed(ref_errors)
        print(f"PROPOSED RESULTS RENDERED: {token_count}")
        for pname in proposed_names:
            print(f"  - {pname}")
        print()

    # Tier 2
    n2 = len(tier2)
    print(f"TIER 2: Prose Quality — {n2} violation{'s' if n2 != 1 else ''}")
    if tier2:
        for v in tier2:
            print(f"  [{v.check_id}] {v.file}:{v.line}: {v.message}")
    else:
        print("  (none)")
    print()

    # Tier 3
    n3 = len(tier3)
    print(f"TIER 3: Style — {n3} finding{'s' if n3 != 1 else ''}")
    if tier3:
        for v in tier3:
            print(f"  [{v.check_id}] {v.file}:{v.line}: {v.message}")
    else:
        print("  (none)")
    print()

    # Output path (relative to paper_dir if possible)
    try:
        rel = output_path.relative_to(paper_dir.parent)
        out_str = str(rel)
    except ValueError:
        out_str = str(output_path)
    print(f"Output: {out_str}")

    # Build status
    has_fatal = any(e.fatal for e in ref_errors)
    has_qc_issues = bool(tier2 or tier3)
    if has_fatal or (strict and has_qc_issues):
        print("Build: FAILED")
    else:
        print("Build: SUCCESS")
