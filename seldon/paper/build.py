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
from typing import Optional

from seldon.config import load_project_config, get_neo4j_driver
from seldon.paper.qc import (
    run_tier2,
    run_tier3,
    load_qc_config,
    load_style_config,
    Violation,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REFERENCE_PATTERN = re.compile(r'\{\{(result|figure|cite):([^:}]+):([^}]+)\}\}')

TYPE_TO_REFTYPE = {
    "Result": "result",
    "Figure": "figure",
    "Citation": "cite",
}

REFTYPE_TO_TYPE = {v: k for k, v in TYPE_TO_REFTYPE.items()}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class RefError:
    check_id: str   # SI-01, SI-02, SI-03, SI-07, SI-08
    file: str
    line: int
    token: str      # the original {{...}} token
    message: str
    fatal: bool     # True = build aborts; False = warning only


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
# Reference resolution
# ---------------------------------------------------------------------------

def resolve_references(
    text: str,
    artifacts: dict,
    filename: str,
    bib_path: Optional[Path] = None,
    paper_dir: Optional[Path] = None,
) -> tuple[str, list[RefError]]:
    """
    Replace {{type:name:field}} tokens with artifact values.
    Returns (resolved_text, errors).

    Tier 1 checks during resolution:
    - SI-01: artifact not found → fatal
    - SI-02: artifact.state == "stale" → fatal
    - SI-03: Result artifact.state == "proposed" → fatal
    - SI-07: cite token, bib_path provided, bibtex_key not in bib content → fatal
    - SI-08: figure token, paper_dir provided, figure path field not a real file → fatal

    On error: leave original token in text, record error.
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
        if reftype == "result" and state == "proposed":
            errors.append(RefError(
                check_id="SI-03",
                file=filename,
                line=lineno,
                token=token,
                message=f"Result '{key}' is proposed (not yet verified)",
                fatal=True,
            ))
            return token

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

        return str(value)

    resolved = REFERENCE_PATTERN.sub(_replace, text)
    return resolved, errors


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
) -> int:
    """
    Full build pipeline. Returns exit code (0=success, 1=fatal errors).

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

    # 3. Discover sections
    sections_dir = paper_dir / "sections"
    section_files = sorted(sections_dir.glob("*.md")) if sections_dir.exists() else []

    # 4. Load artifacts from graph
    driver = get_neo4j_driver(config)
    try:
        artifacts = load_named_artifacts(driver, database)
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
        resolved, errors = resolve_references(
            text=text,
            artifacts=artifacts,
            filename=section_file.name,
            bib_path=bib_path,
            paper_dir=paper_dir,
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
    if frontmatter_path.exists():
        frontmatter_content = frontmatter_path.read_text(encoding="utf-8").rstrip()
        parts.append(frontmatter_content)

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
    _print_report(
        ref_errors=all_ref_errors,
        tier2=tier2_violations,
        tier3=tier3_violations,
        output_path=output_path,
        paper_dir=paper_dir,
        strict=strict,
    )

    # 13. Return code
    if strict and (tier2_violations or tier3_violations):
        return 1
    return 0


def _print_report(
    ref_errors: list[RefError],
    tier2: list[Violation],
    tier3: list[Violation],
    output_path: Path,
    paper_dir: Path,
    strict: bool,
) -> None:
    """Print the structured build summary report."""
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
