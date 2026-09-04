"""
AD-028 Amendment 01: the Result name grammar has exactly one definition point.

The amendment widened the slug grammar to admit uppercase. The reason this file
exists is the *shape* of that change, not its content: before it, the pattern
string was pasted into five places — the constant, a docstring, the
`register --name` help text, the `Result.name` description in
`seldon/domain/research.yaml`, and `docs/conventions/result_units_vocabulary.md`
— so widening the grammar meant finding and editing all five, and missing one
would have left the code enforcing one rule while the docs promised another.

The grep test below makes that failure impossible to commit. It never writes the
pattern itself: it takes the needle from `RESULT_NAME_PATTERN.pattern`, so this
file cannot become the sixth copy it is meant to prevent.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from seldon.commands.result import (
    RESULT_NAME_GRAMMAR_PROSE,
    RESULT_NAME_MAX_LENGTH,
    RESULT_NAME_PATTERN,
    validate_result_name,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

#: The one file allowed to contain the pattern string, relative to the repo root.
DEFINITION_POINT = Path("seldon") / "commands" / "result.py"

#: Directories whose contents are an immutable record of what was decided or
#: done at a past moment, not a statement of what the grammar is now. AD-028 and
#: its amendment necessarily quote BOTH the original and the amended pattern —
#: that is what an amendment is — and the task files and event log record the
#: strings as they stood when they were written. Rewriting history to satisfy a
#: lint is the opposite of an audit trail, so these are exempt by design rather
#: than by oversight.
HISTORICAL_RECORD_DIRS = (
    "docs/design",
    "docs/plans",
    "docs/superpowers",
    "cc_tasks",
    "handoffs",
    "issues",
    "output",
)

#: Directories that hold no authored source at all.
IGNORED_DIRS = (".git", ".claude", "__pycache__", ".pytest_cache",
                ".venv", "venv", "node_modules", ".ruff_cache", ".mypy_cache")

#: Text file types that could plausibly carry a copy of the grammar.
SCANNED_SUFFIXES = {".py", ".yaml", ".yml", ".md", ".toml", ".json", ".txt",
                    ".cfg", ".ini", ".sh", ".rst"}


def _scanned_files() -> list[Path]:
    """Every authored text file that a stray copy of the grammar could hide in.

    Returns:
        Repo-root-relative paths, sorted, excluding history and build noise.
    """
    files: list[Path] = []
    for path in sorted(REPO_ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in SCANNED_SUFFIXES:
            continue
        relative = path.relative_to(REPO_ROOT)
        parts = relative.parts
        if any(part in IGNORED_DIRS for part in parts):
            continue
        posix = relative.as_posix()
        if any(posix.startswith(d + "/") for d in HISTORICAL_RECORD_DIRS):
            continue
        files.append(relative)
    return files


def test_scan_actually_reaches_the_files_it_claims_to():
    """Guard the guard: an empty or tiny scan would make the grep test vacuous."""
    scanned = _scanned_files()
    assert DEFINITION_POINT in scanned
    assert Path("seldon/domain/research.yaml") in scanned
    assert Path("docs/conventions/result_units_vocabulary.md") in scanned
    assert Path("README.md") in scanned
    assert len(scanned) > 100, f"only {len(scanned)} files scanned — too few"


def test_result_name_pattern_appears_in_exactly_one_file():
    """The grammar is defined once. Every other consumer imports the constant.

    The needle comes from the constant itself, so this test tracks the grammar
    automatically: amend the pattern and the test keeps pinning the new one.
    """
    needle = RESULT_NAME_PATTERN.pattern
    hits = {}
    for relative in _scanned_files():
        text = (REPO_ROOT / relative).read_text(encoding="utf-8", errors="replace")
        count = text.count(needle)
        if count:
            hits[relative.as_posix()] = count

    assert hits == {DEFINITION_POINT.as_posix(): 1}, (
        f"The Result name grammar must be written exactly once, in "
        f"{DEFINITION_POINT.as_posix()}. Found: {hits}. Every other place that "
        f"needs to show it must interpolate RESULT_NAME_PATTERN.pattern or "
        f"describe the grammar in words."
    )


def test_the_places_that_used_to_hold_a_copy_now_defer_to_the_constant():
    """The four former copy sites still describe the rule — by reference."""
    research_yaml = (REPO_ROOT / "seldon" / "domain" / "research.yaml").read_text()
    assert "RESULT_NAME_PATTERN" in research_yaml

    conventions = (
        REPO_ROOT / "docs" / "conventions" / "result_units_vocabulary.md"
    ).read_text()
    assert "RESULT_NAME_PATTERN" in conventions

    source = (REPO_ROOT / DEFINITION_POINT).read_text()
    # The --help text and the error message interpolate rather than restate.
    assert "RESULT_NAME_PATTERN.pattern" in source


def test_help_text_shows_the_live_pattern():
    """`register --help` prints whatever the constant currently says."""
    from click.testing import CliRunner

    from seldon.commands.result import result_register

    output = CliRunner().invoke(result_register, ["--help"]).output
    # Click rewraps help text, so compare on whitespace-collapsed output.
    assert RESULT_NAME_PATTERN.pattern in " ".join(output.split())
    assert str(RESULT_NAME_MAX_LENGTH) in output


def test_error_message_names_the_value_and_the_grammar():
    with pytest.raises(ValueError) as exc:
        validate_result_name("no good")
    message = str(exc.value)
    assert "no good" in message
    assert RESULT_NAME_PATTERN.pattern in message
    assert RESULT_NAME_GRAMMAR_PROSE in message


def test_grammar_prose_and_pattern_agree_on_the_boundary_cases():
    """The prose says 'ASCII letter or digit' first; the pattern must too."""
    assert "ASCII letter or digit" in RESULT_NAME_GRAMMAR_PROSE
    assert RESULT_NAME_PATTERN.match("A")
    assert RESULT_NAME_PATTERN.match("z")
    assert RESULT_NAME_PATTERN.match("0")
    assert not RESULT_NAME_PATTERN.match("_a")
    assert not RESULT_NAME_PATTERN.match("-a")
    assert not RESULT_NAME_PATTERN.match(".a")
